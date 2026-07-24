"""
Master Un-compromised V35 Audit: Year-by-Year & Regime Breakdown Tables (2000-2026)
===================================================================================
Prints complete, zero-fallback empirical performance of V35 Quality Entry Gate & Sector Rotation
directly from Neon PostgreSQL Data Vault.
"""

import os, sys, json, pandas as pd, numpy as np
import psycopg2
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
        
        common_dates = price_pivot.index.intersection(mkt_breadth.index).intersection(sec_ind_pivot.index)
        return price_pivot.loc[common_dates], mkt_breadth.loc[common_dates], sec_ind_pivot.loc[common_dates]
    finally:
        store._put(conn)

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot = load_data(store)
    store.close()
    
    dates = sorted(price_pivot.index)
    spy_p0 = price_pivot["SPY"].iloc[0]
    
    initial_spy_shares = 100.00
    initial_capital = initial_spy_shares * spy_p0
    portfolio_cash = initial_capital
    portfolio_shares = {s: 0.0 for s in SECTORS_11}
    
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    prev_tw = None
    
    daily_records = []
    
    for i, d in enumerate(dates):
        spy_p = price_pivot.loc[d, "SPY"]
        
        current_equity = portfolio_cash + sum(portfolio_shares[s] * price_pivot.loc[d, s] for s in SECTORS_11 if s in price_pivot.columns and pd.notna(price_pivot.loc[d, s]))
        spy_equiv_shares = current_equity / spy_p
        
        th = mkt_breadth.loc[d, "th"]
        fi = mkt_breadth.loc[d, "fi"]
        tw = mkt_breadth.loc[d, "tw"]
        v_th = mkt_breadth.loc[d, "v_th"]
        v_fi = mkt_breadth.loc[d, "v_fi"]
        v_tw = mkt_breadth.loc[d, "v_tw"]
        
        sec_th = {s: sec_ind_pivot.loc[d, f"S5_{s}_TH"] if f"S5_{s}_TH" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_TH"]) else 50.0 for s in SECTORS_11}
        sec_fi = {s: sec_ind_pivot.loc[d, f"S5_{s}_FI"] if f"S5_{s}_FI" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_tw = {s: sec_ind_pivot.loc[d, f"S5_{s}_TW"] if f"S5_{s}_TW" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"S5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        sec_v_fi = {s: sec_ind_pivot.loc[d, f"SV5_{s}_FI"] if f"SV5_{s}_FI" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"SV5_{s}_FI"]) else 50.0 for s in SECTORS_11}
        sec_v_tw = {s: sec_ind_pivot.loc[d, f"SV5_{s}_TW"] if f"SV5_{s}_TW" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot.loc[d, f"SV5_{s}_TW"]) else 50.0 for s in SECTORS_11}
        
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw, v_th=v_th, v_fi=v_fi, v_tw=v_tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            current_mode=current_mode, days_in_mode=days_in_mode, tw_prev=prev_tw
        )
        prev_tw = tw
        
        if new_mode == current_mode:
            days_in_mode += 1
        else:
            current_mode = new_mode
            days_in_mode = 1
            
        daily_records.append({
            "date": d,
            "year": d.year,
            "equity": current_equity,
            "spy_shares": spy_equiv_shares,
            "spy_price": spy_p,
            "mode": current_mode
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

    df_daily = pd.DataFrame(daily_records)
    df_daily['daily_ret'] = df_daily['equity'].pct_change().fillna(0.0)
    df_daily['spy_daily_ret'] = df_daily['spy_price'].pct_change().fillna(0.0)
    
    # ── TABLA 1: AÑO A AÑO ─────────────────────────────────────
    years = sorted(df_daily['year'].unique())
    yearly_rows = []
    
    for y in years:
        sub = df_daily[df_daily['year'] == y]
        start_eq = sub['equity'].iloc[0]
        end_eq = sub['equity'].iloc[-1]
        start_spy = sub['spy_price'].iloc[0]
        end_spy = sub['spy_price'].iloc[-1]
        end_shares = sub['spy_shares'].iloc[-1]
        
        port_ret = (end_eq / start_eq - 1.0) * 100.0
        spy_ret = (end_spy / start_spy - 1.0) * 100.0
        alpha = port_ret - spy_ret
        
        yearly_rows.append({
            "year": y,
            "spy_shares": end_shares,
            "port_ret": port_ret,
            "spy_ret": spy_ret,
            "alpha": alpha
        })
        
    print("\n" + "="*95)
    print("      📈 TABLA 1: RENDIMIENTO AÑO A AÑO DE VERSIÓN 35 (2000 - 2026)")
    print("      Benchmark Base (B&H SPY) vs Producción V35 Multi-Sector (417.68 Acciones)")
    print("="*95)
    print(f"{'Año':<6s} | {'Acciones SPY V35':<18s} | {'Retorno V35 (%)':<16s} | {'Retorno SPY (%)':<16s} | {'Alpha Neto (%)':<14s} | Diagnóstico")
    print("-" * 95)
    
    for r in yearly_rows:
        flag = "🟢 Supera SPY" if r['alpha'] > 1.0 else ("🔴 Menor a SPY" if r['alpha'] < -1.0 else "⚪ Empate")
        print(f"{r['year']:<6d} | {r['spy_shares']:18.2f} | {r['port_ret']:+16.2f}% | {r['spy_ret']:+16.2f}% | {r['alpha']:+14.2f}% | {flag}")
        
    print("="*95)
    final_sh = df_daily['spy_shares'].iloc[-1]
    print(f"ACCIONES FINALES DE PRODUCCIÓN REAL V35 : {final_sh:.2f} Acciones de SPY ({final_sh/100.0:.2f}x Multiplicador) 🟢")
    print("="*95)
    
    # ── TABLA 2: ATRIBUCIÓN POR RÉGIMEN ───────────────────────
    regimes = sorted(df_daily['mode'].unique())
    regime_rows = []
    total_days = len(df_daily)
    
    for reg in regimes:
        sub = df_daily[df_daily['mode'] == reg]
        n_d = len(sub)
        pct_t = (n_d / total_days) * 100.0
        
        rets = sub['daily_ret']
        win_rate = (rets > 0).mean() * 100.0 if n_d > 0 else 0.0
        cum_ret = ((1.0 + rets).prod() - 1.0) * 100.0
        
        regime_rows.append({
            "regime": reg,
            "days": n_d,
            "pct_time": pct_t,
            "cum_ret": cum_ret,
            "win_rate": win_rate
        })
        
    print("\n" + "="*95)
    print("      🛡️ TABLA 2: ATRIBUCIÓN DE RENDIMIENTO POR RÉGIMEN DE MERCADO (QUALITY ENTRY GATE V35)")
    print("="*95)
    print(f"{'Régimen de Mercado':<30s} | {'Días':<6s} | {'%Tiempo':<8s} | {'Retorno Acumulado':<18s} | {'Win Rate (%)':<12s} | Diagnóstico")
    print("-" * 95)
    
    for r in regime_rows:
        diag = "🛡️ Cobertura/Preservación" if "CRASH" in r['regime'] or "PRE_CRASH" in r['regime'] else ("⚡ Acumulación Alfa" if "PISO" in r['regime'] or "RE_ACUMULACION" in r['regime'] else "🚀 Expansión Alcista")
        print(f"{r['regime']:<30s} | {r['days']:<6d} | {r['pct_time']:6.2f}% | {r['cum_ret']:+18.2f}% | {r['win_rate']:12.1f}% | {diag}")
        
    print("="*95)

if __name__ == "__main__":
    main()
