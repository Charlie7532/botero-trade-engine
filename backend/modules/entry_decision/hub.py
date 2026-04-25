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
from dataclasses import asdict
from datetime import datetime, date, UTC
from typing import Optional
from modules.entry_decision.models import EntryIntelligenceReport

logger = logging.getLogger(__name__)


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
        # Módulos de decisión (from modules/)
        from modules.flow_intelligence.whale_engine import EventFlowIntelligence
        from modules.price_analysis.phase_engine import PricePhaseIntelligence
        from modules.flow_intelligence.persistence_engine import FlowPersistenceAnalyzer
        from modules.volume_intelligence.profile_engine import VolumeProfileAnalyzer

        self.event_flow = EventFlowIntelligence()
        self.price_phase = PricePhaseIntelligence()
        self.flow_persistence = FlowPersistenceAnalyzer()
        self.volume_profile = VolumeProfileAnalyzer()
        self._rsi_intel = None             # RSIIntelligence (lazy)

        from application.trade_journal import TradeJournal
        self.journal = TradeJournal()

        # Módulos de datos vivos (existentes)
        self._options = None
        self._kalman = None
        self._uw = None
        self._pattern = None           # PatternRecognitionIntelligence (lazy)
        self._uw_data_cache = {}  # Pre-fetched UW data from MCP
        self._spy_cache = None     # Cached SPY data for RS calculation (avoid 500 downloads)
        self._spy_cache_date = None

    # ── Lazy init de módulos costosos ───────────────────────────

    def _get_options(self):
        if self._options is None:
            try:
                from modules.options_gamma.options_engine import OptionsAwareness
                self._options = OptionsAwareness()
                logger.info("EntryHub: OptionsAwareness conectado ✅")
            except Exception as e:
                logger.warning(f"EntryHub: OptionsAwareness NO disponible: {e}")
        return self._options

    def _get_kalman(self):
        if self._kalman is None:
            try:
                from modules.volume_intelligence.kalman_engine import KalmanVolumeTracker
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

    def _get_pattern(self):
        if self._pattern is None:
            try:
                from modules.pattern_recognition.pattern_engine import PatternRecognitionIntelligence
                self._pattern = PatternRecognitionIntelligence()
                logger.info("EntryHub: PatternRecognitionIntelligence conectado ✅")
            except Exception as e:
                logger.warning(f"EntryHub: PatternRecognitionIntelligence NO disponible: {e}")
        return self._pattern

    def inject_uw_data(
        self,
        spy_ticks: list[dict] = None,
        flow_alerts: list[dict] = None,
        tide_data: list[dict] = None,
        recent_flow: list[dict] = None,
        darkpool_prints: list[dict] = None,
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
            "recent_flow": recent_flow or [],
            "darkpool_prints": darkpool_prints or [],
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
        strategy_bucket: str = "CORE",  # "CORE" or "TACTICAL"
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
        report.whale_last_updated = flow.get("last_updated")

        # ══════════════════════════════════════════════════════
        # STEP 4b: Flow Persistence Analyzer (V7)
        # ══════════════════════════════════════════════════════
        recent_flow = self._uw_data_cache.get("recent_flow", [])
        darkpool_prints = self._uw_data_cache.get("darkpool_prints", [])
        persistence = self.flow_persistence.evaluate_persistence(
            ticker=ticker,
            recent_flow=recent_flow,
            darkpool_prints=darkpool_prints,
            current_price=report.current_price,
            price_history=prices['Close'].tolist() if prices is not None else [],
            reference_date=reference_date
        )
        report.flow_persistence_grade = persistence.persistence_grade
        report.flow_freshness_weight = persistence.freshness_weight
        report.flow_consecutive_days = persistence.consecutive_days
        report.flow_darkpool_confirmed = persistence.darkpool_aligned
        report.flow_hours_since_latest = persistence.hours_since_latest

        # Early exit if DEAD_SIGNAL
        if persistence.persistence_grade == "DEAD_SIGNAL":
            report.final_verdict = "BLOCK"
            report.final_scale = 0.0
            report.final_reason = f"BLOCK: DEAD_SIGNAL — Options flow is {persistence.hours_since_latest:.1f} hours old (decayed)."
            logger.info(f"EntryHub {ticker}: BLOCKED by DEAD_SIGNAL")
            return report

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

        # Early exit if CONTRA_FLOW — but TACTICAL gets a pass if momentum is strong
        if whale_verdict.verdict == "CONTRA_FLOW":
            if strategy_bucket == "TACTICAL":
                # Tactical: Log warning but DON'T block. Let PricePhase decide.
                logger.info(f"EntryHub {ticker}: CONTRA_FLOW detected but TACTICAL bucket — passing to phase analysis")
                report.whale_verdict = "CONTRA_FLOW_TACTICAL"  # Mark it
            else:
                report.final_verdict = "BLOCK"
                report.final_scale = 0.0
                report.final_reason = f"CONTRA_FLOW: {whale_verdict.diagnosis[:100]}"
                logger.info(f"EntryHub {ticker}: BLOCKED by CONTRA_FLOW")
                return report

        # ══════════════════════════════════════════════════════
        # STEP 5.5: Volume Profile (Institutional Levels)
        # ══════════════════════════════════════════════════════
        try:
            vp_result = self.volume_profile.compute(prices)
            report.vp_poc_short = vp_result.short.poc
            report.vp_vah_short = vp_result.short.vah
            report.vp_val_short = vp_result.short.val
            report.vp_poc_long = vp_result.long.poc
            report.vp_vah_long = vp_result.long.vah
            report.vp_val_long = vp_result.long.val
            report.vp_shape_short = vp_result.short.shape
            report.vp_shape_long = vp_result.long.shape
            report.vp_poc_migration = vp_result.poc_migration
            report.vp_institutional_bias = vp_result.institutional_bias
            report.vp_bias_confidence = vp_result.bias_confidence
            report.vp_price_vs_va = vp_result.short.current_vs_va
            report.vp_diagnosis = vp_result.diagnosis
            logger.info(
                f"EntryHub {ticker}: VP Short={vp_result.short.shape}(POC=${vp_result.short.poc:.2f}) "
                f"Long={vp_result.long.shape}(POC=${vp_result.long.poc:.2f}) "
                f"Migration={vp_result.poc_migration} Bias={vp_result.institutional_bias}"
            )
        except Exception as e:
            logger.warning(f"EntryHub {ticker}: Volume Profile error: {e}")
            vp_result = None

        # ══════════════════════════════════════════════════════
        # STEP 5.6: Institutional Bias Gate (V9 — from VP)
        # ══════════════════════════════════════════════════════
        # CORE: Block if VP shows DISTRIBUTION with high confidence
        if (strategy_bucket == "CORE"
                and report.vp_institutional_bias == "DISTRIBUTION"
                and report.vp_bias_confidence >= 75):
            report.final_verdict = "STALK"
            report.final_scale = 0.0
            report.final_reason = (
                f"VP_DISTRIBUTION_GATE: Institucionales distribuyendo "
                f"(conf={report.vp_bias_confidence:.0f}%, shapes={report.vp_shape_short}/{report.vp_shape_long}, "
                f"POC migration={report.vp_poc_migration}). No entrar CORE."
            )
            logger.info(f"EntryHub {ticker}: BLOCKED by VP Distribution Gate")
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
            strategy_bucket=strategy_bucket,
            vp_result=vp_result,
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
        # STEP 6b: PatternRecognitionIntelligence (4ª Dimensión)
        # ══════════════════════════════════════════════════════
        pattern_eng = self._get_pattern()
        if pattern_eng is not None:
            try:
                pv = pattern_eng.detect(
                    prices=prices,
                    put_wall=report.put_wall,
                    call_wall=report.call_wall,
                    ticker=ticker,
                )
                report.candlestick_pattern = pv.primary_pattern
                report.pattern_sentiment = pv.sentiment
                report.pattern_score = pv.confirmation_score
                report.pattern_on_support = pv.detected_on_support
                report.pattern_diagnosis = pv.diagnosis

                # ¿El patrón confirma la fase actual?
                bullish_phases = {
                    "CORRECTION", "BREAKOUT", "EXHAUSTION_DOWN",
                    "CONTRARIAN_DIP", "MOMENTUM_CONTINUATION"
                }
                bearish_phases = {"EXHAUSTION_UP", "STEALTH_DISTRIBUTION"}

                report.pattern_confirms = (
                    (pv.sentiment == "BULLISH" and report.phase in bullish_phases)
                    or (pv.sentiment == "BEARISH" and report.phase in bearish_phases)
                    or (pv.is_inside_bar_series and report.phase in {"CORRECTION", "CONSOLIDATION"})
                    or (pv.is_vcp_tight and report.phase in {"CORRECTION", "CONSOLIDATION"})
                )

                # Sumar la 4ª dimensión al conteo
                if report.pattern_confirms:
                    report.dimensions_confirming += 1

                logger.info(
                    f"EntryHub {ticker}: Pattern={pv.primary_pattern} "
                    f"sentiment={pv.sentiment} score={pv.confirmation_score:+.2f} "
                    f"confirms={report.pattern_confirms} "
                    f"→ dims_total={report.dimensions_confirming}"
                )
            except Exception as e:
                logger.warning(f"EntryHub: PatternIntelligence error for {ticker}: {e}")

        # ══════════════════════════════════════════════════════
        # STEP 6c: RSI Intelligence (Cardwell/Brown Regime-Aware)
        # ══════════════════════════════════════════════════════
        try:
            if self._rsi_intel is None:
                from modules.price_analysis.rsi_engine import RSIIntelligence
                self._rsi_intel = RSIIntelligence()

            close_arr = prices['Close'].values.astype(float)
            # Use VP institutional bias as regime hint
            regime_map = {
                'ACCUMULATION': 'BULL', 'DISTRIBUTION': 'BEAR', 'NEUTRAL': 'NEUTRAL'
            }
            regime_hint = regime_map.get(report.vp_institutional_bias, 'NEUTRAL')

            rsi_result = self._rsi_intel.analyze(close_arr, regime_hint=regime_hint)

            report.rsi_regime = rsi_result.rsi_regime
            report.rsi_zone = rsi_result.rsi_zone
            report.rsi_divergence = rsi_result.divergence_type
            report.rsi_divergence_strength = rsi_result.divergence_strength
            report.rsi_price_slope = rsi_result.price_slope
            report.rsi_indicator_slope = rsi_result.rsi_slope
            report.rsi_slope_alignment = rsi_result.slope_alignment
            report.rsi_conviction = rsi_result.rsi_conviction
            report.rsi_diagnosis = rsi_result.diagnosis

            logger.info(
                f"EntryHub {ticker}: RSI_Intel regime={rsi_result.rsi_regime} "
                f"zone={rsi_result.rsi_zone} div={rsi_result.divergence_type} "
                f"conviction={rsi_result.rsi_conviction:+.2f}"
            )
        except Exception as e:
            logger.warning(f"EntryHub: RSIIntelligence error for {ticker}: {e}")

        # ══════════════════════════════════════════════════════
        # STEP 7: Dictamen Final
        # ══════════════════════════════════════════════════════
        if phase_verdict.verdict == "ABORT":
            report.final_verdict = "BLOCK"
            report.final_scale = 0.0
            report.final_reason = f"ABORT: {phase_verdict.phase} — {phase_verdict.diagnosis[:80]}"

        elif phase_verdict.verdict == "FIRE":
            # ── Forensic Quality Gates (V10 — Cardwell Regime-Aware RSI) ────
            # V9 had static RSI 35-65 which blocked valid continuation trades.
            # V10: Use RSI zone classification — block only hostile zones.
            hostile_rsi_zones = {"BOUNCE_SELL", "EXTREME_BULL", "EXTREME_BEAR", "OVERBOUGHT"}
            if strategy_bucket == "CORE" and report.rsi_zone in hostile_rsi_zones:
                report.final_verdict = "STALK"
                report.final_scale = 0.0
                report.final_reason = (
                    f"QUALITY_GATE_V10: CORE entry in hostile RSI zone={report.rsi_zone} "
                    f"(regime={report.rsi_regime}, RSI={report.rsi:.0f}). "
                    f"Conviction={report.rsi_conviction:+.2f}. STALK."
                )
                logger.info(f"EntryHub {ticker}: QUALITY_GATE_V10 blocked zone={report.rsi_zone}")
                return report

            # ── Pattern Gate (V8) ─────────────────────────────────
            # VETO: patrón bajista cancela FIRE → STALK
            if report.pattern_sentiment == "BEARISH" and report.pattern_score <= -0.5:
                report.final_verdict = "STALK"
                report.final_scale = 0.0
                report.final_reason = (
                    f"PATTERN_VETO: {report.candlestick_pattern} (score={report.pattern_score:+.2f}) "
                    f"cancela FIRE. {phase_verdict.phase} requiere confirmación visual."
                )
                logger.info(f"EntryHub {ticker}: PATTERN_VETO → STALK ({report.candlestick_pattern})")
                return report

            # V7: Pre-Trade Memory Query
            vector = self._vectorize_report(report)
            similar_trades = self.journal.find_similar_trades(vector, limit=5)

            # Analizar si los similares fracasaron
            bad_luck = 0
            for t in similar_trades:
                if not t.get("was_winner", False) and "grade" in t:
                    bad_luck += 1

            if len(similar_trades) >= 3 and bad_luck / len(similar_trades) >= 0.8:
                report.final_verdict = "BLOCK"
                report.final_scale = 0.0
                report.final_reason = "BLOCK: Vector DB Query — 80%+ de setups históricos similares fracasaron sin edge."
                logger.warning(f"EntryHub {ticker}: BLOCKED by Vector Memory! Evitando error histórico.")
            else:
                report.final_verdict = "EXECUTE"
                base_scale = whale_verdict.position_scale

                # AMPLIFY: patrón alcista en soporte institucional → +25% escala
                if (report.pattern_sentiment == "BULLISH"
                        and report.pattern_on_support
                        and report.pattern_score >= 0.5):
                    base_scale = min(1.0, base_scale * 1.25)
                    logger.info(
                        f"EntryHub {ticker}: PATTERN_AMPLIFY → scale {whale_verdict.position_scale:.0%} "
                        f"→ {base_scale:.0%} ({report.candlestick_pattern} en soporte)"
                    )

                report.final_scale = base_scale
                report.final_reason = (
                    f"FIRE: {phase_verdict.phase}, R:R={phase_verdict.risk_reward_ratio}:1, "
                    f"Whale={whale_verdict.verdict}, Dims={report.dimensions_confirming}, "
                    f"Pattern={report.candlestick_pattern}"
                )

        elif phase_verdict.verdict == "STALK":
            # ── Pattern PROMOTE: patrón fuerte puede elevar STALK → FIRE ──
            if (report.pattern_sentiment == "BULLISH"
                    and report.pattern_score >= 0.7
                    and report.dimensions_confirming >= 2
                    and report.risk_reward >= 3.0):
                report.final_verdict = "EXECUTE"
                report.final_scale = whale_verdict.position_scale * 0.75  # Escala reducida
                report.final_reason = (
                    f"PATTERN_PROMOTE: {report.candlestick_pattern} (score={report.pattern_score:+.2f}) "
                    f"eleva STALK → FIRE. R:R={report.risk_reward}:1, Dims={report.dimensions_confirming}."
                )
                logger.info(f"EntryHub {ticker}: PATTERN_PROMOTE → EXECUTE ({report.candlestick_pattern})")
            else:
                report.final_verdict = "STALK"
                report.final_scale = 0.0
                report.final_reason = (
                    f"STALK: {phase_verdict.phase}, R:R={phase_verdict.risk_reward_ratio}:1, "
                    f"Dims={report.dimensions_confirming} — esperando mejor setup"
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
    # V8: VECTORIZATION (9 dimensiones — incluye pattern_score)
    # ═══════════════════════════════════════════════════════════
    def _vectorize_report(self, report: EntryIntelligenceReport) -> list[float]:
        """
        Convierte las variables críticas del reporte en un vector para búsqueda.
        9 dimensiones (V8): agrega pattern_score para mejor recall en Atlas VS.

        ⚠️ NOTA: Si hay vectores de 8D en Atlas, reindexar la colección antes
        de activar esta versión (dimensión incompatible).
        """
        return [
            float(report.vix),
            float(report.rsi),
            float(report.rs_vs_spy),
            1.0 if report.gamma_regime == "POSITIVE" else -1.0,
            float(report.whale_confidence),
            float(report.phase_confidence),
            float(report.risk_reward),
            float(report.flow_persistence_grade == "CONFIRMED_STREAK"),
            float(report.pattern_score),  # Dim 9: sentimiento visual (-1.0 → +1.0)
        ]

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
        """Calcula RS vs SPY 20d. Uses cache to avoid repeated downloads."""
        try:
            today = date.today()
            if self._spy_cache is None or self._spy_cache_date != today:
                spy = yf.download('SPY', period='3mo', interval='1d', progress=False)
                if isinstance(spy.columns, pd.MultiIndex):
                    spy.columns = spy.columns.get_level_values(0)
                self._spy_cache = spy
                self._spy_cache_date = today
            spy = self._spy_cache
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
                result["spy_updated"] = gate.last_updated

            # Parse Market Tide
            tide_data = self._uw_data_cache.get("tide_data", [])
            if tide_data:
                tide = uw.parse_market_tide(tide_data)
                result["tide_direction"] = tide.tide_direction
                result["tide_accelerating"] = tide.is_accelerating
                result["tide_net_premium"] = tide.cum_net_premium
                result["tide_updated"] = tide.last_updated

            # Parse Flow Alerts for ticker sweeps
            flow_alerts = self._uw_data_cache.get("flow_alerts", [])
            if flow_alerts:
                flow = uw.parse_flow_alerts(ticker, flow_alerts)
                result["total_sweeps"] = flow.n_sweeps
                result["sweep_call_pct"] = (
                    flow.n_calls / (flow.n_calls + flow.n_puts) * 100
                    if (flow.n_calls + flow.n_puts) > 0 else 50.0
                )
                result["flow_updated"] = flow.last_updated

                # Market sentiment for breadth
                sentiment = uw.parse_market_sentiment(flow_alerts)
                result["sentiment_regime"] = sentiment.regime
                result["breadth_pct"] = sentiment.breadth_pct

        except Exception as e:
            logger.warning(f"EntryHub: UW Intelligence error: {e}")

        # Get latest timestamp from parsed elements
        timestamps = [result.get(k) for k in ["spy_updated", "tide_updated", "flow_updated"] if result.get(k)]
        if timestamps:
            result["last_updated"] = max(timestamps)

        return result
