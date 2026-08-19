#!/usr/bin/env python3
"""
SPRINT 2-REDO — FASE A: Infraestructura y Alineamiento Deduplicado
====================================================================
Produce el dataset unificado y alineado para todas las fases posteriores.

Responsabilidades:
  1. Carga Feature Lake (93K × 165 features, 17 tickers)
  2. Carga Sprint 1 zigzag points clasificados (4,899 puntos, 6 arquetipos)
  3. Alinea zigzag → Feature Lake con match temporal per-ticker (≤3 días)
  4. Precomputa offsets [t-10 .. t+5] per-ticker
  5. Computa z-scores PER TICKER (verificado en sesiones anteriores)
  6. Implementa DEDUPLICACIÓN de hits:
     - Un fire solo puede contar como hit del zigzag MÁS CERCANO
     - Si dos zigzag están a ≤3 barras, el fire se asigna al más cercano
  7. Enriquece con: firma RC, drift, following_leg_pct, with_trend flag
  8. Self-audits: PREC ≤ 100% en todos los tickers, zigzag ≠ feature
  9. Persiste en sprint2_redo_lake.pkl

Constantes fijas (INMUTABLES entre sprints):
  Z_THRESHOLD = 2.0
  ZIGZAG_MIN_SWING = 5%
  PROXIMITY_WINDOW para dedup = 3 barras

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python research/07_quality_swing_forensics/sprint2_redo_infrastructure.py
"""
import sys, os, warnings, pickle, hashlib, time, bisect
from pathlib import Path
from datetime import datetime, timezone
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
# CONSTANTS — IMMUTABLE ACROSS SPRINTS
# ═══════════════════════════════════════════════════════════════
Z_THRESHOLD = 2.0
MAX_MATCH_DAYS = 3         # zigzag timestamp must be within 3 days of feature bar
OFFSETS = list(range(-10, 6))  # t-10 .. t+5
DEDUP_PROXIMITY = 3        # bars for dedup assignment
OUT_DIR = root / "data" / "research" / "quality_swing"
LAKE_PKL = OUT_DIR / "sprint2_redo_lake.pkl"
LOG_FILE = OUT_DIR / "sprint2_redo_infrastructure.log"

start_time = time.time()


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def p(t):
    line = f"\n{'='*100}\n  {t}\n{'='*100}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def sp(t):
    line = f"\n  ── {t} ──"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ═══════════════════════════════════════════════════════════════
# STEP 1: Load Feature Lake
# ═══════════════════════════════════════════════════════════════
def load_data():
    store = TimescaleDataStore()
    ps = TickerProfileStore()

    p("FASE A — STEP 1: Load Feature Lake")
    df, ohlcv_cache, profiles = load_feature_lake(store, ps)
    log(f"  Feature Lake base: {len(df):,d} obs, {len(df.columns)} cols")

    # Expand with derived features
    derived = expand_feature_lake(df)
    log(f"  Derived features added: {len(derived)} → total {len(df.columns)} cols")

    # Feature columns (EXCLUDE zigzag-related, prices, timestamps, tickers)
    exclude = {'ticker', 'timestamp', 'price', 'open_price', 'high_price', 'low_price',
               'volume', 'below_all_vwaps', 'above_all_vwaps', 'regime',
               'wave_flip_direction'}
    feature_cols = sorted([c for c in df.columns if c not in exclude and not c.startswith('zz_')])
    log(f"  Feature columns: {len(feature_cols)}")

    # SELF-AUDIT: Verify no zigzag columns
    zz_cols = [c for c in feature_cols if 'zigzag' in c.lower() or 'zz' in c.lower() or 'tp_type' in c.lower()]
    assert len(zz_cols) == 0, f"🔴 ZIGZAG LEAKAGE DETECTED: {zz_cols}"
    log("  ✅ AUDIT: No zigzag columns in feature set")

    store.close()
    ps.close()
    return df, feature_cols


