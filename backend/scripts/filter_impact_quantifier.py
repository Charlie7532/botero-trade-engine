#!/usr/bin/env python3
"""
Filter Impact Quantifier — Test confirmation filters on top of P(bull)
=======================================================================
For each filter combination, measures:
  - Signal reduction (fewer = more selective)
  - % BEFORE vs AFTER trough (higher AFTER = better timing)
  - Hit rate (zigzag direction)
  - Max drawdown (median)
  - Capture ratio (higher = closer to bottom)
  - Profit to next peak

Filters tested (all on ACCUMULATE signals with P≥75%):
  A. wave_accel > 0
  B. current_accel > 0
  C. σVw transition ≥ +1 (flow improving)
  D. kf_price_innovation > 0
  E. hookup (close > prev close)
  F. wave_flip_direction == +1
  G. days_in_state ≤ 3 (fresh state)
  H. wave_accel > 0 AND σVw_transition ≥ +1
  I. wave_accel > 0 AND hookup
  J. σVw_transition ≥ +1 AND hookup
  K. σVw_transition ≥ +1 AND wave_accel > 0 AND hookup

No retraining. No code changes. Pure measurement.
"""
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
import numpy as np
from collections import defaultdict

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.quality_swing.domain.rules.rc_state_probability import (
    lookup_probability, _classify_sigma,
)


TEST_START = "2020-02-01"
ZIGZAG_LEVEL = 0.05
P_THRESHOLD = 0.75


def load_data():
    store = TimescaleDataStore()
    conn = store._conn()

    cs = pd.read_sql(f"""
        SELECT ticker, timestamp::date as date,
               sigma_current, sigma_wave, vwap_sigma_wave, tide_slope,
               current_accel, wave_accel, tide_accel,
               kf_price_innovation, kf_price_filt_vel,
               wave_flip, wave_flip_direction
        FROM engine.channel_snapshots
        WHERE timeframe = '1d' AND timestamp >= '{TEST_START}'
        ORDER BY ticker, timestamp
    """, conn)

    zz = pd.read_sql(f"""
        SELECT ticker, timestamp::date as date, tp_type, price
        FROM engine.zigzag_points
        WHERE min_swing_pct = {ZIGZAG_LEVEL}
        ORDER BY ticker, timestamp
    """, conn)

    bars = pd.read_sql("""
        SELECT ticker, time::date as date, close, low
        FROM market.ohlcv_bars
        WHERE timeframe = '1d'
        ORDER BY ticker, time
    """, conn)

    store._put(conn)
    store.close()

    cs['date'] = pd.to_datetime(cs['date'])
    zz['date'] = pd.to_datetime(zz['date'])
    bars['date'] = pd.to_datetime(bars['date'])

    return cs, zz, bars


def prepare_signals(cs, bars):
    """Add P(bull), σVw state, prev state, hookup, days_in_state."""
    df = cs.merge(bars[['ticker', 'date', 'close', 'low']], on=['ticker', 'date'], how='inner')
    df = df.sort_values(['ticker', 'date']).reset_index(drop=True)

    # P(bull)
    p_bulls = []
    for _, r in df.iterrows():
        rc = lookup_probability(
            float(r['tide_slope']), float(r['sigma_current']),
            float(r['sigma_wave']), float(r['vwap_sigma_wave']))
        p_bulls.append(rc.prob_bull if rc else 0.5)
    df['p_bull'] = p_bulls

    # σVw bin label
    df['svw_bin'] = df['vwap_sigma_wave'].apply(_classify_sigma)

    # L2 state key
    df['state'] = df.apply(
        lambda r: f"{_classify_sigma(r['sigma_current'])}|{_classify_sigma(r['sigma_wave'])}|{_classify_sigma(r['vwap_sigma_wave'])}",
        axis=1)

    # Per-ticker: prev_svw_bin, hookup, days_in_state, svw_transition
    df['prev_svw_bin'] = df.groupby('ticker')['svw_bin'].shift(1)
    df['prev_close'] = df.groupby('ticker')['close'].shift(1)
    df['hookup'] = df['close'] > df['prev_close']

    # σVw transition
    rank_map = {'<<': 0, '<': 1, '~': 2, '>': 3, '>>': 4}
    df['svw_rank'] = df['svw_bin'].map(rank_map)
    df['prev_svw_rank'] = df['prev_svw_bin'].map(rank_map)
    df['svw_transition'] = df['svw_rank'] - df['prev_svw_rank']

    # Days in same state
    df['prev_state'] = df.groupby('ticker')['state'].shift(1)
    df['state_changed'] = df['state'] != df['prev_state']

    days = []
    current_days = 1
    prev_ticker = None
    for _, r in df.iterrows():
        if r['ticker'] != prev_ticker:
            current_days = 1
            prev_ticker = r['ticker']
        elif r['state_changed']:
            current_days = 1
        else:
            current_days += 1
        days.append(current_days)
    df['days_in_state'] = days

    print(f"Prepared: {len(df):,} bars, {df['ticker'].nunique()} tickers")
    return df


