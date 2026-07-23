#!/usr/bin/env python3
"""
Train Wave W×σVc×σc×vel_σVw Pivot-Prediction Table
=====================================================
Output:
  rc_wave_probability_table.json — W(6)×σVc(5)×σc(5)×vel(3) = 450 L1 states
    - stereo_counts: {HH, HL, LH, LL} per cell (causal stereotypes)
    - pre (T-1): per zigzag event: count + stereotype distribution
    - at  (T=0): per zigzag event: count + stereo_before + stereo_after

Velocity source: obs_vel_svw (Kalman) from engine.channel_snapshots.
Thresholds: P33/P67 of obs_vel_svw computed from all data → saved to metadata.

All data from Vault:
  - engine.channel_snapshots (wave_slope, vwap_sigma_current, sigma_current, vwap_sigma_wave)
  - engine.zigzag_points (3 levels: 2.5%, 5%, 7.5%)

Usage:
  nohup bash -c 'PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
    backend/scripts/train_wave_table.py' \
    > /tmp/train_wave.log 2>&1 &
"""
import os, sys, json, time, logging, math
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

import numpy as np
import pandas as pd

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
STEREOTYPE_PCT = 0.025  # Zigzag level for causal stereotypes
MIN_OBS_L1 = 10
OUTPUT_TABLE = root_dir / "backend/modules/quality_swing/domain/rules/rc_wave_probability_table.json"

# Wave slope thresholds — asymmetric
SLOPE_TH_W = {
    "+": (0.1262, 0.2717),  # W+: [0, 0.1262), W++: [0.1262, 0.2717), W+++: [0.2717, ∞)
    "-": (0.1032, 0.2598),  # W-: [-0.1032, 0), W--: [-0.2598, -0.1032), W---: (-∞, -0.2598)
}

# Sigma bins for σVc and σc
SIGMA_BINS = [
    (-999.0, -1.0, "<<"),
    ( -1.0, -0.3, "<"),
    ( -0.3,  0.3, "~"),
    (  0.3,  1.0, ">"),
    (  1.0, 999.0, ">>"),
]

# Velocity of σVw thresholds — computed dynamically from P33/P67
# These defaults are overwritten by main() from actual Kalman data
VEL_SVW_TH = (-0.124, 0.130)  # Kalman P33/P67 (was -0.091/0.091 from EMA)

ZZ_EVENTS = ["zz25_min", "zz25_max", "zz50_min", "zz50_max", "zz75_min", "zz75_max"]
STEREO_KEYS = ["HH", "HL", "LH", "LL"]


# ═══════════════════════════════════════════════════════════════
# Classification
# ═══════════════════════════════════════════════════════════════
def classify_wave_slope(value: float) -> str:
    """Classify wave_slope into W+++/W++/W+/W-/W--/W---."""
    if value >= 0:
        t1, t2 = SLOPE_TH_W["+"]
        if value >= t2:
            return "W+++"
        elif value >= t1:
            return "W++"
        else:
            return "W+"
    else:
        t1, t2 = SLOPE_TH_W["-"]
        av = abs(value)
        if av >= t2:
            return "W---"
        elif av >= t1:
            return "W--"
        else:
            return "W-"


def classify_sigma(value: float) -> str:
    """Classify sigma into <</</ ~/>/>>."""
    for lo, hi, label in SIGMA_BINS:
        if lo <= value < hi:
            return label
    return ">>"


def classify_vel_svw(vel: float) -> str:
    """Classify vel_σVw into ▼/~/▲."""
    if vel < VEL_SVW_TH[0]:
        return "▼"
    elif vel > VEL_SVW_TH[1]:
        return "▲"
    return "~"


