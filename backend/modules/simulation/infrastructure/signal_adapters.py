"""
Signal Adapters — Thin Wrappers for Modular Evaluation
=========================================================
Each adapter wraps an existing intelligence module and implements
SignalPort for isolated Oracle testing and ML weight discovery.

The adapters are intentionally thin — they translate the module's
output into the canonical signal format (1=long, -1=short, 0=flat).
"""
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from backend.modules.simulation.domain.ports.signal_port import SignalPort

logger = logging.getLogger(__name__)


class KalmanSignalAdapter(SignalPort):
    """Wraps KalmanVolumeTracker — signal when Wyckoff=ACCUMULATION + velocity > 0."""

    @property
    def name(self) -> str:
        return "kalman_wyckoff"

    def generate(self, ohlc: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
        from backend.modules.volume_intelligence.application.use_cases.track_volume_dynamics import (
            KalmanVolumeTracker,
        )
        tracker = KalmanVolumeTracker(dt=1.0, process_noise=0.05, obs_noise=0.2)
        signals = []

        # Pre-compute rolling mean volume for relative volume calculation
        vol_series = ohlc["volume"].astype(float)
        vol_mean_20 = vol_series.rolling(window=20, min_periods=1).mean()

        ticker = context.get("ticker", "SIGNAL") if context else "SIGNAL"

        for i in range(len(ohlc)):
            row = ohlc.iloc[i]
            raw_vol = float(row["volume"])
            avg_vol = float(vol_mean_20.iloc[i])
            observed_rvol = raw_vol / avg_vol if avg_vol > 0 else 1.0

            prev_close = float(ohlc.iloc[max(0, i - 1)]["close"])
            curr_close = float(row["close"])
            change_pct = ((curr_close - prev_close) / prev_close * 100) if prev_close > 0 else 0.0

            state = tracker.update(ticker, observed_rvol, change_pct)
            wyckoff_state = state.get("wyckoff_state", "UNKNOWN")
            velocity = state.get("velocity", 0.0)

            if wyckoff_state == "ACCUMULATION" and velocity > 0:
                signals.append(1)
            elif wyckoff_state == "DISTRIBUTION" and velocity < 0:
                signals.append(-1)
            else:
                signals.append(0)

        result = pd.DataFrame({"signal": signals}, index=ohlc.index)
        return result

    def required_context(self) -> list[str]:
        return []


class MeanReversionSignalAdapter(SignalPort):
    """Legacy mean-reversion signal: oversold 5-day return + relative volume."""

    @property
    def name(self) -> str:
        return "mean_reversion"

    def generate(self, ohlc: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
        close = ohlc["close"]
        volume = ohlc["volume"]

        ret_5d = close.pct_change(5) * 100
        vol_20d_avg = volume.rolling(20).mean()
        rvol = volume / vol_20d_avg.replace(0, np.nan)

        # Default thresholds (will be replaced by adaptive_params)
        entry_threshold = context.get("entry_threshold", -5.0) if context else -5.0
        rvol_threshold = context.get("rvol_threshold", 1.2) if context else 1.2

        signal = ((ret_5d <= entry_threshold) & (rvol >= rvol_threshold)).astype(int)
        return pd.DataFrame({"signal": signal}, index=ohlc.index)

    def required_context(self) -> list[str]:
        return []


class VolumeQualitySignalAdapter(SignalPort):
    """Signal when volume quality score exceeds threshold."""

    @property
    def name(self) -> str:
        return "volume_quality"

    @staticmethod
    def volume_quality_score(
        close: float,
        high: float,
        low: float,
        volume: float,
        avg_volume: float,
        prev_close: float,
    ) -> float:
        score = 0.0
        price_range = high - low
        if price_range <= 0 or volume <= 0 or avg_volume <= 0:
            return 0.0

        abs_return = abs(close - prev_close) / prev_close if prev_close > 0 else 0
        dollar_volume = volume * close
        amihud = abs_return / (dollar_volume / 1e9) if dollar_volume > 0 else 0

        if amihud > 0.5:
            score += 1.0
        elif amihud > 0.1:
            score += 0.5

        close_position = (close - low) / price_range
        if close_position > 0.6:
            score += 1.0
        elif close_position > 0.3:
            score += 0.5

        rvol = volume / avg_volume
        if rvol > 2.0:
            score += 1.0
        elif rvol > 1.5:
            score += 0.5

        return score

    def generate(self, ohlc: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
        signals = []
        for i in range(len(ohlc)):
            if i < 20:
                signals.append(0)
                continue

            window = ohlc.iloc[max(0, i - 20):i + 1]
            try:
                vq = self.volume_quality_score(
                    close=float(ohlc.iloc[i]["close"]),
                    high=float(ohlc.iloc[i]["high"]),
                    low=float(ohlc.iloc[i]["low"]),
                    volume=float(ohlc.iloc[i]["volume"]),
                    avg_volume=float(window["volume"].mean()),
                    prev_close=float(ohlc.iloc[i-1]["close"]),
                )
                threshold = context.get("vq_threshold", 1.0) if context else 1.0
                signals.append(1 if vq >= threshold else 0)
            except Exception:
                signals.append(0)

        return pd.DataFrame({"signal": signals}, index=ohlc.index)

    def required_context(self) -> list[str]:
        return []


class RSISignalAdapter(SignalPort):
    """RSI Intelligence: Regime-Aware, Cycle-Adaptive RSI (H3 — validated).

    Forensic audit result: 10 hypotheses tested, H3 is the winner.
    Sharpe 0.586 (+47% vs brute-force baseline), PF 1.281, 65% fewer entries.

    Architecture (7 layers — entries validated, trims [HYPOTHESIS]):
      1. REGIME from PRICE: Long regression (120 bars) classifies BULL/BEAR/FLAT.
         The RSI does NOT determine its own regime — that's circular.
      2. CROSS-REGRESSION: Short regression (60 bars) compared to long (120 bars).
         When short < long but converging → pullback ending → BULL entry.
      3. SLOPE DIVERGENCE: Short price slope vs short RSI slope.
         Price falling + RSI recovering → exhaustion → BEAR entry.
      4. CYCLE-ADAPTIVE PERIOD: Autocorrelation detects each asset's dominant
         oscillation frequency. RSI lookback = cycle/2 (Nyquist).
         NVDA cycles at 15d → RSI-7. JPM cycles at 44d → RSI-22.
      5. FEAR LEVEL BIAS: Dual RC channel (200/cycle-adaptive bars) produces
         fear_level 0-5. Contrarian: PANIC → confidence bonus, GREED → penalty.
         Empirical: RSI improves in CRISIS (56.2%) and ELEVATED (54.8%).
      6. KALMAN ACCUMULATION: When Kalman-Wyckoff detects ACCUMULATION + positive
         velocity simultaneously with RSI signal → confidence multiplied.
         Validated: RSI+Kalman WR 75.7% → 93.5% (GOLDEN COMBO).
      7. REGIME-INVERTED TRIM: [HYPOTHESIS] D — Advisory Only.
         RSI reading is asymmetric by regime:
           - BULL: valid signals at RSI LOWS (entries — pullback buying)
           - BAJISTA: valid signals at RSI HIGHS (trims — bear rally exhaustion)
           - MUY_BAJISTA: NO trim — RSI high = V-recovery momentum (contrarian)
         Forensic basis (110K events, 32 tickers, 20yr):
           BAJISTA + RSI>=65 + RSI_slope<0: P(fall)=52.8%, Avg=-0.31% (N=106)
           BAJISTA + RSI>=60 + RSI_slope<0: P(fall)=52.0%, Avg=-0.18% (N=202)
           FLAT + cross-regression exhaustion: price bouncing + RSI peaking
         Pending: Walk-Forward DSR validation to promote from D.

    Entry rules:
      BULL: Cross-regression pullback + RSI 33-50 + drop ≥12pts + hookup
      BEAR: Price slope negative + RSI slope positive + RSI < 40
      FLAT: RSI < 35 + regression slope divergence confirmed
      ALL: confidence modulated by fear_level bias + Kalman confirmation

    Trim rules (signal=-1) [HYPOTHESIS]:
      BAJISTA: RSI ≥ 60 + RSI slope negative (bear rally peaked + falling)
      FLAT: RSI ≥ 65 + short slope positive + RSI slope negative (bounce exhaustion)
    """

    @property
    def name(self) -> str:
        return "rsi_intelligence"

    @staticmethod
    def _linreg_slope(data: np.ndarray, window: int) -> float:
        """Normalized linear regression slope over last `window` bars.
        Returns slope as % change per bar (price-normalized).
        """
        if len(data) < window:
            return 0.0
        y = data[-window:]
        x = np.arange(window)
        # Least squares: slope = cov(x,y) / var(x)
        x_mean = x.mean()
        y_mean = y.mean()
        slope = np.sum((x - x_mean) * (y - y_mean)) / np.sum((x - x_mean) ** 2)
        # Normalize by mean price to get % per bar
        return (slope / y_mean * 100) if y_mean > 0 else 0.0

    @staticmethod
    def _calc_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
        """Wilder's RSI series."""
        deltas = np.diff(close)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)

        avg_gain = np.zeros(len(gains))
        avg_loss = np.zeros(len(gains))

        if len(gains) < period:
            return np.full(len(close), 50.0)

        avg_gain[period - 1] = np.mean(gains[:period])
        avg_loss[period - 1] = np.mean(losses[:period])

        for i in range(period, len(gains)):
            avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i]) / period
            avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i]) / period

        with np.errstate(divide='ignore', invalid='ignore'):
            rs = np.where(avg_loss > 0, avg_gain / avg_loss, 100.0)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        rsi[:period] = 50.0
        # Prepend one value so rsi aligns with close (np.diff removes one element)
        return np.concatenate(([50.0], rsi))

    @staticmethod
    def _detect_dominant_cycle(close: np.ndarray, min_period: int = 8, max_period: int = 50) -> int:
        """Detect dominant cycle period via autocorrelation on returns.

        Delegated to shared/domain/rules/cycle_detection.py (canonical location).
        """
        from backend.modules.shared.domain.rules.cycle_detection import detect_dominant_cycle
        return detect_dominant_cycle(close, min_period, max_period)

    def generate(self, ohlc: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
        close = ohlc["close"].values.astype(float)

        # ── Layer 4: Cycle-Adaptive Period (Nyquist) ──
        dominant_cycle = self._detect_dominant_cycle(close)
        adaptive_rsi_period = max(5, dominant_cycle // 2)  # Nyquist: period/2
        rsi_full = self._calc_rsi(close, period=adaptive_rsi_period)

        # ── Adaptive short regression window (same logic as RC adapter) ──
        # Matches each asset's natural cycle: NVDA (15d) vs JPM (44d)
        short_slope_window = max(10, min(dominant_cycle, 60))  # Clamp 10-60

        # ── Layer 6: Pre-compute Kalman states for all bars ──
        kalman_states = self._precompute_kalman(ohlc)

        signals = []
        confidences = []

        for i in range(len(ohlc)):
            if i < 200:  # Extended from 120 to 200 — need 200 bars for fear_level
                signals.append(0)
                confidences.append(0.0)
                continue

            price_window = close[:i + 1]
            rsi_window = rsi_full[:i + 1]
            current_rsi = rsi_window[i]

            # ── Layer 1: PRICE REGRESSIONS (the regime anchors) ──
            slope_long = self._linreg_slope(price_window, 120)   # Macro trend (fixed)
            slope_short = self._linreg_slope(price_window, short_slope_window)  # Adaptive micro momentum

            # ── REGIME CLASSIFICATION (from PRICE, not RSI) ──
            # 5-state for trim granularity (BAJISTA vs MUY_BAJISTA)
            if slope_long > 0.02:
                regime = "BULL"
            elif slope_long > -0.005:
                regime = "FLAT"
            elif slope_long > -0.02:
                regime = "BAJISTA"
            else:
                regime = "MUY_BAJISTA"

            # ── Layer 3: SHORT REGRESSION ON RSI (divergence) ──
            rsi_slope_short = self._linreg_slope(rsi_window, 30)

            signal = 0
            confidence = 0.0

            # ═══════════════════════════════════════════════════
            # ENTRY SIGNALS (signal = +1)
            # ═══════════════════════════════════════════════════

            if regime == "BULL":
                # ── Layer 2: Cross-regression pullback (H2e — validated) ──
                short_below_long = slope_short < slope_long
                short_recovering = slope_short > (slope_long * 0.3)
                rsi_in_pullback = 33 <= current_rsi <= 50
                rsi_hooking_up = current_rsi > rsi_window[i - 1]
                rsi_recent_high = np.max(rsi_window[max(0, i-20):i])
                rsi_drop = rsi_recent_high - current_rsi
                real_pullback = rsi_drop >= 12

                if short_below_long and short_recovering and rsi_in_pullback and rsi_hooking_up and real_pullback:
                    signal = 1
                    depth = (50 - current_rsi) / 17
                    convergence = min((slope_long - slope_short) / 0.05, 1.0) if slope_long > slope_short else 0
                    trend_strength = min(slope_long / 0.10, 1.0)
                    confidence = round(min(depth * 0.3 + convergence * 0.3 + trend_strength * 0.4, 1.0), 2)

            elif regime == "MUY_BAJISTA":
                # ── Layer 3: Structural divergence via regression slopes ──
                # In severe bear: RSI oversold + recovering = contrarian entry
                # (Mirror: NO trim here — RSI high in MUY_BAJISTA = V-recovery)
                price_falling = slope_short < 0
                rsi_recovering = rsi_slope_short > 0
                rsi_oversold = current_rsi < 40

                if price_falling and rsi_recovering and rsi_oversold:
                    signal = 1
                    div_strength = min(abs(slope_short) + abs(rsi_slope_short), 1.0)
                    confidence = round(0.5 + div_strength * 0.2, 2)

            elif regime == "BAJISTA":
                # ── BAJISTA entry: same divergence logic as MUY_BAJISTA ──
                price_falling = slope_short < 0
                rsi_recovering = rsi_slope_short > 0
                rsi_oversold = current_rsi < 40

                if price_falling and rsi_recovering and rsi_oversold:
                    signal = 1
                    div_strength = min(abs(slope_short) + abs(rsi_slope_short), 1.0)
                    confidence = round(0.5 + div_strength * 0.2, 2)

            else:  # FLAT
                # ── FLAT: Only extreme divergence ──
                if current_rsi < 35:
                    price_falling = slope_short < 0
                    rsi_recovering = rsi_slope_short > 0
                    if price_falling and rsi_recovering:
                            signal = 1
                            confidence = 0.5

            # ═══════════════════════════════════════════════════
            # TRIM SIGNALS (signal = -1) — Layer 7
            # [HYPOTHESIS] D — Advisory Only. Pending WF-DSR.
            #
            # The regime-inverted RSI reading:
            #   BULL: valid signals are at RSI LOWS (entries)
            #   BAJISTA: valid signals are at RSI HIGHS (trims)
            #   MUY_BAJISTA: NO trim — high RSI = V-recovery
            #
            # Forensic basis (110K events, 32 tickers, 20yr):
            #   BAJISTA + RSI>=65 + RSI↓: P(fall)=52.8%, N=106
            #   BAJISTA + RSI>=60 + RSI↓: P(fall)=52.0%, N=202
            # ═══════════════════════════════════════════════════

            if signal == 0:  # Only check trim if no entry signal
                trim_signal, trim_conf = self._check_rsi_trim(
                    regime, current_rsi, rsi_slope_short,
                    slope_short, slope_long,
                )
                if trim_signal:
                    signal = -1
                    confidence = trim_conf

            # ── Layer 5: Fear Level Bias (dual RC channel) ──
            # Applied AFTER signal generation — modulates confidence, doesn't gate
            if signal == 1:
                confidence = self._apply_fear_bias(ohlc, i, confidence)

            # ── Layer 6: Kalman ACCUMULATION Confirmation ──
            # Applied AFTER signal — boosts confidence when Kalman confirms
            if signal == 1:
                confidence = self._apply_kalman_boost(kalman_states, i, confidence)

            signals.append(signal)
            confidences.append(confidence)

        return pd.DataFrame({
            "signal": signals,
            "confidence": confidences,
        }, index=ohlc.index)

    @staticmethod
    def _check_rsi_trim(
        regime: str, current_rsi: float, rsi_slope: float,
        slope_short: float, slope_long: float,
    ) -> tuple[bool, float]:
        """Layer 7: Regime-Inverted RSI Trim Detection.

        [HYPOTHESIS] D — Advisory Only. Pending Walk-Forward DSR validation.

        The key insight: RSI reading is ASYMMETRIC by regime.
          - In BULL: entries are at RSI lows (pullback buying)
          - In BAJISTA: trims are at RSI highs (bear rally exhaustion)
          - In MUY_BAJISTA: NO trim — high RSI = V-recovery momentum

        The mirror logic of entry:
          ENTRY (BULL): price falling (short < long) + RSI low + RSI hooking UP
          TRIM (BAJISTA): price bouncing (short > 0) + RSI high + RSI hooking DOWN

        Forensic basis (110K events, 32 tickers, 20yr):
          BAJISTA + RSI>=65 + RSI_slope<0: P(fall 10d)=52.8%, Avg=-0.31% (N=106)
          BAJISTA + RSI>=60 + RSI_slope<0: P(fall 10d)=52.0%, Avg=-0.18% (N=202)

        Confidence tiers:
          RSI ≥ 70 + RSI falling:  confidence 0.30 (stronger signal)
          RSI ≥ 65 + RSI falling:  confidence 0.20
          RSI ≥ 60 + RSI falling:  confidence 0.15 (weakest trim)
        """
        # ── BAJISTA only (slope_long between -0.02 and -0.005) ──
        # MUY_BAJISTA excluded: RSI high there = V-recovery, NOT exhaustion
        if regime == "BAJISTA":
            rsi_falling = rsi_slope < 0

            if rsi_falling and current_rsi >= 70:
                return True, 0.30
            if rsi_falling and current_rsi >= 65:
                return True, 0.20
            if rsi_falling and current_rsi >= 60:
                return True, 0.15

        # ── FLAT: bounce exhaustion (price bouncing but RSI peaking) ──
        if regime == "FLAT":
            price_bouncing = slope_short > 0
            rsi_peaking = rsi_slope < 0
            if price_bouncing and rsi_peaking and current_rsi >= 65:
                return True, 0.15

        return False, 0.0

    @staticmethod
    def _find_swing_lows(data: np.ndarray, min_dist: int = 3) -> list[int]:
        """Find local minima indices."""
        lows = []
        for i in range(1, len(data) - 1):
            if data[i] < data[i - 1] and data[i] <= data[i + 1]:
                if not lows or (i - lows[-1]) >= min_dist:
                    lows.append(i)
        return lows

    def _apply_fear_bias(self, ohlc: pd.DataFrame, idx: int, base_confidence: float) -> float:
        """Layer 5: Modulate confidence by fear_level from dual RC channel.

        Empirical basis (forensic audit, 20 tickers × 5 years):
          PANIC (fear=5): P(↑)=47.6%, Ret20d=+3.12% → confidence BOOST
          FEAR (fear=4): P(↑)=44.9% → confidence BOOST
          ANXIETY (fear=3): P(↑)=43.7% → slight BOOST
          NEUTRAL (fear=2): no change
          CONFIDENCE (fear=1): P(↑)=41.2% → slight PENALTY
          GREED (fear=0): P(↑)=40.4%, Ret20d=+1.26% → confidence PENALTY

        The fear_level comes from the SEPARATE dual regression channel
        (200-bar tide + cycle-adaptive wave) — NOT from the RSI's own
        regressions (120/60). Two independent confirmation sources.
        """
        try:
            from backend.modules.quality_swing.domain.rules.fear_level import compute_ticker_fear_level
            bias = compute_ticker_fear_level(ohlc, idx)
            if bias is None:
                return base_confidence

            # Contrarian scaling: higher fear = higher conviction
            fear_bonus_map = {
                5: +0.20,   # PANIC — best forward return
                4: +0.15,   # FEAR
                3: +0.08,   # ANXIETY
                2: 0.00,    # NEUTRAL — no change
                1: -0.05,   # CONFIDENCE — slight penalty
                0: -0.10,   # GREED — worst forward return
            }
            bonus = fear_bonus_map.get(bias.fear_level, 0.0)

            # Wave flip positive (knife stopped falling) = extra conviction
            if bias.wave_flip and bias.wave_flip_direction == 1 and bias.fear_level >= 3:
                bonus += 0.10  # Slope conjugation — the true edge

            adjusted = min(max(base_confidence + bonus, 0.1), 1.0)
            return round(adjusted, 2)
        except Exception:
            return base_confidence

    def _apply_kalman_boost(self, kalman_states: dict, idx: int, base_confidence: float) -> float:
        """Layer 6: Boost confidence when Kalman-Wyckoff confirms ACCUMULATION.

        Validated conjugation (oracle-training-forensic KI):
          RSI solo: WR 75.7% → RSI + Kalman: WR 93.5%
          This is the HIGHEST VALIDATED CONJUGATION in the entire system.

        When both RSI and Kalman agree, the trade has:
          - Regime confirmation (price regression)
          - Momentum exhaustion (RSI divergence)
          - Institutional accumulation (Kalman Wyckoff)
        = Triple confirmation → maximum conviction.
        """
        state = kalman_states.get(idx)
        if state is None:
            return base_confidence

        wyckoff = state.get("wyckoff_state", "UNKNOWN")
        velocity = state.get("velocity", 0.0)

        if wyckoff == "ACCUMULATION" and velocity > 0:
            # Kalman confirms → boost confidence by 25%
            # Forensic: this conjugation raised WR from 75.7% to 93.5%
            boosted = min(base_confidence * 1.25, 1.0)
            return round(boosted, 2)
        elif wyckoff == "DISTRIBUTION" and velocity < 0:
            # Kalman contradicts → reduce confidence
            reduced = max(base_confidence * 0.60, 0.1)
            return round(reduced, 2)

        return base_confidence

    @staticmethod
    def _precompute_kalman(ohlc: pd.DataFrame) -> dict:
        """Pre-compute Kalman Wyckoff states for all bars (avoid N² cost)."""
        try:
            from backend.modules.volume_intelligence.application.use_cases.track_volume_dynamics import (
                KalmanVolumeTracker,
            )
            tracker = KalmanVolumeTracker(dt=1.0, process_noise=0.05, obs_noise=0.2)
            vol_series = ohlc["volume"].astype(float)
            vol_mean_20 = vol_series.rolling(window=20, min_periods=1).mean()
            states = {}

            for i in range(len(ohlc)):
                row = ohlc.iloc[i]
                raw_vol = float(row["volume"])
                avg_vol = float(vol_mean_20.iloc[i])
                observed_rvol = raw_vol / avg_vol if avg_vol > 0 else 1.0

                prev_close = float(ohlc.iloc[max(0, i - 1)]["close"])
                curr_close = float(row["close"])
                change_pct = ((curr_close - prev_close) / prev_close * 100) if prev_close > 0 else 0.0

                state = tracker.update("RSI_KALMAN", observed_rvol, change_pct)
                states[i] = state

            return states
        except Exception:
            return {}

    def required_context(self) -> list[str]:
        return []


class FlowSignalAdapter(SignalPort):
    """Signal from UW flow features: persistence confirmed + high sweep count."""

    @property
    def name(self) -> str:
        return "flow_persistence"

    def generate(self, ohlc: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
        signals = pd.Series(0, index=ohlc.index)

        if context and "uw_flow_features" in context:
            flow = context["uw_flow_features"]
            if isinstance(flow, pd.DataFrame) and not flow.empty:
                # Align flow features with OHLCV index via forward-fill join
                aligned = flow.reindex(ohlc.index, method="ffill")

                sweep_ok = aligned.get("uw_sweep_count", pd.Series(0, index=ohlc.index)) > 0
                score_ok = aligned.get("uw_flow_score", pd.Series(0, index=ohlc.index)) >= 60

                signals = (sweep_ok & score_ok).astype(int)

        return pd.DataFrame({"signal": signals}, index=ohlc.index)

    def required_context(self) -> list[str]:
        return ["uw_flow_features"]


class BOSSignalAdapter(SignalPort):
    """Self-contained BOS/CHoCH signal via smartmoneyconcepts.

    Pre-computes SMC structure once on the full OHLCV history,
    then extracts BOS/CHoCH events as signals. No external context needed.
    """

    @property
    def name(self) -> str:
        return "bos_choch"

    def generate(self, ohlc: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
        signals = pd.Series(0, index=ohlc.index, dtype=int)

        if len(ohlc) < 50:
            return pd.DataFrame({"signal": signals}, index=ohlc.index)

        try:
            from smartmoneyconcepts import smc
        except ImportError:
            logger.warning("smartmoneyconcepts not installed")
            return pd.DataFrame({"signal": signals}, index=ohlc.index)

        try:
            df = ohlc.copy()
            df.columns = [c.lower() for c in df.columns]

            # Single-pass: compute swing structure + BOS/CHoCH on full history
            swing_hl = smc.swing_highs_lows(df, swing_length=10)
            if swing_hl is None or swing_hl.empty:
                return pd.DataFrame({"signal": signals}, index=ohlc.index)

            bos_choch = smc.bos_choch(df, swing_hl)
            if bos_choch is None or bos_choch.empty:
                return pd.DataFrame({"signal": signals}, index=ohlc.index)

            # Extract BOS events: +1 = bullish BOS, -1 = bearish BOS
            bos_mask = bos_choch["BOS"].notna()
            if bos_mask.any():
                bos_vals = bos_choch.loc[bos_mask, "BOS"]
                for idx in bos_vals.index:
                    if idx < len(signals):
                        signals.iloc[idx] = 1 if bos_vals[idx] > 0 else -1

            # CHoCH events override: bearish CHoCH = -1, bullish CHoCH = +1
            choch_mask = bos_choch["CHOCH"].notna()
            if choch_mask.any():
                choch_vals = bos_choch.loc[choch_mask, "CHOCH"]
                for idx in choch_vals.index:
                    if idx < len(signals):
                        signals.iloc[idx] = 1 if choch_vals[idx] > 0 else -1

        except Exception as e:
            logger.error(f"BOSSignalAdapter error: {e}")

        return pd.DataFrame({"signal": signals}, index=ohlc.index)

    def required_context(self) -> list[str]:
        return []


class PatternSignalAdapter(SignalPort):
    """Dual-Layer Pattern Recognition — Micro (3 real candles) + Macro (3 super-candles).

    Forensic audit 2026-05-13: Original adapter only detected Bullish Engulfing
    (1 of 17 patterns). Replaced with full PatternRecognitionIntelligence engine
    operating on two layers:

    MICRO LAYER (3 real bars):
      Detects all 17 patterns (single, double, triple) on the actual daily candles.
      This is the TRIGGER — "what happened today?"

    MACRO LAYER (3 super-candles synthesized from 15 bars):
      Groups bars into 3 "super-candles" of 5 bars each (~1 trading week).
      Detects the same 17 patterns on the structural formation.
      This is the CONTEXT — "what pattern is the 3-week structure building?"

    POSITION:
      Where did price close within the current super-candle being formed?
      0.0 = floor of the week → potential reversal
      1.0 = ceiling of the week → potential exhaustion

    SIGNAL LOGIC — [VALIDATED Grade C] (Forensic DSR + 20yr Deep History, 2026-05-19):
      Downgraded A→C: base signal overfit to 2022 crash with 5yr data.
      With 20yr history: WR 62.9% (N=717). Narrative decomposition enriches.

      1. Hyper Capitulation (WR 62.9%, N=717):
         HYPER THREE_BLACK_CROWS en DLR MUY_BAJISTA → COMPRA
         Confidence modified by internal narrative (0.3 to 1.5):
           - BEARISH_ENGULFING central: ×1.25 (73.9% WR, N=23)
           - BEARISH_MARUBOZU central:  ×1.25 (75.0% WR, N=16)
           - DRAGONFLY_DOJI central:    ×0.50 (28.6% WR, anti-signal)
           - MORNING_STAR conclusion:   ×0.60 (54.5% WR, trap)
      2. Micro Capitulation (Sharpe 2.257, N=102):
         MICRO BEARISH_MARUBOZU en DLR MUY_BAJISTA → COMPRA
      
      ANTI-SEÑALES (Veto):
      1. MACRO/HYPER SHOOTING_STAR en ALCISTA → Ignorar reversión (Sharpe negativo)
         El mercado absorbe el patrón y sigue subiendo.

    Empirical basis: Walk-Forward Purged CV (2yr Train/6mo Test) + 
    Deflated Sharpe Ratio > 1.0 en 32 tickers (30 Quality + SPY + QQQ, 20+ años).
    """

    SUPER_CANDLE_SIZE = 5   # bars per super-candle (≈1 trading week)
    N_SUPER_CANDLES = 3     # number of super-candles to synthesize
    HYPER_SUPER_SIZE = 5    # bars per super-candle within each hyper-candle
    HYPER_N_SUPERS = 3      # super-candles per hyper-candle
    N_HYPER_CANDLES = 3     # number of hyper-candles (3 × 15 = 45 bars)
    MIN_LOOKBACK = 60       # DLR needs 60 bars for valid trend classification

    def __init__(self):
        from backend.modules.pattern_recognition.application.use_cases.detect_patterns import (
            PatternRecognitionIntelligence,
        )
        self._engine = PatternRecognitionIntelligence()

    @property
    def name(self) -> str:
        return "pattern_recognition"

    @staticmethod
    def synthesize_super_candles(
        ohlc: pd.DataFrame,
        end_idx: int,
        group_size: int = 5,
        n_groups: int = 3,
    ) -> pd.DataFrame | None:
        """Synthesize n_groups super-candles from consecutive bar groups.

        Each super-candle compresses `group_size` real bars into one OHLC bar:
          Open  = open of the first bar in the group
          High  = max high across all bars in the group
          Low   = min low across all bars in the group
          Close = close of the last bar in the group
          Volume = sum of volumes

        Args:
            ohlc: Full OHLC DataFrame.
            end_idx: Index (iloc) of the last bar to include in synthesis.
                     Super-candles are built from bars BEFORE the micro window.
            group_size: Number of bars per super-candle (default 5 = ~1 week).
            n_groups: Number of super-candles to build (default 3).

        Returns:
            DataFrame with n_groups rows of synthesized OHLC, or None if
            insufficient data.
        """
        total_bars_needed = group_size * n_groups
        start_idx = end_idx - total_bars_needed + 1
        if start_idx < 0:
            return None

        super_candles = []
        # Select only OHLCV columns to avoid mixed-dtype iloc issues
        # (historical data may have NaN in vwap/trade_count)
        ohlcv_cols = [c for c in ["open", "high", "low", "close", "volume"] if c in ohlc.columns]
        ohlc_clean = ohlc[ohlcv_cols]
        for g in range(n_groups):
            g_start = start_idx + g * group_size
            g_end = g_start + group_size
            group = ohlc_clean.iloc[g_start:g_end]

            super_candles.append({
                "Open": float(group.iloc[0]["open"]),
                "High": float(group["high"].max()),
                "Low": float(group["low"].min()),
                "Close": float(group.iloc[-1]["close"]),
                "Volume": float(group["volume"].sum()),
            })

        return pd.DataFrame(super_candles)

    @staticmethod
    def compute_position_in_formation(
        ohlc: pd.DataFrame,
        current_idx: int,
        group_size: int = 5,
    ) -> float:
        """Compute where current price sits within the super-candle being formed.

        Looks at the most recent `group_size` bars ending at current_idx
        (the current week in construction) and returns a 0.0-1.0 position.

        Returns:
            0.0 = price at the floor of the current formation
            1.0 = price at the ceiling
            0.5 = mid-range (indecision)
        """
        start = max(0, current_idx - group_size + 1)
        window = ohlc.iloc[start:current_idx + 1]
        if window.empty:
            return 0.5

        formation_high = float(window["high"].max())
        formation_low = float(window["low"].min())
        current_close = float(ohlc["close"].iloc[current_idx])

        rng = formation_high - formation_low
        if rng <= 0:
            return 0.5

        return max(0.0, min(1.0, (current_close - formation_low) / rng))

    @staticmethod
    def synthesize_hyper_candles(
        ohlc: pd.DataFrame,
        end_idx: int,
        super_size: int = 5,
        n_supers: int = 3,
        n_hypers: int = 3,
    ) -> pd.DataFrame | None:
        """Synthesize n_hypers hyper-candles from consecutive super-candle groups.

        Each hyper-candle compresses `super_size * n_supers` real bars into one OHLC bar.
        Default: 3 hyper-candles × 15 bars each = 45 bars total.

        This captures structural narratives invisible to daily or weekly candles:
        - THREE_BLACK_CROWS at HYPER scale = 3 consecutive weeks of selling
        - Validated Grade A signal (Sharpe 1.893, N=300, DSR=1.000)

        Args:
            ohlc: Full OHLC DataFrame (lowercase columns: open, high, low, close, volume).
            end_idx: Index (iloc) of the last bar to include.
            super_size: Bars per super-candle within each hyper-candle (default 5).
            n_supers: Super-candles per hyper-candle (default 3).
            n_hypers: Number of hyper-candles to build (default 3).

        Returns:
            DataFrame with n_hypers rows of synthesized OHLC (Title Case columns),
            or None if insufficient data.
        """
        bars_per_hyper = super_size * n_supers
        total = bars_per_hyper * n_hypers
        start = end_idx - total + 1
        if start < 0:
            return None

        hyper_candles = []
        ohlcv_cols = [c for c in ["open", "high", "low", "close", "volume"] if c in ohlc.columns]
        ohlc_clean = ohlc[ohlcv_cols]
        for h in range(n_hypers):
            h_s = start + h * bars_per_hyper
            h_e = h_s + bars_per_hyper
            grp = ohlc_clean.iloc[h_s:h_e]
            hyper_candles.append({
                "Open": float(grp.iloc[0]["open"]),
                "High": float(grp["high"].max()),
                "Low": float(grp["low"].min()),
                "Close": float(grp.iloc[-1]["close"]),
                "Volume": float(grp["volume"].sum()),
            })

        return pd.DataFrame(hyper_candles)

    # ── Bearish MACRO patterns that confirm capitulation narrative ──
    _BEARISH_MACROS = frozenset({
        "BEARISH_MARUBOZU", "BEARISH_ENGULFING", "THREE_BLACK_CROWS",
        "DARK_CLOUD_COVER", "EVENING_STAR",
    })
    # ── Patterns that indicate premature buying (traps) ──
    _TRAP_CONCLUSIONS = frozenset({
        "MORNING_STAR", "BULLISH_ENGULFING", "THREE_WHITE_SOLDIERS",
    })
    # ── High-confidence central signatures (empirical 73-75% WR, N=16-23) ──
    _DEEP_CENTRAL = frozenset({"BEARISH_ENGULFING", "BEARISH_MARUBOZU"})
    # ── Anti-signal central patterns (empirical 28.6% WR, N=7) ──
    _WEAK_CENTRAL = frozenset({"DRAGONFLY_DOJI"})

    @staticmethod
    def decompose_narrative(
        engine,
        ohlc: pd.DataFrame,
        end_idx: int,
        super_size: int = 5,
        n_supers: int = 3,
        n_hypers: int = 3,
    ) -> dict | None:
        """Decompose a HYPER pattern into its internal MACRO narrative.

        Reads the 'words' (MACRO patterns) inside each 'paragraph' (hyper-candle)
        to determine narrative quality and confidence.

        Empirical basis (2026-05-19, 20yr, 32 tickers, N=717):
          - BEARISH_ENGULFING central: 73.9% WR (N=23)  → confidence ×1.25
          - BEARISH_MARUBOZU central:  75.0% WR (N=16)  → confidence ×1.25
          - DRAGONFLY_DOJI central:    28.6% WR (N=7)   → confidence ×0.50
          - SHOOTING_STAR conclusion:  87.5% WR (N=8)   → confidence boost
          - MORNING_STAR conclusion:   54.5% WR (N=22)  → trap, confidence ×0.60

        Returns:
            {
                'macro_central': str,    # Pattern of 2nd hyper-candle
                'macro_final': str,      # Pattern of 3rd hyper-candle
                'narrative_type': str,   # 'DEEP' | 'NEUTRAL' | 'DILUTED'
                'confidence': float,     # 0.3 to 1.5 sizing modifier
            }
            or None if insufficient data.
        """
        bars_per_hyper = super_size * n_supers  # 15
        total = bars_per_hyper * n_hypers       # 45
        start = end_idx - total + 1
        if start < 0:
            return None

        ohlcv_cols = [c for c in ["open", "high", "low", "close", "volume"] if c in ohlc.columns]
        ohlc_clean = ohlc[ohlcv_cols]

        # Build 3 MACRO patterns (one per hyper-candle)
        macro_patterns = []
        for h in range(n_hypers):
            h_start = start + h * bars_per_hyper
            # Build n_supers super-candles inside this hyper-candle
            super_candles = []
            for s in range(n_supers):
                s_start = h_start + s * super_size
                s_end = s_start + super_size
                grp = ohlc_clean.iloc[s_start:s_end]
                if len(grp) < super_size:
                    super_candles = []
                    break
                super_candles.append({
                    "Open": float(grp.iloc[0]["open"]),
                    "High": float(grp["high"].max()),
                    "Low": float(grp["low"].min()),
                    "Close": float(grp.iloc[-1]["close"]),
                    "Volume": float(grp["volume"].sum()),
                })

            if len(super_candles) == n_supers:
                macro_df = pd.DataFrame(super_candles)
                macro_verdict = engine.detect(macro_df)
                macro_patterns.append(macro_verdict.primary_pattern)
            else:
                macro_patterns.append("NONE")

        if len(macro_patterns) < 3:
            return None

        macro_central = macro_patterns[1]  # The "central word"
        macro_final = macro_patterns[2]    # The "conclusion"

        # ── Compute confidence modifier ──
        confidence = 1.0

        # Central word enrichment
        if macro_central in PatternSignalAdapter._DEEP_CENTRAL:
            confidence = 1.25
        elif macro_central in PatternSignalAdapter._WEAK_CENTRAL:
            confidence = 0.50

        # Conclusion enrichment
        if macro_final == "SHOOTING_STAR":
            confidence = min(confidence * 1.3, 1.5)
        elif macro_final in PatternSignalAdapter._TRAP_CONCLUSIONS:
            confidence *= 0.60

        confidence = max(0.3, min(1.5, confidence))

        # Classify narrative type
        non_none = [m for m in macro_patterns if m != "NONE"]
        if all(m in PatternSignalAdapter._BEARISH_MACROS for m in non_none) and non_none:
            narrative_type = "DEEP"
        elif any(m in PatternSignalAdapter._TRAP_CONCLUSIONS for m in macro_patterns):
            narrative_type = "DILUTED"
        else:
            narrative_type = "NEUTRAL"

        # ── Raw morphology of each hyper-candle (beyond patterns) ──
        # These metrics tell the story even when no cataloged pattern fires.
        hyper_df = PatternSignalAdapter.synthesize_hyper_candles(
            ohlc, end_idx=end_idx,
            super_size=super_size, n_supers=n_supers, n_hypers=n_hypers,
        )
        morphology = []
        if hyper_df is not None and len(hyper_df) >= n_hypers:
            for _, candle in hyper_df.iterrows():
                rng = candle["High"] - candle["Low"]
                if rng > 0:
                    body = abs(candle["Close"] - candle["Open"])
                    body_ratio = body / rng          # 0=doji, 1=marubozu
                    upper_wick = candle["High"] - max(candle["Open"], candle["Close"])
                    wick_bias = upper_wick / rng     # 0=no rejection, 1=all wick
                    close_pos = (candle["Close"] - candle["Low"]) / rng  # 0=floor, 1=ceiling
                else:
                    body_ratio = 0.0
                    wick_bias = 0.5
                    close_pos = 0.5
                morphology.append({
                    "body_ratio": round(body_ratio, 3),
                    "wick_bias": round(wick_bias, 3),
                    "close_position": round(close_pos, 3),
                    "bearish": candle["Close"] < candle["Open"],
                })

        # Morphology-based confidence adjustments — only validated metrics
        if len(morphology) == 3:
            final_candle = morphology[2]  # The conclusion
            # [VALIDATED] Close position: floor close (≤0.28) = 66.0% WR (+3.1pp)
            #             ceiling close (>0.28) = 59.8% WR (-3.1pp). N=717.
            if final_candle["close_position"] <= 0.28:
                confidence = min(confidence * 1.10, 1.5)
            # [VALIDATED] Extreme body ratio >0.80 = 71.9% WR (+9pp). N=64.
            if final_candle["body_ratio"] > 0.80:
                confidence = min(confidence * 1.15, 1.5)
            confidence = max(0.3, min(1.5, confidence))

        return {
            "macro_central": macro_central,
            "macro_final": macro_final,
            "narrative_type": narrative_type,
            "confidence": confidence,
            "morphology": morphology,  # Raw shape of each hyper-candle
        }

    @staticmethod
    def _compute_dlr_trend(ohlc: pd.DataFrame, lookback: int = 60) -> pd.Series:
        """Vectorized 60-day linear regression slope classification."""
        closes = ohlc["close"].values
        n = len(closes)
        trends = pd.Series("HORIZONTAL", index=ohlc.index)
        
        if n < lookback:
            return trends
            
        x = np.arange(lookback)
        x_mean = np.mean(x)
        x_diff = x - x_mean
        ss_xx = np.sum(x_diff ** 2)
        
        for i in range(lookback, n):
            y = closes[i-lookback:i]
            if y[0] <= 0:
                continue
            y_norm = y / y[0]
            
            y_mean = np.mean(y_norm)
            slope = np.sum(x_diff * (y_norm - y_mean)) / ss_xx
            
            if slope > 0.0020:
                trends.iloc[i] = "MUY_ALCISTA"
            elif slope > 0.0005:
                trends.iloc[i] = "ALCISTA"
            elif slope > -0.0005:
                trends.iloc[i] = "HORIZONTAL"
            elif slope > -0.0020:
                trends.iloc[i] = "BAJISTA"
            else:
                trends.iloc[i] = "MUY_BAJISTA"
                
        return trends

    def generate(self, ohlc: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
        signals = pd.Series(0, index=ohlc.index)
        
        # [VALIDATED] DLR Trend State — regime classifier for pattern conjugation
        trend_series = self._compute_dlr_trend(ohlc, lookback=60)

        # Precompute column-name normalization for the engine
        # The engine expects Title Case columns; ohlc has lowercase
        for i in range(self.MIN_LOOKBACK, len(ohlc)):
            try:
                # ── MICRO: 3 real candles ──
                micro_window = ohlc.iloc[max(0, i - 2):i + 1].copy()
                micro_window.columns = [c.capitalize() for c in micro_window.columns]
                micro_verdict = self._engine.detect(micro_window)
                micro_pattern = micro_verdict.primary_pattern

                # ── MACRO: 3 super-candles from 15 bars ──
                macro_end_idx = i - 3
                super_df = self.synthesize_super_candles(
                    ohlc, end_idx=macro_end_idx,
                    group_size=self.SUPER_CANDLE_SIZE,
                    n_groups=self.N_SUPER_CANDLES,
                )
                macro_pattern = "NONE"
                if super_df is not None and len(super_df) >= 3:
                    super_df.columns = [c.capitalize() for c in super_df.columns]
                    macro_verdict = self._engine.detect(super_df)
                    macro_pattern = macro_verdict.primary_pattern

                # ── HYPER: 3 hyper-candles of 15 bars each (45 bars total) ──
                # Each hyper-candle compresses 3 super-candles (5 bars each).
                # This is the validated Grade A layer (Sharpe 1.893, N=300).
                hyper_pattern = "NONE"
                hyper_df = self.synthesize_hyper_candles(
                    ohlc, end_idx=i,
                    super_size=self.HYPER_SUPER_SIZE,
                    n_supers=self.HYPER_N_SUPERS,
                    n_hypers=self.N_HYPER_CANDLES,
                )
                if hyper_df is not None and len(hyper_df) >= 3:
                    hyper_verdict = self._engine.detect(hyper_df)
                    hyper_pattern = hyper_verdict.primary_pattern
                
                trend_state = trend_series.iloc[i]

                # =====================================================================
                # [VALIDATED] EVIDENCE STATUS TAG: GRADE C (Sizing Modifier)
                # Walk-Forward PCV + Deflated Sharpe Ratio executed 2026-05-19.
                # 32 tickers, 20yr history. N=717 (base WR 62.9%).
                # Downgraded from A→C: signal overfit to 2022 crash with 5yr data.
                # Narrative decomposition enriches to 73-75% WR on specific sigs.
                # =====================================================================

                # ── 1. The Contrarian Hyper-Capitulation (WR 62.9%, N=717) ──
                # 3 consecutive hyper-candles (45 days total) of selling in a
                # MUY_BAJISTA regime. Confidence modified by internal narrative:
                #   - BEARISH_ENGULFING central: ×1.25 (73.9% WR, N=23)
                #   - BEARISH_MARUBOZU central:  ×1.25 (75.0% WR, N=16)
                #   - DRAGONFLY_DOJI central:    ×0.50 (28.6% WR, N=7)
                #   - MORNING_STAR conclusion:   ×0.60 (54.5% WR, N=22)
                if trend_state == "MUY_BAJISTA" and hyper_pattern == "THREE_BLACK_CROWS":
                    narrative = self.decompose_narrative(
                        self._engine, ohlc, end_idx=i,
                    )
                    confidence = narrative["confidence"] if narrative else 1.0
                    signals.iloc[i] = confidence
                    continue

                # ── 2. The Micro Capitulation (Sharpe 2.257) ──
                # A massive single-day or 3-day drop without any intraday bounce
                # (Bearish Marubozu) in a MUY_BAJISTA regime. Provides maximum
                # liquidity for institutional entry.
                if trend_state == "MUY_BAJISTA" and micro_pattern == "BEARISH_MARUBOZU":
                    signals.iloc[i] = 1
                    continue
                    
                # =====================================================================
                # 🚨 ANTI-SIGNALS (Destruyen capital - Sharpe negativo demostrado)
                # =====================================================================
                
                # Un Shooting Star en tendencia ALCISTA no es una señal de reversión,
                # el mercado simplemente la absorbe y sigue subiendo. Actuar como si
                # fuera una reversión o tratar de comprar el "dip" produce retornos 
                # negativos (Sharpe OOS = -0.50 a -1.07).
                if trend_state == "ALCISTA":
                    if macro_pattern == "SHOOTING_STAR" or hyper_pattern == "SHOOTING_STAR":
                        signals.iloc[i] = -1  # Señal de VETO / ADVERTENCIA
                        continue

            except Exception:
                continue

        return pd.DataFrame({"signal": signals}, index=ohlc.index)

    def required_context(self) -> list[str]:
        return []


class RegressionChannelAdapter(SignalPort):
    """Statistical Regression Channel + VWAP Tension — Fully Assembled (8 layers).

    The BEST standalone signal in the system: Sharpe 1.326, WR 82.2% (THESIS).
    Now fully assembled with all forensic-validated enhancements.

    Architecture (8 validated layers):
      1. Long regression (200 bars, FIXED) → channel center line (the tide)
      2. Short regression (cycle-adaptive) → micro-momentum direction (the wave)
      3. VWAP (20 bars) → institutional fair price reference
      4. 1-bar hookup → reversal candle confirmation
      5. FEAR LEVEL BIAS → contrarian: PANIC +0.20, GREED -0.10
         Empirical: P(↑)=47.6% at PANIC vs 40.4% at GREED (7.2pt spread)
      6. KALMAN ACCUMULATION → confirmation boost 1.25×
         Empirical: RC+Kalman WR 78.2→84.2% (+6pts)
      7. VOLUME UP/DOWN RATIO → stealth distribution detection
         Production PricePhaseIntelligence uses this (L212-227). If vol on DOWN
         days > UP days → DISTRIBUTION disguised as correction → penalty
      8. TRIM OUTPUT → signal=-1 when movement exhausted
         σ≥+1.5 AND (fear_level≤1 OR wave_flip negative) → trim signal

    SLOPE CONJUGATION — The Determinant Feature:
      Feature J11 (MTF_SlopeConjugation_5): ranked #11 global, spread -6.7%
      wave_slope - tide_slope < 0 → wave falling, tide rising → PULLBACK
      This yields WR=100% under THESIS geometry. The ANGLE between the two
      lines is what separates winners from losers.

    Entry logic:
      BULL: σ ≤ -1.5, below VWAP, hookup → confidence modulated by fear+Kalman+vol
      BEAR: shallow (> -0.03), σ ≤ -2.0, short turning, VWAP cross
      FLAT: σ ≤ -2.0, hookup → WR 91.7% (THESIS)

    Trim logic (NEW):
      σ ≥ +2.0 AND fear=0: signal=-1, confidence=0.50 (max trim)
      σ ≥ +1.5 AND fear≤1: signal=-1, confidence=0.25
      σ ≥ +1.0 AND wave_flip neg AND fear≤1: signal=-1, confidence=0.15
    """

    @property
    def name(self) -> str:
        return "regression_channel"

    @staticmethod
    def _linreg_channel(close: np.ndarray, window: int):
        """Delegated to quality_swing/domain/rules/regression_channel.py."""
        from backend.modules.quality_swing.domain.rules.regression_channel import linreg_channel
        return linreg_channel(close, window)

    @staticmethod
    def _calc_vwap(close: np.ndarray, high: np.ndarray, low: np.ndarray,
                   volume: np.ndarray, window: int = 20) -> float:
        """Delegated to quality_swing/domain/rules/regression_channel.py."""
        from backend.modules.quality_swing.domain.rules.regression_channel import calc_vwap
        return calc_vwap(close, high, low, volume, window)

    def generate(self, ohlc: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
        close = ohlc["close"].values.astype(float)
        high_arr = ohlc["high"].values.astype(float)
        low_arr = ohlc["low"].values.astype(float)
        vol_arr = ohlc["volume"].values.astype(float)

        # ── Layer 2: Detect asset's dominant cycle for adaptive short regression ──
        dominant_cycle = RSISignalAdapter._detect_dominant_cycle(close)
        short_window = max(10, min(dominant_cycle, 60))  # Clamp to 10-60

        # ── Layer 6: Pre-compute Kalman states for all bars ──
        kalman_states = RSISignalAdapter._precompute_kalman(ohlc)

        signals = []
        confidences = []

        for i in range(len(ohlc)):
            if i < 200:
                signals.append(0)
                confidences.append(0.0)
                continue

            price_window = close[:i + 1]
            current_price = close[i]

            # ── Layer 1: LONG CHANNEL (200 bars, FIXED — the tide) ──
            reg_value, slope_long, residual_std = self._linreg_channel(price_window, 200)
            sigma_position = (current_price - reg_value) / residual_std

            # ── Layer 2: SHORT REGRESSION (cycle-adaptive — the wave) ──
            _, slope_short, _ = self._linreg_channel(price_window, short_window)

            # ── Layer 3: VWAP (institutional fair price) ──
            vwap = self._calc_vwap(
                close[:i + 1], high_arr[:i + 1], low_arr[:i + 1], vol_arr[:i + 1], 20
            )
            below_vwap = current_price < vwap

            # ── REGIME from long slope ──
            if slope_long > 0.01:
                regime = "BULL"
            elif slope_long < -0.01:
                regime = "BEAR"
            else:
                regime = "FLAT"

            signal = 0
            confidence = 0.0

            # ═══ ENTRY SIGNALS (signal = +1) ═══

            if regime == "BULL":
                # ── BULL: statistical pullback to channel support ──
                at_support = sigma_position <= -1.5
                # Forensic: winners have slope_short NEGATIVE (avg=-0.05).
                # The dip itself IS the signal — entering during the pullback.
                # Slope conjugation: wave < tide → the determinant feature (#11, -6.7% spread)
                hookup = close[i] > close[i - 1] if i > 0 else False

                if at_support and below_vwap and hookup:
                    signal = 1
                    depth = min(abs(sigma_position) / 2.0, 1.0)
                    vwap_discount = min(abs(vwap - current_price) / vwap * 100, 1.0) if vwap > 0 else 0
                    confidence = round(min(depth * 0.4 + vwap_discount * 0.3 + min(slope_long / 0.05, 1.0) * 0.3, 1.0), 2)

            elif regime == "BEAR":
                # ── BEAR: only SHALLOW bear trends + extreme σ ──
                # Forensic: 5/5 BEAR losers were UNH with slope_long < -0.05.
                # Winners had slope_long > -0.03 (shallow bear = pullback opportunity).
                shallow_bear = slope_long > -0.03
                at_extreme = sigma_position <= -2.0
                short_turning = slope_short > 0
                prev_vwap = self._calc_vwap(
                    close[:i], high_arr[:i], low_arr[:i], vol_arr[:i], 20
                ) if i > 20 else vwap
                vwap_cross_up = close[i - 1] < prev_vwap and current_price >= vwap if i > 0 else False

                if shallow_bear and at_extreme and short_turning and (below_vwap or vwap_cross_up):
                    signal = 1
                    confidence = round(min(abs(sigma_position) / 3.0 + 0.3, 1.0), 2)

            else:  # FLAT
                # ── FLAT: extreme σ with hookup ──
                # Forensic: FLAT regime has WR=91.7% (THESIS). Mean reversion is almost inevitable.
                if sigma_position <= -2.0 and close[i] > close[i - 1]:
                    signal = 1
                    confidence = 0.4

            # ═══ TRIM SIGNALS (signal = -1) — Layer 8 ═══

            if signal == 0:  # Only check trim if no entry signal
                trim_signal, trim_conf = self._check_trim(
                    ohlc, i, sigma_position, slope_short
                )
                if trim_signal:
                    signal = -1
                    confidence = trim_conf

            # ═══ POST-SIGNAL MODULATION (only for entries) ═══

            if signal == 1:
                # ── Layer 5: Fear Level Bias ──
                confidence = self._apply_fear_bias(ohlc, i, confidence)

                # ── Layer 6: Kalman ACCUMULATION Confirmation ──
                confidence = self._apply_kalman_boost(kalman_states, i, confidence)

                # ── Layer 7: Volume UP/DOWN Ratio ──
                confidence = self._apply_vol_ratio_check(ohlc, i, confidence)

            signals.append(signal)
            confidences.append(confidence)

        return pd.DataFrame({
            "signal": signals,
            "confidence": confidences,
        }, index=ohlc.index)

    # ── Layer 5: Fear Level Bias ──────────────────────────────────────

    def _apply_fear_bias(self, ohlc: pd.DataFrame, idx: int, base_confidence: float) -> float:
        """Modulate confidence by fear_level from the SAME dual regression channel.

        The RC adapter already computes tide_slope and wave_slope — these are
        exactly the inputs to compute_ticker_fear_level(). No circular dependency:
        fear_level classifies the STATE of the channel (fear/greed), while the
        entry rules use the POSITION within the channel (sigma).

        Empirical (20,580 obs): PANIC→47.6% P(↑), GREED→40.4% P(↑).
        """
        try:
            from backend.modules.quality_swing.domain.rules.fear_level import compute_ticker_fear_level
            bias = compute_ticker_fear_level(ohlc, idx)
            if bias is None:
                return base_confidence

            fear_bonus_map = {
                5: +0.20,   # PANIC — best forward return
                4: +0.15,   # FEAR
                3: +0.08,   # ANXIETY
                2: 0.00,    # NEUTRAL
                1: -0.05,   # CONFIDENCE
                0: -0.10,   # GREED — worst forward return
            }
            bonus = fear_bonus_map.get(bias.fear_level, 0.0)

            # Slope conjugation bonus: wave < tide (negative conj) = entry zone
            # Feature J11: spread -6.7%, the ANGLE between lines is determinant
            if bias.slope_conjugation < -0.03 and bias.fear_level >= 3:
                bonus += 0.10  # Deep pullback in fear = maximum conviction

            # Wave flip positive (knife stopped falling) + fear ≥ 3
            if bias.wave_flip and bias.wave_flip_direction == 1 and bias.fear_level >= 3:
                bonus += 0.08  # 8.6% spread validated

            adjusted = min(max(base_confidence + bonus, 0.1), 1.0)
            return round(adjusted, 2)
        except Exception:
            return base_confidence

    # ── Layer 6: Kalman ACCUMULATION ──────────────────────────────────

    def _apply_kalman_boost(self, kalman_states: dict, idx: int, base_confidence: float) -> float:
        """Boost confidence when Kalman-Wyckoff confirms ACCUMULATION.

        Validated: RC solo WR 78.2% → RC + Kalman WR 84.2% (+6pts, Ret +5.6%).
        """
        state = kalman_states.get(idx)
        if state is None:
            return base_confidence

        wyckoff = state.get("wyckoff_state", "UNKNOWN")
        velocity = state.get("velocity", 0.0)

        if wyckoff == "ACCUMULATION" and velocity > 0:
            boosted = min(base_confidence * 1.25, 1.0)
            return round(boosted, 2)
        elif wyckoff == "DISTRIBUTION" and velocity < 0:
            reduced = max(base_confidence * 0.60, 0.1)
            return round(reduced, 2)

        return base_confidence

    # ── Layer 7: Volume UP/DOWN Ratio ────────────────────────────────

    @staticmethod
    def _apply_vol_ratio_check(ohlc: pd.DataFrame, idx: int, base_confidence: float) -> float:
        """Detect stealth distribution via volume direction analysis.

        Production PricePhaseIntelligence (L212-227) uses this to block
        STEALTH_DISTRIBUTION: when volume on DOWN days > UP days, institutions
        are selling disguised as a correction.

        If vol_up/vol_down < 1.0 → penalize confidence by 30%.
        """
        if idx < 5:
            return base_confidence

        close = ohlc["close"].values.astype(float)
        volume = ohlc["volume"].values.astype(float)

        up_vol = 0.0
        down_vol = 0.0
        up_count = 0
        down_count = 0

        for j in range(max(0, idx - 4), idx + 1):
            if j > 0 and close[j] > close[j - 1]:
                up_vol += volume[j]
                up_count += 1
            elif j > 0:
                down_vol += volume[j]
                down_count += 1

        avg_up = up_vol / max(up_count, 1)
        avg_down = down_vol / max(down_count, 1)
        ratio = avg_up / avg_down if avg_down > 0 else 2.0

        if ratio < 0.8:
            # Strong distribution signal → heavy penalty
            reduced = max(base_confidence * 0.50, 0.1)
            return round(reduced, 2)
        elif ratio < 1.0:
            # Mild distribution → moderate penalty
            reduced = max(base_confidence * 0.70, 0.1)
            return round(reduced, 2)

        return base_confidence

    # ── Layer 8: Trim Detection ──────────────────────────────────────

    @staticmethod
    def _check_trim(
        ohlc: pd.DataFrame, idx: int,
        sigma_position: float, slope_short: float,
    ) -> tuple[bool, float]:
        """Detect movement exhaustion → emit TRIM signal.

        Based on empirical data:
          - σ ≥ +2.0 AND fear=0 (GREED): P(↑)=40.4% → max trim (50%)
          - σ ≥ +1.5 AND fear≤1: overextended → trim 25%
          - σ ≥ +1.0 AND wave_flip neg AND fear≤1: wave reversal → early trim 15%

        Trim ≠ sell. Trim = reduce swing allocation at statistical extremes.
        """
        try:
            from backend.modules.quality_swing.domain.rules.fear_level import compute_ticker_fear_level
            bias = compute_ticker_fear_level(ohlc, idx)
            if bias is None:
                return False, 0.0

            # Extreme GREED + overextended = max trim
            if sigma_position >= 2.0 and bias.fear_level == 0:
                return True, 0.50

            # Overextended
            if sigma_position >= 1.5 and bias.fear_level <= 1:
                return True, 0.25

            # Wave flip negative (knife started falling) at high sigma
            if (sigma_position >= 1.0 and bias.wave_flip
                    and bias.wave_flip_direction == -1 and bias.fear_level <= 1):
                return True, 0.15

        except Exception:
            pass

        return False, 0.0

    def required_context(self) -> list[str]:
        return []


# ═══════════════════════════════════════════════════════════════════════
# TICKER SENTIMENT BIAS — Re-exported from quality_swing module
# ═══════════════════════════════════════════════════════════════════════
# Canonical location: backend/modules/quality_swing/domain/
# Kept here as re-exports for backward compatibility.

from backend.modules.quality_swing.domain.entities.swing_bias import TickerSentimentBias  # noqa: F811
from backend.modules.quality_swing.domain.rules.fear_level import compute_ticker_fear_level  # noqa: F811


ALL_SIGNAL_ADAPTERS: list[type[SignalPort]] = [
    KalmanSignalAdapter,
    # VolumeQualitySignalAdapter ELIMINATED: Forensic audit 2026-05-13.
    # Created as HFT noise filter (commit 474e14b), mutated into signal adapter
    # during Phase 2 migration (commit 3d9daf9). Empirical results:
    # - As signal: 140 entries/yr/ticker (noise), Sharpe 0.89, no regime sensitivity
    # - As filter for RC: REDUCES WR by -5.3% and return by -1.69% (counterproductive)
    # - Winners have LOWER VQ than losers (inverted vs intent, p=0.082)
    # - Original purpose (filter HFT) invalid for daily bars on S&P 500 large caps
    RSISignalAdapter,
    FlowSignalAdapter,
    BOSSignalAdapter,
    PatternSignalAdapter,
    RegressionChannelAdapter,
]


def create_all_signals() -> list[SignalPort]:
    """Instantiate all available signal adapters."""
    return [cls() for cls in ALL_SIGNAL_ADAPTERS]

