"""
Lead-Lag Microstructural Analysis: XLK (Pure Tech) vs QQQ (Nasdaq 100)
====================================================================
Empirical Lead-Lag Study:
1. Does XLK lead QQQ at market tops and bottoms?
2. Does QQQ lead XLK?
3. S5_XLK vs S5_QQQ cross-correlation and lead/lag days.
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
    xlk = price_pivot["XLK"]
    qqq = price_pivot["QQQ"]
    
    s5_xlk = sec_ind_pivot.get("S5_XLK_FI", pd.Series(50.0, index=dates))
    s5_qqq = sec_ind_pivot.get("S5_QQQ_FI", pd.Series(50.0, index=dates))
    
    sv5_xlk = sec_ind_pivot.get("SV5_XLK_FI", pd.Series(50.0, index=dates))
    sv5_qqq = sec_ind_pivot.get("SV5_QQQ_FI", pd.Series(50.0, index=dates))
    
    df = pd.DataFrame({
        "XLK": xlk,
        "QQQ": qqq,
        "S5_XLK": s5_xlk,
        "S5_QQQ": s5_qqq,
        "SV5_XLK": sv5_xlk,
        "SV5_QQQ": sv5_qqq
    }, index=dates).dropna()
    
    # 1. Lead/Lag Cross Correlations
    # We test shifts of -5 to +5 days for XLK relative to QQQ
    corr_results = {}
    for lag in range(-5, 6):
        if lag < 0:
            c = df['S5_XLK'].shift(-lag).corr(df['S5_QQQ'])
        elif lag > 0:
            c = df['S5_XLK'].corr(df['S5_QQQ'].shift(lag))
        else:
            c = df['S5_XLK'].corr(df['S5_QQQ'])
        corr_results[lag] = round(c, 4)
        
    # 2. Turning Point Lead Analysis
    # Define local min/max (5-day rolling min/max)
    df['xlk_min'] = df['XLK'] == df['XLK'].rolling(11, center=True).min()
    df['qqq_min'] = df['QQQ'] == df['QQQ'].rolling(11, center=True).min()
    df['xlk_max'] = df['XLK'] == df['XLK'].rolling(11, center=True).max()
    df['qqq_max'] = df['QQQ'] == df['QQQ'].rolling(11, center=True).max()
    
    # Analyze lead/lag when SV5_XLK surges BEFORE SV5_QQQ
    df['sv5_diff'] = df['SV5_XLK'] - df['SV5_QQQ']
    df['xlk_leads_vol'] = df['sv5_diff'] > 15.0 # XLK volume breadth is 15% higher than QQQ
    df['qqq_leads_vol'] = df['sv5_diff'] < -15.0 # QQQ volume breadth is 15% higher than XLK
    
    xlk_lead_fwd5d_xlk = (df[df['xlk_leads_vol']]['XLK'].shift(-5) / df[df['xlk_leads_vol']]['XLK'] - 1.0).mean() * 100
    xlk_lead_fwd5d_qqq = (df[df['xlk_leads_vol']]['QQQ'].shift(-5) / df[df['xlk_leads_vol']]['QQQ'] - 1.0).mean() * 100
    
    qqq_lead_fwd5d_xlk = (df[df['qqq_leads_vol']]['XLK'].shift(-5) / df[df['qqq_leads_vol']]['XLK'] - 1.0).mean() * 100
    qqq_lead_fwd5d_qqq = (df[df['qqq_leads_vol']]['QQQ'].shift(-5) / df[df['qqq_leads_vol']]['QQQ'] - 1.0).mean() * 100
    
    print("\n" + "="*95)
    print("      ⏱️ ESTUDIO EMPÍRICO DE ADELANTO Y RETRASO (LEAD / LAG): XLK vs QQQ")
    print("="*95)
    print(f"Días de Adelanto de XLK sobre QQQ cuando SV5_XLK > SV5_QQQ + 15%: {df['xlk_leads_vol'].sum()} Días")
    print(f"  -> Retorno Promedio 5d Posterior de XLK cuando XLK se adelanta : {xlk_lead_fwd5d_xlk:+.2f}%")
    print(f"  -> Retorno Promedio 5d Posterior de QQQ cuando XLK se adelanta : {xlk_lead_fwd5d_qqq:+.2f}%")
    print(f"  -> VENTAJA DE ADELANTO DE XLK sobre QQQ                        : {xlk_lead_fwd5d_xlk - xlk_lead_fwd5d_qqq:+.2f}%")
    print("-" * 95)
    print(f"Días de Adelanto de QQQ sobre XLK cuando SV5_QQQ > SV5_XLK + 15%: {df['qqq_leads_vol'].sum()} Días")
    print(f"  -> Retorno Promedio 5d Posterior de XLK cuando QQQ se adelanta : {qqq_lead_fwd5d_xlk:+.2f}%")
    print(f"  -> Retorno Promedio 5d Posterior de QQQ cuando QQQ se adelanta : {qqq_lead_fwd5d_qqq:+.2f}%")
    print(f"  -> VENTAJA DE ADELANTO DE QQQ sobre XLK                        : {qqq_lead_fwd5d_qqq - qqq_lead_fwd5d_xlk:+.2f}%")
    print("="*95)

if __name__ == "__main__":
    main()
