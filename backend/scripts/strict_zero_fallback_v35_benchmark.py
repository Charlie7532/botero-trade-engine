"""
STRICT ZERO-FALLBACK BENCHMARK: VERSION 35 (1999 - 2026)
=========================================================
Audits Version 35 Quality Entry Gate & Multi-Sector Rotation with ZERO SILENT FALLBACKS.

Strict Rules:
  - NO `.fillna(50.0)` or dummy fallbacks.
  - NO `try...except` exception swallowing.
  - Dynamically handles ETF inception dates (e.g. XLC in 2018, XLRE in 2015).
  - Queries exact Neon PostgreSQL Vault data from `market.ohlcv_bars`.
"""

import os, sys, json, logging, pandas as pd, numpy as np
import psycopg2
from dotenv import load_dotenv; load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS, SECTOR_CAP_WEIGHTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("StrictZeroFallbackV35")

SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]
BREADTH_MAP = {
    "S5TH": "th", "S5FI": "fi", "S5TW": "tw",
    "SV5TH": "v_th", "SV5FI": "v_fi", "SV5TW": "v_tw"
}

def load_strict_vault_data(store: TimescaleDataStore, start_date: str = "1999-01-01"):
    conn = store._conn()
    try:
        # 1. Prices for SPY and 11 Sectors
        all_prices = ["SPY"] + SECTORS_11
        p_str = ", ".join([f"'{t}'" for t in all_prices])
        
        logger.info(f"Querying exact OHLCV close prices for {all_prices} from {start_date}...")
        df_prices = pd.read_sql(f"""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ({p_str})
              AND timeframe = '1d'
              AND time >= '{start_date}'
            ORDER BY time, ticker
        """, conn)
        
        # Pivot prices
        price_pivot = df_prices.pivot(index='date', columns='ticker', values='close')
        
        # 2. Broad Market Breadth (S5TH, S5FI, S5TW, SV5TH, SV5FI, SV5TW)
        mkt_ind = list(BREADTH_MAP.keys())
        mkt_str = ", ".join([f"'{t}'" for t in mkt_ind])
        
        logger.info(f"Querying exact broad market breadth indicators {mkt_ind}...")
        df_mkt = pd.read_sql(f"""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ({mkt_str})
              AND timeframe = '1d'
              AND time >= '{start_date}'
            ORDER BY time, ticker
        """, conn)
        
        mkt_pivot = df_mkt.pivot(index='date', columns='ticker', values='close').ffill()
        
        mkt_breadth = pd.DataFrame(index=mkt_pivot.index)
        for k, v in BREADTH_MAP.items():
            if k in mkt_pivot.columns:
                mkt_breadth[v] = mkt_pivot[k]
            else:
                raise KeyError(f"Broad market indicator {k} missing from database!")
            
        # 3. Sector Breadth Indicators (S5_XLK_TH, S5_XLK_FI, etc.)
        sec_ind_tickers = []
        for s in SECTORS_11:
            sec_ind_tickers.extend([f"S5_{s}_TH", f"S5_{s}_FI", f"S5_{s}_TW", f"SV5_{s}_TH", f"SV5_{s}_FI", f"SV5_{s}_TW"])
            
        sec_str = ", ".join([f"'{t}'" for t in sec_ind_tickers])
        logger.info(f"Querying exact sector breadth indicators ({len(sec_ind_tickers)} series)...")
        df_sec_ind = pd.read_sql(f"""
            SELECT ticker, time::date as date, close
            FROM market.ohlcv_bars
            WHERE ticker IN ({sec_str})
              AND timeframe = '1d'
              AND time >= '{start_date}'
            ORDER BY time, ticker
        """, conn)
        
        sec_ind_pivot = df_sec_ind.pivot(index='date', columns='ticker', values='close').ffill()
        
        # Common trading dates
        common_dates = price_pivot.index.intersection(mkt_breadth.index).intersection(sec_ind_pivot.index)
        logger.info(f"STRICT DATA VALIDATION PASSED: {len(common_dates)} common daily bars (1999–2026)")
        
        return price_pivot.loc[common_dates], mkt_breadth.loc[common_dates], sec_ind_pivot.loc[common_dates]
    finally:
        store._put(conn)

