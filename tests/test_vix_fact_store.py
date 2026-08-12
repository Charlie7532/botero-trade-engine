"""
Unit tests for Pure Autonomous 3-Day Fast Velocity CBOE Volatility Index (VIX) Fact Store and Lookup Adapter
"""
import pytest
from pathlib import Path
import json

from backend.modules.entry_decision.domain.rules.vix_lookup import vix_lookup, VIXStateGuidance

FACT_STORE_PATH = Path(__file__).parent.parent / "backend" / "modules" / "entry_decision" / "domain" / "rules" / "vix_fact_store.json"

def test_fact_store_rule21_schema():
    """Verify that the VIX fact store JSON complies with standard Rule 21 specifications."""
    assert FACT_STORE_PATH.exists(), "VIX Fact Store file must exist"
    
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

def test_lookup_adapter_deep_calm():
    """Verify that lookup returns correct guidance under deep calm VIX states."""
    guidance = vix_lookup.lookup_vix_guidance(
        vix_val=10.0, 
        vix_d3=0.0
    )
    assert guidance is not None
    assert isinstance(guidance, VIXStateGuidance)
    assert guidance.bin == "DEEP_COMPLACENCY"
    
    # Check scale details
    assert guidance.zz50.p_bull > 0.0
    assert guidance.zz50.p_bear > 0.0
    assert isinstance(guidance.divergence_regime, str)
    assert isinstance(guidance.operational_guidance, str)

def test_lookup_adapter_crisis_spike():
    """Verify that lookup returns correct guidance under crisis spike VIX states."""
    guidance = vix_lookup.lookup_vix_guidance(
        vix_val=45.0, 
        vix_d3=5.0
    )
    assert guidance is not None
    assert guidance.bin == "CRISIS_SPIKE"
    assert guidance.vix_bin == "CRISIS_SPIKE"
    assert guidance.velocity_vector == "EXTREME_SPIKE_3D"
