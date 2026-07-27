#!/usr/bin/env python3
"""
SwingGate Comparison — Legacy (v1) vs Probabilistic (v2)
=========================================================
For each bar in the test period (2020-2026), evaluates:
  - v1 (legacy): heuristic σ/fear thresholds
  - v2 (probability): P(bull|sigma_state) from lookup table

Measures:
  - Signal count (ACCUMULATE / TRIM / HOLD per version)
  - Hit rate: % of ACCUMULATE signals where next zigzag was HH/HL
  - Forward return: avg 20-day return after ACCUMULATE
  - Agreement rate: how often v1 and v2 agree

Clean Architecture: Script (delivery mechanism). Reads from Vault.
"""
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
import numpy as np
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from collections import Counter

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.quality_swing.domain.rules.rc_tide_lookup import lookup_tide_signal
from backend.modules.quality_swing.domain.rules.rc_tide_ev_lookup import lookup_real_ev
from backend.modules.quality_swing.domain.rules.swing_entry_rules import (
    is_accumulate_signal,
    is_trim_signal,
    ACCUMULATE_HIGH,
    ACCUMULATE_MOD,
)


# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

TEST_START = "2020-02-01"   # Post-embargo
FWD_DAYS = 20               # Forward return window
ZIGZAG_LEVEL = 0.05


# ═══════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════

def load_test_data():
    """Load channel snapshots, zigzag labels, and OHLCV for test period."""
    store = TimescaleDataStore()
    conn = store._conn()

    cs = pd.read_sql(f"""
        SELECT ticker, timestamp::date as date,
               sigma_current, sigma_wave, sigma_tide,
               vwap_sigma_current, vwap_sigma_wave, vwap_sigma_tide,
               tide_slope, current_slope, wave_slope
        FROM engine.channel_snapshots
        WHERE timeframe = '1d'
          AND timestamp >= '{TEST_START}'
        ORDER BY ticker, timestamp
    """, conn)

    zz = pd.read_sql(f"""
        SELECT ticker, timestamp::date as date, tp_type, price
        FROM engine.zigzag_points
        WHERE min_swing_pct = {ZIGZAG_LEVEL}
        ORDER BY ticker, timestamp
    """, conn)

    bars = pd.read_sql(f"""
        SELECT ticker, time::date as date, close
        FROM market.ohlcv_bars
        WHERE timeframe = '1d'
        ORDER BY ticker, time
    """, conn)

    store._put(conn)
    store.close()

    # Normalize dates
    cs['date'] = pd.to_datetime(cs['date'])
    zz['date'] = pd.to_datetime(zz['date'])
    bars['date'] = pd.to_datetime(bars['date'])

    print(f"Loaded: {len(cs):,} snapshots, {len(zz):,} zigzag, {len(bars):,} bars")
    return cs, zz, bars


# ═══════════════════════════════════════════════════════════════
# LABELING
# ═══════════════════════════════════════════════════════════════

def add_labels(cs, zz, bars):
    """Add zigzag stereotype and forward return to each snapshot bar."""
    df = cs.merge(bars[['ticker', 'date', 'close']], on=['ticker', 'date'], how='inner')
    df = df.sort_values(['ticker', 'date']).reset_index(drop=True)

    # Forward return (20 days)
    fwd_returns = []
    stereotypes = []

    for ticker in df['ticker'].unique():
        mask = df['ticker'] == ticker
        tk_df = df[mask].copy()
        tk_dates = tk_df['date'].values
        tk_close = tk_df['close'].values

        # Forward returns
        for i, (d, cl) in enumerate(zip(tk_dates, tk_close)):
            if i + FWD_DAYS < len(tk_close):
                fwd = (tk_close[i + FWD_DAYS] / cl - 1.0) * 100
                fwd_returns.append(fwd)
            else:
                fwd_returns.append(None)

        # Zigzag stereotypes
        tk_zz = zz[zz['ticker'] == ticker].sort_values('date')
        peaks = tk_zz[tk_zz['tp_type'] == 'MAX']
        troughs = tk_zz[tk_zz['tp_type'] == 'MIN']

        if len(peaks) < 2 or len(troughs) < 2:
            stereotypes.extend([None] * mask.sum())
            continue

        peak_dates = peaks['date'].values
        peak_prices = peaks['price'].values.astype(float)
        trough_dates = troughs['date'].values
        trough_prices = troughs['price'].values.astype(float)

        for d in tk_dates:
            p_next = np.searchsorted(peak_dates, d, side='right')
            t_next = np.searchsorted(trough_dates, d, side='right')

            if p_next >= len(peak_prices) or t_next >= len(trough_prices):
                stereotypes.append(None)
                continue
            if p_next < 1 or t_next < 1:
                stereotypes.append(None)
                continue

            hh = peak_prices[p_next] > peak_prices[p_next - 1]
            hl = trough_prices[t_next] > trough_prices[t_next - 1]

            if hh and hl:
                stereotypes.append("HH")
            elif not hh and hl:
                stereotypes.append("HL")
            elif hh and not hl:
                stereotypes.append("LH")
            else:
                stereotypes.append("LL")

    df['fwd_return'] = fwd_returns
    df['stereotype'] = stereotypes
    df['is_bull'] = df['stereotype'].isin(['HH', 'HL'])

    n = df['stereotype'].notna().sum()
    print(f"Labeled: {n:,} / {len(df):,} ({n/len(df):.1%})")
    return df


