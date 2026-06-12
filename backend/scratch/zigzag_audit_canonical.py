#!/usr/bin/env python3
"""
ZigZag Algorithm Audit — Canonical vs Current Implementation
================================================================
Compares:
  A) Current: close-only with argmax/argmin backtrack
  B) Canonical: High/Low with no backtrack (literature standard)
  C) Close-only without backtrack (isolate the backtrack effect)

For each variant, computes zigzag at 3%, 5%, 7% for all 17 tickers.
Reports: point counts, location divergence, and examples.

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scratch/zigzag_audit_canonical.py
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
SWING_PCTS = [0.03, 0.05, 0.07]


# ═══════════════════════════════════════════════════════════════
# VARIANT A: Current implementation (close-only + argmax backtrack)
# ═══════════════════════════════════════════════════════════════
def zigzag_current(close: np.ndarray, min_pct: float = 0.05):
    """Current implementation — close only, with argmax/argmin backtrack."""
    if len(close) < 2:
        return []

    pts = []
    last_idx = 0
    last_type = 'MIN' if close[0] < close[min(1, len(close)-1)] else 'MAX'
    last_val = close[0]

    for i in range(1, len(close)):
        if last_type == 'MIN':
            if close[i] > last_val * (1 + min_pct):
                pts.append((last_idx, 'MIN', last_val))
                best = last_idx + int(np.argmax(close[last_idx:i+1]))
                last_idx, last_type, last_val = best, 'MAX', close[best]
            elif close[i] < last_val:
                last_idx, last_val = i, close[i]
        else:
            if close[i] < last_val * (1 - min_pct):
                pts.append((last_idx, 'MAX', last_val))
                best = last_idx + int(np.argmin(close[last_idx:i+1]))
                last_idx, last_type, last_val = best, 'MIN', close[best]
            elif close[i] > last_val:
                last_idx, last_val = i, close[i]

    return pts


# ═══════════════════════════════════════════════════════════════
# VARIANT B: Canonical (High/Low, no backtrack)
# ═══════════════════════════════════════════════════════════════
def zigzag_canonical(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                     min_pct: float = 0.05):
    """Canonical zigzag — uses High for peaks, Low for valleys.
    
    No backtrack after confirmation. After confirming a pivot,
    the next candidate starts from the current bar.
    
    Confirmation uses close crossing the threshold (standard approach):
    - MAX confirmed when close drops below peak_high * (1 - min_pct)
    - MIN confirmed when close rises above trough_low * (1 + min_pct)
    """
    n = len(close)
    if n < 2:
        return []

    pts = []

    # Initialize direction: look at first few bars to determine
    # Find first significant move
    direction = 0  # 1 = looking for MAX (trending up), -1 = looking for MIN (trending down)
    
    # Start by finding whether first move is up or down
    cand_high_idx, cand_high_val = 0, high[0]
    cand_low_idx, cand_low_val = 0, low[0]
    
    # Determine initial direction from first bars
    for i in range(1, min(20, n)):
        if high[i] > cand_high_val:
            cand_high_idx, cand_high_val = i, high[i]
        if low[i] < cand_low_val:
            cand_low_idx, cand_low_val = i, low[i]
    
    if cand_high_idx < cand_low_idx:
        # Price went up first then down — start looking for MAX
        direction = 1
        cand_high_idx, cand_high_val = 0, high[0]
        cand_low_idx, cand_low_val = 0, low[0]
    else:
        # Price went down first — start looking for MIN
        direction = -1
        cand_high_idx, cand_high_val = 0, high[0]
        cand_low_idx, cand_low_val = 0, low[0]

    for i in range(1, n):
        if direction == 1:  # Trending up — looking for MAX
            # Update candidate MAX if new high
            if high[i] > cand_high_val:
                cand_high_idx, cand_high_val = i, high[i]

            # Check confirmation: close drops enough from candidate MAX
            if close[i] < cand_high_val * (1 - min_pct):
                # Confirm MAX at cand_high_idx
                pts.append((cand_high_idx, 'MAX', cand_high_val))
                # Switch direction — start looking for MIN from current bar
                direction = -1
                cand_low_idx, cand_low_val = i, low[i]

        elif direction == -1:  # Trending down — looking for MIN
            # Update candidate MIN if new low
            if low[i] < cand_low_val:
                cand_low_idx, cand_low_val = i, low[i]

            # Check confirmation: close rises enough from candidate MIN
            if close[i] > cand_low_val * (1 + min_pct):
                # Confirm MIN at cand_low_idx
                pts.append((cand_low_idx, 'MIN', cand_low_val))
                # Switch direction — start looking for MAX from current bar
                direction = 1
                cand_high_idx, cand_high_val = i, high[i]

    return pts


# ═══════════════════════════════════════════════════════════════
# VARIANT C: Close-only WITHOUT backtrack (isolate backtrack effect)
# ═══════════════════════════════════════════════════════════════
def zigzag_close_no_backtrack(close: np.ndarray, min_pct: float = 0.05):
    """Close-only zigzag WITHOUT argmax/argmin backtrack.
    
    Same as current but after confirming a pivot, the next candidate
    starts at the CURRENT bar (i), not at argmax/argmin of the range.
    """
    n = len(close)
    if n < 2:
        return []

    pts = []
    last_type = 'MIN' if close[0] < close[min(1, n-1)] else 'MAX'
    
    if last_type == 'MIN':
        cand_idx, cand_val = 0, close[0]
    else:
        cand_idx, cand_val = 0, close[0]

    for i in range(1, n):
        if last_type == 'MIN':
            # Update candidate MIN
            if close[i] < cand_val:
                cand_idx, cand_val = i, close[i]
            # Confirm MIN
            elif close[i] > cand_val * (1 + min_pct):
                pts.append((cand_idx, 'MIN', cand_val))
                last_type = 'MAX'
                cand_idx, cand_val = i, close[i]  # Start from current bar
        else:  # MAX
            # Update candidate MAX
            if close[i] > cand_val:
                cand_idx, cand_val = i, close[i]
            # Confirm MAX
            elif close[i] < cand_val * (1 - min_pct):
                pts.append((cand_idx, 'MAX', cand_val))
                last_type = 'MIN'
                cand_idx, cand_val = i, close[i]  # Start from current bar

    return pts


# ═══════════════════════════════════════════════════════════════
# COMPARISON ENGINE
# ═══════════════════════════════════════════════════════════════
def compare_zigzags(pts_a, pts_b, timestamps, label_a="A", label_b="B",
                    proximity_bars=3):
    """Compare two zigzag point sets using vectorized numpy ops."""
    if not pts_a or not pts_b:
        return {'matched': 0, 'only_a': len(pts_a), 'only_b': len(pts_b),
                'total_a': len(pts_a), 'total_b': len(pts_b),
                'avg_dist': float('nan'), 'examples': []}

    # Extract arrays
    idx_a = np.array([p[0] for p in pts_a])
    tp_a = np.array([p[1] for p in pts_a])
    val_a = np.array([p[2] for p in pts_a])

    idx_b = np.array([p[0] for p in pts_b])
    tp_b = np.array([p[1] for p in pts_b])
    val_b = np.array([p[2] for p in pts_b])

    matched = 0
    only_a = 0
    distances = []
    examples = []

    for tp in ['MIN', 'MAX']:
        mask_a = tp_a == tp
        mask_b = tp_b == tp
        ia = idx_a[mask_a]
        va = val_a[mask_a]
        ib = idx_b[mask_b]
        vb = val_b[mask_b]

        if len(ia) == 0:
            continue
        if len(ib) == 0:
            only_a += len(ia)
            continue

        # For each point in A, find nearest in B (vectorized)
        for j in range(len(ia)):
            diffs = np.abs(ib - ia[j])
            closest = np.argmin(diffs)
            dist = diffs[closest]

            if dist <= proximity_bars:
                matched += 1
                distances.append(int(dist))
            else:
                only_a += 1
                if len(examples) < 10 and ia[j] < len(timestamps):
                    examples.append({
                        'date_a': pd.Timestamp(timestamps[ia[j]]).strftime('%Y-%m-%d'),
                        'type': tp,
                        'price_a': float(va[j]),
                        'nearest_b_dist': int(dist),
                        'nearest_b_price': float(vb[closest]),
                    })

    # Points in B not matched to A (same logic reversed)
    only_b = 0
    for tp in ['MIN', 'MAX']:
        mask_a = tp_a == tp
        mask_b = tp_b == tp
        ia = idx_a[mask_a]
        ib = idx_b[mask_b]

        if len(ib) == 0:
            continue
        if len(ia) == 0:
            only_b += len(ib)
            continue

        for j in range(len(ib)):
            dist = np.min(np.abs(ia - ib[j]))
            if dist > proximity_bars:
                only_b += 1

    return {
        'total_a': len(pts_a),
        'total_b': len(pts_b),
        'matched': matched,
        'only_a': only_a,
        'only_b': only_b,
        'avg_dist': np.mean(distances) if distances else float('nan'),
        'median_dist': np.median(distances) if distances else float('nan'),
        'examples': examples,
    }


def main():
    print("=" * 90)
    print("  ZIGZAG ALGORITHM AUDIT — Canonical vs Current")
    print("  A: Current (close + backtrack)")
    print("  B: Canonical (high/low, no backtrack)")
    print("  C: Close-only, no backtrack (isolates backtrack effect)")
    print("=" * 90)

    store = TimescaleDataStore()
    t0 = time.time()

    # Collect results
    all_results = {pct: [] for pct in SWING_PCTS}

    for tk in TICKERS:
        ohlcv = store.load_bars(tk, "1d")
        if ohlcv is None or len(ohlcv) < 100:
            continue

        high = ohlcv['high'].values.astype(float)
        low = ohlcv['low'].values.astype(float)
        close = ohlcv['close'].values.astype(float)
        timestamps = ohlcv.index.values

        for pct in SWING_PCTS:
            pts_a = zigzag_current(close, pct)
            pts_b = zigzag_canonical(high, low, close, pct)
            pts_c = zigzag_close_no_backtrack(close, pct)

            cmp_ab = compare_zigzags(pts_a, pts_b, timestamps, "Current", "Canonical")
            cmp_ac = compare_zigzags(pts_a, pts_c, timestamps, "Current", "NoBacktrack")
            cmp_bc = compare_zigzags(pts_b, pts_c, timestamps, "Canonical", "NoBacktrack")

            all_results[pct].append({
                'ticker': tk,
                'n_bars': len(close),
                'n_a': len(pts_a),
                'n_b': len(pts_b),
                'n_c': len(pts_c),
                'ab_matched': cmp_ab['matched'],
                'ab_only_a': cmp_ab['only_a'],
                'ab_only_b': cmp_ab['only_b'],
                'ab_avg_dist': cmp_ab['avg_dist'],
                'ac_matched': cmp_ac['matched'],
                'ac_only_a': cmp_ac['only_a'],
                'ac_only_c': cmp_ac['only_b'],
                'ac_avg_dist': cmp_ac['avg_dist'],
                'examples_ab': cmp_ab['examples'],
            })

    store.close()

    # ── Report ──
    for pct in SWING_PCTS:
        pct_int = int(pct * 100)
        print(f"\n{'=' * 90}")
        print(f"  ZIGZAG {pct_int}% — COMPARISON")
        print(f"{'=' * 90}")

        results = all_results[pct]
        if not results:
            print("  No results")
            continue

        # Summary table
        print(f"\n  {'Ticker':<6s} {'Bars':>6s} │ {'A(cur)':>6s} {'B(can)':>6s} {'C(noBT)':>7s} │ "
              f"{'A↔B match':>9s} {'A only':>6s} {'B only':>6s} {'μ dist':>6s} │ "
              f"{'A↔C match':>9s} {'A only':>6s} {'C only':>6s} {'μ dist':>6s}")
        print("  " + "─" * 105)

        tot_a = tot_b = tot_c = 0
        tot_ab_match = tot_ab_a = tot_ab_b = 0
        tot_ac_match = tot_ac_a = tot_ac_c = 0
        ab_dists = []
        ac_dists = []

        for r in results:
            tot_a += r['n_a']; tot_b += r['n_b']; tot_c += r['n_c']
            tot_ab_match += r['ab_matched']; tot_ab_a += r['ab_only_a']; tot_ab_b += r['ab_only_b']
            tot_ac_match += r['ac_matched']; tot_ac_a += r['ac_only_a']; tot_ac_c += r['ac_only_c']
            if not np.isnan(r['ab_avg_dist']):
                ab_dists.append(r['ab_avg_dist'])
            if not np.isnan(r['ac_avg_dist']):
                ac_dists.append(r['ac_avg_dist'])

            ab_d = f"{r['ab_avg_dist']:.1f}" if not np.isnan(r['ab_avg_dist']) else "N/A"
            ac_d = f"{r['ac_avg_dist']:.1f}" if not np.isnan(r['ac_avg_dist']) else "N/A"

            print(f"  {r['ticker']:<6s} {r['n_bars']:>6d} │ {r['n_a']:>6d} {r['n_b']:>6d} {r['n_c']:>7d} │ "
                  f"{r['ab_matched']:>9d} {r['ab_only_a']:>6d} {r['ab_only_b']:>6d} {ab_d:>6s} │ "
                  f"{r['ac_matched']:>9d} {r['ac_only_a']:>6d} {r['ac_only_c']:>6d} {ac_d:>6s}")

        print("  " + "─" * 105)
        ab_d_tot = f"{np.mean(ab_dists):.1f}" if ab_dists else "N/A"
        ac_d_tot = f"{np.mean(ac_dists):.1f}" if ac_dists else "N/A"
        print(f"  {'TOTAL':<6s} {'':>6s} │ {tot_a:>6d} {tot_b:>6d} {tot_c:>7d} │ "
              f"{tot_ab_match:>9d} {tot_ab_a:>6d} {tot_ab_b:>6d} {ab_d_tot:>6s} │ "
              f"{tot_ac_match:>9d} {tot_ac_a:>6d} {tot_ac_c:>6d} {ac_d_tot:>6s}")

        # Match rates
        if tot_a > 0:
            ab_rate = tot_ab_match / tot_a * 100
            ac_rate = tot_ac_match / tot_a * 100
            print(f"\n  A↔B concordance: {ab_rate:.1f}% of Current points match Canonical (±3 bars)")
            print(f"  A↔C concordance: {ac_rate:.1f}% of Current points match NoBacktrack (±3 bars)")

        # Divergence examples (first ticker with examples)
        for r in results:
            if r['examples_ab']:
                print(f"\n  ── Divergence Examples ({r['ticker']}, A vs B) ──")
                for ex in r['examples_ab'][:5]:
                    print(f"    {ex['date_a']} {ex['type']}: "
                          f"Current price={ex['price_a']:.2f}, "
                          f"nearest Canonical is {ex['nearest_b_dist']} bars away "
                          f"(price={ex['nearest_b_price']:.2f})")
                break

    # ── VERDICT ──
    print(f"\n{'=' * 90}")
    print(f"  VERDICT")
    print(f"{'=' * 90}")

    # Check 5% specifically (our main training scale)
    r5 = all_results[0.05]
    if r5:
        tot_a = sum(r['n_a'] for r in r5)
        tot_b = sum(r['n_b'] for r in r5)
        tot_match = sum(r['ab_matched'] for r in r5)
        rate = tot_match / max(tot_a, 1) * 100

        print(f"  ZigZag 5% (training scale):")
        print(f"    Current:   {tot_a} points")
        print(f"    Canonical: {tot_b} points")
        print(f"    Match rate: {rate:.1f}%")

        if rate > 90:
            print(f"    → ✅ High concordance — implementations are mostly equivalent")
        elif rate > 70:
            print(f"    → ⚠️ Moderate divergence — {100-rate:.0f}% of points differ")
            print(f"      The training ground truth has meaningful differences")
        else:
            print(f"    → 🔴 SIGNIFICANT divergence — {100-rate:.0f}% of points differ")
            print(f"      The training ground truth may be substantially wrong")

    elapsed = time.time() - t0
    print(f"\n  Time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
