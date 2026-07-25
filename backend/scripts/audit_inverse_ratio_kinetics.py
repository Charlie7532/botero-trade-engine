"""
Audit of Inverse Ratio Kinetics (S5 / SV5) around Zigzag Pivots (2000-2026)
==========================================================================
Analyses:
  1. The exact kinetics of Ratio_inv = S5_TW / SV5_TW.
  2. Bounded levels and rate of change (first derivative) leading to t_zero.
"""

import os, sys, json, pandas as pd, numpy as np
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

BREADTH_MAP = {
    "S5TH": "th", "S5FI": "fi", "S5TW": "tw",
    "SV5TH": "v_th", "SV5FI": "v_fi", "SV5TW": "v_tw"
}

def identify_zigzag(series, threshold_pct=0.05):
    p = series.values
    n = len(p)
    pivots = np.zeros(n, dtype=int)
    if n == 0:
        return pivots
    up = True
    last_p_idx = 0
    last_p_val = p[0]
    for i in range(1, n):
        val = p[i]
        if up:
            if val > last_p_val:
                last_p_val = val
                last_p_idx = i
            elif val <= last_p_val * (1.0 - threshold_pct):
                pivots[last_p_idx] = 1
                up = False
                last_p_val = val
                last_p_idx = i
        else:
            if val < last_p_val:
                last_p_val = val
                last_p_idx = i
            elif val >= last_p_val * (1.0 + threshold_pct):
                pivots[last_p_idx] = -1
                up = True
                last_p_val = val
                last_p_idx = i
    return pivots

def load_data(store):
    conn = store._conn()
    try:
        df = pd.read_sql("""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ('SPY', 'S5TW', 'SV5TW')
              AND timeframe = '1d'
              AND time >= '2000-01-01'
            ORDER BY time, ticker
        """, conn)
        pivot = df.pivot(index='date', columns='ticker', values='close').ffill()
        return pivot
    finally:
        store._put(conn)

def main():
    store = TimescaleDataStore()
    df = load_data(store)
    store.close()
    
    # Calculate Inverse Ratio S5 / SV5
    # Avoid zero division
    df['ratio_inv'] = df['S5TW'] / df['SV5TW'].replace(0, 1.0)
    df['d_ratio'] = df['ratio_inv'].diff(1)
    
    df['zz_50'] = identify_zigzag(df['SPY'], 0.05)
    
    bottoms_idx = [i for i in np.where(df['zz_50'] == -1)[0] if 5 <= i < len(df) - 5]
    tops_idx = [i for i in np.where(df['zz_50'] == 1)[0] if 5 <= i < len(df) - 5]
    
    print("\n" + "="*115)
    print("      📊 AUDITORÍA DEL CINÉTICA DE LA PROPORCIÓN INVERSA: S5_TW / SV5_TW")
    print("="*115)
    
    print("\n📉 KINETICS EN SUELOS (zz_5.0% Bottoms)")
    print(f"{'Día':<10s} | {'S5_TW Mean':<12s} | {'SV5_TW Mean':<12s} | {'S5 / SV5 Ratio':<16s} | {'Delta Ratio (1d)'}")
    print("-" * 70)
    for offset in range(-5, 6):
        off_str = f"t{offset:+d}" if offset != 0 else "t_zero"
        s5_vals = [df['S5TW'].iloc[i+offset] for i in bottoms_idx]
        sv5_vals = [df['SV5TW'].iloc[i+offset] for i in bottoms_idx]
        r_vals = [df['ratio_inv'].iloc[i+offset] for i in bottoms_idx]
        dr_vals = [df['d_ratio'].iloc[i+offset] for i in bottoms_idx]
        
        print(f"{off_str:<10s} | {np.mean(s5_vals):10.2f}% | {np.mean(sv5_vals):10.2f}% | {np.mean(r_vals):14.3f} | {np.mean(dr_vals):+16.3f}")

    print("\n📈 KINETICS EN TECHOS (zz_5.0% Tops)")
    print(f"{'Día':<10s} | {'S5_TW Mean':<12s} | {'SV5_TW Mean':<12s} | {'S5 / SV5 Ratio':<16s} | {'Delta Ratio (1d)'}")
    print("-" * 70)
    for offset in range(-5, 6):
        off_str = f"t{offset:+d}" if offset != 0 else "t_zero"
        s5_vals = [df['S5TW'].iloc[i+offset] for i in tops_idx]
        sv5_vals = [df['SV5TW'].iloc[i+offset] for i in tops_idx]
        r_vals = [df['ratio_inv'].iloc[i+offset] for i in tops_idx]
        dr_vals = [df['d_ratio'].iloc[i+offset] for i in tops_idx]
        
        print(f"{off_str:<10s} | {np.mean(s5_vals):10.2f}% | {np.mean(sv5_vals):10.2f}% | {np.mean(r_vals):14.3f} | {np.mean(dr_vals):+16.3f}")

if __name__ == "__main__":
    main()
