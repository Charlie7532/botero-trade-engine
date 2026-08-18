#!/usr/bin/env python3
"""
Zigzag Quality Forensics — Timing, Drift, Opportunity & Pareto Selection
==========================================================================
For each confirmed zigzag turning point:
  1. TIMING: How many bars early/late was the signal vs the actual turn?
  2. DRIFT: How much drawdown occurred AFTER the signal before the move started?
  3. OPPORTUNITY: What was the zigzag leg size (min/max/avg)?
  4. HIGHER HIGHS / HIGHER LOWS: Classify major vs minor turns
  5. PARETO: Find the minimum set of orthogonal features that covers 80%+ of turns

Uses multiple zigzag thresholds: 5% (standard), 10% (swing), 15% (major)
"""
import sys, warnings, json
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
from sqlalchemy import text

from unified_pretrainer_v2 import load_feature_lake, ALL_FEATURES
from feature_optimizer import expand_feature_lake
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore

OUT_DIR = root / "backend" / "scratch" / "zigzag_forensics"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_zigzag_with_prices(store, min_swing_pct=0.05):
    """Load zigzag turning points with prices, ordered for leg analysis."""
    zz = pd.read_sql(
        text("SELECT ticker, timestamp, tp_type, price "
             "FROM engine.zigzag_points "
             "WHERE min_swing_pct = :pct "
             "ORDER BY ticker, timestamp"),
        store.engine, params={'pct': min_swing_pct}
    )
    print(f"  Zigzag ({min_swing_pct:.0%}): {len(zz):,d} points "
          f"({(zz['tp_type']=='MIN').sum()} MIN, {(zz['tp_type']=='MAX').sum()} MAX)")
    return zz


def compute_legs_and_classify(zz_df):
    """For each turning point, compute:
    - Previous leg (drawdown to this point or rally to this point)
    - Next leg (opportunity from this point)
    - Classification: Higher High, Lower High, Higher Low, Lower Low
    """
    results = []

    for ticker in zz_df['ticker'].unique():
        tk = zz_df[zz_df['ticker'] == ticker].sort_values('timestamp').reset_index(drop=True)
        if len(tk) < 3:
            continue

        # Track previous highs and lows for HH/HL/LH/LL classification
        prev_max_price = None
        prev_min_price = None

        for i in range(1, len(tk) - 1):
            row = tk.iloc[i]
            prev = tk.iloc[i - 1]
            next_ = tk.iloc[i + 1]

            price = float(row['price'])
            prev_price = float(prev['price'])
            next_price = float(next_['price'])
            tp = row['tp_type']

            # Previous leg (what happened BEFORE this turn)
            prev_leg_pct = (price / prev_price - 1) * 100

            # Next leg (OPPORTUNITY from this turn)
            next_leg_pct = (next_price / price - 1) * 100

            # Duration in bars (approximate using calendar days / 1.4 for trading days)
            prev_duration = (row['timestamp'] - prev['timestamp']).days
            next_duration = (next_['timestamp'] - row['timestamp']).days

            # Classification
            if tp == 'MIN':
                if prev_min_price is not None:
                    classification = 'HIGHER_LOW' if price > prev_min_price else 'LOWER_LOW'
                else:
                    classification = 'FIRST_LOW'
                prev_min_price = price
            else:  # MAX
                if prev_max_price is not None:
                    classification = 'HIGHER_HIGH' if price > prev_max_price else 'LOWER_HIGH'
                else:
                    classification = 'FIRST_HIGH'
                prev_max_price = price

            results.append({
                'ticker': ticker,
                'timestamp': row['timestamp'],
                'tp_type': tp,
                'price': price,
                'prev_leg_pct': round(prev_leg_pct, 2),
                'next_leg_pct': round(next_leg_pct, 2),
                'prev_duration_days': prev_duration,
                'next_duration_days': next_duration,
                'classification': classification,
            })

    return pd.DataFrame(results)


