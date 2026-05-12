"""
hyperparameter_sweep.py — Optuna-free Grid Search for Meta-Model
================================================================
Tests key hyperparameter combinations to maximize OOS Sharpe lift
while penalizing folds with 0 trades.

Focus on the parameters that matter most:
  - min_child_weight: Controls leaf size (100 may be too restrictive)
  - max_depth: 2-4 range (currently 3)
  - learning_rate: 0.01-0.1 range (currently 0.05)
  - gamma: 0.1-2.0 (currently 1.0)
  - threshold: probability cutoff (currently 0.5)

Usage:
    source backend/.venv/bin/activate && python backend/scripts/hyperparameter_sweep.py
"""
import sys
import json
import logging
from pathlib import Path
from itertools import product

import numpy as np
import pandas as pd
import xgboost as xgb
from scipy import stats

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("HyperSweep")

_root = Path("/root/botero-trade")
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "backend" / "scripts"))

from dotenv import load_dotenv
load_dotenv(_root / ".env")

from train_meta_model import (
    load_ml_data, create_meta_labels,
    compute_sample_weights, purged_walk_forward_cv,
    get_feature_columns, _annualized_sharpe, _tf_to_minutes,
)


def evaluate_config(df, feature_cols, X, y, weights, folds, tf_minutes, config):
    """Train + evaluate a single hyperparameter config across all folds."""
    xgb_params = {
        "objective": "binary:logistic",
        "eval_metric": "logloss",
        "max_depth": config["max_depth"],
        "learning_rate": config["learning_rate"],
        "n_estimators": 500,
        "subsample": 0.8,
        "colsample_bytree": 0.7,
        "min_child_weight": config["min_child_weight"],
        "gamma": config["gamma"],
        "reg_alpha": config.get("reg_alpha", 0.5),
        "reg_lambda": config.get("reg_lambda", 2.0),
        "scale_pos_weight": (y == 0).sum() / max((y == 1).sum(), 1),
        "random_state": 42,
        "verbosity": 0,
        "early_stopping_rounds": 20,
    }
    threshold = config.get("threshold", 0.5)

    all_filtered_rets = []
    all_filtered_bars = []
    all_rets = []
    all_bars = []
    folds_with_trades = 0
    fold_lifts = []

    for fold in folds:
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

        proba = model.predict_proba(X[fold.test_idx])[:, 1]
        filtered_mask = proba > threshold

        test_returns = df.iloc[fold.test_idx]["return_pct"].values
        test_bars = df.iloc[fold.test_idx]["bars_held"].values

        all_rets.extend(test_returns)
        all_bars.extend(test_bars)

        if filtered_mask.sum() > 0:
            folds_with_trades += 1
            all_filtered_rets.extend(test_returns[filtered_mask])
            all_filtered_bars.extend(test_bars[filtered_mask])

        sr_f = _annualized_sharpe(
            test_returns[filtered_mask], test_bars[filtered_mask], tf_minutes
        ) if filtered_mask.sum() > 0 else 0.0
        sr_b = _annualized_sharpe(test_returns, test_bars, tf_minutes)
        fold_lifts.append(sr_f - sr_b)

    all_rets = np.array(all_rets)
    all_bars = np.array(all_bars)
    all_filtered_rets = np.array(all_filtered_rets)
    all_filtered_bars = np.array(all_filtered_bars)

    baseline = _annualized_sharpe(all_rets, all_bars, tf_minutes)
    filtered = _annualized_sharpe(all_filtered_rets, all_filtered_bars, tf_minutes)
    lift = filtered - baseline

    return {
        "sharpe_lift": lift,
        "sharpe_filtered": filtered,
        "sharpe_baseline": baseline,
        "n_trades": len(all_filtered_rets),
        "n_total": len(all_rets),
        "filter_rate": len(all_filtered_rets) / len(all_rets) * 100,
        "folds_with_trades": folds_with_trades,
        "folds_total": len(folds),
        "mean_fold_lift": float(np.mean(fold_lifts)),
        "min_fold_lift": float(min(fold_lifts)),
    }


