import logging
from dataclasses import dataclass, field
from typing import Optional, Any
import numpy as np
import pandas as pd

from backend.modules.shared.domain.ports.time_series_port import TimeSeriesPort
from backend.modules.shared.domain.rules.compute_channel import compute_channel_snapshot
from backend.modules.simulation.domain.entities.indicator_snapshot import IndicatorSnapshot
from backend.modules.simulation.domain.entities.signal_forensic_label import SignalForensicLabel, HorizonSnapshot
from backend.modules.simulation.domain.entities.entry_report_card import EntryReportCard
from backend.modules.simulation.domain.entities.exit_report_card import ExitReportCard

from backend.modules.price_analysis.application.use_cases.analyze_regression_channel import RegressionChannelIntelligence
from backend.modules.pattern_recognition.application.use_cases.detect_patterns import PatternRecognitionIntelligence
from backend.modules.volatility_regime.domain.rules.vol_classifier import VolRegimeClassifier
from backend.modules.entry_decision.domain.rules.vol_regime_gate import compute_vol_regime_snapshot
from backend.modules.price_analysis.domain.rules.rsi_math import calc_rsi
from backend.modules.volume_intelligence.application.use_cases.track_volume_dynamics import KalmanVolumeTracker

logger = logging.getLogger(__name__)

