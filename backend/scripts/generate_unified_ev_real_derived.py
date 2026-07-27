#!/usr/bin/env python3
"""
Generate Unified Real EV Tree & Hierarchical Fallbacks (S1 to S5)
================================================================──
Chunked Vault-First Aggregator (Lightning fast, Zero OOM).
Queries channel_snapshots and ohlcv_bars in chunks of 25 tickers,
computes 10-bar forward returns and aggregates metrics into hierarchical
fallbacks (S0, S1, S3).

Calculates per node:
  - p_bull (P(next pivot = MAX))
  - p_bear (P(next pivot = MIN))
  - e_ret_max (Expected return % to MAX pivot)
  - e_ret_min (Expected drawdown % to MIN pivot)
  - ev = p_bull * e_ret_max + p_bear * e_ret_min
  - rr_asymmetry = e_ret_max / |e_ret_min|

Output: backend/modules/quality_swing/domain/rules/rc_ev_unified_tree.json
"""
import sys
import json
import logging
from pathlib import Path
from collections import defaultdict
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.quality_swing.domain.rules.rc_slope_classifier import _classify_one

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GenerateUnifiedEVRealDerived")

OUTPUT_PATH = ROOT / "backend/modules/quality_swing/domain/rules/rc_ev_unified_tree.json"


def classify_sigma_bin(val: float) -> str:
    if val < -1.0:
        return "<<"
    elif val < -0.3:
        return "<"
    elif val <= 0.3:
        return "~"
    elif val <= 1.0:
        return ">"
    else:
        return ">>"


class NodeAccumulator:
    def __init__(self):
        self.n = 0
        self.n_bull = 0
        self.sum_ret_max = 0.0
        self.sum_ret_min = 0.0
        self.returns = []

    def add(self, fwd_ret: float):
        self.n += 1
        self.returns.append(fwd_ret)
        if fwd_ret > 0:
            self.n_bull += 1
            self.sum_ret_max += fwd_ret
        else:
            self.sum_ret_min += fwd_ret

    def format(self) -> dict:
        if self.n == 0:
            return {}
        p_bull = round(float(self.n_bull / self.n), 4)
        p_bear = round(1.0 - p_bull, 4)
        e_ret_max = round(float(self.sum_ret_max / max(self.n_bull, 1)) if self.n_bull > 0 else 0.02, 4)
        n_bear = self.n - self.n_bull
        e_ret_min = round(float(self.sum_ret_min / max(n_bear, 1)) if n_bear > 0 else -0.02, 4)

        ev = round(p_bull * e_ret_max + p_bear * e_ret_min, 4)
        abs_min = abs(e_ret_min) if abs(e_ret_min) > 1e-6 else 1e-6
        rr_asymmetry = round(e_ret_max / abs_min, 4)
        std_fwd = float(np.std(self.returns)) if len(self.returns) > 1 else 0.05
        sharpe = round(ev / (std_fwd + 1e-6), 4)

        return {
            "n": int(self.n),
            "p_bull": p_bull,
            "p_bear": p_bear,
            "ev": ev,
            "sharpe": sharpe,
            "e_ret_max": e_ret_max,
            "e_ret_min": e_ret_min,
            "rr_asymmetry": rr_asymmetry,
        }


def main():
    logger.info("Iniciando agregación por lotes de activos para rc_ev_unified_tree.json...")
    store = TimescaleDataStore()
    conn = store._conn()

    try:
        # Get tickers directly from market.ticker_metadata
        tickers_df = pd.read_sql("SELECT ticker FROM market.ticker_metadata", conn)
        all_tickers = tickers_df["ticker"].tolist()
        logger.info(f"Cargados {len(all_tickers)} activos desde market.ticker_metadata.")

        s0_acc = NodeAccumulator()
        s1_acc = defaultdict(NodeAccumulator)
        s3_acc = defaultdict(NodeAccumulator)

        chunk_size = 20
        total_chunks = (len(all_tickers) + chunk_size - 1) // chunk_size

        for idx, i in enumerate(range(0, len(all_tickers), chunk_size)):
            chunk_tickers = all_tickers[i:i + chunk_size]
            placeholders = ",".join(f"'{t}'" for t in chunk_tickers)

            q_snaps = f"""
                SELECT ticker, timestamp::date as date, tide_slope, current_slope, wave_slope,
                       sigma_current, sigma_wave, vwap_sigma_wave
                FROM engine.channel_snapshots
                WHERE ticker IN ({placeholders}) AND timeframe = '1d'
            """
            q_bars = f"""
                SELECT ticker, time::date as date, close
                FROM market.ohlcv_bars
                WHERE ticker IN ({placeholders}) AND timeframe = '1d'
            """

            df_snaps = pd.read_sql(q_snaps, conn)
            df_bars = pd.read_sql(q_bars, conn)

            if df_snaps.empty or df_bars.empty:
                continue

            df_bars["next_close"] = df_bars.groupby("ticker")["close"].shift(-10)
            df_merged = pd.merge(df_snaps, df_bars, on=["ticker", "date"]).dropna(subset=["next_close", "close"])

            if df_merged.empty:
                continue

            df_merged["fwd_return"] = (df_merged["next_close"] / df_merged["close"]) - 1.0

            for _, r in df_merged.iterrows():
                fwd_ret = float(r["fwd_return"])
                t_lbl = _classify_one(float(r['tide_slope']), "T")
                c_lbl = _classify_one(float(r['current_slope']), "C")
                w_lbl = _classify_one(float(r['wave_slope']), "W")
                sc_lbl = classify_sigma_bin(float(r['sigma_current']))
                sw_lbl = classify_sigma_bin(float(r['sigma_wave']))
                svw_lbl = classify_sigma_bin(float(r['vwap_sigma_wave']))

                # S0 Global
                s0_acc.add(fwd_ret)

                # S3 Triad
                k3 = f"{t_lbl}|{c_lbl}|{w_lbl}"
                s3_acc[k3].add(fwd_ret)

                # S1 Full 6D
                k1 = f"{t_lbl}|{c_lbl}|{w_lbl}|{sc_lbl}|{sw_lbl}|{svw_lbl}"
                s1_acc[k1].add(fwd_ret)

            logger.info(f"  Lote {idx + 1}/{total_chunks} procesado ({len(chunk_tickers)} activos). Total acumulado: {s0_acc.n:,} muestras.")

        s1_dict = {k: acc.format() for k, acc in s1_acc.items() if acc.n >= 5}
        s3_dict = {k: acc.format() for k, acc in s3_acc.items() if acc.n >= 5}

        tree = {
            "version": "v1_ev_unified_2026",
            "n_samples_total": int(s0_acc.n),
            "s0_global": s0_acc.format(),
            "s1_full": s1_dict,
            "s3_triad": s3_dict,
        }

        with open(OUTPUT_PATH, "w") as f:
            json.dump(tree, f, indent=2)

        logger.info(f"✅ ¡Compilación estocástica por lotes completada exitosamente! Guardado en {OUTPUT_PATH}")
        logger.info(f"  Total S0 Muestras: {s0_acc.n:,}")
        logger.info(f"  Total S1 Full Nodos: {len(s1_dict)}")
        logger.info(f"  Total S3 Triad Nodos: {len(s3_dict)}")

    finally:
        store._put(conn)

if __name__ == "__main__":
    main()
