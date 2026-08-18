#!/usr/bin/env python3
"""
Expected Value Analysis — Next Pivot Forward Model
===================================================
For each bar in each T×C×σVw state, find the NEXT zigzag pivot that
forms AFTER this bar. Compute:
  - P(next=MIN), P(next=MAX)
  - E[swing_return | MIN], E[swing_return | MAX]
  - E[swing_days | MIN], E[swing_days | MAX]
  - Expected Value = P(MIN)*E[ret|MIN] + P(MAX)*E[ret|MAX]
  - Compare EV vs current P(bull) — does EV add information?

Constraint: only accept models that beat the current one.
"""
import os, sys, time
from pathlib import Path
from collections import defaultdict
import numpy as np

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
from dotenv import load_dotenv
load_dotenv(root / ".env")

import psycopg2
import pandas as pd

t0 = time.time()
conn = psycopg2.connect(os.environ["POSTGRES_URL"])

# ── Load channel_snapshots (slopes for state classification) ──
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
print(f"  {len(df):,} rows ({time.time()-t0:.1f}s)")

# ── Load zigzag pivots (all 3 levels) ──
print("Loading zigzag_points...")
zz = pd.read_sql("""
    SELECT ticker, timestamp, tp_type, min_swing_pct,
           swing_return, swing_days, swing_speed
    FROM engine.zigzag_points
    WHERE swing_days > 0
    ORDER BY ticker, timestamp
""", conn)
print(f"  {len(zz):,} rows ({time.time()-t0:.1f}s)")
conn.close()

# ── Classify states (same thresholds as model) ──
SLOPE_TH = {
    "T": {"+": (0.0456, 0.0983), "-": (0.0263, 0.0765)},
    "C": {"+": (0.0845, 0.1749), "-": (0.0613, 0.1583)},
}
SIGMA_BINS = [(-999,-1.0,"<<"),(-1.0,-0.3,"<"),(-0.3,0.3,"~"),(0.3,1.0,">"),(1.0,999,">>")]

def cls_slope(v, ch):
    th = SLOPE_TH[ch]
    if v >= 0:
        p33, p66 = th["+"]
        if v >= p66: return f"{ch}+++"
        elif v >= p33: return f"{ch}++"
        else: return f"{ch}+"
    else:
        p33, p66 = th["-"]
        av = abs(v)
        if av >= p66: return f"{ch}---"
        elif av >= p33: return f"{ch}--"
        else: return f"{ch}-"

def cls_sigma(v):
    for lo,hi,l in SIGMA_BINS:
        if lo <= v < hi: return l
    return ">>"

df['T'] = df['tide_slope'].apply(lambda x: cls_slope(x,'T'))
df['C'] = df['current_slope'].apply(lambda x: cls_slope(x,'C'))
df['svw'] = df['vwap_sigma_wave'].apply(cls_sigma)
df['state'] = df['T'] + '|' + df['C'] + '|' + df['svw']
print(f"  States classified: {df['state'].nunique()} ({time.time()-t0:.1f}s)")

# ── For each bar, find the NEXT zigzag pivot after it ──
# Strategy: for each ticker, merge snapshots with zigzag pivots,
# and for each snapshot bar, find the first pivot with timestamp > bar timestamp

print("Computing next-pivot forward labels...")

# Split zigzag by level
zz_levels = {lvl: zz[zz['min_swing_pct'] == lvl].copy() for lvl in [0.025, 0.05, 0.075]}

results = []
tickers = df['ticker'].unique()
total_tickers = len(tickers)

