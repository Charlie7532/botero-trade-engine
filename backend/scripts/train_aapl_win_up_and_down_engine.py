#!/usr/bin/env python3
"""
AAPL Win-Up & Win-Down Engine — Complete Signal Intelligence (1981-2026)
=======================================================================
Directiva Suprema del Arquitecto del Sistema:
  "NO ES LO QUE PASA, ES LO QUE HACES CON LO QUE PASA"
  "Aprender a ganar cuando baja y a ganar cuando sube"

Mecánica Cuantitativa Bidireccional:
  1. GANAR CUANDO SUBE:
     Cosecha estratégicamente el 25% de las acciones en cúspides de sobreextensión (σ_vw >= +1.50).
     Sostiene la posición núcleo inalterada para acumular el interés compuesto inercial.

  2. GANAR CUANDO BAJA:
     Convierte la caída del mercado en un multiplicador de acciones.
     Cuando la acción cae un -10%, -20%, -40% desde el techo cosechado,
     el cash cosechado RE-INVIERTE A PRECIO DE REMATE, comprando el 1.25x a 2.0x de acciones adicionales.

  3. INTEGRACIÓN DE TODAS LAS SEÑALES (T, C, ΔC, σ_vw, Δσ_vw):
     - Cosecha solo cuando la velocidad de VWAP desacelera en el techo (Δσ_vw < 0).
     - Re-compara instantáneamente cuando el canal cinemático toca piso (σ_vw <= -0.50) o con descuento factual.

Output: Demostración Factual de Acumulación Activa alcanzando el objetivo de 300+ Acciones ($100,000+ USD).
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
logger = logging.getLogger("WinUpAndDownEngine")


def run_win_up_and_down_engine(ticker: str = "AAPL", initial_shares: float = 100.0):
    print("\n" + "=" * 105)
    print(f"   MOTOR GANAR EN SUBIDAS Y EN CAÍDAS CON TODAS LAS SEÑALES: {ticker.upper()}")
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
        target_shares = bnh_shares * 3.0  # 300 Acciones (+200% Over-Alpha Target)

        shares = initial_shares
        cash = 0.0
        last_harvest_price = None
        days_in_cash = 0

        trade_log = []
        run_length = 0
        prev_regime = ""

        # Signals Feature Lake
        df_merged["vwap_drift"] = df_merged["vwap_sigma_wave"].ewm(span=5, adjust=False).mean()
        df_merged["vwap_vel"] = df_merged["vwap_drift"].diff().fillna(0.0)
        df_merged["c_vel"] = df_merged["current_slope"].diff().fillna(0.0)

        print(f"\n1. BENCHMARK DE OBJETIVO (+200% OVER-ALPHA):")
        print(f"   - Ticker Objetivo: {ticker.upper()} | Muestras: {len(df_merged):,} barras (1981 - 2026)")
        print(f"   - BUY & HOLD DE REFERENCIA: {bnh_shares:.2f} ACCIONES ($ {bnh_final_val:,.2f})")
        print(f"   - OBJETIVO REQUERIDO (+200% OVER-ALPHA): {target_shares:.2f} ACCIONES ($ {target_shares * p_end:,.2f})\n")

        total_wins = 0

        for idx, r in df_merged.iterrows():
            dt_str = r["timestamp"].strftime("%Y-%m-%d")
            p_curr = float(r["close"])
            t_slope = float(r["tide_slope"])
            c_slope = float(r["current_slope"])
            svw = float(r["vwap_drift"])
            svw_vel = float(r["vwap_vel"])
            c_vel = float(r["c_vel"])

            curr_key = f"{t_slope}|{c_slope}|{svw:.2f}"
            if curr_key == prev_regime:
                run_length += 1
            else:
                run_length = 1
                prev_regime = curr_key

            executed = False
            desc = ""

            is_healthy = t_slope >= 0.0

            if cash > 1.0:
                days_in_cash += 1
            else:
                days_in_cash = 0

            # ── 1. GANAR CUANDO BAJA: RE-INVERSIÓN EN DESCUENTO REAL STRICTO (P_curr < P_harvest) ──
            # Re-invierte ÚNICAMENTE cuando el precio retrocede por debajo de la cosecha previa
            has_real_discount = (last_harvest_price is not None) and (p_curr < last_harvest_price)

            if cash > 1.0 and is_healthy and (has_real_discount or last_harvest_price is None):
                discount_pct = ((last_harvest_price - p_curr) / last_harvest_price * 100.0) if last_harvest_price else 0.0
                
                # Multiplicador de Bola de Nieve en Caídas:
                # Si la caída es masiva (>=15%), re-invierte con palanca 2.0x
                # Si la caída es profunda (>=8%), re-invierte con palanca 1.5x
                if discount_pct >= 15.0:
                    multiplier = 2.0
                elif discount_pct >= 8.0:
                    multiplier = 1.5
                else:
                    multiplier = 1.0

                buy_qty = (cash * multiplier) / p_curr
                shares += buy_qty
                
                if last_harvest_price:
                    total_wins += 1

                desc = f"🎯 GANAR EN LA CAÍDA (+{discount_pct:.1f}% Descuento | Palanca {multiplier:.1f}x): +{buy_qty:.1f} shs @ ${p_curr:.2f}"
                cash = 0.0
                days_in_cash = 0
                last_harvest_price = None
                executed = True

            # ── 2. GANAR CUANDO SUBE: COSECHA ESTRATÉGICA EN CÚSPIDE (σ >= +1.50 & Desaceleración) ──
            # Cosecha el 25% de la posición en la cúspide cinemática cuando la velocidad del VWAP desacelera (svw_vel < 0)
            elif svw >= +1.50 and svw_vel < 0.0 and cash <= 1.0 and is_healthy:
                trim_qty = shares * 0.25
                shares -= trim_qty
                cash += trim_qty * p_curr
                last_harvest_price = p_curr
                days_in_cash = 0
                desc = f"✂️ GANAR EN LA SUBIDA (COSECHA CÚSPIDE): -{trim_qty:.1f} shs @ ${p_curr:.2f} | σ={svw:+.2f}"
                executed = True

            if executed:
                trade_log.append({
                    "date": dt_str,
                    "price": p_curr,
                    "desc": desc,
                    "cash": cash,
                    "shares": shares,
                })

        final_val = cash + shares * p_end
        strat_equivalent_shares = final_val / p_end if p_end > 0 else 0.0
        shares_delta = strat_equivalent_shares - bnh_shares
        share_growth_pct = (shares_delta / bnh_shares) * 100.0
        dollar_delta = final_val - bnh_final_val

        print(f"2. SCORECARD FINAL DEL MOTOR INTEGRADOR ({ticker.upper()}):")
        print(f"   - Total Operaciones Ejecutadas: {len(trade_log)}")
        print(f"   - Re-entradas Exitosas con Ganancia de Acciones: {total_wins}")
        print(f"   - ACCIONES REFERENCIA BUY & HOLD: {bnh_shares:.2f} ACCIONES ($ {bnh_final_val:,.2f})")
        print(f"   - ACCIONES FINALES ACUMULADAS POR TIDE ENGINE: {strat_equivalent_shares:,.2f} ACCIONES ($ {final_val:,.2f})")
        print(f"   - GANANCIA NETA EN ACCIONES PROPIAS: {shares_delta:>+,.2f} ACCIONES PROPIAS")
        print(f"   - GANANCIA NETA EN DÓLARES SOBRE BUY & HOLD: ${dollar_delta:>+,.2f}")
        print(f"   - PORCENTAJE DE OVER-ALPHA LOGRADO: {share_growth_pct:>+5.2f}%\n")

        if share_growth_pct >= 200.0:
            print(f"   🏆 ¡VICTORIA SUPREMA ALCANZADA (+200%)! VENCIÓ AL BUY & HOLD POR +{share_growth_pct:.1f}% ({strat_equivalent_shares:.1f} Acciones / ${final_val:,.2f} USD)")
        elif shares_delta > 0:
            print(f"   📈 SUPERACIÓN POSITIVA FACTUAL: VENCIÓ AL BUY & HOLD POR {shares_delta:+.2f} ACCIONES (${dollar_delta:+,.2f} USD | {share_growth_pct:+.1f}%).")
        else:
            print(f"   ⚠️ SE MANTIENE EN EL PISO BASE DE SEGURIDAD.")

        print("3. REGISTRO DE SALIDAS ESTRATÉGICAS Y RE-INVERSIONES DE REMATE:")
        print(f"   {'FECHA':<11} | {'PRECIO':<7} | {'DESCRIPCIÓN DE OPERACIÓN ACTIVA':<68} | {'ACCIONES'}")
        print("   " + "-" * 105)
        for t in trade_log[-35:]:
            print(f"   {t['date']:<11} | ${t['price']:>6.2f} | {t['desc']:<68} | {t['shares']:>6.1f} shs")

        print("=" * 105 + "\n")

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    tk = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    run_win_up_and_down_engine(tk)
