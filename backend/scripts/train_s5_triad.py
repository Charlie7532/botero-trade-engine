"""
Train S5 Triad Table
=====================
Generates:
  1. s5_triad_table.json  — 125 states (5**3), ZZ coincidence, Tier Pooling
  2. s5_relative_modifier.json — 5 cells (FI_sector - FI_spy)

Methodology identical to rc_probability_table.json:
  - Classify levels into bins
  - Count visits to each state
  - Cross with ZigZag turns at 2.5%, 5.0%, 7.5%
  - Compute P(near_turn | state)
"""
import sys
import os
import json
from datetime import datetime, timezone

sys.path.append("/root/botero-trade")
os.chdir("/root/botero-trade")
from dotenv import load_dotenv

load_dotenv(".env")

import pandas as pd
import numpy as np
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.constants.sectors import (
    SECTOR_ETFS,
    SECTOR_BREADTH_TICKERS,
)

store = TimescaleDataStore()

# ── Configuration ──
BIN_LABELS = ["<<", "<", "~", ">", ">>"]
# 4 edges → 5 bins: <<(10%) < (20%) ~(40%) >(20%) >>(10%)
BIN_PERCENTILES = [0.10, 0.30, 0.70, 0.90]
ZZ_THRESHOLDS = [2.5, 5.0, 7.5]
NEAR_WINDOW = 3  # bars before/after a ZZ turn to count as "near"
MIN_N_L1 = 20  # minimum samples for L1 (tier/entity) stats

TIERS = {
    "Defensive": ["XLP", "XLV", "XLU", "XLRE", "XLB"],
    "Mixed": ["XLE", "XLF", "XLC"],
    "Cyclical": ["XLK", "XLY", "XLI"],
}
ETF_TO_TIER = {}
for tier_name, etfs in TIERS.items():
    for etf in etfs:
        ETF_TO_TIER[etf] = tier_name

# SPY S5 tickers (market-wide, no sector prefix)
SPY_S5 = {"structural": "S5TH", "intermediate": "S5FI", "tactical": "S5TW"}


# ── Helpers ──
def compute_zigzag(prices: pd.Series, pct_threshold: float) -> pd.Series:
    """Compute zigzag turning points. Returns Series: 1=TOP, -1=BOTTOM, 0=nothing."""
    n = len(prices)
    if n < 10:
        return pd.Series(0, index=prices.index)
    threshold = pct_threshold / 100.0
    direction = 1
    last_pivot_price = prices.iloc[0]
    last_pivot_idx = 0
    pivots = pd.Series(0, index=prices.index)
    for i in range(1, n):
        price = prices.iloc[i]
        if direction == 1:
            if price >= last_pivot_price:
                last_pivot_price = price
                last_pivot_idx = i
            elif price <= last_pivot_price * (1 - threshold):
                pivots.iloc[last_pivot_idx] = 1
                last_pivot_price = price
                last_pivot_idx = i
                direction = -1
        else:
            if price <= last_pivot_price:
                last_pivot_price = price
                last_pivot_idx = i
            elif price >= last_pivot_price * (1 + threshold):
                pivots.iloc[last_pivot_idx] = -1
                last_pivot_price = price
                last_pivot_idx = i
                direction = 1
    return pivots


def make_near_flags(zz: pd.Series, window: int) -> tuple[pd.Series, pd.Series]:
    """Create boolean Series for 'near a ZZ bottom' and 'near a ZZ top'."""
    near_bot = pd.Series(False, index=zz.index)
    near_top = pd.Series(False, index=zz.index)
    n = len(zz)
    for i in range(n):
        if zz.iloc[i] == -1:  # bottom
            for d in range(-window, window + 1):
                p = i + d
                if 0 <= p < n:
                    near_bot.iloc[p] = True
        elif zz.iloc[i] == 1:  # top
            for d in range(-window, window + 1):
                p = i + d
                if 0 <= p < n:
                    near_top.iloc[p] = True
    return near_bot, near_top


def classify_bin(value: float, edges: list[float]) -> str:
    """Classify a value into one of 5 bins based on edges."""
    for i, edge in enumerate(edges):
        if value < edge:
            return BIN_LABELS[i]
    return BIN_LABELS[-1]