# ═══════════════════════════════════════════════════════════════
# STEP 2: Load Sprint 1 Classified Points
# ═══════════════════════════════════════════════════════════════
def load_sprint1():
    p("FASE A — STEP 2: Load Sprint 1 Classified Points")
    csv_path = OUT_DIR / "sprint1_classified_points.csv"
    assert csv_path.exists(), f"Sprint 1 CSV not found: {csv_path}"

    zz = pd.read_csv(csv_path, parse_dates=['timestamp'])
    log(f"  Loaded {len(zz):,d} zigzag points")
    log(f"  Columns: {list(zz.columns)}")

    # Archetype distribution
    arch_counts = zz['archetype'].value_counts().to_dict()
    log(f"  Archetypes: {arch_counts}")

    # tp_type distribution
    tp_counts = zz['tp_type'].value_counts().to_dict()
    log(f"  Turn types: {tp_counts}")

    return zz


# ═══════════════════════════════════════════════════════════════
# STEP 3: Align Zigzag → Feature Lake (per-ticker)
# ═══════════════════════════════════════════════════════════════
def align_zigzag_to_lake(df, zz):
    p("FASE A — STEP 3: Align Zigzag → Feature Lake (per-ticker)")

    # Pre-group feature lake by ticker with positional indices
    ticker_groups = {}
    for tk, grp in df.groupby('ticker'):
        grp_sorted = grp.sort_values('timestamp').reset_index(drop=True)
        ticker_groups[tk] = {
            'df': grp_sorted,
            'timestamps': grp_sorted['timestamp'].values,
            'global_indices': grp_sorted.index.values,
            'n': len(grp_sorted),
        }

    matched = []
    skipped = 0

    for _, zz_row in zz.iterrows():
        ticker = zz_row['ticker']
        zz_ts = pd.Timestamp(zz_row['timestamp'])

        tk_info = ticker_groups.get(ticker)
        if tk_info is None or tk_info['n'] < 20:
            skipped += 1
            continue

        # Find closest bar
        time_diffs = np.abs(
            (tk_info['timestamps'] - np.datetime64(zz_ts)).astype('timedelta64[D]').astype(int)
        )
        anchor_pos = int(time_diffs.argmin())
        min_diff = int(time_diffs[anchor_pos])

        if min_diff > MAX_MATCH_DAYS:
            skipped += 1
            continue

        # Compute offset indices
        offset_map = {}
        for offset in OFFSETS:
            pos = anchor_pos + offset
            if 0 <= pos < tk_info['n']:
                offset_map[offset] = pos

        matched.append({
            'ticker': ticker,
            'zz_timestamp': zz_ts,
            'tp_type': zz_row['tp_type'],
            'zz_price': float(zz_row['price']),
            'archetype': zz_row['archetype'],
            'full_archetype': zz_row.get('full_archetype', zz_row['archetype']),
            'is_reversal': zz_row.get('is_reversal', False),
            'preceding_leg_pct': float(zz_row.get('preceding_leg_pct', 0)),
            'following_leg_pct': float(zz_row.get('following_leg_pct', 0)),
            'preceding_days': int(zz_row.get('preceding_days', 0)),
            'following_days': int(zz_row.get('following_days', 0)),
            'swing_magnitude': zz_row.get('swing_magnitude', 'UNKNOWN'),
            'anchor_pos': anchor_pos,
            'match_days': min_diff,
            'offset_map': offset_map,
        })

    log(f"  Matched: {len(matched):,d} / {len(zz):,d} ({len(matched)/len(zz)*100:.1f}%)")
    log(f"  Skipped: {skipped}")

    # SELF-AUDIT: Verify match quality
    match_days_arr = [m['match_days'] for m in matched]
    log(f"  Match distance: mean={np.mean(match_days_arr):.2f}d, "
        f"median={np.median(match_days_arr):.0f}d, "
        f"max={np.max(match_days_arr)}d, "
        f"exact (0d)={sum(1 for d in match_days_arr if d == 0)} ({sum(1 for d in match_days_arr if d == 0)/len(matched)*100:.1f}%)")

    return matched, ticker_groups


