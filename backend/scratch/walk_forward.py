#!/usr/bin/env python3
"""
Walk-Forward Validation — EV Model vs P(bull) Model
====================================================
Split: 2007-2022 train, 2023-2026 test (out-of-sample).

For each period:
  1. Compute P(bull) = P(HH+HL | state)  [current model — zigzag stereotypes]
  2. Compute EV = P(MIN)*E[ret|MIN] + P(MAX)*E[ret|MAX]  [proposed model]
  3. Compare: which model produces better signals out-of-sample?

Metrics:
  - Signal accuracy: does the signal direction match actual outcome?
  - Expected return per signal
  - Sharpe of signal-weighted returns
  - Deflated Sharpe Ratio (López de Prado)
  - Head-to-head: train EV, test EV vs train P(bull), test P(bull)

Constraint: only accept EV model if it beats P(bull) out-of-sample.
"""
import os, sys, time, math, bisect
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
from dotenv import load_dotenv
load_dotenv(root / ".env")

import psycopg2

t0 = time.time()
conn = psycopg2.connect(os.environ["POSTGRES_URL"])

# ── Load channel_snapshots ──
print("Loading channel_snapshots...")
df = pd.read_sql("""
    SELECT ticker, timestamp, tide_slope, current_slope, vwap_sigma_wave
    FROM engine.channel_snapshots
    WHERE timeframe = '1d'
      AND tide_slope IS NOT NULL
      AND current_slope IS NOT NULL
      AND vwap_sigma_wave IS NOT NULL
    ORDER BY ticker, timestamp
""", conn)
df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
print(f"  {len(df):,} rows ({time.time()-t0:.1f}s)")

# ── Load zigzag pivots (2.5% level for primary comparison) ──
print("Loading zigzag_points (2.5%)...")
zz = pd.read_sql("""
    SELECT ticker, timestamp, tp_type, min_swing_pct,
           swing_return, swing_days
    FROM engine.zigzag_points
    WHERE min_swing_pct = 0.025 AND swing_days > 0
    ORDER BY ticker, timestamp
""", conn)
zz['timestamp'] = pd.to_datetime(zz['timestamp'], utc=True)
print(f"  {len(zz):,} rows ({time.time()-t0:.1f}s)")

# ── Load OHLCV for stereotype computation (HH/HL/LH/LL) ──
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

# ── Classify states ──
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

df['T'] = df['tide_slope'].apply(lambda x: cls_slope(x,'T'))
df['C'] = df['current_slope'].apply(lambda x: cls_slope(x,'C'))
df['svw'] = df['vwap_sigma_wave'].apply(cls_sigma)
df['state'] = df['T'] + '|' + df['C'] + '|' + df['svw']
print(f"  States: {df['state'].nunique()} ({time.time()-t0:.1f}s)")

# ── Split: train (≤2022-12-31) vs test (≥2023-01-01) ──
split_date = pd.Timestamp('2023-01-01', tz='UTC')
df_train = df[df['timestamp'] < split_date].copy()
df_test = df[df['timestamp'] >= split_date].copy()
print(f"\n  Train: {len(df_train):,} rows (≤2022)")
print(f"  Test:  {len(df_test):,} rows (≥2023)")

# ── Compute forward labels (next pivot after each bar) ──
def compute_forward_labels(snap_df, zz_df):
    """For each snapshot bar, find next zigzag pivot after it."""
    labels = []
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
        snap_state = tdf['state'].values
        for i in range(len(tdf)):
            j = bisect.bisect_right(zz_ts, snap_ts[i])
            if j >= len(zz_ts):
                continue
            labels.append({
                'ticker': ticker,
                'timestamp': snap_ts[i],
                'state': snap_state[i],
                'next_type': zz_type[j],
                'next_return': float(zz_ret[j]),
                'next_days': int(zz_days[j]),
            })
    return pd.DataFrame(labels)

