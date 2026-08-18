"""
Pullback Transition & Handoff Attribution Audit (2000-2026)
============================================================
Proves that PULLBACK_ALCISTA acts as an entry antenna whose capital gains
are realized upon handoff to MERCADO_SANO.
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
        
        df = pd.read_sql(f"""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ({p_str})
              AND timeframe = '1d'
              AND time >= '2000-01-01'
            ORDER BY time, ticker
        """, conn)
        pivot = df.pivot(index='date', columns='ticker', values='close').ffill()
        return pivot
    finally:
        store._put(conn)

def main():
    store = TimescaleDataStore()
    pivot = load_data(store)
    store.close()
    
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    daily_records = []
    
    for i, d in enumerate(pivot.index):
        th = pivot.loc[d, "S5TH"]
        fi = pivot.loc[d, "S5FI"]
        tw = pivot.loc[d, "S5TW"]
        v_th = pivot.loc[d, "SV5TH"]
        v_fi = pivot.loc[d, "SV5FI"]
        v_tw = pivot.loc[d, "SV5TW"]
        
        sec_th = {s: pivot.loc[d, f"S5_{s}_TH"] if f"S5_{s}_TH" in pivot.columns and pd.notna(pivot.loc[d, f"S5_{s}_TH"]) else 50.0 for s in SECTORS_11}
        sec_fi = {s: pivot.loc[d, f"S5_{s}_FI"] if f"S5_{s}_FI" in pivot.columns and pd.notna(pivot.loc[d, f"S5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_tw = {s: pivot.loc[d, f"S5_{s}_TW"] if f"S5_{s}_TW" in pivot.columns and pd.notna(pivot.loc[d, f"S5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        sec_v_fi = {s: pivot.loc[d, f"SV5_{s}_FI"] if f"SV5_{s}_FI" in pivot.columns and pd.notna(pivot.loc[d, f"SV5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_v_tw = {s: pivot.loc[d, f"SV5_{s}_TW"] if f"SV5_{s}_TW" in pivot.columns and pd.notna(pivot.loc[d, f"SV5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw, sec_v_tw=sec_v_tw,
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
            "mode": current_mode,
            "spy_price": pivot.loc[d, "SPY"]
        })
        
    df_res = pd.DataFrame(daily_records)
    
    # Identify episode handoffs
    pullback_episodes = []
    in_pb = False
    entry_idx = 0
    
    for i in range(len(df_res)):
        if df_res['mode'].iloc[i] == 'PULLBACK_ALCISTA' and not in_pb:
            in_pb = True
            entry_idx = i
        elif df_res['mode'].iloc[i] != 'PULLBACK_ALCISTA' and in_pb:
            in_pb = False
            exit_idx = i - 1
            handoff_mode = df_res['mode'].iloc[i]
            
            p_entry = df_res['spy_price'].iloc[entry_idx]
            p_exit = df_res['spy_price'].iloc[exit_idx]
            
            # Forward 20d return from entry
            fwd_20d_idx = min(len(df_res)-1, entry_idx + 20)
            p_20d = df_res['spy_price'].iloc[fwd_20d_idx]
            fwd_ret = ((p_20d / p_entry) - 1.0) * 100.0
            
            pullback_episodes.append({
                "entry_date": df_res['date'].iloc[entry_idx],
                "duration_days": exit_idx - entry_idx + 1,
                "handoff_mode": handoff_mode,
                "fwd_20d_return": fwd_ret
            })
            
    df_ep = pd.DataFrame(pullback_episodes)
    
    print("\n" + "="*115)
    print("      🔬 AUDITORÍA DE TRANSFERENCIAS Y HANDOFFS DE PULLBACK_ALCISTA (2000 - 2026)")
    print("="*115)
    print(f"📌 Total de Episodios Gatillados por PULLBACK_ALCISTA : {len(df_ep)} Episodios")
    
    handoff_counts = df_ep['handoff_mode'].value_counts()
    print("\n📊 Destino de Transferencia tras el Dip:")
    for mode, count in handoff_counts.items():
        pct = (count / len(df_ep)) * 100.0
        avg_fwd = df_ep[df_ep['handoff_mode'] == mode]['fwd_20d_return'].mean()
        print(f"  • {mode:<26s} : {count:2d} episodios ({pct:5.1f}%) | Retorno Fwd 20d Promedio: {avg_fwd:+6.2f}%")

    wins = len(df_ep[df_ep['fwd_20d_return'] > 0])
    win_rate = (wins / len(df_ep)) * 100.0
    print("\n" + "="*115)
    print(f"  TASA DE ÉXITO DE LAS ENTRADAS PULLBACK_ALCISTA (Fwd 20d) : {win_rate:.1f}% Win Rate ({wins}/{len(df_ep)} epis.)")
    print(f"  RETORNO MEDIO POST-ENTRADA A 20 DÍAS                     : {df_ep['fwd_20d_return'].mean():+.2f}%")
    print("="*115)

if __name__ == "__main__":
    main()
