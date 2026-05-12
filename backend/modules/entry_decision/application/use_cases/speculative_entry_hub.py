"""
SPECULATIVE ENTRY HUB — PTJ, Karsan & Eifert
================================================
Pipeline de decisión de entrada RÁPIDO para trades SPECULATIVE.

3 preguntas, respuesta en <1 segundo:
1. ¿Gamma regime confirma? (Karsan)
2. ¿Flow es unidireccional y persistente? (Eifert)
3. ¿Asimetría ≥ 5:1? (PTJ)

+ Memory Guard: ¿Este setup fracasó históricamente? (Simons)

V2: Now integrates VP (short-term), Pattern Recognition, and SMC structure.
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
        self._vp = None       # VolumeProfileAnalyzer (lazy)
        self._pattern = None  # PatternRecognitionIntelligence (lazy)
        self._smc = None      # SMCAdapter (lazy)

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

        # ── Gate -1: Vol Regime (Seykota hunt cycle) ──
        # RETREAT = block (capital preservation). HARVEST = reduce sizing.
        # STRIKE = boost sizing (compression breakout). STALK = normal.
        # Evidence Status: HYPOTHESIS — thresholds need calibration.
        _vol_sizing = 1.0
        try:
            from backend.modules.entry_decision.domain.rules.vol_regime_gate import compute_vol_regime_snapshot
            from backend.modules.volatility_regime.domain.entities.vol_regime import S_RETREAT, S_HARVEST, S_STRIKE

            vix_mean_90d = 20.0  # HYPOTHESIS
            vix_std_90d = 5.0    # HYPOTHESIS
            vix_z = (report.vix - vix_mean_90d) / vix_std_90d if vix_std_90d > 0 else 0.0

            regime = compute_vol_regime_snapshot(prices, vix_zscore=vix_z)
            report.vol_regime_quality = regime.quality_label
            report.vol_regime_speculative = regime.speculative_label

            if regime.speculative_regime == S_RETREAT:
                report.final_verdict = "BLOCK"
                report.final_scale = 0.0
                report.final_reason = (
                    f"VOL_REGIME_GATE: RETREAT regime detected "
                    f"(VIX={report.vix:.1f}, z={vix_z:+.1f}). "
                    f"Speculative: vol chaotic — protect capital."
                )
                logger.warning(f"SpecHub {ticker}: BLOCKED by VOL_REGIME RETREAT")
                return report

            if regime.speculative_regime == S_HARVEST:
                _vol_sizing = 0.5  # Move is maturing, don't chase
                report.alerts = report.alerts or []
                report.alerts.append(
                    f"VOL_REGIME_HARVEST: Sizing reduced — "
                    f"move is maturing, ride don't chase."
                )

            if regime.speculative_regime == S_STRIKE:
                _vol_sizing = 1.25  # Compression breakout — Seykota's edge
                report.alerts = report.alerts or []
                report.alerts.append(
                    f"VOL_REGIME_STRIKE: Compression breakout detected — "
                    f"sizing boosted to 125%."
                )

            logger.info(
                f"SpecHub {ticker}: Vol regime Q={regime.quality_label} "
                f"S={regime.speculative_label} sizing={_vol_sizing:.0%}"
            )
        except Exception as e:
            logger.debug(f"SpecHub: Vol regime gate skipped: {e}")

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
        # Flow data is now read from Vault inside get_flow_signal, but persistence needs history
        # For now, we will assume FlowPersistenceAnalyzer can fetch its own data or we pass empty
        # to rely on its internal mechanisms if any, or we fetch from Vault.
        try:
            from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
            store = TimescaleDataStore()
            recent_flow = store.load_mcp_latest("flow/alerts", ticker) or []
            darkpool_prints = store.load_mcp_latest("flow/darkpool", ticker) or []
            store.close()
        except Exception:
            recent_flow = []
            darkpool_prints = []

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

        # ── Step 5b: Volume Profile (short-term institutional levels) ──
        vp_result = self._run_volume_profile(prices)

        # ── Step 6: Price Phase (fast timing — now VP-aware) ──
        phase_verdict = self.price_phase.diagnose(
            ticker=ticker, prices=prices,
            put_wall=report.put_wall, call_wall=report.call_wall,
            gamma_regime=report.gamma_regime,
            wyckoff_state=report.wyckoff_state,
            wyckoff_velocity=report.wyckoff_velocity,
            strategy_bucket="SPECULATIVE", vp_result=vp_result,
        )

        # ── Step 6b: Pattern Recognition (4th Dimension — visual confirmation) ──
        pattern = self._run_pattern(prices, ticker, report.put_wall, report.call_wall)
        report.candlestick_pattern = pattern.get("primary_pattern", "NONE")
        report.pattern_sentiment = pattern.get("sentiment", "NEUTRAL")
        report.pattern_score = pattern.get("score", 0.0)
        report.pattern_on_support = pattern.get("on_support", False)

        # ── Step 6c: SMC Structure Filter (BOS, CHoCH, Order Blocks) ──
        smc = self._run_smc(prices)
        report.smc_swing_trend = smc.swing_trend
        report.smc_bos_direction = smc.bos_direction
        report.smc_choch_detected = smc.choch_detected
        report.smc_choch_direction = smc.choch_direction
        report.smc_ob_price = smc.nearest_ob_price
        report.smc_fvg_active = smc.fvg_active
        report.smc_liquidity_swept = smc.liquidity_swept
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

        # Pattern VETO: strong bearish candle formation cancels FIRE
        # (Pending walk-forward validation — currently acts as a safety downgrade)
        if report.pattern_sentiment == "BEARISH" and report.pattern_score <= -0.5:
            if phase_verdict.verdict == "FIRE":
                phase_verdict.verdict = "STALK"
                report.alerts = report.alerts or []
                report.alerts.append(f"PATTERN_VETO: {report.candlestick_pattern} suggests caution")
                logger.info(f"SpecHub {ticker}: PATTERN_VETO {report.candlestick_pattern} → STALK")

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
            report.final_scale = min(1.0, whale_verdict.position_scale * _vol_sizing)
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
        """13D vector for Memory Guard similarity search (V2: +SMC/VP structure).

        ⚠️ MIGRATION: If pgvector index has 9D vectors, they must be backfilled
        with [0.0, 0.0, 0.0, 0.0] or reindexed before this version activates.
        """
        # Compute POC distance if VP data is available
        poc_distance_pct = 0.0
        if hasattr(report, 'vp_poc_short') and report.vp_poc_short and report.current_price:
            poc_distance_pct = (report.current_price - report.vp_poc_short) / report.current_price * 100

        return [
            # Original 9D
            float(report.vix), float(report.rsi), float(report.rs_vs_spy),
            1.0 if report.gamma_regime == "POSITIVE" else -1.0,
            float(report.whale_confidence), float(report.phase_confidence),
            float(report.risk_reward),
            float(report.flow_persistence_grade == "CONFIRMED_STREAK"),
            float(getattr(report, 'pattern_score', 0.0)),
            # New 4D: SMC + VP structure
            1.0 if getattr(report, 'smc_bos_direction', 'NONE') == "BULLISH" else (-1.0 if getattr(report, 'smc_bos_direction', 'NONE') == "BEARISH" else 0.0),
            float(getattr(report, 'smc_ob_price', 0.0)) / max(float(report.current_price), 1.0) if report.current_price else 0.0,
            poc_distance_pct,
            1.0 if getattr(report, 'smc_fvg_active', False) else 0.0,
        ]

    def _fetch_options_data(self, ticker: str, vix_trend: Optional[IndicatorTrend] = None) -> dict:
        if self._options is None:
            try:
                from backend.modules.options_gamma.application.use_cases.analyze_gamma import OptionsAwareness
                self._options = OptionsAwareness(self._options_provider)
            except Exception:
                return {}
        try:
            return self._options.get_full_analysis(ticker, vix_trend=vix_trend)
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

    def _run_volume_profile(self, prices: pd.DataFrame):
        """Run short-term Volume Profile analysis."""
        if self._vp is None:
            try:
                from backend.modules.volume_intelligence.application.use_cases.analyze_volume_profile import VolumeProfileAnalyzer
                self._vp = VolumeProfileAnalyzer()
            except Exception:
                return None
        try:
            return self._vp.analyze_dual(prices)
        except Exception:
            return None

    def _run_pattern(self, prices: pd.DataFrame, ticker: str, put_wall: float, call_wall: float) -> dict:
        """Run Pattern Recognition Intelligence."""
        if self._pattern is None:
            try:
                from backend.modules.pattern_recognition.application.use_cases.detect_patterns import PatternRecognitionIntelligence
                self._pattern = PatternRecognitionIntelligence()
            except Exception:
                return {}
        try:
            v = self._pattern.detect(prices, put_wall=put_wall, call_wall=call_wall, ticker=ticker)
            return {
                "primary_pattern": v.primary_pattern,
                "sentiment": v.sentiment,
                "score": v.confirmation_score,
                "on_support": v.detected_on_support,
            }
        except Exception:
            return {}

    def _run_smc(self, prices: pd.DataFrame):
        """Run Smart Money Concepts structural analysis."""
        if self._smc is None:
            try:
                from backend.modules.simulation.infrastructure.smc_adapter import SMCAdapter
                self._smc = SMCAdapter()
            except Exception:
                from backend.modules.shared.domain.ports.market_structure_port import MarketStructureResult
                return MarketStructureResult()
        try:
            return self._smc.analyze(prices)
        except Exception:
            from backend.modules.shared.domain.ports.market_structure_port import MarketStructureResult
            return MarketStructureResult()

    def _parse_whale_flow(self, ticker: str) -> dict:
        result = {}
        try:
            gate = self._flow_data.get_macro_gate()
            result.update({
                "spy_cum_delta": gate.cum_delta, 
                "spy_signal": gate.signal, 
                "spy_confidence": gate.confidence, 
                "am_pm_divergence": gate.am_pm_diverges
            })
            
            tide = self._flow_data.get_market_tide()
            result.update({
                "tide_direction": tide.tide_direction, 
                "tide_accelerating": tide.is_accelerating, 
                "tide_net_premium": tide.cum_net_premium
            })
            
            flow = self._flow_data.get_flow_signal(ticker)
            result["total_sweeps"] = flow.n_sweeps
            result["sweep_call_pct"] = (flow.n_calls / (flow.n_calls + flow.n_puts) * 100 if (flow.n_calls + flow.n_puts) > 0 else 50.0)
            
            sentiment = self._flow_data.get_market_sentiment()
            result.update({
                "sentiment_regime": sentiment.regime, 
                "breadth_pct": sentiment.breadth_pct
            })
        except Exception as e:
            logger.warning(f"SpecHub: Whale flow error: {e}")
        return result
