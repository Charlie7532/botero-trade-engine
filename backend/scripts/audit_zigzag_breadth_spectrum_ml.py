"""
Zigzag Breadth Spectrum & Velocity Profile ML Audit (2000-2026)
===============================================================
Persona: Marcos López de Prado (Chief Quantitative Strategist)

Measures:
  1. Identifies Zigzag PIVOTS (Peaks & Troughs) at 2.5%, 5.0%, and 7.5% thresholds.
  2. For each pivot, extracts -5 to +5 day window of:
     - S5_TW, S5_FI, S5_TH (Percentage of S&P 500 stocks above 20d, 50d, 200d MA)
     - Net Stock Flips per day: N_flips = (S5_TW_t - S5_TW_{t-1}) * 5
     - Breadth Velocity (1st derivative): v_t = S5_TW_t - S5_TW_{t-1}
     - Breadth Acceleration (2nd derivative): a_t = v_t - v_{t-1}
     - Institutional Volume Divergence: D_t = SV5_TW - S5_TW
  3. ML Feature Importance (Random Forest) to discriminate between 2.5%, 5.0%, and 7.5% turns.
  4. Outputs the "Spectral Fingerprint" for Top Formations vs Bottom Formations across scales.
"""

import os, sys, json, pandas as pd, numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

BREADTH_MAP = {
    "S5TH": "th", "S5FI": "fi", "S5TW": "tw",
    "SV5TH": "v_th", "SV5FI": "v_fi", "SV5TW": "v_tw"
}

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

def compute_zigzag(prices, threshold_pct):
    """
    Computes Zigzag pivots (1 for Peak, -1 for Trough) at given threshold %.
    Returns array of (index, date, pivot_type, price)
    """
    p = prices.values
    dates = prices.index
    n = len(p)
    
    pivots = [] # (idx, date, type, price)
    
    trend = 0
    last_high_idx = 0
    last_high_val = p[0]
    last_low_idx = 0
    last_low_val = p[0]
    
    thresh = threshold_pct / 100.0
    
    for i in range(1, n):
        val = p[i]
        if trend == 0:
            if val >= last_low_val * (1 + thresh):
                trend = 1
                last_high_val = val
                last_high_idx = i
                pivots.append((last_low_idx, dates[last_low_idx], -1, last_low_val))
            elif val <= last_high_val * (1 - thresh):
                trend = -1
                last_low_val = val
                last_low_idx = i
                pivots.append((last_high_idx, dates[last_high_idx], 1, last_high_val))
        elif trend == 1: # Up
            if val > last_high_val:
                last_high_val = val
                last_high_idx = i
            elif val <= last_high_val * (1 - thresh):
                pivots.append((last_high_idx, dates[last_high_idx], 1, last_high_val))
                trend = -1
                last_low_val = val
                last_low_idx = i
        elif trend == -1: # Down
            if val < last_low_val:
                last_low_val = val
                last_low_idx = i
            elif val >= last_low_val * (1 + thresh):
                pivots.append((last_low_idx, dates[last_low_idx], -1, last_low_val))
                trend = 1
                last_high_val = val
                last_high_idx = i
                
    return pivots

def extract_window_features(df, idx, window=5):
    """Extracts -window to +window features around index."""
    if idx < window or idx + window >= len(df):
        return None
    
    sub = df.iloc[idx - window : idx + window + 1]
    
    # Calculate daily stock flips (500 * delta S5_TW)
    tw = sub['tw'].values
    v_tw = sub['v_tw'].values
    th = sub['th'].values
    fi = sub['fi'].values
    
    # Daily velocity (1st derivative) for 20d MA
    v_20d = np.diff(tw) # length 2*window
    stock_flips_20d = v_20d * 5.0 # 1% = 5 stocks
    
    # 2nd derivative (acceleration)
    a_20d = np.diff(v_20d)
    
    # Pre-pivot velocity (-5d to 0d)
    pre_velocity_20d = tw[window] - tw[0] # change over 5 days up to pivot
    pre_flips_total = pre_velocity_20d * 5.0 # Net stocks flipped in 5 days prior
    
    # Volume divergence at pivot
    vol_div_pivot = v_tw[window] - tw[window]
    
    # Return dictionary of spectral features
    feat = {
        "tw_pivot": tw[window],
        "fi_pivot": fi[window],
        "th_pivot": th[window],
        "vol_div_pivot": vol_div_pivot,
        "pre_velocity_5d": pre_velocity_20d,
        "pre_flips_5d": pre_flips_total,
        "max_flips_1d_pre": np.max(np.abs(stock_flips_20d[:window])) if len(stock_flips_20d[:window])>0 else 0,
        "pre_acc_2d": a_20d[window-2] if len(a_20d) >= window else 0,
        "post_velocity_5d": tw[-1] - tw[window],
        "post_flips_5d": (tw[-1] - tw[window]) * 5.0
    }
    return feat

