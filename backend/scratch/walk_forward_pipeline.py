#!/usr/bin/env python3
"""
Walk-Forward Validation — EV Pipeline vs P(bull) Pipeline
=========================================================
Uses the FULL pipeline for both models:
  1. Train both models on ≤2022 data (generate JSONs)
  2. Test both models on ≥2023 data (evaluate JSONs against actual outcomes)
  3. Head-to-head comparison

This is a FAIR comparison — both models go through their complete pipelines.

Pipeline steps:
  P(bull): train_combined_table.py → generate_derived_table.py → rc_combined_derived.json
  EV:      train_ev_table.py → generate_ev_derived.py → rc_ev_derived.json

For walk-forward, we:
  1. Filter Vault data to ≤2022 → train both models → save train JSONs
  2. Filter Vault data to ≥2023 → compute actual forward returns per state
  3. Evaluate: for each state, what signal does each JSON give? Does it match reality?

Usage:
  PYTHONPATH=. backend/.venv/bin/python backend/scratch/walk_forward_pipeline.py
"""
import os, sys, json, time, math, bisect, tempfile
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import psycopg2

t0 = time.time()
SPLIT_DATE = pd.Timestamp('2023-01-01', tz='UTC')
RULES_DIR = root_dir / "backend/modules/quality_swing/domain/rules"

# ── Load ALL data from Vault ──
conn = psycopg2.connect(os.environ["POSTGRES_URL"])

print("Loading channel_snapshots...")
df = pd.read_sql("""
    SELECT ticker, timestamp, tide_slope, current_slope, vwap_sigma_wave
    FROM engine.channel_snapshots
    WHERE timeframe = '1d'
      AND tide_slope IS NOT NULL AND current_slope IS NOT NULL
      AND vwap_sigma_wave IS NOT NULL
    ORDER BY ticker, timestamp
""", conn)
df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
print(f"  {len(df):,} rows ({time.time()-t0:.1f}s)")

print("Loading zigzag_points...")
zz_all = pd.read_sql("""
    SELECT ticker, timestamp, tp_type, min_swing_pct, swing_return, swing_days, swing_speed
    FROM engine.zigzag_points
    WHERE swing_days > 0
    ORDER BY ticker, timestamp
""", conn)
zz_all['timestamp'] = pd.to_datetime(zz_all['timestamp'], utc=True)
print(f"  {len(zz_all):,} rows ({time.time()-t0:.1f}s)")

print("Loading ohlcv_bars...")
ohlc = pd.read_sql("""
    SELECT ticker, time AS timestamp, high, low, close
    FROM market.ohlcv_bars
    WHERE timeframe = '1d'
    ORDER BY ticker, time
""", conn)
ohlc['timestamp'] = pd.to_datetime(ohlc['timestamp'], utc=True)
print(f"  {len(ohlc):,} rows ({time.time()-t0:.1f}s)")
conn.close()

# ── Split data ──
df_train = df[df['timestamp'] < SPLIT_DATE].copy()
df_test = df[df['timestamp'] >= SPLIT_DATE].copy()
zz_train = zz_all[zz_all['timestamp'] < SPLIT_DATE].copy()
zz_test = zz_all[zz_all['timestamp'] >= SPLIT_DATE].copy()
ohlc_train = ohlc[ohlc['timestamp'] < SPLIT_DATE].copy()

print(f"\nSplit at {SPLIT_DATE.date()}:")
print(f"  Train: {len(df_train):,} snapshots, {len(zz_train):,} pivots")
print(f"  Test:  {len(df_test):,} snapshots, {len(zz_test):,} pivots")

# ── Classification helpers (same thresholds) ──
SLOPE_TH = {
    "T": {"+": (0.0456, 0.0983), "-": (0.0263, 0.0765)},
    "C": {"+": (0.0845, 0.1749), "-": (0.0613, 0.1583)},
}
SIGMA_BINS = [(-999,-1.0,"<<"),(-1.0,-0.3,"<"),(-0.3,0.3,"~"),(0.3,1.0,">"),(1.0,999,">>")]

def cls_slope(v, ch):
    th = SLOPE_TH[ch]
    if v >= 0:
        p33, p66 = th["+"]
        return f"{ch}+++" if v >= p66 else (f"{ch}++" if v >= p33 else f"{ch}+")
    else:
        p33, p66 = th["-"]
        av = abs(v)
        return f"{ch}---" if av >= p66 else (f"{ch}--" if av >= p33 else f"{ch}-")

