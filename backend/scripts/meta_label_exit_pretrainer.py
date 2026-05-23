#!/usr/bin/env python3
"""
Meta-Label EXIT Pre-Trainer — Calibrates Trim/Exit Gate + Per-Ticker Profiles
=================================================================================
Strategy-agnostic trainer for "trim" signals (direction="short"/exit).
Mirrors meta_label_pretrainer.py architecture but with INVERTED labeling.

Reads from engine.channel_snapshots (Feature Lake) + market.ohlcv_bars.
Trains XGBoost meta-label model with Purged Walk-Forward CV.

LABELING DECISION (Audited, Deliberate):
    An entry asks: "Will I profit?"     → needs Triple Barrier (asymmetric, path-dependent)
    A trim asks:   "Should I reduce?"   → needs fixed-horizon: "did price drop?"
    win = 1 if future_price < current_price else 0
    This is correct because a trim has no stop loss — only "was I right to reduce?"

Feature set (29 features):
    1-9:   sigma_{t,c,w}, vwap_sigma_{t,c,w}, slopes × 3      (ChannelSnapshot)
    10-12: accel_{t,c,w}                                        (ChannelSnapshot)
    13-15: conj_{w_c, w_t, c_t}                                 (ChannelSnapshot)
    16-18: spread_{t_c, t_w, c_w}                               (ChannelSnapshot)
    19-20: fear_level, vol_up_down_ratio                         (ChannelSnapshot)
    21-23: tension_{t,c,w}                                      (NEW)
    24:    compression_ratio                                     (NEW)
    25-29: geo_{state_norm, vel_align, exit_align, accel_align, phase}  (NEW)

Outputs:
  1. Global feature importance → which features predict successful trims
  2. Global optimal thresholds → default exit/trim thresholds
  3. Per-ticker exit profiles → adaptive trim thresholds per symbol
  4. Trained exit model → pickled for production use

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/meta_label_exit_pretrainer.py
"""
import os, sys, warnings, json, pickle, time
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

def p(t): print(f"\n{'='*95}\n  {t}\n{'='*95}")
def sp(t): print(f"\n  ── {t} ──")

TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]

# 29 features: original 20 + 4 tensions/compression + 5 geometric
FEATURES = [
    # Original 20 from entry pretrainer
    'sigma_tide', 'sigma_current', 'sigma_wave',
    'vwap_sigma_tide', 'vwap_sigma_current', 'vwap_sigma_wave',
    'tide_slope', 'current_slope', 'wave_slope',
    'tide_accel', 'current_accel', 'wave_accel',
    'conj_wave_current', 'conj_wave_tide', 'conj_current_tide',
    'spread_tide_current', 'spread_tide_wave', 'spread_current_wave',
    'fear_level', 'vol_up_down_ratio',
    # 4 NEW: tensions + compression (Fase 2A)
    'tension_tide', 'tension_current', 'tension_wave',
    'compression_ratio',
    # 5 NEW: geometric features (Fase 2A)
    'geo_state_norm', 'geo_velocity_align', 'geo_exit_align',
    'geo_accel_align', 'geo_phase_angle',
]

FORWARD_BARS = 20  # Must match meta_label_pretrainer.py for consistency


# ═══════════════════════════════════════════════════════════
# STEP 1: Build Exit-Labeled Dataset from Feature Lake
# ═══════════════════════════════════════════════════════════

