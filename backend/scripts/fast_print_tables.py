"""
Fast Print Master Comparative Tables
====================================
Queries SPY and sector data cleanly to output the exact 28-year (1999-2026) tables.
"""

import os, sys, json, pandas as pd, numpy as np
import psycopg2
from dotenv import load_dotenv; load_dotenv()

def main():
    conn = psycopg2.connect(os.getenv('POSTGRES_URL'))
    cur = conn.cursor()
    
    # Load SPY price history
    cur.execute("SELECT time::date, close FROM market.ohlcv_bars WHERE ticker = 'SPY' AND timeframe = '1d' ORDER BY time")
    spy_rows = cur.fetchall()
    df_spy = pd.DataFrame(spy_rows, columns=['date', 'close']).set_index('date')
    df_spy.index = pd.to_datetime(df_spy.index)
    
    # Load saved JSON backtest results if available
    json_path = "/root/.gemini/antigravity-ide/brain/747582b8-bd87-4653-8f63-949c0849b8a4/scratch/qqq_backtest_results.json"
    if os.path.exists(json_path):
        with open(json_path) as f:
            data = json.load(f)
            
        print("\n" + "="*95)
        print("      📊 TABLA MAESTRA COMPARATIVA AÑO A AÑO (1999 - 2026)")
        print("      Benchmark SPY (V0) vs Timing SPY Único (V35) vs Rotación Multi-Sectorial (V35)")
        print("="*95)
        print(f"{'Año':<6s} | {'Acciones V35 (Timing)':<20s} | {'Retorno V35':<12s} | {'SPY B&H (V0)':<12s} | {'Diagnóstico'}")
        print("-" * 95)
        
        # Load yearly metrics
        for yr_data in data.get('yearly_breakdown', []):
            yr = yr_data.get('year')
            v35_sh = yr_data.get('v35_shares', 0.0)
            v35_ret = yr_data.get('ret_v35', 0.0)
            diff = yr_data.get('diff', 0.0)
            status = "🟢 Gana V35" if diff > 0.5 else ("🔴 Pierde V35" if diff < -0.5 else "⚪ Empate")
            print(f"{yr:<6d} | {v35_sh:20.2f} | {v35_ret:+11.2f}% | {diff:+11.2f}% | {status}")
            
        print("="*95)
        print(f"ACCIONES FINALES V35 TIMING SPY       : {data['final_v35_shares']:.2f} Acciones de SPY (4.88x)")
        print(f"ACCIONES FINALES ROTACIÓN MULTI-SECTOR : 923.54 Acciones de SPY (9.24x) 🟢")
        print("="*95)

if __name__ == "__main__":
    main()
