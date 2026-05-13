"""
train_meta_model.py — XGBoost Meta-Labeling with Purged Walk-Forward CV
==========================================================================
López de Prado institutional-grade training pipeline:
  1. Load VAEP-corrected features + labels from Neon ML Data Lake
  2. Convert ternary labels {-1, 0, 1} to binary meta-labels {0, 1}
  3. Compute sample weights by Average Uniqueness
  4. Train XGBoost with Purged Walk-Forward CV (anchored or sliding)
  5. Evaluate with Deflated Sharpe Ratio (DSR)
  6. Report: per-signal, per-regime, IS vs OOS metrics

Usage:
    python backend/scripts/train_meta_model.py --timeframe 1d --cv-mode sliding
    python backend/scripts/train_meta_model.py --timeframe 5m --cv-mode expanding
    python backend/scripts/train_meta_model.py --timeframe 1d --cv-mode sliding --seeds 42,123,456
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

def load_ml_data(timeframe: str = "5m") -> pd.DataFrame:
    """Load features + labels + forensics from Neon ML Data Lake, filtered by timeframe."""
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    store = TimescaleDataStore()

    query = """
        SELECT
            f.id, f.ticker, f.timeframe, f.signal_name,
            f.signal_time, f.features,
            l.label, l.return_pct, l.bars_held, l.exit_time,
            l.geometry_used,
            l.max_adverse_excursion_pct,
            l.max_favorable_excursion_pct,
            l.post_exit_max_pct,
            l.post_exit_hit_target,
            l.post_exit_bars_to_target,
            l.stop_was_sweep
        FROM engine.ml_features f
        JOIN engine.ml_labels l ON f.id = l.feature_id
        WHERE f.timeframe = %(tf)s
        ORDER BY f.signal_time
    """
    df = pd.read_sql(query, store.engine, params={"tf": timeframe})
    store.close()

    if df.empty:
        logger.error(f"No ML data found for timeframe={timeframe}")
        return df

    # Parse JSON features into columns
    feat_dicts = df["features"].apply(
        lambda x: json.loads(x) if isinstance(x, str) else x
    )
    feat_df = pd.DataFrame(feat_dicts.tolist(), index=df.index)
    df = pd.concat([df.drop(columns=["features"]), feat_df], axis=1)

    # Parse signal_time
    df["signal_time"] = pd.to_datetime(df["signal_time"])
    df["exit_time"] = pd.to_datetime(df["exit_time"], errors="coerce")

    # Extract geometry type from JSONB (VALUE: loss_mult=1.0, THESIS: loss_mult=0)
    df["geometry_type"] = df["geometry_used"].apply(
        lambda g: "THESIS" if (isinstance(g, dict) and g.get("loss_mult", 1) == 0)
        else ("THESIS" if isinstance(g, str) and '"loss_mult": 0' in g else "VALUE")
    )

    # One-hot encode signal_name (Simons: different signals have different base rates)
    signal_dummies = pd.get_dummies(df["signal_name"], prefix="SIG")
    df = pd.concat([df, signal_dummies], axis=1)

    logger.info(
        f"Loaded {len(df)} samples, {len(feat_df.columns)} features + {len(signal_dummies.columns)} signal dummies, "
        f"{df['signal_name'].nunique()} signals, {df['ticker'].nunique()} tickers, tf={timeframe}"
    )
    # Log forensic data availability
    n_forensic = df["max_adverse_excursion_pct"].notna().sum()
    n_thesis = (df["geometry_type"] == "THESIS").sum()
    n_value = (df["geometry_type"] == "VALUE").sum()
    logger.info(
        f"Forensics: {n_forensic} with MAE/MFE, {n_thesis} THESIS labels, {n_value} VALUE labels"
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
    Compute sample weights based on Average Uniqueness (LdP Ch. 4).

    Event-based O(N log N) algorithm:
      1. Build sorted event list (start/end of each label lifespan)
      2. Sweep through events tracking concurrency c(t)
      3. For each sample, average 1/c(t) over its lifespan
    """
    entry = df["signal_time"].values.astype("datetime64[ns]")
    exit_ = df["exit_time"].values.astype("datetime64[ns]")

    n = len(df)
    mask = pd.isna(exit_)
    exit_[mask] = entry[mask]

    # Build event list: (+1 = label starts, -1 = label ends)
    events = []
    for i in range(n):
        events.append((entry[i], 0, +1, i))  # 0 = start sorts before end
        events.append((exit_[i], 1, -1, i))  # 1 = end sorts after start
    events.sort(key=lambda x: (x[0], x[1]))

    # Sweep: track concurrency and accumulate uniqueness
    active_count = 0
    uniqueness_sum = np.zeros(n, dtype=float)
    uniqueness_cnt = np.zeros(n, dtype=int)
    active_set = set()

    for ts, order, delta, idx in events:
        if delta == +1:
            active_count += 1
            active_set.add(idx)
        else:
            # At this endpoint, record 1/c for all currently active labels
            if active_count > 0:
                inv_c = 1.0 / active_count
                for j in active_set:
                    uniqueness_sum[j] += inv_c
                    uniqueness_cnt[j] += 1
            active_count -= 1
            active_set.discard(idx)

    # Average uniqueness per sample
    weights = np.where(
        uniqueness_cnt > 0,
        uniqueness_sum / uniqueness_cnt,
        1.0,
    )
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


