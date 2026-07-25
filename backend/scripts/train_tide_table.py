#!/usr/bin/env python3
"""
Train Combined T×C×σVw Probability Table + Zigzag Coincidence Audit
====================================================================
Two outputs:
  1. rc_combined_probability_table.json — T(6)×C(6)×σVw(5) = 180 L1 states
     - 16 stereotype fields (count/N_runs/max/min per HH/HL/LH/LL)
     - 6 zigzag T=0 coincidence counts (zz25/50/75 × MIN/MAX)
     - 6 zigzag T-1 predictive counts
     → Total: 28 raw fields per cell

  2. zigzag_rc_audit.json — For every zigzag pivot in the DB:
     What is the RC channel state at that exact bar?
     Produces frequency tables per zigzag level × type.

All data from Vault:
  - engine.channel_snapshots (640K rows, 547 tickers)
  - engine.zigzag_points (265K pivots, 507 tickers, 3 levels)

Usage:
  nohup bash -c 'PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
    backend/scripts/train_combined_table.py' \
    > /tmp/train_combined.log 2>&1 &
"""
import os, sys, json, time, logging
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

import numpy as np

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════
ZIGZAG_LEVELS = [0.025, 0.05, 0.075]
ZIGZAG_LABEL = {0.025: "zz25", 0.05: "zz50", 0.075: "zz75"}
STEREOTYPE_PCT = 0.025  # Zigzag level for stereotypes
MIN_OBS_L1 = 10
OUTPUT_TABLE = root_dir / "backend/modules/quality_swing/domain/rules/rc_combined_probability_table.json"
OUTPUT_AUDIT = root_dir / "backend/modules/quality_swing/domain/rules/rc_zigzag_audit.json"

# Slope thresholds — from rc_slope_classifier.py
SLOPE_TH = {
    "T": {"+": (0.0456, 0.0983), "-": (0.0263, 0.0765)},
    "C": {"+": (0.0845, 0.1749), "-": (0.0613, 0.1583)},
}

# Sigma bins for σ_vwap_wave — from enriched table
SIGMA_BINS = [
    (-999, -1.0, "<<"),
    (-1.0, -0.3, "<"),
    (-0.3,  0.3, "~"),
    ( 0.3,  1.0, ">"),
    ( 1.0,  999, ">>"),
]


# ═══════════════════════════════════════════════════════════════
# Classification
# ═══════════════════════════════════════════════════════════════
def classify_slope(value: float, channel: str) -> str:
    """Classify slope into +++/++/+/-/--/--- for T or C channels."""
    th = SLOPE_TH[channel]
    if value >= 0:
        p33, p66 = th["+"]
        if value >= p66:
            return f"{channel}+++"
        elif value >= p33:
            return f"{channel}++"
        else:
            return f"{channel}+"
    else:
        p33, p66 = th["-"]
        av = abs(value)
        if av >= p66:
            return f"{channel}---"
        elif av >= p33:
            return f"{channel}--"
        else:
            return f"{channel}-"


def classify_sigma_vw(value: float) -> str:
    """Classify σ_vwap_wave into <</</ ~/>/>>."""
    for lo, hi, label in SIGMA_BINS:
        if lo <= value < hi:
            return label
    return ">>"


