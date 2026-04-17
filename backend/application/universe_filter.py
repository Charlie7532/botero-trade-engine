import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


class MarketRegime(str, Enum):
    """Régimen macroeconómico detectado."""
    RISK_ON = "risk_on"          # VIX < 18, Yield positiva → Cíclicos
    NEUTRAL = "neutral"          # VIX 18-25 → Selectivo
    RISK_OFF = "risk_off"        # VIX > 25 → Defensivos o Cash
    CRISIS = "crisis"            # VIX > 35 → Solo reversión extrema


@dataclass
class UniverseCandidate:
    """Un activo que pasó los filtros y es elegible para la LSTM."""
    ticker: str
    regime: MarketRegime
    sector: str = ""
    relative_momentum: float = 0.0       # Momentum vs SPX
    vix_at_selection: float = 0.0
    guru_accumulation: bool = False       # True si Gurus están comprando
    dcf_discount_pct: float = 0.0         # Descuento vs valor intrínseco
    catalyst_active: bool = False         # Sobrerreacción detectada
    # Opciones & Sentimiento
    max_pain: float = 0.0                 # Max Pain del ticker
    max_pain_distance_pct: float = 0.0    # Distancia precio→MaxPain en %
    put_call_ratio: float = 0.0           # Put/Call OI Ratio
    gex_positive: bool = True             # GEX neto positivo (vol suprimida)
    mm_bias: str = "NEUTRAL"              # BULLISH_PULL / BEARISH_PULL / NEUTRAL
    sentiment_score: float = 50.0         # Score sentimiento 0-100
    sentiment_rating: str = "neutral"     # extreme_fear → extreme_greed
    fear_greed_macro: float = 50.0        # CNN Fear & Greed
    sp500_breadth_pct: float = 50.0       # S5TH proxy
    score: float = 0.0                    # Score compuesto
    selected_at: datetime = field(default_factory=datetime.utcnow)


class MacroRegimeDetector:
    """
    Tier 0: Detecta el régimen macroeconómico usando VIX y Yield Curve.
    
    Opera en dos modos:
    1. Live: Descarga VIX y bonos vía yfinance.
    2. Local: Usa datos precalculados si están disponibles.
    """

    def __init__(self):
        self.vix_level: float = 20.0
        self.yield_spread: float = 0.5
        self.regime: MarketRegime = MarketRegime.NEUTRAL

    def detect_from_market(self) -> MarketRegime:
        """Detecta régimen descargando VIX y Yield Curve actuales."""
        try:
            # VIX
            vix_data = yf.download("^VIX", period="5d", progress=False)
            if not vix_data.empty:
                # Handle multi-level columns from yfinance
                if isinstance(vix_data.columns, pd.MultiIndex):
                    vix_data.columns = vix_data.columns.get_level_values(0)
                self.vix_level = float(vix_data['Close'].iloc[-1])

            # Yield Curve Proxy: 10Y - 2Y
            tny = yf.download("^TNX", period="5d", progress=False)  # 10Y
            twy = yf.download("^IRX", period="5d", progress=False)  # 13W T-Bill

            if not tny.empty and not twy.empty:
                if isinstance(tny.columns, pd.MultiIndex):
                    tny.columns = tny.columns.get_level_values(0)
                if isinstance(twy.columns, pd.MultiIndex):
                    twy.columns = twy.columns.get_level_values(0)
                self.yield_spread = float(
                    tny['Close'].iloc[-1] - twy['Close'].iloc[-1]
                )

            self.regime = self._classify()
            logger.info(
                f"Régimen detectado: {self.regime.value} "
                f"(VIX={self.vix_level:.1f}, YieldSpread={self.yield_spread:.2f})"
            )
            return self.regime

        except Exception as e:
            logger.warning(f"Error detectando régimen macro: {e}. Usando NEUTRAL.")
            self.regime = MarketRegime.NEUTRAL
            return self.regime

    def detect_from_data(self, vix: float, yield_spread: float) -> MarketRegime:
        """Detecta régimen desde datos proporcionados (para backtesting)."""
        self.vix_level = vix
        self.yield_spread = yield_spread
        self.regime = self._classify()
        return self.regime

    def _classify(self) -> MarketRegime:
        """Clasificación basada en umbrales institucionales estándar."""
        if self.vix_level > 35:
            return MarketRegime.CRISIS
        elif self.vix_level > 25:
            return MarketRegime.RISK_OFF
        elif self.vix_level < 18 and self.yield_spread > 0:
            return MarketRegime.RISK_ON
        else:
            return MarketRegime.NEUTRAL