# ═══════════════════════════════════════════════════════════════
# Data loading
# ═══════════════════════════════════════════════════════════════
def get_universe(store):
    """Get tickers that have channel_snapshots."""
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ticker
                FROM engine.channel_snapshots
                WHERE wave_slope IS NOT NULL
                  AND vwap_sigma_current IS NOT NULL
                  AND sigma_current IS NOT NULL
                  AND vwap_sigma_wave IS NOT NULL
                ORDER BY ticker
            """)
            return [r[0] for r in cur.fetchall()]
    finally:
        store._put(conn)


def load_ticker_data(store, ticker):
    """Load channel snapshots + zigzag pivots for one ticker.

    Returns:
        snapshots: list of (timestamp, wave_slope, vwap_sigma_current, sigma_current, vwap_sigma_wave, obs_vel_svw)
        zz_sets: {level: {date: tp_type}} — pivot dates per level for T=0/T-1 matching
        st_pivots: list of (tp_type, bar_idx, price) for STEREOTYPE_PCT level
    """
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            # Channel snapshots — Wave features
            cur.execute("""
                SELECT timestamp, wave_slope, vwap_sigma_current, sigma_current,
                       vwap_sigma_wave, obs_vel_svw
                FROM engine.channel_snapshots
                WHERE ticker = %s
                  AND wave_slope IS NOT NULL
                  AND vwap_sigma_current IS NOT NULL
                  AND sigma_current IS NOT NULL
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

        # Build lookup sets per level: {date: tp_type}
        zz_sets = {level: {} for level in ZIGZAG_LEVELS}
        for level, ts, tp_type, price in zz_all:
            lvl = float(level)
            if lvl in zz_sets:
                key = ts.date() if hasattr(ts, 'date') else ts
                zz_sets[lvl][key] = tp_type

        # Build stereotype pivots (bar_idx mapping for STEREOTYPE_PCT)
        st_pivot_rows = [(ts, tp_type, float(price))
                         for lvl, ts, tp_type, price in zz_all
                         if float(lvl) == STEREOTYPE_PCT]

        # Map timestamps to bar indices
        ts_to_idx = {}
        for i, (ts, *_) in enumerate(snapshots):
            key = ts.date() if hasattr(ts, 'date') else ts
            ts_to_idx[key] = i

        st_pivots = []
        for ts, tp_type, price in st_pivot_rows:
            key = ts.date() if hasattr(ts, 'date') else ts
            idx = ts_to_idx.get(key)
            if idx is not None:
                st_pivots.append((tp_type, idx, price))

        return snapshots, zz_sets, st_pivots
    finally:
        store._put(conn)


# ═══════════════════════════════════════════════════════════════
# Causal stereotypes — derived from zigzag sequence
# ═══════════════════════════════════════════════════════════════
def build_causal_stereotypes(n_bars, st_pivots):
    """Build causal stereotype at each bar from zigzag sequence.

    At each bar t, the stereotype = last_zig + last_zag where:
      - last_zig = "H" if most recent MAX price > previous MAX price, else "L"
      - last_zag = "H" if most recent MIN price > previous MIN price, else "L"

    Also builds pivot_events: {bar_idx: (tp_type, stereo_before, stereo_after)}

    Returns:
        bar_stereo: [str or None] — causal stereotype per bar
        pivot_events: {bar_idx: (tp_type, stereo_before, stereo_after)}
    """
    bar_stereo = [None] * n_bars
    pivot_events = {}

    last_zig = None
    last_zag = None
    prev_max_price = None
    prev_min_price = None

    # Sort pivots by bar_idx
    sorted_pivots = sorted(st_pivots, key=lambda p: p[1])

    # Build a map of bar_idx -> pivot for quick lookup
    pivot_by_idx = {}
    for tp_type, bar_idx, price in sorted_pivots:
        pivot_by_idx[bar_idx] = (tp_type, price)

    # Walk through ALL bars in order to build causal stereotypes
    for bar_idx in range(n_bars):
        if bar_idx in pivot_by_idx:
            tp_type, price = pivot_by_idx[bar_idx]

            # Record stereo BEFORE this pivot changes anything
            stereo_before = (last_zig or "?") + (last_zag or "?")

            # Update the appropriate letter
            if tp_type == "MAX":
                if prev_max_price is not None:
                    last_zig = "H" if price > prev_max_price else "L"
                prev_max_price = price
            else:  # MIN
                if prev_min_price is not None:
                    last_zag = "H" if price > prev_min_price else "L"
                prev_min_price = price

            # Record stereo AFTER this pivot
            stereo_after = (last_zig or "?") + (last_zag or "?")

            # Only record if both letters are known
            if "?" not in stereo_before and "?" not in stereo_after:
                pivot_events[bar_idx] = (tp_type, stereo_before, stereo_after)

        # Set the bar's causal stereotype
        if last_zig and last_zag:
            bar_stereo[bar_idx] = last_zig + last_zag

    return bar_stereo, pivot_events