def compute_cell_stats(sub_df: pd.DataFrame) -> dict | None:
    """Compute ZZ coincidence stats for a subset of observations."""
    n = len(sub_df)
    if n == 0:
        return None
    stats = {"n": n}
    for pct in ZZ_THRESHOLDS:
        key_pct = str(pct).replace(".", "_")
        stats[f"P_bot_{key_pct}"] = round(float(sub_df[f"near_bot_{pct}"].mean()), 4)
        stats[f"P_top_{key_pct}"] = round(float(sub_df[f"near_top_{pct}"].mean()), 4)
    return stats


# ══════════════════════════════════════════════════════════════
# STEP 1: LOAD DATA
# ══════════════════════════════════════════════════════════════
print("Step 1: Loading data...")

entities = {}  # etf -> DataFrame with th, fi, tw, etf_close columns

# Load SPY
spy_th = store.load_bars(SPY_S5["structural"], "1d")["close"].astype(float).rename("th")
spy_fi = store.load_bars(SPY_S5["intermediate"], "1d")["close"].astype(float).rename("fi")
spy_tw = store.load_bars(SPY_S5["tactical"], "1d")["close"].astype(float).rename("tw")
spy_price = store.load_bars("SPY", "1d")["close"].astype(float).rename("etf_close")
spy_merged = pd.concat([spy_th, spy_fi, spy_tw, spy_price], axis=1, join="inner").dropna()
entities["SPY"] = spy_merged
print(f"  SPY: {len(spy_merged)} bars")

# Load sectors
for etf, sector_name in SECTOR_ETFS.items():
    tickers = SECTOR_BREADTH_TICKERS.get(etf)
    if not tickers:
        continue
    th = store.load_bars(tickers["structural"], "1d")["close"].astype(float).rename("th")
    fi = store.load_bars(tickers["intermediate"], "1d")["close"].astype(float).rename("fi")
    tw = store.load_bars(tickers["tactical"], "1d")["close"].astype(float).rename("tw")
    etf_price = store.load_bars(etf, "1d")["close"].astype(float).rename("etf_close")
    merged = pd.concat([th, fi, tw, etf_price], axis=1, join="inner").dropna()
    if len(merged) < 200:
        print(f"  {etf}: SKIP ({len(merged)} bars)")
        continue
    entities[etf] = merged
    print(f"  {etf} ({sector_name}): {len(merged)} bars")

# Keep spy_fi accessible for relative modifier
spy_fi_series = spy_merged["fi"]


# ══════════════════════════════════════════════════════════════
# STEP 2: DEFINE BIN EDGES (global percentiles)
# ══════════════════════════════════════════════════════════════
print("\nStep 2: Computing bin edges...")

all_th = pd.concat([d["th"] for d in entities.values()])
all_fi = pd.concat([d["fi"] for d in entities.values()])
all_tw = pd.concat([d["tw"] for d in entities.values()])

bin_edges = {}
for name, series in [("TH", all_th), ("FI", all_fi), ("TW", all_tw)]:
    cuts = series.quantile(BIN_PERCENTILES).tolist()
    bin_edges[name] = [round(c, 2) for c in cuts]
    print(f"  {name}: {bin_edges[name]}")


# ══════════════════════════════════════════════════════════════
# STEP 3: CLASSIFY + COMPUTE ZIGZAG + BUILD OBSERVATION TABLE
# ══════════════════════════════════════════════════════════════
print("\nStep 3: Classifying bins and computing ZigZag...")

all_obs = []

