"""
Comprehensive Final Benchmark Report & Efficiency Statistics (V37.1)
====================================================================
Generates:
  1. Master Compounding Year-by-Year Table (2000-2026)
  2. Master Regime Return Table
  3. Regime Performance & Win Rate Efficiency Matrix
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
        
        df_p = pd.read_sql(f"""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ({p_str})
              AND timeframe = '1d'
              AND time >= '2000-01-01'
            ORDER BY time, ticker
        """, conn)
        pivot = df_p.pivot(index='date', columns='ticker', values='close').ffill()
        
        df_macro = pd.read_sql("""
            SELECT ticker, time::date as date, close 
            FROM market.ohlcv_bars 
            WHERE ticker IN ('VIX', 'CBOE_PCR', 'FG') 
              AND timeframe = '1d' 
              AND time >= '2000-01-01' 
            ORDER BY time
        """, conn)
        macro_pivot = df_macro.pivot(index='date', columns='ticker', values='close').ffill().bfill()
        
        common_dates = pivot.index.intersection(macro_pivot.index)
        return pivot.loc[common_dates], macro_pivot.loc[common_dates]
    finally:
        store._put(conn)

def run_simulation(pivot, macro_pivot):
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    spy_p0 = pivot["SPY"].iloc[0]
    portfolio_cash = 100.0 * spy_p0
    portfolio_shares = {s: 0.0 for s in SECTORS_11}
    
    daily_records = []
    
    for i, d in enumerate(pivot.index):
        spy_p = pivot.loc[d, "SPY"]
        current_equity = portfolio_cash + sum(portfolio_shares[s] * pivot.loc[d, s] for s in SECTORS_11 if s in pivot.columns and pd.notna(pivot.loc[d, s]))
        spy_equiv_shares = current_equity / spy_p
        
        th = pivot.loc[d, "S5TH"]
        fi = pivot.loc[d, "S5FI"]
        tw = pivot.loc[d, "S5TW"]
        v_th = pivot.loc[d, "SV5TH"]
        v_fi = pivot.loc[d, "SV5FI"]
        v_tw = pivot.loc[d, "SV5TW"]
        vix = macro_pivot.loc[d, 'VIX'] if 'VIX' in macro_pivot.columns else 18.0
        
        sec_th = {s: pivot.loc[d, f"S5_{s}_TH"] if f"S5_{s}_TH" in pivot.columns and pd.notna(pivot.loc[d, f"S5_{s}_TH"]) else 50.0 for s in SECTORS_11}
        sec_fi = {s: pivot.loc[d, f"S5_{s}_FI"] if f"S5_{s}_FI" in pivot.columns and pd.notna(pivot.loc[d, f"S5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_tw = {s: pivot.loc[d, f"S5_{s}_TW"] if f"S5_{s}_TW" in pivot.columns and pd.notna(pivot.loc[d, f"S5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        sec_v_fi = {s: pivot.loc[d, f"SV5_{s}_FI"] if f"SV5_{s}_FI" in pivot.columns and pd.notna(pivot.loc[d, f"SV5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_v_tw = {s: pivot.loc[d, f"SV5_{s}_TW"] if f"SV5_{s}_TW" in pivot.columns and pd.notna(pivot.loc[d, f"SV5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        
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
            "year": d.year,
            "equity": current_equity,
            "spy_shares": spy_equiv_shares,
            "spy_price": spy_p,
            "mode": current_mode
        })
        
        available_secs = [s for s in SECTORS_11 if s in pivot.columns and pd.notna(pivot.loc[d, s])]
        target_weights = gate.calculate_target_weights(
            mode=current_mode,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            avail_sectors=available_secs,
            sec_v_fi=sec_v_fi, sec_v_tw=sec_v_tw
        )
        
        portfolio_cash = current_equity
        portfolio_shares = {s: 0.0 for s in SECTORS_11}
        for s, w in target_weights.items():
            if w > 0 and s in pivot.columns and pd.notna(pivot.loc[d, s]) and pivot.loc[d, s] > 0:
                allocated = current_equity * w
                portfolio_shares[s] = allocated / pivot.loc[d, s]
                portfolio_cash -= allocated
                
    return pd.DataFrame(daily_records)

def main():
    store = TimescaleDataStore()
    pivot, macro_pivot = load_data(store)
    store.close()
    
    df_res = run_simulation(pivot, macro_pivot)
    df_res['ret'] = df_res['equity'].pct_change().fillna(0.0)
    
    # Yearly Table
    print("\n" + "="*115)
    print("      📊 BENCHMARK ANUAL DETALLADO: VERSIÓN 37.1 OPTIMIZADA EN PRODUCCIÓN")
    print("="*115)
    print(f"{'Año':<6s} | {'Acciones Fin Año':<18s} | {'Retorno Año (%)':<16s} | {'SPY Benchmark (%)':<18s} | {'Alpha vs SPY'}")
    print("-" * 80)
    
    years = sorted(df_res['year'].unique())
    for y in years:
        sub = df_res[df_res['year'] == y]
        end_shares = sub.iloc[-1]['spy_shares']
        start_equity = sub.iloc[0]['equity']
        end_equity = sub.iloc[-1]['equity']
        y_ret = ((end_equity / start_equity) - 1.0) * 100.0
        
        spy_start = sub.iloc[0]['spy_price']
        spy_end = sub.iloc[-1]['spy_price']
        spy_ret = ((spy_end / spy_start) - 1.0) * 100.0
        
        alpha = y_ret - spy_ret
        print(f"{y:<6d} | {end_shares:18.2f} | {y_ret:+16.2f}% | {spy_ret:+18.2f}% | {alpha:+12.2f}%")

    print("\n" + "="*115)
    print(f"  ACCIONES TOTALES COMPOUNDING V37.1 : {df_res.iloc[-1]['spy_shares']:.2f} Acciones SPY")
    print("="*115)
    
    # Regime Return & Win Rate Efficiency Table
    print("\n" + "="*115)
    print("      🛡️ RENDIMIENTO POR RÉGIMEN Y EFICIENCIA DE TRANSACCIÓN (V37.1)")
    print("="*115)
    print(f"{'Régimen de Mercado':<26s} | {'Días':<6s} | {'Ret. Acum. (%)':<16s} | {'Win Rate (%)':<14s} | {'Profit Factor':<15s} | {'Ret. Prom/Día'}")
    print("-" * 95)
    
    for mode, grp in df_res.groupby('mode'):
        n_days = len(grp)
        tot_ret = (np.prod(1.0 + grp['ret']) - 1.0) * 100.0
        wins = grp[grp['ret'] > 0]['ret']
        losses = grp[grp['ret'] < 0]['ret']
        
        wr = (len(wins) / n_days * 100.0) if n_days > 0 else 0.0
        gross_profit = wins.sum()
        gross_loss = abs(losses.sum())
        pf = (gross_profit / gross_loss) if gross_loss > 0 else (99.9 if gross_profit > 0 else 1.0)
        
        avg_d = grp['ret'].mean() * 100.0
        print(f"{mode:<26s} | {n_days:<6d} | {tot_ret:+16.2f}% | {wr:12.1f}% | {pf:15.2f} | {avg_d:+12.4f}%")

if __name__ == "__main__":
    main()
