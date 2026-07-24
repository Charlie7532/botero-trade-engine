"""
Detailed Regime & Yearly Comparison: V35 vs V39 vs V40
======================================================
Prints exact year-by-year and regime-by-regime performance,
analyzing where we gain (🟢) and where we lose (🔴).
"""

import os
import sys
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
from backend.scripts.backtest_qqq_integrated_gate import load_data, SECTORS_11, run_simulation
from backend.scripts.test_v39_surgical_qqq_gate import run_v39_simulation
from backend.scripts.test_v40_volatility_adjusted_qqq_gate import run_v40_simulation

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot = load_data(store, start_date="1999-01-01")
    
    eq_v35, _ = run_simulation(price_pivot, mkt_breadth, sec_ind_pivot, use_qqq_integration=False)
    eq_v39 = run_v39_simulation(price_pivot, mkt_breadth, sec_ind_pivot)
    eq_v40 = run_v40_simulation(price_pivot, mkt_breadth, sec_ind_pivot)
    
    dates = price_pivot.index
    gate = QualityEntryGate()
    
    current_mode = "NORMAL"
    days_in_mode = 0
    regime_series = []
    
    for dt in dates:
        th = mkt_breadth["th"].loc[dt] if dt in mkt_breadth.index else 50.0
        fi = mkt_breadth["fi"].loc[dt] if dt in mkt_breadth.index else 50.0
        tw = mkt_breadth["tw"].loc[dt] if dt in mkt_breadth.index else 50.0
        v_th = mkt_breadth["v_th"].loc[dt] if dt in mkt_breadth.index else 50.0
        v_fi = mkt_breadth["v_fi"].loc[dt] if dt in mkt_breadth.index else 50.0
        v_tw = mkt_breadth["v_tw"].loc[dt] if dt in mkt_breadth.index else 50.0
        
        sec_th = {s: sec_ind_pivot.get(f"S5_{s}_TH", pd.Series(50.0, index=dates)).loc[dt] for s in SECTORS_11 + ["QQQ"]}
        sec_fi = {s: sec_ind_pivot.get(f"S5_{s}_FI", pd.Series(50.0, index=dates)).loc[dt] for s in SECTORS_11 + ["QQQ"]}
        sec_tw = {s: sec_ind_pivot.get(f"S5_{s}_TW", pd.Series(50.0, index=dates)).loc[dt] for s in SECTORS_11 + ["QQQ"]}
        
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
        regime_series.append(current_mode)
        
    df_reg = pd.DataFrame({"regime": regime_series}, index=dates)
    
    eq_v35 = eq_v35.join(df_reg)
    eq_v39 = eq_v39.join(df_reg)
    eq_v40 = eq_v40.join(df_reg)
    
    eq_v35['daily_ret'] = eq_v35['spy_shares'].pct_change().fillna(0)
    eq_v39['daily_ret'] = eq_v39['spy_shares'].pct_change().fillna(0)
    eq_v40['daily_ret'] = eq_v40['spy_shares'].pct_change().fillna(0)
    
    # Calculate performance by regime
    regimes = eq_v35['regime'].unique()
    reg_summary = []
    for r in regimes:
        sub35 = eq_v35[eq_v35['regime'] == r]
        sub39 = eq_v39[eq_v39['regime'] == r]
        sub40 = eq_v40[eq_v40['regime'] == r]
        
        n_days = len(sub35)
        ret35_tot = (sub35['spy_shares'].iloc[-1] / sub35['spy_shares'].iloc[0] - 1.0) * 100.0 if n_days > 0 else 0
        ret39_tot = (sub39['spy_shares'].iloc[-1] / sub39['spy_shares'].iloc[0] - 1.0) * 100.0 if n_days > 0 else 0
        ret40_tot = (sub40['spy_shares'].iloc[-1] / sub40['spy_shares'].iloc[0] - 1.0) * 100.0 if n_days > 0 else 0
        
        win35 = (sub35['daily_ret'] > 0).mean() * 100.0
        win39 = (sub39['daily_ret'] > 0).mean() * 100.0
        win40 = (sub40['daily_ret'] > 0).mean() * 100.0
        
        reg_summary.append({
            "regime": r,
            "days": n_days,
            "pct_time": (n_days / len(dates)) * 100.0,
            "v35_ret": ret35_tot,
            "v39_ret": ret39_tot,
            "v40_ret": ret40_tot,
            "v35_win": win35,
            "v39_win": win39,
            "v40_win": win40,
        })
        
    df_reg_res = pd.DataFrame(reg_summary).sort_values("days", ascending=False)
    print("\n" + "="*110)
    print("      📊 COMPARATIVA DE DESEMPEÑO DETALLADA POR RÉGIMEN DE MERCADO")
    print("="*110)
    print(f"{'Régimen de Mercado':<30s} | {'Días':<6s} | {'%Tiempo':<8s} | {'V35 Ret':<9s} | {'V39 Ret':<9s} | {'V40 Ret':<9s} | {'V35 Win%':<9s} | {'V40 Win%':<9s}")
    print("-" * 110)
    for _, row in df_reg_res.iterrows():
        print(f"{row['regime']:<30s} | {row['days']:<6d} | {row['pct_time']:7.1f}% | {row['v35_ret']:+8.1f}% | {row['v39_ret']:+8.1f}% | {row['v40_ret']:+8.1f}% | {row['v35_win']:8.1f}% | {row['v40_win']:8.1f}%")
    print("="*110)

if __name__ == "__main__":
    main()
