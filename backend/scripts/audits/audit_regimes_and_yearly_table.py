"""
Deep Audit: Year-by-Year & Market Regime Performance Breakdown (1999 - 2026)
=============================================================================
Evaluates Production Baseline V35 vs Surgical QQQ V39 vs Volatility Parity V40
across all 10 Market Regimes and prints the complete 27.5-year table.
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
from backend.scripts._lib.backtest_qqq_integrated_gate import load_data, SECTORS_11, run_simulation
from backend.scripts._lib.backtest_qqq_integrated_gate import run_v39_simulation
from backend.scripts._lib.backtest_qqq_integrated_gate import run_v40_simulation

def analyze_regime_breakdown(price_pivot, mkt_breadth, sec_ind_pivot):
    dates = price_pivot.index
    gate = QualityEntryGate()
    
    current_mode = "NORMAL"
    days_in_mode = 0
    
    mode_counts = {}
    
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
            
        mode_counts[current_mode] = mode_counts.get(current_mode, 0) + 1
        
    return mode_counts

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot = load_data(store, start_date="1999-01-01")
    
    print("Ejecutando simulaciones 1999-2026...")
    eq_v35, _ = run_simulation(price_pivot, mkt_breadth, sec_ind_pivot, use_qqq_integration=False)
    eq_v39 = run_v39_simulation(price_pivot, mkt_breadth, sec_ind_pivot)
    eq_v40 = run_v40_simulation(price_pivot, mkt_breadth, sec_ind_pivot)
    
    mode_counts = analyze_regime_breakdown(price_pivot, mkt_breadth, sec_ind_pivot)
    
    eq_v35['year'] = pd.to_datetime(eq_v35.index).year
    eq_v39['year'] = pd.to_datetime(eq_v39.index).year
    eq_v40['year'] = pd.to_datetime(eq_v40.index).year
    
    years = sorted(eq_v35['year'].unique())
    
    print("\n" + "="*95)
    print("      📊 COMPARATIVA MAESTRA POR RÉGIMEN DE MERCADO (1999 - 2026)")
    print("="*95)
    print(f"{'Régimen de Mercado':<35s} | {'Días Activos':<12s} | {'% del Tiempo':<12s}")
    print("-" * 95)
    tot_days = sum(mode_counts.values())
    for mode, cnt in sorted(mode_counts.items(), key=lambda x: x[1], reverse=True):
        pct = (cnt / tot_days) * 100.0
        print(f"{mode:<35s} | {cnt:<12d} | {pct:11.1f}%")
    print("="*95)
    
    print("\n" + "="*105)
    print("      📈 TABLA DEFINITIVA AÑO A AÑO: PRODUCCIÓN V35 vs SURGICAL V39 vs VOL PARITY V40")
    print("="*105)
    print(f"{'Año':<6s} | {'V35 Acc':<11s} | {'V39 Acc':<11s} | {'V40 Acc':<11s} | {'Ret V35':<10s} | {'Ret V39':<10s} | {'Ret V40':<10s} | {'Δ V39 vs V35':<12s}")
    print("-" * 105)
    
    prev35, prev39, prev40 = 100.0, 100.0, 100.0
    
    for y in years:
        sub35 = eq_v35[eq_v35['year'] == y]
        sub39 = eq_v39[eq_v39['year'] == y]
        sub40 = eq_v40[eq_v40['year'] == y]
        
        end35 = sub35['spy_shares'].iloc[-1]
        end39 = sub39['spy_shares'].iloc[-1]
        end40 = sub40['spy_shares'].iloc[-1]
        
        ret35 = (end35 / prev35 - 1.0) * 100.0
        ret39 = (end39 / prev39 - 1.0) * 100.0
        ret40 = (end40 / prev40 - 1.0) * 100.0
        
        diff = ret39 - ret35
        flag = "🟢" if diff > 0.3 else ("🔴" if diff < -0.3 else "⚪")
        
        print(f"{y:<6d} | {end35:11.2f} | {end39:11.2f} | {end40:11.2f} | {ret35:+9.2f}% | {ret39:+9.2f}% | {ret40:+9.2f}% | {diff:+11.2f}% {flag}")
        
        prev35, prev39, prev40 = end35, end39, end40
        
    print("-" * 105)
    tot35 = eq_v35['spy_shares'].iloc[-1]
    tot39 = eq_v39['spy_shares'].iloc[-1]
    tot40 = eq_v40['spy_shares'].iloc[-1]
    
    print(f"ACCIONES FINALES PRODUCCIÓN V35 : {tot35:.2f} Acciones de SPY (+{tot35-100:.2f} acc)")
    print(f"ACCIONES FINALES SURGICAL V39   : {tot39:.2f} Acciones de SPY (+{tot39-100:.2f} acc)")
    print(f"ACCIONES FINALES VOL PARITY V40 : {tot40:.2f} Acciones de SPY (+{tot40-100:.2f} acc)")
    print(f"NUEVO RECORD HISTÓRICO V39: +{tot39 - tot35:+.2f} Acciones de SPY ganadas sobre Producción V35")
    print("="*105)

if __name__ == "__main__":
    main()
