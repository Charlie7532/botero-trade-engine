"""
train_meta_model.py — XGBoost Meta-Labeling with Purged Walk-Forward CV
==========================================================================
López de Prado institutional-grade training pipeline:
  1. Load VAEP-corrected features + labels from Neon ML Data Lake
  2. Convert ternary labels {-1, 0, 1} to binary meta-labels {0, 1}
  3. Compute sample weights by Average Uniqueness
  4. Train XGBoost with Purged Walk-Forward Anchored CV
  5. Evaluate with Deflated Sharpe Ratio (DSR)
  6. Report: per-signal, per-regime, IS vs OOS metrics

Usage:
    python backend/scripts/train_meta_model.py
"""
import sys
import json
import logging
from pathlib import Path
from dataclasses import dataclass

import numpy as np
import pandas as pd
import xgboost as xgb
from scipy import stats
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score,
    f1_score, roc_auc_score, log_loss,
)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("MetaModelTrainer")

_root = Path("/root/botero-trade")
sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(_root / ".env")


# ══════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════

def load_ml_data() -> pd.DataFrame:
    """Load features + labels from Neon ML Data Lake into a single DataFrame."""
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    store = TimescaleDataStore()
    conn = store._conn()

    query = """
        SELECT
            f.id, f.ticker, f.timeframe, f.signal_name,
            f.signal_time, f.features,
            l.label, l.return_pct, l.bars_held, l.exit_time,
            l.geometry_used
        FROM engine.ml_features f
        JOIN engine.ml_labels l ON f.id = l.feature_id
        ORDER BY f.signal_time
    """
    df = pd.read_sql(query, store.engine)
    store.close()

    # Parse JSON features into columns
    feat_dicts = df["features"].apply(
        lambda x: json.loads(x) if isinstance(x, str) else x
    )
    feat_df = pd.DataFrame(feat_dicts.tolist(), index=df.index)
    df = pd.concat([df.drop(columns=["features"]), feat_df], axis=1)

    # Parse signal_time
    df["signal_time"] = pd.to_datetime(df["signal_time"])
    df["exit_time"] = pd.to_datetime(df["exit_time"], errors="coerce")

    logger.info(
        f"Loaded {len(df)} samples, {len(feat_df.columns)} features, "
        f"{df['signal_name'].nunique()} signals, {df['ticker'].nunique()} tickers"
    )
    return df


# ══════════════════════════════════════════════════════════════
# META-LABELING (LdP Ch. 3)
# ══════════════════════════════════════════════════════════════

def create_meta_labels(df: pd.DataFrame) -> pd.Series:
    """
    Convert ternary labels {-1, 0, 1} to binary meta-labels {0, 1}.

    Meta-label = 1: The primary signal was CORRECT (profit barrier hit).
    Meta-label = 0: The primary signal was WRONG (loss or time exit).

    The meta-model doesn't predict direction — it predicts whether
    the primary model's prediction will succeed.
    """
    meta_y = (df["label"] == 1).astype(int)
    logger.info(
        f"Meta-labels: {meta_y.sum()} positive ({meta_y.mean()*100:.1f}%), "
        f"{(~meta_y.astype(bool)).sum()} negative ({(1-meta_y.mean())*100:.1f}%)"
    )
    return meta_y


# ══════════════════════════════════════════════════════════════
# SAMPLE WEIGHTS — Average Uniqueness (LdP Ch. 4)
# ══════════════════════════════════════════════════════════════

