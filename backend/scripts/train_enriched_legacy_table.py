#!/usr/bin/env python3
"""
Train Enriched Legacy Probability Table — Full S&P 500 Universe
================================================================
Retrains rc_probability_table.json using ALL 505 stocks in the Vault
(not just the 17 training tickers), and enriches each cell with
stereotype run-length composition:

  avg_HH_run, max_HH_run, N_HH_runs,
  avg_HL_run, max_HL_run, N_HL_runs,
  avg_LH_run, max_LH_run, N_LH_runs,
  avg_LL_run, max_LL_run, N_LL_runs

Output:
  - backend/modules/quality_swing/domain/rules/rc_probability_table_enriched.json
  - Log: /tmp/train_enriched_legacy.log

Usage (background, survives session close):
  nohup bash -c 'PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
    backend/scripts/train_enriched_legacy_table.py' \
    > /tmp/train_enriched_legacy.log 2>&1 &

Estimated time: ~30-60 min (505 tickers × ~1000 bars × compute_channel_snapshot)
"""
import os, sys, time, json, logging
from pathlib import Path
from collections import defaultdict

import numpy as np

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.rules.compute_channel import compute_channel_snapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════
MIN_BARS = 250
ZIGZAG_PCT = 0.025
MIN_CELL_N = 10  # Minimum observations per cell for inclusion

SIGMA_BINS = [
    (-999, -1.0, "<<"), (-1.0, -0.3, "<"), (-0.3, 0.3, "~"),
    (0.3, 1.0, ">"), (1.0, 999, ">>"),
]

# 6 Tide bins matching original Legacy table
TIDE_BINS = [
    (-999, -0.03, "T---"),
    (-0.03, -0.01, "T--"),
    (-0.01, 0.0, "T-"),
    (0.0, 0.01, "T+"),
    (0.01, 0.03, "T++"),
    (0.03, 999, "T+++"),
]

OUTPUT_PATH = root_dir / "backend/modules/quality_swing/domain/rules/rc_probability_table_enriched.json"


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════
def sigma_bin(val: float) -> str:
    for lo, hi, label in SIGMA_BINS:
        if lo <= val < hi:
            return label
    return ">>"


def tide_bin(slope: float) -> str:
    """Classify tide slope into 6 bins matching Legacy table."""
    for lo, hi, label in TIDE_BINS:
        if lo <= slope < hi:
            return label
    return "T+++"


def get_stock_universe(store: TimescaleDataStore) -> list[str]:
    """Get clean S&P 500 stock universe from Vault."""
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT tm.ticker
                FROM market.ticker_metadata tm
                JOIN market.ohlcv_bars b ON b.ticker = tm.ticker AND b.timeframe = '1d'
                WHERE tm.asset_type = 'STOCK'
                  AND tm.sector NOT IN ('Breadth','Options Flow','Sentiment','Commodities',
                                        'Fixed Income','Currency','Yields','International',
                                        'Broad Market','Volatility')
                  AND tm.ticker NOT LIKE 'UW_%%'
                  AND tm.industry NOT IN ('ETF','INDICATOR','Breadth Index','Equity Index')
                  AND LENGTH(tm.ticker) <= 5
                GROUP BY tm.ticker
                HAVING COUNT(b.time) >= %s
                ORDER BY tm.ticker
            """, (MIN_BARS,))
            return [r[0] for r in cur.fetchall()]
    finally:
        store._put(conn)


def load_zigzag_pivots(store: TimescaleDataStore, ticker: str, level: float) -> list:
    """Load canonical zigzag pivots from engine.zigzag_points.

    Returns list of (tp_type, bar_index, price) matching the OHLCV bar indices.
    """
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT timestamp, tp_type, price
                FROM engine.zigzag_points
                WHERE ticker = %s AND min_swing_pct = %s
                ORDER BY timestamp
            """, (ticker, level))
            return cur.fetchall()
    finally:
        store._put(conn)


