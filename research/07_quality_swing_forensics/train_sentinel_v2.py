#!/usr/bin/env python3
"""
Train Sentinel Models v2 — Canonical ZigZag 2.5%
=====================================================
Retrains PISO and TECHO using canonical H/L zigzag at 2.5%.

Changes from v1:
  - ZigZag: canonical H/L (not close-only) at 2.5% (not 3/5/7% composite)
  - Labels: single-scale (2.5%) instead of OR(3%, 5%, 7%)
  - Model files: sentinel_piso_v2.pkl, sentinel_techo_v2.pkl
  - Everything else identical: features, XGB params, PurgedKFold

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python research/07_quality_swing_forensics/train_sentinel_v2.py
"""
import os, sys, time, pickle
from pathlib import Path
from datetime import datetime, timezone

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.metrics import roc_auc_score, precision_recall_curve

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

MODELS_DIR = root_dir / "backend" / "models"

TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]

# ── NEW: Single-scale canonical zigzag ──
ZZ_THRESHOLD = 0.025
DEDUP_PROXIMITY = 3  # bars

# Feature sets (same as v1 — SHAP-selected from Sprint 2)
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

XGB_PARAMS = {
    "n_estimators": 200,
    "max_depth": 4,
    "learning_rate": 0.05,
    "min_child_weight": 50,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "scale_pos_weight": 1.0,
    "eval_metric": "logloss",
    "random_state": 42,
    "n_jobs": -1,
}


def purged_kfold_split(df, n_splits=5, embargo_pct=0.05):
    """PurgedKFold: temporal splits with embargo gap per ticker."""
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
    """Load snapshots + zigzag 2.5% labels."""
    print("  Loading channel snapshots with Kalman features...")
    conn = store._conn()
    cur = conn.cursor()

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
    print(f"  Loaded {len(df):,} snapshots")

    # Load zigzag 2.5% canonical labels
    print(f"  Loading zigzag {ZZ_THRESHOLD*100:.1f}% canonical labels...")
    cur.execute("""
        SELECT ticker, timestamp, tp_type
        FROM engine.zigzag_points
        WHERE min_swing_pct = %s
        ORDER BY ticker, timestamp
    """, (ZZ_THRESHOLD,))
    zz_rows = cur.fetchall()
    zz_df = pd.DataFrame(zz_rows, columns=["ticker", "zz_timestamp", "tp_type"])
    zz_df["zz_timestamp"] = pd.to_datetime(zz_df["zz_timestamp"], utc=True)
    zz_df["zz_date"] = zz_df["zz_timestamp"].dt.tz_localize(None).dt.normalize()
    print(f"  Loaded {len(zz_df):,} zigzag points "
          f"({(zz_df['tp_type']=='MIN').sum():,} MIN, {(zz_df['tp_type']=='MAX').sum():,} MAX)")

    store._put(conn)

    # Label each snapshot: is it within DEDUP_PROXIMITY bars of a zigzag?
    df["is_piso"] = False
    df["is_techo"] = False

    for tk in TICKERS:
        tk_snap = df[df["ticker"] == tk]
        tk_zz = zz_df[zz_df["ticker"] == tk]
        if tk_snap.empty or tk_zz.empty:
            continue

        snap_dates = tk_snap["timestamp"].dt.tz_localize(None).values
        zz_dates_arr = tk_zz["zz_date"].values
        zz_types_arr = tk_zz["tp_type"].values

        for i in range(len(zz_dates_arr)):
            zz_date = zz_dates_arr[i]
            distances = np.abs((snap_dates - zz_date) / np.timedelta64(1, "D"))
            near_mask = distances <= DEDUP_PROXIMITY
            mask_idx = tk_snap.index[near_mask]
            if zz_types_arr[i] == "MIN":
                df.loc[mask_idx, "is_piso"] = True
            elif zz_types_arr[i] == "MAX":
                df.loc[mask_idx, "is_techo"] = True

    n_piso = df["is_piso"].sum()
    n_techo = df["is_techo"].sum()
    n_ambig = (df["is_piso"] & df["is_techo"]).sum()
    print(f"  Labels: {n_piso:,} PISO ({n_piso/len(df)*100:.1f}%), "
          f"{n_techo:,} TECHO ({n_techo/len(df)*100:.1f}%), "
          f"{n_ambig:,} ambiguous ({n_ambig/len(df)*100:.1f}%)")

    return df


