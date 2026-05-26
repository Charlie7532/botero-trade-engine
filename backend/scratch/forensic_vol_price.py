#!/usr/bin/env python3
"""
Forencia Vol-Price Correlation — Challenger v3 Feature Discovery
================================================================
Investigates Volume-Price relationship features for the 3 weak heads:
  - zz_top_detector (DROP from v2)
  - short_cover (below production)
  - swing_exit (≈ SAME)

Features under investigation:
  1. vol_price_corr_20d: Rolling Pearson correlation (volume, returns, 20d)
  2. effort_vs_result: avg_volume / (avg_range × close) — Wyckoff effort/result
  3. vol_price_divergence_20d: Extended divergence (vs 5-bar in optimizer)
  4. climax_volume_ratio: Current vol / highest vol in lookback
  5. volume_momentum: Rate of change of volume MA

Methodology: López de Prado SFI (Single Feature Importance) via AUC
on each label type, with t-test for statistical significance at floors/ceilings.
"""
import os, sys, warnings, time
from pathlib import Path
warnings.filterwarnings("ignore")

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

def p(t): print(f"\n{'='*90}\n  {t}\n{'='*90}")
def sp(t): print(f"\n  ── {t} ──")

TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]


def load_data(store):
    """Load feature lake with OHLCV for vol-price analysis."""
    sp("Loading feature lake + OHLCV")
    
    query = """
        SELECT cs.ticker, cs.timestamp,
               cs.sigma_tide, cs.sigma_current, cs.sigma_wave,
               cs.tide_slope, cs.current_slope, cs.wave_slope,
               cs.tide_accel, cs.current_accel, cs.wave_accel,
               cs.tension_tide, cs.compression_ratio,
               cs.fear_level, cs.vol_up_down_ratio,
               cs.rsi_value,
               cs.vwap_sigma_tide, cs.vwap_sigma_current,
               ob.open as open_price,
               ob.high as high_price,
               ob.low as low_price,
               ob.close as price,
               ob.volume as volume
        FROM engine.channel_snapshots cs
        JOIN market.ohlcv_bars ob
            ON ob.ticker = cs.ticker AND ob.timeframe = '1d' AND ob.time = cs.timestamp
        WHERE cs.sigma_tide IS NOT NULL
          AND cs.tide_slope IS NOT NULL
        ORDER BY cs.ticker, cs.timestamp
    """
    
    df = pd.read_sql(query, store.engine)
    print(f"    Loaded {len(df):,d} rows, {df['ticker'].nunique()} tickers")
    return df


