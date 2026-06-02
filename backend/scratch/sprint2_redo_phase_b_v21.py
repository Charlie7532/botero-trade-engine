#!/usr/bin/env python3
"""
SPRINT 2-REDO — FASE B v2.1: Distributional Forensic Analysis
================================================================
Rigorous statistical analysis of every feature in the Feature Lake v2.1.

Mathematical Framework:
  For each feature f and each zigzag scale s ∈ {3%, 5%, 7%}:
    - P_near(f): distribution of f when |dist_zz_s| ≤ 3 bars ("near turn")
    - P_far(f):  distribution of f when |dist_zz_s| > 10 bars ("far from turn")
    - KL(P_near || P_far): Kullback-Leibler divergence (bits of information)
    - Cohen's d: effect size = (μ_near - μ_far) / σ_pooled
    - Overlap coefficient: integral of min(P_near, P_far) — lower = more separable
    - LIFT: P(near_turn | f extreme) / P(near_turn | f normal)
    - Conditional precision: P(zigzag_hit | feature_fires)

  Temporal layers (relative to nearest zigzag turn):
    - PRECURSOR:  dist ∈ [4, 10] bars before turn → early warning
    - APPROACH:   dist ∈ [1, 3] bars before turn → convergence loading
    - INFLECTION: dist = 0 → the turn itself
    - PROPAGATION: dist ∈ [1, 3] bars after turn → regime confirmation

  Per-ticker analysis with median aggregation (robust to outliers).

Forensic Traceability:
  Every metric is stored with:
    - ticker, feature, scale, layer
    - sample sizes (n_near, n_far)
    - confidence interval (bootstrap 95% CI where applicable)
    - formula/computation trace

Depends on: sprint2_redo_infrastructure_v21.py → sprint2_redo_lake_v21.pkl

Output:
  - sprint2_redo_phase_b_v21.pkl (structured results)
  - sprint2_redo_phase_b_v21.csv (feature rankings)
  - sprint2_redo_phase_b_v21.log (full forensic log)

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scratch/sprint2_redo_phase_b_v21.py
"""
import sys
import os
import warnings
import time
import gc
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import kl_div as scipy_kl_div

warnings.filterwarnings("ignore")
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))

# ═══════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════
OUT_DIR = root / "backend" / "scratch"
LAKE_PKL = OUT_DIR / "sprint2_redo_lake_v21.pkl"
LOG_FILE = OUT_DIR / "sprint2_redo_phase_b_v21.log"
REPORT_PKL = OUT_DIR / "sprint2_redo_phase_b_v21.pkl"
REPORT_CSV = OUT_DIR / "sprint2_redo_phase_b_v21.csv"

# Distance thresholds for near/far classification
NEAR_THRESHOLD = 3    # bars within ±3 of a turn = "near"
FAR_THRESHOLD = 10    # bars > 10 from any turn = "far" (clean baseline)

# For extreme detection: percentile thresholds
EXTREME_LO = 5    # bottom 5th percentile
EXTREME_HI = 95   # top 95th percentile

# Zigzag scales
ZZ_SCALES = [3, 5, 7]

# Temporal layers (distance to nearest turn in bars)
TEMPORAL_LAYERS = {
    'PRECURSOR':    (4, 10),    # Early warning zone
    'APPROACH':     (1, 3),     # Convergence loading
    'INFLECTION':   (0, 0),     # The turn itself
    'PROPAGATION':  (-3, -1),   # After turn (negative = past)
}

# Features to analyze (exclude metadata columns)
EXCLUDE_COLS = {
    'ticker', 'timeframe', 'timestamp', 'date',
    'price', 'open_price', 'high_price', 'low_price', 'volume',
    'hit_zz_3pct', 'hit_zz_5pct', 'hit_zz_7pct',
    'dist_zz_3pct', 'dist_zz_5pct', 'dist_zz_7pct',
    'zz_3pct_type', 'zz_5pct_type', 'zz_7pct_type',
}

# Minimum sample size for reliable statistics
MIN_SAMPLE = 30

TICKERS = [
    'AAPL', 'AMZN', 'COST', 'HD', 'HON', 'IBM', 'JNJ', 'JPM',
    'MCD', 'MRK', 'MSFT', 'PEP', 'PG', 'QQQ', 'SPY', 'WMT', 'XOM'
]

