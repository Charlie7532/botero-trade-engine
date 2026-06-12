#!/usr/bin/env python3
"""
Signal Timing Forensics — ¿Cuán oportunas son nuestras señales?
================================================================
Para cada señal ACCUMULATE/TRIM del modelo v2, mide:

ACCUMULATE:
  1. days_to_trough: ¿Cuántos días hasta el siguiente zigzag MIN?
     → Negativo = compramos ANTES del piso (malo, cuchillo cayendo)
     → Positivo = compramos DESPUÉS del piso (bien, confirmación)
  2. days_since_trough: ¿Cuántos días desde el último MIN?
     → Bajo = comprando cerca del piso (bien)
  3. price_from_trough_pct: ¿Cuánto arriba del piso más cercano?
     → Bajo = bueno, compramos near-bottom
  4. capture_ratio: Del swing total (trough→peak), ¿qué % capturamos?
     → 1.0 = compramos en el fondo exacto, 0.0 = compramos en el techo
  5. max_drawdown_to_trough: ¿Cuánto cae desde nuestra compra hasta el piso?
     → Mide el dolor de comprar antes de tiempo

TRIM:
  1. days_to_peak: ¿Cuántos días hasta el siguiente zigzag MAX?
  2. price_from_peak_pct: ¿Cuánto debajo del techo vendemos?
  3. upside_left: ¿Cuánto dejamos en la mesa?

Output: Tabla de timing quality por P(bull) quintile y por ticker.
"""
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
import numpy as np
from datetime import date
from collections import defaultdict

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.quality_swing.domain.rules.rc_state_probability import lookup_probability


# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════

TEST_START = "2020-02-01"
ZIGZAG_LEVEL = 0.05
ACCUMULATE_THRESHOLD = 0.65  # Current v2 threshold


# ═══════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════

def load_data():
    store = TimescaleDataStore()
    conn = store._conn()

    cs = pd.read_sql(f"""
        SELECT ticker, timestamp::date as date,
               sigma_current, sigma_wave, vwap_sigma_wave, tide_slope
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
        SELECT ticker, time::date as date, close, high, low
        FROM market.ohlcv_bars
        WHERE timeframe = '1d'
        ORDER BY ticker, time
    """, conn)

    store._put(conn); store.close()

    cs['date'] = pd.to_datetime(cs['date'])
    zz['date'] = pd.to_datetime(zz['date'])
    bars['date'] = pd.to_datetime(bars['date'])

    return cs, zz, bars


# ═══════════════════════════════════════════════════════════════
# TIMING ANALYSIS
# ═══════════════════════════════════════════════════════════════

