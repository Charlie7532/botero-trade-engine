#!/usr/bin/env python3
"""
SPRINT 2-REDO — FASE C v2.1: La Película del Giro
====================================================================
Reverse-engineers the turn sequence for every zigzag turn point.

For each turn:
  1. Classify archetype (HL, LL, HH, LH) by comparing with previous turn
  2. Trace z-score activation sequence backwards from t=0
  3. Measure density curve (how many features are active per bar)
  4. Record which feature fires FIRST (alarm feature)
  5. Measure pressurization ramp slope
  6. Snapshot at t=0 (explosion energy)
  7. Measure post-turn confirmation decay

Segmentation:
  - By archetype (HL, LL, HH, LH)
  - By direction (BOTTOM = MIN turns, TOP = MAX turns)
  - By zigzag scale (3%, 5%, 7%)
  - By ticker

Forensic output:
  - Activation sequence per archetype
  - Lead time distribution per feature
  - Primacy rankings (which feature fires first most often)
  - Density ramp profiles per archetype
  - Archetype-specific feature signatures

Depends on:
  - sprint2_redo_lake_v21.pkl (Feature Lake)
  - sprint2_redo_phase_b_v21.pkl (Phase B rankings for top feature selection)

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scratch/sprint2_redo_phase_c_v21.py
"""
import sys
import os
import warnings
import time
import gc
import pickle
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict, Counter

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))

# ═══════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════
OUT_DIR = root / "backend" / "scratch"
LAKE_PKL = OUT_DIR / "sprint2_redo_lake_v21.pkl"
PHASE_B_PKL = OUT_DIR / "sprint2_redo_phase_b_v21.pkl"
LOG_FILE = OUT_DIR / "sprint2_redo_phase_c_v21.log"
REPORT_PKL = OUT_DIR / "sprint2_redo_phase_c_v21.pkl"
REPORT_CSV = OUT_DIR / "sprint2_redo_phase_c_v21.csv"

# Z-score threshold for feature activation
Z_THRESHOLD = 2.0

# Lookback for alarm detection (bars before turn)
MAX_LOOKBACK = 10

# Post-turn horizon for confirmation
POST_HORIZON = 5

# Top N features to use for density analysis (from Phase B)
TOP_N_FEATURES = 30

# Zigzag scales
ZZ_SCALES = [3, 5, 7]

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
# ARCHETYPE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

def classify_archetypes(df, scale_pct):
    """
    Classify each zigzag turn into an archetype by comparing with the previous turn.

    For MIN turns (bottoms):
      HL = current low > previous low (higher low)
      LL = current low < previous low (lower low)

    For MAX turns (tops):
      LH = current high < previous high (lower high)
      HH = current high > previous high (higher high)

    Uses ONLY the price at each turn and the previous turn of the SAME type.
    This is historical information — no look-ahead bias.
    """
    hit_col = f'hit_zz_{scale_pct}pct'
    type_col = f'zz_{scale_pct}pct_type'
    dist_col = f'dist_zz_{scale_pct}pct'

    archetypes = {}  # (ticker, row_idx) → archetype

    for tk in TICKERS:
        mask = df['ticker'] == tk
        tk_df = df.loc[mask].copy()
        tk_indices = tk_df.index.tolist()

        # Find turn points (dist=0 means exact turn bar)
        turn_mask = tk_df[dist_col] == 0
        turn_rows = tk_df.loc[turn_mask]

        if len(turn_rows) < 2:
            continue

        # Track previous MIN and MAX prices for comparison
        prev_min_price = None
        prev_max_price = None

        for idx in turn_rows.index:
            turn_type = tk_df.at[idx, type_col]
            turn_price = tk_df.at[idx, 'price']

            if turn_type == 'MIN':
                if prev_min_price is not None:
                    if turn_price > prev_min_price:
                        archetypes[(tk, idx)] = 'HL'
                    else:
                        archetypes[(tk, idx)] = 'LL'
                prev_min_price = turn_price

            elif turn_type == 'MAX':
                if prev_max_price is not None:
                    if turn_price > prev_max_price:
                        archetypes[(tk, idx)] = 'HH'
                    else:
                        archetypes[(tk, idx)] = 'LH'
                prev_max_price = turn_price

    return archetypes


