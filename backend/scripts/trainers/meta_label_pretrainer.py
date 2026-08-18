#!/usr/bin/env python3
"""
Meta-Label Pre-Trainer — Calibrates Entry Gate + Per-Ticker Profiles
=======================================================================
Reads from engine.channel_snapshots (Feature Lake) + market.ohlcv_bars.
Trains XGBoost meta-label model with Purged Walk-Forward CV.

Outputs:
  1. Global feature importance → which features matter universally
  2. Global optimal thresholds → default entry/exit thresholds
  3. Per-ticker profiles → which features are adaptive per symbol
  4. Trained model → pickled for production use
  5. Entry delay table → optimal wait bars per ticker
  6. TickerProfile → persisted to engine.ticker_profiles

This runs periodically (quarterly). Idempotent.

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/meta_label_pretrainer.py
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

# Features used for meta-label (the 4 stable + 3 supporting from v20)
FEATURES = [
    'sigma_tide', 'sigma_current', 'sigma_wave',
    'vwap_sigma_tide', 'vwap_sigma_current', 'vwap_sigma_wave',
    'tide_slope', 'current_slope', 'wave_slope',
    'tide_accel', 'current_accel', 'wave_accel',
    'conj_wave_current', 'conj_wave_tide', 'conj_current_tide',
    'spread_tide_current', 'spread_tide_wave', 'spread_current_wave',
    'fear_level', 'vol_up_down_ratio',
]

FORWARD_BARS = 20  # Forward return horizon for labeling


# ═══════════════════════════════════════════════════════════
# STEP 1: Build Labeled Dataset from Feature Lake
# ═══════════════════════════════════════════════════════════

def build_labeled_dataset(store):
    """Join channel_snapshots with forward returns to create labeled dataset."""
    sp("STEP 1: Building labeled dataset from Feature Lake")

    query = """
        SELECT cs.ticker, cs.timestamp,
               cs.sigma_tide, cs.sigma_current, cs.sigma_wave,
               cs.vwap_sigma_tide, cs.vwap_sigma_current, cs.vwap_sigma_wave,
               cs.tide_slope, cs.current_slope, cs.wave_slope,
               cs.tide_accel, cs.current_accel, cs.wave_accel,
               cs.conj_wave_current, cs.conj_wave_tide, cs.conj_current_tide,
               cs.spread_tide_current, cs.spread_tide_wave, cs.spread_current_wave,
               cs.fear_level, cs.vol_up_down_ratio,
               cs.vwap_spread_tide_current, cs.vwap_spread_tide_wave,
               cs.vwap_spread_current_wave,
               cs.regime, cs.below_all_vwaps, cs.above_all_vwaps,
               ob.close as price
        FROM engine.channel_snapshots cs
        JOIN market.ohlcv_bars ob 
            ON ob.ticker = cs.ticker AND ob.timeframe = '1d' AND ob.time = cs.timestamp
        WHERE cs.sigma_tide < -2.0 
          AND cs.vwap_sigma_wave < -1.5 
          AND cs.below_all_vwaps = true
        ORDER BY cs.ticker, cs.timestamp
    """
    df = pd.read_sql(query, store.engine)
    print(f"    Raw ALL_EXTREME signals: {len(df):,d}")

    # Add forward return + approach_bars — VECTORIZED per ticker
    # (17 queries for OHLCV + 17 for snapshots, instead of 1,882 individual queries)
    results = []
    for ticker in df['ticker'].unique():
        ohlc = store.load_bars(ticker, "1d")
        if ohlc is None or ohlc.empty:
            continue
        tdf = df[df['ticker'] == ticker].copy()

        # Vectorized forward returns using index alignment
        closes = ohlc['close']
        for idx, row in tdf.iterrows():
            ts = row['timestamp']
            if ts in ohlc.index:
                pos = ohlc.index.get_loc(ts)
                if pos + FORWARD_BARS < len(ohlc):
                    future_price = closes.iloc[pos + FORWARD_BARS]
                    tdf.loc[idx, 'return_fwd'] = (future_price / row['price'] - 1) * 100
                    tdf.loc[idx, 'win'] = 1 if future_price > row['price'] else 0

        # Pre-load ALL snapshots for this ticker ONCE (1 query, not N)
        snaps = store.load_snapshots(ticker, "1d")
        sigma_tide_series = snaps['sigma_tide'] if not snaps.empty else pd.Series(dtype=float)

        # Vectorized approach_bars computation
        approach_list = []
        for idx, row in tdf.iterrows():
            ts = row['timestamp']
            if snaps.empty or len(snaps) < 5 or ts not in snaps.index:
                approach_list.append(30)
                continue
            ts_loc = snaps.index.get_loc(ts)
            ab = 0
            for j in range(ts_loc - 1, max(ts_loc - 60, 0), -1):
                if sigma_tide_series.iloc[j] >= -1.0:
                    ab = ts_loc - j
                    break
            approach_list.append(ab if ab > 0 else 60)

        tdf['approach_bars'] = approach_list
        results.append(tdf)
        print(f"      {ticker}: {len(tdf)} signals, snaps loaded")

    full = pd.concat(results, ignore_index=True)
    full = full.dropna(subset=['return_fwd', 'win'])

    print(f"    Labeled signals: {len(full):,d}")
    print(f"    Win rate: {full['win'].mean()*100:.1f}%")
    print(f"    Avg return: {full['return_fwd'].mean():+.2f}%")
    return full


# ═══════════════════════════════════════════════════════════
# STEP 2: Purged Walk-Forward Cross-Validation
# ═══════════════════════════════════════════════════════════

def purged_walk_forward_cv(X, y, n_splits=5, purge_gap=10):
    """López de Prado's Purged Walk-Forward CV.
    
    Unlike random CV, this respects temporal ordering:
    - Train on past, test on future
    - Purge gap between train/test to avoid information leakage
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