def analyze_timing(cs, zz, bars):
    """For each signal bar, measure timing vs zigzag turning points."""
    df = cs.merge(bars[['ticker', 'date', 'close']], on=['ticker', 'date'], how='inner')
    df = df.sort_values(['ticker', 'date']).reset_index(drop=True)

    # Classify signals
    signals = []
    for _, row in df.iterrows():
        rc = lookup_probability(
            tide_slope=float(row['tide_slope']),
            sigma_current=float(row['sigma_current']),
            sigma_wave=float(row['sigma_wave']),
            vwap_sigma_wave=float(row['vwap_sigma_wave']),
        )
        if rc is None:
            continue

        if rc.prob_bull >= ACCUMULATE_THRESHOLD:
            action = "ACCUMULATE"
        elif rc.prob_bull <= 0.35:
            action = "TRIM"
        else:
            action = "HOLD"

        signals.append({
            'ticker': row['ticker'],
            'date': row['date'],
            'close': float(row['close']),
            'action': action,
            'p_bull': rc.prob_bull,
            'level': rc.level,
            'state_key': rc.state_key,
        })

    sig_df = pd.DataFrame(signals)
    print(f"Signals: {len(sig_df):,} total")
    print(f"  ACCUMULATE: {(sig_df['action']=='ACCUMULATE').sum():,}")
    print(f"  TRIM: {(sig_df['action']=='TRIM').sum():,}")
    print(f"  HOLD: {(sig_df['action']=='HOLD').sum():,}")

    # Timing metrics
    accum_metrics = []
    trim_metrics = []

    for ticker in sig_df['ticker'].unique():
        tk_sig = sig_df[sig_df['ticker'] == ticker]
        tk_zz = zz[zz['ticker'] == ticker].sort_values('date')
        tk_bars = bars[bars['ticker'] == ticker].sort_values('date')

        troughs = tk_zz[tk_zz['tp_type'] == 'MIN']
        peaks = tk_zz[tk_zz['tp_type'] == 'MAX']

        if len(troughs) < 2 or len(peaks) < 2:
            continue

        trough_dates = pd.to_datetime(troughs['date']).values  # numpy datetime64
        trough_prices = troughs['price'].values.astype(float)
        peak_dates = pd.to_datetime(peaks['date']).values
        peak_prices = peaks['price'].values.astype(float)

        bar_dates = pd.to_datetime(tk_bars['date']).values
        bar_close = tk_bars['close'].values.astype(float)
        bar_low = tk_bars['low'].values.astype(float)

        for _, sig in tk_sig.iterrows():
            d = np.datetime64(sig['date'])
            price = sig['close']

            if sig['action'] == 'ACCUMULATE':
                # Find nearest trough (before and after)
                t_next_idx = np.searchsorted(trough_dates, d, side='right')
                t_prev_idx = t_next_idx - 1

                if t_next_idx >= len(trough_dates) or t_prev_idx < 0:
                    continue

                next_trough_date = trough_dates[t_next_idx]
                next_trough_price = trough_prices[t_next_idx]
                prev_trough_date = trough_dates[t_prev_idx]
                prev_trough_price = trough_prices[t_prev_idx]

                # Days to/from troughs
                days_to_next_trough = (next_trough_date - d) / np.timedelta64(1, 'D')
                days_from_prev_trough = (d - prev_trough_date) / np.timedelta64(1, 'D')

                # Find the nearest trough (whichever is closer in time)
                if days_to_next_trough < days_from_prev_trough:
                    nearest_trough_price = next_trough_price
                    days_to_nearest = days_to_next_trough
                    side = "BEFORE"
                else:
                    nearest_trough_price = prev_trough_price
                    days_to_nearest = -days_from_prev_trough
                    side = "AFTER"

                # Price distance from nearest trough
                price_from_trough_pct = (price / nearest_trough_price - 1.0) * 100

                # Next peak after this date (for capture ratio)
                p_next_idx = np.searchsorted(peak_dates, d, side='right')
                if p_next_idx >= len(peak_dates):
                    continue

                next_peak_price = peak_prices[p_next_idx]

                # Capture ratio: how much of the trough-to-peak swing do we get?
                if next_peak_price > nearest_trough_price:
                    # Ideal: bought at trough → capture = 1.0
                    # Bought at peak → capture = 0.0
                    capture = (next_peak_price - price) / (next_peak_price - nearest_trough_price)
                    capture = max(0.0, min(1.0, capture))
                else:
                    capture = 0.0

                # Max drawdown from entry to next trough
                if days_to_next_trough > 0:
                    # We're buying before the trough — measure the pain
                    bar_idx = np.searchsorted(bar_dates, d, side='left')
                    trough_bar_idx = np.searchsorted(bar_dates, next_trough_date, side='left')
                    if bar_idx < len(bar_low) and trough_bar_idx < len(bar_low):
                        min_low = bar_low[bar_idx:min(trough_bar_idx+1, len(bar_low))].min()
                        max_dd = (min_low / price - 1.0) * 100
                    else:
                        max_dd = 0.0
                else:
                    max_dd = 0.0  # Bought after trough — no drawdown to trough

                accum_metrics.append({
                    'ticker': ticker,
                    'date': d,
                    'price': price,
                    'p_bull': sig['p_bull'],
                    'level': sig['level'],
                    'days_to_nearest_trough': days_to_nearest,
                    'side': side,
                    'days_to_next_trough': days_to_next_trough,
                    'days_from_prev_trough': days_from_prev_trough,
                    'price_from_trough_pct': price_from_trough_pct,
                    'capture_ratio': capture,
                    'max_drawdown_pct': max_dd,
                    'next_peak_price': next_peak_price,
                    'profit_to_peak_pct': (next_peak_price / price - 1.0) * 100,
                })

            elif sig['action'] == 'TRIM':
                # Find nearest peak
                p_next_idx = np.searchsorted(peak_dates, d, side='right')
                p_prev_idx = p_next_idx - 1

                if p_prev_idx < 0:
                    continue

                if p_next_idx < len(peak_dates):
                    next_peak_date = peak_dates[p_next_idx]
                    next_peak_price = peak_prices[p_next_idx]
                    days_to_next_peak = (next_peak_date - d) / np.timedelta64(1, 'D')
                else:
                    days_to_next_peak = None
                    next_peak_price = None

                prev_peak_date = peak_dates[p_prev_idx]
                prev_peak_price = peak_prices[p_prev_idx]
                days_from_prev_peak = (d - prev_peak_date) / np.timedelta64(1, 'D')

                # Next trough (the downside we're avoiding)
                t_next_idx = np.searchsorted(trough_dates, d, side='right')
                if t_next_idx < len(trough_dates):
                    next_trough_price = trough_prices[t_next_idx]
                    avoided_loss = (1.0 - next_trough_price / price) * 100
                else:
                    avoided_loss = None

                trim_metrics.append({
                    'ticker': ticker,
                    'date': d,
                    'price': price,
                    'p_bull': sig['p_bull'],
                    'days_to_next_peak': days_to_next_peak,
                    'days_from_prev_peak': days_from_prev_peak,
                    'upside_left_pct': (next_peak_price / price - 1.0) * 100 if next_peak_price else None,
                    'avoided_loss_pct': avoided_loss,
                })

    return pd.DataFrame(accum_metrics), pd.DataFrame(trim_metrics)


