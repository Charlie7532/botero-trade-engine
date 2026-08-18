"""
Fast Master Yearly and Regime Breakdown
"""

import os
import sys
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
from backend.scripts._lib.backtest_qqq_integrated_gate import load_data, SECTORS_11, run_simulation
from backend.scripts._lib.backtest_qqq_integrated_gate import run_v39_simulation
from backend.scripts._lib.backtest_qqq_integrated_gate import run_v40_simulation

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot = load_data(store, start_date="1999-01-01")
    
    eq_v35, _ = run_simulation(price_pivot, mkt_breadth, sec_ind_pivot, use_qqq_integration=False)
    eq_v39 = run_v39_simulation(price_pivot, mkt_breadth, sec_ind_pivot)
    eq_v40 = run_v40_simulation(price_pivot, mkt_breadth, sec_ind_pivot)
    
    eq_v35['year'] = pd.to_datetime(eq_v35.index).year
    eq_v39['year'] = pd.to_datetime(eq_v39.index).year
    eq_v40['year'] = pd.to_datetime(eq_v40.index).year
    
    years = sorted(eq_v35['year'].unique())
    
    out = []
    out.append("="*105)
    out.append("      📈 TABLA DEFINITIVA AÑO A AÑO: PRODUCCIÓN V35 vs SURGICAL V39 vs VOL PARITY V40")
    out.append("="*105)
    out.append(f"{'Año':<6s} | {'V35 Acc':<11s} | {'V39 Acc':<11s} | {'V40 Acc':<11s} | {'Ret V35':<10s} | {'Ret V39':<10s} | {'Ret V40':<10s} | {'Δ V39 vs V35':<12s}")
    out.append("-" * 105)
    
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
        
        out.append(f"{y:<6d} | {end35:11.2f} | {end39:11.2f} | {end40:11.2f} | {ret35:+9.2f}% | {ret39:+9.2f}% | {ret40:+9.2f}% | {diff:+11.2f}% {flag}")
        
        prev35, prev39, prev40 = end35, end39, end40
        
    out.append("-" * 105)
    tot35 = eq_v35['spy_shares'].iloc[-1]
    tot39 = eq_v39['spy_shares'].iloc[-1]
    tot40 = eq_v40['spy_shares'].iloc[-1]
    
    out.append(f"ACCIONES FINALES PRODUCCIÓN V35 : {tot35:.2f} Acciones de SPY (+{tot35-100:.2f} acc)")
    out.append(f"ACCIONES FINALES SURGICAL V39   : {tot39:.2f} Acciones de SPY (+{tot39-100:.2f} acc)")
    out.append(f"ACCIONES FINALES VOL PARITY V40 : {tot40:.2f} Acciones de SPY (+{tot40-100:.2f} acc)")
    out.append(f"NUEVO RECORD HISTÓRICO V39: +{tot39 - tot35:+.2f} Acciones de SPY ganadas sobre Producción V35")
    out.append("="*105)
    
    text = "\n".join(out)
    with open("backend/scripts/summary_output.txt", "w") as f:
        f.write(text)
    print("SAVED TO backend/scripts/summary_output.txt")

if __name__ == "__main__":
    main()
