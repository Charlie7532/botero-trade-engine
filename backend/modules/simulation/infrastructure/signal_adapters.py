"""
Signal Adapters — Thin Wrappers for Modular Evaluation
=========================================================
Each adapter wraps an existing intelligence module and implements
SignalPort for isolated Oracle testing and ML weight discovery.

The adapters are intentionally thin — they translate the module's
output into the canonical signal format (1=long, -1=short, 0=flat).
"""
import logging

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
    """RSI Intelligence signal: oversold zone + bullish divergence."""

    @property
    def name(self) -> str:
        return "rsi_intelligence"

    def generate(self, ohlc: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
        close = ohlc["close"]
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))

        # Simple oversold signal
        signal = (rsi < 30).astype(int)
        confidence = ((30 - rsi) / 30).clip(0, 1)

        return pd.DataFrame({
            "signal": signal,
            "confidence": confidence,
        }, index=ohlc.index)

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
    """Signal from candlestick pattern recognition on support."""

    @property
    def name(self) -> str:
        return "pattern_recognition"

    def generate(self, ohlc: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
        # Simplified: detect bullish engulfing pattern
        signals = pd.Series(0, index=ohlc.index)

        for i in range(1, len(ohlc)):
            prev = ohlc.iloc[i - 1]
            curr = ohlc.iloc[i]

            prev_bearish = prev["close"] < prev["open"]
            curr_bullish = curr["close"] > curr["open"]
            engulfing = curr["open"] <= prev["close"] and curr["close"] >= prev["open"]

            if prev_bearish and curr_bullish and engulfing:
                signals.iloc[i] = 1

        return pd.DataFrame({"signal": signals}, index=ohlc.index)

    def required_context(self) -> list[str]:
        return []


# ── Factory ──────────────────────────────────────────────────

ALL_SIGNAL_ADAPTERS: list[type[SignalPort]] = [
    KalmanSignalAdapter,
    MeanReversionSignalAdapter,
    VolumeQualitySignalAdapter,
    RSISignalAdapter,
    FlowSignalAdapter,
    BOSSignalAdapter,
    PatternSignalAdapter,
]


def create_all_signals() -> list[SignalPort]:
    """Instantiate all available signal adapters."""
    return [cls() for cls in ALL_SIGNAL_ADAPTERS]
