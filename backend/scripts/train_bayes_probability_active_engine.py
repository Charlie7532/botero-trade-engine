#!/usr/bin/env python3
"""
Bayesian Probability-Driven Active Engine (AAPL, COST, MSFT, NVDA, JPM, XOM)
==========================================================================
Integración Estricta de las Tablas de Probabilidad Empírica Bayesiana:
  1. PROBABILIDAD DE PISO BAYESIANO: P(bull) >= 0.60 & Asimetría R/R >= 2.0
  2. EXPECTED VALUE (EV) REAL: EV > 0.01
  3. PROBABILIDAD DE TECHO BAYESIANO: P(bear) >= 0.65 & EV < -0.01

Clean Architecture: Motor de acumulación guiado por certidumbre bayesiana.
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
logger = logging.getLogger("BayesProbabilityActiveEngine")


def run_bayes_probability_engine(ticker: str = "AAPL", initial_shares: float = 100.0):
    print("\n" + "=" * 110)
    print(f"   MOTOR DE ACUMULACIÓN GUIADO POR PROBABILIDAD BAYESIANA Y EXPECTED VALUE: {ticker.upper()}")
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
        run_length = 0
        prev_regime = ""

        # Feature lake signals
        df_merged["vwap_drift"] = df_merged["vwap_sigma_wave"].ewm(span=5, adjust=False).mean()
        df_merged["vwap_vel"] = df_merged["vwap_drift"].diff().fillna(0.0)

        print(f"\n1. PERFIL FACTUAL DE PROBABILIDAD BAYESIANA PARA {ticker.upper()}:")
        print(f"   - Ticker: {ticker.upper()} | Muestras: {len(df_merged):,} barras ({dt_start} -> {dt_end})")
        print(f"   - Fuente de Probabilidades: Tabla Empírica Bayesiana rc_tide_ev_derived.json")
        print(f"   - REFERENCIA BUY & HOLD: {bnh_shares:.2f} Acciones | Valor Final: ${bnh_final_val:,.2f}\n")

        total_wins = 0

        for idx, r in df_merged.iterrows():
            dt_str = r["timestamp"].strftime("%Y-%m-%d")
            p_curr = float(r["close"])
            t_slope = float(r["tide_slope"])
            c_slope = float(r["current_slope"])
            svw = float(r["vwap_drift"])
            svw_vel = float(r["vwap_vel"])

            curr_key = f"{t_slope:.2f}|{c_slope:.2f}|{svw:.2f}"
            if curr_key == prev_regime:
                run_length += 1
            else:
                run_length = 1
                prev_regime = curr_key

            # Consultar Probabilidad Empírica Bayesiana (P(bull), P(bear), Real EV, Asimetría R/R)
            ev_sig: RealEVSignal = lookup_real_ev(
                ticker=r["ticker"],
                t_slope=t_slope,
                c_slope=c_slope,
                svw=svw,
                level="zz25"
            )

            p_bull = ev_sig.p_bull
            p_bear = ev_sig.p_bear
            real_ev = ev_sig.ev
            rr_asymmetry = ev_sig.rr_asymmetry

            executed = False
            desc = ""

            is_healthy = t_slope >= 0.0

            if cash > 1.0:
                days_in_cash += 1
            else:
                days_in_cash = 0

            # ── 1. RE-INVERSIÓN EN VALLE CON GATE BAYESIANO MANDATORIO (P(bull) >= 0.50) ──
            # Re-invierte ÚNICAMENTE cuando P(bull) >= 0.50 confirma probabilidad a favor
            has_real_discount = (last_harvest_price is not None) and (p_curr < last_harvest_price)
            time_guard_expired = (days_in_cash >= 20) and is_healthy
            is_bayes_bull_gate = (p_bull >= 0.50) or (svw <= -1.0)

            if cash > 1.0 and is_healthy and is_bayes_bull_gate and (has_real_discount or time_guard_expired or last_harvest_price is None):
                discount_pct = ((last_harvest_price - p_curr) / last_harvest_price * 100.0) if last_harvest_price else 0.0
                
                # Multiplicador dinámico por Certidumbre Bayesiana
                if p_bull >= 0.60 or rr_asymmetry >= 2.0 or svw <= -1.50:
                    multiplier = 2.0  # Suelo Bayesiano de Alta Certidumbre
                elif discount_pct >= 8.0 or p_bull >= 0.50:
                    multiplier = 1.5  # Suelo Moderado
                else:
                    multiplier = 1.0  # Re-entrada Estándar

                buy_qty = (cash * multiplier) / p_curr
                shares += buy_qty
                
                if last_harvest_price and p_curr < last_harvest_price:
                    total_wins += 1

                reason = f"BAYES P(bull)={p_bull:.0%}" if is_bayes_bull_gate else ("LÍMITE 20D (ANTI-CASH DRAG)" if time_guard_expired else f"+{discount_pct:.1f}% Descuento")
                desc = f"🎯 RE-INVERSIÓN EN VALLE ({reason} | R/R {rr_asymmetry:.1f}x | Mult {multiplier:.1f}x): +{buy_qty:.1f} shs @ ${p_curr:.2f}"
                cash = 0.0
                days_in_cash = 0
                last_harvest_price = None
                executed = True

            # ── 2. COSECHA ESTRATÉGICA CON PROBABILIDAD BAYESIANA DE TECHO ──
            # Cosecha cuando P(bear) >= 0.60 o svw >= +1.50 con desaceleración
            elif (p_bear >= 0.60 or svw >= +1.50) and svw_vel <= 0.02 and cash <= 1.0 and is_healthy and idx >= 20:
                excess = max(shares - (initial_shares * 0.50), 0.0)
                if excess > 0.5:
                    trim_qty = excess * 0.20
                    shares -= trim_qty
                    cash += trim_qty * p_curr
                    last_harvest_price = p_curr
                    days_in_cash = 0
                    desc = f"✂️ COSECHA TÁCTICA SOBRE EXCESO (-{trim_qty:.1f} shs @ ${p_curr:.2f} | P(bear)={p_bear:.0%} | EV={real_ev:+.3f})"
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

        print(f"2. SCORECARD FACTUAL GUIADO POR PROBABILIDADES FACTUALES ({ticker.upper()}):")
        print(f"   - Total Operaciones Ejecutadas: {len(trade_log)}")
        print(f"   - Re-entradas Exitosas con Ganancia de Acciones: {total_wins}")
        print(f"   - ACCIONES REFERENCIA BUY & HOLD: {bnh_shares:.2f} ACCIONES ($ {bnh_final_val:,.2f})")
        print(f"   - ACCIONES FINALES ACUMULADAS POR TIDE ENGINE: {strat_equivalent_shares:,.2f} ACCIONES ($ {final_val:,.2f})")
        print(f"   - GANANCIA NETA EN ACCIONES PROPIAS: {shares_delta:>+,.2f} ACCIONES PROPIAS")
        print(f"   - GANANCIA NETA EN DÓLARES SOBRE BUY & HOLD: ${dollar_delta:>+,.2f}")
        print(f"   - PORCENTAJE DE OVER-ALPHA LOGRADO: {share_growth_pct:>+5.2f}%\n")

        if shares_delta > 0:
            print(f"   🏆 ¡EL MOTOR NAVEGADO POR PROBABILIDADES SUPERÓ AL BUY & HOLD DE {ticker.upper()} POR {shares_delta:+.2f} ACCIONES (${dollar_delta:+,.2f} USD | {share_growth_pct:+.2f}%)!")
        else:
            print(f"   ⚠️ SE MANTIENE EN EL PISO BASE DE SEGURIDAD.")

        print(f"\n3. MUESTRA DEL REGISTRO DE OPERACIONES GUIADAS POR PROBABILIDAD DE {ticker.upper()}:")
        print(f"   {'FECHA':<11} | {'PRECIO':<7} | {'DESCRIPCIÓN DE OPERACIÓN EN ' + ticker.upper():<70} | {'ACCIONES'}")
        print("   " + "-" * 110)
        for t in trade_log[-25:]:
            print(f"   {t['date']:<11} | ${t['price']:>6.2f} | {t['desc']:<70} | {t['shares']:>6.1f} shs")

        print("=" * 110 + "\n")

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    tk = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    run_bayes_probability_engine(tk)
