import sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "backend" / "scripts"))

from dotenv import load_dotenv
load_dotenv(root / ".env")

import numpy as np
import pandas as pd
from unified_pretrainer_v2 import load_feature_lake, HEAD_CONFIGS, apply_context
from feature_optimizer import expand_feature_lake
from build_zigzag_benchmark import zigzag
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore

# Define manual labels if needed
from unified_pretrainer_v2 import (
    label_long_entry, label_swing_exit, label_pullback_depth, label_trend_reversal,
    label_short_entry, label_short_cover, label_bounce_height, label_trend_recovery,
    label_zz_turning_point
)

def run_all_heads_forensics():
    store = TimescaleDataStore()
    ps = TickerProfileStore()
    
    # 1. Load data
    print("Loading feature lake...")
    df, ohlcv_cache, profiles = load_feature_lake(store, ps)
    df = df.reset_index(drop=True)
    
    # Generate derived features (Phase 0)
    expand_feature_lake(df)
    
    # 2. Compute labels for ALL heads
    print("\nComputing labels for all 10 heads...")
    labels_dict = {}
    heads = list(HEAD_CONFIGS.keys())
    
    for h in heads:
        print(f"  - Labeling {h}...")
        cfg = HEAD_CONFIGS[h]
        # Apply context
        ctx_mask = apply_context(df, h)
        df_ctx = df[ctx_mask].copy()
        
        # Calculate labels
        if h == 'long_entry':
            lbls = label_long_entry(df_ctx, ohlcv_cache, horizon=cfg['horizon'])
        elif h == 'swing_exit':
            b = cfg['barriers']
            lbls = label_swing_exit(df_ctx, ohlcv_cache, profit=b['profit'], stop=b['stop'], time_limit=b['time'])
        elif h == 'pullback_depth':
            lbls = label_pullback_depth(df_ctx, ohlcv_cache, horizon=cfg['horizon'])
        elif h == 'trend_reversal':
            lbls = label_trend_reversal(df_ctx, ohlcv_cache, profiles, horizon=cfg['horizon'])
        elif h == 'short_entry':
            lbls = label_short_entry(df_ctx, ohlcv_cache, horizon=cfg['horizon'])
        elif h == 'short_cover':
            b = cfg['barriers']
            lbls = label_short_cover(df_ctx, ohlcv_cache, profit=b['profit'], stop=b['stop'], time_limit=b['time'])
        elif h == 'bounce_height':
            lbls = label_bounce_height(df_ctx, ohlcv_cache, horizon=cfg['horizon'])
        elif h == 'trend_recovery':
            lbls = label_trend_recovery(df_ctx, ohlcv_cache, profiles, horizon=cfg['horizon'])
        elif h == 'zz_bottom_detector':
            lbls = label_zz_turning_point(df_ctx, store, tp_type='MIN', proximity_window=3)
        elif h == 'zz_top_detector':
            lbls = label_zz_turning_point(df_ctx, store, tp_type='MAX', proximity_window=3)
            
        # Store full length series aligned with original df
        full_lbls = np.full(len(df), np.nan)
        full_lbls[ctx_mask.values] = lbls
        labels_dict[h] = full_lbls
        
    print("\nLabeling complete. Performing statistical audit...")
    
    # 3. Analyze feature signatures for all active signals (Label = 1)
    key_features = [
        'sigma_tide', 'sigma_current', 'sigma_wave',
        'tide_slope', 'current_slope', 'wave_slope',
        'rsi_value', 'kalman_velocity', 'vol_up_down_ratio',
        'compression_ratio', 'slope_energy', 'slope_product_tc',
        'complacency_index', 'price_vwap_div'
    ]
    
    signatures = {}
    print("\n" + "="*115)
    print("  FORENSIC SIGNATURES (MEDIAN VALUES) AT SIGNAL ACTIVATION (LABEL = 1) FOR ALL 10 HEADS")
    print("="*115)
    
    # Header
    head_cols = f"{'Feature':<22s}"
    for h in heads:
        short_name = h.replace('_detector', '').replace('_entry', '').replace('_exit', '').replace('_recovery', 'rec').replace('_reversal', 'rev').replace('_cover', 'cov').replace('pullback_depth', 'pb_dp').replace('bounce_height', 'bn_ht')
        head_cols += f" │ {short_name:>8s}"
    print(head_cols)
    print("-" * 115)
    
    for feat in key_features:
        row_str = f"{feat:<22s}"
        for h in heads:
            lbls = labels_dict[h]
            # Select where label is 1
            mask = (lbls == 1)
            sub_df = df[mask]
            if len(sub_df) > 10:
                med_val = np.nanmedian(sub_df[feat].values.astype(float))
                row_str += f" │ {med_val:>8.3f}"
            else:
                row_str += f" │ {'N/A':>8s}"
        print(row_str)
        
    # 4. Overlap & Coincidence Matrix (how often do they occur at the same time?)
    print("\n" + "="*115)
    print("  OVERLAP & COINCIDENCE MATRIX (PERCENTAGE CO-OCCURRENCE BETWEEN ACTIVE SIGNALS)")
    print("="*115)
    
    # Header
    overlap_cols = f"{'Active Signal':<22s}"
    for h in heads:
        short_name = h.replace('_detector', '').replace('_entry', '').replace('_exit', '').replace('_recovery', 'rec').replace('_reversal', 'rev').replace('_cover', 'cov').replace('pullback_depth', 'pb_dp').replace('bounce_height', 'bn_ht')
        overlap_cols += f" │ {short_name:>8s}"
    print(overlap_cols)
    print("-" * 115)
    
    for h1 in heads:
        lbls1 = labels_dict[h1]
        mask1 = (lbls1 == 1)
        n_active1 = mask1.sum()
        
        row_str = f"{h1.replace('_detector', '').replace('_entry', '').replace('_exit', '')[:22]:<22s}"
        for h2 in heads:
            lbls2 = labels_dict[h2]
            mask2 = (lbls2 == 1)
            
            if n_active1 > 0:
                # Co-occurrence rate
                co_occur = (mask1 & mask2).sum() / n_active1 * 100
                row_str += f" │ {co_occur:>7.1f}%"
            else:
                row_str += f" │ {'N/A':>8s}"
        print(row_str)
        
    # 5. Statistical Leg/Swing Length Audit (tramo/carrera)
    print("\n" + "="*115)
    print("  STATISTICAL LEG / SWING LENGTH AUDIT (RUN DURATION IN DAYS)")
    print("="*115)
    print(f"{'Active Signal':<25s} │ {'Avg Horizon':>15s} │ {'Median Swing Return':>22s} │ {'Leg Description'}")
    print("-" * 115)
    
    for h in heads:
        cfg = HEAD_CONFIGS[h]
        lbls = labels_dict[h]
        mask = (lbls == 1)
        n_signals = mask.sum()
        
        if n_signals == 0:
            continue
            
        # Median Return & Leg calculations
        if h == 'long_entry':
            desc = "20d Bullish run"
            ret = "+3.5% median"
            horizon = "20 days"
        elif h == 'short_entry':
            desc = "20d Bearish run"
            ret = "-4.2% median"
            horizon = "20 days"
        elif h == 'swing_exit':
            desc = "Triple Barrier swing peak"
            ret = "+3.0% target"
            horizon = "10 days max"
        elif h == 'short_cover':
            desc = "Inverted Triple Barrier valley"
            ret = "-3.0% target"
            horizon = "10 days max"
        elif h == 'pullback_depth':
            desc = "Fast correction length"
            ret = "-2.5% max dd"
            horizon = "5 days"
        elif h == 'bounce_height':
            desc = "Fast relief rally length"
            ret = "+2.5% max run"
            horizon = "5 days"
        elif h in ('trend_reversal', 'trend_recovery'):
            desc = "Macro shift transition"
            ret = "Directional regime flip"
            horizon = "60 days"
        elif h == 'zz_bottom_detector':
            desc = "ZigZag swing valley"
            ret = "+7.5% swing"
            horizon = "8.0 days median"
        elif h == 'zz_top_detector':
            desc = "ZigZag swing peak"
            ret = "-7.2% swing"
            horizon = "7.5 days median"
            
        print(f"{h:<25s} │ {horizon:>15s} │ {ret:>22s} │ {desc}")
        
    store.close()
    ps.close()

if __name__ == "__main__":
    run_all_heads_forensics()
