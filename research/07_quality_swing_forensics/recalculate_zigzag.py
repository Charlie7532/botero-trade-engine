#!/usr/bin/env python3
"""
Recalculate Zigzag Points — Only SPY and QQQ
====================================================================
Step 3 of the Remediation Plan:
  1. Delete existing zigzag points for SPY & QQQ in engine.zigzag_points
  2. Compute and persist new clean zigzag points at 3%, 5%, 7% swings
"""
import os, sys, time
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "backend" / "scripts"))

from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
import pandas as pd
from sqlalchemy import text as sa_text
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from build_zigzag_benchmark import zigzag

TICKERS = ["SPY", "QQQ"]
SWING_PCTS = [0.03, 0.05, 0.07]

def main():
    print("=" * 80)
    print("  RECALCULATING ZIGZAG POINTS FOR SPY & QQQ ONLY")
    print("=" * 80)
    
    store = TimescaleDataStore()
    conn = store.engine.raw_connection()
    cur = conn.cursor()
    
    try:
        # 1. PURGE ZIGZAG POINTS
        print("\n1. PURGING OLD ZIGZAG POINTS FOR SPY & QQQ...")
        cur.execute("DELETE FROM engine.zigzag_points WHERE ticker IN ('SPY', 'QQQ');")
        purged = cur.rowcount
        conn.commit()
        print(f"   ✅ Purged {purged:,d} zigzag points for SPY and QQQ.")
        
        # 2. LOAD CLEAN OHLCV
        print("\n2. LOADING CLEAN OHLCV DATA...")
        ohlcv = pd.read_sql("""
            SELECT ticker, time as timestamp, close 
            FROM market.ohlcv_bars 
            WHERE ticker IN ('SPY', 'QQQ') AND timeframe='1d' 
            ORDER BY ticker, time
        """, store.engine)
        print(f"   Loaded {len(ohlcv):,d} clean OHLCV bars.")
        
        # 3. COMPUTE AND SAVE ZIGZAGS
        print("\n3. COMPUTING ZIGZAG POINTS...")
        total_points = 0
        
        for ticker in TICKERS:
            tk_data = ohlcv[ohlcv['ticker'] == ticker].sort_values('timestamp').reset_index(drop=True)
            close = tk_data['close'].values.astype(float)
            timestamps = tk_data['timestamp'].values
            
            if len(close) < 100:
                print(f"   ⚠️ {ticker}: skipped (only {len(close)} bars)")
                continue
            
            for min_sw in SWING_PCTS:
                pts = zigzag(close, min_sw)
                
                rows = []
                for j, (idx, tp_type, val) in enumerate(pts):
                    if idx >= len(timestamps):
                        continue
                    
                    # Compute swing parameters
                    swing_ret = None
                    swing_days = None
                    swing_speed = None
                    if j + 1 < len(pts):
                        next_idx, _, next_val = pts[j+1]
                        if next_idx < len(timestamps):
                            swing_ret = next_val / val - 1
                            swing_days = next_idx - idx
                            swing_speed = swing_ret / max(swing_days, 1)
                    
                    rows.append({
                        'ticker': ticker,
                        'timestamp': pd.Timestamp(timestamps[idx]),
                        'tp_type': tp_type,
                        'price': float(val),
                        'min_swing_pct': min_sw,
                        'swing_return': swing_ret,
                        'swing_days': swing_days,
                        'swing_speed': swing_speed,
                    })
                
                if rows:
                    df_rows = pd.DataFrame(rows)
                    # Convert pandas Timestamp to string to avoid DB driver conversions
                    df_rows['timestamp'] = df_rows['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S%z')
                    
                    # Insert in batches using cursor executemany
                    insert_query = """
                        INSERT INTO engine.zigzag_points 
                        (ticker, timestamp, tp_type, price, min_swing_pct, swing_return, swing_days, swing_speed)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    data_tuples = []
                    for _, r in df_rows.iterrows():
                        ticker_val = r['ticker']
                        ts_val = r['timestamp']
                        tp_val = r['tp_type']
                        price_val = float(r['price'])
                        min_sw_val = float(r['min_swing_pct'])
                        
                        ret_val = float(r['swing_return']) if pd.notna(r['swing_return']) else None
                        days_val = int(r['swing_days']) if pd.notna(r['swing_days']) else None
                        speed_val = float(r['swing_speed']) if pd.notna(r['swing_speed']) else None
                        
                        data_tuples.append((
                            ticker_val, ts_val, tp_val, price_val, min_sw_val,
                            ret_val, days_val, speed_val
                        ))
                    cur.executemany(insert_query, data_tuples)
                    total_points += len(rows)
                    
                    mins = sum(1 for r in rows if r['tp_type'] == 'MIN')
                    maxs = sum(1 for r in rows if r['tp_type'] == 'MAX')
                    print(f"   ✅ {ticker} ({min_sw*100:.0f}%): {mins} MIN + {maxs} MAX = {len(rows)} points saved.")
                    
        conn.commit()
        print(f"\n🎉 ALL ZIGZAG POINTS RECALCULATED: {total_points:,d} points saved!")
        
        # 4. STATISTICAL SUMMARY
        print("\n4. POST-RECALCULATION STATS (5% swing):")
        cur.execute("""
            SELECT ticker, tp_type, COUNT(*), ROUND((AVG(ABS(swing_return))*100)::numeric, 2) as avg_swing_pct
            FROM engine.zigzag_points 
            WHERE ticker IN ('SPY', 'QQQ') AND min_swing_pct = 0.05
            GROUP BY ticker, tp_type
            ORDER BY ticker, tp_type;
        """)
        rows = cur.fetchall()
        for r in rows:
            ticker, tp_type, count, avg_swing = r
            print(f"   {ticker} ({tp_type}): {count} turns, avg swing size = {avg_swing}%")
            
    except Exception as e:
        conn.rollback()
        print(f"🔴 ERROR: Zigzag recalculation failed: {str(e)}")
    finally:
        cur.close()
        conn.close()
        store.close()

if __name__ == "__main__":
    main()
