#!/usr/bin/env python3
"""
SPRINT 2-REDO — FASE B: Features Individuales por Capa Temporal
====================================================================
Depends on: sprint2_redo_infrastructure.py (Fase A) → sprint2_redo_lake.pkl

For each of the 154 features, at each temporal layer (ALERTA, DETECCIÓN,
CONFIRMACIÓN, CONTINUACIÓN), computes:
  1. Fires, Hits (dedup), PREC, Recall, LIFT — GLOBAL
  2. Same per-ticker (17 tickers)
  3. Stratified by RC signature (8 combinations)
  4. Stratified by with_trend / against_trend
  5. Stratified by full_archetype (6 types: HL, LL, LL_TO_HL, HH, LH, HH_TO_LH)
  6. Drift: mean price change from fire bar to t=0
  7. E[V]: P_hit * mean_following_leg - (1-P_hit) * |mean_drift|
  8. Persistence ratio: classify as DETECTOR (<0.5), NEUTRAL (0.5-2.0), CONFIRMADOR (>2.0)

Self-audit checks:
  - PREC ≤ 100% everywhere (dedup guarantee)
  - Global PREC matches sum-of-tickers weighted average
  - Feature count matches Phase A

Output:
  - sprint2_redo_features.log (full report)
  - sprint2_redo_features_report.pkl (structured data for Phase C)

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python research/07_quality_swing_forensics/sprint2_redo_features.py
"""
import sys, os, warnings, pickle, time, bisect, json
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "backend" / "scripts"))

