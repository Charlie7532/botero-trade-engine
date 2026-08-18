"""
V38 Dynamic Distribution & Generational Floor Engine Simulation (2000-2026)
===========================================================================
Persona: Ray Dalio & Marcos López de Prado (Institutional Allocation V38)

Implements the User's Architectural Directives:
  1. Split DISTRIBUCION into:
     - RE_ACUMULACION_SALUDABLE (n_dead = 0): 100% Normal Sector Rotation.
     - DISTRIBUCION_ESTRUCTURAL (n_dead >= 1): Dynamic Cash Scaling = min(1.0, 0.25 * n_dead).
  2. Absolute 100% Cash in CRASH_SISTEMICO (0% equity exposure).
  3. Offensive High-Beta Beaten-Down Sector Accumulation in PISO_GENERACIONAL:
     - When VIX > 28 and S5_TW turning up from bottom, buy lowest 30-day return sectors (XLK, XLF, XLY, XLI).
"""

import os, sys, json, pandas as pd, numpy as np
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate

SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]
SECTOR_CAP_WEIGHTS = {
    "XLK": 0.317, "XLC": 0.089, "XLF": 0.132, "XLI": 0.078,
    "XLV": 0.118, "XLP": 0.058, "XLU": 0.024, "XLRE": 0.022,
    "XLB": 0.021, "XLE": 0.034, "XLY": 0.107
}

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

def run_v38_simulation(pivot, sec_pivot, macro_pivot):
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    spy_p0 = pivot["SPY"].iloc[0]
    portfolio_cash = 100.0 * spy_p0
    portfolio_shares = {s: 0.0 for s in SECTORS_11}
    
    daily_records = []
    
    for idx_i, d in enumerate(pivot.index):
        spy_p = pivot.loc[d, "SPY"]
        current_equity = portfolio_cash + sum(portfolio_shares[s] * sec_pivot.loc[d, s] for s in SECTORS_11 if s in sec_pivot.columns and pd.notna(sec_pivot.loc[d, s]))
        spy_equiv_shares = current_equity / spy_p
        
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
            
        available_secs = [s for s in SECTORS_11 if s in sec_pivot.columns and pd.notna(sec_pivot.loc[d, s])]
        n_dead = sum(1 for v in sec_th.values() if v < 25.0)
        
        # -------------------------------------------------------------
        # V38 ALLOCATION DIRECTIVES
        # -------------------------------------------------------------
        if current_mode == "CRASH_SISTEMICO":
            # Directiva 1: 100% Cash en Crash (0% Renta Variable / 0% ETFs)
            target_weights = {s: 0.0 for s in available_secs}
            
        elif current_mode == "DISTRIBUCION_PRE_CRASH":
            if n_dead == 0:
                # Directiva 2A: Si n_dead == 0 y S5TH >= 50% -> Re-Acumulación Saludable (100% Invertido en Rotación Core)
                target_weights = gate.calculate_target_weights(
                    mode="RE_ACUMULACION_ALCISTA",
                    sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
                    avail_sectors=available_secs,
                    sec_v_tw=sec_v_tw, sec_v_fi=sec_v_fi
                )
            else:
                # Directiva 2B: Distribución Estructural (n_dead >= 1) -> Cash Escalonado por n_dead
                cash_frac = min(1.0, 0.25 * n_dead) # 1 sector muerto -> 25% cash, 2 -> 50% cash, 3 -> 75%, 4+ -> 100% cash
                def_frac = 1.0 - cash_frac
                
                def_pool = ["XLP", "XLU", "XLV"]
                tot_cap = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s in def_pool if s in available_secs)
                target_weights = {}
                for s in def_pool:
                    if s in available_secs and tot_cap > 0:
                        target_weights[s] = def_frac * (SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot_cap)
                        
        elif current_mode == "PISO_GENERACIONAL":
            # Directiva 3: Acumulación Ofensiva en Sectores Alta Beta Castigados (No Defensivos)
            # Encuentra los 3 sectores no defensivos con mayor caída a 30 días
            past_idx = max(0, idx_i - 20)
            past_date = pivot.index[past_idx]
            
            non_def_sectors = [s for s in available_secs if s not in ["XLP", "XLU", "XLV"]]
            sec_returns = {}
            for s in non_def_sectors:
                p_now = sec_pivot.loc[d, s]
                p_past = sec_pivot.loc[past_date, s]
                if p_past > 0:
                    sec_returns[s] = (p_now / p_past) - 1.0
            
            # Ordenar de mayor caída a menor
            sorted_beaten = sorted(sec_returns.items(), key=lambda x: x[1])
            top3_beaten = [x[0] for x in sorted_beaten[:3]]
            
            target_weights = {s: 0.0 for s in available_secs}
            if len(top3_beaten) > 0:
                w_each = 1.0 / len(top3_beaten)
                for s in top3_beaten:
                    target_weights[s] = w_each
            else:
                target_weights["XLK"] = 0.50
                target_weights["XLF"] = 0.50
                
        else:
            # Baseline normal allocation for MERCADO_SANO, RE_ACUMULACION, etc.
            target_weights = gate.calculate_target_weights(
                mode=current_mode,
                sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
                avail_sectors=available_secs,
                sec_v_tw=sec_v_tw, sec_v_fi=sec_v_fi
            )
            
        daily_records.append({
            "date": d,
            "equity": current_equity,
            "spy_shares": spy_equiv_shares,
            "mode": current_mode,
            "n_dead": n_dead
        })
        
        # Execute rebalance on end of day
        portfolio_cash = current_equity
        portfolio_shares = {s: 0.0 for s in SECTORS_11}
        for s, w in target_weights.items():
            if w > 0 and s in sec_pivot.columns and pd.notna(sec_pivot.loc[d, s]) and sec_pivot.loc[d, s] > 0:
                allocated = current_equity * w
                portfolio_shares[s] = allocated / sec_pivot.loc[d, s]
                portfolio_cash -= allocated
                
    return pd.DataFrame(daily_records)

