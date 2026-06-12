#!/usr/bin/env python3
"""
Deep Feature Mining with Zigzag Confluence Ground Truth
=========================================================
Uses multi-scale zigzag confluences (2.5%, 5%, 7.5%) as GROUND TRUTH
for timing quality. Finds which features DETECT:

  1. Proximity to an L3_BOS trough (Break of Structure)
  2. Being AFTER (not before) the trough 
  3. The golden combination: near BOS + AFTER

This is CONSTRUCTIVE — we're not looking for flaws, we're finding
the features that detect structural breaks in real-time.

All 79 original + ~20 derived features tested exhaustively.
"""
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.quality_swing.domain.rules.rc_state_probability import lookup_probability


TEST_START = "2006-01-01"
CONFLUENCE_WINDOW = 5


def load_everything():
    store = TimescaleDataStore(); conn = store._conn()

    cs = pd.read_sql(f"""
        SELECT ticker, timestamp::date as date,
               sigma_tide, sigma_current, sigma_wave,
               residual_std_tide, residual_std_current, residual_std_wave,
               vwap_sigma_tide, vwap_sigma_current, vwap_sigma_wave,
               tide_slope, current_slope, wave_slope,
               tide_accel, current_accel, wave_accel,
               conj_wave_current, conj_wave_tide, conj_current_tide,
               spread_tide_current, spread_tide_wave, spread_current_wave,
               vwap_spread_tide_current, vwap_spread_tide_wave, vwap_spread_current_wave,
               fear_level,
               vol_up_down_ratio,
               tension_tide, tension_current, tension_wave,
               compression_ratio,
               rsi_value, rsi_divergence_strength, rsi_conviction,
               kalman_velocity, vol_adj_delta,
               geo_state_norm, geo_velocity_align, geo_exit_align, geo_accel_align, geo_phase_angle,
               kf_price_pred_val, kf_price_filt_vel, kf_price_innovation,
               kf_rvol_pred_val, kf_rvol_filt_vel,
               kf_tension_pred_val, kf_tension_filt_vel,
               kf_rsi_pred_val, kf_rsi_filt_vel,
               kf_conj_pred_val, kf_conj_filt_vel,
               turn_prob_piso, turn_prob_techo
        FROM engine.channel_snapshots
        WHERE timeframe = '1d' AND timestamp >= '{TEST_START}'
        ORDER BY ticker, timestamp
    """, conn)

    zz25 = pd.read_sql("SELECT ticker, timestamp::date as date, tp_type, price FROM engine.zigzag_points WHERE min_swing_pct=0.025 ORDER BY ticker, timestamp", conn)
    zz50 = pd.read_sql("SELECT ticker, timestamp::date as date, tp_type, price FROM engine.zigzag_points WHERE min_swing_pct=0.05 ORDER BY ticker, timestamp", conn)
    zz75 = pd.read_sql("SELECT ticker, timestamp::date as date, tp_type, price FROM engine.zigzag_points WHERE min_swing_pct=0.075 ORDER BY ticker, timestamp", conn)

    bars = pd.read_sql("SELECT ticker, time::date as date, close, volume FROM market.ohlcv_bars WHERE timeframe='1d' ORDER BY ticker, time", conn)

    store._put(conn); store.close()
    for d in [cs, zz25, zz50, zz75, bars]:
        d['date'] = pd.to_datetime(d['date'])
    return cs, zz25, zz50, zz75, bars


def build_confluence_map(zz25, zz50, zz75, tp_type='MIN'):
    """Build lookup: for each ticker, list of (date, level, price) for troughs."""
    result = {}
    for ticker in zz25['ticker'].unique():
        tk25 = zz25[(zz25['ticker'] == ticker) & (zz25['tp_type'] == tp_type)].sort_values('date')
        d50 = pd.to_datetime(zz50[(zz50['ticker'] == ticker) & (zz50['tp_type'] == tp_type)]['date']).values
        d75 = pd.to_datetime(zz75[(zz75['ticker'] == ticker) & (zz75['tp_type'] == tp_type)]['date']).values

        entries = []
        for _, r in tk25.iterrows():
            d = np.datetime64(r['date'])
            has_50 = len(d50) > 0 and np.abs((d50 - d) / np.timedelta64(1, 'D')).min() <= CONFLUENCE_WINDOW
            has_75 = len(d75) > 0 and np.abs((d75 - d) / np.timedelta64(1, 'D')).min() <= CONFLUENCE_WINDOW

            if has_50 and has_75:
                level = 3  # L3_BOS
            elif has_50:
                level = 2  # L2_CONF
            else:
                level = 1  # L1_NOISE

            entries.append((np.datetime64(r['date']), level, float(r['price'])))
        result[ticker] = entries
    return result


