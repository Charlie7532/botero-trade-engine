"""
Strategy Composer — Weighted Signal Combination
===================================================
Combines multiple signal outputs using StrategyProfile weights
to produce a composite entry decision.

Composition methods:
- weighted_vote: weighted sum of signals ≥ threshold
- majority: >50% of enabled signals agree
- unanimous: all enabled signals agree
"""
import logging
from dataclasses import dataclass

import pandas as pd

from backend.modules.simulation.domain.entities.strategy_profile import StrategyProfile
from backend.modules.simulation.domain.ports.signal_port import SignalPort

logger = logging.getLogger(__name__)


@dataclass
class CompositeDecision:
    """Result of composing multiple signals."""
    entry: bool = False               # Final entry decision
    score: float = 0.0                # Weighted composite score (0-1)
    method: str = "weighted_vote"     # Composition method used
    signals_active: int = 0           # How many signals fired
    signals_total: int = 0            # Total enabled signals
    contributions: dict = None        # {signal_name: contribution_value}
    reason: str = ""                  # Human-readable explanation

    def __post_init__(self):
        if self.contributions is None:
            self.contributions = {}


class StrategyComposer:
    """
    Combines signal outputs using StrategyProfile weights.

    The composer is stateless — all configuration comes from the
    StrategyProfile passed at composition time.
    """

    def compose(
        self,
        profile: StrategyProfile,
        signal_outputs: dict[str, int],  # {signal_name: signal_value (1/0/-1)}
        confidences: dict[str, float] | None = None,
    ) -> CompositeDecision:
        """
        Combine signal outputs into a single entry decision.

        Args:
            profile: Strategy recipe with signal weights and thresholds.
            signal_outputs: {name: value} from each SignalPort.generate().
            confidences: Optional {name: confidence} from signals.

        Returns:
            CompositeDecision with entry flag, score, and breakdown.
        """
        confidences = confidences or {}
        enabled = profile.enabled_signals

        if not enabled:
            return CompositeDecision(reason="No enabled signals in profile")

        method = profile.composite_method
        min_required = profile.min_signals_required

        if method == "weighted_vote":
            return self._weighted_vote(enabled, signal_outputs, confidences, min_required)
        elif method == "majority":
            return self._majority(enabled, signal_outputs, confidences, min_required)
        elif method == "unanimous":
            return self._unanimous(enabled, signal_outputs, confidences)
        else:
            logger.warning(f"Unknown composition method: {method}, falling back to weighted_vote")
            return self._weighted_vote(enabled, signal_outputs, confidences, min_required)

    def _weighted_vote(self, signals, outputs, confidences, min_required) -> CompositeDecision:
        """Weighted sum of signals. Entry when score ≥ threshold."""
        total_weight = sum(s.weight for s in signals)
        if total_weight == 0:
            return CompositeDecision(reason="All signal weights are zero")

        score = 0.0
        contributions = {}
        active_count = 0

        for sig in signals:
            value = outputs.get(sig.name, 0)
            conf = confidences.get(sig.name, 1.0)

            # Only contribute if signal fires AND confidence meets threshold
            if value != 0 and conf >= sig.threshold:
                contribution = (sig.weight / total_weight) * value * conf
                score += contribution
                contributions[sig.name] = round(contribution, 4)
                active_count += 1
            else:
                contributions[sig.name] = 0.0

        entry = score >= 0.5 and active_count >= min_required

        return CompositeDecision(
            entry=entry,
            score=round(score, 4),
            method="weighted_vote",
            signals_active=active_count,
            signals_total=len(signals),
            contributions=contributions,
            reason=(
                f"Score={score:.2f} ({'≥' if score >= 0.5 else '<'}0.5), "
                f"Active={active_count}/{len(signals)} "
                f"({'≥' if active_count >= min_required else '<'}min={min_required})"
            ),
        )

    def _majority(self, signals, outputs, confidences, min_required) -> CompositeDecision:
        """Entry when >50% of enabled signals agree on direction."""
        contributions = {}
        bullish = 0
        bearish = 0

        for sig in signals:
            value = outputs.get(sig.name, 0)
            conf = confidences.get(sig.name, 1.0)
            if value > 0 and conf >= sig.threshold:
                bullish += 1
                contributions[sig.name] = 1
            elif value < 0 and conf >= sig.threshold:
                bearish += 1
                contributions[sig.name] = -1
            else:
                contributions[sig.name] = 0

        total = len(signals)
        majority_threshold = total / 2
        active = bullish + bearish
        entry = bullish > majority_threshold and active >= min_required

        return CompositeDecision(
            entry=entry,
            score=round(bullish / max(total, 1), 4),
            method="majority",
            signals_active=active,
            signals_total=total,
            contributions=contributions,
            reason=f"Bullish={bullish} Bearish={bearish} of {total}",
        )

    def _unanimous(self, signals, outputs, confidences) -> CompositeDecision:
        """Entry only when ALL enabled signals agree."""
        contributions = {}
        all_bullish = True

        for sig in signals:
            value = outputs.get(sig.name, 0)
            conf = confidences.get(sig.name, 1.0)
            if value > 0 and conf >= sig.threshold:
                contributions[sig.name] = 1
            else:
                all_bullish = False
                contributions[sig.name] = 0

        return CompositeDecision(
            entry=all_bullish and len(signals) > 0,
            score=1.0 if all_bullish else 0.0,
            method="unanimous",
            signals_active=sum(1 for v in contributions.values() if v > 0),
            signals_total=len(signals),
            contributions=contributions,
            reason="All signals agree" if all_bullish else "Not all signals agree",
        )

    def compose_series(
        self,
        profile: StrategyProfile,
        signals: list[SignalPort],
        ohlc: pd.DataFrame,
        context: dict | None = None,
    ) -> pd.DataFrame:
        """
        Generate composite signal series for backtesting.

        Returns DataFrame with 'composite_signal' (1/0/-1) and 'composite_score'.
        """
        # Generate all signals
        all_outputs = {}
        for signal in signals:
            if any(s.name == signal.name and s.enabled for s in profile.signals):
                signal_df = signal.generate(ohlc, context)
                all_outputs[signal.name] = signal_df["signal"]

        # Compose bar by bar
        composite_signals = []
        composite_scores = []

        for i in range(len(ohlc)):
            bar_outputs = {name: int(series.iloc[i]) for name, series in all_outputs.items()}
            decision = self.compose(profile, bar_outputs)
            composite_signals.append(1 if decision.entry else 0)
            composite_scores.append(decision.score)

        return pd.DataFrame({
            "composite_signal": composite_signals,
            "composite_score": composite_scores,
        }, index=ohlc.index)
