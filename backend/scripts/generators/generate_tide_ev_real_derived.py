#!/usr/bin/env python3
"""
Generate Real EV Derived Matrix & Multi-Level Rules (P(bull) x EV)
===================================================================
Reads rc_tide_ev_probability_table.json (Real Point-in-Time EV model).
Applies Hierarchical Bayesian Shrinkage (L3 -> L2 -> L1 -> L0) across all 3 ZigZag scales (zz25, zz50, zz75).
Computes Risk/Reward Asymmetry, Capital Velocity (ev_per_day), Sharpe, and Rule 21 compliant Fact Store.

Output: backend/modules/quality_swing/domain/rules/rc_tide_ev_derived.json
"""
import sys, json, logging, datetime, subprocess
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

INPUT_PATH = root_dir / "backend/modules/quality_swing/domain/rules/rc_tide_ev_probability_table.json"
OUTPUT_PATH = root_dir / "backend/modules/quality_swing/domain/rules/rc_tide_ev_derived.json"

DEFAULT_FRICTION_BPS = 0.0010
PRIOR_WEIGHT = 20.0
ZIGZAG_LEVELS = ["zz25", "zz50", "zz75"]


def shrink_tide_cell(cell: dict, parent_cell: dict) -> dict:
    """Applies Hierarchical Bayesian Shrinkage on cell toward parent_cell."""
    if not cell:
        return parent_cell or {}

    n = float(cell.get("n", 0))
    parent = parent_cell or {}

    derived = {
        "n": int(n),
        "is_rare_state": n < 30,
        "std_return": round(float(cell.get("std_return", parent.get("std_return", 0.05))), 4),
    }

    ev_sum = 0.0

    for scale in ZIGZAG_LEVELS:
        n_pos = float(cell.get(f"n_pos_{scale}", 0))
        n_neg = float(cell.get(f"n_neg_{scale}", 0))
        sum_pos = float(cell.get(f"sum_max_{scale}", 0.0))
        sum_neg = float(cell.get(f"sum_min_{scale}", 0.0))
        e_days_raw = float(cell.get(f"e_days_{scale}", 10.0))

        n_tot = n_pos + n_neg

        p_parent = parent.get(f"p_bull_{scale}", 0.50)
        e_max_parent = parent.get(f"e_ret_max_{scale}", 0.05)
        e_min_parent = parent.get(f"e_ret_min_{scale}", -0.04)
        days_parent = parent.get(f"e_days_{scale}", 10.0)

        if n_tot > 0:
            raw_p_bull = n_neg / n_tot  # P(floor / bottom MIN)
            e_max = sum_pos / n_pos if n_pos > 0 else e_max_parent
            e_min = sum_neg / n_neg if n_neg > 0 else e_min_parent
            e_days = e_days_raw
        else:
            raw_p_bull = p_parent
            e_max = e_max_parent
            e_min = e_min_parent
            e_days = days_parent

        p_bull = (n_tot * raw_p_bull + PRIOR_WEIGHT * p_parent) / (n_tot + PRIOR_WEIGHT)
        p_bear = 1.0 - p_bull

        ev_net = (p_bull * e_max + p_bear * e_min) - DEFAULT_FRICTION_BPS
        ev_per_day = ev_net / max(e_days, 1.0)
        ev_sum += ev_net

        abs_min = abs(e_min) if abs(e_min) > 1e-6 else 1e-6
        rr_asymmetry = round(e_max / abs_min, 4)

        derived[scale] = {
            "p_bull": round(p_bull, 4),
            "p_bear": round(p_bear, 4),
            "e_ret_max": round(e_max, 4),
            "e_ret_min": round(e_min, 4),
            "ev_net": round(ev_net, 4),
            "e_days": round(e_days, 1),
            "ev_per_day": round(ev_per_day, 6),
            "rr_asymmetry": rr_asymmetry,
        }

    std_ret = derived["std_return"]
    ev_global = ev_sum / len(ZIGZAG_LEVELS)
    derived["ev_net_global"] = round(ev_global, 4)
    derived["sharpe"] = round(ev_global / (std_ret + 1e-6), 4)

    return derived


