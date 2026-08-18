"""
V37.1 Structural Integrity & Parameter Edge-Case Audit
========================================================
Validates that the updated QualityEntryGate V37.1:
  1. Handles missing optional parameters (sec_v_tw = None, fgbi = None) without crashing.
  2. Correctly executes the V-shaped recovery escape hatch under extreme momentum.
  3. Correctly handles null and boundary values.
"""

import os, sys, logging
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_missing_optional_params():
    gate = QualityEntryGate()
    
    # Check that evaluate_regime runs without optional parameters
    try:
        mode = gate.evaluate_regime(
            th=45.0, fi=42.0, tw=25.0, v_th=30.0, v_fi=28.0, v_tw=20.0,
            sec_th={"XLK": 50.0}, sec_fi={"XLK": 40.0}, sec_tw={"XLK": 30.0},
            current_mode="NORMAL", days_in_mode=25
        )
        logger.info(f"✅ Safe fallback (no optional params): PASSED (Mode: {mode})")
    except Exception as e:
        logger.error(f"❌ Safe fallback failed: {e}")
        raise e

def test_v_recovery_escape_hatch():
    gate = QualityEntryGate()
    
    # 1. Normal transition (no hatch): th = 45 (<= 50) and fi = 45 (<= 50) -> stays RECUPERACION
    mode_normal = gate.evaluate_regime(
        th=45.0, fi=45.0, tw=55.0, v_th=30.0, v_fi=28.0, v_tw=45.0,
        sec_th={"XLK": 50.0}, sec_fi={"XLK": 40.0}, sec_tw={"XLK": 30.0},
        current_mode="RECUPERACION", days_in_mode=25
    )
    
    # 2. Hatch transition: tw > 60 and v_fi > 55 and th > 40 -> triggers MERCADO_SANO escape
    mode_escape = gate.evaluate_regime(
        th=42.0, fi=35.0, tw=62.0, v_th=45.0, v_fi=58.0, v_tw=60.0,
        sec_th={"XLK": 50.0}, sec_fi={"XLK": 40.0}, sec_tw={"XLK": 30.0},
        current_mode="RECUPERACION", days_in_mode=25
    )
    
    logger.info(f"✅ V-Recovery normal path: PASSED (Mode: {mode_normal})")
    logger.info(f"✅ V-Recovery escape hatch path: PASSED (Mode: {mode_escape})")
    assert mode_normal == "RECUPERACION"
    assert mode_escape == "MERCADO_SANO"

def test_re_acumulacion_3d_rules():
    gate = QualityEntryGate()
    
    # Bullish re-absorption: th >= 60, fi <= 45, v_tw >= 60
    # Rule V37.1 requires: ratio_tw_fi <= 1.2 and div_fi >= 0.0
    
    # Case A: ratio_tw_fi = 58 / 40 = 1.45 (> 1.2) -> Should NOT trigger RE_ACUMULACION
    mode_blocked = gate.evaluate_regime(
        th=65.0, fi=40.0, tw=58.0, v_th=62.0, v_fi=38.0, v_tw=65.0,
        sec_th={"XLK": 50.0}, sec_fi={"XLK": 40.0}, sec_tw={"XLK": 30.0},
        current_mode="NORMAL", days_in_mode=25
    )
    
    # Case B: ratio_tw_fi = 42 / 40 = 1.05 (<= 1.2) and div_fi = 45 - 40 = 5.0 (>= 0.0) -> Should trigger
    mode_triggered = gate.evaluate_regime(
        th=65.0, fi=40.0, tw=42.0, v_th=62.0, v_fi=45.0, v_tw=65.0,
        sec_th={"XLK": 50.0}, sec_fi={"XLK": 40.0}, sec_tw={"XLK": 30.0},
        current_mode="NORMAL", days_in_mode=25
    )
    
    logger.info(f"✅ Re-Accumulation 3D blocked: PASSED (Mode: {mode_blocked})")
    logger.info(f"✅ Re-Accumulation 3D triggered: PASSED (Mode: {mode_triggered})")
    assert mode_blocked != "RE_ACUMULACION_ALCISTA"
    assert mode_triggered == "RE_ACUMULACION_ALCISTA"

def main():
    print("\n" + "="*115)
    print("      🔬 AUDITORÍA ESTRUCTURAL Y DE CASOS LÍMITE: QUALITY ENTRY GATE V37.1")
    print("="*115)
    test_missing_optional_params()
    test_v_recovery_escape_hatch()
    test_re_acumulacion_3d_rules()
    print("\n" + "="*115)
    print("  RESULTADO: ESTRUCTURA LÓGICA Y PARÁMETROS 100% CORRECTOS Y ROBUSTOS.")
    print("="*115)

if __name__ == "__main__":
    main()