for ti, ticker in enumerate(tickers):
    if (ti+1) % 100 == 0:
        print(f"  [{ti+1}/{total_tickers}] {time.time()-t0:.1f}s")

    tdf = df[df['ticker'] == ticker].sort_values('timestamp').reset_index(drop=True)

    for lvl in [0.025, 0.05, 0.075]:
        tzz = zz_levels[lvl]
        tzz = tzz[tzz['ticker'] == ticker].sort_values('timestamp').reset_index(drop=True)
        if len(tzz) == 0:
            continue

        # For each snapshot bar, find first pivot after it
        zz_ts = tzz['timestamp'].values
        zz_type = tzz['tp_type'].values
        zz_ret = tzz['swing_return'].values
        zz_days = tzz['swing_days'].values
        zz_speed = tzz['swing_speed'].values

        snap_ts = tdf['timestamp'].values
        snap_state = tdf['state'].values

        # Use searchsorted: for each snap_ts, find first zz_ts > snap_ts
        # zz_ts is sorted, snap_ts is sorted
        import bisect
        for i in range(len(snap_ts)):
            # Find first pivot index where zz_ts > snap_ts[i]
            j = bisect.bisect_right(zz_ts, snap_ts[i])
            if j >= len(zz_ts):
                continue  # No future pivot

            results.append({
                'ticker': ticker,
                'state': snap_state[i],
                'level': lvl,
                'next_type': zz_type[j],
                'next_return': float(zz_ret[j]),
                'next_days': int(zz_days[j]),
                'next_speed': float(zz_speed[j]),
            })

ev_df = pd.DataFrame(results)
print(f"  Forward labels computed: {len(ev_df):,} ({time.time()-t0:.1f}s)")

# ═══════════════════════════════════════════════════════════════
# ANALYSIS 1: Expected Value by state (zz 2.5% level)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 90)
print("  ANALYSIS 1: Expected Value by state — next 2.5% pivot")
print("=" * 90)

ev25 = ev_df[ev_df['level'] == 0.025]
top_states = ev25['state'].value_counts().head(20).index.tolist()

print(f"\n  {'State':>20s} {'N':>7s} {'P(MIN)':>6s} {'P(MAX)':>6s} "
      f"{'E[ret|MIN]':>11s} {'E[ret|MAX]':>11s} {'EV':>8s} "
      f"{'E[days]':>7s} {'E[speed]':>8s}")

ev_by_state = {}
for state in top_states:
    sdf = ev25[ev25['state'] == state]
    n = len(sdf)
    if n < 50:
        continue
    p_min = (sdf['next_type'] == 'MIN').mean()
    p_max = (sdf['next_type'] == 'MAX').mean()
    e_ret_min = sdf[sdf['next_type']=='MIN']['next_return'].mean() if p_min > 0 else 0
    e_ret_max = sdf[sdf['next_type']=='MAX']['next_return'].mean() if p_max > 0 else 0
    ev = p_min * e_ret_min + p_max * e_ret_max
    e_days = sdf['next_days'].mean()
    e_speed = sdf['next_speed'].abs().mean()

    ev_by_state[state] = {
        'n': n, 'p_min': p_min, 'p_max': p_max,
        'e_ret_min': e_ret_min, 'e_ret_max': e_ret_max,
        'ev': ev, 'e_days': e_days, 'e_speed': e_speed,
    }

    print(f"  {state:>20s} {n:>7,} {p_min:>5.1%} {p_max:>5.1%} "
          f"{e_ret_min:>+10.2%} {e_ret_max:>+10.2%} {ev:>+7.2%} "
          f"{e_days:>6.1f} {e_speed:>8.5f}")

# ═══════════════════════════════════════════════════════════════
# ANALYSIS 2: EV by state × level (5% and 7.5%)
# ═══════════════════════════════════════════════════════════════
for lvl_label, lvl in [("5%", 0.05), ("7.5%", 0.075)]:
    print(f"\n\n{'=' * 90}")
    print(f"  ANALYSIS 2: Expected Value by state — next {lvl_label} pivot")
    print("=" * 90)

    ev_lvl = ev_df[ev_df['level'] == lvl]
    top_s = ev_lvl['state'].value_counts().head(15).index.tolist()

    print(f"\n  {'State':>20s} {'N':>7s} {'P(MIN)':>6s} {'P(MAX)':>6s} "
          f"{'E[ret|MIN]':>11s} {'E[ret|MAX]':>11s} {'EV':>8s} "
          f"{'E[days]':>7s}")

    for state in top_s:
        sdf = ev_lvl[ev_lvl['state'] == state]
        n = len(sdf)
        if n < 30:
            continue
        p_min = (sdf['next_type'] == 'MIN').mean()
        p_max = (sdf['next_type'] == 'MAX').mean()
        e_ret_min = sdf[sdf['next_type']=='MIN']['next_return'].mean() if p_min > 0 else 0
        e_ret_max = sdf[sdf['next_type']=='MAX']['next_return'].mean() if p_max > 0 else 0
        ev = p_min * e_ret_min + p_max * e_ret_max
        e_days = sdf['next_days'].mean()

        print(f"  {state:>20s} {n:>7,} {p_min:>5.1%} {p_max:>5.1%} "
              f"{e_ret_min:>+10.2%} {e_ret_max:>+10.2%} {ev:>+7.2%} "
              f"{e_days:>6.1f}")

