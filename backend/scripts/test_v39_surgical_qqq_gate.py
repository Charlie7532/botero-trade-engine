"""
Test V39: Surgical QQQ Integration into Sector Rotation Pool
============================================================
Integrates QQQ into QualityEntryGate.calculate_target_weights() as a high-conviction
satellite asset during Tech Leadership regimes, WITHOUT destroying macro pre-crash protection.
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
from backend.scripts.backtest_qqq_integrated_gate import load_data, SECTORS_11, ALL_ASSETS

def run_v39_simulation(price_pivot, mkt_breadth, sec_ind_pivot):
    dates = price_pivot.index
    n_days = len(dates)
    
    spy_price_0 = price_pivot["SPY"].iloc[0]
    portfolio_value = 100.0 * spy_price_0
    shares_held = {"SPY": 100.0}
    cash = 0.0
    
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    
    # Calculate 20-day relative strength of QQQ vs SPY
    qqq_rs_20d = (price_pivot["QQQ"] / price_pivot["SPY"]).pct_change(20)
    qqq_ma150 = price_pivot["QQQ"].rolling(150, min_periods=50).mean()
    
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
        
        # Standard macro regime evaluation (UNTOUCHED Macro Risk Guardian)
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            current_mode=current_mode, days_in_mode=days_in_mode
        )
        
        if new_mode == current_mode:
            days_in_mode += 1
        else:
            current_mode = new_mode
            days_in_mode = 1
            
        # Target weight allocation with Surgical QQQ Integration
        avail = SECTORS_11.copy()
        target_weights = gate.calculate_target_weights(
            mode=current_mode,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            avail_sectors=avail,
            sec_v_fi=sec_v_fi, sec_v_tw=sec_v_tw
        )
        
        # SURGICAL QQQ RULE: When QQQ is in Stage 2 (price > MA150) and outperforming SPY with S5_QQQ_FI >= 55%
        qqq_p = price_pivot["QQQ"].loc[dt]
        qqq_ma = qqq_ma150.loc[dt] if dt in qqq_ma150.index else qqq_p
        rs_val = qqq_rs_20d.loc[dt] if dt in qqq_rs_20d.index else 0.0
        qqq_fi_val = sec_fi.get("QQQ", 50.0)
        
        is_qqq_stage2_leader = (qqq_p >= qqq_ma) and (rs_val > 0.0) and (qqq_fi_val >= 55.0)
        
        if current_mode in ("NORMAL", "MERCADO_SANO", "RE_ACUMULACION_ALCISTA") and is_qqq_stage2_leader:
            # Allocate 25% to QQQ, re-scaling remaining 75% among healthy sectors
            tot_w = sum(target_weights.values())
            if tot_w > 0:
                target_weights = {s: w / tot_w * 0.75 for s, w in target_weights.items()}
                target_weights["QQQ"] = 0.25
            else:
                target_weights["QQQ"] = 0.25
                
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
    
    print("Running V39 Surgical QQQ Gate Backtest (1999-2026)...")
    eq_v39 = run_v39_simulation(price_pivot, mkt_breadth, sec_ind_pivot)
    
    eq_v39['year'] = pd.to_datetime(eq_v39.index).year
    years = sorted(eq_v39['year'].unique())
    
    print("\n" + "="*70)
    print("      V39 TABLA MAESTRA CON INTEGRACIÓN QUIRÚRGICA QQQ (1999 - 2026)")
    print("="*70)
    print(f"{'Año':<6s} | {'SPY Shares V39':<14s} | {'Retorno V39':<12s}")
    print("-" * 70)
    
    prev = 100.0
    for y in years:
        sub = eq_v39[eq_v39['year'] == y]
        end = sub['spy_shares'].iloc[-1]
        ret = (end / prev - 1.0) * 100.0
        flag = "🟢" if ret > 0 else "🔴"
        print(f"{y:<6d} | {end:14.2f} | {ret:+11.2f}% {flag}")
        prev = end
        
    print("-" * 70)
    tot = eq_v39['spy_shares'].iloc[-1]
    print(f"ACCIONES FINALES V39 : {tot:.2f} Acciones de SPY (+{tot-100:.2f} acc)")
    print("="*70)

if __name__ == "__main__":
    main()
