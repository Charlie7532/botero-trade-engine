#!/usr/bin/env python3
"""
Sentinel v2 — Proximity Sweep + Ambiguity Exclusion
=====================================================
Tests DEDUP_PROXIMITY = 1, 2, 3 with and without ambiguous bar exclusion.
Finds the configuration that maximizes AUC while minimizing ambiguity.

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python research/07_quality_swing_forensics/train_sentinel_v2_sweep.py
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

ZZ_THRESHOLD = 0.025

PISO_FEATURES = [
    "kf_rsi_pred_val", "kf_price_filt_vel", "kf_price_pred_val",
    "kf_conj_pred_val", "rsi_value", "sigma_tide",
]
TECHO_FEATURES = [
    "kf_rsi_pred_val", "kf_price_filt_vel", "kf_tension_pred_val",
    "kf_conj_filt_vel", "rsi_value", "sigma_tide",
]

XGB_PARAMS = {
    "n_estimators": 200, "max_depth": 4, "learning_rate": 0.05,
    "min_child_weight": 50, "subsample": 0.8, "colsample_bytree": 0.8,
    "scale_pos_weight": 1.0, "eval_metric": "logloss",
    "random_state": 42, "n_jobs": -1,
}


def purged_kfold_split(df, n_splits=5, embargo_pct=0.05):
    splits = []
    for tk in df["ticker"].unique():
        tk_indices = df.index[df["ticker"] == tk].tolist()
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
                splits[fold] = (splits[fold][0] + train_idx, splits[fold][1] + test_idx)
            else:
                splits.append((train_idx, test_idx))
    return [(np.array(tr), np.array(te)) for tr, te in splits]


def load_base_data(store):
    """Load snapshots + zigzag points (raw, before labeling)."""
    print("  Loading channel snapshots...")
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

    cur.execute("""
        SELECT ticker, timestamp, tp_type
        FROM engine.zigzag_points WHERE min_swing_pct = %s
        ORDER BY ticker, timestamp
    """, (ZZ_THRESHOLD,))
    zz_rows = cur.fetchall()
    zz_df = pd.DataFrame(zz_rows, columns=["ticker", "zz_timestamp", "tp_type"])
    zz_df["zz_timestamp"] = pd.to_datetime(zz_df["zz_timestamp"], utc=True)
    zz_df["zz_date"] = zz_df["zz_timestamp"].dt.tz_localize(None).dt.normalize()
    print(f"  Loaded {len(zz_df):,} zigzag points")

    store._put(conn)
    return df, zz_df


def apply_labels(df_orig, zz_df, proximity):
    """Label snapshots with given proximity."""
    df = df_orig.copy()
    df["is_piso"] = False
    df["is_techo"] = False

    for tk in TICKERS:
        tk_snap = df[df["ticker"] == tk]
        tk_zz = zz_df[zz_df["ticker"] == tk]
        if tk_snap.empty or tk_zz.empty:
            continue

        snap_dates = tk_snap["timestamp"].dt.tz_localize(None).values
        zz_dates = tk_zz["zz_date"].values
        zz_types = tk_zz["tp_type"].values

        for i in range(len(zz_dates)):
            distances = np.abs((snap_dates - zz_dates[i]) / np.timedelta64(1, "D"))
            near = distances <= proximity
            mask_idx = tk_snap.index[near]
            if zz_types[i] == "MIN":
                df.loc[mask_idx, "is_piso"] = True
            elif zz_types[i] == "MAX":
                df.loc[mask_idx, "is_techo"] = True

    return df


def quick_train(df, features, label_col, model_name):
    """Quick PurgedKFold — returns AUC stats without saving."""
    X = df[features].fillna(0.0).values
    y = df[label_col].values.astype(int)
    n_pos = y.sum()
    n_neg = len(y) - n_pos

    params = XGB_PARAMS.copy()
    params["scale_pos_weight"] = n_neg / max(n_pos, 1)

    splits = purged_kfold_split(df)
    fold_aucs = []
    fold_gaps = []

    for train_idx, test_idx in splits:
        train_pos = [df.index.get_loc(i) for i in train_idx if i in df.index]
        test_pos = [df.index.get_loc(i) for i in test_idx if i in df.index]

        X_train, y_train = X[train_pos], y[train_pos]
        X_test, y_test = X[test_pos], y[test_pos]

        model = XGBClassifier(**params)
        model.fit(X_train, y_train, verbose=False)

        y_prob_test = model.predict_proba(X_test)[:, 1]
        y_prob_train = model.predict_proba(X_train)[:, 1]

        if len(np.unique(y_test)) < 2:
            continue

        auc_test = roc_auc_score(y_test, y_prob_test)
        auc_train = roc_auc_score(y_train, y_prob_train)
        fold_aucs.append(auc_test)
        fold_gaps.append(auc_train - auc_test)

    if not fold_aucs:
        return None

    mean_auc = np.mean(fold_aucs)
    std_auc = np.std(fold_aucs)
    dsr = (mean_auc - 0.5) / max(std_auc, 1e-6) * np.sqrt(len(fold_aucs))

    return {
        "mean_auc": mean_auc,
        "std_auc": std_auc,
        "dsr": dsr,
        "mean_gap": np.mean(fold_gaps),
        "n_pos": n_pos,
        "n_neg": n_neg,
        "n_total": len(y),
    }


def full_train_and_save(df, features, label_col, model_name, pkl_name):
    """Full training + threshold calibration + save."""
    X = df[features].fillna(0.0).values
    y = df[label_col].values.astype(int)
    n_pos = y.sum()
    n_neg = len(y) - n_pos

    params = XGB_PARAMS.copy()
    params["scale_pos_weight"] = n_neg / max(n_pos, 1)

    splits = purged_kfold_split(df)
    fold_aucs = []
    fold_gaps = []

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
            continue

        auc_test = roc_auc_score(y_test, y_prob_test)
        auc_train = roc_auc_score(y_train, y_prob_train)
        fold_aucs.append(auc_test)
        fold_gaps.append(auc_train - auc_test)
        print(f"    Fold {fold_idx}: AUC={auc_test:.4f} (gap={auc_train - auc_test:.3f})")

    mean_auc = np.mean(fold_aucs)
    std_auc = np.std(fold_aucs)
    dsr = (mean_auc - 0.5) / max(std_auc, 1e-6) * np.sqrt(len(fold_aucs))

    # Final model on all data
    final_model = XGBClassifier(**params)
    final_model.fit(X, y, verbose=False)

    # Threshold
    y_prob_full = final_model.predict_proba(X)[:, 1]
    precision, recall, thresholds = precision_recall_curve(y, y_prob_full)
    diffs = np.abs(precision[:-1] - recall[:-1])
    best_idx = np.argmin(diffs)
    optimal_threshold = float(thresholds[best_idx])

    # Importance
    importances = final_model.feature_importances_
    sorted_idx = np.argsort(importances)[::-1]
    print(f"    AUC={mean_auc:.4f}±{std_auc:.4f} DSR={dsr:.1f} "
          f"Threshold={optimal_threshold:.4f} P={precision[best_idx]:.3f} R={recall[best_idx]:.3f}")
    print(f"    Features: ", end="")
    for i in sorted_idx:
        print(f"{features[i]}={importances[i]:.3f} ", end="")
    print()

    result = {
        "model": final_model, "feature_cols": features,
        "threshold": optimal_threshold, "mean_auc": mean_auc,
        "std_auc": std_auc, "dsr": dsr, "fold_aucs": fold_aucs,
        "mean_gap": np.mean(fold_gaps),
        "class_balance": {"positive": int(n_pos), "negative": int(n_neg)},
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_samples": len(y),
        "zigzag_version": "canonical_hl_2.5pct",
        "feature_importance": {features[i]: float(importances[i]) for i in range(len(features))},
    }

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    pkl_path = MODELS_DIR / pkl_name
    with open(pkl_path, "wb") as f:
        pickle.dump(result, f)
    print(f"    ✅ Saved: {pkl_path}")

    return result


def main():
    print("=" * 80)
    print("  SENTINEL v2 — PROXIMITY SWEEP + AMBIGUITY EXCLUSION")
    print("=" * 80)

    store = TimescaleDataStore()
    t0 = time.time()

    df_base, zz_df = load_base_data(store)
    store.close()

    # ── SWEEP ──
    configs = []
    for prox in [1, 2, 3]:
        for excl_ambig in [False, True]:
            configs.append((prox, excl_ambig))

    print(f"\n{'=' * 80}")
    print(f"  SWEEP: 6 configurations (proximity × ambiguity exclusion)")
    print(f"{'=' * 80}")
    print(f"\n  {'Config':<20s} │ {'Prox':>4s} {'ExclAmb':>7s} │ "
          f"{'PISO+':>6s} {'TECHO+':>7s} {'Ambig':>6s} {'Ambig%':>6s} │ "
          f"{'AUC_P':>6s} {'AUC_T':>6s} {'Gap_P':>5s} {'Gap_T':>5s}")
    print(f"  {'─' * 95}")

    best_config = None
    best_score = 0

    for prox, excl_ambig in configs:
        label = f"P{prox}_{'noAmb' if excl_ambig else 'withAmb'}"

        df = apply_labels(df_base, zz_df, prox)
        n_piso = df["is_piso"].sum()
        n_techo = df["is_techo"].sum()
        n_ambig = (df["is_piso"] & df["is_techo"]).sum()
        ambig_pct = n_ambig / len(df) * 100

        if excl_ambig:
            ambig_mask = df["is_piso"] & df["is_techo"]
            df = df[~ambig_mask].reset_index(drop=True)
            n_piso = df["is_piso"].sum()
            n_techo = df["is_techo"].sum()

        r_piso = quick_train(df, PISO_FEATURES, "is_piso", f"PISO_{label}")
        r_techo = quick_train(df, TECHO_FEATURES, "is_techo", f"TECHO_{label}")

        if r_piso and r_techo:
            auc_p = r_piso["mean_auc"]
            auc_t = r_techo["mean_auc"]
            combined = (auc_p + auc_t) / 2

            print(f"  {label:<20s} │ {prox:>4d} {'Yes' if excl_ambig else 'No':>7s} │ "
                  f"{n_piso:>6,d} {n_techo:>7,d} {n_ambig:>6,d} {ambig_pct:>5.1f}% │ "
                  f"{auc_p:>6.4f} {auc_t:>6.4f} {r_piso['mean_gap']:>5.3f} {r_techo['mean_gap']:>5.3f}")

            if combined > best_score:
                best_score = combined
                best_config = (prox, excl_ambig, label)

    print(f"\n  🏆 Best: {best_config[2]} (combined AUC={best_score:.4f})")

    # ── FULL TRAINING with best config ──
    prox, excl_ambig, label = best_config
    print(f"\n{'=' * 80}")
    print(f"  FULL TRAINING — {label}")
    print(f"{'=' * 80}")

    df = apply_labels(df_base, zz_df, prox)
    if excl_ambig:
        ambig_mask = df["is_piso"] & df["is_techo"]
        df = df[~ambig_mask].reset_index(drop=True)

    n_piso = df["is_piso"].sum()
    n_techo = df["is_techo"].sum()
    print(f"  Labels: {n_piso:,} PISO, {n_techo:,} TECHO, {len(df):,} total")

    print(f"\n  ── PISO ──")
    piso = full_train_and_save(df, PISO_FEATURES, "is_piso", "PISO_v2", "sentinel_piso_v2.pkl")

    print(f"\n  ── TECHO ──")
    techo = full_train_and_save(df, TECHO_FEATURES, "is_techo", "TECHO_v2", "sentinel_techo_v2.pkl")

    # ── COMPARISON ──
    elapsed = time.time() - t0
    print(f"\n{'=' * 80}")
    print(f"  FINAL COMPARISON — v1 vs v2")
    print(f"{'=' * 80}")
    print(f"  {'Model':<20s} {'AUC':>7s} {'± std':>7s} {'DSR':>7s} {'Gap':>6s} {'Thresh':>8s} {'Pos':>8s} {'Config'}")
    print(f"  {'─'*80}")

    if piso:
        print(f"  {'PISO_v2':<20s} {piso['mean_auc']:>7.4f} {piso['std_auc']:>7.4f} "
              f"{piso['dsr']:>7.1f} {piso['mean_gap']:>6.3f} {piso['threshold']:>8.4f} "
              f"{piso['class_balance']['positive']:>8,} {label}")
    if techo:
        print(f"  {'TECHO_v2':<20s} {techo['mean_auc']:>7.4f} {techo['std_auc']:>7.4f} "
              f"{techo['dsr']:>7.1f} {techo['mean_gap']:>6.3f} {techo['threshold']:>8.4f} "
              f"{techo['class_balance']['positive']:>8,} {label}")

    for v1_name in ["piso", "techo"]:
        v1_path = MODELS_DIR / f"sentinel_{v1_name}_v1.pkl"
        if v1_path.exists():
            with open(v1_path, "rb") as f:
                v1 = pickle.load(f)
            gap = v1.get('mean_gap', 0)
            print(f"  {v1_name.upper()+'_v1 (old)':<20s} {v1['mean_auc']:>7.4f} {v1['std_auc']:>7.4f} "
                  f"{v1['dsr']:>7.1f} {gap:>6.3f} {v1['threshold']:>8.4f} "
                  f"{v1['class_balance']['positive']:>8,} close_3/5/7%")

    print(f"\n  Time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
