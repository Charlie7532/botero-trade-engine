"""
Feature Discovery Runner — XGBoost Backward Elimination
===========================================================
Starts with the enriched quaternion (all ~36 dimensions) and uses
XGBoost feature importance + backward elimination to discover
which dimensions maximize next-bar prediction accuracy.

Strategy:
  1. Build full feature matrix: Quaternion 4D + derivatives + extras
  2. Label: next_bar_label (BULL=1, BEAR=-1, NEUTRAL=0)
  3. XGBoost fit → feature_importances_ ranking
  4. Backward elimination: remove least important, re-measure
  5. Stop when removing any feature drops accuracy > 1%
  6. Record optimal subset in ExperimentRegistry with DSR

Usage:
    PYTHONPATH=. backend/.venv/bin/python backend/research_lab/experiments/feature_discovery_runner.py
"""
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")

from backend.research_lab.models.quaternion_core import MarketQuaternion
from backend.research_lab.experiments.experiment_registry import ExperimentRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger("FeatureDiscovery")


def build_enriched_features(
    ohlcv: pd.DataFrame,
    macro_extras: dict[str, pd.Series] | None = None,
    market_data: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """
    Build the full enriched feature matrix:
      - Quaternion 4D base + 8 derivatives (12 dims)
      - QuantFeatureEngineer features (~30+ dims)
      - Macro extras from Vault (SKEW, VVIX)

    V2 additions (via market_data dict):
      - Organic Volume Decomposition (SPY + Sector ETF)
      - Calendar Mechanical Forces (OPEX, Month-End, Quarter-End)
      - Intermarket Rotation (Sector RS, Yield Delta, Credit Spread)

    Each QFE family is extracted independently — a failure in one
    family does not block the others.

    Returns a single DataFrame with all candidate dimensions.
    """
    market_data = market_data or {}

    # 1. Quaternion base + derivatives
    q = MarketQuaternion.compute(ohlcv, extras=macro_extras)

    # 2. QuantFeatureEngineer features (from production, read-only)
    try:
        from backend.modules.simulation.application.use_cases.engineer_features import (
            QuantFeatureEngineer,
        )
        tf_minutes = 1440  # daily bars = 1440 minutes
        qfe = QuantFeatureEngineer(ohlcv, tf_minutes)

        # Extract each family independently — one failure doesn't kill the rest
        # V1 families (no external data needed)
        for method_name in [
            "extract_fractional_features",
            "extract_microstructure_features",
            "extract_temporal_features",
            "extract_volume_flow_features",
        ]:
            try:
                getattr(qfe, method_name)()
            except Exception as e:
                logger.debug(f"QFE.{method_name} failed: {e}")

        # V2 families (require external market data)
        try:
            qfe.extract_organic_volume_features(
                spy_df=market_data.get("spy"),
                sector_etf_df=market_data.get("sector_etf"),
            )
        except Exception as e:
            logger.debug(f"QFE.extract_organic_volume_features failed: {e}")

        try:
            qfe.extract_calendar_features()
        except Exception as e:
            logger.debug(f"QFE.extract_calendar_features failed: {e}")

        try:
            qfe.extract_intermarket_features(
                spy_df=market_data.get("spy"),
                sector_etf_df=market_data.get("sector_etf"),
                bond_df=market_data.get("bond"),
                hyg_df=market_data.get("hyg"),
            )
        except Exception as e:
            logger.debug(f"QFE.extract_intermarket_features failed: {e}")

        # Merge QFE columns into quaternion DataFrame
        original_cols = {"open", "high", "low", "close", "volume", "vwap", "trade_count"}
        new_cols = [c for c in qfe.df.columns if c not in original_cols]
        for col in new_cols:
            if col not in q.columns:
                q[col] = qfe.df[col].reindex(q.index)

        logger.info(f"QFE added {len(new_cols)} features → total {q.shape[1]}D")
    except ImportError as e:
        logger.warning(f"QuantFeatureEngineer import failed: {e}")

    return q


def label_next_bar(ohlcv: pd.DataFrame, neutral_threshold: float = 0.001) -> pd.Series:
    """
    Create next-bar label:
      1 = BULLISH (next close > current close by threshold)
     -1 = BEARISH (next close < current close by threshold)
      0 = NEUTRAL (within threshold)
    """
    next_return = ohlcv["close"].pct_change().shift(-1)
    labels = pd.Series(0, index=ohlcv.index, dtype=int)
    labels[next_return > neutral_threshold] = 1
    labels[next_return < -neutral_threshold] = -1
    return labels


def run_xgboost_importance(
    X: pd.DataFrame,
    y: pd.Series,
    test_fraction: float = 0.3,
) -> tuple[dict[str, float], float]:
    """
    Train XGBoost classifier, return feature importances and accuracy.

    NaN handling: fills forward then drops remaining leading NaNs,
    preserving maximum sample count.

    Returns:
        (importance_dict, accuracy)
    """
    from sklearn.model_selection import train_test_split
    from xgboost import XGBClassifier

    # Clean: inf→NaN, drop mostly-NaN columns, ffill/bfill survivors
    X_safe = X.replace([np.inf, -np.inf], np.nan)
    # Drop columns where >50% of values are NaN (e.g., FD_LogClose when
    # the FFD window exceeds available data)
    good_cols = X_safe.columns[X_safe.notna().mean() > 0.5]
    X_filled = X_safe[good_cols].ffill().bfill()
    mask = X_filled.notna().all(axis=1) & y.notna()
    X_clean = X_filled[mask]
    y_clean = y[mask]

    if len(X_clean) < 200:
        logger.warning(f"Only {len(X_clean)} samples after NaN handling — insufficient for XGBoost")
        return {}, 0.0

    # Shift labels to 0-based for XGBoost multiclass (0, 1, 2)
    y_shifted = y_clean + 1  # -1,0,1 → 0,1,2

    X_train, X_test, y_train, y_test = train_test_split(
        X_clean, y_shifted, test_size=test_fraction, shuffle=False,
    )

    model = XGBClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        random_state=42,
        verbosity=0,
        objective="multi:softmax",
        num_class=3,
        eval_metric="mlogloss",
    )
    model.fit(X_train, y_train)

    accuracy = float(model.score(X_test, y_test))
    importance = dict(zip(X_clean.columns, model.feature_importances_))

    return importance, accuracy