def cls_sigma(v):
    for lo,hi,l in SIGMA_BINS:
        if lo <= v < hi: return l
    return ">>"

def classify_state(row):
    t = cls_slope(row['tide_slope'], 'T')
    c = cls_slope(row['current_slope'], 'C')
    s = cls_sigma(row['vwap_sigma_wave'])
    return f"{t}|{c}|{s}"

for d in [df_train, df_test]:
    d['state_key'] = d.apply(classify_state, axis=1)

# ═══════════════════════════════════════════════════════════════
# STEP 1: Train BOTH models on ≤2022 data
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 90)
print("  STEP 1: TRAIN BOTH MODELS ON ≤2022 DATA")
print("=" * 90)

# ── Train P(bull) model (stereotypes) ──
print("\n  Training P(bull) model (stereotypes)...")
# Compute stereotypes for train data
def assign_stereotypes(high, low, close, pivots, n_bars):
    bar_st = [None] * n_bars
    if len(pivots) < 4:
        return bar_st
    maxes = [(idx, val) for t, idx, val in pivots if t == "MAX"]
    mins = [(idx, val) for t, idx, val in pivots if t == "MIN"]
    if len(maxes) < 2 or len(mins) < 2:
        return bar_st
    zig_labels = [(maxes[i][0], "H" if maxes[i][1] > maxes[i-1][1] else "L") for i in range(1, len(maxes))]
    zag_labels = [(mins[i][0], "H" if mins[i][1] > mins[i-1][1] else "L") for i in range(1, len(mins))]
    zi, za = 0, 0
    while zi < len(zig_labels) and za < len(zag_labels):
        zig_idx, zig_l = zig_labels[zi]
        zag_idx, zag_l = zag_labels[za]
        st = zig_l + zag_l
        for b in range(min(zig_idx, zag_idx), min(max(zig_idx, zag_idx) + 1, n_bars)):
            bar_st[b] = st
        zi += 1; za += 1
    last_st = None
    for b in range(n_bars):
        if bar_st[b] is not None:
            last_st = bar_st[b]
        elif last_st is not None:
            bar_st[b] = last_st
    return bar_st

pbull_train = {}  # state → {p_bull, n, action}
zz25_train = zz_train[zz_train['min_swing_pct'] == 0.025]

for ticker in df_train['ticker'].unique():
    tdf = df_train[df_train['ticker'] == ticker].sort_values('timestamp').reset_index(drop=True)
    tohlc = ohlc_train[ohlc_train['ticker'] == ticker].sort_values('timestamp').reset_index(drop=True)
    tzz = zz25_train[zz25_train['ticker'] == ticker].sort_values('timestamp').reset_index(drop=True)
    if len(tohlc) < 250 or len(tzz) < 4:
        continue

    high = tohlc['high'].values.astype(float)
    low = tohlc['low'].values.astype(float)
    close = tohlc['close'].values.astype(float)
    ts_list = tohlc['timestamp'].tolist()
    ts_to_idx = {ts: i for i, ts in enumerate(ts_list)}
    pivots = [(row['tp_type'], ts_to_idx.get(row['timestamp'], 0), float(close[ts_to_idx.get(row['timestamp'], 0)]))
              for _, row in tzz.iterrows() if row['timestamp'] in ts_to_idx]

    bar_st = assign_stereotypes(high, low, close, pivots, len(tohlc))

    ohlc_ts_arr = tohlc['timestamp'].values
    snap_ts_arr = tdf['timestamp'].values
    for i in range(len(tdf)):
        j = bisect.bisect_left(ohlc_ts_arr, snap_ts_arr[i])
        if j < len(ohlc_ts_arr) and ohlc_ts_arr[j] == tdf.iloc[i]['timestamp']:
            st = bar_st[j]
        elif j > 0:
            st = bar_st[j-1]
        else:
            continue
        if st is None:
            continue
        state = tdf.iloc[i]['state_key']
        is_bull = st in ('HH', 'HL')
        if state not in pbull_train:
            pbull_train[state] = {'bull_count': 0, 'n': 0}
        pbull_train[state]['bull_count'] += int(is_bull)
        pbull_train[state]['n'] += 1