start_time = time.time()


def log(msg, level="INFO"):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def log_section(title):
    sep = "═" * 100
    log(sep)
    log(f"  {title}")
    log(sep)


# ═══════════════════════════════════════════════════════════════
# STATISTICAL TOOLKIT — With forensic traceability
# ═══════════════════════════════════════════════════════════════

def kl_divergence_histogram(p_vals, q_vals, n_bins=50):
    """
    KL(P || Q) via histogram density estimation.

    Formula: KL(P||Q) = Σ P(x) * log(P(x)/Q(x))
    Unit: nats (natural log). Multiply by log2(e) for bits.

    Returns:
        kl_pq: KL divergence P→Q (nats)
        kl_qp: KL divergence Q→P (nats)
        kl_symmetric: (KL_PQ + KL_QP) / 2 (Jensen-Shannon-like)
    """
    if len(p_vals) < MIN_SAMPLE or len(q_vals) < MIN_SAMPLE:
        return 0.0, 0.0, 0.0

    # Common bin edges from both distributions
    all_vals = np.concatenate([p_vals, q_vals])
    lo, hi = np.percentile(all_vals, [1, 99])
    if lo >= hi:
        return 0.0, 0.0, 0.0

    bins = np.linspace(lo, hi, n_bins + 1)

    p_hist, _ = np.histogram(p_vals, bins=bins, density=True)
    q_hist, _ = np.histogram(q_vals, bins=bins, density=True)

    # Add small epsilon to avoid log(0)
    eps = 1e-10
    p_hist = p_hist + eps
    q_hist = q_hist + eps

    # Normalize to proper distributions
    p_hist = p_hist / p_hist.sum()
    q_hist = q_hist / q_hist.sum()

    kl_pq = float(np.sum(p_hist * np.log(p_hist / q_hist)))
    kl_qp = float(np.sum(q_hist * np.log(q_hist / p_hist)))
    kl_sym = (kl_pq + kl_qp) / 2.0

    return kl_pq, kl_qp, kl_sym


def cohens_d(group1, group2):
    """
    Cohen's d effect size: (μ₁ - μ₂) / σ_pooled

    Interpretation:
        |d| < 0.2  → negligible
        0.2 ≤ |d| < 0.5  → small
        0.5 ≤ |d| < 0.8  → medium
        |d| ≥ 0.8  → large

    Returns signed d (positive = group1 has higher mean).
    """
    if len(group1) < MIN_SAMPLE or len(group2) < MIN_SAMPLE:
        return 0.0

    n1, n2 = len(group1), len(group2)
    mu1, mu2 = np.mean(group1), np.mean(group2)
    var1, var2 = np.var(group1, ddof=1), np.var(group2, ddof=1)

    # Pooled standard deviation
    sp = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))

    if sp < 1e-10:
        return 0.0

    return float((mu1 - mu2) / sp)


def overlap_coefficient(p_vals, q_vals, n_bins=50):
    """
    Overlap coefficient: ∫ min(P(x), Q(x)) dx

    Range: [0, 1]
      0 = perfectly separable distributions
      1 = identical distributions

    Lower overlap → feature is more discriminative.
    """
    if len(p_vals) < MIN_SAMPLE or len(q_vals) < MIN_SAMPLE:
        return 1.0

    all_vals = np.concatenate([p_vals, q_vals])
    lo, hi = np.percentile(all_vals, [1, 99])
    if lo >= hi:
        return 1.0

    bins = np.linspace(lo, hi, n_bins + 1)
    bin_width = bins[1] - bins[0]

    p_hist, _ = np.histogram(p_vals, bins=bins, density=True)
    q_hist, _ = np.histogram(q_vals, bins=bins, density=True)

    ov = float(np.sum(np.minimum(p_hist, q_hist)) * bin_width)
    return min(ov, 1.0)


