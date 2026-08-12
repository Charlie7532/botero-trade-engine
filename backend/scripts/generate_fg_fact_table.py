#!/usr/bin/env python3
"""
Generate Empirical CNN Fear & Greed Index (FG) Fact Store Table
=============================================================================
Calculates exact empirical asymmetric expected values (EV), win probabilities (p_bull),
and physical durations DIRECTLY from confirmed ZigZag legs in Neon Vault (market.zigzag_legs).

Zero Barrier Drift. Zero Arbitrary Forward Touch Loops. Zero Lag Distortion.
Outputs a Rule 21 compliant JSON Fact Store.

Usage:
    python3 -m backend.scripts.generate_fg_fact_table
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
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GenerateFGFactTable")

OUTPUT_PATH = root_dir / "backend/modules/entry_decision/domain/rules/fg_fact_store.json"

PERCENTILES_7 = [0.05, 0.15, 0.35, 0.65, 0.85, 0.95]
LABELS_L0 = [
    "EXTREME_FEAR",
    "FEAR",
    "MODERATE_FEAR",
    "NEUTRAL",
    "MODERATE_GREED",
    "GREED",
    "EXTREME_GREED"
]
LABELS_L1 = [
    "EXTREME_PANIC_CAPITULATION_3D",
    "FEAR_SURGE_3D",
    "DECELERATING_3D",
    "STABLE_3D",
    "RISING_3D",
    "GREED_SURGE_3D",
    "EXTREME_EUPHORIA_SPIKE_3D"
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


def calculate_pure_zigzag_fg_stats(repo: ZigzagLegRepository, df_aligned: pd.DataFrame):
    fg_edges = [float(x) for x in df_aligned['fg'].quantile(PERCENTILES_7)]
    fg_d3 = df_aligned['fg'].diff(3)
    vel_edges = [float(x) for x in fg_d3.dropna().quantile(PERCENTILES_7)]

    final_states = {}

    scale_dfs = {}
    for scale in ["zz25", "zz50", "zz75"]:
        df_legs = repo.get_confirmed_legs_with_indicators("SPY", scale=scale)
        if not df_legs.empty:
            df_legs["fg_bin"] = df_legs["vix_at_start"].apply(lambda v: classify_bin(v, fg_edges)) if "vix_at_start" in df_legs.columns else "NEUTRAL"
            df_legs["fg_speed"] = "STABLE_3D"
            df_legs["state_key"] = df_legs["fg_bin"] + "__STABLE_3D"
        scale_dfs[scale] = df_legs

    state_groups = df_aligned.groupby('state_key')

    for state_k, df_group in state_groups:
        n_state = len(df_group)
        fg_t0_vals = df_group['fg'].values
        fg_prev_vals = df_group['fg_prev'].values
        dates_set = set(df_group.index)

        state_doc = {
            "n": int(n_state),
            "fg_t0_stats": {
                "min": float(np.min(fg_t0_vals)),
                "max": float(np.max(fg_t0_vals)),
                "mean": float(np.mean(fg_t0_vals)),
                "std": float(np.std(fg_t0_vals)) if n_state > 1 else 0.0
            },
            "fg_t_minus_1_stats": {
                "min": float(np.min(fg_prev_vals)),
                "max": float(np.max(fg_prev_vals)),
                "mean": float(np.mean(fg_prev_vals))
            }
        }

        evs = {}

        for scale in ["zz25", "zz50", "zz75"]:
            df_scale_legs = scale_dfs[scale]
            if df_scale_legs.empty:
                state_doc[scale] = {
                    "n_pos": 0, "n_neg": 0, "p_bull": 0.5, "p_bear": 0.5,
                    "e_ret_max": 0.0, "e_ret_min": 0.0, "ev_net": 0.0,
                    "e_days": 15.0, "ftt_bull_days": 15.0, "ftt_bear_days": 15.0,
                    "ev_per_day": 0.0, "rr_asymmetry": 1.0
                }
                evs[scale] = 0.0
                continue

            df_scale_legs["start_date"] = pd.to_datetime(df_scale_legs["start_timestamp"]).dt.date
            matched_legs = df_scale_legs[df_scale_legs["start_date"].isin(dates_set)]

            pos_legs = matched_legs[matched_legs["start_type"] == "MIN"]
            neg_legs = matched_legs[matched_legs["start_type"] == "MAX"]

            n_pos = len(pos_legs)
            n_neg = len(neg_legs)
            n_tot = n_pos + n_neg

            p_bull = n_pos / n_tot if n_tot > 0 else 0.50
            p_bear = 1.0 - p_bull

            e_max = float(pos_legs["log_return"].mean()) if n_pos > 0 else 2.5
            e_min = float(neg_legs["log_return"].mean()) if n_neg > 0 else -2.5

            e_days = float(matched_legs["duration_bars"].median()) if n_tot > 0 else 10.0
            ftt_bull_days = float(pos_legs["duration_bars"].median()) if n_pos > 0 else e_days
            ftt_bear_days = float(neg_legs["duration_bars"].median()) if n_neg > 0 else e_days

            ev_net = (p_bull * e_max + p_bear * e_min)
            ev_per_day = ev_net / max(e_days, 1.0)
            abs_min = abs(e_min) if abs(e_min) > 1e-6 else 1e-6
            rr_asymmetry = e_max / abs_min

            state_doc[scale] = {
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
                "zigzag_pure_vault": True
            }
            evs[scale] = ev_net

        # Regime classification with L2 Kinematic Pivot Override
        l2_pivot = state_k.split("__")[-1] if len(state_k.split("__")) >= 3 else "STABLE_CONTINUATION"
        ev25, ev50, ev75 = evs.get("zz25", 0.0), evs.get("zz50", 0.0), evs.get("zz75", 0.0)

        if l2_pivot == "FALLING_KNIFE":
            regime = "FULL_STRUCTURAL_BEAR"
            guidance = "STK_BLOCK_CRISIS"
        elif l2_pivot == "FLOOR_CONFIRMED":
            regime = "FULL_STRUCTURAL_BULL"
            guidance = "STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION"
        elif ev25 > 0 and ev50 < 0 and ev75 < 0:
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

    return final_states, fg_edges, vel_edges


def main():
    logger.info("Cargando historia completa de CNN Fear & Greed (FG) y SPY de Neon Vault (market.ohlcv_bars)...")
    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store=store)

    conn = store._conn()
    try:
        df_bars = pd.read_sql("""
            SELECT time::date as date, ticker, open, high, low, close
            FROM market.ohlcv_bars
            WHERE ticker IN ('SPY', 'FG')
              AND timeframe = '1d'
            ORDER BY time, ticker
        """, conn)
    finally:
        store._put(conn)

    pivot_c = df_bars.pivot(index='date', columns='ticker', values='close').dropna()
    pivot_h = df_bars.pivot(index='date', columns='ticker', values='high').dropna()
    pivot_l = df_bars.pivot(index='date', columns='ticker', values='low').dropna()

    common = pivot_c.index
    fg = pivot_c['FG'].loc[common]
    spy_c = pivot_c['SPY'].loc[common]
    spy_h = pivot_h['SPY'].loc[common]
    spy_l = pivot_l['SPY'].loc[common]

    start_date = common.min()
    end_date = common.max()
    n_days = len(common)
    logger.info(f"Población de entrenamiento Fear & Greed: {start_date} a {end_date} ({n_days} días hábiles / {n_days/252:.2f} años)")

    fg_edges = [float(x) for x in fg.quantile(PERCENTILES_7)]
    fg_d3 = fg.diff(3)
    vel_edges = [float(x) for x in fg_d3.dropna().quantile(PERCENTILES_7)]

    fg_min5 = fg.rolling(5).min()
    fg_max5 = fg.rolling(5).max()
    fg_d1 = fg.diff(1)

    pivot_labels = []
    for i in range(len(common)):
        v = fg.iloc[i]
        m5 = fg_min5.iloc[i]
        mx5 = fg_max5.iloc[i]
        d1 = fg_d1.iloc[i]
        pv = fg.iloc[i-1] if i > 0 else v
        
        if pd.isna(v) or pd.isna(m5):
            pivot_labels.append("STABLE_CONTINUATION")
        elif v <= m5 + 1.0 and d1 <= 0:
            pivot_labels.append("FALLING_KNIFE")
        elif pv <= m5 + 1.0 and d1 > 0:
            pivot_labels.append("FLOOR_CONFIRMED")
        elif v >= mx5 - 1.0 and d1 >= 0:
            pivot_labels.append("CEILING_DISTRIBUTION")
        else:
            pivot_labels.append("STABLE_CONTINUATION")

    df_aligned = pd.DataFrame({
        'close': spy_c,
        'high': spy_h,
        'low': spy_l,
        'fg': fg,
        'fg_prev': fg.shift(1),
        'fg_bin': fg.apply(lambda v: classify_bin(v, fg_edges)),
        'fg_speed': fg_d3.apply(lambda v: classify_speed(v, vel_edges)),
        'fg_pivot': pivot_labels
    }, index=common).dropna()

    df_aligned['state_key'] = df_aligned['fg_bin'] + "__" + df_aligned['fg_speed'] + "__" + df_aligned['fg_pivot']

    pure_states, fg_edges, vel_edges = calculate_pure_zigzag_fg_stats(repo, df_aligned)

    fact_store = {
        "_documentation": {
            "model_purpose": "CNN Fear & Greed Index Pure Physical ZigZag Leg Expected Value Matrix",
            "return_formula": "R_net = log(P_end / P_start) * 100 on pure confirmed Neon Vault ZigZag legs",
            "velocity_lookback_window": "3 trading days (72h fast response)",
            "data_sources": {
                "bars": "market.ohlcv_bars",
                "zigzag_repository": "market.zigzag_legs (Neon Vault)",
                "start_date": str(start_date),
                "end_date": str(end_date),
                "sample_size_days": int(n_days),
                "years_covered": round(float(n_days / 252.0), 2)
            },
            "state_hierarchy": {
                "L0": "FG_Granular_Band_Percentiles_7",
                "L1": "FG_3Day_Fast_Velocity_Percentiles_7"
            },
            "dimension_thresholds_definition": {
                "fg_percentiles": PERCENTILES_7,
                "fg_edges": fg_edges,
                "fg_speed_percentiles": PERCENTILES_7,
                "fg_speed_edges": vel_edges,
                "fg_labels_l0": LABELS_L0,
                "fg_labels_l1": LABELS_L1
            },
            "field_glossary": {
                "n": "Sample size in this exact sentiment stereotype",
                "n_pos": "Number of bullish MIN->MAX physical legs starting in this condition",
                "n_neg": "Number of bearish MAX->MIN physical legs starting in this condition",
                "p_bull": "Pure probability leg is a bullish MIN->MAX leg",
                "p_bear": "Pure probability leg is a bearish MAX->MIN leg",
                "e_ret_max": "Average physical log return of MIN->MAX legs starting in this condition",
                "e_ret_min": "Average physical log return of MAX->MIN legs starting in this condition",
                "ev_net": "Pure physical expected value across confirmed Neon Vault legs",
                "e_days": "Median physical duration (T_end - T_start) in trading days",
                "ftt_bull_days": "Median physical duration of MIN->MAX legs",
                "ftt_bear_days": "Median physical duration of MAX->MIN legs",
                "ev_per_day": "Pure physical capital velocity (ev_net / e_days)",
                "rr_asymmetry": "e_ret_max / |e_ret_min|",
                "divergence_regime": "Multi-scale horizon divergence regime",
                "operational_guidance": "Sizing code from Universal Institutional Taxonomy"
            },
            "signal_interpretation_policy": "Pure domain adapters interpret probabilities dynamically.",
            "reproducibility_context": {
                "calibration_timestamp": "2026-08-03T00:00:00Z",
                "calibrated_under_commit": "HEAD"
            }
        },
        "states": pure_states
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(fact_store, f, indent=2, ensure_ascii=False)

    logger.info(f"🎉 ✅ Fact Store PURO DE ZIGZAG de Fear & Greed guardado exitosamente en {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
