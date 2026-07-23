"""
Train S5 Triad Table
=====================
Generates two JSON artifacts consumed by the Quality Entry Gate (Gate 1.5b):

  1. s5_triad_table.json     — Conditional probability table (112 of 125 states)
  2. s5_relative_modifier.json — Sector vs SPY breadth modifier (5 bins)

═══════════════════════════════════════════════════════════════════════════════
WHAT IS THE S5 TRIAD?
═══════════════════════════════════════════════════════════════════════════════

The S&P 500's internal health is measured by three breadth indicators, each
representing a different moving-average timescale of the % of stocks above
their respective MA:

  S5TH  (Structural)    — % of S&P 500 stocks above their 200-day MA
  S5FI  (Intermediate)  — % of S&P 500 stocks above their  50-day MA
  S5TW  (Tactical)      — % of S&P 500 stocks above their  20-day MA

Each indicator ranges 0–100%. The three together form the "Triad" — a 3D
state space that captures the breadth health at structural, intermediate,
and tactical timescales simultaneously.

The key insight: these three levels cascade. In a selloff, TW breaks first
(fastest MA), then FI, then TH last. In a recovery, TW recovers first,
then FI, then TH. This cascade creates predictable sequences of states
that anticipate ZigZag turning points (bottoms and tops).

═══════════════════════════════════════════════════════════════════════════════
DATA SOURCES (from the Vault)
═══════════════════════════════════════════════════════════════════════════════

  SPY breadth:     S5TH, S5FI, S5TW     (market-wide, all S&P 500 stocks)
  Sector breadth:  S5_{XLK}_TH, etc.    (per-sector, only that sector's stocks)
  Price data:      SPY + 11 sector ETFs  (XLK, XLV, XLF, XLY, XLP, XLI,
                                           XLE, XLU, XLRE, XLB, XLC)

  Historical range: 2006-12-29 → present (from TradingView import + daemon)
  Note: Pre-2022 data has volume=0 (TradingView), post-2022 has volume>0 (daemon).
  All timestamps normalized to midnight UTC (Rule 18).

═══════════════════════════════════════════════════════════════════════════════
BIN CLASSIFICATION
═══════════════════════════════════════════════════════════════════════════════

Each of TH, FI, TW is classified into 5 bins using GLOBAL percentiles
(pooled across all 12 entities × all dates):

  Bin  Label  Percentile Range  Typical TH Values   Meaning
  ───  ─────  ────────────────  ─────────────────   ─────────────────────
   0    <<    [0, P10)          < 26.5%             BROKEN — structural damage
   1     <    [P10, P30)        26.5% – 48.8%       WEAK — below average
   2     ~    [P30, P70)        48.8% – 74.2%       NEUTRAL — normal range
   3     >    [P70, P90)        74.2% – 87.5%       STRONG — above average
   4    >>    [P90, 100]        > 87.5%             EUPHORIC — stretched

  3 families × 5 bins = 125 possible states (5³)
  Only 112 are ever observed. 13 are mechanically impossible because
  the cascade constraint prevents certain combinations (e.g., FI euphoric
  while TH and TW are both broken).

═══════════════════════════════════════════════════════════════════════════════
ZIGZAG COINCIDENCE METHODOLOGY
═══════════════════════════════════════════════════════════════════════════════

For each entity (SPY + 11 sectors), we compute a ZigZag indicator on the
ETF price at three thresholds: 2.5%, 5.0%, and 7.5%. The ZigZag marks
local tops (+1) and bottoms (-1) that represent price reversals of at
least that percentage.

A bar is flagged as "near" a ZZ turn if it falls within ±NEAR_WINDOW (3)
trading days of the pivot. Then for each triad state, we compute:

  P_bot_X_Y = fraction of bars in that state that are "near" a ZZ X.Y% bottom
  P_top_X_Y = fraction of bars in that state that are "near" a ZZ X.Y% top
  lift_bot   = P_bot_state / P_bot_global    (how much more likely than average)
  lift_top   = P_top_state / P_top_global
  net_bias   = P_bot - P_top                 (positive = accumulation zone)

═══════════════════════════════════════════════════════════════════════════════
TIER POOLING
═══════════════════════════════════════════════════════════════════════════════

Sectors are grouped into volatility tiers to ensure statistical significance
when individual sectors don't have enough observations (N < MIN_N_L1 = 20):

  Defensive: XLP, XLV, XLU, XLRE, XLB  — Low beta, lower dispersion
  Mixed:     XLE, XLF, XLC             — Variable beta
  Cyclical:  XLK, XLY, XLI            — High beta, higher dispersion

Each cell in the output table reports stats for: global, Defensive, Mixed,
Cyclical, and SPY — but only if N >= 20 for that tier.

═══════════════════════════════════════════════════════════════════════════════
RELATIVE MODIFIER (s5_relative_modifier.json)
═══════════════════════════════════════════════════════════════════════════════

Measures the difference: FI_sector - FI_spy (percentage points).
This captures whether a sector's intermediate breadth is leading or
lagging the overall market.

  Bin edges: [-30, -10, 10, 30] pp
  <<  = sector 30+ pp BELOW SPY   → bot_factor > 1 (more likely near bottom)
  <   = sector 10-30 pp below     → slightly elevated bottom probability
  ~   = within ±10 pp (aligned)   → neutral
  >   = sector 10-30 pp above     → slightly elevated top probability
  >>  = sector 30+ pp ABOVE SPY   → top_factor > 1 (sector euphoric vs market)

The bot_factor and top_factor are MULTIPLIERS applied to the triad's
P_bot and P_top to adjust for the sector's relative position.

═══════════════════════════════════════════════════════════════════════════════
OUTPUT SCHEMA — s5_triad_table.json
═══════════════════════════════════════════════════════════════════════════════

{
  "version": "1.0",
  "generated_at": "ISO timestamp",
  "training": {
    "n_entities":       12,              // SPY + 11 sectors
    "entities":         ["SPY", ...],    // List of ETFs used
    "n_observations":   16724,           // Total bar-days (all entities × dates)
    "near_window_bars": 3,               // ±3 bars from ZZ pivot = "near"
    "zigzag_thresholds":[2.5, 5.0, 7.5], // % thresholds for ZZ
    "min_n_l1":         20,              // Min N for tier-level stats
    "bin_percentiles":  [0.10, 0.30, 0.70, 0.90]
  },
  "bin_edges": {
    "TH": [26.5, 48.8, 74.2, 87.5],     // Percentile-derived cut points
    "FI": [19.4, 41.9, 72.1, 87.3],
    "TW": [15.0, 39.6, 73.2, 88.2]
  },
  "bin_labels": ["<<", "<", "~", ">", ">>"],
  "tiers": { "Defensive": [...], "Mixed": [...], "Cyclical": [...] },
  "baselines": {
    "global": { "n": 16724, "P_bot_5_0": 0.1178, ... },
    "Defensive": { ... }, "Mixed": { ... }, "Cyclical": { ... }, "SPY": { ... }
  },
  "cells": {
    "<<|<<|<<": {                        // Key = TH_bin | FI_bin | TW_bin
      "global": {
        "n": 565,                        // Total observations in this state
        "P_bot_2_5": 0.7929,             // P(near ZZ 2.5% bottom | state)
        "P_top_2_5": 0.2425,
        "P_bot_5_0": 0.6124,             // ★ PRIMARY METRIC
        "P_top_5_0": 0.1611,
        "P_bot_7_5": 0.4212,
        "P_top_7_5": 0.0708,
        "lift_bot_5_0": 5.20,            // P_bot / baseline P_bot
        "lift_top_5_0": 1.35,
        "net_bias": 0.4513               // P_bot - P_top (>0 = accumulation)
      },
      "Defensive": { "n": 287, ... },    // Only if N >= 20
      "Mixed":     { "n": ..., ... },
      "Cyclical":  { "n": ..., ... },
      "SPY":       { "n": ..., ... }
    },
    ... // 112 states total
  }
}

═══════════════════════════════════════════════════════════════════════════════
OUTPUT SCHEMA — s5_relative_modifier.json
═══════════════════════════════════════════════════════════════════════════════

{
  "version": "1.0",
  "description": "FI_sector - FI_spy relative breadth modifier",
  "bin_edges": [-30, -10, 10, 30],        // Percentage points
  "bin_labels": ["<<", "<", "~", ">", ">>"],
  "bins": {
    "<<": {                               // Sector 30+pp below SPY
      "n": 606,
      "P_bot_5_0": 0.186,                // Raw P(near bottom) for this bin
      "P_top_5_0": 0.040,
      "bot_factor": 1.58,                // MULTIPLIER for triad P_bot
      "top_factor": 0.33                  // MULTIPLIER for triad P_top
    },
    ... // 5 bins total
  }
}

═══════════════════════════════════════════════════════════════════════════════
CONSUMERS
═══════════════════════════════════════════════════════════════════════════════

  - triad_lookup.py     — Domain rule that reads both JSONs, classifies current
                          breadth state, returns P_bot/P_top/signal/conviction
  - quality_entry_gate  — Gate 1.5b uses triad_lookup output to modulate sizing
  - s5_triad_derived    — Enriched derived table (generated separately) adds
                          forward returns, anticipation timing, and alpha per tier
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
    """Create boolean Series for 'near a ZZ bottom' and 'near a ZZ top' (strictly future/forward-looking)."""
    near_bot = pd.Series(False, index=zz.index)
    near_top = pd.Series(False, index=zz.index)
    n = len(zz)
    for i in range(n):
        if zz.iloc[i] == -1:  # bottom
            # Flag points preceding the bottom (i-window to i)
            for d in range(-window, 1):
                p = i + d
                if 0 <= p < n:
                    near_bot.iloc[p] = True
        elif zz.iloc[i] == 1:  # top
            # Flag points preceding the top (i-window to i)
            for d in range(-window, 1):
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
    # Compute tw_diff and drop first row to handle NaNs
    merged["tw_diff"] = merged["tw"].diff(1)
    merged = merged.dropna()

    # Classify bins
    th_bins = merged["th"].apply(lambda v: classify_bin(v, bin_edges["TH"]))
    fi_bins = merged["fi"].apply(lambda v: classify_bin(v, bin_edges["FI"]))
    tw_bins = merged["tw"].apply(lambda v: classify_bin(v, bin_edges["TW"]))
    dir_bins = merged["tw_diff"].apply(lambda v: "+" if v > 0 else "-")
    triad_keys = th_bins + "|" + fi_bins + "|" + tw_bins + "|" + dir_bins

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
            "dir_bin": dir_bins.iloc[i],
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
# STEP 4: BUILD TRIAD TABLE (250 states)
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

# Compute prefix cells (R3, R2, R1) for hierarchical fallback
# R3: TH|FI|TW
r3_groups = df.groupby(["th_bin", "fi_bin", "tw_bin"])
for (th, fi, tw), sub in r3_groups:
    r3_key = f"{th}|{fi}|{tw}"
    cell = {}
    cell["global"] = compute_cell_stats(sub)
    for tier_name in TIERS:
        tier_sub = sub[sub["tier"] == tier_name]
        tier_stats = compute_cell_stats(tier_sub)
        if tier_stats and tier_stats["n"] >= MIN_N_L1:
            cell[tier_name] = tier_stats
    spy_sub = sub[sub["etf"] == "SPY"]
    spy_stats = compute_cell_stats(spy_sub)
    if spy_stats and spy_stats["n"] >= MIN_N_L1:
        cell["SPY"] = spy_stats

    if cell["global"]:
        base_bot = baselines["global"]["P_bot_5_0"]
        base_top = baselines["global"]["P_top_5_0"]
        cell_bot = cell["global"]["P_bot_5_0"]
        cell_top = cell["global"]["P_top_5_0"]
        cell["global"]["lift_bot_5_0"] = round(cell_bot / base_bot, 2) if base_bot > 0 else 0.0
        cell["global"]["lift_top_5_0"] = round(cell_top / base_top, 2) if base_top > 0 else 0.0
        cell["global"]["net_bias"] = round(cell_bot - cell_top, 4)

    cells[r3_key] = cell

# R2: TH|FI
r2_groups = df.groupby(["th_bin", "fi_bin"])
for (th, fi), sub in r2_groups:
    r2_key = f"{th}|{fi}"
    cell = {}
    cell["global"] = compute_cell_stats(sub)
    for tier_name in TIERS:
        tier_sub = sub[sub["tier"] == tier_name]
        tier_stats = compute_cell_stats(tier_sub)
        if tier_stats and tier_stats["n"] >= MIN_N_L1:
            cell[tier_name] = tier_stats
    spy_sub = sub[sub["etf"] == "SPY"]
    spy_stats = compute_cell_stats(spy_sub)
    if spy_stats and spy_stats["n"] >= MIN_N_L1:
        cell["SPY"] = spy_stats

    if cell["global"]:
        base_bot = baselines["global"]["P_bot_5_0"]
        base_top = baselines["global"]["P_top_5_0"]
        cell_bot = cell["global"]["P_bot_5_0"]
        cell_top = cell["global"]["P_top_5_0"]
        cell["global"]["lift_bot_5_0"] = round(cell_bot / base_bot, 2) if base_bot > 0 else 0.0
        cell["global"]["lift_top_5_0"] = round(cell_top / base_top, 2) if base_top > 0 else 0.0
        cell["global"]["net_bias"] = round(cell_bot - cell_top, 4)

    cells[r2_key] = cell

# R1: TH
r1_groups = df.groupby("th_bin")
for th, sub in r1_groups:
    r1_key = f"{th}"
    cell = {}
    cell["global"] = compute_cell_stats(sub)
    for tier_name in TIERS:
        tier_sub = sub[sub["tier"] == tier_name]
        tier_stats = compute_cell_stats(tier_sub)
        if tier_stats and tier_stats["n"] >= MIN_N_L1:
            cell[tier_name] = tier_stats
    spy_sub = sub[sub["etf"] == "SPY"]
    spy_stats = compute_cell_stats(spy_sub)
    if spy_stats and spy_stats["n"] >= MIN_N_L1:
        cell["SPY"] = spy_stats

    if cell["global"]:
        base_bot = baselines["global"]["P_bot_5_0"]
        base_top = baselines["global"]["P_top_5_0"]
        cell_bot = cell["global"]["P_bot_5_0"]
        cell_top = cell["global"]["P_top_5_0"]
        cell["global"]["lift_bot_5_0"] = round(cell_bot / base_bot, 2) if base_bot > 0 else 0.0
        cell["global"]["lift_top_5_0"] = round(cell_top / base_top, 2) if base_top > 0 else 0.0
        cell["global"]["net_bias"] = round(cell_bot - cell_top, 4)

    cells[r1_key] = cell

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
    "version": "2.0",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "generated_by": "backend/scripts/train_s5_triad.py",
    "_metadata": {
        "shannon_mutual_info": {
            "R4_bot_5_0": 0.0941,
            "R4_top_5_0": 0.0317,
            "note": "Bits de información mutua I(State; NearBot/Top) por nivel de resolución"
        },
        "purpose": (

            "Tabla de probabilidad condicional de giros ZigZag basada en 3 ejes de "
            "amplitud de PRECIO sectorial (S5). Cada celda responde: dado que el sector "
            "tiene este estado combinatorio de stocks por encima de sus medias móviles, "
            "¿cuál es la probabilidad de estar cerca de un suelo (bottom) o techo (top) "
            "del precio del ETF?"
        ),
        "data_source": (
            "Vault (Neon PostgreSQL). Tickers: S5_{ETF}_TH, S5_{ETF}_FI, S5_{ETF}_TW "
            "para cada sector. S5TH, S5FI, S5TW para SPY. Precio del ETF para ZigZag."
        ),
        "axes": {
            "TH (Structural)": "% de constituyentes del sector con PRECIO > media móvil 200 días. Indica tendencia de largo plazo.",
            "FI (Intermediate)": "% de constituyentes del sector con PRECIO > media móvil 50 días. Señal principal de salud intermedia.",
            "TW (Tactical)": "% de constituyentes del sector con PRECIO > media móvil 20 días. Momentum de corto plazo.",
            "Direction (+/-)": "+ si TW subió vs día anterior, - si bajó o igual.",
        },
        "key_difference_vs_s5v": (
            "S5 mide PRECIO (cuántos stocks suben). S5V mide VOLUMEN (cuántos stocks "
            "tienen actividad de trading elevada). Son ortogonales (r ≈ -0.26). Juntos "
            "capturan 2x más información que cualquiera solo."
        ),
        "bin_classification": {
            "method": "Percentiles globales sobre todas las observaciones",
            "bin_percentiles": BIN_PERCENTILES,
            "bin_labels_meaning": {
                "<<": f"Extremo frío: < percentil {BIN_PERCENTILES[0]*100:.0f}% (pocos stocks en uptrend)",
                "<": f"Frío: percentil {BIN_PERCENTILES[0]*100:.0f}%-{BIN_PERCENTILES[1]*100:.0f}%",
                "~": f"Neutral: percentil {BIN_PERCENTILES[1]*100:.0f}%-{BIN_PERCENTILES[2]*100:.0f}%",
                ">": f"Caliente: percentil {BIN_PERCENTILES[2]*100:.0f}%-{BIN_PERCENTILES[3]*100:.0f}%",
                ">>": f"Extremo caliente: > percentil {BIN_PERCENTILES[3]*100:.0f}% (mayoría en uptrend)",
            },
        },
        "cell_key_format": "TH_bin|FI_bin|TW_bin|Direction → ejemplo: '<<|<<|>>|+' = TH frío, FI frío, TW caliente, subiendo",
        "cell_fields": {
            "n": "Número de observaciones (días) en este estado",
            "P_bot_2_5": "P(cerca de suelo ZZ 2.5%)",
            "P_bot_5_0": "P(cerca de suelo ZZ 5.0%) — PRINCIPAL",
            "P_bot_7_5": "P(cerca de suelo ZZ 7.5%) — estructural",
            "P_top_2_5": "P(cerca de techo ZZ 2.5%)",
            "P_top_5_0": "P(cerca de techo ZZ 5.0%) — PRINCIPAL",
            "P_top_7_5": "P(cerca de techo ZZ 7.5%) — estructural",
            "lift_bot_5_0": "P_bot celda / P_bot global. >1 = más suelos que promedio",
            "lift_top_5_0": "P_top celda / P_top global. >1 = más techos que promedio",
            "net_bias": "P_bot - P_top. Positivo = sesgo a suelo (acumulación). Negativo = distribución",
        },
        "tier_pooling": {
            "purpose": "Sectores agrupados por comportamiento. L1 si N≥MIN_N, fallback a L2 global.",
            "L1_tiers": TIERS,
            "min_n_l1": MIN_N_L1,
        },
        "operational_interpretation": {
            "ACCUMULATION": "net_bias > +0.10 → favorece entrada",
            "DISTRIBUTION": "net_bias < -0.10 → reduce sizing o espera",
            "NEUTRAL": "entre -0.10 y +0.10 → sin sesgo claro",
        },
    },
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
    "generated_by": "backend/scripts/train_s5_triad.py",
    "_metadata": {
        "purpose": (
            "Modificador relativo para S5 Price Breadth. Mide la diferencia simple "
            "FI_sector - FI_spy (en puntos porcentuales). Si un sector tiene más stocks "
            "arriba de su MA50 que el SPY, se le da un boost al P_bot."
        ),
        "formula": "rel_fi = S5_{ETF}_FI - S5FI (diferencia en pp)",
        "bins": {
            "<<": "rel_fi < -30pp → sector muy por debajo del mercado",
            "<": "-30 ≤ rel_fi < -10pp → sector ligeramente bajo",
            "~": "-10 ≤ rel_fi < +10pp → alineado con mercado",
            ">": "+10 ≤ rel_fi < +30pp → sector ligeramente arriba",
            ">>": "rel_fi ≥ +30pp → sector muy por encima del mercado",
        },
        "bin_fields": {
            "n": "Observaciones en este bin",
            "P_bot_5_0 / P_top_5_0": "Probabilidades ZZ 5.0% en este bin",
            "bot_factor": "Multiplicador sobre P_bot. >1 = amplifica señal de suelo",
            "top_factor": "Multiplicador sobre P_top. >1 = amplifica señal de techo",
        },
        "application": "adj_P_bot = P_bot_triad × rel_bot_factor",
    },
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
print(f"  Triad table: {n_cells_total} cells (of 250 possible)")
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