# ═══════════════════════════════════════════════════════════════
# Stereotype logic
# ═══════════════════════════════════════════════════════════════
def assign_bar_stereotypes(n_bars: int, pivots: list) -> list:
    """Assign HH/HL/LH/LL stereotype to each bar."""
    bar_st = [None] * n_bars
    if len(pivots) < 4:
        return bar_st

    maxes = [(idx, val) for t, idx, val in pivots if t == "MAX"]
    mins = [(idx, val) for t, idx, val in pivots if t == "MIN"]

    if len(maxes) < 2 or len(mins) < 2:
        return bar_st

    zig_labels = []
    for i in range(1, len(maxes)):
        label = "H" if maxes[i][1] > maxes[i - 1][1] else "L"
        zig_labels.append((maxes[i][0], label))

    zag_labels = []
    for i in range(1, len(mins)):
        label = "H" if mins[i][1] > mins[i - 1][1] else "L"
        zag_labels.append((mins[i][0], label))

    zi, za = 0, 0
    cycles = []
    while zi < len(zig_labels) and za < len(zag_labels):
        zig_idx, zig_l = zig_labels[zi]
        zag_idx, zag_l = zag_labels[za]
        stereotype = zig_l + zag_l
        cycle_start = min(zig_idx, zag_idx)
        cycle_end = max(zig_idx, zag_idx)
        cycles.append((cycle_start, cycle_end, stereotype))
        zi += 1
        za += 1

    for cycle_start, cycle_end, st in cycles:
        for b in range(cycle_start, min(cycle_end + 1, n_bars)):
            bar_st[b] = st

    last_st = None
    for b in range(n_bars):
        if bar_st[b] is not None:
            last_st = bar_st[b]
        elif last_st is not None:
            bar_st[b] = last_st

    return bar_st


# ═══════════════════════════════════════════════════════════════
# Data loading — single bulk query per ticker
# ═══════════════════════════════════════════════════════════════
def load_ticker_full(store, ticker):
    """Load channel_snapshots + all zigzag pivots for a ticker.

    Returns:
        snapshots: list of (timestamp, tide_slope, current_slope, vwap_sigma_wave)
        zz_sets: {level: {(date, tp_type)}} — set of zigzag pivot dates per level
        st_pivots: list of (tp_type, bar_idx, price) for STEREOTYPE_PCT level
    """
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            # Channel snapshots — T, C, σVw
            cur.execute("""
                SELECT timestamp, tide_slope, current_slope, vwap_sigma_wave
                FROM engine.channel_snapshots
                WHERE ticker = %s
                  AND tide_slope IS NOT NULL
                  AND current_slope IS NOT NULL
                  AND vwap_sigma_wave IS NOT NULL
                ORDER BY timestamp
            """, (ticker,))
            snapshots = cur.fetchall()

            # ALL zigzag pivots (3 levels)
            cur.execute("""
                SELECT min_swing_pct, timestamp, tp_type, price
                FROM engine.zigzag_points
                WHERE ticker = %s
                ORDER BY min_swing_pct, timestamp
            """, (ticker,))
            zz_all = cur.fetchall()

        # Build lookup sets per level
        zz_sets = {level: {} for level in ZIGZAG_LEVELS}
        for level, ts, tp_type, price in zz_all:
            lvl = float(level)
            if lvl in zz_sets:
                key = ts.date() if hasattr(ts, 'date') else ts
                zz_sets[lvl][key] = tp_type

        # Build stereotype pivots (bar_idx mapping for STEREOTYPE_PCT)
        st_pivot_rows = [(ts, tp_type, price) for lvl, ts, tp_type, price in zz_all
                         if float(lvl) == STEREOTYPE_PCT]

        # Map to bar indices
        ts_to_idx = {}
        for i, (ts, *_) in enumerate(snapshots):
            key = ts.date() if hasattr(ts, 'date') else ts
            ts_to_idx[key] = i

        st_pivots = []
        for ts, tp_type, price in st_pivot_rows:
            key = ts.date() if hasattr(ts, 'date') else ts
            idx = ts_to_idx.get(key)
            if idx is not None:
                st_pivots.append((tp_type, idx, float(price)))

        return snapshots, zz_sets, st_pivots
    finally:
        store._put(conn)


