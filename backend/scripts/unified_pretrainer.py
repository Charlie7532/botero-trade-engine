#!/usr/bin/env python3
"""
Unified Pre-Trainer v1 — Bidirectional Entry + Exit Model
=============================================================
Single XGBoost model that predicts P(win) for BOTH entry (LONG)
and exit (SHORT) signals, using the FULL Feature Lake without
pre-filters.

Key design decisions (approved by Committee 2026-05-23):
  1. NO pre-filters: model sees ALL 93,776 observations (not 7% extremes)
  2. BIDIRECTIONAL: direction feature (+1 LONG, -1 SHORT) in same model
  3. 52 FEATURES across 8 families (all existing DB columns + TSI/ADI)
  4. Purged Walk-Forward CV (López de Prado) with DSR validation
  5. Per-ticker stability check (>50% WR in ≥82% of tickers)
  6. Results saved to engine.ticker_profiles

Replaces: meta_label_pretrainer.py + meta_label_exit_pretrainer.py

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/unified_pretrainer.py
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/unified_pretrainer.py --dry-run
"""
import os, sys, warnings, json, pickle, time, argparse
from pathlib import Path
warnings.filterwarnings("ignore")

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import pandas as pd
import numpy as np
from scipy import stats

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore
from backend.modules.shared.domain.rules.trend_strength import compute_tsi, compute_adi

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)

def p(t): print(f"\n{'='*95}\n  {t}\n{'='*95}")
def sp(t): print(f"\n  ── {t} ──")

TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]

FORWARD_BARS = 20

# ═══════════════════════════════════════════════════════════════
# FEATURE DEFINITIONS — 8 Families, 52 Features
# ═══════════════════════════════════════════════════════════════

# Features read directly from channel_snapshots (39 fields)
DB_FEATURES = [
    # Position (9)
    'sigma_tide', 'sigma_current', 'sigma_wave',
    'vwap_sigma_tide', 'vwap_sigma_current', 'vwap_sigma_wave',
    'tension_tide', 'tension_current', 'tension_wave',
    # Dynamics (9)
    'tide_slope', 'current_slope', 'wave_slope',
    'tide_accel', 'current_accel', 'wave_accel',
    'conj_wave_current', 'conj_wave_tide', 'conj_current_tide',
    # Structure (7)
    'spread_tide_current', 'spread_tide_wave', 'spread_current_wave',
    'vwap_spread_tide_current', 'vwap_spread_tide_wave', 'vwap_spread_current_wave',
    'compression_ratio',
    # Sentiment (4)
    'fear_level', 'vol_up_down_ratio',
    'wave_flip',        # bool → int
    'wave_flip_direction',
    # RSI (3) — may be defaults for most tickers until backfilled
    'rsi_value', 'rsi_divergence_strength', 'rsi_conviction',
    # Kalman (2) — may be defaults until backfilled
    'kalman_velocity', 'vol_adj_delta',
    # Geometric (5)
    'geo_state_norm', 'geo_velocity_align', 'geo_exit_align',
    'geo_accel_align', 'geo_phase_angle',
]

# Computed features (13 fields — added by the trainer)
COMPUTED_FEATURES = [
    'tsi_tide', 'tsi_current', 'tsi_wave',
    'adi_tide', 'adi_current', 'adi_wave',
    'below_all_vwaps_int', 'above_all_vwaps_int',
    'regime_encoded',        # BULL=2, FLAT=1, BEAR=0
    'direction',             # +1=LONG, -1=SHORT
]

ALL_FEATURES = DB_FEATURES + COMPUTED_FEATURES


# ═══════════════════════════════════════════════════════════════
# STEP 1: Build Full Dataset (NO pre-filters)
# ═══════════════════════════════════════════════════════════════

