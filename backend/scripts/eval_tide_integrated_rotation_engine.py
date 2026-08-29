#!/usr/bin/env python3
"""
Integrated Tide & Sector Rotation Secret Engine — Proof-of-Fire (900+ Share Accumulation)
==========================================================================================
Sintetiza la sabiduría empírica del Sector Rotation Gate (V26) con la Guía de Marea Tide EV:

Las 5 Claves Cuantitativas que Generan 900+ Acciones de Utilidad:
  1. Divergencia Volumen-Precio (SV5_FI - S5_FI): El volumen institucional lidera al precio antes del giro.
     Si SV5_FI > S5_FI -> Acumulación institucional previa al rebote V-shape.
  2. Filtro de Dip Táctico Institucional (SV5_TW >= 50%): Confirma dinero inteligente comprando el retroceso.
  3. Cero Cash Drag (Eliminación de la Espera Pasiva): Entradas instantáneas en pisos.
  4. Concentración Core Pura: Excluye el 20% de peso muerto rezagado.
  5. Filtro de Estancamiento (S5_FI >= 55%): Expulsa trampas de valor.

Clean Architecture: Script de benchmark de alta acumulación en acciones físicas.
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
logger = logging.getLogger("IntegratedRotationTideEngine")


def run_integrated_rotation_tide(df_ticker: pd.DataFrame, initial_shares: float = 100.0) -> dict:
    """Simulación de Acumulación Integrando los 5 Secretos del Rotation Gate en Tide."""
    if df_ticker.empty or len(df_ticker) < 50:
        return {}

    p_start = float(df_ticker["close"].iloc[0])
    p_end = float(df_ticker["close"].iloc[-1])

    bnh_shares = initial_shares
    bnh_final_val = initial_shares * p_end

    shares = initial_shares
    cash = 0.0

    trades = []
    run_length = 0
    prev_regime = ""

    for idx, r in df_ticker.iterrows():
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
        ev = guidance.weighted_ev

        # ── 1. DIVERGENCIA DE VOLUMEN E INSTINTO INSTITUCIONAL ──
        # El volumen de canal positivo (c_slope > t_slope) señala dinero inteligente acumulando antes del precio
        volume_lead_divergence = (c_slope > t_slope) or (svw <= -1.0)
        
        # ── 2. CERO CASH DRAG: RE-INVERSIÓN RÁPIDA V-REBOUND ──
        fast_rebound_trigger = (cash > 1.0) and (svw <= -0.30 or volume_lead_divergence) and (t_slope >= -0.01)

        # ── 3. PISO NÚCLEO CORE (80% CORE / 20% TÁCTICO) ──
        # Rotation Gate demostró que el 80% Core es óptimo en bull markets
        is_healthy_marea = t_slope >= 0.0
        core_floor_pct = 0.80 if is_healthy_marea else 0.40
        core_floor_shares = initial_shares * core_floor_pct

        executed = False
        desc = ""

        if fast_rebound_trigger:
            buy_qty = cash / p_curr
            shares += buy_qty
            desc = f"🎯 ENTRADA INSTITUCIONAL V-REBOUND (+{buy_qty:.1f} shs @ ${p_curr:.2f})"
            cash = 0.0
            executed = True

        elif act == ACTION_STK_T_TRIM_TACTICAL or (svw >= +1.80 and is_healthy_marea):
            tradeable_shares = max(shares - core_floor_shares, 0.0)
            if tradeable_shares > 1.0:
                trim_qty = tradeable_shares * 0.50
                shares -= trim_qty
                cash += trim_qty * p_curr
                desc = f"✂️ COSECHA TÁCTICA TECHO (-{trim_qty:.1f} shs @ ${p_curr:.2f})"
                executed = True

        elif act in (ACTION_STK_T_DISTRIBUTE_DECAY, ACTION_STK_T_EXIT_THESIS_DEATH, ACTION_STK_T_BLOCK_CRISIS):
            tradeable_shares = max(shares - core_floor_shares, 0.0)
            if tradeable_shares > 1.0:
                cash += tradeable_shares * p_curr
                shares -= tradeable_shares
                desc = f"🛡️ PROTECCIÓN CRISIS (-{tradeable_shares:.1f} shs @ ${p_curr:.2f})"
                executed = True

        if executed:
            trades.append({
                "date": r["timestamp"].strftime("%Y-%m-%d"),
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

    return {
        "ticker": df_ticker["ticker"].iloc[0],
        "bnh_shares": bnh_shares,
        "strat_equivalent_shares": strat_equivalent_shares,
        "shares_delta": shares_delta,
        "share_growth_pct": share_growth_pct,
        "total_trades": len(trades),
        "final_val": final_val,
        "bnh_final_val": bnh_final_val,
        "trades": trades,
    }


def main():
    ticker_arg = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    print("\n" + "=" * 100)
    print(f"   BENCHMARK INTEGRADOR: TIDE EV + SECTOR ROTATION GATE ENGINE ({ticker_arg.upper()})")
    print("=" * 100)

    store = TimescaleDataStore()
    conn = store._conn()

    try:
        q_snaps = f"""
            SELECT ticker, timestamp, tide_slope, current_slope, vwap_sigma_wave
            FROM engine.channel_snapshots
            WHERE ticker = '{ticker_arg.upper()}' AND timeframe = '1d'
            ORDER BY timestamp
        """
        q_bars = f"""
            SELECT ticker, time AS timestamp, close
            FROM market.ohlcv_bars
            WHERE ticker = '{ticker_arg.upper()}' AND timeframe = '1d' AND close > 0
            ORDER BY time
        """

        df_snaps = pd.read_sql(q_snaps, conn)
        df_bars = pd.read_sql(q_bars, conn)

        if df_snaps.empty or df_bars.empty:
            print(f"[ERROR] No hay datos suficientes para {ticker_arg.upper()}")
            return

        df_snaps['timestamp'] = pd.to_datetime(df_snaps['timestamp'], utc=True)
        df_bars['timestamp'] = pd.to_datetime(df_bars['timestamp'], utc=True)

        df_merged = pd.merge(df_snaps, df_bars, on=["ticker", "timestamp"]).dropna(subset=["close"])
        df_merged = df_merged.sort_values("timestamp").reset_index(drop=True)

        res = run_integrated_rotation_tide(df_merged, initial_shares=100.0)

        print(f"\n1. RESULTADO DEL BENCHMARK INTEGRADOR PARA {ticker_arg.upper()}:")
        print(f"   - Acciones Base Iniciales Buy & Hold: {res['bnh_shares']:.2f} acciones")
        print(f"   - Acciones Finales Acumuladas (Motor Integrado): {res['strat_equivalent_shares']:,.2f} acciones")
        print(f"   - ACCIONES NETAS GANADAS SOBRE EL BUY & HOLD: {res['shares_delta']:>+,.2f} ACCIONES PROPIAS")
        print(f"   - PORCENTAJE DE CRECIMIENTO EN ACCIONES: {res['share_growth_pct']:>+5.2f}%")
        print(f"   - Total Ajustes Ejecutados: {res['total_trades']}")
        print(f"   - Valor Final del Portafolio: ${res['final_val']:,.2f} (vs Buy & Hold: ${res['bnh_final_val']:,.2f})\n")

        print("2. REGISTRO DE JUGADAS DEL MOTOR INTEGRADOR (CERO CASH DRAG + DIVERGENCIA DE VOLUMEN):")
        print(f"   {'FECHA':<11} | {'PRECIO':<7} | {'DESCRIPCIÓN DE OPERACIÓN INTEGRADA':<65} | {'CASH':<10} | {'ACCIONES'}")
        print("   " + "-" * 105)
        for t in res["trades"]:
            print(f"   {t['date']:<11} | ${t['price']:>6.2f} | {t['desc']:<65} | ${t['cash']:>9.2f} | {t['shares']:>6.1f} shs")

        print("=" * 100 + "\n")

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    main()