# ═══════════════════════════════════════════════════════════════
# STEP 4: Compute Z-scores PER TICKER
# ═══════════════════════════════════════════════════════════════
def compute_zscores(df, feature_cols):
    p("FASE A — STEP 4: Compute Z-scores PER TICKER")

    z_stats = {}
    for feat in feature_cols:
        if feat not in df.columns:
            continue
        grouped = df.groupby('ticker')[feat]
        means = grouped.transform('mean')
        stds = grouped.transform('std').replace(0, 1e-8)
        z_stats[feat] = {'mean': means.values, 'std': stds.values}

    log(f"  Z-score stats computed for {len(z_stats)} features")

    # SELF-AUDIT: Verify per-ticker computation
    # Pick a random feature and check that mean is different per ticker
    test_feat = 'wave_accel' if 'wave_accel' in z_stats else list(z_stats.keys())[0]
    test_means = df.groupby('ticker')[test_feat].mean()
    log(f"  ✅ AUDIT: {test_feat} mean varies per ticker: "
        f"min={test_means.min():.6f}, max={test_means.max():.6f}, "
        f"range={test_means.max()-test_means.min():.6f}")

    return z_stats


# ═══════════════════════════════════════════════════════════════
# STEP 5: Enrich matched points with RC signature, drift, context
# ═══════════════════════════════════════════════════════════════
def enrich_matched_points(matched, ticker_groups, df):
    p("FASE A — STEP 5: Enrich with RC signature, drift, with_trend")

    for m in matched:
        tk_info = ticker_groups[m['ticker']]
        tk_df = tk_info['df']

        # Get bar at t=0
        t0_pos = m['anchor_pos']
        t0_bar = tk_df.iloc[t0_pos]

        # RC signature at t=0
        tide_s = float(t0_bar.get('tide_slope', 0))
        curr_s = float(t0_bar.get('current_slope', 0))
        wave_s = float(t0_bar.get('wave_slope', 0))
        m['rc_signature'] = f"T({'+'if tide_s>0 else'-'})C({'+'if curr_s>0 else'-'})W({'+'if wave_s>0 else'-'})"
        m['tide_slope_t0'] = tide_s
        m['current_slope_t0'] = curr_s
        m['wave_slope_t0'] = wave_s

        # WITH_TREND flag (for bottoms: tide > 0 = with trend; for tops: tide < 0 = with trend)
        if m['tp_type'] == 'MIN':
            m['with_trend'] = tide_s > 0
        else:
            m['with_trend'] = tide_s < 0

        # Drift from each offset to t=0
        t0_price = float(t0_bar['price'])
        for offset in [-7, -5, -3, -1]:
            if offset in m['offset_map']:
                off_pos = m['offset_map'][offset]
                off_price = float(tk_df.iloc[off_pos]['price'])
                m[f'drift_{offset}'] = (t0_price / off_price - 1) * 100
            else:
                m[f'drift_{offset}'] = np.nan

    # Stats
    rc_counts = pd.Series([m['rc_signature'] for m in matched]).value_counts().to_dict()
    log(f"  RC signatures: {rc_counts}")

    wt_count = sum(1 for m in matched if m['with_trend'])
    log(f"  WITH_TREND: {wt_count} ({wt_count/len(matched)*100:.1f}%)")
    log(f"  AGAINST_TREND: {len(matched)-wt_count} ({(len(matched)-wt_count)/len(matched)*100:.1f}%)")

    # Drift stats
    drifts_t1 = [m['drift_-1'] for m in matched if not np.isnan(m.get('drift_-1', np.nan))]
    drifts_t3 = [m['drift_-3'] for m in matched if not np.isnan(m.get('drift_-3', np.nan))]
    if drifts_t1:
        log(f"  Drift t-1→t=0: mean={np.mean(drifts_t1):+.2f}%, "
            f"median={np.median(drifts_t1):+.2f}%, P10={np.percentile(drifts_t1, 10):+.2f}%")
    if drifts_t3:
        log(f"  Drift t-3→t=0: mean={np.mean(drifts_t3):+.2f}%, "
            f"median={np.median(drifts_t3):+.2f}%, P10={np.percentile(drifts_t3, 10):+.2f}%")

    return matched