def map_pivots_to_bar_indices(pivot_rows, ohlc_index) -> list:
    """Map DB pivot timestamps to bar indices in the OHLCV DataFrame.

    Returns list of (tp_type, bar_index, price) tuples.
    """
    # Build timestamp → index lookup
    ts_to_idx = {}
    for i, ts in enumerate(ohlc_index):
        # Normalize: compare as date to handle timezone mismatches
        if hasattr(ts, 'date'):
            ts_to_idx[ts.date()] = i
        else:
            ts_to_idx[ts] = i

    pivots = []
    for db_ts, tp_type, price in pivot_rows:
        if hasattr(db_ts, 'date'):
            key = db_ts.date()
        else:
            key = db_ts

        idx = ts_to_idx.get(key)
        if idx is not None:
            pivots.append((tp_type, idx, float(price)))

    return pivots


def assign_bar_stereotypes(close: np.ndarray, pivots: list) -> list:
    """Assign each bar its zigzag cycle stereotype (HH/HL/LH/LL).

    A stereotype classifies a COMPLETE CYCLE (one zig + one zag):
      - 1st letter: Zig (MAX) vs previous Zig → H if higher, L if lower
      - 2nd letter: Zag (MIN) vs previous Zag → H if higher, L if lower

    So HH = Higher High + Higher Low (uptrend)
       HL = Higher High + Lower Low  (widening/distribution)
       LH = Lower High + Higher Low  (compression/accumulation)
       LL = Lower High + Lower Low   (downtrend)

    All bars within a cycle inherit the cycle's stereotype.
    """
    bar_st = [None] * len(close)
    if len(pivots) < 4:
        return bar_st

    # Separate zigs and zags
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
        for b in range(cycle_start, min(cycle_end + 1, len(close))):
            bar_st[b] = st

    last_st = None
    for b in range(len(close)):
        if bar_st[b] is not None:
            last_st = bar_st[b]
        elif last_st is not None:
            bar_st[b] = last_st

    return bar_st


def process_ticker(store: TimescaleDataStore, ticker: str):
    """Process one ticker: read canonical zigzag from DB, compute RC states.

    Returns list of (state_key, stereotype) tuples for each bar.
    Also returns run data: {state_key: {stereotype: [run_lengths]}}.
    """
    ohlc = store.load_bars(ticker, "1d")
    if ohlc is None or len(ohlc) < MIN_BARS:
        return [], {}

    close = ohlc["close"].values.astype(float)
    high = ohlc["high"].values.astype(float)
    low = ohlc["low"].values.astype(float)
    volume = ohlc["volume"].values.astype(float)

    # Read canonical zigzag from DB (NOT computed on-the-fly)
    pivot_rows = load_zigzag_pivots(store, ticker, ZIGZAG_PCT)
    if len(pivot_rows) < 4:
        return [], {}
    pivots = map_pivots_to_bar_indices(pivot_rows, ohlc.index)
    bar_stereotypes = assign_bar_stereotypes(close, pivots)

    # Per-bar: (state_key, stereotype)
    observations = []  # (state_key, stereotype)
    state_runs = defaultdict(lambda: defaultdict(list))

    prev_state = None
    prev_st = None
    run_len = 0

    for idx in range(MIN_BARS, len(close)):
        st = bar_stereotypes[idx]
        if st is None:
            continue

        ch = compute_channel_snapshot(close, high, low, volume, idx)
        if ch is None:
            continue

        tb = tide_bin(ch.tide_slope)
        sc = sigma_bin(ch.sigma_current)
        sw = sigma_bin(ch.sigma_wave)
        svw = sigma_bin(ch.vwap_sigma_wave)
        state_key = f"{tb}|{sc}|{sw}|{svw}"

        observations.append((state_key, st))

        # Track runs within same state
        if state_key == prev_state and st == prev_st:
            run_len += 1
        else:
            if prev_state and prev_st and run_len > 0:
                state_runs[prev_state][prev_st].append(run_len)
            run_len = 1
            prev_state = state_key
            prev_st = st

    # Flush last run
    if prev_state and prev_st and run_len > 0:
        state_runs[prev_state][prev_st].append(run_len)

    return observations, dict(state_runs)