def analyze_signal_timing(df, zz_legs, feature_cols, stats, zz_type='MIN'):
    """For each zigzag turn, measure signal timing and drift quality."""
    Z_THRESHOLD = 1.5
    WINDOW = 10  # Look 10 bars before/after the turn

    legs = zz_legs[zz_legs['tp_type'] == zz_type].copy()
    print(f"\n  Analyzing {len(legs)} {zz_type} turns...")

    # Per-feature timing stats
    feature_timing = defaultdict(lambda: {
        'advances': [], 'delays': [], 'at_turn': 0, 'total_active': 0,
        'drift_after_signal': [], 'opportunity_when_active': [],
    })

    for _, leg in legs.iterrows():
        ticker = leg['ticker']
        zz_ts = leg['timestamp']
        opp_pct = abs(leg['next_leg_pct'])  # Opportunity size

        tk_mask = df['ticker'] == ticker
        tk_df = df[tk_mask]
        if len(tk_df) == 0:
            continue

        # Find the bar at the zigzag turn
        time_diffs = (tk_df['timestamp'].values - np.datetime64(zz_ts)).astype('timedelta64[D]').astype(int)
        abs_diffs = np.abs(time_diffs)
        closest_idx_pos = abs_diffs.argmin()
        if abs_diffs[closest_idx_pos] > 5:
            continue

        # For each feature, find the FIRST bar where it was active within [-WINDOW, +WINDOW]
        for feat in feature_cols:
            if feat not in stats:
                continue

            first_active_bar = None
            for offset in range(-WINDOW, WINDOW + 1):
                check_pos = closest_idx_pos + offset
                if check_pos < 0 or check_pos >= len(tk_df):
                    continue

                row_idx = tk_df.index[check_pos]
                val = df.at[row_idx, feat]
                mean_val = stats[feat]['mean'].at[row_idx]
                std_val = stats[feat]['std'].at[row_idx]
                z = (val - mean_val) / std_val if std_val > 1e-8 else 0.0

                if abs(z) >= Z_THRESHOLD:
                    first_active_bar = offset
                    break

            if first_active_bar is not None:
                ft = feature_timing[feat]
                ft['total_active'] += 1

                if first_active_bar < 0:
                    ft['advances'].append(-first_active_bar)  # Positive = bars early
                elif first_active_bar == 0:
                    ft['at_turn'] += 1
                else:
                    ft['delays'].append(first_active_bar)

                ft['opportunity_when_active'].append(opp_pct)

                # Drift: price movement from signal bar to actual turn
                if first_active_bar < 0:
                    signal_idx = tk_df.index[closest_idx_pos + first_active_bar]
                    turn_idx = tk_df.index[closest_idx_pos]
                    signal_price = df.at[signal_idx, 'price']
                    turn_price = df.at[turn_idx, 'price']
                    if signal_price > 0:
                        drift = (turn_price / signal_price - 1) * 100
                        ft['drift_after_signal'].append(drift)

    return feature_timing


def compute_feature_stats_fast(df, feature_cols):
    """Compute per-ticker z-score stats."""
    stats = {}
    for feat in feature_cols:
        if feat not in df.columns:
            continue
        grouped = df.groupby('ticker')[feat]
        means = grouped.transform('mean')
        stds = grouped.transform('std').replace(0, 1e-8)
        stats[feat] = {'mean': means, 'std': stds}
    return stats