# ── Compute stereotypes (HH/HL/LH/LL) for P(bull) model ──
def assign_stereotypes(high, low, close, pivots, n_bars):
    """Assign HH/HL/LH/LL stereotype to each bar using zigzag pivots."""
    bar_st = [None] * n_bars
    if len(pivots) < 4:
        return bar_st
    maxes = [(idx, val) for t, idx, val in pivots if t == "MAX"]
    mins = [(idx, val) for t, idx, val in pivots if t == "MIN"]
    if len(maxes) < 2 or len(mins) < 2:
        return bar_st

    zig_labels = []
    for i in range(1, len(maxes)):
        label = "H" if maxes[i][1] > maxes[i-1][1] else "L"
        zig_labels.append((maxes[i][0], label))
    zag_labels = []
    for i in range(1, len(mins)):
        label = "H" if mins[i][1] > mins[i-1][1] else "L"
        zag_labels.append((mins[i][0], label))

    zi, za = 0, 0
    while zi < len(zig_labels) and za < len(zag_labels):
        zig_idx, zig_l = zig_labels[zi]
        zag_idx, zag_l = zag_labels[za]
        stereotype = zig_l + zag_l
        cycle_start = min(zig_idx, zag_idx)
        cycle_end = max(zig_idx, zag_idx)
        for b in range(cycle_start, min(cycle_end + 1, n_bars)):
            bar_st[b] = stereotype
        zi += 1
        za += 1

    last_st = None
    for b in range(n_bars):
        if bar_st[b] is not None:
            last_st = bar_st[b]
        elif last_st is not None:
            bar_st[b] = last_st
    return bar_st

def compute_pbull_labels(snap_df, ohlc_df, zz_df):
    """Compute P(bull) = P(HH+HL) labels using zigzag stereotypes."""
    labels = []
    for ticker in snap_df['ticker'].unique():
        tdf = snap_df[snap_df['ticker'] == ticker].sort_values('timestamp').reset_index(drop=True)
        tohlc = ohlc_df[ohlc_df['ticker'] == ticker].sort_values('timestamp').reset_index(drop=True)
        tzz = zz_df[zz_df['ticker'] == ticker].sort_values('timestamp').reset_index(drop=True)
        if len(tohlc) < 250 or len(tzz) < 4:
            continue

        high = tohlc['high'].values.astype(float)
        low = tohlc['low'].values.astype(float)
        close = tohlc['close'].values.astype(float)
        ts_list = tohlc['timestamp'].tolist()

        # Map zigzag pivots to ohlc bar indices
        ts_to_idx = {ts: i for i, ts in enumerate(ts_list)}
        pivots = []
        for _, row in tzz.iterrows():
            idx = ts_to_idx.get(row['timestamp'])
            if idx is not None:
                pivots.append((row['tp_type'], idx, float(row.get('price', close[idx]))))

        bar_st = assign_stereotypes(high, low, close, pivots, len(tohlc))

        # Map back to snapshot timestamps
        snap_ts = tdf['timestamp'].values
        snap_state = tdf['state'].values
        ohlc_ts_arr = tohlc['timestamp'].values

        for i in range(len(tdf)):
            # Find corresponding ohlc bar
            j = bisect.bisect_left(ohlc_ts_arr, snap_ts[i])
            if j < len(ohlc_ts_arr) and ohlc_ts_arr[j] == snap_ts[i]:
                st = bar_st[j]
                if st is not None:
                    labels.append({
                        'ticker': ticker,
                        'timestamp': snap_ts[i],
                        'state': snap_state[i],
                        'stereotype': st,
                        'is_bull': st in ('HH', 'HL'),
                    })
            elif j > 0:
                st = bar_st[j-1]
                if st is not None:
                    labels.append({
                        'ticker': ticker,
                        'timestamp': snap_ts[i],
                        'state': snap_state[i],
                        'stereotype': st,
                        'is_bull': st in ('HH', 'HL'),
                    })
    return pd.DataFrame(labels)


print("\nComputing forward labels (EV model)...")
# Forward labels for ALL data (we'll split after)
fwd_all = compute_forward_labels(df, zz)
fwd_all['timestamp'] = pd.to_datetime(fwd_all['timestamp'], utc=True)
print(f"  {len(fwd_all):,} forward labels ({time.time()-t0:.1f}s)")

print("Computing stereotype labels (P(bull) model)...")
# Stereotype labels for ALL data
st_all = compute_pbull_labels(df, ohlc, zz)
st_all['timestamp'] = pd.to_datetime(st_all['timestamp'], utc=True)
print(f"  {len(st_all):,} stereotype labels ({time.time()-t0:.1f}s)")

# ── Split into train/test ──
fwd_train = fwd_all[fwd_all['timestamp'] < split_date]
fwd_test = fwd_all[fwd_all['timestamp'] >= split_date]
st_train = st_all[st_all['timestamp'] < split_date]
st_test = st_all[st_all['timestamp'] >= split_date]

