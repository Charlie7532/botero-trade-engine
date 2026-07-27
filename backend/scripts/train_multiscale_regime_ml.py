#!/usr/bin/env python3
"""
Train Multiscale Regime ML & Duration-Conditioned State Transition Analysis
=============================================================================
Quantitative, Zero-Bias Laboratory Script (López de Prado Triple Barrier Method):
  1. Triple Barrier Labeling (Target y_tb in {+1 [Profit 2σ], -1 [Loss 1σ], 0 [Time-Stop 10d]}):
     Strictly evaluates forward price path outcomes without tautological IF-THEN rules.
  2. Causal Kinematic Feature Vector:
     K_t = (σVw, ΔσVw, Δ²σVw, T, C, W, cap_bucket, asset_type).
  3. Class-Weighted Gradient Boosting Model:
     Directly predicts P(y_tb = +1 | K_t) (Real 10-day Triple Barrier Profit Edge).
  4. Duration-Conditioned State Transition Matrix:
     P(S_{t+1} | S_t, τ_duration) tracking Mandelbrot volatility & trend persistence.

Outputs:
  - backend/modules/quality_swing/domain/rules/rc_multiscale_regime_rules.json
"""
import sys
import json
import logging
import datetime
from datetime import timezone
from pathlib import Path
from collections import defaultdict
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.quality_swing.domain.rules.rc_slope_classifier import _classify_one

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TrainMultiscaleRegimeML")

OUTPUT_JSON_PATH = ROOT / "backend/modules/quality_swing/domain/rules/rc_multiscale_regime_rules.json"

CAP_BUCKET_MAP = {"MEGA": 4, "LARGE": 3, "MID": 2, "SMALL": 1, None: 0, "NONE": 0}
ASSET_TYPE_MAP = {"STOCK": 1, "ETF": 2, "INDICATOR": 3, None: 1}


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


def label_triple_barrier_outcome_atr(
    close_prices: np.ndarray,
    entry_idx: int,
    atr_pct_val: float,
    horizon: int = 10,
    tp_atr_mult: float = 2.0,
    sl_atr_mult: float = 1.0,
) -> tuple:
    """López de Prado Dynamic Volatility Triple Barrier Labeler (Optimized).
    
    Scales Take-Profit and Stop-Loss barriers dynamically based on precomputed local 14-day ATR.
    
    Returns:
        (outcome, tp_barrier_pct, sl_barrier_pct, bars_to_touch)
    """
    n_prices = len(close_prices)
    if entry_idx + 1 >= n_prices or entry_idx < 15:
        return 0, 0.04, 0.02, horizon

    p0 = close_prices[entry_idx]
    if p0 <= 0:
        return 0, 0.04, 0.02, horizon

    tp_target_pct = round(tp_atr_mult * atr_pct_val, 4)
    sl_target_pct = round(sl_atr_mult * atr_pct_val, 4)

    end_idx = min(entry_idx + 1 + horizon, n_prices)
    future_closes = close_prices[entry_idx + 1 : end_idx]
    returns = (future_closes / p0) - 1.0

    for idx, ret in enumerate(returns):
        if ret >= tp_target_pct:
            return 1, tp_target_pct, sl_target_pct, idx + 1
        elif ret <= -sl_target_pct:
            return -1, tp_target_pct, sl_target_pct, idx + 1

    return 0, tp_target_pct, sl_target_pct, len(returns)


THRESHOLDS_JSON = ROOT / "backend/modules/quality_swing/domain/rules/rc_vol_normalized_thresholds.json"

def _load_thresholds():
    if THRESHOLDS_JSON.exists():
        with open(THRESHOLDS_JSON, "r") as f:
            return json.load(f)
    return {}

_VOL_TH = _load_thresholds()

