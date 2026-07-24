"""
Compare V35 Baseline vs V39 Surgical QQQ Integration
"""
import json
import pandas as pd
from backend.scripts.backtest_qqq_integrated_gate import load_data, SECTORS_11
from backend.scripts.test_v39_surgical_qqq_gate import run_v39_simulation
from backend.scripts.backtest_qqq_integrated_gate import run_simulation
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

store = TimescaleDataStore()
price_pivot, mkt_breadth, sec_ind_pivot = load_data(store, start_date="1999-01-01")

eq_v35, _ = run_simulation(price_pivot, mkt_breadth, sec_ind_pivot, use_qqq_integration=False)
eq_v39 = run_v39_simulation(price_pivot, mkt_breadth, sec_ind_pivot)

eq_v35['year'] = pd.to_datetime(eq_v35.index).year
eq_v39['year'] = pd.to_datetime(eq_v39.index).year

years = sorted(eq_v35['year'].unique())

print("\n" + "="*85)
print("      TABLA DEFINITIVA 1999 - 2026: V35 BASELINE vs V39 SURGICAL QQQ GATE")
print("="*85)
print(f"{'Año':<6s} | {'V35 Acciones':<14s} | {'V39 Acciones':<14s} | {'Retorno V35':<12s} | {'Retorno V39':<12s} | {'Δ V39 vs V35':<12s}")
print("-" * 85)

prev_35, prev_39 = 100.0, 100.0

for y in years:
    sub35 = eq_v35[eq_v35['year'] == y]
    sub39 = eq_v39[eq_v39['year'] == y]
    
    end35 = sub35['spy_shares'].iloc[-1]
    end39 = sub39['spy_shares'].iloc[-1]
    
    ret35 = (end35 / prev_35 - 1.0) * 100.0
    ret39 = (end39 / prev_39 - 1.0) * 100.0
    diff = ret39 - ret35
    
    flag = "🟢" if diff > 0.3 else ("🔴" if diff < -0.3 else "⚪")
    print(f"{y:<6d} | {end35:14.2f} | {end39:14.2f} | {ret35:+11.2f}% | {ret39:+11.2f}% | {diff:+11.2f}% {flag}")
    
    prev_35, prev_39 = end35, end39

print("-" * 85)
tot35 = eq_v35['spy_shares'].iloc[-1]
tot39 = eq_v39['spy_shares'].iloc[-1]
print(f"ACCIONES FINALES V35 : {tot35:.2f} Acciones de SPY (+{tot35-100:.2f} acc)")
print(f"ACCIONES FINALES V39 : {tot39:.2f} Acciones de SPY (+{tot39-100:.2f} acc)")
print(f"NUEVO RECORD HISTÓRICO: +{tot39 - tot35:+.2f} Acciones de SPY ganadas sobre V35")
print("="*85)
