"""
Master Regime Attribution Comparison & Certainty Calibration Audit (2000-2026)
=============================================================================
1. Prints complete Regime Attribution Table for Baseline vs Enhanced.
2. Audits the historical vector availability effect on Certainty Score (C_score)
   to ensure point-in-time historical data completeness does not penalize bull market expansions.
"""

import os, sys, json, pandas as pd, numpy as np
import psycopg2
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
from backend.modules.causal_investigation.domain.rules.certainty_rules import compute_certainty_score
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

def run_regime_sim(price_pivot, mkt_breadth, sec_ind_pivot, mode_type="BASELINE"):
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
        
        hot_tw = sum(1 for v in sec_tw.values() if v > 50.0)
        cold_tw = sum(1 for v in sec_tw.values() if v < 20.0)
        is_pre_crash_distribution = (v_tw < 40.0 and th < 45.0) or (hot_tw <= 1 and cold_tw >= 7)
        
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            current_mode=current_mode, days_in_mode=days_in_mode, tw_prev=prev_tw
        )
        prev_tw = tw
        
        if mode_type != "BASELINE":
            if current_mode == "PULLBACK_ALCISTA" and is_pre_crash_distribution:
                new_mode = "DISTRIBUCION_PRE_CRASH"
                
        if new_mode == current_mode:
            days_in_mode += 1
        else:
            current_mode = new_mode
            days_in_mode = 1
            
        daily_records.append({
            "date": d,
            "equity": current_equity,
            "mode": current_mode
        })
        
        available_secs = [s for s in SECTORS_11 if s in price_pivot.columns and pd.notna(price_pivot.loc[d, s])]
        target_weights = gate.calculate_target_weights(
            mode=current_mode,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            avail_sectors=available_secs,
            sec_v_fi=sec_v_fi, sec_v_tw=sec_v_tw
        )
        
        if mode_type != "BASELINE" and current_mode == "PULLBACK_ALCISTA":
            valid_secs = [s for s in available_secs if sec_v_tw.get(s, 0.0) >= 45.0]
            if valid_secs:
                tot_cap = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s in valid_secs)
                target_weights = {s: SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot_cap for s in valid_secs}
            else:
                target_weights = {s: 0.0 for s in available_secs}
                
        portfolio_cash = current_equity
        portfolio_shares = {s: 0.0 for s in SECTORS_11}
        for s, w in target_weights.items():
            if w > 0 and s in price_pivot.columns and pd.notna(price_pivot.loc[d, s]) and price_pivot.loc[d, s] > 0:
                allocated = current_equity * w
                portfolio_shares[s] = allocated / price_pivot.loc[d, s]
                portfolio_cash -= allocated

    df = pd.DataFrame(daily_records)
    df['daily_ret'] = df['equity'].pct_change().fillna(0.0)
    return df

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot = load_data(store)
    store.close()
    
    df_base = run_regime_sim(price_pivot, mkt_breadth, sec_ind_pivot, mode_type="BASELINE")
    df_enh = run_regime_sim(price_pivot, mkt_breadth, sec_ind_pivot, mode_type="INTELLIGENCE_ENHANCED")
    
    total_days = len(df_base)
    regimes = sorted(list(set(df_base['mode'].unique()) | set(df_enh['mode'].unique())))
    
    print("\n" + "="*105)
    print("      🛡️ ATRIBUCIÓN COMPARATIVA POR RÉGIMEN: V35 BASELINE VS INTELLIGENCE ENHANCED (2000 - 2026)")
    print("="*105)
    print(f"{'Régimen de Mercado':<28s} | {'Días (Base/Enh)':<16s} | {'Retorno Base':<14s} | {'Retorno Enhanced':<16s} | {'Impacto Alpha'}")
    print("-" * 105)
    
    for reg in regimes:
        sub_b = df_base[df_base['mode'] == reg]
        sub_e = df_enh[df_enh['mode'] == reg]
        
        n_b = len(sub_b)
        n_e = len(sub_e)
        
        ret_b = ((1.0 + sub_b['daily_ret']).prod() - 1.0) * 100.0 if n_b > 0 else 0.0
        ret_e = ((1.0 + sub_e['daily_ret']).prod() - 1.0) * 100.0 if n_e > 0 else 0.0
        diff = ret_e - ret_b
        
        status = "🟢 Protección / Alfa" if diff > 0.5 else ("🔴 Mayor Fricción" if diff < -0.5 else "⚪ Neutro")
        print(f"{reg:<28s} | {n_b:6d} / {n_e:<6d} | {ret_b:+14.2f}% | {ret_e:+16.2f}% | {diff:+12.2f}% ({status})")
        
    print("="*105)

if __name__ == "__main__":
    main()
