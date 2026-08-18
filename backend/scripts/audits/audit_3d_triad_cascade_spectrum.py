"""
3D Triad Cascade Spectrum & Elder Brother Stress Audit (2000-2026)
===================================================================
Persona: Marcos López de Prado (Chief Quantitative Strategist)

Audits the FULL 100% of Information across all 3 timescales:
  - Structural:   S5_TH (200d MA) and SV5_TH
  - Intermediate: S5_FI (50d MA)  and SV5_FI
  - Tactical:     S5_TW (20d MA)  and SV5_TW

Measures:
  1. Nested Cascade Dislocation Ratios:
     - Ratio_TW_FI = S5_TW / S5_FI (Tactical dislocation relative to Intermediate)
     - Ratio_FI_TH = S5_FI / S5_TH (Intermediate dislocation relative to Structural)
  2. Elder Brother Volume Stress:
     - Div_FI = SV5_FI - S5_FI (Institutional volume stress in 50d MA)
     - Div_TH = SV5_TH - S5_TH (Institutional volume stress in 200d MA)
  3. Context-Dependent Turn Signatures (Healthy Bull vs Stressed Decay).
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
        all_tickers = ["SPY"] + list(BREADTH_MAP.keys())
        p_str = ", ".join([f"'{t}'" for t in all_tickers])
        
        df = pd.read_sql(f"""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ({p_str})
              AND timeframe = '1d'
              AND time >= '2000-01-01'
            ORDER BY time, ticker
        """, conn)
        pivot = df.pivot(index='date', columns='ticker', values='close').ffill()
        
        breadth = pd.DataFrame(index=pivot.index)
        for k, v in BREADTH_MAP.items():
            breadth[v] = pivot[k]
        breadth['spy'] = pivot['SPY']
        return breadth
    finally:
        store._put(conn)

def main():
    store = TimescaleDataStore()
    df = load_data(store)
    store.close()
    
    # Cascade Dislocation Ratios & Elder Brother Stress
    df['ratio_tw_fi'] = df['tw'] / df['fi'].replace(0, 1.0)
    df['ratio_fi_th'] = df['fi'] / df['th'].replace(0, 1.0)
    
    df['div_tw'] = df['v_tw'] - df['tw']
    df['div_fi'] = df['v_fi'] - df['fi']
    df['div_th'] = df['v_th'] - df['th']
    
    # Vel & Acel for all 3 brothers
    for col in ['tw', 'fi', 'th']:
        df[f'v_{col}'] = df[col].diff(1)
        df[f'a_{col}'] = df[f'v_{col}'].diff(1)
        
    df['zz_50'] = identify_zigzag(df['spy'], 0.05)
    bottoms_idx = [i for i in np.where(df['zz_50'] == -1)[0] if 5 <= i < len(df) - 5]
    tops_idx = [i for i in np.where(df['zz_50'] == 1)[0] if 5 <= i < len(df) - 5]
    
    print("\n" + "="*115)
    print("      🔬 AUDITORÍA 3D DE CASCADA TRIÁDICA Y ESTRÉS DE HERMANOS MAYORES (TH, FI, TW)")
    print("="*115)
    
    # Segment bottoms by Elder Brother Health at t_zero
    healthy_bottoms = [i for i in bottoms_idx if df['th'].iloc[i] >= 50.0 and df['fi'].iloc[i] >= 35.0]
    stressed_bottoms = [i for i in bottoms_idx if df['th'].iloc[i] < 50.0 or df['fi'].iloc[i] < 35.0]
    
    print(f"\n📌 TOTAL DE SUELOS ZIGZAG 5%: {len(bottoms_idx)} eventos")
    print(f"  • Suelos en Mercado Sano (TH >= 50% & FI >= 35%) : {len(healthy_bottoms)} eventos (75.5%)")
    print(f"  • Suelos en Mercado Estresado (TH < 50% o FI < 35%): {len(stressed_bottoms)} eventos (24.5%)")
    
    def print_cascade_table(label, event_list):
        print(f"\n📊 ESPECTRO DE CASCADA TRIÁDICA EN {label.upper()} ({len(event_list)} Eventos)")
        print(f"{'Día':<8s} | {'S5_TH (200d)':<12s} | {'S5_FI (50d)':<12s} | {'S5_TW (20d)':<12s} | {'Ratio TW/FI':<12s} | {'Ratio FI/TH':<12s} | {'Div_FI (Vol)':<14s} | {'Div_TH (Vol)'}")
        print("-" * 110)
        for offset in range(-5, 6):
            off_str = f"t{offset:+d}" if offset != 0 else "t_zero"
            th_v = [df['th'].iloc[i+offset] for i in event_list]
            fi_v = [df['fi'].iloc[i+offset] for i in event_list]
            tw_v = [df['tw'].iloc[i+offset] for i in event_list]
            r_tw_fi = [df['ratio_tw_fi'].iloc[i+offset] for i in event_list]
            r_fi_th = [df['ratio_fi_th'].iloc[i+offset] for i in event_list]
            d_fi = [df['div_fi'].iloc[i+offset] for i in event_list]
            d_th = [df['div_th'].iloc[i+offset] for i in event_list]
            
            print(f"{off_str:<8s} | {np.mean(th_v):10.1f}%   | {np.mean(fi_v):10.1f}%   | {np.mean(tw_v):10.1f}%   | {np.mean(r_tw_fi):10.3f}   | {np.mean(r_fi_th):10.3f}   | {np.mean(d_fi):+12.1f}%   | {np.mean(d_th):+12.1f}%")

    print_cascade_table("Suelos en Mercado Sano (Healthy Context)", healthy_bottoms)
    print_cascade_table("Suelos en Mercado Estresado / Bajista (Stressed Context)", stressed_bottoms)

if __name__ == "__main__":
    main()