for etf, merged in entities.items():
    # Classify bins
    th_bins = merged["th"].apply(lambda v: classify_bin(v, bin_edges["TH"]))
    fi_bins = merged["fi"].apply(lambda v: classify_bin(v, bin_edges["FI"]))
    tw_bins = merged["tw"].apply(lambda v: classify_bin(v, bin_edges["TW"]))
    triad_keys = th_bins + "|" + fi_bins + "|" + tw_bins

    # Compute ZigZag at 3 scales
    zz_flags = {}
    for pct in ZZ_THRESHOLDS:
        zz = compute_zigzag(merged["etf_close"], pct)
        near_bot, near_top = make_near_flags(zz, NEAR_WINDOW)
        zz_flags[f"near_bot_{pct}"] = near_bot
        zz_flags[f"near_top_{pct}"] = near_top

    # Compute relative FI (sector - SPY), aligned by index
    if etf != "SPY":
        # Reindex spy_fi to sector dates for proper alignment
        spy_fi_aligned = spy_fi_series.reindex(merged.index, method="ffill")
        rel_fi = merged["fi"] - spy_fi_aligned
    else:
        rel_fi = pd.Series(0.0, index=merged.index)

    # Build observation records
    tier = ETF_TO_TIER.get(etf, "SPY")
    for i in range(len(merged)):
        rec = {
            "etf": etf,
            "tier": tier,
            "th_bin": th_bins.iloc[i],
            "fi_bin": fi_bins.iloc[i],
            "tw_bin": tw_bins.iloc[i],
            "triad": triad_keys.iloc[i],
            "rel_fi": float(rel_fi.iloc[i]) if not pd.isna(rel_fi.iloc[i]) else 0.0,
        }
        for pct in ZZ_THRESHOLDS:
            rec[f"near_bot_{pct}"] = bool(zz_flags[f"near_bot_{pct}"].iloc[i])
            rec[f"near_top_{pct}"] = bool(zz_flags[f"near_top_{pct}"].iloc[i])
        all_obs.append(rec)

    n_bots_5 = sum(1 for r in all_obs[-len(merged):] if r["near_bot_5.0"])
    n_tops_5 = sum(1 for r in all_obs[-len(merged):] if r["near_top_5.0"])
    print(f"  {etf}: {len(merged)} obs, ZZ5 near_bot={n_bots_5} near_top={n_tops_5}")

df = pd.DataFrame(all_obs)
print(f"\nTotal observations: {len(df)}")


# ══════════════════════════════════════════════════════════════
# STEP 4: BUILD TRIAD TABLE (125 states)
# ══════════════════════════════════════════════════════════════
print("\nStep 4: Building triad table...")

# Compute baselines
baselines = {}
for group_name, group_filter in [
    ("global", df),
    ("Defensive", df[df["tier"] == "Defensive"]),
    ("Mixed", df[df["tier"] == "Mixed"]),
    ("Cyclical", df[df["tier"] == "Cyclical"]),
    ("SPY", df[df["etf"] == "SPY"]),
]:
    stats = compute_cell_stats(group_filter)
    if stats:
        baselines[group_name] = stats

print(f"  Baselines computed: {list(baselines.keys())}")
print(f"  Global baseline P_bot_5.0: {baselines['global']['P_bot_5_0']}")

# Compute cells
cells = {}
unique_triads = df["triad"].unique()
print(f"  Unique triad states observed: {len(unique_triads)}/125")

for triad_key in sorted(unique_triads):
    sub = df[df["triad"] == triad_key]
    cell = {}

    # Global stats
    cell["global"] = compute_cell_stats(sub)

    # Tier stats
    for tier_name in TIERS:
        tier_sub = sub[sub["tier"] == tier_name]
        tier_stats = compute_cell_stats(tier_sub)
        if tier_stats and tier_stats["n"] >= MIN_N_L1:
            cell[tier_name] = tier_stats

    # SPY stats
    spy_sub = sub[sub["etf"] == "SPY"]
    spy_stats = compute_cell_stats(spy_sub)
    if spy_stats and spy_stats["n"] >= MIN_N_L1:
        cell["SPY"] = spy_stats

    # Compute lift vs global baseline
    if cell["global"]:
        base_bot = baselines["global"]["P_bot_5_0"]
        base_top = baselines["global"]["P_top_5_0"]
        cell_bot = cell["global"]["P_bot_5_0"]
        cell_top = cell["global"]["P_top_5_0"]
        cell["global"]["lift_bot_5_0"] = round(cell_bot / base_bot, 2) if base_bot > 0 else 0.0
        cell["global"]["lift_top_5_0"] = round(cell_top / base_top, 2) if base_top > 0 else 0.0
        cell["global"]["net_bias"] = round(cell_bot - cell_top, 4)

    cells[triad_key] = cell

# Count coverage
n_cells_total = len(cells)
tier_coverage = {}
for tier_name in list(TIERS.keys()) + ["SPY"]:
    n_with_tier = sum(1 for c in cells.values() if tier_name in c)
    tier_coverage[tier_name] = n_with_tier

print(f"  Cells with data: {n_cells_total}")
for tier_name, count in tier_coverage.items():
    print(f"    {tier_name}: {count} cells with N>={MIN_N_L1}")


