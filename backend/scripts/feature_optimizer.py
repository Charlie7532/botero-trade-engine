#!/usr/bin/env python3
"""
Feature Optimizer — Simons Discovery + López de Prado Validation
=================================================================
Phase 0: Expand feature lake with 42 derived features (blind spots)
Phase 1: SFI — Single Feature Importance per head (each feature alone)
Phase 2: Orthogonality clustering (hierarchical, |r| < 0.7)
Phase 3: Sequential Forward Selection with DSR
Phase 4: Cross-reference + dictamen

Usage:
    nohup python backend/scripts/feature_optimizer.py > /dev/null 2>&1 &
    tail -f backend/scratch/optimization_results/progress.log
"""
import sys
import gc
import json
import time
import pickle
import traceback
import warnings
from pathlib import Path
from datetime import datetime, timezone
from io import StringIO

warnings.filterwarnings("ignore")
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "backend" / "scripts"))

from dotenv import load_dotenv
load_dotenv(root / ".env")

import numpy as np
import pandas as pd

from unified_pretrainer_v2 import (
    load_feature_lake, HEAD_CONFIGS, ALL_FEATURES,
    DB_FEATURES, COMPUTED_FEATURES, PHASE1_FEATURES, DELTA_SOURCES,
    label_long_entry, label_swing_exit, label_pullback_depth,
    label_trend_reversal, label_short_entry, label_short_cover,
    label_bounce_height, label_trend_recovery, label_zz_turning_point,
    apply_context, purged_walk_forward_cv, compute_dsr,
)
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore

MODELS_DIR = root / "backend" / "models"
RESULTS_DIR = root / "backend" / "scratch" / "optimization_results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = RESULTS_DIR / "progress.log"


# ═══════════════════════════════════════════════════════════════
# LOGGING — dual output (console + file)
# ═══════════════════════════════════════════════════════════════

def log(msg, level="INFO"):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def log_section(title):
    sep = "=" * 90
    log(sep)
    log(f"  {title}")
    log(sep)


# ═══════════════════════════════════════════════════════════════
# PHASE 0: Expand Feature Lake
# ═══════════════════════════════════════════════════════════════

DERIVED_FEATURES = []  # Will be populated by expand_feature_lake


def safe_div(a, b, fill=0.0):
    """Safe division avoiding inf/nan."""
    result = np.where(np.abs(b) > 1e-8, a / b, fill)
    return np.nan_to_num(result, nan=fill, posinf=fill, neginf=fill)


