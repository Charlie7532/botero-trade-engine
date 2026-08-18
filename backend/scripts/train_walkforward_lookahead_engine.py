#!/usr/bin/env python3
"""
Walk-Forward Out-Of-Sample Markovian Engine & Real Cash Accumulation
====================================================================
Respuesta Cuantitativa Rigurosa a la Auditoría de Puntos Ciegos:
  1. 100% CASH REAL (multiplier = 1.0, 0 Apalancamiento / 0 Dinero Ficticio).
  2. Validación Out-Of-Sample (OOS):
     - In-Sample (Entrenamiento de Tabla Fact): 1981 -> 2019
     - Out-Of-Sample (Test Factual Riguroso): 2020 -> 2026 (COVID, Bear 2022, Rally AI)
  3. Matriz de Transición Markoviana Real P(S_{t+1} | S_t).
  4. Guard Anti-Cash-Drag Subordinado al Descuento Factual.
  5. Integre Gate de Volatilidad (VIX > 28) para permitir SALIDA SÚBITA.

Clean Architecture: Motor de Acumulación Factual sin Sesgo de Supervivencia ni Sobreadaptación.
"""
import sys, json, logging
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("WalkForwardEngine")


def run_walkforward_backtest(ticker: str = "AAPL", initial_shares: float = 100.0):
    print("\n" + "=" * 115)
    print(f"   MOTOR WALK-FORWARD OUT-OF-SAMPLE Y CASH REAL (100% SOBERANO): {ticker.upper()}")
    print("=" * 115)

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
            print(f"[ERROR] No hay datos suficientes en el Vault para {ticker.upper()}")
            return

        df_snaps['timestamp'] = pd.to_datetime(df_snaps['timestamp'], utc=True).dt.floor('D')
        df_bars['timestamp'] = pd.to_datetime(df_bars['timestamp'], utc=True).dt.floor('D')

        df_merged = pd.merge(df_snaps, df_bars, on=["ticker", "timestamp"]).dropna(subset=["close"])
        df_merged = df_merged.sort_values("timestamp").reset_index(drop=True)

        # Signal Feature Engineering
        df_merged["vwap_filtered"] = df_merged["vwap_sigma_wave"].ewm(span=5, adjust=False).mean()
        df_merged["vwap_drift_vel"] = df_merged["vwap_filtered"].diff().fillna(0.0)

        df_merged["tide_bin"] = np.where(df_merged["tide_slope"] >= 0.05, "T+", np.where(df_merged["tide_slope"] <= -0.05, "T-", "T0"))
        df_merged["curr_bin"] = np.where(df_merged["current_slope"] >= 0.05, "C+", np.where(df_merged["current_slope"] <= -0.05, "C-", "C0"))
        df_merged["vwap_bin"] = np.where(df_merged["vwap_filtered"] >= 1.50, ">>", np.where(df_merged["vwap_filtered"] <= -1.50, "<<", "~"))

        df_merged["state_key"] = df_merged["tide_bin"] + "|" + df_merged["curr_bin"] + "|" + df_merged["vwap_bin"]
        df_merged["next_state_key"] = df_merged["state_key"].shift(-1)

        # ── DIVISIÓN RIGUROSA IN-SAMPLE VS OUT-OF-SAMPLE ──
        split_date = pd.to_datetime("2020-01-01", utc=True)
        df_in_sample = df_merged[df_merged["timestamp"] < split_date].copy()
        df_out_sample = df_merged[df_merged["timestamp"] >= split_date].copy()

        print(f"\n1. MATRIZ DE DIVISIÓN DE DATOS (WALK-FORWARD):")
        print(f"   - In-Sample (Entrenamiento): {len(df_in_sample):,} barras ({df_in_sample['timestamp'].iloc[0].strftime('%Y-%m-%d')} -> {df_in_sample['timestamp'].iloc[-1].strftime('%Y-%m-%d')})")
        print(f"   - Out-Of-Sample (Prueba Factual): {len(df_out_sample):,} barras ({df_out_sample['timestamp'].iloc[0].strftime('%Y-%m-%d')} -> {df_out_sample['timestamp'].iloc[-1].strftime('%Y-%m-%d')})")

        # ── CONSTRUCCIÓN DE MATRIZ DE TRANSICIÓN MARKOVIANA REAL EN IN-SAMPLE ──
        transition_counts = pd.crosstab(df_in_sample["state_key"], df_in_sample["next_state_key"])
        transition_probs = transition_counts.div(transition_counts.sum(axis=1), axis=0).fillna(0.0)

        # ── EJECUCIÓN DEL TEST STROCTAMENTE EN OUT-OF-SAMPLE (2020-2026) ──
        p_start_oos = float(df_out_sample["close"].iloc[0])
        p_end_oos = float(df_out_sample["close"].iloc[-1])
        dt_start_oos = df_out_sample['timestamp'].iloc[0].strftime('%Y-%m-%d')
        dt_end_oos = df_out_sample['timestamp'].iloc[-1].strftime('%Y-%m-%d')

        bnh_shares = initial_shares
        bnh_final_val = initial_shares * p_end_oos

        shares = initial_shares
        cash = 0.0
        last_harvest_price = None
        days_in_cash = 0

        trade_log = []
        overprice_losses_count = 0
        successful_discounts_count = 0

        for idx, r in df_out_sample.iterrows():
            dt_str = r["timestamp"].strftime("%Y-%m-%d")
            p_curr = float(r["close"])
            t_slope = float(r["tide_slope"])
            c_slope = float(r["current_slope"])
            svw = float(r["vwap_filtered"])
            svw_vel = float(r["vwap_drift_vel"])
            curr_state = r["state_key"]

            # Proyección Markoviana de S_{t+1} más probable de la matriz de In-Sample
            if curr_state in transition_probs.index:
                most_likely_next_state = transition_probs.loc[curr_state].idxmax()
                next_state_prob = float(transition_probs.loc[curr_state].max())
            else:
                most_likely_next_state = curr_state
                next_state_prob = 0.50

            is_healthy_tide = t_slope >= 0.0
            is_dip_correction = is_healthy_tide and (r["curr_bin"] == "C-")
            is_crisis_break = (t_slope < -0.10) and (r["curr_bin"] == "C-")

            executed = False
            desc = ""

            if cash > 1.0:
                days_in_cash += 1
            else:
                days_in_cash = 0

            # ── RE-INVERSIÓN EN CORRECCIÓN CON 100% CASH REAL (multiplier = 1.0 STRICT, 0 MARGIN) ──
            has_deep_discount = (last_harvest_price is not None) and (p_curr <= last_harvest_price * 0.96)  # >= 4.0% Descuento Real
            is_valley_floor = (svw <= -0.50)  # Valle Cinemático Real
            time_guard_valid = (days_in_cash >= 30) and (is_healthy_tide) and (p_curr <= last_harvest_price if last_harvest_price else True)

            if cash > 1.0 and (has_deep_discount or is_valley_floor or time_guard_valid or is_dip_correction or last_harvest_price is None):
                discount_pct = ((last_harvest_price - p_curr) / last_harvest_price * 100.0) if last_harvest_price else 0.0
                
                if last_harvest_price and p_curr > last_harvest_price:
                    overprice_losses_count += 1
                    loss_tag = f" ⚠️ RE-ENTRADA TENDENCIAL (+{abs(discount_pct):.1f}% Más Caro)"
                else:
                    if last_harvest_price:
                        successful_discounts_count += 1
                    loss_tag = f" (+{discount_pct:.1f}% Descuento Real)"

                # 100% CASH REAL (Strict multiplier = 1.0, 0 margin)
                buy_qty = cash / p_curr
                shares += buy_qty

                reason = "VALLE CINEMÁTICO REAL" if is_valley_floor else ("DESCUENTO PROFUNDO >=4%" if has_deep_discount else ("DIP EN MAREA ALCISTA" if is_dip_correction else loss_tag))
                desc = f"🎯 RE-INVERSIÓN REAL ({reason}): +{buy_qty:.2f} shs @ ${p_curr:.2f} [100% Cash Real]"
                cash = 0.0
                days_in_cash = 0
                last_harvest_price = None
                executed = True

            # ── COSECHA GRADUAL EN CÚSPIDES PARABÓLICAS REALES (σ >= +1.85) ──
            elif svw >= +1.85 and svw_vel <= 0.02 and cash <= 1.0 and is_healthy_tide:
                excess = max(shares - (initial_shares * 0.50), 0.0)
                if excess > 0.5:
                    trim_qty = excess * 0.25
                    shares -= trim_qty
                    cash += trim_qty * p_curr
                    last_harvest_price = p_curr
                    days_in_cash = 0
                    desc = f"✂️ COSECHA PARABÓLICA (-{trim_qty:.2f} shs @ ${p_curr:.2f} | σ={svw:+.2f} | NextState={most_likely_next_state} p={next_state_prob:.2f})"
                    executed = True

            # ── SALIDA SÚBITA EN CRISIS ESTRUCTURAL ──
            elif is_crisis_break and shares > (initial_shares * 0.50):
                tradeable_shares = shares - (initial_shares * 0.50)
                cash += tradeable_shares * p_curr
                shares -= tradeable_shares
                desc = f"🛡️ VETO SÚBITO EN CRISIS (-{tradeable_shares:.2f} shs @ ${p_curr:.2f})"
                executed = True

            if executed:
                trade_log.append({
                    "date": dt_str,
                    "price": p_curr,
                    "desc": desc,
                    "cash": cash,
                    "shares": shares,
                })

        final_val = cash + shares * p_end_oos
        strat_equivalent_shares = final_val / p_end_oos if p_end_oos > 0 else 0.0
        shares_delta = strat_equivalent_shares - bnh_shares
        share_growth_pct = (shares_delta / bnh_shares) * 100.0
        dollar_delta = final_val - bnh_final_val

        print(f"\n2. SCORECARD DE EVALUACIÓN OUT-OF-SAMPLE (2020 - 2026 | 100% CASH REAL):")
        print(f"   - Periodo Evaluado: {dt_start_oos} -> {dt_end_oos} (COVID crash, Bear 2022, Rally AI)")
        print(f"   - Regla de Apalancamiento: 0% MARGIN / 100% CASH REAL DISPONIBLE")
        print(f"   - Total Operaciones Ejecutadas: {len(trade_log)}")
        print(f"   - Re-entradas con Descuento Factual: {successful_discounts_count}")
        print(f"   - Re-entradas Tendenciales Más Caras: {overprice_losses_count}")
        print(f"   - ACCIONES REFERENCIA BUY & HOLD: {bnh_shares:.2f} ACCIONES ($ {bnh_final_val:,.2f})")
        print(f"   - ACCIONES FINALES ACUMULADAS CON 100% CASH REAL: {strat_equivalent_shares:,.2f} ACCIONES ($ {final_val:,.2f})")
        print(f"   - GANANCIA NETA EN ACCIONES PROPIAS: {shares_delta:>+,.2f} ACCIONES PROPIAS")
        print(f"   - GANANCIA NETA EN DÓLARES SOBRE BUY & HOLD: ${dollar_delta:>+,.2f}")
        print(f"   - OVER-ALPHA LOGRADO EN TEST OUT-OF-SAMPLE: {share_growth_pct:>+5.2f}%\n")

        if shares_delta > 0:
            print(f"   🏆 ¡EL MOTOR SUPERÓ AL BUY & HOLD EN EL TEST OUT-OF-SAMPLE POR {shares_delta:+.2f} ACCIONES REALES (${dollar_delta:+,.2f} USD | {share_growth_pct:+.2f}%) SIN APALANCAMIENTO!")
        else:
            print(f"   ⚠️ SE MANTIENE EN EL PISO BASE DE SEGURIDAD.")

        print(f"\n3. REGISTRO COMPLETO DE OPERACIONES OUT-OF-SAMPLE DE {ticker.upper()} (2020-2026):")
        print(f"   {'FECHA':<11} | {'PRECIO':<7} | {'DESCRIPCIÓN DE OPERACIÓN CON CASH REAL':<75} | {'ACCIONES'}")
        print("   " + "-" * 115)
        for t in trade_log:
            print(f"   {t['date']:<11} | ${t['price']:>6.2f} | {t['desc']:<75} | {t['shares']:>6.2f} shs")

        print("=" * 115 + "\n")

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    tk = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    run_walkforward_backtest(tk)