# ═══════════════════════════════════════════════════════════════
# TURN ANALYSIS
# ═══════════════════════════════════════════════════════════════

def analyze_turn(z_matrix, feature_names, turn_local_idx, max_lb=MAX_LOOKBACK, post_h=POST_HORIZON):
    """
    Full reverse-engineering of a single turn point.

    Args:
        z_matrix: (n_bars, n_features) array of z-scores per-ticker
        feature_names: list of feature names
        turn_local_idx: local index within the ticker's data
        max_lb: max lookback bars for alarm detection
        post_h: post-turn bars for confirmation

    Returns dict with:
        alarm_lead, alarm_feature, alarm_direction,
        density_curve, ramp_slope, max_density,
        activation_sequence, explosion_energy,
        confirmation_decay, active_features_at_t0
    """
    n_bars, n_feats = z_matrix.shape
    result = {
        'alarm_lead': None,
        'alarm_feature': None,
        'alarm_direction': 0,
        'density_curve': [],
        'ramp_slope': 0.0,
        'max_pre_density': 0,
        'activation_sequence': [],
        'explosion_energy': 0.0,
        'explosion_density': 0,
        'active_features_at_t0': [],
        'confirmation_bars': [],
        'confirmation_decay': 0.0,
    }

    # ── 1. ALARM: Trace backwards from turn ──
    for lb in range(1, min(max_lb + 1, turn_local_idx)):
        bar = turn_local_idx - lb
        z_row = z_matrix[bar]
        activated = np.where(np.abs(z_row) > Z_THRESHOLD)[0]
        if len(activated) > 0:
            # First feature to cross threshold
            first_feat_idx = activated[np.argmax(np.abs(z_row[activated]))]
            result['alarm_lead'] = lb
            result['alarm_feature'] = feature_names[first_feat_idx]
            result['alarm_direction'] = int(np.sign(z_row[first_feat_idx]))
            break

    # ── 2. PRESSURIZATION: Density curve from alarm to turn ──
    start_bar = max(0, turn_local_idx - max_lb)
    density_curve = []
    seen_features = set()
    activation_seq = []

    for bar in range(start_bar, turn_local_idx):
        z_row = z_matrix[bar]
        active_set = set(np.where(np.abs(z_row) > Z_THRESHOLD)[0])
        density_curve.append(len(active_set))

        # Record new activations
        new_activations = active_set - seen_features
        for fi in sorted(new_activations):
            activation_seq.append({
                'offset': bar - turn_local_idx,  # negative = before turn
                'feature': feature_names[fi],
                'z_score': float(z_row[fi]),
            })
            seen_features.add(fi)

    result['density_curve'] = density_curve
    result['activation_sequence'] = activation_seq
    result['max_pre_density'] = max(density_curve) if density_curve else 0

    # Ramp slope (linear fit of density curve)
    if len(density_curve) >= 3:
        x = np.arange(len(density_curve))
        result['ramp_slope'] = float(np.polyfit(x, density_curve, 1)[0])

    # ── 3. EXPLOSION: Snapshot at t=0 ──
    z_t0 = z_matrix[turn_local_idx]
    active_at_t0 = np.abs(z_t0) > Z_THRESHOLD
    extreme_at_t0 = np.abs(z_t0) > 3.0

    result['explosion_density'] = int(active_at_t0.sum())
    result['explosion_energy'] = float(np.sum(z_t0[active_at_t0] ** 2))
    result['active_features_at_t0'] = [
        {'feature': feature_names[i], 'z': float(z_t0[i])}
        for i in np.where(active_at_t0)[0]
    ]

    # ── 4. CONFIRMATION: Post-turn decay ──
    confirmation_bars = []
    for offset in range(1, min(post_h + 1, n_bars - turn_local_idx)):
        bar = turn_local_idx + offset
        z_row = z_matrix[bar]
        active = int((np.abs(z_row) > Z_THRESHOLD).sum())
        confirmation_bars.append(active)

    result['confirmation_bars'] = confirmation_bars
    if len(confirmation_bars) >= 2:
        x = np.arange(len(confirmation_bars))
        result['confirmation_decay'] = float(np.polyfit(x, confirmation_bars, 1)[0])

    return result


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    LOG_FILE.unlink(missing_ok=True)
    log_section("SPRINT 2-REDO — FASE C v2.1: La Película del Giro")
    log(f"Started at {datetime.now(timezone.utc).isoformat()}")

    # ── STEP 1: Load data ──
    log_section("STEP 1: Load Data")
    df = pd.read_pickle(LAKE_PKL)
    log(f"  Feature Lake: {len(df):,} rows × {len(df.columns)} columns")

    # Load Phase B rankings to select top features
    with open(PHASE_B_PKL, 'rb') as f:
        phase_b = pickle.load(f)

    # Get top features from Phase B (scale 5%, universal)
    pb_results = pd.DataFrame(phase_b['universal_results'])
    pb5 = pb_results[pb_results['scale_pct'] == 5].sort_values('composite_score', ascending=False)
    top_features = pb5.head(TOP_N_FEATURES)['feature'].tolist()
    # Keep only features that exist in df and are numeric
    top_features = [f for f in top_features if f in df.columns
                    and df[f].dtype in [np.float32, np.float64, np.int32, np.int64]]
    log(f"  Top {len(top_features)} features from Phase B selected")
    for i, f in enumerate(top_features):
        score = pb5[pb5['feature'] == f]['composite_score'].iloc[0]
        log(f"    #{i+1:2d} {f:<40s} Score={score:.3f}")

    # ── STEP 2: Classify archetypes ──
    log_section("STEP 2: Classify Archetypes")

    all_archetypes = {}
    for scale in ZZ_SCALES:
        archetypes = classify_archetypes(df, scale)
        all_archetypes[scale] = archetypes

        counts = Counter(archetypes.values())
        total = sum(counts.values())
        log(f"  Scale {scale}%: {total} classified turns")
        for arch in ['HL', 'LL', 'HH', 'LH']:
            n = counts.get(arch, 0)
            pct = n / total * 100 if total > 0 else 0
            log(f"    {arch}: {n:,} ({pct:.1f}%)")

    # ── STEP 3: Analyze each turn ──
    log_section("STEP 3: Reverse-Engineer Every Turn (Scale 5%)")

    scale = 5
    dist_col = f'dist_zz_{scale}pct'
    type_col = f'zz_{scale}pct_type'
    archetypes = all_archetypes[scale]

    all_turn_results = []
    primacy_counter = Counter()  # Which feature fires first most often
    alarm_lead_dist = defaultdict(list)  # Lead time distribution per feature
    archetype_density_curves = defaultdict(list)  # Density curves per archetype
    archetype_ramp_slopes = defaultdict(list)
    archetype_explosion = defaultdict(list)
    direction_stats = defaultdict(lambda: defaultdict(list))

    for ti, tk in enumerate(TICKERS):
        log(f"  [{ti+1}/17] {tk}...")
        mask = df['ticker'] == tk
        tk_df = df.loc[mask].reset_index(drop=True)

        # Compute z-scores for this ticker
        z_matrix = np.zeros((len(tk_df), len(top_features)), dtype=np.float32)
        for fi, feat in enumerate(top_features):
            vals = tk_df[feat].values.astype(float)
            mu = np.nanmean(vals)
            sigma = np.nanstd(vals)
            if sigma > 1e-8:
                z_matrix[:, fi] = (vals - mu) / sigma

        # Find turn points (dist=0)
        turn_mask = tk_df[dist_col] == 0
        turn_indices = np.where(turn_mask.values)[0]

        for local_idx in turn_indices:
            # Get archetype
            orig_idx = df.loc[mask].index[local_idx]
            arch = archetypes.get((tk, orig_idx), None)
            turn_type = tk_df.at[local_idx, type_col]
            direction = 'BOTTOM' if turn_type == 'MIN' else 'TOP'

            # Skip if too close to edges
            if local_idx < MAX_LOOKBACK or local_idx >= len(tk_df) - POST_HORIZON:
                continue

            # Analyze
            turn_result = analyze_turn(z_matrix, top_features, local_idx)
            turn_result['ticker'] = tk
            turn_result['archetype'] = arch or 'UNKNOWN'
            turn_result['direction'] = direction
            turn_result['scale_pct'] = scale
            turn_result['price'] = float(tk_df.at[local_idx, 'price'])

            all_turn_results.append(turn_result)

            # Aggregate statistics
            if turn_result['alarm_feature']:
                primacy_counter[turn_result['alarm_feature']] += 1
                alarm_lead_dist[turn_result['alarm_feature']].append(turn_result['alarm_lead'])

            if arch:
                archetype_density_curves[arch].append(turn_result['density_curve'])
                archetype_ramp_slopes[arch].append(turn_result['ramp_slope'])
                archetype_explosion[arch].append(turn_result['explosion_density'])
                direction_stats[direction][arch].append(turn_result)

    log(f"  Total turns analyzed: {len(all_turn_results)}")

    # ── STEP 4: Primacy Rankings ──
    log_section("STEP 4: Primacy Rankings — Which Feature Fires First?")

    total_with_alarm = sum(1 for r in all_turn_results if r['alarm_lead'] is not None)
    log(f"  Turns with alarm detected: {total_with_alarm}/{len(all_turn_results)} "
        f"({total_with_alarm/len(all_turn_results)*100:.1f}%)")

    log(f"\n  {'Feature':<40s} {'Fires':>6} {'%Primacy':>9} {'Med Lead':>9} {'Mean Lead':>10}")
    log(f"  {'─'*40} {'─'*6} {'─'*9} {'─'*9} {'─'*10}")

    for feat, count in primacy_counter.most_common(20):
        pct = count / total_with_alarm * 100
        leads = alarm_lead_dist[feat]
        med_lead = np.median(leads)
        mean_lead = np.mean(leads)
        log(f"  {feat:<40s} {count:6d} {pct:8.1f}% {med_lead:9.1f} {mean_lead:10.1f}")

    # ── STEP 5: Archetype Profiles ──
    log_section("STEP 5: Archetype Profiles")

    for arch in ['HL', 'LL', 'HH', 'LH']:
        curves = archetype_density_curves.get(arch, [])
        ramps = archetype_ramp_slopes.get(arch, [])
        explosions = archetype_explosion.get(arch, [])

        if not curves:
            log(f"\n  {arch}: No data")
            continue

        n = len(curves)
        log(f"\n  ═══ {arch} — {n} turns ═══")
        log(f"  Ramp slope:      μ={np.mean(ramps):+.3f}  med={np.median(ramps):+.3f}")
        log(f"  Explosion density: μ={np.mean(explosions):.1f}  med={np.median(explosions):.0f}  "
            f"p75={np.percentile(explosions,75):.0f}  max={np.max(explosions):.0f}")

        # Average density curve (pad shorter curves)
        max_len = max(len(c) for c in curves)
        padded = np.zeros((len(curves), max_len))
        for i, c in enumerate(curves):
            padded[i, max_len - len(c):] = c
        avg_curve = np.mean(padded, axis=0)
        med_curve = np.median(padded, axis=0)

        log(f"  Avg density curve (last {min(10, max_len)} bars before turn):")
        display_len = min(10, max_len)
        bars = [f"t-{display_len-i}" for i in range(display_len)]
        vals = [f"{avg_curve[max_len-display_len+i]:.1f}" for i in range(display_len)]
        log(f"    Bars:    {' '.join(f'{b:>5}' for b in bars)}")
        log(f"    Avg:     {' '.join(f'{v:>5}' for v in vals)}")

        # Primacy within this archetype
        arch_primacy = Counter()
        for r in all_turn_results:
            if r['archetype'] == arch and r['alarm_feature']:
                arch_primacy[r['alarm_feature']] += 1

        log(f"  Top alarm features for {arch}:")
        for feat, count in arch_primacy.most_common(5):
            pct = count / n * 100
            log(f"    {feat:<40s} {count:4d} ({pct:.1f}%)")

    # ── STEP 6: Direction comparison (BOTTOM vs TOP) ──
    log_section("STEP 6: BOTTOM vs TOP Comparison")

    for direction in ['BOTTOM', 'TOP']:
        archs = direction_stats.get(direction, {})
        total_d = sum(len(v) for v in archs.values())
        log(f"\n  ═══ {direction} — {total_d} turns ═══")

        # Aggregate alarm features for this direction
        dir_primacy = Counter()
        dir_leads = []
        dir_explosions = []
        dir_ramps = []

        for arch_name, turns in archs.items():
            for t in turns:
                if t['alarm_feature']:
                    dir_primacy[t['alarm_feature']] += 1
                    dir_leads.append(t['alarm_lead'])
                dir_explosions.append(t['explosion_density'])
                dir_ramps.append(t['ramp_slope'])

        log(f"  Alarm lead: μ={np.mean(dir_leads):.1f}  med={np.median(dir_leads):.0f}")
        log(f"  Ramp slope: μ={np.mean(dir_ramps):+.3f}  med={np.median(dir_ramps):+.3f}")
        log(f"  Explosion:  μ={np.mean(dir_explosions):.1f}  med={np.median(dir_explosions):.0f}")

        log(f"\n  Top alarm features ({direction}):")
        for feat, count in dir_primacy.most_common(10):
            pct = count / total_d * 100
            log(f"    {feat:<40s} {count:4d} ({pct:.1f}%)")

    # ── STEP 7: Feature activation heatmap by archetype ──
    log_section("STEP 7: Feature × Archetype Activation Heatmap (% active at t=0)")

    log(f"  {'Feature':<35s} {'HL':>6} {'LL':>6} {'HH':>6} {'LH':>6} {'Δ(HL-LL)':>9} {'Δ(HH-LH)':>9}")
    log(f"  {'─'*35} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*9} {'─'*9}")

    # Count how often each feature is active at t=0 per archetype
    feat_arch_active = defaultdict(lambda: defaultdict(int))
    arch_counts = Counter()

    for r in all_turn_results:
        arch = r['archetype']
        if arch == 'UNKNOWN':
            continue
        arch_counts[arch] += 1
        for af in r['active_features_at_t0']:
            feat_arch_active[af['feature']][arch] += 1

    for feat in top_features[:20]:
        vals = {}
        for arch in ['HL', 'LL', 'HH', 'LH']:
            n_arch = arch_counts.get(arch, 1)
            n_active = feat_arch_active.get(feat, {}).get(arch, 0)
            vals[arch] = n_active / n_arch * 100

        delta_bottom = vals.get('HL', 0) - vals.get('LL', 0)
        delta_top = vals.get('HH', 0) - vals.get('LH', 0)

        log(f"  {feat:<35s} {vals.get('HL',0):5.1f}% {vals.get('LL',0):5.1f}% "
            f"{vals.get('HH',0):5.1f}% {vals.get('LH',0):5.1f}% "
            f"{delta_bottom:+8.1f}% {delta_top:+8.1f}%")

    # ── STEP 8: Self-Audit ──
    log_section("STEP 8: Self-Audit")

    errors = 0

    # Check alarm lead range
    all_leads = [r['alarm_lead'] for r in all_turn_results if r['alarm_lead'] is not None]
    if all_leads:
        log(f"  Alarm lead range: [{min(all_leads)}, {max(all_leads)}] bars")
        if min(all_leads) < 1 or max(all_leads) > MAX_LOOKBACK:
            log(f"  ❌ Lead outside [1, {MAX_LOOKBACK}]!", "ERROR")
            errors += 1
        else:
            log(f"  ✅ Leads within [1, {MAX_LOOKBACK}]")

    # Check density never negative
    neg_density = sum(1 for r in all_turn_results for d in r['density_curve'] if d < 0)
    if neg_density > 0:
        log(f"  ❌ {neg_density} negative density values!", "ERROR")
        errors += 1
    else:
        log(f"  ✅ Density always ≥ 0")

    # Check archetype balance
    for arch in ['HL', 'LL', 'HH', 'LH']:
        n = arch_counts.get(arch, 0)
        log(f"  {arch}: {n} turns")

    total_classified = sum(arch_counts.values())
    total_unknown = sum(1 for r in all_turn_results if r['archetype'] == 'UNKNOWN')
    log(f"  Classified: {total_classified}  Unknown: {total_unknown}")

    if errors == 0:
        log(f"  ✅ ALL SELF-AUDITS PASSED")
    else:
        log(f"  ❌ {errors} AUDIT FAILURES", "ERROR")

    # ── STEP 9: Export ──
    log_section("STEP 9: Export")

    report = {
        'turn_results': all_turn_results,
        'primacy_rankings': dict(primacy_counter.most_common()),
        'alarm_lead_distributions': {k: v for k, v in alarm_lead_dist.items()},
        'archetype_profiles': {
            arch: {
                'n': len(archetype_density_curves.get(arch, [])),
                'ramp_slopes': archetype_ramp_slopes.get(arch, []),
                'explosion_densities': archetype_explosion.get(arch, []),
            }
            for arch in ['HL', 'LL', 'HH', 'LH']
        },
        'archetypes_by_scale': {
            scale: dict(Counter(all_archetypes[scale].values()))
            for scale in ZZ_SCALES
        },
        'top_features_used': top_features,
        'metadata': {
            'n_turns_analyzed': len(all_turn_results),
            'z_threshold': Z_THRESHOLD,
            'max_lookback': MAX_LOOKBACK,
            'n_features': len(top_features),
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
    }

    with open(REPORT_PKL, 'wb') as f:
        pickle.dump(report, f)
    pkl_size = REPORT_PKL.stat().st_size / (1024 * 1024)
    log(f"  PKL: {REPORT_PKL.name} ({pkl_size:.1f} MB)")

    # Export summary CSV
    summary_rows = []
    for r in all_turn_results:
        summary_rows.append({
            'ticker': r['ticker'],
            'archetype': r['archetype'],
            'direction': r['direction'],
            'alarm_lead': r['alarm_lead'],
            'alarm_feature': r['alarm_feature'],
            'ramp_slope': round(r['ramp_slope'], 4),
            'max_pre_density': r['max_pre_density'],
            'explosion_density': r['explosion_density'],
            'explosion_energy': round(r['explosion_energy'], 2),
            'confirmation_decay': round(r['confirmation_decay'], 4),
            'n_active_at_t0': len(r['active_features_at_t0']),
            'price': r['price'],
        })
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(REPORT_CSV, index=False)
    csv_size = REPORT_CSV.stat().st_size / (1024 * 1024)
    log(f"  CSV: {REPORT_CSV.name} ({csv_size:.1f} MB)")

    # ── Final Summary ──
    elapsed = time.time() - start_time
    log_section("SUMMARY")
    log(f"  Turns analyzed: {len(all_turn_results)}")
    log(f"  Turns with alarm: {total_with_alarm} ({total_with_alarm/len(all_turn_results)*100:.1f}%)")
    log(f"  Top alarm feature: {primacy_counter.most_common(1)[0] if primacy_counter else 'N/A'}")
    log(f"  Archetypes: HL={arch_counts.get('HL',0)} LL={arch_counts.get('LL',0)} "
        f"HH={arch_counts.get('HH',0)} LH={arch_counts.get('LH',0)}")
    log(f"  Audit: {'✅ PASSED' if errors == 0 else '❌ FAILED'}")
    log(f"  Time: {elapsed:.0f}s ({elapsed/60:.1f}min)")

    del df
    gc.collect()


if __name__ == "__main__":
    main()
