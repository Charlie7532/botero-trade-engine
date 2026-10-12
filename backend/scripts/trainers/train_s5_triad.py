#!/usr/bin/env python3
"""
Train S5 Triad Table v3.1 (Price Breadth + Kinematics + Time Store + Timing)
=============================================================================
Generates two JSON artifacts consumed by the Quality Entry Gate (Gate 1.5b)
and pure-domain adapter triad_lookup.py:

  1. s5_triad_table.json       — Multiscale conditional probability and kinematic fact store (391 cells total: 238 R4, 123 R3, 25 R2, 5 R1)
  2. s5_relative_modifier.json  — Sector vs SPY relative breadth modifier (5 bins)

═══════════════════════════════════════════════════════════════════════════════
FOUR ATOMIC BLOCKS PER CELL (v3.1 SPECIFICATION):
═══════════════════════════════════════════════════════════════════════════════

  1. LEGACY BLOCK (100% Backwards Compatible):
     - n, P_bot_2_5, P_bot_5_0, P_bot_7_5, P_top_2_5, P_top_5_0, P_top_7_5,
       lift_bot_5_0, lift_top_5_0, net_bias.
  2. TEMPORAL BLOCK (Time Store & Sojourn Renewal):
     - n_episodes, pct_tiempo, duration_mean, duration_max, fatigue_buckets
       (fresh, persist, mature, exhaustion with empirical n, pct, and ev_net).
  3. TIMING GEOMETRY BLOCK (Chronos / METAR Timing):
     - pct_en_rango (within ±2 bars of turn), pct_fuera, delta_mediana_barras,
       slots_canonicos (t-2, t-1 precursor, t=0 simultaneous, entre).
  4. KINEMATIC LEGS BLOCK (market.zigzag_legs at zz25, zz50, zz75):
     - p_bull, p_bear (Laplace Bayesian Shrinkage M=10), e_ret_max, e_ret_min,
       ev_net, rr_asymmetry, e_days, ev_per_day, timeout_rate, confidence_tier.
  5. TRIPARTITE RESOLUTION HIERARCHY:
     - global: Aggregated macro observations (~83.170 bars across 13 entities).
     - tiers: Defensive, Mixed, Cyclical, High-Beta, SPY (if N >= 20).
     - sectors: Individual ETFs XLK, XLF, etc. (if N >= 20).

═══════════════════════════════════════════════════════════════════════════════
DATA INTEGRITY & POST-AUDIT SAFEGUARDS:
═══════════════════════════════════════════════════════════════════════════════
  - Sourced directly from market.zigzag_legs in Neon Vault.
  - Zero-price leg filter: WHERE start_price > 0 AND end_price > 0.
  - Canonical 13 entities: SPY, QQQ + 11 SPDR Sector ETFs.
  - Canonical bin edges: TH [28.6, 55.0, 82.7, 93.3], FI [20.7, 46.7, 76.6, 90.0], TW [16.7, 42.3, 74.7, 89.6].
"""
import sys
import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS, SECTOR_BREADTH_TICKERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TrainS5Triad")

# ── Canonical Configuration ──
BIN_LABELS = ["<<", "<", "~", ">", ">>"]
BIN_PERCENTILES = [0.10, 0.30, 0.70, 0.90]

# Canonical bin edges (SSOT)
CANONICAL_BIN_EDGES = {
    "TH": [28.6, 55.0, 82.7, 93.3],
    "FI": [20.7, 46.7, 76.6, 90.0],
    "TW": [16.7, 42.3, 74.7, 89.6],
}

ZZ_THRESHOLDS = [2.5, 5.0, 7.5]
SCALE_MAP = {2.5: "zz25", 5.0: "zz50", 7.5: "zz75"}
NEAR_WINDOW = 3
MIN_N_L1 = 20
DEFAULT_FRICTION_BPS = 0.0010  # 10 bps round-trip friction

TIERS = {
    "Defensive": ["XLP", "XLV", "XLU", "XLRE", "XLB"],
    "Mixed": ["XLE", "XLF", "XLC"],
    "Cyclical": ["XLK", "XLY", "XLI"],
    "High-Beta": ["QQQ"],
}
ETF_TO_TIER = {}
for tier_name, etfs in TIERS.items():
    for etf in etfs:
        ETF_TO_TIER[etf] = tier_name

