#!/usr/bin/env python3
"""
Adaptive Learning Multi-Ticker Engine (AAPL, COST, MSFT, NVDA, JPM)
===================================================================
Aplica la lógica exacta de eval_tide_adaptive_learning.py que logró +51.26 acciones de Over-Alpha en AAPL:
  - Cosecha 50% de acciones tácticas en Techo Extremo (σ >= +1.80) o Degradación de Señal (ΔEV < 0, ΔC < 0).
  - Re-invierte 100% de Cash en Suelo Extremo (σ <= -1.80) o Mejora de Señal (ΔEV > 0, ΔC > 0 y σ <= -0.30).
  - Escudo Reina: 50% Piso Núcleo Inviolable.

Output: Evaluaciones comparativas sobre todos los tickers.
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
logger = logging.getLogger("AdaptiveLearningMultiTicker")


def run_adaptive_engine(ticker: str = "AAPL", initial_shares: float = 100.0):
    print("\n" + "=" * 105)
    print(f"   MOTOR DE APRENDIZAJE ADAPTATIVO (CON GRADIETES Y DEGRADACIÓN): {ticker.upper()}")
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

        df_snaps['timestamp'] = pd.to_datetime(df_snaps['timestamp'], utc=True).dt.floor('D')
        df_bars['timestamp'] = pd.to_datetime(df_bars['timestamp'], utc=True).dt.floor('D')

        df_merged = pd.merge(df_snaps, df_bars, on=["ticker", "timestamp"]).dropna(subset=["close"])
        df_merged = df_merged.sort_values("timestamp").reset_index(drop=True)

        p_start = float(df_merged["close"].iloc[0])
        p_end = float(df_merged["close"].iloc[-1])

        bnh_shares = initial_shares
        bnh_final_val = initial_shares * p_end

        shares = initial_shares
        cash = 0.0

        trade_log = []
        run_length = 0
        prev_regime = ""

        ev_history = []
        c_history = []

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

            executed = False
            desc = ""

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
                tag = " [PATRÓN ROTO: SUELO EXTREMO]" if is_extreme_floor else " [SEÑAL MEJORANDO]"
                desc = f"🎯 RE-INVERSIÓN REINA{tag} (+{buy_qty:.1f} shs @ ${p_curr:.2f})"
                cash = 0.0
                executed = True

            elif is_extreme_top or act == ACTION_STK_T_TRIM_TACTICAL or is_degrading:
                tradeable_shares = max(shares - core_floor_shares, 0.0)
                if tradeable_shares > 1.0:
                    harvest_fraction = 0.50 if is_extreme_top else 0.33
                    trim_qty = tradeable_shares * harvest_fraction
                    shares -= trim_qty
                    cash += trim_qty * p_curr
                    tag = " [PATRÓN ROTO: TECHO EXTREMO]" if is_extreme_top else (" [SEÑAL DEGRADANDO]" if is_degrading else "")
                    desc = f"✂️ COSECHA TÁCTICA{tag} (-{trim_qty:.1f} shs @ ${p_curr:.2f})"
                    executed = True

            elif act in (ACTION_STK_T_DISTRIBUTE_DECAY, ACTION_STK_T_EXIT_THESIS_DEATH, ACTION_STK_T_BLOCK_CRISIS):
                tradeable_shares = max(shares - core_floor_shares, 0.0)
                if tradeable_shares > 1.0:
                    cash += tradeable_shares * p_curr
                    shares -= tradeable_shares
                    desc = f"🛡️ VETO DE CRISIS (-{tradeable_shares:.1f} shs @ ${p_curr:.2f})"
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

        print(f"2. SCORECARD AUDITADO FACTUAL PARA {ticker.upper()}:")
        print(f"   - Total Operaciones Ejecutadas: {len(trade_log)}")
        print(f"   - ACCIONES REFERENCIA BUY & HOLD: {bnh_shares:.2f} ACCIONES ($ {bnh_final_val:,.2f})")
        print(f"   - ACCIONES FINALES ACUMULADAS POR MOTOR TIDE: {strat_equivalent_shares:,.2f} ACCIONES ($ {final_val:,.2f})")
        print(f"   - GANANCIA NETA EN ACCIONES PROPIAS: {shares_delta:>+,.2f} ACCIONES PROPIAS")
        print(f"   - GANANCIA NETA EN DÓLARES SOBRE BUY & HOLD: ${dollar_delta:>+,.2f}")
        print(f"   - PORCENTAJE DE OVER-ALPHA LOGRADO: {share_growth_pct:>+5.2f}%\n")

        print("3. REGISTRO DE SALIDAS ESTRATÉGICAS Y RE-INVERSIONES:")
        print(f"   {'FECHA':<11} | {'PRECIO':<7} | {'DESCRIPCIÓN DE OPERACIÓN EN ' + ticker.upper():<65} | {'ACCIONES'}")
        print("   " + "-" * 100)
        for t in trade_log[-25:]:
            print(f"   {t['date']:<11} | ${t['price']:>6.2f} | {t['desc']:<65} | {t['shares']:>6.1f} shs")

        print("=" * 105 + "\n")

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    tk = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    run_adaptive_engine(tk)