def compute_sample_weights(df: pd.DataFrame) -> np.ndarray:
    """
    Compute sample weights based on Average Uniqueness.

    For each sample i with lifespan [entry_time, exit_time], compute:
        ū_i = (1 / |L_i|) × Σ_{t ∈ L_i} (1 / c_t)
    where c_t = number of concurrent labels at timestamp t.

    Samples with higher uniqueness (less overlap) get higher weight.
    """
    entry = df["signal_time"].values.astype("datetime64[ns]")
    exit_ = df["exit_time"].values.astype("datetime64[ns]")

    n = len(df)
    # For samples without exit_time, use entry_time (instantaneous)
    mask = pd.isna(exit_)
    exit_[mask] = entry[mask]

    # Build concurrency count at each sample's midpoint
    weights = np.ones(n, dtype=float)

    # Efficient overlap computation using sorted events
    # For each sample, count how many other samples overlap with it
    for i in range(n):
        overlap_count = 0
        for j in range(max(0, i - 500), min(n, i + 500)):  # Local window for speed
            if j == i:
                continue
            # Check temporal overlap: [entry_i, exit_i] ∩ [entry_j, exit_j]
            if entry[j] <= exit_[i] and exit_[j] >= entry[i]:
                overlap_count += 1

        # Average uniqueness: 1 / (1 + concurrent_count)
        weights[i] = 1.0 / (1.0 + overlap_count)

    # Normalize to mean=1
    weights = weights / weights.mean()

    logger.info(
        f"Sample weights: min={weights.min():.3f}, max={weights.max():.3f}, "
        f"mean={weights.mean():.3f}, std={weights.std():.3f}"
    )
    return weights


# ══════════════════════════════════════════════════════════════
# PURGED WALK-FORWARD CV (LdP Ch. 7)
# ══════════════════════════════════════════════════════════════

@dataclass
class CVFold:
    """A single cross-validation fold with purge and embargo."""
    fold_id: int
    train_idx: np.ndarray
    test_idx: np.ndarray
    n_purged: int
    n_embargoed: int


