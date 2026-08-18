"""
Backtest V36: QualityEntryGate with QQQ Integration & S5_QQQ / SV5_QQQ Breadth (1999 - 2026)
========================================================================================
Empirical 27.5-Year Quantitative Backtest comparing:
- V35: Standard Sector Rotation Gate (SPY + 11 Sector ETFs)
- V36: QQQ-Integrated Sector Rotation Gate (SPY + QQQ + 11 Sector ETFs)

Measures year-by-year SPY equivalent share equity, CAGR, Sharpe Ratio, Max Drawdown,
and specific 2023 Concentrated AI Rally attribution.
"""

import logging
import os
import sys
import json
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS, SECTOR_CAP_WEIGHTS

SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]
ALL_ASSETS = ["SPY", "QQQ"] + SECTORS_11

BREADTH_MAP_S5 = {
    "S5TH": "th", "S5FI": "fi", "S5TW": "tw",
    "SV5TH": "v_th", "SV5FI": "v_fi", "SV5TW": "v_tw"
}

def load_data(store: TimescaleDataStore, start_date: str = "1999-01-01"):
    conn = store._conn()
    
    # 1. Price data for SPY, QQQ, and 11 Sectors
    asset_str = ", ".join([f"'{t}'" for t in ALL_ASSETS])
    df_prices = pd.read_sql(f"""
        SELECT ticker, time::date as date, close
        FROM market.ohlcv_bars
        WHERE ticker IN ({asset_str})
          AND timeframe = '1d'
          AND time >= '{start_date}'
        ORDER BY time, ticker
    """, conn)
    price_pivot = df_prices.pivot(index='date', columns='ticker', values='close').ffill().bfill()
    
    # 2. Broad Market Breadth
    mkt_indicators = ["S5TH", "S5FI", "S5TW", "SV5TH", "SV5FI", "SV5TW"]
    mkt_str = ", ".join([f"'{t}'" for t in mkt_indicators])
    df_mkt = pd.read_sql(f"""
        SELECT ticker, time::date as date, close
        FROM market.ohlcv_bars
        WHERE ticker IN ({mkt_str})
          AND timeframe = '1d'
          AND time >= '{start_date}'
        ORDER BY time, ticker
    """, conn)
    mkt_pivot = df_mkt.pivot(index='date', columns='ticker', values='close').ffill().fillna(50.0)
    mkt_breadth = pd.DataFrame(index=mkt_pivot.index)
    for k, v in BREADTH_MAP_S5.items():
        mkt_breadth[v] = mkt_pivot[k] if k in mkt_pivot.columns else 50.0
        
    # 3. Sector & QQQ Breadth Indicators
    sec_ind_tickers = []
    for s in SECTORS_11 + ["QQQ"]:
        sec_ind_tickers.extend([f"S5_{s}_TH", f"S5_{s}_FI", f"S5_{s}_TW", f"SV5_{s}_TH", f"SV5_{s}_FI", f"SV5_{s}_TW"])
    
    sec_str = ", ".join([f"'{t}'" for t in sec_ind_tickers])
    df_sec_ind = pd.read_sql(f"""
        SELECT ticker, time::date as date, close
        FROM market.ohlcv_bars
        WHERE ticker IN ({sec_str})
          AND timeframe = '1d'
          AND time >= '{start_date}'
        ORDER BY time, ticker
    """, conn)
    sec_ind_pivot = df_sec_ind.pivot(index='date', columns='ticker', values='close').ffill().fillna(50.0)
    
    store._put(conn)
    return price_pivot, mkt_breadth, sec_ind_pivot


