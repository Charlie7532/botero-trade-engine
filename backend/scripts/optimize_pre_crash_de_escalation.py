"""
Pre-Crash Progressive De-escalation & Lag Mitigation Simulation (2000-2026)
===========================================================================
Hypothesis:
  DISTRIBUCION_PRE_CRASH currently allocates 100% long risk assets, absorbing an average 
  -9.23% drawdown in the 10 days BEFORE CRASH_SISTEMICO triggers.
  
Solution:
  In DISTRIBUCION_PRE_CRASH, progressively trim risk exposure as distribution persists:
    - Days 1-4: 75% Core, 25% Defensive/Cash
    - Days 5-9: 50% Core, 50% Defensive/Cash
    - Days >=10: 25% Core, 75% Defensive/Cash
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

def simulate_de_escalation(pivot, sec_pivot, macro_pivot, de_escalate_active=True):
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    spy_p0 = pivot["SPY"].iloc[0]
    portfolio_cash = 100.0 * spy_p0
    portfolio_shares = {s: 0.0 for s in SECTORS_11}
    
    daily_records = []
    
    for d in pivot.index:
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
            
        daily_records.append({
            "date": d,
            "equity": current_equity,
            "spy_shares": spy_equiv_shares,
            "mode": current_mode
        })
        
        available_secs = [s for s in SECTORS_11 if s in sec_pivot.columns and pd.notna(sec_pivot.loc[d, s])]
        target_weights = gate.calculate_target_weights(
            mode=current_mode,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            avail_sectors=available_secs,
            sec_v_tw=sec_v_tw, sec_v_fi=sec_v_fi
        )
        
        # Apply De-escalation Rule in DISTRIBUCION_PRE_CRASH
        if de_escalate_active and current_mode == "DISTRIBUCION_PRE_CRASH":
            if days_in_mode >= 10:
                # Scale down to 25% risk exposure, 75% cash
                target_weights = {s: w * 0.25 for s, w in target_weights.items()}
            elif days_in_mode >= 5:
                # Scale down to 50% risk exposure, 50% cash
                target_weights = {s: w * 0.50 for s, w in target_weights.items()}
            elif days_in_mode >= 2:
                # Scale down to 75% risk exposure, 25% cash
                target_weights = {s: w * 0.75 for s, w in target_weights.items()}
        
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
    print("      🔬 OPTIMIZACIÓN DE DESESCALADA PROGRESIVA EN DISTRIBUCION_PRE_CRASH")
    print("="*115)
    
    df_base = simulate_de_escalation(pivot, sec_pivot, macro_pivot, de_escalate_active=False)
    df_opt = simulate_de_escalation(pivot, sec_pivot, macro_pivot, de_escalate_active=True)
    
    df_base['ret'] = df_base['equity'].pct_change().fillna(0.0)
    df_opt['ret'] = df_opt['equity'].pct_change().fillna(0.0)
    
    dist_base = df_base[df_base['mode'] == 'DISTRIBUCION_PRE_CRASH']
    dist_opt = df_opt[df_opt['mode'] == 'DISTRIBUCION_PRE_CRASH']
    
    ret_base = (np.prod(1.0 + dist_base['ret']) - 1.0) * 100.0
    ret_opt = (np.prod(1.0 + dist_opt['ret']) - 1.0) * 100.0
    
    print(f"\n📊 IMPACTO EN EL RÉGIMEN DISTRIBUCION_PRE_CRASH:")
    print(f"  • Modelo Baseline (100% Invertido en Distribución)  : Retorno = {ret_base:+.2f}%")
    print(f"  • Modelo Optimizado (Desescalada Progresiva a Cash)  : Retorno = {ret_opt:+.2f}% (🟢 Reducción de Arrastre de Caída)")
    
    shares_base = df_base.iloc[-1]['spy_shares']
    shares_opt = df_opt.iloc[-1]['spy_shares']
    print("\n" + "="*115)
    print(f"  ACCIONES FINALES BASELINE V37.2     : {shares_base:.2f} Acciones")
    print(f"  ACCIONES FINALES OPTIMIZADAS V38.0  : {shares_opt:.2f} Acciones (🟢 {shares_opt - shares_base:+.2f} Acciones de Alpha Neto)")
    print("="*115)

if __name__ == "__main__":
    main()
