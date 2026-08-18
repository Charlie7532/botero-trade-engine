#!/usr/bin/env python3
"""
AAPL Over-Alpha Engine — Beat Buy & Hold Reference (1981-2026)
==============================================================
Sintetiza la Solución Maestra para Derrocar a la Referencia Buy & Hold:
  1. Base Floor Inviolable (100% Position Protection):
     Las 100 acciones base del Buy & Hold jamás se venden. Se protegen como el piso mínimo.
  2. Tactical Share Accumulation on Valleys (Valley Dip Buying):
     En cada suelo de canal (vwap_sigma_wave <= -1.0), el modelo compra acciones adicionales con capital táctico.
  3. Cosecha en Techos Extremos (vwap_sigma_wave >= +2.0):
     Cosecha el 15% del exceso táctico a Cash para generar reservas de compra.
  4. Límite Temporal de Cash (60-Day Re-investment Guard):
     Si transcurren 60 días de marea alcista sin que ocurra un retroceso del -4%, el cash se RE-INVIERTE automáticamente,
     impidiendo que el cash drag reduzca las acciones acumuladas por debajo de 100.

Output: Demostración Factual de Superación del Buy & Hold.
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
logger = logging.getLogger("BeatBuyAndHoldMaster")


def run_beat_buy_and_hold_master(ticker: str = "AAPL", initial_shares: float = 100.0):
    print("\n" + "=" * 105)
    print(f"   DEMOSTRACIÓN FACTUAL: DERROCAR A LA REFERENCIA BUY & HOLD EN {ticker.upper()}")
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

        # Strategy Portfolio: Start with 100 Shares + $0 Cash
        shares = initial_shares
        cash = 0.0
        last_trim_price = None
        days_in_cash = 0

        trade_log = []
        run_length = 0
        prev_regime = ""

        print(f"\n1. REFERENCIA FACTUAL A VENCER:")
        print(f"   - Ticker: {ticker.upper()} | Muestras: {len(df_merged):,} barras (1981-2026)")
        print(f"   - BUY & HOLD DE REFERENCIA: {bnh_shares:.2f} ACCIONES | VALOR FINAL: ${bnh_final_val:,.2f}\n")

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

            is_healthy_marea = t_slope >= 0.0

            if cash > 1.0:
                days_in_cash += 1
            else:
                days_in_cash = 0

            executed = False
            desc = ""

            # ── 1. COMPRA DE ACUMULACIÓN EN SUELO CINEMÁTICO (vwap_sigma_wave <= -0.50) ──
            is_4pct_discount = (last_trim_price is not None) and (p_curr <= 0.96 * last_trim_price)
            cash_time_limit_expired = (days_in_cash >= 60) and is_healthy_marea

            smart_accumulation = (
                cash > 1.0 and
                is_healthy_marea and
                (svw <= -0.50 or is_4pct_discount or cash_time_limit_expired)
            )

            if smart_accumulation:
                buy_qty = cash / p_curr
                shares += buy_qty
                
                reason = "LIMITE TEMPORAL 60D (RE-INVERSIÓN ANTI-CASH DRAG)" if cash_time_limit_expired else "DESCUENTO EN VALLE"
                desc = f"🎯 ACUMULACIÓN OVER-ALPHA ({reason}): +{buy_qty:.1f} shs @ ${p_curr:.2f}"
                cash = 0.0
                days_in_cash = 0
                last_trim_price = None
                executed = True

            # ── 2. COSECHA TÁCTICA SOLO EN ACCESO POR ENCIMA DE 100 ACCIONES BASE ──
            elif svw >= +2.20 and is_healthy_marea and cash <= 1.0:
                tradeable_excess = max(shares - initial_shares, 0.0)
                if tradeable_excess > 0.5:
                    trim_qty = tradeable_excess * 0.33
                    shares -= trim_qty
                    cash += trim_qty * p_curr
                    last_trim_price = p_curr
                    days_in_cash = 0
                    desc = f"✂️ COSECHA TÁCTICA SOBRE EXCESO (-{trim_qty:.1f} shs @ ${p_curr:.2f} | σ={svw:+.2f})"
                    executed = True

            # ── 3. VETO DE CRISIS EN ACANTILADO ESTRUCTURAL ($T---$) ──
            elif act == ACTION_STK_T_BLOCK_CRISIS and t_slope < -0.03:
                tradeable = max(shares - initial_shares, 0.0)
                if tradeable > 0.5:
                    cash += tradeable * p_curr
                    shares -= tradeable
                    last_trim_price = p_curr
                    desc = f"🛡️ VETO CRISIS TÁCTICO (-{tradeable:.1f} shs @ ${p_curr:.2f})"
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
        dollar_delta = final_val - bnh_final_val

        print(f"2. SCORECARD MAESTRO: DEMOSTRACIÓN DE SUPERACIÓN DEL BUY & HOLD ({ticker.upper()}):")
        print(f"   - Total Ajustes Ejecutados: {len(trade_log)}")
        print(f"   - ACCIONES REFERENCIA BUY & HOLD: {bnh_shares:.2f} ACCIONES ($ {bnh_final_val:,.2f})")
        print(f"   - ACCIONES FINALES ACUMULADAS POR TIDE ENGINE: {strat_equivalent_shares:,.2f} ACCIONES ($ {final_val:,.2f})")
        print(f"   - GANANCIA NETA EN ACCIONES PROPIAS: {shares_delta:>+,.2f} ACCIONES PROPIAS")
        print(f"   - GANANCIA NETA EN DÓLARES SOBRE BUY & HOLD: ${dollar_delta:>+,.2f}")
        print(f"   - PORCENTAJE DE SUPERACIÓN (OVER-ALPHA): {share_growth_pct:>+5.2f}%\n")
        
        if shares_delta > 0:
            print(f"   🏆 ¡VICTORIA CUANTITATIVA CONFIRMADA! EL MOTOR TIDE VENCIÓ AL BUY & HOLD DE AAPL POR {shares_delta:+.2f} ACCIONES (${dollar_delta:+,.2f} USD)")
        else:
            print(f"   ⚠️ AÚN FALTA AJUSTE: BRECHA DE {shares_delta:.2f} ACCIONES PARA ALCANZAR EL BUY & HOLD.")

        print("\n" + "=" * 105 + "\n")

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    tk = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    run_beat_buy_and_hold_master(tk)
