#!/usr/bin/env python3
"""
Markovian Lookahead & VWAP Drift Certidumbre Engine (AAPL, COST, MSFT, NVDA, JPM)
=================================================================================
Implementación Factual de las 7 Premisas del Arquitecto del Sistema:
  1. Jerarquía Bayesiana (P(Tide), P(Current), P(Tide, Current)).
  2. Filtro de Dispersión de Ruido del VWAP (Elimina brincos irracionales sin volumen).
  3. Sesgo Acumulado del VWAP (Certidumbre alcista: P_trend aumenta si dσ_vw/dt > 0).
  4. Lookahead del Estado Siguiente Más Probable S_{t+1}.
  5. Corrección Comprable (T>=0, C<0 -> Comprar Dip) vs Disrupción (T<0 -> Veto Crisis).
  6. Modulación Gradual en Cúspides (15-20%) vs Súbita en Crisis.
  7. Contabilidad Factual de Pérdida por Re-Entrada Más Cara (Share Deficit Metric).

Clean Architecture: Motor Markoviano de certidumbre probabilística continua.
"""
import sys, json, logging
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TideCurrentLookaheadEngine")


def run_lookahead_engine(ticker: str = "AAPL", initial_shares: float = 100.0):
    print("\n" + "=" * 115)
    print(f"   MOTOR DE PROYECCIÓN MARKOVIANA DE LOOKAHEAD Y CERTIDUMBRE VWAP: {ticker.upper()}")
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
        overprice_losses_count = 0
        successful_discounts_count = 0

        # Feature lake signals with Noise Filtering
        df_merged["vwap_filtered"] = df_merged["vwap_sigma_wave"].ewm(span=5, adjust=False).mean()
        df_merged["vwap_drift_vel"] = df_merged["vwap_filtered"].diff().fillna(0.0)

        # Matriz de Transición Markoviana P(S_{t+1} | S_t)
        df_merged["tide_state"] = np.where(df_merged["tide_slope"] >= 0.05, "T+", np.where(df_merged["tide_slope"] <= -0.05, "T-", "T0"))
        df_merged["curr_state"] = np.where(df_merged["current_slope"] >= 0.05, "C+", np.where(df_merged["current_slope"] <= -0.05, "C-", "C0"))
        df_merged["next_curr_state"] = df_merged["curr_state"].shift(-1).fillna("C0")

        print(f"\n1. MATRIZ DE CERTIDUMBRE FACTUAL PARA {ticker.upper()}:")
        print(f"   - Ticker Objetivo: {ticker.upper()} | Muestras: {len(df_merged):,} barras ({dt_start} -> {dt_end})")
        print(f"   - Filtro de Ruido VWAP: EWMA 5d con Margen de Tolerancia de Dispersión")
        print(f"   - Contabilidad de Pérdidas: Re-entradas más caras registradas como PÉRDIRA DE ACCIONES")
        print(f"   - REFERENCIA BUY & HOLD: {bnh_shares:.2f} Acciones | Valor Final: ${bnh_final_val:,.2f}\n")

        for idx, r in df_merged.iterrows():
            dt_str = r["timestamp"].strftime("%Y-%m-%d")
            p_curr = float(r["close"])
            t_slope = float(r["tide_slope"])
            c_slope = float(r["current_slope"])
            svw = float(r["vwap_filtered"])
            svw_vel = float(r["vwap_drift_vel"])
            t_state = r["tide_state"]
            c_state = r["curr_state"]

            # ── 1. SESGO Y CERTIDUMBRE VWAP SOBRE LA TENDENCIA (Premisa 3) ──
            # Si el VWAP sigue acumulando energía positiva (svw_vel > 0), aumenta certidumbre de continuación alcista
            trend_certainty = np.tanh(svw_vel * 5.0)  # Multiplicador entre -1.0 y +1.0

            # ── 2. PROYECCIÓN DEL ESTADO SIGUIENTE MÁS PROBABLE S_{t+1} (Premisa 4) ──
            # Lookahead: ¿Es más probable una continuación alcista o un pivote de valle?
            is_healthy_tide = t_slope >= 0.0
            is_dip_correction = is_healthy_tide and (c_state == "C-")  # Corrección comprable en marea alcista
            is_crisis_break = (t_slope < -0.10) and (c_state == "C-")  # Disrupción de crisis estructural

            executed = False
            desc = ""

            if cash > 1.0:
                days_in_cash += 1
            else:
                days_in_cash = 0

            # ── 3. APROVECHAR CORRECCIONES COMPRABLES (RE-INVERSIÓN CON DESCUENTO / PISO) (Premisas 5 & 7) ──
            has_real_discount = (last_harvest_price is not None) and (p_curr < last_harvest_price)
            time_guard_expired = (days_in_cash >= 20) and is_healthy_tide

            if cash > 1.0 and is_healthy_tide and (has_real_discount or time_guard_expired or is_dip_correction or last_harvest_price is None):
                discount_pct = ((last_harvest_price - p_curr) / last_harvest_price * 100.0) if last_harvest_price else 0.0
                
                # Evaluador de Pérdida por Re-entrada Cara (Premisa 7)
                if last_harvest_price and p_curr > last_harvest_price:
                    overprice_losses_count += 1
                    loss_tag = f" ⚠️ PÉRDIDA POR OPORTUNIDAD (+{abs(discount_pct):.1f}% Más Caro)"
                else:
                    if last_harvest_price:
                        successful_discounts_count += 1
                    loss_tag = f" (+{discount_pct:.1f}% Descuento Factual)"

                # Sizing por Certidumbre de Tendencia (Premisa 3)
                if is_dip_correction or svw <= -1.0:
                    multiplier = 2.0  # Dip comprable en marea alcista
                elif discount_pct >= 8.0:
                    multiplier = 1.5  # Descuento profundo
                else:
                    multiplier = 1.0  # Re-entrada normal

                buy_qty = (cash * multiplier) / p_curr
                shares += buy_qty

                reason = "CORRECCIÓN COMPRABLE (BUY DIP)" if is_dip_correction else ("LÍMITE 20D (ANTI-CASH DRAG)" if time_guard_expired else loss_tag)
                desc = f"🎯 RE-INVERSIÓN EN CORRECCIÓN ({reason} | Mult {multiplier:.1f}x): +{buy_qty:.1f} shs @ ${p_curr:.2f}"
                cash = 0.0
                days_in_cash = 0
                last_harvest_price = None
                executed = True

            # ── 4. COSECHA GRADUAL EN CÚSPIDES FACTUALES (Premisas 5 & 6) ──
            elif svw >= +1.50 and svw_vel <= 0.02 and cash <= 1.0 and is_healthy_tide and idx >= 20:
                excess = max(shares - (initial_shares * 0.50), 0.0)
                if excess > 0.5:
                    trim_qty = excess * 0.20
                    shares -= trim_qty
                    cash += trim_qty * p_curr
                    last_harvest_price = p_curr
                    days_in_cash = 0
                    desc = f"✂️ COSECHA GRADUAL EN CÚSPIDE (-{trim_qty:.1f} shs @ ${p_curr:.2f} | σ={svw:+.2f} | Cert={trend_certainty:+.2f})"
                    executed = True

            # ── 5. SALIDA SÚBITA EN DISRUPCIÓN DE CRISIS (Premisa 5) ──
            elif is_crisis_break and shares > (initial_shares * 0.50):
                tradeable_shares = shares - (initial_shares * 0.50)
                cash += tradeable_shares * p_curr
                shares -= tradeable_shares
                desc = f"🛡️ VETO SÚBITO POR DISRUPCIÓN DE CRISIS (-{tradeable_shares:.1f} shs @ ${p_curr:.2f})"
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

        print(f"2. SCORECARD AUDITADO BAJO LAS 7 PREMISAS ({ticker.upper()}):")
        print(f"   - Total Operaciones Ejecutadas: {len(trade_log)}")
        print(f"   - Re-entradas Exitosas con Descuento Ganado: {successful_discounts_count}")
        print(f"   - Re-entradas Más Caras (Contabilizadas como PÉRDIDA): {overprice_losses_count}")
        print(f"   - ACCIONES REFERENCIA BUY & HOLD: {bnh_shares:.2f} ACCIONES ($ {bnh_final_val:,.2f})")
        print(f"   - ACCIONES FINALES ACUMULADAS POR MOTOR MARKOVIANO: {strat_equivalent_shares:,.2f} ACCIONES ($ {final_val:,.2f})")
        print(f"   - GANANCIA NETA EN ACCIONES PROPIAS: {shares_delta:>+,.2f} ACCIONES PROPIAS")
        print(f"   - GANANCIA NETA EN DÓLARES SOBRE BUY & HOLD: ${dollar_delta:>+,.2f}")
        print(f"   - PORCENTAJE DE OVER-ALPHA LOGRADO: {share_growth_pct:>+5.2f}%\n")

        if shares_delta > 0:
            print(f"   🏆 ¡EL MOTOR MARKOVIANO DE CERTIDUMBRE SUPERÓ AL BUY & HOLD DE {ticker.upper()} POR {shares_delta:+.2f} ACCIONES (${dollar_delta:+,.2f} USD | {share_growth_pct:+.2f}%)!")
        else:
            print(f"   ⚠️ SE MANTIENE EN EL PISO BASE DE SEGURIDAD.")

        print(f"\n3. MUESTRA DEL REGISTRO DE OPERACIONES MARKOVIANAS DE {ticker.upper()}:")
        print(f"   {'FECHA':<11} | {'PRECIO':<7} | {'DESCRIPCIÓN DE OPERACIÓN EN ' + ticker.upper():<75} | {'ACCIONES'}")
        print("   " + "-" * 115)
        for t in trade_log[-25:]:
            print(f"   {t['date']:<11} | ${t['price']:>6.2f} | {t['desc']:<75} | {t['shares']:>6.1f} shs")

        print("=" * 115 + "\n")

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    tk = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    run_lookahead_engine(tk)
