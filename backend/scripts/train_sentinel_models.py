#!/usr/bin/env python3
"""
Train Sentinel Models — PISO and TECHO
==========================================
Trains 2 XGBoost models from the Vault Feature Lake:
  - PISO: P(near bottom) — labels from zigzag LOW points
  - TECHO: P(near top) — labels from zigzag HIGH points

Data source: engine.channel_snapshots (with Kalman 5-channel columns)
Labels: engine.zigzag_points (multi-scale: 3%/5%/7%)

Validation: PurgedKFold with 5% embargo (López de Prado methodology)
Metrics: AUC, DSR, per-fold consistency

Features (6 per model — SHAP-selected from Sprint 2):
  PISO: kf_rsi_pred_val, kf_price_filt_vel, kf_price_pred_val,
        kf_conj_pred_val, rsi_value, sigma_tide
  TECHO: kf_rsi_pred_val, kf_price_filt_vel, kf_tension_pred_val,
         kf_conj_filt_vel, rsi_value, sigma_tide

Output: backend/models/sentinel_piso_v1.pkl, sentinel_techo_v1.pkl

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/train_sentinel_models.py
"""
import os
import sys
import time
import pickle
import logging
from pathlib import Path
from datetime import datetime, timezone

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.metrics import roc_auc_score

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

MODELS_DIR = root_dir / "data" / "models"

# Tickers
TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]

# Zigzag settings (from Sprint 2)
ZZ_THRESHOLDS = [0.03, 0.05, 0.07]
DEDUP_PROXIMITY = 3  # bars

# Feature sets (SHAP-selected from Sprint 2 Phase E/F)
PISO_FEATURES = [
    "kf_rsi_pred_val",
    "kf_price_filt_vel",
    "kf_price_pred_val",
    "kf_conj_pred_val",
    "rsi_value",
    "sigma_tide",
]

TECHO_FEATURES = [
    "kf_rsi_pred_val",
    "kf_price_filt_vel",
    "kf_tension_pred_val",
    "kf_conj_filt_vel",
    "rsi_value",
    "sigma_tide",
]

# XGBoost hyperparameters (from Sprint 2 grid search)
XGB_PARAMS = {
    "n_estimators": 200,
    "max_depth": 4,
    "learning_rate": 0.05,
    "min_child_weight": 50,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "scale_pos_weight": 1.0,  # Will be adjusted per label imbalance
    "eval_metric": "logloss",
    "random_state": 42,
    "n_jobs": -1,
}


def purged_kfold_split(df, n_splits=5, embargo_pct=0.05):
    """PurgedKFold: temporal splits with embargo gap.

    Prevents train/test leakage by:
    1. Splitting temporally (not randomly)
    2. Adding embargo gap between train and test
    3. Per-ticker temporal ordering preserved

    Returns list of (train_idx, test_idx) arrays.
    """
    splits = []
    for tk in df["ticker"].unique():
        tk_mask = df["ticker"] == tk
        tk_indices = df.index[tk_mask].tolist()
        n = len(tk_indices)
        fold_size = n // n_splits
        embargo_size = max(1, int(fold_size * embargo_pct))

        for fold in range(n_splits):
            test_start = fold * fold_size
            test_end = min(test_start + fold_size, n)
            test_idx = tk_indices[test_start:test_end]

            # Train: everything EXCEPT test + embargo
            embargo_start = max(0, test_start - embargo_size)
            embargo_end = min(n, test_end + embargo_size)
            train_idx = tk_indices[:embargo_start] + tk_indices[embargo_end:]

            if fold < len(splits):
                splits[fold] = (
                    splits[fold][0] + train_idx,
                    splits[fold][1] + test_idx,
                )
            else:
                splits.append((train_idx, test_idx))

    return [(np.array(tr), np.array(te)) for tr, te in splits]


