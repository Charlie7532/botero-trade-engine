"""
ENTRY INTELLIGENCE HUB — El Puente que Conecta Todas las Piezas
================================================================
"Los componentes individuales son órganos.
 Este módulo es el sistema nervioso que los conecta."

Este hub orquesta la comunicación entre los módulos existentes y los
nuevos módulos de inteligencia de entrada:

  DATOS VIVOS (Módulos Existentes):
    options_awareness.py → put_wall, call_wall, gamma_regime
    volume_dynamics.py   → wyckoff_state, velocity (Kalman)
    uw_intelligence.py   → spy_macro_gate, market_tide, sweeps

  MÓDULOS DE DECISIÓN (Nuevos):
    event_flow_intelligence.py → WhaleVerdict (RIDE/LEAN/UNCERTAIN/CONTRA)
    price_phase_intelligence.py → EntryVerdict (FIRE/STALK/ABORT)
    portfolio_intelligence.py → GammaAwareStop (Put Wall, VIX, Freeze)

  OUTPUT:
    EntryIntelligenceReport — El dictamen final con todos los datos
    para que el orquestador decida si entra o no.
"""
import logging
import yfinance as yf
import pandas as pd
import numpy as np
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, UTC
from typing import Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# REPORT DATACLASS
# ═══════════════════════════════════════════════════════════════

@dataclass
class EntryIntelligenceReport:
    """Reporte unificado de inteligencia para decisión de entrada."""
    ticker: str
    timestamp: str = ""

    # ── EventFlowIntelligence ──────────────────────────────────
    whale_verdict: str = "UNKNOWN"       # RIDE_THE_WHALES, LEAN_WITH_FLOW, UNCERTAIN, CONTRA_FLOW
    whale_scale: float = 1.0
    whale_confidence: float = 0.0
    whale_diagnosis: str = ""
    nearest_event: str = ""
    hours_to_event: float = 999.0
    freeze_stops: bool = False
    freeze_duration_min: int = 0

    # ── PricePhaseIntelligence ─────────────────────────────────
    phase: str = "UNKNOWN"               # CORRECTION, BREAKOUT, EXHAUSTION_UP/DOWN, CONSOLIDATION
    phase_verdict: str = "STALK"         # FIRE, STALK, ABORT
    entry_price: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    risk_reward: float = 0.0
    dimensions_confirming: int = 0
    phase_confidence: float = 0.0
    phase_diagnosis: str = ""

    # ── Datos Vivos (fuentes) ──────────────────────────────────
    current_price: float = 0.0
    vix: float = 17.0
    rs_vs_spy: float = 1.0
    atr: float = 0.0
    rsi: float = 50.0
    rvol: float = 1.0

    # Gamma (from options_awareness)
    put_wall: float = 0.0
    call_wall: float = 0.0
    gamma_regime: str = "UNKNOWN"
    max_pain: float = 0.0

    # Wyckoff (from volume_dynamics)
    wyckoff_state: str = "UNKNOWN"
    wyckoff_velocity: float = 0.0

    # Whale Flow (from uw_intelligence)
    spy_cum_delta: float = 0.0
    spy_signal: str = "NEUTRAL"
    sweep_call_pct: float = 50.0
    total_sweeps: int = 0
    tide_direction: str = "NEUTRAL"
    tide_accelerating: bool = False
    am_pm_divergence: bool = False

    # ── Dictamen Final ─────────────────────────────────────────
    final_verdict: str = "PASS"          # EXECUTE, STALK, PASS, BLOCK
    final_scale: float = 0.0            # 0-1
    final_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════
# MAIN HUB
# ═══════════════════════════════════════════════════════════════