SPY_S5 = {"structural": "S5TH", "intermediate": "S5FI", "tactical": "S5TW"}


def classify_bin(val: float, edges: list[float]) -> str:
    """Classify a scalar into one of 5 bins based on cut edges."""
    for i, edge in enumerate(edges):
        if val < edge:
            return BIN_LABELS[i]
    return BIN_LABELS[-1]


def load_all_data(store: TimescaleDataStore):
    """Load confirmed legs from market.zigzag_legs and price/breadth bars from market.ohlcv_bars."""
    conn = store.engine.connect()
    try:
        # 1. Confirmed legs
        logger.info("1. Loading confirmed legs from market.zigzag_legs...")
        q_legs = """
        SELECT ticker, scale, start_timestamp, start_price, start_type,
               end_timestamp, end_price, end_type, prev_leg_return, prev_leg_duration
        FROM market.zigzag_legs
        WHERE ticker IN ('SPY','QQQ','XLK','XLV','XLF','XLY','XLP','XLI','XLE','XLU','XLRE','XLB','XLC')
          AND status = 'CONFIRMED'
          AND start_price > 0 AND end_price > 0
        ORDER BY ticker, scale, start_timestamp;
        """
        legs_df = pd.read_sql(q_legs, conn)
        logger.info(f"Loaded {len(legs_df)} confirmed legs across 13 tickers.")

        pivots_by_ticker_scale = defaultdict(dict)
        for (ticker, scale), grp in legs_df.groupby(["ticker", "scale"]):
            grp = grp.sort_values("start_timestamp")
            pivots_list = [{
                "timestamp": grp["start_timestamp"].iloc[0],
                "type": grp["start_type"].iloc[0],
                "price": float(grp["start_price"].iloc[0]),
            }]
            for _, row in grp.iterrows():
                pivots_list.append({
                    "timestamp": row["end_timestamp"],
                    "type": row["end_type"],
                    "price": float(row["end_price"]),
                })
            pdf = pd.DataFrame(pivots_list).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
            pivots_by_ticker_scale[ticker][scale] = pdf

        # 2. Price and breadth bars
        logger.info("2. Loading price and breadth bars from market.ohlcv_bars...")
        entities = {}

        # SPY
        spy_th = store.load_bars(SPY_S5["structural"], "1d")["close"].astype(float).rename("th")
        spy_fi = store.load_bars(SPY_S5["intermediate"], "1d")["close"].astype(float).rename("fi")
        spy_tw = store.load_bars(SPY_S5["tactical"], "1d")["close"].astype(float).rename("tw")
        spy_price = store.load_bars("SPY", "1d")["close"].astype(float).rename("etf_close")
        spy_merged = pd.concat([spy_th, spy_fi, spy_tw, spy_price], axis=1, join="inner").dropna()
        entities["SPY"] = spy_merged

        # Sectors + QQQ
        sector_dict = dict(SECTOR_ETFS)
        sector_dict["QQQ"] = "Nasdaq 100"

        for etf, sname in sector_dict.items():
            tickers = SECTOR_BREADTH_TICKERS.get(etf)
            if not tickers:
                continue
            th = store.load_bars(tickers["structural"], "1d")["close"].astype(float).rename("th")
            fi = store.load_bars(tickers["intermediate"], "1d")["close"].astype(float).rename("fi")
            tw = store.load_bars(tickers["tactical"], "1d")["close"].astype(float).rename("tw")
            etf_price = store.load_bars(etf, "1d")["close"].astype(float).rename("etf_close")
            merged = pd.concat([th, fi, tw, etf_price], axis=1, join="inner").dropna()
            if len(merged) < 200:
                continue
            entities[etf] = merged

        logger.info(f"Loaded bars for {len(entities)} entities successfully.")
        return pivots_by_ticker_scale, entities
    finally:
        conn.close()


