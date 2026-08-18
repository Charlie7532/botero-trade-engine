"""
Test V40: Volatility Parity & Asymmetric Exit Policies for QQQ and SPY (1999 - 2026)
====================================================================================
Quantitative evaluation of User's Hypothesis:
1. QQQ has ~1.35x realized volatility vs SPY. Treating QQQ with equiparable weights
   or entry/exit policies leads to precipitous drawdowns during tech reversals.
2. Volatility Parity Sizing: Scale QQQ weight by (vol_SPY / vol_QQQ).
3. Asymmetric Tight Exit: Exit QQQ immediately when SV5_QQQ_TW < 35% (institutional volume distribution)
   even if broad SPY remains in MERCADO_SANO.
"""

import os
import sys
import json
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
from backend.scripts._lib.backtest_qqq_integrated_gate import load_data, SECTORS_11, ALL_ASSETS

def run_v40_simulation(price_pivot, mkt_breadth, sec_ind_pivot):
    dates = price_pivot.index
    n_days = len(dates)
    
    spy_price_0 = price_pivot["SPY"].iloc[0]
    portfolio_value = 100.0 * spy_price_0
    shares_held = {"SPY": 100.0}
    cash = 0.0
    
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    
    # Realized 20-day volatility for SPY and QQQ
    spy_returns = price_pivot["SPY"].pct_change()
    qqq_returns = price_pivot["QQQ"].pct_change()
    
    spy_vol_20d = spy_returns.rolling(20).std() * np.sqrt(252)
    qqq_vol_20d = qqq_returns.rolling(20).std() * np.sqrt(252)
    
    # Relative Volatility Ratio: vol_SPY / vol_QQQ
    vol_ratio_qqq = (spy_vol_20d / qqq_vol_20d.replace(0, np.nan)).clip(0.4, 1.0).fillna(0.75)
    
    # 20-day relative strength of QQQ vs SPY
    qqq_rs_20d = (price_pivot["QQQ"] / price_pivot["SPY"]).pct_change(20)
    qqq_ma150 = price_pivot["QQQ"].rolling(150, min_periods=50).mean()
    
    equity_curve = []
    
    for i in range(n_days):
        dt = dates[i]
        spy_p = price_pivot["SPY"].loc[dt]
        
        curr_val = cash
        for asset, s_cnt in shares_held.items():
            if asset in price_pivot.columns:
                curr_val += s_cnt * price_pivot[asset].loc[dt]
        
        equity_spy_shares = curr_val / spy_p
        equity_curve.append((dt, equity_spy_shares, curr_val))
        
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
        
        # Standard macro regime evaluation
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
            
        avail = SECTORS_11.copy()
        target_weights = gate.calculate_target_weights(
            mode=current_mode,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            avail_sectors=avail,
            sec_v_fi=sec_v_fi, sec_v_tw=sec_v_tw
        )
        
        # QQQ Stage 2 & Relative Volatility Sizing
        qqq_p = price_pivot["QQQ"].loc[dt]
        qqq_ma = qqq_ma150.loc[dt] if dt in qqq_ma150.index else qqq_p
        rs_val = qqq_rs_20d.loc[dt] if dt in qqq_rs_20d.index else 0.0
        qqq_fi_val = sec_fi.get("QQQ", 50.0)
        qqq_v_tw_val = sec_v_tw.get("QQQ", 50.0)
        
        # ASYMMETRIC EXIT CONDITION FOR QQQ:
        # Exit QQQ immediately if QQQ volume breadth drops below 35% (smart money distribution in tech)
        # or if QQQ falls below 150-DMA, REGARDLESS of SPY mode!
        is_qqq_distribution_exit = (qqq_v_tw_val < 35.0) or (qqq_p < qqq_ma)
        
        is_qqq_entry_ok = (qqq_p >= qqq_ma) and (rs_val > 0.0) and (qqq_fi_val >= 55.0) and not is_qqq_distribution_exit
        
        if current_mode in ("NORMAL", "MERCADO_SANO", "RE_ACUMULACION_ALCISTA") and is_qqq_entry_ok:
            # Volatility Parity Sizing: Base 25% multiplied by vol_ratio (vol_SPY / vol_QQQ)
            v_ratio = vol_ratio_qqq.loc[dt] if dt in vol_ratio_qqq.index else 0.75
            qqq_alloc = float(np.clip(0.30 * v_ratio, 0.15, 0.30))
            
            tot_w = sum(target_weights.values())
            if tot_w > 0:
                target_weights = {s: w / tot_w * (1.0 - qqq_alloc) for s, w in target_weights.items()}
                target_weights["QQQ"] = qqq_alloc
            else:
                target_weights["QQQ"] = qqq_alloc
        else:
            # Under exit condition or crash regime, QQQ weight is 0.0!
            target_weights["QQQ"] = 0.0
            
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
    return df_eq

def main():
    store = TimescaleDataStore()
    price_pivot, mkt_breadth, sec_ind_pivot = load_data(store, start_date="1999-01-01")
    
    print("Running V40 Volatility Parity & Asymmetric Exit QQQ Gate Backtest (1999-2026)...")
    eq_v40 = run_v40_simulation(price_pivot, mkt_breadth, sec_ind_pivot)
    
    eq_v40['year'] = pd.to_datetime(eq_v40.index).year
    years = sorted(eq_v40['year'].unique())
    
    print("\n" + "="*70)
    print("      V40 TABLA MAESTRA CON PARIDAD DE VOLATILIDAD Y SALIDAS ASIMÉTRICAS")
    print("="*70)
    print(f"{'Año':<6s} | {'SPY Shares V40':<14s} | {'Retorno V40':<12s}")
    print("-" * 70)
    
    prev = 100.0
    for y in years:
        sub = eq_v40[eq_v40['year'] == y]
        end = sub['spy_shares'].iloc[-1]
        ret = (end / prev - 1.0) * 100.0
        flag = "🟢" if ret > 0 else "🔴"
        print(f"{y:<6d} | {end:14.2f} | {ret:+11.2f}% {flag}")
        prev = end
        
    print("-" * 70)
    tot = eq_v40['spy_shares'].iloc[-1]
    print(f"ACCIONES FINALES V40 : {tot:.2f} Acciones de SPY (+{tot-100:.2f} acc)")
    print("="*70)

if __name__ == "__main__":
    main()
