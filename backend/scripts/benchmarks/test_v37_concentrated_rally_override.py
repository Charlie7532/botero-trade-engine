"""
Test V37: Cap-Weighted Breadth Divergence Regime Override for Concentrated Rallies
===================================================================================
Evaluates V37 where Cap-Weighted Breadth Divergence (S5_QQQ_FI - S5_FI >= 15pp)
overrides macro equal-weighted cash drag and triggers RALLY_CONCENTRADO_MEGA_CAP.
"""

import os
import sys
import json
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
from backend.scripts._lib.backtest_qqq_integrated_gate import load_data, SECTORS_11, ALL_ASSETS

def run_v37_simulation(price_pivot, mkt_breadth, sec_ind_pivot):
    dates = price_pivot.index
    n_days = len(dates)
    
    spy_price_0 = price_pivot["SPY"].iloc[0]
    portfolio_value = 100.0 * spy_price_0
    shares_held = {"SPY": 100.0}
    cash = 0.0
    
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    
    equity_curve = []
    
    for i in range(n_days):
        dt = dates[i]
        spy_p = price_pivot["SPY"].loc[dt]
        
        curr_val = cash
        for asset, s_cnt in shares_held.items():
            if asset in price_pivot.columns:
                curr_val += s_cnt * price_pivot[asset].loc[dt]
        
        equity_spy_shares = curr_val / spy_p
        equity_curve.append((dt, equity_spy_shares, curr_val))
        
        th = mkt_breadth["th"].loc[dt] if dt in mkt_breadth.index else 50.0
        fi = mkt_breadth["fi"].loc[dt] if dt in mkt_breadth.index else 50.0
        tw = mkt_breadth["tw"].loc[dt] if dt in mkt_breadth.index else 50.0
        v_th = mkt_breadth["v_th"].loc[dt] if dt in mkt_breadth.index else 50.0
        v_fi = mkt_breadth["v_fi"].loc[dt] if dt in mkt_breadth.index else 50.0
        v_tw = mkt_breadth["v_tw"].loc[dt] if dt in mkt_breadth.index else 50.0
        
        sec_th = {s: sec_ind_pivot.get(f"S5_{s}_TH", pd.Series(50.0, index=dates)).loc[dt] for s in SECTORS_11 + ["QQQ"]}
        sec_fi = {s: sec_ind_pivot.get(f"S5_{s}_FI", pd.Series(50.0, index=dates)).loc[dt] for s in SECTORS_11 + ["QQQ"]}
        sec_tw = {s: sec_ind_pivot.get(f"S5_{s}_TW", pd.Series(50.0, index=dates)).loc[dt] for s in SECTORS_11 + ["QQQ"]}
        sec_v_fi = {s: sec_ind_pivot.get(f"SV5_{s}_FI", pd.Series(50.0, index=dates)).loc[dt] for s in SECTORS_11 + ["QQQ"]}
        sec_v_tw = {s: sec_ind_pivot.get(f"SV5_{s}_TW", pd.Series(50.0, index=dates)).loc[dt] for s in SECTORS_11 + ["QQQ"]}
        
        # Base regime evaluation
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            current_mode=current_mode, days_in_mode=days_in_mode
        )
        
        # V37 OVERRIDE: Concentrated Mega-Cap Rally Detection
        qqq_fi_val = sec_fi.get("QQQ", 50.0)
        qqq_div = qqq_fi_val - fi
        
        # Trigger Concentrated Mega-Cap Rally override if QQQ breadth > 55% AND divergence >= 15pp
        # (Must NOT be in CRASH_SISTEMICO or DISTRIBUCION_PRE_CRASH)
        if current_mode not in ("CRASH_SISTEMICO", "DISTRIBUCION_PRE_CRASH"):
            if qqq_fi_val >= 55.0 and qqq_div >= 15.0:
                new_mode = "RALLY_CONCENTRADO_MEGA_CAP"
                
        if new_mode == current_mode:
            days_in_mode += 1
        else:
            current_mode = new_mode
            days_in_mode = 1
            
        # Target weight allocation
        if current_mode == "RALLY_CONCENTRADO_MEGA_CAP":
            # Direct 60% QQQ + 20% XLK + 20% XLC (100% Equity, 0% Cash drag)
            target_weights = {"QQQ": 0.60, "XLK": 0.20, "XLC": 0.20}
        else:
            avail = SECTORS_11.copy()
            target_weights = gate.calculate_target_weights(
                mode=current_mode,
                sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
                avail_sectors=avail,
                sec_v_fi=sec_v_fi, sec_v_tw=sec_v_tw
            )
            
        tot_wt = sum(target_weights.values())
        if tot_wt > 0:
            target_weights = {s: w / tot_wt for s, w in target_weights.items()}
            
        new_shares = {}
        for asset, w in target_weights.items():
            if w > 0 and asset in price_pivot.columns:
                asset_p = price_pivot[asset].loc[dt]
                new_shares[asset] = (curr_val * w) / asset_p
                
        shares_held = new_shares
        cash = curr_val * (1.0 - sum(target_weights.values()))
        
    df_eq = pd.DataFrame(equity_curve, columns=["date", "spy_shares", "usd_val"]).set_index("date")
    return df_eq

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot = load_data(store, start_date="1999-01-01")
    
    print("Running V37 Concentrated Mega-Cap Rally Backtest (1999-2026)...")
    eq_v37 = run_v37_simulation(price_pivot, mkt_breadth, sec_ind_pivot)
    
    eq_v37['year'] = pd.to_datetime(eq_v37.index).year
    years = sorted(eq_v37['year'].unique())
    
    print("\n" + "="*70)
    print("      V37 TABLA MAESTRA CON OVERRIDE DE RALLY CONCENTRADO (1999 - 2026)")
    print("="*70)
    print(f"{'Año':<6s} | {'SPY Shares V37':<14s} | {'Retorno V37':<12s}")
    print("-" * 70)
    
    prev = 100.0
    for y in years:
        sub = eq_v37[eq_v37['year'] == y]
        end = sub['spy_shares'].iloc[-1]
        ret = (end / prev - 1.0) * 100.0
        flag = "🟢" if ret > 0 else "🔴"
        print(f"{y:<6d} | {end:14.2f} | {ret:+11.2f}% {flag}")
        prev = end
        
    print("-" * 70)
    tot = eq_v37['spy_shares'].iloc[-1]
    print(f"ACCIONES FINALES V37 : {tot:.2f} Acciones de SPY (+{tot-100:.2f} acc)")
    print("="*70)

if __name__ == "__main__":
    main()