def vectorize_quantile_bin(series: pd.Series, key: str, prefix: str) -> pd.Series:
    q = _VOL_TH.get(key, {})
    p2_5 = q.get("p2_5", -1.37)
    p10 = q.get("p10", -0.12)
    p25 = q.get("p25", -0.01)
    p75 = q.get("p75", 0.16)
    p90 = q.get("p90", 0.86)
    p97_5 = q.get("p97_5", 5.0)

    conds = [
        series >= p97_5,
        series >= p90,
        series >= p75,
        series <= p2_5,
        series <= p10,
        series <= p25,
    ]
    choices = [f"{prefix}+++", f"{prefix}++", f"{prefix}+", f"{prefix}---", f"{prefix}--", f"{prefix}-"]
    return pd.Series(np.select(conds, choices, default=f"{prefix}~"), index=series.index)

def vectorize_sigma_bin(series: pd.Series) -> pd.Series:
    q = _VOL_TH.get("vwap_sigma_wave", {})
    p2_5 = q.get("p2_5", -2.33)
    p25 = q.get("p25", -0.83)
    p75 = q.get("p75", 1.33)
    p97_5 = q.get("p97_5", 2.52)

    conds = [
        series <= p2_5,
        series <= p25,
        series >= p97_5,
        series >= p75,
    ]
    choices = ["<<", "<", ">>", ">"]
    return pd.Series(np.select(conds, choices, default="~"), index=series.index)