print(f"\n  EV labels  — Train: {len(fwd_train):,}, Test: {len(fwd_test):,}")
print(f"  P(bull)    — Train: {len(st_train):,}, Test: {len(st_test):,}")

# ═══════════════════════════════════════════════════════════════
# Build models on TRAIN data
# ═══════════════════════════════════════════════════════════════

# ── P(bull) model (current) — from train stereotypes ──
print("\n" + "=" * 90)
print("  P(bull) MODEL (current) — trained on ≤2022")
print("=" * 90)

pbull_model = {}  # state -> {p_bull, n, action}
for state in st_train['state'].unique():
    sdf = st_train[st_train['state'] == state]
    n = len(sdf)
    if n < 30:
        continue
    p_bull = sdf['is_bull'].mean()
    # Action: ACCUMULATE if p_bull > 0.60, BLOCK if < 0.40, else HOLD
    if p_bull > 0.60:
        action = "ACCUMULATE"
    elif p_bull < 0.40:
        action = "BLOCK"
    else:
        action = "HOLD"
    pbull_model[state] = {'p_bull': p_bull, 'n': n, 'action': action}
    print(f"  {state:>20s} N={n:>6,} P(bull)={p_bull:.3f} → {action}")

print(f"\n  P(bull) states: {len(pbull_model)}")

# ── EV model (proposed) — from train forward labels ──
print("\n" + "=" * 90)
print("  EV MODEL (proposed) — trained on ≤2022")
print("=" * 90)

ev_model = {}  # state -> {ev, p_min, p_max, e_ret_min, e_ret_max, n, action, sharpe}
for state in fwd_train['state'].unique():
    sdf = fwd_train[fwd_train['state'] == state]
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

    # Action: ACCUMULATE if EV > 1%, BLOCK if EV < -2%, else HOLD
    if ev > 0.01 and ann_sharpe > 0.5:
        action = "ACCUMULATE"
    elif ev < -0.02:
        action = "BLOCK"
    elif ev < -0.005:
        action = "REDUCE"
    else:
        action = "HOLD"

    ev_model[state] = {
        'ev': ev, 'p_min': p_min, 'p_max': p_max,
        'e_ret_min': e_ret_min, 'e_ret_max': e_ret_max,
        'n': n, 'action': action,
        'sharpe': sharpe, 'ann_sharpe': ann_sharpe,
        'e_days': e_days,
    }

print(f"\n  EV states: {len(ev_model)}")

# ═══════════════════════════════════════════════════════════════
# TEST: evaluate both models on out-of-sample (≥2023)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 90)
print("  OUT-OF-SAMPLE TEST (≥2023)")
print("=" * 90)

# For the test set, we need actual outcomes.
# For P(bull): actual = stereotype (HH/HL = bull)
# For EV: actual = next pivot return

# ── P(bull) test ──
pbull_test_results = []
for state, model in pbull_model.items():
    sdf = st_test[st_test['state'] == state]
    n = len(sdf)
    if n < 10:
        continue
    actual_p_bull = sdf['is_bull'].mean()
    predicted_p_bull = model['p_bull']
    error = abs(actual_p_bull - predicted_p_bull)
    # Signal accuracy: does the action direction match?
    actual_action = "ACCUMULATE" if actual_p_bull > 0.60 else ("BLOCK" if actual_p_bull < 0.40 else "HOLD")
    signal_correct = model['action'] == actual_action
    # Expected return of following this signal
    if model['action'] == "ACCUMULATE":
        # If we accumulate, we hold for the "bull" outcome
        # Actual return = mean of forward returns for bull bars
        fwd_sdf = fwd_test[fwd_test['state'] == state]
        if len(fwd_sdf) > 0:
            actual_ret = fwd_sdf['next_return'].mean()
        else:
            actual_ret = 0
    elif model['action'] == "BLOCK":
        # If we block, we avoid — return = 0 (cash)
        actual_ret = 0
    else:
        actual_ret = 0  # HOLD = cash

    pbull_test_results.append({
        'state': state, 'n': n,
        'pred_p_bull': predicted_p_bull, 'actual_p_bull': actual_p_bull,
        'error': error,
        'action': model['action'], 'actual_action': actual_action,
        'signal_correct': signal_correct,
        'actual_ret': actual_ret,
    })