def main():
    logger.info("=" * 60)
    logger.info("HYPERPARAMETER SWEEP — Meta-Model Optimization")
    logger.info("=" * 60)

    df = load_ml_data("1d")
    feature_cols = get_feature_columns(df)
    tf_minutes = _tf_to_minutes(df["timeframe"].iloc[0])

    X = df[feature_cols].values.astype(np.float32)
    meta_y = create_meta_labels(df)
    y = meta_y.values
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    weights = compute_sample_weights(df)

    n_folds = 5
    folds = purged_walk_forward_cv(df, n_folds=n_folds, embargo_pct=0.01)

    # Grid: focus on the parameters that fix 0-trade folds
    grid = {
        "min_child_weight": [30, 50, 100],       # Current: 100 (too restrictive?)
        "max_depth":        [3, 4],               # Current: 3
        "learning_rate":    [0.03, 0.05],         # Current: 0.05
        "gamma":            [0.3, 0.5, 1.0],      # Current: 1.0 (too aggressive?)
        "threshold":        [0.45, 0.50, 0.55],   # Current: 0.5
    }

    keys = sorted(grid.keys())
    combos = list(product(*(grid[k] for k in keys)))
    logger.info(f"Testing {len(combos)} configurations...")

    results = []
    best_lift = -999
    best_config = None

    for i, combo in enumerate(combos):
        config = dict(zip(keys, combo))

        try:
            r = evaluate_config(df, feature_cols, X, y, weights, folds, tf_minutes, config)
        except Exception as e:
            logger.warning(f"  Config {i+1} failed: {e}")
            continue

        # Penalty: if any fold has 0 trades, penalize the score
        penalty = 0.0
        if r["folds_with_trades"] < r["folds_total"]:
            penalty = 0.2 * (r["folds_total"] - r["folds_with_trades"])

        score = r["sharpe_lift"] - penalty

        results.append({**config, **r, "score": score})

        if score > best_lift:
            best_lift = score
            best_config = {**config, **r, "score": score}

        if (i + 1) % 10 == 0 or i == 0:
            logger.info(
                f"  [{i+1}/{len(combos)}] depth={config['max_depth']} "
                f"mcw={config['min_child_weight']} γ={config['gamma']:.1f} "
                f"lr={config['learning_rate']} thr={config['threshold']} "
                f"→ lift={r['sharpe_lift']:+.3f} trades={r['n_trades']} "
                f"folds_active={r['folds_with_trades']}/{r['folds_total']} "
                f"score={score:+.3f}"
            )

    # Sort by score
    results.sort(key=lambda x: x["score"], reverse=True)

    logger.info("\n" + "=" * 60)
    logger.info("TOP 5 CONFIGURATIONS")
    logger.info("=" * 60)
    for i, r in enumerate(results[:5]):
        logger.info(
            f"  #{i+1}: depth={r['max_depth']} mcw={r['min_child_weight']} "
            f"γ={r['gamma']:.1f} lr={r['learning_rate']} thr={r['threshold']} "
            f"→ lift={r['sharpe_lift']:+.3f} filtered={r['sharpe_filtered']:.3f} "
            f"trades={r['n_trades']}/{r['n_total']} "
            f"folds={r['folds_with_trades']}/{r['folds_total']} "
            f"score={r['score']:+.3f}"
        )

    logger.info("\n" + "=" * 60)
    logger.info("CURRENT CONFIG vs BEST CONFIG")
    logger.info("=" * 60)

    # Find current config result
    current = next(
        (r for r in results
         if r["max_depth"] == 3 and r["min_child_weight"] == 100
         and r["gamma"] == 1.0 and r["learning_rate"] == 0.05
         and r["threshold"] == 0.50),
        None
    )
    if current:
        logger.info(f"  CURRENT: lift={current['sharpe_lift']:+.3f} "
                    f"filtered={current['sharpe_filtered']:.3f} "
                    f"trades={current['n_trades']} "
                    f"folds={current['folds_with_trades']}/{current['folds_total']}")

    best = results[0]
    logger.info(f"  BEST:    lift={best['sharpe_lift']:+.3f} "
                f"filtered={best['sharpe_filtered']:.3f} "
                f"trades={best['n_trades']} "
                f"folds={best['folds_with_trades']}/{best['folds_total']}")
    if current:
        logger.info(f"  IMPROVEMENT: {best['sharpe_lift'] - current['sharpe_lift']:+.3f} Sharpe lift")

    # Save results
    out_path = _root / "backend" / "scripts" / "hyperparam_sweep_results.json"
    with open(out_path, "w") as f:
        json.dump({"top_5": results[:5], "best": best, "current": current}, f, indent=2, default=str)
    logger.info(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
