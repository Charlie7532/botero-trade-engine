#!/usr/bin/env python3
"""
Backtest T10 (No-Determination) and T12 (σVw Transition) — Zone-Guarded
=========================================================================
Tests whether these two remaining candidate filters add value when
combined with the Unified Tree (T8) and velocities (T7).

T10: RSI < 40 AND RSIδ5 < 0 AND σ < -1 → confirms piso
     RSI > 45 OR RSIδ5 > +5 OR σ > 0 → rejects piso

T12: σVw transition ≥ +1 → 62.6% AFTER trough (but PREMATURE in extremes)
     Zone guard: only fire in normal zone (-2 < σ_w < 2)

Run:
  PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
    backend/scripts/backtest_t10_t12.py
"""
from dotenv import load_dotenv
load_dotenv()

import numpy as np
import pandas as pd
import logging
from datetime import timedelta

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

TICKERS = [
    "AAPL", "AMZN", "COST", "HD", "HON", "IBM", "JNJ", "JPM",
    "MCD", "MRK", "MSFT", "PEP", "PG", "QQQ", "SPY", "WMT", "XOM",
]

# ZigZag threshold for ground truth
ZIGZAG_PCT = 0.025


def compute_zigzag(close: np.ndarray, pct: float = ZIGZAG_PCT) -> np.ndarray:
    """Compute zigzag labels: +1=trough (MIN), -1=peak (MAX), 0=neither."""
    n = len(close)
    labels = np.zeros(n, dtype=int)

    direction = 0  # +1 looking for peak, -1 looking for trough
    last_pivot_val = close[0]
    last_pivot_idx = 0

    for i in range(1, n):
        if direction == 0:
            if close[i] >= last_pivot_val * (1 + pct):
                direction = 1
                labels[last_pivot_idx] = 1  # previous was trough
                last_pivot_val = close[i]
                last_pivot_idx = i
            elif close[i] <= last_pivot_val * (1 - pct):
                direction = -1
                labels[last_pivot_idx] = -1  # previous was peak
                last_pivot_val = close[i]
                last_pivot_idx = i
        elif direction == 1:
            if close[i] >= last_pivot_val:
                last_pivot_val = close[i]
                last_pivot_idx = i
            elif close[i] <= last_pivot_val * (1 - pct):
                labels[last_pivot_idx] = -1  # peak
                direction = -1
                last_pivot_val = close[i]
                last_pivot_idx = i
        else:
            if close[i] <= last_pivot_val:
                last_pivot_val = close[i]
                last_pivot_idx = i
            elif close[i] >= last_pivot_val * (1 + pct):
                labels[last_pivot_idx] = 1  # trough
                direction = 1
                last_pivot_val = close[i]
                last_pivot_idx = i

    return labels


