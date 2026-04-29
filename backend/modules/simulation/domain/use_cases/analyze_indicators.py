"""
Indicator Analyzer — Per-Signal Quality Report
==================================================
Uses vaulted trade snapshots and outcomes to measure the precision,
recall, and predictive power of each signal module.

This closes the feedback loop: TradeSnapshot + Outcome → Signal Quality.
"""
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from backend.modules.simulation.domain.ports.historical_data_port import HistoricalDataPort

logger = logging.getLogger(__name__)


@dataclass
class SignalQuality:
    """Quality metrics for a single signal module."""
    name: str
    total_appearances: int = 0     # Times signal fired at entry
    correct_predictions: int = 0   # Signal fired AND trade was winner
    incorrect_predictions: int = 0  # Signal fired AND trade was loser
    precision: float = 0.0         # correct / (correct + incorrect)
    avg_contribution: float = 0.0  # Average weighted contribution when active
    avg_pnl_when_active: float = 0.0  # Average PnL when this signal was active
    avg_pnl_when_inactive: float = 0.0  # Average PnL when this signal was NOT active
    lift: float = 0.0             # active_pnl / inactive_pnl — does this signal add value?


@dataclass
class QualityReport:
    """Aggregate quality report across all signals."""
    ticker: Optional[str] = None
    category: Optional[str] = None
    total_snapshots: int = 0
    total_with_outcomes: int = 0
    signals: list[SignalQuality] = field(default_factory=list)
    best_signal: str = ""
    worst_signal: str = ""
    recommendation: str = ""


class IndicatorAnalyzer:
    """
    Analyzes per-signal precision using historical trade snapshots.

    Requires snapshots with filled outcomes (post TradeAutopsy).
    """

    def __init__(self, store: HistoricalDataPort):
        self.store = store

    def quality_report(
        self,
        ticker: Optional[str] = None,
        category: Optional[str] = None,
    ) -> QualityReport:
        """
        Generate quality report for all signals using vaulted snapshots.

        Only includes snapshots that have outcome data (post-trade).
        """
        snapshots = self.store.load_snapshots(ticker=ticker, category=category)

        # Filter to those with outcomes
        completed = [s for s in snapshots if s.get("outcome_was_winner") is not None]

        report = QualityReport(
            ticker=ticker,
            category=category,
            total_snapshots=len(snapshots),
            total_with_outcomes=len(completed),
        )

        if not completed:
            report.recommendation = "No completed trades with outcomes. Run more trades."
            return report

        # Aggregate per signal
        signal_stats = defaultdict(lambda: {
            "active_wins": 0, "active_losses": 0,
            "inactive_wins": 0, "inactive_losses": 0,
            "contributions": [], "active_pnls": [], "inactive_pnls": [],
        })

        # Collect all signal names across snapshots
        all_signal_names = set()
        for snap in completed:
            for sig in snap.get("signals", []):
                all_signal_names.add(sig["name"])

        for snap in completed:
            was_winner = snap.get("outcome_was_winner", False)
            pnl = snap.get("outcome_pnl_pct", 0.0) or 0.0
            active_signals = {
                sig["name"] for sig in snap.get("signals", [])
                if sig.get("value", 0) != 0
            }

            for name in all_signal_names:
                stats = signal_stats[name]
                if name in active_signals:
                    sig_data = next(
                        (s for s in snap.get("signals", []) if s["name"] == name),
                        {},
                    )
                    if was_winner:
                        stats["active_wins"] += 1
                    else:
                        stats["active_losses"] += 1
                    stats["contributions"].append(sig_data.get("contribution", 0))
                    stats["active_pnls"].append(pnl)
                else:
                    if was_winner:
                        stats["inactive_wins"] += 1
                    else:
                        stats["inactive_losses"] += 1
                    stats["inactive_pnls"].append(pnl)

        # Build quality entries
        qualities = []
        for name, stats in signal_stats.items():
            total = stats["active_wins"] + stats["active_losses"]
            precision = stats["active_wins"] / max(total, 1)

            avg_active_pnl = (
                sum(stats["active_pnls"]) / max(len(stats["active_pnls"]), 1)
            )
            avg_inactive_pnl = (
                sum(stats["inactive_pnls"]) / max(len(stats["inactive_pnls"]), 1)
            )
            lift = avg_active_pnl / max(abs(avg_inactive_pnl), 0.01)

            qualities.append(SignalQuality(
                name=name,
                total_appearances=total,
                correct_predictions=stats["active_wins"],
                incorrect_predictions=stats["active_losses"],
                precision=round(precision, 4),
                avg_contribution=round(
                    sum(stats["contributions"]) / max(len(stats["contributions"]), 1), 4
                ),
                avg_pnl_when_active=round(avg_active_pnl, 4),
                avg_pnl_when_inactive=round(avg_inactive_pnl, 4),
                lift=round(lift, 4),
            ))

        # Sort by precision
        qualities.sort(key=lambda q: q.precision, reverse=True)
        report.signals = qualities

        if qualities:
            report.best_signal = qualities[0].name
            report.worst_signal = qualities[-1].name

            # Recommendation
            degraded = [q for q in qualities if q.precision < 0.4 and q.total_appearances >= 5]
            if degraded:
                names = [q.name for q in degraded]
                report.recommendation = f"RETRAIN RECOMMENDED: signals {names} have precision < 40%"
            else:
                report.recommendation = "All signals performing within acceptable range"

        logger.info(
            f"Quality Report ({ticker or 'ALL'}/{category or 'ALL'}): "
            f"{len(completed)} trades analyzed, "
            f"best={report.best_signal} worst={report.worst_signal}"
        )
        return report
