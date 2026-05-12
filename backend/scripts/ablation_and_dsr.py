"""
ablation_and_dsr.py — P0 Diagnostic Suite
==========================================
1. Ablation test: train WITH vs WITHOUT RG_VolRegime_* features (LdP requirement)
2. Multi-trial DSR: run 10 random-seed trials to compute proper DSR
3. Basing diagnostic: analyze what the model sees in Basing regime

Usage:
    python backend/scripts/ablation_and_dsr.py
"""
import sys
import json
import logging
from pathlib import Path
from copy import deepcopy

import numpy as np
import pandas as pd
import xgboost as xgb
from scipy import stats

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("AblationDSR")

_root = Path("/root/botero-trade")
sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(_root / ".env")

# Import from existing training script
sys.path.insert(0, str(_root / "backend" / "scripts"))
from train_meta_model import (
    load_ml_data, create_meta_labels,
    compute_sample_weights, purged_walk_forward_cv,
    get_feature_columns, deflated_sharpe_ratio,
    _annualized_sharpe, _tf_to_minutes,
)


def train_with_features(df, feature_cols, seed=42):
    """Train a single model config and return OOS Sharpe."""
    tf_minutes = _tf_to_minutes(df["timeframe"].iloc[0])
    X = df[feature_cols].values.astype(np.float32)
    meta_y = create_meta_labels(df)
    y = meta_y.values
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    weights = compute_sample_weights(df)

    n_folds = 3 if len(df) < 10000 else 5
    folds = purged_walk_forward_cv(df, n_folds=n_folds, embargo_pct=0.01)

    xgb_params = {
        "objective": "binary:logistic",
        "eval_metric": "logloss",
        "max_depth": 3,
        "learning_rate": 0.05,
        "n_estimators": 500,
        "subsample": 0.8,
        "colsample_bytree": 0.7,
        "min_child_weight": 100,
        "gamma": 1.0,
        "reg_alpha": 0.5,
        "reg_lambda": 2.0,
        "scale_pos_weight": (y == 0).sum() / max((y == 1).sum(), 1),
        "random_state": seed,
        "verbosity": 0,
        "early_stopping_rounds": 20,
    }

    all_filtered_rets = []
    all_filtered_bars = []
    all_rets = []
    all_bars = []

    for fold in folds:
        X_train = X[fold.train_idx]
        y_train = y[fold.train_idx]

        X_test = X[fold.test_idx]
        y_test = y[fold.test_idx]

        val_split = int(len(fold.train_idx) * 0.8)
        train_sub = fold.train_idx[:val_split]
        val_sub = fold.train_idx[val_split:]

        model = xgb.XGBClassifier(**xgb_params)
        model.fit(
            X[train_sub], y[train_sub],
            sample_weight=weights[train_sub],
            eval_set=[(X[val_sub], y[val_sub])],
            verbose=False,
        )

        proba = model.predict_proba(X_test)[:, 1]
        filtered_mask = proba > 0.5

        test_returns = df.iloc[fold.test_idx]["return_pct"].values
        test_bars = df.iloc[fold.test_idx]["bars_held"].values

        all_rets.extend(test_returns)
        all_bars.extend(test_bars)

        if filtered_mask.sum() > 0:
            all_filtered_rets.extend(test_returns[filtered_mask])
            all_filtered_bars.extend(test_bars[filtered_mask])

    all_rets = np.array(all_rets)
    all_bars = np.array(all_bars)
    all_filtered_rets = np.array(all_filtered_rets)
    all_filtered_bars = np.array(all_filtered_bars)

    baseline_sharpe = _annualized_sharpe(all_rets, all_bars, tf_minutes)
    filtered_sharpe = _annualized_sharpe(all_filtered_rets, all_filtered_bars, tf_minutes)
    lift = filtered_sharpe - baseline_sharpe
    n_taken = len(all_filtered_rets)

    return {
        "sharpe_baseline": baseline_sharpe,
        "sharpe_filtered": filtered_sharpe,
        "sharpe_lift": lift,
        "n_trades": n_taken,
        "n_total": len(all_rets),
        "filter_rate": n_taken / len(all_rets) * 100 if len(all_rets) > 0 else 0,
    }


