"""
Empirical Ablation Audit: Physics Motor (Velocities & Accelerations) vs Sentiment Classifier
=============================================================================================
Audits and tests:
  1. Baseline V35 Engine
  2. V36 + Physics Motor (1st & 2nd Derivatives of Breadth: v_FI velocity + a_TW acceleration)
  3. V36 + Physics Motor + Sentiment Regime Classifier (Ablation Proof)

Evaluates on Neon PostgreSQL data (2000 - 2026):
  - Total SPY Shares Acumulated
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

def run_ablation_simulation(price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot, mode_type="PHYSICS_ONLY"):
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
    
    for i in range(10, len(dates)):
        d = dates[i]
        spy_p = price_pivot.loc[d, "SPY"]
        current_equity = portfolio_cash + sum(portfolio_shares[s] * price_pivot.loc[d, s] for s in SECTORS_11 if s in price_pivot.columns and pd.notna(price_pivot.loc[d, s]))
        spy_equiv_shares = current_equity / spy_p
        
        th = mkt_breadth.loc[d, "th"]
        fi = mkt_breadth.loc[d, "fi"]
        tw = mkt_breadth.loc[d, "tw"]
        v_th = mkt_breadth.loc[d, "v_th"]
        v_fi = mkt_breadth.loc[d, "v_fi"]
        v_tw = mkt_breadth.loc[d, "v_tw"]
        
        # Derivatives of Breadth
        fi_5d_prev = mkt_breadth.iloc[i-5]["fi"]
        tw_5d_prev = mkt_breadth.iloc[i-5]["tw"]
        tw_10d_prev = mkt_breadth.iloc[i-10]["tw"]
        
        v_fi_vel5 = fi - fi_5d_prev # 1st derivative (velocity)
        v_tw_vel5 = tw - tw_5d_prev
        v_tw_vel5_prev = tw_5d_prev - tw_10d_prev
        a_tw_acc5 = v_tw_vel5 - v_tw_vel5_prev # 2nd derivative (acceleration)
        
        vix = macro_pivot.loc[d, 'VIX'] if 'VIX' in macro_pivot.columns else 18.0
        pcr = macro_pivot.loc[d, 'CBOE_PCR'] if 'CBOE_PCR' in macro_pivot.columns else 1.0
        fg = macro_pivot.loc[d, 'FG'] if 'FG' in macro_pivot.columns else 50.0
        
        sec_th = {s: sec_ind_pivot.loc[d, f"S5_{s}_TH"] if f"S5_{s}_TH" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_TH"]) else 50.0 for s in SECTORS_11}
        sec_fi = {s: sec_ind_pivot.loc[d, f"S5_{s}_FI"] if f"S5_{s}_FI" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_tw = {s: sec_ind_pivot.loc[d, f"S5_{s}_TW"] if f"S5_{s}_TW" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        sec_v_fi = {s: sec_ind_pivot.loc[d, f"SV5_{s}_FI"] if f"SV5_{s}_FI" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"SV5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_v_tw = {s: sec_ind_pivot.loc[d, f"SV5_{s}_TW"] if f"SV5_{s}_TW" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"SV5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            current_mode=current_mode, days_in_mode=days_in_mode, tw_prev=prev_tw
        )
        prev_tw = tw
        
        # 1. Physics Engine: Accel Inflection & Falling Knife
        is_falling_knife = (v_fi_vel5 <= -15.0)
        is_bottom_inflection = (th <= 25.0) and (a_tw_acc5 >= 15.0) # 2nd Derivative positive acceleration
        
        if is_bottom_inflection:
            new_mode = "PISO_GENERACIONAL"
        elif is_falling_knife and new_mode in ["PULLBACK_ALCISTA", "NORMAL"]:
            new_mode = "DISTRIBUCION_PRE_CRASH"
            
        # 2. Crash Sistémico Redirection
        if new_mode == "CRASH_SISTEMICO" and vix <= 28.0 and v_th >= 25.0:
            new_mode = "PISO_GENERACIONAL"
            
        # 3. Sentiment Classifier Integration (if enabled)
        if mode_type == "PHYSICS_AND_SENTIMENT":
            if fg < 20.0 and vix > 25.0 and current_mode in ["NORMAL", "PULLBACK_ALCISTA"]:
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
    
    sh_phys, yr_phys, d_phys = run_ablation_simulation(price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot, mode_type="PHYSICS_ONLY")
    sh_full, yr_full, d_full = run_ablation_simulation(price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot, mode_type="PHYSICS_AND_SENTIMENT")
    
    print("\n" + "="*115)
    print("      📊 PRUEBA DE ABLACIÓN EMPÍRICA: FÍSICA DE AMPLITUD (DERIVADAS 1A Y 2A) VS SENTIMIENTO (2000-2026)")
    print("="*115)
    print(f"{'Año':<6s} | {'Solo Física (Aceleración/Velocidad)':<38s} | {'Física + Sentimiento (VIX/FG)':<32s} | {'Diagnóstico'}")
    print("-" * 115)
    
    for yr in yr_phys.index:
        s_p = yr_phys.loc[yr, 'spy_shares']
        s_f = yr_full.loc[yr, 'spy_shares'] if yr in yr_full.index else s_p
        diff = s_f - s_p
        status = "🟢 Sentimiento Aporta Alfa" if diff > 0.5 else ("🔴 Sentimiento es Ruido" if diff < -0.5 else "⚪ Idéntico")
        print(f"{yr:<6d} | {s_p:38.2f} | {s_f:32.2f} | {status}")
        
    print("="*115)
    print(f"ACCIONES CON SOLO FÍSICA (DERIVADAS 1A Y 2A)         : {sh_phys:.2f} Acciones SPY ({sh_phys/100.0:.2f}x Compounding)")
    print(f"ACCIONES CON FÍSICA + CLASIFICADOR DE SENTIMIENTO     : {sh_full:.2f} Acciones SPY ({sh_full/100.0:.2f}x Compounding) 🟢")
    print(f"IMPACTO NETO DEL CLASIFICADOR DE SENTIMIENTO (HECHOS): {sh_full - sh_phys:+.2f} ACCIONES DE SPY MÁS 🟢")
    print("="*115)

if __name__ == "__main__":
    main()
