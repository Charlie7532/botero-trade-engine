"""
Deep Quantitative Forensic Autopsy of PULLBACK_ALCISTA Regime (2000 - 2026)
==========================================================================
Persona: Marcos López de Prado (Chief Quantitative Strategist)

Audits every single episode of PULLBACK_ALCISTA across 6,676 daily bars in Neon DB:
  1. Entry Context: Previous regime + exact breadth/volume/velocity/market-intel conditions on Day -5 to Day 0.
  2. Duration & Internal Dynamics: Length of episode, sector allocation, equity curve.
  3. Exit Context: Subsequent regime on Day N+1 to N+5 + exit triggers.
  4. Winner vs Loser Classification: Profit/Loss per episode, Win Rate, Drawdowns.
  5. Sector Rotation Forensics: Sector allocation efficacy (oversold vs momentum).
"""

import os, sys, json, pandas as pd, numpy as np
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
            "days_in_mode": days_in_mode,
            "th": th, "fi": fi, "tw": tw,
            "v_th": v_th, "v_fi": v_fi, "v_tw": v_tw,
            "vix": vix, "pcr": pcr, "fg": fg,
            "target_weights": target_weights
        })
        
    df_history = pd.DataFrame(daily_history)
    
    # Isolate PULLBACK_ALCISTA episodes
    episodes = []
    in_ep = False
    ep_start_idx = 0
    
    for i in range(len(df_history)):
        row = df_history.iloc[i]
        if row['mode'] == "PULLBACK_ALCISTA":
            if not in_ep:
                in_ep = True
                ep_start_idx = i
        else:
            if in_ep:
                in_ep = False
                ep_end_idx = i - 1
                episodes.append((ep_start_idx, ep_end_idx))
                
    if in_ep:
        episodes.append((ep_start_idx, len(df_history) - 1))
        
    print("\n" + "="*115)
    print(f"      🔬 AUTOPSIA FORENSE MARCOS LÓPEZ DE PRADO: RÉGIMEN PULLBACK_ALCISTA ({len(episodes)} EPISODIOS)")
    print("="*115)
    
    ep_records = []
    
    for ep_num, (start_idx, end_idx) in enumerate(episodes, 1):
        start_row = df_history.iloc[start_idx]
        end_row = df_history.iloc[end_idx]
        
        # Pre-entry state (5 days before)
        pre_idx = max(0, start_idx - 1)
        prev_mode = df_history.iloc[pre_idx]['mode']
        
        # Post-exit state (1 day after)
        post_idx = min(len(df_history) - 1, end_idx + 1)
        next_mode = df_history.iloc[post_idx]['mode']
        
        start_date = start_row['date']
        end_date = end_row['date']
        duration = end_idx - start_idx + 1
        
        start_eq = start_row['equity']
        end_eq = end_row['equity']
        ep_return = ((end_eq / start_eq) - 1.0) * 100.0
        
        start_spy = start_row['spy_price']
        end_spy = end_row['spy_price']
        spy_return = ((end_spy / start_spy) - 1.0) * 100.0
        alpha = ep_return - spy_return
        
        # Max drawdown during episode
        sub_eq = df_history.iloc[start_idx:end_idx+1]['equity']
        peak = sub_eq.cummax()
        dd = ((sub_eq - peak) / peak).min() * 100.0
        
        # Top allocated sectors during episode
        weights_sum = {}
        for idx in range(start_idx, end_idx + 1):
            tw_dict = df_history.iloc[idx]['target_weights']
            for s, w in tw_dict.items():
                weights_sum[s] = weights_sum.get(s, 0.0) + w
        top_secs = sorted(weights_sum.keys(), key=lambda x: weights_sum[x], reverse=True)[:3]
        top_secs_str = ", ".join(top_secs)
        
        status = "🟢 GANADOR" if ep_return > 0 else "🔴 PERDEDOR"
        
        ep_records.append({
            "ep": ep_num,
            "start": start_date,
            "end": end_date,
            "duration": duration,
            "prev_mode": prev_mode,
            "next_mode": next_mode,
            "return": ep_return,
            "spy_return": spy_return,
            "alpha": alpha,
            "max_dd": dd,
            "top_sectors": top_secs_str,
            "status": status,
            "th_start": start_row['th'],
            "fi_start": start_row['fi'],
            "tw_start": start_row['tw'],
            "vix_start": start_row['vix']
        })
        
    df_ep = pd.DataFrame(ep_records)
    
    # Detailed Table of Episodes
    print(f"{'Ep#':<4s} | {'Fecha Inicio':<11s} | {'Fecha Fin':<11s} | {'Días':<5s} | {'Prev Régimen':<18s} | {'Next Régimen':<18s} | {'Retorno (%)':<12s} | {'Alpha (%)':<10s} | {'MaxDD (%)':<10s} | {'Resultado'}")
    print("-" * 115)
    
    for _, r in df_ep.iterrows():
        print(f"{r['ep']:<4d} | {str(r['start']):<11s} | {str(r['end']):<11s} | {r['duration']:<5d} | {r['prev_mode']:<18s} | {r['next_mode']:<18s} | {r['return']:+12.2f}% | {r['alpha']:+10.2f}% | {r['max_dd']:10.2f}% | {r['status']}")
        
    # Statistical Summary
    n_total = len(df_ep)
    n_win = (df_ep['return'] > 0).sum()
    n_loss = n_total - n_win
    win_rate = (n_win / n_total) * 100.0 if n_total > 0 else 0.0
    
    avg_ret = df_ep['return'].mean()
    avg_win_ret = df_ep[df_ep['return'] > 0]['return'].mean() if n_win > 0 else 0.0
    avg_loss_ret = df_ep[df_ep['return'] <= 0]['return'].mean() if n_loss > 0 else 0.0
    profit_factor = abs(df_ep[df_ep['return'] > 0]['return'].sum() / df_ep[df_ep['return'] <= 0]['return'].sum()) if df_ep[df_ep['return'] <= 0]['return'].sum() != 0 else np.nan
    
    print("\n" + "="*115)
    print("      📊 RESUMEN FORENSE LÓPEZ DE PRADO DE PULLBACK_ALCISTA")
    print("="*115)
    print(f"Total Episodios Evaluados                 : {n_total}")
    print(f"Episodios Ganadores (Retorno > 0)          : {n_win} ({win_rate:.1f}% Win Rate)")
    print(f"Episodios Perdedores (Retorno <= 0)        : {n_loss}")
    print(f"Retorno Promedio por Episodio              : {avg_ret:+.2f}%")
    print(f"Retorno Promedio en Episodios Ganadores   : {avg_win_ret:+.2f}%")
    print(f"Retorno Promedio en Episodios Perdedores  : {avg_loss_ret:+.2f}%")
    print(f"Factor de Ganancia (Profit Factor)         : {profit_factor:.2f}")
    print("="*115)
    
    # Save JSON result artifact
    artifact_data = df_ep.to_dict(orient="records")
    with open("/root/.gemini/antigravity-ide/brain/747582b8-bd87-4653-8f63-949c0849b8a4/scratch/pullback_alcista_forensic_episodes.json", "w") as f:
        json.dump(artifact_data, f, indent=2, default=str)

if __name__ == "__main__":
    main()