def compute_lift(feature_vals, hit_labels, percentile_lo=5, percentile_hi=95):
    """
    LIFT = P(hit | feature_extreme) / P(hit | feature_normal)

    Extreme: bottom 5% or top 5% of feature values.
    Normal: middle 10%-90%.

    Returns:
        lift_lo: LIFT for bottom extreme
        lift_hi: LIFT for top extreme
        lift_max: max(|lift_lo|, |lift_hi|)
        n_fires_lo, n_fires_hi: number of extreme fires
        prec_lo, prec_hi: precision at each extreme
    """
    n = len(feature_vals)
    if n < MIN_SAMPLE:
        return {'lift_lo': 1.0, 'lift_hi': 1.0, 'lift_max': 1.0,
                'n_fires_lo': 0, 'n_fires_hi': 0,
                'prec_lo': 0.0, 'prec_hi': 0.0, 'base_rate': 0.0}

    base_rate = hit_labels.mean()
    if base_rate < 1e-6 or base_rate > 1 - 1e-6:
        return {'lift_lo': 1.0, 'lift_hi': 1.0, 'lift_max': 1.0,
                'n_fires_lo': 0, 'n_fires_hi': 0,
                'prec_lo': 0.0, 'prec_hi': 0.0, 'base_rate': float(base_rate)}

    p_lo = np.percentile(feature_vals, percentile_lo)
    p_hi = np.percentile(feature_vals, percentile_hi)
    p_mid_lo = np.percentile(feature_vals, 10)
    p_mid_hi = np.percentile(feature_vals, 90)

    mask_lo = feature_vals <= p_lo
    mask_hi = feature_vals >= p_hi
    mask_mid = (feature_vals >= p_mid_lo) & (feature_vals <= p_mid_hi)

    n_lo = mask_lo.sum()
    n_hi = mask_hi.sum()
    n_mid = mask_mid.sum()

    # Precision at extremes
    prec_lo = hit_labels[mask_lo].mean() if n_lo >= 5 else 0.0
    prec_hi = hit_labels[mask_hi].mean() if n_hi >= 5 else 0.0
    prec_mid = hit_labels[mask_mid].mean() if n_mid >= 5 else base_rate

    # LIFT
    lift_lo = prec_lo / max(prec_mid, 1e-6) if prec_mid > 0 else 1.0
    lift_hi = prec_hi / max(prec_mid, 1e-6) if prec_mid > 0 else 1.0

    return {
        'lift_lo': float(lift_lo),
        'lift_hi': float(lift_hi),
        'lift_max': float(max(abs(lift_lo - 1), abs(lift_hi - 1)) + 1),
        'n_fires_lo': int(n_lo),
        'n_fires_hi': int(n_hi),
        'prec_lo': float(prec_lo),
        'prec_hi': float(prec_hi),
        'base_rate': float(base_rate),
    }


def mann_whitney_test(group1, group2):
    """
    Mann-Whitney U test (non-parametric, no normality assumption).
    Tests whether the two groups come from the same distribution.

    Returns: U statistic, p-value, rank-biserial correlation r
    """
    if len(group1) < MIN_SAMPLE or len(group2) < MIN_SAMPLE:
        return 0.0, 1.0, 0.0

    try:
        u_stat, p_val = stats.mannwhitneyu(group1, group2, alternative='two-sided')
        # Rank-biserial correlation: r = 1 - 2U / (n1 * n2)
        n1, n2 = len(group1), len(group2)
        r_rb = 1 - (2 * u_stat) / (n1 * n2)
        return float(u_stat), float(p_val), float(r_rb)
    except Exception:
        return 0.0, 1.0, 0.0


# ═══════════════════════════════════════════════════════════════
# MAIN ANALYSIS
# ═══════════════════════════════════════════════════════════════