class SectorRanker:
    """
    Tier 1: Ranking de sectores por momentum relativo contra SPX.
    
    Usa los datos locales de la bóveda (.claude/DATA/) para calcular
    fuerza relativa sin depender de APIs externas.
    """

    # Sectores defensivos vs cíclicos
    CYCLICAL = ["XLK", "XLY", "XLI"]
    DEFENSIVE = ["XLRE"]

    def __init__(self, data_dir: str = "/root/botero-trade/.claude/DATA"):
        self.data_dir = data_dir

    def rank_sectors(
        self,
        regime: MarketRegime,
        timeframe: str = "1D",
        lookback: int = 60,
    ) -> list[dict]:
        """
        Calcula momentum relativo de cada sector vs SPX.
        Filtra por régimen macro.
        
        Returns:
            Lista ordenada de sectores con su momentum score.
        """
        import os
        from pathlib import Path

        data_path = Path(self.data_dir)
        spx_file = None
        sector_files = {}

        # Buscar archivos por timeframe
        for folder in data_path.iterdir():
            if not folder.is_dir():
                continue
            ticker = folder.name
            for f in folder.glob(f"*{timeframe}*"):
                if ticker == "SPX":
                    spx_file = f
                else:
                    sector_files[ticker] = f

        if spx_file is None:
            logger.warning("No se encontró SPX para ranking. Retornando todos.")
            return [{"ticker": t, "momentum": 0.0, "eligible": True} for t in sector_files]

        # Cargar SPX
        spx_df = pd.read_csv(spx_file)
        spx_df.columns = [c.strip() for c in spx_df.columns]
        spx_close = spx_df['close'].values

        rankings = []
        for ticker, path in sector_files.items():
            try:
                df = pd.read_csv(path)
                df.columns = [c.strip() for c in df.columns]
                close = df['close'].values

                # Ajustar longitudes
                min_len = min(len(close), len(spx_close))
                if min_len < lookback + 1:
                    continue

                # Momentum relativo: Log(Sector/SPX) últimos N períodos
                ratio = close[-min_len:] / spx_close[-min_len:]
                momentum = np.log(ratio[-1] / ratio[-lookback]) if ratio[-lookback] > 0 else 0

                # Filtrar por régimen
                is_cyclical = ticker in self.CYCLICAL
                eligible = True
                if regime == MarketRegime.RISK_OFF and is_cyclical:
                    eligible = False  # En Risk-Off, no operar cíclicos
                elif regime == MarketRegime.CRISIS:
                    eligible = False  # En crisis, solo reversiones extremas

                rankings.append({
                    "ticker": ticker,
                    "momentum": float(momentum),
                    "eligible": eligible,
                    "type": "cyclical" if is_cyclical else "defensive",
                })
            except Exception as e:
                logger.warning(f"Error procesando {ticker}: {e}")

        # Ordenar por momentum descendente
        rankings.sort(key=lambda x: x["momentum"], reverse=True)
        return rankings


