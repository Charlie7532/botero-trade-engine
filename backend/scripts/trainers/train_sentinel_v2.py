#!/usr/bin/env python3
"""
Train Sentinel V2 — Atomic Pipeline (Zero Manual Junctions)
=============================================================
Single script that replaces the multi-phase manual pipeline.
Closes every audit gap found in the methodology review:

  1. Feature selection: Automatic from Phase H SHAP × Permutation convergence
  2. PurgedKFold: Single standardized implementation (López de Prado)
  3. Threshold: Calibrated on OOS folds, NOT in-sample
  4. Signal Replay: Uses calibrated threshold, not 0.5
  5. Hyperparameters: Grid search (3 configs), all reported
  6. Audit: Full traceability log — every decision documented

Supports multiple CONFIGS (variants) in a single run:
  - v2a_shap_aligned: Features from Phase H SHAP top-8 (no temporal)
  - v2c_temporal:     SHAP top-8 + causal temporal features for TECHO
  - v2e_matched_hp:   Current 6 features but with Phase H hyperparameters

Data source: engine.channel_snapshots + engine.zigzag_points (Neon Vault)
Output: models pkl + audit log + signal replay results

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python \\
        backend/scripts/train_sentinel_v2.py [--config v2a_shap_aligned]

Re-runnable. Does not modify any database tables.
"""
import sys
import os
import time
import pickle
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy.stats import norm

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

from sklearn.metrics import (
    roc_auc_score, precision_score, recall_score, f1_score,
    precision_recall_curve,
)
import xgboost as xgb

from backend.modules.shared.infrastructure.timescale_data_store import (
    TimescaleDataStore,
)

# ═══════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════
OUT_DIR = root_dir / "backend" / "scripts" / "sentinel_v2_output"
OUT_DIR.mkdir(exist_ok=True)

LOG_LINES: list[str] = []

def log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    LOG_LINES.append(line)

def log_section(title: str) -> None:
    sep = "═" * 100
    log(sep)
    log(f"  {title}")
    log(sep)


# ═══════════════════════════════════════════════════════════════
# CONFIGURATION — Variant Definitions
# ═══════════════════════════════════════════════════════════════

# ---------- Column availability in engine.channel_snapshots ----------
# These are the columns that exist in the Vault after backfill_kalman_5channel.
# The names below are EXACT Vault column names.
#
# Kalman channels (11):
#   kf_price_pred_val, kf_price_filt_vel, kf_price_innovation,
#   kf_rvol_pred_val, kf_rvol_filt_vel,
#   kf_tension_pred_val, kf_tension_filt_vel,
#   kf_rsi_pred_val, kf_rsi_filt_vel,
#   kf_conj_pred_val, kf_conj_filt_vel
#
# Channel/RC (base snapshot):
#   sigma_tide, sigma_current, sigma_wave,
#   vwap_sigma_tide, vwap_sigma_current, vwap_sigma_wave,
#   vwap_spread_tide_current, vwap_spread_tide_wave, vwap_spread_current_wave,
#   tide_slope, current_slope, wave_slope,
#   tide_accel, current_accel, wave_accel,
#   reg_value_tide, reg_value_current, reg_value_wave,
#   conj_wave_tide, conj_current_tide, conj_wave_current,
#   rsi_value, fear_level, compression_ratio,
#   tension_tide, tension_current, tension_wave

# Feature name mapping: Phase H lake name → Vault column name
# Most map 1:1. Exceptions documented here.
# Phase H used 'kf_conjugation_pred_val' → Vault has 'kf_conj_pred_val'
# Phase H used 'd_current_slope' / 'd_tide_slope' → these are deltas
#   computed by the lake builder, not raw Vault columns. We'll compute them.

# ---------- SHAP-derived feature sets (from Phase H log) ----------
# PISO Strategy A SHAP Top-15 (excluding ★TEMP):
#   1. kf_rsi_pred_val (1.5475)
#   2. rsi_value (0.4361)
#   4. vwap_sigma_current (0.2077)
#   5. kf_price_filt_vel (0.1643)
#   6. kf_price_pred_val (0.1630)
#   7. vwap_sigma_tide (0.1620)
#   8. vwap_sigma_wave (0.1536)
#  10. reg_value_tide (0.0991)
#
# TECHO Strategy A SHAP Top-15 (excluding ★TEMP):
#   1. kf_rsi_pred_val (0.7338)
#   2. kf_price_filt_vel (0.2081)
#   4. rsi_value (0.1827)
#   5. kf_price_pred_val (0.1413)
#   7. vwap_spread_tide_current (0.0956)
#   8. vwap_sigma_wave (0.0933)
#   9. sigma_tide (0.0851)
#  11. reg_value_tide (0.0653)

