#!/usr/bin/env python3
"""
Zigzag Confluence & Break of Structure Analysis
=================================================
Identifica puntos donde zigzags de múltiples escalas CONFLUYEN:
  - L1: Solo 2.5% (ruido, entrenamiento)
  - L2: 2.5% + 5% confluyen (swing significativo)
  - L3: 2.5% + 5% + 7.5% confluyen (BREAK OF STRUCTURE)

Para cada nivel de confluencia, mide:
  1. ¿Cuántas señales ACCUMULATE ocurren cerca?
  2. ¿Mejora el timing (% AFTER trough)?
  3. ¿Mejoran los forward returns?
  4. ¿Funcionan hookup/accel/Kalman de forma diferente aquí?

Preserva todo lo ganado — no modifica el modelo, solo OBSERVA.
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
CONFLUENCE_WINDOW = 5  # Days window for confluence (2 troughs within ±5 days = same event)


def load_all():
    store = TimescaleDataStore(); conn = store._conn()

    cs = pd.read_sql(f"""
        SELECT ticker, timestamp::date as date,
               sigma_current, sigma_wave, vwap_sigma_wave, tide_slope,
               current_accel, wave_accel, kf_price_innovation
        FROM engine.channel_snapshots
        WHERE timeframe = '1d' AND timestamp >= '{TEST_START}'
        ORDER BY ticker, timestamp
    """, conn)

    zz25 = pd.read_sql("""
        SELECT ticker, timestamp::date as date, tp_type, price
        FROM engine.zigzag_points WHERE min_swing_pct = 0.025
        ORDER BY ticker, timestamp
    """, conn)
    zz50 = pd.read_sql("""
        SELECT ticker, timestamp::date as date, tp_type, price
        FROM engine.zigzag_points WHERE min_swing_pct = 0.05
        ORDER BY ticker, timestamp
    """, conn)
    zz75 = pd.read_sql("""
        SELECT ticker, timestamp::date as date, tp_type, price
        FROM engine.zigzag_points WHERE min_swing_pct = 0.075
        ORDER BY ticker, timestamp
    """, conn)

    bars = pd.read_sql("""
        SELECT ticker, time::date as date, close, low
        FROM market.ohlcv_bars WHERE timeframe = '1d'
        ORDER BY ticker, time
    """, conn)

    store._put(conn); store.close()

    for d in [cs, zz25, zz50, zz75, bars]:
        d['date'] = pd.to_datetime(d['date'])

    return cs, zz25, zz50, zz75, bars


def find_confluences(zz25, zz50, zz75, tp_type='MIN'):
    """Find where zigzag troughs/peaks from different levels coincide."""
    confluences = {}  # ticker -> list of {date, level, prices}

    for ticker in zz25['ticker'].unique():
        tk25 = zz25[(zz25['ticker'] == ticker) & (zz25['tp_type'] == tp_type)].sort_values('date')
        tk50 = zz50[(zz50['ticker'] == ticker) & (zz50['tp_type'] == tp_type)].sort_values('date')
        tk75 = zz75[(zz75['ticker'] == ticker) & (zz75['tp_type'] == tp_type)].sort_values('date')

        dates_25 = pd.to_datetime(tk25['date']).values
        dates_50 = pd.to_datetime(tk50['date']).values
        dates_75 = pd.to_datetime(tk75['date']).values
        prices_25 = tk25['price'].values.astype(float)
        prices_50 = tk50['price'].values.astype(float)
        prices_75 = tk75['price'].values.astype(float)

        tk_conf = []

        for i, d25 in enumerate(dates_25):
            # Check if this 2.5% point has a 5% neighbor within ±WINDOW days
            has_50 = False
            if len(dates_50) > 0:
                diffs_50 = np.abs((dates_50 - d25) / np.timedelta64(1, 'D'))
                min_50 = diffs_50.min()
                has_50 = min_50 <= CONFLUENCE_WINDOW

            has_75 = False
            if len(dates_75) > 0:
                diffs_75 = np.abs((dates_75 - d25) / np.timedelta64(1, 'D'))
                min_75 = diffs_75.min()
                has_75 = min_75 <= CONFLUENCE_WINDOW

            if has_50 and has_75:
                level = "L3_BOS"     # Break of Structure: all 3 agree
            elif has_50:
                level = "L2_CONF"    # Confluence: 2.5% + 5%
            else:
                level = "L1_NOISE"   # Only 2.5% (noise)

            tk_conf.append({
                'ticker': ticker,
                'date': d25,
                'price': prices_25[i],
                'level': level,
                'has_50': has_50,
                'has_75': has_75,
            })

        confluences[ticker] = tk_conf

    all_conf = pd.DataFrame([c for clist in confluences.values() for c in clist])
    return all_conf


def analyze_signals_vs_confluences(cs, bars, conf_troughs, conf_peaks):
    """For each ACCUMULATE signal, classify by proximity to confluence levels."""
    df = cs.merge(bars[['ticker', 'date', 'close', 'low']], on=['ticker', 'date'], how='inner')
    df = df.sort_values(['ticker', 'date']).reset_index(drop=True)

    # Add P(bull) and hookup
    p_bulls = []
    for _, r in df.iterrows():
        rc = lookup_probability(
            float(r['tide_slope']), float(r['sigma_current']),
            float(r['sigma_wave']), float(r['vwap_sigma_wave']))
        p_bulls.append(rc.prob_bull if rc else 0.5)
    df['p_bull'] = p_bulls
    df['prev_close'] = df.groupby('ticker')['close'].shift(1)
    df['hookup'] = df['close'] > df['prev_close']

    accum = df[df['p_bull'] >= 0.75].copy()
    print(f"ACCUMULATE signals (P≥75%): {len(accum):,}")

    # For each ACCUMULATE, find nearest trough confluence level
    results = []
    for ticker in accum['ticker'].unique():
        tk_a = accum[accum['ticker'] == ticker]
        tk_ct = conf_troughs[conf_troughs['ticker'] == ticker].sort_values('date')
        tk_cp = conf_peaks[conf_peaks['ticker'] == ticker].sort_values('date')

        if len(tk_ct) < 2:
            continue

        ct_dates = pd.to_datetime(tk_ct['date']).values
        ct_levels = tk_ct['level'].values
        ct_prices = tk_ct['price'].values.astype(float)

        cp_dates = pd.to_datetime(tk_cp['date']).values
        cp_levels = tk_cp['level'].values if len(tk_cp) > 0 else np.array([])

        bar_dates = pd.to_datetime(bars[bars['ticker'] == ticker].sort_values('date')['date']).values
        bar_low = bars[bars['ticker'] == ticker].sort_values('date')['low'].values.astype(float)

        for _, sig in tk_a.iterrows():
            d = np.datetime64(sig['date'])
            price = float(sig['close'])

            # Find nearest TROUGH
            t_next = np.searchsorted(ct_dates, d, side='right')
            t_prev = t_next - 1

            if t_next >= len(ct_dates) or t_prev < 0:
                continue

            dist_next = (ct_dates[t_next] - d) / np.timedelta64(1, 'D')
            dist_prev = (d - ct_dates[t_prev]) / np.timedelta64(1, 'D')

            if dist_next < dist_prev:
                side = "BEFORE"
                nearest_trough_level = ct_levels[t_next]
                nearest_trough_price = ct_prices[t_next]
                dist_to_trough = dist_next
            else:
                side = "AFTER"
                nearest_trough_level = ct_levels[t_prev]
                nearest_trough_price = ct_prices[t_prev]
                dist_to_trough = dist_prev

            # Price from trough
            price_from_trough = (price / nearest_trough_price - 1.0) * 100

            # Forward: find next peak (any level)
            p_next = np.searchsorted(cp_dates, d, side='right')
            if p_next >= len(cp_dates):
                continue

            next_peak_level = cp_levels[p_next]

            # Capture ratio
            next_peak_price_idx = np.searchsorted(
                pd.to_datetime(conf_peaks[conf_peaks['ticker'] == ticker].sort_values('date')['date']).values,
                d, side='right')
            if next_peak_price_idx >= len(conf_peaks[conf_peaks['ticker'] == ticker]):
                continue
            next_peak_price = float(conf_peaks[conf_peaks['ticker'] == ticker].sort_values('date').iloc[next_peak_price_idx]['price'])

            if next_peak_price > nearest_trough_price:
                capture = max(0, min(1, (next_peak_price - price) / (next_peak_price - nearest_trough_price)))
            else:
                capture = 0.0

            profit = (next_peak_price / price - 1.0) * 100

            # Max drawdown (to nearest future trough at 2.5% level)
            if side == "BEFORE":
                bi = np.searchsorted(bar_dates, d, side='left')
                ti = np.searchsorted(bar_dates, ct_dates[t_next], side='left')
                if bi < len(bar_low) and ti < len(bar_low) and bi < ti:
                    dd = (bar_low[bi:min(ti+1, len(bar_low))].min() / price - 1.0) * 100
                else:
                    dd = 0.0
            else:
                dd = 0.0

            accel_confirmed = float(sig['wave_accel']) > 0 and float(sig['current_accel']) > 0

            results.append({
                'ticker': ticker,
                'date': sig['date'],
                'price': price,
                'p_bull': sig['p_bull'],
                'side': side,
                'trough_level': nearest_trough_level,
                'dist_to_trough': dist_to_trough,
                'price_from_trough': price_from_trough,
                'capture': capture,
                'max_dd': dd,
                'profit_to_peak': profit,
                'peak_level': next_peak_level,
                'hookup': bool(sig['hookup']),
                'wave_accel': float(sig['wave_accel']),
                'current_accel': float(sig['current_accel']),
                'accel_confirmed': accel_confirmed,
                'kf_innovation': float(sig['kf_price_innovation']),
            })

    return pd.DataFrame(results)


def report(results):
    df = results.copy()
    n_total = len(df)

    print(f"\n{'='*130}")
    print(f"  ZIGZAG CONFLUENCE & BREAK OF STRUCTURE — SIGNAL QUALITY ANALYSIS")
    print(f"  {n_total:,} ACCUMULATE signals analyzed")
    print(f"{'='*130}")

    # ═══════════════════════════════════════════════════════════
    # 1. CONFLUENCE FREQUENCY near our signals
    # ═══════════════════════════════════════════════════════════
    print(f"\n  1. NEAREST TROUGH CONFLUENCE LEVEL FOR OUR SIGNALS:")
    print(f"  {'Level':<20s} {'N':>6s} {'%':>7s} {'%AFTER':>7s} {'capture':>8s} {'dd':>8s} {'profit':>8s} {'P(bull)':>8s}")

    for level in ['L1_NOISE', 'L2_CONF', 'L3_BOS']:
        sub = df[df['trough_level'] == level]
        if len(sub) < 20:
            continue
        pct = len(sub) / n_total
        after = (sub['side'] == 'AFTER').mean()
        cap = sub['capture'].median()
        dd = sub['max_dd'].median()
        profit = sub['profit_to_peak'].median()
        pb = sub['p_bull'].median()
        print(f"  {level:<20s} {len(sub):>6,} {pct:>6.1%} {after:>6.1%} {cap:>8.2f} {dd:>+7.1f}% {profit:>+7.1f}% {pb:>7.1%}")

    # ═══════════════════════════════════════════════════════════
    # 2. SIGNALS NEAR BOS TROUGHS (within 10 days)
    # ═══════════════════════════════════════════════════════════
    print(f"\n  2. SIGNALS WITHIN 10 DAYS OF A CONFLUENCE TROUGH:")
    print(f"  {'Level':<20s} {'N':>6s} {'%AFTER':>7s} {'capture':>8s} {'dd':>8s} {'profit':>8s} {'dist_med':>10s}")

    for level in ['L1_NOISE', 'L2_CONF', 'L3_BOS']:
        sub = df[(df['trough_level'] == level) & (df['dist_to_trough'] <= 10)]
        if len(sub) < 20:
            continue
        after = (sub['side'] == 'AFTER').mean()
        cap = sub['capture'].median()
        dd = sub['max_dd'].median()
        profit = sub['profit_to_peak'].median()
        dist = sub['dist_to_trough'].median()
        print(f"  {level:<20s} {len(sub):>6,} {after:>6.1%} {cap:>8.2f} {dd:>+7.1f}% {profit:>+7.1f}% {dist:>9.0f}d")

    # ═══════════════════════════════════════════════════════════
    # 3. BOS TROUGHS + CONFIRMATION FILTERS
    # ═══════════════════════════════════════════════════════════
    print(f"\n  3. BREAK OF STRUCTURE + CONFIRMATION FILTERS (within 10d of L3_BOS trough):")

    bos_near = df[(df['trough_level'] == 'L3_BOS') & (df['dist_to_trough'] <= 10)]
    if len(bos_near) >= 20:
        filters = {
            "BOS baseline": pd.Series(True, index=bos_near.index),
            "BOS + hookup": bos_near['hookup'],
            "BOS + accel_dual": bos_near['accel_confirmed'],
            "BOS + hookup + accel": bos_near['hookup'] & bos_near['accel_confirmed'],
            "BOS + AFTER trough": bos_near['side'] == 'AFTER',
            "BOS + AFTER + hookup": (bos_near['side'] == 'AFTER') & bos_near['hookup'],
            "BOS + AFTER + accel": (bos_near['side'] == 'AFTER') & bos_near['accel_confirmed'],
        }

        print(f"  {'Filter':<35s} {'N':>6s} {'%AFTER':>7s} {'capture':>8s} {'dd':>8s} {'profit':>8s}")
        for name, mask in filters.items():
            sub = bos_near[mask]
            if len(sub) < 10:
                print(f"  {name:<35s} {len(sub):>6,} (N<10, skip)")
                continue
            after = (sub['side'] == 'AFTER').mean()
            cap = sub['capture'].median()
            dd = sub['max_dd'].median()
            profit = sub['profit_to_peak'].median()
            print(f"  {name:<35s} {len(sub):>6,} {after:>6.1%} {cap:>8.2f} {dd:>+7.1f}% {profit:>+7.1f}%")
    else:
        print(f"  BOS near signals: {len(bos_near)} (insufficient)")

    # ═══════════════════════════════════════════════════════════
    # 4. COMPARISON TABLE: BOS vs non-BOS timing
    # ═══════════════════════════════════════════════════════════
    print(f"\n  4. HEAD-TO-HEAD: BOS vs NON-BOS signals (all, within 10d):")

    near = df[df['dist_to_trough'] <= 10]
    bos = near[near['trough_level'] == 'L3_BOS']
    conf = near[near['trough_level'] == 'L2_CONF']
    noise = near[near['trough_level'] == 'L1_NOISE']

    print(f"  {'Group':<20s} {'N':>6s} {'%AFTER':>7s} {'capture':>8s} {'dd':>8s} {'profit':>8s} {'fwd quality':>12s}")

    for name, sub in [('L1 NOISE', noise), ('L2 CONFLUENCE', conf), ('L3 BOS', bos)]:
        if len(sub) < 20:
            continue
        after = (sub['side'] == 'AFTER').mean()
        cap = sub['capture'].median()
        dd = sub['max_dd'].median()
        profit = sub['profit_to_peak'].median()
        quality = after * cap * 100
        print(f"  {name:<20s} {len(sub):>6,} {after:>6.1%} {cap:>8.2f} {dd:>+7.1f}% {profit:>+7.1f}% {quality:>11.1f}")

    # ═══════════════════════════════════════════════════════════
    # 5. THE ULTIMATE: What model are we NOT losing?
    # ═══════════════════════════════════════════════════════════
    print(f"\n  5. FULL MODEL COMPARISON — v2 (baseline) vs v3 (confirmation) vs v3+BOS:")

    # v2: all P>=75%
    v2 = df.copy()
    # v3: P>=75% + (hookup OR accel)
    v3 = df[df['hookup'] | df['accel_confirmed']]
    # v3+BOS: P>=75% + (hookup OR accel) + near L2/L3 trough
    v3_bos = df[(df['hookup'] | df['accel_confirmed']) &
                (df['trough_level'].isin(['L2_CONF', 'L3_BOS'])) &
                (df['dist_to_trough'] <= 15)]

    print(f"  {'Model':<30s} {'N':>6s} {'%AFTER':>7s} {'capture':>8s} {'dd':>8s} {'profit':>8s}")
    for name, sub in [('v2 BASELINE', v2), ('v3 CONFIRMED', v3), ('v3 + CONFLUENCE', v3_bos)]:
        if len(sub) < 20:
            print(f"  {name:<30s} {len(sub):>6,} (insufficient)")
            continue
        after = (sub['side'] == 'AFTER').mean()
        cap = sub['capture'].median()
        dd = sub['max_dd'].median()
        profit = sub['profit_to_peak'].median()
        print(f"  {name:<30s} {len(sub):>6,} {after:>6.1%} {cap:>8.2f} {dd:>+7.1f}% {profit:>+7.1f}%")

    # ═══════════════════════════════════════════════════════════
    # 6. CONFLUENCE TROUGH STATISTICS (standalone)
    # ═══════════════════════════════════════════════════════════
    print(f"\n  6. ZIGZAG CONFLUENCE STATISTICS:")

    all_troughs = df.drop_duplicates(subset=['ticker', 'trough_level', 'dist_to_trough'])
    print(f"  {'Level':<15s} {'Total troughs':>15s} {'Near signals':>15s} {'Coverage':>10s}")
    for level in ['L1_NOISE', 'L2_CONF', 'L3_BOS']:
        sub = df[df['trough_level'] == level]
        total_near = len(sub[sub['dist_to_trough'] <= 5])
        total_all = len(sub)
        print(f"  {level:<15s} {total_all:>15,} {total_near:>15,} {total_near/max(total_all,1):>9.1%}")

    print("\nDONE")


def main():
    print("Loading data...")
    cs, zz25, zz50, zz75, bars = load_all()

    print("Finding trough confluences...")
    conf_troughs = find_confluences(zz25, zz50, zz75, tp_type='MIN')
    print(f"  L1_NOISE: {(conf_troughs['level']=='L1_NOISE').sum():,}")
    print(f"  L2_CONF:  {(conf_troughs['level']=='L2_CONF').sum():,}")
    print(f"  L3_BOS:   {(conf_troughs['level']=='L3_BOS').sum():,}")

    print("Finding peak confluences...")
    conf_peaks = find_confluences(zz25, zz50, zz75, tp_type='MAX')

    print("Analyzing signals vs confluences...")
    results = analyze_signals_vs_confluences(cs, bars, conf_troughs, conf_peaks)

    report(results)


if __name__ == "__main__":
    main()