def compute_vol_price_features(df):
    """Compute all vol-price candidate features. Fully vectorized per-ticker."""
    sp("Computing Vol-Price Features (vectorized)")
    t0 = time.time()
    
    new_features = []
    
    # Pre-allocate arrays
    n = len(df)
    vol_price_corr_20 = np.full(n, np.nan)
    vol_price_corr_10 = np.full(n, np.nan)
    effort_vs_result_10 = np.full(n, np.nan)
    effort_vs_result_20 = np.full(n, np.nan)
    climax_vol_ratio = np.full(n, np.nan)
    vol_momentum_5_20 = np.full(n, np.nan)
    vol_return_interaction = np.full(n, np.nan)
    obv_slope_20 = np.full(n, np.nan)
    vol_price_regime = np.full(n, np.nan)
    vol_breakout_signal = np.full(n, np.nan)
    
    for ticker in df['ticker'].unique():
        mask = (df['ticker'] == ticker).values
        idx = np.where(mask)[0]
        
        close = df.loc[mask, 'price'].values.astype(float)
        high = df.loc[mask, 'high_price'].values.astype(float)
        low = df.loc[mask, 'low_price'].values.astype(float)
        volume = df.loc[mask, 'volume'].values.astype(float)
        
        returns = np.zeros_like(close)
        returns[1:] = (close[1:] - close[:-1]) / np.where(close[:-1] > 0, close[:-1], 1.0)
        
        candle_range = high - low
        candle_range_safe = np.where(candle_range > 0, candle_range, 1e-8)
        
        n_tk = len(close)
        
        # 1. Rolling Pearson correlation: volume vs returns (20d and 10d)
        #    Optimized with pandas rolling to avoid O(N²) Python loops.
        vol_s = pd.Series(volume)
        ret_s = pd.Series(returns)
        for w, arr in [(20, vol_price_corr_20), (10, vol_price_corr_10)]:
            rolling_corr = vol_s.rolling(w, min_periods=w).corr(ret_s).values
            for i in range(w, n_tk):
                val = rolling_corr[i]
                arr[idx[i]] = val if np.isfinite(val) else 0.0
        
        # 2. Effort vs Result (Wyckoff): avg_volume / (avg_range × close)
        #    High effort + low result = accumulation/distribution
        for w, arr in [(10, effort_vs_result_10), (20, effort_vs_result_20)]:
            for i in range(w, n_tk):
                avg_vol = np.mean(volume[i-w:i])
                avg_range = np.mean(candle_range_safe[i-w:i])
                arr[idx[i]] = avg_vol / (avg_range * close[i]) if close[i] > 0 else 0.0
        
        # 3. Climax Volume Ratio: current / max(last 20 bars)
        vol_s = pd.Series(volume)
        vol_max_20 = vol_s.rolling(20, min_periods=5).max().values
        for i in range(20, n_tk):
            if vol_max_20[i] > 0:
                climax_vol_ratio[idx[i]] = volume[i] / vol_max_20[i]
        
        # 4. Volume Momentum: MA5 / MA20 rate of change
        vol_ma5 = vol_s.rolling(5, min_periods=1).mean().values
        vol_ma20 = vol_s.rolling(20, min_periods=1).mean().values
        for i in range(20, n_tk):
            if vol_ma20[i] > 0:
                curr_ratio = vol_ma5[i] / vol_ma20[i]
                prev_ratio = vol_ma5[max(0,i-5)] / vol_ma20[max(0,i-5)] if vol_ma20[max(0,i-5)] > 0 else 1.0
                vol_momentum_5_20[idx[i]] = curr_ratio - prev_ratio
        
        # 5. Volume × Return interaction (instantaneous)
        for i in range(20, n_tk):
            vol_z = (volume[i] - vol_ma20[i]) / max(np.std(volume[max(0,i-20):i]), 1e-8)
            vol_return_interaction[idx[i]] = vol_z * returns[i]
        
        # 6. OBV slope (20-bar): On Balance Volume trend
        obv = np.cumsum(np.where(returns > 0, volume, np.where(returns < 0, -volume, 0)))
        obv_s = pd.Series(obv)
        for i in range(20, n_tk):
            y = obv[i-20:i]
            x = np.arange(20)
            if np.std(y) > 0:
                slope, _, _, _, _ = scipy_stats.linregress(x, y)
                obv_slope_20[idx[i]] = slope / max(np.mean(volume[i-20:i]), 1e-8)
            else:
                obv_slope_20[idx[i]] = 0.0
        
        # 7. Vol-Price Regime: classify the current vol-price relationship
        # +2 = high vol + up = confirmed rally
        # +1 = low vol + up = suspicious rally  
        # -1 = low vol + down = orderly decline
        # -2 = high vol + down = panic selling
        for i in range(20, n_tk):
            vol_z = (volume[i] - vol_ma20[i]) / max(np.std(volume[max(0,i-20):i]), 1e-8)
            ret_5d = (close[i] - close[max(0,i-5)]) / close[max(0,i-5)] if close[max(0,i-5)] > 0 else 0
            
            if vol_z > 1.0 and ret_5d > 0.01:
                vol_price_regime[idx[i]] = 2.0  # Confirmed rally
            elif vol_z < -0.5 and ret_5d > 0.01:
                vol_price_regime[idx[i]] = 1.0  # Suspicious rally
            elif vol_z < -0.5 and ret_5d < -0.01:
                vol_price_regime[idx[i]] = -1.0  # Orderly decline
            elif vol_z > 1.0 and ret_5d < -0.01:
                vol_price_regime[idx[i]] = -2.0  # Panic selling
            else:
                vol_price_regime[idx[i]] = 0.0  # Neutral
        
        # 8. Volume Breakout Signal: vol spike + range expansion
        for i in range(20, n_tk):
            vol_z = (volume[i] - vol_ma20[i]) / max(np.std(volume[max(0,i-20):i]), 1e-8)
            range_z = (candle_range[i] - np.mean(candle_range_safe[max(0,i-20):i])) / max(np.std(candle_range_safe[max(0,i-20):i]), 1e-8)
            vol_breakout_signal[idx[i]] = vol_z * range_z  # Both spike = strong signal
    
    # Assign to DataFrame
    features_map = {
        'vol_price_corr_20d': vol_price_corr_20,
        'vol_price_corr_10d': vol_price_corr_10,
        'effort_vs_result_10d': effort_vs_result_10,
        'effort_vs_result_20d': effort_vs_result_20,
        'climax_vol_ratio': climax_vol_ratio,
        'vol_momentum_5_20': vol_momentum_5_20,
        'vol_return_interaction': vol_return_interaction,
        'obv_slope_20d': obv_slope_20,
        'vol_price_regime': vol_price_regime,
        'vol_breakout_signal': vol_breakout_signal,
    }
    
    for name, values in features_map.items():
        df[name] = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
        new_features.append(name)
    
    elapsed = time.time() - t0
    print(f"    Computed {len(new_features)} vol-price features in {elapsed:.1f}s")
    return new_features


