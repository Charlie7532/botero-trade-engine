#!/usr/bin/env python3
"""
State Fatigue Analysis — Exploratory (read-only, no code changes)
=================================================================
Validates Juan's hypothesis: P(bull|state) should decay with run_length
(consecutive bars in same state) — "state fatigue".

Uses 5-day forward return > 0 as bull/bear proxy.
Data: engine.channel_snapshots (640K rows, 547 tickers)
"""
import os, sys, time
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
from dotenv import load_dotenv
load_dotenv(root / ".env")

import psycopg2
import pandas as pd
import numpy as np

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
print(f"  {len(df):,} rows loaded ({time.time()-t0:.1f}s)")

# ── Load OHLCV close prices for forward returns ──
print("Loading ohlcv_bars (close prices)...")
ohlc = pd.read_sql("""
    SELECT ticker, time AS timestamp, close
    FROM market.ohlcv_bars
    WHERE timeframe = '1d'
    ORDER BY ticker, time
""", conn)
print(f"  {len(ohlc):,} rows loaded ({time.time()-t0:.1f}s)")
conn.close()

# ── Merge close prices onto snapshots ──
df = df.merge(ohlc[['ticker', 'timestamp', 'close']], on=['ticker', 'timestamp'], how='left')
df = df.dropna(subset=['close'])

# ── Compute 5-day forward return ──
df = df.sort_values(['ticker', 'timestamp']).reset_index(drop=True)
df['fwd_5d_close'] = df.groupby('ticker')['close'].shift(-5)
df['fwd_5d_ret'] = (df['fwd_5d_close'] - df['close']) / df['close']
df['bull'] = df['fwd_5d_ret'] > 0
df = df.dropna(subset=['fwd_5d_ret'])

print(f"  After merge + fwd return: {len(df):,} rows ({time.time()-t0:.1f}s)")

# ── Classify slopes into T×C×σVw states (same thresholds as model) ──
SLOPE_TH = {
    "T": {"+": (0.0456, 0.0983), "-": (0.0263, 0.0765)},
    "C": {"+": (0.0845, 0.1749), "-": (0.0613, 0.1583)},
}
SIGMA_BINS = [(-999, -1.0, "<<"), (-1.0, -0.3, "<"),
              (-0.3, 0.3, "~"), (0.3, 1.0, ">"), (1.0, 999, ">>")]

def classify_slope(value, channel):
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

def classify_sigma(value):
    for lo, hi, label in SIGMA_BINS:
        if lo <= value < hi: return label
    return ">>"

df['T_level'] = df['tide_slope'].apply(lambda x: classify_slope(x, 'T'))
df['C_level'] = df['current_slope'].apply(lambda x: classify_slope(x, 'C'))
df['svw_bin'] = df['vwap_sigma_wave'].apply(classify_sigma)
df['state_key'] = df['T_level'] + '|' + df['C_level'] + '|' + df['svw_bin']

print(f"  States classified: {df['state_key'].nunique()} unique ({time.time()-t0:.1f}s)")

# ── Compute run_length per ticker (consecutive bars in same state) ──
df['prev_state'] = df.groupby('ticker')['state_key'].shift(1)
df['state_change'] = df['state_key'] != df['prev_state']
df['run_group'] = df.groupby('ticker')['state_change'].cumsum()
df['run_length'] = df.groupby(['ticker', 'run_group']).cumcount() + 1

# Run length buckets
df['run_bucket'] = pd.cut(df['run_length'],
    bins=[0, 1, 2, 4, 7, 10, 1000],
    labels=['1', '2', '3-4', '5-7', '8-10', '11+'])

print(f"  Runs computed ({time.time()-t0:.1f}s)")

# ═══════════════════════════════════════════════════════════════
# ANALYSIS 1: P(bull) by state × run_length bucket
# Top 15 most frequent states
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("  ANALYSIS 1: P(bull) by state × run_length bucket")
print("  (5-day forward return > 0 as bull proxy)")
print("=" * 80)

