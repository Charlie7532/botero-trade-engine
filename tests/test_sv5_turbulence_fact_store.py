"""
Unit tests for Pure Autonomous 3-Day Fast Velocity SV5_TURBULENCE Fact Store and Lookup Adapter
"""
import pytest
from pathlib import Path
import json

from backend.modules.entry_decision.domain.rules.sv5_turbulence_lookup import sv5_turbulence_lookup, SV5TurbulenceStateGuidance

FACT_STORE_PATH = Path(__file__).parent.parent / "backend" / "modules" / "entry_decision" / "domain" / "rules" / "sv5_turbulence_fact_store.json"


def test_sv5_turbulence_fact_store_rule21_schema():
    """Verify that the SV5_TURBULENCE fact store JSON complies with standard Rule 21 specifications."""
    assert FACT_STORE_PATH.exists(), "SV5_TURBULENCE Fact Store file must exist"

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
    assert len(states) == 49, f"Must contain all 49 cell permutations (7x7), found {len(states)}"


def test_sv5_turbulence_lookup_adapter_deep_serenity():
    """Verify that lookup returns correct guidance under deep serenity SV5_TURBULENCE states."""
    guidance = sv5_turbulence_lookup.lookup_sv5_turbulence_guidance(
        turbulence_val=2.0,
        turbulence_d3=0.0
    )
    assert guidance is not None
    assert isinstance(guidance, SV5TurbulenceStateGuidance)
    assert guidance.state_key == "DEEP_SERENITY__STABLE_3D"
    assert guidance.turbulence_bin == "DEEP_SERENITY"
    assert guidance.velocity_vector == "STABLE_3D"

    # Check scale details and vector conversion
    vec = guidance.to_vector()
    assert len(vec["p_bull"]) == 3
    assert len(vec["ev_net"]) == 3
    assert 0.0 <= vec["primary_p_bull"] <= 1.0
    assert isinstance(guidance.divergence_regime, str)
    assert isinstance(guidance.operational_guidance, str)


def test_sv5_turbulence_lookup_adapter_crisis_veto():
    """Verify that lookup returns correct guidance under crisis volume turbulence states."""
    guidance = sv5_turbulence_lookup.lookup_sv5_turbulence_guidance(
        turbulence_val=20.0,
        turbulence_d3=5.0
    )
    assert guidance is not None
    assert guidance.state_key == "CRISIS_TURBULENCE_VETO__EXTREME_TURBULENCE_SPIKE_3D"
    assert guidance.turbulence_bin == "CRISIS_TURBULENCE_VETO"
    assert guidance.velocity_vector == "EXTREME_TURBULENCE_SPIKE_3D"
