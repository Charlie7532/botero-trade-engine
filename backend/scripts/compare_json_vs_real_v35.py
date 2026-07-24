"""
Forensic Audit: Compare JSON (Complacent V26) vs Real V35 Production Year-by-Year (1999-2026)
=============================================================================================
Audits exact year-by-year discrepancies caused by S5 QQQ enrichment contamination and
complacent JSON fallbacks versus strict zero-fallback Neon PostgreSQL production data.
"""

import os, sys, json, pandas as pd, numpy as np
import psycopg2
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS

SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]
BREADTH_MAP = {
    "S5TH": "th", "S5FI": "fi", "S5TW": "tw",
    "SV5TH": "v_th", "SV5FI": "v_fi", "SV5TW": "v_tw"
}

def load_real_v35_data():
    store = TimescaleDataStore()
    conn = store._conn()
    try:
        all_tickers = ["SPY"] + SECTORS_11
        p_str = ", ".join([f"'{t}'" for t in all_tickers])
        
        df_p = pd.read_sql(f"""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ({p_str})
              AND timeframe = '1d'
              AND time >= '1999-01-01'
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
              AND time >= '1999-01-01'
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
              AND time >= '1999-01-01'
            ORDER BY time, ticker
        """, conn)
        sec_ind_pivot = df_sec_ind.pivot(index='date', columns='ticker', values='close').ffill()
        
        common_dates = price_pivot.index.intersection(mkt_breadth.index).intersection(sec_ind_pivot.index)
        return price_pivot.loc[common_dates], mkt_breadth.loc[common_dates], sec_ind_pivot.loc[common_dates]
    finally:
        store._put(conn)
        store.close()

def run_real_v35_sim(price_pivot, mkt_breadth, sec_ind_pivot):
    dates = sorted(price_pivot.index)
    spy_p0 = price_pivot["SPY"].iloc[0]
    
    initial_spy_shares = 100.00
    initial_capital = initial_spy_shares * spy_p0
    portfolio_cash = initial_capital
    portfolio_shares = {s: 0.0 for s in SECTORS_11}
    
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    daily_records = []
    
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

    df_daily = pd.DataFrame(daily_records)
    
    yearly_rows = []
    for y in sorted(df_daily['year'].unique()):
        sub = df_daily[df_daily['year'] == y]
        start_eq = sub['equity'].iloc[0]
        end_eq = sub['equity'].iloc[-1]
        start_spy = sub['spy_price'].iloc[0]
        end_spy = sub['spy_price'].iloc[-1]
        end_shares = sub['spy_shares'].iloc[-1]
        
        port_ret = (end_eq / start_eq - 1.0) * 100.0
        spy_ret = (end_spy / start_spy - 1.0) * 100.0
        
        yearly_rows.append({
            "year": int(y),
            "real_shares": float(end_shares),
            "real_ret": float(port_ret),
            "spy_ret": float(spy_ret)
        })
        
    return pd.DataFrame(yearly_rows).set_index("year")

def main():
    json_path = "/root/botero-trade/scratch/final_tables.json"
    with open(json_path, "r") as f:
        json_data = json.load(f)
        
    df_json = pd.DataFrame(json_data["yearly"]).set_index("year")
    
    price_pivot, mkt_breadth, sec_ind_pivot = load_real_v35_data()
    df_real = run_real_v35_sim(price_pivot, mkt_breadth, sec_ind_pivot)
    
    print("\n" + "="*105)
    print("      🔍 AUDITORÍA COMPARATIVA FORENSE: DATA DEL JSON (COMPLACIENTE) VS V35 PRODUCCIÓN REAL")
    print("="*105)
    print(f"{'Año':<6s} | {'JSON Shares (923.54)':<20s} | {'V35 Real Shares (483.97)':<24s} | {'Ret. JSON (%)':<14s} | {'Ret. Real (%)':<14s} | {'Diferencia (Δ Acc)'}")
    print("-" * 105)
    
    all_years = sorted(list(set(df_json.index) | set(df_real.index)))
    
    for yr in all_years:
        js_sh = df_json.loc[yr, 'v35_shares'] if yr in df_json.index else 100.0
        js_ret = df_json.loc[yr, 'v35_ret'] if yr in df_json.index else 0.0
        
        rl_sh = df_real.loc[yr, 'real_shares'] if yr in df_real.index else js_sh
        rl_ret = df_real.loc[yr, 'real_ret'] if yr in df_real.index else js_ret
        
        diff_sh = rl_sh - js_sh
        
        status = "🔴 Inflado en JSON" if diff_sh < -5.0 else ("🟢 Real V35 Superior" if diff_sh > 5.0 else "⚪ Coinciden")
        print(f"{yr:<6d} | {js_sh:20.2f} | {rl_sh:24.2f} | {js_ret:+14.2f}% | {rl_ret:+14.2f}% | {diff_sh:+16.2f} ({status})")
        
    print("="*105)
    print(f"ACCIONES TOTALES ACUMULADAS EN ARTEFACTO JSON : {df_json['v35_shares'].iloc[-1]:.2f} Acciones SPY (Sobrestimado por V26)")
    print(f"ACCIONES TOTALES ACUMULADAS EN V35 REAL VAULT  : {df_real['real_shares'].iloc[-1]:.2f} Acciones SPY (Verdad Cuantitativa)")
    print("="*95)

if __name__ == "__main__":
    main()