def _build_cell(counts: dict, runs: dict, level: str) -> dict:
    """Build a single cell with 16 raw fields."""
    cell = {"level": level}
    for st in ["HH", "HL", "LH", "LL"]:
        cell[f"count_{st}"] = counts[st]
        r = runs.get(st, [])
        cell[f"N_{st}_runs"] = len(r)
        if r:
            arr = np.array(r)
            cell[f"max_{st}_run"] = int(arr.max())
            cell[f"min_{st}_run"] = int(arr.min())
        else:
            cell[f"max_{st}_run"] = 0
            cell[f"min_{st}_run"] = 0
    return cell


def build_enriched_table(
    all_observations: list[tuple[str, str]],
    all_runs: dict[str, dict[str, list[int]]],
) -> dict:
    """Build the enriched probability table from aggregated data.

    Each cell stores 16 raw fields:
      count_HH, count_HL, count_LH, count_LL     (4 observation counts)
      N_HH_runs, N_HL_runs, N_LH_runs, N_LL_runs (4 run counts)
      max_HH_run, max_HL_run, max_LH_run, max_LL_run (4 max run lengths)
      min_HH_run, min_HL_run, min_LH_run, min_LL_run (4 min run lengths)

    All derived values (P_bull, avg_XX_run, N, confidence) are computable
    from these at lookup time.
    """

    # Aggregate observations per state
    state_counts = defaultdict(lambda: {"HH": 0, "HL": 0, "LH": 0, "LL": 0})
    for state_key, st in all_observations:
        state_counts[state_key][st] += 1

    cells = {}

    # ── L1: Full state (Tide + σc + σw + σVw) ──
    for state_key, counts in state_counts.items():
        n = sum(counts.values())
        if n < MIN_CELL_N:
            continue
        runs = all_runs.get(state_key, {})
        cells[f"L1_full:{state_key}"] = _build_cell(counts, runs, "L1_full")

    # ── L2: No tide (σc + σw + σVw) ──
    l2_counts = defaultdict(lambda: {"HH": 0, "HL": 0, "LH": 0, "LL": 0})
    l2_runs = defaultdict(lambda: defaultdict(list))
    for state_key, counts in state_counts.items():
        parts = state_key.split("|")
        l2_key = "|".join(parts[1:])
        for st in ["HH", "HL", "LH", "LL"]:
            l2_counts[l2_key][st] += counts[st]
        runs = all_runs.get(state_key, {})
        for st, rl_list in runs.items():
            l2_runs[l2_key][st].extend(rl_list)

    for l2_key, counts in l2_counts.items():
        n = sum(counts.values())
        if n < MIN_CELL_N:
            continue
        key = f"L2_no_tide:{l2_key}"
        if key not in cells:
            cells[key] = _build_cell(counts, l2_runs[l2_key], "L2_no_tide")

    # ── L3: σc + σVw only ──
    l3_counts = defaultdict(lambda: {"HH": 0, "HL": 0, "LH": 0, "LL": 0})
    l3_runs = defaultdict(lambda: defaultdict(list))
    for state_key, counts in state_counts.items():
        parts = state_key.split("|")
        l3_key = f"{parts[1]}|{parts[3]}"
        for st in ["HH", "HL", "LH", "LL"]:
            l3_counts[l3_key][st] += counts[st]
        runs = all_runs.get(state_key, {})
        for st, rl_list in runs.items():
            l3_runs[l3_key][st].extend(rl_list)

    for l3_key, counts in l3_counts.items():
        n = sum(counts.values())
        if n < MIN_CELL_N:
            continue
        key = f"L3_sc_svw:{l3_key}"
        if key not in cells:
            cells[key] = _build_cell(counts, l3_runs[l3_key], "L3_sc_svw")

    # ── L4: σVw only ──
    l4_counts = defaultdict(lambda: {"HH": 0, "HL": 0, "LH": 0, "LL": 0})
    l4_runs = defaultdict(lambda: defaultdict(list))
    for state_key, counts in state_counts.items():
        parts = state_key.split("|")
        l4_key = parts[3]
        for st in ["HH", "HL", "LH", "LL"]:
            l4_counts[l4_key][st] += counts[st]
        runs = all_runs.get(state_key, {})
        for st, rl_list in runs.items():
            l4_runs[l4_key][st].extend(rl_list)

    for l4_key, counts in l4_counts.items():
        n = sum(counts.values())
        if n < MIN_CELL_N:
            continue
        key = f"L4_svw:{l4_key}"
        if key not in cells:
            cells[key] = _build_cell(counts, l4_runs[l4_key], "L4_svw")


    return cells