class EntryIntelligenceHub:
    """
    Hub central que conecta TODOS los subsistemas de inteligencia
    para producir un veredicto unificado de entrada.

    Uso:
        hub = EntryIntelligenceHub()
        report = hub.evaluate("NVDA")
        if report.final_verdict == "EXECUTE":
            # Proceder con la orden
            limit_price = report.entry_price
            stop = report.stop_price
    """

    def __init__(self):
        # Módulos de decisión (nuevos)
        from infrastructure.data_providers.event_flow_intelligence import EventFlowIntelligence
        from application.price_phase_intelligence import PricePhaseIntelligence

        self.event_flow = EventFlowIntelligence()
        self.price_phase = PricePhaseIntelligence()

        # Módulos de datos vivos (existentes)
        self._options = None
        self._kalman = None
        self._uw = None
        self._uw_data_cache = {}  # Pre-fetched UW data from MCP

    # ── Lazy init de módulos costosos ───────────────────────────

    def _get_options(self):
        if self._options is None:
            try:
                from infrastructure.data_providers.options_awareness import OptionsAwareness
                self._options = OptionsAwareness()
                logger.info("EntryHub: OptionsAwareness conectado ✅")
            except Exception as e:
                logger.warning(f"EntryHub: OptionsAwareness NO disponible: {e}")
        return self._options

    def _get_kalman(self):
        if self._kalman is None:
            try:
                from infrastructure.data_providers.volume_dynamics import KalmanVolumeTracker
                self._kalman = KalmanVolumeTracker()
                logger.info("EntryHub: KalmanVolumeTracker conectado ✅")
            except Exception as e:
                logger.warning(f"EntryHub: KalmanVolumeTracker NO disponible: {e}")
        return self._kalman

    def _get_uw(self):
        if self._uw is None:
            try:
                from infrastructure.data_providers.uw_intelligence import UnusualWhalesIntelligence
                self._uw = UnusualWhalesIntelligence()
                logger.info("EntryHub: UnusualWhalesIntelligence conectado ✅")
            except Exception as e:
                logger.warning(f"EntryHub: UnusualWhalesIntelligence NO disponible: {e}")
        return self._uw

    def inject_uw_data(
        self,
        spy_ticks: list[dict] = None,
        flow_alerts: list[dict] = None,
        tide_data: list[dict] = None,
    ):
        """
        Inyecta datos pre-obtenidos de Unusual Whales (via MCP).
        El orchestrador llama esto ANTES de evaluate().

        UW sigue el patrón MCP: el orquestador obtiene los datos crudos
        y este hub los parsea con uw_intelligence.py.
        """
        self._uw_data_cache = {
            "spy_ticks": spy_ticks or [],
            "flow_alerts": flow_alerts or [],
            "tide_data": tide_data or [],
        }

    # ═══════════════════════════════════════════════════════════
    # MAIN EVALUATE
    # ═══════════════════════════════════════════════════════════

    def evaluate(
        self,
        ticker: str,
        reference_date: Optional[date] = None,
        # Pre-computed data (optional — if not provided, we'll fetch)
        prices_df: pd.DataFrame = None,
        vix_override: float = None,
    ) -> EntryIntelligenceReport:
        """
        Evaluación completa de inteligencia para un ticker.

        Conecta TODOS los módulos:
        1. Descarga precio 3 meses (yfinance)
        2. Consulta opciones (OptionsAwareness)
        3. Calcula Wyckoff (KalmanVolumeTracker)
        4. Lee flujo de ballenas (UW Intelligence)
        5. Ejecuta EventFlowIntelligence
        6. Ejecuta PricePhaseIntelligence
        7. Emite dictamen final

        Returns:
            EntryIntelligenceReport con todo el contexto y dictamen.
        """
        report = EntryIntelligenceReport(
            ticker=ticker,
            timestamp=datetime.now(UTC).isoformat(),
        )

        # ══════════════════════════════════════════════════════
        # STEP 1: Datos de Precio (yfinance)
        # ══════════════════════════════════════════════════════
        if prices_df is not None:
            prices = prices_df
        else:
            prices = self._fetch_prices(ticker)

        if prices is None or prices.empty:
            report.final_verdict = "PASS"
            report.final_reason = "No se pudieron obtener datos de precio"
            return report

        # Normalize columns
        if isinstance(prices.columns, pd.MultiIndex):
            prices.columns = prices.columns.get_level_values(0)

        report.current_price = float(prices['Close'].iloc[-1])
        report.atr = float((prices['High'] - prices['Low']).rolling(14).mean().iloc[-1])

        # VIX
        if vix_override is not None:
            report.vix = vix_override
        else:
            report.vix = self._fetch_vix()

        # RVOL
        avg_vol = float(prices['Volume'].rolling(20).mean().iloc[-1])
        report.rvol = float(prices['Volume'].iloc[-1]) / avg_vol if avg_vol > 0 else 1.0

        # RS vs SPY
        report.rs_vs_spy = self._calc_rs_vs_spy(prices)

        # ══════════════════════════════════════════════════════
        # STEP 2: Opciones — Gamma Regime, Put/Call Walls
        # ══════════════════════════════════════════════════════
        opts = self._fetch_options_data(ticker)
        report.put_wall = opts.get("put_wall", 0.0)
        report.call_wall = opts.get("call_wall", 0.0)
        report.gamma_regime = opts.get("gamma_regime", "UNKNOWN")
        report.max_pain = opts.get("max_pain", 0.0)

        # ══════════════════════════════════════════════════════
        # STEP 3: Volumen — Wyckoff + Kalman
        # ══════════════════════════════════════════════════════
        wyckoff = self._run_kalman(ticker, prices)
        report.wyckoff_state = wyckoff.get("wyckoff_state", "UNKNOWN")
        report.wyckoff_velocity = wyckoff.get("velocity", 0.0)

        # ══════════════════════════════════════════════════════
        # STEP 4: Flujo de Ballenas (UW Intelligence)
        # ══════════════════════════════════════════════════════
        flow = self._parse_whale_flow(ticker)
        report.spy_cum_delta = flow.get("spy_cum_delta", 0.0)
        report.spy_signal = flow.get("spy_signal", "NEUTRAL")
        report.sweep_call_pct = flow.get("sweep_call_pct", 50.0)
        report.total_sweeps = flow.get("total_sweeps", 0)
        report.tide_direction = flow.get("tide_direction", "NEUTRAL")
        report.tide_accelerating = flow.get("tide_accelerating", False)
        report.am_pm_divergence = flow.get("am_pm_divergence", False)

        # ══════════════════════════════════════════════════════
        # STEP 5: EventFlowIntelligence (Calendario + Flujo)
        # ══════════════════════════════════════════════════════
        whale_verdict = self.event_flow.assess(
            reference_date=reference_date,
            spy_cum_delta=report.spy_cum_delta,
            spy_signal=report.spy_signal,
            spy_confidence=flow.get("spy_confidence", 0.5),
            am_pm_diverges=report.am_pm_divergence,
            sweep_call_pct=report.sweep_call_pct,
            total_sweeps=report.total_sweeps,
            sentiment_regime=flow.get("sentiment_regime", "NEUTRAL"),
            tide_direction=report.tide_direction,
            tide_accelerating=report.tide_accelerating,
            tide_net_premium=flow.get("tide_net_premium", 0.0),
            gex_regime=report.gamma_regime,
            gex_net=0.0,
            market_breadth_pct=flow.get("breadth_pct", 50.0),
        )

        report.whale_verdict = whale_verdict.verdict
        report.whale_scale = whale_verdict.position_scale
        report.whale_confidence = whale_verdict.confidence
        report.whale_diagnosis = whale_verdict.diagnosis
        report.freeze_stops = whale_verdict.freeze_stops
        report.freeze_duration_min = whale_verdict.freeze_duration_min
        if whale_verdict.nearest_event:
            report.nearest_event = whale_verdict.nearest_event.name
            report.hours_to_event = whale_verdict.hours_to_event

        # Early exit if CONTRA_FLOW
        if whale_verdict.verdict == "CONTRA_FLOW":
            report.final_verdict = "BLOCK"
            report.final_scale = 0.0
            report.final_reason = f"CONTRA_FLOW: {whale_verdict.diagnosis[:100]}"
            logger.info(f"EntryHub {ticker}: BLOCKED by CONTRA_FLOW")
            return report

        # ══════════════════════════════════════════════════════
        # STEP 6: PricePhaseIntelligence (Timing)
        # ══════════════════════════════════════════════════════
        phase_verdict = self.price_phase.diagnose(
            ticker=ticker,
            prices=prices,
            put_wall=report.put_wall,
            call_wall=report.call_wall,
            gamma_regime=report.gamma_regime,
            wyckoff_state=report.wyckoff_state,
            wyckoff_velocity=report.wyckoff_velocity,
        )

        report.phase = phase_verdict.phase
        report.phase_verdict = phase_verdict.verdict
        report.entry_price = phase_verdict.entry_price
        report.stop_price = phase_verdict.stop_price
        report.target_price = phase_verdict.target_price
        report.risk_reward = phase_verdict.risk_reward_ratio
        report.dimensions_confirming = phase_verdict.dimensions_confirming
        report.phase_confidence = phase_verdict.confidence
        report.phase_diagnosis = phase_verdict.diagnosis
        report.rsi = phase_verdict.rsi14

        # ══════════════════════════════════════════════════════
        # STEP 7: Dictamen Final
        # ══════════════════════════════════════════════════════
        if phase_verdict.verdict == "ABORT":
            report.final_verdict = "BLOCK"
            report.final_scale = 0.0
            report.final_reason = f"ABORT: {phase_verdict.phase} — {phase_verdict.diagnosis[:80]}"

        elif phase_verdict.verdict == "FIRE":
            report.final_verdict = "EXECUTE"
            report.final_scale = whale_verdict.position_scale
            report.final_reason = (
                f"FIRE: {phase_verdict.phase}, R:R={phase_verdict.risk_reward_ratio}:1, "
                f"Whale={whale_verdict.verdict}, Dims={phase_verdict.dimensions_confirming}/3"
            )

        elif phase_verdict.verdict == "STALK":
            report.final_verdict = "STALK"
            report.final_scale = 0.0
            report.final_reason = (
                f"STALK: {phase_verdict.phase}, R:R={phase_verdict.risk_reward_ratio}:1, "
                f"Dims={phase_verdict.dimensions_confirming}/3 — esperando mejor setup"
            )

        else:
            report.final_verdict = "PASS"
            report.final_scale = 0.0
            report.final_reason = "Unknown phase verdict"

        logger.info(
            f"EntryHub {ticker}: {report.final_verdict} "
            f"(whale={report.whale_verdict}, phase={report.phase}, "
            f"R:R={report.risk_reward}:1, scale={report.final_scale:.0%})"
        )

        return report

    # ═══════════════════════════════════════════════════════════
    # STEP IMPLEMENTATIONS
    # ═══════════════════════════════════════════════════════════

    def _fetch_prices(self, ticker: str) -> Optional[pd.DataFrame]:
        """Descarga datos de precio de yfinance."""
        try:
            data = yf.download(ticker, period='3mo', interval='1d', progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            return data if not data.empty else None
        except Exception as e:
            logger.error(f"EntryHub: Error descargando precios de {ticker}: {e}")
            return None

    def _fetch_vix(self) -> float:
        """Obtiene VIX actual."""
        try:
            vix_data = yf.download('^VIX', period='5d', interval='1d', progress=False)
            if isinstance(vix_data.columns, pd.MultiIndex):
                vix_data.columns = vix_data.columns.get_level_values(0)
            return float(vix_data['Close'].iloc[-1]) if not vix_data.empty else 17.0
        except Exception:
            return 17.0

    def _calc_rs_vs_spy(self, prices: pd.DataFrame) -> float:
        """Calcula RS vs SPY 20d."""
        try:
            spy = yf.download('SPY', period='3mo', interval='1d', progress=False)
            if isinstance(spy.columns, pd.MultiIndex):
                spy.columns = spy.columns.get_level_values(0)
            if len(prices) >= 20 and len(spy) >= 20:
                stock_ret = float(prices['Close'].iloc[-1]) / float(prices['Close'].iloc[-20]) - 1
                spy_ret = float(spy['Close'].iloc[-1]) / float(spy['Close'].iloc[-20]) - 1
                return round((1 + stock_ret) / (1 + spy_ret), 4)
        except Exception:
            pass
        return 1.0

    def _fetch_options_data(self, ticker: str) -> dict:
        """Obtiene datos de opciones de OptionsAwareness."""
        opts = self._get_options()
        if opts is None:
            return {}
        try:
            analysis = opts.get_full_analysis(ticker)
            return {
                "put_wall": analysis.get("put_wall", 0.0),
                "call_wall": analysis.get("call_wall", 0.0),
                "gamma_regime": analysis.get("gamma_regime", "UNKNOWN"),
                "max_pain": analysis.get("max_pain", 0.0),
            }
        except Exception as e:
            logger.warning(f"EntryHub: OptionsAwareness error for {ticker}: {e}")
            return {}

    def _run_kalman(self, ticker: str, prices: pd.DataFrame) -> dict:
        """Ejecuta el Kalman tracker sobre los datos de volumen."""
        kalman = self._get_kalman()
        if kalman is None:
            return {}

        try:
            close = prices['Close'].values.astype(float)
            volume = prices['Volume'].values.astype(float)
            avg_vol_20 = pd.Series(volume).rolling(20).mean().values

            # Feed the last 20 bars through Kalman to build state
            result = {}
            for i in range(-20, 0):
                if np.isnan(avg_vol_20[i]) or avg_vol_20[i] <= 0:
                    continue
                rvol = float(volume[i]) / float(avg_vol_20[i])
                change_pct = float(close[i] / close[i - 1] - 1) * 100 if i > -len(close) else 0
                result = kalman.update(ticker, rvol, change_pct=change_pct)

            return result
        except Exception as e:
            logger.warning(f"EntryHub: Kalman error for {ticker}: {e}")
            return {}

    def _parse_whale_flow(self, ticker: str) -> dict:
        """Parsea datos de UW Intelligence de la caché inyectada."""
        uw = self._get_uw()
        if uw is None:
            return {}

        result = {}
        try:
            # Parse SPY Macro Gate
            spy_ticks = self._uw_data_cache.get("spy_ticks", [])
            if spy_ticks:
                gate = uw.parse_spy_macro_gate(spy_ticks)
                result["spy_cum_delta"] = gate.cum_delta
                result["spy_signal"] = gate.signal
                result["spy_confidence"] = gate.confidence
                result["am_pm_divergence"] = gate.am_pm_diverges

            # Parse Market Tide
            tide_data = self._uw_data_cache.get("tide_data", [])
            if tide_data:
                tide = uw.parse_market_tide(tide_data)
                result["tide_direction"] = tide.tide_direction
                result["tide_accelerating"] = tide.is_accelerating
                result["tide_net_premium"] = tide.cum_net_premium

            # Parse Flow Alerts for ticker sweeps
            flow_alerts = self._uw_data_cache.get("flow_alerts", [])
            if flow_alerts:
                flow = uw.parse_flow_alerts(ticker, flow_alerts)
                result["total_sweeps"] = flow.n_sweeps
                result["sweep_call_pct"] = (
                    flow.n_calls / (flow.n_calls + flow.n_puts) * 100
                    if (flow.n_calls + flow.n_puts) > 0 else 50.0
                )

                # Market sentiment for breadth
                sentiment = uw.parse_market_sentiment(flow_alerts)
                result["sentiment_regime"] = sentiment.regime
                result["breadth_pct"] = sentiment.breadth_pct

        except Exception as e:
            logger.warning(f"EntryHub: UW Intelligence error: {e}")

        return result