def compute_labels(df, store):
    """Compute forward return labels for the 3 weak heads + general floor/ceiling."""
    sp("Computing Labels")
    
    n = len(df)
    # Forward returns
    fwd_20d = np.full(n, np.nan)
    fwd_max_dd_5d = np.full(n, np.nan)
    fwd_max_runup_5d = np.full(n, np.nan)
    
    for ticker in df['ticker'].unique():
        mask = (df['ticker'] == ticker).values
        idx = np.where(mask)[0]
        close = df.loc[mask, 'price'].values.astype(float)
        n_tk = len(close)
        
        for i in range(n_tk - 20):
            base = close[i]
            if base <= 0:
                continue
            fwd_20d[idx[i]] = (close[min(i+20, n_tk-1)] - base) / base
            
            fwd_5 = close[i+1:min(i+6, n_tk)]
            if len(fwd_5) > 0:
                fwd_ret_5 = (fwd_5 - base) / base
                fwd_max_dd_5d[idx[i]] = np.min(fwd_ret_5)
                fwd_max_runup_5d[idx[i]] = np.max(fwd_ret_5)
    
    df['fwd_20d'] = fwd_20d
    df['fwd_max_dd_5d'] = fwd_max_dd_5d
    df['fwd_max_runup_5d'] = fwd_max_runup_5d
    
    # Labels matching the 3 weak heads — NaN-safe: set label to NaN where fwd is NaN
    # so SFI analysis filters them out correctly instead of treating NaN as label=0.
    fwd_valid = df['fwd_20d'].notna()
    df['label_long_entry'] = np.where(fwd_valid, (df['fwd_20d'] > 0).astype(float), np.nan)
    dd_valid = df['fwd_max_dd_5d'].notna()
    df['label_pullback_deepen'] = np.where(dd_valid, (df['fwd_max_dd_5d'] < -0.02).astype(float), np.nan)
    ru_valid = df['fwd_max_runup_5d'].notna()
    df['label_bounce_higher'] = np.where(ru_valid, (df['fwd_max_runup_5d'] > 0.02).astype(float), np.nan)
    
    # Floor/Ceiling labels (for universal t-test) — NaN-safe
    sigma = df['sigma_tide'].values
    df['is_floor'] = np.where(fwd_valid, ((sigma < -1.5) & (df['fwd_20d'] > 0.03)).astype(float), np.nan)
    df['is_ceiling'] = np.where(fwd_valid, ((sigma > 1.5) & (df['fwd_20d'] < -0.02)).astype(float), np.nan)
    
    valid = df['fwd_20d'].notna().sum()
    floors = df['is_floor'].sum()
    ceilings = df['is_ceiling'].sum()
    print(f"    Valid labels: {valid:,d} | Floors: {floors:,.0f} | Ceilings: {ceilings:,.0f}")