def build_observations_table(pivots_by_ticker_scale: dict, entities: dict, bin_edges: dict) -> pd.DataFrame:
    """Build unified observations dataframe with legacy flags, forward swings, timing, and episodes."""
    logger.info("3. Vectorized feature extraction across all entities...")
    spy_fi_series = entities["SPY"]["fi"]
    all_obs = []

    for etf, merged in entities.items():
        merged = merged.copy()
        merged["tw_diff"] = merged["tw"].diff(1)
        merged = merged.dropna()

        th_bins = merged["th"].apply(lambda v: classify_bin(v, bin_edges["TH"]))
        fi_bins = merged["fi"].apply(lambda v: classify_bin(v, bin_edges["FI"]))
        tw_bins = merged["tw"].apply(lambda v: classify_bin(v, bin_edges["TW"]))
        dir_bins = merged["tw_diff"].apply(lambda v: "+" if v > 0 else "-")
        triad_keys = th_bins + "|" + fi_bins + "|" + tw_bins + "|" + dir_bins
        merged["triad"] = triad_keys

        # Episode grouping (Time Store)
        episode_ids = (merged["triad"] != merged["triad"].shift(1)).cumsum()
        merged["episode_id"] = episode_ids
        day_in_ep = merged.groupby("episode_id").cumcount() + 1

        def get_fatigue_stage(d):
            if d == 1:
                return "fresh"
            elif d == 2:
                return "persist"
            elif d in (3, 4):
                return "mature"
            else:
                return "exhaustion"

        fatigue_stages = day_in_ep.apply(get_fatigue_stage)

        # Relative FI (Sector - SPY)
        if etf != "SPY":
            spy_fi_aligned = spy_fi_series.reindex(merged.index, method="ffill")
            rel_fi = merged["fi"] - spy_fi_aligned
        else:
            rel_fi = pd.Series(0.0, index=merged.index)

        bar_dates = pd.to_datetime(merged.index, utc=True).values
        close_vals = merged["etf_close"].values
        n_bars = len(merged)

        # Process scales vectorized
        scale_data = {}
        for pct in ZZ_THRESHOLDS:
            sc = SCALE_MAP[pct]
            pivots_df = pivots_by_ticker_scale[etf].get(sc)
            if pivots_df is None or pivots_df.empty:
                continue

            p_dates = pd.to_datetime(pivots_df["timestamp"].values, utc=True).values
            p_types = pivots_df["type"].values
            p_prices = pivots_df["price"].values

            idx_right = np.searchsorted(p_dates, bar_dates, side="right")
            idx_right_clip = np.clip(idx_right, 0, len(p_dates) - 1)
            idx_left = np.clip(idx_right - 1, 0, len(p_dates) - 1)

            diff_left = (bar_dates - p_dates[idx_left]) / np.timedelta64(1, "D")
            diff_right = (p_dates[idx_right_clip] - bar_dates) / np.timedelta64(1, "D")

            # Near flags (within 3 days preceding or at turn)
            near_bot = (diff_right <= 3.0) & (p_types[idx_right_clip] == "MIN") & (idx_right < len(p_dates))
            near_bot |= (diff_left == 0.0) & (p_types[idx_left] == "MIN")

            near_top = (diff_right <= 3.0) & (p_types[idx_right_clip] == "MAX") & (idx_right < len(p_dates))
            near_top |= (diff_left == 0.0) & (p_types[idx_left] == "MAX")

            # Forward swing target
            valid_fwd = idx_right < len(p_dates)
            fwd_is_bull = np.where(valid_fwd, p_types[idx_right_clip] == "MAX", True)
            fwd_target_px = np.where(valid_fwd, p_prices[idx_right_clip], close_vals)
            fwd_ret = np.where(valid_fwd, (fwd_target_px / close_vals) - 1.0 - DEFAULT_FRICTION_BPS, 0.0)
            fwd_days = np.where(valid_fwd, np.maximum(diff_right, 1.0), 10.0)

            scale_data[pct] = {
                "near_bot": near_bot,
                "near_top": near_top,
                "fwd_is_bull": fwd_is_bull,
                "fwd_ret": fwd_ret,
                "fwd_days": fwd_days,
            }

        # Timing geometry on zz50 (vectorized)
        p50_df = pivots_by_ticker_scale[etf].get("zz50")
        if p50_df is not None and not p50_df.empty:
            p50_dates = pd.to_datetime(p50_df["timestamp"].values, utc=True).values
            idx_right_50 = np.searchsorted(p50_dates, bar_dates, side="right")
            idx_rc_50 = np.clip(idx_right_50, 0, len(p50_dates) - 1)
            idx_lc_50 = np.clip(idx_right_50 - 1, 0, len(p50_dates) - 1)

            d_left_50 = (bar_dates - p50_dates[idx_lc_50]) / np.timedelta64(1, "D")
            d_right_50 = (p50_dates[idx_rc_50] - bar_dates) / np.timedelta64(1, "D")

            choose_right = d_right_50 < d_left_50
            nearest_idx = np.where(choose_right, idx_rc_50, idx_lc_50)
            signed_delta = (bar_dates - p50_dates[nearest_idx]) / np.timedelta64(1, "D")

            en_rango = np.abs(signed_delta) <= 2.0
            slots = np.where(
                signed_delta == -2.0, "t-2",
                np.where(signed_delta == -1.0, "t-1",
                np.where(signed_delta == 0.0, "t=0", "entre"))
            )
            delta_bars = signed_delta
        else:
            en_rango = np.zeros(n_bars, dtype=bool)
            delta_bars = np.zeros(n_bars, dtype=float)
            slots = np.array(["entre"] * n_bars)

        tier = ETF_TO_TIER.get(etf, "SPY")
        for i in range(n_bars):
            rec = {
                "etf": etf,
                "tier": tier,
                "th_bin": th_bins.iloc[i],
                "fi_bin": fi_bins.iloc[i],
                "tw_bin": tw_bins.iloc[i],
                "dir_bin": dir_bins.iloc[i],
                "triad": triad_keys.iloc[i],
                "rel_fi": float(rel_fi.iloc[i]) if not pd.isna(rel_fi.iloc[i]) else 0.0,
                "episode_id": f"{etf}_{episode_ids.iloc[i]}",
                "fatigue_stage": fatigue_stages.iloc[i],
                "en_rango": bool(en_rango[i]),
                "delta_bars": float(delta_bars[i]),
                "slot": str(slots[i]),
            }
            for pct in ZZ_THRESHOLDS:
                sd = scale_data[pct]
                rec[f"near_bot_{pct}"] = bool(sd["near_bot"][i])
                rec[f"near_top_{pct}"] = bool(sd["near_top"][i])
                rec[f"fwd_bull_{pct}"] = bool(sd["fwd_is_bull"][i])
                rec[f"fwd_ret_{pct}"] = float(sd["fwd_ret"][i])
                rec[f"fwd_days_{pct}"] = float(sd["fwd_days"][i])

            all_obs.append(rec)

    df = pd.DataFrame(all_obs)
    logger.info(f"Total observations collected: {len(df)}")
    return df