def expand_feature_lake(df):
    """Generate derived features from existing data. Returns list of new column names."""
    new_features = []

    def add(name, values):
        df[name] = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
        new_features.append(name)

    # ── RATIOS (cross-timeframe divergence) ──
    add('sigma_ratio_tw', safe_div(df['sigma_tide'].values, df['sigma_wave'].values))
    add('slope_ratio_tc', safe_div(df['tide_slope'].values, df['current_slope'].values))
    add('slope_ratio_tw', safe_div(df['tide_slope'].values, df['wave_slope'].values))
    add('tension_ratio_tw', safe_div(df['tension_tide'].values, df['tension_wave'].values))

    # ── SLOPE DIFFERENCES (cross-TF, same instant) ──
    add('slope_diff_tc', df['tide_slope'].values - df['current_slope'].values)
    add('slope_diff_tw', df['tide_slope'].values - df['wave_slope'].values)
    add('slope_diff_cw', df['current_slope'].values - df['wave_slope'].values)

    # ── SLOPES SQUARED (non-linear extreme detection) ──
    add('tide_slope_sq', df['tide_slope'].values ** 2)
    add('current_slope_sq', df['current_slope'].values ** 2)
    add('wave_slope_sq', df['wave_slope'].values ** 2)
    add('slope_energy', np.abs(df['tide_slope'].values) + np.abs(df['current_slope'].values) + np.abs(df['wave_slope'].values))
    add('slope_product_tc', df['tide_slope'].values * df['current_slope'].values)

    # ── ANGULAR ──
    add('slope_phase_tw', np.arctan(df['tide_slope'].values - df['wave_slope'].values))
    add('sigma_phase_tc', np.arctan(df['sigma_tide'].values - df['sigma_current'].values))

    # ── INTERACTIONS ──
    add('rsi_sigma_interact', df['rsi_value'].values * df['sigma_tide'].values)
    add('kalman_slope_conf', df['kalman_velocity'].values * df['tide_slope'].values)
    add('compr_at_extreme', df['compression_ratio'].values * np.abs(df['sigma_tide'].values))
    add('vol_slope_conf', df['vol_up_down_ratio'].values * df['tide_slope'].values)

    # ── VELOCITIES (missing deltas) ──
    for src in ['sigma_tide', 'sigma_current', 'tide_accel', 'current_slope',
                'tension_tide', 'conj_wave_tide', 'vwap_sigma_tide', 'spread_tide_wave']:
        col = f'd2_{src}'  # d2_ prefix to distinguish from existing d_ deltas
        vals = df[src].values.astype(float)
        delta = np.zeros_like(vals)
        # Group by ticker for proper bar-over-bar
        for tk in df['ticker'].unique():
            mask = (df['ticker'] == tk).values
            tk_vals = vals[mask]
            tk_delta = np.diff(tk_vals, prepend=tk_vals[0])
            delta[mask] = tk_delta
        add(col, delta)

    # ── ALIGNMENT ──
    add('triple_alignment', np.sign(df['tide_slope'].values) * np.sign(df['current_slope'].values) * np.sign(df['wave_slope'].values))
    bullish = ((df['sigma_tide'].values > 0).astype(float) +
               (df['sigma_current'].values > 0).astype(float) +
               (df['sigma_wave'].values > 0).astype(float)) / 3.0
    add('bullish_score', bullish)
    add('total_displacement', np.abs(df['sigma_tide'].values) + np.abs(df['sigma_current'].values) + np.abs(df['sigma_wave'].values))

    # ── DISTANCE / EXTREMES ──
    add('price_vwap_div', df['sigma_tide'].values - df['vwap_sigma_tide'].values)
    add('sigma_abs_dist', np.abs(df['sigma_tide'].values))
    add('sigma_squared', df['sigma_tide'].values ** 2)
    sigma_stack = np.stack([df['sigma_tide'].values, df['sigma_current'].values, df['sigma_wave'].values])
    add('sigma_max_tf', np.max(sigma_stack, axis=0))
    add('sigma_min_tf', np.min(sigma_stack, axis=0))

    # ── RESIDUAL STD (channel fit quality — main blind spot) ──
    for col in ['residual_std_tide', 'residual_std_current', 'residual_std_wave']:
        if col in df.columns:
            add(col, df[col].values.astype(float))
        else:
            log(f"  Column {col} not in feature lake — skipping", "WARN")

    log(f"  Generated {len(new_features)} derived features")
    return new_features


# ═══════════════════════════════════════════════════════════════
# LABELING
# ═══════════════════════════════════════════════════════════════

def compute_labels(head_name, df, ohlcv_cache, profiles, store):
    """Compute labels for a head. Returns float numpy array."""
    cfg = HEAD_CONFIGS[head_name]
    if head_name == 'zz_bottom_detector':
        labels = label_zz_turning_point(df, store, tp_type='MIN', proximity_window=3)
    elif head_name == 'zz_top_detector':
        labels = label_zz_turning_point(df, store, tp_type='MAX', proximity_window=3)
    elif head_name in ('trend_reversal', 'trend_recovery'):
        labeler = {'trend_reversal': label_trend_reversal, 'trend_recovery': label_trend_recovery}[head_name]
        labels = labeler(df, ohlcv_cache, profiles, horizon=cfg['horizon'])
    elif head_name == 'long_entry':
        labels = label_long_entry(df, ohlcv_cache, horizon=cfg['horizon'])
    elif head_name == 'short_entry':
        labels = label_short_entry(df, ohlcv_cache, horizon=cfg['horizon'])
    elif head_name == 'swing_exit':
        labels = label_swing_exit(df, ohlcv_cache)
    elif head_name == 'short_cover':
        labels = label_short_cover(df, ohlcv_cache)
    elif head_name == 'pullback_depth':
        labels = label_pullback_depth(df, ohlcv_cache)
    elif head_name == 'bounce_height':
        labels = label_bounce_height(df, ohlcv_cache)
    else:
        raise ValueError(f"Unknown head: {head_name}")
    return np.array(labels, dtype=float)


