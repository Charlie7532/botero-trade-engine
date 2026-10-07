"""
Population Stability Index (PSI) Drift Monitor — Pure Domain Service
=====================================================================
Monitors statistical drift between recent operational market windows (e.g. 60 sessions)
and canonical historical baseline distributions across METAR weather stations.

In credit and risk modeling (Basel II/III, institutional risk engineering):
  - PSI < 0.10: Stable / no significant distribution change.
  - 0.10 <= PSI <= 0.25: Moderate shift / monitoring flag.
  - PSI > 0.25: Significant distribution drift -> Emits NOTAM_DISTRIBUTION_DRIFT.

Follows Institutional Taxonomy: Universal Institutional Action Taxonomy Standard.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

from backend.modules.entry_decision.domain.services.notam_incident_service import OperationalNOTAM

PSI_DRIFT_THRESHOLD = 0.25
EPSILON = 1e-4


def calculate_psi(expected_probs: np.ndarray, actual_probs: np.ndarray, epsilon: float = EPSILON) -> float:
    """
    Compute Population Stability Index (PSI) between two probability vectors.

    Formula:
      PSI = sum((actual - expected) * ln(actual / expected))
    """
    # Normalize and clip probabilities to avoid zero division or log(0)
    exp = np.clip(expected_probs, epsilon, None)
    exp = exp / exp.sum()

    act = np.clip(actual_probs, epsilon, None)
    act = act / act.sum()

    psi_values = (act - exp) * np.log(act / exp)
    return float(np.sum(psi_values))


def bin_observations(values: np.ndarray, bin_edges: List[float]) -> np.ndarray:
    """Classify numerical values into 1D discrete bins using given edges."""
    # np.digitize returns 1-based bin index
    return np.digitize(values, bin_edges)


class PSIDriftMonitor:
    """Evaluates telemetry distribution drift and issues NOTAMs upon critical divergence."""

    def __init__(self, drift_threshold: float = PSI_DRIFT_THRESHOLD):
        self.drift_threshold = drift_threshold

    def evaluate_drift(
        self,
        station: str,
        recent_values: List[float],
        bin_edges: List[float],
        baseline_distribution: Optional[List[float]] = None,
        as_of_date: Optional[str] = None,
    ) -> Tuple[float, Optional[OperationalNOTAM]]:
        """
        Evaluate drift of recent_values against baseline_distribution.

        Args:
            station: Station name (e.g. 'VIX', 'SV5_TURBULENCE', 'CREDIT').
            recent_values: List of observations in the evaluation window (e.g. last 60 sessions).
            bin_edges: Value edges defining discrete bins.
            baseline_distribution: Optional baseline probability distribution. If None, assumed uniform.
            as_of_date: Optional reference date YYYY-MM-DD.

        Returns:
            Tuple of (psi_score, optional OperationalNOTAM).
        """
        if not recent_values or len(recent_values) < 10:
            return 0.0, None

        n_bins = len(bin_edges) + 1
        arr = np.array(recent_values, dtype=float)
        binned = bin_observations(arr, bin_edges)

        counts = np.bincount(binned, minlength=n_bins)[:n_bins]
        actual_probs = counts / max(1, len(arr))

        if baseline_distribution is not None and len(baseline_distribution) == n_bins:
            expected_probs = np.array(baseline_distribution, dtype=float)
        else:
            # Default to uniform prior if baseline not provided
            expected_probs = np.full(n_bins, 1.0 / n_bins)

        psi = calculate_psi(expected_probs, actual_probs)

        notam: Optional[OperationalNOTAM] = None
        if psi > self.drift_threshold:
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            date_str = as_of_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            st_upper = station.upper()

            notam = OperationalNOTAM(
                notam_id=f"NOTAM-DRIFT-{st_upper}-{date_str}",
                timestamp_utc=now_iso,
                incident_type="NOTAM_DISTRIBUTION_DRIFT",
                severity="WARNING",
                component=f"Station.{st_upper}",
                title=f"Statistical Distribution Drift on {st_upper} (PSI={psi:.4f} > {self.drift_threshold})",
                description=(
                    f"Market station {st_upper} exhibited significant statistical distribution shift "
                    f"over recent {len(recent_values)} sessions compared to historical baseline. "
                    f"Measured PSI: {psi:.4f} exceeds institutional threshold ({self.drift_threshold})."
                ),
                operational_action="MKT_RECALIBRATE_REGIME",
                is_active=True,
                details={
                    "station": st_upper,
                    "psi_score": round(psi, 4),
                    "threshold": self.drift_threshold,
                    "sample_size": len(recent_values),
                    "actual_distribution": [round(float(p), 4) for p in actual_probs],
                    "expected_distribution": [round(float(p), 4) for p in expected_probs],
                },
            )

        return psi, notam