def pareto_selection(feature_timing, zz_legs, zz_type, df, feature_cols, stats, max_features=7):
    """Greedy Pareto selection: pick features that cover the MOST UNCOVERED turns."""
    Z_THRESHOLD = 1.5
    legs = zz_legs[zz_legs['tp_type'] == zz_type]

    # Build per-turn active feature sets
    turn_features = []
    for _, leg in legs.iterrows():
        ticker = leg['ticker']
        zz_ts = leg['timestamp']

        tk_mask = df['ticker'] == ticker
        tk_df = df[tk_mask]
        if len(tk_df) == 0:
            turn_features.append(set())
            continue

        time_diffs = np.abs((tk_df['timestamp'].values - np.datetime64(zz_ts)).astype('timedelta64[D]').astype(int))
        closest = time_diffs.argmin()
        if time_diffs[closest] > 5:
            turn_features.append(set())
            continue

        active = set()
        row_idx = tk_df.index[closest]
        for feat in feature_cols:
            if feat not in stats:
                continue
            val = df.at[row_idx, feat]
            mean_val = stats[feat]['mean'].at[row_idx]
            std_val = stats[feat]['std'].at[row_idx]
            z = (val - mean_val) / std_val if std_val > 1e-8 else 0.0
            if abs(z) >= Z_THRESHOLD:
                active.add(feat)
        turn_features.append(active)

    # Greedy coverage
    total_turns = len(turn_features)
    uncovered = set(range(total_turns))
    selected = []
    coverage_log = []

    # Pre-compute per-feature coverage
    feat_coverage = {}
    for feat in feature_cols:
        if feat not in stats:
            continue
        covered_turns = {i for i, tf in enumerate(turn_features) if feat in tf}
        feat_coverage[feat] = covered_turns

    for step in range(max_features):
        best_feat = None
        best_new_coverage = 0

        for feat, cov in feat_coverage.items():
            if feat in [s[0] for s in selected]:
                continue
            new_cov = len(cov & uncovered)
            if new_cov > best_new_coverage:
                best_new_coverage = new_cov
                best_feat = feat

        if best_feat is None or best_new_coverage == 0:
            break

        uncovered -= feat_coverage[best_feat]
        total_covered = total_turns - len(uncovered)
        selected.append((best_feat, best_new_coverage, total_covered / total_turns * 100))

        coverage_log.append({
            'step': step + 1,
            'feature': best_feat,
            'new_turns_covered': best_new_coverage,
            'cumulative_coverage_pct': round(total_covered / total_turns * 100, 1),
        })

    return selected, coverage_log


