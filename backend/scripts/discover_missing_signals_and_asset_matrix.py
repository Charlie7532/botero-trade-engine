"""
Discover Missing Signals & Dynamic Asset Choice Matrix by Regime (1999-2026)
=============================================================================
Quantitative Research Pipeline to uncover:
1. Optimal Asset Choice (SPY vs QQQ vs CASH) in each of the 10 Regimes.
2. Impact of 3 Orthogonal Signals:
   - Signal A: CBOE Put/Call Ratio (Institutional Hedging Panic)
   - Signal B: VIX Volatility Regime (Low Vol vs High Vol)
   - Signal C: Sector Rotation Divergence (Tech XLK vs Financials XLF Breadth)
"""

import os, sys, json, pandas as pd, numpy as np
import psycopg2
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
from backend.scripts._lib.backtest_qqq_integrated_gate import load_data, SECTORS_11

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot = load_data(store, start_date="1999-01-01")
    
    dates = price_pivot.index
    gate = QualityEntryGate()
    
    # Load VIX and CBOE_PCR from database if available
    conn = psycopg2.connect(os.getenv('POSTGRES_URL'))
    cur = conn.cursor()
    
    def load_indicator(ticker):
        cur.execute("SELECT time::date, close FROM market.ohlcv_bars WHERE ticker = %s AND timeframe = '1d' ORDER BY time", (ticker,))
        rows = cur.fetchall()
        if not rows: return pd.Series(dtype=float)
        df = pd.DataFrame(rows, columns=['date', 'close']).set_index('date')
        df.index = pd.to_datetime(df.index)
        return df['close']
        
    vix_series = load_indicator("VIX")
    pcr_series = load_indicator("CBOE_PCR")
    
    # Evaluate Regime for every single day
    current_mode = "NORMAL"
    days_in_mode = 0
    records = []
    
    for i in range(25, len(dates) - 1):
        dt = dates[i]
        dt_next = dates[i+1]
        
        spy_close = price_pivot['SPY'].loc[dt]
        spy_next_ret = (price_pivot['SPY'].loc[dt_next] / spy_close - 1.0) * 100.0
        qqq_next_ret = (price_pivot['QQQ'].loc[dt_next] / price_pivot['QQQ'].loc[dt] - 1.0) * 100.0
        
        th = mkt_breadth["th"].loc[dt] if dt in mkt_breadth.index else 50.0
        fi = mkt_breadth["fi"].loc[dt] if dt in mkt_breadth.index else 50.0
        tw = mkt_breadth["tw"].loc[dt] if dt in mkt_breadth.index else 50.0
        v_th = mkt_breadth["v_th"].loc[dt] if dt in mkt_breadth.index else 50.0
        v_fi = mkt_breadth["v_fi"].loc[dt] if dt in mkt_breadth.index else 50.0
        v_tw = mkt_breadth["v_tw"].loc[dt] if dt in mkt_breadth.index else 50.0
        
        sec_th = {s: sec_ind_pivot.get(f"S5_{s}_TH", pd.Series(50.0, index=dates)).loc[dt] for s in SECTORS_11 + ["QQQ"]}
        sec_fi = {s: sec_ind_pivot.get(f"S5_{s}_FI", pd.Series(50.0, index=dates)).loc[dt] for s in SECTORS_11 + ["QQQ"]}
        sec_tw = {s: sec_ind_pivot.get(f"S5_{s}_TW", pd.Series(50.0, index=dates)).loc[dt] for s in SECTORS_11 + ["QQQ"]}
        
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            current_mode=current_mode, days_in_mode=days_in_mode
        )
        if new_mode == current_mode:
            days_in_mode += 1
        else:
            current_mode = new_mode
            days_in_mode = 1
            
        vix_val = vix_series.loc[dt] if dt in vix_series.index else 20.0
        pcr_val = pcr_series.loc[dt] if dt in pcr_series.index else 0.85
        
        xlk_fi = sec_fi.get("XLK", 50.0)
        xlf_fi = sec_fi.get("XLF", 50.0)
        rotation_divergence = xlf_fi - xlk_fi # Positive when Financials lead Tech
        
        records.append({
            "date": dt,
            "regime": current_mode,
            "spy_next_ret": spy_next_ret,
            "qqq_next_ret": qqq_next_ret,
            "vix": vix_val,
            "pcr": pcr_val,
            "xlk_fi": xlk_fi,
            "xlf_fi": xlf_fi,
            "rot_div": rotation_divergence
        })
        
    df_rec = pd.DataFrame(records)
    
    # Analyze Best Asset Choice Per Regime
    reg_analysis = []
    for r in df_rec['regime'].unique():
        sub = df_rec[df_rec['regime'] == r]
        n_days = len(sub)
        
        spy_cum = (1 + sub['spy_next_ret'] / 100.0).prod() - 1.0
        qqq_cum = (1 + sub['qqq_next_ret'] / 100.0).prod() - 1.0
        cash_cum = 0.0
        
        # Best Asset
        best_asset = "QQQ" if qqq_cum > spy_cum and qqq_cum > 0 else ("SPY" if spy_cum > 0 else "CASH")
        
        reg_analysis.append({
            "regime": r,
            "days": n_days,
            "pct_time": round(n_days / len(df_rec) * 100, 1),
            "spy_cum": round(spy_cum * 100, 1),
            "qqq_cum": round(qqq_cum * 100, 1),
            "best_asset": best_asset,
            "avg_vix": round(sub['vix'].mean(), 1),
            "avg_pcr": round(sub['pcr'].mean(), 2),
            "avg_rot_div": round(sub['rot_div'].mean(), 1)
        })
        
    df_reg_out = pd.DataFrame(reg_analysis).sort_values("days", ascending=False)
    
    print("\n" + "="*110)
    print("      🔍 MATRIZ DE SELECCIÓN ÓPTIMA DE ACTIVO (SPY vs QQQ vs CASH) Y SEÑALES FALTANTES POR RÉGIMEN")
    print("="*110)
    print(f"{'Régimen':<26s} | {'Días':<5s} | {'Ret SPY':<9s} | {'Ret QQQ':<9s} | {'Mejor Activo':<12s} | {'VIX Prom':<9s} | {'Rot Div (XLF-XLK)':<18s}")
    print("-" * 110)
    for _, r in df_reg_out.iterrows():
        print(f"{r['regime']:<26s} | {r['days']:<5d} | {r['spy_cum']:+8.1f}% | {r['qqq_cum']:+8.1f}% | {r['best_asset']:<12s} | {r['avg_vix']:8.1f} | {r['avg_rot_div']:+16.1f}%")
    print("="*110)

if __name__ == "__main__":
    main()