def main():
    if not INPUT_PATH.exists():
        logger.error(f"Input file does not exist: {INPUT_PATH}")
        sys.exit(1)

    logger.info(f"Loading {INPUT_PATH}...")
    with open(INPUT_PATH) as f:
        data = json.load(f)

    # Process L0 Global Baseline
    logger.info("Processing L0 Global Baseline...")
    l0_raw = data.get("l0_global", {})
    l0_derived = shrink_tide_cell(l0_raw, {})

    # Process L1 Macro
    logger.info("Processing L1 Macro Rollups...")
    l1_raw = data.get("l1_macro", {})
    l1_derived = {}
    for k1, v1 in l1_raw.items():
        l1_derived[k1] = shrink_tide_cell(v1, l0_derived)

    # Process L2 Mid-Macro
    logger.info("Processing L2 Mid-Macro Rollups...")
    l2_raw = data.get("l2_mid_macro", {})
    l2_derived = {}
    for k2, v2 in l2_raw.items():
        parts = k2.split("|")
        parent_k1 = parts[0] if parts else ""
        parent_l1 = l1_derived.get(parent_k1, l0_derived)
        l2_derived[k2] = shrink_tide_cell(v2, parent_l1)

    # Process L3 Full States
    logger.info("Processing L3 Full 3D States...")
    l3_raw = data.get("l3_full_state", {})
    l3_derived = {}
    for k3, v3 in l3_raw.items():
        parts = k3.split("|")
        parent_k2 = f"{parts[0]}|{parts[1]}" if len(parts) >= 2 else ""
        parent_l2 = l2_derived.get(parent_k2, l0_derived)
        l3_derived[k3] = shrink_tide_cell(v3, parent_l2)

    try:
        git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
    except Exception:
        git_commit = "unknown"

    from backend.modules.quality_swing.domain.rules.rc_slope_classifier import _SLOPE_TH
    t_th = _SLOPE_TH["T"]
    c_th = _SLOPE_TH["C"]

    _documentation = {
        "model_purpose": "Point-in-Time Real Expected Value (EV) and Dual Confluence Matrix for quality_swing Tide Model",
        "return_formula": "Real Return = (Price(t_pivot_next) / Close(t)) - 1. Zero Ghost Return bias.",
        "horizon_gate": "Maximum horizon = 120 days. Eliminates truncated or missing future swings.",
        "state_hierarchy": {
            "L3": "Full 3D State: T_slope|C_slope|vwap_sigma_wave (180 granular micro/macro states)",
            "L2": "Mid-Macro State: T_slope|C_slope (36 mid-term trend states)",
            "L1": "Macro State: T_slope (6 macro tide trend states)",
            "L0": "Global Baseline: Aggregated market baseline across all observations"
        },
        "dimension_thresholds_definition": {
            "Tide_slope_T_200d": {
                "T+++": f"Extremely Bullish Macro Trend (slope_norm >= +{t_th.get('p90', 9.0)})",
                "T++": f"Strong Bullish Macro Trend (+{t_th.get('p75', 5.8)} <= slope_norm < +{t_th.get('p90', 9.0)})",
                "T+": f"Mild Bullish Macro Trend (+{t_th.get('p50', 2.4)} <= slope_norm < +{t_th.get('p75', 5.8)})",
                "T-": f"Mild Bearish Macro Trend ({t_th.get('p25', -0.8)} < slope_norm <= +{t_th.get('p50', 2.4)})",
                "T--": f"Strong Bearish Macro Trend ({t_th.get('p10', -3.7)} < slope_norm <= {t_th.get('p25', -0.8)})",
                "T---": f"Extremely Bearish Macro Trend (slope_norm <= {t_th.get('p10', -3.7)})"
            },
            "Current_slope_C_50d": {
                "C+++": f"Extremely Bullish Medium Impulse (slope_norm >= +{c_th.get('p90', 15.8)})",
                "C++": f"Strong Bullish Medium Impulse (+{c_th.get('p75', 9.7)} <= slope_norm < +{c_th.get('p90', 15.8)})",
                "C+": f"Mild Bullish Medium Impulse (+{c_th.get('p50', 2.8)} <= slope_norm < +{c_th.get('p75', 9.7)})",
                "C-": f"Mild Bearish Pullback ({c_th.get('p25', -3.7)} < slope_norm <= +{c_th.get('p50', 2.8)})",
                "C--": f"Strong Bearish Pullback ({c_th.get('p10', -9.3)} < slope_norm <= {c_th.get('p25', -3.7)})",
                "C---": f"Extremely Bearish Pullback (slope_norm <= {c_th.get('p10', -9.3)})"
            },
            "vwap_sigma_wave_position": {
                "<<": "FLOOR — Price far below VWAP Wave (sigma_vwap < -1.0 std dev)",
                "<": "BELOW — Price moderately below VWAP Wave (-1.0 <= sigma_vwap < -0.30)",
                "~": "NEUTRAL — Price near VWAP Wave center (-0.30 <= sigma_vwap <= +0.30)",
                ">": "ABOVE — Price moderately above VWAP Wave (+0.30 < sigma_vwap <= +1.0)",
                ">>": "CEILING — Price far above VWAP Wave (sigma_vwap > +1.0 std dev)"
            }
        },
        "field_glossary": {
            "n": "Sample size for this state/level combination",
            "is_rare_state": "Flag booleano de muestra baja (N < 30) preservado para eventos de cola",
            "p_bull": "P(next pivot = MIN). Probability of floor/bottom opportunity",
            "p_bear": "P(next pivot = MAX). Probability of ceiling/top opportunity",
            "ev_net": "Real Expected Value: P(bull)*E[ret_max] + P(bear)*E[ret_min] - friction_bps",
            "e_ret_min": "Expected real drawdown % to next MIN pivot",
            "e_ret_max": "Expected real upside gain % to next MAX pivot",
            "sharpe": "Real EV / std(real_return). Risk-adjusted return ratio",
            "rr_asymmetry": "E[ret_max] / |E[ret_min]|. Risk/Reward Asymmetry Ratio",
            "e_days": "Expected calendar days to next pivot",
            "ev_per_day": "Real return speed per calendar day"
        },
        "signal_interpretation_policy": "Clean Architecture Standard: Tactical actions are dynamically evaluated in runtime by pure-domain adapters. Dynamic rules: P(bull) >= 0.55 and EV >= +0.005 -> ACCUMULATE; P(bull) >= 0.52 and EV >= +0.002 -> BUY_DIP; P(bull) <= 0.45 or EV <= -0.005 -> TRIM; Else -> NEUTRAL.",
        "rare_event_policy": "States with extreme deviation (vwap_sigma_wave = << or >>) represent mean-reversion spring stretch. Samples n >= 1 are preserved without artificial fallback degradation to maintain tail asymmetry.",
        "reproducibility_context": {
            "calibration_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "calibrated_under_commit": git_commit
        }
    }

    output_derived = {
        "_documentation": _documentation,
        "version": "v2_tide_ev_derived_2026",
        "git_commit": git_commit,
        "friction_bps": DEFAULT_FRICTION_BPS,
        "prior_weight": PRIOR_WEIGHT,
        "n_samples_total": int(data.get("n_samples_total", 0)),
        "l0_global": l0_derived,
        "l1_macro": l1_derived,
        "l2_mid_macro": l2_derived,
        "l3_full_state": l3_derived,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output_derived, f, indent=2)

    logger.info(f"🎉 Matriz Tide EV derivada generada exitosamente en {OUTPUT_PATH}")
    logger.info(f"   Celdas L1: {len(l1_derived)} | Celdas L2: {len(l2_derived)} | Celdas L3: {len(l3_derived)}")


if __name__ == "__main__":
    main()