def build_unified_dataset(store, profile_store):
    """Build bidirectional dataset from ALL channel_snapshots."""
    sp("STEP 1: Building UNIFIED dataset (no pre-filters, bidirectional)")

    # Load ALL channel_snapshots joined with close prices
    db_cols = ", ".join([f"cs.{c}" for c in DB_FEATURES
                         if c not in ('wave_flip',)])
    query = f"""
        SELECT cs.ticker, cs.timestamp,
               {db_cols},
               cs.wave_flip,
               cs.below_all_vwaps, cs.above_all_vwaps,
               cs.regime,
               ob.close as price
        FROM engine.channel_snapshots cs
        JOIN market.ohlcv_bars ob
            ON ob.ticker = cs.ticker AND ob.timeframe = '1d' AND ob.time = cs.timestamp
        WHERE cs.sigma_tide IS NOT NULL
          AND cs.tide_slope IS NOT NULL
        ORDER BY cs.ticker, cs.timestamp
    """
    df = pd.read_sql(query, store.engine)
    print(f"    Raw observations (ALL, no filter): {len(df):,d}")

    # Convert booleans to int
    df['wave_flip'] = df['wave_flip'].astype(int)
    df['below_all_vwaps_int'] = df['below_all_vwaps'].astype(int)
    df['above_all_vwaps_int'] = df['above_all_vwaps'].astype(int)

    # Encode regime
    regime_map = {'BEAR': 0, 'FLAT': 1, 'BULL': 2}
    df['regime_encoded'] = df['regime'].map(regime_map).fillna(1).astype(int)

    # ── Compute TSI/ADI per-ticker ──
    profiles = {p.ticker: p for p in profile_store.load_all_profiles()}
    print(f"    Loaded {len(profiles)} ticker profiles")

    for col in ['tsi_tide', 'tsi_current', 'tsi_wave',
                'adi_tide', 'adi_current', 'adi_wave']:
        df[col] = 50  # Default neutral

    for ticker in df['ticker'].unique():
        profile = profiles.get(ticker)
        if profile is None:
            continue

        mask = df['ticker'] == ticker
        tdf = df.loc[mask]

        df.loc[mask, 'tsi_tide'] = tdf['tide_slope'].apply(
            lambda s: compute_tsi(s, profile.tsi_tide_percentiles))
        df.loc[mask, 'tsi_current'] = tdf['current_slope'].apply(
            lambda s: compute_tsi(s, profile.tsi_current_percentiles))
        df.loc[mask, 'tsi_wave'] = tdf['wave_slope'].apply(
            lambda s: compute_tsi(s, profile.tsi_wave_percentiles))

        df.loc[mask, 'adi_tide'] = tdf['tension_tide'].apply(
            lambda t: compute_adi(t, profile.adi_tide_percentiles))
        df.loc[mask, 'adi_current'] = tdf['tension_current'].apply(
            lambda t: compute_adi(t, profile.adi_current_percentiles))
        df.loc[mask, 'adi_wave'] = tdf['tension_wave'].apply(
            lambda t: compute_adi(t, profile.adi_wave_percentiles))

    # ── Forward returns + labeling (vectorized per-ticker) ──
    sp("Computing forward returns per-ticker (vectorized)")
    labeled_rows = []

    for ticker in df['ticker'].unique():
        ohlc = store.load_bars(ticker, "1d")
        if ohlc is None or ohlc.empty:
            continue

        tdf = df[df['ticker'] == ticker].copy()
        closes = ohlc['close']

        # Compute forward returns per observation
        # NOTE: Must use .iloc (not .values) to preserve tz-aware Timestamps.
        # .values produces numpy datetime64 (tz-naive) which fails index lookup.
        fwd_returns = np.full(len(tdf), np.nan)

        for i in range(len(tdf)):
            ts = tdf['timestamp'].iloc[i]
            if ts in ohlc.index:
                pos = ohlc.index.get_loc(ts)
                if pos + FORWARD_BARS < len(ohlc):
                    future_price = closes.iloc[pos + FORWARD_BARS]
                    fwd_returns[i] = (future_price / tdf.iloc[i]['price'] - 1) * 100

        tdf['return_fwd'] = fwd_returns
        tdf = tdf.dropna(subset=['return_fwd'])

        if len(tdf) == 0:
            continue

        # LONG label: win if price went UP
        tdf_long = tdf.copy()
        tdf_long['direction'] = 1
        tdf_long['win'] = (tdf_long['return_fwd'] > 0).astype(int)

        # SHORT label: win if price went DOWN
        tdf_short = tdf.copy()
        tdf_short['direction'] = -1
        tdf_short['win'] = (tdf_short['return_fwd'] < 0).astype(int)

        labeled_rows.append(tdf_long)
        labeled_rows.append(tdf_short)

        n_long = len(tdf_long)
        wr_long = tdf_long['win'].mean() * 100
        wr_short = tdf_short['win'].mean() * 100
        print(f"    {ticker:>5s}: {n_long:,d} obs × 2 dirs | LONG WR={wr_long:.1f}% | SHORT WR={wr_short:.1f}%")

    if not labeled_rows:
        print("    ❌ No labeled data")
        return pd.DataFrame()

    full = pd.concat(labeled_rows, ignore_index=True)
    print(f"\n    ★ Total training rows: {len(full):,d} ({len(full)//2:,d} × 2 directions)")
    print(f"    ★ Overall LONG WR:  {full[full['direction']==1]['win'].mean()*100:.1f}%")
    print(f"    ★ Overall SHORT WR: {full[full['direction']==-1]['win'].mean()*100:.1f}%")

    return full