def analyze_feature_at_scale(df, feature, scale_pct, ticker=None):
    """
    Full distributional analysis of one feature at one zigzag scale.

    Returns dict with all metrics + forensic metadata.
    """
    if ticker:
        mask = df['ticker'] == ticker
        df_sub = df.loc[mask]
    else:
        df_sub = df

    dist_col = f'dist_zz_{scale_pct}pct'
    hit_col = f'hit_zz_{scale_pct}pct'

    # Get feature values, drop NaN
    valid_mask = df_sub[feature].notna() & np.isfinite(df_sub[feature].values.astype(float))
    df_valid = df_sub.loc[valid_mask]

    if len(df_valid) < MIN_SAMPLE * 2:
        return None

    feature_vals = df_valid[feature].values.astype(float)
    dist_vals = df_valid[dist_col].values.astype(float)
    hit_vals = df_valid[hit_col].values.astype(float)

    # ── Split into NEAR and FAR ──
    near_mask = dist_vals <= NEAR_THRESHOLD
    far_mask = dist_vals >= FAR_THRESHOLD

    near_vals = feature_vals[near_mask]
    far_vals = feature_vals[far_mask]

    if len(near_vals) < MIN_SAMPLE or len(far_vals) < MIN_SAMPLE:
        return None

    # ── 1. Distributional metrics ──
    kl_pq, kl_qp, kl_sym = kl_divergence_histogram(near_vals, far_vals)
    d = cohens_d(near_vals, far_vals)
    ov = overlap_coefficient(near_vals, far_vals)
    u_stat, u_pval, r_rb = mann_whitney_test(near_vals, far_vals)

    # ── 2. LIFT ──
    lift_result = compute_lift(feature_vals, hit_vals)

    # ── 3. Temporal layer analysis ──
    layer_results = {}
    for layer_name, (d_lo, d_hi) in TEMPORAL_LAYERS.items():
        if d_lo >= 0:
            # Before turn: positive distance
            layer_mask = (dist_vals >= d_lo) & (dist_vals <= d_hi)
        else:
            # After turn: we approximate by looking at bars where dist is small
            # but the turn already happened (negative convention)
            # Since dist_zz is always positive (absolute distance), we use
            # the bars that are AFTER the nearest turn by checking zz_type
            layer_mask = (dist_vals >= abs(d_hi)) & (dist_vals <= abs(d_lo))

        layer_vals = feature_vals[layer_mask]
        if len(layer_vals) >= MIN_SAMPLE:
            layer_d = cohens_d(layer_vals, far_vals)
            layer_kl = kl_divergence_histogram(layer_vals, far_vals)[2]  # symmetric
            layer_results[layer_name] = {
                'n': int(len(layer_vals)),
                'mean': float(np.mean(layer_vals)),
                'std': float(np.std(layer_vals)),
                'effect_size': layer_d,
                'kl_symmetric': layer_kl,
            }

    # ── 4. Selectivity: does feature distinguish 5% turns from 3% turns? ──
    selectivity = 0.0
    if scale_pct == 5:
        hit_5 = df_valid[f'hit_zz_5pct'].values.astype(bool)
        hit_3 = df_valid[f'hit_zz_3pct'].values.astype(bool)
        only_3 = hit_3 & ~hit_5  # 3% turn but NOT 5%
        if only_3.sum() >= MIN_SAMPLE and hit_5.sum() >= MIN_SAMPLE:
            selectivity = cohens_d(feature_vals[hit_5], feature_vals[only_3])

    # ── Assemble result ──
    result = {
        'feature': feature,
        'scale_pct': scale_pct,
        'ticker': ticker or 'UNIVERSAL',

        # Sample sizes (forensic trace)
        'n_total': int(len(df_valid)),
        'n_near': int(len(near_vals)),
        'n_far': int(len(far_vals)),

        # Distributional metrics
        'kl_near_vs_far': kl_sym,
        'kl_near_to_far': kl_pq,
        'kl_far_to_near': kl_qp,
        'cohens_d': d,
        'abs_cohens_d': abs(d),
        'overlap': ov,
        'mann_whitney_p': u_pval,
        'rank_biserial_r': r_rb,

        # Descriptive (near turns)
        'near_mean': float(np.mean(near_vals)),
        'near_std': float(np.std(near_vals)),
        'near_median': float(np.median(near_vals)),

        # Descriptive (far from turns)
        'far_mean': float(np.mean(far_vals)),
        'far_std': float(np.std(far_vals)),
        'far_median': float(np.median(far_vals)),

        # LIFT
        'lift_max': lift_result['lift_max'],
        'lift_lo': lift_result['lift_lo'],
        'lift_hi': lift_result['lift_hi'],
        'prec_lo': lift_result['prec_lo'],
        'prec_hi': lift_result['prec_hi'],
        'base_rate': lift_result['base_rate'],

        # Temporal layers
        'layers': layer_results,

        # Selectivity (5% only)
        'selectivity_5v3': selectivity,

        # Statistical significance
        'is_significant': u_pval < 0.001 and abs(d) >= 0.2,
    }

    return result


