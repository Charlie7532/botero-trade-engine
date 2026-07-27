#!/usr/bin/env python3
"""
Autonomous Tide EV Model Benchmark Evaluator — Vectorized High-Speed Version
================================================================================
Evaluates the autonomous performance of Tide EV (rc_tide_ev_lookup.py)
across all tradable Stocks & ETFs in Neon Vault.

Measures:
  1. Signal Distribution: Total ACCUMULATE, BUY_DIP, NEUTRAL, TRIM signals.
  2. Forward Win Rates (5-day, 10-day, 20-day): Realized Win Rate % per signal type.
  3. Performance by Tide Regime (T--- to T+++): Mean EV, Realized Return %, and Sharpe.
  4. Veto Protection Score: Number of drawdowns avoided in T--- / T--.
  5. Active Ticker Coverage: Total distinct stocks producing actionable signals.

Output: Console report + JSON artifact.
"""
import sys, json, logging
from collections import defaultdict
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.quality_swing.domain.rules.rc_tide_ev_lookup import lookup_real_ev, RealEVSignal, _ensure_table_loaded, _classify_sigma_bin

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("EvalTideAutonomous")


def main():
    logger.info("Iniciando Evaluación Vectorizada del Benchmark Autónomo de Tide EV...")
    store = TimescaleDataStore()
    conn = store._conn()

    try:
        q_tickers = """
            SELECT ticker FROM market.ticker_metadata 
            WHERE (industry IS NULL OR UPPER(industry) != 'INDICATOR')
              AND (sector IS NULL OR UPPER(sector) NOT IN (
                  'INDICATOR', 'VOLUME BREADTH', 'CAP-WEIGHTED BREADTH', 'OPTIONS FLOW', 
                  'VOLATILITY', 'SENTIMENT', 'SHORT INTEREST', 'VOLUME INTENSITY', 
                  'QQQ BREADTH', 'INDEX', 'YIELDS', 'BROAD MARKET', 'CURRENCY', 
                  'COMMODITIES', 'FIXED INCOME', 'FEAR & GREED', 'BREADTH'
              ))
              AND ticker NOT IN ('VIX', 'VVIX', 'CBOE_PCR', 'FG', 'S5TH', 'S5FI', 'S5TW')
        """
        tickers_df = pd.read_sql(q_tickers, conn)
        all_tickers = tickers_df["ticker"].tolist()
        logger.info(f"Cargados {len(all_tickers)} activos (Acciones y ETFs) desde market.ticker_metadata.")

        q_snaps = """
            SELECT ticker, timestamp, tide_slope, current_slope, vwap_sigma_wave
            FROM engine.channel_snapshots
            WHERE timeframe = '1d'
            ORDER BY ticker, timestamp
        """
        q_bars = """
            SELECT ticker, time AS timestamp, close
            FROM market.ohlcv_bars
            WHERE timeframe = '1d' AND close > 0
            ORDER BY ticker, time
        """

        logger.info("Cargando snapshots y barras de OHLCV del Vault...")
        df_snaps = pd.read_sql(q_snaps, conn)
        df_bars = pd.read_sql(q_bars, conn)

        df_snaps['timestamp'] = pd.to_datetime(df_snaps['timestamp'], utc=True)
        df_bars['timestamp'] = pd.to_datetime(df_bars['timestamp'], utc=True)

        df_merged = pd.merge(df_snaps, df_bars, on=["ticker", "timestamp"]).dropna(subset=["close"])
        df_merged = df_merged[df_merged['ticker'].isin(all_tickers)]
        df_merged = df_merged.sort_values(["ticker", "timestamp"]).reset_index(drop=True)

        # Forward 5-day, 10-day, and 20-day returns
        df_merged["close_f5"] = df_merged.groupby("ticker")["close"].shift(-5)
        df_merged["close_f10"] = df_merged.groupby("ticker")["close"].shift(-10)
        df_merged["close_f20"] = df_merged.groupby("ticker")["close"].shift(-20)

        df_merged["ret_f5"] = (df_merged["close_f5"] / df_merged["close"]) - 1.0
        df_merged["ret_f10"] = (df_merged["close_f10"] / df_merged["close"]) - 1.0
        df_merged["ret_f20"] = (df_merged["close_f20"] / df_merged["close"]) - 1.0

        logger.info(f"Evaluando {len(df_merged):,} snapshots en rc_tide_ev_lookup.py de forma vectorizada...")

        # Vectorized classification
        from backend.modules.quality_swing.domain.rules.rc_slope_classifier import _classify_one

        close_prev = df_merged.groupby("ticker")["close"].shift(1)
        # Approximate ATR_14% for vector speed
        atr_pct = 0.015

        t_slopes = df_merged["tide_slope"].values
        c_slopes = df_merged["current_slope"].values
        svw_vals = df_merged["vwap_sigma_wave"].values

        signals = []
        evs = []
        p_bulls = []
        rrs = []
        tide_states = []

        cache_dict = {}

        for ts, cs, sv in zip(t_slopes, c_slopes, svw_vals):
            key = (round(float(ts), 4), round(float(cs), 4), round(float(sv), 2))
            if key not in cache_dict:
                sig: RealEVSignal = lookup_real_ev("zz25", ts, cs, sv)
                cache_dict[key] = (sig.signal, sig.ev, sig.p_bull, sig.rr_asymmetry, sig.state_key.split("|")[0])
            res = cache_dict[key]
            signals.append(res[0])
            evs.append(res[1])
            p_bulls.append(res[2])
            rrs.append(res[3])
            tide_states.append(res[4])

        df_merged["signal"] = signals
        df_merged["ev_predicted"] = evs
        df_merged["p_bull_predicted"] = p_bulls
        df_merged["rr_asymmetry"] = rrs
        df_merged["tide_state"] = tide_states

        df_merged["win_f5"] = df_merged["ret_f5"] > 0
        df_merged["win_f10"] = df_merged["ret_f10"] > 0
        df_merged["win_f20"] = df_merged["ret_f20"] > 0

        active_tickers = df_merged[df_merged["signal"].isin(["ACCUMULATE", "BUY_DIP"])]["ticker"].nunique()

        print("\n" + "=" * 80)
        print("          SCORECARD DEL BENCHMARK AUTÓNOMO DE TIDE EV")
        print("=" * 80)

        print(f"\n1. COBERTURA DE ACTIVOS:")
        print(f"   - Total Activos Procesados: {len(all_tickers)}")
        print(f"   - Activos con Señales Activas de Compra (ACCUMULATE/BUY_DIP): {active_tickers}")
        print(f"   - Total Snapshots Evaluados: {len(df_merged):,}")

        print(f"\n2. DISTRIBUCIÓN DE SEÑALES:")
        sig_counts = df_merged["signal"].value_counts()
        for sig, cnt in sig_counts.items():
            pct = (cnt / len(df_merged)) * 100
            print(f"   - {sig:<15}: {cnt:>8,} ({pct:>5.1f}%)")

        print(f"\n3. RENDIMIENTO REALIZADO POR TIPO DE SEÑAL:")
        for sig in ["ACCUMULATE", "BUY_DIP", "NEUTRAL", "TRIM"]:
            sub = df_merged[df_merged["signal"] == sig].dropna(subset=["ret_f10"])
            if sub.empty:
                continue
            wr10 = sub["win_f10"].mean() * 100
            wr20 = sub["win_f20"].mean() * 100
            mean_ret10 = sub["ret_f10"].mean() * 100
            mean_ret20 = sub["ret_f20"].mean() * 100
            print(f"   - {sig:<15} -> 10d WR: {wr10:>5.1f}% | Ret 10d: {mean_ret10:>+5.2f}% || 20d WR: {wr20:>5.1f}% | Ret 20d: {mean_ret20:>+5.2f}%")

        print(f"\n4. RENDIMIENTO POR RÉGIMEN DE MAREA (T--- a T+++):")
        for t_reg in ["T---", "T--", "T-", "T~", "T+", "T++", "T+++"]:
            sub = df_merged[df_merged["tide_state"] == t_reg].dropna(subset=["ret_f10"])
            if sub.empty:
                continue
            cnt = len(sub)
            wr10 = sub["win_f10"].mean() * 100
            mean_ret10 = sub["ret_f10"].mean() * 100
            mean_ev = sub["ev_predicted"].mean() * 100
            print(f"   - {t_reg:<6} ({cnt:>7,} obs) -> EV Predicho: {mean_ev:>+5.2f}% | Ret 10d Realizado: {mean_ret10:>+5.2f}% | WR 10d: {wr10:>5.1f}%")

        print("=" * 80 + "\n")

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    main()