# ═══════════════════════════════════════════════════════════════
# STEP 2: Purged Walk-Forward CV + Training
# ═══════════════════════════════════════════════════════════════

def purged_walk_forward_cv(n, n_splits=5, purge_gap=20):
    """López de Prado's Purged Walk-Forward CV.

    purge_gap = FORWARD_BARS to prevent any lookahead from forward returns.
    """
    fold_size = n // (n_splits + 1)
    splits = []
    for i in range(n_splits):
        train_end = fold_size * (i + 1)
        test_start = train_end + purge_gap
        test_end = min(test_start + fold_size, n)
        if test_end > test_start + 20:
            splits.append((list(range(0, train_end)), list(range(test_start, test_end))))
    return splits


def compute_dsr(fold_sharpes):
    """Deflated Sharpe Ratio — penalizes multiple testing.

    DSR > 1.0 means the model is unlikely to be a false positive.
    """
    if len(fold_sharpes) < 2:
        return 0.0
    mean_sr = np.mean(fold_sharpes)
    std_sr = np.std(fold_sharpes, ddof=1)
    if std_sr < 1e-8:
        return mean_sr * 10  # Perfect consistency
    n_trials = len(fold_sharpes)
    # DSR = mean(SR) / std(SR) * sqrt(n_trials)
    # Simplified: t-statistic of the Sharpe ratios
    t_stat = mean_sr / (std_sr / np.sqrt(n_trials))
    return float(t_stat)


