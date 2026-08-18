#!/usr/bin/env python3
"""
Train Dual Probability Tables — Walk-Forward
================================================
Generates two JSON lookup tables for the Dual P(piso)/P(techo) model.

Output:
  rc_piso_table.json  — P(near zigzag MIN | state) for 2.5%, 5%, 7.5%
  rc_techo_table.json — P(near zigzag MAX | state) for 5%, 7.5%

Walk-forward:
  Train: pre-2016
  Test: 2016+ (validation metrics only — NOT used in table)

Features (empirically validated, Fase 0):
  PISOS:  sign_family × σVc_bin × vel_σVw_ema_sign × vol_surge_bin
  TECHOS: sign_family × σc_bin × σw_bin × vel_σc_diff_sign × W_duration_bin

Architecture note: This script runs ONCE offline. The output JSON files are
loaded by rc_state_probability.py at runtime. Clean Architecture boundary:
this script is infrastructure (delivery mechanism); the JSON is consumed
by domain rules (pure functions).
"""
import json
import math
import numpy as np
import pandas as pd
import sys
import warnings
from pathlib import Path

warnings.filterwarnings('ignore')
sys.path.insert(0, "/root/botero-trade")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.quality_swing.domain.rules.rc_slope_classifier import classify_slopes

# ══════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════

TRAIN_END = pd.Timestamp('2016-01-01', tz='UTC')
OUTPUT_DIR = Path("/root/botero-trade/backend/modules/quality_swing/domain/rules")

# Sigma bins (same as existing tables)
SIGMA_BINS = [(-999, -1.0, "<<"), (-1.0, -0.3, "<"), (-0.3, 0.3, "~"),
              (0.3, 1.0, ">"), (1.0, 999, ">>")]

# N_min thresholds per level
PISO_N_MIN = {"L1": 30, "L2": 50, "L3": 100}
TECHO_N_MIN = {"L1": 20, "L2": 30, "L3": 50, "L4": 100}


def p(t):
    print(f"\n{'='*100}\n  {t}\n{'='*100}")


def wilson_lower(p_hat: float, n: int, z: float = 1.96) -> float:
    """Wilson score interval lower bound."""
    if n == 0:
        return 0.0
    denom = 1 + z**2 / n
    center = p_hat + z**2 / (2 * n)
    spread = z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2))
    return max((center - spread) / denom, 0.0)


def bin_sigma(v: float) -> str:
    for lo, hi, label in SIGMA_BINS:
        if lo <= v < hi:
            return label
    return ">>"


def sign_family(t_sign: int, c_sign: int, w_sign: int) -> str:
    """Classify T/C/W signs into 8 families."""
    if t_sign > 0 and c_sign > 0 and w_sign > 0: return 'ALL_POS'
    if t_sign < 0 and c_sign < 0 and w_sign < 0: return 'ALL_NEG'
    if t_sign > 0 and c_sign > 0 and w_sign < 0: return 'T+C+W-'
    if t_sign > 0 and c_sign < 0 and w_sign > 0: return 'T+C-W+'
    if t_sign > 0 and c_sign < 0 and w_sign < 0: return 'T+C-W-'
    if t_sign < 0 and c_sign > 0 and w_sign > 0: return 'T-C+W+'
    if t_sign < 0 and c_sign > 0 and w_sign < 0: return 'T-C+W-'
    if t_sign < 0 and c_sign < 0 and w_sign > 0: return 'T-C-W+'
    return 'OTHER'


# ══════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════

def load_data():
    """Load channel_snapshots, OHLCV bars, and zigzag points."""
    store = TimescaleDataStore()
    conn = store._conn()

    cs = pd.read_sql("""
        SELECT ticker, timestamp,
               tide_slope, current_slope, wave_slope,
               sigma_tide, sigma_current, sigma_wave,
               vwap_sigma_tide, vwap_sigma_current, vwap_sigma_wave
        FROM engine.channel_snapshots WHERE timeframe = '1d'
        ORDER BY ticker, timestamp
    """, conn)
    cs['timestamp'] = pd.to_datetime(cs['timestamp'], utc=True)

    bars = pd.read_sql("""
        SELECT ticker, time as timestamp, close, volume
        FROM market.ohlcv_bars WHERE timeframe = '1d'
        ORDER BY ticker, time
    """, conn)
    bars['timestamp'] = pd.to_datetime(bars['timestamp'], utc=True)

    zigzags = {}
    for pct in [0.025, 0.05, 0.075]:
        zz = pd.read_sql(f"""
            SELECT ticker, timestamp, tp_type
            FROM engine.zigzag_points WHERE min_swing_pct = {pct}
            ORDER BY ticker, timestamp
        """, conn)
        zz['timestamp'] = pd.to_datetime(zz['timestamp'], utc=True)
        zigzags[pct] = zz

    store._put(conn)
    store.close()
    return cs, bars, zigzags


