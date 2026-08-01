#!/usr/bin/env python3
"""
Generate Empirical Sector Rotation Intelligence (ROTATION) Fact Store Table (Vault 1998–2026)
================================================================================================
Calculates exact empirical percentiles for the composite Sector Rotation Index (L0 - 7 Bins)
combining Z252(XLY/XLP) + Z252(XLK/XLU) and 3-day Kinematic Velocity (L1 - 7 Vectors)
across 27+ years of aligned market history in Neon Vault (1998–2026, 6,900+ trading sessions).

L0 Labels (Static Rotation Level):
  - EXTREME_DEFENSIVE_ROTATION (Index <= P05)
  - DEFENSIVE_ROTATION (P05 < Index <= P15)
  - MODERATE_DEFENSIVE (P15 < Index <= P35)
  - BALANCED_ROTATION (P35 < Index <= P65)
  - MODERATE_CYCLICAL (P65 < Index <= P85)
  - CYCLICAL_ROTATION (P85 < Index <= P95)
  - EXTREME_CYCLICAL_EXPANSION (Index > P95)

L1 Labels (3-Day Fast Kinematic Velocity Delta_3d):
  - EXTREME_DEFENSIVE_FLIGHT_3D (Delta_3d <= P05)
  - FAST_DEFENSIVE_ROTATION_3D (P05 < Delta_3d <= P15)
  - DECELERATING_ROTATION_3D (P15 < Delta_3d <= P35)
  - STABLE_ROTATION_3D (P35 < Delta_3d <= P65)
  - ACCELERATING_CYCLICAL_3D (P65 < Delta_3d <= P85)
  - FAST_CYCLICAL_SURGE_3D (P85 < Delta_3d <= P95)
  - EXTREME_CYCLICAL_SPIKE_3D (Delta_3d > P95)

Outputs a Rule 21 compliant JSON Fact Store at:
backend/modules/entry_decision/domain/rules/rotation_fact_store.json

Usage:
    python -m backend.scripts.generate_rotation_fact_table
"""
import os
import sys
import json
import logging
from pathlib import Path
import numpy as np
import pandas as pd

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GenerateRotationFactTable")

OUTPUT_PATH = root_dir / "backend/modules/entry_decision/domain/rules/rotation_fact_store.json"

ZIGZAG_LEVELS = [0.025, 0.05, 0.075]
ZIGZAG_LABEL = {0.025: "zz25", 0.05: "zz50", 0.075: "zz75"}
MAX_HORIZONS = {0.025: 30, 0.05: 60, 0.075: 90}

PERCENTILES_7 = [0.05, 0.15, 0.35, 0.65, 0.85, 0.95]
LABELS_L0 = [
    "EXTREME_DEFENSIVE_ROTATION",
    "DEFENSIVE_ROTATION",
    "MODERATE_DEFENSIVE",
    "BALANCED_ROTATION",
    "MODERATE_CYCLICAL",
    "CYCLICAL_ROTATION",
    "EXTREME_CYCLICAL_EXPANSION",
]
LABELS_L1 = [
    "EXTREME_DEFENSIVE_FLIGHT_3D",
    "FAST_DEFENSIVE_ROTATION_3D",
    "DECELERATING_ROTATION_3D",
    "STABLE_ROTATION_3D",
    "ACCELERATING_CYCLICAL_3D",
    "FAST_CYCLICAL_SURGE_3D",
    "EXTREME_CYCLICAL_SPIKE_3D",
]


def classify_bin(v: float, edges: list) -> str:
    for idx, e in enumerate(edges):
        if v < e:
            return LABELS_L0[idx]
    return LABELS_L0[-1]


def classify_speed(v: float, edges: list) -> str:
    if pd.isna(v):
        return "STABLE_ROTATION_3D"
    for idx, e in enumerate(edges):
        if v < e:
            return LABELS_L1[idx]
    return LABELS_L1[-1]