def main():
    store = TimescaleDataStore()
    conn = store._conn()

    logger.info("=" * 60)
    logger.info("T10/T12 BACKTEST — Combined with Unified Tree (T8)")
    logger.info("=" * 60)

    all_results = []

    for ticker in TICKERS:
        try:
            df = pd.read_sql("""
                SELECT cs.timestamp, cs.ticker,
                       cs.sigma_current, cs.sigma_wave, cs.vwap_sigma_wave,
                       cs.tide_slope, cs.current_slope, cs.wave_slope,
                       cs.rsi_value,
                       cs.obs_recovery_score, cs.obs_vel_sigma_c, cs.obs_vel_svw
                FROM engine.channel_snapshots cs
                WHERE cs.ticker = %s AND cs.timeframe = '1d'
                ORDER BY cs.timestamp
            """, conn, params=(ticker,))

            if len(df) < 250:
                logger.info(f"  {ticker}: skipping ({len(df)} bars < 250)")
                continue

            # Get close prices for zigzag
            prices = pd.read_sql("""
                SELECT time, close FROM market.ohlcv_bars
                WHERE ticker = %s AND timeframe = '1d'
                ORDER BY time
            """, conn, params=(ticker,))

            # Merge on date
            df['date'] = pd.to_datetime(df['timestamp']).dt.date
            prices['date'] = pd.to_datetime(prices['time']).dt.date
            merged = df.merge(prices[['date', 'close']], on='date', how='inner')

            if len(merged) < 250:
                continue

            close = merged['close'].values.astype(float)
            zz = compute_zigzag(close, ZIGZAG_PCT)

            # Build forward labels: is the NEXT zigzag point a trough (+1) or peak (-1)?
            fwd_label = np.zeros(len(merged))
            next_pivot_type = 0
            for i in range(len(merged) - 1, -1, -1):
                if zz[i] != 0:
                    next_pivot_type = zz[i]
                fwd_label[i] = next_pivot_type

            # Forward return 20d
            fwd20 = np.zeros(len(merged))
            for i in range(len(merged) - 20):
                fwd20[i] = (close[i + 20] / close[i]) - 1

            merged['fwd_label'] = fwd_label
            merged['fwd20'] = fwd20
            merged['is_bull'] = (fwd_label == 1).astype(int)  # next pivot is trough = currently bullish
            # Actually: next pivot = trough means we're heading DOWN to it
            # next pivot = peak means we're heading UP to it
            # So is_bull = next pivot is peak (we're going UP)
            merged['is_bull'] = (fwd_label == -1).astype(int)

            # ── T10: No-Determination filter ──
            sigma_c = merged['sigma_current'].fillna(0).values
            rsi = merged['rsi_value'].fillna(50).values
            rsi_d5 = np.zeros(len(merged))
            rsi_d5[5:] = rsi[5:] - rsi[:-5]

            t10_confirms = (rsi < 40) & (rsi_d5 < 0) & (sigma_c < -1)
            t10_rejects = (rsi > 45) | (rsi_d5 > 5) | (sigma_c > 0)

            # ── T12: σVw Transition (zone-guarded) ──
            svw = merged['vwap_sigma_wave'].fillna(0).values
            svw_delta = np.zeros(len(merged))
            svw_delta[1:] = svw[1:] - svw[:-1]
            sigma_w = merged['sigma_wave'].fillna(0).values

            t12_normal_zone = (sigma_w > -2) & (sigma_w < 2)
            t12_improving = (svw_delta >= 0.1) & t12_normal_zone
            t12_deteriorating = (svw_delta <= -0.1) & t12_normal_zone

            # ── Collect statistics ──
            for filter_name, mask in [
                ("BASELINE", np.ones(len(merged), dtype=bool)),
                ("T10_CONFIRMS", t10_confirms),
                ("T10_REJECTS", t10_rejects),
                ("T12_IMPROVING", t12_improving),
                ("T12_DETERIORATING", t12_deteriorating),
                ("T10+T12_COMBINED", t10_confirms & t12_improving),
            ]:
                subset = merged[mask]
                if len(subset) < 10:
                    continue

                n = len(subset)
                bull_pct = subset['is_bull'].mean() * 100
                fwd20_mean = subset['fwd20'].mean() * 100
                fwd20_med = subset['fwd20'].median() * 100

                all_results.append({
                    'ticker': ticker,
                    'filter': filter_name,
                    'n': n,
                    'bull_pct': bull_pct,
                    'fwd20_mean': fwd20_mean,
                    'fwd20_med': fwd20_med,
                })

        except Exception as e:
            logger.warning(f"  {ticker}: error: {e}")

    store._put(conn)
    store.close()

    if not all_results:
        logger.error("No results! Check DB connectivity.")
        return

    results = pd.DataFrame(all_results)

    # ── Aggregate across tickers ──
    logger.info("\n" + "=" * 60)
    logger.info("AGGREGATE RESULTS (all tickers)")
    logger.info("=" * 60)

    agg = results.groupby('filter').agg(
        n_total=('n', 'sum'),
        n_tickers=('ticker', 'nunique'),
        bull_pct_mean=('bull_pct', 'mean'),
        fwd20_mean=('fwd20_mean', 'mean'),
        fwd20_med=('fwd20_med', 'mean'),
    ).round(2)

    # Compute spread vs baseline
    baseline = agg.loc['BASELINE'] if 'BASELINE' in agg.index else None

    print("\n{:<25s} {:>8s} {:>6s} {:>10s} {:>10s} {:>10s} {:>10s}".format(
        "Filter", "N", "Tks", "Bull%", "Fwd20µ%", "Fwd20m%", "Δ_Bull"
    ))
    print("-" * 80)
    for idx, row in agg.iterrows():
        delta = row['bull_pct_mean'] - baseline['bull_pct_mean'] if baseline is not None else 0
        print("{:<25s} {:>8.0f} {:>6.0f} {:>10.1f} {:>10.2f} {:>10.2f} {:>+10.1f}".format(
            idx, row['n_total'], row['n_tickers'],
            row['bull_pct_mean'], row['fwd20_mean'], row['fwd20_med'], delta,
        ))

    # ── Per filter × ticker detail ──
    logger.info("\n" + "=" * 60)
    logger.info("PER TICKER DETAIL")
    logger.info("=" * 60)

    for filt in ['T10_CONFIRMS', 'T12_IMPROVING', 'T10+T12_COMBINED']:
        sub = results[results['filter'] == filt]
        if sub.empty:
            continue
        base = results[results['filter'] == 'BASELINE']
        print(f"\n--- {filt} ---")
        print(f"{'Ticker':<8s} {'N':>6s} {'Bull%':>8s} {'Δ_Bull':>8s} {'Fwd20µ%':>10s}")
        for _, r in sub.iterrows():
            b = base[base['ticker'] == r['ticker']]
            delta = r['bull_pct'] - b.iloc[0]['bull_pct'] if not b.empty else 0
            print(f"{r['ticker']:<8s} {r['n']:>6.0f} {r['bull_pct']:>8.1f} {delta:>+8.1f} {r['fwd20_mean']:>10.2f}")

    logger.info("\nBacktest complete.")


if __name__ == "__main__":
    main()