def main():
    store = TimescaleDataStore()
    df = load_data(store)
    store.close()
    
    thresholds = [2.5, 5.0, 7.5]
    pivots_by_thresh = {}
    
    for t in thresholds:
        pivots_by_thresh[t] = compute_zigzag(df['spy'], t)
        
    print("\n" + "="*115)
    print("      🔬 AUTOPSIA ML: ESPECTRO DE BREADTH & FLIPS DE MEDIAS MÓVILES (2000-2026)")
    print("      Persona: Prof. Marcos López de Prado")
    print("="*115)
    
    # 1. Summary of Pivots per Threshold
    for t in thresholds:
        pivs = pivots_by_thresh[t]
        peaks = [p for p in pivs if p[2] == 1]
        troughs = [p for p in pivs if p[2] == -1]
        print(f"• Zigzag {t:3.1f}%: Total Pivotes = {len(pivs)} (Techos = {len(peaks)}, Suelos = {len(troughs)})")
        
    # 2. Analyze Bottom Formations (Troughs)
    print("\n" + "="*115)
    print("      📉 PERFIL ESPECTRAL EN FORMACIÓN DE SUELOS (TROUGHS: REBOTES Y PISOS)")
    print("      Ventana: -5 días a +5 días respecto al pivote de giro")
    print("="*115)
    
    trough_data = []
    for t in thresholds:
        troughs = [p for p in pivots_by_thresh[t] if p[2] == -1]
        feats = [extract_window_features(df, p[0]) for p in troughs]
        feats = [f for f in feats if f is not None]
        
        avg_tw = np.mean([f['tw_pivot'] for f in feats])
        avg_pre_flips = np.mean([f['pre_flips_5d'] for f in feats])
        avg_post_flips = np.mean([f['post_flips_5d'] for f in feats])
        avg_vdiv = np.mean([f['vol_div_pivot'] for f in feats])
        max_daily_flips = np.mean([f['max_flips_1d_pre'] for f in feats])
        
        trough_data.append({
            "Scale": f"Zigzag {t}%",
            "S5_TW_Pivot": f"{avg_tw:.1f}%",
            "Flips_Pre_5d": f"{avg_pre_flips:+.1f} acciones",
            "Flips_Post_5d": f"{avg_post_flips:+.1f} acciones",
            "Max_1d_Flips": f"{max_daily_flips:.1f} acc/día",
            "Vol_Divergence": f"{avg_vdiv:+.1f}%"
        })
        
    df_troughs = pd.DataFrame(trough_data)
    print(df_troughs.to_string(index=False))
    
    # 3. Analyze Top Formations (Peaks)
    print("\n" + "="*115)
    print("      📈 PERFIL ESPECTRAL EN FORMACIÓN DE TECHOS (PEAKS: AGOTAMIENTO Y DISTRIBUCIÓN)")
    print("      Ventana: -5 días a +5 días respecto al pivote de giro")
    print("="*115)
    
    peak_data = []
    for t in thresholds:
        peaks = [p for p in pivots_by_thresh[t] if p[2] == 1]
        feats = [extract_window_features(df, p[0]) for p in peaks]
        feats = [f for f in feats if f is not None]
        
        avg_tw = np.mean([f['tw_pivot'] for f in feats])
        avg_pre_flips = np.mean([f['pre_flips_5d'] for f in feats])
        avg_post_flips = np.mean([f['post_flips_5d'] for f in feats])
        avg_vdiv = np.mean([f['vol_div_pivot'] for f in feats])
        max_daily_flips = np.mean([f['max_flips_1d_pre'] for f in feats])
        
        peak_data.append({
            "Scale": f"Zigzag {t}%",
            "S5_TW_Pivot": f"{avg_tw:.1f}%",
            "Flips_Pre_5d": f"{avg_pre_flips:+.1f} acciones",
            "Flips_Post_5d": f"{avg_post_flips:+.1f} acciones",
            "Max_1d_Flips": f"{max_daily_flips:.1f} acc/día",
            "Vol_Divergence": f"{avg_vdiv:+.1f}%"
        })
        
    df_peaks = pd.DataFrame(peak_data)
    print(df_peaks.to_string(index=False))

    # 4. Machine Learning Classification: Can pre-pivot velocity & volume divergence predict 2.5% vs 5.0% vs 7.5%?
    print("\n" + "="*115)
    print("      🤖 MACHINE LEARNING: CAPACIDAD DISCRIMINANTE DE LA VELOCIDAD DE FLIPS")
    print("===================================================================================")
    
    X = []
    y = [] # 0 for 2.5% pullback, 1 for 5.0% minor corr, 2 for 7.5% major corr
    
    for t_idx, t in enumerate(thresholds):
        troughs = [p for p in pivots_by_thresh[t] if p[2] == -1]
        for p in troughs:
            f = extract_window_features(df, p[0])
            if f:
                X.append([
                    f['tw_pivot'], f['fi_pivot'], f['th_pivot'],
                    f['vol_div_pivot'], f['pre_velocity_5d'], f['pre_flips_5d']
                ])
                y.append(t_idx)
                
    X = np.array(X)
    y = np.array(y)
    
    rf = RandomForestClassifier(n_estimators=100, max_depth=4, random_state=42)
    rf.fit(X, y)
    
    feature_names = ["S5_TW", "S5_FI", "S5_TH", "Vol_Divergence(SV5-S5)", "5d_Velocity", "5d_Net_Flips"]
    importances = rf.feature_importances_
    
    print("\nImportance of Spectral Features in Predicting Correction Scale (2.5% vs 5.0% vs 7.5%):")
    for name, imp in sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True):
        print(f"  • {name:<25s}: {imp*100:5.2f}%")
        
    print("="*115)

if __name__ == "__main__":
    main()
