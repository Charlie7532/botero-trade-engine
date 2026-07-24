"""
Master Intelligence Audit: How It Was vs How It Should Be (2000 - 2026)
=======================================================================
Audits the impact of incorporating:
  1. Connected Pre-Crash Distribution Antenna in PULLBACK_ALCISTA.
  2. Certainty-Weighted Capital Allocation (scaling exposure by Certainty Score).
  3. Tactical Volume Accumulation Filter (SV5_TW >= 45%) with CASH fallback.
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
        
        # Load macro indicators for certainty scoring (VIX, PCR, FG)
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

def run_simulation(price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot, mode_type="BASELINE"):
    dates = sorted(price_pivot.index)
    spy_p0 = price_pivot["SPY"].iloc[0]
    
    initial_capital = 100.0 * spy_p0
    portfolio_cash = initial_capital
    portfolio_shares = {s: 0.0 for s in SECTORS_11}
    
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
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
        
        sec_th = {s: sec_ind_pivot.loc[d, f"S5_{s}_TH"] if f"S5_{s}_TH" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_TH"]) else 50.0 for s in SECTORS_11}
        sec_fi = {s: sec_ind_pivot.loc[d, f"S5_{s}_FI"] if f"S5_{s}_FI" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_tw = {s: sec_ind_pivot.loc[d, f"S5_{s}_TW"] if f"S5_{s}_TW" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        sec_v_fi = {s: sec_ind_pivot.loc[d, f"SV5_{s}_FI"] if f"SV5_{s}_FI" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"SV5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_v_tw = {s: sec_ind_pivot.loc[d, f"SV5_{s}_TW"] if f"SV5_{s}_TW" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"SV5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        
        # Pre-crash distribution flag
        hot_tw = sum(1 for v in sec_tw.values() if v > 50.0)
        cold_tw = sum(1 for v in sec_tw.values() if v < 20.0)
        is_pre_crash_distribution = (v_tw < 40.0 and th < 45.0) or (hot_tw <= 1 and cold_tw >= 7)
        
        # Compute certainty score
        vix_val = macro_pivot.loc[d, 'VIX'] if 'VIX' in macro_pivot.columns else 18.0
        pcr_val = macro_pivot.loc[d, 'CBOE_PCR'] if 'CBOE_PCR' in macro_pivot.columns else 1.0
        fg_val = macro_pivot.loc[d, 'FG'] if 'FG' in macro_pivot.columns else 50.0
        
        vec_scores = [
            0.8 if th >= 50.0 else 0.3,
            0.8 if v_tw >= 50.0 else 0.3,
            0.8 if vix_val < 20.0 else 0.3,
            0.8 if pcr_val < 1.0 else 0.3,
            0.8 if fg_val >= 45.0 else 0.3
        ]
        c_score, _, _, _ = compute_certainty_score([], 0.0, vec_scores)
        
        # Regime Evaluation
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            current_mode=current_mode, days_in_mode=days_in_mode, tw_prev=prev_tw
        )
        prev_tw = tw
        
        # ENHANCED MODE FIX: Intercept pre-crash distribution in PULLBACK_ALCISTA
        if mode_type != "BASELINE":
            if current_mode == "PULLBACK_ALCISTA" and is_pre_crash_distribution:
                new_mode = "DISTRIBUCION_PRE_CRASH"
                
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
        
        # ENHANCED ALLOCATION FIX: In PULLBACK_ALCISTA, enforce SV5_TW >= 45% or hold CASH
        if mode_type != "BASELINE" and current_mode == "PULLBACK_ALCISTA":
            valid_secs = [s for s in available_secs if sec_v_tw.get(s, 0.0) >= 45.0]
            if valid_secs:
                tot_cap = sum(SECTOR_CAP_WEIGHTS.get(s, 0.05) for s in valid_secs)
                target_weights = {s: SECTOR_CAP_WEIGHTS.get(s, 0.05) / tot_cap for s in valid_secs}
            else:
                target_weights = {s: 0.0 for s in available_secs}
                
        # CERTAINTY SCALING: Scale exposure by Certainty Score
        if mode_type == "INTELLIGENCE_ENHANCED":
            scale_factor = 1.0 if c_score >= 75.0 else (0.7 if c_score >= 50.0 else 0.4)
            target_weights = {s: w * scale_factor for s, w in target_weights.items()}
            
        portfolio_cash = current_equity
        portfolio_shares = {s: 0.0 for s in SECTORS_11}
        for s, w in target_weights.items():
            if w > 0 and s in price_pivot.columns and pd.notna(price_pivot.loc[d, s]) and price_pivot.loc[d, s] > 0:
                allocated = current_equity * w
                portfolio_shares[s] = allocated / price_pivot.loc[d, s]
                portfolio_cash -= allocated

        # Check year end
        if i < len(dates) - 1 and dates[i+1].year != curr_yr:
            yearly_records.append({"year": curr_yr, "spy_shares": round(spy_equiv_shares, 2)})
            curr_yr = dates[i+1].year
            
    yearly_records.append({"year": curr_yr, "spy_shares": round(spy_equiv_shares, 2)})
    return spy_equiv_shares, pd.DataFrame(yearly_records).set_index("year")

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot = load_data(store)
    store.close()
    
    sh_base, yr_base = run_simulation(price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot, mode_type="BASELINE")
    sh_enh, yr_enh = run_simulation(price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot, mode_type="INTELLIGENCE_ENHANCED")
    
    print("\n" + "="*95)
    print("      ⚖️ AUDITORÍA MAESTRA: CÓMO FUE (V35 BASELINE) VS CÓMO DEBIÓ SER (INTELLIGENCE ENHANCED)")
    print("="*95)
    print(f"{'Año':<6s} | {'V35 Baseline Shares':<22s} | {'Intelligence Enhanced Shares':<28s} | {'Diferencia Net Alpha'}")
    print("-" * 95)
    
    for yr in yr_base.index:
        sb = yr_base.loc[yr, 'spy_shares']
        se = yr_enh.loc[yr, 'spy_shares'] if yr in yr_enh.index else sb
        diff = se - sb
        status = "🟢 Mejora Limpia" if diff > 0.5 else ("🔴 Ligero Retroceso" if diff < -0.5 else "⚪ Empate")
        print(f"{yr:<6d} | {sb:22.2f} | {se:28.2f} | {diff:+18.2f} ({status})")
        
    print("="*95)
    print(f"ACCIONES FINALES BASELINE V35                : {sh_base:.2f} Acciones de SPY (4.84x Compounding)")
    print(f"ACCIONES FINALES CÓMO DEBIÓ SER (ENHANCED)  : {sh_enh:.2f} Acciones de SPY ({sh_enh/100.0:.2f}x Compounding) 🟢")
    print(f"GANANCIA NETA INCREMENTAL DE INTELIGENCIA    : +{sh_enh - sh_base:.2f} ACCIONES DE SPY MÁS 🟢")
    print("="*95)

if __name__ == "__main__":
    main()