def compute_four_blocks(sub_df: pd.DataFrame, total_obs: int, baselines: dict = None) -> dict:
    """Compute the 4 atomic blocks for a given observation subset."""
    n = len(sub_df)
    if n == 0:
        return {}

    # 1. LEGACY BLOCK
    legacy = {"n": n}
    for pct in ZZ_THRESHOLDS:
        k = str(pct).replace(".", "_")
        legacy[f"P_bot_{k}"] = round(float(sub_df[f"near_bot_{pct}"].mean()), 4)
        legacy[f"P_top_{k}"] = round(float(sub_df[f"near_top_{pct}"].mean()), 4)

    if baselines and "global" in baselines:
        base_bot = baselines["global"].get("P_bot_5_0", 0.0742)
        base_top = baselines["global"].get("P_top_5_0", 0.0747)
        cell_bot = legacy["P_bot_5_0"]
        cell_top = legacy["P_top_5_0"]
        legacy["lift_bot_5_0"] = round(cell_bot / base_bot, 2) if base_bot > 0 else 0.0
        legacy["lift_top_5_0"] = round(cell_top / base_top, 2) if base_top > 0 else 0.0
        legacy["net_bias"] = round(cell_bot - cell_top, 4)

    # 2. TEMPORAL BLOCK (Time Store & Sojourn)
    n_episodes = int(sub_df["episode_id"].nunique())
    pct_tiempo = round(n / total_obs, 4)
    duration_mean = round(n / max(n_episodes, 1), 2)
    ep_lens = sub_df.groupby("episode_id").size()
    duration_max = int(ep_lens.max()) if not ep_lens.empty else 1

    fatigue_buckets = {}
    for stg in ["fresh", "persist", "mature", "exhaustion"]:
        stg_sub = sub_df[sub_df["fatigue_stage"] == stg]
        stg_n = len(stg_sub)
        fatigue_buckets[stg] = {
            "n": stg_n,
            "pct": round(stg_n / n, 4),
            "ev_net": round(float(stg_sub["fwd_ret_5.0"].mean()), 4) if stg_n > 0 else 0.0,
        }

    temporal = {
        "n_episodes": n_episodes,
        "pct_tiempo": pct_tiempo,
        "duration_mean": duration_mean,
        "duration_max": duration_max,
        "fatigue_buckets": fatigue_buckets,
    }

    # 3. TIMING GEOMETRY BLOCK (Chronos / METAR)
    pct_en_rango = round(float(sub_df["en_rango"].mean()), 4)
    pct_fuera = round(1.0 - pct_en_rango, 4)
    delta_mediana = round(float(sub_df["delta_bars"].median()), 1)
    slots = {
        "t-2": round(float((sub_df["slot"] == "t-2").mean()), 4),
        "t-1": round(float((sub_df["slot"] == "t-1").mean()), 4),
        "t=0": round(float((sub_df["slot"] == "t=0").mean()), 4),
        "entre": round(float((sub_df["slot"] == "entre").mean()), 4),
    }
    timing = {
        "pct_en_rango": pct_en_rango,
        "pct_fuera": pct_fuera,
        "delta_mediana_barras": delta_mediana,
        "slots_canonicos": slots,
    }

    # 4. KINEMATIC LEGS BLOCK (market.zigzag_legs)
    kinematics = {}
    for pct in ZZ_THRESHOLDS:
        sc = SCALE_MAP[pct]
        n_pos = int(sub_df[f"fwd_bull_{pct}"].sum())
        n_neg = n - n_pos

        # Laplace Bayesian Shrinkage M=10
        p_bull = round((n_pos + 5.0) / (n + 10.0), 4)
        p_bear = round(1.0 - p_bull, 4)

        pos_rets = sub_df[sub_df[f"fwd_bull_{pct}"]][f"fwd_ret_{pct}"]
        neg_rets = sub_df[~sub_df[f"fwd_bull_{pct}"]][f"fwd_ret_{pct}"]

        e_max = round(float(pos_rets.mean()), 4) if len(pos_rets) > 0 else 0.05
        e_min = round(float(neg_rets.mean()), 4) if len(neg_rets) > 0 else -0.04
        ev_net = round(p_bull * e_max + p_bear * e_min, 4)
        rr_asym = round(e_max / max(abs(e_min), 0.0001), 2)
        e_days = round(float(sub_df[f"fwd_days_{pct}"].mean()), 1)
        ev_per_day = round(ev_net / max(e_days, 1.0), 6)

        kinematics[sc] = {
            "p_bull": p_bull,
            "p_bear": p_bear,
            "e_ret_max": e_max,
            "e_ret_min": e_min,
            "ev_net": ev_net,
            "rr_asymmetry": rr_asym,
            "e_days": e_days,
            "ev_per_day": ev_per_day,
        }

    # Confidence tier based on zz50
    ev_50 = kinematics["zz50"]["ev_net"]
    if n >= 100 and abs(ev_50) >= 0.02:
        conf_tier = "TIER_1_DIAMOND"
    elif n >= 30 and abs(ev_50) >= 0.01:
        conf_tier = "TIER_2_GOLD"
    elif n >= 10:
        conf_tier = "TIER_3_SILVER"
    else:
        conf_tier = "TIER_4_BRONZE"

    kinematics["confidence_tier"] = conf_tier
    kinematics["timeout_rate"] = round(float((sub_df["fwd_days_5.0"] > 60).mean()), 4)

    # Consolidate into single cell dictionary
    res = {}
    res.update(legacy)
    res.update(temporal)
    res.update(timing)
    res.update(kinematics)
    return res