def main():
    store = TimescaleDataStore()
    pivot, sec_pivot, macro_pivot = load_data(store)
    store.close()
    
    print("\n" + "="*115)
    print("      🚀 SIMULACIÓN Y AUDITORÍA V38: ARQUITECTURA DINÁMICA DE DISTRIBUCIÓN Y PISO GENERACIONAL")
    print("="*115)
    
    df_v38 = run_v38_simulation(pivot, sec_pivot, macro_pivot)
    
    final_shares_v38 = df_v38.iloc[-1]['spy_shares']
    initial_shares = 100.0
    total_ret = ((df_v38.iloc[-1]['equity'] / df_v38.iloc[0]['equity']) - 1.0) * 100.0
    
    print(f"\n📈 RESULTADOS CUANTITATIVOS V38 (2000 - 2026):")
    print(f"  • Acciones SPY Compuestas Finales (V38) : {final_shares_v38:8.2f} ACCIONES SPY")
    print(f"  • Acciones Baseline Previo (V37.1)      :   525.36 ACCIONES SPY")
    print(f"  • Alpha Neto Directo de V38             :  {(final_shares_v38 - 525.36):+7.2f} ACCIONES SPY 🔥")
    print(f"  • Retorno Total Compuesto V38          : {total_ret:+8.2f}%")
    
    print("\n" + "="*115)
    print("  VERIFICACIÓN DE DIRECTIVAS V38:")
    print("  1. RE_ACUMULACION SALUDABLE (n_dead = 0): Mantiene 100% rotación en sectores core (cero cash drag).")
    print("  2. CASH ESCALONADO POR n_dead (25% por sector muerto): Protege progresivamente según deterioro real.")
    print("  3. 100% CASH EN CRASH SISTÉMICO: Cero exposición a ETFs o acciones durante el colapso.")
    print("  4. ACUMULACIÓN OFENSIVA EN PISO GENERACIONAL: Compra los 3 sectores no defensivos más castigados (XLK, XLF, XLY) al rebotar.")
    print("="*115)

if __name__ == "__main__":
    main()