# ═══════════════════════════════════════════════════════════════
# ANALYSIS 3: EV distribution — how many states have positive EV?
# ═══════════════════════════════════════════════════════════════
print(f"\n\n{'=' * 90}")
print(f"  ANALYSIS 3: EV distribution across all 180 states (zz 2.5%)")
print("=" * 90)

all_states = ev25['state'].unique()
ev_list = []
for state in all_states:
    sdf = ev25[ev25['state'] == state]
    n = len(sdf)
    if n < 50:
        continue
    p_min = (sdf['next_type'] == 'MIN').mean()
    p_max = (sdf['next_type'] == 'MAX').mean()
    e_ret_min = sdf[sdf['next_type']=='MIN']['next_return'].mean() if p_min > 0 else 0
    e_ret_max = sdf[sdf['next_type']=='MAX']['next_return'].mean() if p_max > 0 else 0
    ev = p_min * e_ret_min + p_max * e_ret_max
    ev_list.append((state, n, p_min, p_max, ev, e_ret_min, e_ret_max))

ev_list.sort(key=lambda x: -x[4])

print(f"\n  States with N>=50: {len(ev_list)}")
print(f"  Positive EV: {sum(1 for x in ev_list if x[4] > 0)}")
print(f"  Negative EV: {sum(1 for x in ev_list if x[4] < 0)}")
print(f"  Mean EV: {np.mean([x[4] for x in ev_list]):+.4f}")
print(f"  Median EV: {np.median([x[4] for x in ev_list]):+.4f}")

print(f"\n  Top 10 (highest EV):")
print(f"  {'State':>20s} {'N':>7s} {'P(MIN)':>6s} {'EV':>8s} {'E[ret|MIN]':>11s} {'E[ret|MAX]':>11s}")
for state, n, p_min, p_max, ev, erm, erx in ev_list[:10]:
    print(f"  {state:>20s} {n:>7,} {p_min:>5.1%} {ev:>+7.2%} {erm:>+10.2%} {erx:>+10.2%}")

print(f"\n  Bottom 10 (lowest EV):")
for state, n, p_min, p_max, ev, erm, erx in ev_list[-10:]:
    print(f"  {state:>20s} {n:>7,} {p_min:>5.1%} {ev:>+7.2%} {erm:>+10.2%} {erx:>+10.2%}")

# ═══════════════════════════════════════════════════════════════
# ANALYSIS 4: Does EV add info beyond P(bull)?
# Compare P(bull) ranking vs EV ranking for top states
# ═══════════════════════════════════════════════════════════════
print(f"\n\n{'=' * 90}")
print(f"  ANALYSIS 4: P(bull) vs EV — do they tell the same story?")
print("=" * 90)

# P(bull) from current model: P(HH+HL) / N
# We need to recompute this. Load stereotypes from current training.
# Actually, let's compute P(next=MIN) as proxy for P(bull) — MIN = bottom = bullish forward
# And compare P(MIN) vs EV

print(f"\n  {'State':>20s} {'N':>7s} {'P(MIN)':>6s} {'EV':>8s} {'P(MIN) rank':>11s} {'EV rank':>8s} {'Diverge':>8s}")

ranked_pmin = sorted(ev_list, key=lambda x: -x[2])
ranked_ev = sorted(ev_list, key=lambda x: -x[4])
pmin_rank = {x[0]: i+1 for i, x in enumerate(ranked_pmin)}
ev_rank = {x[0]: i+1 for i, x in enumerate(ranked_ev)}

# Show states where rankings diverge most
divergence = []
for state, n, p_min, p_max, ev, erm, erx in ev_list:
    pr = pmin_rank[state]
    er = ev_rank[state]
    div = abs(pr - er)
    divergence.append((state, n, p_min, ev, pr, er, div))

divergence.sort(key=lambda x: -x[6])