# Classify P(bull) signals
for state, data in pbull_train.items():
    if data['n'] < 30:
        data['action'] = 'HOLD'
        continue
    p_bull = data['bull_count'] / data['n']
    data['p_bull'] = p_bull
    # Same thresholds as walk_forward.py: >0.60 ACCUMULATE, <0.40 BLOCK
    if p_bull > 0.60:
        data['action'] = 'ACCUMULATE'
    elif p_bull < 0.40:
        data['action'] = 'BLOCK'
    else:
        data['action'] = 'HOLD'

pbull_states = {s: d for s, d in pbull_train.items() if d['n'] >= 30}
print(f"  P(bull) trained: {len(pbull_states)} states")

# ── Train EV model (forward pivot) ──
print("\n  Training EV model (forward pivot)...")

def compute_forward_labels_train(snap_df, zz_df):
    """Compute forward labels for training data."""
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
        snap_ts = tdf['timestamp'].values
        snap_state = tdf['state_key'].values
        for i in range(len(tdf)):
            j = bisect.bisect_right(zz_ts, snap_ts[i])
            if j >= len(zz_ts):
                continue
            results.append({
                'state_key': snap_state[i],
                'next_type': zz_type[j],
                'next_return': float(zz_ret[j]),
                'next_days': int(zz_days[j]),
            })
    return pd.DataFrame(results)

ev_train = {}  # state → {ev, p_min, p_max, e_ret_min, e_ret_max, n, action, ann_sharpe, e_days}

# Train on zz25 (primary level)
fwd25_train = compute_forward_labels_train(df_train, zz25_train)
print(f"  Forward labels (zz25): {len(fwd25_train):,}")

for state in fwd25_train['state_key'].unique():
    sdf = fwd25_train[fwd25_train['state_key'] == state]
    n = len(sdf)
    if n < 30:
        continue
    p_min = (sdf['next_type'] == 'MIN').mean()
    p_max = 1 - p_min
    e_ret_min = sdf[sdf['next_type']=='MIN']['next_return'].mean() if p_min > 0 else 0
    e_ret_max = sdf[sdf['next_type']=='MAX']['next_return'].mean() if p_max > 0 else 0
    ev = p_min * e_ret_min + p_max * e_ret_max
    std_ret = sdf['next_return'].std()
    sharpe = ev / std_ret if std_ret > 0 else 0
    e_days = sdf['next_days'].mean()
    swings_yr = 252 / e_days if e_days > 0 else 0
    ann_sharpe = sharpe * math.sqrt(swings_yr) if swings_yr > 0 else 0

    # Signal classification (same as generate_ev_derived.py)
    zone = {"<<": "FLOOR", "<": "BELOW", "~": "NEUTRAL", ">": "ABOVE", ">>": "CEILING"}.get(state.split("|")[-1], "NEUTRAL")

    if ev < -0.02:
        action = "BLOCK"
    elif zone == "CEILING" and ev < -0.03:
        action = "TAKE_PROFIT"
    elif zone == "CEILING" and ev < 0 and ann_sharpe < 0:
        action = "REDUCE"
    elif ev > 0.01 and ann_sharpe > 0.5:
        action = "ACCUMULATE"
    elif ev > 0.005 and p_min > 0.40:
        action = "BUY_DIP"
    elif ev > 0.04 and ann_sharpe > 1.0:
        action = "MOMENTUM"
    elif abs(ev) < 0.005:
        action = "WATCH"
    else:
        action = "NO_EDGE"

    ev_train[state] = {
        'ev': ev, 'p_min': p_min, 'p_max': p_max,
        'e_ret_min': e_ret_min, 'e_ret_max': e_ret_max,
        'n': n, 'action': action,
        'ann_sharpe': ann_sharpe, 'e_days': e_days,
    }

print(f"  EV trained: {len(ev_train)} states")

# ═══════════════════════════════════════════════════════════════
# STEP 2: TEST on ≥2023 data — compute actual forward returns
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 90)
print("  STEP 2: TEST ON ≥2023 DATA (out-of-sample)")
print("=" * 90)

# Compute forward labels for test data
zz25_test = zz_test[zz_test['min_swing_pct'] == 0.025]
fwd25_test = compute_forward_labels_train(df_test, zz25_test)
print(f"  Test forward labels: {len(fwd25_test):,}")