def build_exit_dataset(store):
    """Build dataset for EXIT/TRIM signals.

    Exit signal candidates: price is HIGH within the channel (σ > +1.5).
    This is the inverse of the entry pretrainer which looks for σ < -2.0.

    Labeling: win = 1 if price DROPPED after 20 bars (trim was correct).
    """
    sp("STEP 1: Building EXIT labeled dataset from Feature Lake")

    query = """
        SELECT cs.ticker, cs.timestamp,
               cs.sigma_tide, cs.sigma_current, cs.sigma_wave,
               cs.vwap_sigma_tide, cs.vwap_sigma_current, cs.vwap_sigma_wave,
               cs.tide_slope, cs.current_slope, cs.wave_slope,
               cs.tide_accel, cs.current_accel, cs.wave_accel,
               cs.conj_wave_current, cs.conj_wave_tide, cs.conj_current_tide,
               cs.spread_tide_current, cs.spread_tide_wave, cs.spread_current_wave,
               cs.fear_level, cs.vol_up_down_ratio,
               cs.tension_tide, cs.tension_current, cs.tension_wave,
               cs.compression_ratio,
               cs.geo_state_norm, cs.geo_velocity_align, cs.geo_exit_align,
               cs.geo_accel_align, cs.geo_phase_angle,
               cs.vwap_spread_tide_current, cs.vwap_spread_tide_wave,
               cs.vwap_spread_current_wave,
               cs.regime, cs.above_all_vwaps,
               ob.close as price
        FROM engine.channel_snapshots cs
        JOIN market.ohlcv_bars ob
            ON ob.ticker = cs.ticker AND ob.timeframe = '1d' AND ob.time = cs.timestamp
        WHERE cs.sigma_tide > 1.5
          AND cs.vwap_sigma_wave > 1.0
          AND cs.above_all_vwaps = true
        ORDER BY cs.ticker, cs.timestamp
    """
    df = pd.read_sql(query, store.engine)
    print(f"    Raw OVEREXTENDED signals (σ>1.5 + above VWAPs): {len(df):,d}")

    if len(df) == 0:
        # Fallback: less restrictive filter if few overextended signals
        print("    ⚠️ No signals with strict filter. Trying σ_tide > 1.0...")
        query_fallback = """
            SELECT cs.ticker, cs.timestamp,
                   cs.sigma_tide, cs.sigma_current, cs.sigma_wave,
                   cs.vwap_sigma_tide, cs.vwap_sigma_current, cs.vwap_sigma_wave,
                   cs.tide_slope, cs.current_slope, cs.wave_slope,
                   cs.tide_accel, cs.current_accel, cs.wave_accel,
                   cs.conj_wave_current, cs.conj_wave_tide, cs.conj_current_tide,
                   cs.spread_tide_current, cs.spread_tide_wave, cs.spread_current_wave,
                   cs.fear_level, cs.vol_up_down_ratio,
                   cs.tension_tide, cs.tension_current, cs.tension_wave,
                   cs.compression_ratio,
                   cs.geo_state_norm, cs.geo_velocity_align, cs.geo_exit_align,
                   cs.geo_accel_align, cs.geo_phase_angle,
                   cs.vwap_spread_tide_current, cs.vwap_spread_tide_wave,
                   cs.vwap_spread_current_wave,
                   cs.regime, cs.above_all_vwaps,
                   ob.close as price
            FROM engine.channel_snapshots cs
            JOIN market.ohlcv_bars ob
                ON ob.ticker = cs.ticker AND ob.timeframe = '1d' AND ob.time = cs.timestamp
            WHERE cs.sigma_tide > 1.0
            ORDER BY cs.ticker, cs.timestamp
        """
        df = pd.read_sql(query_fallback, store.engine)
        print(f"    Fallback signals (σ>1.0): {len(df):,d}")

    if len(df) == 0:
        print("    ❌ No exit signals found. Run backfill first.")
        return pd.DataFrame()

    # Add forward return — INVERTED: win if price DROPS
    results = []
    for ticker in df['ticker'].unique():
        ohlc = store.load_bars(ticker, "1d")
        if ohlc is None or ohlc.empty:
            continue
        tdf = df[df['ticker'] == ticker].copy()
        closes = ohlc['close']

        for idx, row in tdf.iterrows():
            ts = row['timestamp']
            if ts in ohlc.index:
                pos = ohlc.index.get_loc(ts)
                if pos + FORWARD_BARS < len(ohlc):
                    future_price = closes.iloc[pos + FORWARD_BARS]
                    tdf.loc[idx, 'return_fwd'] = (future_price / row['price'] - 1) * 100
                    # INVERTED: win if price DROPPED (trim was correct)
                    tdf.loc[idx, 'win'] = 1 if future_price < row['price'] else 0

        results.append(tdf)
        print(f"      {ticker}: {len(tdf)} exit signals")

    if not results:
        return pd.DataFrame()

    full = pd.concat(results, ignore_index=True)
    full = full.dropna(subset=['return_fwd', 'win'])

    print(f"    Labeled exit signals: {len(full):,d}")
    print(f"    Trim success rate: {full['win'].mean()*100:.1f}%")
    print(f"    Avg post-trim drop: {full['return_fwd'].mean():+.2f}%")
    return full


# ═══════════════════════════════════════════════════════════
# STEP 2: Purged Walk-Forward Cross-Validation
# ═══════════════════════════════════════════════════════════