print(f"\n  States where P(MIN) and EV diverge most:")
print(f"  {'State':>20s} {'N':>7s} {'P(MIN)':>6s} {'EV':>8s} {'P rank':>7s} {'EV rank':>7s} {'Δrank':>6s}")
for state, n, p_min, ev, pr, er, div in divergence[:15]:
    print(f"  {state:>20s} {n:>7,} {p_min:>5.1%} {ev:>+7.2%} {pr:>7d} {er:>7d} {div:>5d}")

# ═══════════════════════════════════════════════════════════════
# ANALYSIS 5: EV with fatigue (run_length interaction)
# ═══════════════════════════════════════════════════════════════
print(f"\n\n{'=' * 90}")
print(f"  ANALYSIS 5: EV × run_length — does fatigue affect EV?")
print("=" * 90)

# Compute run_length on the snapshot data
df_sorted = df.sort_values(['ticker', 'timestamp']).reset_index(drop=True)
df_sorted['prev_state'] = df_sorted.groupby('ticker')['state'].shift(1)
df_sorted['state_change'] = df_sorted['state'] != df_sorted['prev_state']
df_sorted['run_group'] = df_sorted.groupby('ticker')['state_change'].cumsum()
df_sorted['run_length'] = df_sorted.groupby(['ticker','run_group']).cumcount() + 1

# Merge run_length onto ev_df
# ev_df has ticker + state but not timestamp. We need to re-merge.
# Actually, let's just tag each snapshot with run_length first, then recompute.
# For simplicity, let's just use the ev25 data and add run_length.

# Re-merge: we need timestamp in ev_df. Let's recompute.
print("  Recomputing with run_length...")

# Build a lookup: ticker + timestamp -> run_length
rl_lookup = df_sorted[['ticker', 'timestamp', 'state', 'run_length']].copy()
rl_lookup['ts_key'] = rl_lookup['ticker'] + '_' + rl_lookup['timestamp'].astype(str)

# We need to tag ev_df with the source timestamp. Let's redo the merge more carefully.
# Actually, ev_df was built from snapshots that had timestamps. Let's rebuild.
# For efficiency, let's just re-run the forward label computation with run_length included.

# Simpler approach: tag each result row with run_length by re-running the loop
# but this time storing the run_length too.
# That's too slow. Let's use merge_asof.

# Actually, let's just compute EV by state × run_bucket for top 10 states
print("  Computing EV × run_bucket for top 10 states...")

# Get top 10 states by N from ev25
top10 = [x[0] for x in ev_list[:10]]

# For each of these states, we need run_length. Let's get it from the snapshot data.
# We need to match snapshot bars to their forward pivots.
# Let's build a merged dataframe for just these states.

# Build a per-bar forward-label dataset
print("  Building per-bar forward labels for top states...")
state_set = set(top10)
df_top = df_sorted[df_sorted['state'].isin(state_set)].copy()

# For each ticker in df_top, find next zz25 pivot
zz25 = zz_levels[0.025].copy()
# Normalize both to tz-naive for comparison
df_top = df_top.copy()
df_top['ts_naive'] = pd.to_datetime(df_top['timestamp'], utc=True).dt.tz_localize(None)
zz25 = zz25.copy()
zz25['ts_naive'] = pd.to_datetime(zz25['timestamp'], utc=True).dt.tz_localize(None)

forward_labels = []
for ticker in df_top['ticker'].unique():
    tdf = df_top[df_top['ticker'] == ticker].sort_values('ts_naive').reset_index(drop=True)
    tzz = zz25[zz25['ticker'] == ticker].sort_values('ts_naive').reset_index(drop=True)
    if len(tzz) == 0:
        continue
    zz_ts = tzz['ts_naive'].values
    zz_type = tzz['tp_type'].values
    zz_ret = tzz['swing_return'].values
    zz_days = tzz['swing_days'].values

    import bisect
    snap_ts_arr = tdf['ts_naive'].values
    for i in range(len(tdf)):
        j = bisect.bisect_right(zz_ts, snap_ts_arr[i])
        if j >= len(zz_ts):
            continue
        forward_labels.append({
            'state': tdf.iloc[i]['state'],
            'run_length': tdf.iloc[i]['run_length'],
            'next_type': zz_type[j],
            'next_return': float(zz_ret[j]),
            'next_days': int(zz_days[j]),
        })

