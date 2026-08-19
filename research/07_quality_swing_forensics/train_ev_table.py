#!/usr/bin/env python3
"""
Train EV Probability Table — Forward Pivot Expected Value Model
================================================================
Replaces train_combined_table.py with a forward-label approach.

Instead of counting HH/HL/LH/LL stereotypes (retrospective zigzag labels),
this script counts the NEXT zigzag pivot that forms AFTER each bar.

For each of the 180 T×C×σVw states, computes:
  - P(next=MIN), P(next=MAX)
  - E[swing_return | MIN], E[swing_return | MAX]
  - EV = P(MIN)*E[ret|MIN] + P(MAX)*E[ret|MAX]
  - E[swing_days], E[swing_speed]
  - std(swing_return) — for Sharpe computation
  - Run-length interaction: EV by run_bucket (fatigue)

For each of the 3 zigzag levels (2.5%, 5%, 7.5%):
  - Full forward-label computation
  - Per-level EV, Sharpe, horizon

Output: rc_ev_probability_table.json (replaces rc_combined_probability_table.json)

Architecture: Same clean/hexagonal structure as train_combined_table.py.
Reads from Vault (engine.channel_snapshots + engine.zigzag_points).
Pure data extraction + counting. No signal classification (that's in generate_ev_derived.py).

Usage:
  PYTHONPATH=. backend/.venv/bin/python research/07_quality_swing_forensics/train_ev_table.py

  # Background:
  nohup bash -c 'PYTHONPATH=. backend/.venv/bin/python research/07_quality_swing_forensics/train_ev_table.py' \
    > /tmp/train_ev.log 2>&1 &
"""
import os, sys, json, time, math, logging, bisect
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

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
# Configuration — MUST match rc_slope_classifier.py thresholds
# ═══════════════════════════════════════════════════════════════
ZIGZAG_LEVELS = [0.025, 0.05, 0.075]
ZIGZAG_LABEL = {0.025: "zz25", 0.05: "zz50", 0.075: "zz75"}
MIN_OBS = 30  # Minimum observations per state
OUTPUT_PATH = root_dir / "backend/modules/quality_swing/domain/rules/rc_ev_probability_table.json"

# Slope thresholds — identical to rc_slope_classifier.py
SLOPE_TH = {
    "T": {"+": (0.0456, 0.0983), "-": (0.0263, 0.0765)},
    "C": {"+": (0.0845, 0.1749), "-": (0.0613, 0.1583)},
}

# Sigma bins — identical to rc_combined_lookup.py
SIGMA_BINS = [
    (-999, -1.0, "<<"),
    (-1.0, -0.3, "<"),
    (-0.3,  0.3, "~"),
    ( 0.3,  1.0, ">"),
    ( 1.0,  999, ">>"),
]

# Run-length buckets for fatigue analysis
RUN_BUCKETS = [
    (0, 1, "1"),
    (1, 2, "2"),
    (2, 4, "3-4"),
    (4, 7, "5-7"),
    (7, 10, "8-10"),
    (10, 9999, "11+"),
]


# ═══════════════════════════════════════════════════════════════
# Classification — same as train_combined_table.py
# ═══════════════════════════════════════════════════════════════

def classify_slope(value: float, channel: str) -> str:
    """Classify slope into +++/++/+/-/--/--- for T or C channels."""
    th = SLOPE_TH[channel]
    if value >= 0:
        p33, p66 = th["+"]
        if value >= p66: return f"{channel}+++"
        elif value >= p33: return f"{channel}++"
        else: return f"{channel}+"
    else:
        p33, p66 = th["-"]
        av = abs(value)
        if av >= p66: return f"{channel}---"
        elif av >= p33: return f"{channel}--"
        else: return f"{channel}-"


def classify_sigma(value: float) -> str:
    """Classify σ_vwap_wave into <</</ ~/>/>>."""
    for lo, hi, label in SIGMA_BINS:
        if lo <= value < hi:
            return label
    return ">>"


def get_run_bucket(run_length: int) -> str:
    """Classify run_length into bucket label."""
    for lo, hi, label in RUN_BUCKETS:
        if lo < run_length <= hi:
            return label
    return "11+"


