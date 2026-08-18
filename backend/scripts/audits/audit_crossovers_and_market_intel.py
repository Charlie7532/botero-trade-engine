"""
Quantitative Audit of Breadth Crossovers and Market Intelligence Indicators (2000-2026)
========================================================================================
Audits lead-lag breadth relationships (S5_TW vs S5_FI vs S5_TH crossovers) and
multi-vector market intelligence (VIX, PCR, F&G, Credit stress, Yield Curve).
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
            
        df_macro = pd.read_sql("""
            SELECT ticker, time::date as date, close 
            FROM market.ohlcv_bars 
            WHERE ticker IN ('VIX', 'CBOE_PCR', 'FG') 
              AND timeframe = '1d' 
              AND time >= '2000-01-01' 
            ORDER BY time
        """, conn)
        macro_pivot = df_macro.pivot(index='date', columns='ticker', values='close').ffill().bfill()
        
        common_dates = price_pivot.index.intersection(mkt_breadth.index).intersection(macro_pivot.index)
        return price_pivot.loc[common_dates], mkt_breadth.loc[common_dates], macro_pivot.loc[common_dates]
    finally:
        store._put(conn)

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, macro_pivot = load_data(store)
    store.close()
    
    dates = sorted(price_pivot.index)
    df = pd.DataFrame(index=dates)
    df['spy_price'] = price_pivot['SPY']
    df['fwd_20d_ret'] = (df['spy_price'].shift(-20) / df['spy_price'] - 1.0) * 100.0
    
    for k in BREADTH_MAP.values():
        df[k] = mkt_breadth[k]
        
    df['vix'] = macro_pivot['VIX'] if 'VIX' in macro_pivot.columns else 18.0
    df['pcr'] = macro_pivot['CBOE_PCR'] if 'CBOE_PCR' in macro_pivot.columns else 1.0
    df['fg'] = macro_pivot['FG'] if 'FG' in macro_pivot.columns else 50.0
    
    # Lead-lag spreads
    df['spread_tw_fi'] = df['tw'] - df['fi']
    df['spread_fi_th'] = df['fi'] - df['th']
    
    # Directional momentum
    df['tw_diff_5d'] = df['tw'].diff(5)
    df['fi_diff_5d'] = df['fi'].diff(5)
    df['th_diff_5d'] = df['th'].diff(5)
    
    # Crossovers
    df['tw_cross_fi_up'] = (df['spread_tw_fi'] > 0) & (df['spread_tw_fi'].shift(1) <= 0)
    df['tw_cross_fi_down'] = (df['spread_tw_fi'] < 0) & (df['spread_tw_fi'].shift(1) >= 0)
    
    # Audit outcomes
    print("\n" + "="*115)
    print("      📈 AUDITORÍA CUANTITATIVA: CRUCES DE BREADTH Y SEÑALES MULTIVECTORIALES (2000-2026)")
    print("="*115)
    
    # 1. Bearish warning crossover (tw cross fi down)
    sub_down = df[df['tw_cross_fi_down'] == True]
    print(f"Cruces de Advertencia Bajista (S5_TW cruza bajo S5_FI) : {len(sub_down)} eventos")
    print(f"  • Retorno SPY promedio fwd 20d                         : {sub_down['fwd_20d_ret'].mean():+.2f}%")
    print(f"  • Win Rate Alcista (% días fwd 20d > 0)                : {(sub_down['fwd_20d_ret'] > 0).mean()*100:.1f}%")
    
    # 2. Bullish momentum crossover (tw cross fi up)
    sub_up = df[df['tw_cross_fi_up'] == True]
    print(f"\nCruces de Recuperación Alcista (S5_TW cruza sobre S5_FI) : {len(sub_up)} eventos")
    print(f"  • Retorno SPY promedio fwd 20d                         : {sub_up['fwd_20d_ret'].mean():+.2f}%")
    print(f"  • Win Rate Alcista (% días fwd 20d > 0)                : {(sub_up['fwd_20d_ret'] > 0).mean()*100:.1f}%")
    
    # 3. Market Intelligence Complacency Warning (F&G > 60 + VIX < 15 + PCR < 0.85)
    sub_comp = df[(df['fg'] > 60) & (df['vix'] < 15) & (df['pcr'] < 0.85)]
    print(f"\nSeñales de Complacencia Extrema (F&G > 60 + VIX < 15 + PCR < 0.85): {len(sub_comp)} días")
    print(f"  • Retorno SPY promedio fwd 20d                         : {sub_comp['fwd_20d_ret'].mean():+.2f}%")
    print(f"  • Win Rate Alcista (% días fwd 20d > 0)                : {(sub_comp['fwd_20d_ret'] > 0).mean()*100:.1f}%")
    
    # 4. Market Intelligence Capitulation (F&G < 20 + VIX > 25)
    sub_cap = df[(df['fg'] < 20) & (df['vix'] > 25)]
    print(f"\nSeñales de Capitulación e Inclemencia (F&G < 20 + VIX > 25)      : {len(sub_cap)} días")
    print(f"  • Retorno SPY promedio fwd 20d                         : {sub_cap['fwd_20d_ret'].mean():+.2f}%")
    print(f"  • Win Rate Alcista (% días fwd 20d > 0)                : {(sub_cap['fwd_20d_ret'] > 0).mean()*100:.1f}%")
    
    print("="*115)

if __name__ == "__main__":
    main()