# ══════════════════════════════════════════════════════════════
# FEATURE ENGINEERING
# ══════════════════════════════════════════════════════════════

def build_features(cs, bars, zigzags):
    """Build all features and targets."""
    df = cs.merge(bars[['ticker', 'timestamp', 'close', 'volume']],
                  on=['ticker', 'timestamp'], how='inner')
    df = df.sort_values(['ticker', 'timestamp']).reset_index(drop=True)
    print(f"  Merged bars: {len(df):,}")

    # ── Slope classification ──
    levels = []
    for _, r in df.iterrows():
        sl = classify_slopes(r['tide_slope'], r['current_slope'], r['wave_slope'])
        levels.append((sl.tide_sign, sl.current_sign, sl.wave_sign, sl.wave_level))
    df[['T_sign', 'C_sign', 'W_sign', 'W_level']] = pd.DataFrame(levels, index=df.index)

    # Sign family
    df['family'] = df.apply(lambda r: sign_family(r['T_sign'], r['C_sign'], r['W_sign']), axis=1)

    # ── Sigma features ──
    df['σVc'] = df['vwap_sigma_current']
    df['σVw'] = df['vwap_sigma_wave']
    df['σc'] = df['sigma_current']
    df['σw'] = df['sigma_wave']

    # Bins
    df['σVc_bin'] = df['σVc'].apply(bin_sigma)
    df['σc_bin'] = df['σc'].apply(bin_sigma)
    df['σw_bin'] = df['σw'].apply(bin_sigma)

    # ── Velocity features ──
    # Pisos: EMA-smoothed velocity of σVw (validated +0.0221 AUC)
    df['vel_σVw_ema'] = df.groupby('ticker')['vwap_sigma_wave'].transform(
        lambda x: x.ewm(span=5).mean().diff()
    )
    df['vel_σVw_ema_sign'] = (df['vel_σVw_ema'] > 0).map({True: '+', False: '-'})

    # Techos: Raw diff of σc (validated +0.0335 AUC)
    df['vel_σc_diff'] = df.groupby('ticker')['sigma_current'].diff()
    df['vel_σc_diff_sign'] = (df['vel_σc_diff'] > 0).map({True: '+', False: '-'})

    # ── Volume surge ──
    df['vol_sma20'] = df.groupby('ticker')['volume'].transform(lambda x: x.rolling(20).mean())
    df['vol_surge'] = df['volume'] / df['vol_sma20']

    # ── W_duration (consecutive bars at same W level) ──
    def compute_w_duration(group):
        levels = group['W_level'].values
        durations = np.ones(len(levels), dtype=int)
        for i in range(1, len(levels)):
            if levels[i] == levels[i-1]:
                durations[i] = durations[i-1] + 1
        return pd.Series(durations, index=group.index)

    df['W_duration'] = df.groupby('ticker').apply(compute_w_duration).reset_index(level=0, drop=True)

    # ── Tag zigzag targets ──
    for pct, zz in zigzags.items():
        pct_str = f"{pct:.3f}".rstrip('0')
        for tp in ['MIN', 'MAX']:
            col = f'zz{pct_str}_{tp}'
            window = 2 if tp == 'MIN' else 3  # Asymmetric windows
            df[col] = False
            for tk in df['ticker'].unique():
                pts = zz[(zz['ticker'] == tk) & (zz['tp_type'] == tp)]['timestamp'].values
                tk_idx = df[df['ticker'] == tk].index
                for pvt in pts:
                    pvt_ts = pd.Timestamp(pvt)
                    if pvt_ts.tzinfo is None:
                        pvt_ts = pvt_ts.tz_localize('UTC')
                    mask = (df.index.isin(tk_idx)) & ((df['timestamp'] - pvt_ts).dt.days.abs() <= window)
                    df.loc[mask, col] = True

    # ── Train/test split ──
    df['is_train'] = df['timestamp'] < TRAIN_END

    return df