def purged_walk_forward_cv(X, y, n_splits=5, purge_gap=10):
    """López de Prado's Purged Walk-Forward CV.

    Identical to entry pretrainer — temporal ordering, no leakage.
    """
    n = len(X)
    fold_size = n // (n_splits + 1)
    splits = []

    for i in range(n_splits):
        train_end = fold_size * (i + 1)
        test_start = train_end + purge_gap
        test_end = min(test_start + fold_size, n)

        if test_end > test_start + 10:
            train_idx = list(range(0, train_end))
            test_idx = list(range(test_start, test_end))
            splits.append((train_idx, test_idx))

    return splits


def train_exit_model(df):
    """Train XGBoost exit meta-label with Purged Walk-Forward CV."""
    sp("STEP 2: Training Exit Meta-Label Model (Purged Walk-Forward CV)")

    if len(df) < 50:
        print(f"    ⚠️ Insufficient data ({len(df)} signals). Need ≥50.")
        return None, [], None, df, np.array([]), np.array([])

    try:
        from xgboost import XGBClassifier
    except ImportError:
        print("    ⚠️ XGBoost not available. Using sklearn GradientBoosting.")
        from sklearn.ensemble import GradientBoostingClassifier as XGBClassifier

    feature_cols = [f for f in FEATURES if f in df.columns]
    print(f"    Using {len(feature_cols)} features (of {len(FEATURES)} planned)")

    # Drop rows with NaN in features
    valid_mask = df[feature_cols].notna().all(axis=1)
    df_clean = df[valid_mask].copy()
    if len(df_clean) < 50:
        print(f"    ⚠️ Only {len(df_clean)} rows after NaN removal. Need ≥50.")
        return None, feature_cols, None, df_clean, np.array([]), np.array([])

    X = df_clean[feature_cols].values
    y = df_clean['win'].values.astype(int)

    # Sort by timestamp for temporal CV
    sort_idx = df_clean['timestamp'].argsort().values
    X = X[sort_idx]
    y = y[sort_idx]
    df_sorted = df_clean.iloc[sort_idx].reset_index(drop=True)

    # Purged Walk-Forward CV
    splits = purged_walk_forward_cv(X, y, n_splits=5, purge_gap=10)

    fold_results = []
    all_predictions = np.zeros(len(X))
    all_has_pred = np.zeros(len(X), dtype=bool)

    for fold_idx, (train_idx, test_idx) in enumerate(splits):
        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]

        try:
            model = XGBClassifier(
                n_estimators=100,
                max_depth=3,
                learning_rate=0.1,
                min_child_weight=5,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                eval_metric='logloss',
            )
            model.fit(X_train, y_train, verbose=False)
        except TypeError:
            from sklearn.ensemble import GradientBoostingClassifier
            model = GradientBoostingClassifier(
                n_estimators=100, max_depth=3, learning_rate=0.1,
                min_samples_leaf=5, subsample=0.8, random_state=42,
            )
            model.fit(X_train, y_train)

        y_prob = model.predict_proba(X_test)[:, 1]
        y_pred = (y_prob >= 0.5).astype(int)

        acc = (y_pred == y_test).mean()
        wr_above = y_test[y_prob >= 0.65].mean() if (y_prob >= 0.65).sum() > 5 else float('nan')
        wr_below = y_test[y_prob < 0.35].mean() if (y_prob < 0.35).sum() > 5 else float('nan')

        all_predictions[test_idx] = y_prob
        all_has_pred[test_idx] = True

        fold_results.append({
            'fold': fold_idx,
            'train_n': len(train_idx),
            'test_n': len(test_idx),
            'accuracy': acc,
            'trim_success_high': wr_above,
            'trim_success_low': wr_below,
        })
        print(f"    Fold {fold_idx}: train={len(train_idx)}, test={len(test_idx)}, "
              f"acc={acc:.3f}, Trim(P≥0.65)={wr_above:.3f}, Hold(P<0.35)={wr_below:.3f}")

    # Train final model on ALL data
    try:
        final_model = XGBClassifier(
            n_estimators=100, max_depth=3, learning_rate=0.1,
            min_child_weight=5, subsample=0.8, colsample_bytree=0.8,
            random_state=42, eval_metric='logloss',
        )
        final_model.fit(X, y, verbose=False)
    except TypeError:
        from sklearn.ensemble import GradientBoostingClassifier
        final_model = GradientBoostingClassifier(
            n_estimators=100, max_depth=3, learning_rate=0.1,
            min_samples_leaf=5, subsample=0.8, random_state=42,
        )
        final_model.fit(X, y)

    # Feature importance
    if hasattr(final_model, 'feature_importances_'):
        importances = final_model.feature_importances_
    else:
        importances = np.zeros(len(feature_cols))

    importance_df = pd.DataFrame({
        'feature': feature_cols,
        'importance': importances,
    }).sort_values('importance', ascending=False)

    sp("EXIT FEATURE IMPORTANCE (XGBoost)")
    print(f"\n    {'Feature':<25s} │ {'Importance':>10s} │ {'Rank':>4s} │ {'Action':>15s}")
    print(f"    {'─'*65}")
    for rank, (_, row) in enumerate(importance_df.iterrows(), 1):
        action = "★★★ PRIMARY" if row['importance'] > 0.08 else \
                 "★★ SECONDARY" if row['importance'] > 0.04 else \
                 "★ TERTIARY" if row['importance'] > 0.02 else "── minor"
        print(f"    {row['feature']:<25s} │ {row['importance']:>9.4f} │ {rank:>4d} │ {action:>15s}")

    return final_model, feature_cols, importance_df, df_sorted, all_predictions, all_has_pred


