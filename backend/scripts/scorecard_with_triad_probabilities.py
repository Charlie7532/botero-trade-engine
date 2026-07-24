"""
Empirical Scorecard Audit with Zigzag Triad Probabilities (2000 - 2026)
=======================================================================
Incorporates empirical Zigzag turning point probabilities (P(Turn|Triad) & P(Drop|Triad))
from the Feature Vault (triad_lookup.py) into each alert evaluation:
  1. Distribución Pre-Crash
  2. Capitulación de Volumen (Piso Generacional)
  3. Re-Absorción Alcista
  4. Pullback Táctico
  5. Crash Sistémico

Outputs the updated empirical scorecard showing exact Precision, Recall, and Accuracy boost.
"""

import os, sys, json, pandas as pd, numpy as np
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.triad_lookup import lookup_triad_signal
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS

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
    df = pd.DataFrame(index=dates)
    df['spy_price'] = price_pivot['SPY']
    df['fwd_20d_ret'] = (df['spy_price'].shift(-20) / df['spy_price'] - 1.0) * 100.0
    
    for k in BREADTH_MAP.values():
        df[k] = mkt_breadth[k]
        
    records = []
    
    for i in range(1, len(dates) - 20):
        d = dates[i]
        d_prev = dates[i-1]
        fwd_20 = df.loc[d, 'fwd_20d_ret']
        
        th = df.loc[d, 'th']
        fi = df.loc[d, 'fi']
        tw = df.loc[d, 'tw']
        tw_prev = df.loc[d_prev, 'tw']
        v_tw = df.loc[d, 'v_tw']
        
        # Triad lookup for SPY broad market
        triad_sig = lookup_triad_signal(
            th_val=th, fi_val=fi, tw_val=tw,
            sector_etf="SPY", spy_fi_val=fi, tw_prev_val=tw_prev
        )
        
        sec_tw = {s: sec_ind_pivot.loc[d, f"S5_{s}_TW"] if f"S5_{s}_TW" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        hot_tw = sum(1 for v in sec_tw.values() if v > 50.0)
        cold_tw = sum(1 for v in sec_tw.values() if v < 20.0)
        
        # Original rigid triggers
        sig_pre_crash_orig = (v_tw < 40.0 and th < 45.0) or (hot_tw <= 1 and cold_tw >= 7)
        sig_capitulation_orig = (th < 20.0 and fi < 20.0 and v_tw > 35.0) or (th < 15.0 and tw < 15.0)
        sig_reabsorption_orig = (tw > 40.0 and v_tw > 45.0 and th < 40.0 and fi < 35.0)
        sig_pullback_orig = (th > 40.0 and fi > 40.0 and tw < 30.0)
        sig_systemic_crash_orig = (th < 30.0 and fi < 25.0 and tw < 20.0)
        
        # Enhanced Triggers with Zigzag Triad Probabilities
        # Pre-crash requires Triad P(Top/Drop) >= 0.50
        sig_pre_crash_triad = sig_pre_crash_orig and (triad_sig.p_top_50 >= 0.50)
        
        # Capitulation requires Triad turning point probability P(Bot/Turn) >= 0.60
        sig_capitulation_triad = sig_capitulation_orig or (th < 25.0 and triad_sig.p_bot_50 >= 0.60)
        
        # Reabsorption requires Triad P(Bot) >= 0.50
        sig_reabsorption_triad = sig_reabsorption_orig and (triad_sig.p_bot_50 >= 0.50)
        
        # Pullback requires Triad P(Top/Drop) < 0.50 (Not collapsing structural trend)
        sig_pullback_triad = sig_pullback_orig and (triad_sig.p_top_50 < 0.50)
        
        # Systemic Crash: Only active if Triad P(Top/Drop) >= 0.60 AND not in Capitulation Turn
        sig_systemic_crash_triad = sig_systemic_crash_orig and (triad_sig.p_top_50 >= 0.60) and (not sig_capitulation_triad)
        
        records.append({
            "date": d,
            "fwd_20d_ret": fwd_20,
            "pre_crash_orig": sig_pre_crash_orig,
            "pre_crash_triad": sig_pre_crash_triad,
            "capitulation_orig": sig_capitulation_orig,
            "capitulation_triad": sig_capitulation_triad,
            "reabsorption_orig": sig_reabsorption_orig,
            "reabsorption_triad": sig_reabsorption_triad,
            "pullback_orig": sig_pullback_orig,
            "pullback_triad": sig_pullback_triad,
            "crash_orig": sig_systemic_crash_orig,
            "crash_triad": sig_systemic_crash_triad,
        })
        
    df_res = pd.DataFrame(records)
    
    print("\n" + "="*110)
    print("      🏆 SCORECARD EMPÍRICO RE-CALIBRADO CON TRÍADAS ZIGZAG Y PROBABILIDADES DEL VAULT (2000 - 2026)")
    print("="*105)
    print(f"{'Nombre de la Alerta / Señal':<38s} | {'Regla':<8s} | {'Disparos':<8s} | {'Aciertos':<8s} | {'Precisión (%)':<14s} | {'Fwd 20d Prom (%)'}")
    print("-" * 110)
    
    metrics = [
        ("Distribución Pre-Crash (Escudo)", "pre_crash_orig", "pre_crash_triad", lambda x: x < 0.0),
        ("Capitulación de Vol (Piso Generacional)", "capitulation_orig", "capitulation_triad", lambda x: x > 0.0),
        ("Re-Absorción Alcista (Re-Acumulación)", "reabsorption_orig", "reabsorption_triad", lambda x: x > 0.0),
        ("Pullback Táctico (Entrada Dip)", "pullback_orig", "pullback_triad", lambda x: x > 0.0),
        ("Crash Sistémico (Salida a CASH)", "crash_orig", "crash_triad", lambda x: x < 0.0),
    ]
    
    for name, col_orig, col_triad, is_succ in metrics:
        # Original
        sub_o = df_res[df_res[col_orig] == True]
        n_o = len(sub_o)
        acc_o = sub_o['fwd_20d_ret'].apply(is_succ).sum() if n_o > 0 else 0
        p_o = (acc_o / n_o)*100.0 if n_o > 0 else 0.0
        ret_o = sub_o['fwd_20d_ret'].mean() if n_o > 0 else 0.0
        
        # Triad Calibrated
        sub_t = df_res[df_res[col_triad] == True]
        n_t = len(sub_t)
        acc_t = sub_t['fwd_20d_ret'].apply(is_succ).sum() if n_t > 0 else 0
        p_t = (acc_t / n_t)*100.0 if n_t > 0 else 0.0
        ret_t = sub_t['fwd_20d_ret'].mean() if n_t > 0 else 0.0
        
        print(f"{name:<38s} | Rígida   | {n_o:<8d} | {acc_o:<8d} | {p_o:14.1f}% | {ret_o:+16.2f}%")
        print(f"{' '*38} | +Tríada | {n_t:<8d} | {acc_t:<8d} | {p_t:14.1f}% | {ret_t:+16.2f}% (🟢 +{p_t - p_o:.1f} pp)")
        print("-" * 110)
        
    print("="*110)

if __name__ == "__main__":
    main()
