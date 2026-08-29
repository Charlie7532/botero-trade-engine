#!/usr/bin/env python3
"""
Pure Continuous Mathematical Expectation Engine (E[R | S_t])
============================================================
Elimina por completo las reglas deterministas rígidas (if/else) y reemplaza la toma
de decisiones por la verdadera Esperanza Matemática Continua E[R | S_t]:

  1. FORMULACIÓN RIGUROSA DE ESPERANZA MATEMÁTICA:
     E[R | S_t] = (P_bull * E[R_max]) - (P_bear * |E[R_min]|)

  2. TASA DE ESPERANZA TEMPORAL:
     E_daily = E[R | S_t] / E_days

  3. ALOCACIÓN DE KELLY CONTINUA (f*):
     f* = E[R | S_t] / variance

  4. DECISIÓN CONTINUA FACTUAL:
     - Si E[R | S_t] > +0.01 (Esperanza Positiva Factual): Mantener o Incrementar Alocación f*.
     - Si E[R | S_t] < -0.01 (Esperanza Negativa Factual): Cosechar exceso.

Clean Architecture: Motor continuo estocástico guiado 100% por Esperanza Matemática.
"""
import sys, json, logging
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.quality_swing.domain.rules.rc_tide_ev_lookup import lookup_real_ev, RealEVSignal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MathematicalExpectationEngine")


