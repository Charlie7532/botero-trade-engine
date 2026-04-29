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
        from backend.modules.volume_intelligence.domain.use_cases.track_volume_dynamics import (
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

    def generate(self, ohlc: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
        from backend.modules.simulation.domain.use_cases.run_backtest import WalkForwardBacktester

        signals = []
        for i in range(len(ohlc)):
            if i < 20:
                signals.append(0)
                continue

            window = ohlc.iloc[max(0, i - 20):i + 1]
            try:
                vq = WalkForwardBacktester.volume_quality_score(
                    volumes=window["volume"].values,
                    closes=window["close"].values,
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
    """Signal from SMC Break of Structure: recent bullish BOS."""

    @property
    def name(self) -> str:
        return "bos_choch"

    def generate(self, ohlc: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
        signals = pd.Series(0, index=ohlc.index)

        if context and "smc_structure" in context:
            structure = context["smc_structure"]
            if isinstance(structure, pd.DataFrame) and not structure.empty:
                aligned = structure.reindex(ohlc.index, method="ffill")
                bos_bull = aligned.get("bos_direction", pd.Series("NONE", index=ohlc.index)) == "BULLISH"
                bos_recent = aligned.get("bos_bars_ago", pd.Series(999, index=ohlc.index)) <= 5
                signals = (bos_bull & bos_recent).astype(int)

        return pd.DataFrame({"signal": signals}, index=ohlc.index)

    def required_context(self) -> list[str]:
        return ["smc_structure"]


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