def backward_elimination(
    X: pd.DataFrame,
    y: pd.Series,
    importance: dict[str, float],
    accuracy_drop_threshold: float = 0.01,
) -> tuple[list[str], float]:
    """
    Remove features one at a time (least important first).
    Stop when removing any feature drops accuracy by > threshold.

    Returns:
        (optimal_features, final_accuracy)
    """
    # Sort by importance ascending (remove least important first)
    ranked = sorted(importance.items(), key=lambda x: x[1])
    current_features = list(X.columns)
    _, baseline_acc = run_xgboost_importance(X[current_features], y)

    logger.info(f"Baseline: {len(current_features)} features, accuracy={baseline_acc:.4f}")

    for feat_name, feat_imp in ranked:
        if len(current_features) <= 4:
            break  # Don't go below 4 features (quaternion core)

        candidate = [f for f in current_features if f != feat_name]
        _, new_acc = run_xgboost_importance(X[candidate], y)
        drop = baseline_acc - new_acc

        if drop > accuracy_drop_threshold:
            logger.info(
                f"  KEEP {feat_name} (imp={feat_imp:.4f}): "
                f"removing drops accuracy by {drop:.4f}"
            )
        else:
            logger.info(
                f"  DROP {feat_name} (imp={feat_imp:.4f}): "
                f"accuracy change={-drop:+.4f}"
            )
            current_features = candidate
            baseline_acc = new_acc

    return current_features, baseline_acc


def _evaluate_subset(
    X: pd.DataFrame, y: pd.Series, ohlcv: pd.DataFrame,
) -> tuple[float, float, float, float, float, int]:
    """Evaluate a feature subset, return (accuracy, sharpe, pf, wr, mdd, n_trades)."""
    from sklearn.model_selection import train_test_split
    from xgboost import XGBClassifier

    X_safe = X.replace([np.inf, -np.inf], np.nan)
    good_cols = X_safe.columns[X_safe.notna().mean() > 0.5]
    X_filled = X_safe[good_cols].ffill().bfill()
    mask = X_filled.notna().all(axis=1) & y.notna()
    X_c = X_filled[mask]
    y_c = y[mask] + 1

    if len(X_c) < 200:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0

    X_tr, X_te, y_tr, y_te = train_test_split(X_c, y_c, test_size=0.3, shuffle=False)
    m = XGBClassifier(
        n_estimators=200, max_depth=5, learning_rate=0.05,
        random_state=42, verbosity=0,
        objective="multi:softmax", num_class=3, eval_metric="mlogloss",
    )
    m.fit(X_tr, y_tr)
    acc = float(m.score(X_te, y_te))
    preds = m.predict(X_te)

    returns = ohlcv["close"].pct_change().reindex(X_te.index).shift(-1)
    sr = returns[preds == 2].dropna()
    if len(sr) > 10:
        sharpe = float(sr.mean() / sr.std() * np.sqrt(252))
        pf = float(sr[sr > 0].sum() / max(abs(sr[sr < 0].sum()), 1e-8))
        mdd = float(sr.cumsum().min())
    else:
        sharpe, pf, mdd = 0.0, 0.0, 0.0

    wr = float((preds == 2).sum() / max(len(preds), 1))
    nt = int((preds == 2).sum())
    return acc, sharpe, pf, wr, mdd, nt