def sfi_analysis(df, features, label_col, label_name):
    """Single Feature Importance via AUC for each feature."""
    sp(f"SFI Analysis: {label_name} (label={label_col})")
    
    valid = df[label_col].notna() & (df[label_col] != -1)
    df_valid = df[valid].copy()
    y = df_valid[label_col].values
    
    if len(y) < 100 or y.sum() < 20:
        print(f"    ⚠️ Insufficient data: N={len(y)}, pos={y.sum()}")
        return []
    
    print(f"    N={len(y):,d} | pos_rate={y.mean():.3f}")
    
    from sklearn.metrics import roc_auc_score

    results = []
    for feat in features:
        x = df_valid[feat].values.astype(float)
        # Only filter NaN/inf — do NOT exclude zeros (vol_price_regime=0 is "Neutral", a valid state)
        valid_mask = np.isfinite(x)
        if valid_mask.sum() < 100:
            continue
        
        x_v = x[valid_mask]
        y_v = y[valid_mask]
        
        # SFI via AUC — single feature vs label
        try:
            auc = roc_auc_score(y_v, x_v)
        except ValueError:
            auc = 0.5
        
        sfi = abs(auc - 0.5)
        
        results.append({
            'feature': feat,
            'auc': auc,
            'sfi': sfi,
            'n_valid': int(valid_mask.sum()),
        })
    
    results.sort(key=lambda x: x['sfi'], reverse=True)
    
    print(f"\n    {'Feature':<30s} │ {'AUC':>6s} │ {'SFI':>6s} │ {'N':>7s} │ {'Dir':>5s}")
    print(f"    {'─'*65}")
    for r in results:
        direction = "↑" if r['auc'] > 0.5 else "↓" if r['auc'] < 0.5 else "—"
        star = "★★★" if r['sfi'] > 0.10 else "★★" if r['sfi'] > 0.05 else "★" if r['sfi'] > 0.02 else ""
        print(f"    {r['feature']:<30s} │ {r['auc']:>5.3f} │ {r['sfi']:>5.3f} │ {r['n_valid']:>7,d} │ {direction:>3s} {star}")
    
    return results


