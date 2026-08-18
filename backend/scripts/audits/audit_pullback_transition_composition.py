"""
Audit of PULLBACK_ALCISTA Transition Composition & Opportunity Capture (2000-2026)
====================================================================================
Analyzes:
  1. Did PULLBACK_ALCISTA actually capture the dip (buy low), or did it immediately hand off?
  2. For transitions to DISTRIBUCION_PRE_CRASH: Was it a "false alarm" that missed a rally, or a "true rescue" from a crash?
  3. For transitions to NORMAL / RE_ACUMULACION: Did it successfully buy the dip and ride the recovery?
  4. 10-day forward return of SPY and Portfolio after PULLBACK_ALCISTA exits.
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

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot = load_data(store)
    store.close()
    
    dates = sorted(price_pivot.index)
    spy_p0 = price_pivot["SPY"].iloc[0]
    
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    portfolio_cash = 100.0 * spy_p0
    portfolio_shares = {s: 0.0 for s in SECTORS_11}
    
    daily_history = []
    
    for i, d in enumerate(dates):
        spy_p = price_pivot.loc[d, "SPY"]
        current_equity = portfolio_cash + sum(portfolio_shares[s] * price_pivot.loc[d, s] for s in SECTORS_11 if s in price_pivot.columns and pd.notna(price_pivot.loc[d, s]))
        
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
            current_mode=current_mode, days_in_mode=days_in_mode, tw_prev=prev_tw,
            vix=vix
        )
        prev_tw = tw
        
        if new_mode == current_mode:
            days_in_mode += 1
        else:
            current_mode = new_mode
            days_in_mode = 1
            
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
                
        daily_history.append({
            "idx": i,
            "date": d,
            "equity": current_equity,
            "spy_price": spy_p,
            "mode": current_mode,
            "target_weights": target_weights
        })
        
    df_history = pd.DataFrame(daily_history)
    
    # Isolate PULLBACK_ALCISTA episodes
    episodes = []
    in_ep = False
    ep_start = 0
    for i in range(len(df_history)):
        if df_history.iloc[i]['mode'] == "PULLBACK_ALCISTA":
            if not in_ep:
                in_ep = True
                ep_start = i
        else:
            if in_ep:
                in_ep = False
                episodes.append((ep_start, i - 1))
    if in_ep:
        episodes.append((ep_start, len(df_history) - 1))
        
    print("\n" + "="*115)
    print("      🔬 AUDITORÍA DE TRANSICIONES Y CAPTURA DE OPORTUNIDAD: PULLBACK_ALCISTA")
    print("="*115)
    
    by_next_mode = {}
    
    for start_idx, end_idx in episodes:
        start_row = df_history.iloc[start_idx]
        end_row = df_history.iloc[end_idx]
        
        next_idx = min(len(df_history) - 1, end_idx + 1)
        next_mode = df_history.iloc[next_idx]['mode']
        
        # 10-day forward return after exit
        fwd_10_idx = min(len(df_history) - 1, end_idx + 10)
        fwd_10_spy_ret = ((df_history.iloc[fwd_10_idx]['spy_price'] / end_row['spy_price']) - 1.0) * 100.0
        fwd_10_eq_ret = ((df_history.iloc[fwd_10_idx]['equity'] / end_row['equity']) - 1.0) * 100.0
        
        dur = end_idx - start_idx + 1
        ep_ret = ((end_row['equity'] / start_row['equity']) - 1.0) * 100.0
        
        if next_mode not in by_next_mode:
            by_next_mode[next_mode] = []
            
        by_next_mode[next_mode].append({
            "start_date": start_row['date'],
            "end_date": end_row['date'],
            "dur": dur,
            "ep_ret": ep_ret,
            "fwd_10_spy": fwd_10_spy_ret,
            "fwd_10_eq": fwd_10_eq_ret
        })
        
    for mode, list_ep in by_next_mode.items():
        print(f"\n📌 TRANSICIÓN HACIA: {mode} ({len(list_ep)} Episodios)")
        print(f"{'Inicio':<11s} | {'Fin':<11s} | {'Días':<5s} | {'Retorno Episodio (%)':<22s} | {'Fwd 10d SPY (%)':<16s} | {'Fwd 10d Portfolio (%)'}")
        print("-" * 100)
        
        avg_ep = np.mean([e['ep_ret'] for e in list_ep])
        avg_fwd_spy = np.mean([e['fwd_10_spy'] for e in list_ep])
        avg_fwd_eq = np.mean([e['fwd_10_eq'] for e in list_ep])
        
        for e in list_ep:
            print(f"{str(e['start_date']):<11s} | {str(e['end_date']):<11s} | {e['dur']:<5d} | {e['ep_ret']:+22.2f}% | {e['fwd_10_spy']:+16.2f}% | {e['fwd_10_eq']:+20.2f}%")
        print(f"--> PROMEDIO {mode}: Retorno Episodio={avg_ep:+.2f}%, Fwd 10d SPY={avg_fwd_spy:+.2f}%, Fwd 10d Portfolio={avg_fwd_eq:+.2f}%")

if __name__ == "__main__":
    main()
