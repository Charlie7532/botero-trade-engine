import logging
from datetime import datetime, UTC
from backend.modules.execution.application.use_cases.orchestrate_paper_trading import PaperTradingOrchestrator
from backend.modules.portfolio_management.application.use_cases.cio_orchestrator import CIOOrchestrator

logger = logging.getLogger(__name__)

class ScanOrchestrator:
    """
    Orquesta los escaneos Quality y Speculative usando el PaperTradingOrchestrator
    para verificar límites de cuenta y ejecutar las órdenes, guiado por el CIO.
    """
    
    def __init__(
        self, 
        paper_orchestrator: PaperTradingOrchestrator,
        cio_orchestrator: CIOOrchestrator = None
    ):
        self.orchestrator = paper_orchestrator
        self.cio = cio_orchestrator or CIOOrchestrator()

    def get_sp500_universe(self) -> list[str]:
        """Extrae el universo completo del S&P500 desde Wikipedia (o fallback amplio)."""
        try:
            import pandas as pd
            # Intento dinámico de obtener las 500
            table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
            tickers = table[0]['Symbol'].str.replace('.', '-', regex=False).tolist()
            return tickers
        except Exception as e:
            logger.warning(f"No se pudo descargar S&P500 de Wikipedia: {e}. Usando fallback.")
            return ['AAPL','MSFT','NVDA','AMZN','GOOGL','META','BRK-B','TSLA','LLY','JPM',
                    'UNH','V','XOM','JNJ','MA','PG','COST','HD','AVGO','ABBV',
                    'MRK','CVX','CRM','AMD','PEP','KO','ADBE','WMT','TMO','MCD',
                    'ACN','ORCL','LIN','CSCO','PM','ABT','IBM','GE','CAT','ISRG',
                    'NOW','TXN','QCOM','INTU','BKNG','SPGI','HON','AXP','COP','BA']

    def extract_guru_gems(self, guru_mcp_data: dict) -> list[str]:
        """Extrae mid/large caps fuera del SP500 fuertemente acumuladas por Gurús."""
        if not guru_mcp_data: return []
        gems = []
        for ticker, data in guru_mcp_data.items():
            holders = data if isinstance(data, list) else data.get("data", [])
            net_buys = sum(1 for h in holders if "buy" in str(h.get("action","")).lower() or "add" in str(h.get("action","")).lower())
            net_sells = sum(1 for h in holders if "sell" in str(h.get("action","")).lower() or "reduce" in str(h.get("action","")).lower())
            if net_buys > net_sells:
                gems.append(ticker)
        return gems

    def run_quality_scan(
        self,
        max_positions: int = 5,
        notional_per_trade: float = 8000.0,
        guru_mcp_data: dict = None,
        macro_mcp_data: dict = None,
        sector_mcp_data: dict = None,
    ) -> dict:
        """
        ===================================================================
        MODO HOHN & MUNGER — Quality Department
        ===================================================================
        1. Obtiene el mandato del CIO (Presupuesto y Sectores permitidos).
        2. Obtiene S&P500 + Joyas de GuruFocus.
        3. Consulta la caché fundamental (MongoDB) antes de golpear APIs.
        4. UniverseFilter evalúa la CALIDAD SUPREMA con datos frescos.
        5. Pasa los ganadores estrictos al AlphaScanner para timing de entrada.
        6. Compra con Strategy: QUALITY.
        """
        from backend.modules.portfolio_management.application.use_cases.filter_universe import UniverseFilter
        from backend.modules.portfolio_management.domain.entities.universe_candidate import UniverseCandidate
        from backend.modules.portfolio_management.application.use_cases.scan_alpha import AlphaScanner

        session_start = datetime.now(UTC).isoformat()
        logger.info(f"🏛️ INICIANDO ESCANEO QUALITY (Hohn & Munger Modo) — {session_start}")

        # 1. Chequeo de CIO Mandate y Cuenta
        mandate = self.cio.get_current_mandate()
        limit = mandate.quality_budget_pct
        
        account = self.orchestrator.get_account_status()
        if 'error' in account: return {"error": account['error']}

        # Validamos si cabe otro core trade
        exposure = account.get("quality_exposure", 0) / max(account.get("equity", 1), 1)
        if exposure >= limit:
            logger.warning(f"🚫 Escaneo Quality Anulado: Bucket QUALITY Lleno al {limit*100:.0f}% (CIO Mandate).")
            return {"status": "BUCKET_FULL"}

        current_positions = len(account.get('positions', []))
        slots_available = max(0, max_positions - current_positions)
        if slots_available == 0: return {"status": "PORTFOLIO_FULL"}

        # 2. Reclutar Candidatos (S&P500 + Guru Gems)
        sp500 = self.get_sp500_universe()
        guru_gems = self.extract_guru_gems(guru_mcp_data)
        raw_tickers = list(set(sp500 + guru_gems))
        logger.info(f"🔍 Evaluando Universo ESTRUCTURAL: {len(raw_tickers)} activos (SP500 + Guru).")

        # 2.5. Fundamental data — read from vault via adapter
        try:
            from backend.modules.portfolio_management.infrastructure.gurufocus_fundamental_adapter import GuruFocusFundamentalAdapter
            fundamental_adapter = GuruFocusFundamentalAdapter()
        except Exception as e:
            logger.warning(f"Fundamental adapter init failed: {e}")
            fundamental_adapter = None
        cache_hits = 0
        cache_misses = 0

        # 3. Flujo HOHN: Primero filtramos la CALIDAD ESTRUCTURAL
        uf = UniverseFilter()
        if macro_mcp_data: uf.update_macro_regime(macro_mcp_data)
        
        # Filtraremos simulando Candidates, etiquetando Gemas
        # y enriqueciendo con datos del vault si están disponibles
        base_candidates = []
        sp500_set = set(sp500)
        for t in raw_tickers:
            is_gem = t not in sp500_set
            candidate = UniverseCandidate(ticker=t, sector="Unknown", is_emerging_gem=is_gem)
            
            # Enriquecer desde vault fundamental data
            if fundamental_adapter:
                summary = fundamental_adapter.get_financial_summary(t)
                if summary and summary.get("piotroski_f_score"):
                    candidate.piotroski_f_score = summary.get("piotroski_f_score", 0)
                    candidate.altman_z_score = summary.get("altman_z_score", 0.0)
                    candidate.beneish_m_score = summary.get("beneish_m_score", -3.0)
                    candidate.price_to_gf_value = summary.get("price_to_gf_value", 0.0)
                    candidate.fcf_margin = summary.get("net_margin", 0.0)

                    guru = fundamental_adapter.get_guru_analysis(t)
                    if guru:
                        candidate.guru_conviction_score = guru.get("guru_buy_pct", 0.0)
                        candidate.qgarp_score = guru.get("gf_score", 0.0)
                    cache_hits += 1
                else:
                    cache_misses += 1
            
            base_candidates.append(candidate)
        
        if fundamental_adapter:
            logger.info(f"💾 Vault: {cache_hits} hits, {cache_misses} misses de {len(raw_tickers)} tickers.")
        
        strong_candidates = uf.filter_and_rank(
            base_candidates,
            sector_mcp_data=sector_mcp_data,
            max_results=slots_available * 3, # Nos quedamos con la crema de la crema
        )

        if not strong_candidates:
            return {"status": "NO_CORE_CANDIDATES"}

        # 3.5. CIO Sector Vetoes — remove candidates in forbidden sectors
        if mandate.vetoed_sectors:
            pre_veto = len(strong_candidates)
            strong_candidates = [c for c in strong_candidates if c.sector not in mandate.vetoed_sectors]
            vetoed_count = pre_veto - len(strong_candidates)
            if vetoed_count > 0:
                logger.info(f"🚫 CIO Veto: {vetoed_count} candidatos eliminados por sector vetado ({mandate.vetoed_sectors}).")
            if not strong_candidates:
                return {"status": "ALL_VETOED"}

        # 4. AlphaScanner (Tactical Entry sobre los fuertes fundamentales)
        strong_tickers = [c.ticker for c in strong_candidates]
        logger.info(f"🏢 Hohn & Munger seleccionó The Elite {len(strong_tickers)}. Buscando táctica con Eifert...")

        scanner = AlphaScanner()
        alpha_results = scanner.scan(
            tickers=strong_tickers,
            max_results=slots_available,
            include_qualifier=False,
            # No usamos finviz_movers porque Hohn no requiere explosión hoy
        )

        trades_attempted = []
        for result in alpha_results:
            ticker = result['ticker']
            score = result['alpha_score']
            logger.info(f"📝 Orden QUALITY para {ticker} (Alpha={score})")
            res = self.orchestrator.open_position(
                ticker=ticker,
                thesis=f"Moat Confirmado. Alpha Timing Score: {score}",
                strategy_type="QUALITY",
                alpha_score=score,
                notional=notional_per_trade,
            )
            trades_attempted.append(res)
            
        return {"status": "QUALITY_SCAN_COMPLETE", "trades": trades_attempted}

    def run_speculative_scan(
        self,
        max_positions: int = 5,
        notional_per_trade: float = 2000.0, 
        finviz_movers_data: dict = None,
        macro_mcp_data: dict = None,
    ) -> dict:
        """
        ===================================================================
        MODO EIFERT & PTJ — Speculative Department
        ===================================================================
        Busca momentum direccional puro y asimetrías de opciones.
        Respeta implacablemente el presupuesto dictado por el CIO (Ray Dalio).
        """
        from backend.modules.portfolio_management.application.use_cases.scan_alpha import AlphaScanner
        from backend.modules.portfolio_management.application.use_cases.filter_universe import UniverseFilter
        from backend.modules.portfolio_management.domain.entities.universe_candidate import UniverseCandidate

        logger.info(f"🔥 INICIANDO ESCANEO SPECULATIVE (Eifert & PTJ Modo)")
        
        mandate = self.cio.get_current_mandate()
        limit = mandate.speculative_budget_pct
        
        if limit <= 0.0:
            logger.warning("🚫 Escaneo Speculative Anulado: El CIO asignó 0% de presupuesto a tácticas hoy (Risk-Off).")
            return {"status": "CIO_VETO"}
            
        account = self.orchestrator.get_account_status()
        if 'error' in account: return {"error": account['error']}

        exposure = account.get("speculative_exposure", 0) / max(account.get("equity", 1), 1)
        if exposure >= limit:
            logger.warning(f"🚫 Escaneo Speculative Anulado: Bucket SPECULATIVE Lleno al {limit*100:.0f}% (CIO Mandate).")
            return {"status": "BUCKET_FULL"}

        current_positions = len(account.get('positions', []))
        slots_available = max(0, max_positions - current_positions)
        if slots_available == 0: return {"status": "PORTFOLIO_FULL"}

        scanner = AlphaScanner()
        # Escanea FinViz movers (si tickers=None)
        alpha_results = scanner.scan(
            tickers=None, 
            max_results=slots_available * 2,
            finviz_movers_data=finviz_movers_data,
        )

        if not alpha_results: return {"status": "NO_MOVERS"}
        
        # Filtro muy leve (UniverseFilter solo para evitar basuras extremas)
        uf = UniverseFilter()
        if macro_mcp_data: uf.update_macro_regime(macro_mcp_data)
        
        candidates = [UniverseCandidate(ticker=r['ticker'], alpha_score=r['alpha_score']) for r in alpha_results]
        approved = uf.filter_and_rank(candidates, max_results=slots_available)

        # CIO Sector Vetoes
        if mandate.vetoed_sectors:
            pre_veto = len(approved)
            approved = [c for c in approved if c.sector not in mandate.vetoed_sectors]
            vetoed_count = pre_veto - len(approved)
            if vetoed_count > 0:
                logger.info(f"🚫 CIO Veto: {vetoed_count} candidatos especulativos eliminados por sector vetado ({mandate.vetoed_sectors}).")

        trades_attempted = []
        for candidate in approved:
            ticker = candidate.ticker
            score = candidate.alpha_score
            logger.info(f"📝 Orden SPECULATIVE para {ticker} (Alpha={score})")
            res = self.orchestrator.open_position(
                ticker=ticker,
                thesis=f"Gamma Squeeze/ Momentum Surge hoy. Alpha: {score}",
                strategy_type="SPECULATIVE",
                alpha_score=score,
                notional=notional_per_trade,
            )
            trades_attempted.append(res)
            
        return {"status": "SPECULATIVE_SCAN_COMPLETE", "trades": trades_attempted}