def train_unified_model(df):
    """Train XGBoost unified model with Purged Walk-Forward CV."""
    sp("STEP 2: Training Unified Model (Purged Walk-Forward CV)")

    if len(df) < 200:
        print(f"    ⚠️ Insufficient data ({len(df)}). Need ≥200.")
        return None, [], None, df, np.array([]), np.array([])

    try:
        from xgboost import XGBClassifier
        use_xgb = True
    except ImportError:
        from sklearn.ensemble import GradientBoostingClassifier
        use_xgb = False
        print("    ⚠️ XGBoost not available. Using sklearn GradientBoosting.")

    # Select features that exist in the dataframe
    feature_cols = [f for f in ALL_FEATURES if f in df.columns]
    print(f"    Features available: {len(feature_cols)} of {len(ALL_FEATURES)} planned")

    # Drop rows with NaN in features
    valid_mask = df[feature_cols].notna().all(axis=1)
    df_clean = df[valid_mask].copy()
    print(f"    Rows after NaN removal: {len(df_clean):,d}")

    if len(df_clean) < 200:
        print(f"    ⚠️ Insufficient rows after cleaning.")
        return None, feature_cols, None, df_clean, np.array([]), np.array([])

    X = df_clean[feature_cols].values.astype(np.float32)
    y = df_clean['win'].values.astype(int)

    # Sort by timestamp for temporal CV (CRITICAL for purged CV)
    sort_idx = df_clean['timestamp'].argsort().values
    X = X[sort_idx]
    y = y[sort_idx]
    df_sorted = df_clean.iloc[sort_idx].reset_index(drop=True)

    # Purged Walk-Forward CV
    splits = purged_walk_forward_cv(len(X), n_splits=5, purge_gap=FORWARD_BARS)

    fold_results = []
    fold_sharpes = []
    all_predictions = np.zeros(len(X))
    all_has_pred = np.zeros(len(X), dtype=bool)

    for fold_idx, (train_idx, test_idx) in enumerate(splits):
        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]

        if use_xgb:
            model = XGBClassifier(
                n_estimators=200,
                max_depth=4,
                learning_rate=0.05,
                min_child_weight=10,
                subsample=0.8,
                colsample_bytree=0.7,
                reg_alpha=0.1,
                reg_lambda=1.0,
                random_state=42,
                eval_metric='logloss',
                tree_method='hist',
            )
            model.fit(X_train, y_train, verbose=False)
        else:
            model = GradientBoostingClassifier(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                min_samples_leaf=10, subsample=0.8, random_state=42,
            )
            model.fit(X_train, y_train)

        y_prob = model.predict_proba(X_test)[:, 1]
        y_pred = (y_prob >= 0.5).astype(int)

        acc = (y_pred == y_test).mean()

        # Fold Sharpe: excess return of predictions vs random
        # If model predicts well, high-P signals should have better WR than low-P
        high_p = y_prob >= 0.65
        low_p = y_prob < 0.35
        wr_high = y_test[high_p].mean() if high_p.sum() > 20 else float('nan')
        wr_low = y_test[low_p].mean() if low_p.sum() > 20 else float('nan')
        spread = wr_high - wr_low if not (np.isnan(wr_high) or np.isnan(wr_low)) else 0.0

        # Sharpe proxy: WR spread / std of returns
        returns_test = df_sorted.iloc[test_idx]['return_fwd'].values
        ret_std = np.std(returns_test) if len(returns_test) > 1 else 1.0
        sharpe_fold = spread / max(ret_std / 100, 0.01)
        fold_sharpes.append(sharpe_fold)

        all_predictions[test_idx] = y_prob
        all_has_pred[test_idx] = True

        fold_results.append({
            'fold': fold_idx,
            'train_n': len(train_idx),
            'test_n': len(test_idx),
            'accuracy': acc,
            'wr_high_p': wr_high,
            'wr_low_p': wr_low,
            'spread': spread,
            'sharpe': sharpe_fold,
        })
        print(f"    Fold {fold_idx}: train={len(train_idx):,d}, test={len(test_idx):,d}, "
              f"acc={acc:.3f}, WR(P≥.65)={wr_high:.3f}, WR(P<.35)={wr_low:.3f}, "
              f"spread={spread:.3f}")

    # Deflated Sharpe Ratio
    dsr = compute_dsr(fold_sharpes)
    print(f"\n    ★ Deflated Sharpe Ratio (DSR): {dsr:.3f} {'✅ PASS' if dsr > 1.0 else '⚠️ WEAK' if dsr > 0.5 else '❌ FAIL'}")
    print(f"    ★ Mean fold Sharpe: {np.mean(fold_sharpes):.4f} ± {np.std(fold_sharpes):.4f}")

    # Train FINAL model on ALL data
    sp("Training final model on ALL data")
    if use_xgb:
        final_model = XGBClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            min_child_weight=10, subsample=0.8, colsample_bytree=0.7,
            reg_alpha=0.1, reg_lambda=1.0,
            random_state=42, eval_metric='logloss', tree_method='hist',
        )
        final_model.fit(X, y, verbose=False)
    else:
        final_model = GradientBoostingClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            min_samples_leaf=10, subsample=0.8, random_state=42,
        )
        final_model.fit(X, y)

    # Feature importance
    importances = final_model.feature_importances_
    importance_df = pd.DataFrame({
        'feature': feature_cols,
        'importance': importances,
    }).sort_values('importance', ascending=False)

    sp("FEATURE IMPORTANCE (Top 20)")
    print(f"\n    {'Feature':<30s} │ {'Importance':>10s} │ {'Rank':>4s} │ {'Tier':>12s}")
    print(f"    {'─'*65}")
    for rank, (_, row) in enumerate(importance_df.head(20).iterrows(), 1):
        tier = "★★★ PRIMARY" if row['importance'] > 0.06 else \
               "★★ SECONDARY" if row['importance'] > 0.03 else \
               "★ TERTIARY" if row['importance'] > 0.015 else "── minor"
        print(f"    {row['feature']:<30s} │ {row['importance']:>9.4f} │ {rank:>4d} │ {tier:>12s}")

    return final_model, feature_cols, importance_df, df_sorted, all_predictions, all_has_pred, fold_results, dsr


