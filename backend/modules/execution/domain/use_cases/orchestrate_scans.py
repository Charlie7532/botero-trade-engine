import logging
from datetime import datetime, UTC
from backend.modules.execution.domain.use_cases.orchestrate_paper_trading import PaperTradingOrchestrator

logger = logging.getLogger(__name__)

class ScanOrchestrator:
    """
    Orquesta los escaneos Core y Tactical usando el PaperTradingOrchestrator
    para verificar límites de cuenta y ejecutar las órdenes.
    """
    
    def __init__(self, paper_orchestrator: PaperTradingOrchestrator):
        self.orchestrator = paper_orchestrator

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

    def run_core_scan(
        self,
        max_positions: int = 5,
        notional_per_trade: float = 8000.0,
        guru_mcp_data: dict = None,
        macro_mcp_data: dict = None,
        sector_mcp_data: dict = None,
    ) -> dict:
        """
        ===================================================================
        MODO CHRISTOPHER HOHN (80% DEL CAPITAL)
        ===================================================================
        1. Obtiene S&P500 + Joyas de GuruFocus.
        2. Consulta la caché fundamental (MongoDB) antes de golpear APIs.
        3. UniverseFilter evalúa la CALIDAD SUPREMA con datos frescos.
        4. Pasa los ganadores estrictos al AlphaScanner para timing de entrada.
        5. Compra con Strategy: CORE.
        """
        from backend.modules.portfolio_management.domain.use_cases.filter_universe import UniverseFilter
        from backend.modules.portfolio_management.domain.entities.universe_candidate import UniverseCandidate
        from backend.modules.portfolio_management.domain.use_cases.scan_alpha import AlphaScanner

        session_start = datetime.now(UTC).isoformat()
        logger.info(f"🏛️ INICIANDO ESCANEO CORE (Hohn Modo) — {session_start}")

        # 1. Chequeo de Account
        account = self.orchestrator.get_account_status()
        if 'error' in account: return {"error": account['error']}

        # Validamos si cabe otro core trade ($8000 en 80%) o si excedemos límite
        if account.get("core_exposure", 0) / max(account.get("equity", 1), 1) >= 0.80:
            logger.warning("🚫 Escaneo Core Anulado: Bucket CORE Lleno al 80%.")
            return {"status": "BUCKET_FULL"}

        current_positions = len(account.get('positions', []))
        slots_available = max(0, max_positions - current_positions)
        if slots_available == 0: return {"status": "PORTFOLIO_FULL"}

        # 2. Reclutar Candidatos (S&P500 + Guru Gems)
        sp500 = self.get_sp500_universe()
        guru_gems = self.extract_guru_gems(guru_mcp_data)
        raw_tickers = list(set(sp500 + guru_gems))
        logger.info(f"🔍 Evaluando Universo ESTRUCTURAL: {len(raw_tickers)} activos (SP500 + Guru).")

        # 2.5. Inicializar caché fundamental (MongoDB)
        cache = None
        cache_hits = 0
        cache_misses = 0
        try:
            from backend.infrastructure.data_providers.fundamental_cache import FundamentalCache
            cache = FundamentalCache()
        except Exception as e:
            logger.warning(f"Caché fundamental no disponible: {e}. Continuando sin caché.")

        # 3. Flujo HOHN: Primero filtramos la CALIDAD ESTRUCTURAL
        uf = UniverseFilter()
        if macro_mcp_data: uf.update_macro_regime(macro_mcp_data)
        
        # Filtraremos simulando Candidates, etiquetando Gemas
        # y enriqueciendo con datos de la caché si están disponibles
        base_candidates = []
        sp500_set = set(sp500)
        for t in raw_tickers:
            is_gem = t not in sp500_set
            candidate = UniverseCandidate(ticker=t, sector="Unknown", is_emerging_gem=is_gem)
            
            # Intentar enriquecer desde la caché
            if cache:
                cached = cache.get_cached_data(t)
                if cached and cached.get("status") == "fresh":
                    data = cached.get("data", {})
                    candidate.qgarp_score = data.get("qgarp_score", 0.0)
                    candidate.piotroski_f_score = data.get("piotroski_f_score", 0)
                    candidate.altman_z_score = data.get("altman_z_score", 0.0)
                    candidate.guru_conviction_score = data.get("guru_conviction_score", 0.0)
                    candidate.insider_conviction_score = data.get("insider_conviction_score", 0.0)
                    candidate.fcf_margin = data.get("fcf_margin", 0.0)
                    candidate.price_to_gf_value = data.get("price_to_gf_value", 0.0)
                    candidate.beneish_m_score = data.get("beneish_m_score", -3.0)
                    candidate.guru_accumulation = data.get("guru_accumulation", False)
                    cache_hits += 1
                else:
                    cache_misses += 1
            
            base_candidates.append(candidate)
        
        if cache:
            logger.info(f"💾 Caché: {cache_hits} hits, {cache_misses} misses de {len(raw_tickers)} tickers.")
        
        strong_candidates = uf.filter_and_rank(
            base_candidates,
            sector_mcp_data=sector_mcp_data,
            max_results=slots_available * 3, # Nos quedamos con la crema de la crema
        )

        if not strong_candidates:
            return {"status": "NO_CORE_CANDIDATES"}

        # 4. AlphaScanner (Tactical Entry sobre los fuertes fundamentales)
        strong_tickers = [c.ticker for c in strong_candidates]
        logger.info(f"🏢 Hohn seleccionó The Elite {len(strong_tickers)}. Buscando táctica con Eifert...")

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
            logger.info(f"📝 Orden CORE para {ticker} (Alpha={score})")
            res = self.orchestrator.open_position(
                ticker=ticker,
                thesis=f"Moat Confirmado. Alpha Timing Score: {score}",
                strategy_type="CORE",
                alpha_score=score,
                notional=notional_per_trade,
            )
            trades_attempted.append(res)
            
        return {"status": "CORE_SCAN_COMPLETE", "trades": trades_attempted}

    def run_tactical_scan(
        self,
        max_positions: int = 5,
        notional_per_trade: float = 2000.0, 
        finviz_movers_data: dict = None,
        macro_mcp_data: dict = None,
    ) -> dict:
        """
        ===================================================================
        MODO TACTICAL EIFERT/TUDOR JONES (20% DEL CAPITAL)
        ===================================================================
        Busca momentum direccional puro y asimetrías de opciones.
        Ignora calidades profundas, busca la acción del mercado de hoy.
        """
        from backend.modules.portfolio_management.domain.use_cases.scan_alpha import AlphaScanner
        from backend.modules.portfolio_management.domain.use_cases.filter_universe import UniverseFilter
        from backend.modules.portfolio_management.domain.entities.universe_candidate import UniverseCandidate

        logger.info(f"🔥 INICIANDO ESCANEO TÁCTICO (Eifert Modo)")
        
        account = self.orchestrator.get_account_status()
        if 'error' in account: return {"error": account['error']}

        if account.get("tactical_exposure", 0) / max(account.get("equity", 1), 1) >= 0.20:
            logger.warning("🚫 Escaneo Táctico Anulado: Bucket TACTICAL Lleno al 20%.")
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
        approved = uf.filter_and_rank(candidates, max_results=slots_available) # Podríamos relajar filtros aquí luego

        trades_attempted = []
        for candidate in approved:
            ticker = candidate.ticker
            score = candidate.alpha_score
            logger.info(f"📝 Orden TACTICAL para {ticker} (Alpha={score})")
            res = self.orchestrator.open_position(
                ticker=ticker,
                thesis=f"Gamma Squeeze/ Momentum Surge hoy. Alpha: {score}",
                strategy_type="TACTICAL",
                alpha_score=score,
                notional=notional_per_trade,
            )
            trades_attempted.append(res)
            
        return {"status": "TACTICAL_SCAN_COMPLETE", "trades": trades_attempted}