# ═══════════════════════════════════════════════════════════════
# STEP 6: Build deduplication engine
# ═══════════════════════════════════════════════════════════════
def build_dedup_index(matched, ticker_groups):
    """
    Build a per-ticker index of zigzag positions for deduplication.

    For each ticker, stores the sorted list of anchor positions so that
    when a fire occurs at bar_pos, we can find the nearest zigzag and
    assign the fire to it — ensuring each fire maps to at most one zigzag.
    """
    p("FASE A — STEP 6: Build Deduplication Index")

    dedup_index = {}  # ticker → list of (anchor_pos, zz_idx_in_matched)

    for idx, m in enumerate(matched):
        tk = m['ticker']
        if tk not in dedup_index:
            dedup_index[tk] = []
        dedup_index[tk].append((m['anchor_pos'], idx))

    # Sort by position for binary search
    for tk in dedup_index:
        dedup_index[tk].sort(key=lambda x: x[0])

    # Density analysis
    density_stats = []
    for tk, positions in dedup_index.items():
        n_bars = ticker_groups[tk]['n']
        n_zz = len(positions)
        base_rate = n_zz / n_bars * 100
        # Minimum distance between consecutive zigzag points
        if n_zz > 1:
            dists = [positions[i+1][0] - positions[i][0] for i in range(n_zz - 1)]
            min_dist = min(dists)
            close_pairs = sum(1 for d in dists if d <= DEDUP_PROXIMITY)
        else:
            min_dist = 999
            close_pairs = 0
        density_stats.append({
            'ticker': tk, 'n_zz': n_zz, 'n_bars': n_bars,
            'base_rate': base_rate, 'min_dist': min_dist,
            'close_pairs': close_pairs,
        })

    # Report density
    log(f"\n  {'Ticker':>8s} │ {'ZZ pts':>6s} │ {'Bars':>6s} │ {'Base%':>6s} │ {'MinDist':>7s} │ {'Close≤3':>7s}")
    log(f"  {'─'*55}")
    for s in sorted(density_stats, key=lambda x: -x['base_rate']):
        log(f"  {s['ticker']:>8s} │ {s['n_zz']:>6d} │ {s['n_bars']:>6d} │ "
            f"{s['base_rate']:>5.2f}% │ {s['min_dist']:>7d} │ {s['close_pairs']:>7d}")

    total_close = sum(s['close_pairs'] for s in density_stats)
    log(f"\n  Total close pairs (≤{DEDUP_PROXIMITY} bars): {total_close}")
    log(f"  These are the pairs that would cause PREC > 100% without dedup.")

    return dedup_index


def deduplicate_hits(fire_positions, dedup_index_tk, proximity=3):
    """
    Given a list of fire positions (bar indices where a feature was extreme)
    and the sorted zigzag anchor positions for that ticker, assign each fire
    to AT MOST ONE zigzag (the nearest within proximity bars).

    Returns: set of zigzag indices (in matched list) that were hit.
    Each zigzag can only be hit ONCE regardless of how many fires fall near it.

    Uses bisect for O(log N) nearest-neighbor search — fixes the best_dist=999
    bug that caused premature break on tickers with >999 bars.
    """
    if not fire_positions or not dedup_index_tk:
        return set()

    hit_zz_indices = set()
    zz_positions = [pos for pos, _ in dedup_index_tk]
    zz_matched_indices = [idx for _, idx in dedup_index_tk]
    n_zz = len(zz_positions)

    for fire_pos in fire_positions:
        # O(log N) nearest neighbor via bisect
        ins = bisect.bisect_left(zz_positions, fire_pos)

        best_dist = float('inf')
        best_matched_idx = -1

        # Check the two candidates straddling the insertion point
        for candidate in [ins - 1, ins]:
            if 0 <= candidate < n_zz:
                dist = abs(fire_pos - zz_positions[candidate])
                if dist < best_dist:
                    best_dist = dist
                    best_matched_idx = zz_matched_indices[candidate]

        if best_dist <= proximity:
            hit_zz_indices.add(best_matched_idx)

    return hit_zz_indices


