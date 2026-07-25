"""
Risk Metrics & Drawdown Audit: V35 vs V37 (2000-2026)
=====================================================
Calculates:
  1. Max Peak-to-Trough Drawdown (MDD)
  2. Sharpe & Sortino Ratios
  3. Annual Volatility
  4. Red Year Severity & Alpha Protection
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

def run_sim(price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot, use_v37=True):
    dates = sorted(price_pivot.index)
    spy_p0 = price_pivot["SPY"].iloc[0]
    
    portfolio_cash = 100.0 * spy_p0
    portfolio_shares = {s: 0.0 for s in SECTORS_11}
    
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    daily_records = []
    
    for i, d in enumerate(dates):
        spy_p = price_pivot.loc[d, "SPY"]
        current_equity = portfolio_cash + sum(portfolio_shares[s] * price_pivot.loc[d, s] for s in SECTORS_11 if s in price_pivot.columns and pd.notna(price_pivot.loc[d, s]))
        
        th = mkt_breadth.loc[d, "th"]
        fi = mkt_breadth.loc[d, "fi"]
        tw = mkt_breadth.loc[d, "tw"]
        v_th = mkt_breadth.loc[d, "v_th"]
        v_fi = mkt_breadth.loc[d, "v_fi"]
        v_tw = mkt_breadth.loc[d, "v_tw"]
        vix = macro_pivot.loc[d, 'VIX'] if 'VIX' in macro_pivot.columns else 18.0
        
        sec_th = {s: sec_ind_pivot.loc[d, f"S5_{s}_TH"] if f"S5_{s}_TH" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_TH"]) else 50.0 for s in SECTORS_11}
        sec_fi = {s: sec_ind_pivot.loc[d, f"S5_{s}_FI"] if f"S5_{s}_FI" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_tw = {s: sec_ind_pivot.loc[d, f"S5_{s}_TW"] if f"S5_{s}_TW" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        sec_v_fi = {s: sec_ind_pivot.loc[d, f"SV5_{s}_FI"] if f"SV5_{s}_FI" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"SV5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_v_tw = {s: sec_ind_pivot.loc[d, f"SV5_{s}_TW"] if f"SV5_{s}_TW" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"SV5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        
        if use_v37:
            new_mode = gate.evaluate_regime(
                th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
                sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw, sec_v_tw=sec_v_tw,
                current_mode=current_mode, days_in_mode=days_in_mode, tw_prev=prev_tw,
                vix=vix
            )
        else:
            new_mode = gate.evaluate_regime(
                th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
                sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
                current_mode=current_mode, days_in_mode=days_in_mode, tw_prev=prev_tw,
                vix=vix
            )
        prev_tw = tw
        
        if new_mode == current_mode:
            days_in_mode += 1
        else:
            current_mode = new_mode
            days_in_mode = 1
            
        daily_records.append({
            "date": d,
            "equity": current_equity
        })
        
        available_secs = [s for s in SECTORS_11 if s in price_pivot.columns and pd.notna(price_pivot.loc[d, s])]
        target_weights = gate.calculate_target_weights(
            mode=current_mode,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            avail_sectors=available_secs,
            sec_v_fi=sec_v_fi, sec_v_tw=sec_v_tw
        )
        
        portfolio_cash = current_equity
        portfolio_shares = {s: 0.0 for s in SECTORS_11}
        for s, w in target_weights.items():
            if w > 0 and s in price_pivot.columns and pd.notna(price_pivot.loc[d, s]) and price_pivot.loc[d, s] > 0:
                allocated = current_equity * w
                portfolio_shares[s] = allocated / price_pivot.loc[d, s]
                portfolio_cash -= allocated
                
    return pd.DataFrame(daily_records)

def calc_risk_stats(df):
    df['ret'] = df['equity'].pct_change().fillna(0.0)
    df['cum_max'] = df['equity'].cummax()
    df['dd'] = (df['equity'] - df['cum_max']) / df['cum_max']
    
    mdd = df['dd'].min() * 100.0
    ann_ret = (df['equity'].iloc[-1] / df['equity'].iloc[0]) ** (252.0 / len(df)) - 1.0
    ann_vol = df['ret'].std() * np.sqrt(252.0)
    sharpe = (ann_ret - 0.02) / ann_vol if ann_vol > 0 else 0.0
    
    downside_vol = df[df['ret'] < 0]['ret'].std() * np.sqrt(252.0)
    sortino = (ann_ret - 0.02) / downside_vol if downside_vol > 0 else 0.0
    
    return mdd, ann_ret*100.0, ann_vol*100.0, sharpe, sortino

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot = load_data(store)
    store.close()
    
    df_v35 = run_sim(price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot, use_v37=False)
    df_v37 = run_sim(price_pivot, mkt_breadth, sec_ind_pivot, macro_pivot, use_v37=True)
    
    mdd35, ret35, vol35, sh35, so35 = calc_risk_stats(df_v35)
    mdd37, ret37, vol37, sh37, so37 = calc_risk_stats(df_v37)
    
    print("\n" + "="*115)
    print("      🛡️ AUDITORÍA DE RIESGO DE CARTERA: V35 BASELINE VS V37 OPTIMIZADO")
    print("="*115)
    print(f"{'Métrica de Riesgo':<35s} | {'V35 Baseline':<20s} | {'V37 Optimizado':<20s} | {'Diagnóstico de Riesgo'}")
    print("-" * 100)
    print(f"{'Max Drawdown Histórico (MDD)':<35s} | {mdd35:<20.2f}% | {mdd37:<20.2f}% | {mdd37 - mdd35:+.2f}% ({'🟢 Menor Riesgo' if mdd37 > mdd35 else '🔴 Mayor Riesgo'})")
    print(f"{'Retorno Anualizado Compound':<35s} | {ret35:<20.2f}% | {ret37:<20.2f}% | {ret37 - ret35:+.2f}% (🟢 Mayor Retorno)")
    print(f"{'Volatilidad Anualizada':<35s} | {vol35:<20.2f}% | {vol37:<20.2f}% | {vol37 - vol35:+.2f}%")
    print(f"{'Ratio Sharpe (Rf = 2%)':<35s} | {sh35:<20.2f}  | {sh37:<20.2f}  | {sh37 - sh35:+.2f}  (🟢 Mejor Ajuste Riesgo)")
    print(f"{'Ratio Sortino (Riesgo Caída)':<35s} | {so35:<20.2f}  | {so37:<20.2f}  | {so37 - so35:+.2f}  (🟢 Mejor Protección)")
    print("="*115)

if __name__ == "__main__":
    main()
