"""
Experiment Registry — Scientific Experiment Log + DSR
========================================================
Records every quaternion experiment with its exact configuration,
metrics, and verdict. Persists to JSON for full auditability.

Includes Deflated Sharpe Ratio (DSR) to correct for multiple
hypothesis testing (López de Prado, Advances in Financial ML).
"""
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Results directory
RESULTS_DIR = Path(__file__).parent / "results"


@dataclass
class ExperimentRecord:
    """Immutable record of a single experiment run."""
    experiment_id: str
    timestamp: str
    description: str

    # Configuration
    dimensions_used: list[str]
    dimensions_excluded: list[str]
    ticker: str
    timeframe: str
    n_samples: int

    # Metrics
    accuracy: float = 0.0          # Next-bar prediction accuracy
    sharpe: float = 0.0            # Annualized Sharpe ratio
    profit_factor: float = 0.0     # Gross profit / gross loss
    win_rate: float = 0.0          # % profitable predictions
    max_drawdown: float = 0.0      # Worst cumulative drawdown
    n_trades: int = 0              # Number of signals generated

    # Statistical correction
    n_trials: int = 1              # Total experiments run (for DSR)
    dsr_pvalue: float = 1.0        # Deflated Sharpe p-value

    # Verdict
    verdict: str = "PENDING"       # PROMOTED | OBSERVATION | REJECTED


def deflated_sharpe_ratio(
    observed_sharpe: float,
    n_trials: int,
    n_observations: int,
    sharpe_std: float = 1.0,
) -> float:
    """
    Compute the Deflated Sharpe Ratio p-value.

    Answers: "Given that I tested n_trials configurations, what is
    the probability that this Sharpe is due to luck?"

    Based on López de Prado (2018), Chapter 8.

    Args:
        observed_sharpe: The Sharpe ratio to test.
        n_trials: Number of independent experiments run.
        sharpe_std: Standard deviation of Sharpe ratios across trials.
        n_observations: Number of return observations.

    Returns:
        p-value. < 0.05 means the Sharpe is statistically real.
    """
    from scipy import stats

    if n_trials <= 1 or n_observations < 10:
        return 1.0  # Can't deflate with single trial

    # Expected maximum Sharpe under null (all strategies are noise)
    # E[max(Z_1, ..., Z_n)] ≈ (1 - γ) × Φ^{-1}(1 - 1/N) + γ × Φ^{-1}(1 - 1/(N×e))
    # Simplified approximation:
    euler_mascheroni = 0.5772156649
    expected_max = sharpe_std * (
        (1 - euler_mascheroni) * stats.norm.ppf(1 - 1 / n_trials)
        + euler_mascheroni * stats.norm.ppf(1 - 1 / (n_trials * np.e))
    )

    # Test: is our observed Sharpe significantly above the expected max?
    se = sharpe_std / np.sqrt(n_observations)
    if se < 1e-8:
        return 1.0

    z_score = (observed_sharpe - expected_max) / se
    p_value = 1 - stats.norm.cdf(z_score)

    return float(p_value)


def determine_verdict(sharpe: float, dsr_pvalue: float) -> str:
    """Apply Go/No-Go criteria."""
    if sharpe >= 0.5 and dsr_pvalue < 0.05:
        return "PROMOTED"
    elif sharpe >= 0.3:
        return "OBSERVATION"
    else:
        return "REJECTED"


class ExperimentRegistry:
    """Manages experiment records with persistence."""

    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir or RESULTS_DIR
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self._records: list[ExperimentRecord] = []
        self._load_existing()

    def _load_existing(self) -> None:
        """Load previous experiment records from disk."""
        registry_file = self.results_dir / "registry.json"
        if registry_file.exists():
            try:
                with open(registry_file) as f:
                    data = json.load(f)
                for entry in data:
                    self._records.append(ExperimentRecord(**entry))
                logger.info(f"Loaded {len(self._records)} previous experiments")
            except Exception as e:
                logger.warning(f"Failed to load registry: {e}")

    def _save(self) -> None:
        """Persist all records to disk."""
        registry_file = self.results_dir / "registry.json"
        with open(registry_file, "w") as f:
            json.dump([asdict(r) for r in self._records], f, indent=2)

    @property
    def n_trials(self) -> int:
        """Total number of experiments run (for DSR correction)."""
        return len(self._records)

    def record(
        self,
        description: str,
        dimensions_used: list[str],
        dimensions_excluded: list[str],
        ticker: str,
        timeframe: str,
        n_samples: int,
        accuracy: float,
        sharpe: float,
        profit_factor: float,
        win_rate: float,
        max_drawdown: float,
        n_trades: int,
        returns_std: float = 1.0,
    ) -> ExperimentRecord:
        """Record a new experiment with automatic DSR calculation."""
        n_trials = self.n_trials + 1

        dsr = deflated_sharpe_ratio(
            observed_sharpe=sharpe,
            n_trials=n_trials,
            n_observations=n_samples,
            sharpe_std=returns_std,
        )
        verdict = determine_verdict(sharpe, dsr)

        record = ExperimentRecord(
            experiment_id=f"EXP-{n_trials:04d}",
            timestamp=datetime.now(UTC).isoformat(),
            description=description,
            dimensions_used=dimensions_used,
            dimensions_excluded=dimensions_excluded,
            ticker=ticker,
            timeframe=timeframe,
            n_samples=n_samples,
            accuracy=round(accuracy, 4),
            sharpe=round(sharpe, 4),
            profit_factor=round(profit_factor, 4),
            win_rate=round(win_rate, 4),
            max_drawdown=round(max_drawdown, 4),
            n_trades=n_trades,
            n_trials=n_trials,
            dsr_pvalue=round(dsr, 6),
            verdict=verdict,
        )

        self._records.append(record)
        self._save()

        emoji = {"PROMOTED": "🟢", "OBSERVATION": "🟡", "REJECTED": "🔴"}
        logger.info(
            f"{emoji.get(verdict, '⚪')} {record.experiment_id}: "
            f"{description} → Sharpe={sharpe:.2f}, DSR p={dsr:.4f}, "
            f"Verdict={verdict}"
        )
        return record

    def summary_table(self) -> str:
        """Return a formatted summary of all experiments."""
        if not self._records:
            return "No experiments recorded."

        lines = [
            f"{'ID':<10} {'Description':<40} {'Sharpe':>7} {'Acc':>6} "
            f"{'DSR-p':>7} {'Verdict':<12}",
            "-" * 90,
        ]
        for r in sorted(self._records, key=lambda x: x.sharpe, reverse=True):
            lines.append(
                f"{r.experiment_id:<10} {r.description[:40]:<40} "
                f"{r.sharpe:>7.2f} {r.accuracy:>5.1%} "
                f"{r.dsr_pvalue:>7.4f} {r.verdict:<12}"
            )
        return "\n".join(lines)