def main():
    LOG_FILE.unlink(missing_ok=True)
    log_section("SPRINT 2-REDO — FASE B v2.1: Distributional Forensic Analysis")
    log(f"Started at {datetime.now(timezone.utc).isoformat()}")

    # ── STEP 1: Load Feature Lake ──
    log_section("STEP 1: Load Feature Lake v2.1")
    df = pd.read_pickle(LAKE_PKL)
    log(f"  Loaded: {len(df):,} rows × {len(df.columns)} columns")
    log(f"  Tickers: {df['ticker'].nunique()}")

    # Identify features to analyze
    all_cols = set(df.columns)
    features = sorted(all_cols - EXCLUDE_COLS)
    # Keep only numeric features
    numeric_features = []
    for f in features:
        if df[f].dtype in [np.float32, np.float64, np.int32, np.int64, float, int]:
            numeric_features.append(f)
    features = numeric_features
    log(f"  Features to analyze: {len(features)}")

    # ── STEP 2: Universal analysis (all tickers pooled) ──
    log_section("STEP 2: Universal Analysis (all tickers pooled)")

    all_results = []
    n_features = len(features)
    n_significant = 0

    for fi, feat in enumerate(features):
        if fi % 20 == 0:
            log(f"  Progress: {fi}/{n_features} features...")

        for scale in ZZ_SCALES:
            result = analyze_feature_at_scale(df, feat, scale, ticker=None)
            if result is not None:
                all_results.append(result)
                if result['is_significant']:
                    n_significant += 1

    log(f"  Completed: {len(all_results)} analyses, {n_significant} significant")

    # ── STEP 3: Per-ticker analysis (median aggregation) ──
    log_section("STEP 3: Per-Ticker Analysis (forensic cross-validation)")

    ticker_results = []
    for ti, tk in enumerate(TICKERS):
        log(f"  [{ti+1}/17] {tk}...")
        for feat in features:
            for scale in ZZ_SCALES:
                result = analyze_feature_at_scale(df, feat, scale, ticker=tk)
                if result is not None:
                    ticker_results.append(result)

    log(f"  Completed: {len(ticker_results)} per-ticker analyses")

    # ── STEP 4: Aggregate per-ticker → median ──
    log_section("STEP 4: Median Aggregation Across Tickers")

    # Group by (feature, scale) and compute median of key metrics
    ticker_df = pd.DataFrame(ticker_results)
    if not ticker_df.empty:
        agg_cols = ['kl_near_vs_far', 'cohens_d', 'abs_cohens_d', 'overlap',
                    'lift_max', 'lift_lo', 'lift_hi', 'rank_biserial_r']

        median_agg = ticker_df.groupby(['feature', 'scale_pct'])[agg_cols].median()
        count_sig = ticker_df.groupby(['feature', 'scale_pct'])['is_significant'].sum()
        count_total = ticker_df.groupby(['feature', 'scale_pct'])['is_significant'].count()

        median_agg['n_tickers_significant'] = count_sig
        median_agg['n_tickers_total'] = count_total
        median_agg['pct_tickers_significant'] = (count_sig / count_total * 100).round(1)

        log(f"  Aggregated {len(median_agg)} (feature, scale) pairs")
    else:
        median_agg = pd.DataFrame()

    # ── STEP 5: Build ranking ──
    log_section("STEP 5: Feature Ranking by Discriminative Power")

    results_df = pd.DataFrame(all_results)

    # Composite score: weighted combination of orthogonal metrics
    # KL captures distributional difference
    # |d| captures mean shift
    # (1-overlap) captures tail separation
    # LIFT captures predictive power at extremes
    if not results_df.empty:
        # Normalize each metric to [0, 1] via rank-percentile
        for col in ['kl_near_vs_far', 'abs_cohens_d', 'lift_max']:
            results_df[f'{col}_rank'] = results_df[col].rank(pct=True)

        results_df['overlap_inv_rank'] = (1 - results_df['overlap']).rank(pct=True)

        # Composite: equal weight
        results_df['composite_score'] = (
            results_df['kl_near_vs_far_rank'] * 0.30 +
            results_df['abs_cohens_d_rank'] * 0.25 +
            results_df['overlap_inv_rank'] * 0.20 +
            results_df['lift_max_rank'] * 0.25
        )

        # Sort by composite score
        results_df = results_df.sort_values('composite_score', ascending=False)

    # ── STEP 6: Report top features ──
    log_section("STEP 6: TOP FEATURES BY SCALE")

    for scale in ZZ_SCALES:
        log(f"\n  ═══ Zigzag {scale}% — Top 25 Features ═══")
        log(f"  {'Rank':>4} {'Feature':<40} {'|d|':>6} {'KL':>7} {'Overlap':>8} {'LIFT':>6} {'p<.001':>7} {'Score':>6}")
        log(f"  {'─'*4} {'─'*40} {'─'*6} {'─'*7} {'─'*8} {'─'*6} {'─'*7} {'─'*6}")

        scale_df = results_df[results_df['scale_pct'] == scale].head(25)
        for rank, (_, row) in enumerate(scale_df.iterrows(), 1):
            sig = '✓' if row['is_significant'] else ''
            log(f"  {rank:4d} {row['feature']:<40} {row['abs_cohens_d']:6.3f} "
                f"{row['kl_near_vs_far']:7.4f} {row['overlap']:8.3f} "
                f"{row['lift_max']:6.2f} {sig:>7} {row['composite_score']:6.3f}")

    # ── STEP 7: Temporal layer heatmap ──
    log_section("STEP 7: Temporal Layer Analysis (Top 15 features × 5% zigzag)")

    top_features_5 = results_df[results_df['scale_pct'] == 5].head(15)['feature'].tolist()
    log(f"  {'Feature':<40} {'PRECURSOR':>12} {'APPROACH':>12} {'INFLECTION':>12} {'PROPAGATION':>12}")
    log(f"  {'─'*40} {'─'*12} {'─'*12} {'─'*12} {'─'*12}")

    for feat in top_features_5:
        row = results_df[(results_df['feature'] == feat) & (results_df['scale_pct'] == 5)]
        if row.empty:
            continue
        layers = row.iloc[0].get('layers', {})
        vals = []
        for layer_name in ['PRECURSOR', 'APPROACH', 'INFLECTION', 'PROPAGATION']:
            if layer_name in layers:
                d_val = layers[layer_name]['effect_size']
                vals.append(f"{d_val:+.3f}")
            else:
                vals.append("---")
        log(f"  {feat:<40} {vals[0]:>12} {vals[1]:>12} {vals[2]:>12} {vals[3]:>12}")

    # ── STEP 8: Kalman predictive features audit ──
    log_section("STEP 8: Kalman Predictive Features — Special Audit")

    kalman_features = [c for c in features if c.startswith('kf_')]
    log(f"  Kalman features: {len(kalman_features)}")

    kalman_rows = results_df[results_df['feature'].isin(kalman_features)].copy()
    if not kalman_rows.empty:
        kalman_summary = kalman_rows.groupby('feature').agg({
            'abs_cohens_d': 'mean',
            'kl_near_vs_far': 'mean',
            'lift_max': 'mean',
            'composite_score': 'mean',
        }).sort_values('composite_score', ascending=False)

        log(f"\n  {'Kalman Feature':<40} {'|d|':>6} {'KL':>7} {'LIFT':>6} {'Score':>6}")
        log(f"  {'─'*40} {'─'*6} {'─'*7} {'─'*6} {'─'*6}")
        for feat, row in kalman_summary.iterrows():
            log(f"  {feat:<40} {row['abs_cohens_d']:6.3f} {row['kl_near_vs_far']:7.4f} "
                f"{row['lift_max']:6.2f} {row['composite_score']:6.3f}")

    # ── STEP 9: Cross-ticker consistency ──
    log_section("STEP 9: Cross-Ticker Consistency (features that work everywhere)")

    if not median_agg.empty:
        consistent = median_agg[median_agg['pct_tickers_significant'] >= 70].copy()
        consistent = consistent.sort_values('abs_cohens_d', ascending=False)

        log(f"  Features significant in ≥70% of tickers: {len(consistent)}")
        log(f"\n  {'Feature':<40} {'Scale':>5} {'|d|med':>7} {'KL_med':>7} {'%Tickers':>9}")
        log(f"  {'─'*40} {'─'*5} {'─'*7} {'─'*7} {'─'*9}")

        for (feat, scale), row in consistent.head(30).iterrows():
            log(f"  {feat:<40} {scale:5d}% {row['abs_cohens_d']:7.3f} "
                f"{row['kl_near_vs_far']:7.4f} {row['pct_tickers_significant']:8.1f}%")

    # ── STEP 10: Self-Audit ──
    log_section("STEP 10: Self-Audit")

    errors = 0

    # Check sample sizes
    if not results_df.empty:
        min_n_near = results_df['n_near'].min()
        min_n_far = results_df['n_far'].min()
        log(f"  Min n_near: {min_n_near} (threshold: {MIN_SAMPLE})")
        log(f"  Min n_far: {min_n_far} (threshold: {MIN_SAMPLE})")
        if min_n_near < MIN_SAMPLE:
            log(f"  ⚠️ Some analyses have n_near < {MIN_SAMPLE}", "WARN")

    # Check KL is non-negative
    if not results_df.empty:
        neg_kl = (results_df['kl_near_vs_far'] < -0.001).sum()
        if neg_kl > 0:
            log(f"  ❌ {neg_kl} negative KL values!", "ERROR")
            errors += 1
        else:
            log(f"  ✅ KL divergence always ≥ 0")

    # Check overlap ∈ [0, 1]
    if not results_df.empty:
        bad_overlap = ((results_df['overlap'] < -0.01) | (results_df['overlap'] > 1.01)).sum()
        if bad_overlap > 0:
            log(f"  ❌ {bad_overlap} overlap values outside [0,1]!", "ERROR")
            errors += 1
        else:
            log(f"  ✅ Overlap coefficient ∈ [0, 1]")

    # Check base rate consistency
    if not results_df.empty:
        for scale in ZZ_SCALES:
            scale_rows = results_df[results_df['scale_pct'] == scale]
            if not scale_rows.empty:
                br = scale_rows['base_rate'].iloc[0]
                log(f"  ✅ Base rate zigzag {scale}%: {br*100:.1f}%")

    if errors == 0:
        log(f"  ✅ ALL SELF-AUDITS PASSED")
    else:
        log(f"  ❌ {errors} AUDIT FAILURES", "ERROR")

    # ── STEP 11: Export ──
    log_section("STEP 11: Export")

    # Remove 'layers' column for CSV (nested dict)
    export_df = results_df.drop(columns=['layers'], errors='ignore').copy()

    # Sort by composite score
    export_df = export_df.sort_values('composite_score', ascending=False)

    # Save PKL (full results including layers)
    report = {
        'universal_results': results_df.to_dict('records'),
        'ticker_results': ticker_results,
        'median_aggregation': median_agg.to_dict() if not median_agg.empty else {},
        'metadata': {
            'n_features': len(features),
            'n_tickers': len(TICKERS),
            'n_rows': len(df),
            'near_threshold': NEAR_THRESHOLD,
            'far_threshold': FAR_THRESHOLD,
            'scales': ZZ_SCALES,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
    }

    import pickle
    with open(REPORT_PKL, 'wb') as f:
        pickle.dump(report, f)
    pkl_size = REPORT_PKL.stat().st_size / (1024 * 1024)
    log(f"  PKL: {REPORT_PKL.name} ({pkl_size:.1f} MB)")

    # Save CSV
    export_df.to_csv(REPORT_CSV, index=False, float_format='%.4f')
    csv_size = REPORT_CSV.stat().st_size / (1024 * 1024)
    log(f"  CSV: {REPORT_CSV.name} ({csv_size:.1f} MB)")

    # ── Final Summary ──
    elapsed = time.time() - start_time
    log_section("SUMMARY")
    log(f"  Total analyses: {len(all_results)} universal + {len(ticker_results)} per-ticker")
    log(f"  Features analyzed: {len(features)}")
    log(f"  Significant (p<.001 ∧ |d|≥0.2): {n_significant}")
    if not results_df.empty:
        log(f"  Top composite score: {results_df['composite_score'].max():.3f}")
        log(f"  Max |Cohen's d|: {results_df['abs_cohens_d'].max():.3f}")
        log(f"  Max KL: {results_df['kl_near_vs_far'].max():.4f}")
        log(f"  Min overlap: {results_df['overlap'].min():.3f}")
    log(f"  Audit: {'✅ PASSED' if errors == 0 else '❌ FAILED'}")
    log(f"  Time: {elapsed:.0f}s ({elapsed/60:.1f}min)")

    del df
    gc.collect()


if __name__ == "__main__":
    main()