# ═══════════════════════════════════════════════════════════════
# Data loading
# ═══════════════════════════════════════════════════════════════

def load_all_data(store: TimescaleDataStore):
    """Load channel_snapshots + zigzag_points from Vault.

    Returns:
        snapshots: DataFrame with ticker, timestamp, T, C, svw, state_key
        zigzags: dict {level: DataFrame} with ticker, timestamp, tp_type,
                 swing_return, swing_days
    """
    # ── Channel snapshots ──
    logger.info("Loading channel_snapshots...")
    df = pd.read_sql("""
        SELECT ticker, timestamp, tide_slope, current_slope, vwap_sigma_wave
        FROM engine.channel_snapshots
        WHERE timeframe = '1d'
          AND tide_slope IS NOT NULL
          AND current_slope IS NOT NULL
          AND vwap_sigma_wave IS NOT NULL
        ORDER BY ticker, timestamp
    """, store.engine)

    # Classify states
    df['T'] = df['tide_slope'].apply(lambda x: classify_slope(x, 'T'))
    df['C'] = df['current_slope'].apply(lambda x: classify_slope(x, 'C'))
    df['svw'] = df['vwap_sigma_wave'].apply(classify_sigma)
    df['state_key'] = df['T'] + '|' + df['C'] + '|' + df['svw']

    # Compute run_length per ticker (consecutive bars in same state)
    df = df.sort_values(['ticker', 'timestamp']).reset_index(drop=True)
    df['prev_state'] = df.groupby('ticker')['state_key'].shift(1)
    df['state_change'] = df['state_key'] != df['prev_state']
    df['run_group'] = df.groupby('ticker')['state_change'].cumsum()
    df['run_length'] = df.groupby(['ticker', 'run_group']).cumcount() + 1

    logger.info(f"  {len(df):,} snapshots, {df['state_key'].nunique()} states")

    # ── Zigzag pivots ──
    zigzags = {}
    for level in ZIGZAG_LEVELS:
        logger.info(f"Loading zigzag_points ({level*100:.1f}%)...")
        zz = pd.read_sql(f"""
            SELECT ticker, timestamp, tp_type, swing_return, swing_days, swing_speed
            FROM engine.zigzag_points
            WHERE min_swing_pct = {level} AND swing_days > 0
            ORDER BY ticker, timestamp
        """, store.engine)
        zz['timestamp'] = pd.to_datetime(zz['timestamp'], utc=True)
        zigzags[level] = zz
        logger.info(f"  {len(zz):,} pivots at {level*100:.1f}%")

    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    return df, zigzags


# ═══════════════════════════════════════════════════════════════
# Forward label computation
# ═══════════════════════════════════════════════════════════════

def compute_forward_labels(snap_df: pd.DataFrame, zz_df: pd.DataFrame) -> pd.DataFrame:
    """For each snapshot bar, find the NEXT zigzag pivot that forms AFTER it.

    This is the FORWARD label — no look-ahead bias. The pivot is an event
    that hasn't happened yet from the perspective of the current bar.

    Returns DataFrame with: ticker, timestamp, state_key, run_length,
                            next_type, next_return, next_days, next_speed
    """
    results = []
    for ticker in snap_df['ticker'].unique():
        tdf = snap_df[snap_df['ticker'] == ticker].sort_values('timestamp').reset_index(drop=True)
        tzz = zz_df[zz_df['ticker'] == ticker].sort_values('timestamp').reset_index(drop=True)
        if len(tzz) == 0:
            continue

        zz_ts = tzz['timestamp'].values
        zz_type = tzz['tp_type'].values
        zz_ret = tzz['swing_return'].values
        zz_days = tzz['swing_days'].values
        zz_speed = tzz['swing_speed'].values

        snap_ts = tdf['timestamp'].values
        snap_state = tdf['state_key'].values
        snap_rl = tdf['run_length'].values

        for i in range(len(tdf)):
            j = bisect.bisect_right(zz_ts, snap_ts[i])
            if j >= len(zz_ts):
                continue
            results.append({
                'ticker': ticker,
                'timestamp': snap_ts[i],
                'state_key': snap_state[i],
                'run_length': snap_rl[i],
                'next_type': zz_type[j],
                'next_return': float(zz_ret[j]),
                'next_days': int(zz_days[j]),
                'next_speed': float(zz_speed[j]) if 'swing_speed' in tzz.columns else 0.0,
            })

    return pd.DataFrame(results)