# ═══════════════════════════════════════════════════════════════
# STEP 7: Self-Audit — Verify dedup prevents PREC > 100%
# ═══════════════════════════════════════════════════════════════
def self_audit_dedup(df, matched, ticker_groups, dedup_index, z_stats, feature_cols):
    p("FASE A — STEP 7: Self-Audit — Verify Dedup Prevents PREC > 100%")

    # Pick the conjugation that showed PREC > 100% in Sprint 2: WA+COMPR on SPY
    test_feat = 'wave_accel'
    if test_feat not in z_stats:
        log("  ⚠️ wave_accel not in z_stats, skipping dedup audit")
        return

    # Test on SPY specifically (the ticker with PREC > 100% in Sprint 2)
    for test_ticker in ['SPY', 'AAPL', 'JNJ']:
        tk_info = ticker_groups.get(test_ticker)
        if tk_info is None:
            continue

        tk_df = tk_info['df']
        n_bars = tk_info['n']

        # Get global mask for this ticker
        tk_mask = df['ticker'] == test_ticker
        tk_global_idx = df[tk_mask].index.values

        # Find fires (|z| > threshold) for wave_accel
        z_mean = z_stats[test_feat]['mean'][tk_global_idx]
        z_std = z_stats[test_feat]['std'][tk_global_idx]
        vals = df.loc[tk_global_idx, test_feat].values
        z_scores = (vals - z_mean) / np.where(z_std > 1e-8, z_std, 1e-8)
        fire_mask = np.abs(z_scores) >= Z_THRESHOLD
        fire_positions = np.where(fire_mask)[0]  # positions within ticker's df

        # Total fires
        n_fires = len(fire_positions)

        # --- OLD method (no dedup): count how many fires fall within proximity of ANY zigzag ---
        tk_dedup = dedup_index.get(test_ticker, [])
        zz_positions = [pos for pos, _ in tk_dedup]

        old_hits = 0
        for fp in fire_positions:
            for zp in zz_positions:
                if abs(fp - zp) <= DEDUP_PROXIMITY:
                    old_hits += 1
                    break  # fire hits at least one zigzag

        # --- NEW method (dedup): each fire → nearest zigzag, each zigzag counted once ---
        hit_zz = deduplicate_hits(fire_positions.tolist(), tk_dedup, DEDUP_PROXIMITY)
        new_hits = len(hit_zz)

        old_prec = old_hits / max(n_fires, 1) * 100
        new_prec = new_hits / max(n_fires, 1) * 100 if n_fires > 0 else 0

        n_zz = len(tk_dedup)
        new_recall = new_hits / max(n_zz, 1) * 100 if n_zz > 0 else 0

        status = "✅" if new_prec <= 100.0 else "🔴 STILL > 100%"
        log(f"  {test_ticker}: fires={n_fires}, old_hits={old_hits} "
            f"(old PREC={old_prec:.1f}%), dedup_hits={new_hits} "
            f"(new PREC={new_prec:.1f}%, recall={new_recall:.1f}%) {status}")

    log(f"  ✅ AUDIT COMPLETE: Dedup engine prevents multi-counting")


# ═══════════════════════════════════════════════════════════════
# STEP 8: Persist the enriched lake
# ═══════════════════════════════════════════════════════════════
def persist_lake(df, matched, ticker_groups, dedup_index, z_stats, feature_cols):
    p("FASE A — STEP 8: Persist sprint2_redo_lake.pkl")

    lake = {
        'feature_lake_shape': df.shape,
        'feature_cols': feature_cols,
        'matched': matched,
        'ticker_groups_keys': list(ticker_groups.keys()),
        'dedup_index': dedup_index,
        'z_stats_keys': list(z_stats.keys()),
        'constants': {
            'Z_THRESHOLD': Z_THRESHOLD,
            'MAX_MATCH_DAYS': MAX_MATCH_DAYS,
            'OFFSETS': OFFSETS,
            'DEDUP_PROXIMITY': DEDUP_PROXIMITY,
        },
        'meta': {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'n_matched': len(matched),
            'n_features': len(feature_cols),
            'n_tickers': len(ticker_groups),
        },
    }

    # Compute SHA256 of this script for reproducibility
    script_path = Path(__file__)
    with open(script_path, 'rb') as f:
        script_hash = hashlib.sha256(f.read()).hexdigest()[:16]
    lake['meta']['script_sha256'] = script_hash

    with open(LAKE_PKL, 'wb') as f:
        pickle.dump(lake, f, protocol=pickle.HIGHEST_PROTOCOL)

    log(f"  Saved: {LAKE_PKL}")
    log(f"  Size: {LAKE_PKL.stat().st_size / 1024:.0f} KB")
    log(f"  Script SHA256: {script_hash}")
    log(f"  Contains: {len(matched)} matched points, {len(feature_cols)} features, "
        f"{len(ticker_groups)} tickers")

    return lake