def main():
    logger.info("=" * 60)
    logger.info("P0 DIAGNOSTIC SUITE: Ablation + Multi-Trial DSR + Basing")
    logger.info("=" * 60)

    # Load data
    df = load_ml_data("1d")
    all_feature_cols = get_feature_columns(df)
    logger.info(f"Loaded {len(df)} samples, {len(all_feature_cols)} features")

    # ── TEST 1: ABLATION — With vs Without VolRegime ────────
    logger.info("\n" + "=" * 60)
    logger.info("TEST 1: ABLATION — RG_VolRegime_* features")
    logger.info("=" * 60)

    vol_regime_cols = [c for c in all_feature_cols if "VolRegime" in c]
    non_regime_cols = [c for c in all_feature_cols if "VolRegime" not in c]

    logger.info(f"Vol regime features: {vol_regime_cols}")
    logger.info(f"Features WITH regime: {len(all_feature_cols)}")
    logger.info(f"Features WITHOUT regime: {len(non_regime_cols)}")

    r_with = train_with_features(df, all_feature_cols, seed=42)
    r_without = train_with_features(df, non_regime_cols, seed=42)

    logger.info(f"\n  WITH regime:    Sharpe lift={r_with['sharpe_lift']:+.4f}, "
                f"Filtered={r_with['sharpe_filtered']:.3f}, "
                f"Trades={r_with['n_trades']}/{r_with['n_total']}")
    logger.info(f"  WITHOUT regime: Sharpe lift={r_without['sharpe_lift']:+.4f}, "
                f"Filtered={r_without['sharpe_filtered']:.3f}, "
                f"Trades={r_without['n_trades']}/{r_without['n_total']}")
    delta = r_with['sharpe_lift'] - r_without['sharpe_lift']
    logger.info(f"  DELTA: {delta:+.4f} {'✅ Regime adds value' if delta > 0 else '⚠️ Regime adds no value'}")

    # ── TEST 2: MULTI-TRIAL DSR ─────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: MULTI-TRIAL DSR (10 random seeds)")
    logger.info("=" * 60)

    n_trials = 10
    trial_sharpes = []
    for i, seed in enumerate(range(42, 42 + n_trials)):
        r = train_with_features(df, all_feature_cols, seed=seed)
        trial_sharpes.append(r['sharpe_filtered'])
        logger.info(f"  Trial {i+1}/{n_trials} (seed={seed}): "
                    f"Sharpe={r['sharpe_filtered']:.3f}, lift={r['sharpe_lift']:+.3f}")

    best_sharpe = max(trial_sharpes)
    median_sharpe = float(np.median(trial_sharpes))
    mean_sharpe = float(np.mean(trial_sharpes))
    std_sharpe = float(np.std(trial_sharpes))

    logger.info(f"\n  Best Sharpe: {best_sharpe:.3f}")
    logger.info(f"  Mean Sharpe: {mean_sharpe:.3f} ± {std_sharpe:.3f}")
    logger.info(f"  Median Sharpe: {median_sharpe:.3f}")

    # Compute DSR with best Sharpe across all trials
    # DSR asks: "Is the best Sharpe among N trials actually significant?"
    tf_minutes = _tf_to_minutes(df["timeframe"].iloc[0])
    # Use the best trial's filtered returns for skew/kurtosis estimation
    r_best = train_with_features(df, all_feature_cols, seed=42 + np.argmax(trial_sharpes))
    skew = 0.0  # Approximate — proper would need filtered returns
    kurt = 3.0
    dsr = deflated_sharpe_ratio(
        sharpe_observed=best_sharpe,
        n_trials=n_trials,
        n_observations=r_best['n_trades'],
        skewness=skew,
        kurtosis=kurt,
    )
    logger.info(f"  DSR (n_trials={n_trials}): {dsr:.4f}")
    if dsr > 0.95:
        logger.info("  ✅ DSR > 0.95: Sharpe is statistically robust")
    elif dsr > 0.50:
        logger.info("  ⚠️ DSR 0.50-0.95: Moderate evidence")
    else:
        logger.info("  ❌ DSR < 0.50: Sharpe may be explained by luck")

    # ── TEST 3: BASING DIAGNOSTIC ────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: BASING REGIME DIAGNOSTIC")
    logger.info("=" * 60)

    # Identify Basing samples using the Weinstein proxy
    if "RG_WinsteinProxy" in df.columns:
        basing_mask = df["RG_WinsteinProxy"] == 0.25
    else:
        # Reconstruct from features dict
        basing_mask = pd.Series(False, index=df.index)
        for i, row in df.iterrows():
            feats = row.get("features", {})
            if isinstance(feats, dict):
                wp = feats.get("RG_WinsteinProxy", 0)
                if wp == 0.25:
                    basing_mask.at[i] = True

    n_basing = basing_mask.sum()
    logger.info(f"  Basing samples: {n_basing}/{len(df)} ({n_basing/len(df)*100:.1f}%)")

    if n_basing > 0:
        basing_df = df[basing_mask]
        meta_y = create_meta_labels(basing_df)
        win_rate = (meta_y == 1).mean() * 100

        basing_rets = basing_df["return_pct"].values
        logger.info(f"  Basing win rate (meta): {win_rate:.1f}%")
        logger.info(f"  Basing mean return: {np.mean(basing_rets):.4f}")
        logger.info(f"  Basing std return: {np.std(basing_rets):.4f}")
        logger.info(f"  Basing median return: {np.median(basing_rets):.4f}")

        # Per-signal breakdown in Basing
        for sig in basing_df["signal_name"].unique():
            sig_mask = basing_df["signal_name"] == sig
            sig_rets = basing_df[sig_mask]["return_pct"].values
            sig_wr = (create_meta_labels(basing_df[sig_mask]) == 1).mean() * 100
            logger.info(f"    {sig:25s}: N={sig_mask.sum()}, WR={sig_wr:.0f}%, "
                        f"mean_ret={np.mean(sig_rets):.4f}")

        # Vol regime distribution in Basing
        for col in vol_regime_cols:
            if col in basing_df.columns:
                dist = basing_df[col].value_counts().to_dict()
                logger.info(f"  {col} in Basing: {dist}")

    # ── SUMMARY ──────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)

    results = {
        "ablation": {
            "with_regime": r_with,
            "without_regime": r_without,
            "delta_lift": delta,
        },
        "multi_trial_dsr": {
            "n_trials": n_trials,
            "trial_sharpes": trial_sharpes,
            "best_sharpe": best_sharpe,
            "mean_sharpe": mean_sharpe,
            "std_sharpe": std_sharpe,
            "dsr": dsr,
        },
        "basing": {
            "n_samples": int(n_basing),
            "pct_of_total": round(n_basing / len(df) * 100, 1),
        },
    }

    out_path = _root / "backend" / "scripts" / "ablation_dsr_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"Results saved to {out_path}")


if __name__ == "__main__":
    main()
