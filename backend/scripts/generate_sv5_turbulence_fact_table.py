#!/usr/bin/env python3
"""
Generate Empirical SV5_TURBULENCE Fact Store Table (Institutional Volume Turbulence 7x7 Kinematics)
==================================================================================================
Calculates exact empirical asymmetric percentiles for SV5_TURBULENCE index (L0 - 7 Bins)
and SV5_TURBULENCE 3-day Fast Kinematic Velocity (L1 - 7 Vectors) across historical
aligned market population in Neon Vault:
- EXTREME_TURBULENCE_CRUSH_3D (Delta_3d <= P05)
- TURBULENCE_DECAY_3D (P05 < Delta_3d <= P15)
- DECELERATING_3D (P15 < Delta_3d <= P35)
- STABLE_3D (P35 < Delta_3d <= P65)
- RISING_3D (P65 < Delta_3d <= P85)
- TURBULENCE_SURGE_3D (P85 < Delta_3d <= P95)
- EXTREME_TURBULENCE_SPIKE_3D (Delta_3d > P95)

Uses 100% Exclusive Per-Condition Sampling (Zero Blending) for Probabilities,
Intraday High/Low Barrier Touches (López de Prado Triple Barrier), and Condition-Specific FTT Timelines.
Outputs a Rule 21 compliant JSON Fact Store.

Usage:
    backend/.venv/bin/python3 -m backend.scripts.generate_sv5_turbulence_fact_table
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
logger = logging.getLogger("GenerateSV5TurbulenceFactTable")

OUTPUT_PATH = root_dir / "backend/modules/entry_decision/domain/rules/sv5_turbulence_fact_store.json"

ZIGZAG_LEVELS = [0.025, 0.05, 0.075]
ZIGZAG_LABEL = {0.025: "zz25", 0.05: "zz50", 0.075: "zz75"}
MAX_HORIZONS = {0.025: 30, 0.05: 60, 0.075: 90}

PERCENTILES_7 = [0.05, 0.15, 0.35, 0.65, 0.85, 0.95]
LABELS_L0 = [
    "DEEP_SERENITY",
    "SERENE_VOLUME",
    "NORMAL_PARTICIPATION",
    "ELEVATED_PARTICIPATION",
    "HIGH_VOLUME_TURBULENCE",
    "EXTREME_TURBULENCE_SHOCK",
    "CRISIS_TURBULENCE_VETO"
]
LABELS_L1 = [
    "EXTREME_TURBULENCE_CRUSH_3D",
    "TURBULENCE_DECAY_3D",
    "DECELERATING_3D",
    "STABLE_3D",
    "RISING_3D",
    "TURBULENCE_SURGE_3D",
    "EXTREME_TURBULENCE_SPIKE_3D"
]


def classify_bin(v: float, edges: list) -> str:
    for idx, e in enumerate(edges):
        if v < e:
            return LABELS_L0[idx]
    return LABELS_L0[-1]


def classify_speed(v: float, edges: list) -> str:
    if pd.isna(v):
        return "STABLE_3D"
    for idx, e in enumerate(edges):
        if v < e:
            return LABELS_L1[idx]
    return LABELS_L1[-1]


def calculate_3d_sv5_turbulence_stats(df_aligned: pd.DataFrame):
    prices_c = df_aligned['close'].values
    prices_h = df_aligned['high'].values
    prices_l = df_aligned['low'].values
    turb_vals = df_aligned['turbulence'].values
    turb_prev = df_aligned['turbulence_prev'].values
    state_keys_arr = df_aligned['state_key'].values
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
        turb_t0_vals = turb_vals[idx_list]
        turb_prev_vals = turb_prev[idx_list]

        state_doc = {
            "n": int(n_state),
            "turbulence_t0_stats": {
                "min": float(np.min(turb_t0_vals)),
                "max": float(np.max(turb_t0_vals)),
                "mean": float(np.mean(turb_t0_vals)),
                "std": float(np.std(turb_t0_vals)) if n_state > 1 else 0.0
            },
            "turbulence_t_minus_1_stats": {
                "min": float(np.min(turb_prev_vals)),
                "max": float(np.max(turb_prev_vals)),
                "mean": float(np.mean(turb_prev_vals))
            }
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
                local_turb = turb_vals[i]
                # 25 bps friction in panic regime (SV5_TURBULENCE > 10.0), 10 bps standard
                friction = 0.0025 if local_turb > 10.0 else 0.0010

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

                    # True Intraday High/Low barrier touch detection (Zero-Bias Conservative Rule)
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
                        # Conservative assignment on high volatility bar (zero-bias risk rule)
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

            # Pure exclusive probability for this specific condition
            p_bull = n_pos / n_tot if n_tot > 0 else 0.50
            p_bear = 1.0 - p_bull

            # Pure exclusive expected returns for this specific condition
            e_max = float(np.mean(pos_returns)) if n_pos > 0 else target_pct
            e_min = float(np.mean(neg_returns)) if n_neg > 0 else -target_pct

            # Pure exclusive condition FTT medians
            e_days = float(np.median(days_hits)) if len(days_hits) > 0 else float(np.median(days_all)) if len(days_all) > 0 else 15.0
            ftt_bull_days = float(np.median(pos_days)) if len(pos_days) > 0 else e_days
            ftt_bear_days = float(np.median(neg_days)) if len(neg_days) > 0 else e_days

            ev_net = (p_bull * e_max + p_bear * e_min)
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
                "rr_asymmetry": round(float(rr_asymmetry), 4)
            }
            evs[lbl] = ev_net

        # Regime classification based on multi-horizon EV profile
        ev25, ev50, ev75 = evs["zz25"], evs["zz50"], evs["zz75"]
        if ev25 > 0 and ev50 < 0 and ev75 < 0:
            regime = "TACTICAL_BOUNCE_ONLY"
            guidance = "STK_BUY_DIP_TACTICAL_ONLY_STRICT_STOP"
        elif ev25 > 0 and ev50 > 0 and ev75 > 0:
            regime = "FULL_STRUCTURAL_BULL"
            guidance = "STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION"
        elif ev25 < 0 and ev50 < 0 and ev75 < 0:
            regime = "FULL_STRUCTURAL_BEAR"
            guidance = "STK_BLOCK_CRISIS"
        elif ev25 < 0 and ev75 > 0:
            regime = "TACTICAL_PULLBACK"
            guidance = "STK_BUY_DIP_TACTICAL"
        else:
            regime = "TRANSITIONAL"
            guidance = "STK_HOLD_STABLE"

        state_doc["divergence_regime"] = regime
        state_doc["operational_guidance"] = guidance
        final_states[state_k] = state_doc

    return final_states


def main():
    logger.info("Cargando historia de SV5_TURBULENCE y SPY desde Neon Vault (market.ohlcv_bars)...")
    store = TimescaleDataStore()
    conn = store._conn()
    try:
        df_bars = pd.read_sql("""
            SELECT time::date as date, ticker, open, high, low, close
            FROM market.ohlcv_bars
            WHERE ticker IN ('SPY', 'SV5_TURBULENCE')
              AND timeframe = '1d'
            ORDER BY time, ticker
        """, conn)
    finally:
        store._put(conn)

    pivot_c = df_bars.pivot(index='date', columns='ticker', values='close').dropna()
    pivot_h = df_bars.pivot(index='date', columns='ticker', values='high').dropna()
    pivot_l = df_bars.pivot(index='date', columns='ticker', values='low').dropna()

    common = pivot_c.index
    turb = pivot_c['SV5_TURBULENCE'].loc[common]
    spy_c = pivot_c['SPY'].loc[common]
    spy_h = pivot_h['SPY'].loc[common]
    spy_l = pivot_l['SPY'].loc[common]

    start_date = common.min()
    end_date = common.max()
    n_days = len(common)
    logger.info(f"Población de entrenamiento SV5_TURBULENCE: {start_date} a {end_date} ({n_days} días hábiles / {n_days/252:.2f} años)")

    # Compute 7-scale percentiles for L0 (SV5_TURBULENCE Bins) and L1 (3-Day Fast Velocity Vectors)
    turb_edges = [float(x) for x in turb.quantile(PERCENTILES_7)]
    turb_d3 = turb.diff(3)
    vel_edges = [float(x) for x in turb_d3.dropna().quantile(PERCENTILES_7)]

    logger.info(f"Cortes SV5_TURBULENCE Level (L0): {turb_edges}")
    logger.info(f"Cortes SV5_TURBULENCE Velocity 3-Day (L1): {vel_edges}")

    df_aligned = pd.DataFrame({
        'close': spy_c,
        'high': spy_h,
        'low': spy_l,
        'turbulence': turb,
        'turbulence_prev': turb.shift(1),
        'turbulence_bin': turb.apply(lambda v: classify_bin(v, turb_edges)),
        'turbulence_speed': turb_d3.apply(lambda v: classify_speed(v, vel_edges))
    }).dropna()

    df_aligned['state_key'] = df_aligned['turbulence_bin'] + "__" + df_aligned['turbulence_speed']

    # Compute pure SV5_TURBULENCE 3-day volatility statistics using Intraday High/Low FTT
    pure_states = calculate_3d_sv5_turbulence_stats(df_aligned)

    # Ensure all 49 permutations are represented
    for l0 in LABELS_L0:
        for l1 in LABELS_L1:
            k = f"{l0}__{l1}"
            if k not in pure_states:
                logger.warning(f"Unpopulated state key in training data: {k}. Inserting zero-sample default.")
                pure_states[k] = {
                    "n": 0,
                    "turbulence_t0_stats": {"min": 0.0, "max": 0.0, "mean": 0.0, "std": 0.0},
                    "turbulence_t_minus_1_stats": {"min": 0.0, "max": 0.0, "mean": 0.0},
                    "zz25": {"n_pos": 0, "n_neg": 0, "p_bull": 0.5, "p_bear": 0.5, "e_ret_max": 0.025, "e_ret_min": -0.025, "ev_net": 0.0, "e_days": 15.0, "ftt_bull_days": 15.0, "ftt_bear_days": 15.0, "ev_per_day": 0.0, "rr_asymmetry": 1.0},
                    "zz50": {"n_pos": 0, "n_neg": 0, "p_bull": 0.5, "p_bear": 0.5, "e_ret_max": 0.05, "e_ret_min": -0.05, "ev_net": 0.0, "e_days": 30.0, "ftt_bull_days": 30.0, "ftt_bear_days": 30.0, "ev_per_day": 0.0, "rr_asymmetry": 1.0},
                    "zz75": {"n_pos": 0, "n_neg": 0, "p_bull": 0.5, "p_bear": 0.5, "e_ret_max": 0.075, "e_ret_min": -0.075, "ev_net": 0.0, "e_days": 45.0, "ftt_bull_days": 45.0, "ftt_bear_days": 45.0, "ev_per_day": 0.0, "rr_asymmetry": 1.0},
                    "divergence_regime": "TRANSITIONAL",
                    "operational_guidance": "STK_HOLD_STABLE"
                }

    # Final document structure conforming to Rule 21 Standard JSON Fact Store Metadata Specification
    fact_store = {
        "_documentation": {
            "model_purpose": "Institutional Volume Turbulence (SV5_TURBULENCE - std(Delta_SV5TW, 10d)) 3-Day Fast Kinematic Velocity Matrix (Full Vault Population)",
            "return_formula": "R_net = (P_ftt / P_t) - 1.0 - friction (25bps in ppanic SV5_TURBULENCE > 10.0, 10bps standard)",
            "velocity_lookback_window": "3 trading days (72h fast response)",
            "data_sources": {
                "bars": "market.ohlcv_bars",
                "start_date": str(start_date),
                "end_date": str(end_date),
                "sample_size_days": int(n_days),
                "years_covered": round(float(n_days / 252.0), 2)
            },
            "state_hierarchy": {
                "L0": "SV5_TURBULENCE_Granular_Band_Percentiles_7",
                "L1": "SV5_TURBULENCE_3Day_Fast_Velocity_Percentiles_7"
            },
            "dimension_thresholds_definition": {
                "turbulence_percentiles": PERCENTILES_7,
                "turbulence_edges": turb_edges,
                "turbulence_speed_percentiles": PERCENTILES_7,
                "turbulence_speed_edges": vel_edges,
                "turbulence_labels_l0": LABELS_L0,
                "turbulence_labels_l1": LABELS_L1
            },
            "field_glossary": {
                "n": "Sample size in this exact volume turbulence stereotype",
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
                "operational_guidance": "Sizing code from Universal Institutional Taxonomy"
            },
            "signal_interpretation_policy": "Pure domain adapters (MarketHealthIntelligence, QualityEntryGate, SpeculativeEntryHub) interpret probabilities dynamically.",
            "reproducibility_context": {
                "calibration_timestamp": "2026-07-31T00:00:00Z",
                "calibrated_under_commit": "HEAD"
            }
        },
        "states": pure_states
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(fact_store, f, indent=2, ensure_ascii=False)

    logger.info(f"Fact Store SV5_TURBULENCE 3-Day Fast Velocity guardado exitosamente en {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