def ttest_at_extremes(df, features):
    """T-test: feature values at floors vs non-floors, ceilings vs non-ceilings."""
    sp("T-Test at Extremes (Floors & Ceilings)")
    
    floors = df['is_floor'] == 1
    ceilings = df['is_ceiling'] == 1
    normal = (df['is_floor'] == 0) & (df['is_ceiling'] == 0)
    
    print(f"    Floors: {floors.sum():,d} | Ceilings: {ceilings.sum():,d} | Normal: {normal.sum():,d}")
    
    results = []
    for feat in features:
        x = df[feat].values.astype(float)
        
        # Floor t-test
        x_floor = x[floors.values & np.isfinite(x)]
        x_normal = x[normal.values & np.isfinite(x)]
        
        if len(x_floor) > 20 and len(x_normal) > 100:
            t_floor, p_floor = scipy_stats.ttest_ind(x_floor, x_normal, equal_var=False)
        else:
            t_floor, p_floor = 0, 1
        
        # Ceiling t-test
        x_ceiling = x[ceilings.values & np.isfinite(x)]
        if len(x_ceiling) > 20 and len(x_normal) > 100:
            t_ceil, p_ceil = scipy_stats.ttest_ind(x_ceiling, x_normal, equal_var=False)
        else:
            t_ceil, p_ceil = 0, 1
        
        results.append({
            'feature': feat,
            't_floor': t_floor,
            'p_floor': p_floor,
            't_ceiling': t_ceil,
            'p_ceiling': p_ceil,
            'mean_floor': np.mean(x_floor) if len(x_floor) > 0 else 0,
            'mean_normal': np.mean(x_normal) if len(x_normal) > 0 else 0,
            'mean_ceiling': np.mean(x_ceiling) if len(x_ceiling) > 0 else 0,
        })
    
    results.sort(key=lambda x: abs(x['t_floor']), reverse=True)
    
    print(f"\n    {'Feature':<30s} │ {'t(floor)':>9s} │ {'p':>8s} │ {'t(ceil)':>9s} │ {'p':>8s} │ {'μ_floor':>8s} │ {'μ_norm':>8s} │ {'μ_ceil':>8s}")
    print(f"    {'─'*115}")
    for r in results:
        star_f = "★★★" if abs(r['t_floor']) > 10 else "★★" if abs(r['t_floor']) > 5 else "★" if abs(r['t_floor']) > 2 else ""
        star_c = "★★★" if abs(r['t_ceiling']) > 10 else "★★" if abs(r['t_ceiling']) > 5 else "★" if abs(r['t_ceiling']) > 2 else ""
        print(f"    {r['feature']:<30s} │ {r['t_floor']:>+8.2f} │ {r['p_floor']:>8.1e} │ {r['t_ceiling']:>+8.2f} │ {r['p_ceiling']:>8.1e} │ {r['mean_floor']:>8.4f} │ {r['mean_normal']:>8.4f} │ {r['mean_ceiling']:>8.4f} {star_f} {star_c}")
    
    return results


def orthogonality_check(df, features, existing_features):
    """Check correlation between new vol-price features and existing features."""
    sp("Orthogonality Check (vs existing features)")
    
    # Top existing features from the optimizer
    existing_top = [f for f in existing_features if f in df.columns][:15]
    
    print(f"    New features: {len(features)} | Existing reference: {len(existing_top)}")
    
    results = {}
    for new_f in features:
        if new_f not in df.columns:
            continue
        max_corr = 0
        max_corr_with = ""
        for exist_f in existing_top:
            if exist_f not in df.columns:
                continue
            valid = np.isfinite(df[new_f].values) & np.isfinite(df[exist_f].values)
            if valid.sum() < 100:
                continue
            corr = abs(np.corrcoef(df[new_f].values[valid], df[exist_f].values[valid])[0, 1])
            if corr > max_corr:
                max_corr = corr
                max_corr_with = exist_f
        
        results[new_f] = {'max_corr': max_corr, 'with': max_corr_with}
        
        ortho = "✅ ORTHOGONAL" if max_corr < 0.3 else "⚠️ MODERATE" if max_corr < 0.6 else "❌ REDUNDANT"
        print(f"    {new_f:<30s}: max|r|={max_corr:.3f} vs {max_corr_with:<25s} {ortho}")
    
    return results


