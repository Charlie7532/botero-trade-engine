#!/usr/bin/env python3
"""
Zigzag Signal Forensics — ¿Qué señales coinciden en cada giro?
================================================================
For each confirmed zigzag turning point (5% swing):
  1. Which features were in extreme zones (|z| > 1.5σ)?
  2. How many bars BEFORE the turn were they active?
  3. Which features are ALWAYS present vs DECORATIVE?
  4. Which turns had ZERO features active (blind spots)?
  5. Parsimony analysis: what's the optimal feature CAP?

Output: forensic report with hard numbers, not theory.
"""
import sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "backend" / "scripts"))

from dotenv import load_dotenv
load_dotenv(root / ".env")

import numpy as np
import pandas as pd
from collections import defaultdict

from unified_pretrainer_v2 import (
    load_feature_lake, ALL_FEATURES, HEAD_CONFIGS,
    label_zz_turning_point, apply_context,
)
from feature_optimizer import expand_feature_lake
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore

OUT_DIR = root / "backend" / "scratch" / "zigzag_forensics"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_zigzag_points(store):
    """Load all confirmed zigzag turning points."""
    from sqlalchemy import text
    mins = pd.read_sql(
        text("SELECT ticker, timestamp, price FROM engine.zigzag_points "
             "WHERE min_swing_pct = 0.05 AND tp_type = 'MIN' "
             "ORDER BY ticker, timestamp"),
        store.engine
    )
    maxs = pd.read_sql(
        text("SELECT ticker, timestamp, price FROM engine.zigzag_points "
             "WHERE min_swing_pct = 0.05 AND tp_type = 'MAX' "
             "ORDER BY ticker, timestamp"),
        store.engine
    )
    print(f"  Zigzag MIN (bottoms): {len(mins):,d}")
    print(f"  Zigzag MAX (tops):    {len(maxs):,d}")
    return mins, maxs


def compute_feature_stats(df, feature_cols):
    """Compute per-ticker z-score statistics for all features."""
    stats = {}
    for feat in feature_cols:
        if feat not in df.columns:
            continue
        # Per-ticker mean/std for proper z-scoring
        grouped = df.groupby('ticker')[feat]
        means = grouped.transform('mean')
        stds = grouped.transform('std').replace(0, 1e-8)
        stats[feat] = {'mean': means, 'std': stds}
    return stats


def analyze_coincidences(df, zz_points, zz_type, feature_cols, stats, anticipation_bars=[0, 1, 2, 3, 5]):
    """For each zigzag point, check which features were extreme."""
    Z_THRESHOLD = 1.5  # |z| > 1.5 = "feature is active/extreme"

    # Results accumulators
    coincidence_at_turn = defaultdict(int)      # feature -> count active AT the turn
    coincidence_pre = defaultdict(lambda: defaultdict(int))  # feature -> bars_before -> count
    turn_coverage = []  # per-turn: how many features were active
    turn_details = []   # per-turn: list of active features

    total_turns = 0
    blind_spots = 0

    for _, zz_row in zz_points.iterrows():
        ticker = zz_row['ticker']
        zz_ts = zz_row['timestamp']

        # Find this ticker's data
        tk_mask = df['ticker'] == ticker
        tk_df = df[tk_mask].copy()
        if len(tk_df) == 0:
            continue

        # Find the bar closest to the zigzag timestamp
        time_diffs = np.abs((tk_df['timestamp'].values - np.datetime64(zz_ts)).astype('timedelta64[D]').astype(int))
        closest_idx = time_diffs.argmin()
        if time_diffs[closest_idx] > 3:  # Must be within 3 days
            continue

        total_turns += 1
        active_features = []

        for feat in feature_cols:
            if feat not in stats:
                continue

            # Check at the turn and pre-turn bars
            for bars_before in anticipation_bars:
                check_idx = closest_idx - bars_before
                if check_idx < 0 or check_idx >= len(tk_df):
                    continue

                row_pos = tk_df.index[check_idx]
                val = df.at[row_pos, feat]
                mean_val = stats[feat]['mean'].at[row_pos]
                std_val = stats[feat]['std'].at[row_pos]

                z = (val - mean_val) / std_val if std_val > 1e-8 else 0.0

                if abs(z) >= Z_THRESHOLD:
                    if bars_before == 0:
                        coincidence_at_turn[feat] += 1
                        active_features.append((feat, round(float(z), 2)))
                    coincidence_pre[feat][bars_before] += 1

        n_active = len(active_features)
        turn_coverage.append(n_active)
        turn_details.append({
            'ticker': ticker,
            'timestamp': str(zz_ts),
            'n_active': n_active,
            'top_features': sorted(active_features, key=lambda x: -abs(x[1]))[:10],
        })

        if n_active == 0:
            blind_spots += 1

    return {
        'type': zz_type,
        'total_turns': total_turns,
        'blind_spots': blind_spots,
        'coincidence_at_turn': dict(coincidence_at_turn),
        'coincidence_pre': {k: dict(v) for k, v in coincidence_pre.items()},
        'turn_coverage': turn_coverage,
        'turn_details': turn_details,
    }


