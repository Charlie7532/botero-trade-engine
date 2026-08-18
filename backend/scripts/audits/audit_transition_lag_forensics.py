"""
Transition Lag & Preceding Regime Forensics Audit (2000-2026)
=============================================================
Persona: Marcos López de Prado & Benn Eifert

Audits the lead/lag time of transitions into:
  1. CRASH_SISTEMICO
  2. PULLBACK_ALCISTA

Measures:
  - Preceding regime identity (where did we come from?).
  - Drawdown incurred in the 5d and 10d BEFORE the state transition triggered.
  - Early-warning indicators (Breadth Velocity, Volume Acceleration) that could trigger earlier protection.
"""

import os, sys, json, pandas as pd, numpy as np
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate

SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]

def load_data(store):
    conn = store._conn()
    try:
        df_p = pd.read_sql("""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ('SPY', 'S5TH', 'S5FI', 'S5TW', 'SV5TH', 'SV5FI', 'SV5TW')
              AND timeframe = '1d'
              AND time >= '2000-01-01'
            ORDER BY time, ticker
        """, conn)
        pivot = df_p.pivot(index='date', columns='ticker', values='close').ffill()
        
        sec_ind_tickers = []
        for s in SECTORS_11:
            sec_ind_tickers.extend([f"S5_{s}_TH", f"S5_{s}_FI", f"S5_{s}_TW", f"SV5_{s}_TH", f"SV5_{s}_FI", f"SV5_{s}_TW"])
        p_str = ", ".join([f"'{t}'" for t in sec_ind_tickers + SECTORS_11])
        
        df_sectors = pd.read_sql(f"""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ({p_str})
              AND timeframe = '1d'
              AND time >= '2000-01-01'
            ORDER BY time, ticker
        """, conn)
        sec_pivot = df_sectors.pivot(index='date', columns='ticker', values='close').ffill()
        
        df_macro = pd.read_sql("""
            SELECT ticker, time::date as date, close 
            FROM market.ohlcv_bars 
            WHERE ticker IN ('VIX') 
              AND timeframe = '1d' 
              AND time >= '2000-01-01' 
            ORDER BY time
        """, conn)
        macro_pivot = df_macro.pivot(index='date', columns='ticker', values='close').ffill().bfill()
        
        common_dates = pivot.index.intersection(sec_pivot.index).intersection(macro_pivot.index)
        return pivot.loc[common_dates], sec_pivot.loc[common_dates], macro_pivot.loc[common_dates]
    finally:
        store._put(conn)

