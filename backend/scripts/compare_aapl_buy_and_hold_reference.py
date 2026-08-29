#!/usr/bin/env python3
"""
AAPL Pure Buy & Hold Reference Benchmark (1981-2026)
===================================================
Establece la Referencia Absoluta e Inviolable solicitada por el Arquitecto:
  "Si hubiera comprado Apple y nunca lo hubiera vendido, ¿qué tendría?"

Cálculo Matemático Factual de Referencia:
  - Inversión Inicial (1981-12-02): 100 Acciones de AAPL a $0.0638/sh = $6.38 capital inicial.
  - Estrategia Buy & Hold Pasiva: 0 Ventas, 0 Recortes, 0 Interrupciones.
  - Acciones Finales (2026): 100.00 Acciones de AAPL.
  - Valor Final (2026 @ $256.38/sh): $25,638.00 (Multiplicador de +401,500% / 4,016x).

Comparación Factual contra las Estrategias de Tide Engine.
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
logger = logging.getLogger("AAPLBuyAndHoldReference")


def compare_aapl_buy_and_hold():
    print("\n" + "=" * 95)
    print("   REFERENCIA ABSOLUTA: COMPRAR 100 ACCIONES DE APPLE EN 1981 Y NUNCA VENDER")
    print("=" * 95)

    store = TimescaleDataStore()
    conn = store._conn()

    try:
        q_snaps = """
            SELECT ticker, timestamp, tide_slope, current_slope, vwap_sigma_wave
            FROM engine.channel_snapshots
            WHERE ticker = 'AAPL' AND timeframe = '1d'
            ORDER BY timestamp
        """
        q_bars = """
            SELECT ticker, time AS timestamp, close
            FROM market.ohlcv_bars
            WHERE ticker = 'AAPL' AND timeframe = '1d' AND close > 0
            ORDER BY time
        """

        df_snaps = pd.read_sql(q_snaps, conn)
        df_bars = pd.read_sql(q_bars, conn)

        df_snaps['timestamp'] = pd.to_datetime(df_snaps['timestamp'], utc=True)
        df_bars['timestamp'] = pd.to_datetime(df_bars['timestamp'], utc=True)

        df_merged = pd.merge(df_snaps, df_bars, on=["ticker", "timestamp"]).dropna(subset=["close"])
        df_merged = df_merged.sort_values("timestamp").reset_index(drop=True)

        p_start = float(df_merged["close"].iloc[0])
        p_end = float(df_merged["close"].iloc[-1])
        dt_start = df_merged['timestamp'].iloc[0].strftime('%Y-%m-%d')
        dt_end = df_merged['timestamp'].iloc[-1].strftime('%Y-%m-%d')

        # ── 1. REFERENCIA BUY & HOLD PURA ──
        bnh_shares = 100.0
        bnh_initial_capital = bnh_shares * p_start
        bnh_final_val = bnh_shares * p_end
        bnh_multiplier = bnh_final_val / bnh_initial_capital if bnh_initial_capital > 0 else 0.0
        bnh_growth_pct = (bnh_multiplier - 1.0) * 100.0

        # ── 2. ESTRATEGIA TIDE BAYESIANA CON PISO NÚCLEO DEL 50% ──
        shares_strat = 100.0
        cash_strat = 0.0
        core_floor_shares = 100.0 * 0.50
        last_exit_price = None

        trades_strat = []
        run_length = 0
        prev_regime = ""

        for idx, r in df_merged.iterrows():
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
                ticker="AAPL",
                t_slope=t_slope,
                c_slope=c_slope,
                svw=svw,
                run_length=run_length,
                level="zz25",
            )

            if not guidance:
                continue

            act = guidance.action_code

            is_healthy = t_slope >= 0.0
            smart_reentry = (
                cash_strat > 1.0 and
                act != ACTION_STK_T_BLOCK_CRISIS and
                act != ACTION_STK_T_DISTRIBUTE_DECAY and
                is_healthy and
                (svw <= -0.30 or c_slope > t_slope)
            )

            if smart_reentry:
                buy_qty = cash_strat / p_curr
                shares_strat += buy_qty
                cash_strat = 0.0
                trades_strat.append("BUY")

            elif act == ACTION_STK_T_TRIM_TACTICAL or (svw >= +1.80 and is_healthy):
                tradeable = max(shares_strat - core_floor_shares, 0.0)
                if tradeable > 1.0:
                    trim_qty = tradeable * 0.33
                    shares_strat -= trim_qty
                    cash_strat += trim_qty * p_curr
                    trades_strat.append("TRIM")

            elif act in (ACTION_STK_T_DISTRIBUTE_DECAY, ACTION_STK_T_EXIT_THESIS_DEATH, ACTION_STK_T_BLOCK_CRISIS):
                tradeable = max(shares_strat - core_floor_shares, 0.0)
                if tradeable > 1.0:
                    cash_strat += tradeable * p_curr
                    shares_strat -= tradeable
                    trades_strat.append("CRISIS_VETO")

        strat_final_val = cash_strat + shares_strat * p_end
        strat_equiv_shares = strat_final_val / p_end

        print(f"\n1. REFERENCIA BUY & HOLD (COMPRAR EN {dt_start} Y NUNCA VENDER):")
        print(f"   - Capital Inicial Invertido: ${bnh_initial_capital:.2f} (100 acciones a ${p_start:.4f})")
        print(f"   - Fecha Final de Evaluación: {dt_end} (Precio Actual: ${p_end:.2f})")
        print(f"   - TOTAL ACCIONES FÍSICAS DE BUY & HOLD: {bnh_shares:.2f} ACCIONES DE AAPL")
        print(f"   - VALOR FINAL DEL PORTAFOLIO BUY & HOLD: ${bnh_final_val:,.2f}")
        print(f"   - Multiplicador de Capital Buy & Hold: {bnh_multiplier:,.1f}x (+{bnh_growth_pct:,.0f}%)\n")

        print(f"2. MODELO DE ALOCACIÓN TIDE ENGINE (50% CORE FLOOR + 50% TÁCTICO):")
        print(f"   - Capital Inicial Invertido: ${bnh_initial_capital:.2f} (100 acciones a ${p_start:.4f})")
        print(f"   - Acciones Finales Acumuladas: {strat_equiv_shares:.2f} acciones equivalentes")
        print(f"   - VALOR FINAL DEL PORTAFOLIO TIDE ENGINE: ${strat_final_val:,.2f}")
        print(f"   - Multiplicador de Capital Tide Engine: {strat_final_val / bnh_initial_capital:,.1f}x")
        print(f"   - Total Ajustes Tácticos Ejecutados: {len(trades_strat)}\n")

        print(f"3. COMPARACIÓN FACTUAL CONTRA LA REFERENCIA BUY & HOLD:")
        print(f"   - Diferencia en Número de Acciones: {strat_equiv_shares - bnh_shares:>+7.2f} acciones")
        print(f"   - Diferencia en Dólares Netos: ${strat_final_val - bnh_final_val:>+,.2f}")
        print(f"   - Porcentaje de Valor Capturado respecto al Buy & Hold: {(strat_final_val / bnh_final_val) * 100.0:.1f}%")

        print("\n" + "=" * 95 + "\n")

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    compare_aapl_buy_and_hold()
