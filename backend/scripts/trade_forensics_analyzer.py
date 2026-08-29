#!/usr/bin/env python3
"""
Full History Peak & Valley Forensics Analyzer — AAPL (1981-2026)
================================================================
Auditoría Forense COMPLETA desde 1981 hasta 2026 sobre Apple (AAPL):
  - Analiza CADA PICO (Techo σ >= +1.50) y CADA VALLE (Suelo σ <= -0.50).
  - Evalúa la precisión del timing en el Retroceso Comprable:
      * ¿Vendió en el Pico Verdadero o se precipitó?
      * ¿Compró en el Valle Verdadero o compró un cuchillo cayendo?
      * ¿Cuántas acciones netas se ganaron/perdieron en CADA ciclo de Pico-Valle?

Clean Architecture: Auditoría sin truncado para aprendizaje fino.
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
logger = logging.getLogger("FullPeakValleyAnalyzer")


def analyze_full_history_peaks_valleys(ticker: str = "AAPL", initial_shares: float = 100.0):
    print("\n" + "=" * 105)
    print(f"   AUDITORÍA FORENSE DE PICOS Y VALLES HISTORIA COMPLETA 1981-2026: {ticker.upper()}")
    print("=" * 105)

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
            print(f"[ERROR] No hay datos suficientes para {ticker.upper()}")
            return

        df_snaps['timestamp'] = pd.to_datetime(df_snaps['timestamp'], utc=True)
        df_bars['timestamp'] = pd.to_datetime(df_bars['timestamp'], utc=True)

        df_merged = pd.merge(df_snaps, df_bars, on=["ticker", "timestamp"]).dropna(subset=["close"])
        df_merged = df_merged.sort_values("timestamp").reset_index(drop=True)

        p_start = float(df_merged["close"].iloc[0])
        p_end = float(df_merged["close"].iloc[-1])

        bnh_shares = initial_shares
        bnh_final_val = initial_shares * p_end

        shares = initial_shares
        cash = 0.0

        trade_cycles = []
        last_trim_price = None
        last_trim_date = None

        run_length = 0
        prev_regime = ""
        ev_history = []
        c_history = []

        print(f"\n1. RESUMEN DE PARTIDA HISTÓRICA COMPLETA:")
        print(f"   - Ticker: {ticker.upper()} | Período: {df_merged['timestamp'].iloc[0].strftime('%Y-%m-%d')} a {df_merged['timestamp'].iloc[-1].strftime('%Y-%m-%d')} ({len(df_merged):,} barras)")
        print(f"   - Posición Base Inicial: {initial_shares} Acciones de {ticker.upper()} a ${p_start:.2f} (${initial_shares * p_start:,.2f})\n")

        for idx, r in df_merged.iterrows():
            dt_str = r["timestamp"].strftime("%Y-%m-%d")
            p_curr = float(r["close"])
            t_slope = float(r["tide_slope"])
            c_slope = float(r["current_slope"])
            svw = float(r["vwap_sigma_wave"])

            c_history.append(c_slope)
            if len(c_history) > 10:
                c_history.pop(0)

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
            ev = guidance.weighted_ev
            ev_history.append(ev)
            if len(ev_history) > 10:
                ev_history.pop(0)

            delta_ev = (ev - ev_history[-4]) if len(ev_history) >= 4 else 0.0
            delta_c = (c_slope - c_history[-4]) if len(c_history) >= 4 else 0.0

            is_improving = delta_ev > 0.001 and delta_c > 0.0
            is_degrading = delta_ev < -0.001 and delta_c < 0.0
            is_healthy_marea = t_slope >= 0.0
            is_extreme_top = is_healthy_marea and svw >= +1.80
            is_extreme_floor = is_healthy_marea and svw <= -1.80

            core_floor_shares = initial_shares * 0.50

            # Re-entry Trigger: Re-invest cash ONLY when Marea is non-crisis
            smart_reentry = (
                cash > 1.0 and
                act != ACTION_STK_T_BLOCK_CRISIS and
                act != ACTION_STK_T_DISTRIBUTE_DECAY and
                is_healthy_marea and
                (is_extreme_floor or (svw <= -0.30 and is_improving))
            )

            if smart_reentry:
                buy_qty = cash / p_curr
                shares += buy_qty
                
                # Calculate exact Peak-to-Valley Share Gain / Loss
                analysis_str = "RE-INVERSIÓN VALLE"
                if last_trim_price:
                    pct_discount = ((last_trim_price - p_curr) / last_trim_price) * 100.0
                    if p_curr < last_trim_price:
                        analysis_str = f"COMPRA EN VALLE (+{pct_discount:.1f}% DESCUENTO vs Pico ${last_trim_price:.2f})"
                    else:
                        analysis_str = f"COMPRA EN VALLE (-{abs(pct_discount):.1f}% SOBREPRECIO vs Pico ${last_trim_price:.2f})"

                cash = 0.0
                trade_cycles.append({
                    "date": dt_str,
                    "type": "COMPRA VALLE",
                    "price": p_curr,
                    "qty": buy_qty,
                    "sigma": svw,
                    "analysis": analysis_str,
                    "shares": shares,
                })

            elif is_extreme_top or act == ACTION_STK_T_TRIM_TACTICAL or is_degrading:
                tradeable_shares = max(shares - core_floor_shares, 0.0)
                if tradeable_shares > 1.0:
                    harvest_fraction = 0.50 if is_extreme_top else 0.33
                    trim_qty = tradeable_shares * harvest_fraction
                    shares -= trim_qty
                    cash += trim_qty * p_curr
                    last_trim_price = p_curr
                    last_trim_date = dt_str
                    trade_cycles.append({
                        "date": dt_str,
                        "type": "COSECHA PICO",
                        "price": p_curr,
                        "qty": trim_qty,
                        "sigma": svw,
                        "analysis": f"COSECHA PICO (σ={svw:+.2f})",
                        "shares": shares,
                    })

            elif act in (ACTION_STK_T_DISTRIBUTE_DECAY, ACTION_STK_T_EXIT_THESIS_DEATH, ACTION_STK_T_BLOCK_CRISIS):
                tradeable_shares = max(shares - core_floor_shares, 0.0)
                if tradeable_shares > 1.0:
                    cash += tradeable_shares * p_curr
                    shares -= tradeable_shares
                    last_trim_price = p_curr
                    last_trim_date = dt_str
                    trade_cycles.append({
                        "date": dt_str,
                        "type": "VETO CRISIS",
                        "price": p_curr,
                        "qty": tradeable_shares,
                        "sigma": svw,
                        "analysis": f"VETO CRISIS (T_slope={t_slope:+.3f})",
                        "shares": shares,
                    })

        final_val = cash + shares * p_end
        strat_equivalent_shares = final_val / p_end if p_end > 0 else 0.0
        shares_delta = strat_equivalent_shares - bnh_shares
        share_growth_pct = (shares_delta / bnh_shares) * 100.0

        print(f"2. REGISTRO COMPLETO Y NO TRUNCADO DE PICOS Y VALLES (1981 - 2026): {len(trade_cycles)} OPERACIONES")
        print(f"   {'FECHA':<11} | {'TIPO JUGADA':<14} | {'PRECIO':<7} | {'SIGMA σ':<8} | {'ANÁLISIS FORENSE PICO-VALLE':<55} | {'ACCIONES'}")
        print("   " + "-" * 115)

        for t in trade_cycles:
            print(f"   {t['date']:<11} | {t['type']:<14} | ${t['price']:>6.2f} | {t['sigma']:>+6.2f}σ | {t['analysis']:<55} | {t['shares']:>6.1f} shs")

        print("\n" + "=" * 105 + "\n")

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    tk = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    analyze_full_history_peaks_valleys(tk)