# ═══════════════════════════════════════════════════════════════
# REPORTING
# ═══════════════════════════════════════════════════════════════

def report(accum, trim):
    print(f"\n{'='*120}")
    print(f"  SIGNAL TIMING FORENSICS")
    print(f"  ACCUMULATE signals: {len(accum):,} | TRIM signals: {len(trim):,}")
    print(f"{'='*120}")

    # ── ACCUMULATE TIMING ──
    print(f"\n{'─'*120}")
    print(f"  ACCUMULATE — Timing vs Zigzag Troughs (5% swing)")
    print(f"{'─'*120}\n")

    # Before vs After trough
    before = accum[accum['side'] == 'BEFORE']
    after = accum[accum['side'] == 'AFTER']
    print(f"  Buying BEFORE trough (cuchillo cayendo):  {len(before):>6,} ({len(before)/len(accum):.1%})")
    print(f"  Buying AFTER trough (confirmación):       {len(after):>6,} ({len(after)/len(accum):.1%})")

    print(f"\n  {'Metric':<35s} {'All':>10s} {'BEFORE':>10s} {'AFTER':>10s}")
    for name, col in [
        ('Days to nearest trough', 'days_to_nearest_trough'),
        ('Price from trough (%)', 'price_from_trough_pct'),
        ('Capture ratio (0=top, 1=bottom)', 'capture_ratio'),
        ('Max drawdown to trough (%)', 'max_drawdown_pct'),
        ('Profit to next peak (%)', 'profit_to_peak_pct'),
    ]:
        all_med = accum[col].median()
        bef_med = before[col].median() if len(before) > 0 else 0
        aft_med = after[col].median() if len(after) > 0 else 0
        print(f"  {name:<35s} {all_med:>+10.1f} {bef_med:>+10.1f} {aft_med:>+10.1f}")

    # By P(bull) quintile
    print(f"\n  ACCUMULATE TIMING BY P(bull) QUINTILE:")
    print(f"  {'P(bull)':<12s} {'N':>6s} {'%BEFORE':>8s} {'capture':>8s} {'dd_med':>8s} "
          f"{'profit':>8s} {'dist_trough':>12s}")

    pbins = [(0.65, 0.70), (0.70, 0.75), (0.75, 0.80), (0.80, 0.85),
             (0.85, 0.90), (0.90, 1.01)]
    for lo, hi in pbins:
        sub = accum[(accum['p_bull'] >= lo) & (accum['p_bull'] < hi)]
        if len(sub) < 20:
            continue
        pct_before = (sub['side'] == 'BEFORE').mean()
        cap = sub['capture_ratio'].median()
        dd = sub['max_drawdown_pct'].median()
        profit = sub['profit_to_peak_pct'].median()
        dist = sub['price_from_trough_pct'].median()
        print(f"  {lo:.0%}-{hi:.0%}       {len(sub):>6,} {pct_before:>7.1%} {cap:>8.2f} {dd:>+7.1f}% "
              f"{profit:>+7.1f}% {dist:>+11.1f}%")

    # By ticker
    print(f"\n  ACCUMULATE TIMING BY TICKER:")
    print(f"  {'Ticker':<8s} {'N':>6s} {'%BEFORE':>8s} {'capture':>8s} {'dd_med':>8s} "
          f"{'profit':>8s} {'dist_days':>10s}")

    for ticker in sorted(accum['ticker'].unique()):
        sub = accum[accum['ticker'] == ticker]
        if len(sub) < 10:
            continue
        pct_before = (sub['side'] == 'BEFORE').mean()
        cap = sub['capture_ratio'].median()
        dd = sub['max_drawdown_pct'].median()
        profit = sub['profit_to_peak_pct'].median()
        dist_days = sub['days_to_nearest_trough'].abs().median()
        print(f"  {ticker:<8s} {len(sub):>6,} {pct_before:>7.1%} {cap:>8.2f} {dd:>+7.1f}% "
              f"{profit:>+7.1f}% {dist_days:>9.0f}d")

    # ── TRIM TIMING ──
    if len(trim) > 0:
        print(f"\n{'─'*120}")
        print(f"  TRIM — Timing vs Zigzag Peaks (5% swing)")
        print(f"{'─'*120}\n")

        valid_trim = trim.dropna(subset=['avoided_loss_pct', 'upside_left_pct'])
        print(f"  Signals with complete data: {len(valid_trim):,}")
        if len(valid_trim) > 0:
            print(f"  Median avoided loss:     {valid_trim['avoided_loss_pct'].median():+.1f}%")
            print(f"  Median upside left:      {valid_trim['upside_left_pct'].median():+.1f}%")
            print(f"  Median days to next peak:{valid_trim['days_to_next_peak'].median():.0f}")

            # Trim where we actually avoided loss > 5%
            good_trims = valid_trim[valid_trim['avoided_loss_pct'] > 5.0]
            bad_trims = valid_trim[valid_trim['avoided_loss_pct'] < 0.0]
            print(f"\n  Good trims (avoided >5% loss): {len(good_trims):,} ({len(good_trims)/len(valid_trim):.1%})")
            print(f"  Bad trims (price went up):     {len(bad_trims):,} ({len(bad_trims)/len(valid_trim):.1%})")

    # ── TRANSITION ANALYSIS: when do signals CLUSTER? ──
    print(f"\n{'─'*120}")
    print(f"  SIGNAL CLUSTERING — Are signals isolated or clustered?")
    print(f"{'─'*120}\n")

    # For each ticker, find runs of consecutive ACCUMULATE days
    run_lengths = []
    for ticker in accum['ticker'].unique():
        tk = accum[accum['ticker'] == ticker].sort_values('date')
        if len(tk) < 2:
            continue
        diffs = tk['date'].diff().dt.days
        # New run when gap > 3 business days
        run_id = (diffs > 3).cumsum()
        for _, grp in tk.groupby(run_id):
            run_lengths.append({
                'ticker': ticker,
                'length': len(grp),
                'start': grp['date'].min(),
                'end': grp['date'].max(),
                'mean_p_bull': grp['p_bull'].mean(),
                'mean_capture': grp['capture_ratio'].mean(),
            })

    runs = pd.DataFrame(run_lengths)
    if len(runs) > 0:
        print(f"  Total ACCUMULATE clusters: {len(runs):,}")
        print(f"  Median cluster length:     {runs['length'].median():.0f} days")
        print(f"  Mean cluster length:       {runs['length'].mean():.0f} days")
        print(f"  Isolated signals (1 day):  {(runs['length'] == 1).sum():,} ({(runs['length'] == 1).mean():.1%})")

        # Capture by cluster position: first day vs last day vs middle
        print(f"\n  Capture by cluster position (first/last/middle):")
        first_days = []
        last_days = []
        mid_days = []
        for ticker in accum['ticker'].unique():
            tk = accum[accum['ticker'] == ticker].sort_values('date')
            diffs = tk['date'].diff().dt.days
            run_id = (diffs > 3).cumsum()
            for _, grp in tk.groupby(run_id):
                if len(grp) >= 3:
                    first_days.append(grp.iloc[0])
                    last_days.append(grp.iloc[-1])
                    for j in range(1, len(grp)-1):
                        mid_days.append(grp.iloc[j])

        if first_days:
            fd = pd.DataFrame(first_days)
            ld = pd.DataFrame(last_days)
            md = pd.DataFrame(mid_days) if mid_days else pd.DataFrame()

            print(f"    First day:  capture={fd['capture_ratio'].median():.2f}  "
                  f"dd={fd['max_drawdown_pct'].median():+.1f}%  "
                  f"profit={fd['profit_to_peak_pct'].median():+.1f}%  N={len(fd)}")
            print(f"    Last day:   capture={ld['capture_ratio'].median():.2f}  "
                  f"dd={ld['max_drawdown_pct'].median():+.1f}%  "
                  f"profit={ld['profit_to_peak_pct'].median():+.1f}%  N={len(ld)}")
            if len(md) > 0:
                print(f"    Middle:     capture={md['capture_ratio'].median():.2f}  "
                      f"dd={md['max_drawdown_pct'].median():+.1f}%  "
                      f"profit={md['profit_to_peak_pct'].median():+.1f}%  N={len(md)}")

    print("\nDONE")


def main():
    cs, zz, bars = load_data()
    accum, trim = analyze_timing(cs, zz, bars)
    report(accum, trim)


if __name__ == "__main__":
    main()
