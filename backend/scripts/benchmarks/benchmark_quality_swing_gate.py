#!/usr/bin/env python3
"""
BENCHMARK MULTISECTORIAL — QUALITY SWING / ENTRY GATE (V35)
============================================================
Evaluación cuantitativa del Quality Swing / Entry Gate sobre los 11 sectores SPDR
(XLK, XLC, XLF, XLI, XLV, XLP, XLU, XLRE, XLB, XLE, XLY) y el benchmark SPY.

DIRECTIVAS FUNDAMENTALES:
  1. Preservación Absoluta de la Verdad Empírica (Cero sesgo, medición cuantitativa directa).
  2. Unidad Estándar — Acciones Equivalentes de SPY (Precisión Fraccionaria):
     Cada estrategia inicia con un capital equivalente a exactamente 100.00 acciones de SPY
     (Capital inicial = 100.0 * SPY_price_0). El desempeño final se expresa en acciones de SPY.

Clean Architecture: Script (delivery mechanism). Lee únicamente del Vault (TimescaleDataStore).
"""
import os
import sys
import json
import logging
from datetime import datetime
import numpy as np
import pandas as pd

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate
from backend.modules.shared.domain.constants.sectors import SECTOR_ETFS, SECTOR_CAP_WEIGHTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BenchmarkQualitySwingGate")

SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]
BREADTH_MAP_S5 = {
    "S5TH": "th", "S5FI": "fi", "S5TW": "tw",
    "SV5TH": "v_th", "SV5FI": "v_fi", "SV5TW": "v_tw"
}


def load_vault_data(store: TimescaleDataStore, start_date: str = "2000-01-01"):
    """Carga OHLCV de SPY, 11 ETFs Sectoriales e Indicadores de Amplitud del Vault."""
    conn = store._conn()
    
    # 1. Precios de SPY y 11 Sectores
    tickers = ["SPY"] + SECTORS_11
    ticker_list_str = ", ".join([f"'{t}'" for t in tickers])
    
    logger.info(f"Cargando barras 1d para {tickers} desde {start_date}...")
    df_prices = pd.read_sql(f"""
        SELECT ticker, time::date as date, close
        FROM market.ohlcv_bars
        WHERE ticker IN ({ticker_list_str})
          AND timeframe = '1d'
          AND time >= '{start_date}'
        ORDER BY time, ticker
    """, conn)
    
    # Pivotear precios por fecha: col = ticker, val = close
    price_pivot = df_prices.pivot(index='date', columns='ticker', values='close').ffill().bfill()
    
    # 2. Indicadores Agregados de Amplitud de Mercado (S5_TH, S5_FI, S5_TW, SV5_TH, SV5_FI, SV5_TW)
    mkt_indicators = ["S5TH", "S5FI", "S5TW", "SV5TH", "SV5FI", "SV5TW"]
    mkt_list_str = ", ".join([f"'{t}'" for t in mkt_indicators])
    
    df_mkt = pd.read_sql(f"""
        SELECT ticker, time::date as date, close
        FROM market.ohlcv_bars
        WHERE ticker IN ({mkt_list_str})
          AND timeframe = '1d'
          AND time >= '{start_date}'
        ORDER BY time, ticker
    """, conn)
    
    mkt_pivot = df_mkt.pivot(index='date', columns='ticker', values='close').ffill().fillna(50.0)
    
    # Normalize naming: S5TH -> th, S5FI -> fi, S5TW -> tw, SV5TH -> v_th, SV5FI -> v_fi, SV5TW -> v_tw
    mkt_breadth = pd.DataFrame(index=mkt_pivot.index)
    for k, v in BREADTH_MAP_S5.items():
        if k in mkt_pivot.columns:
            mkt_breadth[v] = mkt_pivot[k]
        else:
            mkt_breadth[v] = 50.0

    # 3. Indicadores de Amplitud Sectorial (S5_XLK_TH, S5_XLK_FI, etc.)
    sec_ind_tickers = []
    for s in SECTORS_11:
        sec_ind_tickers.extend([f"S5_{s}_TH", f"S5_{s}_FI", f"S5_{s}_TW", f"SV5_{s}_TH", f"SV5_{s}_FI", f"SV5_{s}_TW"])
    
    sec_list_str = ", ".join([f"'{t}'" for t in sec_ind_tickers])
    df_sec_ind = pd.read_sql(f"""
        SELECT ticker, time::date as date, close
        FROM market.ohlcv_bars
        WHERE ticker IN ({sec_list_str})
          AND timeframe = '1d'
          AND time >= '{start_date}'
        ORDER BY time, ticker
    """, conn)
    
    sec_ind_pivot = df_sec_ind.pivot(index='date', columns='ticker', values='close').ffill().fillna(50.0)

    store._put(conn)
    return price_pivot, mkt_breadth, sec_ind_pivot