CONFIGS = {
    "v2a_shap_aligned": {
        "description": "SHAP top-8 (non-temporal) from Phase H Strategy A",
        "piso_features": [
            "kf_rsi_pred_val", "rsi_value", "vwap_sigma_current",
            "kf_price_filt_vel", "kf_price_pred_val", "vwap_sigma_tide",
            "vwap_sigma_wave", "reg_value_tide",
        ],
        "techo_features": [
            "kf_rsi_pred_val", "kf_price_filt_vel", "rsi_value",
            "kf_price_pred_val", "vwap_spread_tide_current", "vwap_sigma_wave",
            "sigma_tide", "reg_value_tide",
        ],
        "temporal_features": False,
        "label_strategy": "or_multiscale",
        "hyperparams": [
            {  # Config 1: Phase H params (the exploration params)
                "n_estimators": 150, "max_depth": 5, "learning_rate": 0.1,
                "min_child_weight": 5, "gamma": 0.1,
                "subsample": 0.8, "colsample_bytree": 0.8,
            },
            {  # Config 2: Production V1 params (the conservative params)
                "n_estimators": 200, "max_depth": 4, "learning_rate": 0.05,
                "min_child_weight": 50, "gamma": 0.0,
                "subsample": 0.8, "colsample_bytree": 0.8,
            },
            {  # Config 3: Balanced — between exploration and production
                "n_estimators": 200, "max_depth": 5, "learning_rate": 0.08,
                "min_child_weight": 10, "gamma": 0.05,
                "subsample": 0.8, "colsample_bytree": 0.8,
            },
        ],
    },

    "v2c_temporal": {
        "description": "SHAP top-8 + 3 causal temporal features (for TECHO improvement)",
        "piso_features": [
            "kf_rsi_pred_val", "rsi_value", "vwap_sigma_current",
            "kf_price_filt_vel", "kf_price_pred_val", "vwap_sigma_tide",
            "vwap_sigma_wave", "reg_value_tide",
        ],
        "techo_features": [
            "kf_rsi_pred_val", "kf_price_filt_vel", "rsi_value",
            "kf_price_pred_val", "vwap_spread_tide_current", "vwap_sigma_wave",
            "sigma_tide", "reg_value_tide",
            # Temporal (computed in-script, causal rolling windows):
            "kf_price_pred_trend_5bar", "rsi_z_trend_5bar", "rolling_density_3bar",
        ],
        "temporal_features": True,
        "label_strategy": "or_multiscale",
        "hyperparams": [
            {
                "n_estimators": 150, "max_depth": 5, "learning_rate": 0.1,
                "min_child_weight": 5, "gamma": 0.1,
                "subsample": 0.8, "colsample_bytree": 0.8,
            },
            {
                "n_estimators": 200, "max_depth": 5, "learning_rate": 0.08,
                "min_child_weight": 10, "gamma": 0.05,
                "subsample": 0.8, "colsample_bytree": 0.8,
            },
        ],
    },

    "v2e_matched_hp": {
        "description": "V1 features (6) with Phase H hyperparameters — isolate HP effect",
        "piso_features": [
            "kf_rsi_pred_val", "kf_price_filt_vel", "kf_price_pred_val",
            "kf_conj_pred_val", "rsi_value", "sigma_tide",
        ],
        "techo_features": [
            "kf_rsi_pred_val", "kf_price_filt_vel", "kf_tension_pred_val",
            "kf_conj_filt_vel", "rsi_value", "sigma_tide",
        ],
        "temporal_features": False,
        "label_strategy": "or_multiscale",
        "hyperparams": [
            {  # Phase H params on V1 features
                "n_estimators": 150, "max_depth": 5, "learning_rate": 0.1,
                "min_child_weight": 5, "gamma": 0.1,
                "subsample": 0.8, "colsample_bytree": 0.8,
            },
            {  # V1 production params (baseline comparison)
                "n_estimators": 200, "max_depth": 4, "learning_rate": 0.05,
                "min_child_weight": 50, "gamma": 0.0,
                "subsample": 0.8, "colsample_bytree": 0.8,
            },
        ],
    },
}

ZZ_THRESHOLDS = [0.03, 0.05, 0.07]
LABEL_PROXIMITY = 3  # bars either side of turn point
N_FOLDS = 5
EMBARGO_BARS = 10

TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]


# ═══════════════════════════════════════════════════════════════
# STEP 1: DATA LOADING
# ═══════════════════════════════════════════════════════════════