# ── EV test ──
ev_test_results = []
for state, model in ev_model.items():
    sdf = fwd_test[fwd_test['state'] == state]
    n = len(sdf)
    if n < 10:
        continue
    actual_ev = sdf['next_return'].mean()
    predicted_ev = model['ev']
    error = abs(actual_ev - predicted_ev)
    # Signal accuracy
    actual_action = "ACCUMULATE" if actual_ev > 0.01 else ("BLOCK" if actual_ev < -0.02 else "HOLD")
    signal_correct = model['action'] == actual_action
    # Expected return of following this signal
    if model['action'] == "ACCUMULATE":
        actual_ret = sdf['next_return'].mean()
    elif model['action'] == "BLOCK":
        actual_ret = 0  # cash
    elif model['action'] == "REDUCE":
        actual_ret = -sdf['next_return'].mean() * 0.5  # partial trim
    else:
        actual_ret = 0  # HOLD

    ev_test_results.append({
        'state': state, 'n': n,
        'pred_ev': predicted_ev, 'actual_ev': actual_ev,
        'error': error,
        'action': model['action'], 'actual_action': actual_action,
        'signal_correct': signal_correct,
        'actual_ret': actual_ret,
        'ann_sharpe': model['ann_sharpe'],
    })

# ═══════════════════════════════════════════════════════════════
# HEAD-TO-HEAD COMPARISON
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 90)
print("  HEAD-TO-HEAD: P(bull) vs EV — out-of-sample (≥2023)")
print("=" * 90)

# States that appear in both models
common_states = set(pbull_model.keys()) & set(ev_model.keys())
common_states = [s for s in common_states if s in [r['state'] for r in pbull_test_results] and s in [r['state'] for r in ev_test_results]]

print(f"\n  Common states tested: {len(common_states)}")

# ── Metric 1: Signal Accuracy ──
pbull_correct = sum(1 for r in pbull_test_results if r['signal_correct'])
pbull_total = sum(1 for r in pbull_test_results)
ev_correct = sum(1 for r in ev_test_results if r['signal_correct'])
ev_total = sum(1 for r in ev_test_results)

print(f"\n  1. SIGNAL ACCURACY (action direction matches actual):")
print(f"     P(bull): {pbull_correct}/{pbull_total} = {pbull_correct/pbull_total*100:.1f}%")
print(f"     EV:      {ev_correct}/{ev_total} = {ev_correct/ev_total*100:.1f}%")

# ── Metric 2: Prediction Error ──
pbull_errors = [r['error'] for r in pbull_test_results]
ev_errors = [r['error'] for r in ev_test_results]
print(f"\n  2. PREDICTION ERROR (|predicted - actual|):")
print(f"     P(bull): mean={np.mean(pbull_errors):.4f}, median={np.median(pbull_errors):.4f}")
print(f"     EV:      mean={np.mean(ev_errors):.4f}, median={np.median(ev_errors):.4f}")

# ── Metric 3: Expected Return per ACCUMULATE signal ──
pbull_accum = [r for r in pbull_test_results if r['action'] == 'ACCUMULATE']
ev_accum = [r for r in ev_test_results if r['action'] == 'ACCUMULATE']
pbull_accum_rets = [r['actual_ret'] for r in pbull_accum if r['actual_ret'] != 0]
ev_accum_rets = [r['actual_ret'] for r in ev_accum]

print(f"\n  3. ACCUMULATE SIGNAL PERFORMANCE:")
print(f"     P(bull): {len(pbull_accum)} ACCUMULATE signals, "
      f"mean actual return = {np.mean(pbull_accum_rets)*100:+.2f}% (if any)")
if pbull_accum_rets:
    print(f"             N with returns: {len(pbull_accum_rets)}, "
          f"mean = {np.mean(pbull_accum_rets)*100:+.2f}%, "
          f"std = {np.std(pbull_accum_rets)*100:.2f}%")
print(f"     EV:      {len(ev_accum)} ACCUMULATE signals, "
      f"mean actual return = {np.mean(ev_accum_rets)*100:+.2f}%")
if ev_accum_rets:
    print(f"             N with returns: {len(ev_accum_rets)}, "
          f"mean = {np.mean(ev_accum_rets)*100:+.2f}%, "
          f"std = {np.std(ev_accum_rets)*100:.2f}%")