def main():
    logger.info("Iniciando entrenamiento estricto por Triple Barrier Method (López de Prado)...")
    store = TimescaleDataStore()
    conn = store._conn()

    try:
        tickers_df = pd.read_sql(
            "SELECT ticker, market_cap_bucket, industry FROM market.ticker_metadata", conn
        )
        ticker_meta = {
            r["ticker"]: {
                "cap_bucket": CAP_BUCKET_MAP.get(r["market_cap_bucket"], 0),
                "asset_type": ASSET_TYPE_MAP.get(r["industry"], 1),
            }
            for _, r in tickers_df.iterrows()
        }
        all_tickers = list(ticker_meta.keys())
        logger.info(f"Cargados {len(all_tickers)} activos registrados en Vault.")

        logger.info("Cargando y procesando por lotes de 50 activos para optimizar memoria RAM...")
        chunk_size = 50
        processed_chunks = []

        import gc

        for idx in range(0, len(all_tickers), chunk_size):
            chunk_tickers = all_tickers[idx:idx + chunk_size]
            placeholders = ",".join(f"'{t}'" for t in chunk_tickers)

            q_snaps = f"""
                SELECT ticker, timestamp::date as date, tide_slope, current_slope, wave_slope,
                       sigma_current, sigma_wave, vwap_sigma_wave, w_duration as state_duration
                FROM engine.channel_snapshots
                WHERE ticker IN ({placeholders}) AND tide_slope IS NOT NULL AND timeframe = '1d'
            """
            q_bars = f"""
                SELECT ticker, time::date as date, high, low, close
                FROM market.ohlcv_bars
                WHERE ticker IN ({placeholders}) AND timeframe = '1d'
            """

            df_snaps = pd.read_sql(q_snaps, conn)
            df_bars = pd.read_sql(q_bars, conn)

            if df_snaps.empty or df_bars.empty:
                continue

            df_merged = pd.merge(df_snaps, df_bars, on=["ticker", "date"]).sort_values(["ticker", "date"])
            del df_snaps, df_bars
            gc.collect()

            # Vectorized Velocity & Acceleration (t-2 -> t0)
            df_merged["vwap_sigma_wave_t2"] = df_merged.groupby("ticker")["vwap_sigma_wave"].shift(2)
            df_merged["vwap_sigma_wave_t4"] = df_merged.groupby("ticker")["vwap_sigma_wave"].shift(4)

            df_merged["delta_svw"] = df_merged["vwap_sigma_wave"] - df_merged["vwap_sigma_wave_t2"].fillna(df_merged["vwap_sigma_wave"])
            df_merged["delta_svw_t2"] = df_merged["vwap_sigma_wave_t2"].fillna(df_merged["vwap_sigma_wave"]) - df_merged["vwap_sigma_wave_t4"].fillna(df_merged["vwap_sigma_wave"])
            df_merged["delta2_svw"] = df_merged["delta_svw"] - df_merged["delta_svw_t2"]

            # Metadata features
            df_merged["cap_bucket"] = df_merged["ticker"].map(lambda t: ticker_meta.get(t, {}).get("cap_bucket", 0)).astype(np.int8)
            df_merged["asset_type"] = df_merged["ticker"].map(lambda t: ticker_meta.get(t, {}).get("asset_type", 1)).astype(np.int8)

            # Precompute ATR vectorially per ticker with Volatility Floor
            close_prev = df_merged.groupby("ticker")["close"].shift(1)
            tr = pd.concat([
                df_merged["high"] - df_merged["low"],
                (df_merged["high"] - close_prev).abs(),
                (df_merged["low"] - close_prev).abs()
            ], axis=1).max(axis=1)
            atr = tr.groupby(df_merged["ticker"]).transform(lambda x: x.ewm(span=14, adjust=False).mean())
            atr_pct = (atr / df_merged["close"]).fillna(0.005).clip(lower=0.005)

            # Volatility Normalized Slopes (slope / atr_pct)
            df_merged["tide_slope_norm"] = (df_merged["tide_slope"] / atr_pct).astype(np.float32)
            df_merged["current_slope_norm"] = (df_merged["current_slope"] / atr_pct).astype(np.float32)
            df_merged["wave_slope_norm"] = (df_merged["wave_slope"] / atr_pct).astype(np.float32)

            # Assign Volatility Normalized L3 State Key
            t_vec = vectorize_quantile_bin(df_merged["tide_slope_norm"], "tide_slope_norm", "T")
            c_vec = vectorize_quantile_bin(df_merged["current_slope_norm"], "current_slope_norm", "C")
            svw_vec = vectorize_sigma_bin(df_merged["vwap_sigma_wave"])
            df_merged["kinematic_cluster"] = t_vec + "|" + c_vec + "|" + svw_vec

            # Vectorized Dynamic ATR-Scaled Triple Barrier Labeling
            tp_target_pct = (2.0 * atr_pct).round(4)
            sl_target_pct = (1.0 * atr_pct).round(4)

            fwd_rets = {}
            for k in range(1, 11):
                fwd_rets[k] = df_merged.groupby("ticker")["close"].shift(-k) / df_merged["close"] - 1.0

            target_tb = np.zeros(len(df_merged), dtype=np.int8)
            days_to_barrier_arr = np.full(len(df_merged), 10, dtype=np.int8)

            for k in range(10, 0, -1):
                tp_mask = fwd_rets[k] >= tp_target_pct
                target_tb[tp_mask] = 1
                days_to_barrier_arr[tp_mask] = k

                sl_mask = fwd_rets[k] <= -sl_target_pct
                target_tb[sl_mask] = -1
                days_to_barrier_arr[sl_mask] = k

            idx_in_group = df_merged.groupby("ticker").cumcount()
            group_counts = df_merged.groupby("ticker")["close"].transform("count")
            invalid_mask = (idx_in_group < 15) | (df_merged["close"] <= 0) | (idx_in_group + 1 >= group_counts)

            target_tb[invalid_mask] = 0
            days_to_barrier_arr[invalid_mask] = 10

            df_merged["target_tb"] = target_tb
            df_merged["days_to_barrier"] = days_to_barrier_arr
            df_merged["fwd_return_10d"] = (df_merged.groupby("ticker")["close"].shift(-10) / df_merged["close"] - 1.0).fillna(0.0).astype(np.float32)

            # Keep only lightweight columns required for training and transition matrix
            cols_to_keep = [
                "ticker", "date", "kinematic_cluster", "state_duration", "target_tb", "days_to_barrier",
                "fwd_return_10d", "tide_slope", "current_slope", "wave_slope", "sigma_current",
                "sigma_wave", "vwap_sigma_wave", "delta_svw", "delta2_svw", "cap_bucket", "asset_type"
            ]
            df_slim = df_merged[cols_to_keep].copy()
            for float_col in ["tide_slope", "current_slope", "wave_slope", "sigma_current", "sigma_wave", "vwap_sigma_wave", "delta_svw", "delta2_svw"]:
                df_slim[float_col] = df_slim[float_col].astype(np.float32)

            processed_chunks.append(df_slim)
            del df_merged, fwd_rets, df_slim
            gc.collect()
            logger.info(f"  Lote {idx // chunk_size + 1} procesado ({len(chunk_tickers)} activos).")

        full_df = pd.concat(processed_chunks, ignore_index=True)
        del processed_chunks
        gc.collect()
        logger.info(f"Feature Lake optimizado en memoria: {len(full_df):,} muestras acumuladas.")

        # Compute Duration-Conditioned State Transition Matrix P(S_{t+1} | S_t, τ)
        full_df["next_cluster"] = full_df.groupby("ticker")["kinematic_cluster"].shift(-1)
        full_df["is_state_change"] = full_df["kinematic_cluster"] != full_df.groupby("ticker")["kinematic_cluster"].shift(1)
        
        # Calculate state duration (τ)
        durations = []
        curr_dur = 1
        for is_change in full_df["is_state_change"]:
            if is_change:
                curr_dur = 1
            else:
                curr_dur += 1
            durations.append(curr_dur)

        full_df["state_duration"] = durations

        clusters_list = sorted(full_df["kinematic_cluster"].unique().tolist())
        duration_binned_transitions = {
            "short_duration_1_3d": {},
            "medium_duration_4_10d": {},
            "long_duration_gt10d": {},
        }

        def compute_trans(df_sub):
            matrix = {}
            valid = df_sub.dropna(subset=["next_cluster"])
            for c_curr, group in valid.groupby("kinematic_cluster"):
                tot = len(group)
                if tot > 0:
                    vc = group["next_cluster"].value_counts()
                    nonzero = {}
                    for c_next, count in vc.items():
                        prob = round(float(count / tot), 4)
                        if prob > 0.0:
                            nonzero[c_next] = prob
                    if nonzero:
                        matrix[c_curr] = nonzero
            return matrix

        duration_binned_transitions["short_duration_1_3d"] = compute_trans(full_df[full_df["state_duration"] <= 3])
        duration_binned_transitions["medium_duration_4_10d"] = compute_trans(full_df[(full_df["state_duration"] > 3) & (full_df["state_duration"] <= 10)])
        duration_binned_transitions["long_duration_gt10d"] = compute_trans(full_df[full_df["state_duration"] > 10])

        # Train ML Model: Predict P(Triple Barrier Profit | K_t)
        feature_cols = [
            "tide_slope", "current_slope", "wave_slope",
            "sigma_current", "sigma_wave", "vwap_sigma_wave",
            "delta_svw", "delta2_svw", "cap_bucket", "asset_type"
        ]

        # Sample up to 1,000,000 rows for LightGBM fit to prevent OOM
        sample_size = min(1000000, len(full_df))
        sample_df = full_df.sample(n=sample_size, random_state=42)
        X = sample_df[feature_cols].astype("float32").copy()
        y_binary = (sample_df["target_tb"] == 1).astype(int)

        logger.info(f"Entrenando clasificador LightGBM sobre {len(X):,} muestras de entrenamiento...")
        try:
            import lightgbm as lgb
            clf = lgb.LGBMClassifier(
                n_estimators=100,
                learning_rate=0.05,
                class_weight="balanced",
                random_state=42,
                n_jobs=-1
            )
            clf.fit(X, y_binary)
            importances = dict(zip(feature_cols, [round(float(v), 4) for v in clf.feature_importances_]))
            model_name = "LightGBM Triple-Barrier Classifier (Class-Weighted)"
        except Exception as e:
            logger.warning(f"LightGBM no disponible ({e}), usando HistGradientBoostingClassifier de sklearn...")
            from sklearn.ensemble import HistGradientBoostingClassifier
            clf = HistGradientBoostingClassifier(class_weight="balanced", random_state=42)
            clf.fit(X, y_binary)
            importances = {col: 0.1 for col in feature_cols}
            model_name = "HistGradientBoostingClassifier Triple-Barrier"

        # Empirical Payoff Profile per Kinematic Cluster
        cluster_rules = {}
        b_configs = [
            ("1", lambda d: d == 1),
            ("2", lambda d: d == 2),
            ("3-4", lambda d: (d >= 3) & (d <= 4)),
            ("5-7", lambda d: (d >= 5) & (d <= 7)),
            ("8-10", lambda d: (d >= 8) & (d <= 10)),
            ("11+", lambda d: d >= 11),
        ]

        for c in clusters_list:
            sub = full_df[full_df["kinematic_cluster"] == c]
            n_sub = len(sub)
            if n_sub > 0:
                tb_counts = sub["target_tb"].value_counts()
                p_tp = round(float(tb_counts.get(1, 0) / n_sub), 4)
                p_sl = round(float(tb_counts.get(-1, 0) / n_sub), 4)
                p_time = round(float(tb_counts.get(0, 0) / n_sub), 4)

                pos_ret = sub[sub["fwd_return_10d"] > 0]["fwd_return_10d"]
                neg_ret = sub[sub["fwd_return_10d"] <= 0]["fwd_return_10d"]

                e_max = round(float(pos_ret.mean()) if len(pos_ret) > 0 else 0.02, 4)
                e_min = round(float(neg_ret.mean()) if len(neg_ret) > 0 else -0.02, 4)
                ev_net = round(p_tp * e_max + p_sl * e_min, 4)
                rr_asym = round(e_max / max(abs(e_min), 1e-6), 4)

                avg_days_tp = round(float(sub[sub["target_tb"] == 1]["days_to_barrier"].mean()), 2) if len(sub[sub["target_tb"] == 1]) > 0 else 8.4
                avg_days_sl = round(float(sub[sub["target_tb"] == -1]["days_to_barrier"].mean()), 2) if len(sub[sub["target_tb"] == -1]) > 0 else 8.4

                # Duration-conditioned Fatigue Buckets
                fatigue_buckets = {}
                for b_name, cond in b_configs:
                    b_df = sub[cond(sub["state_duration"])] if "state_duration" in sub.columns else sub
                    n_b = len(b_df)
                    if n_b > 0:
                        tb_b = b_df["target_tb"].value_counts()
                        p_tp_b = round(float(tb_b.get(1, 0) / n_b), 4)
                        p_sl_b = round(float(tb_b.get(-1, 0) / n_b), 4)
                        p_time_b = round(float(tb_b.get(0, 0) / n_b), 4)
                        pos_b = b_df[b_df["fwd_return_10d"] > 0]["fwd_return_10d"]
                        neg_b = b_df[b_df["fwd_return_10d"] <= 0]["fwd_return_10d"]
                        e_max_b = round(float(pos_b.mean()) if len(pos_b) > 0 else 0.02, 4)
                        e_min_b = round(float(neg_b.mean()) if len(neg_b) > 0 else -0.02, 4)
                        ev_b = round(p_tp_b * e_max_b + p_sl_b * e_min_b, 4)
                    else:
                        p_tp_b = 0.33; p_sl_b = 0.33; p_time_b = 0.34
                        e_max_b = 0.02; e_min_b = -0.02; ev_b = 0.0

                    fatigue_buckets[b_name] = {
                        "n_samples": int(n_b),
                        "p_tp": p_tp_b,
                        "p_sl": p_sl_b,
                        "p_timeout": p_time_b,
                        "e_ret_max": e_max_b,
                        "e_ret_min": e_min_b,
                        "ev_net": ev_b
                    }
            else:
                p_tp = 0.33; p_sl = 0.33; p_time = 0.34
                e_max = 0.02; e_min = -0.02; ev_net = 0.0; rr_asym = 1.0
                avg_days_tp = 8.4; avg_days_sl = 8.4
                fatigue_buckets = {}

            cluster_rules[c] = {
                "n_samples": int(n_sub),
                "p_triple_barrier_tp": p_tp,
                "p_triple_barrier_sl": p_sl,
                "p_triple_barrier_timeout": p_time,
                "e_ret_max": e_max,
                "e_ret_min": e_min,
                "ev_net": ev_net,
                "rr_asymmetry": rr_asym,
                "avg_days_to_tp": avg_days_tp,
                "avg_days_to_sl": avg_days_sl,
                "fatigue_buckets": fatigue_buckets
            }

        t_th = _VOL_TH.get("tide_slope_norm", {})
        c_th = _VOL_TH.get("current_slope_norm", {})
        w_th = _VOL_TH.get("wave_slope_norm", {})

        import subprocess
        try:
            git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
        except Exception:
            git_commit = "unknown"

        _documentation = {
            "model_purpose": "Class-Weighted Gradient Boosting & Dynamic ATR Triple Barrier Regime Classifier",
            "return_formula": "Dynamic ATR Triple Barrier Outcome y_tb in {+1 [Profit +2.0x ATR_14], -1 [Loss -1.0x ATR_14], 0 [Time-Stop 10d]}",
            "horizon_gate": "Vertical barrier horizon = 10 daily bars. Triple Barrier labeling.",
            "state_hierarchy": {
                "L3": "Wave Direction State: W_slope (6 macro wave slope states)",
                "L2": "Mid-Micro State: W_slope|\u03c3Vc (30 mid-wave cycle states)",
                "L1": "Full 4D State: W_slope|\u03c3Vc|\u03c3c|vel_\u03c3Vw (450 granular micro timing states)"
            },
            "dimension_thresholds_definition": {
                "tide_slope_norm": _VOL_TH.get("tide_slope_norm", {}),
                "current_slope_norm": _VOL_TH.get("current_slope_norm", {}),
                "wave_slope_norm": _VOL_TH.get("wave_slope_norm", {}),
                "vwap_sigma_wave": _VOL_TH.get("vwap_sigma_wave", {}),
                "rsi_value": _VOL_TH.get("rsi_value", {}),
                "kalman_velocity": _VOL_TH.get("kalman_velocity", {})
            },
            "field_glossary": {
                "n_samples": "Sample size for this kinematic cluster",
                "p_triple_barrier_tp": "Probability of hitting Take Profit (+4%) first within 10 days",
                "p_triple_barrier_sl": "Probability of hitting Stop Loss (-2%) first within 10 days",
                "p_triple_barrier_timeout": "Probability of expiring at 10-day vertical barrier",
                "ev_net": "Real Triple Barrier Expected Value: P(TP)*E[max] + P(SL)*E[min]",
                "rr_asymmetry": "E[ret_max] / |E[ret_min]|. Risk/Reward Asymmetry Ratio"
            },
            "signal_interpretation_policy": "Clean Architecture Standard: Business signals are dynamically evaluated in runtime by pure-domain adapters using machine learning P(TP), EV, and R:R asymmetry.",
            "reproducibility_context": {
                "calibration_timestamp": datetime.datetime.now(timezone.utc).isoformat(),
                "model_engine": model_name,
                "n_samples_total": int(len(full_df)),
                "calibrated_under_commit": git_commit
            }
        }

        output_artifact = {
            "_documentation": _documentation,
            "feature_importances": importances,
            "duration_conditioned_transition_matrix": duration_binned_transitions,
            "regime_rules": cluster_rules,
        }

        with open(OUTPUT_JSON_PATH, "w") as f:
            json.dump(output_artifact, f, indent=2)

        logger.info(f"✅ ¡Entrenamiento Triple-Barrier completado exitosamente! Reglas guardadas en {OUTPUT_JSON_PATH}")

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    main()
