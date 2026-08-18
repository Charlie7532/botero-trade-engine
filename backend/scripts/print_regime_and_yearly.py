import os, sys, json, pandas as pd, numpy as np
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
from backend.scripts._lib.backtest_qqq_integrated_gate import load_data, SECTORS_11, run_simulation
from backend.scripts._lib.backtest_qqq_integrated_gate import run_v39_simulation
from backend.scripts._lib.backtest_qqq_integrated_gate import run_v40_simulation

store = TimescaleDataStore()
price_pivot, mkt_breadth, sec_ind_pivot = load_data(store, start_date="1999-01-01")

eq_v35, _ = run_simulation(price_pivot, mkt_breadth, sec_ind_pivot, use_qqq_integration=False)
eq_v39 = run_v39_simulation(price_pivot, mkt_breadth, sec_ind_pivot)
eq_v40 = run_v40_simulation(price_pivot, mkt_breadth, sec_ind_pivot)

eq_v35['year'] = pd.to_datetime(eq_v35.index).year
eq_v39['year'] = pd.to_datetime(eq_v39.index).year
eq_v40['year'] = pd.to_datetime(eq_v40.index).year

years = sorted(eq_v35['year'].unique())

print("\n=== TABLA COMPARATIVA AÑO A AÑO (DÓNDE GANAMOS Y DÓNDE PERDEMOS) ===")
print(f"{'Año':<6s} | {'V35 (Prod)':<10s} | {'V39 (Surgical)':<13s} | {'V40 (Vol Parity)':<15s} | {'Δ V40 vs V35':<12s} | {'Diagnóstico':<25s}")
print("-" * 95)

prev35, prev39, prev40 = 100.0, 100.0, 100.0
gains_years, loss_years, neutral_years = 0, 0, 0

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
    
    diff = ret40 - ret35
    if diff > 0.3:
        status = "🟢 GANA (Mayor Retorno)"
        gains_years += 1
    elif diff < -0.3:
        status = "🔴 PIERDE (Menor Retorno)"
        loss_years += 1
    else:
        status = "⚪ EMPATE (Idéntico)"
        neutral_years += 1
        
    print(f"{y:<6d} | {ret35:+9.2f}% | {ret39:+12.2f}% | {ret40:+14.2f}% | {diff:+11.2f}% | {status}")
    prev35, prev39, prev40 = end35, end39, end40

print("-" * 95)
print(f"RESUMEN DE AÑOS: {gains_years} Años Ganados 🟢 | {loss_years} Años Perdedores 🔴 | {neutral_years} Años Empatados ⚪")