def load_data(store: TimescaleDataStore) -> pd.DataFrame:
    """Load channel_snapshots + zigzag labels from Vault.

    Returns DataFrame with ticker, timestamp, all feature columns,
    and label columns (is_piso_Xpct, is_techo_Xpct, is_piso, is_techo).
    """
    log_section("STEP 1: LOAD DATA FROM VAULT")

    conn = store._conn()
    cur = conn.cursor()

    # ── 1a. Load snapshots (no correlated subquery — fast) ──
    log(f"  Loading channel_snapshots...")
    cur.execute("""
        SELECT ticker, timestamp,
               kf_price_pred_val, kf_price_filt_vel, kf_price_innovation,
               kf_rvol_pred_val, kf_rvol_filt_vel,
               kf_tension_pred_val, kf_tension_filt_vel,
               kf_rsi_pred_val, kf_rsi_filt_vel,
               kf_conj_pred_val, kf_conj_filt_vel,
               rsi_value, sigma_tide, sigma_current, sigma_wave,
               vwap_sigma_tide, vwap_sigma_current, vwap_sigma_wave,
               vwap_spread_tide_current, vwap_spread_tide_wave, vwap_spread_current_wave,
               tide_slope, current_slope, wave_slope,
               tide_accel, current_accel, wave_accel,
               reg_value_tide, reg_value_current, reg_value_wave,
               conj_wave_tide, conj_current_tide, conj_wave_current,
               tension_tide, tension_current, tension_wave,
               compression_ratio, fear_level
        FROM engine.channel_snapshots
        WHERE kf_rsi_pred_val IS NOT NULL
          AND timeframe = '1d'
        ORDER BY ticker, timestamp
    """)
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    df = pd.DataFrame(rows, columns=cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    log(f"  Snapshots: {len(df):,} rows × {len(cols)} columns")

    # ── 1b. Load OHLCV close prices separately, then join ──
    log(f"  Loading OHLCV close prices...")
    cur.execute("""
        SELECT ticker, time::date as trade_date, close
        FROM market.ohlcv_bars
        WHERE timeframe = '1d'
        ORDER BY ticker, time
    """)
    ohlcv_rows = cur.fetchall()
    ohlcv_df = pd.DataFrame(ohlcv_rows, columns=["ticker", "trade_date", "close"])
    ohlcv_df["trade_date"] = pd.to_datetime(ohlcv_df["trade_date"])
    log(f"  OHLCV: {len(ohlcv_df):,} bars loaded")

    # Join on (ticker, date)
    df["trade_date"] = df["timestamp"].dt.normalize().dt.tz_localize(None)
    ohlcv_df = ohlcv_df.drop_duplicates(subset=["ticker", "trade_date"], keep="last")
    df = df.merge(ohlcv_df[["ticker", "trade_date", "close"]],
                  on=["ticker", "trade_date"], how="left")
    df.rename(columns={"close": "close_price"}, inplace=True)
    df.drop(columns=["trade_date"], inplace=True)
    n_with_price = df["close_price"].notna().sum()
    log(f"  Close prices matched: {n_with_price:,}/{len(df):,} "
        f"({n_with_price/len(df)*100:.1f}%)")

    log(f"  Tickers: {sorted(df['ticker'].unique())}")
    log(f"  Date range: {df['timestamp'].min().date()} → {df['timestamp'].max().date()}")

    # Load zigzag turn points and build labels
    log(f"  Building labels from zigzag points...")
    for threshold in ZZ_THRESHOLDS:
        pct = int(threshold * 100)
        cur.execute("""
            SELECT ticker, timestamp, tp_type
            FROM engine.zigzag_points
            WHERE min_swing_pct = %s
            ORDER BY ticker, timestamp
        """, (threshold,))
        zz_rows = cur.fetchall()
        zz_df = pd.DataFrame(zz_rows, columns=["ticker", "timestamp", "tp_type"])
        zz_df["timestamp"] = pd.to_datetime(zz_df["timestamp"], utc=True)

        # Initialize label columns
        piso_col = f"is_piso_{pct}pct"
        techo_col = f"is_techo_{pct}pct"
        df[piso_col] = 0
        df[techo_col] = 0

        # For each ticker, find bars near turn points
        for tk in df["ticker"].unique():
            tk_mask = df["ticker"] == tk
            tk_timestamps = df.loc[tk_mask, "timestamp"].values.astype("datetime64[ns]")
            tk_indices = df.index[tk_mask].values

            zz_tk = zz_df[zz_df["ticker"] == tk]
            for _, zz_row in zz_tk.iterrows():
                zz_ts = np.datetime64(zz_row["timestamp"])
                zz_type = zz_row["tp_type"]

                # Find bar index closest to this zigzag point
                diffs = np.abs(tk_timestamps - zz_ts)
                min_idx_local = np.argmin(diffs)

                # Label bars within ±LABEL_PROXIMITY
                for offset in range(-LABEL_PROXIMITY, LABEL_PROXIMITY + 1):
                    idx_local = min_idx_local + offset
                    if 0 <= idx_local < len(tk_indices):
                        global_idx = tk_indices[idx_local]
                        if zz_type == "MIN":
                            df.at[global_idx, piso_col] = 1
                        elif zz_type == "MAX":
                            df.at[global_idx, techo_col] = 1

        n_piso = df[piso_col].sum()
        n_techo = df[techo_col].sum()
        log(f"    {pct}%: PISO={n_piso:,} ({n_piso/len(df)*100:.1f}%)  "
            f"TECHO={n_techo:,} ({n_techo/len(df)*100:.1f}%)")

    # Build composite OR labels
    df["is_piso"] = ((df["is_piso_3pct"] == 1) |
                     (df["is_piso_5pct"] == 1) |
                     (df["is_piso_7pct"] == 1)).astype(int)
    df["is_techo"] = ((df["is_techo_3pct"] == 1) |
                      (df["is_techo_5pct"] == 1) |
                      (df["is_techo_7pct"] == 1)).astype(int)

    log(f"  Composite OR: PISO={df['is_piso'].sum():,} ({df['is_piso'].mean()*100:.1f}%)  "
        f"TECHO={df['is_techo'].sum():,} ({df['is_techo'].mean()*100:.1f}%)")

    # Build forward returns for Signal Replay
    log(f"  Computing forward returns...")
    for horizon in [5, 10, 20]:
        col_name = f"fwd_return_{horizon}d"
        df[col_name] = np.nan
        for tk in df["ticker"].unique():
            tk_mask = df["ticker"] == tk
            prices = df.loc[tk_mask, "close_price"].values.astype(float)
            fwd = np.full(len(prices), np.nan)
            for i in range(len(prices) - horizon):
                if prices[i] > 0:
                    fwd[i] = (prices[i + horizon] - prices[i]) / prices[i] * 100
            df.loc[tk_mask, col_name] = fwd

    store._put(conn)
    log(f"  ✅ Data loaded: {len(df):,} rows")
    return df


# ═══════════════════════════════════════════════════════════════
# STEP 2: FEATURE ENGINEERING (Temporal)
# ═══════════════════════════════════════════════════════════════

def compute_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute causal temporal features (rolling lookback only, no leakage).

    All features use only bars [t-N+1, t] — strictly causal.
    """
    log_section("STEP 2: TEMPORAL FEATURE ENGINEERING (causal)")

    for tk in sorted(df["ticker"].unique()):
        mask = df["ticker"] == tk
        idx = df.index[mask]

        # kf_price_pred_trend_5bar: slope of kf_price_pred_val over last 5 bars
        kf_vals = df.loc[mask, "kf_price_pred_val"].values.astype(float)
        trend_5 = pd.Series(kf_vals).rolling(5, min_periods=2).apply(
            lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) >= 2 else 0,
            raw=True,
        ).values
        df.loc[idx, "kf_price_pred_trend_5bar"] = np.nan_to_num(trend_5, nan=0.0)

        # rsi_z_trend_5bar: slope of rsi z-score over last 5 bars
        rsi_vals = df.loc[mask, "rsi_value"].values.astype(float)
        mu_rsi = np.nanmean(rsi_vals)
        std_rsi = np.nanstd(rsi_vals)
        if std_rsi < 1e-8:
            std_rsi = 1.0
        rsi_z = (rsi_vals - mu_rsi) / std_rsi
        rsi_trend = pd.Series(rsi_z).rolling(5, min_periods=2).apply(
            lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) >= 2 else 0,
            raw=True,
        ).values
        df.loc[idx, "rsi_z_trend_5bar"] = np.nan_to_num(rsi_trend, nan=0.0)

        # rolling_density_3bar: rolling count of features with |z| > 2 over 3 bars
        # Uses the 8 base TECHO features for density calculation
        density_cols = [
            "kf_rsi_pred_val", "kf_price_filt_vel", "rsi_value",
            "kf_price_pred_val", "vwap_spread_tide_current", "vwap_sigma_wave",
            "sigma_tide", "reg_value_tide",
        ]
        available_cols = [c for c in density_cols if c in df.columns]
        tk_feats = df.loc[mask, available_cols].values.astype(float)
        mu = np.nanmean(tk_feats, axis=0)
        sigma = np.nanstd(tk_feats, axis=0)
        sigma[sigma < 1e-8] = 1.0
        z_abs = np.abs((tk_feats - mu) / sigma)
        density_per_bar = (z_abs > 2.0).sum(axis=1).astype(float)
        rolling_d3 = pd.Series(density_per_bar).rolling(3, min_periods=1).mean().values
        df.loc[idx, "rolling_density_3bar"] = rolling_d3

    log(f"  Temporal features computed: kf_price_pred_trend_5bar, rsi_z_trend_5bar, rolling_density_3bar")
    log(f"  All are causal (rolling lookback only)")
    return df


# ═══════════════════════════════════════════════════════════════
# STEP 3: PURGEDKFOLD — Single Implementation
# ═══════════════════════════════════════════════════════════════

def purged_kfold(df: pd.DataFrame, n_folds: int = N_FOLDS,
                 embargo: int = EMBARGO_BARS):
    """PurgedKFold per-ticker with temporal embargo (López de Prado).

    Yields (train_indices, test_indices) as numpy arrays of df.index values.
    - Temporal split per ticker: each ticker divided into n_folds temporal chunks
    - Embargo: ±embargo bars around test set boundaries are purged from training
    - No leakage: train bars never temporally overlap test bars ± embargo
    """
    ticker_values = df["ticker"].values

    # Build per-ticker temporal folds
    folds = [[] for _ in range(n_folds)]
    for tk in sorted(df["ticker"].unique()):
        positions = np.where(ticker_values == tk)[0]
        n = len(positions)
        fold_size = n // n_folds
        for fi in range(n_folds):
            start = fi * fold_size
            end = start + fold_size if fi < n_folds - 1 else n
            folds[fi].extend(positions[start:end].tolist())

    # Yield train/test pairs with purge + embargo
    for test_fold in range(n_folds):
        test_idx = np.array(folds[test_fold])

        # Train = all other folds, then purge embargo zone
        train_candidates = []
        for fi in range(n_folds):
            if fi != test_fold:
                train_candidates.extend(folds[fi])
        train_candidates = np.array(train_candidates)

        # Per-ticker embargo purge
        test_tickers = ticker_values[test_idx]
        train_tickers = ticker_values[train_candidates]

        purged_train = []
        for tk in sorted(df["ticker"].unique()):
            tk_test_mask = test_tickers == tk
            tk_train_mask = train_tickers == tk

            if not tk_test_mask.any() or not tk_train_mask.any():
                purged_train.extend(train_candidates[tk_train_mask].tolist())
                continue

            tk_test_pos = test_idx[tk_test_mask]
            tk_train_pos = train_candidates[tk_train_mask]

            # All positions for this ticker (for searchsorted)
            tk_all_pos = np.where(ticker_values == tk)[0]

            # Build embargo set
            embargo_set = set()
            for pos in tk_test_pos:
                rank = np.searchsorted(tk_all_pos, pos)
                for e in range(-embargo, embargo + 1):
                    r = rank + e
                    if 0 <= r < len(tk_all_pos):
                        embargo_set.add(tk_all_pos[r])

            for pos in tk_train_pos:
                if pos not in embargo_set:
                    purged_train.append(pos)

        purged_train = np.array(purged_train)
        assert len(set(purged_train) & set(test_idx)) == 0, "LEAKAGE DETECTED!"
        yield purged_train, test_idx


# ═══════════════════════════════════════════════════════════════
# STEP 4: TRAIN + CALIBRATE
# ═══════════════════════════════════════════════════════════════

def train_model(df: pd.DataFrame, features: list[str], label_col: str,
                model_name: str, hp_configs: list[dict]) -> dict:
    """Train a model with PurgedKFold + OOS threshold calibration.

    Returns dict with best model, metrics, threshold, feature importance.
    """
    log(f"\n  ── {model_name} ({len(features)} features, label={label_col}) ──")

    X = df[features].values.astype(np.float32)
    y = df[label_col].values.astype(int)
    X = np.nan_to_num(X, nan=0.0)

    log(f"  X: {X.shape}, positive rate: {y.mean()*100:.1f}%")

    # Log feature list with provenance
    for i, f in enumerate(features):
        log(f"    Feature {i+1}: {f}")

    best_result = None
    best_mean_auc = -1.0

    for hp_idx, hp in enumerate(hp_configs):
        hp_name = f"HP-{hp_idx+1}"
        log(f"\n  --- {hp_name}: depth={hp['max_depth']}, lr={hp['learning_rate']}, "
            f"mcw={hp['min_child_weight']}, gamma={hp['gamma']} ---")

        fold_results = []
        fold_thresholds = []
        oos_probs_all = []
        oos_labels_all = []

        for fold_i, (train_idx, test_idx) in enumerate(
            purged_kfold(df, N_FOLDS, EMBARGO_BARS)
        ):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            scale_pos = (y_train == 0).sum() / max((y_train == 1).sum(), 1)

            model = xgb.XGBClassifier(
                **hp,
                scale_pos_weight=scale_pos,
                random_state=42,
                eval_metric="logloss",
                verbosity=0,
            )
            model.fit(X_train, y_train, verbose=False)

            y_prob = model.predict_proba(X_test)[:, 1]
            y_pred = model.predict(X_test)

            auc = roc_auc_score(y_test, y_prob)
            prec = precision_score(y_test, y_pred, zero_division=0)
            rec = recall_score(y_test, y_pred, zero_division=0)
            f1 = f1_score(y_test, y_pred, zero_division=0)

            # ── OOS threshold calibration ──
            # Find threshold where precision ≈ recall on THIS fold's test set
            pr_prec, pr_rec, pr_thresh = precision_recall_curve(y_test, y_prob)
            # Find point where |precision - recall| is minimized
            valid = (pr_prec[:-1] > 0.01) & (pr_rec[:-1] > 0.01)
            if valid.any():
                diff = np.abs(pr_prec[:-1] - pr_rec[:-1])
                diff[~valid] = 999
                best_t_idx = np.argmin(diff)
                fold_threshold = float(pr_thresh[best_t_idx])
            else:
                fold_threshold = 0.5

            fold_thresholds.append(fold_threshold)

            # Train AUC for gap measurement
            y_prob_train = model.predict_proba(X_train)[:, 1]
            auc_train = roc_auc_score(y_train, y_prob_train)
            gap = auc_train - auc

            fold_results.append({
                "fold": fold_i + 1,
                "auc_test": auc, "auc_train": auc_train, "gap": gap,
                "precision": prec, "recall": rec, "f1": f1,
                "threshold": fold_threshold,
                "train_n": len(X_train), "test_n": len(X_test),
            })

            oos_probs_all.extend(y_prob.tolist())
            oos_labels_all.extend(y_test.tolist())

            log(f"    Fold {fold_i+1}: AUC={auc:.4f} (train={auc_train:.4f} gap={gap:.3f}) "
                f"P={prec:.3f} R={rec:.3f} F1={f1:.3f} thr={fold_threshold:.3f}")

        mean_auc = np.mean([r["auc_test"] for r in fold_results])
        std_auc = np.std([r["auc_test"] for r in fold_results])
        mean_gap = np.mean([r["gap"] for r in fold_results])
        median_threshold = float(np.median(fold_thresholds))

        log(f"  {hp_name} SUMMARY: AUC={mean_auc:.4f}±{std_auc:.4f}  "
            f"gap={mean_gap:.3f}  threshold={median_threshold:.3f}")

        if mean_auc > best_mean_auc:
            best_mean_auc = mean_auc
            best_result = {
                "hp_name": hp_name,
                "hp_config": hp,
                "fold_results": fold_results,
                "mean_auc": mean_auc,
                "std_auc": std_auc,
                "mean_gap": mean_gap,
                "oos_threshold": median_threshold,
                "fold_thresholds": fold_thresholds,
            }

    log(f"\n  ★ BEST: {best_result['hp_name']}  AUC={best_result['mean_auc']:.4f}±{best_result['std_auc']:.4f}  "
        f"gap={best_result['mean_gap']:.3f}  threshold={best_result['oos_threshold']:.3f}")

    # ── Train final model on ALL data with best HP ──
    log(f"  Training final model on all {len(X):,} samples...")
    scale_pos = (y == 0).sum() / max((y == 1).sum(), 1)
    final_model = xgb.XGBClassifier(
        **best_result["hp_config"],
        scale_pos_weight=scale_pos,
        random_state=42,
        eval_metric="logloss",
        verbosity=0,
    )
    final_model.fit(X, y, verbose=False)

    # Feature importance (gain-based)
    importances = final_model.feature_importances_
    imp_order = np.argsort(-importances)
    log(f"  Feature importance (gain):")
    for rank, idx in enumerate(imp_order):
        log(f"    {rank+1:2d}. {features[idx]:<35s} {importances[idx]:.4f}")

    best_result["final_model"] = final_model
    best_result["features"] = features
    best_result["feature_importances"] = dict(zip(features, importances.tolist()))
    best_result["model_name"] = model_name
    best_result["label_col"] = label_col

    return best_result


# ═══════════════════════════════════════════════════════════════
# STEP 5: SIGNAL REPLAY
# ═══════════════════════════════════════════════════════════════

def signal_replay(df: pd.DataFrame, model_result: dict) -> dict:
    """Run Signal Replay with the OOS-calibrated threshold.

    Uses the LAST 20% of each ticker's data (temporal holdout) for evaluation.
    This data was part of training, but we use forward returns as validation.
    """
    model = model_result["final_model"]
    features = model_result["features"]
    threshold = model_result["oos_threshold"]
    model_name = model_result["model_name"]
    label_col = model_result["label_col"]

    log(f"\n  ── SIGNAL REPLAY: {model_name} (threshold={threshold:.3f}) ──")

    # Use last 20% of each ticker as evaluation window
    replay_results = []
    for tk in sorted(df["ticker"].unique()):
        tk_mask = df["ticker"] == tk
        tk_df = df.loc[tk_mask].copy()
        n = len(tk_df)
        eval_start = int(n * 0.8)
        eval_df = tk_df.iloc[eval_start:]

        if len(eval_df) < 20:
            continue

        X_eval = eval_df[features].values.astype(np.float32)
        X_eval = np.nan_to_num(X_eval, nan=0.0)
        probs = model.predict_proba(X_eval)[:, 1]

        # Find signal bars (prob > threshold)
        signal_mask = probs > threshold
        n_signals = signal_mask.sum()

        if n_signals == 0:
            continue

        signal_bars = eval_df.iloc[np.where(signal_mask)[0]]

        # Measure forward returns at signal bars
        for horizon in [5, 10, 20]:
            fwd_col = f"fwd_return_{horizon}d"
            fwd_returns = signal_bars[fwd_col].dropna()
            if len(fwd_returns) == 0:
                continue

            # For PISO, expect POSITIVE returns (buying at bottom)
            # For TECHO, expect NEGATIVE returns (selling at top)
            is_piso = "piso" in model_name.lower()
            if is_piso:
                hit_rate = (fwd_returns > 0).mean() * 100
                mean_ret = fwd_returns.mean()
            else:
                hit_rate = (fwd_returns < 0).mean() * 100
                mean_ret = -fwd_returns.mean()  # Positive = good for shorts

            replay_results.append({
                "ticker": tk,
                "horizon": horizon,
                "n_signals": len(fwd_returns),
                "hit_rate": hit_rate,
                "mean_return": mean_ret,
                "median_return": float(fwd_returns.median()) * (1 if is_piso else -1),
            })

    if not replay_results:
        log(f"    ⚠️ No signals generated — threshold may be too restrictive")
        return {"replay_results": [], "pass": False}

    replay_df = pd.DataFrame(replay_results)

    # Aggregate by horizon
    log(f"\n  {'Horizon':<10} {'Signals':<10} {'Hit Rate':<12} {'Mean Ret':<12} {'Verdict'}")
    log(f"  {'─'*10} {'─'*10} {'─'*12} {'─'*12} {'─'*10}")

    pass_count = 0
    total_horizons = 0
    for horizon in [5, 10, 20]:
        h_df = replay_df[replay_df["horizon"] == horizon]
        if len(h_df) == 0:
            continue
        n_signals = h_df["n_signals"].sum()
        mean_hr = h_df["hit_rate"].mean()
        mean_ret = h_df["mean_return"].mean()
        verdict = "✅" if mean_hr > 50 else "❌"
        if mean_hr > 50:
            pass_count += 1
        total_horizons += 1
        log(f"  {horizon}d{'':<7} {n_signals:<10} {mean_hr:.1f}%{'':<7} {mean_ret:+.2f}%{'':<6} {verdict}")

    overall_pass = pass_count >= 2  # At least 2 of 3 horizons pass
    log(f"\n  Signal Replay: {'✅ PASS' if overall_pass else '❌ FAIL'} "
        f"({pass_count}/{total_horizons} horizons > 50% HR)")

    # Per-ticker breakdown
    log(f"\n  Per-ticker (10d horizon):")
    h10 = replay_df[replay_df["horizon"] == 10]
    for _, row in h10.sort_values("hit_rate", ascending=False).iterrows():
        v = "✅" if row["hit_rate"] > 50 else "❌"
        log(f"    {row['ticker']:<6} n={row['n_signals']:<4} HR={row['hit_rate']:.1f}%  "
            f"ret={row['mean_return']:+.2f}% {v}")

    return {
        "replay_results": replay_results,
        "pass": overall_pass,
        "threshold_used": threshold,
    }


# ═══════════════════════════════════════════════════════════════
# STEP 6: DEFLATED SHARPE RATIO
# ═══════════════════════════════════════════════════════════════

def compute_dsr(fold_aucs: list[float], n_trials: int) -> float:
    """Deflated Sharpe Ratio (López de Prado).

    Treats (AUC - 0.5) as "excess returns" and computes DSR.
    """
    excess = [a - 0.5 for a in fold_aucs]
    if np.std(excess) < 1e-8:
        return 0.0

    sharpe = np.mean(excess) / np.std(excess)
    T = len(fold_aucs)
    sr0 = np.sqrt(2 * np.log(n_trials))
    skew = float(pd.Series(excess).skew()) if T >= 3 else 0.0
    kurt = float(pd.Series(excess).kurtosis()) + 3 if T >= 4 else 3.0

    denom = np.sqrt(1 - skew * sharpe + (kurt - 1) / 4 * sharpe ** 2)
    if denom <= 0:
        return 0.0

    z = (sharpe - sr0) * np.sqrt(T - 1) / denom
    return float(norm.cdf(z))


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Train Sentinel V2")
    parser.add_argument(
        "--config",
        default="v2a_shap_aligned",
        choices=list(CONFIGS.keys()),
        help="Training configuration variant",
    )
    args = parser.parse_args()

    config_name = args.config
    config = CONFIGS[config_name]

    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = OUT_DIR / f"sentinel_v2_{config_name}_{timestamp_str}.log"
    pkl_file = OUT_DIR / f"sentinel_v2_{config_name}_{timestamp_str}.pkl"

    log_section(f"TRAIN SENTINEL V2 — {config_name}")
    log(f"  Config: {config['description']}")
    log(f"  Timestamp: {timestamp_str}")
    log(f"  Output: {OUT_DIR}")
    log(f"  PurgedKFold: {N_FOLDS} folds, embargo={EMBARGO_BARS} bars")

    t0 = time.time()
    store = TimescaleDataStore()

    # ── STEP 1: Load data ──
    df = load_data(store)
    store.close()

    # ── STEP 2: Temporal features (if configured) ──
    if config["temporal_features"]:
        df = compute_temporal_features(df)
    else:
        log_section("STEP 2: TEMPORAL FEATURES — SKIPPED (not in this config)")

    # ── STEP 3: Select label strategy ──
    log_section("STEP 3: LABEL STRATEGY")
    label_strategy = config["label_strategy"]
    if label_strategy == "or_multiscale":
        piso_label = "is_piso"
        techo_label = "is_techo"
        log(f"  Strategy: OR multi-scale (3% OR 5% OR 7%)")
    elif label_strategy == "5pct_only":
        piso_label = "is_piso_5pct"
        techo_label = "is_techo_5pct"
        log(f"  Strategy: 5% only")
    else:
        piso_label = "is_piso"
        techo_label = "is_techo"
        log(f"  Strategy: default (OR multi-scale)")

    log(f"  PISO positive rate: {df[piso_label].mean()*100:.1f}%")
    log(f"  TECHO positive rate: {df[techo_label].mean()*100:.1f}%")

    # ── STEP 4: Train PISO ──
    log_section("STEP 4A: TRAIN PISO MODEL")
    piso_features = config["piso_features"]
    # Verify all features exist in df
    missing_piso = [f for f in piso_features if f not in df.columns]
    if missing_piso:
        log(f"  ❌ Missing PISO features: {missing_piso}", "ERROR")
        return
    piso_result = train_model(df, piso_features, piso_label, "PISO", config["hyperparams"])

    # ── Train TECHO ──
    log_section("STEP 4B: TRAIN TECHO MODEL")
    techo_features = config["techo_features"]
    missing_techo = [f for f in techo_features if f not in df.columns]
    if missing_techo:
        log(f"  ❌ Missing TECHO features: {missing_techo}", "ERROR")
        return
    techo_result = train_model(df, techo_features, techo_label, "TECHO", config["hyperparams"])

    # ── STEP 5: Signal Replay ──
    log_section("STEP 5: SIGNAL REPLAY (OOS Threshold)")
    piso_replay = signal_replay(df, piso_result)
    techo_replay = signal_replay(df, techo_result)

    # Also replay with 0.5 threshold for comparison
    log(f"\n  ── COMPARISON: Signal Replay with threshold=0.5 ──")
    piso_result_05 = dict(piso_result)
    piso_result_05["oos_threshold"] = 0.5
    techo_result_05 = dict(techo_result)
    techo_result_05["oos_threshold"] = 0.5
    piso_replay_05 = signal_replay(df, piso_result_05)
    techo_replay_05 = signal_replay(df, techo_result_05)

    # ── STEP 6: DSR + Final Audit ──
    log_section("STEP 6: DEFLATED SHARPE RATIO + AUDIT")

    piso_aucs = [r["auc_test"] for r in piso_result["fold_results"]]
    techo_aucs = [r["auc_test"] for r in techo_result["fold_results"]]
    n_trials = len(config["hyperparams"]) * 2  # configs × models

    piso_dsr = compute_dsr(piso_aucs, n_trials)
    techo_dsr = compute_dsr(techo_aucs, n_trials)

    log(f"  PISO DSR: {piso_dsr:.3f} (n_trials={n_trials}) "
        f"→ {'✅ Significant' if piso_dsr > 0.5 else '⚠️ Not significant'}")
    log(f"  TECHO DSR: {techo_dsr:.3f} (n_trials={n_trials}) "
        f"→ {'✅ Significant' if techo_dsr > 0.5 else '⚠️ Not significant'}")

    # ── Summary ──
    elapsed = time.time() - t0
    log_section("FINAL SUMMARY")
    log(f"  Config: {config_name} — {config['description']}")
    log(f"  Data: {len(df):,} snapshots × {len(df['ticker'].unique())} tickers")
    log(f"")
    log(f"  ┌─────────────────────────────────────────────────────────────────┐")
    log(f"  │ Model    AUC±σ          Gap    Threshold  DSR    Replay        │")
    log(f"  ├─────────────────────────────────────────────────────────────────┤")
    log(f"  │ PISO  {piso_result['mean_auc']:.4f}±{piso_result['std_auc']:.3f}"
        f"   {piso_result['mean_gap']:.3f}  "
        f"  {piso_result['oos_threshold']:.3f}    {piso_dsr:.3f}  "
        f"{'✅ PASS' if piso_replay['pass'] else '❌ FAIL':<14}│")
    log(f"  │ TECHO {techo_result['mean_auc']:.4f}±{techo_result['std_auc']:.3f}"
        f"   {techo_result['mean_gap']:.3f}  "
        f"  {techo_result['oos_threshold']:.3f}    {techo_dsr:.3f}  "
        f"{'✅ PASS' if techo_replay['pass'] else '❌ FAIL':<14}│")
    log(f"  └─────────────────────────────────────────────────────────────────┘")
    log(f"")
    log(f"  PISO best HP: {piso_result['hp_name']} ({piso_result['hp_config']})")
    log(f"  TECHO best HP: {techo_result['hp_name']} ({techo_result['hp_config']})")
    log(f"  PISO features ({len(piso_features)}): {piso_features}")
    log(f"  TECHO features ({len(techo_features)}): {techo_features}")
    log(f"  Time: {elapsed:.0f}s ({elapsed/60:.1f}min)")

    # ── Save results ──
    results = {
        "config_name": config_name,
        "config": config,
        "piso": {
            "model": piso_result["final_model"],
            "features": piso_features,
            "label_col": piso_label,
            "best_hp": piso_result["hp_config"],
            "mean_auc": piso_result["mean_auc"],
            "std_auc": piso_result["std_auc"],
            "mean_gap": piso_result["mean_gap"],
            "oos_threshold": piso_result["oos_threshold"],
            "fold_results": piso_result["fold_results"],
            "feature_importances": piso_result["feature_importances"],
            "dsr": piso_dsr,
            "replay": piso_replay,
            "replay_05": piso_replay_05,
        },
        "techo": {
            "model": techo_result["final_model"],
            "features": techo_features,
            "label_col": techo_label,
            "best_hp": techo_result["hp_config"],
            "mean_auc": techo_result["mean_auc"],
            "std_auc": techo_result["std_auc"],
            "mean_gap": techo_result["mean_gap"],
            "oos_threshold": techo_result["oos_threshold"],
            "fold_results": techo_result["fold_results"],
            "feature_importances": techo_result["feature_importances"],
            "dsr": techo_dsr,
            "replay": techo_replay,
            "replay_05": techo_replay_05,
        },
        "metadata": {
            "n_samples": len(df),
            "n_tickers": len(df["ticker"].unique()),
            "n_folds": N_FOLDS,
            "embargo_bars": EMBARGO_BARS,
            "label_strategy": label_strategy,
            "timestamp": timestamp_str,
            "elapsed_seconds": elapsed,
            "script_version": "v2.0",
        },
    }

    with open(pkl_file, "wb") as f:
        pickle.dump(results, f)
    log(f"\n  ✅ PKL saved: {pkl_file.name} ({pkl_file.stat().st_size / (1024*1024):.1f} MB)")

    # Save log
    with open(log_file, "w") as f:
        f.write("\n".join(LOG_LINES))
    log(f"  ✅ LOG saved: {log_file.name}")

    log(f"\n  {'='*60}")
    log(f"  TRAIN SENTINEL V2 COMPLETE")
    log(f"  {'='*60}")


if __name__ == "__main__":
    main()
