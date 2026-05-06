"""
Quaternion Signal Adapter — Research-Only SignalPort
=======================================================
Implements the production SignalPort interface for Oracle testing.
NOT registered in production signal_adapters.py — lives in research.

Includes a self-calibrating prediction layer:
  D5: Q_pred_bull  — P(next bar bullish | current state neighborhood)
  D6: Q_pred_bear  — P(next bar bearish | current state neighborhood)
  D7: Q_pred_accuracy — Rolling hit rate of past predictions

The adapter accumulates a scorecard: at each bar, it compares
yesterday's prediction to today's reality and updates probabilities.
"""
import logging
from collections import defaultdict

import numpy as np
import pandas as pd

from backend.modules.simulation.domain.ports.signal_port import SignalPort
from backend.research_lab.models.quaternion_core import MarketQuaternion

logger = logging.getLogger(__name__)


class QuaternionScorecard:
    """
    Self-calibrating prediction tracker.

    Discretizes the 4D quaternion space into zones and tracks
    the empirical distribution of next-bar outcomes for each zone.
    """

    def __init__(self, n_bins: int = 5):
        """
        Args:
            n_bins: Number of bins per dimension for state discretization.
                5 bins × 4 dims = 625 possible zones.
        """
        self.n_bins = n_bins
        # zone_key → {"bull": count, "bear": count, "neutral": count}
        self._zone_stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"bull": 0, "bear": 0, "neutral": 0}
        )
        self._total_predictions = 0
        self._correct_predictions = 0

    def _discretize(self, q_w: float, q_x: float, q_y: float, q_z: float) -> str:
        """Map continuous 4D state to a discrete zone key."""
        def bin_val(v: float, low: float = -3.0, high: float = 3.0) -> int:
            clamped = max(low, min(high, v))
            return int((clamped - low) / (high - low) * self.n_bins)

        return f"{bin_val(q_w)}_{bin_val(q_x, -1, 1)}_{bin_val(q_y)}_{bin_val(q_z, -1, 1)}"

    def get_prediction(self, q_w: float, q_x: float, q_y: float, q_z: float) -> dict:
        """
        Get empirical prediction for the next bar based on this zone's history.

        Returns:
            {"bull": P(bull), "bear": P(bear), "neutral": P(neutral),
             "n_observations": count, "accuracy": hit_rate}
        """
        zone = self._discretize(q_w, q_x, q_y, q_z)
        stats = self._zone_stats[zone]
        total = stats["bull"] + stats["bear"] + stats["neutral"]

        if total == 0:
            # No history for this zone — uniform prior
            return {
                "bull": 0.333, "bear": 0.333, "neutral": 0.334,
                "n_observations": 0,
                "accuracy": 0.0,
            }

        return {
            "bull": stats["bull"] / total,
            "bear": stats["bear"] / total,
            "neutral": stats["neutral"] / total,
            "n_observations": total,
            "accuracy": (
                self._correct_predictions / self._total_predictions
                if self._total_predictions > 0 else 0.0
            ),
        }

    def update(
        self,
        q_w: float, q_x: float, q_y: float, q_z: float,
        actual_label: str,
        predicted_label: str | None = None,
    ) -> None:
        """
        Record what actually happened after being in this state.

        Args:
            q_w, q_x, q_y, q_z: The state that PRECEDED this outcome.
            actual_label: "bull", "bear", or "neutral".
            predicted_label: What we predicted (for accuracy tracking).
        """
        zone = self._discretize(q_w, q_x, q_y, q_z)
        self._zone_stats[zone][actual_label] += 1

        if predicted_label is not None:
            self._total_predictions += 1
            if predicted_label == actual_label:
                self._correct_predictions += 1


class QuaternionSignalAdapter(SignalPort):
    """
    Research-only adapter for Oracle backtesting of the Quaternion signal.

    Signal rule: emit 1 (buy) when the 4D state indicates:
      - Q_x > 0         (bullish session)
      - Q_y > 0.5        (above-average volume)
      - Q_z > 0.3        (bearish rejection / accumulation wick)
      - Q_rotation > 0.2 (market state rotated, not stagnant)

    Also computes self-calibrating prediction columns (D5, D6, D7).
    """

    def __init__(self, include_predictions: bool = True):
        self._include_predictions = include_predictions
        self._scorecard = QuaternionScorecard()

    @property
    def name(self) -> str:
        return "quaternion_state"

    def generate(self, ohlc: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
        """Generate quaternion signals + self-calibrating predictions."""
        q = MarketQuaternion.compute(ohlc)

        # ── Base signal: accumulation with rotation ──
        signal = pd.Series(0, index=ohlc.index)

        # Need rotation_angle which requires at least 2 bars
        has_rotation = q["Q_rotation_angle"].notna()

        signal[
            has_rotation
            & (q["Q_x"] > 0)
            & (q["Q_y"] > 0.5)
            & (q["Q_z"] > 0.3)
            & (q["Q_rotation_angle"] > 0.2)
        ] = 1

        result = pd.DataFrame({"signal": signal}, index=ohlc.index)

        # ── Self-calibrating predictions (D5, D6, D7) ──
        if self._include_predictions:
            pred_bull = pd.Series(0.333, index=ohlc.index)
            pred_bear = pd.Series(0.333, index=ohlc.index)
            pred_accuracy = pd.Series(0.0, index=ohlc.index)

            # Compute next-bar labels for scorecard training
            next_return = ohlc["close"].pct_change().shift(-1)
            labels = pd.Series("neutral", index=ohlc.index)
            labels[next_return > 0.001] = "bull"
            labels[next_return < -0.001] = "bear"

            # Walk through bars, updating scorecard
            for i in range(len(ohlc)):
                if q["Q_w"].isna().iloc[i]:
                    continue

                qw = float(q["Q_w"].iloc[i])
                qx = float(q["Q_x"].iloc[i])
                qy = float(q["Q_y"].iloc[i])
                qz = float(q["Q_z"].iloc[i])

                # Get prediction BEFORE seeing the outcome
                pred = self._scorecard.get_prediction(qw, qx, qy, qz)
                pred_bull.iloc[i] = pred["bull"]
                pred_bear.iloc[i] = pred["bear"]
                pred_accuracy.iloc[i] = pred["accuracy"]

                # Determine what we would have predicted
                predicted = max(pred, key=lambda k: pred[k] if k in ("bull", "bear", "neutral") else 0)

                # Update scorecard with actual outcome (if available)
                if i > 0 and not pd.isna(labels.iloc[i - 1]):
                    prev_qw = float(q["Q_w"].iloc[i - 1])
                    prev_qx = float(q["Q_x"].iloc[i - 1])
                    prev_qy = float(q["Q_y"].iloc[i - 1])
                    prev_qz = float(q["Q_z"].iloc[i - 1])
                    if not np.isnan(prev_qw):
                        actual = labels.iloc[i - 1]
                        # Get what we predicted for bar i-1
                        prev_pred = self._scorecard.get_prediction(
                            prev_qw, prev_qx, prev_qy, prev_qz
                        )
                        prev_predicted = max(
                            prev_pred,
                            key=lambda k: prev_pred[k] if k in ("bull", "bear", "neutral") else 0
                        )
                        self._scorecard.update(
                            prev_qw, prev_qx, prev_qy, prev_qz,
                            actual_label=actual,
                            predicted_label=prev_predicted,
                        )

            result["Q_pred_bull"] = pred_bull
            result["Q_pred_bear"] = pred_bear
            result["Q_pred_accuracy"] = pred_accuracy

        return result

    def required_context(self) -> list[str]:
        return []  # Pure OHLCV — no external data needed