# ═══════════════════════════════════════════════════════════════
# Per-ticker processing
# ═══════════════════════════════════════════════════════════════
def process_ticker(store, ticker):
    """Process one ticker: classify W×σVc×σc×vel + causal stereotypes + pivot prediction.

    Returns:
        profiles: [(state_key, causal_stereo)] — for stereo_counts
        pre_data: {state_key: {zz_event: {count, stereo_dist}}}
        at_data:  {state_key: {zz_event: {count, stereo_before_dist, stereo_after_dist}}}
    """
    snapshots, zz_sets, st_pivots = load_ticker_data(store, ticker)
    if len(snapshots) < 250:
        return [], {}, {}

    n_bars = len(snapshots)

    # ── Use Kalman obs_vel_svw directly from DB; fallback to EMA(5).diff() if None ──
    svw_series = pd.Series([float(s[4]) for s in snapshots])
    ema_diff = svw_series.ewm(span=5).mean().diff().fillna(0.0).values
    vel_svw = np.array([float(s[5]) if s[5] is not None else float(ema_diff[i]) for i, s in enumerate(snapshots)])

    # ── Build causal stereotypes from 2.5% zigzag ──
    bar_stereo, pivot_events = build_causal_stereotypes(n_bars, st_pivots)

    # ── Classify all bars into profile keys ──
    bar_profiles = [None] * n_bars
    for idx in range(n_bars):
        ts, w_slope, svc, sc, svw, obs_vel = snapshots[idx]
        w = classify_wave_slope(float(w_slope))
        sigma_vc = classify_sigma(float(svc))
        sigma_c = classify_sigma(float(sc))
        vel = classify_vel_svw(float(vel_svw[idx]))
        bar_profiles[idx] = f"{w}|σVc:{sigma_vc}|σc:{sigma_c}|vel:{vel}"

    # ── Collect profile + stereotype observations ──
    profiles = []
    for idx in range(n_bars):
        if bar_profiles[idx] and bar_stereo[idx]:
            profiles.append((bar_profiles[idx], bar_stereo[idx]))

    # ── Collect T-1 (pre) and T=0 (at) observations ──
    # pre: {state_key: {zz_event: {"count": int, "stereo": {HH:n, HL:n, ...}}}}
    pre_data = defaultdict(lambda: defaultdict(lambda: {
        "count": 0, "stereo": defaultdict(int)
    }))

    # at: {state_key: {zz_event: {"count": int, "stereo_before": {...}, "stereo_after": {...}}}}
    at_data = defaultdict(lambda: defaultdict(lambda: {
        "count": 0, "stereo_before": defaultdict(int), "stereo_after": defaultdict(int)
    }))

    for level in ZIGZAG_LEVELS:
        label = ZIGZAG_LABEL[level]
        for idx in range(n_bars):
            ts = snapshots[idx][0]
            bar_date = ts.date() if hasattr(ts, 'date') else ts
            tp_type = zz_sets[level].get(bar_date)
            if tp_type is None:
                continue

            event_key = f"{label}_{tp_type.lower()}"  # e.g. "zz25_min"

            # ── T=0 (at): profile at pivot bar ──
            profile_at = bar_profiles[idx]
            if profile_at:
                at_entry = at_data[profile_at][event_key]
                at_entry["count"] += 1

                # stereo_before and stereo_after from zigzag-derived causal stereotypes
                # Only available for STEREOTYPE_PCT level pivots
                if level == STEREOTYPE_PCT and idx in pivot_events:
                    _, s_before, s_after = pivot_events[idx]
                    at_entry["stereo_before"][s_before] += 1
                    at_entry["stereo_after"][s_after] += 1
                elif level != STEREOTYPE_PCT:
                    # For 5% and 7.5% pivots, look up the causal stereotype
                    # The stereo_before = bar_stereo[idx-1] if available (state before pivot)
                    # stereo_after must be derived from the 2.5% zigzag
                    # For non-2.5% pivots, we need the zigzag comparison but we only
                    # have it for 2.5%. Use bar_stereo which is already causal.
                    s_before = bar_stereo[idx - 1] if idx > 0 else None
                    s_after = bar_stereo[idx] if idx < n_bars else None
                    if s_before:
                        at_entry["stereo_before"][s_before] += 1
                    if s_after:
                        at_entry["stereo_after"][s_after] += 1

            # ── T-1 (pre): profile one bar before pivot ──
            if idx > 0:
                profile_pre = bar_profiles[idx - 1]
                stereo_pre = bar_stereo[idx - 1]
                if profile_pre and stereo_pre:
                    pre_entry = pre_data[profile_pre][event_key]
                    pre_entry["count"] += 1
                    pre_entry["stereo"][stereo_pre] += 1

    return profiles, dict(pre_data), dict(at_data)