def compute_bins_from_train(df):
    """Compute vol_surge and W_duration bin thresholds from training data only."""
    train = df[df['is_train']].copy()

    # Vol surge: terciles from training data
    vol_q33 = train['vol_surge'].quantile(0.33)
    vol_q66 = train['vol_surge'].quantile(0.66)

    def vol_bin(v):
        if v <= vol_q33: return 'low'
        if v <= vol_q66: return 'mid'
        return 'high'

    # W_duration: terciles from training data
    dur_q33 = train['W_duration'].quantile(0.33)
    dur_q66 = train['W_duration'].quantile(0.66)

    def dur_bin(v):
        if v <= dur_q33: return 'short'
        if v <= dur_q66: return 'mid'
        return 'long'

    df['vol_surge_bin'] = df['vol_surge'].apply(vol_bin)
    df['W_duration_bin'] = df['W_duration'].apply(dur_bin)

    thresholds = {
        'vol_surge': {'q33': round(float(vol_q33), 4), 'q66': round(float(vol_q66), 4)},
        'W_duration': {'q33': int(dur_q33), 'q66': int(dur_q66)},
    }
    print(f"  Vol surge bins: low ≤ {vol_q33:.2f} ≤ mid ≤ {vol_q66:.2f} ≤ high")
    print(f"  W_duration bins: short ≤ {dur_q33:.0f} ≤ mid ≤ {dur_q66:.0f} ≤ long")

    return df, thresholds


# ══════════════════════════════════════════════════════════════
# TABLE BUILDING
# ══════════════════════════════════════════════════════════════

def build_hierarchical_table(df_train, group_levels, target_col, n_min_map):
    """Build a hierarchical probability table with fallback levels.

    Args:
        df_train: Training dataframe
        group_levels: List of (level_name, [columns]) from most specific to broadest
        target_col: Target column name (boolean)
        n_min_map: Dict of level_name -> minimum N

    Returns:
        dict of key -> cell data
    """
    cells = {}
    coverage_stats = {}

    for level_name, cols in group_levels:
        n_min = n_min_map.get(level_name, 20)
        grouped = df_train.groupby(cols)

        n_cells = 0
        n_valid = 0

        for key, group in grouped:
            n = len(group)
            if n < n_min:
                continue

            n_cells += 1
            n_target = group[target_col].sum()
            p_target = n_target / n if n > 0 else 0.0
            conf = wilson_lower(p_target, n)

            # Build key string
            if isinstance(key, str):
                key_str = f"{level_name}:{key}"
            else:
                key_str = f"{level_name}:{'|'.join(str(k) for k in key)}"

            cells[key_str] = {
                "P_target": round(p_target, 4),
                "N": int(n),
                "N_target": int(n_target),
                "confidence": round(conf, 4),
                "level": level_name,
            }
            n_valid += n

        coverage = n_valid / len(df_train) * 100 if len(df_train) > 0 else 0
        coverage_stats[level_name] = {
            'n_cells': n_cells, 'coverage': coverage, 'n_valid': n_valid
        }
        print(f"    {level_name}: {n_cells} cells, coverage={coverage:.1f}%")

    return cells, coverage_stats


def build_magnitude_breakdown(df_train, group_levels, n_min_map, zigzag_pcts):
    """Build magnitude-specific probabilities for each cell.

    For each cell, compute P(target) at each zigzag magnitude.
    """
    magnitude_data = {}

    # Only use the broadest level (L2 or L3) for magnitude breakdown
    # to ensure sufficient N per cell per magnitude
    level_name, cols = group_levels[1]  # L2
    n_min = max(n_min_map.get(level_name, 20), 10)

    grouped = df_train.groupby(cols)

    for key, group in grouped:
        n = len(group)
        if n < n_min:
            continue

        if isinstance(key, str):
            key_str = f"{level_name}:{key}"
        else:
            key_str = f"{level_name}:{'|'.join(str(k) for k in key)}"

        mag_probs = {}
        for pct in zigzag_pcts:
            pct_str = f"{pct:.3f}".rstrip('0')
            col = f'zz{pct_str}_MIN' if 'MIN' in df_train.columns or True else f'zz{pct_str}_MAX'
            # Try both MIN and MAX
            for tp in ['MIN', 'MAX']:
                tc = f'zz{pct_str}_{tp}'
                if tc in group.columns:
                    n_hit = group[tc].sum()
                    p_hit = n_hit / n if n > 0 else 0.0
                    mag_probs[f"{pct_str}_{tp}"] = {
                        "P": round(p_hit, 4),
                        "N": int(n_hit),
                    }

        magnitude_data[key_str] = mag_probs

    return magnitude_data


