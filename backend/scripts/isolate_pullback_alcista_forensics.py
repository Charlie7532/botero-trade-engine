"""
Surgical Forensics: Isolate PULLBACK_ALCISTA Regime (2000 - 2026)
===================================================================
Audits every single day spent in PULLBACK_ALCISTA regime to identify:
  1. Exact dates, returns, and drawdowns during PULLBACK_ALCISTA.
  2. Blind spots: Was the market entering pre-crash distribution while trapped in PULLBACK_ALCISTA?
  3. Signal analysis: S5_TH, S5_FI, S5_TW, SV5_TW, VBI, and sector dynamics.
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
        
        common_dates = price_pivot.index.intersection(mkt_breadth.index).intersection(sec_ind_pivot.index)
        return price_pivot.loc[common_dates], mkt_breadth.loc[common_dates], sec_ind_pivot.loc[common_dates]
    finally:
        store._put(conn)

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot = load_data(store)
    store.close()
    
    dates = sorted(price_pivot.index)
    spy_p0 = price_pivot["SPY"].iloc[0]
    
    initial_capital = 100.0 * spy_p0
    portfolio_cash = initial_capital
    portfolio_shares = {s: 0.0 for s in SECTORS_11}
    
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    records = []
    
    for i, d in enumerate(dates):
        spy_p = price_pivot.loc[d, "SPY"]
        
        current_equity = portfolio_cash + sum(portfolio_shares[s] * price_pivot.loc[d, s] for s in SECTORS_11 if s in price_pivot.columns and pd.notna(price_pivot.loc[d, s]))
        
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
        
        # Check pre-crash distribution condition manually
        hot_tw = sum(1 for v in sec_tw.values() if v > 50.0)
        cold_tw = sum(1 for v in sec_tw.values() if v < 20.0)
        is_notam_pre_crash = (v_tw < 40.0 and th < 45.0) or (hot_tw <= 1 and cold_tw >= 7)
        
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
            
        records.append({
            "date": d,
            "mode": current_mode,
            "days_in_mode": days_in_mode,
            "equity": current_equity,
            "spy_price": spy_p,
            "th": th, "fi": fi, "tw": tw, "v_tw": v_tw,
            "is_notam_pre_crash": is_notam_pre_crash
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

    df = pd.DataFrame(records)
    df['ret'] = df['equity'].pct_change()
    df['spy_ret'] = df['spy_price'].pct_change()
    
    df_pb = df[df['mode'] == "PULLBACK_ALCISTA"].copy()
    
    print("\n" + "="*95)
    print("      🔍 AUTOPSIA FORENSE: PULLBACK_ALCISTA (2000 - 2026)")
    print("="*95)
    print(f"Total de Días en PULLBACK_ALCISTA                     : {len(df_pb)} días")
    print(f"Retorno Acumulado Total en PULLBACK_ALCISTA            : {((1.0 + df_pb['ret'].fillna(0.0)).prod() - 1.0)*100:.2f}%")
    print(f"Retorno Promedio Diario en PULLBACK_ALCISTA           : {df_pb['ret'].mean()*100:+.3f}%")
    print(f"Win Rate Diaria en PULLBACK_ALCISTA                    : {(df_pb['ret'] > 0).mean()*100:.1f}%")
    
    # Días atrapados en Pre-Crash Distribution mientras estaba en PULLBACK_ALCISTA
    trapped_pre_crash = df_pb['is_notam_pre_crash'].sum()
    pct_trapped = (trapped_pre_crash / len(df_pb)) * 100.0 if len(df_pb) > 0 else 0.0
    print(f"\n🔴 DÍAS ATRAPADOS EN PRE-CRASH DISTRIBUCIÓN SINTÉTICA  : {trapped_pre_crash} días ({pct_trapped:.1f}% del tiempo)")
    print("   ↳ Causa del Punto Ciego: El régimen PULLBACK_ALCISTA no escuchaba la antena is_pre_crash_distribution.")
    print("     Continuaba comprado al 100% mientras el mercado acumulaba distribución institucional pre-crash!")
    
    # Identify distinct episodes of PULLBACK_ALCISTA
    df_pb['episode'] = (df_pb['days_in_mode'] == 1).cumsum()
    episodes = df_pb.groupby('episode')
    
    print("\n" + "="*95)
    print("      📅 EPISODIOS HISTÓRICOS DE PULLBACK_ALCISTA Y PÉRDIDAS CLAVE")
    print("="*95)
    print(f"{'Episodio':<10s} | {'Fecha Inicio':<12s} | {'Fecha Fin':<12s} | {'Días':<6s} | {'Retorno V35':<14s} | {'Retorno SPY':<14s} | {'Pre-Crash Atrapado'}")
    print("-" * 95)
    
    for ep_id, group in episodes:
        start_dt = group['date'].iloc[0].strftime('%Y-%m-%d')
        end_dt = group['date'].iloc[-1].strftime('%Y-%m-%d')
        n_days = len(group)
        ret_v35 = ((1.0 + group['ret'].fillna(0.0)).prod() - 1.0) * 100.0
        ret_spy = ((group['spy_price'].iloc[-1] / group['spy_price'].iloc[0]) - 1.0) * 100.0
        n_pre = group['is_notam_pre_crash'].sum()
        status = "🔴 ATRASE Y PÉRDIDA" if ret_v35 < -2.0 else "🟢 POSITIVO"
        print(f"Episodio {ep_id:<2d} | {start_dt:<12s} | {end_dt:<12s} | {n_days:<6d} | {ret_v35:+14.2f}% | {ret_spy:+14.2f}% | {n_pre} días ({status})")
        
    print("="*95)

if __name__ == "__main__":
    main()