def load_feature_lake(store):
    """Load snapshots with Kalman features + zigzag labels."""
    print("  Loading channel snapshots with Kalman features...")
    conn = store._conn()
    cur = conn.cursor()

    # Load all snapshots with Kalman columns
    cur.execute("""
        SELECT ticker, timestamp,
               kf_rsi_pred_val, kf_price_filt_vel, kf_price_pred_val,
               kf_price_innovation,
               kf_rvol_pred_val, kf_rvol_filt_vel,
               kf_tension_pred_val, kf_tension_filt_vel,
               kf_conj_pred_val, kf_conj_filt_vel,
               rsi_value, sigma_tide, sigma_current, sigma_wave,
               tension_tide, conj_wave_tide, tide_slope,
               compression_ratio, fear_level
        FROM engine.channel_snapshots
        WHERE kf_rsi_pred_val IS NOT NULL
        ORDER BY ticker, timestamp
    """)
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    df = pd.DataFrame(rows, columns=cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    print(f"  Loaded {len(df):,} snapshots with Kalman features")

    # Load zigzag points for labeling
    print("  Loading zigzag labels...")
    for threshold in ZZ_THRESHOLDS:
        pct = int(threshold * 100)
        cur.execute("""
            SELECT ticker, timestamp, tp_type
            FROM engine.zigzag_points
            WHERE min_swing_pct = %s
            ORDER BY ticker, timestamp
        """, (threshold,))
        zz_rows = cur.fetchall()
        zz_df = pd.DataFrame(zz_rows, columns=["ticker", "zz_timestamp", "tp_type"])
        zz_df["zz_timestamp"] = pd.to_datetime(zz_df["zz_timestamp"], utc=True)
        zz_df["zz_date"] = zz_df["zz_timestamp"].dt.tz_localize(None).dt.normalize()

        # Label each snapshot: is it within DEDUP_PROXIMITY bars of a zigzag?
        df[f"near_low_{pct}"] = False
        df[f"near_high_{pct}"] = False

        for tk in TICKERS:
            tk_snap = df[df["ticker"] == tk].copy()
            tk_zz = zz_df[zz_df["ticker"] == tk]
            if tk_snap.empty or tk_zz.empty:
                continue

            # Strip timezone for numpy date arithmetic
            snap_dates = tk_snap["timestamp"].dt.tz_localize(None).values
            zz_dates_arr = tk_zz["zz_date"].values  # already tz-naive
            zz_types_arr = tk_zz["tp_type"].values

            for i in range(len(zz_dates_arr)):
                zz_date = zz_dates_arr[i]
                distances = np.abs((snap_dates - zz_date) / np.timedelta64(1, "D"))
                near_mask = distances <= DEDUP_PROXIMITY
                mask_idx = tk_snap.index[near_mask]
                if zz_types_arr[i] == "MIN":
                    df.loc[mask_idx, f"near_low_{pct}"] = True
                elif zz_types_arr[i] == "MAX":
                    df.loc[mask_idx, f"near_high_{pct}"] = True

        n_low = df[f"near_low_{pct}"].sum()
        n_high = df[f"near_high_{pct}"].sum()
        print(f"  Zigzag {pct}%: {n_low:,} LOW labels, {n_high:,} HIGH labels")

    store._put(conn)

    # Create composite labels (any scale)
    df["is_piso"] = df["near_low_3"] | df["near_low_5"] | df["near_low_7"]
    df["is_techo"] = df["near_high_3"] | df["near_high_5"] | df["near_high_7"]
    print(f"  Composite: {df['is_piso'].sum():,} PISO, {df['is_techo'].sum():,} TECHO")

    return df


def train_model(df, features, label_col, model_name):
    """Train one XGBoost model with PurgedKFold."""
    print(f"\n{'='*60}")
    print(f"  Training {model_name}")
    print(f"  Features: {features}")
    print(f"  Label: {label_col}")
    print(f"{'='*60}")

    # Prepare data
    X = df[features].fillna(0.0).values
    y = df[label_col].values.astype(int)
    n_pos = y.sum()
    n_neg = len(y) - n_pos
    print(f"  Class balance: {n_pos:,} positive ({n_pos/len(y)*100:.1f}%), {n_neg:,} negative")

    # Adjust scale_pos_weight for class imbalance
    params = XGB_PARAMS.copy()
    params["scale_pos_weight"] = n_neg / max(n_pos, 1)

    # PurgedKFold
    splits = purged_kfold_split(df)
    fold_aucs = []
    fold_models = []

    for fold_idx, (train_idx, test_idx) in enumerate(splits):
        # Convert to positional indices
        train_pos = [df.index.get_loc(i) for i in train_idx if i in df.index]
        test_pos = [df.index.get_loc(i) for i in test_idx if i in df.index]

        X_train, y_train = X[train_pos], y[train_pos]
        X_test, y_test = X[test_pos], y[test_pos]

        model = XGBClassifier(**params)
        model.fit(X_train, y_train, verbose=False)

        y_prob = model.predict_proba(X_test)[:, 1]

        if len(np.unique(y_test)) < 2:
            print(f"  Fold {fold_idx}: skipped (single class in test)")
            continue

        auc = roc_auc_score(y_test, y_prob)
        fold_aucs.append(auc)
        fold_models.append(model)
        print(f"  Fold {fold_idx}: AUC={auc:.4f} (train={len(train_pos):,}, test={len(test_pos):,})")

    if not fold_aucs:
        print(f"  ❌ No valid folds for {model_name}")
        return None

    mean_auc = np.mean(fold_aucs)
    std_auc = np.std(fold_aucs)
    print(f"\n  Mean AUC: {mean_auc:.4f} ± {std_auc:.4f}")

    # Deflated Sharpe Ratio (simplified)
    if std_auc > 0:
        dsr = (mean_auc - 0.5) / std_auc * np.sqrt(len(fold_aucs))
    else:
        dsr = 0.0
    print(f"  DSR: {dsr:.2f} (>2.0 = significant)")

    # Train final model on all data
    final_model = XGBClassifier(**params)
    final_model.fit(X, y, verbose=False)

    # Calibrate threshold
    y_prob_full = final_model.predict_proba(X)[:, 1]
    # Use precision-recall balance: threshold where precision ≈ recall
    from sklearn.metrics import precision_recall_curve
    precision, recall, thresholds = precision_recall_curve(y, y_prob_full)
    # Find threshold where precision meets recall
    diffs = np.abs(precision[:-1] - recall[:-1])
    best_idx = np.argmin(diffs)
    optimal_threshold = float(thresholds[best_idx])
    print(f"  Optimal threshold: {optimal_threshold:.4f}")

    # Feature importance
    importances = final_model.feature_importances_
    sorted_idx = np.argsort(importances)[::-1]
    print(f"\n  Feature importance:")
    for i in sorted_idx:
        print(f"    {features[i]:<25s}: {importances[i]:.4f}")

    return {
        "model": final_model,
        "feature_cols": features,
        "threshold": optimal_threshold,
        "mean_auc": mean_auc,
        "std_auc": std_auc,
        "dsr": dsr,
        "fold_aucs": fold_aucs,
        "class_balance": {"positive": int(n_pos), "negative": int(n_neg)},
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_samples": len(y),
        "feature_importance": {features[i]: float(importances[i]) for i in range(len(features))},
    }


def main():
    print("=" * 80)
    print("  TRAIN SENTINEL MODELS — PISO and TECHO")
    print("  PurgedKFold with 5% embargo (López de Prado)")
    print("  6 SHAP-selected features per model")
    print("=" * 80)

    store = TimescaleDataStore()
    t0 = time.time()

    # Load feature lake
    df = load_feature_lake(store)
    store.close()

    # Train PISO model
    piso_result = train_model(df, PISO_FEATURES, "is_piso", "SENTINEL_PISO")
    if piso_result:
        pkl_path = MODELS_DIR / "sentinel_piso_v1.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump(piso_result, f)
        print(f"\n  ✅ Saved: {pkl_path}")
        print(f"     AUC={piso_result['mean_auc']:.4f}, DSR={piso_result['dsr']:.2f}")

    # Train TECHO model
    techo_result = train_model(df, TECHO_FEATURES, "is_techo", "SENTINEL_TECHO")
    if techo_result:
        pkl_path = MODELS_DIR / "sentinel_techo_v1.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump(techo_result, f)
        print(f"\n  ✅ Saved: {pkl_path}")
        print(f"     AUC={techo_result['mean_auc']:.4f}, DSR={techo_result['dsr']:.2f}")

    elapsed = time.time() - t0
    print(f"\n{'=' * 80}")
    print(f"  TRAINING COMPLETE")
    print(f"  Time: {elapsed:.1f}s")
    if piso_result:
        print(f"  PISO: AUC={piso_result['mean_auc']:.4f} DSR={piso_result['dsr']:.2f}")
    if techo_result:
        print(f"  TECHO: AUC={techo_result['mean_auc']:.4f} DSR={techo_result['dsr']:.2f}")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