def run_discovery(
    ticker: str = "SPY",
    timeframe: str = "1d",
) -> None:
    """Run the full feature discovery pipeline on a ticker."""
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

    store = TimescaleDataStore()
    registry = ExperimentRegistry()

    logger.info(f"═══ Feature Discovery: {ticker}/{timeframe} ═══")

    # Load OHLCV from Neon vault
    ohlcv = store.load_bars(ticker, timeframe)
    if ohlcv.empty or len(ohlcv) < 300:
        logger.error(f"Insufficient data for {ticker}: {len(ohlcv)} bars")
        store.close()
        return

    logger.info(f"Loaded {len(ohlcv)} bars from Neon ({ohlcv.index.min()} to {ohlcv.index.max()})")

    # Load macro extras from vault
    macro_extras = {}
    for macro_ticker, label in [("SKEW", "skew"), ("VVIX", "vvix")]:
        try:
            macro_bars = store.load_bars(macro_ticker, timeframe)
            if not macro_bars.empty:
                raw = macro_bars["close"].reindex(ohlcv.index, method="ffill")
                mean = raw.rolling(50, min_periods=10).mean()
                std = raw.rolling(50, min_periods=10).std().clip(lower=1e-8)
                macro_extras[f"{label}_zscore"] = (raw - mean) / std
                macro_extras[f"{label}_delta"] = raw.pct_change(5)
                logger.info(f"  Added macro: {label} ({len(raw.dropna())} values)")
        except Exception as e:
            logger.debug(f"  Macro {label} unavailable: {e}")

    # Build enriched features
    features = build_enriched_features(ohlcv, macro_extras or None)
    labels = label_next_bar(ohlcv)

    logger.info(f"Feature matrix: {features.shape[1]} dimensions × {len(features)} bars")

    # ── Experiment 1: Full enriched model ──
    importance, full_acc = run_xgboost_importance(features, labels)

    if not importance:
        logger.error("XGBoost failed — aborting")
        store.close()
        return

    # Log top features
    sorted_imp = sorted(importance.items(), key=lambda x: x[1], reverse=True)
    logger.info("Top-10 feature importances:")
    for name, imp in sorted_imp[:10]:
        logger.info(f"  {name}: {imp:.4f}")

    # Calculate Sharpe from predictions
    _, sharpe, pf, wr, mdd, nt = _evaluate_subset(features, labels, ohlcv)

    registry.record(
        description=f"Full enriched ({features.shape[1]}D)",
        dimensions_used=list(features.columns),
        dimensions_excluded=[],
        ticker=ticker, timeframe=timeframe,
        n_samples=len(features),
        accuracy=full_acc,
        sharpe=sharpe,
        profit_factor=pf,
        win_rate=wr,
        max_drawdown=mdd,
        n_trades=nt,
    )

    # ── Experiment 2: Backward elimination ──
    logger.info("\n═══ Backward Elimination ═══")
    optimal_features, optimal_acc = backward_elimination(
        features, labels, importance,
    )

    # Re-run final model with optimal features
    _, sharpe_opt, pf_opt, wr_opt, mdd_opt, nt_opt = _evaluate_subset(
        features[optimal_features], labels, ohlcv,
    )

    excluded = [f for f in features.columns if f not in optimal_features]
    registry.record(
        description=f"Optimized ({len(optimal_features)}D)",
        dimensions_used=optimal_features,
        dimensions_excluded=excluded,
        ticker=ticker, timeframe=timeframe,
        n_samples=len(features),
        accuracy=optimal_acc,
        sharpe=sharpe_opt,
        profit_factor=pf_opt,
        win_rate=wr_opt,
        max_drawdown=mdd_opt,
        n_trades=nt_opt,
    )

    # ── Print summary ──
    logger.info("\n" + registry.summary_table())
    store.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Quaternion Feature Discovery")
    parser.add_argument("--ticker", default="SPY", help="Ticker to analyze")
    parser.add_argument("--tf", default="1d", help="Timeframe")
    args = parser.parse_args()

    run_discovery(ticker=args.ticker, timeframe=args.tf)