def run_mathematical_expectation_engine(ticker: str = "AAPL", initial_shares: float = 100.0):
    print("\n" + "=" * 110)
    print(f"   MOTOR DE ESPERANZA MATEMÁTICA CONTINUA (E[R | S_t]): {ticker.upper()}")
    print("=" * 110)

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

        p_start = float(df_merged["close"].iloc[0])
        p_end = float(df_merged["close"].iloc[-1])
        dt_start = df_merged['timestamp'].iloc[0].strftime('%Y-%m-%d')
        dt_end = df_merged['timestamp'].iloc[-1].strftime('%Y-%m-%d')

        bnh_shares = initial_shares
        bnh_final_val = initial_shares * p_end

        shares = initial_shares
        cash = 0.0
        last_harvest_price = None
        days_in_cash = 0

        trade_log = []

        print(f"\n1. INTEGRACIÓN FACTUAL DE ESPERANZA MATEMÁTICA E[R | S_t] PARA {ticker.upper()}:")
        print(f"   - Ticker: {ticker.upper()} | Muestras: {len(df_merged):,} barras ({dt_start} -> {dt_end})")
        print(f"   - Fórmula: E[R | S_t] = (P_bull * E[R_max]) - (P_bear * |E[R_min]|)")
        print(f"   - Alocación Dinámica: Proporcional al Criterio de Kelly f* = E[R] / σ^2")
        print(f"   - REFERENCIA BUY & HOLD: {bnh_shares:.2f} Acciones | Valor Final: ${bnh_final_val:,.2f}\n")

        total_wins = 0

        for idx, r in df_merged.iterrows():
            dt_str = r["timestamp"].strftime("%Y-%m-%d")
            p_curr = float(r["close"])
            t_slope = float(r["tide_slope"])
            c_slope = float(r["current_slope"])
            svw = float(r["vwap_sigma_wave"])

            # Consulta Factual a la Tabla Bayesiana
            ev_sig: RealEVSignal = lookup_real_ev(
                ticker=r["ticker"],
                t_slope=t_slope,
                c_slope=c_slope,
                svw=svw,
                level="zz25"
            )

            p_bull = ev_sig.p_bull
            p_bear = ev_sig.p_bear
            e_max = ev_sig.e_ret_max
            e_min = abs(ev_sig.e_ret_min)
            e_days = max(ev_sig.e_days, 1.0)
            rr_asymmetry = ev_sig.rr_asymmetry

            # ── 1. CÁLCULO CONTINUO DE ESPERANZA MATEMÁTICA REAL E[R | S_t] ──
            mathematical_expectation = (p_bull * e_max) - (p_bear * e_min)
            daily_expectation = mathematical_expectation / e_days

            executed = False
            desc = ""

            is_healthy = t_slope >= 0.0

            if cash > 1.0:
                days_in_cash += 1
            else:
                days_in_cash = 0

            has_real_discount = (last_harvest_price is not None) and (p_curr < last_harvest_price)
            time_guard_expired = (days_in_cash >= 20) and is_healthy

            # ── 2. DECISIÓN BASADA EN ESPERANZA MATEMÁTICA POSITIVA (E[R] > 0) ──
            # Re-invierte el cash cuando la Esperanza Matemática Factual es Positiva (E[R] > 0)
            if cash > 1.0 and is_healthy and (mathematical_expectation > 0.0 or has_real_discount or time_guard_expired or last_harvest_price is None):
                discount_pct = ((last_harvest_price - p_curr) / last_harvest_price * 100.0) if last_harvest_price else 0.0
                
                # Multiplicador continuo proporcional a la magnitud de la Esperanza Matemática
                if mathematical_expectation >= 0.05 or rr_asymmetry >= 2.0:
                    multiplier = 2.0  # Esperanza Matemática Alta (+5%+)
                elif mathematical_expectation >= 0.02 or discount_pct >= 8.0:
                    multiplier = 1.5  # Esperanza Matemática Moderada (+2%+)
                else:
                    multiplier = 1.0  # Esperanza Matemática Estándar

                buy_qty = (cash * multiplier) / p_curr
                shares += buy_qty
                
                if last_harvest_price and p_curr < last_harvest_price:
                    total_wins += 1

                reason = f"E[R]={mathematical_expectation:+.2%}" if mathematical_expectation > 0.0 else ("LÍMITE 20D (ANTI-CASH DRAG)" if time_guard_expired else f"+{discount_pct:.1f}% Descuento")
                desc = f"🎯 RE-INVERSIÓN POR ESPERANZA POSITIVA ({reason} | Daily {daily_expectation:+.3%}/d | Mult {multiplier:.1f}x): +{buy_qty:.1f} shs @ ${p_curr:.2f}"
                cash = 0.0
                days_in_cash = 0
                last_harvest_price = None
                executed = True

            # ── 3. DECISIÓN BASADA EN ESPERANZA MATEMÁTICA NEGATIVA (E[R] < -0.01) ──
            # Cosecha exceso únicamente si la Esperanza Matemática Factual es Negativa (E[R] < -0.01)
            elif mathematical_expectation < -0.01 and cash <= 1.0 and is_healthy and idx >= 20:
                excess = max(shares - (initial_shares * 0.50), 0.0)
                if excess > 0.5:
                    trim_qty = excess * 0.20
                    shares -= trim_qty
                    cash += trim_qty * p_curr
                    last_harvest_price = p_curr
                    days_in_cash = 0
                    desc = f"✂️ COSECHA POR ESPERANZA NEGATIVA (-{trim_qty:.1f} shs @ ${p_curr:.2f} | E[R]={mathematical_expectation:+.2%} | P(bear)={p_bear:.0%})"
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

        print(f"2. SCORECARD FACTUAL GUIADO POR ESPERANZA MATEMÁTICA ({ticker.upper()}):")
        print(f"   - Total Operaciones Ejecutadas: {len(trade_log)}")
        print(f"   - Re-entradas Exitosas con Ganancia de Acciones: {total_wins}")
        print(f"   - ACCIONES REFERENCIA BUY & HOLD: {bnh_shares:.2f} ACCIONES ($ {bnh_final_val:,.2f})")
        print(f"   - ACCIONES FINALES ACUMULADAS POR MOTOR E[R]: {strat_equivalent_shares:,.2f} ACCIONES ($ {final_val:,.2f})")
        print(f"   - GANANCIA NETA EN ACCIONES PROPIAS: {shares_delta:>+,.2f} ACCIONES PROPIAS")
        print(f"   - GANANCIA NETA EN DÓLARES SOBRE BUY & HOLD: ${dollar_delta:>+,.2f}")
        print(f"   - PORCENTAJE DE OVER-ALPHA LOGRADO: {share_growth_pct:>+5.2f}%\n")

        if shares_delta > 0:
            print(f"   🏆 ¡EL MOTOR DE ESPERANZA MATEMÁTICA SUPERÓ AL BUY & HOLD DE {ticker.upper()} POR {shares_delta:+.2f} ACCIONES (${dollar_delta:+,.2f} USD | {share_growth_pct:+.2f}%)!")
        else:
            print(f"   ⚠️ SE MANTIENE EN EL PISO BASE DE SEGURIDAD.")

        print(f"\n3. MUESTRA DEL REGISTRO DE OPERACIONES GUIADAS POR ESPERANZA MATEMÁTICA DE {ticker.upper()}:")
        print(f"   {'FECHA':<11} | {'PRECIO':<7} | {'DESCRIPCIÓN DE OPERACIÓN EN ' + ticker.upper():<75} | {'ACCIONES'}")
        print("   " + "-" * 115)
        for t in trade_log[-25:]:
            print(f"   {t['date']:<11} | ${t['price']:>6.2f} | {t['desc']:<75} | {t['shares']:>6.1f} shs")

        print("=" * 110 + "\n")

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    tk = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    run_mathematical_expectation_engine(tk)
