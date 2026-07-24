"""
Compare S5 & SV5 Breadth: XLK (Pure Tech) vs QQQ (Nasdaq 100)
============================================================
Evaluates:
1. S5_XLK_FI vs S5_QQQ_FI (Price Breadth Divergence)
2. SV5_XLK_FI vs SV5_QQQ_FI (Institutional Volume Breadth Divergence)
3. Quantitative Signal: When to allocate to XLK vs QQQ vs SPY.
"""

import os, sys, json, pandas as pd, numpy as np
import psycopg2
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.scripts.backtest_qqq_integrated_gate import load_data, SECTORS_11

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot = load_data(store, start_date="1999-01-01")
    
    dates = price_pivot.index
    
    s5_xlk_fi = sec_ind_pivot.get("S5_XLK_FI", pd.Series(50.0, index=dates))
    s5_qqq_fi = sec_ind_pivot.get("S5_QQQ_FI", pd.Series(50.0, index=dates))
    
    sv5_xlk_fi = sec_ind_pivot.get("SV5_XLK_FI", pd.Series(50.0, index=dates))
    sv5_qqq_fi = sec_ind_pivot.get("SV5_QQQ_FI", pd.Series(50.0, index=dates))
    
    xlk_prices = price_pivot["XLK"]
    qqq_prices = price_pivot["QQQ"]
    spy_prices = price_pivot["SPY"]
    
    df = pd.DataFrame({
        "XLK": xlk_prices,
        "QQQ": qqq_prices,
        "SPY": spy_prices,
        "S5_XLK_FI": s5_xlk_fi,
        "S5_QQQ_FI": s5_qqq_fi,
        "SV5_XLK_FI": sv5_xlk_fi,
        "SV5_QQQ_FI": sv5_qqq_fi
    }, index=dates).dropna()
    
    df['xlk_fwd5d'] = (df['XLK'].shift(-5) / df['XLK'] - 1.0) * 100
    df['qqq_fwd5d'] = (df['QQQ'].shift(-5) / df['QQQ'] - 1.0) * 100
    df['diff_fwd5d'] = df['xlk_fwd5d'] - df['qqq_fwd5d'] # Positive when XLK outperforms QQQ
    
    # Analyze volume breadth spread: SV5_XLK - SV5_QQQ
    df['v_spread'] = df['SV5_XLK_FI'] - df['SV5_QQQ_FI']
    
    # Group by Volume Spread Deciles
    df['v_spread_bin'] = pd.qcut(df['v_spread'], q=5, labels=["1_Extreme_QQQ_Vol", "2_QQQ_Vol", "3_Neutral", "4_XLK_Vol", "5_Extreme_XLK_Vol"])
    
    analysis = []
    for cat, sub in df.groupby('v_spread_bin'):
        avg_xlk_fwd = sub['xlk_fwd5d'].mean()
        avg_qqq_fwd = sub['qqq_fwd5d'].mean()
        avg_diff = sub['diff_fwd5d'].mean()
        xlk_win_rate = (sub['diff_fwd5d'] > 0).mean() * 100
        
        analysis.append({
            "vol_spread_regime": cat,
            "obs": len(sub),
            "avg_v_spread": round(sub['v_spread'].mean(), 1),
            "avg_xlk_fwd5d": round(avg_xlk_fwd, 2),
            "avg_qqq_fwd5d": round(avg_qqq_fwd, 2),
            "avg_alpha_xlk_vs_qqq": round(avg_diff, 2),
            "xlk_win_rate": round(xlk_win_rate, 1)
        })
        
    df_res = pd.DataFrame(analysis)
    
    print("\n" + "="*105)
    print("      📊 PRUEBA DE VOLUMEN INSTITUCIONAL: DIVERGENCIA DE VOLUMEN SV5 (XLK vs QQQ)")
    print("="*110)
    print(f"{'Régimen de Volumen S5V':<24s} | {'Obs':<6s} | {'V_Spread (XLK-QQQ)':<18s} | {'Fwd5d XLK':<10s} | {'Fwd5d QQQ':<10s} | {'Alpha XLK vs QQQ':<16s} | {'WinRate XLK'}")
    print("-" * 110)
    for _, r in df_res.iterrows():
        print(f"{r['vol_spread_regime']:<24s} | {r['obs']:<6d} | {r['avg_v_spread']:+17.1f}% | {r['avg_xlk_fwd5d']:+9.2f}% | {r['avg_qqq_fwd5d']:+9.2f}% | {r['avg_alpha_xlk_vs_qqq']:+15.2f}% | {r['xlk_win_rate']:9.1f}%")
    print("="*110)

if __name__ == "__main__":
    main()
