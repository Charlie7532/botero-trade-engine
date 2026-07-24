"""
Compare QQQ vs XLK (Pure Tech) vs SPY & Rotational Edge
======================================================
Empirical analysis of:
1. When is pure Tech (XLK) superior to QQQ?
2. When is QQQ superior to XLK?
3. How do news shocks affect XLK vs QQQ?
"""

import os, sys, json, pandas as pd, numpy as np
import psycopg2
from dotenv import load_dotenv; load_dotenv()

def main():
    conn = psycopg2.connect(os.getenv('POSTGRES_URL'))
    cur = conn.cursor()
    
    def load_df(ticker):
        cur.execute("SELECT time::date, close FROM market.ohlcv_bars WHERE ticker = %s AND timeframe = '1d' ORDER BY time", (ticker,))
        rows = cur.fetchall()
        if not rows: return None
        df = pd.DataFrame(rows, columns=['date', 'close']).set_index('date')
        df.index = pd.to_datetime(df.index)
        return df['close']
        
    qqq = load_df("QQQ")
    xlk = load_df("XLK")
    spy = load_df("SPY")
    xlf = load_df("XLF")
    
    df = pd.DataFrame({"QQQ": qqq, "XLK": xlk, "SPY": spy, "XLF": xlf}).dropna()
    
    df['qqq_ret'] = df['QQQ'].pct_change().fillna(0)
    df['xlk_ret'] = df['XLK'].pct_change().fillna(0)
    df['spy_ret'] = df['SPY'].pct_change().fillna(0)
    df['xlf_ret'] = df['XLF'].pct_change().fillna(0)
    
    # 1. Total compounding (1999-2026)
    qqq_total = (df['QQQ'].iloc[-1] / df['QQQ'].iloc[0] - 1.0) * 100
    xlk_total = (df['XLK'].iloc[-1] / df['XLK'].iloc[0] - 1.0) * 100
    spy_total = (df['SPY'].iloc[-1] / df['SPY'].iloc[0] - 1.0) * 100
    
    # 2. Yearly breakdown QQQ vs XLK
    df['year'] = df.index.year
    yearly = []
    for y, sub in df.groupby('year'):
        q_ret = (sub['QQQ'].iloc[-1] / sub['QQQ'].iloc[0] - 1.0) * 100
        x_ret = (sub['XLK'].iloc[-1] / sub['XLK'].iloc[0] - 1.0) * 100
        s_ret = (sub['SPY'].iloc[-1] / sub['SPY'].iloc[0] - 1.0) * 100
        winner = "XLK (Pure Tech)" if x_ret > q_ret + 1.0 else ("QQQ (Mega Cap Tech+Disc)" if q_ret > x_ret + 1.0 else "TIED")
        yearly.append({
            "year": y,
            "qqq_ret": round(q_ret, 1),
            "xlk_ret": round(x_ret, 1),
            "spy_ret": round(s_ret, 1),
            "winner": winner
        })
        
    df_yr = pd.DataFrame(yearly)
    
    print("\n" + "="*85)
    print("      ⚔️ ANÁLISIS DE ANTES Y DESPUÉS: QQQ (Nasdaq 100) vs XLK (Tecnología Pura)")
    print("="*85)
    print(f"Retorno Total QQQ Buy & Hold (1999-2026) : {qqq_total:+8.1f}%")
    print(f"Retorno Total XLK Buy & Hold (1999-2026) : {xlk_total:+8.1f}%")
    print(f"Retorno Total SPY Buy & Hold (1999-2026) : {spy_total:+8.1f}%")
    print("-" * 85)
    print(f"{'Año':<6s} | {'QQQ Ret':<9s} | {'XLK Ret':<9s} | {'SPY Ret':<9s} | {'Ganador'}")
    print("-" * 85)
    for _, r in df_yr.iterrows():
        print(f"{r['year']:<6d} | {r['qqq_ret']:+8.1f}% | {r['xlk_ret']:+8.1f}% | {r['spy_ret']:+8.1f}% | {r['winner']}")
    print("="*85)

if __name__ == "__main__":
    main()
