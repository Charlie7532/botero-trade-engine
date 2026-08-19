#!/usr/bin/env python3
"""
Regenerate Sprint 1 Classified Points CSV
====================================================================
Step 4 of the Remediation Plan:
  1. Load clean 5% zigzag points from database
  2. Perform structural archetype classification (6 arquetipos)
  3. Extract RC regression signatures from engine.channel_snapshots
  4. Write clean, non-contaminated sprint1_classified_points.csv
"""
import os, sys, time
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

OUT_DIR = root_dir / "data" / "research" / "quality_swing"
CSV_PATH = OUT_DIR / "sprint1_classified_points.csv"

def classify_swing_magnitude(r):
    abs_r = abs(r)
    if abs_r < 7.0:
        return 'MINOR'
    elif abs_r < 15.0:
        return 'NORMAL'
    elif abs_r < 30.0:
        return 'MAJOR'
    else:
        return 'EXTREME'

def main():
    print("=" * 80)
    print("  REGENERATING SPRINT 1 CLASSIFIED POINTS CSV")
    print("=" * 80)
    
    store = TimescaleDataStore()
    
    print("\n1. LOADING ZIGZAG POINTS (5% SWING) FROM DATABASE...")
    zz = pd.read_sql("""
        SELECT ticker, timestamp, tp_type, price, swing_return, swing_days
        FROM engine.zigzag_points
        WHERE min_swing_pct = 0.05
        ORDER BY ticker, timestamp;
    """, store.engine)
    print(f"   Loaded {len(zz):,d} turns from the database.")
    
    print("\n2. RUNNING DETAILED ARCHETYPE CLASSIFICATION...")
    results = []
    
    for ticker in zz['ticker'].unique():
        tk_zz = zz[zz['ticker'] == ticker].sort_values('timestamp').reset_index(drop=True)
        
        # Split into bottoms (MIN) and tops (MAX) for archetype history
        bottoms = tk_zz[tk_zz['tp_type'] == 'MIN'].copy().reset_index()
        tops = tk_zz[tk_zz['tp_type'] == 'MAX'].copy().reset_index()
        
        # ── Classify Bottoms (MIN) ──
        bottom_archs = []
        bottom_full_archs = []
        for i in range(len(bottoms)):
            if i == 0:
                bottom_archs.append('LL')
                bottom_full_archs.append('LL')
            else:
                p_curr = bottoms.loc[i, 'price']
                p_prev = bottoms.loc[i-1, 'price']
                
                if p_curr > p_prev:
                    basic = 'HL'
                    prev_basic = bottom_archs[-1]
                    full = 'LL_TO_HL' if prev_basic == 'LL' else 'HL'
                else:
                    basic = 'LL'
                    full = 'LL'
                    
                bottom_archs.append(basic)
                bottom_full_archs.append(full)
                
        bottoms['archetype'] = bottom_archs
        bottoms['full_archetype'] = bottom_full_archs
        
        # ── Classify Tops (MAX) ──
        top_archs = []
        top_full_archs = []
        for i in range(len(tops)):
            if i == 0:
                top_archs.append('HH')
                top_full_archs.append('HH')
            else:
                p_curr = tops.loc[i, 'price']
                p_prev = tops.loc[i-1, 'price']
                
                if p_curr > p_prev:
                    basic = 'HH'
                    full = 'HH'
                else:
                    basic = 'LH'
                    prev_basic = top_archs[-1]
                    full = 'HH_TO_LH' if prev_basic == 'HH' else 'LH'
                    
                top_archs.append(basic)
                top_full_archs.append(full)
                
        tops['archetype'] = top_archs
        tops['full_archetype'] = top_full_archs
        
        # Merge back to chronological sequence using original index
        bottoms.set_index('index', inplace=True)
        tops.set_index('index', inplace=True)
        
        tk_classified = pd.concat([bottoms, tops]).sort_index()
        
        # Preceding / following leg metrics in chronological sequence
        for i in range(len(tk_classified)):
            row = tk_classified.iloc[i]
            
            p_prev_leg = 0.0
            p_prev_days = 0
            if i > 0:
                prev_row = tk_classified.iloc[i-1]
                p_prev_leg = (row['price'] / prev_row['price'] - 1) * 100
                p_prev_days = (pd.Timestamp(row['timestamp']) - pd.Timestamp(prev_row['timestamp'])).days
                
            p_next_leg = 0.0
            p_next_days = 0
            if i + 1 < len(tk_classified):
                next_row = tk_classified.iloc[i+1]
                p_next_leg = (next_row['price'] / row['price'] - 1) * 100
                p_next_days = (pd.Timestamp(next_row['timestamp']) - pd.Timestamp(row['timestamp'])).days
                
            results.append({
                'ticker': row['ticker'],
                'timestamp': row['timestamp'],
                'tp_type': row['tp_type'],
                'price': row['price'],
                'archetype': row['archetype'],
                'is_reversal': True,
                'preceding_leg_pct': round(p_prev_leg, 2),
                'following_leg_pct': round(p_next_leg, 2),
                'preceding_days': p_prev_days,
                'following_days': p_next_days,
                'swing_magnitude': classify_swing_magnitude(p_next_leg),
                'full_archetype': row['full_archetype'],
            })
            
    df_classified = pd.DataFrame(results)
    
    print("\n3. EXTRACTING RC SIGNATURES FROM CHANNEL SNAPSHOTS...")
    # Load all snapshots for aligning slopes
    snapshots = pd.read_sql("""
        SELECT ticker, timestamp, tide_slope, current_slope, wave_slope
        FROM engine.channel_snapshots
        ORDER BY ticker, timestamp;
    """, store.engine)
    
    # Pre-group snapshots for quick timestamp lookup
    snap_groups = {}
    for tk, grp in snapshots.groupby('ticker'):
        snap_groups[tk] = {
            'timestamps': grp['timestamp'].values,
            'tide_slopes': grp['tide_slope'].values,
            'current_slopes': grp['current_slope'].values,
            'wave_slopes': grp['wave_slope'].values,
        }
        
    rc_signatures = []
    skipped_signatures = 0
    
    for _, row in df_classified.iterrows():
        tk = row['ticker']
        ts = np.datetime64(row['timestamp'])
        
        tk_snaps = snap_groups.get(tk)
        if tk_snaps is None or len(tk_snaps['timestamps']) == 0:
            rc_signatures.append('UNKNOWN')
            skipped_signatures += 1
            continue
            
        # Find closest snapshot in time
        diffs = np.abs((tk_snaps['timestamps'] - ts).astype('timedelta64[D]').astype(int))
        closest = diffs.argmin()
        
        if diffs[closest] > 4:  # Must be within 4 days
            rc_signatures.append('UNKNOWN')
            skipped_signatures += 1
            continue
            
        tide = tk_snaps['tide_slopes'][closest]
        curr = tk_snaps['current_slopes'][closest]
        wave = tk_snaps['wave_slopes'][closest]
        
        tide_sign = '+' if tide > 0 else '-'
        curr_sign = '+' if curr > 0 else '-'
        wave_sign = '+' if wave > 0 else '-'
        
        rc_signatures.append(f"T({tide_sign})C({curr_sign})W({wave_sign})")
        
    df_classified['rc_signature'] = rc_signatures
    print(f"   Aligned signatures: {len(df_classified) - skipped_signatures:,d} (skipped={skipped_signatures})")
    
    # Re-order columns to match Sprint 1 CSV format exactly
    cols = ['ticker', 'timestamp', 'tp_type', 'price', 'archetype', 'is_reversal',
            'preceding_leg_pct', 'following_leg_pct', 'preceding_days', 'following_days',
            'swing_magnitude', 'rc_signature', 'full_archetype']
    df_classified = df_classified[cols]
    
    # Save CSV
    df_classified.to_csv(CSV_PATH, index=False)
    print(f"\n🎉 CLASSIFIED POINTS CSV REGENERATED: {CSV_PATH}")
    
    # Summarize stats
    print("\n   SUMMARY OF REGENERATED ARCHETYPES:")
    print("   " + str(df_classified['full_archetype'].value_counts().to_dict()))
    print("   Total unique turns: ", len(df_classified))
    
    store.close()

if __name__ == "__main__":
    main()
