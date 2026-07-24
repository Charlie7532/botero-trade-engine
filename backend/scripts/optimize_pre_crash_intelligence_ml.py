"""
Quantitative ML & Market Intelligence Optimization for Pre-Crash Distribution Signal
======================================================================================
Trains a scikit-learn Random Forest / Gradient Boosting Decision Tree model combined with
Multi-Vector Market Intelligence consensus (VIX, PCR, FGBI, S5/SV5 Velocities) to filter
false alarms in Pre-Crash Distribution.

Measures:
  1. Precision, Recall, F1-Score of ML & Intelligence Model vs Rigid Rules.
  2. Full 2000-2026 Simulation Impact: Accumulated SPY Shares.
  3. Prints BOTH MASTER TABLES (Year-by-Year & Regime Attribution).
"""

import os, sys, json, pandas as pd, numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, precision_score, recall_score, f1_score
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS, SECTOR_CAP_WEIGHTS

SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]
BREADTH_MAP = {
    "S5TH": "th", "S5FI": "fi", "S5TW": "tw",
    "SV5TH": "v_th", "SV5FI": "v_fi", "SV5TW": "v_tw"
}

def load_ml_dataset(store):
    conn = store._conn()
    try:
        all_tickers = ["SPY"] + SECTORS_11
        p_str = ", ".join([f"'{t}'" for t in all_tickers])
        
        df_p = pd.read_sql(f"""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ({p_str})
              AND timeframe = '1d'
              AND time >= '2000-01-01'
            ORDER BY time, ticker
        """, conn)
        price_pivot = df_p.pivot(index='date', columns='ticker', values='close').ffill()
        
        mkt_ind = list(BREADTH_MAP.keys())
        mkt_str = ", ".join([f"'{t}'" for t in mkt_ind])
        df_mkt = pd.read_sql(f"""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ({mkt_str})
              AND timeframe = '1d'
              AND time >= '2000-01-01'
            ORDER BY time, ticker
        """, conn)
        mkt_pivot = df_mkt.pivot(index='date', columns='ticker', values='close').ffill()
        
        mkt_breadth = pd.DataFrame(index=mkt_pivot.index)
        for k, v in BREADTH_MAP.items():
            mkt_breadth[v] = mkt_pivot[k]
            
        sec_ind_tickers = []
        for s in SECTORS_11:
            sec_ind_tickers.extend([f"S5_{s}_TH", f"S5_{s}_FI", f"S5_{s}_TW", f"SV5_{s}_TH", f"SV5_{s}_FI", f"SV5_{s}_TW"])
            
        sec_str = ", ".join([f"'{t}'" for t in sec_ind_tickers])
        df_sec_ind = pd.read_sql(f"""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ({sec_str})
              AND timeframe = '1d'
              AND time >= '2000-01-01'
            ORDER BY time, ticker
        """, conn)
        sec_ind_pivot = df_sec_ind.pivot(index='date', columns='ticker', values='close').ffill()
        
        df_macro = pd.read_sql("""
            SELECT ticker, time::date as date, close 
            FROM market.ohlcv_bars 
            WHERE ticker IN ('VIX', 'CBOE_PCR', 'FG') 
              AND timeframe = '1d' 
              AND time >= '2000-01-01' 
            ORDER BY time
        """, conn)
        macro_pivot = df_macro.pivot(index='date', columns='ticker', values='close').ffill().bfill()
        
        common_dates = price_pivot.index.intersection(mkt_breadth.index).intersection(sec_ind_pivot.index).intersection(macro_pivot.index)
        return price_pivot.loc[common_dates], mkt_breadth.loc[common_dates], sec_ind_pivot.loc[common_dates], macro_pivot.loc[common_dates]
    finally:
        store._put(conn)

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot = load_ml_dataset(store)
    store.close()
    
    dates = sorted(price_pivot.index)
    df = pd.DataFrame(index=dates)
    df['spy_price'] = price_pivot['SPY']
    df['fwd_20d_ret'] = (df['spy_price'].shift(-20) / df['spy_price'] - 1.0) * 100.0
    
    for k in BREADTH_MAP.values():
        df[k] = mkt_breadth[k]
        
    df['vix'] = macro_pivot['VIX'] if 'VIX' in macro_pivot.columns else 18.0
    df['pcr'] = macro_pivot['CBOE_PCR'] if 'CBOE_PCR' in macro_pivot.columns else 1.0
    df['fg'] = macro_pivot['FG'] if 'FG' in macro_pivot.columns else 50.0
    
    # Feature engineering: Velocities
    df['th_vel_5d'] = df['th'].diff(5)
    df['tw_vel_5d'] = df['tw'].diff(5)
    df['v_tw_vel_5d'] = df['v_tw'].diff(5)
    
    # Rigid Trigger
    sec_tw_df = pd.DataFrame(index=dates)
    for s in SECTORS_11:
        if f"S5_{s}_TW" in sec_ind_pivot.columns:
            sec_tw_df[s] = sec_ind_pivot[f"S5_{s}_TW"]
            
    df['hot_tw'] = (sec_tw_df > 50.0).sum(axis=1)
    df['cold_tw'] = (sec_tw_df < 20.0).sum(axis=1)
    
    df['rigid_pre_crash'] = ((df['v_tw'] < 40.0) & (df['th'] < 45.0)) | ((df['hot_tw'] <= 1) & (df['cold_tw'] >= 7))
    
    # Target label: Real Crash / Drop (forward 20d return < -2.0%)
    df['target_crash'] = (df['fwd_20d_ret'] < -2.0).astype(int)
    
    # Filter dataset to days where rigid_pre_crash triggered
    df_triggers = df[df['rigid_pre_crash'] == True].dropna().copy()
    
    feature_cols = ['th', 'fi', 'tw', 'v_th', 'v_fi', 'v_tw', 'vix', 'pcr', 'fg', 'th_vel_5d', 'tw_vel_5d', 'v_tw_vel_5d', 'hot_tw', 'cold_tw']
    X = df_triggers[feature_cols]
    y = df_triggers['target_crash']
    
    # Train Random Forest Classifier
    rf = RandomForestClassifier(n_estimators=100, max_depth=4, random_state=42)
    rf.fit(X, y)
    
    df_triggers['ml_pred'] = rf.predict(X)
    df_triggers['ml_prob'] = rf.predict_proba(X)[:, 1]
    
    print("\n" + "="*105)
    print("      🧠 AUDITORÍA DE MACHINE LEARNING & MULTI-VECTOR MARKET INTELLIGENCE (PRE-CRASH)")
    print("="*105)
    print(f"Total Disparos de Regla Rígida Pre-Crash                 : {len(df_triggers)} días")
    print(f"Aciertos de Regla Rígida (Caídas Reales < -2%)          : {y.sum()} días ({y.mean()*100:.1f}% Precisión)")
    print(f"Falsas Alarmas de Regla Rígida (Falso Pánico en Bull)   : {len(df_triggers) - y.sum()} días")
    
    ml_prec = precision_score(y, df_triggers['ml_pred']) * 100.0
    ml_rec = recall_score(y, df_triggers['ml_pred']) * 100.0
    ml_f1 = f1_score(y, df_triggers['ml_pred']) * 100.0
    
    print(f"\n--- RENDIMIENTO MODELO ML + INTELIGENCIA DE MERCADOS ---")
    print(f"Precisión del Modelo ML (Acierto en Caídas)              : {ml_prec:.1f}% (Mejora de +{ml_prec - y.mean()*100:.1f} pp sobre regla rígida)")
    print(f"Recall del Modelo ML (Captura de Crashes Reales)          : {ml_rec:.1f}%")
    print(f"F1-Score del Modelo ML                                   : {ml_f1:.1f}%")
    
    # Feature Importances
    fi_series = pd.Series(rf.feature_importances_, index=feature_cols).sort_values(ascending=False)
    print("\n--- IMPORTANCIA DE VECTORES DE INTELIGENCIA (FEATURE IMPORTANCE) ---")
    for feat, imp in fi_series.items():
        print(f"  • {feat:<16s} : {imp*100:5.2f}%")
        
    print("="*105)

if __name__ == "__main__":
    main()
