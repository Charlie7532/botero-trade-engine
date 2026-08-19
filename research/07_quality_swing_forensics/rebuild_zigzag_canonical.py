#!/usr/bin/env python3
"""
Rebuild ZigZag Ground Truth — Canonical H/L Algorithm
======================================================
Replaces ALL zigzag points in engine.zigzag_points with the canonical
implementation using High/Low (not close-only).

Scales: 2.5%, 5%, 7.5%
Tickers: All 17 training tickers
Algorithm: Canonical (High for peaks, Low for valleys, no backtrack)

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python research/07_quality_swing_forensics/rebuild_zigzag_canonical.py
"""
import os, sys, time
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]
SWING_PCTS = [0.025, 0.05, 0.075]


def zigzag_canonical(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                     min_pct: float = 0.05):
    """Canonical zigzag — High for peaks, Low for valleys, no backtrack.

    Confirmation: close crossing the threshold from the candidate extreme.
    - MAX confirmed when close drops below candidate_high * (1 - min_pct)
    - MIN confirmed when close rises above candidate_low * (1 + min_pct)

    After confirmation, the next candidate starts at the current bar.
    Returns list of (index, 'MIN'|'MAX', price) tuples.
    """
    n = len(close)
    if n < 2:
        return []

    pts = []

    # Determine initial direction from first 20 bars
    init_high_idx, init_high_val = 0, high[0]
    init_low_idx, init_low_val = 0, low[0]
    for i in range(1, min(20, n)):
        if high[i] > init_high_val:
            init_high_idx, init_high_val = i, high[i]
        if low[i] < init_low_val:
            init_low_idx, init_low_val = i, low[i]

    if init_high_idx < init_low_idx:
        # Price went up first → start looking for MAX
        direction = 1
    else:
        direction = -1

    cand_high_idx, cand_high_val = 0, high[0]
    cand_low_idx, cand_low_val = 0, low[0]

    for i in range(1, n):
        if direction == 1:  # Trending up — looking for MAX
            if high[i] > cand_high_val:
                cand_high_idx, cand_high_val = i, high[i]

            if close[i] < cand_high_val * (1 - min_pct):
                pts.append((cand_high_idx, 'MAX', cand_high_val))
                direction = -1
                cand_low_idx, cand_low_val = i, low[i]

        elif direction == -1:  # Trending down — looking for MIN
            if low[i] < cand_low_val:
                cand_low_idx, cand_low_val = i, low[i]

            if close[i] > cand_low_val * (1 + min_pct):
                pts.append((cand_low_idx, 'MIN', cand_low_val))
                direction = 1
                cand_high_idx, cand_high_val = i, high[i]

    return pts