# ═══════════════════════════════════════════════════════════
# STEP 3: Optimal Threshold Calibration
# ═══════════════════════════════════════════════════════════

def calibrate_exit_thresholds(df, predictions, has_pred):
    """Find optimal P(trim_correct) thresholds."""
    sp("STEP 3: Exit Threshold Calibration")

    if not has_pred.any():
        print("    ⚠️ No predictions available.")
        return 0.5, {}

    valid = df[has_pred].copy()
    valid['p_trim'] = predictions[has_pred]

    thresholds = [0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]

    print(f"\n    {'Threshold':>9s} │ {'N Trims':>8s} │ {'Success':>8s} │ {'Avg Drop':>8s} │ {'Recommendation':>20s}")
    print(f"    {'─'*65}")

    best_success = -1
    best_threshold = 0.5
    results = {}

    for thr in thresholds:
        above = valid[valid['p_trim'] >= thr]
        if len(above) < 10:
            continue
        success = above['win'].mean() * 100
        avg_drop = above['return_fwd'].mean()

        if success > best_success:
            best_success = success
            best_threshold = thr

        rec = "← OPTIMAL" if thr == best_threshold else \
              "HIGH CONVICTION" if success > 75 else ""

        results[thr] = {'n': len(above), 'success': success, 'avg_drop': avg_drop}
        print(f"    {thr:>8.2f} │ {len(above):>8d} │ {success:>6.1f}% │ {avg_drop:>+7.2f}% │ {rec:>20s}")

    print(f"\n    ★ Optimal exit threshold: P(trim) ≥ {best_threshold:.2f}")
    return best_threshold, results


# ═══════════════════════════════════════════════════════════
# STEP 4: Per-Ticker Exit Profiles
# ═══════════════════════════════════════════════════════════

def build_exit_profiles(df, model, feature_cols, importance_df):
    """Per-ticker exit behavior analysis."""
    sp("STEP 4: Per-Ticker Exit Profiles")

    if model is None or len(df) < 20:
        print("    ⚠️ Insufficient data for per-ticker profiles.")
        return {}

    profiles = {}

    print(f"\n    {'Ticker':>8s} │ {'N':>4s} │ {'Trim%':>6s} │ {'Top1 Feature':>25s} │ {'r':>7s} │ {'Top2 Feature':>25s} │ {'r':>7s}")
    print(f"    {'─'*95}")

    for ticker in sorted(df['ticker'].unique()):
        tdf = df[df['ticker'] == ticker]
        if len(tdf) < 10:
            continue

        trim_rate = tdf['win'].mean() * 100

        # Per-ticker feature correlations with trim success
        feat_cors = {}
        for feat in feature_cols:
            if feat not in tdf.columns:
                continue
            try:
                r, pv = stats.pearsonr(tdf[feat], tdf['win'])
                feat_cors[feat] = {'r': r, 'p': pv, 'significant': pv < 0.10}
            except Exception:
                feat_cors[feat] = {'r': 0, 'p': 1.0, 'significant': False}

        sorted_feats = sorted(feat_cors.items(), key=lambda x: abs(x[1]['r']), reverse=True)
        top1 = sorted_feats[0] if len(sorted_feats) > 0 else ('none', {'r': 0})
        top2 = sorted_feats[1] if len(sorted_feats) > 1 else ('none', {'r': 0})

        profiles[ticker] = {
            'ticker': ticker,
            'n_signals': len(tdf),
            'trim_success_rate': float(trim_rate),
            'avg_post_trim_return': float(tdf['return_fwd'].mean()),
            'top_features': [(f[0], round(float(f[1]['r']), 4)) for f in sorted_feats[:5]],
            'all_feature_correlations': {
                k: round(float(v['r']), 4) for k, v in feat_cors.items()
            },
        }

        print(f"    {ticker:>8s} │ {len(tdf):>4d} │ {trim_rate:>5.1f}% │ {top1[0]:>25s} │ {top1[1]['r']:>+6.3f} │ {top2[0]:>25s} │ {top2[1]['r']:>+6.3f}")

    return profiles