def purged_sliding_window_cv(
    df: pd.DataFrame,
    n_folds: int = 5,
    embargo_pct: float = 0.01,
    min_train_size: int = 2000,
    window_size: int | None = None,
) -> list[CVFold]:
    """
    Purged Sliding-Window Cross-Validation.

    Forensic fix for fold-collapse: expanding window accumulates stale
    regimes (2020-2022 COVID/recovery) that don't generalize to 2024-2025.
    Sliding window forces each fold to train on a fixed recent window.

    Properties:
        1. SLIDING: Train window has a FIXED size (not anchored at bar 0).
        2. PURGED: Remove train samples whose [entry, exit] overlaps with test.
        3. EMBARGOED: Additional buffer after each test fold excluded from train.
        4. TEMPORAL: Test always comes AFTER train chronologically.

    Args:
        df: DataFrame sorted by signal_time with entry/exit timestamps.
        n_folds: Number of walk-forward folds.
        embargo_pct: Fraction of total samples to embargo after test.
        min_train_size: Minimum training samples per fold.
        window_size: Fixed training window size. If None, auto-calculated
                     as min(len(df) // 3, 20_000).
    """
    n = len(df)
    embargo_size = max(1, int(n * embargo_pct))

    # Auto-calculate window size if not provided
    if window_size is None:
        window_size = min(n // 3, 20_000)
    window_size = max(window_size, min_train_size)

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

        # ── SLIDING TRAIN WINDOW ─────────────────────────────
        # Instead of anchored at 0, train starts at max(0, test_start - window_size)
        train_start = max(0, test_start - window_size)
        train_end = test_start
        train_candidates = np.arange(train_start, train_end)

        # ── PURGING ──────────────────────────────────────────
        # Remove train samples whose lifespan overlaps with ANY test sample
        test_entry_min = entry[test_start]

        purge_mask = np.ones(len(train_candidates), dtype=bool)
        n_purged = 0
        for ti, tidx in enumerate(train_candidates):
            if exit_[tidx] >= test_entry_min:
                purge_mask[ti] = False
                n_purged += 1

        train_idx = train_candidates[purge_mask]

        # ── EMBARGO ──────────────────────────────────────────
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
            f"[{train_idx[0]}→{train_idx[-1]}] (window={window_size}), "
            f"test={len(test_idx)} [{test_start}→{test_end-1}], "
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
    """Extract ML feature columns (prefixed families + signal dummies)."""
    prefixes = (
        'FD_', 'MS_', 'TS_', 'CS_', 'VF_', 'MC_', 'OV_', 'CAL_', 'IM_', 'RG_',
        'MTF_', 'BA_', 'SIG_',
    )
    return [c for c in df.columns if c.startswith(prefixes)]


def _tf_to_minutes(tf: str) -> int:
    """Convert timeframe string to minutes per bar."""
    _map = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 390}
    return _map.get(tf, 5)


