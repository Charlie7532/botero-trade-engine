#!/usr/bin/env python3
"""
Forensic Benchmark — Swing EV Decision Engine Calibration Tool
================================================================
Auditoría forense completa de la cadena:
  E[R|S_t] → Ω → drift → instrucción → ejecución → resultado (Δ shares)

5 Módulos de Reporte:
  1. BENCHMARK: Share accumulation vs Buy & Hold (100 acciones iniciales)
  2. AÑO A AÑO: Desglose anual de Δ shares ganadas/perdidas
  3. POR SEÑAL: Estadística por instrucción (ACCUMULATE, HARVEST, EXIT_CRISIS, OBSERVE)
     + señales que NUNCA se emitieron pero existían en la fact table
  4. PRECISIÓN PREDICTIVA: E[R] predicho vs retorno real a 20d (embudo invertido)
  5. TRANSICIONES MARKOV: Probabilidad predicha vs frecuencia observada

Unidad de medida: ACCIONES del título evaluado (no dólares).
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
    decide, configure, _classify_state, _load_ticker_table, lookup_ev,
    project_next_state,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ForensicBenchmark")


def _load_vix_series(conn):
    q = """SELECT time AS timestamp, close AS vix FROM market.ohlcv_bars
           WHERE ticker = 'VIX' AND timeframe = '1d' AND close > 0 ORDER BY time"""
    df = pd.read_sql(q, conn)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.floor("D")
    return df.set_index("timestamp")["vix"]


def _build_transition_matrix_insample(conn, ticker, cutoff="2019-12-31"):
    q = f"""SELECT timestamp, tide_slope, current_slope, vwap_sigma_wave
            FROM engine.channel_snapshots
            WHERE ticker = '{ticker}' AND timeframe = '1d' AND timestamp <= '{cutoff}'
            ORDER BY timestamp"""
    df = pd.read_sql(q, conn)
    if len(df) < 50:
        return None
    df["vwap_filtered"] = df["vwap_sigma_wave"].ewm(span=5, adjust=False).mean()
    states = []
    for _, r in df.iterrows():
        _, _, _, sk = _classify_state(float(r["tide_slope"]), float(r["current_slope"]), float(r["vwap_filtered"]))
        states.append(sk)
    tc = defaultdict(lambda: defaultdict(int))
    for i in range(len(states) - 1):
        tc[states[i]][states[i + 1]] += 1
    tm = {}
    for fs, td in tc.items():
        total = sum(td.values())
        if total >= 5:
            tm[fs] = {k: v / total for k, v in td.items()}
    return tm if tm else None


def run_forensic_benchmark(ticker: str, conn, vix_series, initial_shares: float = 100.0,
                           oos_start: str = "2020-01-01"):
    """Run full forensic benchmark for one ticker."""

    configure(calibration_cutoff="2019-12-31")
    tm = _build_transition_matrix_insample(conn, ticker)

    # Load data
    q_snaps = f"""SELECT ticker, timestamp, tide_slope, current_slope, vwap_sigma_wave
                  FROM engine.channel_snapshots WHERE ticker='{ticker}' AND timeframe='1d' ORDER BY timestamp"""
    q_bars = f"""SELECT ticker, time AS timestamp, close
                 FROM market.ohlcv_bars WHERE ticker='{ticker}' AND timeframe='1d' AND close>0 ORDER BY time"""
    df_s = pd.read_sql(q_snaps, conn)
    df_b = pd.read_sql(q_bars, conn)
    if df_s.empty or df_b.empty:
        return None

    df_s["timestamp"] = pd.to_datetime(df_s["timestamp"], utc=True).dt.floor("D")
    df_b["timestamp"] = pd.to_datetime(df_b["timestamp"], utc=True).dt.floor("D")
    df = pd.merge(df_s, df_b, on=["ticker", "timestamp"]).sort_values("timestamp").reset_index(drop=True)
    df["vwap_f"] = df["vwap_sigma_wave"].ewm(span=5, adjust=False).mean()
    df["vwap_drift"] = df["vwap_f"].diff().fillna(0.0)
    df["fwd_ret_20d"] = df["close"].pct_change(20).shift(-20)

    split = pd.to_datetime(oos_start, utc=True)
    df_oos = df[df["timestamp"] >= split].copy()
    if df_oos.empty:
        return None

    p_end = float(df_oos["close"].iloc[-1])

    # ── Tracking structures ──
    shares = initial_shares
    cash = 0.0
    last_harvest_price = None
    days_in_cash = 0

    # Per-signal stats
    signal_stats = defaultdict(lambda: {"count": 0, "executed": 0, "shs_gained": 0.0, "shs_lost": 0.0,
                                        "wins": 0, "losses": 0, "timely": 0, "correct_er": 0})
    # Year-by-year
    yearly = defaultdict(lambda: {"shs_start": 0.0, "shs_end": 0.0, "trades": 0, "wins": 0, "losses": 0})
    # E[R] prediction accuracy
    er_predictions = []  # (predicted_ev, actual_fwd_ret, state_key, fallback_level, omega)
    # Transition accuracy
    transition_checks = []  # (from_state, predicted_next, actual_next, probability)
    # State tracking for transitions
    prev_state = None
    prev_proj = None
    # All states encountered
    states_encountered = set()

    current_year = None

    for idx, r in df_oos.iterrows():
        dt = r["timestamp"]
        year = dt.year
        p_curr = float(r["close"])
        t_slope = float(r["tide_slope"])
        c_slope = float(r["current_slope"])
        svw = float(r["vwap_f"])
        svw_drift = float(r["vwap_drift"])
        fwd_ret = r["fwd_ret_20d"] if pd.notna(r["fwd_ret_20d"]) else None

        # VIX
        vix_val = 20.0
        if dt in vix_series.index:
            vix_val = float(vix_series.loc[dt])
        else:
            prior = vix_series[vix_series.index <= dt]
            if not prior.empty:
                vix_val = float(prior.iloc[-1])

        # Year tracking
        if current_year != year:
            if current_year is not None:
                equiv = (cash + shares * p_curr) / p_curr
                yearly[current_year]["shs_end"] = equiv
            current_year = year
            equiv_start = (cash + shares * p_curr) / p_curr
            yearly[year]["shs_start"] = equiv_start

        # ── Decision ──
        decision = decide(ticker=ticker, timestamp=dt.strftime("%Y-%m-%d"),
                          t_slope=t_slope, c_slope=c_slope, svw_filtered=svw,
                          svw_drift=svw_drift, vix=vix_val, transition_matrix=tm)

        action = decision.action
        _, _, _, state_key = _classify_state(t_slope, c_slope, svw)
        states_encountered.add(state_key)

        # ── E[R] prediction tracking ──
        if fwd_ret is not None:
            er_predictions.append({
                "predicted_ev": decision.ev_net,
                "actual_ret": fwd_ret,
                "state_key": state_key,
                "fallback_level": decision.fallback_level,
                "omega": decision.omega,
                "vix": vix_val,
                "date": dt.strftime("%Y-%m-%d"),
            })

        # ── Transition tracking ──
        if prev_state is not None and prev_proj is not None:
            transition_checks.append({
                "from_state": prev_state,
                "predicted_next": prev_proj.most_likely_next,
                "predicted_prob": prev_proj.next_probability,
                "actual_next": state_key,
                "hit": state_key == prev_proj.most_likely_next,
            })
        proj = project_next_state(state_key, tm)
        prev_state = state_key
        prev_proj = proj

        # ── Signal counting ──
        signal_stats[action]["count"] += 1

        # Was the signal timely? (price moved in predicted direction within 5 bars)
        if fwd_ret is not None:
            if action in ("ACCUMULATE",) and fwd_ret > 0:
                signal_stats[action]["timely"] += 1
            elif action in ("HARVEST", "EXIT_CRISIS") and fwd_ret < 0:
                signal_stats[action]["timely"] += 1
            elif action == "OBSERVE":
                signal_stats[action]["timely"] += 1  # neutral is always "timely"

            # Was E[R] prediction correct? (actual within ±1σ of predicted)
            ev_pred = decision.ev_net
            variance = decision.variance if hasattr(decision, 'variance') else 0.01
            sigma = variance ** 0.5
            if abs(fwd_ret - ev_pred) <= sigma:
                signal_stats[action]["correct_er"] += 1

        # ── Execution logic ──
        if cash > 1.0:
            days_in_cash += 1
        else:
            days_in_cash = 0

        executed = False
        shs_before = shares

        # BUY BACK
        if cash > 1.0:
            has_discount = last_harvest_price is not None and p_curr <= last_harvest_price * 0.97
            is_strong_acc = action == "ACCUMULATE" and decision.ev_net >= 0.01
            time_guard = days_in_cash >= 30 and t_slope >= 0.0

            if has_discount or is_strong_acc or time_guard or last_harvest_price is None:
                buy_qty = cash / p_curr
                shares += buy_qty
                cash = 0.0
                days_in_cash = 0
                executed = True

                if last_harvest_price:
                    if p_curr < last_harvest_price:
                        signal_stats[action]["wins"] += 1
                        signal_stats[action]["shs_gained"] += (shares - shs_before)
                        yearly[year]["wins"] += 1
                    else:
                        signal_stats[action]["losses"] += 1
                        signal_stats[action]["shs_lost"] += abs(shares - shs_before - (cash / p_curr if cash > 0 else 0))
                        yearly[year]["losses"] += 1
                last_harvest_price = None

        # HARVEST
        elif action == "HARVEST" and cash <= 1.0:
            excess = max(shares - initial_shares * 0.50, 0.0)
            if excess > 0.5:
                trim_frac = decision.sizing_fraction if decision.sizing_fraction > 0 else 0.20
                trim_qty = excess * trim_frac
                shares -= trim_qty
                cash += trim_qty * p_curr
                last_harvest_price = p_curr
                days_in_cash = 0
                executed = True
                yearly[year]["trades"] += 1

        # EXIT CRISIS
        elif action == "EXIT_CRISIS" and shares > initial_shares * 0.50:
            excess = shares - initial_shares * 0.50
            trim_qty = excess * decision.sizing_fraction
            shares -= trim_qty
            cash += trim_qty * p_curr
            last_harvest_price = p_curr
            days_in_cash = 0
            executed = True
            yearly[year]["trades"] += 1

        if executed:
            signal_stats[action]["executed"] += 1
            yearly[year]["trades"] += (1 if action != "HARVEST" and action != "EXIT_CRISIS" else 0)

    # Final year close
    if current_year:
        equiv = (cash + shares * p_end) / p_end
        yearly[current_year]["shs_end"] = equiv

    final_val = cash + shares * p_end
    equiv_shares = final_val / p_end

    # ── States from fact table that were NEVER encountered in OOS ──
    table = _load_ticker_table(ticker)
    all_trained_states = set(table.get("fact_entries", {}).keys()) if table else set()
    unused_states = all_trained_states - states_encountered
    # States encountered in OOS but NOT in fact table (fallback-only)
    untrained_states = states_encountered - all_trained_states

    return {
        "ticker": ticker,
        "bnh_shares": initial_shares,
        "final_equiv": round(equiv_shares, 2),
        "delta_shares": round(equiv_shares - initial_shares, 2),
        "over_alpha_pct": round((equiv_shares - initial_shares) / initial_shares * 100, 2),
        "signal_stats": dict(signal_stats),
        "yearly": dict(yearly),
        "er_predictions": er_predictions,
        "transition_checks": transition_checks,
        "states_encountered": len(states_encountered),
        "trained_states": len(all_trained_states),
        "unused_states": unused_states,
        "untrained_states": untrained_states,
    }


def print_report(res):
    """Print the full forensic report for one ticker."""
    tk = res["ticker"]

    # ═══ MODULE 1: BENCHMARK ═══
    print(f"\n{'═' * 100}")
    print(f"  FORENSIC BENCHMARK: {tk} | OOS 2020-2026")
    print(f"{'═' * 100}")
    print(f"  BnH:         {res['bnh_shares']:.0f} acciones (nunca vendió)")
    print(f"  Estrategia:  {res['final_equiv']:.2f} acciones equivalentes")
    print(f"  Δ Shares:    {res['delta_shares']:+.2f} acciones")
    print(f"  Over-Alpha:  {res['over_alpha_pct']:+.2f}%")

    # ═══ MODULE 2: YEAR BY YEAR ═══
    print(f"\n  {'─' * 90}")
    print(f"  {'Año':>6} | {'Shs Inicio':>10} | {'Shs Fin':>9} | {'Δ Año':>8} | {'Trades':>6} | {'Win':>3} | {'Lose':>4}")
    print(f"  {'─' * 90}")
    for year in sorted(res["yearly"].keys()):
        y = res["yearly"][year]
        delta = y["shs_end"] - y["shs_start"]
        print(f"  {year:>6} | {y['shs_start']:>10.2f} | {y['shs_end']:>9.2f} | {delta:>+8.2f} | {y['trades']:>6} | {y['wins']:>3} | {y['losses']:>4}")

    # ═══ MODULE 3: PER-SIGNAL FORENSICS ═══
    print(f"\n  {'─' * 90}")
    print(f"  ANÁLISIS POR SEÑAL (instrucción emitida por el motor)")
    print(f"  {'─' * 90}")
    print(f"  {'Señal':<15} | {'Count':>5} | {'Exec':>4} | {'Win':>3} | {'Lose':>4} | {'Shs+':>7} | {'Shs-':>7} | {'Timely%':>7} | {'ER OK%':>6}")
    print(f"  {'─' * 90}")

    all_signals = ["ACCUMULATE", "HARVEST", "EXIT_CRISIS", "OBSERVE"]
    for sig in all_signals:
        s = res["signal_stats"].get(sig, {"count": 0, "executed": 0, "wins": 0, "losses": 0,
                                           "shs_gained": 0, "shs_lost": 0, "timely": 0, "correct_er": 0})
        timely_pct = s["timely"] / s["count"] * 100 if s["count"] > 0 else 0
        er_ok_pct = s["correct_er"] / s["count"] * 100 if s["count"] > 0 else 0
        marker = "  " if s["count"] > 0 else "⚠️"
        print(f"  {marker}{sig:<13} | {s['count']:>5} | {s['executed']:>4} | {s['wins']:>3} | {s['losses']:>4} | "
              f"{s['shs_gained']:>+7.2f} | {s['shs_lost']:>-7.2f} | {timely_pct:>6.1f}% | {er_ok_pct:>5.1f}%")

    # Signals that never fired
    never_fired = [s for s in all_signals if res["signal_stats"].get(s, {}).get("count", 0) == 0]
    if never_fired:
        print(f"\n  ⚠️  SEÑALES NUNCA EMITIDAS: {', '.join(never_fired)}")

    # ═══ MODULE 4: E[R] PREDICTION ACCURACY (inverted funnel) ═══
    print(f"\n  {'─' * 90}")
    print(f"  PRECISIÓN PREDICTIVA: E[R] predicho vs retorno real a 20d")
    print(f"  {'─' * 90}")

    preds = res["er_predictions"]
    if preds:
        df_p = pd.DataFrame(preds)
        df_p["error"] = df_p["actual_ret"] - df_p["predicted_ev"]
        df_p["abs_error"] = df_p["error"].abs()

        # Bucket by predicted E[R]
        bins = [-np.inf, -0.03, -0.01, 0.01, 0.03, 0.05, np.inf]
        labels = ["<-3%", "-3%:-1%", "-1%:+1%", "+1%:+3%", "+3%:+5%", ">+5%"]
        df_p["ev_bucket"] = pd.cut(df_p["predicted_ev"], bins=bins, labels=labels)

        print(f"  {'E[R] Predicho':<14} | {'n':>5} | {'Ret Real':>9} | {'Error Abs':>9} | {'Direction%':>10}")
        print(f"  {'─' * 65}")
        for bucket in labels:
            sub = df_p[df_p["ev_bucket"] == bucket]
            if len(sub) < 3:
                continue
            avg_real = sub["actual_ret"].mean()
            avg_err = sub["abs_error"].mean()
            # Direction accuracy: did actual return have same sign as predicted?
            dir_ok = ((sub["predicted_ev"] * sub["actual_ret"]) > 0).mean() * 100
            print(f"  {bucket:<14} | {len(sub):>5} | {avg_real*100:>+8.2f}% | {avg_err*100:>8.2f}% | {dir_ok:>9.1f}%")

    # ═══ MODULE 5: TRANSITION PREDICTION VALIDATION ═══
    print(f"\n  {'─' * 90}")
    print(f"  VALIDACIÓN DE TRANSICIONES MARKOV")
    print(f"  {'─' * 90}")

    checks = res["transition_checks"]
    if checks:
        df_t = pd.DataFrame(checks)
        prob_bins = [0, 0.30, 0.50, 0.70, 1.01]
        prob_labels = ["[0, 0.30)", "[0.30, 0.50)", "[0.50, 0.70)", "[0.70, 1.00]"]
        df_t["prob_bucket"] = pd.cut(df_t["predicted_prob"], bins=prob_bins, labels=prob_labels, right=False)

        print(f"  {'P(S_t+1)':<15} | {'n Trans':>7} | {'Aciertos':>8} | {'Hit Rate':>8} | {'vs Random':>9}")
        print(f"  {'─' * 60}")
        for bucket in prob_labels:
            sub = df_t[df_t["prob_bucket"] == bucket]
            if len(sub) < 3:
                continue
            hits = sub["hit"].sum()
            hit_rate = hits / len(sub) * 100
            # Random baseline: 1/n_states
            n_unique = df_t["actual_next"].nunique()
            random_rate = 100.0 / n_unique if n_unique > 0 else 0
            print(f"  {bucket:<15} | {len(sub):>7} | {hits:>8} | {hit_rate:>7.1f}% | {hit_rate - random_rate:>+8.1f}pp")

    # ═══ STATES COVERAGE ═══
    print(f"\n  {'─' * 90}")
    print(f"  COBERTURA DE ESTADOS")
    print(f"  {'─' * 90}")
    print(f"  Estados entrenados (fact table):       {res['trained_states']}")
    print(f"  Estados encontrados en OOS:             {res['states_encountered']}")
    print(f"  Estados entrenados NUNCA vistos en OOS: {len(res['unused_states'])}")
    if res["unused_states"]:
        for s in sorted(res["unused_states"])[:10]:
            table = _load_ticker_table(tk)
            e = table["fact_entries"].get(s, {}) if table else {}
            n = e.get("n", 0)
            ev = e.get("ev_net", 0)
            print(f"    {s:<20} n={n:<5} E[R]={ev*100:+.2f}% (entrenada pero nunca vista en OOS)")
    print(f"  Estados OOS sin entrenamiento (fallback): {len(res['untrained_states'])}")
    if res["untrained_states"]:
        for s in sorted(res["untrained_states"]):
            print(f"    {s:<20} (solo disponible vía fallback L1/L0)")

    print(f"\n{'═' * 100}\n")


if __name__ == "__main__":
    tickers = sys.argv[1:] if len(sys.argv) > 1 else ["AAPL", "COST", "JPM"]

    store = TimescaleDataStore()
    conn = store._conn()

    vix_series = _load_vix_series(conn)

    try:
        all_results = []
        for tk in tickers:
            res = run_forensic_benchmark(tk, conn, vix_series)
            if res:
                print_report(res)
                all_results.append(res)

        # Cross-ticker summary
        if len(all_results) > 1:
            print(f"\n{'═' * 100}")
            print(f"  RESUMEN CROSS-TICKER")
            print(f"{'═' * 100}")
            print(f"  {'Ticker':<6} | {'BnH':>5} | {'Final':>7} | {'Δ Shs':>7} | {'α%':>6} | {'Trades':>6} | {'States':>6}")
            print(f"  {'─' * 60}")
            for r in all_results:
                total_trades = sum(s.get("executed", 0) for s in r["signal_stats"].values())
                print(f"  {r['ticker']:<6} | {r['bnh_shares']:>5.0f} | {r['final_equiv']:>7.2f} | "
                      f"{r['delta_shares']:>+7.2f} | {r['over_alpha_pct']:>+5.2f}% | {total_trades:>6} | {r['states_encountered']:>6}")

            alphas = [r["over_alpha_pct"] for r in all_results]
            avg = np.mean(alphas)
            std = np.std(alphas) if len(alphas) > 1 else 0
            t_stat = avg / (std / np.sqrt(len(alphas))) if std > 0 else 0
            print(f"\n  Over-Alpha Promedio: {avg:+.2f}% | σ: {std:.2f}% | t-stat: {t_stat:.2f}")
            print(f"{'═' * 100}\n")
    finally:
        try:
            store._put(conn)
        except Exception:
            pass
