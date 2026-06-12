#!/usr/bin/env python3
"""
RC Probability Table — Sigma-Based Training Script
=====================================================
Generates P(bull|sigma_state) lookup table from:
  - engine.channel_snapshots (91K+ bars, 17 tickers)
  - engine.zigzag_points (5% swing level)

State dimensions (from audit §22 ranking):
  1. σVWAP_wave  (IG=0.3942, TOP predictor)
  2. σ_current   (IG=0.2986, #2)
  3. σ_wave      (IG=0.2894, #3)
  4. tide_slope  (context macro, ±28pp modifier)

Hierarchical lookup:
  L1: Full 4D (Tide × σ_c × σ_w × σVw) — max precision
  L2: 3D (σ_c × σ_w × σVw) — no Tide, robust
  L3: 2D (σ_c × σVw) — core pair
  L4: 1D (σVw) — ultimate fallback

Output: rc_probability_table.json

Clean Architecture: This is a training SCRIPT (delivery mechanism),
not a domain rule. It writes to the filesystem.
"""
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
import numpy as np
import json
import sys
from pathlib import Path
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore


# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

ZIGZAG_LEVEL = 0.05          # 5% swing
TRAIN_CUTOFF = "2020-01-01"  # Train: 2006-2019, Test: 2020-2026
EMBARGO_DAYS = 30            # Gap between train and test
N_MIN_L1 = 15               # Minimum samples for L1 (4D)
N_MIN_L2 = 20               # Minimum samples for L2 (3D)
N_MIN_L3 = 30               # Minimum samples for L3 (2D)
N_MIN_L4 = 50               # Minimum samples for L4 (1D)

# Sigma bins (5 bins, aligned with audit §19-21)
SIGMA_BINS = [
    (-999, -1.0, "<<"),
    (-1.0, -0.3, "<"),
    (-0.3,  0.3, "~"),
    ( 0.3,  1.0, ">"),
    ( 1.0,  999, ">>"),
]

# Tide slope bins (6 bins, aligned with audit)
TIDE_BINS = [
    (-999,  -0.03, "T---"),
    (-0.03, -0.01, "T--"),
    (-0.01,  0.0,  "T-"),
    ( 0.0,   0.01, "T+"),
    ( 0.01,  0.03, "T++"),
    ( 0.03,  999,  "T+++"),
]

OUTPUT_PATH = Path(__file__).parent.parent / "modules" / "quality_swing" / "domain" / "rules" / "rc_probability_table.json"


# ═══════════════════════════════════════════════════════════════
# BIN CLASSIFIERS
# ═══════════════════════════════════════════════════════════════

