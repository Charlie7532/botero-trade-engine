"""
ML & Stochastic Breadth Spectrum Analysis around Zigzag Turning Points (2000 - 2026)
=====================================================================================
Persona: Marcos López de Prado (Chief Quantitative Strategist)

Measures the 11-day window [-5, +5] around Zigzag Pivots (2.5%, 5.0%, 7.5% thresholds):
  1. Net Stock Transitions per Day: Daily velocity v_TW, v_FI, v_TH (how many % of S&P 500 stocks flip).
  2. Acceleration (2nd Derivative): Curvature of Floor (Piso) and Ceiling (Techo) formation.
  3. Volume-Weighted Divergence: (SV5 - S5) velocity.
  4. Machine Learning Classification: Can we predict the Depth/Scale of the Turn (2.5% vs 5.0% vs 7.5%) at t=0?
"""

import os, sys, json, pandas as pd, numpy as np
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score

BREADTH_MAP = {
    "S5TH": "th", "S5FI": "fi", "S5TW": "tw",
    "SV5TH": "v_th", "SV5FI": "v_fi", "SV5TW": "v_tw"
}

def identify_zigzag(series, threshold_pct=0.05):
    """Computes exact Zigzag Highs (1) and Lows (-1)."""
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
                pivots[last_p_idx] = 1 # Peak
                up = False
                last_p_val = val
                last_p_idx = i
        else:
            if val < last_p_val:
                last_p_val = val
                last_p_idx = i
            elif val >= last_p_val * (1.0 + threshold_pct):
                pivots[last_p_idx] = -1 # Trough
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
    
    # Calculate daily velocities (net % of stocks changing state per day)
    for col in ['tw', 'fi', 'th', 'v_tw', 'v_fi', 'v_th']:
        df[f'v_{col}'] = df[col].diff(1)
        df[f'a_{col}'] = df[f'v_{col}'].diff(1)
        
    df['v_div_tw'] = df['v_v_tw'] - df['v_tw'] # Volume velocity - Price velocity
    
    # Compute Zigzags for 2.5%, 5.0%, 7.5%
    df['zz_25'] = identify_zigzag(df['spy'], 0.025)
    df['zz_50'] = identify_zigzag(df['spy'], 0.05)
    df['zz_75'] = identify_zigzag(df['spy'], 0.075)
    
    print("\n" + "="*115)
    print("      🔬 AUTOPSIA ML & ESPECTRO DE BREADTH: SPECTRUM OF FLOOR AND CEILING FORMATION")
    print("="*115)
    
    scales = [(0.025, 'zz_25', 'Pullback 2.5%'), (0.05, 'zz_50', 'Corrección Menor 5.0%'), (0.075, 'zz_75', 'Corrección Mayor 7.5%')]
    
    spectrum_results = {}
    
    for thresh, col_name, label in scales:
        bottoms_idx = np.where(df[col_name] == -1)[0]
        tops_idx = np.where(df[col_name] == 1)[0]
        
        # Build window matrix [-5 to +5] for Bottoms
        bot_curves_tw = []
        bot_vel_tw = []
        bot_acc_tw = []
        
        for idx in bottoms_idx:
            if idx >= 5 and idx + 5 < len(df):
                sub_tw = df['tw'].iloc[idx-5 : idx+6].values
                sub_v_tw = df['v_tw'].iloc[idx-5 : idx+6].values
                sub_a_tw = df['a_tw'].iloc[idx-5 : idx+6].values
                bot_curves_tw.append(sub_tw)
                bot_vel_tw.append(sub_v_tw)
                bot_acc_tw.append(sub_a_tw)
                
        # Build window matrix [-5 to +5] for Tops
        top_curves_tw = []
        top_vel_tw = []
        top_acc_tw = []
        
        for idx in tops_idx:
            if idx >= 5 and idx + 5 < len(df):
                sub_tw = df['tw'].iloc[idx-5 : idx+6].values
                sub_v_tw = df['v_tw'].iloc[idx-5 : idx+6].values
                sub_a_tw = df['a_tw'].iloc[idx-5 : idx+6].values
                top_curves_tw.append(sub_tw)
                top_vel_tw.append(sub_v_tw)
                top_acc_tw.append(sub_a_tw)
                
        avg_bot_tw = np.mean(bot_curves_tw, axis=0) if bot_curves_tw else np.zeros(11)
        avg_bot_vel = np.mean(bot_vel_tw, axis=0) if bot_vel_tw else np.zeros(11)
        avg_bot_acc = np.mean(bot_acc_tw, axis=0) if bot_acc_tw else np.zeros(11)
        
        avg_top_tw = np.mean(top_curves_tw, axis=0) if top_curves_tw else np.zeros(11)
        avg_top_vel = np.mean(top_vel_tw, axis=0) if top_vel_tw else np.zeros(11)
        avg_top_acc = np.mean(top_acc_tw, axis=0) if top_acc_tw else np.zeros(11)
        
        spectrum_results[label] = {
            "num_bottoms": len(bottoms_idx),
            "num_tops": len(tops_idx),
            "avg_bot_tw": avg_bot_tw,
            "avg_bot_vel": avg_bot_vel,
            "avg_bot_acc": avg_bot_acc,
            "avg_top_tw": avg_top_tw,
            "avg_top_vel": avg_top_vel,
            "avg_top_acc": avg_top_acc
        }
        
    # Print Floor Formation Spectrum Table
    print("\n📉 CURVA DE FORMACIÓN DE PISO (PUESTA A PUNTO DEL SUELO: S5_TW VELOCIDAD Y ACELERACIÓN)")
    print(f"{'Día Relativo':<12s} | {'Pullback 2.5% (Vel | Acel)':<30s} | {'Corr Menor 5% (Vel | Acel)':<30s} | {'Corr Mayor 7.5% (Vel | Acel)':<30s}")
    print("-" * 115)
    
    days = ["t-5", "t-4", "t-3", "t-2", "t-1", "t=0 (SUELO)", "t+1", "t+2", "t+3", "t+4", "t+5"]
    
    for i in range(11):
        d_name = days[i]
        p25_v, p25_a = spectrum_results['Pullback 2.5%']['avg_bot_vel'][i], spectrum_results['Pullback 2.5%']['avg_bot_acc'][i]
        p50_v, p50_a = spectrum_results['Corrección Menor 5.0%']['avg_bot_vel'][i], spectrum_results['Corrección Menor 5.0%']['avg_bot_acc'][i]
        p75_v, p75_a = spectrum_results['Corrección Mayor 7.5%']['avg_bot_vel'][i], spectrum_results['Corrección Mayor 7.5%']['avg_bot_acc'][i]
        
        print(f"{d_name:<12s} | {p25_v:+6.2f}%/d | {p25_a:+6.2f}%/d²          | {p50_v:+6.2f}%/d | {p50_a:+6.2f}%/d²          | {p75_v:+6.2f}%/d | {p75_a:+6.2f}%/d²")

    # Machine Learning Feature Classification
    print("\n" + "="*115)
    print("      🤖 MACHINE LEARNING: PREDICCIÓN DE PROFUNDIDAD DEL GIRO EN t=0")
    print("="*115)
    
    # Train RF model to predict if a dip is 2.5% (Pullback) vs >= 5% (Correction) at t=0
    features = []
    labels = []
    
    for i in range(5, len(df)-5):
        if df['zz_25'].iloc[i] == -1: # Is a bottom
            # Feature vector at t=0
            v_5d = df['tw'].iloc[i] - df['tw'].iloc[i-5]
            v_1d = df['v_tw'].iloc[i]
            acc_1d = df['a_tw'].iloc[i]
            vol_div = df['v_div_tw'].iloc[i]
            fi_val = df['fi'].iloc[i]
            th_val = df['th'].iloc[i]
            
            feat = [df['tw'].iloc[i], fi_val, th_val, v_1d, v_5d, acc_1d, vol_div]
            
            # Label: 0 = shallow pullback (2.5%), 1 = deep/major correction (5.0%+ / 7.5%+)
            if df['zz_50'].iloc[i] == -1 or df['zz_75'].iloc[i] == -1:
                lbl = 1 # Deep
            else:
                lbl = 0 # Shallow
                
            features.append(feat)
            labels.append(lbl)
            
    X = np.array(features)
    y = np.array(labels)
    
    split = int(len(X) * 0.7)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    
    rf = RandomForestClassifier(n_estimators=100, max_depth=4, random_state=42)
    rf.fit(X_train, y_train)
    preds = rf.predict(X_test)
    
    acc = accuracy_score(y_test, preds)
    feature_names = ["S5_TW", "S5_FI", "S5_TH", "Vel_1d", "Vel_5d", "Acel_1d", "Vol_Divergence"]
    importances = dict(zip(feature_names, rf.feature_importances_))
    
    print(f"Precisión de Clasificación ML (Pullback Superfluo vs Corrección Profunda): {acc*100:.2f}%")
    print("\nFeature Importances (Importancia de Variables):")
    for fname, imp in sorted(importances.items(), key=lambda x: x[1], reverse=True):
        print(f"  • {fname:<20s}: {imp*100:5.2f}%")

if __name__ == "__main__":
    main()