# ── Metric 4: Portfolio Sharpe (signal-weighted) ──
# Simulate: for each state in test, if model says ACCUMULATE, "invest" and get actual return
# Sharpe = mean(returns) / std(returns) * sqrt(annualization)

pbull_port_rets = [r['actual_ret'] for r in pbull_test_results if r['action'] in ('ACCUMULATE','BLOCK','HOLD')]
ev_port_rets = [r['actual_ret'] for r in ev_test_results if r['action'] in ('ACCUMULATE','BLOCK','REDUCE','HOLD')]

# Weighted by N
pbull_weighted = []
for r in pbull_test_results:
    for _ in range(min(r['n'], 100)):  # cap weight
        pbull_weighted.append(r['actual_ret'])
ev_weighted = []
for r in ev_test_results:
    for _ in range(min(r['n'], 100)):
        ev_weighted.append(r['actual_ret'])

print(f"\n  4. PORTFOLIO SIMULATION (signal-weighted, capped at 100 obs/state):")
if pbull_weighted:
    p_mean = np.mean(pbull_weighted)
    p_std = np.std(pbull_weighted)
    p_sharpe = p_mean / p_std * math.sqrt(252 / 7) if p_std > 0 else 0  # ~7 days per swing
    print(f"     P(bull): N={len(pbull_weighted):,}, "
          f"mean={p_mean*100:+.3f}%, std={p_std*100:.2f}%, "
          f"annualized Sharpe={p_sharpe:+.2f}")
if ev_weighted:
    e_mean = np.mean(ev_weighted)
    e_std = np.std(ev_weighted)
    e_sharpe = e_mean / e_std * math.sqrt(252 / 7) if e_std > 0 else 0
    print(f"     EV:      N={len(ev_weighted):,}, "
          f"mean={e_mean*100:+.3f}%, std={e_std*100:.2f}%, "
          f"annualized Sharpe={e_sharpe:+.2f}")

# ── Metric 5: Deflated Sharpe Ratio (López de Prado) ──
print(f"\n  5. DEFLATED SHARPE RATIO (López de Prado):")
n_trials = len(common_states)
# SR_0 = expected max SR under null (all trials independent)
# Approximation: SR_0 ≈ sqrt(2 * ln(n_trials))
sr_0 = math.sqrt(2 * math.log(max(n_trials, 2))) if n_trials > 1 else 0
# Variance of SR estimate
if pbull_weighted:
    p_var = np.var(pbull_weighted, ddof=1)
    p_sr_se = math.sqrt((1 + 0.5 * p_sharpe**2) / len(pbull_weighted)) if len(pbull_weighted) > 1 else 0
    p_dsr = (p_sharpe - sr_0) / p_sr_se if p_sr_se > 0 else 0
    print(f"     P(bull): SR={p_sharpe:+.3f}, SR_0={sr_0:.3f} (N_trials={n_trials}), "
          f"SE={p_sr_se:.3f}, DSR={p_dsr:+.2f}")
if ev_weighted:
    e_var = np.var(ev_weighted, ddof=1)
    e_sr_se = math.sqrt((1 + 0.5 * e_sharpe**2) / len(ev_weighted)) if len(ev_weighted) > 1 else 0
    e_dsr = (e_sharpe - sr_0) / e_sr_se if e_sr_se > 0 else 0
    print(f"     EV:      SR={e_sharpe:+.3f}, SR_0={sr_0:.3f} (N_trials={n_trials}), "
          f"SE={e_sr_se:.3f}, DSR={e_dsr:+.2f}")

# ── Metric 6: Head-to-head per state ──
print(f"\n  6. HEAD-TO-HEAD PER STATE (top 15 by divergence):")
print(f"  {'State':>20s} {'P(bull) act':>11s} {'P(bull) ret':>11s} "
      f"{'EV act':>8s} {'EV ret':>8s} {'Winner':>8s}")

pbull_lookup = {r['state']: r for r in pbull_test_results}
ev_lookup = {r['state']: r for r in ev_test_results}

