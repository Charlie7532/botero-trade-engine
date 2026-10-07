"""
Unit tests for Population Stability Index (PSI) Drift Monitor (F3.8)
"""
import pytest
import numpy as np

from backend.modules.entry_decision.domain.services.psi_drift_monitor import (
    calculate_psi,
    PSIDriftMonitor,
    PSI_DRIFT_THRESHOLD,
)
from backend.modules.entry_decision.domain.services.notam_incident_service import OperationalNOTAM


def test_calculate_psi_identical():
    """Identical distributions should have PSI of zero."""
    probs = np.array([0.2, 0.2, 0.2, 0.2, 0.2])
    psi = calculate_psi(probs, probs)
    assert pytest.approx(psi, abs=1e-5) == 0.0


def test_calculate_psi_moderate_shift():
    """Moderate distribution shift should remain below critical drift threshold."""
    exp = np.array([0.2, 0.2, 0.2, 0.2, 0.2])
    act = np.array([0.25, 0.22, 0.18, 0.18, 0.17])
    psi = calculate_psi(exp, act)
    assert 0.0 < psi < PSI_DRIFT_THRESHOLD


def test_psi_drift_monitor_benign_no_notam():
    """Normal operational window consistent with baseline emits no NOTAM."""
    monitor = PSIDriftMonitor()
    np.random.seed(42)
    # Generate 60 samples from standard normal
    recent = list(np.random.normal(0, 1, 60))
    bin_edges = [-1.5, -0.5, 0.5, 1.5]

    # Baseline: empirical quantiles of standard normal across 5 bins
    # Phi(-1.5) = 0.0668, Phi(-0.5)=0.3085, Phi(0.5)=0.6915, Phi(1.5)=0.9332
    baseline = [0.067, 0.242, 0.383, 0.242, 0.067]

    psi, notam = monitor.evaluate_drift("VIX", recent, bin_edges, baseline)
    assert psi <= PSI_DRIFT_THRESHOLD
    assert notam is None


def test_psi_drift_monitor_emits_notam_on_displaced_series():
    """Severely shifted synthetic series (e.g. regime shock) triggers NOTAM_DISTRIBUTION_DRIFT."""
    monitor = PSIDriftMonitor()
    # Generate synthetic severely shifted series (+3 sigma mean shift)
    displaced_series = list(np.random.normal(3.5, 0.5, 60))
    bin_edges = [-1.5, -0.5, 0.5, 1.5]
    baseline = [0.067, 0.242, 0.383, 0.242, 0.067]

    psi, notam = monitor.evaluate_drift("SV5_TURBULENCE", displaced_series, bin_edges, baseline)

    assert psi > PSI_DRIFT_THRESHOLD
    assert notam is not None
    assert isinstance(notam, OperationalNOTAM)
    assert notam.incident_type == "NOTAM_DISTRIBUTION_DRIFT"
    assert notam.severity == "WARNING"
    assert notam.component == "Station.SV5_TURBULENCE"
    assert notam.operational_action == "MKT_RECALIBRATE_REGIME"
    assert notam.is_active is True
    assert "PSI=" in notam.title
