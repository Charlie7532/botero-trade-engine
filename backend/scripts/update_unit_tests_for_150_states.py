"""
Authoritative 150-State Unit Test Assertion Fixer
=================================================
Updates test assertion lists in all unit test files to strictly match the 150-state Gaussian taxonomy:
D1 Labels per station:
- VIX: DEEP_COMPLACENCY, LOW_VOL, MODERATE_VOL, HIGH_VOL, ELEVATED_PANIC, CRISIS_SPIKE
- VVIX: VVIX_CALM, LOW_VVIX, MODERATE_VVIX, HIGH_VVIX, EXTREME_VVIX, VOL_OF_VOL_CRISIS
- PCR: CALL_EUPHORIA, BULLISH_BIAS, NEUTRAL_PCR, ELEVATED_PUTS, PANIC_PUTS, EXTREME_HEDGING
- FG: EXTREME_FEAR, FEAR, NEUTRAL_FEAR, NEUTRAL_GREED, GREED, EXTREME_GREED
- SV5_TURBULENCE: CALM_PARTICIPATION, LOW_TURBULENCE, MODERATE_TURBULENCE, ELEVATED_PARTICIPATION, HIGH_TURBULENCE, TURBULENCE_CRISIS
- SKEW: TAIL_COMPLACENCY, NORMAL_TAIL, ELEVATED_TAIL, HIGH_SKEW, PARANOIA_SKEW, BLACK_SWAN_PARANOIA
- CREDIT: DEEP_CREDIT_EASE, CREDIT_EASE, STABLE_CREDIT, ELEVATED_CREDIT_STRESS, CREDIT_STRESS, CREDIT_CRISIS
- YIELD_CURVE: DEEP_INVERSION, MODERATE_INVERSION, FLAT_CURVE, NORMAL_CURVE, STEEP_CURVE, EXTREME_STEEPNESS
- ROTATION: DEEP_DEFENSIVE, DEFENSIVE, NEUTRAL_DEFENSIVE, NEUTRAL_CYCLICAL, CYCLICAL, EXTREME_CYCLICAL

D2 Standard Labels: FAST_CRUSH_3D, DECELERATING_DOWN_3D, STABLE_CONTINUATION_3D, ACCELERATING_UP_3D, FAST_SPIKE_3D
D3 Standard Labels: VOL_EXTREME_SQUEEZE, VOL_MODERATE_COMPRESSION, VOL_NEUTRAL_BASELINE, VOL_ACCELERATING_EXPANSION, VOL_PEAK_DECELERATION
Divergence Regimes: BULLISH, BEARISH, NEUTRAL
"""
from pathlib import Path
import re

TESTS_DIR = Path("tests")

D2_STANDARD = ["FAST_CRUSH_3D", "DECELERATING_DOWN_3D", "STABLE_CONTINUATION_3D", "ACCELERATING_UP_3D", "FAST_SPIKE_3D"]
DIVERGENCE_REGIMES = ["BULLISH", "BEARISH", "NEUTRAL"]

STATION_D1 = {
    "vix": ["DEEP_COMPLACENCY", "LOW_VOL", "MODERATE_VOL", "HIGH_VOL", "ELEVATED_PANIC", "CRISIS_SPIKE"],
    "vvix": ["VVIX_CALM", "LOW_VVIX", "MODERATE_VVIX", "HIGH_VVIX", "EXTREME_VVIX", "VOL_OF_VOL_CRISIS"],
    "pcr": ["CALL_EUPHORIA", "BULLISH_BIAS", "NEUTRAL_PCR", "ELEVATED_PUTS", "PANIC_PUTS", "EXTREME_HEDGING"],
    "fg": ["EXTREME_FEAR", "FEAR", "NEUTRAL_FEAR", "NEUTRAL_GREED", "GREED", "EXTREME_GREED"],
    "sv5_turbulence": ["CALM_PARTICIPATION", "LOW_TURBULENCE", "MODERATE_TURBULENCE", "ELEVATED_PARTICIPATION", "HIGH_TURBULENCE", "TURBULENCE_CRISIS"],
    "skew": ["TAIL_COMPLACENCY", "NORMAL_TAIL", "ELEVATED_TAIL", "HIGH_SKEW", "PARANOIA_SKEW", "BLACK_SWAN_PARANOIA"],
    "credit": ["DEEP_CREDIT_EASE", "CREDIT_EASE", "STABLE_CREDIT", "ELEVATED_CREDIT_STRESS", "CREDIT_STRESS", "CREDIT_CRISIS"],
    "yield_curve": ["DEEP_INVERSION", "MODERATE_INVERSION", "FLAT_CURVE", "NORMAL_CURVE", "STEEP_CURVE", "EXTREME_STEEPNESS"],
    "rotation": ["DEEP_DEFENSIVE", "DEFENSIVE", "NEUTRAL_DEFENSIVE", "NEUTRAL_CYCLICAL", "CYCLICAL", "EXTREME_CYCLICAL"]
}

def update_test_file(station_name: str, test_filename: str):
    fpath = TESTS_DIR / test_filename
    if not fpath.exists():
        return

    content = fpath.read_text(encoding="utf-8")
    d1_labels = STATION_D1[station_name]

    # Replace bin list assertion
    bin_attr = f"{station_name}_bin" if f"{station_name}_bin" in content else "bin"
    
    # Use regex to replace bin assertion block
    pattern_bin = re.compile(rf"assert guidance\.\w+_bin in \[[\s\S]*?\]", re.MULTILINE)
    replacement_bin = f"assert guidance.{bin_attr} in {d1_labels}"
    content = pattern_bin.sub(replacement_bin, content)

    # Replace velocity_vector assertion block
    pattern_vel = re.compile(r"assert guidance\.velocity_vector in \[[\s\S]*?\]", re.MULTILINE)
    replacement_vel = f"assert guidance.velocity_vector in {D2_STANDARD}"
    content = pattern_vel.sub(replacement_vel, content)

    # Replace divergence_regime assertion block
    pattern_div = re.compile(r"assert guidance\.divergence_regime in \[[\s\S]*?\]", re.MULTILINE)
    replacement_div = f"assert guidance.divergence_regime in {DIVERGENCE_REGIMES}"
    content = pattern_div.sub(replacement_div, content)

    fpath.write_text(content, encoding="utf-8")
    print(f"✅ Updated test assertions in {test_filename}")

if __name__ == "__main__":
    update_test_file("vix", "test_vix_fact_store.py")
    update_test_file("vvix", "test_vvix_fact_store.py")
    update_test_file("pcr", "test_pcr_fact_store.py")
    update_test_file("fg", "test_fg_fact_store.py")
    update_test_file("sv5_turbulence", "test_sv5_turbulence_fact_store.py")
    update_test_file("skew", "test_skew_lookup.py")
    update_test_file("credit", "test_credit_lookup.py")
    update_test_file("yield_curve", "test_yield_curve_lookup.py")
    update_test_file("rotation", "test_rotation_lookup.py")
    print("Unit tests taxonomy alignment complete.")