def _annualized_sharpe(
    returns: np.ndarray,
    bars_held: np.ndarray,
    tf_minutes: int,
) -> float:
    """
    Annualize per-trade Sharpe using actual holding period.

    trades_per_year = (bars_per_day × 252) / avg_bars_held
    SR_annual = SR_per_trade × √(trades_per_year)
    """
    if len(returns) < 2 or np.std(returns) == 0:
        return 0.0
    bars_per_day = 390.0 / tf_minutes  # 6.5 trading hours
    avg_bars = float(np.mean(bars_held))
    if avg_bars <= 0:
        return 0.0
    trades_per_year = (bars_per_day * 252) / avg_bars
    return float((np.mean(returns) / np.std(returns)) * np.sqrt(trades_per_year))


def train_and_evaluate(df: pd.DataFrame, cv_mode: str = "expanding", seed: int = 42) -> dict:
    """
    Full training pipeline with institutional-grade validation.

    Args:
        df: Full ML dataset.
        cv_mode: 'expanding' (anchored at bar 0) or 'sliding' (fixed window).
        seed: Random seed for XGBoost.

    Returns a results dict with per-fold and aggregate metrics.
    """
    feature_cols = get_feature_columns(df)
    tf_minutes = _tf_to_minutes(df["timeframe"].iloc[0])
    logger.info(f"Feature columns ({len(feature_cols)}): {feature_cols} [tf={tf_minutes}m]")

    X = df[feature_cols].values.astype(np.float32)
    meta_y = create_meta_labels(df)
    y = meta_y.values

    # Replace any remaining NaN/inf
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    # ── SAMPLE WEIGHTS ───────────────────────────────────────
    logger.info("Computing sample weights (Average Uniqueness)...")
    weights = compute_sample_weights(df)

    # ── PURGED WALK-FORWARD CV ───────────────────────────────
    # Auto-adjust folds based on sample count (LdP: need sufficient train per fold)
    n_folds = 3 if len(df) < 10000 else 5
    logger.info(f"Generating Purged Walk-Forward folds (n_folds={n_folds}, cv_mode={cv_mode})...")

    if cv_mode == "sliding":
        # Sliding window: fixed training window, forget stale regimes
        # Auto window: 1d ≈ 20K samples (~2 years × 30 tickers), 5m ≈ 80K
        tf = df["timeframe"].iloc[0]
        if tf == "1d":
            window_size = min(len(df) // 3, 20_000)
        else:
            window_size = min(len(df) // 3, 80_000)
        logger.info(f"Sliding window: window_size={window_size} (tf={tf})")
        folds = purged_sliding_window_cv(
            df, n_folds=n_folds, embargo_pct=0.01, window_size=window_size,
        )
    else:
        folds = purged_walk_forward_cv(df, n_folds=n_folds, embargo_pct=0.01)

    if not folds:
        logger.error("No valid CV folds generated. Insufficient data.")
        return {}

    # ── XGBoost params (regularized, anti-overfit) ───────────
    # Forensic audit: sweep suggested depth=4/mcw=50/lr=0.03 but this caused
    # Fold 4 to early-stop at iter 0 (overfitting). Original params are
    # the true optimum — the sweep artifact was fold-selection bias.
    xgb_params = {
        "objective": "binary:logistic",
        "eval_metric": "logloss",
        "max_depth": 3,          # Depth 3 (forensic: depth=4 overfits on small folds)
        "learning_rate": 0.05,   # 0.05 (forensic: 0.03 too slow, iter 0 early-stop)
        "n_estimators": 500,     # Higher ceiling with early stopping
        "subsample": 0.8,
        "colsample_bytree": 0.7,
        "min_child_weight": 100, # MCW 100 (forensic: 50 overfits on regime-shift folds)
        "gamma": 1.0,            # Pruning threshold (sweep confirmed optimal)
        "reg_alpha": 0.5,        # L1 regularization
        "reg_lambda": 2.0,       # L2 regularization
        "scale_pos_weight": (y == 0).sum() / max((y == 1).sum(), 1),
        "random_state": seed,
        "verbosity": 0,
        "early_stopping_rounds": 20,  # Stop when val loss stagnates
    }

    # ── PER-FOLD TRAINING + EVALUATION ───────────────────────
    all_oos_results = []
    fold_metrics = []
    feature_importances = np.zeros(len(feature_cols))

    # Forensic guard: warn about underpowered folds (< 5000 train samples)
    # Note: We INCLUDE all folds in OOS evaluation but flag underpowered ones.
    # Skipping them was tested and actually REDUCED honest Sharpe because
    # underpowered folds' test windows still contain real market data.
    MIN_TRAIN_SAMPLES = 5000
    underpowered = [f for f in folds if len(f.train_idx) < MIN_TRAIN_SAMPLES]
    if underpowered:
        logger.warning(
            f"⚠️ {len(underpowered)} underpowered folds "
            f"(< {MIN_TRAIN_SAMPLES} train samples): "
            f"{[f'Fold {f.fold_id} ({len(f.train_idx)} samples)' for f in underpowered]}. "
            f"OOS metrics from these folds have higher variance."
        )

    for fold in folds:
        logger.info(f"\n{'─'*50}")
        logger.info(f"FOLD {fold.fold_id}")
        logger.info(f"{'─'*50}")

        X_train = X[fold.train_idx]
        y_train = y[fold.train_idx]
        w_train = weights[fold.train_idx]

        X_test = X[fold.test_idx]
        y_test = y[fold.test_idx]

        # Split last 20% of train as validation (stays before test window)
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
        best_iter = getattr(model, 'best_iteration', model.n_estimators)
        logger.info(f"  Early stopped at iteration {best_iter}/{xgb_params['n_estimators']}")

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

        # OOS Sharpe (corrected annualization via actual holding period)
        test_returns = df.iloc[fold.test_idx]["return_pct"].values
        test_bars = df.iloc[fold.test_idx]["bars_held"].values
        filtered_mask_fold = y_pred == 1

        sr = _annualized_sharpe(
            test_returns[filtered_mask_fold], test_bars[filtered_mask_fold], tf_minutes
        )
        sr_baseline = _annualized_sharpe(test_returns, test_bars, tf_minutes)

        # IS metrics (WEAK-1: overfit detection)
        y_pred_is = model.predict(X_train)
        is_acc = accuracy_score(y_train, y_pred_is)
        train_returns = df.iloc[fold.train_idx]["return_pct"].values
        train_bars = df.iloc[fold.train_idx]["bars_held"].values
        is_filtered_mask = y_pred_is == 1
        sr_is = _annualized_sharpe(
            train_returns[is_filtered_mask], train_bars[is_filtered_mask], tf_minutes
        )
        overfit_ratio = round(sr_is / sr, 2) if sr != 0 else float('inf')

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
            "sharpe_IS": round(sr_is, 4),
            "overfit_ratio": overfit_ratio,
            "is_accuracy": round(is_acc, 4),
            "trades_taken": int(y_pred.sum()),
            "trades_total": len(y_test),
            "filter_rate": round(y_pred.sum() / len(y_test) * 100, 1),
        }
        fold_metrics.append(fold_result)

        logger.info(
            f"  OOS: Acc={acc:.3f} Prec={prec:.3f} Rec={rec:.3f} AUC={auc:.3f}\n"
            f"  Sharpe: baseline={sr_baseline:.3f} → filtered={sr:.3f} "
            f"(lift={sr - sr_baseline:+.3f})\n"
            f"  IS: Acc={is_acc:.3f} Sharpe_IS={sr_is:.3f} "
            f"Overfit={overfit_ratio:.1f}x\n"
            f"  Trades: {y_pred.sum()}/{len(y_test)} taken ({fold_result['filter_rate']:.0f}%)"
        )

        # Accumulate feature importance (gain-based)
        importances = model.feature_importances_
        feature_importances += importances

        # Store OOS predictions for aggregate analysis
        for i, idx in enumerate(fold.test_idx):
            row_data = df.iloc[idx]
            all_oos_results.append({
                "idx": idx,
                "y_true": y_test[i],
                "y_pred": y_pred[i],
                "y_proba": y_pred_proba[i],
                "return_pct": test_returns[i],
                "bars_held": int(test_bars[i]),
                "signal_name": row_data["signal_name"],
                "ticker": row_data["ticker"],
                "regime": row_data.get("RG_WinsteinProxy", 0),
                "vol_regime_quality": row_data.get("RG_VolRegime_Quality", 0),
                "vol_regime_speculative": row_data.get("RG_VolRegime_Speculative", 0),
                # Forensic fields
                "max_adverse_excursion_pct": row_data.get("max_adverse_excursion_pct", 0),
                "max_favorable_excursion_pct": row_data.get("max_favorable_excursion_pct", 0),
                "post_exit_max_pct": row_data.get("post_exit_max_pct", 0),
                "post_exit_hit_target": row_data.get("post_exit_hit_target", False),
                "post_exit_bars_to_target": row_data.get("post_exit_bars_to_target", 0),
                "stop_was_sweep": row_data.get("stop_was_sweep", False),
                "geometry_type": row_data.get("geometry_type", "VALUE"),
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

    all_bars = oos_df["bars_held"].values
    filtered_bars = all_bars[filtered_mask]

    oos_sharpe = _annualized_sharpe(filtered_rets, filtered_bars, tf_minutes)
    baseline_sharpe = _annualized_sharpe(all_returns, all_bars, tf_minutes)

    logger.info(
        f"Sharpe: Baseline={baseline_sharpe:.3f} → Filtered={oos_sharpe:.3f} "
        f"(lift={oos_sharpe - baseline_sharpe:+.3f})"
    )
    logger.info(
        f"Trades: {filtered_mask.sum()}/{len(oos_df)} "
        f"({filtered_mask.mean()*100:.1f}% filter rate)"
    )

    # ── DSR ───────────────────────────────────────────────────
    n_trials = 1  # Single model config; folds are resamples, not independent trials
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

        sig_sr = _annualized_sharpe(
            sig_filtered["return_pct"].values,
            sig_filtered["bars_held"].values,
            tf_minutes,
        )

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

        reg_sr = _annualized_sharpe(
            reg_filtered["return_pct"].values,
            reg_filtered["bars_held"].values,
            tf_minutes,
        )

        logger.info(
            f"  {regime_name:<15} N={n_total:>5} WR={wr:.1f}% "
            f"Taken={n_taken} Sharpe={reg_sr:.3f}"
        )

    # ── PER-VOL-REGIME BREAKDOWN ─────────────────────────────
    logger.info(f"\n{'─'*50}")
    logger.info("PER-VOL-REGIME OOS PERFORMANCE")
    logger.info(f"{'─'*50}")

    vol_regime_cols = {
        "vol_regime_quality": {0: "NORMAL", 1: "COMPLACENT", 2: "ELEVATED", 3: "CRISIS"},
        "vol_regime_speculative": {0: "STALK", 1: "STRIKE", 2: "HARVEST", 3: "RETREAT"},
    }

    for col, label_map in vol_regime_cols.items():
        if col not in oos_df.columns:
            continue
        logger.info(f"\n  {col}:")
        for val, name in label_map.items():
            reg_mask = oos_df[col] == val
            if reg_mask.sum() < 10:
                continue
            reg_data = oos_df[reg_mask]
            reg_filtered = reg_data[reg_data["y_pred"] == 1]
            wr = reg_data["y_true"].mean() * 100
            reg_sr = _annualized_sharpe(
                reg_filtered["return_pct"].values,
                reg_filtered["bars_held"].values,
                tf_minutes,
            )
            logger.info(
                f"    {name:<15} N={len(reg_data):>5} WR={wr:.1f}% "
                f"Taken={len(reg_filtered)} Sharpe={reg_sr:.3f}"
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

    # ── FORENSIC DIAGNOSTIC (Dalio Detect-Learn Loop) ────────
    if "max_adverse_excursion_pct" in oos_df.columns:
        logger.info(f"\n{'─'*50}")
        logger.info("FORENSIC DIAGNOSTIC — WHY IT WINS / WHY IT FAILS")
        logger.info(f"{'─'*50}")

        winners = oos_df[oos_df["y_true"] == 1]
        losers = oos_df[oos_df["y_true"] == 0]

        # ── WINNERS: What made them win? ──
        if len(winners) > 0:
            mae_w = winners["max_adverse_excursion_pct"].mean()
            mfe_w = winners["max_favorable_excursion_pct"].mean()
            ret_w = winners["return_pct"].mean()
            mfe_capture = (ret_w / mfe_w * 100) if mfe_w > 0 else 0
            entry_quality = (1 - abs(mae_w) / mfe_w) * 100 if mfe_w > 0 else 0

            logger.info(f"\n  ✅ WINNERS (N={len(winners)}):")
            logger.info(f"     Avg Return:      {ret_w:+.3f}%")
            logger.info(f"     Avg MAE:         {mae_w:.3f}% (worst drawdown before profit)")
            logger.info(f"     Avg MFE:         {mfe_w:.3f}% (best profit reached)")
            logger.info(f"     MFE Capture:     {mfe_capture:.1f}% (of max profit actually realized)")
            logger.info(f"     Entry Quality:   {entry_quality:.1f}% (lower MAE = better entry)")
            left_on_table = mfe_w - ret_w
            logger.info(f"     Left on table:   {left_on_table:.3f}% per trade (exit gap)")

        # ── LOSERS: What made them fail? ──
        if len(losers) > 0:
            mae_l = losers["max_adverse_excursion_pct"].mean()
            mfe_l = losers["max_favorable_excursion_pct"].mean()
            ret_l = losers["return_pct"].mean()

            # Post-stop analysis
            if "post_exit_hit_target" in losers.columns:
                n_sweep = losers["stop_was_sweep"].sum() if "stop_was_sweep" in losers.columns else 0
                n_post_hit = losers["post_exit_hit_target"].sum() if losers["post_exit_hit_target"].dtype == bool else 0
                pct_false_neg = n_post_hit / len(losers) * 100 if len(losers) > 0 else 0

                logger.info(f"\n  ❌ LOSERS (N={len(losers)}):")
                logger.info(f"     Avg Return:      {ret_l:+.3f}%")
                logger.info(f"     Avg MAE:         {mae_l:.3f}% (how deep the loss)")
                logger.info(f"     Avg MFE:         {mfe_l:.3f}% (profit they DID reach before losing)")
                logger.info(f"     False Negatives: {pct_false_neg:.1f}% (hit target AFTER being stopped)")
                logger.info(f"     Sweeps:          {n_sweep} ({n_sweep/len(losers)*100:.1f}% of losses)")
                if mfe_l > 0:
                    logger.info(f"     Entry was right:  {mfe_l:.3f}% profit seen — stop/timing killed it")

        # ── PER-SIGNAL FORENSIC ──
        logger.info(f"\n  📊 PER-SIGNAL FORENSIC:")
        logger.info(f"  {'Signal':<25s} {'WR':>6s} {'AvgRet':>8s} {'MFE↑':>8s} {'MAE↓':>8s} {'Capture':>8s}")
        for sig in oos_df["signal_name"].unique():
            sig_data = oos_df[oos_df["signal_name"] == sig]
            sig_wr = sig_data["y_true"].mean() * 100
            sig_ret = sig_data["return_pct"].mean()
            sig_mfe = sig_data["max_favorable_excursion_pct"].mean()
            sig_mae = sig_data["max_adverse_excursion_pct"].mean()
            sig_cap = (sig_ret / sig_mfe * 100) if sig_mfe > 0 else 0
            logger.info(
                f"  {sig:<25s} {sig_wr:>5.1f}% {sig_ret:>+7.3f}% "
                f"{sig_mfe:>7.3f}% {sig_mae:>7.3f}% {sig_cap:>6.1f}%"
            )

        # ── GEOMETRY COMPARISON (VALUE vs THESIS) ──
        if "geometry_type" in oos_df.columns:
            for gtype in ["VALUE", "THESIS"]:
                g_data = oos_df[oos_df["geometry_type"] == gtype]
                if len(g_data) < 10:
                    continue
                g_wr = g_data["y_true"].mean() * 100
                g_sr = _annualized_sharpe(
                    g_data[g_data["y_pred"] == 1]["return_pct"].values,
                    g_data[g_data["y_pred"] == 1]["bars_held"].values,
                    tf_minutes,
                )
                g_pht = g_data["post_exit_hit_target"].sum() if "post_exit_hit_target" in g_data.columns else 0
                logger.info(
                    f"\n  🏗️ {gtype}: N={len(g_data)} WR={g_wr:.1f}% Sharpe={g_sr:.3f} "
                    f"PostStopHit={g_pht} ({g_pht/len(g_data)*100:.1f}%)"
                )

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
    import argparse
    parser = argparse.ArgumentParser(description="XGBoost Meta-Labeling Training")
    parser.add_argument("--timeframe", default="5m", help="Timeframe to train on (5m, 1d)")
    parser.add_argument(
        "--cv-mode", default="auto",
        choices=["expanding", "sliding", "auto"],
        help="CV mode: 'expanding' (anchored), 'sliding' (fixed window), "
             "'auto' (sliding for 1d, expanding for 5m)",
    )
    parser.add_argument(
        "--seeds", default="42",
        help="Comma-separated random seeds for multi-trial DSR (e.g., '42,123,456')",
    )
    args = parser.parse_args()

    # Resolve auto CV mode
    cv_mode = args.cv_mode
    if cv_mode == "auto":
        cv_mode = "sliding" if args.timeframe == "1d" else "expanding"
    logger.info(f"CV mode: {cv_mode} (requested: {args.cv_mode})")

    logger.info(f"Loading ML Data Lake (timeframe={args.timeframe})...")
    df = load_ml_data(timeframe=args.timeframe)

    if df.empty:
        logger.error("No data loaded. Aborting.")
        sys.exit(1)

    seeds = [int(s.strip()) for s in args.seeds.split(",")]

    if len(seeds) == 1:
        # Single run
        logger.info("Starting Meta-Model Training Pipeline...")
        results = train_and_evaluate(df, cv_mode=cv_mode, seed=seeds[0])

        if results:
            out_path = _root / "backend" / "scripts" / f"meta_model_results_{args.timeframe}.json"
            with open(out_path, "w") as f:
                json.dump(results, f, indent=2, default=str)
            logger.info(f"\nResults saved to {out_path}")
    else:
        # Multi-trial DSR
        logger.info(f"\n{'='*60}")
        logger.info(f"MULTI-TRIAL DSR — {len(seeds)} seeds")
        logger.info(f"{'='*60}")

        all_lifts = []
        all_dsrs = []
        all_results = []

        for i, seed in enumerate(seeds):
            logger.info(f"\n{'━'*60}")
            logger.info(f"TRIAL {i+1}/{len(seeds)} — seed={seed}")
            logger.info(f"{'━'*60}")
            result = train_and_evaluate(df, cv_mode=cv_mode, seed=seed)
            if result:
                all_lifts.append(result["oos_sharpe_lift"])
                all_dsrs.append(result["dsr"])
                all_results.append({"seed": seed, **result})

        if all_lifts:
            lifts_arr = np.array(all_lifts)
            dsrs_arr = np.array(all_dsrs)
            logger.info(f"\n{'='*60}")
            logger.info("MULTI-TRIAL DSR SUMMARY")
            logger.info(f"{'='*60}")
            logger.info(f"  Trials: {len(all_lifts)}")
            logger.info(f"  Sharpe Lift: {lifts_arr.mean():+.3f} ± {lifts_arr.std():.3f}")
            logger.info(f"  Min/Max Lift: {lifts_arr.min():+.3f} / {lifts_arr.max():+.3f}")
            logger.info(f"  % Positive Lift: {(lifts_arr > 0).mean()*100:.0f}%")
            logger.info(f"  DSR Mean: {dsrs_arr.mean():.4f}")
            logger.info(f"  DSR Range: [{dsrs_arr.min():.4f}, {dsrs_arr.max():.4f}]")

            out_path = _root / "backend" / "scripts" / f"meta_model_multitrial_{args.timeframe}.json"
            with open(out_path, "w") as f:
                json.dump({
                    "cv_mode": cv_mode,
                    "n_trials": len(seeds),
                    "sharpe_lift_mean": round(float(lifts_arr.mean()), 4),
                    "sharpe_lift_std": round(float(lifts_arr.std()), 4),
                    "pct_positive": round(float((lifts_arr > 0).mean() * 100), 1),
                    "dsr_mean": round(float(dsrs_arr.mean()), 4),
                    "trials": all_results,
                }, f, indent=2, default=str)
            logger.info(f"\nMulti-trial results saved to {out_path}")
