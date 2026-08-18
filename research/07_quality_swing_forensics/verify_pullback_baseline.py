#!/usr/bin/env python3
"""
Prueba A/B: ¿Se reproduce el DSR=48.578 de producción para pullback_depth?
Also: reproduce production features for zz_top_detector (DSR=10.198).

This test directly evaluates the PRODUCTION feature sets through the SAME
pipeline V4 uses (train_quick with n_splits=5), to determine if:
  A) The production DSR was inflated by different parameters → baseline bug
  B) The forward selection is greedy and destroys synergies → methodology bug
"""
import sys, warnings, time
from pathlib import Path
warnings.filterwarnings("ignore")

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "backend" / "scripts"))

from dotenv import load_dotenv
load_dotenv(root / ".env")

import numpy as np
import pandas as pd

from unified_pretrainer_v2 import (
    load_feature_lake, HEAD_CONFIGS,
    label_pullback_depth, label_zz_turning_point, label_long_entry,
    apply_context, purged_walk_forward_cv, compute_dsr,
)
from feature_optimizer import expand_feature_lake, train_quick
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore


def test_head(head_name, df, df_ctx, labels_ctx, production_features, horizon):
    """Test production features directly through V4 pipeline."""
    print(f"\n{'='*70}")
    print(f"  TESTING: {head_name.upper()}")
    print(f"  Production features: {production_features}")
    print(f"  Horizon: {horizon}d | Context rows: {len(df_ctx):,d}")
    print(f"{'='*70}")
    
    # Test 1: Exact production features
    result = train_quick(df_ctx, labels_ctx, production_features, horizon, n_splits=5, mode='dsr')
    if result:
        print(f"  DSR (V4 pipeline, 5 folds): {result['dsr']:.4f}")
        print(f"  Fold sharpes: {[round(s,4) for s in result['fold_sharpes']]}")
        print(f"  Mean AUC: {result['mean_auc']:.4f}")
    
    # Test 2: Same features, 7 folds (sensitivity)
    result7 = train_quick(df_ctx, labels_ctx, production_features, horizon, n_splits=7, mode='dsr')
    if result7:
        print(f"  DSR (V4 pipeline, 7 folds): {result7['dsr']:.4f}")
        print(f"  Fold sharpes: {[round(s,4) for s in result7['fold_sharpes']]}")
    
    # Test 3: Same features, 3 folds (as SFI uses)
    result3 = train_quick(df_ctx, labels_ctx, production_features, horizon, n_splits=3, mode='dsr')
    if result3:
        print(f"  DSR (V4 pipeline, 3 folds): {result3['dsr']:.4f}")
        print(f"  Fold sharpes: {[round(s,4) for s in result3['fold_sharpes']]}")
    
    return result


def main():
    print("Loading data...")
    store = TimescaleDataStore()
    ps = TickerProfileStore()
    df, ohlcv_cache, profiles = load_feature_lake(store, ps)
    
    print("Expanding feature lake...")
    expand_feature_lake(df)
    
    # ── PULLBACK_DEPTH ──
    print("\nComputing pullback_depth labels...")
    labels_pd = np.array(label_pullback_depth(df, ohlcv_cache), dtype=float)
    ctx_pd = apply_context(df, 'pullback_depth')
    df_ctx_pd = df[ctx_pd].copy()
    labels_ctx_pd = labels_pd[ctx_pd.values]
    print(f"  Context: {ctx_pd.sum():,d} / {len(df):,d} rows")
    print(f"  Pos rate: {labels_ctx_pd[~np.isnan(labels_ctx_pd)].mean():.3f}")
    
    test_head('pullback_depth', df, df_ctx_pd, labels_ctx_pd,
              ['atr_ratio', 'volume_trend', 'sigma_ratio_tw'],
              horizon=5)
    
    # ── ZZ_TOP_DETECTOR ──
    print("\nComputing zz_top labels...")
    labels_zt = np.array(label_zz_turning_point(df, store, tp_type='MAX', proximity_window=3), dtype=float)
    ctx_zt = apply_context(df, 'zz_top_detector')
    df_ctx_zt = df[ctx_zt].copy()
    labels_ctx_zt = labels_zt[ctx_zt.values]
    
    test_head('zz_top_detector', df, df_ctx_zt, labels_ctx_zt,
              ['atr_ratio', 'sigma_high_current', 'overnight_gap', 'vol_return_interaction',
               'wave_accel', 'rsi_value', 'vol_adj_delta', 'compr_at_extreme',
               'vol_up_down_ratio', 'adi_tide', 'tide_slope_sq', 'volume_trend'],
              horizon=3)
    
    # ── LONG_ENTRY ──
    print("\nComputing long_entry labels...")
    labels_le = np.array(label_long_entry(df, ohlcv_cache, horizon=20), dtype=float)
    ctx_le = apply_context(df, 'long_entry')
    df_ctx_le = df[ctx_le].copy()
    labels_ctx_le = labels_le[ctx_le.values]
    print(f"  Pos rate: {labels_ctx_le[~np.isnan(labels_ctx_le)].mean():.3f}")
    
    test_head('long_entry', df, df_ctx_le, labels_ctx_le,
              ['sigma_high_tide', 'tsi_current', 'reg_value_tide',
               'div_close_low_tide', 'conj_wave_current', 'vol_price_divergence'],
              horizon=20)
    
    store.close()
    ps.close()
    print("\n★ VERIFICATION COMPLETE")


if __name__ == "__main__":
    main()