def run_gate_simulation(price_pivot: pd.DataFrame, mkt_breadth: pd.DataFrame, sec_ind_pivot: pd.DataFrame, gate_version: str = "V35"):
    """
    Ejecuta la simulación cuantitativa multi-sectorial del Quality Entry Gate.
    Unidad Estándar: Inicia exactamente con un valor equivalente a 100.00 acciones de SPY.
    """
    dates = price_pivot.index.intersection(mkt_breadth.index)
    if len(dates) == 0:
        logger.error("No hay fechas coincidentes entre precios y amplitud.")
        return None

    dates = sorted(dates)
    spy_prices = price_pivot.loc[dates, "SPY"]
    
    # Capital Inicial equivalente a 100.00 acciones de SPY en la fecha de inicio
    initial_spy_shares = 100.00
    initial_capital = initial_spy_shares * spy_prices.iloc[0]
    
    portfolio_cash = initial_capital
    portfolio_shares = {s: 0.0 for s in SECTORS_11}
    
    gate = QualityEntryGate()
    current_mode = "NORMAL"
    days_in_mode = 0
    
    regime_days = {}
    equity_curve = []
    prev_tw = None
    
    for i, d in enumerate(dates):
        spy_p = spy_prices.loc[d]
        
        # Calcular valor total actual de la cartera (Equity en USD)
        current_equity = portfolio_cash + sum(portfolio_shares[s] * price_pivot.loc[d, s] for s in SECTORS_11 if s in price_pivot.columns)
        spy_equiv_shares = current_equity / spy_p
        equity_curve.append({"date": d, "equity": current_equity, "spy_shares": spy_equiv_shares, "mode": current_mode})
        
        # Amplitud de mercado agregada
        th = mkt_breadth.loc[d, "th"] if "th" in mkt_breadth.columns else 50.0
        fi = mkt_breadth.loc[d, "fi"] if "fi" in mkt_breadth.columns else 50.0
        tw = mkt_breadth.loc[d, "tw"] if "tw" in mkt_breadth.columns else 50.0
        v_th = mkt_breadth.loc[d, "v_th"] if "v_th" in mkt_breadth.columns else 50.0
        v_fi = mkt_breadth.loc[d, "v_fi"] if "v_fi" in mkt_breadth.columns else 50.0
        v_tw = mkt_breadth.loc[d, "v_tw"] if "v_tw" in mkt_breadth.columns else 50.0
        
        # Amplitud por sector
        sec_th = {}
        sec_fi = {}
        sec_tw = {}
        sec_v_fi = {}
        sec_v_tw = {}
        
        for s in SECTORS_11:
            sec_th[s] = sec_ind_pivot.loc[d, f"S5_{s}_TH"] if f"S5_{s}_TH" in sec_ind_pivot.columns else 50.0
            sec_fi[s] = sec_ind_pivot.loc[d, f"S5_{s}_FI"] if f"S5_{s}_FI" in sec_ind_pivot.columns else 50.0
            sec_tw[s] = sec_ind_pivot.loc[d, f"S5_{s}_TW"] if f"S5_{s}_TW" in sec_ind_pivot.columns else 50.0
            sec_v_fi[s] = sec_ind_pivot.loc[d, f"SV5_{s}_FI"] if f"SV5_{s}_FI" in sec_ind_pivot.columns else 50.0
            sec_v_tw[s] = sec_ind_pivot.loc[d, f"SV5_{s}_TW"] if f"SV5_{s}_TW" in sec_ind_pivot.columns else 50.0

        # Evaluar cambio de régimen de mercado
        new_mode = gate.evaluate_regime(
            th=th, fi=fi, tw=tw,
            v_th=v_th, v_fi=v_fi, v_tw=v_tw,
            sec_th=sec_th, sec_fi=sec_fi, sec_tw=sec_tw,
            current_mode=current_mode,
            days_in_mode=days_in_mode,
            tw_prev=prev_tw,
        )
        prev_tw = tw
        
        if new_mode == current_mode:
            days_in_mode += 1
        else:
            current_mode = new_mode
            days_in_mode = 1
            
        regime_days[current_mode] = regime_days.get(current_mode, 0) + 1
        
        # Ponderaciones objetivo según versión
        available_secs = [s for s in SECTORS_11 if s in price_pivot.columns and not pd.isna(price_pivot.loc[d, s])]
        
        if gate_version == "V20":
            # Equal-weighted baseline
            target_weights = {s: 1.0 / len(available_secs) for s in available_secs}
        else:
            target_weights = gate.calculate_target_weights(
                mode=current_mode,
                sec_th=sec_th,
                sec_fi=sec_fi,
                sec_tw=sec_tw,
                avail_sectors=available_secs,
                sec_v_fi=sec_v_fi,
                sec_v_tw=sec_v_tw,
            )
            
        # Rebalanceo al cierre de mercado
        portfolio_cash = current_equity
        portfolio_shares = {s: 0.0 for s in SECTORS_11}
        
        for s, w in target_weights.items():
            if w > 0 and s in price_pivot.columns and price_pivot.loc[d, s] > 0:
                allocated_usd = current_equity * w
                sec_p = price_pivot.loc[d, s]
                portfolio_shares[s] = allocated_usd / sec_p
                portfolio_cash -= allocated_usd

    df_equity = pd.DataFrame(equity_curve)
    final_spy_shares = df_equity["spy_shares"].iloc[-1]
    net_shares_gained = final_spy_shares - initial_spy_shares
    
    # Cálculo de métricas cuantitativas
    n_days = len(df_equity)
    cagr = ((df_equity["equity"].iloc[-1] / df_equity["equity"].iloc[0]) ** (252.0 / n_days) - 1.0) * 100
    
    # Daily returns for Sharpe/Sortino
    daily_rets = df_equity["equity"].pct_change().dropna()
    sharpe = (daily_rets.mean() / daily_rets.std() * np.sqrt(252.0)) if daily_rets.std() > 0 else 0.0
    
    downside_std = daily_rets[daily_rets < 0].std()
    sortino = (daily_rets.mean() / downside_std * np.sqrt(252.0)) if downside_std > 0 else 0.0
    
    # Max Drawdown
    cum_max = df_equity["equity"].cummax()
    dd = (df_equity["equity"] - cum_max) / cum_max
    max_dd = dd.min() * 100
    
    return {
        "version": gate_version,
        "initial_spy_shares": initial_spy_shares,
        "final_spy_shares": round(final_spy_shares, 2),
        "net_shares_gained": round(net_shares_gained, 2),
        "cagr_pct": round(cagr, 2),
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3),
        "max_drawdown_pct": round(max_dd, 2),
        "trading_days": n_days,
        "regime_days": regime_days,
        "df_equity": df_equity
    }


