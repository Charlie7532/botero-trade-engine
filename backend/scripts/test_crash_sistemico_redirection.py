"""
Redirection Audit: Convert False Crash Sistémico Selling into Piso Generacional Accumulation
=============================================================================================
Tests converting extreme breadth capitulation (TH < 25%) from an EXIT-TO-CASH signal
into a PISO_GENERACIONAL accumulation signal, reserving CRASH_SISTEMICO strictly for
structural volume breakdowns (SV5_TH < 30%) with high VIX volatility (VIX > 30).

Prints BOTH MASTER TABLES:
  - TABLA 1: Rendimiento Año a Año (2000-2026)
  - TABLA 2: Atribución por Régimen de Mercado
"""

import os, sys, json, pandas as pd, numpy as np
import psycopg2
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
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

def run_redirected_sim(price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot):
    dates = sorted(price_pivot.index)
    spy_p0 = price_pivot["SPY"].iloc[0]
    
    initial_capital = 100.0 * spy_p0
    portfolio_cash = initial_capital
    portfolio_shares = {s: 0.0 for s in SECTORS_11}
    
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    daily_records = []
    yearly_records = []
    curr_yr = dates[0].year
    
    for i, d in enumerate(dates):
        spy_p = price_pivot.loc[d, "SPY"]
        current_equity = portfolio_cash + sum(portfolio_shares[s] * price_pivot.loc[d, s] for s in SECTORS_11 if s in price_pivot.columns and pd.notna(price_pivot.loc[d, s]))
        spy_equiv_shares = current_equity / spy_p
        
        th = mkt_breadth.loc[d, "th"]
        fi = mkt_breadth.loc[d, "fi"]
        tw = mkt_breadth.loc[d, "tw"]
        v_th = mkt_breadth.loc[d, "v_th"]
        v_fi = mkt_breadth.loc[d, "v_fi"]
        v_tw = mkt_breadth.loc[d, "v_tw"]
        
        vix = macro_pivot.loc[d, 'VIX'] if 'VIX' in macro_pivot.columns else 18.0
        
        sec_th = {s: sec_ind_pivot.loc[d, f"S5_{s}_TH"] if f"S5_{s}_TH" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_TH"]) else 50.0 for s in SECTORS_11}
        sec_fi = {s: sec_ind_pivot.loc[d, f"S5_{s}_FI"] if f"S5_{s}_FI" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_tw = {s: sec_ind_pivot.loc[d, f"S5_{s}_TW"] if f"S5_{s}_TW" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        sec_v_fi = {s: sec_ind_pivot.loc[d, f"SV5_{s}_FI"] if f"SV5_{s}_FI" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"SV5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_v_tw = {s: sec_ind_pivot.loc[d, f"SV5_{s}_TW"] if f"SV5_{s}_TW" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"SV5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        
        hot_tw = sum(1 for v in sec_tw.values() if v > 50.0)
        cold_tw = sum(1 for v in sec_tw.values() if v < 20.0)
        is_pre_crash_distribution = (v_tw < 40.0 and th < 45.0) or (hot_tw <= 1 and cold_tw >= 7)
        
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            current_mode=current_mode, days_in_mode=days_in_mode, tw_prev=prev_tw
        )
        prev_tw = tw
        
        # REDIRECTION FIX: If new_mode is CRASH_SISTEMICO but VIX <= 28 or v_th >= 25%, redirect to PISO_GENERACIONAL!
        if new_mode == "CRASH_SISTEMICO":
            if vix <= 28.0 and v_th >= 25.0:
                new_mode = "PISO_GENERACIONAL"
                
        if new_mode == current_mode:
            days_in_mode += 1
        else:
            current_mode = new_mode
            days_in_mode = 1
            
        daily_records.append({"date": d, "equity": current_equity, "mode": current_mode})
        
        available_secs = [s for s in SECTORS_11 if s in price_pivot.columns and pd.notna(price_pivot.loc[d, s])]
        target_weights = gate.calculate_target_weights(
            mode=current_mode,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            avail_sectors=available_secs,
            sec_v_fi=sec_v_fi, sec_v_tw=sec_v_tw
        )
        
        portfolio_cash = current_equity
        portfolio_shares = {s: 0.0 for s in SECTORS_11}
        for s, w in target_weights.items():
            if w > 0 and s in price_pivot.columns and pd.notna(price_pivot.loc[d, s]) and price_pivot.loc[d, s] > 0:
                allocated = current_equity * w
                portfolio_shares[s] = allocated / price_pivot.loc[d, s]
                portfolio_cash -= allocated

        if i < len(dates) - 1 and dates[i+1].year != curr_yr:
            yearly_records.append({"year": curr_yr, "spy_shares": round(spy_equiv_shares, 2)})
            curr_yr = dates[i+1].year
            
    yearly_records.append({"year": curr_yr, "spy_shares": round(spy_equiv_shares, 2)})
    df_daily = pd.DataFrame(daily_records)
    df_daily['daily_ret'] = df_daily['equity'].pct_change().fillna(0.0)
    return spy_equiv_shares, pd.DataFrame(yearly_records).set_index("year"), df_daily

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot = load_data(store)
    store.close()
    
    sh_final, df_yearly, df_daily = run_redirected_sim(price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot)
    
    print("\n" + "="*105)
    print("      📈 TABLA 1: RENDIMIENTO AÑO A AÑO (RE-DIRECCIÓN DE CRASH SISTÉMICO A PISO GENERACIONAL)")
    print("="*105)
    print(f"{'Año':<6s} | {'Acciones SPY Acumuladas':<25s} | {'Multiplicador'}")
    print("-" * 105)
    
    for yr in df_yearly.index:
        sh = df_yearly.loc[yr, 'spy_shares']
        print(f"{yr:<6d} | {sh:25.2f} | {sh/100.0:6.2f}x")
        
    print("="*105)
    print(f"ACCIONES FINALES ACUMULADAS: {sh_final:.2f} Acciones SPY ({sh_final/100.0:.2f}x Compounding) 🟢")
    print("="*105)
    
    print("\n" + "="*105)
    print("      🛡️ TABLA 2: ATRIBUCIÓN INTEGRAL POR RÉGIMEN DE MERCADO")
    print("="*105)
    print(f"{'Régimen de Mercado':<28s} | {'Días':<8s} | {'%Tiempo':<10s} | {'Retorno Acumulado':<20s} | {'Win Rate'}")
    print("-" * 105)
    
    regimes = sorted(df_daily['mode'].unique())
    tot_days = len(df_daily)
    
    for reg in regimes:
        sub = df_daily[df_daily['mode'] == reg]
        n_days = len(sub)
        pct = (n_days / tot_days) * 100.0
        ret_cum = ((1.0 + sub['daily_ret']).prod() - 1.0) * 100.0
        wr = (sub['daily_ret'] > 0).mean() * 100.0
        print(f"{reg:<28s} | {n_days:<8d} | {pct:8.2f}% | {ret_cum:+18.2f}% | {wr:6.1f}%")
        
    print("="*105)

if __name__ == "__main__":
    main()