def train_model(df, features, label_col, opposite_col, model_name):
    """Train one XGBoost model with PurgedKFold.

    Strategy A from Phase H: opposite group as negatives.
    """
    print(f"\n{'='*70}")
    print(f"  Training {model_name}")
    print(f"  Features: {features}")
    print(f"  Label: {label_col} | Opposite (negative): {opposite_col}")
    print(f"{'='*70}")

    X = df[features].fillna(0.0).values
    y = df[label_col].values.astype(int)
    n_pos = y.sum()
    n_neg = len(y) - n_pos
    print(f"  Samples: {len(y):,} ({n_pos:,} positive = {n_pos/len(y)*100:.1f}%)")

    params = XGB_PARAMS.copy()
    params["scale_pos_weight"] = n_neg / max(n_pos, 1)

    # PurgedKFold
    splits = purged_kfold_split(df)
    fold_aucs = []
    fold_aucs_train = []
    fold_models = []

    for fold_idx, (train_idx, test_idx) in enumerate(splits):
        train_pos = [df.index.get_loc(i) for i in train_idx if i in df.index]
        test_pos = [df.index.get_loc(i) for i in test_idx if i in df.index]

        X_train, y_train = X[train_pos], y[train_pos]
        X_test, y_test = X[test_pos], y[test_pos]

        model = XGBClassifier(**params)
        model.fit(X_train, y_train, verbose=False)

        y_prob_test = model.predict_proba(X_test)[:, 1]
        y_prob_train = model.predict_proba(X_train)[:, 1]

        if len(np.unique(y_test)) < 2:
            print(f"  Fold {fold_idx}: skipped (single class)")
            continue

        auc_test = roc_auc_score(y_test, y_prob_test)
        auc_train = roc_auc_score(y_train, y_prob_train)
        gap = auc_train - auc_test

        fold_aucs.append(auc_test)
        fold_aucs_train.append(auc_train)
        fold_models.append(model)
        print(f"  Fold {fold_idx}: AUC={auc_test:.4f} (train={auc_train:.4f} gap={gap:.3f})")

    if not fold_aucs:
        print(f"  ❌ No valid folds")
        return None

    mean_auc = np.mean(fold_aucs)
    std_auc = np.std(fold_aucs)
    mean_gap = np.mean(fold_aucs_train) - mean_auc
    print(f"\n  Mean AUC: {mean_auc:.4f} ± {std_auc:.4f} (gap: {mean_gap:.3f})")

    # DSR
    dsr = (mean_auc - 0.5) / max(std_auc, 1e-6) * np.sqrt(len(fold_aucs))
    print(f"  DSR: {dsr:.2f} (>2.0 = significant)")

    # Train final model on all data
    final_model = XGBClassifier(**params)
    final_model.fit(X, y, verbose=False)

    # Calibrate threshold
    y_prob_full = final_model.predict_proba(X)[:, 1]
    precision, recall, thresholds = precision_recall_curve(y, y_prob_full)
    diffs = np.abs(precision[:-1] - recall[:-1])
    best_idx = np.argmin(diffs)
    optimal_threshold = float(thresholds[best_idx])
    print(f"  Optimal threshold: {optimal_threshold:.4f}")
    print(f"  At threshold: P={precision[best_idx]:.3f} R={recall[best_idx]:.3f}")

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
        "mean_gap": mean_gap,
        "class_balance": {"positive": int(n_pos), "negative": int(n_neg)},
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_samples": len(y),
        "zigzag_version": "canonical_hl_2.5pct",
        "feature_importance": {features[i]: float(importances[i]) for i in range(len(features))},
    }


def main():
    print("=" * 70)
    print("  TRAIN SENTINEL v2 — Canonical ZigZag 2.5%")
    print(f"  ZigZag: H/L canonical, {ZZ_THRESHOLD*100:.1f}% swing")
    print("  PurgedKFold 5 folds, 5% embargo")
    print("  6 SHAP-selected features per model")
    print("=" * 70)

    store = TimescaleDataStore()
    t0 = time.time()

    df = load_feature_lake(store)
    store.close()

    # ── PISO ──
    piso_result = train_model(df, PISO_FEATURES, "is_piso", "is_techo", "SENTINEL_PISO_v2")
    if piso_result:
        pkl_path = MODELS_DIR / "sentinel_piso_v2.pkl"
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        with open(pkl_path, "wb") as f:
            pickle.dump(piso_result, f)
        print(f"\n  ✅ Saved: {pkl_path}")

    # ── TECHO ──
    techo_result = train_model(df, TECHO_FEATURES, "is_techo", "is_piso", "SENTINEL_TECHO_v2")
    if techo_result:
        pkl_path = MODELS_DIR / "sentinel_techo_v2.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump(techo_result, f)
        print(f"\n  ✅ Saved: {pkl_path}")

    # ── COMPARISON v1 vs v2 ──
    elapsed = time.time() - t0
    print(f"\n{'=' * 70}")
    print(f"  TRAINING COMPLETE — Time: {elapsed:.1f}s")
    print(f"{'=' * 70}")

    print(f"\n  {'Model':<20s} {'AUC':>8s} {'± std':>8s} {'DSR':>8s} {'Gap':>8s} {'Threshold':>10s} {'Positives':>10s}")
    print(f"  {'─'*72}")

    # Load v1 for comparison
    for name, result in [("PISO_v2", piso_result), ("TECHO_v2", techo_result)]:
        if result:
            print(f"  {name:<20s} {result['mean_auc']:>8.4f} {result['std_auc']:>8.4f} "
                  f"{result['dsr']:>8.2f} {result['mean_gap']:>8.3f} "
                  f"{result['threshold']:>10.4f} {result['class_balance']['positive']:>10,}")

    # Try to load v1 for side-by-side
    for v1_name in ["piso", "techo"]:
        v1_path = MODELS_DIR / f"sentinel_{v1_name}_v1.pkl"
        if v1_path.exists():
            with open(v1_path, "rb") as f:
                v1 = pickle.load(f)
            gap = v1.get('mean_gap', 0)
            print(f"  {v1_name.upper()+'_v1 (old)':<20s} {v1['mean_auc']:>8.4f} {v1['std_auc']:>8.4f} "
                  f"{v1['dsr']:>8.2f} {gap:>8.3f} "
                  f"{v1['threshold']:>10.4f} {v1['class_balance']['positive']:>10,}")


if __name__ == "__main__":
    main()