def label_bars(cs, bars, trough_map, peak_map):
    """For each bar: nearest trough level, distance, BEFORE/AFTER, profit to peak."""
    df = cs.merge(bars[['ticker', 'date', 'close', 'volume']], on=['ticker', 'date'], how='inner')
    df = df.sort_values(['ticker', 'date']).reset_index(drop=True)

    # P(bull)
    p_bulls = []
    for _, r in df.iterrows():
        rc = lookup_probability(
            float(r['tide_slope']), float(r['sigma_current']),
            float(r['sigma_wave']), float(r['vwap_sigma_wave']))
        p_bulls.append(rc.prob_bull if rc else None)
    df['p_bull'] = p_bulls

    # Hookup
    df['hookup'] = df.groupby('ticker')['close'].transform(lambda x: x > x.shift(1))

    # Label from trough/peak maps
    nearest_level = []
    nearest_side = []
    nearest_dist = []
    profit_to_peak = []
    is_accum = []

    for _, row in df.iterrows():
        ticker = row['ticker']
        d = np.datetime64(row['date'])
        price = float(row['close'])
        pb = row['p_bull']

        troughs = trough_map.get(ticker, [])
        peaks = peak_map.get(ticker, [])

        if not troughs or not peaks:
            nearest_level.append(None)
            nearest_side.append(None)
            nearest_dist.append(None)
            profit_to_peak.append(None)
            is_accum.append(False)
            continue

        t_dates = np.array([t[0] for t in troughs])
        t_levels = np.array([t[1] for t in troughs])

        # Find nearest trough
        diffs = np.abs((t_dates - d) / np.timedelta64(1, 'D'))
        nearest_idx = diffs.argmin()
        dist = diffs[nearest_idx]
        level = t_levels[nearest_idx]
        t_date = t_dates[nearest_idx]

        side = "AFTER" if d >= t_date else "BEFORE"

        # Profit to next peak
        p_dates = np.array([p[0] for p in peaks])
        p_prices = np.array([p[2] for p in peaks])
        pi = np.searchsorted(p_dates, d, side='right')
        if pi < len(p_dates):
            pft = (p_prices[pi] / price - 1.0) * 100
        else:
            pft = None

        nearest_level.append(level)
        nearest_side.append(side)
        nearest_dist.append(dist)
        profit_to_peak.append(pft)
        is_accum.append(pb is not None and pb >= 0.65)

    df['trough_level'] = nearest_level
    df['trough_side'] = nearest_side
    df['trough_dist'] = nearest_dist
    df['profit_to_peak'] = profit_to_peak
    df['is_accum'] = is_accum

    # DERIVED FEATURES
    df['div_current'] = df['sigma_current'] - df['vwap_sigma_current']
    df['div_wave'] = df['sigma_wave'] - df['vwap_sigma_wave']
    df['div_tide'] = df['sigma_tide'] - df['vwap_sigma_tide']

    df['stress_cw'] = df['sigma_current'] - df['sigma_wave']
    df['stress_tc'] = df['sigma_tide'] - df['sigma_current']
    df['total_stress'] = df['stress_cw'].abs() + df['stress_tc'].abs()

    df['sigma_c_vel'] = df.groupby('ticker')['sigma_current'].transform(lambda x: x - x.shift(1))
    df['sigma_w_vel'] = df.groupby('ticker')['sigma_wave'].transform(lambda x: x - x.shift(1))
    df['svw_vel'] = df.groupby('ticker')['vwap_sigma_wave'].transform(lambda x: x - x.shift(1))
    df['svc_vel'] = df.groupby('ticker')['vwap_sigma_current'].transform(lambda x: x - x.shift(1))

    df['div_wave_delta'] = df.groupby('ticker')['div_wave'].transform(lambda x: x - x.shift(1))
    df['div_current_delta'] = df.groupby('ticker')['div_current'].transform(lambda x: x - x.shift(1))

    for ch in ['tide', 'current', 'wave']:
        df[f'tension_norm_{ch}'] = df[f'tension_{ch}'] / (df[f'residual_std_{ch}'] + 0.001)

    df['vwap_alignment'] = np.sign(df['vwap_sigma_tide']) + np.sign(df['vwap_sigma_current']) + np.sign(df['vwap_sigma_wave'])
    df['sigma_energy'] = df['sigma_current']**2 + df['sigma_wave']**2
    df['sigma_momentum'] = df['sigma_c_vel']**2 + df['sigma_w_vel']**2

    df['kf_consensus'] = (
        np.sign(df['kf_price_filt_vel'].fillna(0)) +
        np.sign(df['kf_rsi_filt_vel'].fillna(0)) +
        np.sign(df['kf_conj_filt_vel'].fillna(0)) +
        np.sign(df['kf_tension_filt_vel'].fillna(0))
    )

    df['slope_alignment'] = np.sign(df['tide_slope']) + np.sign(df['current_slope']) + np.sign(df['wave_slope'])
    df['accel_alignment'] = np.sign(df['tide_accel']) + np.sign(df['current_accel']) + np.sign(df['wave_accel'])

    # Volume velocity
    df['vol_vel'] = df.groupby('ticker')['volume'].transform(lambda x: x / x.rolling(20).mean()) - 1.0

    # RSI velocity
    df['rsi_vel'] = df.groupby('ticker')['rsi_value'].transform(lambda x: x - x.shift(1))

    # Compression velocity
    df['compression_vel'] = df.groupby('ticker')['compression_ratio'].transform(lambda x: x - x.shift(1))

    # Conj velocity
    df['conj_wc_vel'] = df.groupby('ticker')['conj_wave_current'].transform(lambda x: x - x.shift(1))

    # Tension velocity
    df['tension_w_vel'] = df.groupby('ticker')['tension_wave'].transform(lambda x: x - x.shift(1))
    df['tension_c_vel'] = df.groupby('ticker')['tension_current'].transform(lambda x: x - x.shift(1))

    return df


