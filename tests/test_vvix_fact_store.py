"""
Unit tests for Pure Autonomous 3-Day Fast Velocity CBOE Volatility of Volatility Index (VVIX) Fact Store and Lookup Adapter
"""
import pytest
from pathlib import Path
import json

from backend.modules.entry_decision.domain.rules.vvix_lookup import vvix_lookup, VVIXStateGuidance

FACT_STORE_PATH = Path(__file__).parent.parent / "backend" / "modules" / "entry_decision" / "domain" / "rules" / "vvix_fact_store.json"


def test_vvix_fact_store_rule21_schema():
    """Verify that the VVIX fact store JSON complies with standard Rule 21 specifications."""
    assert FACT_STORE_PATH.exists(), "VVIX Fact Store file must exist"

    with open(FACT_STORE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "_documentation" in data, "Must contain top-level '_documentation'"
    doc = data["_documentation"]

    mandatory_fields = [
        "model_purpose",
        "return_formula",
        "state_hierarchy",
        "dimension_thresholds_definition",
        "field_glossary",
        "signal_interpretation_policy"
    ]
    for field in mandatory_fields:
        assert field in doc, f"Metadata must contain '{field}' block"

    assert "states" in data
    states = data["states"]
    assert len(states) >= 100, f"Must contain empirical states, found {len(states)}"


def test_vvix_lookup_adapter_deep_stability():
    """Verify that lookup returns correct guidance under deep stability VVIX states."""
    guidance = vvix_lookup.lookup_vvix_guidance(
        vvix_val=60.0,
        vvix_d3=0.0
    )
    assert guidance is not None
    assert isinstance(guidance, VVIXStateGuidance)
    assert guidance.bin in ["EXTREME_COMPLACENCY", "LOW_VVIX"]
    assert guidance.velocity_vector in ["STABLE_CONTINUATION_3D", "FAST_CRUSH_3D"]

    # Check scale details and vector conversion
    vec = guidance.to_vector()
    assert len(vec["p_bull"]) == 3
    assert len(vec["ev_net"]) == 3
    assert 0.0 <= vec["primary_p_bull"] <= 1.0
    assert isinstance(guidance.divergence_regime, str)
    assert isinstance(guidance.operational_guidance, str)


def test_vvix_lookup_adapter_vol_of_vol_crisis():
    """Verify that lookup returns correct guidance under volatility of volatility crisis states."""
    guidance = vvix_lookup.lookup_vvix_guidance(
        vvix_val=135.0,
        vvix_d3=15.0
    )
    assert guidance is not None
    assert guidance.vvix_bin in ["EXTREME_VVIX", "HIGH_VVIX"]
    assert guidance.velocity_vector == "FAST_SPIKE_3D"
