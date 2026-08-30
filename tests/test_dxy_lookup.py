"""
Unit tests for DXY Lookup Adapter — 11th METAR Station
"""
import pytest
from backend.modules.entry_decision.domain.rules.dxy_lookup import (
    dxy_lookup,
    DXYStateGuidance,
    ScaleGuidance,
)


def test_dxy_lookup_init():
    """Verify DXY Lookup Adapter loads the V3 fact store correctly."""
    assert len(dxy_lookup.states) > 100
    assert len(dxy_lookup.edges_d1) == 5
    assert len(dxy_lookup.labels_d1) == 6
    assert len(dxy_lookup.labels_d2) == 5
    assert len(dxy_lookup.labels_d3) == 5


def test_dxy_lookup_neutral_state():
    """Test lookup for standard neutral DXY conditions."""
    guidance = dxy_lookup.lookup_dxy_guidance(val=95.0, d3_speed=0.0, vol_norm=1.0)
    assert isinstance(guidance, DXYStateGuidance)
    assert "2__" in guidance.state_key or "3__" in guidance.state_key
    assert isinstance(guidance.zz25, ScaleGuidance)
    assert isinstance(guidance.zz50, ScaleGuidance)
    assert isinstance(guidance.zz75, ScaleGuidance)
    assert guidance.zz25.e_days == 1.0  # Standard layer: continuous 1-day bar return
    assert guidance.zz50.e_days == 3.0
    assert guidance.zz75.e_days == 5.0


def test_dxy_lookup_kinematic_layer():
    """Test that kinematic layer (zigzag physical legs + structural_momentum) is populated."""
    guidance = dxy_lookup.lookup_dxy_guidance(val=95.0, d3_speed=0.0, vol_norm=1.0)
    assert guidance is not None
    assert guidance.zigzag_kinematic is not None
    assert "zz25" in guidance.zigzag_kinematic or "zz50" in guidance.zigzag_kinematic


def test_dxy_lookup_vector_export():
    """Test to_vector() dictionary export format."""
    guidance = dxy_lookup.lookup_dxy_guidance(val=80.0, d3_speed=-1.0, vol_norm=0.5)
    assert guidance is not None
    vec = guidance.to_vector()
    assert "state_key" in vec
    assert "p_bull" in vec
    assert "ev_net" in vec
    assert "primary_capital_velocity" in vec
    assert "zigzag_kinematic" in vec