def mine_for_bos(df):
    """Find features that predict proximity to BOS troughs."""
    # Focus on ACCUMULATE bars within 15 days of ANY trough
    near = df[(df['is_accum']) & (df['trough_dist'].notna()) & (df['trough_dist'] <= 15)].copy()
    n_total = len(near)

    # TARGETS
    near['is_bos'] = near['trough_level'] == 3
    near['is_after'] = near['trough_side'] == 'AFTER'
    near['is_golden'] = near['is_bos'] & near['is_after']  # Near BOS AND after trough

    print(f"\n{'='*130}")
    print(f"  CONSTRUCTIVE FEATURE MINING — Zigzag Confluence as Ground Truth")
    print(f"  ACCUMULATE bars within 15d of a trough: {n_total:,}")
    print(f"  BOS (L3): {near['is_bos'].sum():,} ({near['is_bos'].mean():.1%})")
    print(f"  AFTER trough: {near['is_after'].sum():,} ({near['is_after'].mean():.1%})")
    print(f"  GOLDEN (BOS+AFTER): {near['is_golden'].sum():,} ({near['is_golden'].mean():.1%})")
    print(f"{'='*130}")

    skip = {'ticker', 'date', 'close', 'volume', 'p_bull', 'hookup', 'is_accum',
            'trough_level', 'trough_side', 'trough_dist', 'profit_to_peak',
            'is_bos', 'is_after', 'is_golden'}
    features = [c for c in near.columns if c not in skip and near[c].dtype in ['float64', 'float32', 'int64', 'bool']]

    targets = [
        ("AFTER_TROUGH (timing)", 'is_after'),
        ("BOS_PROXIMITY (structural)", 'is_bos'),
        ("GOLDEN (BOS+AFTER)", 'is_golden'),
    ]

    for target_name, target_col in targets:
        print(f"\n  {'─'*120}")
        print(f"  TARGET: {target_name} — which features predict this?")
        print(f"  Base rate: {near[target_col].mean():.1%}")
        print(f"  {'─'*120}")

        results = []
        for feat in features:
            valid = near[feat].notna()
            sub = near[valid]
            if len(sub) < 1000:
                continue

            try:
                y = sub[target_col].astype(int)
                x = sub[feat].astype(float)
                if x.std() < 1e-10:
                    continue

                auc = roc_auc_score(y, x)
                direction = "HIGH→yes" if auc >= 0.5 else "LOW→yes"
                auc_eff = max(auc, 1 - auc)

                med = x.median()
                rate_hi = sub[x >= med][target_col].mean()
                rate_lo = sub[x < med][target_col].mean()
                spread = abs(rate_hi - rate_lo)

                q10 = x.quantile(0.10)
                q90 = x.quantile(0.90)
                r_q10 = sub[x <= q10][target_col].mean() if (x <= q10).sum() > 30 else None
                r_q90 = sub[x >= q90][target_col].mean() if (x >= q90).sum() > 30 else None
                xspread = abs(r_q90 - r_q10) if r_q10 is not None and r_q90 is not None else 0

                results.append({
                    'feature': feat, 'auc': auc_eff, 'direction': direction,
                    'rate_hi': rate_hi, 'rate_lo': rate_lo, 'spread': spread,
                    'rate_q10': r_q10, 'rate_q90': r_q90, 'xspread': xspread,
                })
            except Exception:
                continue

        rt = pd.DataFrame(results).sort_values('auc', ascending=False)

        print(f"\n  {'#':>3s} {'Feature':<35s} {'AUC':>6s} {'Dir':<10s} {'rate_hi':>8s} {'rate_lo':>8s} "
              f"{'spread':>7s} {'rate_Q10':>8s} {'rate_Q90':>8s} {'Xspread':>8s}")

        for i, (_, r) in enumerate(rt.head(30).iterrows()):
            mk = " ★★" if r['xspread'] > 0.15 else " ★" if r['xspread'] > 0.08 else ""
            q10 = f"{r['rate_q10']:.1%}" if r['rate_q10'] is not None else "  —"
            q90 = f"{r['rate_q90']:.1%}" if r['rate_q90'] is not None else "  —"
            print(f"  {i+1:>3d} {r['feature']:<35s} {r['auc']:>5.3f} {r['direction']:<10s} "
                  f"{r['rate_hi']:>7.1%} {r['rate_lo']:>7.1%} {r['spread']:>6.1%} "
                  f"{q10:>8s} {q90:>8s} {r['xspread']:>7.1%}{mk}")

    # ═══════════════════════════════════════════════════════════
    # SPECIAL: Interaction effects for AFTER_TROUGH target
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'='*130}")
    print(f"  INTERACTION EFFECTS — Feature pairs that predict AFTER trough")
    print(f"{'='*130}")

    # Get top 12 features for AFTER
    results_after = []
    for feat in features:
        valid = near[feat].notna()
        sub = near[valid]
        if len(sub) < 1000:
            continue
        try:
            y = sub['is_after'].astype(int)
            x = sub[feat].astype(float)
            if x.std() < 1e-10:
                continue
            auc = max(roc_auc_score(y, x), 1 - roc_auc_score(y, x))
            results_after.append({'feature': feat, 'auc': auc})
        except Exception:
            continue

    top12 = pd.DataFrame(results_after).nlargest(12, 'auc')['feature'].tolist()

    interactions = []
    for i, f1 in enumerate(top12):
        for f2 in top12[i+1:]:
            valid = near[f1].notna() & near[f2].notna()
            sub = near[valid]
            if len(sub) < 500:
                continue

            m1, m2 = sub[f1].median(), sub[f2].median()

            # For each feature, determine if HIGH or LOW predicts AFTER
            auc1 = roc_auc_score(sub['is_after'].astype(int), sub[f1])
            auc2 = roc_auc_score(sub['is_after'].astype(int), sub[f2])

            # If AUC < 0.5, LOW values predict AFTER, so flip
            if auc1 < 0.5:
                mask1_good = sub[f1] < m1
                mask1_bad = sub[f1] >= m1
            else:
                mask1_good = sub[f1] >= m1
                mask1_bad = sub[f1] < m1

            if auc2 < 0.5:
                mask2_good = sub[f2] < m2
                mask2_bad = sub[f2] >= m2
            else:
                mask2_good = sub[f2] >= m2
                mask2_bad = sub[f2] < m2

            both_good = sub[mask1_good & mask2_good]
            both_bad = sub[mask1_bad & mask2_bad]

            if len(both_good) < 100 or len(both_bad) < 100:
                continue

            r_good = both_good['is_after'].mean()
            r_bad = both_bad['is_after'].mean()
            spread = r_good - r_bad
            profit_good = both_good['profit_to_peak'].dropna().median()
            profit_bad = both_bad['profit_to_peak'].dropna().median()

            interactions.append({
                'pair': f"{f1} × {f2}",
                'after_good': r_good, 'after_bad': r_bad, 'spread': spread,
                'profit_good': profit_good, 'profit_bad': profit_bad,
                'n_good': len(both_good), 'n_bad': len(both_bad),
            })

    int_df = pd.DataFrame(interactions).sort_values('spread', ascending=False)

    print(f"\n  {'Pair':<65s} {'%AFT_good':>10s} {'%AFT_bad':>10s} {'spread':>7s} {'pft_good':>9s} {'pft_bad':>9s}")
    for _, r in int_df.head(20).iterrows():
        mk = " ★★" if r['spread'] > 0.15 else " ★" if r['spread'] > 0.10 else ""
        print(f"  {r['pair']:<65s} {r['after_good']:>9.1%} {r['after_bad']:>9.1%} "
              f"{r['spread']:>6.1%} {r['profit_good']:>+8.1f}% {r['profit_bad']:>+8.1f}%{mk}")

    # ═══════════════════════════════════════════════════════════
    # SPECIAL: Transition features — what CHANGES near BOS
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'='*130}")
    print(f"  TRANSITION DETECTION — Features that CHANGE near BOS troughs")
    print(f"{'='*130}")

    vel_features = [f for f in features if '_vel' in f or '_delta' in f or 'accel' in f]
    print(f"\n  Velocity/Acceleration features ({len(vel_features)}):")
    print(f"  {'Feature':<35s} {'%AFT_pos':>10s} {'%AFT_neg':>10s} {'spread':>7s} {'pft_pos':>9s} {'pft_neg':>9s}")

    for feat in vel_features:
        valid = near[feat].notna()
        sub = near[valid]
        if len(sub) < 500:
            continue

        pos = sub[sub[feat] > 0]
        neg = sub[sub[feat] <= 0]
        if len(pos) < 100 or len(neg) < 100:
            continue

        after_pos = pos['is_after'].mean()
        after_neg = neg['is_after'].mean()
        spread = after_pos - after_neg
        pft_pos = pos['profit_to_peak'].dropna().median()
        pft_neg = neg['profit_to_peak'].dropna().median()

        mk = " ★★" if abs(spread) > 0.10 else " ★" if abs(spread) > 0.05 else ""
        print(f"  {feat:<35s} {after_pos:>9.1%} {after_neg:>9.1%} "
              f"{spread:>+6.1%} {pft_pos:>+8.1f}% {pft_neg:>+8.1f}%{mk}")

    print("\nDONE")


def main():
    print("Loading ALL data...")
    cs, zz25, zz50, zz75, bars = load_everything()
    print(f"  {len(cs):,} snapshots")

    print("Building confluence maps...")
    trough_map = build_confluence_map(zz25, zz50, zz75, 'MIN')
    peak_map = build_confluence_map(zz25, zz50, zz75, 'MAX')
    for tk, entries in trough_map.items():
        levels = [e[1] for e in entries]
        if tk == list(trough_map.keys())[0]:
            print(f"  {tk}: L1={levels.count(1)} L2={levels.count(2)} L3={levels.count(3)}")

    print("Labeling bars with confluence proximity...")
    df = label_bars(cs, bars, trough_map, peak_map)
    print(f"  {len(df):,} labeled bars")

    print("Mining features against BOS ground truth...")
    mine_for_bos(df)


if __name__ == "__main__":
    main()
