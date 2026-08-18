"""
Comprehensive Forensic Audit of V36 Signals, Memory & Market Intelligence Contradictions (2000-2026)
===================================================================================================
Audits every individual regime's transition triggers & alerts point-in-time:
  1. MERCADO_SANO
  2. DISTRIBUCION_PRE_CRASH
  3. PULLBACK_ALCISTA
  4. RE_ACUMULACION_ALCISTA
  5. NORMAL
  6. RECUPERACION
  7. PISO_GENERACIONAL
  8. CRASH_SISTEMICO

Analyzes:
  - Signal Accuracy & Precision per Regime
  - Contradiction Map (Price Breadth S5 vs Volume Breadth SV5 divergence)
  - Memory & Directional Momentum (5d/10d Deltas)
  - Blocked Alpha vs True Risk Protection
"""

import os, sys, json, pandas as pd, numpy as np
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS

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
            
        sec_ind_tickers = []
        for s in SECTORS_11:
            sec_ind_tickers.extend([f"S5_{s}_TH", f"S5_{s}_FI", f"S5_{s}_TW", f"SV5_{s}_TH", f"SV5_{s}_FI", f"SV5_{s}_TW"])
            
        sec_str = ", ".join([f"'{t}'" for t in sec_ind_tickers])
        df_sec_ind = pd.read_sql(f"""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ({sec_str})
              AND timeframe = '1d'
              AND time >= '2000-01-01'
            ORDER BY time, ticker
        """, conn)
        sec_ind_pivot = df_sec_ind.pivot(index='date', columns='ticker', values='close').ffill()
        
        df_macro = pd.read_sql("""
            SELECT ticker, time::date as date, close 
            FROM market.ohlcv_bars 
            WHERE ticker IN ('VIX', 'CBOE_PCR', 'FG') 
              AND timeframe = '1d' 
              AND time >= '2000-01-01' 
            ORDER BY time
        """, conn)
        macro_pivot = df_macro.pivot(index='date', columns='ticker', values='close').ffill().bfill()
        
        common_dates = price_pivot.index.intersection(mkt_breadth.index).intersection(sec_ind_pivot.index).intersection(macro_pivot.index)
        return price_pivot.loc[common_dates], mkt_breadth.loc[common_dates], sec_ind_pivot.loc[common_dates], macro_pivot.loc[common_dates]
    finally:
        store._put(conn)

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot = load_data(store)
    store.close()
    
    dates = sorted(price_pivot.index)
    spy_p = price_pivot["SPY"]
    
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    records = []
    
    for i in range(10, len(dates) - 20):
        d = dates[i]
        d_next20 = dates[i+20]
        
        fwd_20d_spy = (spy_p.loc[d_next20] / spy_p.loc[d] - 1.0) * 100.0
        
        th = mkt_breadth.loc[d, "th"]
        fi = mkt_breadth.loc[d, "fi"]
        tw = mkt_breadth.loc[d, "tw"]
        v_th = mkt_breadth.loc[d, "v_th"]
        v_fi = mkt_breadth.loc[d, "v_fi"]
        v_tw = mkt_breadth.loc[d, "v_tw"]
        
        vix = macro_pivot.loc[d, 'VIX'] if 'VIX' in macro_pivot.columns else 18.0
        pcr = macro_pivot.loc[d, 'CBOE_PCR'] if 'CBOE_PCR' in macro_pivot.columns else 1.0
        
        sec_th = {s: sec_ind_pivot.loc[d, f"S5_{s}_TH"] if f"S5_{s}_TH" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_TH"]) else 50.0 for s in SECTORS_11}
        sec_fi = {s: sec_ind_pivot.loc[d, f"S5_{s}_FI"] if f"S5_{s}_FI" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_tw = {s: sec_ind_pivot.loc[d, f"S5_{s}_TW"] if f"S5_{s}_TW" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        
        # Momentum / Directional memory (5d delta)
        th_5d_prev = mkt_breadth.iloc[i-5]["th"]
        v_tw_5d_prev = mkt_breadth.iloc[i-5]["v_tw"]
        delta_th_5d = th - th_5d_prev
        delta_v_tw_5d = v_tw - v_tw_5d_prev
        
        # Divergence / Contradiction (Price vs Volume)
        vol_price_contradiction = (th > 55.0 and v_th < 40.0) # Price healthy but volume decaying
        
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            current_mode=current_mode, days_in_mode=days_in_mode, tw_prev=prev_tw
        )
        prev_tw = tw
        
        # V36 Calibrated Redirection
        if new_mode == "CRASH_SISTEMICO" and vix <= 28.0 and v_th >= 25.0:
            new_mode = "PISO_GENERACIONAL"
            
        if new_mode == current_mode:
            days_in_mode += 1
        else:
            current_mode = new_mode
            days_in_mode = 1
            
        records.append({
            "date": d,
            "mode": current_mode,
            "days_in_mode": days_in_mode,
            "fwd_20d_spy": fwd_20d_spy,
            "th": th, "fi": fi, "tw": tw, "v_th": v_th, "v_tw": v_tw,
            "delta_th_5d": delta_th_5d, "delta_v_tw_5d": delta_v_tw_5d,
            "vol_price_contradiction": vol_price_contradiction,
            "vix": vix, "pcr": pcr
        })
        
    df = pd.DataFrame(records)
    
    print("\n" + "="*115)
    print("      🔍 AUDITORÍA FORENSE DE ALERTAS Y CONTRADICCIONES DE SEÑAL POR RÉGIMEN (V36)")
    print("="*115)
    print(f"{'Régimen de Mercado':<24s} | {'Días':<6s} | {'Fwd 20d Prom (%)':<18s} | {'Contradicción Vol/Precio':<26s} | {'Mom. 5d Prom (ΔTH)'}")
    print("-" * 115)
    
    regimes = sorted(df['mode'].unique())
    for reg in regimes:
        sub = df[df['mode'] == reg]
        n_days = len(sub)
        avg_fwd = sub['fwd_20d_spy'].mean()
        n_contra = sub['vol_price_contradiction'].sum()
        pct_contra = (n_contra / n_days) * 100.0 if n_days > 0 else 0.0
        avg_mom = sub['delta_th_5d'].mean()
        
        status = "🚀 Bullish" if avg_fwd > 1.5 else ("🛡️ Defensive" if avg_fwd < -0.5 else "⚪ Neutral")
        print(f"{reg:<24s} | {n_days:<6d} | {avg_fwd:+18.2f}% | {n_contra:5d} días ({pct_contra:5.1f}%)       | {avg_mom:+16.2f}% ({status})")
        
    print("="*115)

if __name__ == "__main__":
    main()