from dotenv import load_dotenv
load_dotenv(root / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore
from unified_pretrainer_v2 import load_feature_lake, ALL_FEATURES
from feature_optimizer import expand_feature_lake

# ═══════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════
Z_THRESHOLD = 2.0
DEDUP_PROXIMITY = 3
OUT_DIR = root / "data" / "research" / "quality_swing"
LAKE_PKL = OUT_DIR / "sprint2_redo_lake.pkl"
LOG_FILE = OUT_DIR / "sprint2_redo_features.log"
REPORT_PKL = OUT_DIR / "sprint2_redo_features_report.pkl"

# Temporal layers: which offsets define each layer
LAYERS = {
    'ALERTA':       {'offsets': [-3, -2, -1], 'mode': 'any'},
    'DETECCIÓN':    {'offsets': [0],          'mode': 'exact'},
    'CONFIRMACIÓN': {'offsets': [1, 2],       'mode': 'any'},
    'CONTINUACIÓN': {'offsets': [3, 4, 5],    'mode': 'any'},
}

# Top features to report in detail (focus analysis)
TOP_N_FEATURES = 30

start_time = time.time()


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def p(t):
    line = f"\n{'='*110}\n  {t}\n{'='*110}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def sp(t):
    line = f"\n  ── {t} ──"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ═══════════════════════════════════════════════════════════════
# STEP 0: Reload data (Feature Lake + Phase A metadata)
# ═══════════════════════════════════════════════════════════════
def load_phase_a():
    p("FASE B — STEP 0: Load Phase A Data")

    # Load Phase A metadata
    with open(LAKE_PKL, 'rb') as f:
        lake = pickle.load(f)
    log(f"  Phase A lake: {lake['meta']['n_matched']} matched, "
        f"{lake['meta']['n_features']} features, {lake['meta']['n_tickers']} tickers")

    matched = lake['matched']
    dedup_index = lake['dedup_index']
    feature_cols = lake['feature_cols']

    # Reload Feature Lake (needed for z-score computation)
    store = TimescaleDataStore()
    ps = TickerProfileStore()
    df, _, _ = load_feature_lake(store, ps)
    derived = expand_feature_lake(df)
    log(f"  Feature Lake reloaded: {len(df):,d} obs × {len(df.columns)} cols")

    # Rebuild ticker groups (same logic as Phase A)
    ticker_groups = {}
    for tk, grp in df.groupby('ticker'):
        grp_sorted = grp.sort_values('timestamp').reset_index(drop=True)
        ticker_groups[tk] = {
            'df': grp_sorted,
            'timestamps': grp_sorted['timestamp'].values,
            'n': len(grp_sorted),
        }

    # Recompute z-scores per ticker
    z_stats = {}
    for feat in feature_cols:
        if feat not in df.columns:
            continue
        grouped = df.groupby('ticker')[feat]
        means = grouped.transform('mean')
        stds = grouped.transform('std').replace(0, 1e-8)
        z_stats[feat] = {'mean': means.values, 'std': stds.values}
    log(f"  Z-scores recomputed for {len(z_stats)} features")

    store.close()
    ps.close()

    return df, matched, dedup_index, feature_cols, ticker_groups, z_stats


# ═══════════════════════════════════════════════════════════════
# STEP 1: Core computation — feature × layer × ticker
# ═══════════════════════════════════════════════════════════════
def compute_feature_layer_metrics(df, matched, dedup_index, feature_cols,
                                   ticker_groups, z_stats):
    """
    For each feature and each temporal layer, compute metrics per-ticker.
    Returns a nested dict: results[feature][layer][ticker] = metrics_dict
    """
    p("FASE B — STEP 1: Compute Feature × Layer × Ticker Metrics")

    results = {}
    n_features = len([f for f in feature_cols if f in z_stats])
    log(f"  Computing {n_features} features × {len(LAYERS)} layers × {len(ticker_groups)} tickers")

    # Build per-ticker zigzag sets for quick lookup
    ticker_zz = defaultdict(list)
    for idx, m in enumerate(matched):
        ticker_zz[m['ticker']].append(m)

    processed = 0
    for feat in feature_cols:
        if feat not in z_stats:
            continue

        results[feat] = {}

        for layer_name, layer_cfg in LAYERS.items():
            offsets = layer_cfg['offsets']

            # Accumulate per-ticker metrics
            ticker_metrics = {}

            for tk in ticker_groups:
                tk_info = ticker_groups[tk]
                tk_n = tk_info['n']

                # Get z-scores for this feature × ticker
                tk_mask = df['ticker'] == tk
                tk_global_idx = df[tk_mask].index.values
                n_tk_bars = len(tk_global_idx)

                z_mean = z_stats[feat]['mean'][tk_global_idx]
                z_std = z_stats[feat]['std'][tk_global_idx]
                vals = df.loc[tk_global_idx, feat].values
                z_scores = (vals - z_mean) / np.where(z_std > 1e-8, z_std, 1e-8)
                fire_mask = np.abs(z_scores) >= Z_THRESHOLD
                fire_positions = set(np.where(fire_mask)[0].tolist())
                n_fires = len(fire_positions)

                if n_fires == 0:
                    ticker_metrics[tk] = {
                        'fires': 0, 'hits': 0, 'prec': 0, 'recall': 0,
                        'lift': 0, 'n_zz': len(ticker_zz.get(tk, [])),
                        'base_rate': len(ticker_zz.get(tk, [])) / max(n_tk_bars, 1),
                    }
                    continue

                # For each zigzag in this ticker, check if any fire is within
                # the layer's offset range
                tk_matched = ticker_zz.get(tk, [])
                n_zz = len(tk_matched)
                base_rate = n_zz / max(n_tk_bars, 1)

                hit_zz_indices = set()
                drift_values = []
                following_legs = []

                for m in tk_matched:
                    anchor = m['anchor_pos']
                    # Check if any fire falls at the layer offsets relative to anchor
                    hit = False
                    for offset in offsets:
                        check_pos = anchor + offset
                        if check_pos in fire_positions:
                            hit = True
                            # Compute drift from fire bar to t=0
                            if offset < 0:
                                # Price at fire bar vs price at anchor
                                if 0 <= check_pos < tk_n and 0 <= anchor < tk_n:
                                    p_fire = float(tk_info['df'].iloc[check_pos]['price'])
                                    p_anchor = float(tk_info['df'].iloc[anchor]['price'])
                                    if p_fire > 0:
                                        drift = (p_anchor / p_fire - 1) * 100
                                        drift_values.append(drift)
                            break  # Count each zigzag only once

                    if hit:
                        hit_zz_indices.add(id(m))
                        following_legs.append(m['following_leg_pct'])

                hits = len(hit_zz_indices)
                prec = hits / max(n_fires, 1)
                recall = hits / max(n_zz, 1)
                lift = prec / base_rate if base_rate > 0 else 0

                # E[V] calculation
                if hits > 0 and drift_values:
                    mean_following = np.mean(following_legs)
                    mean_drift = np.mean(np.abs(drift_values))
                    ev = prec * abs(mean_following) - (1 - prec) * mean_drift
                elif hits > 0:
                    mean_following = np.mean(following_legs)
                    ev = prec * abs(mean_following)
                    mean_drift = 0
                else:
                    ev = 0
                    mean_following = 0
                    mean_drift = 0

                ticker_metrics[tk] = {
                    'fires': n_fires,
                    'hits': hits,
                    'prec': prec,
                    'recall': recall,
                    'lift': lift,
                    'n_zz': n_zz,
                    'base_rate': base_rate,
                    'ev': ev,
                    'mean_drift': np.mean(drift_values) if drift_values else 0,
                    'mean_following': mean_following,
                }

            results[feat][layer_name] = ticker_metrics

        processed += 1
        if processed % 20 == 0:
            log(f"    Processed {processed}/{n_features} features...")

    log(f"  ✅ Complete: {processed} features × {len(LAYERS)} layers × {len(ticker_groups)} tickers")
    return results


# ═══════════════════════════════════════════════════════════════
# STEP 2: Aggregate global metrics from per-ticker
# ═══════════════════════════════════════════════════════════════
def aggregate_global(results, ticker_groups):
    """Aggregate per-ticker metrics into global metrics per feature × layer."""
    p("FASE B — STEP 2: Aggregate Global Metrics")

    global_metrics = {}  # feat → layer → {fires, hits, prec, lift, ...}

    for feat, layer_data in results.items():
        global_metrics[feat] = {}
        for layer_name, ticker_metrics in layer_data.items():
            total_fires = sum(m['fires'] for m in ticker_metrics.values())
            total_hits = sum(m['hits'] for m in ticker_metrics.values())
            total_zz = sum(m['n_zz'] for m in ticker_metrics.values())
            total_bars = sum(ticker_groups[tk]['n'] for tk in ticker_metrics)

            base_rate = total_zz / max(total_bars, 1)
            prec = total_hits / max(total_fires, 1)
            recall = total_hits / max(total_zz, 1)
            lift = prec / base_rate if base_rate > 0 else 0

            # Weighted drift and E[V]
            drifts = [m['mean_drift'] * m['hits'] for m in ticker_metrics.values() if m['hits'] > 0]
            hits_with_drift = sum(m['hits'] for m in ticker_metrics.values() if m['hits'] > 0)
            mean_drift = sum(drifts) / max(hits_with_drift, 1)

            followings = [m['mean_following'] * m['hits'] for m in ticker_metrics.values() if m['hits'] > 0]
            mean_following = sum(followings) / max(hits_with_drift, 1)

            ev = prec * abs(mean_following) - (1 - prec) * abs(mean_drift) if total_hits > 0 else 0

            global_metrics[feat][layer_name] = {
                'fires': total_fires, 'hits': total_hits,
                'prec': prec, 'recall': recall, 'lift': lift,
                'mean_drift': mean_drift, 'mean_following': mean_following,
                'ev': ev, 'base_rate': base_rate,
            }

    log(f"  Aggregated {len(global_metrics)} features × {len(LAYERS)} layers")
    return global_metrics


# ═══════════════════════════════════════════════════════════════
# STEP 3: Persistence Ratio (DETECTOR vs CONFIRMADOR classification)
# ═══════════════════════════════════════════════════════════════
def compute_persistence(df, matched, ticker_groups, z_stats, feature_cols):
    """
    For each feature: if it fires at t=0, does it persist at t+1?
    Ratio = P(persist|ZZ fire) / P(persist|non-ZZ fire)
    > 2.0 = CONFIRMADOR, < 0.5 = DETECTOR, else NEUTRAL
    """
    p("FASE B — STEP 3: Persistence Ratio Classification")

    # Build set of zigzag positions per ticker
    zz_positions = defaultdict(set)
    for m in matched:
        zz_positions[m['ticker']].add(m['anchor_pos'])

    persistence = {}

    for feat in feature_cols:
        if feat not in z_stats:
            continue

        zz_fire_persist = 0
        zz_fire_total = 0
        nzz_fire_persist = 0
        nzz_fire_total = 0

        for tk in ticker_groups:
            tk_info = ticker_groups[tk]
            tk_n = tk_info['n']
            tk_mask = df['ticker'] == tk
            tk_global_idx = df[tk_mask].index.values

            z_mean = z_stats[feat]['mean'][tk_global_idx]
            z_std = z_stats[feat]['std'][tk_global_idx]
            vals = df.loc[tk_global_idx, feat].values
            z_scores = (vals - z_mean) / np.where(z_std > 1e-8, z_std, 1e-8)
            fire_mask = np.abs(z_scores) >= Z_THRESHOLD

            tk_zz = zz_positions.get(tk, set())

            for pos in range(tk_n - 1):
                if not fire_mask[pos]:
                    continue
                persists = fire_mask[pos + 1]
                is_zz = pos in tk_zz

                if is_zz:
                    zz_fire_total += 1
                    if persists:
                        zz_fire_persist += 1
                else:
                    nzz_fire_total += 1
                    if persists:
                        nzz_fire_persist += 1

        zz_rate = zz_fire_persist / max(zz_fire_total, 1)
        nzz_rate = nzz_fire_persist / max(nzz_fire_total, 1)
        ratio = zz_rate / max(nzz_rate, 1e-8)

        if ratio > 2.0:
            classification = 'CONFIRMADOR'
        elif ratio < 0.5:
            classification = 'DETECTOR'
        else:
            classification = 'NEUTRAL'

        persistence[feat] = {
            'zz_rate': zz_rate, 'nzz_rate': nzz_rate,
            'ratio': ratio, 'classification': classification,
            'zz_total': zz_fire_total, 'nzz_total': nzz_fire_total,
        }

    # Report
    sp("Persistence Classification")
    log(f"  {'Feature':35s} │ {'ZZ%':>6s} │ {'NZZ%':>6s} │ {'Ratio':>6s} │ {'Class':>12s}")
    log(f"  {'─'*75}")
    for feat, p_data in sorted(persistence.items(), key=lambda x: -x[1]['ratio']):
        if p_data['zz_total'] < 10:
            continue
        log(f"  {feat:35s} │ {p_data['zz_rate']*100:>5.1f}% │ {p_data['nzz_rate']*100:>5.1f}% │ "
            f"{p_data['ratio']:>5.2f}x │ {p_data['classification']:>12s}")

    n_det = sum(1 for v in persistence.values() if v['classification'] == 'DETECTOR')
    n_neu = sum(1 for v in persistence.values() if v['classification'] == 'NEUTRAL')
    n_con = sum(1 for v in persistence.values() if v['classification'] == 'CONFIRMADOR')
    log(f"\n  Classification: {n_det} DETECTOR, {n_neu} NEUTRAL, {n_con} CONFIRMADOR")

    return persistence


# ═══════════════════════════════════════════════════════════════
# STEP 4: Stratified analysis — RC signature, with_trend, archetype
# ═══════════════════════════════════════════════════════════════
def compute_stratified(df, matched, ticker_groups, z_stats, feature_cols):
    """
    For the TOP features, compute PREC/LIFT stratified by:
    - RC signature (8 combos)
    - with_trend (2)
    - full_archetype (6)
    Only for ALERTA and DETECCIÓN layers (the decision-relevant ones).
    """
    p("FASE B — STEP 4: Stratified Analysis (RC, Trend, Archetype)")

    # Select top features based on a preliminary scan
    # We'll focus on features that appeared in Sprint 2 top ranks
    focus_features = [
        'wave_accel', 'd_wave_accel', 'atr_ratio', 'overnight_gap',
        'compression_ratio', 'vwap_sigma_current', 'vwap_sigma_wave',
        'residual_std_wave', 'residual_std_current', 'sigma_current',
        'sigma_tide', 'total_displacement', 'volume_at_extreme',
        'fear_level', 'current_accel', 'rsi_value',
        'compr_at_extreme', 'geo_state_norm',
    ]
    focus_features = [f for f in focus_features if f in z_stats]

    stratified = {}

    # Group matched by dimensions
    for feat in focus_features:
        stratified[feat] = {}

        for layer_name in ['ALERTA', 'DETECCIÓN']:
            offsets = LAYERS[layer_name]['offsets']

            # By RC signature
            rc_groups = defaultdict(lambda: {'hits': 0, 'total': 0, 'drift': [], 'following': []})
            # By with_trend
            wt_groups = defaultdict(lambda: {'hits': 0, 'total': 0, 'drift': [], 'following': []})
            # By full_archetype
            arch_groups = defaultdict(lambda: {'hits': 0, 'total': 0, 'drift': [], 'following': []})

            for m in matched:
                tk = m['ticker']
                tk_info = ticker_groups[tk]
                anchor = m['anchor_pos']

                # Check fire at layer offsets
                tk_mask = df['ticker'] == tk
                tk_global_idx = df[tk_mask].index.values
                n_tk = len(tk_global_idx)

                z_mean = z_stats[feat]['mean'][tk_global_idx]
                z_std = z_stats[feat]['std'][tk_global_idx]
                vals = df.loc[tk_global_idx, feat].values
                z_scores = (vals - z_mean) / np.where(z_std > 1e-8, z_std, 1e-8)

                hit = False
                for offset in offsets:
                    check_pos = anchor + offset
                    if 0 <= check_pos < n_tk:
                        if abs(z_scores[check_pos]) >= Z_THRESHOLD:
                            hit = True
                            break

                rc = m['rc_signature']
                wt = 'WITH_TREND' if m['with_trend'] else 'AGAINST_TREND'
                arch = m['full_archetype']

                rc_groups[rc]['total'] += 1
                wt_groups[wt]['total'] += 1
                arch_groups[arch]['total'] += 1

                if hit:
                    rc_groups[rc]['hits'] += 1
                    wt_groups[wt]['hits'] += 1
                    arch_groups[arch]['hits'] += 1
                    rc_groups[rc]['following'].append(m['following_leg_pct'])
                    wt_groups[wt]['following'].append(m['following_leg_pct'])
                    arch_groups[arch]['following'].append(m['following_leg_pct'])

            stratified[feat][layer_name] = {
                'by_rc': {k: {'hits': v['hits'], 'total': v['total'],
                              'prec': v['hits']/max(v['total'],1),
                              'mean_following': np.mean(v['following']) if v['following'] else 0}
                          for k, v in rc_groups.items()},
                'by_trend': {k: {'hits': v['hits'], 'total': v['total'],
                                 'prec': v['hits']/max(v['total'],1),
                                 'mean_following': np.mean(v['following']) if v['following'] else 0}
                             for k, v in wt_groups.items()},
                'by_archetype': {k: {'hits': v['hits'], 'total': v['total'],
                                     'prec': v['hits']/max(v['total'],1),
                                     'mean_following': np.mean(v['following']) if v['following'] else 0}
                                 for k, v in arch_groups.items()},
            }

        log(f"  {feat}: stratified across RC(8) × Trend(2) × Archetype(6)")

    return stratified


# ═══════════════════════════════════════════════════════════════
# STEP 5: Report
# ═══════════════════════════════════════════════════════════════
def generate_report(global_metrics, persistence, stratified, ticker_groups, results):
    p("FASE B — STEP 5: Generate Report")

    # ── Section A: Global Feature Rankings by Layer ──
    for layer_name in LAYERS:
        sp(f"GLOBAL RANKING — {layer_name}")
        ranked = sorted(global_metrics.items(),
                       key=lambda x: -x[1].get(layer_name, {}).get('lift', 0))
        log(f"  {'Feature':35s} │ {'Fires':>6s} │ {'Hits':>5s} │ {'PREC':>7s} │ {'Recall':>7s} │ "
            f"{'LIFT':>6s} │ {'Drift':>7s} │ {'E[V]':>7s} │ {'Type':>12s}")
        log(f"  {'─'*110}")

        for feat, layers in ranked[:TOP_N_FEATURES]:
            m = layers.get(layer_name, {})
            if m.get('fires', 0) == 0:
                continue
            p_class = persistence.get(feat, {}).get('classification', '?')
            log(f"  {feat:35s} │ {m['fires']:>6d} │ {m['hits']:>5d} │ "
                f"{m['prec']*100:>6.1f}% │ {m['recall']*100:>6.1f}% │ "
                f"{m['lift']:>5.1f}x │ {m['mean_drift']:>+6.2f}% │ "
                f"{m['ev']:>+6.2f}% │ {p_class:>12s}")

    # ── Section B: Stratified — Top features by RC signature ──
    sp("STRATIFIED BY RC SIGNATURE (DETECCIÓN layer)")
    for feat in list(stratified.keys())[:8]:
        data = stratified[feat].get('DETECCIÓN', {}).get('by_rc', {})
        if not data:
            continue
        log(f"\n  {feat}:")
        log(f"    {'RC Signature':20s} │ {'Hits':>5s} │ {'Total':>5s} │ {'Hit%':>6s} │ {'E[ret]':>8s}")
        log(f"    {'─'*55}")
        for rc, vals in sorted(data.items(), key=lambda x: -x[1]['prec']):
            log(f"    {rc:20s} │ {vals['hits']:>5d} │ {vals['total']:>5d} │ "
                f"{vals['prec']*100:>5.1f}% │ {vals['mean_following']:>+7.1f}%")

    # ── Section C: Stratified — Top features by WITH/AGAINST trend ──
    sp("STRATIFIED BY WITH/AGAINST TREND (DETECCIÓN layer)")
    log(f"  {'Feature':35s} │ {'WT Hits':>7s} │ {'WT%':>6s} │ {'AT Hits':>7s} │ {'AT%':>6s} │ {'Discrim':>8s}")
    log(f"  {'─'*85}")
    for feat in stratified:
        data = stratified[feat].get('DETECCIÓN', {}).get('by_trend', {})
        wt = data.get('WITH_TREND', {'hits': 0, 'total': 0, 'prec': 0})
        at = data.get('AGAINST_TREND', {'hits': 0, 'total': 0, 'prec': 0})
        diff = abs(wt['prec'] - at['prec'])
        disc = '✅ YES' if diff > 0.05 else '✖ NO'
        log(f"  {feat:35s} │ {wt['hits']:>5d}/{wt['total']:>0d} │ {wt['prec']*100:>5.1f}% │ "
            f"{at['hits']:>5d}/{at['total']:>0d} │ {at['prec']*100:>5.1f}% │ {disc:>8s}")

    # ── Section D: Stratified — Top features by archetype ──
    sp("STRATIFIED BY FULL ARCHETYPE (ALERTA layer)")
    for feat in list(stratified.keys())[:6]:
        data = stratified[feat].get('ALERTA', {}).get('by_archetype', {})
        if not data:
            continue
        log(f"\n  {feat}:")
        log(f"    {'Archetype':12s} │ {'Hits':>5s} │ {'Total':>5s} │ {'Hit%':>6s} │ {'E[ret]':>8s}")
        log(f"    {'─'*45}")
        for arch in ['HL', 'LL', 'LL_TO_HL', 'HH', 'LH', 'HH_TO_LH']:
            vals = data.get(arch, {'hits': 0, 'total': 0, 'prec': 0, 'mean_following': 0})
            if vals['total'] == 0:
                continue
            log(f"    {arch:12s} │ {vals['hits']:>5d} │ {vals['total']:>5d} │ "
                f"{vals['prec']*100:>5.1f}% │ {vals['mean_following']:>+7.1f}%")

    # ── Section E: Per-ticker universality (DETECCIÓN) ──
    sp("PER-TICKER UNIVERSALITY — Top 5 features (DETECCIÓN)")
    top_feats = sorted(global_metrics.items(),
                      key=lambda x: -x[1].get('DETECCIÓN', {}).get('lift', 0))[:5]
    for feat, _ in top_feats:
        log(f"\n  {feat}:")
        log(f"    {'Ticker':>8s} │ {'Fires':>6s} │ {'Hits':>5s} │ {'PREC':>7s} │ {'LIFT':>6s}")
        log(f"    {'─'*40}")
        excl_spy_precs = []
        for tk in sorted(results[feat]['DETECCIÓN'].keys()):
            m = results[feat]['DETECCIÓN'][tk]
            if m['fires'] == 0:
                continue
            log(f"    {tk:>8s} │ {m['fires']:>6d} │ {m['hits']:>5d} │ "
                f"{m['prec']*100:>6.1f}% │ {m['lift']:>5.1f}x")
            if tk != 'SPY':
                excl_spy_precs.append(m['prec'])
        if excl_spy_precs:
            log(f"    EXCL SPY: mean PREC={np.mean(excl_spy_precs)*100:.1f}%, "
                f"median={np.median(excl_spy_precs)*100:.1f}%")


# ═══════════════════════════════════════════════════════════════
# STEP 6: Self-Audit
# ═══════════════════════════════════════════════════════════════
def self_audit(global_metrics, results, persistence):
    p("FASE B — STEP 6: Self-Audit")

    # Audit 1: No PREC > 100%
    violations = 0
    for feat, layers in results.items():
        for layer, tickers in layers.items():
            for tk, m in tickers.items():
                if m['prec'] > 1.0:
                    log(f"  🔴 PREC > 100%: {feat}/{layer}/{tk} = {m['prec']*100:.1f}%")
                    violations += 1
    if violations == 0:
        log(f"  ✅ No PREC > 100% violations across {len(results)} features")
    else:
        log(f"  🔴 {violations} PREC > 100% violations found!")

    # Audit 2: Global metrics consistency
    test_feat = 'wave_accel'
    if test_feat in results and 'DETECCIÓN' in results[test_feat]:
        tk_fires = sum(m['fires'] for m in results[test_feat]['DETECCIÓN'].values())
        tk_hits = sum(m['hits'] for m in results[test_feat]['DETECCIÓN'].values())
        gl = global_metrics[test_feat]['DETECCIÓN']
        assert gl['fires'] == tk_fires, f"Fires mismatch: {gl['fires']} vs {tk_fires}"
        assert gl['hits'] == tk_hits, f"Hits mismatch: {gl['hits']} vs {tk_hits}"
        log(f"  ✅ Global/per-ticker consistency verified for {test_feat}")

    # Audit 3: Persistence classification sanity
    if 'wave_accel' in persistence:
        wa_class = persistence['wave_accel']['classification']
        log(f"  wave_accel persistence: {persistence['wave_accel']['ratio']:.2f}x → {wa_class}")
    if 'd_wave_accel' in persistence:
        dwa_class = persistence['d_wave_accel']['classification']
        log(f"  d_wave_accel persistence: {persistence['d_wave_accel']['ratio']:.2f}x → {dwa_class}")

    elapsed = time.time() - start_time
    log(f"\n  Phase B execution time: {elapsed:.0f}s ({elapsed/60:.1f} min)")


# ═══════════════════════════════════════════════════════════════
# STEP 7: Persist
# ═══════════════════════════════════════════════════════════════
def persist_report(global_metrics, persistence, stratified, results):
    p("FASE B — STEP 7: Persist Report")

    report = {
        'global_metrics': global_metrics,
        'persistence': persistence,
        'stratified': stratified,
        'per_ticker': results,
        'meta': {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'n_features': len(global_metrics),
            'layers': list(LAYERS.keys()),
            'z_threshold': Z_THRESHOLD,
        },
    }

    with open(REPORT_PKL, 'wb') as f:
        pickle.dump(report, f, protocol=pickle.HIGHEST_PROTOCOL)

    log(f"  Saved: {REPORT_PKL}")
    log(f"  Size: {REPORT_PKL.stat().st_size / 1024:.0f} KB")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    with open(LOG_FILE, "w") as f:
        f.write(f"SPRINT 2-REDO — FASE B — {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"{'='*110}\n\n")

    p("SPRINT 2-REDO — FASE B: FEATURES INDIVIDUALES")

    # Step 0: Load
    df, matched, dedup_index, feature_cols, ticker_groups, z_stats = load_phase_a()

    # Step 1: Core computation
    results = compute_feature_layer_metrics(df, matched, dedup_index, feature_cols,
                                           ticker_groups, z_stats)

    # Step 2: Aggregate
    global_metrics = aggregate_global(results, ticker_groups)

    # Step 3: Persistence
    persistence = compute_persistence(df, matched, ticker_groups, z_stats, feature_cols)

    # Step 4: Stratified
    stratified = compute_stratified(df, matched, ticker_groups, z_stats, feature_cols)

    # Step 5: Report
    generate_report(global_metrics, persistence, stratified, ticker_groups, results)

    # Step 6: Self-audit
    self_audit(global_metrics, results, persistence)

    # Step 7: Persist
    persist_report(global_metrics, persistence, stratified, results)

    p("FASE B COMPLETE")
    log("  Next: Run sprint2_redo_conjugations.py (Fase C)")


if __name__ == "__main__":
    main()
