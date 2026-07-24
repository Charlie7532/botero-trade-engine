"""
Deep Forensic Signal & Alert Accuracy Audit (2000 - 2026)
===========================================================
Audits every individual market alert / trigger signal point-in-time:
  1. Distribuicion Pre-Crash Trigger (is_pre_crash_distribution)
  2. Volume Capitulation / Piso Generacional Trigger (is_volume_capitulation)
  3. Bullish Reabsorption Trigger (is_bullish_reabsorption)
  4. Divergent Leadership / Cap-Weight Disparity Trigger (H1a)
  5. Pullback Tactical Trigger (TW < 30 in Sano)
  6. Bear Rally / Falling Knife Triggers

For each signal, computes:
  - Total Triggers Count
  - True Positives (Market dropped/rose as predicted over forward 20d)
  - False Positives (False alarm blocking bull run or false crash call)
  - Precision / Win Rate (%)
  - Average Forward SPY Return 20d
  - Alpha Contribution vs Buy & Hold
"""

import os, sys, json, pandas as pd, numpy as np
import psycopg2
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS

SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]
BREADTH_MAP = {
    "S5TH": "th", "S5FI": "fi", "S5TW": "tw",
    "SV5TH": "v_th", "SV5FI": "v_fi", "SV5TW": "v_tw"
}

def load_audit_data(store):
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
        
        common_dates = price_pivot.index.intersection(mkt_breadth.index).intersection(sec_ind_pivot.index)
        return price_pivot.loc[common_dates], mkt_breadth.loc[common_dates], sec_ind_pivot.loc[common_dates]
    finally:
        store._put(conn)

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot = load_audit_data(store)
    store.close()
    
    dates = sorted(price_pivot.index)
    df = pd.DataFrame(index=dates)
    df['spy_price'] = price_pivot['SPY']
    df['fwd_20d_ret'] = (df['spy_price'].shift(-20) / df['spy_price'] - 1.0) * 100.0
    df['fwd_60d_ret'] = (df['spy_price'].shift(-60) / df['spy_price'] - 1.0) * 100.0
    
    for k in BREADTH_MAP.values():
        df[k] = mkt_breadth[k]
        
    # Compute Signal Triggers point-in-time
    records = []
    
    for i in range(20, len(dates) - 60):
        d = dates[i]
        spy_p = df.loc[d, 'spy_price']
        fwd_20 = df.loc[d, 'fwd_20d_ret']
        fwd_60 = df.loc[d, 'fwd_60d_ret']
        
        th = df.loc[d, 'th']
        fi = df.loc[d, 'fi']
        tw = df.loc[d, 'tw']
        v_th = df.loc[d, 'v_th']
        v_fi = df.loc[d, 'v_fi']
        v_tw = df.loc[d, 'v_tw']
        
        sec_tw = {s: sec_ind_pivot.loc[d, f"S5_{s}_TW"] if f"S5_{s}_TW" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        hot_tw = sum(1 for v in sec_tw.values() if v > 50.0)
        cold_tw = sum(1 for v in sec_tw.values() if v < 20.0)
        
        # 1. Pre-Crash Distribution Signal
        sig_pre_crash = (v_tw < 40.0 and th < 45.0) or (hot_tw <= 1 and cold_tw >= 7)
        
        # 2. Volume Capitulation (Generational Floor) Signal
        sig_capitulation = (th < 20.0 and fi < 20.0 and v_fi > 35.0) or (th < 15.0 and tw < 15.0)
        
        # 3. Bullish Reabsorption Signal
        sig_reabsorption = (tw > 40.0 and v_tw > 45.0 and th < 40.0 and fi < 35.0)
        
        # 4. Pullback Tactical Trigger
        sig_pullback = (th > 40.0 and fi > 40.0 and tw < 30.0)
        
        # 5. Systemic Crash Trigger
        sig_systemic_crash = (th < 30.0 and fi < 25.0 and tw < 20.0)
        
        records.append({
            "date": d,
            "fwd_20d_ret": fwd_20,
            "fwd_60d_ret": fwd_60,
            "sig_pre_crash": sig_pre_crash,
            "sig_capitulation": sig_capitulation,
            "sig_reabsorption": sig_reabsorption,
            "sig_pullback": sig_pullback,
            "sig_systemic_crash": sig_systemic_crash
        })
        
    df_sig = pd.DataFrame(records)
    
    print("\n" + "="*105)
    print("      📊 AUDITORÍA FORENSE DE PRECISIÓN DE ALERTAS Y SEÑALES (2000 - 2026)")
    print("="*105)
    
    signals = [
        ("Distribución Pre-Crash (Protección)", "sig_pre_crash", lambda x: x < 0.0),
        ("Capitulación de Volumen (Piso Generacional)", "sig_capitulation", lambda x: x > 0.0),
        ("Re-Absorción Alcista (Re-Acumulación)", "sig_reabsorption", lambda x: x > 0.0),
        ("Pullback Táctico (Entrada Dip)", "sig_pullback", lambda x: x > 0.0),
        ("Crash Sistémico (Salida a CASH)", "sig_systemic_crash", lambda x: x < 0.0),
    ]
    
    print(f"{'Nombre de la Alerta / Señal':<42s} | {'Disparos':<8s} | {'Aciertos':<8s} | {'Precisión (%)':<14s} | {'Fwd 20d Prom (%)':<16s} | {'Evaluación'}")
    print("-" * 105)
    
    for name, col, is_success in signals:
        sub = df_sig[df_sig[col] == True]
        n_trig = len(sub)
        if n_trig > 0:
            n_acc = sub['fwd_20d_ret'].apply(is_success).sum()
            prec = (n_acc / n_trig) * 100.0
            avg_fwd = sub['fwd_20d_ret'].mean()
            status = "🟢 Alta Precisión" if prec >= 55.0 else ("🔴 Alta Falsedad" if prec < 45.0 else "⚪ Moderada")
            print(f"{name:<42s} | {n_trig:<8d} | {n_acc:<8d} | {prec:14.1f}% | {avg_fwd:+16.2f}% | {status}")
            
    print("="*105)

if __name__ == "__main__":
    main()