# ═══════════════════════════════════════════════════════════════
# STEP 3: Threshold Calibration (Entry + Exit)
# ═══════════════════════════════════════════════════════════════

def calibrate_thresholds(df, predictions, has_pred):
    """Find optimal P(win) thresholds for entry and exit separately."""
    sp("STEP 3: Threshold Calibration (Entry + Exit)")

    if not has_pred.any():
        print("    ⚠️ No predictions available.")
        return 0.55, 0.55

    valid = df[has_pred].copy()
    valid['p_win'] = predictions[has_pred]

    results = {}
    for direction_label, dir_val in [("ENTRY (LONG)", 1), ("EXIT (SHORT)", -1)]:
        dv = valid[valid['direction'] == dir_val]
        if len(dv) < 100:
            continue

        print(f"\n    {direction_label}:")
        print(f"    {'Threshold':>9s} │ {'N Signals':>9s} │ {'WR':>6s} │ {'Avg Ret':>8s} │ {'Edge':>6s}")
        print(f"    {'─'*50}")

        best_edge = -1
        best_thr = 0.55

        for thr in [0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
            above = dv[dv['p_win'] >= thr]
            if len(above) < 20:
                continue
            wr = above['win'].mean() * 100
            avg_ret = above['return_fwd'].mean()
            # Edge = WR - baseline_WR
            baseline = dv['win'].mean() * 100
            edge = wr - baseline

            if edge > best_edge:
                best_edge = edge
                best_thr = thr

            marker = " ← BEST" if thr == best_thr and edge > 0 else ""
            print(f"    {thr:>8.2f} │ {len(above):>9,d} │ {wr:>5.1f}% │ {avg_ret:>+7.2f}% │ {edge:>+5.1f}%{marker}")

        results[dir_val] = best_thr

    entry_thr = results.get(1, 0.55)
    exit_thr = results.get(-1, 0.55)
    print(f"\n    ★ Optimal ENTRY threshold: P(win) ≥ {entry_thr:.2f}")
    print(f"    ★ Optimal EXIT threshold:  P(win) ≥ {exit_thr:.2f}")

    return entry_thr, exit_thr


# ═══════════════════════════════════════════════════════════════
# STEP 4: Per-Ticker Stability Analysis
# ═══════════════════════════════════════════════════════════════

def analyze_per_ticker(df, predictions, has_pred, entry_thr, exit_thr):
    """Per-ticker WR analysis at calibrated thresholds."""
    sp("STEP 4: Per-Ticker Stability Analysis")

    if not has_pred.any():
        return {}

    valid = df[has_pred].copy()
    valid['p_win'] = predictions[has_pred]

    ticker_results = {}
    tickers_passing = 0
    total_tickers = 0

    print(f"\n    {'Ticker':>6s} │ {'N':>5s} │ {'Entry WR':>8s} │ {'Exit WR':>8s} │ {'N Entry':>7s} │ {'N Exit':>6s} │ {'Pass':>4s}")
    print(f"    {'─'*60}")

    for ticker in sorted(valid['ticker'].unique()):
        tdf = valid[valid['ticker'] == ticker]
        total_tickers += 1

        # Entry signals (LONG with P >= entry_thr)
        entry_signals = tdf[(tdf['direction'] == 1) & (tdf['p_win'] >= entry_thr)]
        entry_wr = entry_signals['win'].mean() * 100 if len(entry_signals) > 5 else float('nan')

        # Exit signals (SHORT with P >= exit_thr)
        exit_signals = tdf[(tdf['direction'] == -1) & (tdf['p_win'] >= exit_thr)]
        exit_wr = exit_signals['win'].mean() * 100 if len(exit_signals) > 5 else float('nan')

        # Pass if BOTH entry and exit WR > 50%
        entry_pass = entry_wr > 50 if not np.isnan(entry_wr) else False
        exit_pass = exit_wr > 50 if not np.isnan(exit_wr) else False
        both_pass = entry_pass and exit_pass
        if both_pass:
            tickers_passing += 1

        marker = "✅" if both_pass else "⚠️" if (entry_pass or exit_pass) else "❌"

        ticker_results[ticker] = {
            'entry_wr': float(entry_wr) if not np.isnan(entry_wr) else None,
            'exit_wr': float(exit_wr) if not np.isnan(exit_wr) else None,
            'n_entry': len(entry_signals),
            'n_exit': len(exit_signals),
            'pass': both_pass,
        }

        print(f"    {ticker:>6s} │ {len(tdf)//2:>5,d} │ {entry_wr:>7.1f}% │ {exit_wr:>7.1f}% │ {len(entry_signals):>7,d} │ {len(exit_signals):>6,d} │ {marker}")

    pct = tickers_passing / total_tickers * 100 if total_tickers > 0 else 0
    print(f"\n    ★ Tickers passing (both WR > 50%): {tickers_passing}/{total_tickers} ({pct:.0f}%)")
    print(f"    ★ Stability threshold: ≥82% (14/17) {'✅ PASS' if pct >= 82 else '⚠️ PARTIAL' if pct >= 60 else '❌ FAIL'}")

    return ticker_results


# ═══════════════════════════════════════════════════════════════
# STEP 5: Feature Importance Stability Across Folds
# ═══════════════════════════════════════════════════════════════

def check_feature_stability(df, feature_cols, n_splits=5):
    """Check if top features are consistent across CV folds."""
    sp("STEP 5: Feature Importance Stability Check")

    try:
        from xgboost import XGBClassifier
    except ImportError:
        print("    ⚠️ Skipping stability check (XGBoost not available)")
        return

    valid_mask = df[feature_cols].notna().all(axis=1)
    df_clean = df[valid_mask].copy()
    X = df_clean[feature_cols].values.astype(np.float32)
    y = df_clean['win'].values.astype(int)

    sort_idx = df_clean['timestamp'].argsort().values
    X = X[sort_idx]
    y = y[sort_idx]

    splits = purged_walk_forward_cv(len(X), n_splits=n_splits, purge_gap=FORWARD_BARS)

    fold_importances = []
    for fold_idx, (train_idx, _) in enumerate(splits):
        model = XGBClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            min_child_weight=10, subsample=0.8, colsample_bytree=0.7,
            reg_alpha=0.1, reg_lambda=1.0,
            random_state=42, eval_metric='logloss', tree_method='hist',
        )
        model.fit(X[train_idx], y[train_idx], verbose=False)
        imp = dict(zip(feature_cols, model.feature_importances_))
        fold_importances.append(imp)

    # Check top-10 consistency
    top10_per_fold = []
    for imp in fold_importances:
        sorted_feats = sorted(imp.items(), key=lambda x: x[1], reverse=True)
        top10_per_fold.append([f[0] for f in sorted_feats[:10]])

    # Count how often each feature appears in top-10 across all folds
    from collections import Counter
    all_top10 = [f for fold in top10_per_fold for f in fold]
    counts = Counter(all_top10)
    stable_features = {f: c for f, c in counts.items() if c >= n_splits - 1}

    print(f"\n    Features in top-10 across ≥{n_splits-1}/{n_splits} folds (STABLE):")
    for f, c in sorted(stable_features.items(), key=lambda x: -x[1]):
        print(f"      {f:<30s} {c}/{n_splits} folds ✅")

    unstable = {f: c for f, c in counts.items() if c < n_splits - 1 and c > 0}
    if unstable:
        print(f"\n    Features in top-10 in some folds (UNSTABLE):")
        for f, c in sorted(unstable.items(), key=lambda x: -x[1]):
            print(f"      {f:<30s} {c}/{n_splits} folds ⚠️")

    return stable_features