# ═══════════════════════════════════════════════════════════════
# SIMULATED FEAR BIAS (for legacy path)
# ═══════════════════════════════════════════════════════════════

class MockFear:
    """Minimal TickerSentimentBias for legacy evaluation."""
    def __init__(self, row):
        self.tide_slope = float(row['tide_slope'])
        self.wave_slope = float(row.get('wave_slope', 0.0))
        self.fear_level = self._classify_fear(row)
        self.fear_label = ["GREED", "CONFIDENCE", "NEUTRAL", "ANXIETY", "FEAR", "PANIC"][self.fear_level]
        self.wave_flip = False
        self.wave_flip_direction = 0

    def _classify_fear(self, row):
        sc = float(row['sigma_current'])
        if sc >= 1.5:
            return 0  # GREED
        elif sc >= 0.5:
            return 1  # CONFIDENCE
        elif sc >= -0.5:
            return 2  # NEUTRAL
        elif sc >= -1.0:
            return 3  # ANXIETY
        elif sc >= -1.5:
            return 4  # FEAR
        else:
            return 5  # PANIC


# ═══════════════════════════════════════════════════════════════
# EVALUATE BOTH PATHS
# ═══════════════════════════════════════════════════════════════

def evaluate_both(df):
    """For each bar, evaluate v1 (legacy) and v2 (probability) paths."""
    results = []

    for _, row in df.iterrows():
        t_slope = str(row['tide_slope'])
        c_slope = str(row['current_slope'])
        svw = float(row['vwap_sigma_wave'])

        tide_sig = lookup_tide_signal(t_slope=t_slope, c_slope=c_slope, svw=svw)
        real_ev_sig = lookup_real_ev(t_slope=t_slope, c_slope=c_slope, svw=svw)

        # Mock fear for legacy
        fear = MockFear(row)
        sigma_pos = float(row['sigma_current'])
        below_vwap = svw < 0  # Approximation
        hookup = True  # Assume true (we don't have bar-by-bar hookup here)

        # v1: Legacy (Tide static cataloger rules only)
        v1_accum, v1_conv_a, v1_reason_a = is_accumulate_signal(
            sigma_pos=sigma_pos, fear=fear, below_vwap=below_vwap,
            hookup=hookup, vol_regime_label="NORMAL", tide_signal=tide_sig, real_ev_signal=None,
        )
        v1_trim, v1_conv_t, v1_reason_t = is_trim_signal(
            sigma_pos=sigma_pos, fear=fear, tide_signal=tide_sig, real_ev_signal=None,
        )

        if v1_accum:
            v1_action = "ACCUMULATE"
        elif v1_trim:
            v1_action = "TRIM"
        else:
            v1_action = "HOLD"

        # v2: Real EV Stochastic (Tide + Real EV Dual Confluence)
        v2_accum, v2_conv_a, v2_reason_a = is_accumulate_signal(
            sigma_pos=sigma_pos, fear=fear, below_vwap=below_vwap,
            hookup=hookup, vol_regime_label="NORMAL", tide_signal=tide_sig, real_ev_signal=real_ev_sig,
        )
        v2_trim, v2_conv_t, v2_reason_t = is_trim_signal(
            sigma_pos=sigma_pos, fear=fear, tide_signal=tide_sig, real_ev_signal=real_ev_sig,
        )

        if v2_accum:
            v2_action = "ACCUMULATE"
        elif v2_trim:
            v2_action = "TRIM"
        else:
            v2_action = "HOLD"

        results.append({
            'ticker': row['ticker'],
            'date': row['date'],
            'sigma_c': sigma_pos,
            'sigma_w': float(row['sigma_wave']),
            'svw': float(row['vwap_sigma_wave']),
            'tide': float(row['tide_slope']),
            'v1_action': v1_action,
            'v1_conviction': v1_conv_a if v1_accum else (v1_conv_t if v1_trim else 0.0),
            'v2_action': v2_action,
            'v2_conviction': v2_conv_a if v2_accum else (v2_conv_t if v2_trim else 0.0),
            'p_bull': real_ev_sig.p_bull if real_ev_sig else (tide_sig.p_bull if tide_sig else None),
            'rc_level': real_ev_sig.fallback_level if real_ev_sig else "L0",
            'rc_n': tide_sig.n_samples if tide_sig else 0,
            'stereotype': row['stereotype'],
            'is_bull': row['is_bull'],
            'fwd_return': row['fwd_return'],
            'agree': v1_action == v2_action,
        })

    return pd.DataFrame(results)