# Actual EV per state in test period
actual_by_state = {}
for state in fwd25_test['state_key'].unique():
    sdf = fwd25_test[fwd25_test['state_key'] == state]
    n = len(sdf)
    if n < 10:
        continue
    actual_ev = sdf['next_return'].mean()
    actual_by_state[state] = {
        'actual_ev': actual_ev,
        'n': n,
        'actual_positive': actual_ev > 0,
    }

print(f"  States with test data: {len(actual_by_state)}")

# ═══════════════════════════════════════════════════════════════
# STEP 3: HEAD-TO-HEAD
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 90)
print("  STEP 3: HEAD-TO-HEAD COMPARISON")
print("=" * 90)

common = set(pbull_states.keys()) & set(ev_train.keys()) & set(actual_by_state.keys())
print(f"  Common states: {len(common)}")

# ── Metric 1: Signal accuracy ──
pbull_correct = 0; pbull_total = 0
ev_correct = 0; ev_total = 0

for state in common:
    actual = actual_by_state[state]
    actual_positive = actual['actual_positive']

    # P(bull) signal
    p_act = pbull_states[state]['action']
    p_match = (p_act == 'ACCUMULATE' and actual_positive) or (p_act == 'BLOCK' and not actual_positive)
    pbull_total += 1
    if p_match:
        pbull_correct += 1

    # EV signal
    e_act = ev_train[state]['action']
    # For EV: ACCUMULATE/BUY_DIP/MOMENTUM = bullish, BLOCK/TAKE_PROFIT/REDUCE = bearish
    e_bullish = e_act in ('ACCUMULATE', 'BUY_DIP', 'MOMENTUM')
    e_bearish = e_act in ('BLOCK', 'TAKE_PROFIT', 'REDUCE')
    e_match = (e_bullish and actual_positive) or (e_bearish and not actual_positive)
    ev_total += 1
    if e_match:
        ev_correct += 1

print(f"\n  1. SIGNAL ACCURACY (bullish/bearish direction matches actual):")
print(f"     P(bull): {pbull_correct}/{pbull_total} = {pbull_correct/max(pbull_total,1)*100:.1f}%")
print(f"     EV:      {ev_correct}/{ev_total} = {ev_correct/max(ev_total,1)*100:.1f}%")

# ── Metric 2: Expected return of ACCUMULATE signals ──
pbull_accum_rets = []
ev_accum_rets = []

for state in common:
    actual = actual_by_state[state]
    if pbull_states[state]['action'] == 'ACCUMULATE':
        pbull_accum_rets.append(actual['actual_ev'])
    if ev_train[state]['action'] in ('ACCUMULATE', 'BUY_DIP', 'MOMENTUM'):
        ev_accum_rets.append(actual['actual_ev'])

print(f"\n  2. ACCUMULATE SIGNAL RETURNS (actual out-of-sample):")
if pbull_accum_rets:
    print(f"     P(bull): {len(pbull_accum_rets)} signals, mean={np.mean(pbull_accum_rets)*100:+.2f}%, std={np.std(pbull_accum_rets)*100:.2f}%")
if ev_accum_rets:
    print(f"     EV:      {len(ev_accum_rets)} signals, mean={np.mean(ev_accum_rets)*100:+.2f}%, std={np.std(ev_accum_rets)*100:.2f}%")

# ── Metric 3: Portfolio simulation (signal-weighted) ──
# For each state: if model says ACCUMULATE → invest (get actual return)
#                 if BLOCK → cash (0)
#                 if HOLD/NO_EDGE/WATCH → cash (0)
# Weight by N observations in test
pbull_weighted = []
ev_weighted = []

for state in common:
    actual = actual_by_state[state]
    weight = min(actual['n'], 100)

    p_act = pbull_states[state]['action']
    p_ret = actual['actual_ev'] if p_act == 'ACCUMULATE' else 0
    for _ in range(weight):
        pbull_weighted.append(p_ret)

    e_act = ev_train[state]['action']
    if e_act in ('ACCUMULATE', 'BUY_DIP', 'MOMENTUM'):
        e_ret = actual['actual_ev']
    elif e_act in ('BLOCK', 'TAKE_PROFIT', 'REDUCE'):
        e_ret = 0  # avoid loss
    else:
        e_ret = 0  # cash
    for _ in range(weight):
        ev_weighted.append(e_ret)