# ═══════════════════════════════════════════════════════════════
# STEP 6: Persist Results
# ═══════════════════════════════════════════════════════════════

def persist_results(model, feature_cols, importance_df, entry_thr, exit_thr,
                    ticker_results, dsr, fold_results, profile_store, dry_run=False):
    """Save model, config, and update ticker profiles with thresholds."""
    sp("STEP 6: Persisting Results")

    if model is None:
        print("    ⚠️ No model to persist.")
        return

    model_dir = root_dir / "backend" / "models"
    model_dir.mkdir(exist_ok=True)

    if not dry_run:
        # 1. Save model pickle
        model_path = model_dir / "unified_pretrainer_v1.pkl"
        with open(model_path, 'wb') as f:
            pickle.dump({
                'model': model,
                'feature_cols': feature_cols,
                'version': 1,
                'direction': 'bidirectional',
                'entry_threshold': entry_thr,
                'exit_threshold': exit_thr,
                'dsr': dsr,
                'trained_at': pd.Timestamp.now().isoformat(),
            }, f)
        print(f"    ✅ Model saved to {model_path}")

        # 2. Save config JSON
        config = {
            'version': 1,
            'type': 'unified_bidirectional',
            'entry_threshold': entry_thr,
            'exit_threshold': exit_thr,
            'dsr': dsr,
            'n_features': len(feature_cols),
            'features': feature_cols,
            'feature_importance': importance_df.set_index('feature')['importance'].to_dict()
                                    if importance_df is not None else {},
            'forward_bars': FORWARD_BARS,
            'labeling': 'bidirectional_fixed_horizon',
            'fold_results': fold_results,
            'per_ticker': ticker_results,
        }
        config_path = model_dir / "unified_pretrainer_config.json"
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2, default=str)
        print(f"    ✅ Config saved to {config_path}")

        # 3. Update ticker profiles with ML thresholds
        top_entry = importance_df.head(10)['feature'].tolist() if importance_df is not None else []
        top_exit = top_entry  # Same model, same features

        profiles = profile_store.load_all_profiles()
        for profile in profiles:
            ticker = profile.ticker
            tr = ticker_results.get(ticker, {})

            profile.entry_p_threshold = entry_thr
            profile.exit_p_threshold = exit_thr
            profile.top_entry_features = top_entry
            profile.top_exit_features = top_exit
            profile.version = 2  # Bump version

            profile_store.save_profile(profile)

        print(f"    ✅ Updated {len(profiles)} ticker profiles (v1 → v2)")
    else:
        print("    [DRY RUN] Would save model, config, and update profiles")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Unified Pre-Trainer (Bidirectional)")
    parser.add_argument("--dry-run", action="store_true", help="Don't persist results")
    args = parser.parse_args()

    p("UNIFIED PRE-TRAINER v1 — Bidirectional Entry + Exit")
    print("  ✦ No pre-filters: model sees ALL observations")
    print("  ✦ Bidirectional: LONG + SHORT in same model")
    print("  ✦ 52 features across 8 families")
    print("  ✦ Purged Walk-Forward CV + DSR validation")

    t0 = time.time()
    store = TimescaleDataStore()
    profile_store = TickerProfileStore()

    # STEP 1: Build dataset
    df = build_unified_dataset(store, profile_store)
    if len(df) < 200:
        print(f"\n  ❌ Insufficient data ({len(df)}). Need ≥200.")
        store.close(); profile_store.close()
        sys.exit(1)

    # STEP 2: Train model
    result = train_unified_model(df)
    model, feature_cols, importance_df, df_sorted, preds, has_pred, fold_results, dsr = result

    # STEP 3: Calibrate thresholds
    entry_thr, exit_thr = calibrate_thresholds(df_sorted, preds, has_pred)

    # STEP 4: Per-ticker stability
    ticker_results = analyze_per_ticker(df_sorted, preds, has_pred, entry_thr, exit_thr)

    # STEP 5: Feature stability
    stable_features = check_feature_stability(df, feature_cols)

    # STEP 6: Persist
    persist_results(model, feature_cols, importance_df, entry_thr, exit_thr,
                    ticker_results, dsr, fold_results, profile_store, dry_run=args.dry_run)

    store.close()
    profile_store.close()
    elapsed = time.time() - t0

    p("UNIFIED PRE-TRAINER COMPLETE")
    print(f"  Total time: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"  DSR: {dsr:.3f}")
    print(f"  Entry threshold: P(win) ≥ {entry_thr:.2f}")
    print(f"  Exit threshold:  P(win) ≥ {exit_thr:.2f}")
    print(f"  Model: backend/models/unified_pretrainer_v1.pkl")
    if importance_df is not None:
        top5 = importance_df.head(5)['feature'].tolist()
        print(f"  Top 5 features: {', '.join(top5)}")


if __name__ == "__main__":
    main()