# ═══════════════════════════════════════════════════════════════
# TRAINING (streamlined for optimizer)
# ═══════════════════════════════════════════════════════════════

def train_quick(df_head, labels, feature_cols, horizon, n_splits=5):
    """Train with walk-forward CV. Returns {dsr, importances} or None."""
    try:
        from xgboost import XGBClassifier

        # Build feature matrix
        feat_data = {}
        for f in feature_cols:
            if f in df_head.columns:
                feat_data[f] = df_head[f].values.astype(np.float32)
            else:
                feat_data[f] = np.zeros(len(df_head), dtype=np.float32)

        X_df = pd.DataFrame(feat_data)
        valid_mask = (~np.isnan(labels)) & X_df.notna().all(axis=1).values
        X_all = X_df[valid_mask].values.astype(np.float32)
        y_all = labels[valid_mask].astype(int)

        if len(y_all) < 200 or y_all.sum() < 20:
            return None

        # Sort temporally
        ts = df_head[valid_mask]['timestamp'].values
        sort_idx = np.argsort(ts)
        X_all = X_all[sort_idx]
        y_all = y_all[sort_idx]

        # Purged Walk-Forward CV
        splits = purged_walk_forward_cv(len(X_all), n_splits=n_splits, purge_gap=horizon)
        fold_sharpes = []

        for train_idx, test_idx in splits:
            X_tr, y_tr = X_all[train_idx], y_all[train_idx]
            X_te, y_te = X_all[test_idx], y_all[test_idx]

            n_pos = y_tr.sum()
            n_neg = len(y_tr) - n_pos
            sw = max(n_neg / max(n_pos, 1), 1.0)

            model = XGBClassifier(
                n_estimators=150, max_depth=4, learning_rate=0.05,
                min_child_weight=10, subsample=0.8, colsample_bytree=0.8,
                reg_alpha=0.1, reg_lambda=1.0,
                scale_pos_weight=min(sw, 5.0),
                random_state=42, eval_metric='logloss', tree_method='hist',
                verbosity=0,
            )
            model.fit(X_tr, y_tr, verbose=False)

            y_prob = model.predict_proba(X_te)[:, 1]
            high_p = y_prob >= 0.65
            low_p = y_prob < 0.35
            wr_h = y_te[high_p].mean() if high_p.sum() > 20 else float('nan')
            wr_l = y_te[low_p].mean() if low_p.sum() > 20 else float('nan')
            spread = wr_h - wr_l if not (np.isnan(wr_h) or np.isnan(wr_l)) else 0.0
            fold_sharpes.append(spread / max(0.01, y_te.std()))

            del model, X_tr, y_tr, X_te, y_te
        gc.collect()

        dsr = compute_dsr(fold_sharpes)

        # Final model for importances (only if multiple features)
        importances = {}
        if len(feature_cols) > 1:
            sw = max((len(y_all) - y_all.sum()) / max(y_all.sum(), 1), 1.0)
            final = XGBClassifier(
                n_estimators=150, max_depth=4, learning_rate=0.05,
                min_child_weight=10, subsample=0.8, colsample_bytree=0.8,
                reg_alpha=0.1, reg_lambda=1.0,
                scale_pos_weight=min(sw, 5.0),
                random_state=42, eval_metric='logloss', tree_method='hist',
                verbosity=0,
            )
            final.fit(X_all, y_all, verbose=False)
            importances = dict(zip(feature_cols, final.feature_importances_))
            del final

        del X_all, y_all
        gc.collect()

        return {'dsr': float(dsr), 'importances': importances, 'fold_sharpes': fold_sharpes}

    except Exception as e:
        log(f"  train_quick error: {e}", "ERROR")
        return None


