"""
SPECULATIVE ENTRY HUB — PTJ, Karsan & Eifert
================================================
Pipeline de decisión de entrada RÁPIDO para trades SPECULATIVE.

3 preguntas, respuesta en <1 segundo:
1. ¿Gamma regime confirma? (Karsan)
2. ¿Flow es unidireccional y persistente? (Eifert)
3. ¿Asimetría ≥ 5:1? (PTJ)

+ Memory Guard: ¿Este setup fracasó históricamente? (Simons)

NO USA: VP largo plazo, RSI hostile zones, fundamental analysis.
"""
import logging
import pandas as pd
import numpy as np
from datetime import datetime, date, UTC
from typing import Optional
from backend.modules.entry_decision.domain.entities.entry_report import EntryIntelligenceReport
from backend.modules.entry_decision.domain.ports.market_data_port import EntryMarketDataPort
from backend.modules.entry_decision.domain.ports.flow_data_port import FlowDataPort
from backend.modules.options_gamma.domain.ports.options_data_port import OptionsDataPort
from backend.modules.shared.domain.entities.indicator_trend import IndicatorTrend

logger = logging.getLogger(__name__)


class SpeculativeEntryHub:
    """
    Hub de entrada para trades SPECULATIVE.

    PTJ: "I'm always thinking about losing money."
    Karsan: "Dealers are forced to hedge. That's not theory, that's mechanics."
    Eifert: "Most GEX signals are noise. Validate with real flow."

    Pipeline rápido, microestructural. Sin fundamentales.
    """

    # PTJ minimum asymmetry
    MIN_RISK_REWARD = 3.0  # Mínimo 3:1, aspiramos 5:1

    def __init__(
        self,
        market_data: EntryMarketDataPort,
        flow_data: FlowDataPort,
        options_provider: OptionsDataPort,
        journal=None,
        blacklist=None,
    ):
        self._market_data = market_data
        self._flow_data = flow_data
        self._options_provider = options_provider
        self.journal = journal  # SPECULATIVE journal (Memory Guard)
        self._blacklist = blacklist

        from backend.modules.flow_intelligence.application.use_cases.analyze_whale_flow import EventFlowIntelligence
        from backend.modules.price_analysis.application.use_cases.detect_price_phase import PricePhaseIntelligence
        from backend.modules.flow_intelligence.application.use_cases.analyze_persistence import FlowPersistenceAnalyzer

        self.event_flow = EventFlowIntelligence()
        self.price_phase = PricePhaseIntelligence()
        self.flow_persistence = FlowPersistenceAnalyzer()

        self._options = None
        self._kalman = None
        self._uw_data_cache = {}

    def inject_uw_data(
        self, spy_ticks=None, flow_alerts=None, tide_data=None,
        recent_flow=None, darkpool_prints=None,
    ):
        """Inyecta datos de Unusual Whales pre-obtenidos via MCP."""
        self._uw_data_cache = {
            "spy_ticks": spy_ticks or [],
            "flow_alerts": flow_alerts or [],
            "tide_data": tide_data or [],
            "recent_flow": recent_flow or [],
            "darkpool_prints": darkpool_prints or [],
        }

    def evaluate(
        self,
        ticker: str,
        reference_date: Optional[date] = None,
        prices_df: pd.DataFrame = None,
        vix_override: float = None,
        vix_trend: Optional[IndicatorTrend] = None,
    ) -> EntryIntelligenceReport:
        """
        Evaluación SPECULATIVE: rápida, microestructural.
        """
        report = EntryIntelligenceReport(
            ticker=ticker,
            timestamp=datetime.now(UTC).isoformat(),
        )

        # ── Gate 0: Blacklist ──
        if self._blacklist and self._blacklist.is_blacklisted(ticker, "SPECULATIVE"):
            report.final_verdict = "BLOCK"
            report.final_scale = 0.0
            report.final_reason = f"BLACKLISTED: {ticker} in SPECULATIVE cooldown"
            return report

        # ── Step 1: Price Data (fast) ──
        prices = prices_df if prices_df is not None else self._market_data.fetch_prices(ticker)
        if prices is None or prices.empty:
            report.final_verdict = "PASS"
            report.final_reason = "No price data"
            return report

        if isinstance(prices.columns, pd.MultiIndex):
            prices.columns = prices.columns.get_level_values(0)

        report.current_price = float(prices['Close'].iloc[-1])
        report.atr = float((prices['High'] - prices['Low']).rolling(14).mean().iloc[-1])
        report.vix = vix_override if vix_override is not None else self._market_data.fetch_vix()
        avg_vol = float(prices['Volume'].rolling(20).mean().iloc[-1])
        report.rvol = float(prices['Volume'].iloc[-1]) / avg_vol if avg_vol > 0 else 1.0
        report.rs_vs_spy = self._market_data.calc_rs_vs_spy(prices)

        # ── Step 2: Gamma Regime (Karsan) ──
        opts = self._fetch_options_data(ticker, vix_trend=vix_trend)
        report.put_wall = opts.get("put_wall", 0.0)
        report.call_wall = opts.get("call_wall", 0.0)
        report.gamma_regime = opts.get("gamma_regime", "UNKNOWN")
        report.max_pain = opts.get("max_pain", 0.0)

        # 8 Forces: Vanna Event + Charm
        report.vanna_event = opts.get("vanna_event", False)
        report.vanna_event_direction = opts.get("vanna_event_direction", "NONE")
        report.charm_direction = opts.get("charm_direction", "NEUTRAL")
        report.opex_proximity = (
            "OPEX_DAY" if opts.get("is_opex_day", False)
            else "48H_PRE_OPEX" if opts.get("opex_time_weight", 0) > 0
            else "NONE"
        )

        # 8 Forces: VIX Trend Context
        if vix_trend:
            report.vix_trend_direction = vix_trend.direction
            report.vix_ma5 = vix_trend.ma5
            report.vix_ma20 = vix_trend.ma20
            report.vix_percentile_90d = vix_trend.percentile_90d

        # ── Step 3: Wyckoff Volume (Kalman) ──
        wyckoff = self._run_kalman(ticker, prices)
        report.wyckoff_state = wyckoff.get("wyckoff_state", "UNKNOWN")
        report.wyckoff_velocity = wyckoff.get("velocity", 0.0)

        # ── Step 4: Flow Intelligence (Eifert validation) ──
        flow = self._parse_whale_flow(ticker)
        report.spy_cum_delta = flow.get("spy_cum_delta", 0.0)
        report.spy_signal = flow.get("spy_signal", "NEUTRAL")
        report.sweep_call_pct = flow.get("sweep_call_pct", 50.0)
        report.total_sweeps = flow.get("total_sweeps", 0)
        report.tide_direction = flow.get("tide_direction", "NEUTRAL")
        report.tide_accelerating = flow.get("tide_accelerating", False)
        report.am_pm_divergence = flow.get("am_pm_divergence", False)

        # ── Step 4b: Flow Persistence (signal freshness) ──
        recent_flow = self._uw_data_cache.get("recent_flow", [])
        darkpool_prints = self._uw_data_cache.get("darkpool_prints", [])
        persistence = self.flow_persistence.evaluate_persistence(
            ticker=ticker, recent_flow=recent_flow, darkpool_prints=darkpool_prints,
            current_price=report.current_price,
            price_history=prices['Close'].tolist() if prices is not None else [],
            reference_date=reference_date,
        )
        report.flow_persistence_grade = persistence.persistence_grade
        report.flow_freshness_weight = persistence.freshness_weight
        report.flow_consecutive_days = persistence.consecutive_days
        report.flow_darkpool_confirmed = persistence.darkpool_aligned
        report.flow_hours_since_latest = persistence.hours_since_latest

        # DEAD_SIGNAL = stale flow, abort
        if persistence.persistence_grade == "DEAD_SIGNAL":
            report.final_verdict = "BLOCK"
            report.final_scale = 0.0
            report.final_reason = f"DEAD_SIGNAL: Flow is {persistence.hours_since_latest:.1f}h old"
            return report

        # ── Step 5: Event Flow (macro context) ──
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
        report.freeze_stops = whale_verdict.freeze_stops

        # SPECULATIVE: CONTRA_FLOW is a warning, not a block
        # PTJ: "Sometimes the best trades are the ones against the crowd"
        if whale_verdict.verdict == "CONTRA_FLOW":
            report.whale_verdict = "CONTRA_FLOW_TACTICAL"
            logger.info(f"SpecHub {ticker}: CONTRA_FLOW detected — passing to phase analysis")

        # ── Step 6: Price Phase (fast timing) ──
        phase_verdict = self.price_phase.diagnose(
            ticker=ticker, prices=prices,
            put_wall=report.put_wall, call_wall=report.call_wall,
            gamma_regime=report.gamma_regime,
            wyckoff_state=report.wyckoff_state,
            wyckoff_velocity=report.wyckoff_velocity,
            strategy_bucket="SPECULATIVE", vp_result=None,
        )
        report.phase = phase_verdict.phase
        report.phase_verdict = phase_verdict.verdict
        report.entry_price = phase_verdict.entry_price
        report.stop_price = phase_verdict.stop_price
        report.target_price = phase_verdict.target_price
        report.risk_reward = phase_verdict.risk_reward_ratio
        report.dimensions_confirming = phase_verdict.dimensions_confirming
        report.phase_confidence = phase_verdict.confidence
        report.rsi = phase_verdict.rsi14

        # ═══ FINAL VERDICT ═══
        if phase_verdict.verdict == "ABORT":
            report.final_verdict = "BLOCK"
            report.final_scale = 0.0
            report.final_reason = f"ABORT: {phase_verdict.phase}"

        elif phase_verdict.verdict == "FIRE":
            # ── Memory Guard (Simons: anti-pattern check) ──
            if self.journal:
                vector = self._vectorize_report(report)
                similar_trades = self.journal.find_similar_trades(vector, limit=5)
                bad_luck = sum(1 for t in similar_trades if not t.get("was_winner", False) and "grade" in t)
                if len(similar_trades) >= 3 and bad_luck / len(similar_trades) >= 0.8:
                    report.final_verdict = "BLOCK"
                    report.final_scale = 0.0
                    report.final_reason = "MEMORY_GUARD: 80%+ similar setups failed historically"
                    logger.warning(f"SpecHub {ticker}: BLOCKED by Memory Guard")
                    return report

            # ── PTJ Asymmetry Gate ──
            if report.risk_reward < self.MIN_RISK_REWARD:
                report.final_verdict = "STALK"
                report.final_scale = 0.0
                report.final_reason = f"ASYMMETRY_GATE: R:R={report.risk_reward:.1f} < {self.MIN_RISK_REWARD}:1"
                return report

            # EXECUTE
            report.final_verdict = "EXECUTE"
            report.final_scale = whale_verdict.position_scale
            report.final_reason = (
                f"FIRE: {phase_verdict.phase}, R:R={report.risk_reward}:1, "
                f"Gamma={report.gamma_regime}, Flow={report.flow_persistence_grade}, "
                f"Dims={report.dimensions_confirming}"
            )

        elif phase_verdict.verdict == "STALK":
            report.final_verdict = "STALK"
            report.final_scale = 0.0
            report.final_reason = f"STALK: {phase_verdict.phase} — waiting for trigger"
        else:
            report.final_verdict = "PASS"
            report.final_scale = 0.0
            report.final_reason = "Unknown phase verdict"

        return report

    # ── Private helpers ──

    def _vectorize_report(self, report: EntryIntelligenceReport) -> list[float]:
        """9D vector for Memory Guard similarity search."""
        return [
            float(report.vix), float(report.rsi), float(report.rs_vs_spy),
            1.0 if report.gamma_regime == "POSITIVE" else -1.0,
            float(report.whale_confidence), float(report.phase_confidence),
            float(report.risk_reward),
            float(report.flow_persistence_grade == "CONFIRMED_STREAK"),
            float(getattr(report, 'pattern_score', 0.0)),
        ]

    def _fetch_options_data(self, ticker: str, vix_trend: Optional[IndicatorTrend] = None) -> dict:
        if self._options is None:
            try:
                from backend.modules.options_gamma.application.use_cases.analyze_gamma import OptionsAwareness
                self._options = OptionsAwareness(self._options_provider)
            except Exception:
                return {}
        try:
            analysis = self._options.get_full_analysis(ticker, vix_trend=vix_trend)
            return analysis
        except Exception:
            return {}

    def _run_kalman(self, ticker: str, prices: pd.DataFrame) -> dict:
        if self._kalman is None:
            try:
                from backend.modules.volume_intelligence.application.use_cases.track_volume_dynamics import KalmanVolumeTracker
                self._kalman = KalmanVolumeTracker()
            except Exception:
                return {}
        try:
            close = prices['Close'].values.astype(float)
            volume = prices['Volume'].values.astype(float)
            avg_vol_20 = pd.Series(volume).rolling(20).mean().values
            result = {}
            for i in range(-20, 0):
                if np.isnan(avg_vol_20[i]) or avg_vol_20[i] <= 0:
                    continue
                rvol = float(volume[i]) / float(avg_vol_20[i])
                change_pct = float(close[i] / close[i - 1] - 1) * 100 if i > -len(close) else 0
                result = self._kalman.update(ticker, rvol, change_pct=change_pct)
            return result
        except Exception:
            return {}

    def _parse_whale_flow(self, ticker: str) -> dict:
        result = {}
        try:
            spy_ticks = self._uw_data_cache.get("spy_ticks", [])
            if spy_ticks:
                gate = self._flow_data.parse_spy_macro_gate(spy_ticks)
                result.update({"spy_cum_delta": gate.cum_delta, "spy_signal": gate.signal, "spy_confidence": gate.confidence, "am_pm_divergence": gate.am_pm_diverges})
            tide_data = self._uw_data_cache.get("tide_data", [])
            if tide_data:
                tide = self._flow_data.parse_market_tide(tide_data)
                result.update({"tide_direction": tide.tide_direction, "tide_accelerating": tide.is_accelerating, "tide_net_premium": tide.cum_net_premium})
            flow_alerts = self._uw_data_cache.get("flow_alerts", [])
            if flow_alerts:
                flow = self._flow_data.parse_flow_alerts(ticker, flow_alerts)
                result["total_sweeps"] = flow.n_sweeps
                result["sweep_call_pct"] = (flow.n_calls / (flow.n_calls + flow.n_puts) * 100 if (flow.n_calls + flow.n_puts) > 0 else 50.0)
                sentiment = self._flow_data.parse_market_sentiment(flow_alerts)
                result.update({"sentiment_regime": sentiment.regime, "breadth_pct": sentiment.breadth_pct})
        except Exception as e:
            logger.warning(f"SpecHub: Whale flow error: {e}")
        return result