def _classify(value, bins: list) -> str:
    """Classify a continuous value into a discrete bin label."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return bins[len(bins) // 2][2]  # Default to middle bin
    value = float(value)
    for lo, hi, label in bins:
        if lo <= value < hi:
            return label
    return bins[-1][2]  # Fallback to last bin


def classify_sigma(val) -> str:
    return _classify(val, SIGMA_BINS)


def classify_tide(val: float) -> str:
    return _classify(val, TIDE_BINS)


# ═══════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════

def load_data():
    """Load channel snapshots and zigzag points from Vault."""
    store = TimescaleDataStore()
    conn = store._conn()

    print("Loading channel_snapshots...")
    cs = pd.read_sql(f"""
        SELECT ticker, timestamp::date as date,
               sigma_current, sigma_wave, sigma_tide,
               vwap_sigma_current, vwap_sigma_wave, vwap_sigma_tide,
               tide_slope, current_slope, wave_slope
        FROM engine.channel_snapshots
        WHERE timeframe = '1d'
        ORDER BY ticker, timestamp
    """, conn)

    print("Loading zigzag_points...")
    zz = pd.read_sql(f"""
        SELECT ticker, timestamp::date as date, tp_type, price
        FROM engine.zigzag_points
        WHERE min_swing_pct = {ZIGZAG_LEVEL}
        ORDER BY ticker, timestamp
    """, conn)

    print("Loading OHLCV close prices...")
    bars = pd.read_sql("""
        SELECT ticker, time::date as date, close
        FROM market.ohlcv_bars
        WHERE timeframe = '1d'
        ORDER BY ticker, time
    """, conn)

    store._put(conn)
    store.close()

    print(f"  Snapshots: {len(cs):,} rows, {cs['ticker'].nunique()} tickers")
    print(f"  Zigzag:    {len(zz):,} points (swing={ZIGZAG_LEVEL})")
    print(f"  OHLCV:     {len(bars):,} bars")
    return cs, zz, bars


# ═══════════════════════════════════════════════════════════════
# LABEL COMPUTATION: What happens NEXT (zigzag-based)
# ═══════════════════════════════════════════════════════════════

def compute_labels(cs: pd.DataFrame, zz: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """For each snapshot bar, determine the next zigzag stereotype (HH/HL/LH/LL).

    A bar is "bull" if the next significant zigzag move produces:
      - HH (Higher High): next peak > prev peak AND next trough > prev trough
      - HL (Higher Low): next peak <= prev peak BUT next trough > prev trough

    And "bear" if:
      - LH (Lower High): next peak > prev peak BUT next trough <= prev trough
      - LL (Lower Low): next peak <= prev peak AND next trough <= prev trough
    """
    # Ensure date columns are consistent types
    cs = cs.copy()
    cs['date'] = pd.to_datetime(cs['date'])
    bars = bars.copy()
    bars['date'] = pd.to_datetime(bars['date'])
    zz = zz.copy()
    zz['date'] = pd.to_datetime(zz['date'])

    # Merge close prices into snapshots
    df = cs.merge(bars[['ticker', 'date', 'close']], on=['ticker', 'date'], how='inner')
    df = df.sort_values(['ticker', 'date']).reset_index(drop=True)

    # Process per ticker
    all_stereotypes = pd.Series([None] * len(df), index=df.index)
    n_labeled_total = 0

    for ticker in df['ticker'].unique():
        mask = df['ticker'] == ticker
        tk_dates = df.loc[mask, 'date'].values  # numpy datetime64

        tk_zz = zz[zz['ticker'] == ticker].sort_values('date')
        # tp_type is MIN (trough) or MAX (peak)
        peaks = tk_zz[tk_zz['tp_type'] == 'MAX']
        troughs = tk_zz[tk_zz['tp_type'] == 'MIN']

        if len(peaks) < 2 or len(troughs) < 2:
            print(f"    {ticker}: skipped (peaks={len(peaks)}, troughs={len(troughs)})")
            continue

        peak_dates_np = peaks['date'].values    # numpy datetime64
        peak_prices_np = peaks['price'].values.astype(float)
        trough_dates_np = troughs['date'].values
        trough_prices_np = troughs['price'].values.astype(float)

        stereotypes = []
        n_labeled = 0
        for d in tk_dates:
            # Find next and previous peaks/troughs
            p_next = np.searchsorted(peak_dates_np, d, side='right')
            t_next = np.searchsorted(trough_dates_np, d, side='right')

            if p_next >= len(peak_prices_np) or t_next >= len(trough_prices_np):
                stereotypes.append(None)
                continue
            if p_next < 1 or t_next < 1:
                stereotypes.append(None)
                continue

            hh = peak_prices_np[p_next] > peak_prices_np[p_next - 1]
            hl = trough_prices_np[t_next] > trough_prices_np[t_next - 1]

            if hh and hl:
                stereotypes.append("HH")
            elif not hh and hl:
                stereotypes.append("HL")
            elif hh and not hl:
                stereotypes.append("LH")
            else:
                stereotypes.append("LL")
            n_labeled += 1

        all_stereotypes.loc[mask] = stereotypes
        n_labeled_total += n_labeled
        print(f"    {ticker}: {n_labeled:,} labeled / {mask.sum():,} bars")

    df['stereotype'] = all_stereotypes
    df['is_bull'] = df['stereotype'].isin(['HH', 'HL'])

    n_labeled = df['stereotype'].notna().sum()
    print(f"  TOTAL Labeled: {n_labeled:,} / {len(df):,} bars ({n_labeled/len(df):.1%})")
    return df.dropna(subset=['stereotype']).reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════
# STATE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

def classify_states(df: pd.DataFrame) -> pd.DataFrame:
    """Add state bin columns to the dataframe."""
    df = df.copy()
    df['sc_bin'] = df['sigma_current'].apply(classify_sigma)
    df['sw_bin'] = df['sigma_wave'].apply(classify_sigma)
    df['svw_bin'] = df['vwap_sigma_wave'].apply(classify_sigma)
    df['tide_bin'] = df['tide_slope'].apply(classify_tide)

    # State keys for each level
    df['L1_key'] = df['tide_bin'] + '|' + df['sc_bin'] + '|' + df['sw_bin'] + '|' + df['svw_bin']
    df['L2_key'] = df['sc_bin'] + '|' + df['sw_bin'] + '|' + df['svw_bin']
    df['L3_key'] = df['sc_bin'] + '|' + df['svw_bin']
    df['L4_key'] = df['svw_bin']

    return df


# ═══════════════════════════════════════════════════════════════
# PROBABILITY COMPUTATION
# ═══════════════════════════════════════════════════════════════

def compute_probabilities(df: pd.DataFrame, key_col: str, level: str,
                          n_min: int) -> dict:
    """Compute P(bull), P(HH/HL/LH/LL) for each state cell."""
    cells = {}
    grouped = df.groupby(key_col)

    for key, group in grouped:
        n = len(group)
        if n < n_min:
            continue

        p_hh = (group['stereotype'] == 'HH').mean()
        p_hl = (group['stereotype'] == 'HL').mean()
        p_lh = (group['stereotype'] == 'LH').mean()
        p_ll = (group['stereotype'] == 'LL').mean()
        p_bull = float(group['is_bull'].mean())

        # Confidence based on sample size (Wilson interval approximation)
        confidence = round(1.0 - 1.96 * np.sqrt(p_bull * (1 - p_bull) / n), 3)
        confidence = max(0.0, confidence)

        cells[key] = {
            "P_bull": round(p_bull, 4),
            "P_HH": round(float(p_hh), 4),
            "P_HL": round(float(p_hl), 4),
            "P_LH": round(float(p_lh), 4),
            "P_LL": round(float(p_ll), 4),
            "N": n,
            "confidence": confidence,
            "level": level,
        }

    return cells


# ═══════════════════════════════════════════════════════════════
# VALIDATION: TRAIN vs TEST
# ═══════════════════════════════════════════════════════════════

def validate_train_test(train_cells: dict, test_cells: dict, level: str):
    """Compare P(bull) between train and test for matching cells."""
    common_keys = set(train_cells.keys()) & set(test_cells.keys())
    if len(common_keys) < 5:
        print(f"  {level}: Only {len(common_keys)} common cells — insufficient for validation")
        return 0.0

    train_vals = [train_cells[k]['P_bull'] for k in common_keys]
    test_vals = [test_cells[k]['P_bull'] for k in common_keys]

    corr = np.corrcoef(train_vals, test_vals)[0, 1]
    mae = np.mean(np.abs(np.array(train_vals) - np.array(test_vals)))
    rmse = np.sqrt(np.mean((np.array(train_vals) - np.array(test_vals))**2))

    # Spread comparison
    train_spread = max(train_vals) - min(train_vals)
    test_spread = max(test_vals) - min(test_vals)

    print(f"  {level}: {len(common_keys)} common cells | "
          f"r={corr:.3f} | MAE={mae:.3f} | RMSE={rmse:.3f} | "
          f"spread train={train_spread:.2f} test={test_spread:.2f}")

    return corr


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    cs, zz, bars = load_data()

    # Label each bar with zigzag stereotype
    df = compute_labels(cs, zz, bars)

    # Classify into state bins
    df = classify_states(df)

    # Train/test split
    cutoff = pd.Timestamp(TRAIN_CUTOFF)
    embargo = pd.Timedelta(days=EMBARGO_DAYS)
    train = df[df['date'] < cutoff]
    test = df[df['date'] >= cutoff + embargo]

    print(f"\n{'='*100}")
    print(f"  TRAIN: {len(train):,} bars ({train['date'].min()} → {train['date'].max()})")
    print(f"  TEST:  {len(test):,} bars ({test['date'].min()} → {test['date'].max()})")
    print(f"  Base P(bull) train: {train['is_bull'].mean():.3f}")
    print(f"  Base P(bull) test:  {test['is_bull'].mean():.3f}")
    print(f"{'='*100}")

    # Compute probabilities at each level
    levels_config = [
        ('L1_key', 'L1_full', N_MIN_L1),
        ('L2_key', 'L2_no_tide', N_MIN_L2),
        ('L3_key', 'L3_sc_svw', N_MIN_L3),
        ('L4_key', 'L4_svw', N_MIN_L4),
    ]

    all_train_cells = {}
    all_test_cells = {}

    print(f"\n{'='*100}")
    print("  TRAINING — Computing P(bull|state) per cell")
    print(f"{'='*100}")

    for key_col, level, n_min in levels_config:
        train_cells = compute_probabilities(train, key_col, level, n_min)
        test_cells = compute_probabilities(test, key_col, level, max(n_min // 2, 5))

        # Print summary
        if train_cells:
            p_vals = [c['P_bull'] for c in train_cells.values()]
            n_vals = [c['N'] for c in train_cells.values()]
            print(f"\n  {level}: {len(train_cells)} cells (N_min={n_min})")
            print(f"    P(bull) range: {min(p_vals):.3f} → {max(p_vals):.3f} "
                  f"(spread={max(p_vals)-min(p_vals):.3f})")
            print(f"    N range: {min(n_vals)} → {max(n_vals)} "
                  f"(median={int(np.median(n_vals))})")

            # Show extreme cells
            sorted_cells = sorted(train_cells.items(), key=lambda x: x[1]['P_bull'])
            print(f"    MOST BEAR:")
            for k, v in sorted_cells[:3]:
                print(f"      {k}: P={v['P_bull']:.3f} N={v['N']}")
            print(f"    MOST BULL:")
            for k, v in sorted_cells[-3:]:
                print(f"      {k}: P={v['P_bull']:.3f} N={v['N']}")

        all_train_cells[level] = train_cells
        all_test_cells[level] = test_cells

    # Validate train vs test
    print(f"\n{'='*100}")
    print("  VALIDATION — Train vs Test correlation")
    print(f"{'='*100}\n")

    correlations = {}
    for key_col, level, n_min in levels_config:
        r = validate_train_test(
            all_train_cells[level],
            all_test_cells[level],
            level,
        )
        correlations[level] = r

    # Build final lookup (train cells only, with level hierarchy)
    lookup = {}
    for level in ['L1_full', 'L2_no_tide', 'L3_sc_svw', 'L4_svw']:
        for key, cell in all_train_cells[level].items():
            lookup[f"{level}:{key}"] = cell

    # Output JSON
    output = {
        "version": "v1_sigma_2026-06-11",
        "zigzag_level": ZIGZAG_LEVEL,
        "n_tickers": int(cs['ticker'].nunique()),
        "n_train_samples": len(train),
        "n_test_samples": len(test),
        "base_p_bull_train": round(float(train['is_bull'].mean()), 4),
        "base_p_bull_test": round(float(test['is_bull'].mean()), 4),
        "sigma_bins": {label: [lo, hi] for lo, hi, label in SIGMA_BINS},
        "tide_bins": {label: [lo, hi] for lo, hi, label in TIDE_BINS},
        "correlations": {k: round(v, 3) for k, v in correlations.items()},
        "n_cells": {level: len(all_train_cells[level]) for level in all_train_cells},
        "cells": lookup,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n{'='*100}")
    print(f"  OUTPUT: {OUTPUT_PATH}")
    print(f"  Total cells: {len(lookup)}")
    print(f"  Correlations: {correlations}")
    print(f"{'='*100}")

    # Print detailed train vs test comparison for L2 (most robust)
    if all_train_cells['L2_no_tide'] and all_test_cells['L2_no_tide']:
        print(f"\n{'='*100}")
        print("  L2 DETAIL: σ_c × σ_w × σVw → P(bull) [TRAIN vs TEST]")
        print(f"{'='*100}\n")
        print(f"  {'Key':<20s} {'Train':>8s} {'Test':>8s} {'Δ':>8s} {'N_tr':>6s} {'N_te':>6s}")
        common = set(all_train_cells['L2_no_tide'].keys()) & set(all_test_cells['L2_no_tide'].keys())
        for key in sorted(common):
            tr = all_train_cells['L2_no_tide'][key]
            te = all_test_cells['L2_no_tide'][key]
            delta = te['P_bull'] - tr['P_bull']
            marker = "✓" if abs(delta) < 0.15 else "⚠" if abs(delta) < 0.25 else "✗"
            print(f"  {key:<20s} {tr['P_bull']:>7.1%} {te['P_bull']:>7.1%} "
                  f"{delta:>+7.1%} {tr['N']:>6d} {te['N']:>6d}  {marker}")

    print("\nDONE")


if __name__ == "__main__":
    main()
