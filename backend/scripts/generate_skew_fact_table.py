#!/usr/bin/env python3
"""
Generate Empirical CBOE SKEW Index Fact Store Table (Full Vault Population 1990–2026)
===================================================================================
Calculates exact empirical asymmetric percentiles for SKEW index (L0 - 7 Bins)
and SKEW 3-day Fast Kinematic Velocity (L1 - 7 Vectors) across 33+ years of
aligned market history in Neon Vault (1990–2026, 8,417 trading sessions).

L0 Labels:
  - DEEP_COMPLACENCY (SKEW <= P05)
  - COMPLACENCY (P05 < SKEW <= P15)
  - NORMAL_LOW (P15 < SKEW <= P35)
  - NORMAL_HIGH (P35 < SKEW <= P65)
  - ELEVATED (P65 < SKEW <= P85)
  - HIGH_TAIL_RISK (P85 < SKEW <= P95)
  - BLACK_SWAN_PARANOIA (SKEW > P95)

L1 Labels:
  - EXTREME_RELAXATION_3D (Delta_3d <= P05)
  - FAST_RELAXATION_3D (P05 < Delta_3d <= P15)
  - DECELERATING_3D (P15 < Delta_3d <= P35)
  - STABLE_3D (P35 < Delta_3d <= P65)
  - RISING_HEDGING_3D (P65 < Delta_3d <= P85)
  - FAST_SPIKE_3D (P85 < Delta_3d <= P95)
  - EXTREME_PANIC_SPIKE_3D (Delta_3d > P95)

Outputs a Rule 21 compliant JSON Fact Store matching the exact schema of vix_fact_store.json.

Usage:
    python -m backend.scripts.generate_skew_fact_table
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
logger = logging.getLogger("GenerateSKEWFactTable")

OUTPUT_PATH = root_dir / "backend/modules/entry_decision/domain/rules/skew_fact_store.json"

ZIGZAG_LEVELS = [0.025, 0.05, 0.075]
ZIGZAG_LABEL = {0.025: "zz25", 0.05: "zz50", 0.075: "zz75"}
MAX_HORIZONS = {0.025: 30, 0.05: 60, 0.075: 90}

PERCENTILES_7 = [0.05, 0.15, 0.35, 0.65, 0.85, 0.95]
LABELS_L0 = [
    "DEEP_COMPLACENCY",
    "COMPLACENCY",
    "NORMAL_LOW",
    "NORMAL_HIGH",
    "ELEVATED",
    "HIGH_TAIL_RISK",
    "BLACK_SWAN_PARANOIA",
]
LABELS_L1 = [
    "EXTREME_RELAXATION_3D",
    "FAST_RELAXATION_3D",
    "DECELERATING_3D",
    "STABLE_3D",
    "RISING_HEDGING_3D",
    "FAST_SPIKE_3D",
    "EXTREME_PANIC_SPIKE_3D",
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


def calculate_3d_skew_stats(df_aligned: pd.DataFrame):
    prices_c = df_aligned["close"].values
    prices_h = df_aligned["high"].values
    prices_l = df_aligned["low"].values
    skew_vals = df_aligned["skew"].values
    skew_prev = df_aligned["skew_prev"].values
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
        skew_t0_vals = skew_vals[idx_list]
        skew_prev_vals = [skew_prev[i] for i in idx_list if not pd.isna(skew_prev[i])]

        state_doc = {
            "n": int(n_state),
            "skew_t0_stats": {
                "min": round(float(np.min(skew_t0_vals)), 2),
                "max": round(float(np.max(skew_t0_vals)), 2),
                "mean": round(float(np.mean(skew_t0_vals)), 2),
                "std": round(float(np.std(skew_t0_vals)), 2) if n_state > 1 else 0.0,
            },
            "skew_t_minus_1_stats": {
                "min": round(float(np.min(skew_prev_vals)), 2) if skew_prev_vals else 0.0,
                "max": round(float(np.max(skew_prev_vals)), 2) if skew_prev_vals else 0.0,
                "mean": round(float(np.mean(skew_prev_vals)), 2) if skew_prev_vals else 0.0,
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
                friction = 0.0010

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
                    days_all.append(max_days)

            n_pos = len(pos_returns)
            n_neg = len(neg_returns)
            n_tot = n_pos + n_neg

            if n_tot > 0:
                p_bull = float(n_pos / n_tot)
                p_bear = float(n_neg / n_tot)
                e_max = float(np.mean(pos_returns)) if n_pos > 0 else target_pct
                e_min = float(np.mean(neg_returns)) if n_neg > 0 else -target_pct
                e_days = float(np.median(days_hits)) if len(days_hits) > 0 else float(np.median(days_all)) if len(days_all) > 0 else 15.0
                ftt_bull_days = float(np.median(pos_days)) if len(pos_days) > 0 else e_days
                ftt_bear_days = float(np.median(neg_days)) if len(neg_days) > 0 else e_days

                ev_net = (p_bull * e_max + p_bear * e_min)
                ev_per_day = ev_net / max(e_days, 1.0)
                abs_min = abs(e_min) if abs(e_min) > 1e-6 else 1e-6
                rr_asym = e_max / abs_min
            else:
                p_bull = 0.50
                p_bear = 0.50
                e_max = target_pct
                e_min = -target_pct
                e_days = float(max_days)
                ftt_bull_days = float(max_days)
                ftt_bear_days = float(max_days)
                ev_net = 0.0
                ev_per_day = 0.0
                rr_asym = 1.0

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
                "rr_asymmetry": round(float(rr_asym), 4),
            }
            evs[lbl] = ev_net

        # Regime classification (Divergence Memory between horizons)
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
    logger.info("Initializing TimescaleDataStore...")
    store = TimescaleDataStore()
    conn = store._conn()

    try:
        # Ensure ticker metadata
        store.upsert_ticker_metadata(
            ticker="SKEW",
            sector="Volatility",
            industry="INDICATOR",
            market_cap_bucket=None,
        )

        logger.info("Loading SKEW index and SPY price history from Vault...")
        q_skew = """
            SELECT time AS timestamp, close AS skew
            FROM market.ohlcv_bars
            WHERE ticker = 'SKEW' AND timeframe = '1d' AND close > 0
            ORDER BY time
        """
        q_spy = """
            SELECT time AS timestamp, open, high, low, close, volume
            FROM market.ohlcv_bars
            WHERE ticker = 'SPY' AND timeframe = '1d' AND close > 0
            ORDER BY time
        """

        df_skew = pd.read_sql(q_skew, conn)
        df_spy = pd.read_sql(q_spy, conn)

        df_skew["timestamp"] = pd.to_datetime(df_skew["timestamp"], utc=True).dt.floor("D")
        df_spy["timestamp"] = pd.to_datetime(df_spy["timestamp"], utc=True).dt.floor("D")

        df = pd.merge(df_spy, df_skew, on="timestamp", how="inner").sort_values("timestamp").reset_index(drop=True)
        logger.info(f"Aligned SPY-SKEW dataset: {len(df)} sessions ({df['timestamp'].min().strftime('%Y-%m-%d')} to {df['timestamp'].max().strftime('%Y-%m-%d')})")

        # 3-day kinematic velocity
        df["skew_delta_3d"] = df["skew"].diff(3)
        df["skew_prev"] = df["skew"].shift(1)

        valid_skew = df["skew"].dropna().values
        valid_delta = df["skew_delta_3d"].dropna().values

        edges_l0 = [float(x) for x in np.percentile(valid_skew, [p * 100 for p in PERCENTILES_7])]
        edges_l1 = [float(x) for x in np.percentile(valid_delta, [p * 100 for p in PERCENTILES_7])]

        logger.info(f"L0 SKEW Level Edges: {edges_l0}")
        logger.info(f"L1 3-Day Velocity Edges: {edges_l1}")

        df["l0_bin"] = df["skew"].apply(lambda v: classify_bin(v, edges_l0))
        df["l1_bin"] = df["skew_delta_3d"].apply(lambda v: classify_speed(v, edges_l1))
        df["state_key"] = df["l0_bin"] + "__" + df["l1_bin"]

        logger.info("Computing Rule 21 compliant SKEW Fact Store...")
        states_dict = calculate_3d_skew_stats(df)

        # Build Rule 21 compliant JSON structure
        fact_store = {
            "_documentation": {
                "model_purpose": "Empirical CBOE SKEW Index Fact Store Table mapping perceived tail risk / black swan put demand levels (L0) and 3-day kinematic velocity (L1) to SPY forward pivot distributions.",
                "return_formula": "Barrier touch return minus local friction (10 bps) over 33+ years of aligned Vault OHLCV history.",
                "state_hierarchy": "L0: SKEW Level (7 Bins) | L1: 3-day Velocity Delta_3d (7 Vectors) -> L2: State Key (L0__L1)",
                "dimension_thresholds_definition": {
                    "skew_edges": edges_l0,
                    "skew_speed_edges": edges_l1,
                },
                "field_glossary": {
                    "n": "Sample size of trading sessions in this state.",
                    "divergence_regime": "Multi-scale horizon divergence regime (FULL_STRUCTURAL_BULL, TACTICAL_PULLBACK, FULL_STRUCTURAL_BEAR, TACTICAL_BOUNCE_ONLY, TRANSITIONAL).",
                    "operational_guidance": "Universal Institutional Action Taxonomy directive code.",
                    "zz25": "Scale-specific metrics at 2.5% ZigZag (p_bull, p_bear, e_ret_max, e_ret_min, ev_net, e_days, ftt_bull_days, ftt_bear_days, ev_per_day, rr_asymmetry).",
                    "zz50": "Scale-specific metrics at 5.0% ZigZag.",
                    "zz75": "Scale-specific metrics at 7.5% ZigZag.",
                },
                "signal_interpretation_policy": "Pure domain lookup. Emits StateSnapshot with RegimeStatePort persistence under key 'skew:entry_decision:MARKET'.",
            },
            "percentiles_l0": dict(zip(LABELS_L0, edges_l0 + [float("inf")])),
            "percentiles_l1": dict(zip(LABELS_L1, edges_l1 + [float("inf")])),
            "states": states_dict,
        }

        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(fact_store, f, indent=2)

        logger.info(f"✅ SKEW Fact Store successfully saved to {OUTPUT_PATH}")
        logger.info(f"   Total states trained: {len(states_dict)}")

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    main()
