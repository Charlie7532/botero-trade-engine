#!/usr/bin/env python3
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from sqlalchemy import text

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "backend" / "scripts"))

from dotenv import load_dotenv
load_dotenv(root / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore
from unified_pretrainer_v2 import load_feature_lake

def load_zigzag_legs(store):
    zz = pd.read_sql(
        text("SELECT ticker, timestamp, tp_type, price "
             "FROM engine.zigzag_points "
             "WHERE min_swing_pct = 0.05 "
             "ORDER BY ticker, timestamp"),
        store.engine
    )
    results = []
    for ticker in zz['ticker'].unique():
        tk = zz[zz['ticker'] == ticker].sort_values('timestamp').reset_index(drop=True)
        for i in range(1, len(tk) - 1):
            row = tk.iloc[i]
            prev = tk.iloc[i-1]
            nxt = tk.iloc[i+1]
            
            prev_price = float(prev['price'])
            curr_price = float(row['price'])
            nxt_price = float(nxt['price'])
            
            prev_leg = (curr_price / prev_price - 1) * 100
            nxt_leg = (nxt_price / curr_price - 1) * 100
            
            results.append({
                'ticker': ticker,
                'timestamp': row['timestamp'],
                'tp_type': row['tp_type'],
                'price': curr_price,
                'prev_leg_pct': prev_leg,
                'next_leg_pct': nxt_leg,
            })
    return pd.DataFrame(results)

def main():
    store = TimescaleDataStore()
    ps = TickerProfileStore()
    
    print("Loading Feature Lake and Zigzag legs...")
    df, _, _ = load_feature_lake(store, ps)
    zz_legs = load_zigzag_legs(store)
    
    print(f"Loaded {len(df):,d} feature rows.")
    print(f"Loaded {len(zz_legs):,d} zigzag turns.")
    
    # Audit BOTTOMS at t-7 by Slope combinations
    bottoms = zz_legs[zz_legs['tp_type'] == 'MIN'].copy()
    
    slope_groups = []
    
    for _, leg in bottoms.iterrows():
        ticker = leg['ticker']
        ts = leg['timestamp']
        opp = abs(leg['next_leg_pct'])
        
        tk_df = df[df['ticker'] == ticker]
        if len(tk_df) == 0:
            continue
            
        time_diffs = np.abs((tk_df['timestamp'].values - np.datetime64(ts)).astype('timedelta64[D]').astype(int))
        closest = time_diffs.argmin()
        if time_diffs[closest] > 4:
            continue
            
        # Analyze t-7 relative to the turn
        t7_pos = closest - 7
        if t7_pos < 0 or t7_pos >= len(tk_df):
            continue
            
        t7_idx = tk_df.index[t7_pos]
        
        tide = tk_df.at[t7_idx, 'tide_slope']
        curr = tk_df.at[t7_idx, 'current_slope']
        wave = tk_df.at[t7_idx, 'wave_slope']
        
        # Binary state of slopes
        tide_sign = '+' if tide > 0 else '-'
        curr_sign = '+' if curr > 0 else '-'
        wave_sign = '+' if wave > 0 else '-'
        
        slope_state = f"Tide({tide_sign}) Curr({curr_sign}) Wave({wave_sign})"
        
        # Verify if below all vwaps at t-7
        below_vwaps = tk_df.at[t7_idx, 'below_all_vwaps_int'] if 'below_all_vwaps_int' in tk_df.columns else 0
        
        # Calculate drift from t-7 to t=0
        p_t7 = tk_df.at[t7_idx, 'price']
        p_t0 = leg['price']
        drift = (p_t0 / p_t7 - 1) * 100
        
        # Is it a successful Higher Low or a Lower Low?
        # A bottom is Higher Low if its price is above the previous MIN
        # We can also classify success by the next leg size: since min_swing_pct = 5%,
        # next_leg is always > 5% alcista for bottoms! The real risk is the drift.
        
        slope_groups.append({
            'slope_state': slope_state,
            'drift': drift,
            'opp': opp,
            'below_vwaps': below_vwaps
        })
        
    df_sg = pd.DataFrame(slope_groups)
    
    print("\n" + "=" * 90)
    print("  AUDIT OF BOTTOM CAPITULATION AT t-7 BY REGRESSION SLOPES")
    print("=" * 90)
    print(f"{'Slope Combination at t-7':35s} │ {'Turns':>5s} │ {'Avg Drift':>10s} │ {'Worst Drift':>12s} │ {'Avg Opp':>7s}")
    print("-" * 90)
    
    grouped = df_sg.groupby('slope_state')
    for name, group in grouped:
        print(f"  {name:35s} │ {len(group):5d} │ {group['drift'].mean():>9.2f}% │ {group['drift'].min():>11.2f}% │ {group['opp'].mean():>6.1f}%")
        
    # Analyze the 4 Stable Gates and their win rates/positive rates in optimization results
    print("\n" + "=" * 90)
    print("  STABLE GATES WIN RATES & METRICS")
    print("=" * 90)
    
    # We can calculate the positive rate (label == 1 rate) in the historical dataset
    # for each of the 4 stable gates' targets:
    # swing_exit, short_entry, bounce_height, trend_reversal
    
    # swing_exit label: price falls below threshold in window (exit long)
    # short_entry label: short entry is profitable
    # bounce_height label: bounce size is significant
    # trend_reversal label: major trend change
    
    # Let's count positive rates in the feature lake
    for col, label in [
        ('p_swing_exit', 'Swing Exit (Exit Long)'),
        ('p_short_entry', 'Short Entry (Go Short)'),
        ('p_bounce_height', 'Bounce Height (Bounce Size)'),
        ('p_trend_reversal', 'Trend Reversal (Major Turn)')
    ]:
        if col in df.columns:
            vals = df[col].dropna()
            pos_rate = (vals == 1).mean() * 100
            print(f"  {label:35s} │ Active Rows: {len(vals):6d} │ Hit Rate (Positive Rate): {pos_rate:>5.2f}%")
        else:
            print(f"  {label:35s} │ Feature not found in lake")
            
    store.close()
    ps.close()

if __name__ == "__main__":
    main()