class OracleTrainer:
    """
    Oracle Forensic Laboratory.
    Observes, evaluates, and labels signal instances (+1 and -1) over historical data.
    Separates Entry Evaluation (+1) and Exit/Trim Evaluation (-1).
    """
    HORIZONS = [3, 5, 10, 20, 40]
    PRIMARY_HORIZON = 10

    def __init__(self, store: TimeSeriesPort):
        self.store = store
        self.rc_intel = RegressionChannelIntelligence()
        self.pattern_intel = PatternRecognitionIntelligence()
        self.vol_classifier = VolRegimeClassifier()

    def _precompute_vol_regimes(self, ohlc: pd.DataFrame) -> dict[int, str]:
        """Precompute the quality vol regime string for each bar index in ohlc (vectorized, O(N))."""
        if len(ohlc) < 60:
            return {}

        close_col = 'Close' if 'Close' in ohlc.columns else 'close'
        high_col = 'High' if 'High' in ohlc.columns else 'high'
        low_col = 'Low' if 'Low' in ohlc.columns else 'low'

        close = ohlc[close_col].astype(float)
        high = ohlc[high_col].astype(float)
        low = ohlc[low_col].astype(float)

        log_returns = np.log(close / close.shift(1))
        real_vol_fast = log_returns.rolling(10, min_periods=5).std() * np.sqrt(252)
        real_vol_slow = log_returns.rolling(60, min_periods=30).std() * np.sqrt(252)

        vol_ratio = real_vol_fast / real_vol_slow.replace(0, np.nan)
        vol_ratio = vol_ratio.fillna(1.0)

        abs_rets = log_returns.abs()
        vol_persistence = abs_rets.rolling(20, min_periods=10).apply(
            lambda x: x.autocorr(lag=1) if len(x) > 5 else 0.5,
            raw=False,
        ).fillna(0.5)

        vol_of_vol = real_vol_fast.rolling(20, min_periods=10).std().fillna(0.15)

        vol_mean = real_vol_fast.rolling(60, min_periods=30).mean()
        is_calm = (real_vol_fast < vol_mean).astype(float)
        calm_groups = (is_calm != is_calm.shift(1)).cumsum()
        calm_duration = is_calm.groupby(calm_groups).cumsum()

        vix_z_series = pd.Series(0.0, index=close.index)  # Default 0.0 z-score
        vix_vel_series = pd.Series(0.0, index=close.index)

        classifier = VolRegimeClassifier()
        quality = classifier.classify_quality_series(
            calm_duration, vol_persistence, vol_of_vol, vol_ratio,
            vix_z_series, vix_vel_series,
        )

        vol_regime_map = {0: "NORMAL", 1: "COMPLACENT", 2: "ELEVATED", 3: "CRISIS"}
        
        regimes_dict = {}
        for i, val in enumerate(quality):
            regimes_dict[i] = vol_regime_map.get(int(val), "NORMAL")
            
        return regimes_dict

    def _build_snapshot(
        self, ohlc: pd.DataFrame, idx: int, rsi_values: np.ndarray, kalman_states: list,
        vol_regimes: dict[int, str] | None = None
    ) -> IndicatorSnapshot:
        """Build IndicatorSnapshot at index `idx` using compute_channel_snapshot.

        Uses the unified ChannelSnapshot (triple regression + triple VWAP)
        instead of calling rc_intel.analyze() which internally duplicated
        regression computations.
        """
        close = ohlc["close"].values.astype(float)
        high = ohlc["high"].values.astype(float)
        low = ohlc["low"].values.astype(float)
        volume = ohlc["volume"].values.astype(float)

        # 1. Compute channel snapshot (single call, 0 duplicates)
        channel = compute_channel_snapshot(close, high, low, volume, idx)
        if channel is None:
            # Fallback: insufficient data, use legacy path
            rc_res = self.rc_intel.analyze(ohlc, idx=idx)
            channel = None

        # 2. Vol regime classification
        if vol_regimes is not None and idx in vol_regimes:
            vol_reg_str = vol_regimes[idx]
        else:
            vol_state = compute_vol_regime_snapshot(ohlc.iloc[:idx+1])
            vol_regime_map = {0: "NORMAL", 1: "COMPLACENT", 2: "ELEVATED", 3: "CRISIS"}
            vol_reg_str = vol_regime_map.get(vol_state.quality_regime, "NORMAL")

        # 3. Kalman states
        k_state = kalman_states[idx] if idx < len(kalman_states) else {}
        wyckoff_state = k_state.get("wyckoff_state", "UNKNOWN")
        kalman_velocity = k_state.get("velocity", 0.0)

        # 4. RSI value
        rsi_val = float(rsi_values[idx]) if idx < len(rsi_values) else 50.0

        # 5. RVOL
        avg_vol_20 = float(np.mean(volume[max(0, idx-19):idx+1])) if idx >= 1 else volume[idx]
        rvol = volume[idx] / max(avg_vol_20, 1.0)

        # 6. Pattern recognition at this bar
        candle_pattern = None
        candle_sentiment = None
        candle_score = None
        if idx >= 3:
            try:
                pattern_result = self.pattern_intel.detect(ohlc.iloc[:idx+1])
                candle_pattern = pattern_result.primary_pattern
                candle_sentiment = pattern_result.sentiment
                candle_score = pattern_result.confirmation_score
            except Exception:
                pass  # Pattern detection is optional

        if channel is not None:
            return IndicatorSnapshot(
                # Triple regression
                sigma_tide=channel.sigma_tide,
                sigma_wave=channel.sigma_wave,
                sigma_current=channel.sigma_current,
                tide_slope=channel.tide_slope,
                wave_slope=channel.wave_slope,
                current_slope=channel.current_slope,
                tide_accel=channel.tide_accel,
                current_accel=channel.current_accel,
                wave_accel=channel.wave_accel,
                # Conjugations
                slope_conjugation=channel.conj_wave_tide,
                conj_wave_tide=channel.conj_wave_tide,
                conj_current_tide=channel.conj_current_tide,
                conj_wave_current=channel.conj_wave_current,
                # Sigma spreads
                spread_tide_current=channel.spread_tide_current,
                spread_tide_wave=channel.spread_tide_wave,
                spread_current_wave=channel.spread_current_wave,
                # Triple VWAP
                vwap_sigma_tide=channel.vwap_sigma_tide,
                vwap_sigma_current=channel.vwap_sigma_current,
                vwap_sigma_wave=channel.vwap_sigma_wave,
                # Legacy VWAP (backward compat)
                below_vwap=channel.below_all_vwaps,
                below_all_vwaps=channel.below_all_vwaps,
                above_all_vwaps=channel.above_all_vwaps,
                # Existing
                vol_up_down_ratio=channel.vol_up_down_ratio,
                wave_flip=channel.wave_flip,
                wave_flip_direction=channel.wave_flip_direction,
                rvol=rvol,
                # Per-indicator
                rsi_value=rsi_val,
                wyckoff_state=wyckoff_state,
                kalman_velocity=kalman_velocity,
                vol_regime=vol_reg_str,
                # Pattern
                candle_pattern=candle_pattern,
                candle_sentiment=candle_sentiment,
                candle_confirmation_score=candle_score,
                # Derived
                regime=channel.regime,
                fear_level=channel.fear_level,
                fear_label=channel.fear_label,
                # Tensions (v15 Part 3)
                tension_tide=channel.tension_tide,
                tension_current=channel.tension_current,
                tension_wave=channel.tension_wave,
                # Compression (v15 Part 8)
                compression_ratio=channel.compression_ratio,
                # Geometric features (Fase 2A)
                geo_state_norm=channel.geo_state_norm,
                geo_velocity_align=channel.geo_velocity_align,
                geo_exit_align=channel.geo_exit_align,
                geo_accel_align=channel.geo_accel_align,
                geo_phase_angle=channel.geo_phase_angle,
            )
        else:
            # Legacy fallback (channel computation failed)
            return IndicatorSnapshot(
                sigma_tide=rc_res.sigma_position,
                sigma_wave=rc_res.sigma_wave,
                tide_slope=rc_res.tide_slope,
                wave_slope=rc_res.wave_slope,
                tide_accel=rc_res.tide_accel,
                below_vwap=rc_res.below_vwap,
                vol_up_down_ratio=rc_res.vol_up_down_ratio,
                wave_flip=rc_res.wave_flip,
                wave_flip_direction=rc_res.wave_flip_direction,
                rvol=rvol,
                rsi_value=rsi_val,
                wyckoff_state=wyckoff_state,
                kalman_velocity=kalman_velocity,
                vol_regime=vol_reg_str,
                candle_pattern=candle_pattern,
                candle_sentiment=candle_sentiment,
                candle_confirmation_score=candle_score,
                regime=rc_res.regime,
                fear_level=rc_res.fear_level,
                fear_label=rc_res.fear_label,
                slope_conjugation=rc_res.slope_conjugation,
            )

    def _calculate_horizons(self, ohlc: pd.DataFrame, idx: int) -> dict[int, HorizonSnapshot]:
        """Calculate forward returns, MAE, MFE for each horizon from signal index `idx`."""
        close = ohlc["close"].values.astype(float)
        high = ohlc["high"].values.astype(float)
        low = ohlc["low"].values.astype(float)
        current_price = close[idx]
        
        horizons_dict = {}
        for h in self.HORIZONS:
            end_idx = min(idx + h, len(ohlc) - 1)
            fwd_close = close[end_idx]
            
            # Returns
            return_pct = ((fwd_close - current_price) / current_price * 100) if current_price > 0 else 0.0

            # Excursions (only inside forward window [idx+1, end_idx])
            if end_idx > idx:
                fwd_highs = high[idx+1 : end_idx+1]
                fwd_lows = low[idx+1 : end_idx+1]
                
                max_high = float(np.max(fwd_highs))
                min_low = float(np.min(fwd_lows))
                
                max_up_pct = ((max_high - current_price) / current_price * 100) if current_price > 0 else 0.0
                max_down_pct = ((min_low - current_price) / current_price * 100) if current_price > 0 else 0.0
                
                bars_to_max_up = int(np.argmax(fwd_highs)) + 1
                bars_to_max_down = int(np.argmin(fwd_lows)) + 1
            else:
                max_up_pct = 0.0
                max_down_pct = 0.0
                bars_to_max_up = 0
                bars_to_max_down = 0

            horizons_dict[h] = HorizonSnapshot(
                bars=h,
                return_pct=round(return_pct, 4),
                max_up_pct=round(max_up_pct, 4),
                max_down_pct=round(max_down_pct, 4),
                bars_to_max_up=bars_to_max_up,
                bars_to_max_down=bars_to_max_down
            )
        return horizons_dict

    # ═══════════════════════════════════════════
    # ENTRY EVALUATION (+1)
    # ═══════════════════════════════════════════

    def evaluate_entries(
        self, ticker: str, tf: str, signal_name: str, adapter: Any
    ) -> tuple[list[SignalForensicLabel], EntryReportCard]:
        """
        Evaluate entry signals (+1) for the given signal generator.
        """
        ohlc = self.store.load_bars(ticker, tf)
        if ohlc.empty:
            logger.error(f"No OHLC bars found for {ticker}")
            return [], EntryReportCard(ticker=ticker, signal_name=signal_name, n_signals=0)

        # Generate adapter output
        sig_df = adapter.generate(ohlc)
        
        # Precompute RSI and Kalman states
        close_arr = ohlc["close"].values.astype(float)
        rsi_vals = calc_rsi(close_arr, period=14)
        
        tracker = KalmanVolumeTracker(dt=1.0, process_noise=0.05, obs_noise=0.2)
        vol_series = ohlc["volume"].astype(float)
        vol_mean_20 = vol_series.rolling(window=20, min_periods=1).mean()
        kalman_states = []
        for i in range(len(ohlc)):
            raw_vol = float(ohlc["volume"].iloc[i])
            avg_vol = float(vol_mean_20.iloc[i])
            observed_rvol = raw_vol / avg_vol if avg_vol > 0 else 1.0
            prev_close = float(ohlc["close"].iloc[max(0, i-1)])
            curr_close = float(ohlc["close"].iloc[i])
            change_pct = ((curr_close - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
            state = tracker.update(ticker, observed_rvol, change_pct)
            kalman_states.append(state)

        # Precompute volatility regimes
        vol_regimes = self._precompute_vol_regimes(ohlc)

        labels = []
        classification_dist = {"GOLDEN_RUN": 0, "SOLID_MOVE": 0, "SLOW_GRIND": 0, "MISS": 0, "TRAP": 0, "FALSE_SIGNAL": 0}
        
        # Regimes and fear conditioning aggregations
        golden_by_fear = {}
        n_by_fear = {}
        golden_by_vol = {}
        n_by_vol = {}
        golden_by_weinstein = {}
        n_by_weinstein = {}
        
        returns_by_h = {h: [] for h in self.HORIZONS}
        wr_by_h = {h: [] for h in self.HORIZONS}
        mfe_list = []
        mae_list = []

        failure_breakdown = {}
        foreseeability_breakdown = {"FORESEEABLE": 0, "PARTIALLY": 0, "UNFORESEEABLE": 0}

        # Find signal == 1 indexes
        signal_indices = sig_df[sig_df["signal"] == 1].index
        
        for sig_time in signal_indices:
            idx = ohlc.index.get_loc(sig_time)
            
            # Ensure we have at least min bars lookback to build a valid snapshot
            if idx < 245:
                continue

            snapshot = self._build_snapshot(ohlc, idx, rsi_vals, kalman_states, vol_regimes)
            horizons = self._calculate_horizons(ohlc, idx)
            
            # Classification
            classification = self._classify_entry(horizons)
            classification_dist[classification] = classification_dist.get(classification, 0) + 1
            
            # Build basic label
            lbl = SignalForensicLabel(
                ticker=ticker,
                signal_name=signal_name,
                signal_direction=1,
                signal_confidence=float(sig_df.loc[sig_time, "confidence"]) if "confidence" in sig_df.columns else 0.5,
                signal_time=sig_time,
                signal_price=float(ohlc["close"].iloc[idx]),
                snapshot=snapshot,
                horizons=horizons,
                classification=classification,
                primary_horizon=self.PRIMARY_HORIZON
            )

            # Failure Diagnosis
            is_success = classification in ("GOLDEN_RUN", "SOLID_MOVE")
            if not is_success:
                diagnosis, foreseeability = self.diagnose_failure(ohlc, lbl)
                lbl.failure_diagnosis = diagnosis
                lbl.foreseeability = foreseeability
                
                # Breakdown updates
                failure_breakdown[diagnosis] = failure_breakdown.get(diagnosis, 0) + 1
                foreseeability_breakdown[foreseeability] = foreseeability_breakdown.get(foreseeability, 0) + 1
            
            labels.append(lbl)

            # Aggregates
            for h in self.HORIZONS:
                returns_by_h[h].append(horizons[h].return_pct)
                wr_by_h[h].append(1.0 if horizons[h].return_pct > 0 else 0.0)

            primary_h = horizons[self.PRIMARY_HORIZON]
            mfe_list.append(primary_h.max_up_pct)
            mae_list.append(primary_h.max_down_pct)

            # Regime conditioning
            fear_lbl = snapshot.fear_label
            n_by_fear[fear_lbl] = n_by_fear.get(fear_lbl, 0) + 1
            if is_success:
                golden_by_fear[fear_lbl] = golden_by_fear.get(fear_lbl, 0) + 1

            vol_reg = snapshot.vol_regime
            n_by_vol[vol_reg] = n_by_vol.get(vol_reg, 0) + 1
            if is_success:
                golden_by_vol[vol_reg] = golden_by_vol.get(vol_reg, 0) + 1

            weinstein = snapshot.regime
            n_by_weinstein[weinstein] = n_by_weinstein.get(weinstein, 0) + 1
            if is_success:
                golden_by_weinstein[weinstein] = golden_by_weinstein.get(weinstein, 0) + 1

        n_signals = len(labels)
        if n_signals == 0:
            return [], EntryReportCard(ticker=ticker, signal_name=signal_name, n_signals=0)

        # Percentages
        classification_pct = {k: round(v / n_signals * 100, 2) for k, v in classification_dist.items()}
        golden_rate = round((classification_dist["GOLDEN_RUN"] + classification_dist["SOLID_MOVE"]) / n_signals * 100, 2)
        trap_rate = round(classification_dist["TRAP"] / n_signals * 100, 2)
        false_rate = round(classification_dist["FALSE_SIGNAL"] / n_signals * 100, 2)
        miss_rate = round(classification_dist["MISS"] / n_signals * 100, 2)

        avg_return_by_horizon = {h: round(float(np.mean(returns_by_h[h])), 2) for h in self.HORIZONS}
        wr_by_horizon = {h: round(float(np.mean(wr_by_h[h])) * 100, 2) for h in self.HORIZONS}

        avg_mfe = float(np.mean(mfe_list))
        avg_mae = float(np.mean(mae_list))
        edge_ratio = round(avg_mfe / abs(avg_mae) if abs(avg_mae) > 0 else avg_mfe, 2)

        # Failures foreseeability
        n_failures = sum(foreseeability_breakdown.values())
        foreseeable_pct = round(foreseeability_breakdown["FORESEEABLE"] / n_failures * 100, 2) if n_failures > 0 else 0.0

        top_lesson = "NONE"
        if failure_breakdown:
            top_lesson = max(failure_breakdown, key=failure_breakdown.get)

        # Regime Conditioning Rates
        golden_rate_by_fear = {k: round(golden_by_fear.get(k, 0) / v * 100, 2) for k, v in n_by_fear.items()}
        golden_rate_by_vol_regime = {k: round(golden_by_vol.get(k, 0) / v * 100, 2) for k, v in n_by_vol.items()}
        golden_rate_by_weinstein = {k: round(golden_by_weinstein.get(k, 0) / v * 100, 2) for k, v in n_by_weinstein.items()}

        # Grading / Verdict
        grade = "D"
        if golden_rate >= 65:
            grade = "A"
        elif golden_rate >= 55:
            grade = "B"
        elif golden_rate >= 45:
            grade = "C"
        elif golden_rate >= 35:
            grade = "D"
        else:
            grade = "F"

        verdict = "REJECT"
        if golden_rate >= 60 and edge_ratio > 2.0:
            verdict = "ELITE"
        elif golden_rate >= 48 and edge_ratio > 1.5:
            verdict = "VIABLE"
        elif golden_rate >= 38:
            verdict = "MARGINAL"
        
        card = EntryReportCard(
            ticker=ticker,
            signal_name=signal_name,
            n_signals=n_signals,
            classification_dist=classification_dist,
            classification_pct=classification_pct,
            golden_rate=golden_rate,
            trap_rate=trap_rate,
            false_rate=false_rate,
            miss_rate=miss_rate,
            avg_return_by_horizon=avg_return_by_horizon,
            wr_by_horizon=wr_by_horizon,
            edge_ratio_10=edge_ratio,
            avg_mfe_10=round(avg_mfe, 2),
            avg_mae_10=round(avg_mae, 2),
            foreseeable_pct=foreseeable_pct,
            failure_breakdown=failure_breakdown,
            foreseeability_breakdown=foreseeability_breakdown,
            top_lesson=top_lesson,
            golden_rate_by_fear=golden_rate_by_fear,
            golden_rate_by_vol_regime=golden_rate_by_vol_regime,
            golden_rate_by_weinstein=golden_rate_by_weinstein,
            grade=grade,
            verdict=verdict
        )

        return labels, card

    def _classify_entry(self, horizons: dict[int, HorizonSnapshot]) -> str:
        """Classify an entry based on multi-horizon return curve."""
        h = horizons[self.PRIMARY_HORIZON]
        if h.return_pct >= 3.0 and h.max_down_pct > -1.0:
            return "GOLDEN_RUN"
        elif h.return_pct >= 1.0:
            return "SOLID_MOVE"
        elif h.return_pct >= 0.0:
            return "SLOW_GRIND" if h.return_pct >= 0.5 else "MISS"
        elif h.max_up_pct >= 1.0 and h.return_pct < 0:
            return "TRAP"
        else:
            return "FALSE_SIGNAL"

    # ═══════════════════════════════════════════
    # EXIT EVALUATION (-1)
    # ═══════════════════════════════════════════

    def evaluate_exits(
        self, ticker: str, tf: str, signal_name: str, adapter: Any
    ) -> tuple[list[SignalForensicLabel], ExitReportCard]:
        """
        Evaluate exit/trim signals (-1) for the given signal generator.
        """
        ohlc = self.store.load_bars(ticker, tf)
        if ohlc.empty:
            logger.error(f"No OHLC bars found for {ticker}")
            return [], ExitReportCard(ticker=ticker, signal_name=signal_name, n_signals=0)

        # Generate adapter output
        sig_df = adapter.generate(ohlc)
        
        # Precompute RSI and Kalman states
        close_arr = ohlc["close"].values.astype(float)
        rsi_vals = calc_rsi(close_arr, period=14)
        
        tracker = KalmanVolumeTracker(dt=1.0, process_noise=0.05, obs_noise=0.2)
        vol_series = ohlc["volume"].astype(float)
        vol_mean_20 = vol_series.rolling(window=20, min_periods=1).mean()
        kalman_states = []
        for i in range(len(ohlc)):
            raw_vol = float(ohlc["volume"].iloc[i])
            avg_vol = float(vol_mean_20.iloc[i])
            observed_rvol = raw_vol / avg_vol if avg_vol > 0 else 1.0
            prev_close = float(ohlc["close"].iloc[max(0, i-1)])
            curr_close = float(ohlc["close"].iloc[i])
            change_pct = ((curr_close - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
            state = tracker.update(ticker, observed_rvol, change_pct)
            kalman_states.append(state)

        # Precompute volatility regimes
        vol_regimes = self._precompute_vol_regimes(ohlc)

        labels = []
        classification_dist = {"SAVED_US": 0, "GOOD_WARNING": 0, "EARLY_BUT_RIGHT": 0, "NEUTRAL_EXIT": 0, "FALSE_ALARM": 0, "MISSED_UPSIDE": 0}
        
        save_by_fear = {}
        n_by_fear = {}
        save_by_vol = {}
        n_by_vol = {}
        false_alarm_by_fear = {}
        
        avoided_loss_by_h = {h: [] for h in self.HORIZONS}
        missed_gain_by_h = {h: [] for h in self.HORIZONS}

        false_alarms_returns = []
        missed_upside_returns = []

        failure_breakdown = {}
        foreseeability_breakdown = {"FORESEEABLE": 0, "PARTIALLY": 0, "UNFORESEEABLE": 0}

        # Find signal == -1 indexes
        signal_indices = sig_df[sig_df["signal"] == -1].index
        
        for sig_time in signal_indices:
            idx = ohlc.index.get_loc(sig_time)
            
            if idx < 200:
                continue

            snapshot = self._build_snapshot(ohlc, idx, rsi_vals, kalman_states, vol_regimes)
            horizons = self._calculate_horizons(ohlc, idx)
            
            # Classification
            classification = self._classify_exit(horizons)
            classification_dist[classification] = classification_dist.get(classification, 0) + 1
            
            # Build basic label
            lbl = SignalForensicLabel(
                ticker=ticker,
                signal_name=signal_name,
                signal_direction=-1,
                signal_confidence=float(sig_df.loc[sig_time, "confidence"]) if "confidence" in sig_df.columns else 0.5,
                signal_time=sig_time,
                signal_price=float(ohlc["close"].iloc[idx]),
                snapshot=snapshot,
                horizons=horizons,
                classification=classification,
                primary_horizon=self.PRIMARY_HORIZON
            )

            # Failure Diagnosis
            is_success = classification in ("SAVED_US", "GOOD_WARNING", "EARLY_BUT_RIGHT")
            if not is_success and classification != "NEUTRAL_EXIT":
                diagnosis, foreseeability = self.diagnose_failure(ohlc, lbl)
                lbl.failure_diagnosis = diagnosis
                lbl.foreseeability = foreseeability
                
                failure_breakdown[diagnosis] = failure_breakdown.get(diagnosis, 0) + 1
                foreseeability_breakdown[foreseeability] = foreseeability_breakdown.get(foreseeability, 0) + 1
            
            labels.append(lbl)

            # Aggregates
            primary_h = horizons[self.PRIMARY_HORIZON]
            for h in self.HORIZONS:
                ret = horizons[h].return_pct
                if ret < 0:
                    avoided_loss_by_h[h].append(ret)
                else:
                    missed_gain_by_h[h].append(ret)

            if classification == "FALSE_ALARM":
                false_alarms_returns.append(primary_h.return_pct)
            elif classification == "MISSED_UPSIDE":
                missed_upside_returns.append(primary_h.return_pct)

            # Regime conditioning
            fear_lbl = snapshot.fear_label
            n_by_fear[fear_lbl] = n_by_fear.get(fear_lbl, 0) + 1
            if is_success:
                save_by_fear[fear_lbl] = save_by_fear.get(fear_lbl, 0) + 1
            if classification == "FALSE_ALARM":
                false_alarm_by_fear[fear_lbl] = false_alarm_by_fear.get(fear_lbl, 0) + 1

            vol_reg = snapshot.vol_regime
            n_by_vol[vol_reg] = n_by_vol.get(vol_reg, 0) + 1
            if is_success:
                save_by_vol[vol_reg] = save_by_vol.get(vol_reg, 0) + 1

        n_signals = len(labels)
        if n_signals == 0:
            return [], ExitReportCard(ticker=ticker, signal_name=signal_name, n_signals=0)

        # Percentages
        classification_pct = {k: round(v / n_signals * 100, 2) for k, v in classification_dist.items()}
        save_rate = round((classification_dist["SAVED_US"] + classification_dist["GOOD_WARNING"]) / n_signals * 100, 2)
        early_rate = round(classification_dist["EARLY_BUT_RIGHT"] / n_signals * 100, 2)
        false_alarm_rate = round(classification_dist["FALSE_ALARM"] / n_signals * 100, 2)
        missed_upside_rate = round(classification_dist["MISSED_UPSIDE"] / n_signals * 100, 2)
        neutral_rate = round(classification_dist["NEUTRAL_EXIT"] / n_signals * 100, 2)

        avg_avoided_loss = {h: round(float(np.mean(avoided_loss_by_h[h])), 2) if avoided_loss_by_h[h] else 0.0 for h in self.HORIZONS}
        avg_missed_gain = {h: round(float(np.mean(missed_gain_by_h[h])), 2) if missed_gain_by_h[h] else 0.0 for h in self.HORIZONS}

        cost_fa = round(float(np.mean(false_alarms_returns)), 2) if false_alarms_returns else 0.0
        cost_mu = round(float(np.mean(missed_upside_returns)), 2) if missed_upside_returns else 0.0
        
        # Net exit value = avoided loss (negative return) - missed gain (positive return)
        net_avoided = float(np.mean([r for h in avoided_loss_by_h.values() for r in h])) if any(avoided_loss_by_h.values()) else 0.0
        net_missed = float(np.mean([r for h in missed_gain_by_h.values() for r in h])) if any(missed_gain_by_h.values()) else 0.0
        net_exit_value = round(-net_avoided - net_missed, 2)

        # Failures foreseeability
        n_failures = sum(foreseeability_breakdown.values())
        foreseeable_pct = round(foreseeability_breakdown["FORESEEABLE"] / n_failures * 100, 2) if n_failures > 0 else 0.0

        top_lesson = "NONE"
        if failure_breakdown:
            top_lesson = max(failure_breakdown, key=failure_breakdown.get)

        # Regime Conditioning Rates
        save_rate_by_fear = {k: round(save_by_fear.get(k, 0) / v * 100, 2) for k, v in n_by_fear.items()}
        save_rate_by_vol_regime = {k: round(save_by_vol.get(k, 0) / v * 100, 2) for k, v in n_by_vol.items()}
        false_alarm_rate_by_fear = {k: round(false_alarm_by_fear.get(k, 0) / v * 100, 2) for k, v in n_by_fear.items()}

        # Grading / Verdict
        grade = "D"
        if save_rate >= 60:
            grade = "A"
        elif save_rate >= 50:
            grade = "B"
        elif save_rate >= 40:
            grade = "C"
        elif save_rate >= 30:
            grade = "D"
        else:
            grade = "F"

        verdict = "REJECT"
        if save_rate >= 55 and net_exit_value > 1.0:
            verdict = "ELITE"
        elif save_rate >= 45 and net_exit_value > 0.0:
            verdict = "VIABLE"
        elif save_rate >= 35:
            verdict = "MARGINAL"

        card = ExitReportCard(
            ticker=ticker,
            signal_name=signal_name,
            n_signals=n_signals,
            classification_dist=classification_dist,
            classification_pct=classification_pct,
            save_rate=save_rate,
            early_rate=early_rate,
            false_alarm_rate=false_alarm_rate,
            missed_upside_rate=missed_upside_rate,
            neutral_rate=neutral_rate,
            avg_avoided_loss=avg_avoided_loss,
            avg_missed_gain=avg_missed_gain,
            cost_of_false_alarms=cost_fa,
            cost_of_missed_upside=cost_mu,
            net_exit_value=net_exit_value,
            foreseeable_pct=foreseeable_pct,
            failure_breakdown=failure_breakdown,
            foreseeability_breakdown=foreseeability_breakdown,
            top_lesson=top_lesson,
            save_rate_by_fear=save_rate_by_fear,
            save_rate_by_vol_regime=save_rate_by_vol_regime,
            false_alarm_rate_by_fear=false_alarm_rate_by_fear,
            grade=grade,
            verdict=verdict
        )

        return labels, card

    def _classify_exit(self, horizons: dict[int, HorizonSnapshot]) -> str:
        """Classify an exit based on multi-horizon return curve (inverted logic)."""
        h = horizons[self.PRIMARY_HORIZON]
        if h.return_pct <= -3.0:
            return "SAVED_US"          # Evitamos una caída grande
        elif h.return_pct <= -1.0:
            return "GOOD_WARNING"      # Evitamos una caída moderada
        elif h.return_pct < -0.5:
            return "EARLY_BUT_RIGHT"   # Dirección correcta pero leve
        elif -0.5 <= h.return_pct <= 0.5:
            return "NEUTRAL_EXIT"      # Nada pasó
        elif h.return_pct <= 2.0:
            return "FALSE_ALARM"       # Subió después — no debimos salir
        else:
            return "MISSED_UPSIDE"     # Gran subida perdida — error costoso

    # ═══════════════════════════════════════════
    # FAILURE DIAGNOSIS (Dalio: Reflection)
    # ═══════════════════════════════════════════

    def diagnose_failure(
        self,
        ohlc: pd.DataFrame,
        label: SignalForensicLabel,
    ) -> tuple[str, str]:
        """
        Diagnose WHY a signal failed and if it was foreseeable.
        """
        try:
            sig_time = label.signal_time
            if isinstance(sig_time, str):
                sig_time = pd.Timestamp(sig_time)
            
            if sig_time in ohlc.index:
                idx = ohlc.index.get_loc(sig_time)
            else:
                idx = ohlc.index.get_indexer([sig_time], method='nearest')[0]

            close = ohlc["close"].values.astype(float)
            vol = ohlc["volume"].values.astype(float)
            
            # Common observables
            avg_vol_20 = float(np.mean(vol[max(0, idx-19):idx+1])) if idx >= 1 else vol[idx]
            rvol = float(vol[idx]) / max(avg_vol_20, 1.0)
            
            # Gap detection (post-signal bar)
            has_gap = False
            gap_pct = 0.0
            if idx + 1 < len(ohlc):
                next_open = float(ohlc["open"].iloc[idx + 1])
                gap_pct = (next_open - close[idx]) / close[idx] * 100
                has_gap = abs(gap_pct) > 3.0
            
            # ATR% for vol regime detection
            lookback = min(14, idx + 1)
            hl_range = (ohlc["high"].iloc[max(0,idx-lookback+1):idx+1].values 
                        - ohlc["low"].iloc[max(0,idx-lookback+1):idx+1].values)
            atr_pct = float(np.mean(hl_range)) / close[idx] * 100 if close[idx] > 0 else 0

            # ══════════════════════════════════════════════════════
            # ENTRY FAILURES (+1 that went wrong)
            # ══════════════════════════════════════════════════════
            if label.signal_direction == 1:
                # Exogenous shock? (Check first — overrides all)
                if has_gap and gap_pct < -3.0:
                    return "EARNINGS_SHOCK", "UNFORESEEABLE"
                
                # Check for black swan (intraday crash > 5%)
                if idx + 1 < len(ohlc):
                    next_low = float(ohlc["low"].iloc[idx + 1])
                    intraday_drop = (next_low - close[idx]) / close[idx] * 100
                    if intraday_drop < -5.0 and not has_gap:
                        return "BLACK_SWAN", "UNFORESEEABLE"
                
                # ── FORESEEABLE entry failures ──
                
                # Bear regime ignored?
                if label.snapshot.fear_level is not None and label.snapshot.fear_level >= 4:
                    if label.snapshot.sigma_tide is not None and label.snapshot.sigma_tide > 0:
                        return "BEAR_REGIME_IGNORED", "FORESEEABLE"
                
                # Greed exhaustion?
                if (label.snapshot.fear_level is not None and label.snapshot.fear_level <= 1
                        and label.snapshot.sigma_tide is not None and label.snapshot.sigma_tide > 1.0):
                    return "GREED_EXHAUSTION", "FORESEEABLE"
                
                # Resistance entry?
                if label.snapshot.sigma_tide is not None and label.snapshot.sigma_tide > 1.5:
                    return "RESISTANCE_ENTRY", "FORESEEABLE"
                
                # Distribution volume? (high vol + negative price)
                if rvol > 2.0 and idx > 0 and close[idx] < close[idx - 1]:
                    return "DISTRIBUTION_VOLUME", "FORESEEABLE"
                
                # Climax volume trap? (for TRAP classification specifically)
                if label.classification == "TRAP" and rvol > 2.5:
                    return "CLIMAX_VOLUME_TRAP", "FORESEEABLE"
                
                # Greed trap?
                if label.classification == "TRAP" and label.snapshot.fear_level is not None and label.snapshot.fear_level <= 1:
                    return "GREED_TRAP", "FORESEEABLE"
                
                # Low RVOL entry?
                if rvol < 0.5:
                    return "LOW_RVOL_ENTRY", "FORESEEABLE"
                
                # MISS-specific: low vol regime?
                if label.classification == "MISS":
                    if atr_pct < 0.8:
                        return "LOW_VOLATILITY_REGIME", "FORESEEABLE"
                    return "CONSOLIDATION_RANGE", "FORESEEABLE"
                
                return "UNFORESEEABLE", "UNFORESEEABLE"
            
            # ══════════════════════════════════════════════════════
            # EXIT FAILURES (-1 that went wrong)
            # ══════════════════════════════════════════════════════
            else:
                # Exogenous catalyst? (Check first)
                if has_gap and gap_pct > 3.0:
                    return "EARNINGS_CATALYST", "UNFORESEEABLE"
                
                # ── FORESEEABLE exit failures ──
                
                # Bull momentum intact?
                if (label.snapshot.fear_level is not None and label.snapshot.fear_level <= 1
                        and label.snapshot.sigma_tide is not None and label.snapshot.sigma_tide < 1.0):
                    return "BULL_MOMENTUM_INTACT", "FORESEEABLE"
                
                # Fear contrarian error?
                if label.snapshot.fear_level is not None and label.snapshot.fear_level >= 3:
                    return "FEAR_CONTRARIAN_ERROR", "FORESEEABLE"
                
                # Low conviction noise?
                if label.signal_confidence < 0.15:
                    return "LOW_CONVICTION_NOISE", "FORESEEABLE"
                
                # Volume absent?
                if rvol < 0.7:
                    return "VOLUME_ABSENT", "FORESEEABLE"
                
                # Support bounce? (trim in discount zone)
                if label.snapshot.sigma_tide is not None and label.snapshot.sigma_tide < 0:
                    return "SUPPORT_BOUNCE", "FORESEEABLE"
                
                # Accumulation disguised as distribution?
                if (label.snapshot.wyckoff_state == "DISTRIBUTION" 
                        and label.snapshot.fear_level is not None and label.snapshot.fear_level >= 2):
                    return "ACCUMULATION_DISGUISED", "FORESEEABLE"
                
                # NEUTRAL_EXIT specific
                if label.classification == "NEUTRAL_EXIT":
                    if atr_pct < 0.8:
                        return "LOW_VOLATILITY_REGIME", "FORESEEABLE"
                    return "RANGE_BOUND", "FORESEEABLE"
                
                return "UNFORESEEABLE", "UNFORESEEABLE"
        except Exception as e:
            logger.error(f"Error diagnosing failure: {e}")
            return "UNFORESEEABLE", "UNFORESEEABLE"

    def evaluate_independence(self, ticker: str, tf: str, adapter_a: Any, adapter_b: Any, direction: int) -> dict:
        """Calculate Jaccard similarity index between two signal generators to measure redundancy."""
        ohlc = self.store.load_bars(ticker, tf)
        if ohlc.empty:
            return {"jaccard": 0.0, "intersection": 0, "union": 0}

        sig_a = adapter_a.generate(ohlc)
        sig_b = adapter_b.generate(ohlc)

        times_a = set(sig_a[sig_a["signal"] == direction].index)
        times_b = set(sig_b[sig_b["signal"] == direction].index)

        intersection = len(times_a & times_b)
        union = len(times_a | times_b)
        jaccard = intersection / union if union > 0 else 0.0

        return {
            "jaccard": round(jaccard, 4),
            "intersection": intersection,
            "union": union,
            "count_a": len(times_a),
            "count_b": len(times_b)
        }