def compute_timing(df, zz, bars):
    """For each ACCUMULATE signal, compute trough proximity and outcome metrics."""
    accum = df[df['p_bull'] >= P_THRESHOLD].copy()
    print(f"ACCUMULATE candidates (P≥{P_THRESHOLD:.0%}): {len(accum):,}")

    results = []
    for ticker in accum['ticker'].unique():
        tk_a = accum[accum['ticker'] == ticker]
        tk_zz_min = zz[(zz['ticker'] == ticker) & (zz['tp_type'] == 'MIN')].sort_values('date')
        tk_zz_max = zz[(zz['ticker'] == ticker) & (zz['tp_type'] == 'MAX')].sort_values('date')
        tk_bars = bars[bars['ticker'] == ticker].sort_values('date')

        if len(tk_zz_min) < 2 or len(tk_zz_max) < 2:
            continue

        trough_dates = pd.to_datetime(tk_zz_min['date']).values
        trough_prices = tk_zz_min['price'].values.astype(float)
        peak_dates = pd.to_datetime(tk_zz_max['date']).values
        peak_prices = tk_zz_max['price'].values.astype(float)
        bar_dates = pd.to_datetime(tk_bars['date']).values
        bar_low = tk_bars['low'].values.astype(float)

        for _, sig in tk_a.iterrows():
            d = np.datetime64(sig['date'])
            price = float(sig['close'])

            t_next = np.searchsorted(trough_dates, d, side='right')
            t_prev = t_next - 1
            p_next = np.searchsorted(peak_dates, d, side='right')

            if t_next >= len(trough_dates) or t_prev < 0 or p_next >= len(peak_dates):
                continue

            dist_next_t = (trough_dates[t_next] - d) / np.timedelta64(1, 'D')
            dist_prev_t = (d - trough_dates[t_prev]) / np.timedelta64(1, 'D')

            if dist_next_t < dist_prev_t:
                side = "BEFORE"
                nearest_tp = trough_prices[t_next]
            else:
                side = "AFTER"
                nearest_tp = trough_prices[t_prev]

            price_from_trough = (price / nearest_tp - 1.0) * 100
            next_peak_p = peak_prices[p_next]

            if next_peak_p > nearest_tp:
                capture = max(0, min(1, (next_peak_p - price) / (next_peak_p - nearest_tp)))
            else:
                capture = 0.0

            # Max drawdown
            if dist_next_t > 0:
                bi = np.searchsorted(bar_dates, d, side='left')
                ti = np.searchsorted(bar_dates, trough_dates[t_next], side='left')
                if bi < len(bar_low) and ti < len(bar_low):
                    dd = (bar_low[bi:min(ti + 1, len(bar_low))].min() / price - 1.0) * 100
                else:
                    dd = 0.0
            else:
                dd = 0.0

            # Zigzag label (bull = next peak higher than previous peak)
            p_prev_idx = p_next - 1
            is_bull = peak_prices[p_next] > peak_prices[p_prev_idx] if p_prev_idx >= 0 else None

            results.append({
                'ticker': sig['ticker'],
                'date': sig['date'],
                'price': price,
                'p_bull': sig['p_bull'],
                'side': side,
                'capture': capture,
                'max_dd': dd,
                'profit_to_peak': (next_peak_p / price - 1.0) * 100,
                'is_bull': is_bull,
                # Filter variables
                'wave_accel': float(sig['wave_accel']),
                'current_accel': float(sig['current_accel']),
                'tide_accel': float(sig['tide_accel']),
                'kf_innovation': float(sig['kf_price_innovation']),
                'hookup': bool(sig['hookup']),
                'wave_flip_dir': int(sig['wave_flip_direction']),
                'svw_transition': sig['svw_transition'],
                'days_in_state': sig['days_in_state'],
            })

    return pd.DataFrame(results)


