#!/usr/bin/env python3
"""
Generate Real EV Derived Matrix & Dual Confluence Rules (P(bull) x EV)
=======================================================================
Reads rc_ev_probability_table.json (Real Point-in-Time EV model).
Computes derived rules, Dual Confluence Matrix (P_bull x EV), Risk/Reward Asymmetry,
and multi-level rollups (L0, L1, L2, L3) for quality_swing.

Output: backend/modules/quality_swing/domain/rules/rc_ev_derived.json
"""
import os, sys, json, logging
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

INPUT_PATH = root_dir / "backend/modules/quality_swing/domain/rules/rc_ev_probability_table.json"
OUTPUT_PATH = root_dir / "backend/modules/quality_swing/domain/rules/rc_ev_derived.json"


def process_levels_dict(levels_raw: dict) -> dict:
    """Derive pure numeric P(bull) x EV metrics, asymmetry, and speed for levels dict.
    
    Clean Architecture: Zero business signals or taxonomy action codes in JSON.
    The JSON Fact Store contains strictly empirical numeric measurements.
    """
    derived_levels = {}
    for lvl_key, metrics in levels_raw.items():
        p_bull = metrics.get("p_max", 0.5)
        p_bear = metrics.get("p_min", 0.5)
        ev = metrics.get("ev", 0.0)
        e_ret_max = metrics.get("e_ret_max", 0.0)
        e_ret_min = metrics.get("e_ret_min", 0.0)
        e_days = metrics.get("e_days", 1.0)
        sharpe = metrics.get("sharpe", 0.0)
        n = metrics.get("n", 0)

        # Risk/Reward Asymmetry Ratio
        abs_min = abs(e_ret_min) if abs(e_ret_min) > 1e-6 else 1e-6
        rr_asymmetry = round(e_ret_max / abs_min, 4)
        ev_per_day = round(ev / max(e_days, 1.0), 6)

        derived_levels[lvl_key] = {
            "n": n,
            "is_rare_state": n < 30,
            "p_bull": round(p_bull, 4),
            "p_bear": round(p_bear, 4),
            "e_ret_min": e_ret_min,
            "e_ret_max": e_ret_max,
            "ev": ev,
            "std_return": metrics.get("std_return", 0.0),
            "sharpe": sharpe,
            "e_days": e_days,
            "e_speed": metrics.get("e_speed", 0.0),
            "rr_asymmetry": rr_asymmetry,
            "ev_per_day": ev_per_day,
            "fatigue_buckets": metrics.get("fatigue_buckets", {}),
        }
    return derived_levels




def main():
    if not INPUT_PATH.exists():
        logger.error(f"Input file does not exist: {INPUT_PATH}")
        sys.exit(1)

    logger.info(f"Loading {INPUT_PATH}...")
    with open(INPUT_PATH) as f:
        data = json.load(f)

    # Process L0 Global Baseline
    logger.info("Processing L0 Global Baseline...")
    l0_derived = process_levels_dict(data.get("l0_global", {}).get("levels", {}))

    # Process L1 Macro
    logger.info("Processing L1 Macro Rollups...")
    l1_derived = {}
    for k1, v1 in data.get("l1_macro", {}).items():
        l1_derived[k1] = {
            "levels": process_levels_dict(v1.get("levels", {}))
        }

    # Process L2 Mid-Macro
    logger.info("Processing L2 Mid-Macro Rollups...")
    l2_derived = {}
    for k2, v2 in data.get("l2_mid_macro", {}).items():
        l2_derived[k2] = {
            "levels": process_levels_dict(v2.get("levels", {}))
        }

    # Process L3 States
    logger.info("Processing L3 Full 3D States...")
    l3_derived = {}
    for k3, v3 in data.get("l3_states", {}).items():
        l3_derived[k3] = {
            "n_total": v3.get("n_total", 0),
            "levels": process_levels_dict(v3.get("levels", {}))
        }

    _documentation = {
        "model_purpose": "Point-in-Time Real Expected Value (EV) and Dual Confluence Matrix for quality_swing",
        "return_formula": "Real Return = (Price(t_pivot_next) / Close(t)) - 1. Zero Ghost Return bias.",
        "horizon_gate": "Maximum horizon = 120 days. Eliminates truncated or missing future swings.",
        "state_hierarchy": {
            "L3": "Full 3D State: T_slope|C_slope|vwap_sigma_wave (180 granular micro/macro states)",
            "L2": "Mid-Macro State: T_slope|C_slope (36 mid-term trend states)",
            "L1": "Macro State: T_slope (6 macro tide trend states)",
            "L0": "Global Baseline: Aggregated market baseline across all observations"
        },
        "field_glossary": {
            "n": "Sample size for this state/level combination",
            "p_bull": "P(next pivot = MAX). Probability of upward swing completion",
            "p_bear": "P(next pivot = MIN). Probability of downward swing completion",
            "ev": "Real Expected Value: P(bull)*E[ret_max] + P(bear)*E[ret_min]",
            "e_ret_min": "Expected real drawdown % to next MIN pivot",
            "e_ret_max": "Expected real upside gain % to next MAX pivot",
            "sharpe": "Real EV / std(real_return). Risk-adjusted return ratio",
            "rr_asymmetry": "E[ret_max] / |E[ret_min]|. Risk/Reward Asymmetry Ratio",
            "e_days": "Expected calendar days to next pivot",
            "e_speed": "Real return speed per calendar day",
            "signal": "Default signal classification (ACCUMULATE / BUY_DIP / NEUTRAL / TRIM)",
            "fatigue_buckets": "Raw EV performance grouped by run_length (1, 2, 3-4, 5-7, 8-10, 11+ bars)"
        },
        "rare_event_policy": "States with extreme deviation (vwap_sigma_wave = << or >>) represent mean-reversion spring stretch. Samples n >= 1 are preserved without artificial fallback degradation to maintain tail asymmetry."
    }

    derived_output = {
        "version": "v2_ev_real_derived_2026-07-25",
        "source_file": "rc_ev_probability_table.json",
        "description": "Real Point-in-Time Dual Confluence Matrix (P(bull) x EV) with Multi-Level Fallbacks (L0-L3)",
        "_documentation": _documentation,
        "l0_global": {"levels": l0_derived},
        "l1_macro": l1_derived,
        "l2_mid_macro": l2_derived,
        "l3_states": l3_derived,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(derived_output, f, indent=2)

    logger.info(f"🎉 Successfully generated {OUTPUT_PATH}")
    logger.info(f"   L3 States: {len(l3_derived)} | L2 States: {len(l2_derived)} | L1 States: {len(l1_derived)}")


if __name__ == "__main__":
    main()