print(f"\n  3. PORTFOLIO SIMULATION (signal-weighted, capped 100 obs/state):")
p_mean = np.mean(pbull_weighted) if pbull_weighted else 0
p_std = np.std(pbull_weighted) if pbull_weighted else 0
p_sharpe = p_mean / p_std * math.sqrt(252 / 7) if p_std > 0 else 0
print(f"     P(bull): N={len(pbull_weighted):,}, mean={p_mean*100:+.3f}%, std={p_std*100:.2f}%, Ann Sharpe={p_sharpe:+.2f}")

e_mean = np.mean(ev_weighted) if ev_weighted else 0
e_std = np.std(ev_weighted) if ev_weighted else 0
e_sharpe = e_mean / e_std * math.sqrt(252 / 7) if e_std > 0 else 0
print(f"     EV:      N={len(ev_weighted):,}, mean={e_mean*100:+.3f}%, std={e_std*100:.2f}%, Ann Sharpe={e_sharpe:+.2f}")

# ── Metric 4: Deflated Sharpe Ratio ──
n_trials = len(common)
sr_0 = math.sqrt(2 * math.log(max(n_trials, 2))) if n_trials > 1 else 0

print(f"\n  4. DEFLATED SHARPE RATIO (López de Prado):")
p_sr_se = math.sqrt((1 + 0.5 * p_sharpe**2) / len(pbull_weighted)) if len(pbull_weighted) > 1 else 0
p_dsr = (p_sharpe - sr_0) / p_sr_se if p_sr_se > 0 else 0
e_sr_se = math.sqrt((1 + 0.5 * e_sharpe**2) / len(ev_weighted)) if len(ev_weighted) > 1 else 0
e_dsr = (e_sharpe - sr_0) / e_sr_se if e_sr_se > 0 else 0
print(f"     P(bull): SR={p_sharpe:+.3f}, SR_0={sr_0:.3f} (N_trials={n_trials}), DSR={p_dsr:+.2f}")
print(f"     EV:      SR={e_sharpe:+.3f}, SR_0={sr_0:.3f} (N_trials={n_trials}), DSR={e_dsr:+.2f}")

# ── Metric 5: Head-to-head per state ──
ev_wins = 0; pbull_wins = 0; ties = 0
divergence = []

for state in sorted(common):
    actual = actual_by_state[state]
    actual_positive = actual['actual_positive']
    actual_ret = actual['actual_ev']

    p_act = pbull_states[state]['action']
    e_act = ev_train[state]['action']

    p_bullish = p_act == 'ACCUMULATE'
    e_bullish = e_act in ('ACCUMULATE', 'BUY_DIP', 'MOMENTUM')

    p_match = (p_bullish and actual_positive) or (not p_bullish and not actual_positive)
    e_match = (e_bullish and actual_positive) or (not e_bullish and not actual_positive)

    if p_match and not e_match:
        winner = "P(bull)"; pbull_wins += 1
    elif e_match and not p_match:
        winner = "EV"; ev_wins += 1
    else:
        winner = "TIE"; ties += 1

    divergence.append((state, p_act, e_act, actual_ret, winner))

# ── Metric 6: False positives / negatives ──
print(f"\n  5. HEAD-TO-HEAD SCORE:")
print(f"     EV wins:      {ev_wins}")
print(f"     P(bull) wins: {pbull_wins}")
print(f"     Ties:         {ties}")

print(f"\n  6. CRITICAL FALSE POSITIVES (model says ACCUMULATE, actual < 0):")
for state, p_act, e_act, actual_ret, winner in sorted(divergence, key=lambda x: x[3]):
    if p_act == 'ACCUMULATE' and actual_ret < 0:
        print(f"     P(bull): {state}: ACCUM but actual={actual_ret*100:+.2f}% | EV says {e_act}")
    if e_act in ('ACCUMULATE', 'BUY_DIP') and actual_ret < 0:
        print(f"     EV:      {state}: {e_act} but actual={actual_ret*100:+.2f}% | P(bull) says {p_act}")

