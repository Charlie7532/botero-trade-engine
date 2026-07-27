#!/usr/bin/env python3
"""
Audit Multiscale Credibility Benchmark — Real EV vs Next Zigzag Pivot (2.5%, 5.0%, 7.5%)
========================================================================================
Vectorized & Optimized laboratory script (NumPy searchsorted binary search):
Measures empirical accuracy of Real EV predicted envelopes [e_min, e_max]
measured at the EXACT next real Zigzag pivot across 712 tickers and 4.57M samples.

Clean Architecture: Script (delivery mechanism).
"""
import sys
import json
import logging
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.quality_swing.domain.rules.rc_multiscale_ev_lookup import lookup_multiscale_kinematic_ev

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AuditMultiscaleCredibilityBenchmark")

RULES_JSON_PATH = ROOT / "backend/modules/quality_swing/domain/rules/rc_multiscale_regime_rules.json"


def main():
    logger.info("=== AUDITORÍA DE CREDIBILIDAD MULTIESCALA: REAL EV vs PRÓXIMO PIVOTE ZIGZAG (VECTORIZADO) ===")
    store = TimescaleDataStore()
    conn = store._conn()

    try:
        tickers_df = pd.read_sql("SELECT ticker FROM market.ticker_metadata", conn)
        all_tickers = tickers_df["ticker"].tolist()
        logger.info(f"Cargados {len(all_tickers)} activos del Vault.")

        logger.info("Cargando y vectorizando pivotes Zigzag (2.5%, 5.0%, 7.5%)...")
        zz_all = pd.read_sql("""
            SELECT ticker, timestamp::date as date, tp_type, price, min_swing_pct
            FROM engine.zigzag_points
            ORDER BY ticker, timestamp
        """, conn)

        # Pre-build NumPy lookup dictionaries for binary search: (ticker, scale, tp_type) -> arrays
        pivot_numpy = {}
        for (tk, scale, tp_type), group in zz_all.groupby(["ticker", "min_swing_pct", "tp_type"]):
            pivot_numpy[(tk, float(scale), tp_type)] = {
                "dates": group["date"].values,
                "prices": group["price"].values,
            }

        stats = {
            "piso_25": {"n": 0, "in_bounds": 0, "upside_surprise": 0, "breaches": 0, "returns": []},
            "piso_50": {"n": 0, "in_bounds": 0, "upside_surprise": 0, "breaches": 0, "returns": []},
            "piso_75": {"n": 0, "in_bounds": 0, "upside_surprise": 0, "breaches": 0, "returns": []},
            "piso_extreme_gt75": {"n": 0, "in_bounds": 0, "upside_surprise": 0, "breaches": 0, "returns": []},
            "techo_25": {"n": 0, "in_bounds": 0, "upside_surprise": 0, "breaches": 0, "returns": []},
            "techo_50": {"n": 0, "in_bounds": 0, "upside_surprise": 0, "breaches": 0, "returns": []},
            "techo_75": {"n": 0, "in_bounds": 0, "upside_surprise": 0, "breaches": 0, "returns": []},
            "techo_extreme_gt75": {"n": 0, "in_bounds": 0, "upside_surprise": 0, "breaches": 0, "returns": []},
        }

        chunk_size = 50
        total_chunks = (len(all_tickers) + chunk_size - 1) // chunk_size

        for idx, i in enumerate(range(0, len(all_tickers), chunk_size)):
            chunk_tickers = all_tickers[i:i + chunk_size]
            placeholders = ",".join(f"'{t}'" for t in chunk_tickers)

            q_snaps = f"""
                SELECT ticker, timestamp::date as date, tide_slope, current_slope, wave_slope,
                       sigma_current, sigma_wave, vwap_sigma_wave
                FROM engine.channel_snapshots
                WHERE ticker IN ({placeholders}) AND timeframe = '1d'
                ORDER BY ticker, timestamp
            """
            q_bars = f"""
                SELECT ticker, time::date as date, close
                FROM market.ohlcv_bars
                WHERE ticker IN ({placeholders}) AND timeframe = '1d'
                ORDER BY ticker, time
            """

            df_snaps = pd.read_sql(q_snaps, conn)
            df_bars = pd.read_sql(q_bars, conn)

            if df_snaps.empty or df_bars.empty:
                continue

            df_merged = pd.merge(df_snaps, df_bars, on=["ticker", "date"]).sort_values(["ticker", "date"])
            if df_merged.empty:
                continue

            df_merged["vwap_sigma_wave_t2"] = df_merged.groupby("ticker")["vwap_sigma_wave"].shift(2)
            df_merged["delta_svw"] = df_merged["vwap_sigma_wave"] - df_merged["vwap_sigma_wave_t2"].fillna(df_merged["vwap_sigma_wave"])

            # Fast NumPy arrays iteration
            tk_arr = df_merged["ticker"].values
            dt_arr = df_merged["date"].values
            close_arr = df_merged["close"].values
            t_arr = df_merged["tide_slope"].values
            c_arr = df_merged["current_slope"].values
            w_arr = df_merged["wave_slope"].values
            sc_arr = df_merged["sigma_current"].values
            sw_arr = df_merged["sigma_wave"].values
            svw_arr = df_merged["vwap_sigma_wave"].values
            delta_arr = df_merged["delta_svw"].values

            for j in range(len(df_merged)):
                tk = tk_arr[j]
                dt = dt_arr[j]
                close_t0 = float(close_arr[j])
                if close_t0 <= 0: continue

                svw = float(svw_arr[j])
                delta_svw = float(delta_arr[j])

                sig = lookup_multiscale_kinematic_ev(
                    tide_slope=t_arr[j],
                    current_slope=c_arr[j],
                    wave_slope=w_arr[j],
                    sigma_current=sc_arr[j],
                    sigma_wave=sw_arr[j],
                    vwap_sigma_wave=svw,
                    delta_svw=delta_svw,
                )

                e_max_pred = sig.e_ret_max if sig else 0.04
                e_min_pred = sig.e_ret_min if sig else -0.02

                def get_next_pivot_return_fast(scale_pct, target_tp_type):
                    pdata = pivot_numpy.get((tk, float(scale_pct), target_tp_type))
                    if pdata is None: return None
                    dates = pdata["dates"]
                    pos = np.searchsorted(dates, dt, side="right")
                    if pos >= len(dates): return None
                    next_price = float(pdata["prices"][pos])
                    return (next_price / close_t0) - 1.0

                # Piso
                if svw <= -0.30 and delta_svw > 0:
                    scale_key = "piso_extreme_gt75" if (svw <= -1.0 and delta_svw > 0.40) else \
                                "piso_75" if svw <= -0.80 else \
                                "piso_50" if svw <= -0.50 else "piso_25"
                    scale_pct = 0.075 if "75" in scale_key else 0.050 if "50" in scale_key else 0.025
                    ret_piv = get_next_pivot_return_fast(scale_pct, "MAX")

                    if ret_piv is not None:
                        st = stats[scale_key]
                        st["n"] += 1
                        st["returns"].append(ret_piv)
                        if ret_piv >= e_max_pred: st["upside_surprise"] += 1
                        elif ret_piv >= e_min_pred: st["in_bounds"] += 1
                        else: st["breaches"] += 1

                # Techo
                elif svw >= 0.30 and delta_svw < 0:
                    scale_key = "techo_extreme_gt75" if (svw >= 1.0 and delta_svw < -0.40) else \
                                "techo_75" if svw >= 0.80 else \
                                "techo_50" if svw >= 0.50 else "techo_25"
                    scale_pct = 0.075 if "75" in scale_key else 0.050 if "50" in scale_key else 0.025
                    ret_piv = get_next_pivot_return_fast(scale_pct, "MIN")

                    if ret_piv is not None:
                        st = stats[scale_key]
                        st["n"] += 1
                        st["returns"].append(ret_piv)
                        if ret_piv <= e_min_pred: st["upside_surprise"] += 1
                        elif ret_piv <= e_max_pred: st["in_bounds"] += 1
                        else: st["breaches"] += 1

            logger.info(f"  Lote {idx + 1}/{total_chunks} procesado.")

        print("\n" + "="*115)
        print("      📊 ATRIBUCIÓN DE CREDIBILIDAD DE ENVOLVENTE AL PRÓXIMO PIVOTE REAL (VECTORIZADO)")
        print("="*115)
        print(f"{'Escala Cinemática':<22} | {'Muestras':<9} | {'En Rango (%)':<14} | {'Sorpresa (+%)':<14} | {'Violación (%)':<14} | Retorno Prom")
        print("-" * 115)

        results_json = {}
        for sk, st in stats.items():
            n = st["n"]
            if n > 0:
                in_b = round((st["in_bounds"] / n) * 100.0, 2)
                up_s = round((st["upside_surprise"] / n) * 100.0, 2)
                brch = round((st["breaches"] / n) * 100.0, 2)
                avg_ret = round(float(np.mean(st["returns"])) * 100.0, 2)
            else:
                in_b = up_s = brch = avg_ret = 0.0

            print(f"{sk:<22} | {n:<9,} | {in_b:>13.2f}% | {up_s:>13.2f}% | {brch:>13.2f}% | {avg_ret:>+10.2f}%")

            results_json[sk] = {
                "n_samples": n,
                "in_bounds_pct": in_b,
                "upside_surprise_pct": up_s,
                "breach_pct": brch,
                "avg_realized_pivot_return_pct": avg_ret,
            }

        # Save to JSON
        if RULES_JSON_PATH.exists():
            with open(RULES_JSON_PATH, "r") as f:
                rules_data = json.load(f)
            rules_data["signal_credibility_benchmark"] = results_json
            with open(RULES_JSON_PATH, "w") as f:
                json.dump(rules_data, f, indent=2)
            logger.info(f" Benchmark guardado en {RULES_JSON_PATH.name}")

    finally:
        store._put(conn)


if __name__ == "__main__":
    main()