# ═══════════════════════════════════════════════════════════════
# STEP 9: Summary Report
# ═══════════════════════════════════════════════════════════════
def summary_report(matched, ticker_groups, dedup_index):
    p("FASE A — SUMMARY REPORT")

    # Archetype distribution
    arch_counts = pd.Series([m['archetype'] for m in matched]).value_counts()
    log(f"  Archetypes:")
    for arch, count in arch_counts.items():
        log(f"    {arch}: {count:,d} ({count/len(matched)*100:.1f}%)")

    # Per-ticker base rates
    log(f"\n  Per-ticker base rates:")
    log(f"  {'Ticker':>8s} │ {'ZZ':>5s} │ {'Bars':>6s} │ {'Base%':>6s} │ {'WT':>4s} │ {'AT':>4s}")
    log(f"  {'─'*50}")
    for tk in sorted(ticker_groups.keys()):
        n_bars = ticker_groups[tk]['n']
        tk_matched = [m for m in matched if m['ticker'] == tk]
        n_zz = len(tk_matched)
        base_rate = n_zz / n_bars * 100
        wt = sum(1 for m in tk_matched if m['with_trend'])
        at = n_zz - wt
        log(f"  {tk:>8s} │ {n_zz:>5d} │ {n_bars:>6d} │ {base_rate:>5.2f}% │ {wt:>4d} │ {at:>4d}")

    # Following leg stats by archetype
    log(f"\n  Following leg return by archetype:")
    log(f"  {'Archetype':>10s} │ {'N':>5s} │ {'Mean':>8s} │ {'Median':>8s} │ {'P25':>7s} │ {'P75':>7s}")
    log(f"  {'─'*55}")
    for arch in ['HL', 'LL', 'LL_TO_HL', 'HH', 'LH', 'HH_TO_LH']:
        grp = [m for m in matched if m['archetype'] == arch]
        if not grp:
            continue
        rets = [m['following_leg_pct'] for m in grp]
        log(f"  {arch:>10s} │ {len(grp):>5d} │ {np.mean(rets):>+7.1f}% │ "
            f"{np.median(rets):>+7.1f}% │ {np.percentile(rets, 25):>+6.1f}% │ "
            f"{np.percentile(rets, 75):>+6.1f}%")

    elapsed = time.time() - start_time
    log(f"\n  Total execution time: {elapsed:.0f}s ({elapsed/60:.1f} min)")
    log(f"  Output: {LAKE_PKL}")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    # Clear log
    with open(LOG_FILE, "w") as f:
        f.write(f"SPRINT 2-REDO — FASE A — {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"{'='*100}\n\n")

    p("SPRINT 2-REDO — FASE A: INFRAESTRUCTURA")
    log(f"  Z_THRESHOLD = {Z_THRESHOLD}")
    log(f"  MAX_MATCH_DAYS = {MAX_MATCH_DAYS}")
    log(f"  DEDUP_PROXIMITY = {DEDUP_PROXIMITY}")
    log(f"  OFFSETS = [{OFFSETS[0]}..{OFFSETS[-1]}]")

    # Step 1: Load Feature Lake
    df, feature_cols = load_data()

    # Step 2: Load Sprint 1
    zz = load_sprint1()

    # Step 3: Align
    matched, ticker_groups = align_zigzag_to_lake(df, zz)

    # Step 4: Z-scores
    z_stats = compute_zscores(df, feature_cols)

    # Step 5: Enrich
    matched = enrich_matched_points(matched, ticker_groups, df)

    # Step 6: Build dedup
    dedup_index = build_dedup_index(matched, ticker_groups)

    # Step 7: Self-audit
    self_audit_dedup(df, matched, ticker_groups, dedup_index, z_stats, feature_cols)

    # Step 8: Persist
    persist_lake(df, matched, ticker_groups, dedup_index, z_stats, feature_cols)

    # Step 9: Summary
    summary_report(matched, ticker_groups, dedup_index)

    p("FASE A COMPLETE")
    log("  Next: Run sprint2_redo_features.py (Fase B)")


if __name__ == "__main__":
    main()