def audit_transitions():
    store = TimescaleDataStore()
    pivot, sec_pivot, macro_pivot = load_data(store)
    store.close()
    
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    modes_history = []
    
    for d in pivot.index:
        th = pivot.loc[d, "S5TH"]
        fi = pivot.loc[d, "S5FI"]
        tw = pivot.loc[d, "S5TW"]
        v_th = pivot.loc[d, "SV5TH"]
        v_fi = pivot.loc[d, "SV5FI"]
        v_tw = pivot.loc[d, "SV5TW"]
        vix = macro_pivot.loc[d, 'VIX'] if 'VIX' in macro_pivot.columns else 18.0
        
        sec_th = {s: sec_pivot.loc[d, f"S5_{s}_TH"] if f"S5_{s}_TH" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"S5_{s}_TH"]) else 50.0 for s in SECTORS_11}
        sec_fi = {s: sec_pivot.loc[d, f"S5_{s}_FI"] if f"S5_{s}_FI" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"S5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_tw = {s: sec_pivot.loc[d, f"S5_{s}_TW"] if f"S5_{s}_TW" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"S5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        sec_v_tw = {s: sec_pivot.loc[d, f"SV5_{s}_TW"] if f"SV5_{s}_TW" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"SV5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        sec_v_fi = {s: sec_pivot.loc[d, f"SV5_{s}_FI"] if f"SV5_{s}_FI" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"SV5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw, sec_v_tw=sec_v_tw,
            current_mode=current_mode, days_in_mode=days_in_mode, tw_prev=prev_tw,
            vix=vix
        )
        prev_tw = tw
        
        if new_mode == current_mode:
            days_in_mode += 1
        else:
            current_mode = new_mode
            days_in_mode = 1
            
        modes_history.append({
            "date": d,
            "spy": pivot.loc[d, "SPY"],
            "mode": current_mode,
            "th": th, "fi": fi, "tw": tw,
            "v_fi": v_fi, "v_tw": v_tw,
            "vix": vix
        })
        
    df = pd.DataFrame(modes_history)
    df['prev_mode'] = df['mode'].shift(1)
    
    print("\n" + "="*115)
    print("      🔬 AUDITORÍA DE RETARDO DE TRANSICIÓN Y DESGASTE PREVIO EN TRANSICIONES CLAVE")
    print("="*115)
    
    # 1. Transitions into CRASH_SISTEMICO
    crash_trans = df[(df['mode'] == 'CRASH_SISTEMICO') & (df['prev_mode'] != 'CRASH_SISTEMICO')]
    print(f"\n📌 1. TRANSICIONES HACIA 'CRASH_SISTEMICO' (Total Eventos: {len(crash_trans)}):")
    print(f"{'Fecha Transición':<16s} | {'Régimen Previo':<24s} | {'Retorno SPY (t-5 a t0)':<24s} | {'Retorno SPY (t-10 a t0)'}")
    print("-" * 88)
    
    for idx, row in crash_trans.iterrows():
        i = df.index.get_loc(idx)
        p_zero = row['spy']
        p_m5 = df.iloc[max(0, i-5)]['spy']
        p_m10 = df.iloc[max(0, i-10)]['spy']
        ret_5 = ((p_zero / p_m5) - 1.0) * 100.0
        ret_10 = ((p_zero / p_m10) - 1.0) * 100.0
        print(f"{str(row['date']):<16s} | {str(row['prev_mode']):<24s} | {ret_5:+22.2f}% | {ret_10:+22.2f}%")

    # 2. Transitions into PULLBACK_ALCISTA
    pb_trans = df[(df['mode'] == 'PULLBACK_ALCISTA') & (df['prev_mode'] != 'PULLBACK_ALCISTA')]
    print(f"\n📌 2. TRANSICIONES HACIA 'PULLBACK_ALCISTA' (Total Eventos: {len(pb_trans)}):")
    print(f"{'Fecha Transición':<16s} | {'Régimen Previo':<24s} | {'Retorno SPY (t-5 a t0)':<24s} | {'Retorno SPY (t-10 a t0)'}")
    print("-" * 88)
    
    pb_ret_5_list = []
    pb_ret_10_list = []
    
    for idx, row in pb_trans.iterrows():
        i = df.index.get_loc(idx)
        p_zero = row['spy']
        p_m5 = df.iloc[max(0, i-5)]['spy']
        p_m10 = df.iloc[max(0, i-10)]['spy']
        ret_5 = ((p_zero / p_m5) - 1.0) * 100.0
        ret_10 = ((p_zero / p_m10) - 1.0) * 100.0
        pb_ret_5_list.append(ret_5)
        pb_ret_10_list.append(ret_10)
        print(f"{str(row['date']):<16s} | {str(row['prev_mode']):<24s} | {ret_5:+22.2f}% | {ret_10:+22.2f}%")

    print("\n" + "="*115)
    print(f"📊 RESUMEN CUANTITATIVO:")
    print(f"  • PULLBACK_ALCISTA - Caída Media Sufrida EN EL RÉGIMEN PREVIO antes de activar Pullback:")
    print(f"      - Retorno Previo a 5 Días  (t-5  a t0): {np.mean(pb_ret_5_list):+.2f}%")
    print(f"      - Retorno Previo a 10 Días (t-10 a t0): {np.mean(pb_ret_10_list):+.2f}%")
    print("="*115)

if __name__ == "__main__":
    audit_transitions()
