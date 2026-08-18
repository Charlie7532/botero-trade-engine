"""
Audit of Breadth Gaps & Multi-Stock Moving Average Breakdowns (2000-2026)
========================================================================
Measures:
  1. 1-day, 3-day, and 5-day sudden drops (gaps) in S5_TW (20d SMA), S5_FI (50d SMA), S5_TH (200d SMA).
  2. Coincidence with SV5_TW (Volume-weighted 20d SMA) to distinguish false panic vs institutional selling.
  3. Gate reaction during extreme gap events (e.g. >15% of S&P 500 breaking 20d SMA in 1-3 days).
"""

import os, sys, json, pandas as pd, numpy as np
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate

SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]
BREADTH_MAP = {
    "S5TH": "th", "S5FI": "fi", "S5TW": "tw",
    "SV5TH": "v_th", "SV5FI": "v_fi", "SV5TW": "v_tw"
}

def load_data(store):
    conn = store._conn()
    try:
        all_tickers = ["SPY"] + list(BREADTH_MAP.keys())
        p_str = ", ".join([f"'{t}'" for t in all_tickers])
        
        df = pd.read_sql(f"""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ({p_str})
              AND timeframe = '1d'
              AND time >= '2000-01-01'
            ORDER BY time, ticker
        """, conn)
        pivot = df.pivot(index='date', columns='ticker', values='close').ffill()
        
        breadth = pd.DataFrame(index=pivot.index)
        for k, v in BREADTH_MAP.items():
            breadth[v] = pivot[k]
        breadth['spy'] = pivot['SPY']
        return breadth
    finally:
        store._put(conn)

def main():
    store = TimescaleDataStore()
    df = load_data(store)
    store.close()
    
    # Calculate 1-day, 3-day, and 5-day deltas (gaps)
    df['tw_diff1'] = df['tw'].diff(1)
    df['tw_diff3'] = df['tw'].diff(3)
    df['tw_diff5'] = df['tw'].diff(5)
    
    df['fi_diff1'] = df['fi'].diff(1)
    df['fi_diff3'] = df['fi'].diff(3)
    df['fi_diff5'] = df['fi'].diff(5)
    
    df['th_diff1'] = df['th'].diff(1)
    df['th_diff3'] = df['th'].diff(3)
    df['th_diff5'] = df['th'].diff(5)
    
    # Volume-weighted gap difference (divergence between price-breadth and volume-breadth drop)
    df['tw_vol_divergence'] = df['v_tw'] - df['tw']
    
    print("\n" + "="*115)
    print("      🔬 AUDITORÍA DE GAPS Y RUPTURAS MULTI-ACCIÓN EN S5 Y SV5 (2000 - 2026)")
    print("="*115)
    
    # Analyze Extreme 1-Day Gaps (>= 10% of S&P 500 breaking 20-day SMA in 1 day)
    severe_gaps = df[df['tw_diff1'] <= -10.0].copy()
    print(f"\n1. DÍAS DE GAP SEVERO (>= 10% de acciones rompen MA20 en 1 solo día): {len(severe_gaps)} eventos")
    print(f"{'Fecha':<11s} | {'Caída 1d S5_TW':<16s} | {'S5_TW':<8s} | {'S5_FI':<8s} | {'S5_TH':<8s} | {'SV5_TW':<8s} | {'Divergencia Vol'}")
    print("-" * 105)
    for _, r in severe_gaps.head(15).iterrows():
        div_str = "🟢 Compra Institucional" if r['tw_vol_divergence'] > 5.0 else "🔴 Venta Institucional"
        print(f"{str(r.name):<11s} | {r['tw_diff1']:+15.2f}% | {r['tw']:7.1f}% | {r['fi']:7.1f}% | {r['th']:7.1f}% | {r['v_tw']:7.1f}% | {r['tw_vol_divergence']:+6.1f}% ({div_str})")
        
    # Analyze 3-Day Cascades (>= 20% of S&P 500 breaking 20-day SMA in 3 days)
    severe_cascades = df[df['tw_diff3'] <= -20.0].copy()
    print(f"\n2. CASCADAS RÁPIDAS (>= 20% de acciones rompen MA20 en 3 días): {len(severe_cascades)} eventos")
    print(f"Caída promedio en 3d: {severe_cascades['tw_diff3'].mean():.2f}%")
    print(f"Divergencia de volumen promedio (SV5_TW - S5_TW): {severe_cascades['tw_vol_divergence'].mean():+.2f}%")
    
    # Check 5-day forward return of SPY following 1-day severe gaps
    fwd_returns = []
    for idx in severe_gaps.index:
        loc = df.index.get_loc(idx)
        if loc + 5 < len(df):
            fwd_ret = ((df.iloc[loc+5]['spy'] / df.iloc[loc]['spy']) - 1.0) * 100.0
            fwd_returns.append(fwd_ret)
            
    avg_fwd_5d = np.mean(fwd_returns) if fwd_returns else 0.0
    win_rate_5d = (np.array(fwd_returns) > 0).mean() * 100.0 if fwd_returns else 0.0
    
    print("\n" + "="*115)
    print(f"      📊 COMPORTAMIENTO POST-GAP DE 1 DÍA (ROPTURA MASIVA DE MEDIAS MÓVILES)")
    print("="*115)
    print(f"Retorno Promedio del SPY a 5 días post-gap  : {avg_fwd_5d:+.2f}%")
    print(f"Probabilidad de Rebote a 5 días (Win Rate)  : {win_rate_5d:.1f}%")
    print("="*115)

if __name__ == "__main__":
    main()