# ═══════════════════════════════════════════════════════════════
# Cell builder
# ═══════════════════════════════════════════════════════════════
def _build_cell(stereo_counts, pre_events, at_events, level_str):
    """Build a cell with stereo_counts + pre + at sections."""
    cell = {
        "level": level_str,
        "n_total": sum(stereo_counts.values()),
        "stereo_counts": {st: stereo_counts.get(st, 0) for st in STEREO_KEYS},
    }

    # Pre section (T-1)
    pre = {}
    for ev in ZZ_EVENTS:
        data = pre_events.get(ev, {"count": 0, "stereo": {}})
        pre[ev] = {
            "count": data["count"],
            "stereo": {st: data.get("stereo", {}).get(st, 0) for st in STEREO_KEYS},
        }
    cell["pre"] = pre

    # At section (T=0)
    at = {}
    for ev in ZZ_EVENTS:
        data = at_events.get(ev, {"count": 0, "stereo_before": {}, "stereo_after": {}})
        at[ev] = {
            "count": data["count"],
            "stereo_before": {st: data.get("stereo_before", {}).get(st, 0) for st in STEREO_KEYS},
            "stereo_after": {st: data.get("stereo_after", {}).get(st, 0) for st in STEREO_KEYS},
        }
    cell["at"] = at

    return cell