def calculate_3d_rotation_stats(df_aligned: pd.DataFrame):
    prices_c = df_aligned["close"].values
    prices_h = df_aligned["high"].values
    prices_l = df_aligned["low"].values
    rot_vals = df_aligned["rotation_index"].values
    rot_prev_vals = df_aligned["rotation_prev"].values
    rot_bins_arr = df_aligned["rotation_bin"].values
    rot_speeds_arr = df_aligned["rotation_speed"].values
    state_keys_arr = df_aligned["state_key"].values
    n = len(prices_c)

    state_indices = {}
    for i in range(n):
        sk = state_keys_arr[i]
        if sk not in state_indices:
            state_indices[sk] = []
        state_indices[sk].append(i)

    final_states = {}

    for state_k, idx_list in state_indices.items():
        n_state = len(idx_list)
        rot_t0_vals = rot_vals[idx_list]
        rot_t_minus1_vals = rot_prev_vals[idx_list]

        state_doc = {
            "n": int(n_state),
            "rotation_index_t0_stats": {
                "min": round(float(np.min(rot_t0_vals)), 4),
                "max": round(float(np.max(rot_t0_vals)), 4),
                "mean": round(float(np.mean(rot_t0_vals)), 4),
                "std": round(float(np.std(rot_t0_vals)), 4) if n_state > 1 else 0.0,
            },
            "rotation_index_t_minus_1_stats": {
                "min": round(float(np.min(rot_t_minus1_vals)), 4),
                "max": round(float(np.max(rot_t_minus1_vals)), 4),
                "mean": round(float(np.mean(rot_t_minus1_vals)), 4),
            },
        }

        evs = {}

        for target_pct in ZIGZAG_LEVELS:
            lbl = ZIGZAG_LABEL[target_pct]
            max_days = MAX_HORIZONS[target_pct]

            pos_returns = []
            neg_returns = []
            pos_days = []
            neg_days = []
            days_hits = []
            days_all = []

            for i in idx_list:
                p0 = prices_c[i]
                local_bin = rot_bins_arr[i]
                friction = 0.0025 if local_bin in ("EXTREME_DEFENSIVE_ROTATION", "DEFENSIVE_ROTATION") else 0.0010

                target_up = p0 * (1.0 + target_pct)
                target_dn = p0 * (1.0 - target_pct)

                hit = False
                for d in range(1, max_days + 1):
                    if i + d >= n:
                        break
                    ph = prices_h[i + d]
                    pl = prices_l[i + d]

                    hit_up = ph >= target_up
                    hit_dn = pl <= target_dn

                    if hit_up and not hit_dn:
                        pos_returns.append(((ph / p0) - 1.0) - friction)
                        pos_days.append(d)
                        days_hits.append(d)
                        days_all.append(d)
                        hit = True
                        break
                    elif hit_dn and not hit_up:
                        neg_returns.append(((pl / p0) - 1.0) - friction)
                        neg_days.append(d)
                        days_hits.append(d)
                        days_all.append(d)
                        hit = True
                        break
                    elif hit_up and hit_dn:
                        neg_returns.append(((pl / p0) - 1.0) - friction)
                        neg_days.append(d)
                        days_hits.append(d)
                        days_all.append(d)
                        hit = True
                        break

                if not hit:
                    end_idx = min(i + max_days, n - 1)
                    d_end = max(end_idx - i, 1)
                    days_all.append(d_end)
                    ret_end = ((prices_c[end_idx] / p0) - 1.0) - friction
                    if ret_end >= 0:
                        pos_returns.append(ret_end)
                    else:
                        neg_returns.append(ret_end)

            n_pos = len(pos_returns)
            n_neg = len(neg_returns)
            n_tot = n_pos + n_neg

            p_bull = n_pos / n_tot if n_tot > 0 else 0.50
            p_bear = 1.0 - p_bull

            e_max = float(np.mean(pos_returns)) if n_pos > 0 else target_pct
            e_min = float(np.mean(neg_returns)) if n_neg > 0 else -target_pct

            e_days = float(np.median(days_hits)) if len(days_hits) > 0 else float(np.median(days_all)) if len(days_all) > 0 else 15.0
            ftt_bull_days = float(np.median(pos_days)) if len(pos_days) > 0 else e_days
            ftt_bear_days = float(np.median(neg_days)) if len(neg_days) > 0 else e_days

            ev_net = p_bull * e_max + p_bear * e_min
            ev_per_day = ev_net / max(e_days, 1.0)
            abs_min = abs(e_min) if abs(e_min) > 1e-6 else 1e-6
            rr_asymmetry = e_max / abs_min

            state_doc[lbl] = {
                "n_pos": int(n_pos),
                "n_neg": int(n_neg),
                "p_bull": round(float(p_bull), 4),
                "p_bear": round(float(p_bear), 4),
                "e_ret_max": round(float(e_max), 4),
                "e_ret_min": round(float(e_min), 4),
                "ev_net": round(float(ev_net), 4),
                "e_days": round(float(e_days), 1),
                "ftt_bull_days": round(float(ftt_bull_days), 1),
                "ftt_bear_days": round(float(ftt_bear_days), 1),
                "ev_per_day": round(float(ev_per_day), 6),
                "rr_asymmetry": round(float(rr_asymmetry), 4),
            }
            evs[lbl] = ev_net

        # Divergence Regime classification
        ev25, ev50, ev75 = evs["zz25"], evs["zz50"], evs["zz75"]
        p_bull_50 = state_doc["zz50"]["p_bull"]

        if p_bull_50 >= 0.65 or (ev25 > 0 and ev50 > 0 and ev75 > 0):
            regime = "FULL_STRUCTURAL_BULL"
        elif p_bull_50 <= 0.35 or (ev25 < 0 and ev50 < 0 and ev75 < 0):
            regime = "FULL_STRUCTURAL_BEAR"
        elif ev25 > 0 and ev50 < 0:
            regime = "TACTICAL_BOUNCE_ONLY"
        elif ev25 < 0 and ev75 > 0:
            regime = "TACTICAL_PULLBACK"
        else:
            regime = "TRANSITIONAL"

        # Action Taxonomy (Rule 20)
        sample_bin, sample_speed = state_k.split("__")

        if (
            sample_bin == "EXTREME_DEFENSIVE_ROTATION"
            or sample_speed == "EXTREME_DEFENSIVE_FLIGHT_3D"
            or (sample_bin == "DEFENSIVE_ROTATION" and sample_speed in ("FAST_DEFENSIVE_ROTATION_3D", "EXTREME_DEFENSIVE_FLIGHT_3D"))
        ):
            action_code = "MKT_ROTATION_DEFENSIVE_FREEZE"
        elif sample_bin in ("DEFENSIVE_ROTATION", "MODERATE_DEFENSIVE"):
            action_code = "MKT_ROTATION_DEFENSIVE_FLIGHT"
        elif sample_bin == "BALANCED_ROTATION":
            action_code = "MKT_ROTATION_NEUTRAL_BALANCED"
        else:
            action_code = "MKT_ROTATION_CYCLICAL_EXPANSION"

        state_doc["divergence_regime"] = regime
        state_doc["operational_guidance"] = action_code
        final_states[state_k] = state_doc


    return final_states