def get_universe(store):
    """Get tickers with snapshots."""
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ticker
                FROM engine.channel_snapshots
                ORDER BY ticker
            """)
            return [r[0] for r in cur.fetchall()]
    finally:
        store._put(conn)


# ═══════════════════════════════════════════════════════════════
# Process ticker
# ═══════════════════════════════════════════════════════════════
def process_ticker(store, ticker):
    """Process one ticker: classify T×C×σVw + stereotypes + zigzag coincidence.

    Returns:
        observations: [(state_key, stereotype)]
        state_runs: {state_key: {st: [run_lengths]}}
        zz_hits: {state_key: {zz_label: count}}  — exact zigzag coincidences (T=0)
        zz_prev_hits: {state_key: {zz_label: count}} — bar BEFORE pivot (T-1, predictive)
        audit_rows: [(zz_level, tp_type, state_key, stereotype)]
    """
    snapshots, zz_sets, st_pivots = load_ticker_full(store, ticker)
    if len(snapshots) < 250:
        return [], {}, {}, []

    n_bars = len(snapshots)

    # Stereotypes from 2.5% zigzag
    bar_stereotypes = assign_bar_stereotypes(n_bars, st_pivots)

    observations = []
    state_runs = defaultdict(lambda: defaultdict(list))
    zz_hits = defaultdict(lambda: defaultdict(int))
    zz_prev_hits = defaultdict(lambda: defaultdict(int))  # T-1 predictive
    audit_rows = []

    # Pre-classify ALL bars for T-1 lookback
    bar_states = []  # [(state_key, bar_date)] for all bars
    for idx_pre in range(n_bars):
        ts_pre, t_slope, c_slope, svw_val = snapshots[idx_pre]
        bar_states.append((
            f"{classify_slope(t_slope, 'T')}|{classify_slope(c_slope, 'C')}|{classify_sigma_vw(svw_val)}",
            ts_pre.date() if hasattr(ts_pre, 'date') else ts_pre,
        ))

    prev_state = None
    prev_st = None
    run_len = 0

    for idx in range(n_bars):
        ts, t_slope, c_slope, vwap_sigma_wave = snapshots[idx]
        st = bar_stereotypes[idx]
        if st is None:
            continue

        t = classify_slope(t_slope, 'T')
        c = classify_slope(c_slope, 'C')
        svw = classify_sigma_vw(vwap_sigma_wave)
        state_key = f"{t}|{c}|{svw}"

        observations.append((state_key, st))

        # Track runs
        if state_key == prev_state and st == prev_st:
            run_len += 1
        else:
            if prev_state and prev_st and run_len > 0:
                state_runs[prev_state][prev_st].append(run_len)
            run_len = 1
            prev_state = state_key
            prev_st = st

        # Check zigzag coincidence — does THIS bar match a pivot?
        bar_date = ts.date() if hasattr(ts, 'date') else ts
        for level in ZIGZAG_LEVELS:
            tp_type = zz_sets[level].get(bar_date)
            if tp_type is not None:
                label = ZIGZAG_LABEL[level]
                zz_key = f"{label}_{tp_type.lower()}"  # e.g. "zz25_min", "zz50_max"
                zz_hits[state_key][zz_key] += 1
                audit_rows.append((level, tp_type, state_key, st))

                # T-1: what state was the PREVIOUS bar? (predictive)
                if idx > 0:
                    prev_state_key = bar_states[idx - 1][0]
                    zz_prev_hits[prev_state_key][f"{zz_key}_prev"] += 1

    # Flush last run
    if prev_state and prev_st and run_len > 0:
        state_runs[prev_state][prev_st].append(run_len)

    return observations, dict(state_runs), dict(zz_hits), dict(zz_prev_hits), audit_rows


# ═══════════════════════════════════════════════════════════════
# Cell builder
# ═══════════════════════════════════════════════════════════════
def _build_cell(counts, runs, zz_counts, zz_prev_counts, level_str):
    """Build cell with 16 stereotype + 6 zigzag T=0 + 6 zigzag T-1 = 28 raw fields."""
    cell = {"level": level_str}

    # Stereotype fields (16)
    for st in ["HH", "HL", "LH", "LL"]:
        cell[f"count_{st}"] = counts[st]
        r = runs.get(st, [])
        cell[f"N_{st}_runs"] = len(r)
        cell[f"max_{st}_run"] = max(r) if r else 0
        cell[f"min_{st}_run"] = min(r) if r else 0

    # Zigzag coincidence fields — T=0 (exact match, 6 fields)
    for zz_key in ["zz25_min", "zz25_max", "zz50_min", "zz50_max", "zz75_min", "zz75_max"]:
        cell[zz_key] = zz_counts.get(zz_key, 0)

    # Zigzag T-1 — bar BEFORE pivot (predictive, 6 fields)
    for zz_key in ["zz25_min_prev", "zz25_max_prev", "zz50_min_prev", "zz50_max_prev",
                   "zz75_min_prev", "zz75_max_prev"]:
        cell[zz_key] = zz_prev_counts.get(zz_key, 0)

    return cell


def build_table(all_obs, all_runs, all_zz, all_zz_prev):
    """Build multi-level probability table."""
    cells = {}

    # ── L1: Full (W|A|σVw) ──
    l1_counts = defaultdict(lambda: defaultdict(int))
    l1_runs = defaultdict(lambda: defaultdict(list))
    l1_zz = defaultdict(lambda: defaultdict(int))
    l1_zz_prev = defaultdict(lambda: defaultdict(int))

    for state_key, st in all_obs:
        l1_counts[state_key][st] += 1

    for state_key, st_runs in all_runs.items():
        for st, runs in st_runs.items():
            l1_runs[state_key][st].extend(runs)

    for state_key, zz_map in all_zz.items():
        for zz_key, count in zz_map.items():
            l1_zz[state_key][zz_key] += count

    for state_key, zz_map in all_zz_prev.items():
        for zz_key, count in zz_map.items():
            l1_zz_prev[state_key][zz_key] += count

    n_l1 = 0
    for key in sorted(l1_counts):
        n = sum(l1_counts[key].values())
        if n >= MIN_OBS_L1:
            cells[f"L1_full:{key}"] = _build_cell(
                l1_counts[key], l1_runs[key], l1_zz[key], l1_zz_prev[key], "L1_full"
            )
            n_l1 += 1

    # ── L2: T|σVw (collapse C) ──
    l2_counts = defaultdict(lambda: defaultdict(int))
    l2_runs = defaultdict(lambda: defaultdict(list))
    l2_zz = defaultdict(lambda: defaultdict(int))
    l2_zz_prev = defaultdict(lambda: defaultdict(int))

    for state_key, st in all_obs:
        parts = state_key.split("|")
        l2_key = f"{parts[0]}|{parts[2]}"
        l2_counts[l2_key][st] += 1

    for state_key, st_runs in all_runs.items():
        parts = state_key.split("|")
        l2_key = f"{parts[0]}|{parts[2]}"
        for st, runs in st_runs.items():
            l2_runs[l2_key][st].extend(runs)

    for state_key, zz_map in all_zz.items():
        parts = state_key.split("|")
        l2_key = f"{parts[0]}|{parts[2]}"
        for zz_key, count in zz_map.items():
            l2_zz[l2_key][zz_key] += count

    for state_key, zz_map in all_zz_prev.items():
        parts = state_key.split("|")
        l2_key = f"{parts[0]}|{parts[2]}"
        for zz_key, count in zz_map.items():
            l2_zz_prev[l2_key][zz_key] += count

    n_l2 = 0
    for key in sorted(l2_counts):
        cells[f"L2_t_svw:{key}"] = _build_cell(
            l2_counts[key], l2_runs[key], l2_zz[key], l2_zz_prev[key], "L2_t_svw"
        )
        n_l2 += 1

    # ── L3: σVw only ──
    l3_counts = defaultdict(lambda: defaultdict(int))
    l3_runs = defaultdict(lambda: defaultdict(list))
    l3_zz = defaultdict(lambda: defaultdict(int))
    l3_zz_prev = defaultdict(lambda: defaultdict(int))

    for state_key, st in all_obs:
        parts = state_key.split("|")
        l3_key = parts[2]  # σVw only
        l3_counts[l3_key][st] += 1

    for state_key, st_runs in all_runs.items():
        parts = state_key.split("|")
        l3_key = parts[2]
        for st, runs in st_runs.items():
            l3_runs[l3_key][st].extend(runs)

    for state_key, zz_map in all_zz.items():
        parts = state_key.split("|")
        l3_key = parts[2]
        for zz_key, count in zz_map.items():
            l3_zz[l3_key][zz_key] += count

    for state_key, zz_map in all_zz_prev.items():
        parts = state_key.split("|")
        l3_key = parts[2]
        for zz_key, count in zz_map.items():
            l3_zz_prev[l3_key][zz_key] += count

    n_l3 = 0
    for key in sorted(l3_counts):
        cells[f"L3_svw:{key}"] = _build_cell(
            l3_counts[key], l3_runs[key], l3_zz[key], l3_zz_prev[key], "L3_svw"
        )
        n_l3 += 1

    return cells, {"L1_full": n_l1, "L2_t_svw": n_l2, "L3_svw": n_l3}


# ═══════════════════════════════════════════════════════════════
# Audit builder
# ═══════════════════════════════════════════════════════════════
def build_audit(all_audit_rows):
    """Build the zigzag RC audit: what does RC look like at every turning point?

    For each (zigzag_level, tp_type), produces:
      - Distribution of T|C|σVw states
      - Distribution of stereotypes
      - Top 10 most frequent patterns
    """
    audit = {}

    # Group by level × type
    groups = defaultdict(list)
    for level, tp_type, state_key, stereotype in all_audit_rows:
        key = f"{ZIGZAG_LABEL[level]}_{tp_type.lower()}"
        groups[key].append((state_key, stereotype))

    for group_key in sorted(groups):
        rows = groups[group_key]
        n = len(rows)

        # State distribution
        state_counts = Counter(sk for sk, _ in rows)
        st_counts = Counter(st for _, st in rows)

        # Combined: state + stereotype
        combo_counts = Counter(rows)

        # Top patterns
        top_states = state_counts.most_common(15)
        top_combos = combo_counts.most_common(15)

        audit[group_key] = {
            "total_pivots": n,
            "unique_states": len(state_counts),
            "stereotype_distribution": dict(st_counts),
            "stereotype_P": {st: round(c / n, 4) for st, c in st_counts.items()},
            "top_states": [
                {"state": s, "count": c, "pct": round(c / n * 100, 2)}
                for s, c in top_states
            ],
            "top_combos": [
                {"state": s, "stereotype": st, "count": c, "pct": round(c / n * 100, 2)}
                for (s, st), c in top_combos
            ],
        }

    return audit


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════
def main():
    t0 = time.time()
    logger.info("=" * 90)
    logger.info("  TRAIN COMBINED T×C×σVw TABLE + ZIGZAG COINCIDENCE AUDIT")
    logger.info("  T(6) × C(6) × σVw(5) = 180 L1 states")
    logger.info("  + 6 zigzag T=0 + 6 zigzag T-1 (predictive) per cell")
    logger.info("  Source: engine.channel_snapshots + engine.zigzag_points (3 levels)")
    logger.info("=" * 90)

    store = TimescaleDataStore()
    tickers = get_universe(store)
    logger.info(f"Universe: {len(tickers)} tickers")

    all_obs = []
    all_runs = defaultdict(lambda: defaultdict(list))
    all_zz = defaultdict(lambda: defaultdict(int))
    all_zz_prev = defaultdict(lambda: defaultdict(int))
    all_audit = []
    processed = 0
    failed = 0

    for i, ticker in enumerate(tickers):
        try:
            obs, runs, zz_hits, zz_prev_hits, audit_rows = process_ticker(store, ticker)
            all_obs.extend(obs)
            for sk, sr in runs.items():
                for st, rl in sr.items():
                    all_runs[sk][st].extend(rl)
            for sk, zm in zz_hits.items():
                for zk, c in zm.items():
                    all_zz[sk][zk] += c
            for sk, zm in zz_prev_hits.items():
                for zk, c in zm.items():
                    all_zz_prev[sk][zk] += c
            all_audit.extend(audit_rows)
            processed += 1

            if (i + 1) % 50 == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed
                eta = (len(tickers) - i - 1) / rate
                zz_total = sum(sum(zm.values()) for zm in all_zz.values())
                logger.info(
                    f"  [{i+1}/{len(tickers)}] {ticker}: "
                    f"obs={len(all_obs):,} | zz_hits={zz_total:,} | "
                    f"{elapsed:.0f}s elapsed, ~{eta:.0f}s ETA"
                )
        except Exception as e:
            failed += 1
            logger.warning(f"  ⚠️  {ticker}: {e}")

    logger.info(f"\nProcessed: {processed}/{len(tickers)} ({failed} failed)")
    logger.info(f"Total observations: {len(all_obs):,}")
    logger.info(f"Total zigzag coincidences: {sum(sum(zm.values()) for zm in all_zz.values()):,}")
    logger.info(f"Total audit rows: {len(all_audit):,}")

    # ── Build combined table ──
    logger.info("\nBuilding combined T×C×σVw table...")
    cells, n_cells = build_table(all_obs, dict(all_runs), dict(all_zz), dict(all_zz_prev))

    # Compute global zigzag totals for P(state | zigzag) denominator
    global_zz_totals = {}
    for zz_key in ["zz25_min", "zz25_max", "zz50_min", "zz50_max", "zz75_min", "zz75_max"]:
        total = sum(zm.get(zz_key, 0) for zm in all_zz.values())
        global_zz_totals[zz_key] = total
    for zz_key in ["zz25_min_prev", "zz25_max_prev", "zz50_min_prev", "zz50_max_prev",
                   "zz75_min_prev", "zz75_max_prev"]:
        total = sum(zm.get(zz_key, 0) for zm in all_zz_prev.values())
        global_zz_totals[zz_key] = total

    table = {
        "version": f"v3_combined_{datetime.now().strftime('%Y-%m-%d')}",
        "dimensions": "T_slope|C_slope|sigma_vwap_wave",
        "zigzag_stereotype_level": STEREOTYPE_PCT,
        "zigzag_coincidence_levels": ZIGZAG_LEVELS,
        "n_tickers": processed,
        "n_total_observations": len(all_obs),
        "global_zigzag_totals": global_zz_totals,
        "slope_thresholds": SLOPE_TH,
        "sigma_bins": {label: [lo, hi] for lo, hi, label in SIGMA_BINS},
        "n_cells": n_cells,
        "cells": cells,
    }

    with open(OUTPUT_TABLE, "w") as f:
        json.dump(table, f, indent=2, default=str)
    logger.info(f"  Table written: {OUTPUT_TABLE} ({OUTPUT_TABLE.stat().st_size / 1024:.0f} KB)")

    # ── Build audit ──
    logger.info("\nBuilding zigzag RC audit...")
    audit = build_audit(all_audit)

    audit_doc = {
        "version": f"v1_audit_{datetime.now().strftime('%Y-%m-%d')}",
        "description": "For every zigzag pivot: what RC state (T×C×σVw) + stereotype was present?",
        "n_tickers": processed,
        "n_total_pivots": len(all_audit),
        "groups": audit,
    }

    with open(OUTPUT_AUDIT, "w") as f:
        json.dump(audit_doc, f, indent=2, default=str)
    logger.info(f"  Audit written: {OUTPUT_AUDIT} ({OUTPUT_AUDIT.stat().st_size / 1024:.0f} KB)")

    store.close()
    elapsed = time.time() - t0

    # ── Summary ──
    logger.info(f"\n{'=' * 90}")
    logger.info(f"  COMPLETE — {elapsed:.1f}s ({elapsed/60:.1f} min)")
    logger.info(f"  Combined table: {n_cells}")
    logger.info(f"  Audit groups: {len(audit)}")

    # Quick validation
    logger.info("\n  Combined table sample:")
    for key in sorted(cells)[:3]:
        c = cells[key]
        n = sum(c[f"count_{s}"] for s in ["HH","HL","LH","LL"])
        p_bull = (c["count_HH"] + c["count_HL"]) / n if n else 0
        zz_total = sum(c.get(f"{zl}_{tp}", 0) for zl in ["zz25","zz50","zz75"] for tp in ["min","max"])
        logger.info(f"    {key}: N={n:,}, P_bull={p_bull:.3f}, zz_hits={zz_total}")

    logger.info("\n  Audit sample:")
    for gk in sorted(audit)[:4]:
        g = audit[gk]
        logger.info(f"    {gk}: {g['total_pivots']:,} pivots, "
                     f"top state={g['top_states'][0]['state']} ({g['top_states'][0]['pct']:.1f}%)")

    logger.info(f"{'=' * 90}")


if __name__ == "__main__":
    main()