class FundamentalFilter:
    """
    Tier 2: Filtro fundamental vía GuruFocus MCP.
    
    Define la interfaz para consultar:
    - Acumulación de Gurus (13F Buy/Add)
    - Descuento vs Valor Intrínseco (DCF)
    - Insider buying
    
    Los datos reales vienen del MCP Server de GuruFocus.
    Este módulo define QUÉ preguntar y CÓMO interpretar las respuestas.
    """

    @staticmethod
    def evaluate_guru_signals(guru_picks: list[dict]) -> dict:
        """
        Evalúa señales de acumulación institucional desde datos de GuruFocus.
        
        Args:
            guru_picks: Lista de picks del MCP (get_guru_picks response).
            
        Returns:
            Dict con métricas de acumulación por ticker.
        """
        accumulation = {}
        for pick in guru_picks:
            symbol = pick.get("symbol", "")
            action = pick.get("action", "").lower()

            if symbol not in accumulation:
                accumulation[symbol] = {
                    "buys": 0, "sells": 0, "adds": 0,
                    "reduces": 0, "net_signal": 0,
                }

            if action in ("buy", "new buy"):
                accumulation[symbol]["buys"] += 1
                accumulation[symbol]["net_signal"] += 2
            elif action == "add":
                accumulation[symbol]["adds"] += 1
                accumulation[symbol]["net_signal"] += 1
            elif action == "reduce":
                accumulation[symbol]["reduces"] += 1
                accumulation[symbol]["net_signal"] -= 1
            elif action in ("sell", "sold out"):
                accumulation[symbol]["sells"] += 1
                accumulation[symbol]["net_signal"] -= 2

        return accumulation

    @staticmethod
    def evaluate_valuation(summary: dict) -> float:
        """
        Calcula el descuento porcentual vs valor intrínseco.
        
        Args:
            summary: Respuesta del MCP get_stock_summary.
            
        Returns:
            Descuento en %. Positivo = infravalorado. Negativo = sobrevalorado.
        """
        price = summary.get("price", 0)
        intrinsic = summary.get("intrinsic_value", 0)

        if intrinsic and intrinsic > 0 and price and price > 0:
            return ((intrinsic - price) / intrinsic) * 100
        return 0.0


class CatalystDetector:
    """
    Tier 3: Detector de sobrerreacciones y catalizadores.
    
    Usa Finviz MCP para screening y datos de precio para detectar
    caídas irracionales en activos con fundamentales sólidos.
    """

    @staticmethod
    def detect_overreaction(
        close_series: pd.Series,
        lookback: int = 20,
        threshold_std: float = 2.5,
    ) -> dict:
        """
        Detecta si un activo sufrió una caída superior a N desviaciones
        estándar en los últimos M períodos.
        
        Returns:
            Dict con is_overreaction, magnitude, y z_score.
        """
        if len(close_series) < lookback + 1:
            return {"is_overreaction": False, "magnitude": 0, "z_score": 0}

        returns = np.log(close_series / close_series.shift(1)).dropna()
        recent_return = returns.iloc[-1]
        mean_ret = returns.iloc[-lookback:].mean()
        std_ret = returns.iloc[-lookback:].std()

        if std_ret < 1e-10:
            return {"is_overreaction": False, "magnitude": 0, "z_score": 0}

        z_score = (recent_return - mean_ret) / std_ret

        return {
            "is_overreaction": z_score < -threshold_std,
            "magnitude": float(recent_return),
            "z_score": float(z_score),
        }