def main():
    logger.info("=== BENCHMARK MULTISECTORIAL — QUALITY SWING GATE ===")
    store = TimescaleDataStore()
    
    price_pivot, mkt_breadth, sec_ind_pivot = load_vault_data(store, start_date="2000-01-01")
    
    logger.info(f"Rango de datos: {price_pivot.index[0]} a {price_pivot.index[-1]} ({len(price_pivot)} días)")
    
    versions = ["V20", "V35"]
    results = {}
    
    # Benchmark Buy & Hold SPY (100.00 acciones constantes)
    spy_start = price_pivot["SPY"].iloc[0]
    spy_end = price_pivot["SPY"].iloc[-1]
    n_days = len(price_pivot)
    spy_cagr = ((spy_end / spy_start) ** (252.0 / n_days) - 1.0) * 100
    spy_rets = price_pivot["SPY"].pct_change().dropna()
    spy_sharpe = (spy_rets.mean() / spy_rets.std() * np.sqrt(252.0))
    spy_cummax = price_pivot["SPY"].cummax()
    spy_max_dd = ((price_pivot["SPY"] - spy_cummax) / spy_cummax).min() * 100

    results["BUY_AND_HOLD_SPY"] = {
        "version": "Buy & Hold SPY (Benchmark Base)",
        "initial_spy_shares": 100.00,
        "final_spy_shares": 100.00,
        "net_shares_gained": 0.00,
        "cagr_pct": round(spy_cagr, 2),
        "sharpe_ratio": round(spy_sharpe, 3),
        "max_drawdown_pct": round(spy_max_dd, 2),
        "trading_days": n_days
    }

    for ver in versions:
        logger.info(f"Ejecutando simulación para {ver}...")
        res = run_gate_simulation(price_pivot, mkt_breadth, sec_ind_pivot, gate_version=ver)
        if res:
            results[ver] = {k: v for k, v in res.items() if k != "df_equity"}

    logger.info("\n" + "="*80)
    logger.info("RESULTADOS BENCHMARK MULTISECTORIAL (Unidad: Acciones de SPY)")
    logger.info("="*80)
    
    print(f"\n{'Estrategia':<35} | {'Acciones SPY Finales':<20} | {'Ganancia neta':<15} | {'CAGR (%)':<10} | {'Sharpe':<8} | {'Max DD (%)':<10}")
    print("-" * 108)
    
    for k, v in results.items():
        print(f"{v['version']:<35} | {v['final_spy_shares']:>20.2f} | {v['net_shares_gained']:>15.2f} | {v['cagr_pct']:>10.2f}% | {v['sharpe_ratio']:>8.3f} | {v['max_drawdown_pct']:>10.2f}%")
        
    print("-" * 108)
    
    # Save output to data/research directory
    os.makedirs("/root/botero-trade/data/research/quality_swing", exist_ok=True)
    out_file = "/root/botero-trade/data/research/quality_swing/quality_swing_benchmark_results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
        
    logger.info(f"✅ Resultados del benchmark guardados en {out_file}")
    store.close()

if __name__ == "__main__":
    main()