divergence = []
for state in common_states:
    pr = pbull_lookup.get(state)
    er = ev_lookup.get(state)
    if not pr or not er:
        continue
    # Winner = the model whose signal matches reality better
    # Reality = actual forward return
    actual_ret = er['actual_ev']  # mean forward return in test
    pbull_would_accum = pr['action'] == 'ACCUMULATE'
    ev_would_accum = er['action'] == 'ACCUMULATE'
    actual_positive = actual_ret > 0

    # Did P(bull) signal match?
    pbull_match = (pbull_would_accum and actual_positive) or (not pbull_would_accum and not actual_positive)
    # Did EV signal match?
    ev_match = (ev_would_accum and actual_positive) or (not ev_would_accum and not actual_positive)

    if pbull_match and not ev_match:
        winner = "P(bull)"
    elif ev_match and not pbull_match:
        winner = "EV"
    else:
        winner = "TIE"

    divergence.append((state, pr['action'], pr['actual_ret'], er['action'], er['actual_ret'], winner, actual_ret))

# Sort by actual return (most extreme first)
divergence.sort(key=lambda x: -abs(x[6]))

for state, p_act, p_ret, e_act, e_ret, winner, actual in divergence[:15]:
    print(f"  {state:>20s} {p_act:>11s} {p_ret*100:>+10.2f}% {e_act:>8s} {e_ret*100:>+7.2f}% {winner:>8s}")

# ── Summary ──
ev_wins = sum(1 for d in divergence if d[5] == "EV")
pbull_wins = sum(1 for d in divergence if d[5] == "P(bull)")
ties = sum(1 for d in divergence if d[5] == "TIE")

print(f"\n  HEAD-TO-HEAD SCORE:")
print(f"     EV wins:      {ev_wins}")
print(f"     P(bull) wins: {pbull_wins}")
print(f"     Ties:         {ties}")
print(f"     Total:         {ev_wins + pbull_wins + ties}")

# ── Key false positives/negatives ──
print(f"\n  CRITICAL FALSE POSITIVES (P(bull) says ACCUMULATE, actual return < 0):")
for state, p_act, p_ret, e_act, e_ret, winner, actual in divergence:
    if p_act == "ACCUMULATE" and actual < 0:
        print(f"    {state}: P(bull)=ACCUM but actual ret={actual*100:+.2f}% | EV says {e_act}")
        break

print(f"\n  CRITICAL FALSE NEGATIVES (P(bull) says BLOCK/HOLD, actual return > 0):")
for state, p_act, p_ret, e_act, e_ret, winner, actual in divergence:
    if p_act in ("BLOCK", "HOLD") and actual > 0.03:
        print(f"    {state}: P(bull)={p_act} but actual ret={actual*100:+.2f}% | EV says {e_act}")

# ═══════════════════════════════════════════════════════════════
# VERDICT
# ═══════════════════════════════════════════════════════════════
print(f"\n\n{'=' * 90}")
print(f"  VERDICT")
print(f"{'=' * 90}")
print(f"  Train period: ≤2022 ({len(fwd_train):,} obs)")
print(f"  Test period:  ≥2023 ({len(fwd_test):,} obs)")
print(f"  States tested: {len(common_states)}")
print(f"")
if pbull_weighted and ev_weighted:
    print(f"  P(bull) annualized Sharpe:  {p_sharpe:+.2f}")
    print(f"  EV annualized Sharpe:      {e_sharpe:+.2f}")
    print(f"  P(bull) Deflated Sharpe:   {p_dsr:+.2f}")
    print(f"  EV Deflated Sharpe:        {e_dsr:+.2f}")
print(f"")
print(f"  Signal accuracy P(bull):    {pbull_correct}/{pbull_total} = {pbull_correct/max(pbull_total,1)*100:.1f}%")
print(f"  Signal accuracy EV:         {ev_correct}/{ev_total} = {ev_correct/max(ev_total,1)*100:.1f}%")
print(f"")
print(f"  Head-to-head: EV={ev_wins}, P(bull)={pbull_wins}, Ties={ties}")
print(f"")

if ev_weighted and pbull_weighted and e_sharpe > p_sharpe and ev_correct > pbull_correct:
    print(f"  ✅ EV MODEL SUPERIOR — higher Sharpe AND higher signal accuracy out-of-sample")
elif ev_weighted and pbull_weighted and e_sharpe > p_sharpe:
    print(f"  ✅ EV MODEL SUPERIOR — higher Sharpe out-of-sample (signal accuracy comparable)")
elif ev_wins > pbull_wins:
    print(f"  ✅ EV MODEL SUPERIOR — more head-to-head wins out-of-sample")
else:
    print(f"  ❌ EV MODEL DOES NOT BEAT P(bull) — recommendation: DO NOT implement")

print(f"\n  Elapsed: {time.time()-t0:.1f}s")
print(f"{'=' * 90}")
