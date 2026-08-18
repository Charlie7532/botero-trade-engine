"""
Targeted 3D Optimization Audit for PISO_GENERACIONAL and PULLBACK_ALCISTA (2000-2026)
=====================================================================================
Measures the exact empirical interaction and combined alpha of:
  1. PULLBACK_ALCISTA: Inertia desaceleration + Ratio TW/FI <= 0.75 + Multi-sector volume support.
  2. PISO_GENERACIONAL: Day-0 3D Volume Absorption (Div_FI >= +35%, Div_TH >= +20%, Ratio_inv <= 0.35).
"""

import os, sys, json, pandas as pd, numpy as np
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate

SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]
BREADTH_MAP = {
    "S5TH": "th", "S5FI": "fi", "S5TW": "tw",
    "SV5TH": "v_th", "SV5FI": "v_fi", "SV5TW": "v_tw"
}

def load_data(store):
    conn = store._conn()
    try:
        all_tickers = ["SPY"] + SECTORS_11 + list(BREADTH_MAP.keys())
        sec_ind_tickers = []
        for s in SECTORS_11:
            sec_ind_tickers.extend([f"S5_{s}_TH", f"S5_{s}_FI", f"S5_{s}_TW", f"SV5_{s}_TH", f"SV5_{s}_FI", f"SV5_{s}_TW"])
            
        all_query_tickers = list(set(all_tickers + sec_ind_tickers))
        p_str = ", ".join([f"'{t}'" for t in all_query_tickers])
        
        df = pd.read_sql(f"""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ({p_str})
              AND timeframe = '1d'
              AND time >= '2000-01-01'
            ORDER BY time, ticker
        """, conn)
        pivot = df.pivot(index='date', columns='ticker', values='close').ffill()
        return pivot
    finally:
        store._put(conn)

def simulate_targeted(df):
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    spy_p0 = df["SPY"].iloc[0]
    portfolio_cash = 100.0 * spy_p0
    portfolio_shares = {s: 0.0 for s in SECTORS_11}
    
    daily_records = []
    
    for i, d in enumerate(df.index):
        spy_p = df.loc[d, "SPY"]
        current_equity = portfolio_cash + sum(portfolio_shares[s] * df.loc[d, s] for s in SECTORS_11 if s in df.columns and pd.notna(df.loc[d, s]))
        spy_equiv_shares = current_equity / spy_p
        
        th = df.loc[d, "S5TH"]
        fi = df.loc[d, "S5FI"]
        tw = df.loc[d, "S5TW"]
        v_th = df.loc[d, "SV5TH"]
        v_fi = df.loc[d, "SV5FI"]
        v_tw = df.loc[d, "SV5TW"]
        
        sec_th = {s: df.loc[d, f"S5_{s}_TH"] if f"S5_{s}_TH" in df.columns and pd.notna(df.loc[d, f"S5_{s}_TH"]) else 50.0 for s in SECTORS_11}
        sec_fi = {s: df.loc[d, f"S5_{s}_FI"] if f"S5_{s}_FI" in df.columns and pd.notna(df.loc[d, f"S5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_tw = {s: df.loc[d, f"S5_{s}_TW"] if f"S5_{s}_TW" in df.columns and pd.notna(df.loc[d, f"S5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        sec_v_fi = {s: df.loc[d, f"SV5_{s}_FI"] if f"SV5_{s}_FI" in df.columns and pd.notna(df.loc[d, f"SV5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_v_tw = {s: df.loc[d, f"SV5_{s}_TW"] if f"SV5_{s}_TW" in df.columns and pd.notna(df.loc[d, f"SV5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw, sec_v_tw=sec_v_tw,
            current_mode=current_mode, days_in_mode=days_in_mode, tw_prev=prev_tw
        )
        
        # Targeted 3D overrides for PISO_GENERACIONAL & PULLBACK_ALCISTA
        div_fi = v_fi - fi
        div_th = v_th - th
        ratio_inv = tw / max(1.0, v_tw)
        ratio_tw_fi = tw / max(1.0, fi)
        
        # 1. Targeted PISO_GENERACIONAL Day-0 Trigger
        if current_mode in ("NORMAL", "DISTRIBUCION_PRE_CRASH", "CAPITULACION_SECTORIAL") and th <= 35.0:
            if div_fi >= 35.0 and div_th >= 20.0 and ratio_inv <= 0.40:
                new_mode = "PISO_GENERACIONAL"
                
        # 2. Targeted PULLBACK_ALCISTA 3D Filter
        if new_mode == "PULLBACK_ALCISTA":
            if ratio_tw_fi > 0.85: # Require tactical dislocation (TW is truly oversold relative to FI)
                new_mode = current_mode # Block false pullback
                
        prev_tw = tw
        
        if new_mode == current_mode:
            days_in_mode += 1
        else:
            current_mode = new_mode
            days_in_mode = 1
            
        daily_records.append({
            "date": d,
            "equity": current_equity,
            "spy_shares": spy_equiv_shares,
            "mode": current_mode
        })
        
        available_secs = [s for s in SECTORS_11 if s in df.columns and pd.notna(df.loc[d, s])]
        target_weights = gate.calculate_target_weights(
            mode=current_mode,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            avail_sectors=available_secs,
            sec_v_fi=sec_v_fi, sec_v_tw=sec_v_tw
        )
        
        portfolio_cash = current_equity
        portfolio_shares = {s: 0.0 for s in SECTORS_11}
        for s, w in target_weights.items():
            if w > 0 and s in df.columns and pd.notna(df.loc[d, s]) and df.loc[d, s] > 0:
                allocated = current_equity * w
                portfolio_shares[s] = allocated / df.loc[d, s]
                portfolio_cash -= allocated
                
    return pd.DataFrame(daily_records)

def main():
    store = TimescaleDataStore()
    df = load_data(store)
    store.close()
    
    print("\n" + "="*115)
    print("      🔬 OPTIMIZACIÓN QUIRÚRGICA: PISO_GENERACIONAL Y PULLBACK_ALCISTA 3D")
    print("="*115)
    
    df_res = simulate_targeted(df)
    df_res['ret'] = df_res['equity'].pct_change().fillna(0.0)
    
    print(f"\n📊 DESEMPEÑO POR RÉGIMEN TARGET:")
    print(f"{'Régimen':<26s} | {'Días Totales':<12s} | {'Retorno Acumulado (%)':<22s} | {'Retorno Promedio Diario (%)'}")
    print("-" * 85)
    
    for mode, grp in df_res.groupby('mode'):
        n_days = len(grp)
        tot_ret = (np.prod(1.0 + grp['ret']) - 1.0) * 100.0
        avg_d = grp['ret'].mean() * 100.0
        print(f"{mode:<26s} | {n_days:<12d} | {tot_ret:+22.2f}% | {avg_d:+26.4f}%")
        
    print("\n" + "="*115)
    print(f"  ACCIONES TOTALES COMPOUNDING TARGETED : {df_res.iloc[-1]['spy_shares']:.2f} Acciones (vs 100.00 iniciales)")
    print("="*115)

if __name__ == "__main__":
    main()
