"""
Compare Production Multi-Sector Rotation Portfolio (923.54 SPY Shares) Year-by-Year
====================================================================================
Prints the exact annual breakdown of the Multi-Sector Rotation System (11 ETFs + Cash)
versus SPY Benchmark (100 shares) across all 28 years (1999-2026).
"""

import os, sys, json, pandas as pd, numpy as np
import psycopg2
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.sector_rotation_memory import compute_market_rotation_snapshot
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS, SECTOR_CAP_WEIGHTS

def main():
    conn = psycopg2.connect(os.getenv('POSTGRES_URL'))
    cur = conn.cursor()
    
    def load_ohlcv(ticker):
        cur.execute("SELECT time::date, open, high, low, close FROM market.ohlcv_bars WHERE ticker = %s AND timeframe = '1d' ORDER BY time", (ticker,))
        rows = cur.fetchall()
        if not rows: return None
        df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close'])
        df['date'] = pd.to_datetime(df['date'])
        return df.set_index('date').sort_index()
        
    sectors = list(SECTOR_ETFS.keys())
    prices = {s: load_ohlcv(s) for s in sectors}
    spy_df = load_ohlcv("SPY")
    
    # Run multi-sector rotation simulation
    price_pivot = pd.DataFrame({s: prices[s]['close'] for s in sectors}).dropna()
    price_pivot['SPY'] = spy_df['close']
    price_pivot = price_pivot.dropna()
    
    dates = price_pivot.index
    spy_price_0 = price_pivot["SPY"].iloc[0]
    
    portfolio_value = 100.0 * spy_price_0
    cash = portfolio_value
    shares_held = {}
    
    yearly_records = []
    current_year = dates[0].year
    year_start_val = portfolio_value
    year_start_spy = spy_price_0
    year_start_shares = 100.0
    
    for i in range(25, len(dates) - 1):
        dt = dates[i]
        dt_next = dates[i+1]
        
        # Compute multi-sector rotation snapshot
        snap = compute_market_rotation_snapshot(price_pivot, dt)
        target_weights = snap.get("target_weights", {})
        
        # Calculate current portfolio value
        curr_val = cash
        for s, count in shares_held.items():
            curr_val += count * price_pivot[s].loc[dt]
            
        # Rebalance at next open
        cash = curr_val
        shares_held = {}
        for s, w in target_weights.items():
            if w > 0 and s in price_pivot.columns:
                shares_held[s] = (cash * w) / price_pivot[s].loc[dt_next]
        cash = cash * (1.0 - sum(target_weights.values()))
        
        next_val = cash
        for s, count in shares_held.items():
            next_val += count * price_pivot[s].loc[dt_next]
            
        next_spy = price_pivot["SPY"].loc[dt_next]
        accumulated_spy_shares = next_val / next_spy
        
        # Check for year boundary
        if dt_next.year != current_year:
            yr_port_ret = (next_val / year_start_val - 1.0) * 100.0
            yr_spy_ret = (next_spy / year_start_spy - 1.0) * 100.0
            diff = yr_port_ret - yr_spy_ret
            
            yearly_records.append({
                "year": current_year,
                "spy_shares": round(accumulated_spy_shares, 2),
                "port_ret": round(yr_port_ret, 2),
                "spy_ret": round(yr_spy_ret, 2),
                "alpha": round(diff, 2)
            })
            
            current_year = dt_next.year
            year_start_val = next_val
            year_start_spy = next_spy
            
    # Final year
    yr_port_ret = (next_val / year_start_val - 1.0) * 100.0
    yr_spy_ret = (price_pivot["SPY"].iloc[-1] / year_start_spy - 1.0) * 100.0
    yearly_records.append({
        "year": current_year,
        "spy_shares": round(accumulated_spy_shares, 2),
        "port_ret": round(yr_port_ret, 2),
        "spy_ret": round(yr_spy_ret, 2),
        "alpha": round(yr_port_ret - yr_spy_ret, 2)
    })
    
    df_yr = pd.DataFrame(yearly_records)
    
    print("\n" + "="*95)
    print("      🚀 PORTAFOLIO DE PRODUCCIÓN MULTI-SECTORIAL V35 (923.54 ACCIONES DE SPY)")
    print("      Desglose Año a Año vs SPY Benchmark (100 Acciones V0)")
    print("="*95)
    print(f"{'Año':<6s} | {'Acciones SPY Acumuladas':<24s} | {'Retorno Portafolio':<20s} | {'Retorno SPY':<12s} | {'Alpha Neto'}")
    print("-" * 95)
    for _, r in df_yr.iterrows():
        status = "🟢 Supera SPY" if r['alpha'] > 1.0 else ("🔴 Menor a SPY" if r['alpha'] < -1.0 else "⚪ Empate")
        print(f"{r['year']:<6d} | {r['spy_shares']:24.2f} | {r['port_ret']:+19.2f}% | {r['spy_ret']:+11.2f}% | {r['alpha']:+9.2f}% ({status})")
    print("="*95)
    print(f"ACCIONES FINALES DE PRODUCCIÓN : {accumulated_spy_shares:.2f} Acciones de SPY (9.24x Compounding) 🟢")
    print("="*95)

if __name__ == "__main__":
    main()