def test_filters(results):
    """Test each filter combination and report impact."""
    df = results.dropna(subset=['is_bull'])

    # Define filters
    filters = {
        "BASELINE (P≥75%, no filter)": lambda d: pd.Series(True, index=d.index),
        "A: wave_accel > 0": lambda d: d['wave_accel'] > 0,
        "B: current_accel > 0": lambda d: d['current_accel'] > 0,
        "C: σVw transition ≥ +1": lambda d: d['svw_transition'] >= 1,
        "D: kf_innovation > 0": lambda d: d['kf_innovation'] > 0,
        "E: hookup": lambda d: d['hookup'],
        "F: wave_flip +1": lambda d: d['wave_flip_dir'] == 1,
        "G: days_in_state ≤ 3": lambda d: d['days_in_state'] <= 3,
        "H: wave_accel>0 + σVw≥+1": lambda d: (d['wave_accel'] > 0) & (d['svw_transition'] >= 1),
        "I: wave_accel>0 + hookup": lambda d: (d['wave_accel'] > 0) & (d['hookup']),
        "J: σVw≥+1 + hookup": lambda d: (d['svw_transition'] >= 1) & (d['hookup']),
        "K: σVw≥+1 + wave_accel>0 + hookup": lambda d: (d['svw_transition'] >= 1) & (d['wave_accel'] > 0) & (d['hookup']),
        "L: σVw≥+1 OR wave_accel>0": lambda d: (d['svw_transition'] >= 1) | (d['wave_accel'] > 0),
        "M: (σVw≥+1 OR wave_accel>0) + hookup": lambda d: ((d['svw_transition'] >= 1) | (d['wave_accel'] > 0)) & d['hookup'],
        "N: current_accel>0 + wave_accel>0": lambda d: (d['current_accel'] > 0) & (d['wave_accel'] > 0),
        "O: days≤3 + wave_accel>0": lambda d: (d['days_in_state'] <= 3) & (d['wave_accel'] > 0),
        "P: days≤3 + σVw≥+1": lambda d: (d['days_in_state'] <= 3) & (d['svw_transition'] >= 1),
    }

    baseline_n = len(df)
    baseline_after = (df['side'] == 'AFTER').mean()

    print(f"\n{'='*140}")
    print(f"  FILTER IMPACT QUANTIFIER — Testing {len(filters)} filters on {baseline_n:,} ACCUMULATE signals (P≥{P_THRESHOLD:.0%})")
    print(f"{'='*140}\n")

    print(f"  {'Filter':<42s} {'N':>6s} {'%kept':>7s} {'HR':>7s} {'%AFTER':>7s} "
          f"{'capture':>8s} {'dd_med':>8s} {'profit':>8s} {'SCORE':>8s}")
    print(f"  {'─'*42} {'─'*6} {'─'*7} {'─'*7} {'─'*7} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")

    results_table = []

    for name, filter_fn in filters.items():
        mask = filter_fn(df)
        sub = df[mask]

        if len(sub) < 30:
            continue

        n = len(sub)
        pct_kept = n / baseline_n
        hr = sub['is_bull'].mean()
        pct_after = (sub['side'] == 'AFTER').mean()
        cap = sub['capture'].median()
        dd = sub['max_dd'].median()
        profit = sub['profit_to_peak'].median()

        # Composite score: HR × %AFTER × (1 - |dd|/10) × capture
        score = hr * pct_after * max(0, 1 - abs(dd) / 10) * cap * 100

        marker = ""
        if pct_after > baseline_after + 0.05 and hr > 0.75:
            marker = " ★"
        elif pct_after > baseline_after + 0.10:
            marker = " ★★"

        print(f"  {name:<42s} {n:>6,} {pct_kept:>6.1%} {hr:>6.1%} {pct_after:>6.1%} "
              f"{cap:>8.2f} {dd:>+7.1f}% {profit:>+7.1f}% {score:>7.1f}{marker}")

        results_table.append({
            'name': name, 'n': n, 'pct_kept': pct_kept, 'hr': hr,
            'pct_after': pct_after, 'capture': cap, 'dd': dd,
            'profit': profit, 'score': score
        })

    # Best filter
    rt = pd.DataFrame(results_table)
    best = rt.loc[rt['score'].idxmax()]
    print(f"\n  BEST FILTER: {best['name']}")
    print(f"    N={best['n']:.0f} ({best['pct_kept']:.1%}) HR={best['hr']:.1%} "
          f"%AFTER={best['pct_after']:.1%} dd={best['dd']:+.1f}% profit={best['profit']:+.1f}%")

    # Show top 5 by different criteria
    print(f"\n  TOP 5 by HR:")
    for _, r in rt.nlargest(5, 'hr').iterrows():
        print(f"    {r['name']:<42s} HR={r['hr']:.1%} N={r['n']:.0f}")

    print(f"\n  TOP 5 by %AFTER (timing quality):")
    for _, r in rt.nlargest(5, 'pct_after').iterrows():
        print(f"    {r['name']:<42s} %AFTER={r['pct_after']:.1%} N={r['n']:.0f}")

    print(f"\n  TOP 5 by drawdown (least pain):")
    for _, r in rt.nlargest(5, 'dd').iterrows():
        print(f"    {r['name']:<42s} dd={r['dd']:+.1f}% N={r['n']:.0f}")

    print("\nDONE")


def main():
    cs, zz, bars = load_data()
    df = prepare_signals(cs, bars)
    results = compute_timing(df, zz, bars)
    test_filters(results)


if __name__ == "__main__":
    main()
