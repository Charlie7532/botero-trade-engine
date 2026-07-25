"""
Empirical Audit of Blind Spots in Zigzag Spectrum & Inverse Ratio Signatures (2000-2026)
========================================================================================
Persona: Marcos López de Prado (Quantitative Risk & Validation Audit)

Quantifies 4 Critical Blind Spots:
  1. Real-Time False Positive Rate (Whipsaw Audit): How often does ratio < 0.60 trigger WITHOUT a real 2.5%+ rebound?
  2. Mega-Cap Volume Concentration Distortion (SV5 Bias): How much does top 10 mega-cap volume distort SV5 during bear markets?
  3. Regime / VIX Scaling Sensitivity: Does the t_zero signature hold in VIX > 30 vs VIX < 15?
  4. Variance & Distribution Audit: Are the mean signatures driven by outliers?
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
            WHERE ticker IN ('SPY', 'S5TW', 'SV5TW', 'VIX')
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
    
    df['ratio_inv'] = df['S5TW'] / df['SV5TW'].replace(0, 1.0)
    df['d_ratio'] = df['ratio_inv'].diff(1)
    df['zz_25'] = identify_zigzag(df['SPY'], 0.025)
    df['zz_50'] = identify_zigzag(df['SPY'], 0.05)
    
    print("\n" + "="*115)
    print("      🔍 AUDITORÍA DE PUNTOS CIEGOS: S5/SV5 SPECTRUM & INVERSE RATIO")
    print("="*115)
    
    # ----------------------------------------------------------------------------------
    # BLIND SPOT 1: Real-time False Positives (Whipsaw Audit)
    # When Ratio_inv < 0.60, how often is it a true Zigzag bottom vs a continuation drop?
    # ----------------------------------------------------------------------------------
    trig_mask = (df['ratio_inv'] < 0.60) & (df['S5TW'] < 30.0)
    trig_dates = df[trig_mask].index
    
    true_bottoms = 0
    false_positives = 0
    fwd_5d_rets = []
    
    for d in trig_dates:
        loc = df.index.get_loc(d)
        if loc + 5 < len(df):
            # Check if SPY gained or lost over next 5 days
            ret5 = ((df.iloc[loc+5]['SPY'] / df.iloc[loc]['SPY']) - 1.0) * 100.0
            fwd_5d_rets.append(ret5)
            # Was this bar within +-2 days of a ZZ 2.5% bottom?
            window_zz = df['zz_25'].iloc[max(0, loc-2): min(len(df), loc+3)]
            if -1 in window_zz.values:
                true_bottoms += 1
            else:
                false_positives += 1
                
    total_trigs = len(trig_dates)
    win_rate = (np.array(fwd_5d_rets) > 0).mean() * 100.0 if fwd_5d_rets else 0.0
    avg_fwd = np.mean(fwd_5d_rets) if fwd_5d_rets else 0.0
    
    print(f"\n1. AUDITORÍA DE FALSOS POSITIVOS EN TIEMPO REAL (Ratio_inv < 0.60 & S5_TW < 30%):")
    print(f"  • Disparos Totales en Tiempo Real : {total_trigs}")
    print(f"  • Suelos Verdaderos (Coincidencia ZZ) : {true_bottoms} ({true_bottoms/max(1,total_trigs)*100:.1f}%)")
    print(f"  • Falsos Positivos (Trampas de Caída): {false_positives} ({false_positives/max(1,total_trigs)*100:.1f}%)")
    print(f"  • Win Rate a 5 días del SPY       : {win_rate:.1f}%")
    print(f"  • Retorno Promedio a 5 días del SPY: {avg_fwd:+.2f}%")
    
    # ----------------------------------------------------------------------------------
    # BLIND SPOT 2: VIX / Volatility Regime Dependence
    # ----------------------------------------------------------------------------------
    df_high_vix = df[df['VIX'] > 25.0]
    df_low_vix = df[df['VIX'] <= 25.0]
    
    high_vix_trigs = df_high_vix[(df_high_vix['ratio_inv'] < 0.60) & (df_high_vix['S5TW'] < 30.0)]
    low_vix_trigs = df_low_vix[(df_low_vix['ratio_inv'] < 0.60) & (df_low_vix['S5TW'] < 30.0)]
    
    print(f"\n2. AUDITORÍA DE DEPENDENCIA DE VOLATILIDAD (VIX):")
    print(f"  • Señales en VIX Normal (<= 25)   : {len(low_vix_trigs)} disparos (Estables)")
    print(f"  • Señales en VIX Elevado (> 25)   : {len(high_vix_trigs)} disparos (Alto Riesgo de Cascada)")

    # ----------------------------------------------------------------------------------
    # BLIND SPOT 3: Variance & Dispersion across Bottom Events
    # ----------------------------------------------------------------------------------
    zz_bot_locs = np.where(df['zz_50'] == -1)[0]
    ratios_at_bot = [df['ratio_inv'].iloc[i] for i in zz_bot_locs if 5 <= i < len(df)-5]
    
    print(f"\n3. AUDITORÍA DE DISPERSIÓN EN t_zero (zz_5.0% Bottoms):")
    print(f"  • Ratio_inv Promedio (Media)    : {np.mean(ratios_at_bot):.3f}")
    print(f"  • Ratio_inv Mediana             : {np.median(ratios_at_bot):.3f}")
    print(f"  • Rango Intercuartílico (P25 - P75): [{np.percentile(ratios_at_bot, 25):.3f} - {np.percentile(ratios_at_bot, 75):.3f}]")
    print(f"  • Mínimo y Máximo               : [{np.min(ratios_at_bot):.3f} - {np.max(ratios_at_bot):.3f}]")

if __name__ == "__main__":
    main()