fl_df = pd.DataFrame(forward_labels)
print(f"  {len(fl_df):,} forward labels for top states ({time.time()-t0:.1f}s)")

fl_df['run_bucket'] = pd.cut(fl_df['run_length'],
    bins=[0,1,2,4,7,10,1000],
    labels=['1','2','3-4','5-7','8-10','11+'])

print(f"\n  {'State':>20s} {'Run':>5s} {'N':>6s} {'P(MIN)':>6s} {'E[ret|MIN]':>11s} {'E[ret|MAX]':>11s} {'EV':>8s}")
for state in top10:
    sdf = fl_df[fl_df['state'] == state]
    for bucket in ['1','2','3-4','5-7','8-10','11+']:
        bdf = sdf[sdf['run_bucket'] == bucket]
        if len(bdf) < 30:
            continue
        p_min = (bdf['next_type'] == 'MIN').mean()
        p_max = 1 - p_min
        e_ret_min = bdf[bdf['next_type']=='MIN']['next_return'].mean() if p_min > 0 else 0
        e_ret_max = bdf[bdf['next_type']=='MAX']['next_return'].mean() if p_max > 0 else 0
        ev = p_min * e_ret_min + p_max * e_ret_max
        print(f"  {state:>20s} {bucket:>5s} {len(bdf):>6,} {p_min:>5.1%} {e_ret_min:>+10.2%} {e_ret_max:>+10.2%} {ev:>+7.2%}")
    print()

# ═══════════════════════════════════════════════════════════════
# ANALYSIS 6: Risk-adjusted EV — Sharpe-like by state
# E[return] / std[return] per state
# ═══════════════════════════════════════════════════════════════
print(f"\n{'=' * 90}")
print(f"  ANALYSIS 6: Risk-adjusted EV (Sharpe-like) by state")
print("=" * 90)

print(f"\n  {'State':>20s} {'N':>7s} {'EV':>8s} {'std_ret':>8s} {'Sharpe':>7s} {'E[days]':>7s} {'Ann_Sharpe':>10s}")

state_sharpes = []
for state, n, p_min, p_max, ev, erm, erx in ev_list:
    sdf = ev25[ev25['state'] == state]
    std_ret = sdf['next_return'].std()
    e_days = sdf['next_days'].mean()
    sharpe = ev / std_ret if std_ret > 0 else 0
    # Annualized: 252 trading days / E[days per swing]
    swings_per_year = 252 / e_days if e_days > 0 else 0
    ann_sharpe = sharpe * np.sqrt(swings_per_year) if swings_per_year > 0 else 0
    state_sharpes.append((state, n, ev, std_ret, sharpe, e_days, ann_sharpe))

state_sharpes.sort(key=lambda x: -x[6])

print(f"\n  Top 15 by Annualized Sharpe:")
for state, n, ev, std, sh, days, ann in state_sharpes[:15]:
    print(f"  {state:>20s} {n:>7,} {ev:>+7.2%} {std:>7.2%} {sh:>+6.3f} {days:>6.1f} {ann:>+9.2f}")

print(f"\n  Bottom 15 by Annualized Sharpe:")
for state, n, ev, std, sh, days, ann in state_sharpes[-15:]:
    print(f"  {state:>20s} {n:>7,} {ev:>+7.2%} {std:>7.2%} {sh:>+6.3f} {days:>6.1f} {ann:>+9.2f}")

# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
print(f"\n\n{'=' * 90}")
print(f"  SUMMARY")
print(f"{'=' * 90}")
print(f"  Total observations: {len(ev25):,}")
print(f"  States with N>=50: {len(ev_list)}")
print(f"  Positive EV states: {sum(1 for x in ev_list if x[4] > 0)}")
print(f"  Negative EV states: {sum(1 for x in ev_list if x[4] < 0)}")
print(f"  Mean EV: {np.mean([x[4] for x in ev_list]):+.4f}")
print(f"  States with |divergence P(MIN) vs EV| > 5 ranks: {sum(1 for x in divergence if x[6] > 5)}")
print(f"  Elapsed: {time.time()-t0:.1f}s")
print(f"{'=' * 90}")
