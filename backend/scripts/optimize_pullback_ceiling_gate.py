"""
Ceiling-Filtered Pullback Gate Optimization (2000-2026)
========================================================
Applies the Techo/Ceiling Inverse Kinetics Rule to PULLBACK_ALCISTA:
  - If Ratio S5_TW / SV5_TW was >= 3.50 within last 5 days (extreme dilation ceiling),
    block entering PULLBACK_ALCISTA to avoid buying direct slides from the top.
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
        
        # Load sector indicators
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
        
        common_dates = pivot.index.intersection(sec_pivot.index)
        return pivot.loc[common_dates], sec_pivot.loc[common_dates]
    finally:
        store._put(conn)

def simulate_with_ceiling_filter(pivot, sec_pivot, filter_active=True):
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    spy_p0 = pivot["SPY"].iloc[0]
    portfolio_cash = 100.0 * spy_p0
    portfolio_shares = {s: 0.0 for s in SECTORS_11}
    
    daily_records = []
    ratio_history = []
    
    for i, d in enumerate(pivot.index):
        spy_p = pivot.loc[d, "SPY"]
        current_equity = portfolio_cash + sum(portfolio_shares[s] * sec_pivot.loc[d, s] for s in SECTORS_11 if s in sec_pivot.columns and pd.notna(sec_pivot.loc[d, s]))
        spy_equiv_shares = current_equity / spy_p
        
        th = pivot.loc[d, "S5TH"]
        fi = pivot.loc[d, "S5FI"]
        tw = pivot.loc[d, "S5TW"]
        v_th = pivot.loc[d, "SV5TH"]
        v_fi = pivot.loc[d, "SV5FI"]
        v_tw = pivot.loc[d, "SV5TW"]
        
        ratio = tw / max(1.0, v_tw)
        ratio_history.append(ratio)
        if len(ratio_history) > 7:
            ratio_history.pop(0)
            
        sec_th = {s: sec_pivot.loc[d, f"S5_{s}_TH"] if f"S5_{s}_TH" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"S5_{s}_TH"]) else 50.0 for s in SECTORS_11}
        sec_fi = {s: sec_pivot.loc[d, f"S5_{s}_FI"] if f"S5_{s}_FI" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"S5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_tw = {s: sec_pivot.loc[d, f"S5_{s}_TW"] if f"S5_{s}_TW" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"S5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        sec_v_tw = {s: sec_pivot.loc[d, f"SV5_{s}_TW"] if f"SV5_{s}_TW" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"SV5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        sec_v_fi = {s: sec_pivot.loc[d, f"SV5_{s}_FI"] if f"SV5_{s}_FI" in sec_pivot.columns and pd.notna(sec_pivot.loc[d, f"SV5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw, sec_v_tw=sec_v_tw,
            current_mode=current_mode, days_in_mode=days_in_mode, tw_prev=prev_tw
        )
        prev_tw = tw
        
        # Apply the Ceiling/Techo Filter to PULLBACK_ALCISTA
        if filter_active and new_mode == "PULLBACK_ALCISTA":
            # If we recently had an extreme ceiling dilation (ratio >= 3.50 in last 5 days), block pullback entry!
            had_recent_ceiling = any(r >= 3.50 for r in ratio_history[:-1]) if len(ratio_history) > 1 else False
            if had_recent_ceiling:
                new_mode = current_mode # Block the pullback entry
        
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
    pivot, sec_pivot = load_data(store)
    store.close()
    
    print("\n" + "="*115)
    print("      🔬 OPTIMIZACIÓN DE PULLBACK_ALCISTA MEDIANTE FILTRO DE TECHO (CEILING FILTER)")
    print("="*115)
    
    df_base = simulate_with_ceiling_filter(pivot, sec_pivot, filter_active=False)
    df_opt = simulate_with_ceiling_filter(pivot, sec_pivot, filter_active=True)
    
    df_base['ret'] = df_base['equity'].pct_change().fillna(0.0)
    df_opt['ret'] = df_opt['equity'].pct_change().fillna(0.0)
    
    pb_base = df_base[df_base['mode'] == 'PULLBACK_ALCISTA']
    pb_opt = df_opt[df_opt['mode'] == 'PULLBACK_ALCISTA']
    
    ret_base = (np.prod(1.0 + pb_base['ret']) - 1.0) * 100.0 if len(pb_base) > 0 else 0.0
    ret_opt = (np.prod(1.0 + pb_opt['ret']) - 1.0) * 100.0 if len(pb_opt) > 0 else 0.0
    
    print(f"\n📊 COMPARATIVA DE RENDIMIENTO DE PULLBACK_ALCISTA:")
    print(f"  • Modelo Baseline (Sin Filtro de Techo)  : Días = {len(pb_base):<4d} | Retorno Acumulado = {ret_base:+.2f}%")
    print(f"  • Modelo Optimizado (Con Filtro de Techo) : Días = {len(pb_opt):<4d} | Retorno Acumulado = {ret_opt:+.2f}%")
    
    shares_base = df_base.iloc[-1]['spy_shares']
    shares_opt = df_opt.iloc[-1]['spy_shares']
    print("\n" + "="*115)
    print(f"  ACCIONES FINALES BASELINE V37.1     : {shares_base:.2f} Acciones")
    print(f"  ACCIONES FINALES OPTIMIZADAS V37.2  : {shares_opt:.2f} Acciones (🟢 {shares_opt - shares_base:+.2f} Acciones de Alpha Neto)")
    print("="*115)

if __name__ == "__main__":
    main()