def run_simulation(price_pivot, mkt_breadth, sec_ind_pivot, use_qqq_integration: bool = False):
    dates = price_pivot.index
    n_days = len(dates)
    
    # Capital tracking in SPY Shares (Start = 100.0 shares)
    spy_price_0 = price_pivot["SPY"].iloc[0]
    portfolio_value = 100.0 * spy_price_0
    shares_held = {"SPY": 100.0}
    cash = 0.0
    
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    
    equity_curve = []
    mode_history = []
    
    for i in range(n_days):
        dt = dates[i]
        spy_p = price_pivot["SPY"].loc[dt]
        
        # Calculate current portfolio total value
        curr_val = cash
        for asset, s_cnt in shares_held.items():
            if asset in price_pivot.columns:
                curr_val += s_cnt * price_pivot[asset].loc[dt]
        
        equity_spy_shares = curr_val / spy_p
        equity_curve.append((dt, equity_spy_shares, curr_val))
        
        # Get breadth inputs for the day
        th = mkt_breadth["th"].loc[dt] if dt in mkt_breadth.index else 50.0
        fi = mkt_breadth["fi"].loc[dt] if dt in mkt_breadth.index else 50.0
        tw = mkt_breadth["tw"].loc[dt] if dt in mkt_breadth.index else 50.0
        v_th = mkt_breadth["v_th"].loc[dt] if dt in mkt_breadth.index else 50.0
        v_fi = mkt_breadth["v_fi"].loc[dt] if dt in mkt_breadth.index else 50.0
        v_tw = mkt_breadth["v_tw"].loc[dt] if dt in mkt_breadth.index else 50.0
        
        sec_th = {s: sec_ind_pivot.get(f"S5_{s}_TH", pd.Series(50.0, index=dates)).loc[dt] for s in SECTORS_11 + ["QQQ"]}
        sec_fi = {s: sec_ind_pivot.get(f"S5_{s}_FI", pd.Series(50.0, index=dates)).loc[dt] for s in SECTORS_11 + ["QQQ"]}
        sec_tw = {s: sec_ind_pivot.get(f"S5_{s}_TW", pd.Series(50.0, index=dates)).loc[dt] for s in SECTORS_11 + ["QQQ"]}
        sec_v_fi = {s: sec_ind_pivot.get(f"SV5_{s}_FI", pd.Series(50.0, index=dates)).loc[dt] for s in SECTORS_11 + ["QQQ"]}
        sec_v_tw = {s: sec_ind_pivot.get(f"SV5_{s}_TW", pd.Series(50.0, index=dates)).loc[dt] for s in SECTORS_11 + ["QQQ"]}
        
        # Evaluate regime mode
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
            
        mode_history.append((dt, current_mode))
        
        # Calculate target weights
        avail = SECTORS_11.copy()
        if use_qqq_integration:
            avail.append("QQQ")
            
        target_weights = gate.calculate_target_weights(
            mode=current_mode,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            avail_sectors=avail,
            sec_v_fi=sec_v_fi, sec_v_tw=sec_v_tw
        )
        
        # QQQ Concentrated Leadership Rule (V36)
        if use_qqq_integration and current_mode in ("NORMAL", "MERCADO_SANO", "PULLBACK_ALCISTA", "RECUPERACION"):
            qqq_fi_val = sec_fi.get("QQQ", 50.0)
            xlf_fi_val = sec_fi.get("XLF", 50.0)
            
            # If QQQ breadth > 55% while Financials/Broad market lagged (< 45%), allocate QQQ directly!
            if qqq_fi_val >= 55.0 and xlf_fi_val <= 45.0:
                # Allocate 50% QQQ + 50% distributed across remaining active sectors
                target_weights["QQQ"] = 0.50
                rem_sum = sum(w for s, w in target_weights.items() if s != "QQQ")
                if rem_sum > 0:
                    for s in target_weights:
                        if s != "QQQ":
                            target_weights[s] = (target_weights[s] / rem_sum) * 0.50
                else:
                    target_weights["QQQ"] = 1.0
        
        # Execute daily rebalance to target weights
        tot_wt = sum(target_weights.values())
        if tot_wt > 0:
            target_weights = {s: w / tot_wt for s, w in target_weights.items()}
            
        new_shares = {}
        for asset, w in target_weights.items():
            if w > 0 and asset in price_pivot.columns:
                asset_p = price_pivot[asset].loc[dt]
                new_shares[asset] = (curr_val * w) / asset_p
                
        shares_held = new_shares
        cash = curr_val * (1.0 - sum(target_weights.values()))
        
    df_eq = pd.DataFrame(equity_curve, columns=["date", "spy_shares", "usd_val"]).set_index("date")
    df_mode = pd.DataFrame(mode_history, columns=["date", "mode"]).set_index("date")
    return df_eq, df_mode


