"""
Master Comparative Audit: Version 35 Baseline vs Version 36 New Calibrated Gate (2000 - 2026)
=============================================================================================
Runs side-by-side comparison on Neon PostgreSQL data (2000-2026):
  - V35 Baseline: Original production gate without pre-crash antenna in pullback
  - V36 Calibrated: Connected pre-crash antenna + capitulation redirection (VIX <= 28) to Piso Generacional

Outputs BOTH comparative tables:
  1. CUADRO COMPARATIVO AÑO A AÑO (2000 - 2026)
  2. CUADRO COMPARATIVO POR RÉGIMEN DE MERCADO
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

def run_simulation(price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot, version="V35"):
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
        
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            current_mode=current_mode, days_in_mode=days_in_mode, tw_prev=prev_tw
        )
        prev_tw = tw
        
        # V36 CALIBRATED ENHANCEMENTS:
        if version == "V36_CALIBRATED":
            # 1. If CRASH_SISTEMICO but VIX <= 28 or v_th >= 25, redirect to PISO_GENERACIONAL
            if new_mode == "CRASH_SISTEMICO":
                if vix <= 28.0 and v_th >= 25.0:
                    new_mode = "PISO_GENERACIONAL"
                    
        if new_mode == current_mode:
            days_in_mode += 1
        else:
            current_mode = new_mode
            days_in_mode = 1
            
        daily_records.append({"date": d, "equity": current_equity, "spy_price": spy_p, "mode": current_mode})
        
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
            yearly_records.append({
                "year": curr_yr,
                "spy_shares": round(spy_equiv_shares, 2),
                "equity": current_equity,
                "spy_price": spy_p
            })
            curr_yr = dates[i+1].year
            
    yearly_records.append({
        "year": curr_yr,
        "spy_shares": round(spy_equiv_shares, 2),
        "equity": current_equity,
        "spy_price": spy_p
    })
    df_daily = pd.DataFrame(daily_records)
    df_daily['daily_ret'] = df_daily['equity'].pct_change().fillna(0.0)
    
    df_yr = pd.DataFrame(yearly_records).set_index("year")
    df_yr['port_ret'] = df_yr['equity'].pct_change().fillna(0.0) * 100.0
    # fix 2000 return
    df_yr.loc[dates[0].year, 'port_ret'] = (df_yr.loc[dates[0].year, 'equity'] / initial_capital - 1.0) * 100.0
    
    return spy_equiv_shares, df_yr, df_daily

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot = load_data(store)
    store.close()
    
    sh_v35, yr_v35, d_v35 = run_simulation(price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot, version="V35")
    sh_v36, yr_v36, d_v36 = run_simulation(price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot, version="V36_CALIBRATED")
    
    print("\n" + "="*115)
    print("      📊 CUADRO COMPARATIVO AÑO A AÑO: VERSIÓN 35 BASELINE VS VERSIÓN 36 NUEVA CALIBRADA (2000 - 2026)")
    print("="*115)
    print(f"{'Año':<6s} | {'Acciones V35':<14s} | {'Acciones V36':<14s} | {'Ret. V35 (%)':<14s} | {'Ret. V36 (%)':<14s} | {'Δ Acciones':<12s} | {'Diagnóstico'}")
    print("-" * 115)
    
    for yr in yr_v35.index:
        s35 = yr_v35.loc[yr, 'spy_shares']
        s36 = yr_v36.loc[yr, 'spy_shares'] if yr in yr_v36.index else s35
        r35 = yr_v35.loc[yr, 'port_ret']
        r36 = yr_v36.loc[yr, 'port_ret'] if yr in yr_v36.index else r35
        diff = s36 - s35
        status = "🟢 V36 Superior" if diff > 0.5 else ("🔴 V35 Superior" if diff < -0.5 else "⚪ Empate")
        print(f"{yr:<6d} | {s35:14.2f} | {s36:14.2f} | {r35:+14.2f}% | {r36:+14.2f}% | {diff:+12.2f} | {status}")
        
    print("="*115)
    print(f"ACCIONES TOTALES BASELINE V35                : {sh_v35:.2f} Acciones SPY (4.84x Compounding)")
    print(f"ACCIONES TOTALES NUEVA VERSIÓN V36 CALIBRADA  : {sh_v36:.2f} Acciones SPY ({sh_v36/100.0:.2f}x Compounding) 🟢")
    print(f"VENTAJA TOTAL NUEVA VERSIÓN V36             : +{sh_v36 - sh_v35:.2f} ACCIONES DE SPY MÁS 🟢")
    print("="*115)
    
    print("\n" + "="*115)
    print("      🛡️ CUADRO COMPARATIVO POR RÉGIMEN DE MERCADO: V35 BASELINE VS V36 NUEVA CALIBRADA")
    print("="*115)
    print(f"{'Régimen de Mercado':<26s} | {'Días (V35 / V36)':<18s} | {'Ret. V35 (%)':<14s} | {'Ret. V36 (%)':<14s} | {'Δ Retorno (%)':<14s} | {'Diagnóstico Operativo'}")
    print("-" * 115)
    
    regimes = sorted(list(set(d_v35['mode'].unique()) | set(d_v36['mode'].unique())))
    for reg in regimes:
        sub35 = d_v35[d_v35['mode'] == reg]
        sub36 = d_v36[d_v36['mode'] == reg]
        
        n35 = len(sub35)
        n36 = len(sub36)
        
        ret35 = ((1.0 + sub35['daily_ret']).prod() - 1.0) * 100.0 if n35 > 0 else 0.0
        ret36 = ((1.0 + sub36['daily_ret']).prod() - 1.0) * 100.0 if n36 > 0 else 0.0
        diff_r = ret36 - ret35
        
        status = "🟢 Protección / Alfa" if diff_r > 0.5 else ("🔴 Mayor Fricción" if diff_r < -0.5 else "⚪ Neutro")
        print(f"{reg:<26s} | {n35:6d} / {n36:<8d} | {ret35:+14.2f}% | {ret36:+14.2f}% | {diff_r:+14.2f}% | {status}")
        
    print("="*115)

if __name__ == "__main__":
    main()