def train_meta_label(df):
    """Train XGBoost meta-label with Purged Walk-Forward CV."""
    sp("STEP 2: Training Meta-Label Model (Purged Walk-Forward CV)")

    try:
        from xgboost import XGBClassifier
    except ImportError:
        print("    ⚠️ XGBoost not available. Using sklearn GradientBoosting.")
        from sklearn.ensemble import GradientBoostingClassifier as XGBClassifier

    feature_cols = [f for f in FEATURES if f in df.columns]
    feature_cols.append('approach_bars')

    X = df[feature_cols].values
    y = df['win'].values.astype(int)

    # Sort by timestamp for temporal CV
    sort_idx = df['timestamp'].argsort().values
    X = X[sort_idx]
    y = y[sort_idx]
    df_sorted = df.iloc[sort_idx].reset_index(drop=True)

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
            # sklearn GradientBoosting fallback
            from sklearn.ensemble import GradientBoostingClassifier
            model = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=3,
                learning_rate=0.1,
                min_samples_leaf=5,
                subsample=0.8,
                random_state=42,
            )
            model.fit(X_train, y_train)

        # Predict probabilities
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
            'wr_high_conviction': wr_above,
            'wr_low_conviction': wr_below,
        })
        print(f"    Fold {fold_idx}: train={len(train_idx)}, test={len(test_idx)}, "
              f"acc={acc:.3f}, WR(P≥0.65)={wr_above:.3f}, WR(P<0.35)={wr_below:.3f}")

    # Train final model on ALL data
    try:
        final_model = XGBClassifier(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.1,
            min_child_weight=5,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            eval_metric='logloss',
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

    sp("GLOBAL FEATURE IMPORTANCE (XGBoost)")
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

def calibrate_thresholds(df, predictions, has_pred):
    """Find optimal P(profit) thresholds for different use cases."""
    sp("STEP 3: Threshold Calibration")

    valid = df[has_pred].copy()
    valid['p_profit'] = predictions[has_pred]

    thresholds = [0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]

    print(f"\n    {'Threshold':>9s} │ {'N Trades':>8s} │ {'WR':>6s} │ {'Avg Ret':>8s} │ {'Sharpe':>6s} │ {'Recommendation':>20s}")
    print(f"    {'─'*70}")

    best_sharpe = -999
    best_threshold = 0.5
    results = {}

    for thr in thresholds:
        above = valid[valid['p_profit'] >= thr]
        if len(above) < 10:
            continue
        wr = above['win'].mean() * 100
        avg_ret = above['return_fwd'].mean()
        std_ret = above['return_fwd'].std()
        sharpe = avg_ret / std_ret * np.sqrt(252/FORWARD_BARS) if std_ret > 0 else 0

        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_threshold = thr

        rec = "← OPTIMAL" if thr == best_threshold and thr >= 0.5 else \
              "HIGH CONVICTION" if wr > 80 else \
              "BALANCED" if wr > 70 else ""

        results[thr] = {'n': len(above), 'wr': wr, 'avg_ret': avg_ret, 'sharpe': sharpe}
        print(f"    {thr:>8.2f} │ {len(above):>8d} │ {wr:>5.1f}% │ {avg_ret:>+7.2f}% │ {sharpe:>5.2f} │ {rec:>20s}")

    print(f"\n    ★ Optimal threshold for Sharpe: {best_threshold:.2f}")
    return best_threshold, results


# ═══════════════════════════════════════════════════════════
# STEP 4: Per-Ticker Adaptive Profiles
# ═══════════════════════════════════════════════════════════

def build_ticker_profiles(df, model, feature_cols, importance_df):
    """Determine which features are adaptive per ticker."""
    sp("STEP 4: Per-Ticker Adaptive Profiles")

    # For each ticker, compute local feature correlations with outcome
    profiles = {}

    print(f"\n    {'Ticker':>8s} │ {'N':>4s} │ {'WR':>6s} │ {'Top1 Feature':>25s} │ {'r':>7s} │ {'Top2 Feature':>25s} │ {'r':>7s} │ {'Delay':>5s}")
    print(f"    {'─'*105}")

    for ticker in sorted(df['ticker'].unique()):
        tdf = df[df['ticker'] == ticker]
        if len(tdf) < 20:
            continue

        wr = tdf['win'].mean() * 100

        # Per-ticker feature correlations
        feat_cors = {}
        for feat in feature_cols:
            if feat not in tdf.columns:
                continue
            try:
                r, pv = stats.pearsonr(tdf[feat], tdf['win'])
                feat_cors[feat] = {'r': r, 'p': pv, 'significant': pv < 0.10}
            except:
                feat_cors[feat] = {'r': 0, 'p': 1.0, 'significant': False}

        # Sort by absolute correlation
        sorted_feats = sorted(feat_cors.items(), key=lambda x: abs(x[1]['r']), reverse=True)
        top1 = sorted_feats[0] if len(sorted_feats) > 0 else ('none', {'r': 0})
        top2 = sorted_feats[1] if len(sorted_feats) > 1 else ('none', {'r': 0})

        # Entry delay (from approach_bars analysis)
        # If approach_bars is small and WR is high → CRASH type → delay 0
        # If approach_bars is large and WR is high → SLOW_BLEED → delay 1-2
        crash_trades = tdf[tdf['approach_bars'] <= 3]
        slow_trades = tdf[tdf['approach_bars'] > 25]
        crash_wr = crash_trades['win'].mean() if len(crash_trades) >= 5 else 0.5
        slow_wr = slow_trades['win'].mean() if len(slow_trades) >= 5 else 0.5
        optimal_delay = 0 if crash_wr > slow_wr + 0.05 else 2 if slow_wr > crash_wr + 0.10 else 1

        # Which features DEVIATE from global importance
        global_top = set(importance_df.head(5)['feature'])
        local_top = set(f[0] for f in sorted_feats[:5])
        unique_local = local_top - global_top

        profiles[ticker] = {
            'ticker': ticker,
            'n_signals': len(tdf),
            'win_rate': float(wr),
            'top_features': [(f[0], round(float(f[1]['r']), 4)) for f in sorted_feats[:5]],
            'unique_features': list(unique_local),
            'optimal_delay_bars': optimal_delay,
            'crash_wr': float(crash_wr * 100) if crash_wr else 0,
            'slow_bleed_wr': float(slow_wr * 100) if slow_wr else 0,
            'all_feature_correlations': {
                k: round(float(v['r']), 4) for k, v in feat_cors.items()
            },
        }

        print(f"    {ticker:>8s} │ {len(tdf):>4d} │ {wr:>5.1f}% │ {top1[0]:>25s} │ {top1[1]['r']:>+6.3f} │ {top2[0]:>25s} │ {top2[1]['r']:>+6.3f} │ {optimal_delay:>5d}")

    # Summary: which features are UNIVERSAL vs ADAPTIVE
    sp("UNIVERSAL vs ADAPTIVE FEATURES")

    # Count how many tickers have each feature in top-5
    feat_ticker_count = {}
    for t_profile in profiles.values():
        for feat, _ in t_profile['top_features']:
            feat_ticker_count[feat] = feat_ticker_count.get(feat, 0) + 1

    total_tickers = len(profiles)
    print(f"\n    {'Feature':<25s} │ {'In Top-5 of':>12s} │ {'Pct':>5s} │ {'Type':>15s}")
    print(f"    {'─'*65}")
    for feat, count in sorted(feat_ticker_count.items(), key=lambda x: -x[1]):
        pct = count / total_tickers * 100
        ftype = "★★★ UNIVERSAL" if pct >= 70 else "★★ SEMI-UNIV" if pct >= 40 else "★ ADAPTIVE"
        print(f"    {feat:<25s} │ {count:>5d}/{total_tickers:<5d} │ {pct:>4.0f}% │ {ftype:>15s}")

    return profiles


# ═══════════════════════════════════════════════════════════
# STEP 5: Persist Results
# ═══════════════════════════════════════════════════════════

def persist_results(store, model, feature_cols, profiles, best_threshold, importance_df):
    """Save model and profiles for production use."""
    sp("STEP 5: Persisting Results")

    # 1. Save model pickle
    model_dir = root_dir / "data" / "models"
    model_dir.mkdir(exist_ok=True)
    model_path = model_dir / "meta_label_v1.pkl"
    with open(model_path, 'wb') as f:
        pickle.dump({
            'model': model,
            'feature_cols': feature_cols,
            'version': 1,
            'threshold': best_threshold,
            'trained_at': pd.Timestamp.now().isoformat(),
        }, f)
    print(f"    ✅ Model saved to {model_path}")

    # 2. Save global config
    config = {
        'version': 1,
        'optimal_threshold': best_threshold,
        'feature_importance': importance_df.set_index('feature')['importance'].to_dict(),
        'features_used': feature_cols,
    }
    config_path = model_dir / "meta_label_config.json"
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2, default=str)
    print(f"    ✅ Config saved to {config_path}")

    # 3. Save per-ticker profiles
    profiles_path = model_dir / "ticker_profiles.json"
    with open(profiles_path, 'w') as f:
        json.dump(profiles, f, indent=2, default=str)
    print(f"    ✅ Ticker profiles saved to {profiles_path}")

    # 4. Persist to DB (engine.ticker_profiles)
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS engine.ticker_profiles (
                    ticker TEXT NOT NULL,
                    version SMALLINT NOT NULL DEFAULT 1,
                    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    n_signals INT,
                    win_rate DOUBLE PRECISION,
                    optimal_delay_bars SMALLINT,
                    crash_wr DOUBLE PRECISION,
                    slow_bleed_wr DOUBLE PRECISION,
                    top_features JSONB,
                    unique_features JSONB,
                    all_correlations JSONB,
                    meta_threshold DOUBLE PRECISION,
                    PRIMARY KEY (ticker, version)
                );
            """)
            for ticker, prof in profiles.items():
                cur.execute("""
                    INSERT INTO engine.ticker_profiles 
                        (ticker, version, n_signals, win_rate, optimal_delay_bars,
                         crash_wr, slow_bleed_wr, top_features, unique_features,
                         all_correlations, meta_threshold)
                    VALUES (%s, 1, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker, version) DO UPDATE SET
                        computed_at = NOW(),
                        n_signals = EXCLUDED.n_signals,
                        win_rate = EXCLUDED.win_rate,
                        optimal_delay_bars = EXCLUDED.optimal_delay_bars,
                        crash_wr = EXCLUDED.crash_wr,
                        slow_bleed_wr = EXCLUDED.slow_bleed_wr,
                        top_features = EXCLUDED.top_features,
                        unique_features = EXCLUDED.unique_features,
                        all_correlations = EXCLUDED.all_correlations,
                        meta_threshold = EXCLUDED.meta_threshold
                """, (
                    ticker,
                    prof['n_signals'],
                    prof['win_rate'],
                    prof['optimal_delay_bars'],
                    prof['crash_wr'],
                    prof['slow_bleed_wr'],
                    json.dumps(prof['top_features']),
                    json.dumps(prof['unique_features']),
                    json.dumps(prof['all_feature_correlations']),
                    best_threshold,
                ))
        conn.commit()
        print(f"    ✅ {len(profiles)} ticker profiles persisted to engine.ticker_profiles")
    except Exception as e:
        conn.rollback()
        print(f"    ❌ DB persist failed: {e}")
    finally:
        store._put(conn)


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("META-LABEL PRE-TRAINER v1")
    print("  Calibrates: global thresholds + per-ticker adaptive features")
    print("  Source: engine.channel_snapshots (93,776 snapshots)")

    t0 = time.time()
    store = TimescaleDataStore()

    # STEP 1: Build dataset
    df = build_labeled_dataset(store)

    # STEP 2: Train model
    model, feature_cols, importance_df, df_sorted, preds, has_pred = train_meta_label(df)

    # STEP 3: Calibrate thresholds
    best_threshold, threshold_results = calibrate_thresholds(df_sorted, preds, has_pred)

    # STEP 4: Per-ticker profiles
    profiles = build_ticker_profiles(df, model, feature_cols, importance_df)

    # STEP 5: Persist
    persist_results(store, model, feature_cols, profiles, best_threshold, importance_df)

    store.close()
    elapsed = time.time() - t0

    p("PRE-TRAINER COMPLETE")
    print(f"  Total time: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"  Model: data/models/meta_label_v1.pkl")
    print(f"  Config: data/models/meta_label_config.json")
    print(f"  Profiles: data/models/ticker_profiles.json")
    print(f"  DB: engine.ticker_profiles ({len(profiles)} tickers)")
    print(f"  Threshold: P(profit) ≥ {best_threshold:.2f}")
    print(f"\n  What this calibrated:")
    print(f"    ✅ Global feature importance → which features matter")
    print(f"    ✅ Optimal P(profit) threshold → entry gate")
    print(f"    ✅ Per-ticker feature rankings → adaptive variables")
    print(f"    ✅ Entry delay per ticker → wait 0/1/2 bars")
    print(f"    ✅ Universal vs Adaptive features → what's fixed vs per-ticker")