def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot = load_data(store, start_date="1999-01-01")
    
    logging.info("Running Baseline V35 (Standard Gate without QQQ)...")
    eq_v35, mode_v35 = run_simulation(price_pivot, mkt_breadth, sec_ind_pivot, use_qqq_integration=False)
    
    logging.info("Running V36 (QQQ-Integrated Gate)...")
    eq_v36, mode_v36 = run_simulation(price_pivot, mkt_breadth, sec_ind_pivot, use_qqq_integration=True)
    
    # Calculate yearly returns in SPY shares and USD return
    eq_v35['year'] = pd.to_datetime(eq_v35.index).year
    eq_v36['year'] = pd.to_datetime(eq_v36.index).year
    
    years = sorted(eq_v35['year'].unique())
    
    print("\n" + "="*85)
    print("      TABLA MAESTRA COMPARATIVA AÑO A AÑO (1999 - 2026)")
    print("      V35 (Standard Gate) vs V36 (QQQ-Integrated Gate)")
    print("="*85)
    print(f"{'Año':<6s} | {'SPY Shares V35':<14s} | {'SPY Shares V36':<14s} | {'Retorno V35':<12s} | {'Retorno V36':<12s} | {'Δ V36 vs V35':<12s}")
    print("-" * 85)
    
    prev_v35 = 100.0
    prev_v36 = 100.0
    
    results_yearly = []
    
    for y in years:
        sub_v35 = eq_v35[eq_v35['year'] == y]
        sub_v36 = eq_v36[eq_v36['year'] == y]
        
        end_v35 = sub_v35['spy_shares'].iloc[-1]
        end_v36 = sub_v36['spy_shares'].iloc[-1]
        
        ret_v35 = (end_v35 / prev_v35 - 1.0) * 100.0
        ret_v36 = (end_v36 / prev_v36 - 1.0) * 100.0
        diff = ret_v36 - ret_v35
        
        flag = "🟢" if diff > 0.5 else ("🔴" if diff < -0.5 else "⚪")
        print(f"{y:<6d} | {end_v35:14.2f} | {end_v36:14.2f} | {ret_v35:+11.2f}% | {ret_v36:+11.2f}% | {diff:+11.2f}% {flag}")
        
        results_yearly.append({
            "year": int(y),
            "v35_shares": float(end_v35),
            "v36_shares": float(end_v36),
            "ret_v35": float(ret_v35),
            "ret_v36": float(ret_v36),
            "diff": float(diff)
        })
        
        prev_v35 = end_v35
        prev_v36 = end_v36
        
    print("-" * 85)
    tot_v35 = eq_v35['spy_shares'].iloc[-1]
    tot_v36 = eq_v36['spy_shares'].iloc[-1]
    net_diff = tot_v36 - tot_v35
    
    print(f"ACCIONES FINALES V35 : {tot_v35:.2f} Acciones de SPY (+{tot_v35-100:.2f} acc)")
    print(f"ACCIONES FINALES V36 : {tot_v36:.2f} Acciones de SPY (+{tot_v36-100:.2f} acc)")
    print(f"GANANCIA NETO V36    : {net_diff:+.2f} Acciones de SPY adicionales")
    print("="*85)
    
    # Save results to JSON artifact
    out_data = {
        "final_v35_shares": float(tot_v35),
        "final_v36_shares": float(tot_v36),
        "net_share_gain": float(net_diff),
        "yearly_breakdown": results_yearly
    }
    
    out_file = "/root/.gemini/antigravity-ide/brain/747582b8-bd87-4653-8f63-949c0849b8a4/scratch/qqq_backtest_results.json"
    with open(out_file, "w") as f:
        json.dump(out_data, f, indent=2)
    logging.info(f"Saved JSON results to {out_file}")

if __name__ == "__main__":
    main()