top_states = df['state_key'].value_counts().head(15).index.tolist()

for state in top_states:
    sdf = df[df['state_key'] == state]
    n_total = len(sdf)
    p_overall = sdf['bull'].mean() * 100

    print(f"\n  ── {state} (N={n_total:,}, P_bull={p_overall:.1f}%) ──")
    print(f"    {'Run':>8s} {'N':>8s} {'P(bull)':>8s} {'Δ vs overall':>13s}")

    for bucket in ['1', '2', '3-4', '5-7', '8-10', '11+']:
        bdf = sdf[sdf['run_bucket'] == bucket]
        if len(bdf) < 30:
            continue
        p_bull = bdf['bull'].mean() * 100
        delta = p_bull - p_overall
        print(f"    {bucket:>8s} {len(bdf):>8,} {p_bull:>7.1f}% {delta:>+12.1f}pp")

# ═══════════════════════════════════════════════════════════════
# ANALYSIS 2: Exit probability by run_length
# "Survival analysis" — P(state ends | duration=N)
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "=" * 80)
print("  ANALYSIS 2: Exit probability by run_length")
print("  P(state ends at this bar | been in state for N bars)")
print("=" * 80)

df['is_last_of_run'] = df.groupby(['ticker', 'run_group'])['timestamp'].transform('max') == df['timestamp']

print(f"\n    {'Run_len':>8s} {'N_total':>10s} {'N_exits':>10s} {'P(exit)':>8s} {'Cum_surv':>9s}")
cum_surv = 1.0
for rl in range(1, 21):
    rl_df = df[df['run_length'] == rl]
    if len(rl_df) < 30:
        continue
    n_exit = rl_df['is_last_of_run'].sum()
    p_exit = n_exit / len(rl_df) * 100
    cum_surv *= (1 - p_exit / 100)
    print(f"    {rl:>8d} {len(rl_df):>10,} {n_exit:>10,} {p_exit:>7.1f}% {cum_surv*100:>8.1f}%")

rl_21plus = df[df['run_length'] >= 21]
if len(rl_21plus) >= 30:
    n_exit = rl_21plus['is_last_of_run'].sum()
    p_exit = n_exit / len(rl_21plus) * 100
    print(f"    {'21+':>8s} {len(rl_21plus):>10,} {n_exit:>10,} {p_exit:>7.1f}%")

# ═══════════════════════════════════════════════════════════════
# ANALYSIS 3: Aggregate fatigue curve (all states combined)
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "=" * 80)
print("  ANALYSIS 3: Aggregate fatigue curve — all states combined")
print("=" * 80)

overall_p = df['bull'].mean() * 100
print(f"\n    Overall P(bull) = {overall_p:.1f}%")
print(f"\n    {'Run_bucket':>10s} {'N':>10s} {'P(bull)':>8s} {'Δ':>8s} {'Lift':>6s}")

for bucket in ['1', '2', '3-4', '5-7', '8-10', '11+']:
    bdf = df[df['run_bucket'] == bucket]
    if len(bdf) < 100:
        continue
    p_bull = bdf['bull'].mean() * 100
    delta = p_bull - overall_p
    lift = p_bull / overall_p
    print(f"    {bucket:>10s} {len(bdf):>10,} {p_bull:>7.1f}% {delta:>+7.1f}pp {lift:>5.3f}x")

# ═══════════════════════════════════════════════════════════════
# ANALYSIS 4: State-specific fatigue (run=1 vs run=8+)
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "=" * 80)
print("  ANALYSIS 4: State-specific fatigue — P(bull) run=1 vs run=8+")
print("=" * 80)

print(f"\n    {'State':>20s} {'N':>8s} {'P(1)':>6s} {'P(8+)':>6s} {'Δ':>7s} {'Fatigue':>8s}")

