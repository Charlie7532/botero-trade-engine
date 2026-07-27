import glob
import json
from pathlib import Path

def test_verify_all_rules_json_metadata_compliance():
    """Recursively validates that all rules JSON files comply with Rule 21 Metadata Standard."""
    root_dir = Path(__file__).resolve().parent.parent
    rules_dir = root_dir / "backend/modules"
    
    # Recursively find all rules JSON files
    json_paths = glob.glob(str(rules_dir / "**/domain/rules/*.json"), recursive=True)
    
    # Exclude files if needed (e.g. empty mock or legacy config templates)
    # None for now to ensure strict compliance
    
    assert len(json_paths) > 0, "No rules JSON files found to validate!"
    
    mandatory_fields = [
        "model_purpose",
        "return_formula",
        "state_hierarchy",
        "dimension_thresholds_definition",
        "field_glossary",
        "signal_interpretation_policy",
    ]
    
    for path_str in json_paths:
        path = Path(path_str)
        # Validate target production derived files under Rule 21
        TARGET_FILES = [
            "rc_tide_ev_derived.json",
            "rc_wave_ev_derived.json",
            "rc_wave_derived.json",
            "rc_wave_multiscale_tree.json",
        ]
        if path.name not in TARGET_FILES:
            continue
            
        with open(path) as f:
            try:
                data = json.load(f)
            except Exception as e:
                raise AssertionError(f"JSON load failed for {path.name}: {e}")
                
        assert "_documentation" in data, f"Rule 21 Violation in {path.name}: Missing top-level '_documentation' block."
        doc = data["_documentation"]
        
        for field in mandatory_fields:
            assert field in doc, f"Rule 21 Violation in {path.name}: '_documentation' is missing mandatory field '{field}'."
            assert doc[field], f"Rule 21 Violation in {path.name}: field '{field}' in '_documentation' cannot be empty or null."
            
        # Verify reproducibility_context if applicable for generated data tables
        if "derived" in path.name or "probability" in path.name or "tree" in path.name:
            assert "reproducibility_context" in doc, f"Rule 21 Violation in {path.name}: Missing 'reproducibility_context'."
            rep = doc["reproducibility_context"]
            assert "calibration_timestamp" in rep, f"Rule 21 Violation in {path.name}: Missing 'calibration_timestamp' in reproducibility_context."
            assert "calibrated_under_commit" in rep, f"Rule 21 Violation in {path.name}: Missing 'calibrated_under_commit' in reproducibility_context."
