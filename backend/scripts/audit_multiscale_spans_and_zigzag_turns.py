"""
Audit of Multiscale Spans (5d, 20d, 50d, 200d) and Zigzag Turning Point Alignment
==================================================================================
Audits the exact multiscale sequence of turning points:
  1. Ultra-tactical 5d momentum inflection (S5_5d / 5-day delta)
  2. Tactical 20d TW turning point
  3. Intermediate 50d FI crossover
  4. Structural 200d TH expansion

Evaluates forward 20d, 60d, and 90d returns when multiscale alignment occurs at floors (TH < 25%).
"""

import os, sys, json, pandas as pd, numpy as np
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.triad_lookup import lookup_triad_signal

SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]
BREADTH_MAP = {
    "S5TH": "th", "S5FI": "fi", "S5TW": "tw",
    "SV5TH": "v_th", "SV5FI": "v_fi", "SV5TW": "v_tw"
}

def load_data(store):
    conn = store._conn()
    try:
        all_tickers = ["SPY"] + SECTORS_11
        p_str = ", ".join([f"'{t}'" for t in all_tickers])
        
        df_p = pd.read_sql(f"""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ({p_str})
              AND timeframe = '1d'
              AND time >= '2000-01-01'
            ORDER BY time, ticker
        """, conn)
        price_pivot = df_p.pivot(index='date', columns='ticker', values='close').ffill()
        
        mkt_ind = list(BREADTH_MAP.keys())
        mkt_str = ", ".join([f"'{t}'" for t in mkt_ind])
        df_mkt = pd.read_sql(f"""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ({mkt_str})
              AND timeframe = '1d'
              AND time >= '2000-01-01'
            ORDER BY time, ticker
        """, conn)
        mkt_pivot = df_mkt.pivot(index='date', columns='ticker', values='close').ffill()
        
        mkt_breadth = pd.DataFrame(index=mkt_pivot.index)
        for k, v in BREADTH_MAP.items():
            mkt_breadth[v] = mkt_pivot[k]
            
        common_dates = price_pivot.index.intersection(mkt_breadth.index)
        return price_pivot.loc[common_dates], mkt_breadth.loc[common_dates]
    finally:
        store._put(conn)

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth = load_data(store)
    store.close()
    
    dates = sorted(price_pivot.index)
    df = pd.DataFrame(index=dates)
    df['spy_price'] = price_pivot['SPY']
    df['fwd_20d_ret'] = (df['spy_price'].shift(-20) / df['spy_price'] - 1.0) * 100.0
    df['fwd_60d_ret'] = (df['spy_price'].shift(-60) / df['spy_price'] - 1.0) * 100.0
    
    for k in BREADTH_MAP.values():
        df[k] = mkt_breadth[k]
        
    # Multiscale Spans
    # 5d (Ultra-tactical 5-day delta of TW)
    df['delta_tw_5d'] = df['tw'].diff(5)
    # 20d (Tactical TW level)
    # 50d (Intermediate FI level)
    # 200d (Structural TH level)
    
    # Multiscale Sequence 1: 5d Ultra-Tactical Turning Point at Structural Floor
    # Condition: Structural Floor (TH < 25%) AND 5-day TW momentum turns up (+10pp)
    df['floor_5d_turn'] = (df['th'] < 25.0) & (df['delta_tw_5d'] >= 10.0)
    
    # Multiscale Sequence 2: 20d Crossover 50d (TW crosses FI up) at Floor
    df['floor_tw_cross_fi'] = (df['th'] < 30.0) & (df['tw'] > df['fi']) & (df['tw'].shift(1) <= df['fi'].shift(1))
    
    # Multiscale Sequence 3: Full Multiscale Convergence (5d, 20d, 50d, 200d aligned up)
    df['full_multiscale_bull'] = (df['delta_tw_5d'] > 0) & (df['tw'] > df['fi']) & (df['fi'] > df['th'])
    
    print("\n" + "="*115)
    print("      🔍 AUDITORÍA DE MULTIESCALA DE BREADTH: 5d, 20d (TW), 50d (FI) Y 200d (TH)")
    print("="*115)
    
    # 1. 5d Ultra-tactical turn at floor
    sub1 = df[df['floor_5d_turn'] == True]
    print(f"1. Giro Ultra-Táctico de 5d en Suelo Estructural (TH < 25% + ΔTW_5d >= +10pp) : {len(sub1)} días")
    print(f"   • Retorno SPY Fwd 20d Promedio : {sub1['fwd_20d_ret'].mean():+.2f}% (Win Rate: {(sub1['fwd_20d_ret'] > 0).mean()*100:.1f}%)")
    print(f"   • Retorno SPY Fwd 60d Promedio : {sub1['fwd_60d_ret'].mean():+.2f}% (Win Rate: {(sub1['fwd_60d_ret'] > 0).mean()*100:.1f}%) 💥")
    
    # 2. 20d Crossover 50d at floor
    sub2 = df[df['floor_tw_cross_fi'] == True]
    print(f"\n2. Cruce Táctico 20d/50d en Suelo (TH < 30% + TW cruza sobre FI)               : {len(sub2)} días")
    print(f"   • Retorno SPY Fwd 20d Promedio : {sub2['fwd_20d_ret'].mean():+.2f}% (Win Rate: {(sub2['fwd_20d_ret'] > 0).mean()*100:.1f}%)")
    print(f"   • Retorno SPY Fwd 60d Promedio : {sub2['fwd_60d_ret'].mean():+.2f}% (Win Rate: {(sub2['fwd_60d_ret'] > 0).mean()*100:.1f}%)")
    
    # 3. Full multiscale alignment (5d, 20d, 50d, 200d)
    sub3 = df[df['full_multiscale_bull'] == True]
    print(f"\n3. Alineación Multiescala Alcista Completa (5d > 0 + 20d > 50d > 200d)         : {len(sub3)} días")
    print(f"   • Retorno SPY Fwd 20d Promedio : {sub3['fwd_20d_ret'].mean():+.2f}% (Win Rate: {(sub3['fwd_20d_ret'] > 0).mean()*100:.1f}%)")
    print(f"   • Retorno SPY Fwd 60d Promedio : {sub3['fwd_60d_ret'].mean():+.2f}% (Win Rate: {(sub3['fwd_60d_ret'] > 0).mean()*100:.1f}%)")
    
    print("="*115)

if __name__ == "__main__":
    main()
