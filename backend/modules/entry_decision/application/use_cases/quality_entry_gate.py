"""
QUALITY ENTRY GATE — Druckenmiller & Weinstein
=================================================
Pipeline de decisión de entrada PROFUNDO para posiciones QUALITY.

Evalúa si un tollkeeper previamente identificado por QualityResearchPipeline
está en el momento correcto para entrar.

Criterios:
1. ¿VP institucional en ACUMULACIÓN? (no entrar en distribución)
2. ¿RSI en zona favorable? (no entrar en zonas hostiles)
3. ¿Patrón confirma? (4ª dimensión visual)
4. ¿Macro soportivo? (whale flow no CONTRA)
5. ¿Blacklist clear? (no THESIS_DEATH en 4Q)

NO USA: Memory Guard (vectorDB), time stops, cadencia intradiaria.
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


class QualityEntryGate:
    """
    Gate de entrada para posiciones QUALITY.

    Druckenmiller: "Sizing is everything. When you have conviction, go big."
    Weinstein: "Only buy in Stage 2."

    Este gate NO predice el mercado. Verifica que las condiciones
    institucionales son favorables para un tollkeeper ya calificado.
    """

    def __init__(
        self,
        market_data: EntryMarketDataPort,
        flow_data: FlowDataPort,
        options_provider: OptionsDataPort,
        blacklist=None,
        fundamental_data=None,
        health_provider=None,
    ):
        self._market_data = market_data
        self._flow_data = flow_data
        self._options_provider = options_provider
        self._blacklist = blacklist
        self._fundamental_data = fundamental_data
        self._health_provider = health_provider

        # Lazy-init modules
        from backend.modules.flow_intelligence.application.use_cases.analyze_whale_flow import EventFlowIntelligence
        from backend.modules.price_analysis.application.use_cases.detect_price_phase import PricePhaseIntelligence
        from backend.modules.volume_intelligence.application.use_cases.analyze_volume_profile import VolumeProfileAnalyzer

        self.event_flow = EventFlowIntelligence()
        self.price_phase = PricePhaseIntelligence()
        self.volume_profile = VolumeProfileAnalyzer()

        self._options = None
        self._rsi_intel = None
        self._pattern = None
        self._kalman = None  # KalmanVolumeTracker (Wyckoff — lazy)

    def evaluate(
        self,
        ticker: str,
        reference_date: Optional[date] = None,
        prices_df: pd.DataFrame = None,
        vix_override: float = None,
        vix_trend: Optional[IndicatorTrend] = None,
    ) -> EntryIntelligenceReport:
        """
        Evaluación QUALITY: profunda, sin prisa.
        """
        report = EntryIntelligenceReport(
            ticker=ticker,
            timestamp=datetime.now(UTC).isoformat(),
        )

        # ── Gate 0: Blacklist (legacy) ──
        if self._blacklist and self._blacklist.is_blacklisted(ticker, "QUALITY"):
            report.final_verdict = "BLOCK"
            report.final_scale = 0.0
            report.final_reason = f"BLACKLISTED: {ticker} in 4Q cooldown after THESIS_DEATH"
            return report

        # ── Gate 0.1: Progressive Health ──
        _health_sizing = 1.0
        if self._health_provider:
            try:
                health = self._health_provider.get_health(ticker, "QUALITY")
                if health.requires_exit:
                    report.final_verdict = "BLOCK"
                    report.final_scale = 0.0
                    report.final_reason = (
                        f"HEALTH_DEATH: {ticker} — {', '.join(health.reasons)}"
                    )
                    return report
                if not health.allows_new_entry:
                    report.final_verdict = "STALK"
                    report.final_scale = 0.0
                    report.final_reason = (
                        f"HEALTH_WOUNDED: {ticker} — hold existing, "
                        f"no new entries ({', '.join(health.reasons)})"
                    )
                    return report
                _health_sizing = health.sizing_multiplier
                if _health_sizing < 1.0:
                    report.alerts = report.alerts or []
                    report.alerts.append(
                        f"HEALTH_ALERT: sizing reduced to {_health_sizing:.0%} "
                        f"({', '.join(health.reasons)})"
                    )
            except Exception as e:
                logger.debug(f"Health check skipped for {ticker}: {e}")

        # ── Gate 0.5: Fundamental Health (Vault-backed) ──
        if self._fundamental_data:
            financials = self._fundamental_data.get_financial_summary(ticker)
            if financials:
                roic = float(financials.get("roic", 0) or 0)
                wacc = float(financials.get("wacc", 0) or 0)
                gf_score = float(financials.get("gf_score", 0) or 0)
                opm_ttm = float(financials.get("operating_margin_ttm", 0) or 0)
                opm_5y = float(financials.get("operating_margin_5y_avg", 0) or 0)

                # Hard gate: ROIC must exceed WACC (value creation)
                if wacc > 0 and roic < wacc:
                    report.final_verdict = "BLOCK"
                    report.final_scale = 0.0
                    report.final_reason = (
                        f"FUNDAMENTAL_GATE: Value destruction "
                        f"(ROIC={roic:.1f}% < WACC={wacc:.1f}%)"
                    )
                    return report

                # Hard gate: GF Score minimum
                if gf_score > 0 and gf_score < 75:
                    report.final_verdict = "BLOCK"
                    report.final_scale = 0.0
                    report.final_reason = f"FUNDAMENTAL_GATE: GF Score too low ({gf_score:.0f} < 75)"
                    return report

                # Moat decay warning (doesn't block, adds to report)
                if opm_5y > 0 and opm_ttm < (opm_5y * 0.85):
                    report.alerts = report.alerts or []
                    report.alerts.append(
                        f"MOAT_DECAY: Operating margin declining "
                        f"(TTM={opm_ttm:.1f}% vs 5Y={opm_5y:.1f}%)"
                    )

        # ── Step 1: Price Data ──
        prices = prices_df if prices_df is not None else self._market_data.fetch_prices(ticker)
        if prices is None or prices.empty:
            report.final_verdict = "PASS"
            report.final_reason = "No price data available"
            return report

        if isinstance(prices.columns, pd.MultiIndex):
            prices.columns = prices.columns.get_level_values(0)

        report.current_price = float(prices['Close'].iloc[-1])
        report.atr = float((prices['High'] - prices['Low']).rolling(14).mean().iloc[-1])
        report.vix = vix_override if vix_override is not None else self._market_data.fetch_vix()
        avg_vol = float(prices['Volume'].rolling(20).mean().iloc[-1])
        report.rvol = float(prices['Volume'].iloc[-1]) / avg_vol if avg_vol > 0 else 1.0
        report.rs_vs_spy = self._market_data.calc_rs_vs_spy(prices)

        # ── Gate -1: Vol Regime (Dalio cycle intelligence) ──
        # P1: Entry gate. CRISIS = block. ELEVATED = reduce sizing.
        # Evidence Status: HYPOTHESIS — thresholds need calibration.
        try:
            from backend.modules.entry_decision.domain.rules.vol_regime_gate import compute_vol_regime_snapshot
            from backend.modules.volatility_regime.domain.entities.vol_regime import Q_CRISIS, Q_ELEVATED, Q_COMPLACENT

            # Compute VIX z-score for the classifier
            vix_mean_90d = 20.0  # HYPOTHESIS — approximate long-run VIX mean
            vix_std_90d = 5.0    # HYPOTHESIS — approximate VIX std
            vix_z = (report.vix - vix_mean_90d) / vix_std_90d if vix_std_90d > 0 else 0.0

            regime = compute_vol_regime_snapshot(prices, vix_zscore=vix_z)
            report.vol_regime_quality = regime.quality_label
            report.vol_regime_speculative = regime.speculative_label

            if regime.quality_regime == Q_CRISIS:
                report.final_verdict = "BLOCK"
                report.final_scale = 0.0
                report.final_reason = (
                    f"VOL_REGIME_GATE: CRISIS regime detected "
                    f"(VIX={report.vix:.1f}, z={vix_z:+.1f}). "
                    f"Quality: thesis exits only. No new entries."
                )
                logger.warning(f"QualityGate {ticker}: BLOCKED by VOL_REGIME CRISIS")
                return report

            if regime.quality_regime == Q_ELEVATED:
                _health_sizing *= 0.5
                report.alerts = report.alerts or []
                report.alerts.append(
                    f"VOL_REGIME_ELEVATED: Sizing reduced to {_health_sizing:.0%} "
                    f"(VIX={report.vix:.1f}, regime={regime.quality_label})"
                )
                logger.info(f"QualityGate {ticker}: ELEVATED regime — sizing reduced")

            if regime.quality_regime == Q_COMPLACENT:
                report.alerts = report.alerts or []
                report.alerts.append(
                    f"VOL_REGIME_COMPLACENT: Market unusually calm — "
                    f"Dalio's lake warning. Predators may be near."
                )
        except Exception as e:
            logger.debug(f"QualityGate: Vol regime gate skipped: {e}")

        # ── Step 2: Options — Gamma Regime ──
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

        # ── Step 3: Volume Profile — Institutional Bias ──
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
        except Exception as e:
            logger.warning(f"QualityGate {ticker}: VP error: {e}")
            vp_result = None

        # ── QUALITY GATE: VP Distribution Block ──
        if (report.vp_institutional_bias == "DISTRIBUTION"
                and report.vp_bias_confidence >= 75):
            report.final_verdict = "STALK"
            report.final_scale = 0.0
            report.final_reason = (
                f"VP_DISTRIBUTION: Institucionales distribuyendo "
                f"(conf={report.vp_bias_confidence:.0f}%). No entrar QUALITY."
            )
            return report

        # ── Step 4: Macro Flow (Whale) ──
        flow = self._parse_whale_flow(ticker)
        report.spy_cum_delta = flow.get("spy_cum_delta", 0.0)
        report.spy_signal = flow.get("spy_signal", "NEUTRAL")
        report.tide_direction = flow.get("tide_direction", "NEUTRAL")

        whale_verdict = self.event_flow.assess(
            reference_date=reference_date,
            spy_cum_delta=report.spy_cum_delta,
            spy_signal=report.spy_signal,
            spy_confidence=flow.get("spy_confidence", 0.5),
            am_pm_diverges=flow.get("am_pm_divergence", False),
            sweep_call_pct=flow.get("sweep_call_pct", 50.0),
            total_sweeps=flow.get("total_sweeps", 0),
            sentiment_regime=flow.get("sentiment_regime", "NEUTRAL"),
            tide_direction=report.tide_direction,
            tide_accelerating=flow.get("tide_accelerating", False),
            tide_net_premium=flow.get("tide_net_premium", 0.0),
            gex_regime=report.gamma_regime,
            gex_net=0.0,
            market_breadth_pct=flow.get("breadth_pct", 50.0),
        )
        report.whale_verdict = whale_verdict.verdict
        report.whale_scale = whale_verdict.position_scale
        report.whale_confidence = whale_verdict.confidence
        report.freeze_stops = whale_verdict.freeze_stops

        # QUALITY blocks on CONTRA_FLOW — no exceptions
        if whale_verdict.verdict == "CONTRA_FLOW":
            report.final_verdict = "BLOCK"
            report.final_scale = 0.0
            report.final_reason = f"CONTRA_FLOW: Macro flow against entry"
            return report

        # ── Step 4b: Wyckoff Phase (Kalman — Druckenmiller gate) ──
        wyckoff = self._run_kalman(ticker, prices)
        report.wyckoff_state = wyckoff.get("wyckoff_state", "UNKNOWN")
        report.wyckoff_velocity = wyckoff.get("velocity", 0.0)

        # QUALITY GATE: If Wyckoff says DISTRIBUTION, warn but allow with reduced sizing
        if report.wyckoff_state == "DISTRIBUTION":
            report.alerts = report.alerts or []
            report.alerts.append(
                f"WYCKOFF_DISTRIBUTION: Kalman velocity={report.wyckoff_velocity:.2f}. "
                f"Institucionales posiblemente distribuyendo — sizing reducido."
            )
            _health_sizing *= 0.5  # Reduce sizing by 50% under distribution

        # ── Step 5: Price Phase (now Wyckoff-aware) ──
        phase_verdict = self.price_phase.diagnose(
            ticker=ticker, prices=prices,
            put_wall=report.put_wall, call_wall=report.call_wall,
            gamma_regime=report.gamma_regime,
            wyckoff_state=report.wyckoff_state, wyckoff_velocity=report.wyckoff_velocity,
            strategy_bucket="QUALITY", vp_result=vp_result,
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

        # ── Step 6: RSI Intelligence — QUALITY hostile zones block ──
        try:
            if self._rsi_intel is None:
                from backend.modules.price_analysis.application.use_cases.analyze_rsi import RSIIntelligence
                self._rsi_intel = RSIIntelligence()

            close_arr = prices['Close'].values.astype(float)
            regime_map = {'ACCUMULATION': 'BULL', 'DISTRIBUTION': 'BEAR', 'NEUTRAL': 'NEUTRAL'}
            regime_hint = regime_map.get(report.vp_institutional_bias, 'NEUTRAL')
            rsi_result = self._rsi_intel.analyze(close_arr, regime_hint=regime_hint)
            report.rsi_regime = rsi_result.rsi_regime
            report.rsi_zone = rsi_result.rsi_zone
            report.rsi_conviction = rsi_result.rsi_conviction
        except Exception as e:
            logger.warning(f"QualityGate: RSI error for {ticker}: {e}")

        # ── Step 7: Pattern Intelligence ──
        if self._pattern is None:
            try:
                from backend.modules.pattern_recognition.application.use_cases.detect_patterns import PatternRecognitionIntelligence
                self._pattern = PatternRecognitionIntelligence()
            except Exception:
                pass

        if self._pattern:
            try:
                pv = self._pattern.detect(prices=prices, put_wall=report.put_wall, call_wall=report.call_wall, ticker=ticker)
                report.candlestick_pattern = pv.primary_pattern
                report.pattern_sentiment = pv.sentiment
                report.pattern_score = pv.confirmation_score
                report.pattern_on_support = pv.detected_on_support
                report.pattern_confirms = (
                    (pv.sentiment == "BULLISH" and report.phase in {"CORRECTION", "BREAKOUT", "CONTRARIAN_DIP"})
                    or (pv.is_inside_bar_series and report.phase in {"CORRECTION", "CONSOLIDATION"})
                )
                if report.pattern_confirms:
                    report.dimensions_confirming += 1
            except Exception as e:
                logger.warning(f"QualityGate: Pattern error for {ticker}: {e}")

        # ═══ FINAL VERDICT ═══
        if phase_verdict.verdict == "ABORT":
            report.final_verdict = "BLOCK"
            report.final_scale = 0.0
            report.final_reason = f"ABORT: {phase_verdict.phase}"

        elif phase_verdict.verdict == "FIRE":
            # Quality RSI Gate — block hostile zones
            hostile_zones = {"BOUNCE_SELL", "EXTREME_BULL", "EXTREME_BEAR", "OVERBOUGHT"}
            if report.rsi_zone in hostile_zones:
                report.final_verdict = "STALK"
                report.final_scale = 0.0
                report.final_reason = f"QUALITY_RSI_GATE: Hostile RSI zone={report.rsi_zone}"
                return report

            # Pattern veto
            if report.pattern_sentiment == "BEARISH" and report.pattern_score <= -0.5:
                report.final_verdict = "STALK"
                report.final_scale = 0.0
                report.final_reason = f"PATTERN_VETO: {report.candlestick_pattern}"
                return report

            # EXECUTE — Quality uses conviction-based sizing (Druckenmiller)
            report.final_verdict = "EXECUTE"
            base_scale = whale_verdict.position_scale
            if report.pattern_on_support and report.pattern_score >= 0.5:
                base_scale = min(1.0, base_scale * 1.25)
            # Apply health-based sizing (ALERT = 0.5x, HEALTHY = 1.0x)
            report.final_scale = base_scale * _health_sizing
            report.final_reason = (
                f"FIRE: {phase_verdict.phase}, R:R={report.risk_reward}:1, "
                f"Dims={report.dimensions_confirming}, VP={report.vp_institutional_bias}"
            )

        elif phase_verdict.verdict == "STALK":
            report.final_verdict = "STALK"
            report.final_scale = 0.0
            report.final_reason = f"STALK: {phase_verdict.phase} — waiting for better setup"
        else:
            report.final_verdict = "PASS"
            report.final_scale = 0.0
            report.final_reason = "Unknown phase verdict"

        return report

    # ── Private helpers ──

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
        """Run Kalman Volume Tracker (Wyckoff phase detection)."""
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
            gate = self._flow_data.get_macro_gate()
            result["spy_cum_delta"] = gate.cum_delta
            result["spy_signal"] = gate.signal
            result["spy_confidence"] = gate.confidence
            result["am_pm_divergence"] = gate.am_pm_diverges
            
            tide = self._flow_data.get_market_tide()
            result["tide_direction"] = tide.tide_direction
            result["tide_accelerating"] = tide.is_accelerating
            result["tide_net_premium"] = tide.cum_net_premium
            
            flow = self._flow_data.get_flow_signal(ticker)
            result["total_sweeps"] = flow.n_sweeps
            result["sweep_call_pct"] = (flow.n_calls / (flow.n_calls + flow.n_puts) * 100 if (flow.n_calls + flow.n_puts) > 0 else 50.0)
            
            sentiment = self._flow_data.get_market_sentiment()
            result["sentiment_regime"] = sentiment.regime
            result["breadth_pct"] = sentiment.breadth_pct
        except Exception as e:
            logger.warning(f"QualityGate: Whale flow error: {e}")
        return result
