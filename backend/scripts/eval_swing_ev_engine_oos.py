#!/usr/bin/env python3
"""
Out-Of-Sample Backtest Engine for Swing EV Decision Engine (2020-2026)
========================================================================
Prueba Factual Definitiva:
  1. Usa la tabla Fact IN-SAMPLE (≤2019) desde DB para CERO data leakage.
  2. Ejecuta en Out-Of-Sample (2020-2026).
  3. Cada barra pasa por rc_swing_ev_decision_engine.decide() con:
     - VIX real del Vault (no hardcodeado)
     - Transition matrix construida estrictamente in-sample
  4. Mide acumulación de acciones reales con 100% Cash Real (0 apalancamiento).
"""
import sys, logging
from pathlib import Path
from collections import defaultdict
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.quality_swing.domain.rules.rc_swing_ev_decision_engine import (
    decide, configure, _classify_state
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SwingEVBacktest")


def _build_transition_matrix_insample(conn, ticker: str, cutoff: str = "2019-12-31"):
    """Build Markov transition matrix from in-sample channel snapshots.

    Counts day-to-day state transitions S_t → S_{t+1} and normalizes to probabilities.
    Strictly uses data ≤ cutoff to avoid leakage.
    """
    q = f"""
        SELECT timestamp, tide_slope, current_slope, vwap_sigma_wave
        FROM engine.channel_snapshots
        WHERE ticker = '{ticker}' AND timeframe = '1d' AND timestamp <= '{cutoff}'
        ORDER BY timestamp
    """
    df = pd.read_sql(q, conn)
    if len(df) < 50:
        return None

    df["vwap_filtered"] = df["vwap_sigma_wave"].ewm(span=5, adjust=False).mean()

    # Classify each bar into 3D state (for Markov transitions)
    states = []
    for _, r in df.iterrows():
        _, _, _, sk = _classify_state(float(r["tide_slope"]), float(r["current_slope"]), float(r["vwap_filtered"]))
        states.append(sk)

    # Count transitions
    transition_counts = defaultdict(lambda: defaultdict(int))
    for i in range(len(states) - 1):
        transition_counts[states[i]][states[i + 1]] += 1

    # Normalize to probabilities
    transition_matrix = {}
    for from_state, to_dict in transition_counts.items():
        total = sum(to_dict.values())
        if total >= 5:  # minimum transitions to be statistically meaningful
            transition_matrix[from_state] = {k: v / total for k, v in to_dict.items()}

    return transition_matrix if transition_matrix else None


def _load_vix_series(conn):
    """Load VIX daily close from Vault as a date-indexed Series."""
    q = """
        SELECT time AS timestamp, close AS vix
        FROM market.ohlcv_bars
        WHERE ticker = 'VIX' AND timeframe = '1d' AND close > 0
        ORDER BY time
    """
    df = pd.read_sql(q, conn)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.floor("D")
    return df.set_index("timestamp")["vix"]


def run_swing_ev_backtest(ticker: str, initial_shares: float = 100.0, oos_start: str = "2020-01-01"):
    """Run OOS backtest with real VIX and in-sample transition matrix."""

    # Configure engine to use in-sample fact tables (≤2019)
    configure(calibration_cutoff="2019-12-31")

    store = TimescaleDataStore()
    conn = store._conn()

    try:
        # ── Load VIX series ──
        vix_series = _load_vix_series(conn)

        # ── Build transition matrix (strictly in-sample) ──
        transition_matrix = _build_transition_matrix_insample(conn, ticker, cutoff="2019-12-31")
        tm_states = len(transition_matrix) if transition_matrix else 0

        q_snaps = f"""
            SELECT ticker, timestamp, tide_slope, current_slope, vwap_sigma_wave
            FROM engine.channel_snapshots
            WHERE ticker = '{ticker}' AND timeframe = '1d'
            ORDER BY timestamp
        """
        q_bars = f"""
            SELECT ticker, time AS timestamp, close
            FROM market.ohlcv_bars
            WHERE ticker = '{ticker}' AND timeframe = '1d' AND close > 0
            ORDER BY time
        """

        df_snaps = pd.read_sql(q_snaps, conn)
        df_bars = pd.read_sql(q_bars, conn)

        if df_snaps.empty or df_bars.empty:
            return None

        df_snaps['timestamp'] = pd.to_datetime(df_snaps['timestamp'], utc=True).dt.floor('D')
        df_bars['timestamp'] = pd.to_datetime(df_bars['timestamp'], utc=True).dt.floor('D')

        df = pd.merge(df_snaps, df_bars, on=["ticker", "timestamp"]).dropna(subset=["close"])
        df = df.sort_values("timestamp").reset_index(drop=True)

        df["vwap_filtered"] = df["vwap_sigma_wave"].ewm(span=5, adjust=False).mean()
        df["vwap_drift"] = df["vwap_filtered"].diff().fillna(0.0)

        # OOS Split
        split = pd.to_datetime(oos_start, utc=True)
        df_oos = df[df["timestamp"] >= split].copy()

        if df_oos.empty:
            return None

        p_end = float(df_oos["close"].iloc[-1])
        bnh_val = initial_shares * p_end

        shares = initial_shares
        cash = 0.0
        last_harvest_price = None
        days_in_cash = 0

        trade_log = []
        winning_cycles = 0
        losing_cycles = 0
        crisis_exits = 0
        preventive_harvests = 0

        for _, r in df_oos.iterrows():
            dt_str = r["timestamp"].strftime("%Y-%m-%d")
            dt_ts = r["timestamp"]
            p_curr = float(r["close"])
            t_slope = float(r["tide_slope"])
            c_slope = float(r["current_slope"])
            svw = float(r["vwap_filtered"])
            svw_drift = float(r["vwap_drift"])

            # ── GET REAL VIX FOR THIS DATE ──
            vix_val = 20.0  # fallback
            if dt_ts in vix_series.index:
                vix_val = float(vix_series.loc[dt_ts])
            else:
                # Find nearest prior VIX
                prior = vix_series[vix_series.index <= dt_ts]
                if not prior.empty:
                    vix_val = float(prior.iloc[-1])

            # ── CONSULTAR EL MÓDULO EV CON VIX REAL + TRANSITION MATRIX ──
            decision = decide(
                ticker=ticker,
                timestamp=dt_str,
                t_slope=t_slope,
                c_slope=c_slope,
                svw_filtered=svw,
                svw_drift=svw_drift,
                vix=vix_val,
                transition_matrix=transition_matrix,
            )

            if cash > 1.0:
                days_in_cash += 1
            else:
                days_in_cash = 0

            executed = False

            # ── EXECUTION LOGIC CONSUMING SWING DECISION ──

            # 1. ACCUMULATE / RE-INVEST CASH
            if cash > 1.0:
                has_discount = (last_harvest_price is not None) and (p_curr <= last_harvest_price * 0.97)
                is_strong_accumulate = decision.action == "ACCUMULATE" and decision.ev_net >= 0.01
                time_guard = days_in_cash >= 30 and t_slope >= 0.0

                if has_discount or is_strong_accumulate or time_guard or last_harvest_price is None:
                    buy_qty = cash / p_curr
                    shares += buy_qty
                    cash = 0.0
                    days_in_cash = 0

                    if last_harvest_price:
                        if p_curr < last_harvest_price:
                            winning_cycles += 1
                        else:
                            losing_cycles += 1

                    last_harvest_price = None
                    executed = True
                    trade_log.append({
                        "date": dt_str,
                        "action": "BUY",
                        "price": p_curr,
                        "shares": shares,
                        "vix": vix_val,
                        "desc": f"🎯 RE-INVERSIÓN ({decision.action}): +{buy_qty:.2f} shs @ ${p_curr:.2f} | VIX={vix_val:.1f} | {decision.reasoning}"
                    })

            # 2. HARVEST (guided by E[R|S_t])
            elif decision.action == "HARVEST" and cash <= 1.0:
                excess = max(shares - initial_shares * 0.50, 0.0)
                if excess > 0.5:
                    trim_fraction = decision.sizing_fraction if decision.sizing_fraction > 0 else 0.20
                    trim_qty = excess * trim_fraction
                    shares -= trim_qty
                    cash += trim_qty * p_curr
                    last_harvest_price = p_curr
                    days_in_cash = 0
                    executed = True

                    if "REVERSAL" in decision.reasoning:
                        preventive_harvests += 1

                    trade_log.append({
                        "date": dt_str,
                        "action": "HARVEST",
                        "price": p_curr,
                        "shares": shares,
                        "vix": vix_val,
                        "desc": f"✂️ COSECHA ({decision.action}): -{trim_qty:.2f} shs @ ${p_curr:.2f} | VIX={vix_val:.1f} | {decision.reasoning}"
                    })

            # 3. EXIT CRISIS (real VIX-triggered)
            elif decision.action == "EXIT_CRISIS" and shares > initial_shares * 0.50:
                excess = shares - initial_shares * 0.50
                trim_qty = excess * decision.sizing_fraction
                shares -= trim_qty
                cash += trim_qty * p_curr
                last_harvest_price = p_curr
                days_in_cash = 0
                executed = True
                crisis_exits += 1
                trade_log.append({
                    "date": dt_str,
                    "action": "EXIT_CRISIS",
                    "price": p_curr,
                    "shares": shares,
                    "vix": vix_val,
                    "desc": f"🛡️ CRISIS EXIT (-{trim_qty:.2f} shs @ ${p_curr:.2f}) | VIX={vix_val:.1f} | {decision.reasoning}"
                })

        final_val = cash + shares * p_end
        equiv_shares = final_val / p_end

        return {
            "ticker": ticker,
            "bnh_shares": initial_shares,
            "bnh_val": round(bnh_val, 2),
            "final_shares": round(equiv_shares, 2),
            "final_val": round(final_val, 2),
            "net_delta_shares": round(equiv_shares - initial_shares, 2),
            "over_alpha_pct": round((equiv_shares - initial_shares) / initial_shares * 100, 2),
            "trades_count": len(trade_log),
            "winning_cycles": winning_cycles,
            "losing_cycles": losing_cycles,
            "crisis_exits": crisis_exits,
            "preventive_harvests": preventive_harvests,
            "tm_states": tm_states,
            "trade_log": trade_log
        }

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    tickers = ["AAPL", "COST", "MSFT", "JPM", "XOM", "PG", "HD", "JNJ", "MRK", "WMT"]

    print("\n" + "=" * 140)
    print("   EVALUACIÓN OOS CON VIX REAL + MARKOV TRANSITION MATRIX IN-SAMPLE (2020-2026)")
    print("=" * 140)

    results = []
    for tk in tickers:
        res = run_swing_ev_backtest(tk)
        if res:
            results.append(res)

    print(f"\n  {'Ticker':<6} | {'BnH':>7} | {'Final':>9} | {'Δ Shs':>8} | {'Over-α%':>7} | {'Trades':>6} | {'Win':>3} | {'Lose':>4} | {'Crisis':>6} | {'Prev.H':>6} | {'TM':>4}")
    print("  " + "─" * 100)
    for r in results:
        print(f"  {r['ticker']:<6} | {r['bnh_shares']:>7.0f} | {r['final_shares']:>9.2f} | {r['net_delta_shares']:>+8.2f} | {r['over_alpha_pct']:>+7.2f} | {r['trades_count']:>6} | {r['winning_cycles']:>3} | {r['losing_cycles']:>4} | {r['crisis_exits']:>6} | {r['preventive_harvests']:>6} | {r['tm_states']:>4}")

    over_alphas = [r['over_alpha_pct'] for r in results]
    avg_alpha = np.mean(over_alphas)
    std_alpha = np.std(over_alphas) if len(over_alphas) > 1 else 0
    t_stat = avg_alpha / (std_alpha / np.sqrt(len(over_alphas))) if std_alpha > 0 else 0

    total_crisis = sum(r['crisis_exits'] for r in results)
    total_prev = sum(r['preventive_harvests'] for r in results)

    print("\n" + "=" * 140)
    print(f"   Over-Alpha Promedio: {avg_alpha:+.2f}% | σ: {std_alpha:.2f}% | t-stat: {t_stat:.2f} ({'SÍ' if abs(t_stat) > 2.0 else 'NO'} significativo al 95%)")
    print(f"   Crisis Exits (VIX real): {total_crisis} | Preventive Harvests (Markov): {total_prev}")
    print("=" * 140 + "\n")
