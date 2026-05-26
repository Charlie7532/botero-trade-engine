import sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "backend" / "scripts"))

from dotenv import load_dotenv
load_dotenv(root / ".env")

import numpy as np
import pandas as pd
from build_zigzag_benchmark import zigzag
from unified_pretrainer_v2 import load_feature_lake
from feature_optimizer import expand_feature_lake
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore

def analyze_zigzag_bottoms():
    store = TimescaleDataStore()
    ps = TickerProfileStore()
    
    # 1. Load data
    print("Loading data from database...")
    df, ohlcv_cache, profiles = load_feature_lake(store, ps)
    
    # Reset index to guarantee a unique, clean integer index
    df = df.reset_index(drop=True)
    
    # Generate derived features (Phase 0)
    new_features = expand_feature_lake(df)
    
    # Pre-compute naive timestamp ONCE
    df['ts_naive'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)
    
    # Pre-group by ticker and sort by ts_naive (preserving original df index)
    tk_groups = {tk: group.sort_values('ts_naive') for tk, group in df.groupby('ticker')}
    
    # 2. Compute ZigZag for 5%, 10%, 15%, and 20% for all tickers
    print("\nComputing ZigZag 5%, 10%, 15%, and 20% bottoms...")
    thresholds = [0.05, 0.10, 0.15, 0.20]
    all_turns = []
    
    for ticker in df['ticker'].unique():
        ohlc = ohlcv_cache.get(ticker)
        if ohlc is None:
            continue
        closes = ohlc['close'].values.astype(float)
        timestamps = ohlc.index.values
        
        for swing_pct in thresholds:
            pts = zigzag(closes, swing_pct)
            for idx, tp_type, val in pts:
                if tp_type == 'MIN':  # Only bottoms (Long Entry points)
                    all_turns.append({
                        'ticker': ticker,
                        'timestamp': pd.Timestamp(timestamps[idx]),
                        'swing_pct': swing_pct,
                        'price': val
                    })
                    
    df_turns = pd.DataFrame(all_turns)
    print(f"Total ZigZag MIN points found: {len(df_turns)}")
    for sw in thresholds:
        print(f"  - {sw*100:.0f}% threshold: {len(df_turns[df_turns['swing_pct']==sw])} points")
        
    # 3. Match turning points to feature snapshots (Vector-optimized)
    print("\nMatching turning points to feature snapshots...")
    
    indices_to_extract = []
    offsets_list = []
    swing_pcts_list = []
    turn_timestamps_list = []
    
    for _, turn in df_turns.iterrows():
        ticker = turn['ticker']
        ts = pd.Timestamp(turn['timestamp']).tz_localize(None)
        swing_pct = turn['swing_pct']
        
        tk_df = tk_groups.get(ticker)
        if tk_df is None or tk_df.empty:
            continue
            
        # Fast index lookup using binary search on ts_naive values
        ts_naive_vals = tk_df['ts_naive'].values
        idx_0 = np.searchsorted(ts_naive_vals, np.datetime64(ts))
        if idx_0 >= len(tk_df):
            idx_0 = len(tk_df) - 1
            
        # Double check date match is within 3 days
        match_ts = pd.Timestamp(ts_naive_vals[idx_0])
        if abs((match_ts - ts).days) <= 3:
            for offset in range(-3, 4):
                target_idx = idx_0 + offset
                if 0 <= target_idx < len(tk_df):
                    df_idx = tk_df.index[target_idx]
                    indices_to_extract.append(df_idx)
                    offsets_list.append(offset)
                    swing_pcts_list.append(swing_pct)
                    turn_timestamps_list.append(ts)
                    
    # Single, vectorized slice of the main DataFrame
    df_matched = df.loc[indices_to_extract].copy()
    df_matched['offset'] = offsets_list
    df_matched['swing_pct'] = swing_pcts_list
    df_matched['turn_timestamp'] = turn_timestamps_list
    
    print(f"Matched snapshots window: {len(df_matched):,d} rows")
    
    # 4. Compare feature values at the exact bottom (Offset = 0) across all thresholds
    key_features = [
        'sigma_tide', 'sigma_current', 'sigma_wave',
        'tension_tide', 'tide_slope', 'current_slope', 'wave_slope',
        'rsi_value', 'fear_level', 'kalman_velocity', 'vol_up_down_ratio',
        'compression_ratio', 'd_tide_slope', 'slope_energy', 'slope_product_tc',
        'complacency_index', 'bullish_score', 'price_vwap_div'
    ]
    
    df_offset_0 = df_matched[df_matched['offset'] == 0]
    
    print("\n" + "="*115)
    print("  COMPARATIVE FORENSIC SIGNATURE AT THE EXACT BOTTOM (OFFSET=0) ACROSS SWING THRESHOLDS")
    print("="*115)
    print(f"{'Feature':<25s} │ {'5% Bottom (Med)':>18s} │ {'10% Bottom (Med)':>18s} │ {'15% Bottom (Med)':>18s} │ {'20% Bottom (Med)':>18s}")
    print("-" * 115)
    
    for feat in key_features:
        if feat not in df_offset_0.columns:
            continue
            
        row_str = f"{feat:<25s} │ "
        for sw in thresholds:
            sub = df_offset_0[df_offset_0['swing_pct'] == sw]
            if len(sub) > 0:
                med_val = np.nanmedian(sub[feat].values.astype(float))
                row_str += f"{med_val:>18.4f} │ "
            else:
                row_str += f"{'N/A':>18s} │ "
        print(row_str)
        
    # 5. Look at TIME SERIES DYNAMICS (Offset -3 to +3) specifically for 10%, 15% and 20%
    for sw in [0.10, 0.15, 0.20]:
        print("\n" + "="*115)
        print(f"  TIME DYNAMICS LEAD/LAG FOR ZIGZAG {sw*100:.0f}% BOTTOMS")
        print("="*115)
        print(f"{'Feature':<25s} │ {'T-3':>8s} │ {'T-2':>8s} │ {'T-1':>8s} │ {'T=0 (Bottom)':>12s} │ {'T+1':>8s} │ {'T+2':>8s} │ {'T+3':>8s}")
        print("-" * 105)
        
        df_sw = df_matched[df_matched['swing_pct'] == sw]
        for feat in key_features:
            if feat not in df_sw.columns:
                continue
                
            row_str = f"{feat:<25s} │ "
            for offset in range(-3, 4):
                offset_df = df_sw[df_sw['offset'] == offset]
                if len(offset_df) > 0:
                    med_val = np.nanmedian(offset_df[feat].values.astype(float))
                    if offset == 0:
                        row_str += f"\033[1m{med_val:>11.4f}\033[0m │ "
                    else:
                        row_str += f"{med_val:>8.4f} │ "
                else:
                    row_str += f"{'N/A':>8s} │ "
            print(row_str)
            
    store.close()
    ps.close()

if __name__ == "__main__":
    analyze_zigzag_bottoms()