def main():
    print("=" * 90)
    print("  REBUILD ZIGZAG — Canonical H/L Algorithm")
    print(f"  Scales: {[f'{p*100:.1f}%' for p in SWING_PCTS]}")
    print(f"  Tickers: {len(TICKERS)}")
    print("=" * 90)

    store = TimescaleDataStore()
    conn = store.engine.raw_connection()
    cur = conn.cursor()
    t0 = time.time()

    try:
        # ── 1. PURGE ALL existing zigzag points ──
        print("\n1. PURGING ALL existing zigzag points...")
        cur.execute("SELECT COUNT(*) FROM engine.zigzag_points;")
        old_count = cur.fetchone()[0]
        cur.execute("DELETE FROM engine.zigzag_points;")
        conn.commit()
        print(f"   Purged {old_count:,d} old points (all tickers, all scales).")

        # ── 2. LOAD OHLCV for all tickers ──
        print("\n2. LOADING OHLCV DATA...")
        ohlcv_all = pd.read_sql("""
            SELECT ticker, time as timestamp, open, high, low, close, volume
            FROM market.ohlcv_bars
            WHERE timeframe='1d'
            ORDER BY ticker, time
        """, store.engine)
        print(f"   Loaded {len(ohlcv_all):,d} total bars.")

        # ── 3. COMPUTE canonical zigzag ──
        print("\n3. COMPUTING CANONICAL ZIGZAG (H/L, no backtrack)...")

        grand_total = 0
        summary_rows = []

        for tk in TICKERS:
            tk_data = ohlcv_all[ohlcv_all['ticker'] == tk].sort_values('timestamp').reset_index(drop=True)
            if len(tk_data) < 100:
                print(f"   ⚠️ {tk}: skipped ({len(tk_data)} bars)")
                continue

            high = tk_data['high'].values.astype(float)
            low = tk_data['low'].values.astype(float)
            close = tk_data['close'].values.astype(float)
            timestamps = tk_data['timestamp'].values

            for min_sw in SWING_PCTS:
                pts = zigzag_canonical(high, low, close, min_sw)

                rows = []
                for j, (idx, tp_type, val) in enumerate(pts):
                    if idx >= len(timestamps):
                        continue

                    # Compute swing to next point
                    swing_ret = None
                    swing_days = None
                    swing_speed = None
                    if j + 1 < len(pts):
                        next_idx, _, next_val = pts[j + 1]
                        if next_idx < len(timestamps):
                            swing_ret = next_val / val - 1
                            swing_days = next_idx - idx
                            swing_speed = swing_ret / max(swing_days, 1)

                    rows.append((
                        tk,
                        pd.Timestamp(timestamps[idx]).strftime('%Y-%m-%d %H:%M:%S+00'),
                        tp_type,
                        float(val),
                        float(min_sw),
                        float(swing_ret) if swing_ret is not None else None,
                        int(swing_days) if swing_days is not None else None,
                        float(swing_speed) if swing_speed is not None else None,
                    ))

                if rows:
                    cur.executemany("""
                        INSERT INTO engine.zigzag_points
                        (ticker, timestamp, tp_type, price, min_swing_pct,
                         swing_return, swing_days, swing_speed)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, rows)

                    n_min = sum(1 for r in rows if r[2] == 'MIN')
                    n_max = sum(1 for r in rows if r[2] == 'MAX')
                    grand_total += len(rows)

                    summary_rows.append({
                        'ticker': tk,
                        'pct': min_sw,
                        'n_min': n_min,
                        'n_max': n_max,
                        'total': len(rows),
                        'bars': len(tk_data),
                    })

                    pct_label = f"{min_sw*100:.1f}%"
                    print(f"   {tk:>6s} ({pct_label}): {n_min} MIN + {n_max} MAX = {len(rows)} points")

        conn.commit()
        print(f"\n   🎉 TOTAL: {grand_total:,d} zigzag points persisted to engine.zigzag_points")

        # ── 4. SUMMARY STATISTICS ──
        print(f"\n{'=' * 90}")
        print(f"  SUMMARY BY SCALE")
        print(f"{'=' * 90}")

        df_sum = pd.DataFrame(summary_rows)
        for pct in SWING_PCTS:
            sub = df_sum[df_sum['pct'] == pct]
            total = sub['total'].sum()
            total_min = sub['n_min'].sum()
            total_max = sub['n_max'].sum()
            density = total / sub['bars'].sum() * 100
            print(f"\n  ZigZag {pct*100:.1f}%:")
            print(f"    Points: {total:,d} ({total_min:,d} MIN + {total_max:,d} MAX)")
            print(f"    Density: {density:.2f}% of bars are turning points")
            print(f"    Avg per ticker: {total/len(TICKERS):.0f}")

        # Per-ticker summary for 5%
        print(f"\n  ── Per-Ticker: ZigZag 5.0% ──")
        print(f"  {'Ticker':>6s} │ {'Bars':>6s} │ {'MINs':>5s} │ {'MAXs':>5s} │ {'Total':>6s} │ {'Density':>7s}")
        print(f"  {'─' * 55}")
        sub5 = df_sum[df_sum['pct'] == 0.05].sort_values('ticker')
        for _, row in sub5.iterrows():
            density = row['total'] / row['bars'] * 100
            print(f"  {row['ticker']:>6s} │ {row['bars']:>6d} │ {row['n_min']:>5d} │ {row['n_max']:>5d} │ {row['total']:>6d} │ {density:>6.2f}%")

        # ── 5. COMPARISON: Old counts vs New ──
        print(f"\n{'=' * 90}")
        print(f"  COMPARISON: Old (close 3/5/7%) vs New (canonical H/L 2.5/5/7.5%)")
        print(f"{'=' * 90}")
        print(f"    Old total (purged): {old_count:,d}")
        print(f"    New total:          {grand_total:,d}")
        if old_count > 0:
            print(f"    Change:             {grand_total - old_count:+,d} ({(grand_total/old_count - 1)*100:+.1f}%)")

        # ── 6. SWING STATS for 2.5% ──
        print(f"\n{'=' * 90}")
        print(f"  SWING STATISTICS — 2.5% (finest grain)")
        print(f"{'=' * 90}")
        cur.execute("""
            SELECT tp_type,
                   COUNT(*) as n,
                   ROUND(AVG(ABS(swing_return) * 100)::numeric, 2) as avg_swing_pct,
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ABS(swing_return) * 100)::numeric, 2) as med_swing_pct,
                   ROUND(AVG(swing_days)::numeric, 1) as avg_days,
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY swing_days)::numeric, 0) as med_days
            FROM engine.zigzag_points
            WHERE min_swing_pct = 0.025 AND swing_return IS NOT NULL
            GROUP BY tp_type
            ORDER BY tp_type;
        """)
        rows = cur.fetchall()
        print(f"  {'Type':>4s} │ {'N':>6s} │ {'Avg Swing%':>10s} │ {'Med Swing%':>10s} │ {'Avg Days':>8s} │ {'Med Days':>8s}")
        print(f"  {'─' * 60}")
        for tp_type, n, avg_sw, med_sw, avg_d, med_d in rows:
            print(f"  {tp_type:>4s} │ {n:>6d} │ {avg_sw:>9.2f}% │ {med_sw:>9.2f}% │ {avg_d:>8.1f} │ {med_d:>8.0f}")

    except Exception as e:
        conn.rollback()
        import traceback
        traceback.print_exc()
        print(f"\n🔴 ERROR: {e}")
    finally:
        cur.close()
        conn.close()
        store.close()

    elapsed = time.time() - t0
    print(f"\n  Time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
