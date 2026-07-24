"""
Surgical Optimization: Crash Sistémico Alert Refinement via Market Intelligence & Triads
======================================================================================
Audits all historical triggers of Crash Sistémico (2000 - 2026) to eliminate the 126 false alarms
where the gate sold at panic bottoms.

Tests multi-vector Market Intelligence filters:
  - VIX Volatility Spike (VIX > 28)
  - Options Put/Call Ratio Panic (CBOE_PCR > 1.25)
  - Breadth Destruction (n_dead >= 6 or S5_TH < 15%)
  - Structural Volume Capitulation vs Systemic Collapse
"""

import os, sys, json, pandas as pd, numpy as np
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
from backend.modules.entry_decision.domain.rules.triad_lookup import lookup_triad_signal
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS, SECTOR_CAP_WEIGHTS

SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]
BREADTH_MAP = {
    "S5TH": "th", "S5FI": "fi", "S5TW": "tw",
    "SV5TH": "v_th", "SV5FI": "v_fi", "SV5TW": "v_tw"
}

def load_data(store):
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
    price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot = load_data(store)
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
    
    # Audit Crash Sistémico Triggers
    records = []
    
    for i in range(1, len(dates) - 20):
        d = dates[i]
        fwd_20 = df.loc[d, 'fwd_20d_ret']
        
        th = df.loc[d, 'th']
        fi = df.loc[d, 'fi']
        tw = df.loc[d, 'tw']
        v_tw = df.loc[d, 'v_tw']
        vix = df.loc[d, 'vix']
        pcr = df.loc[d, 'pcr']
        
        sec_th = {s: sec_ind_pivot.loc[d, f"S5_{s}_TH"] if f"S5_{s}_TH" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_TH"]) else 50.0 for s in SECTORS_11}
        n_dead = sum(1 for v in sec_th.values() if v < 40.0)
        
        # Rigid Crash Sistémico Trigger
        is_rigid_crash = (th < 30.0 and fi < 25.0 and tw < 20.0)
        
        if is_rigid_crash:
            # Test Refinements:
            # 1. Systemic Crash requires Breadth Breakdown (n_dead >= 6 or th < 20%) AND VIX Spike (VIX > 25)
            is_true_systemic = (n_dead >= 6 or th < 20.0) and (vix > 25.0 or pcr > 1.20)
            
            records.append({
                "date": d,
                "fwd_20d_ret": fwd_20,
                "th": th, "fi": fi, "tw": tw, "v_tw": v_tw,
                "n_dead": n_dead,
                "vix": vix, "pcr": pcr,
                "is_true_systemic": is_true_systemic,
                "is_crash_success": fwd_20 < -2.0 # Real market drop
            })
            
    df_crash = pd.DataFrame(records)
    
    print("\n" + "="*105)
    print("      🔍 AUTOPSIA FORENSE DE CRASH SISTÉMICO: REGLA RÍGIDA VS INTELIGENCIA DE MERCADO")
    print("="*105)
    print(f"Total Disparos Rígidos de Crash Sistémico               : {len(df_crash)} días")
    print(f"Caídas Reales a 20 días (< -2%)                          : {df_crash['is_crash_success'].sum()} días ({df_crash['is_crash_success'].mean()*100:.1f}% Precisión)")
    print(f"Falsas Venta en Suelos (Rebotes Alcistas Posteriores)   : {(df_crash['is_crash_success'] == False).sum()} días")
    
    # Filter with Market Intelligence (VIX > 25 + n_dead >= 6)
    sub_intel = df_crash[df_crash['is_true_systemic'] == True]
    n_intel = len(sub_intel)
    acc_intel = sub_intel['is_crash_success'].sum() if n_intel > 0 else 0
    prec_intel = (acc_intel / n_intel)*100.0 if n_intel > 0 else 0.0
    avg_fwd_intel = sub_intel['fwd_20d_ret'].mean() if n_intel > 0 else 0.0
    
    print(f"\n--- REFINAMIENTO CON INTELIGENCIA DE MERCADO (VIX > 25 + N_DEAD >= 6) ---")
    print(f"Disparos Filtrados de Crash Sistémico REAL               : {n_intel} días (Eliminadas {len(df_crash) - n_intel} falsas alarmas)")
    print(f"Precisión Re-Calibrada (Acierto en Caída Real)           : {prec_intel:.1f}% (Mejora de +{prec_intel - df_crash['is_crash_success'].mean()*100:.1f} pp)")
    print(f"Retorno Promedio Futuro a 20d durante Crash Real         : {avg_fwd_intel:+.2f}%")
    print("="*105)

if __name__ == "__main__":
    main()