def purged_walk_forward_cv(
    df: pd.DataFrame,
    n_folds: int = 5,
    embargo_pct: float = 0.01,
    min_train_size: int = 2000,
) -> list[CVFold]:
    """
    Purged Walk-Forward Anchored Cross-Validation.

    Properties:
        1. ANCHORED: Train always starts at bar 0 (growing window).
        2. PURGED: Remove train samples whose [entry, exit] overlaps with test.
        3. EMBARGOED: Additional buffer after each test fold excluded from train.
        4. TEMPORAL: Test always comes AFTER train chronologically.

    Args:
        df: DataFrame sorted by signal_time with entry/exit timestamps.
        n_folds: Number of walk-forward folds.
        embargo_pct: Fraction of total samples to embargo after test.
        min_train_size: Minimum training samples per fold.
    """
    n = len(df)
    embargo_size = max(1, int(n * embargo_pct))

    # Calculate fold boundaries
    test_size = max(200, (n - min_train_size) // n_folds)
    folds = []

    entry = df["signal_time"].values.astype("datetime64[ns]")
    exit_ = df["exit_time"].values.astype("datetime64[ns]")
    # Fill NaN exit times
    exit_mask = pd.isna(exit_)
    exit_[exit_mask] = entry[exit_mask]

    for fold_id in range(n_folds):
        # Test window (slides forward)
        test_start = min_train_size + fold_id * test_size
        test_end = min(test_start + test_size, n)

        if test_start >= n or test_end <= test_start:
            break

        test_idx = np.arange(test_start, test_end)

        # Train window (anchored at 0, grows)
        train_end = test_start
        train_candidates = np.arange(0, train_end)

        # ── PURGING ──────────────────────────────────────────
        # Remove train samples whose lifespan overlaps with ANY test sample
        test_entry_min = entry[test_start]
        test_exit_max = exit_[test_end - 1]

        purge_mask = np.ones(len(train_candidates), dtype=bool)
        n_purged = 0
        for ti, tidx in enumerate(train_candidates):
            # Overlap: train[exit] >= test[first_entry] AND train[entry] <= test[last_exit]
            if exit_[tidx] >= test_entry_min:
                purge_mask[ti] = False
                n_purged += 1

        train_idx = train_candidates[purge_mask]

        # ── EMBARGO ──────────────────────────────────────────
        # Also remove `embargo_size` samples right before the test window
        n_embargoed = 0
        if len(train_idx) > 0 and embargo_size > 0:
            embargo_cutoff = test_start - embargo_size
            embargo_mask = train_idx < embargo_cutoff
            n_embargoed = len(train_idx) - embargo_mask.sum()
            train_idx = train_idx[embargo_mask]

        if len(train_idx) < min_train_size // 2:
            logger.warning(
                f"Fold {fold_id}: Only {len(train_idx)} train samples after purge "
                f"(purged={n_purged}, embargoed={n_embargoed}). Skipping."
            )
            continue

        folds.append(CVFold(
            fold_id=fold_id,
            train_idx=train_idx,
            test_idx=test_idx,
            n_purged=n_purged,
            n_embargoed=n_embargoed,
        ))

        logger.info(
            f"Fold {fold_id}: train={len(train_idx)} "
            f"[0→{train_idx[-1]}], test={len(test_idx)} "
            f"[{test_start}→{test_end-1}], "
            f"purged={n_purged}, embargoed={n_embargoed}"
        )

    return folds


# ══════════════════════════════════════════════════════════════
# DEFLATED SHARPE RATIO (Bailey & LdP, 2014)
# ══════════════════════════════════════════════════════════════

def deflated_sharpe_ratio(
    sharpe_observed: float,
    n_trials: int,
    n_observations: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """
    Compute DSR: probability that observed Sharpe is real (not luck).

    Accounts for multiple testing bias: trying N strategies and reporting
    the best one inflates apparent Sharpe.

    Args:
        sharpe_observed: The best Sharpe ratio found.
        n_trials: Number of strategies/configs tested.
        n_observations: Number of return observations.
        skewness: Return series skewness.
        kurtosis: Return series kurtosis (excess=0 for normal).

    Returns:
        DSR ∈ [0, 1]. Values > 0.95 indicate robust Sharpe.
    """
    if n_trials <= 1 or n_observations <= 1:
        return 0.0

    # Expected max Sharpe under null (Euler-Mascheroni correction)
    euler = 0.5772156649
    sharpe_star = np.sqrt(2 * np.log(n_trials)) * (
        1 - euler / (2 * np.log(n_trials))
    ) + euler / np.sqrt(2 * np.log(n_trials))

    # Variance of Sharpe estimator (non-normal adjustment)
    var_sr = (
        1.0 / n_observations
        * (1 - skewness * sharpe_observed + (kurtosis - 1) / 4 * sharpe_observed**2)
    )

    if var_sr <= 0:
        return 0.0

    # DSR = P(SR > SR*)
    z = (sharpe_observed - sharpe_star) / np.sqrt(var_sr)
    dsr = float(stats.norm.cdf(z))

    return round(dsr, 4)


# ══════════════════════════════════════════════════════════════
# TRAINING PIPELINE
# ══════════════════════════════════════════════════════════════

def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Extract ML feature columns (prefixed families)."""
    prefixes = ('FD_', 'MS_', 'TS_', 'CS_', 'VF_', 'MC_', 'OV_', 'CAL_', 'IM_', 'RG_')
    return [c for c in df.columns if c.startswith(prefixes)]


def train_and_evaluate(df: pd.DataFrame) -> dict:
    """
    Full training pipeline with institutional-grade validation.

    Returns a results dict with per-fold and aggregate metrics.
    """
    feature_cols = get_feature_columns(df)
    logger.info(f"Feature columns ({len(feature_cols)}): {feature_cols}")

    X = df[feature_cols].values.astype(np.float32)
    meta_y = create_meta_labels(df)
    y = meta_y.values

    # Replace any remaining NaN/inf
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    # ── SAMPLE WEIGHTS ───────────────────────────────────────
    logger.info("Computing sample weights (Average Uniqueness)...")
    weights = compute_sample_weights(df)

    # ── PURGED WALK-FORWARD CV ───────────────────────────────
    logger.info("Generating Purged Walk-Forward folds...")
    folds = purged_walk_forward_cv(df, n_folds=5, embargo_pct=0.01)

    if not folds:
        logger.error("No valid CV folds generated. Insufficient data.")
        return {}

    # ── XGBoost params (conservative, anti-overfit) ──────────
    xgb_params = {
        "objective": "binary:logistic",
        "eval_metric": "logloss",
        "max_depth": 4,          # Shallow trees (anti-overfit)
        "learning_rate": 0.05,   # Slow learning
        "n_estimators": 300,
        "subsample": 0.8,
        "colsample_bytree": 0.7,
        "min_child_weight": 50,  # Require 50 samples per leaf
        "gamma": 1.0,            # Pruning threshold
        "reg_alpha": 0.5,        # L1 regularization
        "reg_lambda": 2.0,       # L2 regularization
        "scale_pos_weight": (y == 0).sum() / max((y == 1).sum(), 1),
        "random_state": 42,
        "verbosity": 0,
    }

    # ── PER-FOLD TRAINING + EVALUATION ───────────────────────
    all_oos_results = []
    fold_metrics = []
    feature_importances = np.zeros(len(feature_cols))

    for fold in folds:
        logger.info(f"\n{'─'*50}")
        logger.info(f"FOLD {fold.fold_id}")
        logger.info(f"{'─'*50}")

        X_train = X[fold.train_idx]
        y_train = y[fold.train_idx]
        w_train = weights[fold.train_idx]

        X_test = X[fold.test_idx]
        y_test = y[fold.test_idx]

        model = xgb.XGBClassifier(**xgb_params)
        model.fit(
            X_train, y_train,
            sample_weight=w_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )

        # Predictions
        y_pred_proba = model.predict_proba(X_test)[:, 1]
        y_pred = (y_pred_proba >= 0.5).astype(int)

        # Metrics
        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, zero_division=0)
        rec = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        try:
            auc = roc_auc_score(y_test, y_pred_proba)
        except ValueError:
            auc = 0.5
        ll = log_loss(y_test, y_pred_proba)

        # Sharpe of meta-model filtered trades
        # If meta-model says "take the trade", what's the return?
        test_returns = df.iloc[fold.test_idx]["return_pct"].values
        filtered_returns = test_returns[y_pred == 1]
        if len(filtered_returns) > 1:
            sr = (filtered_returns.mean() / filtered_returns.std()) * np.sqrt(252 / 15)
        else:
            sr = 0.0

        # Unfiltered baseline
        if len(test_returns) > 1:
            sr_baseline = (test_returns.mean() / test_returns.std()) * np.sqrt(252 / 15)
        else:
            sr_baseline = 0.0

        fold_result = {
            "fold": fold.fold_id,
            "n_train": len(fold.train_idx),
            "n_test": len(fold.test_idx),
            "n_purged": fold.n_purged,
            "accuracy": round(acc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "auc": round(auc, 4),
            "logloss": round(ll, 4),
            "sharpe_filtered": round(sr, 4),
            "sharpe_baseline": round(sr_baseline, 4),
            "sharpe_lift": round(sr - sr_baseline, 4),
            "trades_taken": int(y_pred.sum()),
            "trades_total": len(y_test),
            "filter_rate": round(y_pred.sum() / len(y_test) * 100, 1),
        }
        fold_metrics.append(fold_result)

        logger.info(
            f"  Acc={acc:.3f} Prec={prec:.3f} Rec={rec:.3f} AUC={auc:.3f}\n"
            f"  Sharpe: baseline={sr_baseline:.3f} → filtered={sr:.3f} "
            f"(lift={sr - sr_baseline:+.3f})\n"
            f"  Trades: {y_pred.sum()}/{len(y_test)} taken ({fold_result['filter_rate']:.0f}%)"
        )

        # Accumulate feature importance (gain-based)
        importances = model.feature_importances_
        feature_importances += importances

        # Store OOS predictions for aggregate analysis
        for i, idx in enumerate(fold.test_idx):
            all_oos_results.append({
                "idx": idx,
                "y_true": y_test[i],
                "y_pred": y_pred[i],
                "y_proba": y_pred_proba[i],
                "return_pct": test_returns[i],
                "signal_name": df.iloc[idx]["signal_name"],
                "ticker": df.iloc[idx]["ticker"],
                "regime": df.iloc[idx].get("RG_WinsteinProxy", 0),
            })

    # ══════════════════════════════════════════════════════════
    # AGGREGATE OOS METRICS
    # ══════════════════════════════════════════════════════════

    oos_df = pd.DataFrame(all_oos_results)
    logger.info(f"\n{'='*60}")
    logger.info("AGGREGATE OOS RESULTS")
    logger.info(f"{'='*60}")

    # Overall OOS accuracy
    overall_acc = accuracy_score(oos_df["y_true"], oos_df["y_pred"])
    overall_auc = roc_auc_score(oos_df["y_true"], oos_df["y_proba"])
    logger.info(f"Overall OOS: Acc={overall_acc:.3f}, AUC={overall_auc:.3f}")

    # Sharpe of filtered vs unfiltered (aggregate)
    all_returns = oos_df["return_pct"].values
    filtered_mask = oos_df["y_pred"] == 1
    filtered_rets = all_returns[filtered_mask]

    if len(filtered_rets) > 1 and filtered_rets.std() > 0:
        oos_sharpe = (filtered_rets.mean() / filtered_rets.std()) * np.sqrt(252 / 15)
    else:
        oos_sharpe = 0.0

    if len(all_returns) > 1 and all_returns.std() > 0:
        baseline_sharpe = (all_returns.mean() / all_returns.std()) * np.sqrt(252 / 15)
    else:
        baseline_sharpe = 0.0

    logger.info(
        f"Sharpe: Baseline={baseline_sharpe:.3f} → Filtered={oos_sharpe:.3f} "
        f"(lift={oos_sharpe - baseline_sharpe:+.3f})"
    )
    logger.info(
        f"Trades: {filtered_mask.sum()}/{len(oos_df)} "
        f"({filtered_mask.mean()*100:.1f}% filter rate)"
    )

    # ── DSR ───────────────────────────────────────────────────
    n_trials = 4 * 5  # 4 signals × 5 folds tested
    skew = float(stats.skew(filtered_rets)) if len(filtered_rets) > 2 else 0
    kurt = float(stats.kurtosis(filtered_rets, fisher=False)) if len(filtered_rets) > 3 else 3
    dsr = deflated_sharpe_ratio(
        sharpe_observed=oos_sharpe,
        n_trials=n_trials,
        n_observations=len(filtered_rets),
        skewness=skew,
        kurtosis=kurt,
    )
    logger.info(f"DSR (Deflated Sharpe Ratio): {dsr:.4f} (trials={n_trials})")
    if dsr > 0.95:
        logger.info("✅ DSR > 0.95: Sharpe is statistically robust")
    elif dsr > 0.50:
        logger.info("⚠️ DSR in [0.50, 0.95]: Marginal — may be overfitting")
    else:
        logger.info("❌ DSR < 0.50: Sharpe likely explained by luck / multiple testing")

    # ── PER-SIGNAL BREAKDOWN ─────────────────────────────────
    logger.info(f"\n{'─'*50}")
    logger.info("PER-SIGNAL OOS PERFORMANCE")
    logger.info(f"{'─'*50}")

    for sig in oos_df["signal_name"].unique():
        sig_mask = oos_df["signal_name"] == sig
        sig_data = oos_df[sig_mask]
        sig_filtered = sig_data[sig_data["y_pred"] == 1]

        wr = sig_data["y_true"].mean() * 100
        n_total = len(sig_data)
        n_taken = len(sig_filtered)

        if len(sig_filtered) > 1 and sig_filtered["return_pct"].std() > 0:
            sig_sr = (sig_filtered["return_pct"].mean() / sig_filtered["return_pct"].std()) * np.sqrt(252 / 15)
        else:
            sig_sr = 0.0

        logger.info(
            f"  {sig:<25} WR={wr:.1f}% Taken={n_taken}/{n_total} "
            f"Sharpe={sig_sr:.3f}"
        )

    # ── PER-REGIME BREAKDOWN ─────────────────────────────────
    logger.info(f"\n{'─'*50}")
    logger.info("PER-REGIME OOS PERFORMANCE (Weinstein Proxy)")
    logger.info(f"{'─'*50}")

    regime_map = {0.75: "Advancing", 0.25: "Basing", -0.25: "Topping", -0.75: "Declining"}
    for regime_val, regime_name in regime_map.items():
        reg_mask = oos_df["regime"] == regime_val
        if reg_mask.sum() < 10:
            continue
        reg_data = oos_df[reg_mask]
        reg_filtered = reg_data[reg_data["y_pred"] == 1]

        wr = reg_data["y_true"].mean() * 100
        n_total = len(reg_data)
        n_taken = len(reg_filtered)

        if len(reg_filtered) > 1 and reg_filtered["return_pct"].std() > 0:
            reg_sr = (reg_filtered["return_pct"].mean() / reg_filtered["return_pct"].std()) * np.sqrt(252 / 15)
        else:
            reg_sr = 0.0

        logger.info(
            f"  {regime_name:<15} N={n_total:>5} WR={wr:.1f}% "
            f"Taken={n_taken} Sharpe={reg_sr:.3f}"
        )

    # ── FEATURE IMPORTANCE (MDA) ─────────────────────────────
    logger.info(f"\n{'─'*50}")
    logger.info("TOP 15 FEATURES (Gain-Based Importance)")
    logger.info(f"{'─'*50}")

    feature_importances /= len(folds)
    importance_df = pd.DataFrame({
        "feature": feature_cols,
        "importance": feature_importances,
    }).sort_values("importance", ascending=False)

    for _, row in importance_df.head(15).iterrows():
        bar = "█" * int(row["importance"] * 100)
        logger.info(f"  {row['feature']:<25} {row['importance']:.4f} {bar}")

    # ── FINAL REPORT ─────────────────────────────────────────
    results = {
        "n_samples": len(df),
        "n_features": len(feature_cols),
        "n_folds": len(folds),
        "oos_accuracy": round(overall_acc, 4),
        "oos_auc": round(overall_auc, 4),
        "oos_sharpe_baseline": round(baseline_sharpe, 4),
        "oos_sharpe_filtered": round(oos_sharpe, 4),
        "oos_sharpe_lift": round(oos_sharpe - baseline_sharpe, 4),
        "dsr": dsr,
        "n_trials": n_trials,
        "fold_metrics": fold_metrics,
        "top_features": importance_df.head(15).to_dict("records"),
    }

    logger.info(f"\n{'='*60}")
    logger.info("META-MODEL TRAINING COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"  Samples: {results['n_samples']}")
    logger.info(f"  Features: {results['n_features']}")
    logger.info(f"  OOS AUC: {results['oos_auc']}")
    logger.info(f"  OOS Sharpe Lift: {results['oos_sharpe_lift']:+.3f}")
    logger.info(f"  DSR: {results['dsr']:.4f}")

    return results


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info("Loading ML Data Lake...")
    df = load_ml_data()

    logger.info("Starting Meta-Model Training Pipeline...")
    results = train_and_evaluate(df)

    if results:
        # Save results to JSON
        out_path = _root / "backend" / "scripts" / "meta_model_results.json"
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"\nResults saved to {out_path}")