# ══════════════════════════════════════════════════════════════
# STEP 5: BUILD RELATIVE MODIFIER (5 cells)
# ══════════════════════════════════════════════════════════════
print("\nStep 5: Building relative FI modifier...")

# Only use sector data (not SPY, since rel_fi=0 for SPY)
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
    stats = compute_cell_stats(sub)
    if stats:
        bot_factor = round(stats["P_bot_5_0"] / base_bot, 3) if base_bot > 0 else 1.0
        top_factor = round(stats["P_top_5_0"] / base_top, 3) if base_top > 0 else 1.0
        stats["bot_factor"] = bot_factor
        stats["top_factor"] = top_factor
        rel_modifier[label] = stats
        print(f"  {label}: N={stats['n']}, P_bot_5.0={stats['P_bot_5_0']:.3f} (x{bot_factor:.2f}), P_top_5.0={stats['P_top_5_0']:.3f} (x{top_factor:.2f})")


# ══════════════════════════════════════════════════════════════
# STEP 6: WRITE OUTPUT FILES
# ══════════════════════════════════════════════════════════════
print("\nStep 6: Writing output files...")

triad_table = {
    "version": "1.0",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "training": {
        "n_entities": len(entities),
        "entities": sorted(entities.keys()),
        "n_observations": len(df),
        "near_window_bars": NEAR_WINDOW,
        "zigzag_thresholds": ZZ_THRESHOLDS,
        "min_n_l1": MIN_N_L1,
        "bin_percentiles": BIN_PERCENTILES,
    },
    "bin_edges": {k: [round(v, 2) for v in vals] for k, vals in bin_edges.items()},
    "bin_labels": BIN_LABELS,
    "tiers": TIERS,
    "baselines": baselines,
    "cells": cells,
}

out_path = "backend/modules/entry_decision/domain/rules/s5_triad_table.json"
with open(out_path, "w") as f:
    json.dump(triad_table, f, indent=2, default=str)
print(f"  Written: {out_path} ({len(cells)} cells)")

rel_path = "backend/modules/entry_decision/domain/rules/s5_relative_modifier.json"
rel_output = {
    "version": "1.0",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "description": "FI_sector - FI_spy relative breadth modifier",
    "bin_edges": REL_EDGES,
    "bin_labels": BIN_LABELS,
    "bins": rel_modifier,
}
with open(rel_path, "w") as f:
    json.dump(rel_output, f, indent=2, default=str)
print(f"  Written: {rel_path} ({len(rel_modifier)} bins)")

store.close()

# ══════════════════════════════════════════════════════════════
# STEP 7: SUMMARY
# ══════════════════════════════════════════════════════════════
print(f"\n{'=' * 80}")
print("  TRAINING COMPLETE")
print(f"{'=' * 80}")
print(f"  Triad table: {n_cells_total} cells (of 125 possible)")
print(f"  Observations: {len(df)}")
print(f"  Tier coverage (N>={MIN_N_L1}):")
for tier_name, count in tier_coverage.items():
    print(f"    {tier_name}: {count}/{n_cells_total}")

# Top 10 accumulation and distribution states
print(f"\n  Top 10 Accumulation States (by P_bot_5.0):")
ranked = sorted(cells.items(), key=lambda x: x[1].get("global", {}).get("P_bot_5_0", 0), reverse=True)
for i, (key, cell) in enumerate(ranked[:10]):
    g = cell.get("global", {})
    print(f"    {i+1}. {key:<16} N={g.get('n',0):>5}  P_bot={g.get('P_bot_5_0',0):.1%}  P_top={g.get('P_top_5_0',0):.1%}  lift={g.get('lift_bot_5_0',0):.1f}x  bias={g.get('net_bias',0):+.1%}")

print(f"\n  Top 10 Distribution States (by P_top_5.0):")
ranked_top = sorted(cells.items(), key=lambda x: x[1].get("global", {}).get("P_top_5_0", 0), reverse=True)
for i, (key, cell) in enumerate(ranked_top[:10]):
    g = cell.get("global", {})
    print(f"    {i+1}. {key:<16} N={g.get('n',0):>5}  P_top={g.get('P_top_5_0',0):.1%}  P_bot={g.get('P_bot_5_0',0):.1%}  lift={g.get('lift_top_5_0',0):.1f}x  bias={g.get('net_bias',0):+.1%}")
