"""
Optimization & Backtest of V37 PULLBACK_ALCISTA using Spectrum Signatures (2000-2026)
====================================================================================
Measures V35/V36 baseline vs V37 Enhanced PULLBACK_ALCISTA incorporating:
  1. Deceleration Inertia Filter (Eliminates 1-day falling knives).
  2. Day-0 Volume Divergence Trigger (Captures bottoms before t+1 gap).
  3. Multi-Sector Breadth Filter (Eliminates mega-cap distortion bias).
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

def simulate_regime_performance(df, use_v37_rules=False):
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    spy_p0 = df["SPY"].iloc[0]
    portfolio_cash = 100.0 * spy_p0
    portfolio_shares = {s: 0.0 for s in SECTORS_11}
    
    records = []
    
    for i, d in enumerate(df.index):
        spy_p = df.loc[d, "SPY"]
        current_equity = portfolio_cash + sum(portfolio_shares[s] * df.loc[d, s] for s in SECTORS_11 if s in df.columns and pd.notna(df.loc[d, s]))
        
        th = df.loc[d, "S5TH"]
        fi = df.loc[d, "S5FI"]
        tw = df.loc[d, "S5TW"]
        v_th = df.loc[d, "SV5TH"]
        v_fi = df.loc[d, "SV5FI"]
        v_tw = df.loc[d, "SV5TW"]
        
        sec_th = {s: df.loc[d, f"S5_{s}_TH"] if f"S5_{s}_TH" in df.columns and pd.notna(df.loc[d, f"S5_{s}_TH"]) else 50.0 for s in SECTORS_11}
        sec_fi = {s: df.loc[d, f"S5_{s}_FI"] if f"S5_{s}_FI" in df.columns and pd.notna(df.loc[d, f"S5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_tw = {s: df.loc[d, f"S5_{s}_TW"] if f"S5_{s}_TW" in df.columns and pd.notna(df.loc[d, f"S5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        sec_v_fi = {s: df.loc[d, f"SV5_{s}_FI"] if f"SV5_{s}_FI" in df.columns and pd.notna(df.loc[d, f"SV5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_v_tw = {s: df.loc[d, f"SV5_{s}_TW"] if f"SV5_{s}_TW" in df.columns and pd.notna(df.loc[d, f"SV5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        
        # Base V36 mode evaluation
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            current_mode=current_mode, days_in_mode=days_in_mode, tw_prev=prev_tw
        )
        
        # V37 Enhancements for PULLBACK_ALCISTA
        if use_v37_rules:
            # 1. Inertia Filter: If entering PULLBACK_ALCISTA, ensure 2-day TW velocity is not in freefall (<-15.0%)
            tw_vel_2d = tw - df.iloc[max(0, i-2)]['S5TW']
            vol_div = v_tw - tw
            num_strong_sectors = sum(1 for s in SECTORS_11 if sec_v_tw.get(s, 0) >= 45.0)
            
            if new_mode == "PULLBACK_ALCISTA":
                # Block if TW velocity is in freefall without volume absorption, or less than 3 sectors support volume
                if tw_vel_2d < -15.0 and vol_div < 20.0:
                    new_mode = current_mode # Remain in current mode (prevent 1-day noise)
                elif num_strong_sectors < 3:
                    new_mode = current_mode # Block mega-cap volume distortion
                    
        prev_tw = tw
        
        if new_mode == current_mode:
            days_in_mode += 1
        else:
            current_mode = new_mode
            days_in_mode = 1
            
        available_secs = [s for s in SECTORS_11 if s in df.columns and pd.notna(df.loc[d, s])]
        target_weights = gate.calculate_target_weights(
            mode=current_mode,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            avail_sectors=available_secs,
            sec_v_fi=sec_v_fi, sec_v_tw=sec_v_tw
        )
        
        portfolio_cash = current_equity
        portfolio_shares = {s: 0.0 for s in SECTORS_11}
        for s, w in target_weights.items():
            if w > 0 and s in df.columns and pd.notna(df.loc[d, s]) and df.loc[d, s] > 0:
                allocated = current_equity * w
                portfolio_shares[s] = allocated / df.loc[d, s]
                portfolio_cash -= allocated
                
        records.append({
            "date": d,
            "equity": current_equity,
            "mode": current_mode
        })
        
    return pd.DataFrame(records)

def main():
    store = TimescaleDataStore()
    df = load_data(store)
    store.close()
    
    print("\n" + "="*115)
    print("      🔬 OPTIMIZACIÓN Y AUDITORÍA V36 VS V37 EN PULLBACK_ALCISTA (2000 - 2026)")
    print("="*115)
    
    df_v36 = simulate_regime_performance(df, use_v37_rules=False)
    df_v37 = simulate_regime_performance(df, use_v37_rules=True)
    
    # Isolate PULLBACK_ALCISTA episodes for V36 vs V37
    def analyze_pullback_episodes(df_hist):
        episodes = []
        in_ep = False
        start = 0
        for i in range(len(df_hist)):
            if df_hist.iloc[i]['mode'] == "PULLBACK_ALCISTA":
                if not in_ep:
                    in_ep = True
                    start = i
            else:
                if in_ep:
                    in_ep = False
                    episodes.append((start, i-1))
        if in_ep:
            episodes.append((start, len(df_hist)-1))
            
        returns = []
        durations = []
        for s, e in episodes:
            dur = e - s + 1
            ret = ((df_hist.iloc[e]['equity'] / df_hist.iloc[s]['equity']) - 1.0) * 100.0
            returns.append(ret)
            durations.append(dur)
        return len(episodes), np.mean(returns) if returns else 0.0, np.mean(durations) if durations else 0.0, (np.array(returns) > 0).mean() * 100.0 if returns else 0.0, sum(returns)

    eps_v36, ret_v36, dur_v36, wr_v36, sum_v36 = analyze_pullback_episodes(df_v36)
    eps_v37, ret_v37, dur_v37, wr_v37, sum_v37 = analyze_pullback_episodes(df_v37)
    
    print(f"\n📊 COMPARATIVA DE DESEMPEÑO EN PULLBACK_ALCISTA:")
    print(f"{'Métrica':<35s} | {'V36 Baseline':<20s} | {'V37 Optimizado':<20s} | {'Mejora Net'}")
    print("-" * 90)
    print(f"{'Total Episodios Evaluados':<35s} | {eps_v36:<20d} | {eps_v37:<20d} | {eps_v37 - eps_v36:d} episodios")
    print(f"{'Duración Promedio (Días)':<35s} | {dur_v36:<20.1f} | {dur_v37:<20.1f} | {dur_v37 - dur_v36:+.1f} días")
    print(f"{'Win Rate Episódico (% W)':<35s} | {wr_v36:<20.1f}% | {wr_v37:<20.1f}% | {wr_v37 - wr_v36:+.1f}%")
    print(f"{'Retorno Promedio por Episodio (%)':<35s} | {ret_v36:<20.2f}% | {ret_v37:<20.2f}% | {ret_v37 - ret_v36:+.2f}%")
    print(f"{'Retorno Sumado de Episodios (%)':<35s} | {sum_v36:<20.2f}% | {sum_v37:<20.2f}% | {sum_v37 - sum_v36:+.2f}%")

if __name__ == "__main__":
    main()