fatigue_count = 0
total_analyzed = 0
fatigue_details = []

for state in df['state_key'].value_counts().head(30).index:
    sdf = df[df['state_key'] == state]
    n = len(sdf)
    s1 = sdf[sdf['run_length'] == 1]
    s8 = sdf[sdf['run_length'] >= 8]
    if len(s1) < 30 or len(s8) < 30:
        continue
    p1 = s1['bull'].mean() * 100
    p8 = s8['bull'].mean() * 100
    delta = p8 - p1
    fatigue = "YES" if abs(delta) > 5 else "no"
    print(f"    {state:>20s} {n:>8,} {p1:>5.1f}% {p8:>5.1f}% {delta:>+6.1f}pp {fatigue:>8s}")
    total_analyzed += 1
    if abs(delta) > 5:
        fatigue_count += 1
        fatigue_details.append((state, p1, p8, delta))

# ═══════════════════════════════════════════════════════════════
# ANALYSIS 5: Direction of fatigue — does it favor mean reversion?
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "=" * 80)
print("  ANALYSIS 5: Fatigue direction — bullish vs bearish states")
print("=" * 80)

bull_states = [s for s in df['state_key'].value_counts().head(30).index
               if df[df['state_key'] == s]['bull'].mean() > 0.55]
bear_states = [s for s in df['state_key'].value_counts().head(30).index
               if df[df['state_key'] == s]['bull'].mean() < 0.45]

print(f"\n  Bullish states (P_bull > 55%): {len(bull_states)}")
print(f"  {'State':>20s} {'P(1)':>6s} {'P(8+)':>6s} {'Δ':>7s} {'Reversion?':>10s}")
for state in bull_states[:10]:
    sdf = df[df['state_key'] == state]
    s1 = sdf[sdf['run_length'] == 1]
    s8 = sdf[sdf['run_length'] >= 8]
    if len(s1) < 30 or len(s8) < 30:
        continue
    p1 = s1['bull'].mean() * 100
    p8 = s8['bull'].mean() * 100
    delta = p8 - p1
    reversion = "YES ↓" if delta < -3 else "no"
    print(f"  {state:>20s} {p1:>5.1f}% {p8:>5.1f}% {delta:>+6.1f}pp {reversion:>10s}")

print(f"\n  Bearish states (P_bull < 45%): {len(bear_states)}")
print(f"  {'State':>20s} {'P(1)':>6s} {'P(8+)':>6s} {'Δ':>7s} {'Reversion?':>10s}")
for state in bear_states[:10]:
    sdf = df[df['state_key'] == state]
    s1 = sdf[sdf['run_length'] == 1]
    s8 = sdf[sdf['run_length'] >= 8]
    if len(s1) < 30 or len(s8) < 30:
        continue
    p1 = s1['bull'].mean() * 100
    p8 = s8['bull'].mean() * 100
    delta = p8 - p1
    reversion = "YES ↑" if delta > 3 else "no"
    print(f"  {state:>20s} {p1:>5.1f}% {p8:>5.1f}% {delta:>+6.1f}pp {reversion:>10s}")

# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "=" * 80)
print("  SUMMARY")
print("=" * 80)
print(f"  Total observations: {len(df):,}")
print(f"  Unique states: {df['state_key'].nunique()}")
print(f"  States with fatigue (|Δ|>5pp run=1→run=8+): {fatigue_count}/{total_analyzed}")
print(f"  Elapsed: {time.time()-t0:.1f}s")

if fatigue_details:
    print(f"\n  Top fatigue states (biggest |Δ|):")
    for state, p1, p8, delta in sorted(fatigue_details, key=lambda x: -abs(x[3]))[:10]:
        direction = "decays" if delta < 0 else "increases"
        print(f"    {state}: P(1)={p1:.1f}% → P(8+)={p8:.1f}% ({direction} {abs(delta):.1f}pp)")

print("\n" + "=" * 80)