def main():
    store = TimescaleDataStore()
    pivots_by_ticker_scale, entities = load_all_data(store)

    # 3. Dynamic Empirical Bin Edges (Quantiles across all 13 canonical entities)
    logger.info("3. Computing empirical bin edges across all entities...")
    all_th = pd.concat([d["th"] for d in entities.values()])
    all_fi = pd.concat([d["fi"] for d in entities.values()])
    all_tw = pd.concat([d["tw"] for d in entities.values()])
    q = [0.10, 0.30, 0.70, 0.90]
    bin_edges = {
        "TH": [round(float(c), 2) for c in all_th.quantile(q).tolist()],
        "FI": [round(float(c), 2) for c in all_fi.quantile(q).tolist()],
        "TW": [round(float(c), 2) for c in all_tw.quantile(q).tolist()],
    }
    logger.info(f"   Dynamic TH edges: {bin_edges['TH']}")
    logger.info(f"   Dynamic FI edges: {bin_edges['FI']}")
    logger.info(f"   Dynamic TW edges: {bin_edges['TW']}")

    df = build_observations_table(pivots_by_ticker_scale, entities, bin_edges)
    total_obs = len(df)

    # Baselines
    logger.info("4. Computing baselines...")
    baselines = {}
    for gname, gfilter in [
        ("global", df),
        ("Defensive", df[df["tier"] == "Defensive"]),
        ("Mixed", df[df["tier"] == "Mixed"]),
        ("Cyclical", df[df["tier"] == "Cyclical"]),
        ("High-Beta", df[df["tier"] == "High-Beta"]),
        ("SPY", df[df["etf"] == "SPY"]),
    ]:
        stats = compute_four_blocks(gfilter, total_obs)
        if stats:
            baselines[gname] = stats

    # Multi-resolution cells compilation
    logger.info("5. Compiling hierarchical multi-resolution cells...")
    cells = {}

    def build_cell_hierarchical(sub):
        cell = {"global": compute_four_blocks(sub, total_obs, baselines)}
        for tname in TIERS:
            tsub = sub[sub["tier"] == tname]
            if len(tsub) >= MIN_N_L1:
                cell[tname] = compute_four_blocks(tsub, total_obs, baselines)
        spy_sub = sub[sub["etf"] == "SPY"]
        if len(spy_sub) >= MIN_N_L1:
            cell["SPY"] = compute_four_blocks(spy_sub, total_obs, baselines)
        sectors_dict = {}
        for etf_name in sorted(entities.keys()):
            esub = sub[sub["etf"] == etf_name]
            if len(esub) >= MIN_N_L1:
                sectors_dict[etf_name] = compute_four_blocks(esub, total_obs, baselines)
        if sectors_dict:
            cell["sectors"] = sectors_dict
        return cell

    # R4 (4D: TH|FI|TW|DIR)
    r4_groups = df.groupby("triad")
    logger.info(f"Observed R4 groups: {len(r4_groups)}")
    for triad_key, sub in r4_groups:
        cells[triad_key] = build_cell_hierarchical(sub)

    # R3 (3D: TH|FI|TW)
    r3_groups = df.groupby(["th_bin", "fi_bin", "tw_bin"])
    logger.info(f"Observed R3 groups: {len(r3_groups)}")
    for (th, fi, tw), sub in r3_groups:
        cells[f"{th}|{fi}|{tw}"] = build_cell_hierarchical(sub)

    # R2 (2D: TH|FI)
    r2_groups = df.groupby(["th_bin", "fi_bin"])
    logger.info(f"Observed R2 groups: {len(r2_groups)}")
    for (th, fi), sub in r2_groups:
        cells[f"{th}|{fi}"] = build_cell_hierarchical(sub)

    # R1 (1D: TH)
    r1_groups = df.groupby("th_bin")
    logger.info(f"Observed R1 groups: {len(r1_groups)}")
    for th, sub in r1_groups:
        cells[th] = build_cell_hierarchical(sub)

    logger.info(f"Total keys compiled in cells: {len(cells)}")

    r4_keys = [k for k in cells if len(k.split("|")) == 4]
    r3_keys = [k for k in cells if len(k.split("|")) == 3]
    r2_keys = [k for k in cells if len(k.split("|")) == 2]
    r1_keys = [k for k in cells if len(k.split("|")) == 1]
    logger.info(f"  R4: {len(r4_keys)}, R3: {len(r3_keys)}, R2: {len(r2_keys)}, R1: {len(r1_keys)}")

    # 6. Relative FI modifier (5 bins)
    logger.info("6. Building relative FI modifier...")
    sector_df = df[df["etf"] != "SPY"].copy()
    REL_EDGES = [-30, -10, 10, 30]

    def classify_rel(val):
        for i, edge in enumerate(REL_EDGES):
            if val < edge:
                return BIN_LABELS[i]
        return BIN_LABELS[-1]

    sector_df["rel_bin"] = sector_df["rel_fi"].apply(classify_rel)
    rel_modifier = {}
    base_bot = baselines["global"]["P_bot_5_0"]
    base_top = baselines["global"]["P_top_5_0"]

    for label in BIN_LABELS:
        sub = sector_df[sector_df["rel_bin"] == label]
        stats = compute_four_blocks(sub, total_obs, baselines)
        if stats:
            bot_factor = round(stats["P_bot_5_0"] / base_bot, 3) if base_bot > 0 else 1.0
            top_factor = round(stats["P_top_5_0"] / base_top, 3) if base_top > 0 else 1.0
            stats["bot_factor"] = bot_factor
            stats["top_factor"] = top_factor
            rel_modifier[label] = stats

    # 7. Construct output JSONs with Rule 21 Metadata
    logger.info("7. Writing output JSON artifacts with Rule 21 metadata...")
    triad_table_output = {
        "version": "3.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "backend/scripts/trainers/train_s5_triad.py",
        "_documentation": {
            "model_purpose": (
                "Conditional probability, kinematic return, and time-store transition fact store "
                "for S5 Price Breadth Triad. Quantifies the empirical likelihood and return of price reversals "
                "conditional on structural (TH 200d), intermediate (FI 50d), and tactical (TW 20d) breadth state."
            ),
            "return_formula": "ev_net = (P_bull * E[ret_max] + P_bear * E[ret_min]) - 0.0010 (10 bps round-trip friction deducted)",
            "state_hierarchy": (
                "L0: Global macro (13 canonical entities), L1: Volatility Tiers (Defensive, Mixed, Cyclical, High-Beta, SPY), "
                "L2: Individual Sectors (XLK, XLF, etc., exposed if N >= 20). Prefixes: R4 (4D), R3 (3D), R2 (2D), R1 (1D)."
            ),
            "taxonomy": {
                "TH": {"n_bins": 5, "labels": BIN_LABELS, "edges": bin_edges["TH"]},
                "FI": {"n_bins": 5, "labels": BIN_LABELS, "edges": bin_edges["FI"]},
                "TW": {"n_bins": 5, "labels": BIN_LABELS, "edges": bin_edges["TW"]},
                "DIR": {"n_bins": 2, "labels": ["-", "+"], "definition": "+ if TW(t) > TW(t-1) else -"},
            },
            "bin_classification": {
                "method": "Empirical population percentiles [0.10, 0.30, 0.70, 0.90] across all 13 canonical entities",
                "bin_percentiles": [0.10, 0.30, 0.70, 0.90],
                "bin_labels": {
                    "<<": "Severe oversold / collapse (P00-P10)",
                    "<": "Below average / pullback (P10-P30)",
                    "~": "Neutral equilibrium (P30-P70)",
                    ">": "Above average / advance (P70-P90)",
                    ">>": "Euphoric / extended overbought (P90-P100)",
                },
            },
            "dimension_thresholds_definition": {
                "TH": "Structural breadth: % of S&P 500 stocks above 200-day moving average.",
                "FI": "Intermediate breadth: % of S&P 500 stocks above 50-day moving average.",
                "TW": "Tactical breadth: % of S&P 500 stocks above 20-day moving average.",
                "Direction": "Kinematic velocity direction of tactical breadth (+/-).",
            },
            "hierarchical_fallback": {
                "min_n_prefix": MIN_N_L1,
                "strategy": "Sector (N >= 20) -> Tier (N >= 20) -> Global",
            },
            "field_glossary": {
                "n": "Historical observation count (trading days) in this state.",
                "P_bot_X_Y": "Empirical probability of being near a ZigZag X.Y% bottom (preceding by <= 3 days).",
                "P_top_X_Y": "Empirical probability of being near a ZigZag X.Y% top (preceding by <= 3 days).",
                "lift_bot_5_0": "P_bot_5_0 / global baseline. > 1.0 indicates accumulation zone.",
                "lift_top_5_0": "P_top_5_0 / global baseline. > 1.0 indicates distribution zone.",
                "net_bias": "P_bot_5_0 - P_top_5_0. Positive = net accumulation, negative = net distribution.",
                "n_episodes": "Count of distinct contiguous time-series episodes in this state.",
                "pct_tiempo": "Fraction of total historical trading days spent in this state.",
                "duration_mean": "Mean Sojourn Time (average episode duration in trading days).",
                "duration_max": "Maximum observed continuous stay in this state.",
                "fatigue_buckets": "Decay of forward expected return across persistence stages (fresh, persist, mature, exhaustion).",
                "pct_en_rango": "Fraction of observations within ±2 bars of an inflection turn.",
                "pct_fuera": "Fraction of observations outside turn window (in directional inertia).",
                "delta_mediana_barras": "Median signed bar distance to nearest turn.",
                "slots_canonicos": "Observation distribution across canonical timing slots: t-2, t-1, t=0, entre.",
                "p_bull": "Probability of next swing reaching upper pivot (MAX), shrunk via Laplace Bayesian Shrinkage (M=10).",
                "p_bear": "Probability of next swing reaching lower pivot (MIN).",
                "ev_net": "Net expected return of subsequent swing, net of 10 bps friction.",
                "rr_asymmetry": "Reward-to-Risk asymmetry ratio: E[ret_max] / |E[ret_min]|.",
                "e_days": "Expected trading days to reach target pivot.",
                "ev_per_day": "Capital velocity (% net return per day committed).",
                "confidence_tier": "Four-tier confidence rating based on sample size and expected return (Diamond, Gold, Silver, Bronze).",
            },
            "signal_interpretation_policy": (
                "Clean Architecture Standard: Business signals (ALLOW, REDUCE, ACCUMULATE, TRIM) "
                "are NOT static strings in this JSON, but are dynamically interpreted by pure-domain "
                "adapters (triad_lookup.py, quality_entry_gate.py)."
            ),
        },
        "training": {
            "n_entities": len(entities),
            "entities": sorted(entities.keys()),
            "n_observations": total_obs,
            "near_window_bars": NEAR_WINDOW,
            "zigzag_thresholds": ZZ_THRESHOLDS,
            "min_n_l1": MIN_N_L1,
            "bin_percentiles": BIN_PERCENTILES,
        },
        "hierarchical_fallback": {
            "min_n_prefix": MIN_N_L1,
            "strategy": "Sector (N >= 20) -> Tier (N >= 20) -> Global",
        },
        "bin_edges": bin_edges,
        "bin_labels": BIN_LABELS,
        "tiers": TIERS,
        "baselines": baselines,
        "cells": cells,
    }

    project_root = ROOT.parent if ROOT.name == "backend" else ROOT
    out_path = project_root / "backend/modules/entry_decision/domain/rules/s5_triad_table.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(triad_table_output, f, indent=2, default=str)
    logger.info(f"✅ Written {out_path} ({len(cells)} cells).")

    rel_output = {
        "version": "3.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "backend/scripts/trainers/train_s5_triad.py",
        "_documentation": {
            "purpose": "Relative intermediate breadth modifier: FI_sector - FI_spy (percentage points).",
            "formula": "rel_fi = S5_{ETF}_FI - S5FI",
            "bins": {
                "<<": "rel_fi < -30pp (sector severely depressed relative to market)",
                "<": "-30 <= rel_fi < -10pp (sector moderately depressed)",
                "~": "-10 <= rel_fi < +10pp (aligned with market)",
                ">": "+10 <= rel_fi < +30pp (sector leading market)",
                ">>": "rel_fi >= +30pp (sector euphoric relative to market)",
            },
            "bin_fields": {
                "bot_factor": "Multiplier for triad P_bot. > 1.0 amplifies bottom likelihood.",
                "top_factor": "Multiplier for triad P_top. > 1.0 amplifies top likelihood.",
            },
        },
        "bin_edges": REL_EDGES,
        "bin_labels": BIN_LABELS,
        "bins": rel_modifier,
    }

    rel_path = project_root / "backend/modules/entry_decision/domain/rules/s5_relative_modifier.json"
    with open(rel_path, "w", encoding="utf-8") as f:
        json.dump(rel_output, f, indent=2, default=str)
    logger.info(f"✅ Written {rel_path} ({len(rel_modifier)} bins).")
    store.close()
    logger.info("✨ S5 Triad Table v3.1 training completed successfully!")


if __name__ == "__main__":
    main()