# ═══════════════════════════════════════════════════════════════
# PHASE 1: Single Feature Importance
# ═══════════════════════════════════════════════════════════════

def run_sfi(head_name, df_ctx, labels_ctx, all_feature_names, horizon):
    """Run SFI for one head. Returns dict of feature -> dsr."""
    sfi = {}
    total = len(all_feature_names)

    for i, feat in enumerate(all_feature_names):
        if feat not in df_ctx.columns:
            sfi[feat] = 0.0
            continue

        try:
            result = train_quick(df_ctx, labels_ctx, [feat], horizon, n_splits=3)
            dsr = result['dsr'] if result else 0.0
            sfi[feat] = dsr

            if (i + 1) % 10 == 0 or dsr > 1.0:
                marker = " ★" if dsr > 1.0 else ""
                log(f"    SFI [{i+1}/{total}] {feat:35s} DSR={dsr:>7.3f}{marker}")
        except Exception as e:
            log(f"    SFI [{i+1}/{total}] {feat}: ERROR {e}", "WARN")
            sfi[feat] = 0.0

    return sfi


# ═══════════════════════════════════════════════════════════════
# PHASE 2: Orthogonality Clustering
# ═══════════════════════════════════════════════════════════════

def cluster_features(df, feature_names, threshold=0.7):
    """Cluster features by correlation. Returns list of clusters."""
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import squareform

    # Compute correlation matrix
    feat_data = df[feature_names].fillna(0).values.astype(np.float32)
    corr = np.corrcoef(feat_data.T)
    corr = np.nan_to_num(corr, nan=0.0)

    # Distance = 1 - |correlation|
    dist = 1.0 - np.abs(corr)
    np.fill_diagonal(dist, 0)
    dist = np.clip(dist, 0, 2)

    # Make symmetric
    dist = (dist + dist.T) / 2

    # Hierarchical clustering
    condensed = squareform(dist, checks=False)
    Z = linkage(condensed, method='ward')
    labels = fcluster(Z, t=threshold, criterion='distance')

    # Group features by cluster
    clusters = {}
    for feat, label in zip(feature_names, labels):
        clusters.setdefault(int(label), []).append(feat)

    return clusters


# ═══════════════════════════════════════════════════════════════
# PHASE 3: Sequential Forward Selection
# ═══════════════════════════════════════════════════════════════

def forward_selection(head_name, df_ctx, labels_ctx, candidates, horizon):
    """Forward selection: add features one by one, keep only if DSR improves."""
    optimal_set = []
    current_dsr = 0.0
    selection_log = []

    for i, feat in enumerate(candidates):
        test_set = optimal_set + [feat]

        try:
            result = train_quick(df_ctx, labels_ctx, test_set, horizon)
            if result is None:
                log(f"    FWD [{i+1}/{len(candidates)}] {feat}: train failed, SKIP")
                selection_log.append({'feature': feat, 'action': 'SKIP', 'reason': 'train_failed'})
                continue

            test_dsr = result['dsr']
            delta = test_dsr - current_dsr

            if delta > 0:
                optimal_set.append(feat)
                current_dsr = test_dsr
                action = 'ADDED'
                symbol = '✅'
            else:
                action = 'REJECTED'
                symbol = '❌'

            log(f"    FWD [{i+1}/{len(candidates)}] {symbol} {action} '{feat}' "
                f"→ DSR={test_dsr:.4f} (Δ={delta:+.4f}) [{len(optimal_set)}f]")

            selection_log.append({
                'feature': feat,
                'action': action,
                'dsr_after': round(test_dsr, 4),
                'delta': round(delta, 4),
                'n_features': len(optimal_set),
            })

        except Exception as e:
            log(f"    FWD [{i+1}/{len(candidates)}] {feat}: ERROR {e}", "WARN")
            selection_log.append({'feature': feat, 'action': 'ERROR', 'reason': str(e)})

        gc.collect()

    return optimal_set, current_dsr, selection_log