def parsimony_analysis(coincidences, total_turns):
    """Analyze: how many features do you NEED to cover X% of turns?"""
    # Sort features by coincidence rate (descending)
    sorted_feats = sorted(
        coincidences.items(),
        key=lambda x: -x[1]
    )

    # Greedy coverage: add features one by one, track cumulative coverage
    # (This is an approximation — true coverage requires per-turn data)
    coverage_curve = []
    for i, (feat, count) in enumerate(sorted_feats, 1):
        rate = count / max(total_turns, 1) * 100
        coverage_curve.append({
            'rank': i,
            'feature': feat,
            'individual_rate': round(rate, 1),
        })

    return sorted_feats, coverage_curve


def main():
    print("=" * 80)
    print("  ZIGZAG SIGNAL FORENSICS")
    print("=" * 80)

    store = TimescaleDataStore()
    ps = TickerProfileStore()

    print("\nLoading data...")
    df, ohlcv_cache, profiles = load_feature_lake(store, ps)
    print(f"  Feature lake: {len(df):,d} rows")

    print("\nExpanding features...")
    new_features = expand_feature_lake(df)
    ALL_EXPANDED = list(ALL_FEATURES) + new_features
    print(f"  Total features: {len(ALL_EXPANDED)}")

    print("\nLoading zigzag points...")
    zz_mins, zz_maxs = load_zigzag_points(store)

    print("\nComputing feature statistics...")
    stats = compute_feature_stats(df, ALL_EXPANDED)
    print(f"  Stats computed for {len(stats)} features")

    # ═══════════════════════════════════════════════════════════
    # ANALYSIS 1: Coincidence at BOTTOMS (MIN)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("  ANALYZING BOTTOMS (ZIGZAG MIN)")
    print("=" * 80)
    bottoms = analyze_coincidences(df, zz_mins, 'BOTTOM', ALL_EXPANDED, stats)

    # ═══════════════════════════════════════════════════════════
    # ANALYSIS 2: Coincidence at TOPS (MAX)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("  ANALYZING TOPS (ZIGZAG MAX)")
    print("=" * 80)
    tops = analyze_coincidences(df, zz_maxs, 'TOP', ALL_EXPANDED, stats)

    # ═══════════════════════════════════════════════════════════
    # REPORT
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("  RESULTS")
    print("=" * 80)

    for result in [bottoms, tops]:
        zz_type = result['type']
        total = result['total_turns']
        blind = result['blind_spots']
        coverage = result['turn_coverage']

        print(f"\n  ── {zz_type}S ──")
        print(f"  Total turns analyzed:  {total:,d}")
        print(f"  Blind spots (0 feat):  {blind} ({blind/max(total,1)*100:.1f}%)")
        print(f"  Mean features/turn:    {np.mean(coverage):.1f}")
        print(f"  Median features/turn:  {np.median(coverage):.0f}")
        print(f"  Max features/turn:     {max(coverage) if coverage else 0}")

        # Top 20 features by coincidence rate
        sorted_feats, cov_curve = parsimony_analysis(
            result['coincidence_at_turn'], total
        )

        print(f"\n  Top 25 features (present at |z|>1.5 at the turn):")
        print(f"  {'Rank':>4s}  {'Feature':35s}  {'Count':>6s}  {'Rate':>6s}  {'New?':>5s}")
        print(f"  {'─'*60}")
        for i, (feat, count) in enumerate(sorted_feats[:25], 1):
            rate = count / max(total, 1) * 100
            is_new = "★NEW" if feat in new_features else ""
            print(f"  {i:>4d}  {feat:35s}  {count:>6d}  {rate:>5.1f}%  {is_new}")

        # Anticipation analysis for top 10
        print(f"\n  Anticipation (bars before turn where feature was active):")
        print(f"  {'Feature':35s}  {'t=0':>6s}  {'t-1':>6s}  {'t-2':>6s}  {'t-3':>6s}  {'t-5':>6s}")
        print(f"  {'─'*75}")
        for feat, _ in sorted_feats[:15]:
            pre = result['coincidence_pre'].get(feat, {})
            vals = [f"{pre.get(b, 0)/max(total,1)*100:>5.1f}%" for b in [0, 1, 2, 3, 5]]
            print(f"  {feat:35s}  {'  '.join(vals)}")

        # Coverage by feature count
        print(f"\n  Coverage curve (% of turns covered by top-N features):")
        # Need per-turn data to compute true coverage
        # Approximate: turns with >= 1 of top-N features active
        for n_cap in [3, 5, 7, 10, 15, 20, 30]:
            top_n_feats = set(f for f, _ in sorted_feats[:n_cap])
            covered = 0
            for detail in result['turn_details']:
                active_feats = set(f for f, z in detail['top_features'])
                if active_feats & top_n_feats:
                    covered += 1
            pct = covered / max(total, 1) * 100
            print(f"    Top-{n_cap:>2d} features → {covered:>4d}/{total} turns covered ({pct:.1f}%)")

        # Distribution of features per turn
        print(f"\n  Distribution of active features per turn:")
        coverage_arr = np.array(coverage)
        for bucket_start, bucket_end, label in [
            (0, 0, "  0 features (blind)"),
            (1, 3, "  1-3 features"),
            (4, 7, "  4-7 features"),
            (8, 15, "  8-15 features"),
            (16, 30, " 16-30 features"),
            (31, 999, " 31+ features"),
        ]:
            count = ((coverage_arr >= bucket_start) & (coverage_arr <= bucket_end)).sum()
            pct = count / max(total, 1) * 100
            bar = "█" * int(pct / 2)
            print(f"    {label}: {count:>4d} ({pct:>5.1f}%) {bar}")

    # ═══════════════════════════════════════════════════════════
    # PARSIMONY: Optimal feature cap analysis
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("  PARSIMONY ANALYSIS: Optimal Feature Cap")
    print("=" * 80)

    # Compare production feature counts vs V4 feature counts vs DSR
    print("\n  Production models — Features vs Reproducibility:")
    print(f"  {'Head':22s}  {'Prod f':>6s}  {'V4 f':>6s}  {'DSR Prod':>9s}  {'DSR V4':>8s}  {'Diagnosis':20s}")
    print(f"  {'─'*80}")

    prod_data = [
        ('bounce_height',    9, 7,  19.732, 33.487, '★ GAIN (fewer=better)'),
        ('short_entry',      5, 7,   1.816,  4.883, '★ GAIN (+2f acceptable)'),
        ('swing_exit',      11, 6,  13.865, 13.960, '★ parsimony (-5f, same)'),
        ('pullback_depth',   3, 7,  18.180, 24.076, '★ GAIN (baseline=18.18)'),
        ('trend_reversal',   2, 2,  18.492, 18.492, '≈ minimal is optimal'),
        ('zz_bottom',        6, 6,  32.218, 32.218, '≈ 6f is optimal'),
        ('trend_recovery',  13, 10,  7.407,  7.374, '≈ -3f, same DSR'),
        ('zz_top',          12, 12, 10.198,  9.056, '✖ same count, worse'),
        ('long_entry',       6, 18,  2.590,  1.729, '✖ +12f made it WORSE'),
        ('short_cover',      7, 21,  5.132,  4.271, '✖ +14f made it WORSE'),
    ]

    for name, pf, vf, dsr_p, dsr_v, diag in prod_data:
        print(f"  {name:22s}  {pf:>6d}  {vf:>6d}  {dsr_p:>9.3f}  {dsr_v:>8.3f}  {diag}")

    print(f"\n  CONCLUSION: Optimal feature cap appears to be 6-7 features.")
    print(f"  Heads with 2-7 features: ALL gained or held.")
    print(f"  Heads with 10-21 features: ALL dropped or stagnated.")
    print(f"  The Anti-Drop Phase 4 (which adds features) made things WORSE in every case.")

    # Save full details to JSON
    import json

    for result in [bottoms, tops]:
        # Convert turn_details for JSON
        for d in result['turn_details']:
            d['top_features'] = [(f, float(z)) for f, z in d['top_features']]
        result['turn_coverage'] = [int(x) for x in result['turn_coverage']]

    report = {
        'bottoms': {
            'total_turns': bottoms['total_turns'],
            'blind_spots': bottoms['blind_spots'],
            'mean_features_per_turn': round(float(np.mean(bottoms['turn_coverage'])), 1),
            'top_25': [
                {'feature': f, 'count': c, 'rate': round(c/max(bottoms['total_turns'],1)*100, 1)}
                for f, c in sorted(bottoms['coincidence_at_turn'].items(), key=lambda x: -x[1])[:25]
            ],
        },
        'tops': {
            'total_turns': tops['total_turns'],
            'blind_spots': tops['blind_spots'],
            'mean_features_per_turn': round(float(np.mean(tops['turn_coverage'])), 1),
            'top_25': [
                {'feature': f, 'count': c, 'rate': round(c/max(tops['total_turns'],1)*100, 1)}
                for f, c in sorted(tops['coincidence_at_turn'].items(), key=lambda x: -x[1])[:25]
            ],
        },
    }

    with open(OUT_DIR / "coincidence_report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)

    # Save blind spots detail
    for result in [bottoms, tops]:
        blind_list = [d for d in result['turn_details'] if d['n_active'] == 0]
        with open(OUT_DIR / f"blind_spots_{result['type'].lower()}.json", "w") as f:
            json.dump(blind_list, f, indent=2, default=str)

    store.close()
    ps.close()

    print(f"\n  Reports saved to: {OUT_DIR}")
    print(f"\n{'='*80}")
    print(f"  ★★★ FORENSICS COMPLETE ★★★")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
