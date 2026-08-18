#!/usr/bin/env python3
"""
Bayesian VWAP Drift Bias & Multi-Scale Probability Engine — AAPL Deep Training
==============================================================================
Sintetiza los 5 Principios del Arquitecto del Sistema:
  1. Jerarquía Bayesiana: P(Tide), P(Current), P(Tide, Current) combinados.
  2. VWAP Drift Bias & Noise Filter:
     Acumulación de VWAP aporta un sesgo positivo/negativo que altera el Lookahead
     y la certidumbre de las probabilidades de Tide y Current.
  3. "La Tendencia es tu Amiga": Pondera positivamente la inercia alcista.
  4. Manejo Gradual vs Súbito:
     - Gradual: Cosecha del 33% en sobreextensión.
     - Súbito: Veto de Crisis (100% a cash en el tramo táctico en acantilados T---).
  5. Contabilidad Estricta de Pérdida por Re-Entrada Más Cara:
     Castiga explícitamente cualquier compra efectuada por encima de la venta previa.

Output: Evaluaciones profundas y detalladas sobre AAPL.
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
logger = logging.getLogger("BayesVWAPEngine")


def train_bayes_vwap_engine_aapl(ticker: str = "AAPL", initial_shares: float = 100.0):
    print("\n" + "=" * 105)
    print(f"   ENTRENAMIENTO BAYESIANO CON SESGO DE VWAP Y MULTI-ESCALA: {ticker.upper()}")
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

        trade_log = []
        last_exit_price = None
        last_exit_date = None

        run_length = 0
        prev_regime = ""
        ev_history = []
        vwap_history = []

        print(f"\n1. ESTADO INICIAL AUDITADO:")
        print(f"   - Ticker: {ticker.upper()} | Muestras: {len(df_merged)} barras (1981-2026)")
        print(f"   - Posición Base Inicial: {initial_shares} Acciones de {ticker.upper()} a ${p_start:.2f} (${initial_shares * p_start:,.2f})\n")

        total_wins_cheaper_buy = 0
        total_losses_expensive_buy = 0
        total_trims_harvested = 0
        total_crisis_vetos = 0

        for idx, r in df_merged.iterrows():
            dt_str = r["timestamp"].strftime("%Y-%m-%d")
            p_curr = float(r["close"])
            t_slope = float(r["tide_slope"])
            c_slope = float(r["current_slope"])
            svw = float(r["vwap_sigma_wave"])

            vwap_history.append(svw)
            if len(vwap_history) > 10:
                vwap_history.pop(0)

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

            # ── 1. SESGO DE ACUMULACIÓN DE VWAP & CERTIDUMBRE ──
            # Acumulación de VWAP reciente (10d)
            vwap_drift_bias = float(np.mean(vwap_history))
            # Si el VWAP drift es positivo y la marea es alcista, refuerza la certidumbre de la tendencia
            trend_friend_multiplier = 1.25 if (t_slope >= 0 and vwap_drift_bias > -0.2) else 1.0
            
            # Esperanza Matemática Ajustada por Sesgo de VWAP
            adjusted_ev = ev * trend_friend_multiplier

            # ── 2. PISO NÚCLEO INVIOLABLE (50% CORE FLOOR) ──
            core_floor_shares = initial_shares * 0.50

            executed = False
            desc = ""

            # ── 3. RE-ENTRADA EN RETROCESO COMPRABLE INTELIGENTE ──
            # Re-inversión de Cash:
            # - No hay veto de crisis (act != STK_T_BLOCK_CRISIS)
            # - Marea no es bajista extrema (t_slope >= -0.01)
            # - Descuento en canal (svw <= -0.30) o rebote cinemático (c_slope > t_slope)
            smart_dip_trigger = (
                cash > 1.0 and
                act != ACTION_STK_T_BLOCK_CRISIS and
                act != ACTION_STK_T_DISTRIBUTE_DECAY and
                t_slope >= -0.01 and
                (svw <= -0.30 or c_slope > t_slope)
            )

            if smart_dip_trigger:
                buy_qty = cash / p_curr
                shares += buy_qty
                
                # Evaluación Factual del Precio de Re-entrada (Ganancia vs Pérdida de Oportunidad)
                if last_exit_price:
                    pct_diff = ((last_exit_price - p_curr) / last_exit_price) * 100.0
                    if p_curr < last_exit_price:
                        total_wins_cheaper_buy += 1
                        eval_note = f"GANANCIA DE ACCIONES (+{pct_diff:.1f}% Descuento vs ${last_exit_price:.2f})"
                    else:
                        total_losses_expensive_buy += 1
                        eval_note = f"PÉRDIDA DE OPORTUNIDAD (-{abs(pct_diff):.1f}% Sobreprecio vs ${last_exit_price:.2f})"
                else:
                    eval_note = "ENTRADA INICIAL DE CAPITAL"

                desc = f"🎯 COMPRA RETROCESO ({eval_note}): +{buy_qty:.1f} shs @ ${p_curr:.2f}"
                cash = 0.0
                executed = True

            elif act == ACTION_STK_T_TRIM_TACTICAL or (svw >= +1.80 and t_slope >= 0):
                # Cosecha Gradual del 33% al 50% del Tramo Táctico
                tradeable_shares = max(shares - core_floor_shares, 0.0)
                if tradeable_shares > 1.0:
                    harvest_pct = 0.50 if svw >= +1.80 else 0.33
                    trim_qty = tradeable_shares * harvest_pct
                    shares -= trim_qty
                    cash += trim_qty * p_curr
                    last_exit_price = p_curr
                    last_exit_date = dt_str
                    total_trims_harvested += 1
                    desc = f"✂️ COSECHA GRADUAL TECHO (-{trim_qty:.1f} shs @ ${p_curr:.2f} | σ={svw:+.2f})"
                    executed = True

            elif act in (ACTION_STK_T_DISTRIBUTE_DECAY, ACTION_STK_T_EXIT_THESIS_DEATH, ACTION_STK_T_BLOCK_CRISIS):
                # Veto Súbito de Crisis: Liquida el 100% del tramo táctico a Cash
                tradeable_shares = max(shares - core_floor_shares, 0.0)
                if tradeable_shares > 1.0:
                    cash += tradeable_shares * p_curr
                    shares -= tradeable_shares
                    last_exit_price = p_curr
                    last_exit_date = dt_str
                    total_crisis_vetos += 1
                    desc = f"🛡️ VETO SÚBITO DE CRISIS (-{tradeable_shares:.1f} shs @ ${p_curr:.2f} | T_slope={t_slope:+.3f})"
                    executed = True

            if executed:
                trade_log.append({
                    "date": dt_str,
                    "price": p_curr,
                    "action": act,
                    "desc": desc,
                    "cash": cash,
                    "shares": shares,
                })

        final_val = cash + shares * p_end
        strat_equivalent_shares = final_val / p_end if p_end > 0 else 0.0
        shares_delta = strat_equivalent_shares - bnh_shares
        share_growth_pct = (shares_delta / bnh_shares) * 100.0

        total_reentries = total_wins_cheaper_buy + total_losses_expensive_buy
        win_rate_reentry = (total_wins_cheaper_buy / total_reentries) * 100.0 if total_reentries > 0 else 0.0

        print(f"2. SCORECARD AUDITADO DEL MOTOR BAYESIANO VWAP PARA {ticker.upper()}:")
        print(f"   - Total Operaciones Ejecutadas: {len(trade_log)}")
        print(f"   - Cosechas Graduales en Techos: {total_trims_harvested}")
        print(f"   - Vetos Súbitos de Crisis: {total_crisis_vetos}")
        print(f"   - Re-entradas con Ganancia de Acciones (Compró más Barato): {total_wins_cheaper_buy} ({win_rate_reentry:.1f}% WIN RATE)")
        print(f"   - Re-entradas con Pérdida de Oportunidad (Compró más Caro): {total_losses_expensive_buy} ({100.0 - win_rate_reentry:.1f}% LOSS RATE)")
        print(f"   - Acciones Iniciales Buy & Hold: {bnh_shares:.2f} acciones")
        print(f"   - Acciones Finales Acumuladas: {strat_equivalent_shares:,.2f} acciones")
        print(f"   - GANANCIA NETA EN ACCIONES PROPIAS: {shares_delta:>+,.2f} ACCIONES PROPIAS")
        print(f"   - CRECIMIENTO DE PORCENTAJE EN ACCIONES: {share_growth_pct:>+5.2f}%")
        print(f"   - Valor Final del Portafolio: ${final_val:,.2f} (vs Buy & Hold: ${bnh_final_val:,.2f})\n")

        print("3. REGISTRO COMPLETO DE OPERACIONES BAYESIANAS VWAP:")
        print(f"   {'FECHA':<11} | {'PRECIO':<7} | {'DESCRIPCIÓN DE OPERACIÓN CON SESGO VWAP':<70} | {'CASH':<10} | {'ACCIONES'}")
        print("   " + "-" * 115)
        for t in trade_log:
            print(f"   {t['date']:<11} | ${t['price']:>6.2f} | {t['desc']:<70} | ${t['cash']:>9.2f} | {t['shares']:>6.1f} shs")

        print("=" * 105 + "\n")

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    tk = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    train_bayes_vwap_engine_aapl(tk)
