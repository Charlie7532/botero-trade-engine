"""
Compare QQQ Buy-and-Hold vs Gate V40 Across Regimes
===================================================
Analyzes:
1. Regimes where Gate V40 BEATS QQQ (Le ganamos al QQQ).
2. Regimes where QQQ "lays traps" (QQQ nos hace trampas: fake breakouts, sharp drawdowns, distribution traps).
"""

import os, sys, json, pandas as pd, numpy as np
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
from backend.scripts.backtest_qqq_integrated_gate import load_data, SECTORS_11
from backend.scripts.test_v40_volatility_adjusted_qqq_gate import run_v40_simulation

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot = load_data(store, start_date="1999-01-01")
    
    dates = price_pivot.index
    gate = QualityEntryGate()
    
    qqq_prices = price_pivot['QQQ']
    spy_prices = price_pivot['SPY']
    
    eq_v40 = run_v40_simulation(price_pivot, mkt_breadth, sec_ind_pivot)
    
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
    
    df_all = pd.DataFrame({
        "QQQ": qqq_prices,
        "SPY": spy_prices,
        "V40_Shares": eq_v40['spy_shares'],
        "Regime": regime_series
    }, index=dates)
    
    df_all['qqq_ret'] = df_all['QQQ'].pct_change().fillna(0)
    df_all['v40_ret'] = df_all['V40_Shares'].pct_change().fillna(0)
    
    regimes = df_all['Regime'].unique()
    summary = []
    
    for r in regimes:
        sub = df_all[df_all['Regime'] == r]
        n_days = len(sub)
        if n_days == 0: continue
        
        qqq_tot_ret = (sub['QQQ'].iloc[-1] / sub['QQQ'].iloc[0] - 1.0) * 100.0 if n_days > 1 else 0.0
        v40_tot_ret = (sub['V40_Shares'].iloc[-1] / sub['V40_Shares'].iloc[0] - 1.0) * 100.0 if n_days > 1 else 0.0
        
        qqq_max_dd = ((sub['QQQ'] / sub['QQQ'].cummax() - 1.0).min()) * 100.0
        v40_max_dd = ((sub['V40_Shares'] / sub['V40_Shares'].cummax() - 1.0).min()) * 100.0
        
        qqq_win = (sub['qqq_ret'] > 0).mean() * 100.0
        v40_win = (sub['v40_ret'] > 0).mean() * 100.0
        
        delta = v40_tot_ret - qqq_tot_ret
        
        if delta > +5.0:
            verdict = "🟢 LE GANAMOS AMPLIO (Gate protege capital)"
        elif delta < -5.0:
            verdict = "🔴 QQQ TIENE MAS RALLY (Euphoria Momentum)"
        else:
            verdict = "⚪ PAREJO (Paridad)"
            
        summary.append({
            "regime": r,
            "days": n_days,
            "pct_time": (n_days / len(dates)) * 100.0,
            "qqq_ret": qqq_tot_ret,
            "v40_ret": v40_tot_ret,
            "delta": delta,
            "qqq_max_dd": qqq_max_dd,
            "v40_max_dd": v40_max_dd,
            "qqq_win": qqq_win,
            "v40_win": v40_win,
            "verdict": verdict
        })
        
    df_sum = pd.DataFrame(summary).sort_values("days", ascending=False)
    
    print("\n" + "="*115)
    print("      📊 INVESTIGACIÓN: QQQ BUY & HOLD vs GATE V40 POR RÉGIMEN (DÓNDE GANAMOS Y DÓNDE HACE TRAMPAS)")
    print("="*115)
    print(f"{'Régimen':<26s} | {'Días':<5s} | {'QQQ Ret':<9s} | {'V40 Ret':<9s} | {'Δ V40 vs QQQ':<12s} | {'MaxDD QQQ':<10s} | {'MaxDD V40':<10s} | {'Diagnóstico'}")
    print("-" * 115)
    for _, r in df_sum.iterrows():
        print(f"{r['regime']:<26s} | {r['days']:<5d} | {r['qqq_ret']:+8.1f}% | {r['v40_ret']:+8.1f}% | {r['delta']:+11.1f}% | {r['qqq_max_dd']:9.1f}% | {r['v40_max_dd']:9.1f}% | {r['verdict']}")
    print("="*115)

if __name__ == "__main__":
    main()
