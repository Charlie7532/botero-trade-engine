#!/usr/bin/env python3
"""
Self-Ticker Physical Share-Accumulation Engine — Chunked High-Speed Version
=============================================================================
Closed-Loop Proof-of-Fire Benchmark for Tide Model & SwingGate.

Simulates physical share accumulation on 559 Vault Stocks & ETFs in chunks of 50:
  - Initial Position per Ticker: 100 Shares of ITSELF (or cash equivalent at t=0).
  - Uses Waze Guidance Engine lookup_tide_guidance() day-by-day.
  - Memory-Optimized: Processes in 50-ticker chunks (uses <100MB RAM, 15s runtime).

Output: Console scorecard + Sector breakdown table.
"""
import sys, json, logging
from pathlib import Path
from collections import defaultdict
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.quality_swing.domain.rules.rc_tide_ev_lookup import lookup_tide_guidance
from backend.modules.quality_swing.domain.entities.tide_route_guidance import (
    TideRouteGuidance,
    ACTION_STK_T_ACCUMULATE_STRUCTURAL,
    ACTION_STK_T_BUY_DIP_TACTICAL,
    ACTION_STK_T_TRIM_TACTICAL,
    ACTION_STK_T_DISTRIBUTE_DECAY,
    ACTION_STK_T_EXIT_THESIS_DEATH,
    ACTION_STK_T_EXIT_TIME_STOP,
    ACTION_STK_T_BLOCK_CRISIS,
    ACTION_STK_T_HOLD_STABLE,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SelfTickerShareAccumulation")


def run_single_ticker_simulation(df_ticker: pd.DataFrame, sector_name: str, initial_shares: float = 100.0) -> dict:
    """Run closed-loop physical share accumulation simulation on a single ticker measured in ITS OWN SHARES."""
    if df_ticker.empty or len(df_ticker) < 50:
        return {}

    p_start = float(df_ticker["close"].iloc[0])
    p_end = float(df_ticker["close"].iloc[-1])

    bnh_shares = initial_shares
    cash = initial_shares * p_start
    shares = 0.0

    trades = []
    run_length = 0
    prev_regime = ""

    for idx, r in df_ticker.iterrows():
        p_curr = float(r["close"])
        t_slope = float(r["tide_slope"])
        c_slope = float(r["current_slope"])
        svw = float(r["vwap_sigma_wave"])

        curr_key = f"{t_slope}|{c_slope}|{svw}"
        if curr_key == prev_regime:
            run_length += 1
        else:
            run_length = 1
            prev_regime = curr_key

        guidance: TideRouteGuidance = lookup_tide_guidance(
            ticker=r["ticker"],
            t_slope=t_slope,
            c_slope=c_slope,
            svw=svw,
            run_length=run_length,
            level="zz25",
        )

        if not guidance:
            continue

        act = guidance.action_code

        if act == ACTION_STK_T_ACCUMULATE_STRUCTURAL and cash >= p_curr * 5:
            buy_qty = min(25.0, cash / p_curr)
            shares += buy_qty
            cash -= buy_qty * p_curr
            trades.append({"type": "BUY_ACCUMULATE", "price": p_curr, "qty": buy_qty})

        elif act == ACTION_STK_T_BUY_DIP_TACTICAL and cash >= p_curr * 2:
            buy_qty = min(15.0, cash / p_curr)
            shares += buy_qty
            cash -= buy_qty * p_curr
            trades.append({"type": "BUY_DIP", "price": p_curr, "qty": buy_qty})

        elif act == ACTION_STK_T_TRIM_TACTICAL and shares > 1.0:
            trim_qty = shares * 0.33
            shares -= trim_qty
            cash += trim_qty * p_curr
            trades.append({"type": "TRIM", "price": p_curr, "qty": trim_qty})

        elif act in (ACTION_STK_T_DISTRIBUTE_DECAY, ACTION_STK_T_EXIT_THESIS_DEATH, ACTION_STK_T_EXIT_TIME_STOP) and shares > 0:
            cash += shares * p_curr
            trades.append({"type": "LIQUIDATE", "price": p_curr, "qty": shares})
            shares = 0.0

        elif act == ACTION_STK_T_BLOCK_CRISIS and shares > 0:
            cash += shares * p_curr
            trades.append({"type": "BLOCK_LIQUIDATE", "price": p_curr, "qty": shares})
            shares = 0.0

    final_strat_val = cash + shares * p_end
    strat_equivalent_shares = final_strat_val / p_end if p_end > 0 else 0.0
    shares_delta = strat_equivalent_shares - bnh_shares
    share_growth_pct = (shares_delta / bnh_shares) * 100.0

    return {
        "ticker": df_ticker["ticker"].iloc[0],
        "sector": sector_name or "UNCLASSIFIED",
        "bnh_shares": bnh_shares,
        "strat_equivalent_shares": strat_equivalent_shares,
        "shares_delta": shares_delta,
        "share_growth_pct": share_growth_pct,
        "total_trades": len(trades),
    }


def main():
    logger.info("Iniciando Benchmark Optimizado de Acumulación FÍSICA EN ACCIONES PROPIAS por Ticker...")
    store = TimescaleDataStore()
    conn = store._conn()

    try:
        q_tickers = """
            SELECT ticker, COALESCE(sector, 'UNCLASSIFIED') AS sector FROM market.ticker_metadata 
            WHERE (industry IS NULL OR UPPER(industry) != 'INDICATOR')
              AND (sector IS NULL OR UPPER(sector) NOT IN (
                  'INDICATOR', 'VOLUME BREADTH', 'CAP-WEIGHTED BREADTH', 'OPTIONS FLOW', 
                  'VOLATILITY', 'SENTIMENT', 'SHORT INTEREST', 'VOLUME INTENSITY', 
                  'QQQ BREADTH', 'INDEX', 'YIELDS', 'BROAD MARKET', 'CURRENCY', 
                  'COMMODITIES', 'FIXED INCOME', 'FEAR & GREED', 'BREADTH'
              ))
              AND ticker NOT IN ('VIX', 'VVIX', 'CBOE_PCR', 'FG', 'S5TH', 'S5FI', 'S5TW')
        """
        tickers_df = pd.read_sql(q_tickers, conn)
        sector_map = dict(zip(tickers_df["ticker"], tickers_df["sector"]))
        all_tickers = tickers_df["ticker"].tolist()
        logger.info(f"Cargados {len(all_tickers)} activos del Vault clasificados por sectores GICS.")

        chunk_size = 50
        results = []

        for i in range(0, len(all_tickers), chunk_size):
            chunk = all_tickers[i:i + chunk_size]
            placeholders = ",".join(f"'{t}'" for t in chunk)

            q_snaps = f"""
                SELECT ticker, timestamp, tide_slope, current_slope, vwap_sigma_wave
                FROM engine.channel_snapshots
                WHERE ticker IN ({placeholders}) AND timeframe = '1d'
                ORDER BY ticker, timestamp
            """
            q_bars = f"""
                SELECT ticker, time AS timestamp, close
                FROM market.ohlcv_bars
                WHERE ticker IN ({placeholders}) AND timeframe = '1d' AND close > 0
                ORDER BY ticker, time
            """

            df_snaps = pd.read_sql(q_snaps, conn)
            df_bars = pd.read_sql(q_bars, conn)

            if df_snaps.empty or df_bars.empty:
                continue

            df_snaps['timestamp'] = pd.to_datetime(df_snaps['timestamp'], utc=True)
            df_bars['timestamp'] = pd.to_datetime(df_bars['timestamp'], utc=True)

            df_merged = pd.merge(df_snaps, df_bars, on=["ticker", "timestamp"]).dropna(subset=["close"])
            df_merged = df_merged.sort_values(["ticker", "timestamp"]).reset_index(drop=True)

            for tk, group in df_merged.groupby("ticker"):
                sec = sector_map.get(tk, "UNCLASSIFIED")
                res = run_single_ticker_simulation(group, sector_name=sec, initial_shares=100.0)
                if res:
                    results.append(res)

        df_res = pd.DataFrame(results)

        total_bnh_shares = df_res["bnh_shares"].sum()
        total_strat_shares = df_res["strat_equivalent_shares"].sum()
        net_shares_gained = df_res["shares_delta"].sum()
        mean_growth_pct = df_res["share_growth_pct"].mean()
        win_tickers = (df_res["shares_delta"] > 0).sum()
        total_valid_tickers = len(df_res)
        ticker_win_rate = (win_tickers / total_valid_tickers) * 100 if total_valid_tickers > 0 else 0.0

        print("\n" + "=" * 80)
        print("   SCORECARD DE ACUMULACIÓN FÍSICA EN ACCIONES PROPIAS DE CADA ACTIVO")
        print("=" * 80)

        print(f"\n1. RESUMEN DE PRUEBA DE ACUMULACIÓN PURA:")
        print(f"   - Total Activos Evaluados: {total_valid_tickers}")
        print(f"   - Posición Base Inicial por Ticker: 100 Acciones PROPIAS")
        print(f"   - Total Acciones Iniciales Totales: {total_bnh_shares:,.0f} shs")
        print(f"   - Total Acciones Finales Acumuladas por el Tide Engine: {total_strat_shares:,.2f} shs")
        print(f"   - GANANCIA NETA EN NÚMERO DE ACCIONES: {net_shares_gained:>+,.2f} ACCIONES PROPIAS")
        print(f"   - PORCENTAJE PROMEDIO DE CRECIMIENTO EN ACCIONES POR ACTIVO: {mean_growth_pct:>+5.2f}%")
        print(f"   - Tasa de Éxito (% de activos donde se acumularon más acciones): {ticker_win_rate:.1f}% ({win_tickers}/{total_valid_tickers})")

        print(f"\n2. ACUMULACIÓN PROMEDIO DE ACCIONES SEGMENTADO POR SECTOR GICS:")
        print(f"   {'SECTOR':<22} | {'ACTIVOS':<7} | {'ÉXITO %':<9} | {'CRECIMIENTO ACCIONES %':<22} | {'NET SHARES GAINED':<18}")
        print("   " + "-" * 80)

        for sec_name, group in df_res.groupby("sector"):
            sec_count = len(group)
            sec_win = (group["shares_delta"] > 0).mean() * 100
            sec_growth = group["share_growth_pct"].mean()
            sec_shares = group["shares_delta"].sum()
            print(f"   {sec_name:<22} | {sec_count:>7} | {sec_win:>8.1f}% | {sec_growth:>+21.2f}% | {sec_shares:>+17.2f} shs")

        print(f"\n3. TOP 10 ACTIVOS CON MAYOR GANANCIA EN NÚMERO DE ACCIONES PROPIAS:")
        top_gainers = df_res.sort_values("shares_delta", ascending=False).head(10)
        for _, r in top_gainers.iterrows():
            print(f"   - {r['ticker']:<6} ({r['sector']:<18}) -> Acciones Finales: {r['strat_equivalent_shares']:>7.2f} shs (+{r['share_growth_pct']:>+5.1f}%) | Trades: {r['total_trades']}")

        print("=" * 80 + "\n")

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    main()
