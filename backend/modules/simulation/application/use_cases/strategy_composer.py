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
    trim: bool = False                # Final trim decision (partial exit)
    exit: bool = False                # Final exit decision (full exit)
    score: float = 0.0                # Weighted composite score (0-1 for entry, 0 to -1 for trim/exit)
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
        trim_score = 0.0
        contributions = {}
        active_count = 0
        trim_active_count = 0

        for sig in signals:
            value = outputs.get(sig.name, 0)
            conf = confidences.get(sig.name, 1.0)

            # Only contribute if signal fires AND confidence meets threshold
            if value != 0 and conf >= sig.threshold:
                contribution = (sig.weight / total_weight) * value * conf
                if value > 0:
                    score += contribution
                    active_count += 1
                else:
                    trim_score += contribution
                    trim_active_count += 1
                contributions[sig.name] = round(contribution, 4)
            else:
                contributions[sig.name] = 0.0

        entry = score >= 0.5 and active_count >= min_required
        trim = trim_score <= -0.5 and trim_active_count >= min_required
        exit_flag = trim_score <= -0.8 and trim_active_count >= min_required
        
        final_score = score if abs(score) >= abs(trim_score) else trim_score

        return CompositeDecision(
            entry=entry,
            trim=trim,
            exit=exit_flag,
            score=round(final_score, 4),
            method="weighted_vote",
            signals_active=active_count + trim_active_count,
            signals_total=len(signals),
            contributions=contributions,
            reason=(
                f"Score={score:.2f}, TrimScore={trim_score:.2f}, "
                f"Active={active_count}(in)/{trim_active_count}(out) "
                f"(min={min_required})"
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
        entry = bullish > majority_threshold and bullish >= min_required
        trim = bearish > majority_threshold and bearish >= min_required
        
        final_score = bullish / max(total, 1) if bullish >= bearish else -bearish / max(total, 1)

        return CompositeDecision(
            entry=entry,
            trim=trim,
            exit=trim and bearish >= total * 0.75,
            score=round(final_score, 4),
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
        all_bearish = True

        for sig in signals:
            value = outputs.get(sig.name, 0)
            conf = confidences.get(sig.name, 1.0)
            if value > 0 and conf >= sig.threshold:
                contributions[sig.name] = 1
                all_bearish = False
            elif value < 0 and conf >= sig.threshold:
                contributions[sig.name] = -1
                all_bullish = False
            else:
                all_bullish = False
                all_bearish = False
                contributions[sig.name] = 0

        return CompositeDecision(
            entry=all_bullish and len(signals) > 0,
            trim=all_bearish and len(signals) > 0,
            exit=all_bearish and len(signals) > 0,
            score=1.0 if all_bullish else (-1.0 if all_bearish else 0.0),
            method="unanimous",
            signals_active=sum(1 for v in contributions.values() if v != 0),
            signals_total=len(signals),
            contributions=contributions,
            reason="All bullish" if all_bullish else ("All bearish" if all_bearish else "Mixed/No signal"),
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
        all_confidences = {}
        for signal in signals:
            if any(s.name == signal.name and s.enabled for s in profile.signals):
                signal_df = signal.generate(ohlc, context)
                all_outputs[signal.name] = signal_df["signal"]
                if "confidence" in signal_df.columns:
                    all_confidences[signal.name] = signal_df["confidence"]

        # Compose bar by bar
        composite_signals = []
        composite_scores = []

        for i in range(len(ohlc)):
            bar_outputs = {name: int(series.iloc[i]) for name, series in all_outputs.items()}
            bar_conf = {name: float(series.iloc[i]) for name, series in all_confidences.items()}
            
            decision = self.compose(profile, bar_outputs, bar_conf)
            
            if decision.exit or decision.trim:
                composite_signals.append(-1)
            elif decision.entry:
                composite_signals.append(1)
            else:
                composite_signals.append(0)
                
            composite_scores.append(decision.score)

        return pd.DataFrame({
            "composite_signal": composite_signals,
            "composite_score": composite_scores,
        }, index=ohlc.index)