# ═══════════════════════════════════════════════════════════════
# ANALYSIS
# ═══════════════════════════════════════════════════════════════

def analyze(results):
    """Print comparative analysis."""
    df = results.dropna(subset=['stereotype', 'fwd_return'])

    print(f"\n{'='*100}")
    print(f"  COMPARISON: Legacy (v1) vs Probabilistic (v2)")
    print(f"  Period: {df['date'].min().date()} → {df['date'].max().date()}")
    print(f"  Bars: {len(df):,} | Tickers: {df['ticker'].nunique()}")
    print(f"{'='*100}")

    # Action distribution
    print(f"\n  ACTION DISTRIBUTION:")
    for version in ['v1', 'v2']:
        col = f'{version}_action'
        counts = df[col].value_counts()
        total = len(df)
        print(f"    {version.upper()}: ", end="")
        for action in ['ACCUMULATE', 'TRIM', 'HOLD']:
            n = counts.get(action, 0)
            print(f"{action}={n:,} ({n/total:.1%})  ", end="")
        print()

    # Agreement
    agree_rate = df['agree'].mean()
    print(f"\n  AGREEMENT: {agree_rate:.1%} ({df['agree'].sum():,} / {len(df):,})")

    # Disagreement breakdown
    disagree = df[~df['agree']]
    if len(disagree) > 0:
        print(f"\n  DISAGREEMENTS ({len(disagree):,} bars):")
        for (v1a, v2a), grp in disagree.groupby(['v1_action', 'v2_action']):
            wr = grp['is_bull'].mean()
            fwd = grp['fwd_return'].mean()
            print(f"    v1={v1a:12s} → v2={v2a:12s}: {len(grp):>5,} bars | "
                  f"actual_bull={wr:.1%} | fwd_20d={fwd:+.2f}%")

    # Hit rate by version
    print(f"\n{'='*100}")
    print(f"  HIT RATE & FORWARD RETURNS BY ACTION")
    print(f"{'='*100}")

    for version in ['v1', 'v2']:
        col = f'{version}_action'
        print(f"\n  {version.upper()}:")
        for action in ['ACCUMULATE', 'TRIM', 'HOLD']:
            subset = df[df[col] == action]
            if len(subset) == 0:
                continue
            wr = subset['is_bull'].mean()
            fwd_mean = subset['fwd_return'].mean()
            fwd_med = subset['fwd_return'].median()
            n = len(subset)

            # For ACCUMULATE: hit = is_bull. For TRIM: hit = NOT is_bull.
            if action == 'ACCUMULATE':
                hit_rate = wr
                label = "bull"
            elif action == 'TRIM':
                hit_rate = 1.0 - wr
                label = "bear"
            else:
                hit_rate = None
                label = "n/a"

            hit_str = f"HR={hit_rate:.1%}" if hit_rate is not None else "HR=n/a"
            print(f"    {action:12s}: N={n:>6,} | {hit_str} | "
                  f"fwd_20d mean={fwd_mean:+.2f}% med={fwd_med:+.2f}%")

    # v2 ACCUMULATE: breakdown by P(bull) quintile
    v2_accum = df[(df['v2_action'] == 'ACCUMULATE') & df['p_bull'].notna()]
    if len(v2_accum) > 0:
        print(f"\n{'='*100}")
        print(f"  v2 ACCUMULATE — Breakdown by P(bull)")
        print(f"{'='*100}\n")
        print(f"  {'P(bull) range':<20s} {'N':>6s} {'HR':>8s} {'fwd_20d':>10s} {'med_20d':>10s}")

        bins = [(0.65, 0.70), (0.70, 0.75), (0.75, 0.80), (0.80, 0.85),
                (0.85, 0.90), (0.90, 0.95), (0.95, 1.01)]
        for lo, hi in bins:
            subset = v2_accum[(v2_accum['p_bull'] >= lo) & (v2_accum['p_bull'] < hi)]
            if len(subset) < 10:
                continue
            hr = subset['is_bull'].mean()
            fwd_m = subset['fwd_return'].mean()
            fwd_md = subset['fwd_return'].median()
            print(f"  {lo:.0%}-{hi:.0%}              {len(subset):>6,} {hr:>7.1%} "
                  f"{fwd_m:>+9.2f}% {fwd_md:>+9.2f}%")

    # v2 TRIM: breakdown by P(bull)
    v2_trim = df[(df['v2_action'] == 'TRIM') & df['p_bull'].notna()]
    if len(v2_trim) > 0:
        print(f"\n  v2 TRIM — Breakdown by P(bull)")
        print(f"  {'P(bull) range':<20s} {'N':>6s} {'HR(bear)':>8s} {'fwd_20d':>10s}")
        bins_t = [(0.0, 0.15), (0.15, 0.20), (0.20, 0.25), (0.25, 0.30), (0.30, 0.35)]
        for lo, hi in bins_t:
            subset = v2_trim[(v2_trim['p_bull'] >= lo) & (v2_trim['p_bull'] < hi)]
            if len(subset) < 5:
                continue
            hr_bear = 1.0 - subset['is_bull'].mean()
            fwd_m = subset['fwd_return'].mean()
            print(f"  {lo:.0%}-{hi:.0%}              {len(subset):>6,} {hr_bear:>7.1%} "
                  f"{fwd_m:>+9.2f}%")

    # Per-ticker comparison
    print(f"\n{'='*100}")
    print(f"  PER-TICKER: v1 vs v2 ACCUMULATE hit rate")
    print(f"{'='*100}\n")
    print(f"  {'Ticker':<8s} {'v1_N':>6s} {'v1_HR':>8s} {'v1_fwd':>8s}  "
          f"{'v2_N':>6s} {'v2_HR':>8s} {'v2_fwd':>8s}  {'Δ_HR':>8s}")

    for ticker in sorted(df['ticker'].unique()):
        tk = df[df['ticker'] == ticker]

        v1a = tk[tk['v1_action'] == 'ACCUMULATE']
        v2a = tk[tk['v2_action'] == 'ACCUMULATE']

        v1_hr = v1a['is_bull'].mean() if len(v1a) > 0 else 0.0
        v1_fwd = v1a['fwd_return'].mean() if len(v1a) > 0 else 0.0
        v2_hr = v2a['is_bull'].mean() if len(v2a) > 0 else 0.0
        v2_fwd = v2a['fwd_return'].mean() if len(v2a) > 0 else 0.0
        delta = v2_hr - v1_hr if len(v1a) > 0 and len(v2a) > 0 else 0.0

        marker = "✓" if delta >= 0 else "✗"
        print(f"  {ticker:<8s} {len(v1a):>6,} {v1_hr:>7.1%} {v1_fwd:>+7.2f}%  "
              f"{len(v2a):>6,} {v2_hr:>7.1%} {v2_fwd:>+7.2f}%  {delta:>+7.1%} {marker}")

    print("\nDONE")


def main():
    cs, zz, bars = load_test_data()
    df = add_labels(cs, zz, bars)
    results = evaluate_both(df)
    analyze(results)


if __name__ == "__main__":
    main()