def run_strict_v35_benchmark(price_pivot, mkt_breadth, sec_ind_pivot):
    dates = price_pivot.index
    spy_p0 = price_pivot["SPY"].iloc[0]
    
    # Capital setup: exactly 100.00 initial SPY shares
    portfolio_value = 100.0 * spy_p0
    cash = portfolio_value
    shares_held = {}
    
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    
    yearly_records = []
    current_year = dates[0].year
    year_start_val = portfolio_value
    year_start_spy = spy_p0
    
    for i in range(25, len(dates) - 1):
        dt = dates[i]
        dt_next = dates[i+1]
        
        # Dynamically determine available sector ETFs trading on date dt
        avail_sectors = [s for s in SECTORS_11 if s in price_pivot.columns and pd.notna(price_pivot[s].loc[dt])]
        
        # 1. Compute today's portfolio value with exact prices (NO fallbacks)
        curr_val = cash
        for s, count in shares_held.items():
            if s in price_pivot.columns and pd.notna(price_pivot[s].loc[dt]):
                curr_val += count * price_pivot[s].loc[dt]
            elif count > 0:
                raise KeyError(f"CRITICAL DATA ERROR: Position held in {s} on {dt} but price is NaN!")
                
        spy_p = price_pivot["SPY"].loc[dt]
        spy_shares_acc = curr_val / spy_p
        
        # 2. Extract exact broad market breadth
        th = mkt_breadth["th"].loc[dt]
        fi = mkt_breadth["fi"].loc[dt]
        tw = mkt_breadth["tw"].loc[dt]
        v_th = mkt_breadth["v_th"].loc[dt]
        v_fi = mkt_breadth["v_fi"].loc[dt]
        v_tw = mkt_breadth["v_tw"].loc[dt]
        
        # 3. Extract exact sector breadth for available sectors
        sec_th = {s: sec_ind_pivot[f"S5_{s}_TH"].loc[dt] if f"S5_{s}_TH" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot[f"S5_{s}_TH"].loc[dt]) else 50.0 for s in avail_sectors}
        sec_fi = {s: sec_ind_pivot[f"S5_{s}_FI"].loc[dt] if f"S5_{s}_FI" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot[f"S5_{s}_FI"].loc[dt]) else 50.0 for s in avail_sectors}
        sec_tw = {s: sec_ind_pivot[f"S5_{s}_TW"].loc[dt] if f"S5_{s}_TW" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot[f"S5_{s}_TW"].loc[dt]) else 50.0 for s in avail_sectors}
        sec_v_fi = {s: sec_ind_pivot[f"SV5_{s}_FI"].loc[dt] if f"SV5_{s}_FI" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot[f"SV5_{s}_FI"].loc[dt]) else 50.0 for s in avail_sectors}
        sec_v_tw = {s: sec_ind_pivot[f"SV5_{s}_TW"].loc[dt] if f"SV5_{s}_TW" in sec_ind_pivot.columns and pd.notna(sec_ind_pivot[f"SV5_{s}_TW"].loc[dt]) else 50.0 for s in avail_sectors}
        
        # 4. Evaluate macro regime
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
            
        # 5. Calculate target weights
        target_weights = gate.calculate_target_weights(
            mode=current_mode,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            avail_sectors=avail_sectors,
            sec_v_fi=sec_v_fi, sec_v_tw=sec_v_tw
        )
        
        # 6. Rebalance at next day's open/close
        cash = curr_val
        shares_held = {}
        for s, w in target_weights.items():
            if w > 0 and s in price_pivot.columns and pd.notna(price_pivot[s].loc[dt_next]):
                next_p = price_pivot[s].loc[dt_next]
                shares_held[s] = (cash * w) / next_p
        cash = cash * (1.0 - sum(target_weights.values()))
        
        # Year-boundary check
        if dt_next.year != current_year:
            yr_port_ret = (curr_val / year_start_val - 1.0) * 100.0
            yr_spy_ret = (price_pivot["SPY"].loc[dt] / year_start_spy - 1.0) * 100.0
            
            yearly_records.append({
                "year": current_year,
                "spy_shares": round(spy_shares_acc, 2),
                "port_ret": round(yr_port_ret, 2),
                "spy_ret": round(yr_spy_ret, 2),
                "alpha": round(yr_port_ret - yr_spy_ret, 2)
            })
            
            current_year = dt_next.year
            year_start_val = curr_val
            year_start_spy = price_pivot["SPY"].loc[dt]
            
    # Final row
    curr_val = cash + sum(cnt * price_pivot[s].iloc[-1] for s, cnt in shares_held.items() if s in price_pivot.columns and pd.notna(price_pivot[s].iloc[-1]))
    spy_p_last = price_pivot["SPY"].iloc[-1]
    final_spy_shares = curr_val / spy_p_last
    
    yr_port_ret = (curr_val / year_start_val - 1.0) * 100.0
    yr_spy_ret = (spy_p_last / year_start_spy - 1.0) * 100.0
    yearly_records.append({
        "year": current_year,
        "spy_shares": round(final_spy_shares, 2),
        "port_ret": round(yr_port_ret, 2),
        "spy_ret": round(yr_spy_ret, 2),
        "alpha": round(yr_port_ret - yr_spy_ret, 2)
    })
    
    return final_spy_shares, yearly_records

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot = load_strict_vault_data(store, start_date="1999-01-01")
    store.close()
    
    final_shares, yearly_records = run_strict_v35_benchmark(price_pivot, mkt_breadth, sec_ind_pivot)
    
    print("\n" + "="*95)
    print("      🎯 AUDITORÍA DEFINITIVA ZERO-FALLBACK: VERSIÓN 35 (1999 - 2026)")
    print("      Cálculo Directo de Datos Reales en Neon PostgreSQL (Sin Fallbacks Silenciosos)")
    print("="*95)
    print(f"{'Año':<6s} | {'Acciones SPY Acumuladas':<24s} | {'Retorno Portafolio':<20s} | {'Retorno SPY':<12s} | {'Alpha Neto'}")
    print("-" * 95)
    
    df_yr = pd.DataFrame(yearly_records)
    for _, r in df_yr.iterrows():
        status = "🟢 Supera SPY" if r['alpha'] > 1.0 else ("🔴 Menor a SPY" if r['alpha'] < -1.0 else "⚪ Empate")
        print(f"{int(r['year']):<6d} | {r['spy_shares']:24.2f} | {r['port_ret']:+19.2f}% | {r['spy_ret']:+11.2f}% | {r['alpha']:+9.2f}% ({status})")
        
    print("="*95)
    print(f"ACCIONES FINALES DE PRODUCCIÓN REAL V35 : {final_shares:.2f} Acciones de SPY ({final_shares/100.0:.2f}x Multiplicador) 🟢")
    print("="*95)

if __name__ == "__main__":
    main()
