"""
Unit tests for compute_geometric_features.
Validates:
- Correct computation with valid inputs
- None handling when slopes are None/NaN
- None handling when accels are None/NaN
- None handling when sigmas are None/NaN
- Prevention of fabricated 0.0 values
"""
import numpy as np
import pytest
from backend.modules.shared.domain.rules.geometric_features import compute_geometric_features


def test_compute_geometric_features_valid():
    norm, vel_align, exit_align, accel_align, phase_angle = compute_geometric_features(
        sigma_tide=1.0,
        sigma_current=0.5,
        sigma_wave=-0.5,
        tide_slope=-0.01,
        current_slope=-0.02,
        wave_slope=-0.03,
        tide_accel=0.001,
        current_accel=0.002,
        wave_accel=0.003,
    )
    assert norm == pytest.approx(1.2247, abs=0.001)
    assert vel_align is not None and vel_align > 0.9  # falling slopes align with ideal entry
    assert exit_align is not None and exit_align < -0.9
    assert accel_align is not None
    assert phase_angle is not None


def test_compute_geometric_features_none_accel():
    """When accels are None, accel_align is None while norm and velocity_align remain valid."""
    norm, vel_align, exit_align, accel_align, phase_angle = compute_geometric_features(
        sigma_tide=1.0,
        sigma_current=0.5,
        sigma_wave=-0.5,
        tide_slope=-0.01,
        current_slope=-0.02,
        wave_slope=-0.03,
        tide_accel=None,
        current_accel=None,
        wave_accel=None,
    )
    assert norm is not None
    assert vel_align is not None
    assert exit_align is not None
    assert phase_angle is not None
    assert accel_align is None


def test_compute_geometric_features_none_slope():
    """When slopes are None/NaN, slope-dependent features return None."""
    norm, vel_align, exit_align, accel_align, phase_angle = compute_geometric_features(
        sigma_tide=1.0,
        sigma_current=0.5,
        sigma_wave=-0.5,
        tide_slope=None,
        current_slope=np.nan,
        wave_slope=0.01,
        tide_accel=0.001,
        current_accel=0.002,
        wave_accel=0.003,
    )
    assert norm is not None
    assert vel_align is None
    assert exit_align is None
    assert accel_align is None
    assert phase_angle is None


def test_compute_geometric_features_none_sigma():
    """When sigmas are None/NaN, state_norm returns None."""
    norm, vel_align, exit_align, accel_align, phase_angle = compute_geometric_features(
        sigma_tide=None,
        sigma_current=0.5,
        sigma_wave=-0.5,
        tide_slope=0.01,
        current_slope=0.02,
        wave_slope=0.03,
        tide_accel=0.001,
        current_accel=0.002,
        wave_accel=0.003,
    )
    assert norm is None
    assert vel_align is not None
    assert exit_align is not None
    assert accel_align is not None
    assert phase_angle is not None