def main():
    print("=" * 80)
    print("  ZIGZAG QUALITY FORENSICS — Timing, Drift, Opportunity & Pareto")
    print("=" * 80)

    store = TimescaleDataStore()
    ps = TickerProfileStore()

    print("\nLoading data...")
    df, ohlcv_cache, profiles = load_feature_lake(store, ps)
    new_features = expand_feature_lake(df)
    ALL_EXPANDED = list(ALL_FEATURES) + new_features
    # Use top-50 features from previous forensics (no need to test all 158)
    TOP_FEATURES = [
        # Top bottoms
        'below_all_vwaps_int', 'bullish_score', 'sigma_max_tf', 'vwap_sigma_current',
        'vwap_sigma_wave', 'rsi_value', 'wave_accel', 'd2_conj_wave_tide',
        'sigma_current', 'sigma_min_tf', 'd2_vwap_sigma_tide', 'vol_price_regime',
        'sigma_tide', 'vwap_sigma_tide', 'atr_ratio', 'd2_sigma_tide',
        'd_wave_accel', 'd2_tide_accel', 'current_accel', 'd2_current_slope',
        'overnight_gap', 'geo_state_norm', 'total_displacement', 'sigma_low_current',
        'sigma_high_current',
        # Top tops (non-overlapping)
        'rsi_bearish_div', 'rsi_trap_zone', 'tsi_wave', 'regime_encoded',
        'atr_14', 'slope_phase_tw', 'residual_std_wave', 'vol_slope_conf',
        'compression_ratio', 'rsi_sigma_interact', 'residual_std_current', 'tsi_current',
        # Production features (to validate)
        'complacency_index', 'tension_tide', 'sigma_range_tide', 'volume_trend',
        'tide_slope_sq', 'sigma_ratio_tw', 'vol_return_interaction', 'vol_adj_delta',
        'compr_at_extreme', 'slope_ratio_tw', 'kalman_slope_conf',
    ]
    # Deduplicate
    TOP_FEATURES = list(dict.fromkeys(TOP_FEATURES))
    print(f"  Analyzing {len(TOP_FEATURES)} features")

    stats = compute_feature_stats_fast(df, TOP_FEATURES)

    # ═══════════════════════════════════════════════════════════
    # LOAD ZIGZAG AT MULTIPLE THRESHOLDS
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("  ZIGZAG LEGS & CLASSIFICATION")
    print("=" * 80)

    zz_5 = load_zigzag_with_prices(store, 0.05)

    # Check if larger thresholds exist
    for pct in [0.10, 0.15]:
        count = pd.read_sql(
            text("SELECT COUNT(*) as n FROM engine.zigzag_points WHERE min_swing_pct = :pct"),
            store.engine, params={'pct': pct}
        ).iloc[0]['n']
        print(f"  Zigzag {pct:.0%}: {count} points {'(available)' if count > 0 else '(not computed)'}")

    # Compute legs and classification for 5%
    legs_5 = compute_legs_and_classify(zz_5)
    print(f"\n  Legs computed: {len(legs_5)}")

    # ═══════════════════════════════════════════════════════════
    # LEG STATISTICS (Opportunity & Drawdown)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("  LEG STATISTICS — Opportunity & Prior Drawdown")
    print("=" * 80)

    for tp, label in [('MIN', 'BOTTOMS (Opportunity = next rally)'),
                      ('MAX', 'TOPS (Opportunity = next decline)')]:
        subset = legs_5[legs_5['tp_type'] == tp]
        opp = subset['next_leg_pct'].abs()
        prior = subset['prev_leg_pct'].abs()
        dur = subset['next_duration_days']

        print(f"\n  ── {label} ({len(subset)} turns) ──")
        print(f"  OPPORTUNITY (next leg):")
        print(f"    Min:    {opp.min():>6.1f}%")
        print(f"    P25:    {opp.quantile(0.25):>6.1f}%")
        print(f"    Median: {opp.median():>6.1f}%")
        print(f"    Mean:   {opp.mean():>6.1f}%")
        print(f"    P75:    {opp.quantile(0.75):>6.1f}%")
        print(f"    Max:    {opp.max():>6.1f}%")
        print(f"  DURATION (next leg days):")
        print(f"    Min:    {dur.min():>6d}d")
        print(f"    Median: {dur.median():>6.0f}d")
        print(f"    Mean:   {dur.mean():>6.1f}d")
        print(f"    Max:    {dur.max():>6d}d")
        print(f"  PRIOR LEG (drawdown/rally before this turn):")
        print(f"    Min:    {prior.min():>6.1f}%")
        print(f"    Median: {prior.median():>6.1f}%")
        print(f"    Mean:   {prior.mean():>6.1f}%")
        print(f"    Max:    {prior.max():>6.1f}%")

        # Classification breakdown
        print(f"\n  CLASSIFICATION:")
        for cls in ['HIGHER_LOW', 'LOWER_LOW', 'FIRST_LOW', 'HIGHER_HIGH', 'LOWER_HIGH', 'FIRST_HIGH']:
            n = (subset['classification'] == cls).sum()
            if n > 0:
                cls_opp = subset[subset['classification'] == cls]['next_leg_pct'].abs()
                print(f"    {cls:15s}: {n:>4d} ({n/len(subset)*100:>5.1f}%) | Opp median: {cls_opp.median():>5.1f}%")

    # ═══════════════════════════════════════════════════════════
    # SIGNAL TIMING & DRIFT
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("  SIGNAL TIMING & DRIFT ANALYSIS")
    print("=" * 80)

    for tp, label in [('MIN', 'BOTTOMS'), ('MAX', 'TOPS')]:
        timing = analyze_signal_timing(df, legs_5, TOP_FEATURES, stats, zz_type=tp)

        # Sort by total_active
        sorted_timing = sorted(timing.items(), key=lambda x: -x[1]['total_active'])

        print(f"\n  ── {label} — Signal Quality ──")
        print(f"  {'Feature':30s}  {'Active':>6s}  {'Early':>6s}  {'AtTurn':>6s}  {'Late':>6s}  "
              f"{'AvgAdv':>6s}  {'AvgDrift':>8s}  {'AvgOpp':>7s}")
        print(f"  {'─'*100}")

        for feat, t in sorted_timing[:30]:
            total = t['total_active']
            n_adv = len(t['advances'])
            n_at = t['at_turn']
            n_delay = len(t['delays'])
            avg_adv = f"{np.mean(t['advances']):.1f}b" if t['advances'] else "—"
            avg_drift = f"{np.mean(t['drift_after_signal']):+.2f}%" if t['drift_after_signal'] else "—"
            avg_opp = f"{np.mean(t['opportunity_when_active']):.1f}%" if t['opportunity_when_active'] else "—"

            print(f"  {feat:30s}  {total:>6d}  {n_adv:>6d}  {n_at:>6d}  {n_delay:>6d}  "
                  f"{avg_adv:>6s}  {avg_drift:>8s}  {avg_opp:>7s}")

    # ═══════════════════════════════════════════════════════════
    # MAJOR TURNS FORENSICS (Higher Highs / Higher Lows)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("  MAJOR TURNS — Higher Lows & Lower Highs (Trend Continuations)")
    print("=" * 80)

    for cls, tp, label in [
        ('HIGHER_LOW', 'MIN', 'HIGHER LOWS (bullish confirmation — best long entries)'),
        ('LOWER_HIGH', 'MAX', 'LOWER HIGHS (bearish confirmation — best short entries)'),
        ('LOWER_LOW', 'MIN', 'LOWER LOWS (trend acceleration — breakdowns)'),
        ('HIGHER_HIGH', 'MAX', 'HIGHER HIGHS (trend acceleration — breakouts)'),
    ]:
        subset = legs_5[legs_5['classification'] == cls]
        if len(subset) == 0:
            continue

        opp = subset['next_leg_pct'].abs()
        print(f"\n  ── {label} ({len(subset)} turns) ──")
        print(f"    Opportunity: min={opp.min():.1f}% | median={opp.median():.1f}% | "
              f"mean={opp.mean():.1f}% | max={opp.max():.1f}%")

        # Which features are most active at these MAJOR turns?
        major_timing = analyze_signal_timing(df, subset, TOP_FEATURES, stats, zz_type=tp)
        sorted_mt = sorted(major_timing.items(), key=lambda x: -x[1]['total_active'])

        print(f"    Top 10 features at {cls}:")
        for feat, t in sorted_mt[:10]:
            rate = t['total_active'] / max(len(subset), 1) * 100
            avg_adv = f"{np.mean(t['advances']):.1f}b" if t['advances'] else "—"
            avg_drift = f"{np.mean(t['drift_after_signal']):+.2f}%" if t['drift_after_signal'] else "—"
            print(f"      {feat:30s}  {rate:>5.1f}%  adv={avg_adv:>5s}  drift={avg_drift:>7s}")

    # ═══════════════════════════════════════════════════════════
    # PARETO SELECTION — Minimum Orthogonal Set
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("  PARETO SELECTION — Minimum Feature Set for 80% Coverage")
    print("=" * 80)

    for tp, label in [('MIN', 'BOTTOMS'), ('MAX', 'TOPS')]:
        print(f"\n  ── {label} ──")
        selected, cov_log = pareto_selection(
            None, legs_5, tp, df, TOP_FEATURES, stats, max_features=10
        )
        print(f"  {'Step':>4s}  {'Feature':30s}  {'New Turns':>9s}  {'Cumulative':>10s}")
        print(f"  {'─'*60}")
        for s in cov_log:
            print(f"  {s['step']:>4d}  {s['feature']:30s}  {s['new_turns_covered']:>9d}  "
                  f"{s['cumulative_coverage_pct']:>9.1f}%")

    # ═══════════════════════════════════════════════════════════
    # SAVE
    # ═══════════════════════════════════════════════════════════
    legs_5.to_csv(OUT_DIR / "zigzag_legs_classified.csv", index=False)
    print(f"\n  Saved: {OUT_DIR / 'zigzag_legs_classified.csv'}")

    store.close()
    ps.close()
    print(f"\n{'='*80}")
    print(f"  ★★★ QUALITY FORENSICS COMPLETE ★★★")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