def train_piso_table(df):
    """Build P(piso) table."""
    p("TRAINING P(PISO) TABLE")

    train = df[df['is_train']].dropna(subset=['σVc_bin', 'vel_σVw_ema_sign', 'vol_surge_bin']).copy()
    test = df[~df['is_train']].dropna(subset=['σVc_bin', 'vel_σVw_ema_sign', 'vol_surge_bin']).copy()

    # Target columns for each magnitude
    piso_targets = {
        '0.025': 'zz0.025_MIN',
        '0.05': 'zz0.05_MIN',
        '0.075': 'zz0.075_MIN',
    }

    print(f"  Train: {len(train):,} bars")
    print(f"  Test: {len(test):,} bars")
    for label, col in piso_targets.items():
        n_tr = train[col].sum()
        n_te = test[col].sum()
        base_tr = train[col].mean() * 100
        base_te = test[col].mean() * 100
        print(f"  Piso {label}: train={n_tr:,} ({base_tr:.1f}%) | test={n_te:,} ({base_te:.1f}%)")

    # Hierarchical levels for pisos
    group_levels = [
        ("L1", ['family', 'σVc_bin', 'vel_σVw_ema_sign', 'vol_surge_bin']),
        ("L2", ['family', 'σVc_bin']),
        ("L3", ['family']),
    ]

    # Build table for each magnitude
    all_cells = {}
    for mag_label, target_col in piso_targets.items():
        print(f"\n  --- Magnitude {mag_label} ---")
        cells, stats = build_hierarchical_table(train, group_levels, target_col, PISO_N_MIN)
        # Prefix magnitude to keys
        for key, cell in cells.items():
            all_cells[f"M{mag_label}|{key}"] = cell

    # Also build combined (any piso) table — most useful for production
    print(f"\n  --- Combined (any piso 7.5%) ---")
    combined_cells, combined_stats = build_hierarchical_table(
        train, group_levels, 'zz0.075_MIN', PISO_N_MIN
    )
    # Add combined cells without magnitude prefix
    for key, cell in combined_cells.items():
        all_cells[key] = cell

    # Test set evaluation
    print(f"\n  === TEST SET EVALUATION ===")
    for mag_label, target_col in piso_targets.items():
        for level_name, cols in group_levels:
            n_min = PISO_N_MIN[level_name]
            # Count how many test samples land in valid cells
            test_grouped = test.groupby(cols)
            train_grouped = train.groupby(cols)
            train_cell_sizes = train_grouped.size()
            valid_cells = train_cell_sizes[train_cell_sizes >= n_min].index

            if isinstance(valid_cells[0], str):
                test_in_valid = test[test[cols[0]].isin(valid_cells)]
            else:
                test_in_valid = test.set_index(cols)
                test_in_valid = test_in_valid[test_in_valid.index.isin(valid_cells)]

            coverage = len(test_in_valid) / len(test) * 100
            print(f"    {mag_label} {level_name}: test coverage={coverage:.1f}%")

    # Metadata
    metadata = {
        "version": "dual_piso_v1_2026-06-24",
        "type": "piso",
        "train_end": str(TRAIN_END.date()),
        "n_train": len(train),
        "n_test": len(test),
        "magnitudes": list(piso_targets.keys()),
        "features": {
            "family": "sign_family (8 categories: ALL_POS, T+C-W-, etc.)",
            "σVc_bin": "vwap_sigma_current in 5 bins (<<, <, ~, >, >>)",
            "vel_σVw_ema_sign": "sign of EMA(5) of diff(vwap_sigma_wave)",
            "vol_surge_bin": "volume/SMA20 in 3 bins (low/mid/high)",
        },
        "hierarchy": {
            "L1": "family × σVc_bin × vel_sign × vol_bin",
            "L2": "family × σVc_bin",
            "L3": "family",
        },
        "n_min": PISO_N_MIN,
        "sigma_bins": {label: [lo, hi] for lo, hi, label in SIGMA_BINS},
        "n_cells": len(all_cells),
    }

    return {"metadata": metadata, "cells": all_cells}


