#!/usr/bin/env python3
"""
Interactive Ticker-by-Ticker Tide Guidance Forensics & Debugger
================================================================
Runs closed-loop physical share accumulation and trade-by-trade inspection
on a SINGLE specified ticker (e.g. AAPL, COST, MSFT, NVDA).

Prints detailed day-by-day chess moves:
  - Board State: (Tide, Current, Sigma Wave)
  - Waze Guidance Decision: Action Code (STK_T_*), Hazard Alarm, Forecast Top 3
  - Execution: Shares Bought/Trimmed, Price, Cash Balance, Equivalent Shares Held.
  - Performance vs Buy & Hold (100 shares).

Usage:
  PYTHONPATH=. backend/.venv/bin/python backend/scripts/debug_tide_single_ticker.py AAPL
"""
import sys, json, logging
from pathlib import Path
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
logger = logging.getLogger("DebugTideSingleTicker")


def debug_single_ticker(ticker: str, initial_shares: float = 100.0):
    print("\n" + "=" * 90)
    print(f"      INSPECCIÓN FORENSE TICKER-BY-TICKER (DEBUGGER WAZES ENGINE): {ticker.upper()}")
    print("=" * 90)

    store = TimescaleDataStore()
    conn = store._conn()

    try:
        q_snaps = f"""
            SELECT ticker, timestamp, tide_slope, current_slope, vwap_sigma_wave
            FROM engine.channel_snapshots
            WHERE ticker = '{ticker.upper()}' AND timeframe = '1d'
            ORDER BY timestamp
        """
        q_bars = f"""
            SELECT ticker, time AS timestamp, close
            FROM market.ohlcv_bars
            WHERE ticker = '{ticker.upper()}' AND timeframe = '1d' AND close > 0
            ORDER BY time
        """

        df_snaps = pd.read_sql(q_snaps, conn)
        df_bars = pd.read_sql(q_bars, conn)

        if df_snaps.empty or df_bars.empty:
            print(f"[ERROR] No se encontraron datos para el ticker '{ticker.upper()}' en el Vault.")
            return

        df_snaps['timestamp'] = pd.to_datetime(df_snaps['timestamp'], utc=True)
        df_bars['timestamp'] = pd.to_datetime(df_bars['timestamp'], utc=True)

        df_merged = pd.merge(df_snaps, df_bars, on=["ticker", "timestamp"]).dropna(subset=["close"])
        df_merged = df_merged.sort_values("timestamp").reset_index(drop=True)

        p_start = float(df_merged["close"].iloc[0])
        p_end = float(df_merged["close"].iloc[-1])

        bnh_shares = initial_shares
        bnh_final_val = initial_shares * p_end

        cash = initial_shares * p_start
        shares = 0.0

        trade_log = []
        run_length = 0
        prev_regime = ""

        print(f"\n1. ESTADO INICIAL DEL PORTAFOLIO DE PRUEBA:")
        print(f"   - Ticker Objetivo: {ticker.upper()}")
        print(f"   - Período Evaluado: {df_merged['timestamp'].iloc[0].strftime('%Y-%m-%d')} a {df_merged['timestamp'].iloc[-1].strftime('%Y-%m-%d')} ({len(df_merged)} barras)")
        print(f"   - Precio Inicial: ${p_start:.2f} | Precio Final: ${p_end:.2f}")
        print(f"   - Posición Base Buy & Hold: 100 Acciones de {ticker.upper()} (${initial_shares * p_start:,.2f})")
        print(f"   - Cash de Partida del Modelo: ${cash:,.2f}\n")

        print(f"2. REGISTRO DE JUGADAS Y NAVEGACIÓN EN VIVO (TRADE-BY-TRADE FORENSICS):")
        print(f"   {'FECHA':<11} | {'PRECIO':<7} | {'ESTADO TABLERO':<15} | {'JUGADA (SEÑAL)':<28} | {'ALERTA WAZE':<26} | {'CASH RES.':<10} | {'ACCIONES'}")
        print("   " + "-" * 115)

        for idx, r in df_merged.iterrows():
            dt_str = r["timestamp"].strftime("%Y-%m-%d")
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
            hazard = guidance.hazard_alarm

            # Execute trade logic
            executed = False
            trade_desc = ""

            if act == ACTION_STK_T_ACCUMULATE_STRUCTURAL and cash >= p_curr * 5:
                buy_qty = min(25.0, cash / p_curr)
                shares += buy_qty
                cash -= buy_qty * p_curr
                executed = True
                trade_desc = f"COMPRA (+{buy_qty:.1f} shs)"

            elif act == ACTION_STK_T_BUY_DIP_TACTICAL and cash >= p_curr * 2:
                buy_qty = min(15.0, cash / p_curr)
                shares += buy_qty
                cash -= buy_qty * p_curr
                executed = True
                trade_desc = f"COMPRA DIP (+{buy_qty:.1f} shs)"

            elif act == ACTION_STK_T_TRIM_TACTICAL and shares > 1.0:
                trim_qty = shares * 0.33
                shares -= trim_qty
                cash += trim_qty * p_curr
                executed = True
                trade_desc = f"RECORTE (-{trim_qty:.1f} shs)"

            elif act in (ACTION_STK_T_DISTRIBUTE_DECAY, ACTION_STK_T_EXIT_THESIS_DEATH, ACTION_STK_T_EXIT_TIME_STOP) and shares > 0:
                trade_desc = f"LIQUIDACIÓN TOTAL (-{shares:.1f} shs)"
                cash += shares * p_curr
                shares = 0.0
                executed = True

            elif act == ACTION_STK_T_BLOCK_CRISIS and shares > 0:
                trade_desc = f"VETO CRISIS (-{shares:.1f} shs)"
                cash += shares * p_curr
                shares = 0.0
                executed = True

            if executed:
                trade_log.append({
                    "date": dt_str,
                    "price": p_curr,
                    "regime": curr_key,
                    "action": act,
                    "hazard": hazard,
                    "desc": trade_desc,
                    "cash": cash,
                    "shares": shares,
                })
                print(f"   {dt_str:<11} | ${p_curr:>6.2f} | {curr_key:<15} | {act:<28} | {hazard:<26} | ${cash:>9.2f} | {shares:>6.1f} shs")

        final_val = cash + shares * p_end
        strat_equivalent_shares = final_val / p_end if p_end > 0 else 0.0
        shares_delta = strat_equivalent_shares - bnh_shares
        share_growth_pct = (shares_delta / bnh_shares) * 100.0

        print(f"\n3. SCORECARD FINAL PARA {ticker.upper()}:")
        print(f"   - Total Jugadas Ejecutadas: {len(trade_log)}")
        print(f"   - Acciones Finales Acumuladas por el Tide Engine: {strat_equivalent_shares:,.2f} acciones")
        print(f"   - Acciones Iniciales Buy & Hold: {bnh_shares:,.2f} acciones")
        print(f"   - GANANCIA NETA EN ACCIONES DE {ticker.upper()}: {shares_delta:>+,.2f} ACCIONES PROPIAS")
        print(f"   - CRECIMIENTO DE PORCENTAJE EN ACCIONES: {share_growth_pct:>+5.2f}%")
        print(f"   - Valor Final del Portafolio: ${final_val:,.2f} (vs Buy & Hold: ${bnh_final_val:,.2f})\n")

        print("=" * 90 + "\n")

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    tk = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    debug_single_ticker(tk)