class UniverseFilter:
    """
    Pipeline Master: Combina los 3 Tiers para producir un universo filtrado.
    
    Tier 0 (Macro): ¿Qué régimen de mercado estamos?
    Tier 1 (Sector): ¿Qué sectores tienen momentum relativo favorable?
    Tier 2 (Fundamental): ¿Qué activos están siendo acumulados por Gurus?
    Tier 3 (Catalizador): ¿Hay sobrerreacciones explotables?
    
    Output: Lista rankeada de UniverseCandidate para la LSTM.
    """

    def __init__(self, data_dir: str = "/root/botero-trade/.claude/DATA"):
        self.macro = MacroRegimeDetector()
        self.sector_ranker = SectorRanker(data_dir)
        self.fundamental = FundamentalFilter()
        self.catalyst = CatalystDetector()
        # Opciones & Breadth
        self._options = None
        self._breadth = None

    def _init_options(self):
        if self._options is None:
            from backend.infrastructure.data_providers.options_awareness import OptionsAwareness
            self._options = OptionsAwareness()

    def _init_breadth(self):
        if self._breadth is None:
            from backend.infrastructure.data_providers.market_breadth import MarketBreadthProvider
            self._breadth = MarketBreadthProvider()

    def filter_universe(
        self,
        guru_picks: list[dict] = None,
        stock_summaries: dict = None,
        use_live_macro: bool = True,
        vix_override: float = None,
        yield_override: float = None,
        include_options: bool = False,
        include_breadth: bool = False,
    ) -> list[UniverseCandidate]:
        """
        Ejecuta el pipeline completo de filtrado.
        
        Args:
            guru_picks: Datos del MCP GuruFocus (opcional).
            stock_summaries: Dict {ticker: summary} del MCP (opcional).
            use_live_macro: Si True, descarga VIX/Yields en vivo.
            vix_override: VIX manual para backtesting.
            yield_override: Yield spread manual para backtesting.
            
        Returns:
            Lista de candidatos elegibles, rankeados por score compuesto.
        """
        logger.info("=" * 60)
        logger.info("UNIVERSE FILTER: Iniciando pipeline de 3 Tiers")
        logger.info("=" * 60)

        # ── TIER 0: Macro Regime ──
        if vix_override is not None:
            regime = self.macro.detect_from_data(
                vix_override, yield_override or 0.5
            )
        elif use_live_macro:
            regime = self.macro.detect_from_market()
        else:
            regime = MarketRegime.NEUTRAL

        logger.info(f"Tier 0 → Régimen: {regime.value} (VIX={self.macro.vix_level:.1f})")

        # ── TIER 1: Sector Ranking ──
        rankings = self.sector_ranker.rank_sectors(regime)
        eligible_sectors = [r for r in rankings if r["eligible"]]
        logger.info(
            f"Tier 1 → {len(eligible_sectors)}/{len(rankings)} sectores elegibles"
        )

        # ── TIER 2: Fundamental (si hay datos de MCP) ──
        guru_signals = {}
        if guru_picks:
            guru_signals = self.fundamental.evaluate_guru_signals(guru_picks)
            logger.info(f"Tier 2 → {len(guru_signals)} tickers con señal de Gurus")

        # ── TIER OPTIONS: Opciones & Sentimiento (si solicitado) ──
        breadth_data = None
        fear_greed_data = None
        capitulation_signal = None

        if include_breadth:
            self._init_breadth()
            fear_greed_data = self._breadth.get_fear_greed_index()
            breadth_data = self._breadth.get_sp500_breadth()

            s5tw = breadth_data.get('pct_above_20dma', 'N/A')
            s5th = breadth_data.get('pct_above_200dma', 'N/A')
            logger.info(
                f"Tier Breadth → F&G: {fear_greed_data.get('score', 'N/A'):.1f} "
                f"({fear_greed_data.get('rating', '?')}), "
                f"S5TH: {s5th}%, S5TW: {s5tw}%"
            )

            # ── CAPITULATION DETECTOR ──
            capitulation_signal = self._breadth.detect_capitulation(
                vix=self.macro.vix_level,
                breadth_data=breadth_data,
            )

            # En capitulación nivel 3+, reactivar TODOS los sectores
            # (en crisis genuina, los fundamentales sólidos caen injustamente)
            if capitulation_signal["capitulation_level"] >= 3:
                eligible_sectors = rankings  # Todo el universo se abre
                for s in eligible_sectors:
                    s["eligible"] = True
                logger.warning(
                    f"🔥 CAPITULACIÓN NIVEL {capitulation_signal['capitulation_level']}: "
                    f"Reabriendo TODOS los sectores. "
                    f"Retorno esperado 60d: +{capitulation_signal['expected_60d_return_pct']:.1f}%"
                )

        # ── Construir Candidatos ──
        candidates = []
        for sector in eligible_sectors:
            ticker = sector["ticker"]

            candidate = UniverseCandidate(
                ticker=ticker,
                regime=regime,
                sector=sector.get("type", ""),
                relative_momentum=sector["momentum"],
                vix_at_selection=self.macro.vix_level,
            )

            # Enriquecer con fundamentales si disponibles
            if ticker in guru_signals:
                net = guru_signals[ticker]["net_signal"]
                candidate.guru_accumulation = net > 0

            if stock_summaries and ticker in stock_summaries:
                candidate.dcf_discount_pct = self.fundamental.evaluate_valuation(
                    stock_summaries[ticker]
                )

            # Enriquecer con Opciones (Max Pain, PCR, GEX)
            if include_options:
                self._init_options()
                try:
                    opt = self._options.get_full_analysis(ticker)
                    candidate.max_pain = opt.get("max_pain", 0) or 0
                    candidate.max_pain_distance_pct = opt.get("max_pain_distance_pct", 0)
                    candidate.put_call_ratio = opt.get("put_call_ratio", 0) or 0
                    candidate.mm_bias = opt.get("mm_bias", "NEUTRAL")
                    if opt.get("gex"):
                        candidate.gex_positive = opt["gex"].get("gex_positive", True)
                    logger.info(
                        f"  {ticker} Options → MP=${candidate.max_pain} "
                        f"(dist={candidate.max_pain_distance_pct:+.1f}%), "
                        f"PCR={candidate.put_call_ratio:.2f}, "
                        f"MM={candidate.mm_bias}"
                    )
                except Exception as e:
                    logger.warning(f"Error opciones {ticker}: {e}")

            # Enriquecer con Sentimiento compuesto por ticker
            if include_breadth:
                self._init_breadth()
                opt_data = {
                    "put_call_ratio": candidate.put_call_ratio,
                    "max_pain_distance_pct": candidate.max_pain_distance_pct,
                    "gex": {"gex_positive": candidate.gex_positive},
                } if include_options else None
                sentiment = self._breadth.compute_ticker_sentiment(
                    ticker, options_data=opt_data,
                    breadth_data=breadth_data, fear_greed=fear_greed_data,
                )
                candidate.sentiment_score = sentiment["sentiment_score"]
                candidate.sentiment_rating = sentiment["rating"]
                candidate.fear_greed_macro = fear_greed_data.get("score", 50)
                candidate.sp500_breadth_pct = breadth_data.get("pct_above_200dma", 50) or 50

            # Score compuesto
            candidate.score = self._compute_score(candidate)
            candidates.append(candidate)

        # Ordenar por score descendente
        candidates.sort(key=lambda c: c.score, reverse=True)

        logger.info(f"Universe Filter → {len(candidates)} candidatos finales")
        for c in candidates:
            opt_str = ""
            if include_options:
                opt_str = f" | MP_dist={c.max_pain_distance_pct:+.1f}% | PCR={c.put_call_ratio:.2f}"
            sent_str = ""
            if include_breadth:
                sent_str = f" | Sent={c.sentiment_score:.0f}({c.sentiment_rating})"
            logger.info(
                f"  {c.ticker:>6} | Score={c.score:.2f} | "
                f"Mom={c.relative_momentum:+.4f} | "
                f"Guru={'✅' if c.guru_accumulation else '—'}"
                f"{opt_str}{sent_str} | "
                f"Regime={c.regime.value}"
            )

        return candidates

    def _compute_score(self, c: UniverseCandidate) -> float:
        """
        Score compuesto ponderado.
        Factores: Momentum, Gurus, DCF, Catalizador, Options, Sentimiento.
        """
        score = 0.0

        # Momentum relativo (peso: 25%)
        score += c.relative_momentum * 25.0

        # Acumulación de Gurus (peso: 20%)
        if c.guru_accumulation:
            score += 20.0

        # Descuento DCF (peso: 15%)
        if c.dcf_discount_pct > 20:
            score += min(c.dcf_discount_pct * 0.5, 15.0)

        # Catalizador activo (peso: 10%)
        if c.catalyst_active:
            score += 10.0

        # Options: Market Maker Bias (peso: 15%)
        if c.mm_bias == "BULLISH_PULL":
            score += 15.0  # Precio debajo de Max Pain → MMs empujan arriba
        elif c.mm_bias == "BEARISH_PULL":
            score -= 10.0  # Precio arriba de Max Pain → presión bajista

        # Sentimiento contrarian (peso: 15%)
        # Score bajo = fear = oportunidad para value investor
        if c.sentiment_score < 30:
            score += 15.0  # Extreme fear = buy signal
        elif c.sentiment_score > 80:
            score -= 10.0  # Extreme greed = cautela

        return score