def main():
    t0 = time.time()
    store = TimescaleDataStore()

    # 1. Get stock universe
    tickers = get_stock_universe(store)
    logger.info(f"Stock universe: {len(tickers)} tickers")

    # 2. Process each ticker
    all_observations = []
    all_runs = defaultdict(lambda: defaultdict(list))
    processed = 0
    failed = 0

    for i, ticker in enumerate(tickers):
        try:
            obs, runs = process_ticker(store, ticker)
            all_observations.extend(obs)
            for state_key, st_runs in runs.items():
                for st, rl_list in st_runs.items():
                    all_runs[state_key][st].extend(rl_list)
            processed += 1

            if (i + 1) % 25 == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed * 60
                eta = (len(tickers) - i - 1) / rate
                logger.info(
                    f"  Progress: {i+1}/{len(tickers)} tickers "
                    f"({processed} ok, {failed} failed) "
                    f"| {len(all_observations):,} obs "
                    f"| {elapsed/60:.1f}min elapsed, ~{eta:.1f}min remaining"
                )
        except Exception as e:
            failed += 1
            logger.warning(f"  ⚠️  {ticker} failed: {e}")

    logger.info(
        f"Processing complete: {processed}/{len(tickers)} tickers, "
        f"{len(all_observations):,} total observations"
    )

    # 3. Build enriched table
    logger.info("Building enriched probability table...")
    cells = build_enriched_table(all_observations, dict(all_runs))

    # 4. Stats
    l1_cells = [k for k in cells if k.startswith("L1_")]
    l2_cells = [k for k in cells if k.startswith("L2_")]
    l3_cells = [k for k in cells if k.startswith("L3_")]
    l4_cells = [k for k in cells if k.startswith("L4_")]

    logger.info(f"Table built: {len(cells)} total cells")
    logger.info(f"  L1 (full):     {len(l1_cells)} cells")
    logger.info(f"  L2 (no_tide):  {len(l2_cells)} cells")
    logger.info(f"  L3 (σc+σVw):   {len(l3_cells)} cells")
    logger.info(f"  L4 (σVw):      {len(l4_cells)} cells")

    # Sample enriched cell
    for key in sorted(l1_cells, key=lambda k: -(
        cells[k]["count_HH"] + cells[k]["count_HL"] +
        cells[k]["count_LH"] + cells[k]["count_LL"]
    ))[:3]:
        c = cells[key]
        n = c["count_HH"] + c["count_HL"] + c["count_LH"] + c["count_LL"]
        p_bull = (c["count_HH"] + c["count_HL"]) / n if n else 0
        logger.info(
            f"  Sample: {key} → N={n} P_bull={p_bull:.2f} "
            f"counts=[HH:{c['count_HH']} HL:{c['count_HL']} "
            f"LH:{c['count_LH']} LL:{c['count_LL']}] "
            f"max_runs=[HH:{c['max_HH_run']} HL:{c['max_HL_run']} "
            f"LH:{c['max_LH_run']} LL:{c['max_LL_run']}]"
        )

    # 5. Save with metadata header (matching original Legacy format)
    total_obs = len(all_observations)
    output = {
        "version": "v2_enriched_2026-06-25",
        "zigzag_level": ZIGZAG_PCT,
        "n_tickers": processed,
        "n_total_observations": total_obs,
        "sigma_bins": {label: [lo, hi] for lo, hi, label in SIGMA_BINS},
        "tide_bins": {label: [lo, hi] for lo, hi, label in TIDE_BINS},
        "n_cells": {
            "L1_full": len(l1_cells),
            "L2_no_tide": len(l2_cells),
            "L3_sc_svw": len(l3_cells),
            "L4_svw": len(l4_cells),
        },
        "cells": cells,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    elapsed = time.time() - t0
    logger.info(f"✅ Saved to {OUTPUT_PATH}")
    logger.info(f"Total time: {elapsed/60:.1f} minutes")


if __name__ == "__main__":
    main()