# ═══════════════════════════════════════════════════════════════
# Cell builder
# ═══════════════════════════════════════════════════════════════

def build_state_cell(fwd_df: pd.DataFrame, state_key: str) -> dict:
    """Build a complete cell for one state from forward labels.

    Computes per-zigzag-level EV metrics + fatigue (run_length interaction).
    """
    sdf = fwd_df[fwd_df['state_key'] == state_key]
    n = len(sdf)
    if n < MIN_OBS:
        return None

    cell = {
        "state_key": state_key,
        "n_total": n,
        "levels": {},
        "fatigue": {},
    }

    # ── Per-level metrics ──
    for level in ZIGZAG_LEVELS:
        lvl_label = ZIGZAG_LABEL[level]
        # Forward labels are computed per-level, so fwd_df is already for this level
        # But we compute all levels together — need to filter
        # Actually, fwd_df contains forward labels for ONE specific level
        # This function is called per-level
        pass

    # ── Aggregate metrics (for the level that was passed) ──
    p_min = (sdf['next_type'] == 'MIN').mean()
    p_max = 1 - p_min
    e_ret_min = float(sdf[sdf['next_type'] == 'MIN']['next_return'].mean()) if p_min > 0 else 0.0
    e_ret_max = float(sdf[sdf['next_type'] == 'MAX']['next_return'].mean()) if p_max > 0 else 0.0
    ev = p_min * e_ret_min + p_max * e_ret_max
    std_ret = float(sdf['next_return'].std()) if n > 1 else 0.0
    e_days = float(sdf['next_days'].mean())
    e_speed = float(sdf['next_speed'].abs().mean()) if 'next_speed' in sdf.columns else 0.0

    # Sharpe (per-swing, not annualized — annualization in derived)
    sharpe = ev / std_ret if std_ret > 0 else 0.0

    # ── Fatigue: EV by run_length bucket ──
    fatigue = {}
    for lo, hi, bucket_label in RUN_BUCKETS:
        bdf = sdf[(sdf['run_length'] > lo) & (sdf['run_length'] <= hi)]
        bn = len(bdf)
        if bn < 10:
            continue
        bp_min = (bdf['next_type'] == 'MIN').mean()
        bp_max = 1 - bp_min
        be_ret_min = float(bdf[bdf['next_type'] == 'MIN']['next_return'].mean()) if bp_min > 0 else 0
        be_ret_max = float(bdf[bdf['next_type'] == 'MAX']['next_return'].mean()) if bp_max > 0 else 0
        be_ev = bp_min * be_ret_min + bp_max * be_ret_max
        fatigue[bucket_label] = {
            "n": bn,
            "p_min": round(bp_min, 4),
            "p_max": round(bp_max, 4),
            "e_ret_min": round(be_ret_min, 6),
            "e_ret_max": round(be_ret_max, 6),
            "ev": round(be_ev, 6),
        }

    # Classify fatigue type
    if len(fatigue) >= 2:
        evs = [fatigue[k]['ev'] for k in ['1', '2', '3-4', '5-7', '8-10', '11+'] if k in fatigue]
        if len(evs) >= 2:
            ev_change = evs[-1] - evs[0]
            if ev_change > 0.005:
                fatigue_type = "MOMENTUM_CONFIRMING"
            elif ev_change < -0.005:
                fatigue_type = "FATIGUE_RISK"
            else:
                fatigue_type = "STABLE"
        else:
            fatigue_type = "INSUFFICIENT_DATA"
    else:
        fatigue_type = "INSUFFICIENT_DATA"

    cell = {
        "state_key": state_key,
        "n": n,
        "p_min": round(p_min, 4),
        "p_max": round(p_max, 4),
        "e_ret_min": round(e_ret_min, 6),
        "e_ret_max": round(e_ret_max, 6),
        "ev": round(ev, 6),
        "std_return": round(std_ret, 6),
        "sharpe": round(sharpe, 4),
        "e_days": round(e_days, 2),
        "e_speed": round(e_speed, 6),
        "fatigue": fatigue,
        "fatigue_type": fatigue_type,
    }

    return cell


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    logger.info("=" * 90)
    logger.info("  TRAIN EV PROBABILITY TABLE — Forward Pivot Expected Value Model")
    logger.info("  T(6) × C(6) × σVw(5) = 180 states")
    logger.info("  3 zigzag levels: 2.5%, 5%, 7.5%")
    logger.info("  Label: next pivot forward (MIN/MAX + swing_return)")
    logger.info("=" * 90)

    store = TimescaleDataStore()

    # ── Load data ──
    snapshots, zigzags = load_all_data(store)
    n_tickers = snapshots['ticker'].nunique()
    n_total = len(snapshots)
    logger.info(f"Universe: {n_tickers} tickers, {n_total:,} snapshots")

    # ── Compute forward labels per zigzag level ──
    all_cells = {}  # state_key → {level_label → cell_data}
    state_seen = set()

    for level in ZIGZAG_LEVELS:
        lvl_label = ZIGZAG_LABEL[level]
        logger.info(f"\nComputing forward labels for {lvl_label} ({level*100:.1f}%)...")
        fwd = compute_forward_labels(snapshots, zigzags[level])
        logger.info(f"  {len(fwd):,} forward labels computed ({time.time()-t0:.1f}s)")

        # ── Build cells per state ──
        logger.info(f"  Building cells for {lvl_label}...")
        for state_key in fwd['state_key'].unique():
            cell = build_state_cell(fwd, state_key)
            if cell is None:
                continue

            if state_key not in all_cells:
                all_cells[state_key] = {}
            # Store the level-specific cell data
            all_cells[state_key][lvl_label] = {
                "n": cell["n"],
                "p_min": cell["p_min"],
                "p_max": cell["p_max"],
                "e_ret_min": cell["e_ret_min"],
                "e_ret_max": cell["e_ret_max"],
                "ev": cell["ev"],
                "std_return": cell["std_return"],
                "sharpe": cell["sharpe"],
                "e_days": cell["e_days"],
                "e_speed": cell["e_speed"],
            }
            state_seen.add(state_key)

        logger.info(f"  {len(all_cells)} states with data at {lvl_label}")

    # ── Compute fatigue only on primary level (zz25) ──
    logger.info("\nComputing fatigue (run_length interaction) on zz25...")
    fwd25 = compute_forward_labels(snapshots, zigzags[0.025])
    fatigue_by_state = {}
    for state_key in fwd25['state_key'].unique():
        sdf = fwd25[fwd25['state_key'] == state_key]
        if len(sdf) < MIN_OBS:
            continue
        fatigue = {}
        for lo, hi, bucket_label in RUN_BUCKETS:
            bdf = sdf[(sdf['run_length'] > lo) & (sdf['run_length'] <= hi)]
            bn = len(bdf)
            if bn < 10:
                continue
            bp_min = (bdf['next_type'] == 'MIN').mean()
            bp_max = 1 - bp_min
            be_ret_min = float(bdf[bdf['next_type'] == 'MIN']['next_return'].mean()) if bp_min > 0 else 0
            be_ret_max = float(bdf[bdf['next_type'] == 'MAX']['next_return'].mean()) if bp_max > 0 else 0
            be_ev = bp_min * be_ret_min + bp_max * be_ret_max
            fatigue[bucket_label] = {
                "n": bn,
                "p_min": round(bp_min, 4),
                "e_ret_min": round(be_ret_min, 6),
                "e_ret_max": round(be_ret_max, 6),
                "ev": round(be_ev, 6),
            }

        # Classify fatigue type
        if len(fatigue) >= 2:
            evs = [fatigue[k]['ev'] for k in ['1', '2', '3-4', '5-7', '8-10', '11+'] if k in fatigue]
            if len(evs) >= 2:
                ev_change = evs[-1] - evs[0]
                if ev_change > 0.005:
                    fatigue_type = "MOMENTUM_CONFIRMING"
                elif ev_change < -0.005:
                    fatigue_type = "FATIGUE_RISK"
                else:
                    fatigue_type = "STABLE"
            else:
                fatigue_type = "INSUFFICIENT_DATA"
        else:
            fatigue_type = "INSUFFICIENT_DATA"

        fatigue_by_state[state_key] = {
            "buckets": fatigue,
            "fatigue_type": fatigue_type,
        }

    logger.info(f"  Fatigue computed for {len(fatigue_by_state)} states ({time.time()-t0:.1f}s)")

    # ── Assemble final table ──
    logger.info("\nAssembling final table...")

    # Global stats
    global_p_min = 0
    global_p_max = 0
    global_n = 0
    for state_key, levels in all_cells.items():
        if "zz25" in levels:
            global_n += levels["zz25"]["n"]
            global_p_min += levels["zz25"]["p_min"] * levels["zz25"]["n"]
            global_p_max += levels["zz25"]["p_max"] * levels["zz25"]["n"]
    global_p_min = global_p_min / global_n if global_n > 0 else 0
    global_p_max = global_p_max / global_n if global_n > 0 else 0

    states_out = {}
    for state_key, levels in sorted(all_cells.items()):
        state_data = {
            "levels": levels,
            "fatigue": fatigue_by_state.get(state_key, {"buckets": {}, "fatigue_type": "INSUFFICIENT_DATA"}),
        }
        states_out[state_key] = state_data

    table = {
        "version": f"v1_ev_forward_{datetime.now().strftime('%Y-%m-%d')}",
        "model_type": "forward_pivot_expected_value",
        "dimensions": "T_slope|C_slope|sigma_vwap_wave",
        "zigzag_levels": ZIGZAG_LEVELS,
        "n_states": len(states_out),
        "n_tickers": n_tickers,
        "n_total_observations": n_total,
        "min_obs_per_state": MIN_OBS,
        "slope_thresholds": SLOPE_TH,
        "sigma_bins": {label: [lo, hi] for lo, hi, label in SIGMA_BINS},
        "global_p_min": round(global_p_min, 4),
        "global_p_max": round(global_p_max, 4),
        "label_definition": "next zigzag pivot type (MIN/MAX) + swing_return formed AFTER current bar",
        "label_type": "forward (no look-ahead bias from zigzag stereotypes)",
        "ev_formula": "EV = P(MIN)*E[swing_return|MIN] + P(MAX)*E[swing_return|MAX]",
        "states": states_out,
    }

    # ── Write output ──
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(table, f, indent=2, ensure_ascii=False)

    size_kb = OUTPUT_PATH.stat().st_size / 1024
    logger.info(f"\n  ✅ Table written: {OUTPUT_PATH} ({size_kb:.0f} KB)")
    logger.info(f"     States: {len(states_out)}")
    logger.info(f"     Tickers: {n_tickers}")
    logger.info(f"     Observations: {n_total:,}")

    # ── Summary ──
    evs = [states_out[s]["levels"]["zz25"]["ev"] for s in states_out if "zz25" in states_out[s]["levels"]]
    logger.info(f"\n  EV Summary (zz25):")
    logger.info(f"     Positive EV: {sum(1 for e in evs if e > 0)}")
    logger.info(f"     Negative EV: {sum(1 for e in evs if e < 0)}")
    logger.info(f"     Mean EV: {np.mean(evs):+.4f}")
    logger.info(f"     Median EV: {np.median(evs):+.4f}")

    fatigue_types = [states_out[s]["fatigue"]["fatigue_type"] for s in states_out]
    from collections import Counter
    logger.info(f"\n  Fatigue types: {dict(Counter(fatigue_types))}")

    elapsed = time.time() - t0
    logger.info(f"\n{'=' * 90}")
    logger.info(f"  COMPLETE — {elapsed:.1f}s ({elapsed/60:.1f} min)")
    logger.info(f"{'=' * 90}")

    store.close()


if __name__ == "__main__":
    main()