def build_table(all_profiles, all_pre, all_at):
    """Build multi-level probability table: L1 (4D), L2 (W×σVc), L3 (σVc)."""
    cells = {}

    # ── L1: Full W|σVc|σc|vel ──
    l1_stereo = defaultdict(lambda: defaultdict(int))
    l1_pre = defaultdict(lambda: defaultdict(lambda: {"count": 0, "stereo": defaultdict(int)}))
    l1_at = defaultdict(lambda: defaultdict(lambda: {
        "count": 0, "stereo_before": defaultdict(int), "stereo_after": defaultdict(int)
    }))

    for state_key, stereo in all_profiles:
        l1_stereo[state_key][stereo] += 1

    for state_key, events in all_pre.items():
        for ev, data in events.items():
            l1_pre[state_key][ev]["count"] += data["count"]
            for st, c in data["stereo"].items():
                l1_pre[state_key][ev]["stereo"][st] += c

    for state_key, events in all_at.items():
        for ev, data in events.items():
            l1_at[state_key][ev]["count"] += data["count"]
            for st, c in data["stereo_before"].items():
                l1_at[state_key][ev]["stereo_before"][st] += c
            for st, c in data["stereo_after"].items():
                l1_at[state_key][ev]["stereo_after"][st] += c

    n_l1 = 0
    for key in sorted(l1_stereo):
        n = sum(l1_stereo[key].values())
        if n >= MIN_OBS_L1:
            cells[f"L1:{key}"] = _build_cell(
                l1_stereo[key], l1_pre[key], l1_at[key], "L1_full"
            )
            n_l1 += 1

    # ── L2: W|σVc (collapse σc and vel) ──
    l2_stereo = defaultdict(lambda: defaultdict(int))
    l2_pre = defaultdict(lambda: defaultdict(lambda: {"count": 0, "stereo": defaultdict(int)}))
    l2_at = defaultdict(lambda: defaultdict(lambda: {
        "count": 0, "stereo_before": defaultdict(int), "stereo_after": defaultdict(int)
    }))

    for state_key, stereo in all_profiles:
        parts = state_key.split("|")  # W+++|σVc:<<|σc:~|vel:▲
        l2_key = f"{parts[0]}|{parts[1]}"  # W+++|σVc:<<
        l2_stereo[l2_key][stereo] += 1

    for state_key, events in all_pre.items():
        parts = state_key.split("|")
        l2_key = f"{parts[0]}|{parts[1]}"
        for ev, data in events.items():
            l2_pre[l2_key][ev]["count"] += data["count"]
            for st, c in data["stereo"].items():
                l2_pre[l2_key][ev]["stereo"][st] += c

    for state_key, events in all_at.items():
        parts = state_key.split("|")
        l2_key = f"{parts[0]}|{parts[1]}"
        for ev, data in events.items():
            l2_at[l2_key][ev]["count"] += data["count"]
            for st, c in data["stereo_before"].items():
                l2_at[l2_key][ev]["stereo_before"][st] += c
            for st, c in data["stereo_after"].items():
                l2_at[l2_key][ev]["stereo_after"][st] += c

    n_l2 = 0
    for key in sorted(l2_stereo):
        cells[f"L2:{key}"] = _build_cell(
            l2_stereo[key], l2_pre[key], l2_at[key], "L2_w_svc"
        )
        n_l2 += 1

    # ── L3: σVc only ──
    l3_stereo = defaultdict(lambda: defaultdict(int))
    l3_pre = defaultdict(lambda: defaultdict(lambda: {"count": 0, "stereo": defaultdict(int)}))
    l3_at = defaultdict(lambda: defaultdict(lambda: {
        "count": 0, "stereo_before": defaultdict(int), "stereo_after": defaultdict(int)
    }))

    for state_key, stereo in all_profiles:
        parts = state_key.split("|")
        l3_key = parts[1]  # σVc:<<
        l3_stereo[l3_key][stereo] += 1

    for state_key, events in all_pre.items():
        parts = state_key.split("|")
        l3_key = parts[1]
        for ev, data in events.items():
            l3_pre[l3_key][ev]["count"] += data["count"]
            for st, c in data["stereo"].items():
                l3_pre[l3_key][ev]["stereo"][st] += c

    for state_key, events in all_at.items():
        parts = state_key.split("|")
        l3_key = parts[1]
        for ev, data in events.items():
            l3_at[l3_key][ev]["count"] += data["count"]
            for st, c in data["stereo_before"].items():
                l3_at[l3_key][ev]["stereo_before"][st] += c
            for st, c in data["stereo_after"].items():
                l3_at[l3_key][ev]["stereo_after"][st] += c

    n_l3 = 0
    for key in sorted(l3_stereo):
        cells[f"L3:{key}"] = _build_cell(
            l3_stereo[key], l3_pre[key], l3_at[key], "L3_svc"
        )
        n_l3 += 1

    return cells, {"L1_full": n_l1, "L2_w_svc": n_l2, "L3_svc": n_l3}


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════
def main():
    t0 = time.time()
    logger.info("=" * 90)
    logger.info("  TRAIN WAVE W×σVc×σc×vel_σVw PIVOT-PREDICTION TABLE")
    logger.info("  W(6) × σVc(5) × σc(5) × vel(3) = 450 L1 states")
    logger.info("  Velocity: obs_vel_svw (Kalman) from engine.channel_snapshots")
    logger.info("  Causal stereotypes from zigzag sequence (not legacy cycle pairing)")
    logger.info("  pre (T-1): stereotype at profiled bar")
    logger.info("  at  (T=0): stereo_before + stereo_after from zigzag comparison")
    logger.info("  Source: engine.channel_snapshots + engine.zigzag_points (3 levels)")
    logger.info("=" * 90)

    store = TimescaleDataStore()

    # ── Compute vel thresholds from Kalman data (P33/P67) ──
    logger.info("Computing vel_σVw thresholds from Kalman obs_vel_svw (P33/P67)...")
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    percentile_cont(0.33) WITHIN GROUP (ORDER BY obs_vel_svw),
                    percentile_cont(0.67) WITHIN GROUP (ORDER BY obs_vel_svw)
                FROM engine.channel_snapshots
                WHERE obs_vel_svw IS NOT NULL AND obs_vel_svw != 0.0
            """)
            p33, p67 = cur.fetchone()
    finally:
        store._put(conn)

    global VEL_SVW_TH
    VEL_SVW_TH = (round(float(p33), 6), round(float(p67), 6))
    logger.info(f"  Kalman vel thresholds: ▼ < {VEL_SVW_TH[0]:.6f} | ~ | ▲ > {VEL_SVW_TH[1]:.6f}")

    tickers = get_universe(store)
    logger.info(f"Universe: {len(tickers)} tickers")

    all_profiles = []
    all_pre = defaultdict(lambda: defaultdict(lambda: {"count": 0, "stereo": defaultdict(int)}))
    all_at = defaultdict(lambda: defaultdict(lambda: {
        "count": 0, "stereo_before": defaultdict(int), "stereo_after": defaultdict(int)
    }))
    processed = 0
    failed = 0
    total_pivots_at = 0
    total_pivots_pre = 0

    for i, ticker in enumerate(tickers):
        try:
            profiles, pre, at = process_ticker(store, ticker)
            all_profiles.extend(profiles)

            for sk, events in pre.items():
                for ev, data in events.items():
                    all_pre[sk][ev]["count"] += data["count"]
                    for st, c in data["stereo"].items():
                        all_pre[sk][ev]["stereo"][st] += c
                    total_pivots_pre += data["count"]

            for sk, events in at.items():
                for ev, data in events.items():
                    all_at[sk][ev]["count"] += data["count"]
                    for st, c in data["stereo_before"].items():
                        all_at[sk][ev]["stereo_before"][st] += c
                    for st, c in data["stereo_after"].items():
                        all_at[sk][ev]["stereo_after"][st] += c
                    total_pivots_at += data["count"]

            processed += 1

            if (i + 1) % 50 == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed
                eta = (len(tickers) - i - 1) / rate
                logger.info(
                    f"  [{i+1}/{len(tickers)}] {ticker}: "
                    f"profiles={len(all_profiles):,} | "
                    f"pre_pivots={total_pivots_pre:,} | at_pivots={total_pivots_at:,} | "
                    f"{elapsed:.0f}s elapsed, ~{eta:.0f}s ETA"
                )
        except Exception as e:
            failed += 1
            if failed <= 5:
                logger.warning(f"  ⚠️  {ticker}: {e}")
            elif failed == 6:
                logger.warning(f"  ⚠️  (suppressing further warnings)")

    logger.info(f"\nProcessed: {processed}/{len(tickers)} ({failed} failed)")
    logger.info(f"Total profile observations: {len(all_profiles):,}")
    logger.info(f"Total T-1 pre pivot hits: {total_pivots_pre:,}")
    logger.info(f"Total T=0 at pivot hits: {total_pivots_at:,}")

    # ── Build table ──
    logger.info("\nBuilding W×σVc×σc×vel table...")
    cells, n_cells = build_table(all_profiles, dict(all_pre), dict(all_at))

    # Compute global pivot totals
    global_pivot_totals = {}
    for ev in ZZ_EVENTS:
        total_pre = sum(
            all_pre[sk][ev]["count"]
            for sk in all_pre
            if ev in all_pre[sk]
        )
        total_at = sum(
            all_at[sk][ev]["count"]
            for sk in all_at
            if ev in all_at[sk]
        )
        global_pivot_totals[f"{ev}_pre"] = total_pre
        global_pivot_totals[f"{ev}_at"] = total_at

    table = {
        "version": f"v1_wave_{datetime.now().strftime('%Y-%m-%d')}",
        "dimensions": "W_slope|sigma_Vc|sigma_c|vel_sigma_Vw",
        "zigzag_stereotype_level": STEREOTYPE_PCT,
        "zigzag_levels": ZIGZAG_LEVELS,
        "n_tickers": processed,
        "n_total_observations": len(all_profiles),
        "global_pivot_totals": global_pivot_totals,
        "classification": {
            "slope_thresholds_W": SLOPE_TH_W,
            "sigma_Vc_bins": {label: [lo, hi] for lo, hi, label in SIGMA_BINS},
            "sigma_c_bins": {label: [lo, hi] for lo, hi, label in SIGMA_BINS},
            "vel_svw_thresholds": list(VEL_SVW_TH),
            "vel_svw_source": "obs_vel_svw (Kalman)",
            "stereotype_order": STEREO_KEYS,
        },
        "vel_thresholds": {
            "lower": VEL_SVW_TH[0],
            "upper": VEL_SVW_TH[1],
            "source": "P33/P67 of obs_vel_svw (Kalman) excluding zeros",
        },
        "n_cells": n_cells,
        "cells": cells,
    }

    with open(OUTPUT_TABLE, "w") as f:
        json.dump(table, f, indent=2, default=str)
    size_kb = OUTPUT_TABLE.stat().st_size / 1024
    logger.info(f"  Table written: {OUTPUT_TABLE.name} ({size_kb:.0f} KB)")

    store.close()
    elapsed = time.time() - t0

    # ── Summary ──
    logger.info(f"\n{'=' * 90}")
    logger.info(f"  COMPLETE — {elapsed:.1f}s ({elapsed/60:.1f} min)")
    logger.info(f"  Cells: L1={n_cells['L1_full']}, L2={n_cells['L2_w_svc']}, L3={n_cells['L3_svc']}")
    logger.info(f"  Total cells: {len(cells)}")

    # Quick validation
    logger.info("\n  Sample L1 cells:")
    l1_cells = [(k, c) for k, c in cells.items() if c["level"] == "L1_full"]
    l1_cells.sort(key=lambda x: -x[1]["n_total"])
    for key, c in l1_cells[:5]:
        n = c["n_total"]
        sc = c["stereo_counts"]
        p_bull = (sc["HH"] + sc["HL"]) / n * 100 if n else 0
        pre_zz25_min = c["pre"]["zz25_min"]["count"]
        pre_zz25_max = c["pre"]["zz25_max"]["count"]
        at_zz25_min = c["at"]["zz25_min"]["count"]
        logger.info(
            f"    {key}: N={n:,}, P_bull={p_bull:.1f}%, "
            f"pre(zz25_min={pre_zz25_min}, zz25_max={pre_zz25_max}), "
            f"at(zz25_min={at_zz25_min})"
        )

    # Show reversal quality for a specific cell
    for key, c in l1_cells[:1]:
        at_min = c["at"]["zz25_min"]
        if at_min["count"] > 0:
            sb = at_min["stereo_before"]
            sa = at_min["stereo_after"]
            logger.info(f"\n  Reversal quality for {key} at zz25_min (count={at_min['count']}):")
            logger.info(f"    stereo_before: {dict(sb)}")
            logger.info(f"    stereo_after:  {dict(sa)}")

    logger.info(f"{'=' * 90}")


if __name__ == "__main__":
    main()