# ═══════════════════════════════════════════════════════════════
# CHECKPOINT SAVE
# ═══════════════════════════════════════════════════════════════

def save_checkpoint(name, data):
    """Save intermediate results to disk."""
    path = RESULTS_DIR / f"{name}.json"
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        log(f"  Checkpoint saved: {path.name}")
    except Exception as e:
        log(f"  Checkpoint save failed: {e}", "ERROR")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    start_time = time.time()

    # Clear log
    LOG_FILE.write_text(f"Feature Optimizer — Started {datetime.now(timezone.utc).isoformat()}\n")

    log_section("FEATURE OPTIMIZER — Simons + López de Prado Protocol")
    log(f"Started: {datetime.now(timezone.utc).isoformat()}")

    # ── Load data ──
    log_section("LOADING DATA")
    store = TimescaleDataStore()
    ps = TickerProfileStore()
    df, ohlcv_cache, profiles = load_feature_lake(store, ps)
    log(f"Feature lake: {len(df):,d} rows, {df.shape[1]} columns")

    # ── Phase 0: Expand feature lake ──
    log_section("PHASE 0: Expand Feature Lake (Simons Discovery)")
    new_features = expand_feature_lake(df)
    EXPANDED_FEATURES = list(ALL_FEATURES) + new_features
    log(f"Expanded lake: {len(EXPANDED_FEATURES)} features ({len(ALL_FEATURES)} original + {len(new_features)} derived)")
    save_checkpoint("phase0_features", {
        'original': list(ALL_FEATURES),
        'derived': new_features,
        'total': len(EXPANDED_FEATURES),
    })

    # ── Current production DSRs ──
    log_section("PRODUCTION BASELINES")
    production_dsrs = {}
    production_features = {}
    for pkl_path in sorted(MODELS_DIR.glob('head_*_v2.pkl')):
        data = pickle.load(open(pkl_path, 'rb'))
        name = pkl_path.stem.replace('head_', '').replace('_v2', '')
        production_dsrs[name] = data.get('dsr', 0)
        production_features[name] = len(data.get('feature_cols', []))
        log(f"  {name:>22s}: DSR={data.get('dsr',0):>7.3f} ({production_features[name]}f)")

    # ── Pre-compute labels ──
    log_section("PRE-COMPUTING LABELS")
    all_labels = {}
    heads_to_run = list(HEAD_CONFIGS.keys())
    for head_name in heads_to_run:
        try:
            t0 = time.time()
            labels = compute_labels(head_name, df, ohlcv_cache, profiles, store)
            n_valid = (~np.isnan(labels)).sum()
            pos_rate = labels[~np.isnan(labels)].mean() if n_valid > 0 else 0
            all_labels[head_name] = labels
            log(f"  {head_name:>22s}: {n_valid:>7,d} valid, pos={pos_rate:.3f} ({time.time()-t0:.1f}s)")
        except Exception as e:
            log(f"  {head_name}: LABELING FAILED: {e}", "ERROR")
            log(traceback.format_exc(), "ERROR")

    # ══════════════════════════════════════════════════════════
    # PHASE 1: Single Feature Importance
    # ══════════════════════════════════════════════════════════
    log_section("PHASE 1: Single Feature Importance (SFI)")
    log(f"Testing {len(EXPANDED_FEATURES)} features × {len(all_labels)} heads")

    sfi_results = {}
    for head_name in all_labels:
        log(f"\n  ── SFI: {head_name.upper()} ──")
        cfg = HEAD_CONFIGS[head_name]
        labels = all_labels[head_name]

        # Apply context
        ctx_mask = apply_context(df, head_name)
        df_ctx = df[ctx_mask].copy()
        labels_ctx = labels[ctx_mask.values]

        t0 = time.time()
        sfi = run_sfi(head_name, df_ctx, labels_ctx, EXPANDED_FEATURES, cfg['horizon'])
        elapsed = time.time() - t0

        # Sort and report top 10
        sorted_sfi = sorted(sfi.items(), key=lambda x: -x[1])
        log(f"\n  Top 10 features for {head_name}:")
        for rank, (feat, dsr) in enumerate(sorted_sfi[:10], 1):
            is_new = "★NEW" if feat in new_features else ""
            log(f"    {rank:>2d}. {feat:35s} DSR={dsr:>7.3f} {is_new}")

        sfi_results[head_name] = sfi
        log(f"  SFI completed for {head_name} in {elapsed:.0f}s")

        # Checkpoint after each head
        save_checkpoint(f"phase1_sfi_{head_name}", {
            'head': head_name,
            'sfi': {k: round(v, 4) for k, v in sorted_sfi},
            'top_10': [{'feature': f, 'dsr': round(d, 4)} for f, d in sorted_sfi[:10]],
            'elapsed_s': round(elapsed, 1),
        })
        gc.collect()

    # Save full SFI matrix
    save_checkpoint("phase1_sfi_matrix", {
        head: {f: round(d, 4) for f, d in sorted(sfi.items(), key=lambda x: -x[1])}
        for head, sfi in sfi_results.items()
    })

    # ══════════════════════════════════════════════════════════
    # PHASE 2: Orthogonality Clustering
    # ══════════════════════════════════════════════════════════
    log_section("PHASE 2: Orthogonality Clustering")

    # Filter features with SFI > 0 in at least one head
    viable_features = set()
    for head, sfi in sfi_results.items():
        for feat, dsr in sfi.items():
            if dsr > 0.1:
                viable_features.add(feat)

    viable_list = sorted(viable_features)
    log(f"Viable features (SFI > 0.1 in any head): {len(viable_list)} / {len(EXPANDED_FEATURES)}")

    if len(viable_list) < 3:
        log("Too few viable features. Using all.", "WARN")
        viable_list = EXPANDED_FEATURES

    try:
        clusters = cluster_features(df, viable_list, threshold=0.7)
        log(f"Clusters found: {len(clusters)}")
        for cid, members in sorted(clusters.items()):
            log(f"  Cluster {cid}: {members}")
    except Exception as e:
        log(f"Clustering failed: {e}. Using viable list directly.", "WARN")
        clusters = {i: [f] for i, f in enumerate(viable_list)}

    save_checkpoint("phase2_clusters", {
        'n_viable': len(viable_list),
        'n_clusters': len(clusters),
        'clusters': {str(k): v for k, v in clusters.items()},
    })

    # ══════════════════════════════════════════════════════════
    # PHASE 3: Sequential Forward Selection (per head)
    # ══════════════════════════════════════════════════════════
    log_section("PHASE 3: Sequential Forward Selection")

    all_results = {}
    for head_name in all_labels:
        log(f"\n  ── FORWARD SELECTION: {head_name.upper()} ──")
        cfg = HEAD_CONFIGS[head_name]
        labels = all_labels[head_name]
        sfi = sfi_results.get(head_name, {})

        ctx_mask = apply_context(df, head_name)
        df_ctx = df[ctx_mask].copy()
        labels_ctx = labels[ctx_mask.values]

        # Select best representative from each cluster (by SFI for this head)
        candidates = []
        for cid, members in clusters.items():
            best_feat = max(members, key=lambda f: sfi.get(f, 0))
            best_dsr = sfi.get(best_feat, 0)
            if best_dsr > 0.0:  # Only include clusters with positive SFI
                candidates.append((best_feat, best_dsr))

        # Sort by SFI descending (most significant first)
        candidates.sort(key=lambda x: -x[1])
        candidate_names = [c[0] for c in candidates]
        log(f"  Candidates: {len(candidate_names)} (from {len(clusters)} clusters)")
        log(f"  Top 5 candidates: {[(c[0], f'{c[1]:.3f}') for c in candidates[:5]]}")

        # Forward selection
        t0 = time.time()
        optimal_set, final_dsr, sel_log = forward_selection(
            head_name, df_ctx, labels_ctx, candidate_names, cfg['horizon']
        )
        elapsed = time.time() - t0

        prod_dsr = production_dsrs.get(head_name, 0)
        delta_prod = final_dsr - prod_dsr

        status = "★ GAIN" if final_dsr > prod_dsr else "≈ SAME" if final_dsr >= prod_dsr * 0.95 else "✖ DROP"

        log(f"\n  ★ RESULT {head_name.upper()}: {len(optimal_set)} features, DSR={final_dsr:.4f}")
        log(f"    Production: DSR={prod_dsr:.3f} ({production_features.get(head_name, '?')}f) → Optimized: DSR={final_dsr:.3f} ({len(optimal_set)}f) [{status}]")
        log(f"    Features: {optimal_set}")
        log(f"    Elapsed: {elapsed:.0f}s")

        all_results[head_name] = {
            'optimal_features': optimal_set,
            'final_dsr': round(final_dsr, 4),
            'production_dsr': round(prod_dsr, 4),
            'delta_vs_production': round(delta_prod, 4),
            'n_features': len(optimal_set),
            'status': status,
            'selection_log': sel_log,
            'elapsed_s': round(elapsed, 1),
        }

        save_checkpoint(f"phase3_result_{head_name}", all_results[head_name])
        gc.collect()

    # ══════════════════════════════════════════════════════════
    # PHASE 4: Cross-Reference + Dictamen
    # ══════════════════════════════════════════════════════════
    log_section("PHASE 4: COMPARATIVE DICTAMEN")

    # Table
    log(f"\n  {'Head':>22s} │ {'Prod':>6s} │ {'SFI→FWD':>8s} │ {'Δ':>6s} │ {'Feat':>5s} │ {'Status':>8s}")
    log(f"  {'─'*65}")

    gains = 0
    for head_name in heads_to_run:
        if head_name not in all_results:
            continue
        r = all_results[head_name]
        log(f"  {head_name:>22s} │ {r['production_dsr']:>6.2f} │ {r['final_dsr']:>8.3f} │ {r['delta_vs_production']:>+6.2f} │ {r['n_features']:>5d} │ {r['status']:>8s}")
        if 'GAIN' in r['status']:
            gains += 1

    log(f"\n  Gains: {gains}/{len(all_results)}")

    # Feature universality
    log_section("FEATURE UNIVERSALITY MAP")
    all_optimal = [set(r['optimal_features']) for r in all_results.values() if r['optimal_features']]
    if all_optimal:
        all_feats = set.union(*all_optimal)
        for feat in sorted(all_feats):
            count = sum(1 for s in all_optimal if feat in s)
            is_new = " ★NEW" if feat in new_features else ""
            log(f"  {feat:35s} │ {count:>2d}/{len(all_optimal)} heads{is_new}")

    # Zigzag cross-reference
    zz_heads = {'zz_bottom_detector', 'zz_top_detector'}
    entry_heads = set(all_results.keys()) - zz_heads
    zz_features = set()
    for h in zz_heads:
        if h in all_results:
            zz_features |= set(all_results[h]['optimal_features'])

    entry_features = set()
    for h in entry_heads:
        if h in all_results:
            entry_features |= set(all_results[h]['optimal_features'])

    zz_only = zz_features - entry_features
    if zz_only:
        log(f"\n  ZIGZAG-ONLY features (potential discriminators for entry heads):")
        for f in sorted(zz_only):
            log(f"    → {f}")

    # Save final report
    total_time = time.time() - start_time
    final_report = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'total_time_min': round(total_time / 60, 1),
        'total_features_tested': len(EXPANDED_FEATURES),
        'derived_features_generated': len(new_features),
        'heads': {name: r for name, r in all_results.items()},
        'sfi_matrix': {
            head: {f: round(d, 4) for f, d in sorted(sfi.items(), key=lambda x: -x[1])[:20]}
            for head, sfi in sfi_results.items()
        },
    }
    save_checkpoint("final_report", final_report)

    log_section("★★★ OPTIMIZATION COMPLETE ★★★")
    log(f"Total time: {total_time/60:.1f} min ({total_time/3600:.1f} hrs)")
    log(f"Results: {RESULTS_DIR}")
    log(f"Next: Review dictamen → persist winners to production")

    store.close()
    ps.close()


if __name__ == "__main__":
    main()