def train_techo_table(df):
    """Build P(techo) table."""
    p("TRAINING P(TECHO) TABLE")

    train = df[df['is_train']].dropna(
        subset=['σc_bin', 'σw_bin', 'vel_σc_diff_sign', 'W_duration_bin']
    ).copy()
    test = df[~df['is_train']].dropna(
        subset=['σc_bin', 'σw_bin', 'vel_σc_diff_sign', 'W_duration_bin']
    ).copy()

    # Target columns — only 5% and 7.5% for techos (2.5% is noise per plan)
    techo_targets = {
        '0.05': 'zz0.05_MAX',
        '0.075': 'zz0.075_MAX',
    }

    print(f"  Train: {len(train):,} bars")
    print(f"  Test: {len(test):,} bars")
    for label, col in techo_targets.items():
        n_tr = train[col].sum()
        n_te = test[col].sum()
        base_tr = train[col].mean() * 100
        base_te = test[col].mean() * 100
        print(f"  Techo {label}: train={n_tr:,} ({base_tr:.1f}%) | test={n_te:,} ({base_te:.1f}%)")

    # Hierarchical levels for techos (different features!)
    group_levels = [
        ("L1", ['family', 'σc_bin', 'vel_σc_diff_sign', 'W_duration_bin']),
        ("L2", ['family', 'σc_bin', 'σw_bin']),
        ("L3", ['family', 'σc_bin']),
        ("L4", ['family']),
    ]

    all_cells = {}
    for mag_label, target_col in techo_targets.items():
        print(f"\n  --- Magnitude {mag_label} ---")
        cells, stats = build_hierarchical_table(train, group_levels, target_col, TECHO_N_MIN)
        for key, cell in cells.items():
            all_cells[f"M{mag_label}|{key}"] = cell

    # Combined (any techo 7.5%)
    print(f"\n  --- Combined (any techo 7.5%) ---")
    combined_cells, _ = build_hierarchical_table(
        train, group_levels, 'zz0.075_MAX', TECHO_N_MIN
    )
    for key, cell in combined_cells.items():
        all_cells[key] = cell

    # Test coverage
    print(f"\n  === TEST SET EVALUATION ===")
    for mag_label, target_col in techo_targets.items():
        for level_name, cols in group_levels:
            n_min = TECHO_N_MIN[level_name]
            train_grouped = train.groupby(cols)
            train_cell_sizes = train_grouped.size()
            valid_cells = train_cell_sizes[train_cell_sizes >= n_min].index

            if isinstance(valid_cells[0], str):
                test_in_valid = test[test[cols[0]].isin(valid_cells)]
            else:
                test_in_valid = test.set_index(cols)
                test_in_valid = test_in_valid[test_in_valid.index.isin(valid_cells)]

            coverage = len(test_in_valid) / len(test) * 100
            print(f"    {mag_label} {level_name}: test coverage={coverage:.1f}%")

    metadata = {
        "version": "dual_techo_v1_2026-06-24",
        "type": "techo",
        "train_end": str(TRAIN_END.date()),
        "n_train": len(train),
        "n_test": len(test),
        "magnitudes": list(techo_targets.keys()),
        "features": {
            "family": "sign_family (8 categories)",
            "σc_bin": "sigma_current (price) in 5 bins",
            "σw_bin": "sigma_wave (price) in 5 bins",
            "vel_σc_diff_sign": "sign of raw diff(sigma_current)",
            "W_duration_bin": "W_level duration in 3 bins (short/mid/long)",
        },
        "hierarchy": {
            "L1": "family × σc_bin × vel_sign × W_duration_bin",
            "L2": "family × σc_bin × σw_bin",
            "L3": "family × σc_bin",
            "L4": "family",
        },
        "n_min": TECHO_N_MIN,
        "sigma_bins": {label: [lo, hi] for lo, hi, label in SIGMA_BINS},
        "n_cells": len(all_cells),
    }

    return {"metadata": metadata, "cells": all_cells}


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    p("DUAL PROBABILITY TABLE TRAINER — Walk-Forward")
    print(f"  Train end: {TRAIN_END.date()}")
    print(f"  Output: {OUTPUT_DIR}")

    print("\n  Loading data...")
    cs, bars, zigzags = load_data()

    print("  Building features...")
    df = build_features(cs, bars, zigzags)

    print("  Computing bin thresholds from training data...")
    df, thresholds = compute_bins_from_train(df)

    # ── Train piso table ──
    piso_table = train_piso_table(df)
    piso_table["metadata"]["bin_thresholds"] = thresholds

    piso_path = OUTPUT_DIR / "rc_piso_table.json"
    with open(piso_path, 'w') as f:
        json.dump(piso_table, f, indent=2)
    print(f"\n  ✅ Saved: {piso_path} ({len(piso_table['cells'])} cells)")

    # ── Train techo table ──
    techo_table = train_techo_table(df)
    techo_table["metadata"]["bin_thresholds"] = thresholds

    techo_path = OUTPUT_DIR / "rc_techo_table.json"
    with open(techo_path, 'w') as f:
        json.dump(techo_table, f, indent=2)
    print(f"\n  ✅ Saved: {techo_path} ({len(techo_table['cells'])} cells)")

    # ── Summary ──
    p("TRAINING COMPLETE")
    print(f"  Piso table: {len(piso_table['cells'])} cells → {piso_path.name}")
    print(f"  Techo table: {len(techo_table['cells'])} cells → {techo_path.name}")
    print(f"  Bin thresholds: {thresholds}")


if __name__ == "__main__":
    main()