def main():
    logger.info("Cargando historia completa de Neon Vault (market.ohlcv_bars XLY, XLP, XLK, XLU, SPY 1998–2026)...")
    store = TimescaleDataStore()
    conn = store._conn()
    try:
        df_bars = pd.read_sql(
            """
            SELECT time::date as date, ticker, open, high, low, close
            FROM market.ohlcv_bars
            WHERE ticker IN ('XLY', 'XLP', 'XLK', 'XLU', 'SPY')
              AND timeframe = '1d'
            ORDER BY time, ticker
        """,
            conn,
        )
    finally:
        store._put(conn)

    pivot_c = df_bars.pivot(index="date", columns="ticker", values="close").dropna()
    pivot_h = df_bars.pivot(index="date", columns="ticker", values="high").dropna()
    pivot_l = df_bars.pivot(index="date", columns="ticker", values="low").dropna()

    common = pivot_c.index
    xly_c = pivot_c["XLY"].loc[common]
    xlp_c = pivot_c["XLP"].loc[common]
    xlk_c = pivot_c["XLK"].loc[common]
    xlu_c = pivot_c["XLU"].loc[common]
    spy_c = pivot_c["SPY"].loc[common]
    spy_h = pivot_h["SPY"].loc[common]
    spy_l = pivot_l["SPY"].loc[common]

    ratio_xly_xlp = xly_c / xlp_c
    ratio_xlk_xlu = xlk_c / xlu_c

    # Calculate 252-day rolling z-scores
    mean_xly_xlp = ratio_xly_xlp.rolling(252, min_periods=20).mean()
    std_xly_xlp = ratio_xly_xlp.rolling(252, min_periods=20).std().replace(0, np.nan)
    z_xly_xlp = (ratio_xly_xlp - mean_xly_xlp) / std_xly_xlp

    mean_xlk_xlu = ratio_xlk_xlu.rolling(252, min_periods=20).mean()
    std_xlk_xlu = ratio_xlk_xlu.rolling(252, min_periods=20).std().replace(0, np.nan)
    z_xlk_xlu = (ratio_xlk_xlu - mean_xlk_xlu) / std_xlk_xlu

    rotation_index = (z_xly_xlp + z_xlk_xlu).fillna(0.0)
    rotation_d3 = rotation_index.diff(3)

    # Valid range dropping initial warm-up period
    valid_mask = ~rotation_index.isna() & ~rotation_d3.isna()
    rotation_index = rotation_index[valid_mask]
    rotation_d3 = rotation_d3[valid_mask]
    common = rotation_index.index

    start_date = common.min()
    end_date = common.max()
    n_days = len(common)
    logger.info(f"Población de entrenamiento: {start_date} a {end_date} ({n_days} días hábiles / {n_days/252:.2f} años)")

    # Percentiles
    rotation_edges = [float(x) for x in rotation_index.quantile(PERCENTILES_7)]
    vel_edges = [float(x) for x in rotation_d3.quantile(PERCENTILES_7)]

    logger.info(f"Cortes ROTATION Index Level (L0 - 1998-2026): {rotation_edges}")
    logger.info(f"Cortes ROTATION Velocity 3-Day (L1 - 1998-2026): {vel_edges}")

    df_aligned = pd.DataFrame(
        {
            "close": spy_c.loc[common],
            "high": spy_h.loc[common],
            "low": spy_l.loc[common],
            "rotation_index": rotation_index,
            "rotation_prev": rotation_index.shift(1).fillna(0.0),
            "rotation_bin": rotation_index.apply(lambda v: classify_bin(v, rotation_edges)),
            "rotation_speed": rotation_d3.apply(lambda v: classify_speed(v, vel_edges)),
        }
    )

    df_aligned["state_key"] = df_aligned["rotation_bin"] + "__" + df_aligned["rotation_speed"]

    # Compute 3D rotation stats
    pure_states = calculate_3d_rotation_stats(df_aligned)

    # Fact store json document (Rule 21)
    fact_store = {
        "_documentation": {
            "model_purpose": "Composite Cyclical vs Defensive Sector Rotation Index (XLY/XLP + XLK/XLU Z-Scores) 3-Day Kinematic Matrix (Vault 1998-2026)",
            "return_formula": "R_net = (P_ftt / P_t) - 1.0 - friction (25bps in EXTREME_DEFENSIVE_ROTATION or DEFENSIVE_ROTATION, 10bps standard)",
            "velocity_lookback_window": "3 trading days (72h fast response)",
            "data_sources": {
                "bars": "market.ohlcv_bars (XLY, XLP, XLK, XLU, SPY)",
                "start_date": str(start_date),
                "end_date": str(end_date),
                "sample_size_days": int(n_days),
                "years_covered": round(float(n_days / 252.0), 2),
            },
            "state_hierarchy": {
                "L0": "Rotation_Index_Percentiles_7",
                "L1": "Rotation_3Day_Fast_Velocity_Percentiles_7",
            },
            "dimension_thresholds_definition": {
                "rotation_percentiles": PERCENTILES_7,
                "rotation_edges": rotation_edges,
                "rotation_speed_percentiles": PERCENTILES_7,
                "rotation_speed_edges": vel_edges,
                "rotation_labels_l0": LABELS_L0,
                "rotation_labels_l1": LABELS_L1,
            },
            "field_glossary": {
                "n": "Sample size in this exact sector rotation stereotype",
                "n_pos": "Exact number of positive barrier touch outcomes in this specific condition",
                "n_neg": "Exact number of negative barrier touch outcomes in this specific condition",
                "p_bull": "Pure exclusive probability target threshold is hit first in this exact condition",
                "p_bear": "Pure exclusive probability stop threshold is hit first in this exact condition",
                "e_ret_max": "Pure exclusive average net return when MAX threshold is hit in this exact condition",
                "e_ret_min": "Pure exclusive average net return when MIN threshold is hit in this exact condition",
                "ev_net": "Pure exclusive net expected value for this exact condition",
                "e_days": "Pure exclusive median First Touch Time (FTT) in trading days for hits in this condition",
                "ftt_bull_days": "Pure exclusive median FTT for bull target hits in this condition",
                "ftt_bear_days": "Pure exclusive median FTT for bear stop hits in this condition",
                "ev_per_day": "Capital velocity (ev_net / e_days)",
                "rr_asymmetry": "e_ret_max / |e_ret_min|",
                "divergence_regime": "Multi-scale horizon divergence regime",
                "operational_guidance": "Sizing code from Universal Institutional Taxonomy",
            },
            "signal_interpretation_policy": "Pure domain adapters (RotationLookupAdapter, RotationSigmetService, MarketHealthIntelligence) interpret probabilities dynamically.",
            "reproducibility_context": {
                "calibration_timestamp": "2026-08-01T00:00:00Z",
                "calibrated_under_commit": "HEAD",
            },
        },
        "states": pure_states,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(fact_store, f, indent=2, ensure_ascii=False)

    logger.info(f"Fact Store Sector Rotation Velocity guardado exitosamente en {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
