#!/usr/bin/env python3
"""
Breakpoint Forensics — Bar-by-Bar Signal Timing at Zigzag Turns
=================================================================
For each confirmed zigzag turning point:
  1. EXACT bar-by-bar distribution: t=-5, t=-4, ..., t=0, t=+1, t=+2
  2. REGRESSION CONTEXT: What were tide/current/wave slopes at the turn?
     → Entries long with ALL slopes negative = AGAINST TREND = bad
  3. BREAKPOINT ANATOMY: Feature values at t=0, t-1, t-2
  4. WITH-TREND vs AGAINST-TREND separation
  5. Feature × Context matrix: which features fire IN CONTEXT vs OUT OF CONTEXT

The user's insight: we don't need zigzag features — the RC slopes ALREADY
tell direction. A long entry in a bearish channel is fighting the trend,
and 7-bar anticipation + 7% drift is the CONSEQUENCE of that mistake.
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
from collections import defaultdict, Counter
from sqlalchemy import text

from unified_pretrainer_v2 import load_feature_lake, ALL_FEATURES
from feature_optimizer import expand_feature_lake
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore

OUT_DIR = root / "data" / "research" / "quality_swing" / "zigzag_forensics"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# The features that MATTER (from Pareto + production validation)
SIGNAL_FEATURES = [
    'below_all_vwaps_int', 'bullish_score', 'sigma_current', 'tension_tide',
    'rsi_value', 'rsi_bearish_div', 'rsi_trap_zone', 'complacency_index',
    'wave_accel', 'd_wave_accel', 'vol_slope_conf', 'tsi_wave',
    'vol_price_regime', 'atr_ratio', 'compression_ratio',
    'sigma_max_tf', 'sigma_min_tf', 'vwap_sigma_wave',
    'overnight_gap', 'volume_trend', 'd2_tide_accel',
]

# RC CONTEXT features — the THREE REGRESSION LINES
RC_CONTEXT = ['tide_slope', 'current_slope', 'wave_slope',
              'tsi_tide', 'tsi_current', 'tsi_wave',
              'regime_encoded', 'sigma_tide']


def load_zigzag_points(store):
    zz = pd.read_sql(
        text("SELECT ticker, timestamp, tp_type, price "
             "FROM engine.zigzag_points "
             "WHERE min_swing_pct = 0.05 ORDER BY ticker, timestamp"),
        store.engine)
    return zz


def classify_rc_context(row):
    """Classify the regression channel context at a given bar.
    Returns: 'WITH_TREND' or 'AGAINST_TREND' for longs at bottoms.
    """
    tide = row.get('tide_slope', 0)
    current = row.get('current_slope', 0)
    wave = row.get('wave_slope', 0)

    # For BOTTOM (long entry): with-trend = at least tide OR current positive
    # Against-trend = ALL three slopes negative
    all_negative = tide < 0 and current < 0 and wave < 0
    return 'AGAINST_TREND' if all_negative else 'WITH_TREND'


def classify_rc_context_top(row):
    """For TOP (short entry): against-trend = all three positive."""
    tide = row.get('tide_slope', 0)
    current = row.get('current_slope', 0)
    wave = row.get('wave_slope', 0)
    all_positive = tide > 0 and current > 0 and wave > 0
    return 'AGAINST_TREND' if all_positive else 'WITH_TREND'


def main():
    print("=" * 90)
    print("  BREAKPOINT FORENSICS — Bar-by-Bar × Regression Context")
    print("=" * 90)

    store = TimescaleDataStore()
    ps = TickerProfileStore()

    print("\nLoading data...")
    df, ohlcv_cache, profiles = load_feature_lake(store, ps)
    new_features = expand_feature_lake(df)
    ALL_EXPANDED = list(ALL_FEATURES) + new_features

    # Verify signal features exist
    valid_signals = [f for f in SIGNAL_FEATURES if f in df.columns]
    print(f"  Signal features: {len(valid_signals)}/{len(SIGNAL_FEATURES)} available")

    # Compute per-ticker z-score stats
    print("  Computing z-score stats...")
    feat_means = {}
    feat_stds = {}
    for feat in valid_signals:
        grouped = df.groupby('ticker')[feat]
        feat_means[feat] = grouped.transform('mean')
        feat_stds[feat] = grouped.transform('std').replace(0, 1e-8)

    print("\nLoading zigzag points...")
    zz = load_zigzag_points(store)
    print(f"  Total: {len(zz):,d} ({(zz['tp_type']=='MIN').sum()} MIN, {(zz['tp_type']=='MAX').sum()} MAX)")

    # ═══════════════════════════════════════════════════════════
    # BAR-BY-BAR TIMING DISTRIBUTION
    # ═══════════════════════════════════════════════════════════
    Z_THRESHOLD = 1.5
    OFFSETS = list(range(-7, 4))  # t-7 to t+3

    for tp_type, context_fn, entry_label in [
        ('MIN', classify_rc_context, 'LONG ENTRY (Bottoms)'),
        ('MAX', classify_rc_context_top, 'SHORT ENTRY (Tops)'),
    ]:
        print(f"\n{'='*90}")
        print(f"  {entry_label}")
        print(f"{'='*90}")

        zz_tp = zz[zz['tp_type'] == tp_type]

        # Per-feature, per-offset counts
        # Also split by WITH_TREND vs AGAINST_TREND
        timing_all = defaultdict(lambda: Counter())
        timing_with = defaultdict(lambda: Counter())
        timing_against = defaultdict(lambda: Counter())
        total_all = 0
        total_with = 0
        total_against = 0

        # Drift tracking by context
        drift_with = []
        drift_against = []
        opp_with = []
        opp_against = []

        # Breakpoint anatomy: feature values at t=0, t-1, t-2
        anatomy_t0 = defaultdict(list)
        anatomy_t1 = defaultdict(list)
        anatomy_t2 = defaultdict(list)

        # RC state at turn
        rc_at_turn = defaultdict(list)

        for _, zz_row in zz_tp.iterrows():
            ticker = zz_row['ticker']
            zz_ts = zz_row['timestamp']
            zz_price = float(zz_row['price'])

            tk_mask = df['ticker'] == ticker
            tk_df = df[tk_mask]
            if len(tk_df) < 10:
                continue

            # Find closest bar to zigzag timestamp
            time_diffs = (tk_df['timestamp'].values - np.datetime64(zz_ts)).astype('timedelta64[D]').astype(int)
            abs_diffs = np.abs(time_diffs)
            center = abs_diffs.argmin()
            if abs_diffs[center] > 3:
                continue

            total_all += 1

            # Get RC context at the turn
            center_idx = tk_df.index[center]
            rc_row = {col: df.at[center_idx, col] for col in RC_CONTEXT if col in df.columns}
            context = context_fn(rc_row)

            if context == 'WITH_TREND':
                total_with += 1
            else:
                total_against += 1

            # Record RC state
            for col in RC_CONTEXT:
                if col in df.columns:
                    rc_at_turn[col].append((context, float(df.at[center_idx, col])))

            # Next zigzag point for opportunity measurement
            zz_ticker = zz[zz['ticker'] == ticker].sort_values('timestamp')
            zz_idx = zz_ticker[zz_ticker['timestamp'] == zz_ts].index
            if len(zz_idx) > 0:
                pos_in_zz = zz_ticker.index.get_loc(zz_idx[0])
                if pos_in_zz + 1 < len(zz_ticker):
                    next_zz = zz_ticker.iloc[pos_in_zz + 1]
                    opp = abs(float(next_zz['price']) / zz_price - 1) * 100
                    if context == 'WITH_TREND':
                        opp_with.append(opp)
                    else:
                        opp_against.append(opp)

            # For each offset, check each feature
            for offset in OFFSETS:
                check_pos = center + offset
                if check_pos < 0 or check_pos >= len(tk_df):
                    continue
                row_idx = tk_df.index[check_pos]

                for feat in valid_signals:
                    val = df.at[row_idx, feat]
                    mean_v = feat_means[feat].at[row_idx]
                    std_v = feat_stds[feat].at[row_idx]
                    z = (val - mean_v) / std_v if std_v > 1e-8 else 0.0

                    if abs(z) >= Z_THRESHOLD:
                        timing_all[feat][offset] += 1
                        if context == 'WITH_TREND':
                            timing_with[feat][offset] += 1
                        else:
                            timing_against[feat][offset] += 1

                # Record anatomy at t=0, t-1, t-2
                if offset == 0:
                    for feat in valid_signals:
                        anatomy_t0[feat].append(float(df.at[row_idx, feat]))
                elif offset == -1:
                    for feat in valid_signals:
                        anatomy_t1[feat].append(float(df.at[row_idx, feat]))
                elif offset == -2:
                    for feat in valid_signals:
                        anatomy_t2[feat].append(float(df.at[row_idx, feat]))

                # Drift: price at signal bar vs price at turn
                if offset < 0:
                    sig_price = float(df.at[row_idx, 'price'])
                    if sig_price > 0:
                        d = (zz_price / sig_price - 1) * 100
                        if context == 'WITH_TREND':
                            drift_with.append((offset, d))
                        else:
                            drift_against.append((offset, d))

        # ── PRINT RESULTS ──

        print(f"\n  Total turns: {total_all:,d}")
        print(f"  WITH_TREND:    {total_with:,d} ({total_with/max(total_all,1)*100:.1f}%)")
        print(f"  AGAINST_TREND: {total_against:,d} ({total_against/max(total_all,1)*100:.1f}%)")

        if opp_with and opp_against:
            print(f"\n  Opportunity WITH trend:    median={np.median(opp_with):.1f}% | mean={np.mean(opp_with):.1f}%")
            print(f"  Opportunity AGAINST trend: median={np.median(opp_against):.1f}% | mean={np.mean(opp_against):.1f}%")

        # RC state summary
        print(f"\n  RC State at turning points:")
        for col in ['tide_slope', 'current_slope', 'wave_slope']:
            if col not in rc_at_turn:
                continue
            with_vals = [v for ctx, v in rc_at_turn[col] if ctx == 'WITH_TREND']
            against_vals = [v for ctx, v in rc_at_turn[col] if ctx == 'AGAINST_TREND']
            print(f"    {col:20s}  WITH_TREND mean={np.mean(with_vals):+.6f}  "
                  f"AGAINST mean={np.mean(against_vals):+.6f}")

        # Bar-by-bar timing distribution for top features
        sorted_feats = sorted(timing_all.items(), key=lambda x: -sum(x[1].values()))

        print(f"\n  BAR-BY-BAR TIMING (% of turns where feature active at each offset):")
        header = "  " + f"{'Feature':28s}" + "".join(f"{'t'+str(o):>6s}" for o in OFFSETS) + "  TOTAL"
        print(header)
        print(f"  {'─'*len(header)}")

        for feat, counts in sorted_feats[:20]:
            row = f"  {feat:28s}"
            for o in OFFSETS:
                pct = counts.get(o, 0) / max(total_all, 1) * 100
                row += f"{pct:>5.0f}%"
            total_active = sum(1 for o in OFFSETS if counts.get(o, 0) > 0)
            row += f"   {sum(counts.values()):>5d}"
            print(row)

        # WITH vs AGAINST comparison for top 15
        print(f"\n  WITH_TREND vs AGAINST_TREND — Signal at t=0 (the exact breakpoint):")
        print(f"  {'Feature':28s}  {'WITH t=0':>8s}  {'AGST t=0':>8s}  {'WITH t-1':>8s}  {'AGST t-1':>8s}  {'Discrimina?':>12s}")
        print(f"  {'─'*90}")

        for feat, _ in sorted_feats[:20]:
            w0 = timing_with[feat].get(0, 0) / max(total_with, 1) * 100
            a0 = timing_against[feat].get(0, 0) / max(total_against, 1) * 100
            w1 = timing_with[feat].get(-1, 0) / max(total_with, 1) * 100
            a1 = timing_against[feat].get(-1, 0) / max(total_against, 1) * 100
            # Does it discriminate?
            diff = abs(w0 - a0)
            disc = "✅ YES" if diff > 10 else ("⚠️ weak" if diff > 5 else "✖ NO")
            print(f"  {feat:28s}  {w0:>7.1f}%  {a0:>7.1f}%  {w1:>7.1f}%  {a1:>7.1f}%  {disc:>12s}")

        # Breakpoint anatomy: what do features LOOK LIKE at the turn
        print(f"\n  BREAKPOINT ANATOMY — Feature values at t-2, t-1, t=0:")
        print(f"  {'Feature':28s}  {'t-2 mean':>10s}  {'t-1 mean':>10s}  {'t=0 mean':>10s}  {'t-2→t=0 Δ':>10s}")
        print(f"  {'─'*75}")
        for feat in ['rsi_value', 'wave_accel', 'tide_slope', 'current_slope',
                      'wave_slope', 'sigma_tide', 'sigma_current', 'tsi_tide',
                      'tsi_wave', 'compression_ratio', 'below_all_vwaps_int',
                      'atr_ratio', 'complacency_index', 'tension_tide']:
            if feat not in anatomy_t0 or not anatomy_t0[feat]:
                continue
            m0 = np.mean(anatomy_t0[feat])
            m1 = np.mean(anatomy_t1[feat]) if anatomy_t1.get(feat) else m0
            m2 = np.mean(anatomy_t2[feat]) if anatomy_t2.get(feat) else m0
            delta = m0 - m2
            print(f"  {feat:28s}  {m2:>10.4f}  {m1:>10.4f}  {m0:>10.4f}  {delta:>+10.4f}")

        # Drift by context
        print(f"\n  DRIFT by context (how much price moves from signal bar to turn):")
        for ctx_label, drift_data in [('WITH_TREND', drift_with), ('AGAINST_TREND', drift_against)]:
            if not drift_data:
                continue
            for offset in [-1, -2, -3, -5]:
                vals = [d for o, d in drift_data if o == offset]
                if vals:
                    print(f"    {ctx_label:15s} signal at t{offset:+d}: "
                          f"drift mean={np.mean(vals):+.2f}%  "
                          f"median={np.median(vals):+.2f}%  "
                          f"worst={min(vals) if tp_type=='MIN' else max(vals):+.2f}%")

        # ── FIRST ACTIVATION: for each turn, at EXACTLY which bar did each feature FIRST fire?
        print(f"\n  FIRST ACTIVATION — Exact bar where each feature FIRST fired (within t-7..t+3):")
        print(f"  {'Feature':28s}  {'t-7':>4s}{'t-6':>4s}{'t-5':>4s}{'t-4':>4s}{'t-3':>4s}{'t-2':>4s}"
              f"{'t-1':>4s}{'t=0':>4s}{'t+1':>4s}{'t+2':>4s}{'t+3':>4s}  {'≤t=0':>5s}{'t+1+':>5s}")
        print(f"  {'─'*100}")

        # Recompute first-activation per turn
        first_act = defaultdict(lambda: Counter())
        for _, zz_row in zz_tp.iterrows():
            ticker = zz_row['ticker']
            zz_ts = zz_row['timestamp']
            tk_mask = df['ticker'] == ticker
            tk_df = df[tk_mask]
            if len(tk_df) < 10:
                continue
            time_diffs = np.abs((tk_df['timestamp'].values - np.datetime64(zz_ts)).astype('timedelta64[D]').astype(int))
            center = time_diffs.argmin()
            if time_diffs[center] > 3:
                continue

            for feat in valid_signals:
                for offset in OFFSETS:
                    check_pos = center + offset
                    if check_pos < 0 or check_pos >= len(tk_df):
                        continue
                    row_idx = tk_df.index[check_pos]
                    val = df.at[row_idx, feat]
                    z = (val - feat_means[feat].at[row_idx]) / feat_stds[feat].at[row_idx]
                    if abs(z) >= Z_THRESHOLD:
                        first_act[feat][offset] += 1
                        break  # FIRST activation only

        sorted_first = sorted(first_act.items(), key=lambda x: -sum(x[1].values()))
        for feat, counts in sorted_first[:20]:
            total_f = sum(counts.values())
            row = f"  {feat:28s}"
            for o in OFFSETS:
                n = counts.get(o, 0)
                pct = n / max(total_f, 1) * 100
                row += f"{pct:>4.0f}"
            on_time = sum(counts.get(o, 0) for o in OFFSETS if o <= 0) / max(total_f, 1) * 100
            late = sum(counts.get(o, 0) for o in OFFSETS if o > 0) / max(total_f, 1) * 100
            row += f"  {on_time:>4.0f}%{late:>4.0f}%"
            print(row)

    store.close()
    ps.close()
    print(f"\n{'='*90}")
    print(f"  ★★★ BREAKPOINT FORENSICS COMPLETE ★★★")
    print(f"{'='*90}")


if __name__ == "__main__":
    main()
