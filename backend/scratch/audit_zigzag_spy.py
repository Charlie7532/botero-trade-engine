#!/usr/bin/env python3
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from sqlalchemy import text

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))

from dotenv import load_dotenv
load_dotenv(root / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

def zigzag(close: np.ndarray, min_pct: float = 0.03):
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
        else:  # MAX
            if close[i] < last_val * (1 - min_pct):
                pts.append((last_idx, 'MAX', last_val))
                best = last_idx + int(np.argmin(close[last_idx:i+1]))
                last_idx, last_type, last_val = best, 'MIN', close[best]
            elif close[i] > last_val:
                last_idx, last_val = i, close[i]
    return pts

def main():
    store = TimescaleDataStore()
    
    # 1. Load SPY daily close prices
    print("Loading SPY daily bars...")
    ohlcv = pd.read_sql(
        text("SELECT time as timestamp, close "
             "FROM market.ohlcv_bars "
             "WHERE ticker = 'SPY' AND timeframe = '1d' "
             "ORDER BY time"),
        store.engine
    )
    print(f"Loaded {len(ohlcv)} bars.")
    
    close = ohlcv['close'].values.astype(float)
    timestamps = ohlcv['timestamp'].values
    
    # 2. Compute Zigzag locally
    min_pct = 0.05
    print(f"Computing local zigzag (min_pct = {min_pct:.0%})...")
    local_pts = zigzag(close, min_pct)
    
    local_rows = []
    for idx, tp_type, val in local_pts:
        local_rows.append({
            'timestamp': pd.Timestamp(timestamps[idx]),
            'tp_type': tp_type,
            'price_calc': round(val, 4)
        })
    df_calc = pd.DataFrame(local_rows)
    print(f"Calculated {len(df_calc)} turning points.")
    
    # 3. Load DB Zigzag
    print("Loading DB zigzag from engine.zigzag_points...")
    df_db = pd.read_sql(
        text("SELECT timestamp, tp_type, price as price_db "
             "FROM engine.zigzag_points "
             "WHERE ticker = 'SPY' AND min_swing_pct = :pct "
             "ORDER BY timestamp"),
        store.engine,
        params={'pct': min_pct}
    )
    df_db['timestamp'] = pd.to_datetime(df_db['timestamp'])
    print(f"Loaded {len(df_db)} turning points from DB.")
    
    # Convert timestamps in both to date string for robust comparison
    df_calc['date'] = df_calc['timestamp'].dt.strftime('%Y-%m-%d')
    df_db['date'] = df_db['timestamp'].dt.strftime('%Y-%m-%d')
    
    # Merge on Date and Type to compare prices and find mismatches
    merged = pd.merge(df_calc, df_db, on=['date', 'tp_type'], how='outer', suffixes=('_calc', '_db'))
    merged = merged.sort_values('date').reset_index(drop=True)
    
    print("\nAuditing results...")
    exact_matches = 0
    only_calc = 0
    only_db = 0
    price_diffs = 0
    
    for i, row in merged.iterrows():
        calc_exists = not pd.isna(row['price_calc'])
        db_exists = not pd.isna(row['price_db'])
        
        if calc_exists and db_exists:
            diff = abs(row['price_calc'] - row['price_db'])
            if diff < 1e-4:
                exact_matches += 1
            else:
                price_diffs += 1
        elif calc_exists:
            only_calc += 1
        elif db_exists:
            only_db += 1
            
    print(f"Exact Matches (Date, Type, Price): {exact_matches}")
    print(f"Price Mismatches:                  {price_diffs}")
    print(f"Points only in Calculated:         {only_calc}")
    print(f"Points only in DB:                 {only_db}")
    
    # Output the last 20 points in Detail for audit report
    print("\nLast 20 Turning Points Comparison:")
    print(f"{'Date':12s} | {'Type':4s} | {'Price Calc':10s} | {'Price DB':10s} | {'Status'}")
    print("-" * 60)
    for i, row in merged.tail(20).iterrows():
        calc_exists = not pd.isna(row['price_calc'])
        db_exists = not pd.isna(row['price_db'])
        
        p_calc = f"{row['price_calc']:10.2f}" if calc_exists else f"{'—':10s}"
        p_db = f"{row['price_db']:10.2f}" if db_exists else f"{'—':10s}"
        
        if calc_exists and db_exists:
            diff = abs(row['price_calc'] - row['price_db'])
            status = "MATCH" if diff < 1e-4 else f"DIFF: {diff:.2f}"
        elif calc_exists:
            status = "ONLY_CALC"
        else:
            status = "ONLY_DB"
            
        print(f"{row['date']:12s} | {row['tp_type']:4s} | {p_calc} | {p_db} | {status}")
        
    store.close()

if __name__ == "__main__":
    main()
