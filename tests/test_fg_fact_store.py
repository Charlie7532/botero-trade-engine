"""
Unit tests for Pure Autonomous 3-Day Fast Velocity Fear & Greed Index Fact Store and Lookup Adapter
"""
import pytest
from pathlib import Path
import json

from backend.modules.entry_decision.domain.rules.fg_lookup import fg_lookup, FGStateGuidance

FACT_STORE_PATH = Path(__file__).parent.parent / "backend" / "modules" / "entry_decision" / "domain" / "rules" / "fg_fact_store.json"

def test_fact_store_rule21_schema():
    """Verify that the fact store JSON complies with standard Rule 21 specifications."""
    assert FACT_STORE_PATH.exists(), "Fact Store file must exist"
    
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

def test_lookup_adapter_extremes():
    """Verify that lookup returns correct guidance under extreme market sentiment states."""
    # Extreme Fear (5.0 is in DEEP_FEAR bin), Stable Speed
    guidance = fg_lookup.lookup_fg_guidance(
        fg_val=5.0, 
        fg_d3=0.0
    )
    assert guidance is not None
    assert isinstance(guidance, FGStateGuidance)
    assert guidance.state_key == "DEEP_FEAR__STABLE_3D"
    
    # Check scale details
    assert guidance.zz50.p_bull > 0.0
    assert guidance.zz50.p_bear > 0.0
    assert isinstance(guidance.divergence_regime, str)
    assert isinstance(guidance.operational_guidance, str)

def test_lookup_adapter_euphoria():
    """Verify that lookup returns correct guidance under euphoria/high greed states."""
    # Euphoria (95.0 is in EUPHORIA bin), Stable Speed
    guidance = fg_lookup.lookup_fg_guidance(
        fg_val=95.0, 
        fg_d3=0.0
    )
    assert guidance is not None
    assert guidance.state_key == "EUPHORIA__STABLE_3D"
    assert guidance.divergence_regime == "FULL_STRUCTURAL_BULL"
    assert guidance.operational_guidance == "STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION"