print(f"\n  7. CRITICAL FALSE NEGATIVES (model says BLOCK/HOLD, actual > +3%):")
for state, p_act, e_act, actual_ret, winner in sorted(divergence, key=lambda x: -x[3]):
    if p_act in ('BLOCK', 'HOLD') and actual_ret > 0.03:
        print(f"     P(bull): {state}: {p_act} but actual={actual_ret*100:+.2f}% | EV says {e_act}")
    if e_act in ('BLOCK', 'WATCH', 'NO_EDGE', 'REDUCE') and actual_ret > 0.03:
        print(f"     EV:      {state}: {e_act} but actual={actual_ret*100:+.2f}% | P(bull) says {p_act}")

# ── Per-state details for top divergences ──
print(f"\n  8. TOP 15 STATES BY |actual return|:")
print(f"  {'State':>20s} {'P(bull)':>10s} {'EV':>10s} {'Actual':>8s} {'Winner':>8s}")
for state, p_act, e_act, actual_ret, winner in sorted(divergence, key=lambda x: -abs(x[3]))[:15]:
    print(f"  {state:>20s} {p_act:>10s} {e_act:>10s} {actual_ret*100:>+7.2f}% {winner:>8s}")

# ═══════════════════════════════════════════════════════════════
# VERDICT
# ═══════════════════════════════════════════════════════════════
print(f"\n\n{'=' * 90}")
print(f"  VERDICT — Walk-Forward Pipeline Comparison")
print(f"{'=' * 90}")
print(f"  Train: ≤2022 ({len(fwd25_train):,} forward labels)")
print(f"  Test:  ≥2023 ({len(fwd25_test):,} forward labels)")
print(f"  Common states: {len(common)}")
print(f"")
print(f"  {'Metric':>30s} {'P(bull)':>12s} {'EV':>12s} {'Winner':>8s}")
print(f"  {'-'*30} {'-'*12} {'-'*12} {'-'*8}")
print(f"  {'Signal Accuracy':>30s} {pbull_correct/max(pbull_total,1)*100:>10.1f}% {ev_correct/max(ev_total,1)*100:>10.1f}% "
      f"{'P(bull)' if pbull_correct > ev_correct else 'EV' if ev_correct > pbull_correct else 'TIE':>8s}")
print(f"  {'Ann Sharpe':>30s} {p_sharpe:>+11.2f} {e_sharpe:>+11.2f} "
      f"{'P(bull)' if p_sharpe > e_sharpe else 'EV' if e_sharpe > p_sharpe else 'TIE':>8s}")
print(f"  {'Deflated Sharpe':>30s} {p_dsr:>+11.2f} {e_dsr:>+11.2f} "
      f"{'P(bull)' if p_dsr > e_dsr else 'EV' if e_dsr > p_dsr else 'TIE':>8s}")
print(f"  {'Head-to-head wins':>30s} {pbull_wins:>12d} {ev_wins:>12d} "
      f"{'P(bull)' if pbull_wins > ev_wins else 'EV' if ev_wins > pbull_wins else 'TIE':>8s}")
if pbull_accum_rets and ev_accum_rets:
    print(f"  {'Accum mean return':>30s} {np.mean(pbull_accum_rets)*100:>+10.2f}% {np.mean(ev_accum_rets)*100:>+10.2f}% "
          f"{'P(bull)' if np.mean(pbull_accum_rets) > np.mean(ev_accum_rets) else 'EV':>8s}")
print(f"")

# Final verdict
ev_wins_count = sum([
    e_sharpe > p_sharpe,
    e_dsr > p_dsr,
    ev_correct > pbull_correct,
    ev_wins > pbull_wins,
])
pbull_wins_count = sum([
    p_sharpe > e_sharpe,
    p_dsr > e_dsr,
    pbull_correct > ev_correct,
    pbull_wins > ev_wins,
])

if ev_wins_count > pbull_wins_count:
    print(f"  ✅ EV MODEL SUPERIOR — wins {ev_wins_count}/{ev_wins_count+pbull_wins_count} metrics")
elif pbull_wins_count > ev_wins_count:
    print(f"  ❌ P(bull) MODEL SUPERIOR — wins {pbull_wins_count}/{ev_wins_count+pbull_wins_count} metrics")
    print(f"     EV does NOT beat current model. Do NOT implement as replacement.")
else:
    print(f"  ⚠️  TIE — {ev_wins_count} wins each. Inconclusive.")

print(f"\n  Elapsed: {time.time()-t0:.1f}s")
print(f"{'=' * 90}")