def main():
    t0 = time.time()
    p("FORENCIA VOL-PRICE CORRELATION — Challenger v3 Feature Discovery")
    
    store = TimescaleDataStore()
    
    # 1. Load data
    df = load_data(store)
    
    # 2. Compute vol-price features
    vol_features = compute_vol_price_features(df)
    
    # 3. Compute labels
    compute_labels(df, store)
    
    # 4. SFI Analysis per label type
    sfi_long = sfi_analysis(df, vol_features, 'label_long_entry', 'Long Entry (20d > 0)')
    sfi_pullback = sfi_analysis(df, vol_features, 'label_pullback_deepen', 'Pullback Deepen (DD 5d > -2%)')
    sfi_bounce = sfi_analysis(df, vol_features, 'label_bounce_higher', 'Bounce Higher (Runup 5d > +2%)')
    
    # 5. T-test at extremes
    ttest_results = ttest_at_extremes(df, vol_features)
    
    # 6. Orthogonality check vs existing top features
    existing_reference = [
        'sigma_tide', 'tide_slope', 'rsi_value', 'compression_ratio',
        'fear_level', 'vol_up_down_ratio', 'sigma_current', 'tension_tide',
        'wave_slope', 'vwap_sigma_tide', 'kalman_velocity', 'vol_adj_delta',
        'tide_accel', 'current_slope', 'spread_tide_wave',
    ]
    ortho = orthogonality_check(df, vol_features, existing_reference)
    
    # 7. Cross-feature correlations within the vol-price family
    sp("Internal Correlation Matrix (vol-price features)")
    vol_data = df[vol_features].dropna()
    if len(vol_data) > 100:
        corr_matrix = vol_data.corr()
        print(f"\n    {'':>30s}", end="")
        for f in vol_features:
            print(f" {f[:6]:>7s}", end="")
        print()
        for f1 in vol_features:
            print(f"    {f1:<30s}", end="")
            for f2 in vol_features:
                r = corr_matrix.loc[f1, f2]
                marker = "█" if abs(r) > 0.7 else "▓" if abs(r) > 0.4 else "░" if abs(r) > 0.2 else " "
                print(f" {r:>+6.2f}{marker}", end="")
            print()
    
    # 8. DICTAMEN
    sp("DICTAMEN FINAL")
    
    # Rank features by combined score: SFI(long) + |t_floor| + orthogonality_bonus
    combined = {}
    for feat in vol_features:
        sfi_score = 0
        for result_set in [sfi_long, sfi_pullback, sfi_bounce]:
            match = [r for r in result_set if r['feature'] == feat]
            if match:
                sfi_score += match[0]['sfi']
        
        t_match = [r for r in ttest_results if r['feature'] == feat]
        t_score = abs(t_match[0]['t_floor']) if t_match else 0
        
        ortho_bonus = 1.0
        if feat in ortho:
            if ortho[feat]['max_corr'] > 0.6:
                ortho_bonus = 0.3  # Penalize redundant
            elif ortho[feat]['max_corr'] > 0.3:
                ortho_bonus = 0.7
        
        combined[feat] = {
            'sfi_total': sfi_score,
            't_floor': t_score,
            'ortho': ortho.get(feat, {}).get('max_corr', 0),
            'combined': (sfi_score * 100 + t_score) * ortho_bonus
        }
    
    ranked = sorted(combined.items(), key=lambda x: x[1]['combined'], reverse=True)
    
    print(f"\n    {'Rank':>4s} │ {'Feature':<30s} │ {'SFI_sum':>8s} │ {'|t_floor|':>9s} │ {'max|r|':>7s} │ {'Combined':>9s} │ Verdict")
    print(f"    {'─'*110}")
    for rank, (feat, scores) in enumerate(ranked, 1):
        verdict = "✅ APPROVE" if scores['combined'] > 3.0 and scores['ortho'] < 0.5 else \
                  "⚠️ MARGINAL" if scores['combined'] > 1.5 else \
                  "❌ REJECT"
        print(f"    {rank:>4d} │ {feat:<30s} │ {scores['sfi_total']:>7.4f} │ {scores['t_floor']:>8.2f} │ {scores['ortho']:>6.3f} │ {scores['combined']:>8.2f} │ {verdict}")
    
    store.close()
    elapsed = time.time() - t0
    p(f"FORENCIA COMPLETA — {elapsed:.1f}s ({elapsed/60:.1f} min)")


if __name__ == "__main__":
    main()