# ═══════════════════════════════════════════════════════════
# STEP 5: Persist Results
# ═══════════════════════════════════════════════════════════

def persist_exit_results(store, model, feature_cols, profiles, best_threshold, importance_df):
    """Save exit model and profiles."""
    sp("STEP 5: Persisting Exit Results")

    if model is None:
        print("    ⚠️ No model to persist.")
        return

    # 1. Save model pickle
    model_dir = root_dir / "backend" / "models"
    model_dir.mkdir(exist_ok=True)
    model_path = model_dir / "meta_label_exit_v1.pkl"
    with open(model_path, 'wb') as f:
        pickle.dump({
            'model': model,
            'feature_cols': feature_cols,
            'version': 1,
            'direction': 'exit',
            'threshold': best_threshold,
            'trained_at': pd.Timestamp.now().isoformat(),
        }, f)
    print(f"    ✅ Exit model saved to {model_path}")

    # 2. Save config
    config = {
        'version': 1,
        'direction': 'exit',
        'optimal_threshold': best_threshold,
        'feature_importance': importance_df.set_index('feature')['importance'].to_dict() if importance_df is not None else {},
        'features_used': feature_cols,
        'forward_bars': FORWARD_BARS,
        'labeling': 'fixed_horizon_inverted',
        'labeling_rationale': 'Trim success = price dropped after reduction. No stop loss on a trim.',
    }
    config_path = model_dir / "meta_label_exit_config.json"
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2, default=str)
    print(f"    ✅ Exit config saved to {config_path}")

    # 3. Save per-ticker exit profiles
    profiles_path = model_dir / "exit_profiles.json"
    with open(profiles_path, 'w') as f:
        json.dump(profiles, f, indent=2, default=str)
    print(f"    ✅ Exit profiles saved to {profiles_path}")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("META-LABEL EXIT PRE-TRAINER v1")
    print("  Calibrates: exit/trim gate + per-ticker trim behavior")
    print("  Source: engine.channel_snapshots (overextended signals)")
    print("  Label: win=1 if price DROPPED after trim (inverted vs entry)")

    t0 = time.time()
    store = TimescaleDataStore()

    # STEP 1: Build dataset
    df = build_exit_dataset(store)

    if len(df) < 50:
        print(f"\n  ⚠️ Insufficient exit signals ({len(df)}). Need more data.")
        print("  Run backfill_channel_snapshots.py first for all 17 tickers.")
        store.close()
        sys.exit(0)

    # STEP 2: Train model
    model, feature_cols, importance_df, df_sorted, preds, has_pred = train_exit_model(df)

    # STEP 3: Calibrate thresholds
    best_threshold, threshold_results = calibrate_exit_thresholds(df_sorted, preds, has_pred)

    # STEP 4: Per-ticker profiles
    profiles = build_exit_profiles(df, model, feature_cols, importance_df)

    # STEP 5: Persist
    persist_exit_results(store, model, feature_cols, profiles, best_threshold, importance_df)

    store.close()
    elapsed = time.time() - t0

    p("EXIT PRE-TRAINER COMPLETE")
    print(f"  Total time: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"  Model: backend/models/meta_label_exit_v1.pkl")
    print(f"  Config: backend/models/meta_label_exit_config.json")
    print(f"  Profiles: backend/models/exit_profiles.json")
    print(f"  Threshold: P(trim) ≥ {best_threshold:.2f}")
    print(f"\n  What this calibrated:")
    print(f"    ✅ Global exit feature importance → what predicts successful trims")
    print(f"    ✅ Optimal P(trim) threshold → exit gate")
    print(f"    ✅ Per-ticker trim behavior → adaptive exit thresholds")
    print(f"    ✅ 29-feature set (20 original + 9 new from Fase 2A)")
