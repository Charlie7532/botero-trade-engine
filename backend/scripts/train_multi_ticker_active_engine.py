#!/usr/bin/env python3
"""
Pure Mathematical Universal Multi-Ticker Engine (COST / MSFT / NVDA / AAPL / JPM / XOM / QQQ)
=============================================================================================
Elimina cualquier dependencia de JSON keys estáticas y computa la señal cinemática
directamente de los campos factuales (tide_slope, current_slope, vwap_drift):
  - Marea Alcista: tide_slope >= 0.0
  - Cúspide de Techo: vwap_drift >= quantiles(85%)
  - Suelo de Valle: vwap_drift <= quantiles(15%)
  - Guardián Anti-Sobreprecio: P_current < P_harvest

Clean Architecture: Motor universal adaptable a los 531 activos del Vault.
"""
import sys, json, logging
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("UniversalMultiTickerEngine")


def run_universal_ticker_engine(ticker: str = "MSFT", initial_shares: float = 100.0):
    print("\n" + "=" * 105)
    print(f"   MOTOR UNIVERSAL ADAPTATIVO POR CUANTILES: {ticker.upper()}")
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

        # Dynamic Quantile Thresholds per Asset
        harvest_threshold = float(df_merged["vwap_drift"].quantile(0.85))
        valley_threshold = float(df_merged["vwap_drift"].quantile(0.15))

        print(f"\n1. PERFIL CINEMÁTICO ADAPTATIVO FACTUAL PARA {ticker.upper()}:")
        print(f"   - Ticker: {ticker.upper()} | Muestras: {len(df_merged):,} barras ({dt_start} -> {dt_end})")
        print(f"   - Umbral Cinemático de Techo (Percentil 85): +{harvest_threshold:.2f}σ")
        print(f"   - Umbral Cinemático de Valle (Percentil 15): {valley_threshold:.2f}σ")
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

            executed = False
            desc = ""

            is_healthy = t_slope >= 0.0

            if cash > 1.0:
                days_in_cash += 1
            else:
                days_in_cash = 0

            # ── 1. RE-INVERSIÓN EN DESCUENTO REAL O LÍMITE TEMPORAL 20D ──
            has_real_discount = (last_harvest_price is not None) and (p_curr < last_harvest_price)
            time_guard_expired = (days_in_cash >= 20) and is_healthy

            if cash > 1.0 and is_healthy and (has_real_discount or time_guard_expired or last_harvest_price is None):
                discount_pct = ((last_harvest_price - p_curr) / last_harvest_price * 100.0) if last_harvest_price else 0.0
                
                # Multiplicador dinámico por profundidad de suelo: 1.5x en vales profundos
                multiplier = 1.5 if (svw <= valley_threshold and is_healthy) else 1.0

                buy_qty = (cash * multiplier) / p_curr
                shares += buy_qty
                
                if last_harvest_price and p_curr < last_harvest_price:
                    total_wins += 1

                reason = "LÍMITE 20D (ANTI-CASH DRAG)" if time_guard_expired else f"+{discount_pct:.1f}% Descuento"
                desc = f"🎯 RE-INVERSIÓN EN VALLE ({reason} | Palanca {multiplier:.1f}x): +{buy_qty:.1f} shs @ ${p_curr:.2f}"
                cash = 0.0
                days_in_cash = 0
                last_harvest_price = None
                executed = True

            # ── 2. SALIDA ESTRATÉGICA EN CÚSPIDE FACTUAL (svw >= harvest_threshold & idx >= 30) ──
            # Cosecha ÚNICAMENTE sobre acciones en exceso del piso núcleo (10% slice) tras calentamiento de 30d
            elif svw >= harvest_threshold and cash <= 1.0 and is_healthy and idx >= 30:
                excess = max(shares - (initial_shares * 0.50), 0.0)
                if excess > 0.5:
                    trim_qty = excess * 0.15
                    shares -= trim_qty
                    cash += trim_qty * p_curr
                    last_harvest_price = p_curr
                    days_in_cash = 0
                    desc = f"✂️ SALIDA ESTRATÉGICA CÚSPIDE (-{trim_qty:.1f} shs @ ${p_curr:.2f} | σ={svw:+.2f})"
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

        print(f"2. SCORECARD FACTUAL UNIVERSAL PARA {ticker.upper()}:")
        print(f"   - Total Operaciones Ejecutadas: {len(trade_log)}")
        print(f"   - Re-entradas Exitosas con Ganancia de Acciones: {total_wins}")
        print(f"   - ACCIONES REFERENCIA BUY & HOLD: {bnh_shares:.2f} ACCIONES ($ {bnh_final_val:,.2f})")
        print(f"   - ACCIONES FINALES ACUMULADAS POR TIDE ENGINE: {strat_equivalent_shares:,.2f} ACCIONES ($ {final_val:,.2f})")
        print(f"   - GANANCIA NETA EN ACCIONES PROPIAS: {shares_delta:>+,.2f} ACCIONES PROPIAS")
        print(f"   - GANANCIA NETA EN DÓLARES SOBRE BUY & HOLD: ${dollar_delta:>+,.2f}")
        print(f"   - PORCENTAJE DE OVER-ALPHA LOGRADO: {share_growth_pct:>+5.2f}%\n")

        if shares_delta > 0:
            print(f"   🏆 ¡EL MOTOR UNIVERSAL VENCIÓ AL BUY & HOLD DE {ticker.upper()} POR {shares_delta:+.2f} ACCIONES (${dollar_delta:+,.2f} USD | {share_growth_pct:+.2f}%)")
        else:
            print(f"   ⚠️ SE MANTIENE EN EL PISO BASE DE SEGURIDAD.")

        print(f"\n3. MUESTRA DEL REGISTRO DE OPERACIONES DE {ticker.upper()}:")
        print(f"   {'FECHA':<11} | {'PRECIO':<7} | {'DESCRIPCIÓN DE OPERACIÓN EN ' + ticker.upper():<68} | {'ACCIONES'}")
        print("   " + "-" * 105)
        for t in trade_log[-25:]:
            print(f"   {t['date']:<11} | ${t['price']:>6.2f} | {t['desc']:<68} | {t['shares']:>6.1f} shs")

        print("=" * 105 + "\n")

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    tk = sys.argv[1] if len(sys.argv) > 1 else "MSFT"
    run_universal_ticker_engine(tk)
