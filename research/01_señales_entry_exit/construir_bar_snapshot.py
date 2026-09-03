#!/usr/bin/env python3
"""
SPRINT 1: Construir bar_augment.parquet + bar_signals.parquet
==============================================================
Genera las columnas que NO existen en continuous_metar_lake.parquet.

Outputs:
  data/research/bar_augment.parquet  — 51 cols (FP + Timing + Entry flags)
  data/research/bar_signals.parquet  — 72 cols (36 señales × bool + entry)

Prerequisites:
  data/research/continuous_metar_lake.parquet (8,453 × 257)
  data/research/pivots/quants_obs.pkl (ZigZag pivot dates)
"""
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[2]
RESEARCH_DIR = ROOT / "research" / "01_señales_entry_exit"
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluador_general import cargar_entorno_evaluacion, first_passage_bar, build_episodes
from arnes.timing import classify_timing_slots
from arnes.registro import SEÑALES, _CERTEZA
import arnes.señales  # noqa: F401 — force registration of all signals

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
STATIONS = [
    "vix", "vvix", "pcr", "fg", "sv5_turbulence",
    "skew", "credit", "yield_curve", "rotation", "dxy", "bsi",
]

ESCALAS = {"zz25": 0.025, "zz50": 0.050, "zz75": 0.075}
DIRECTIONS = {"long": "MIN", "short": "MAX"}

OUT_DIR = ROOT / "data" / "research"


def build_first_passage_columns(lake: pd.DataFrame) -> pd.DataFrame:
    """Compute 36 First-Passage columns for every bar in the Lake.
    
    For each bar, for each scale (zz25, zz50, zz75) × direction (long, short):
      {scale}_{dir}_hit, {scale}_{dir}_fav, {scale}_{dir}_mae,
      {scale}_{dir}_mfe, {scale}_{dir}_bars, {scale}_{dir}_timeout
    """
    close = lake["spy_close"].values.astype(float)
    highs = lake["spy_high"].values.astype(float)
    lows = lake["spy_low"].values.astype(float)
    n = len(close)
    
    # Pre-allocate arrays
    cols = {}
    for scale_name, scale_val in ESCALAS.items():
        for dir_name, blanco in DIRECTIONS.items():
            prefix = f"{scale_name}_{dir_name}"
            cols[f"{prefix}_hit"] = np.full(n, np.nan)
            cols[f"{prefix}_fav"] = np.full(n, np.nan)
            cols[f"{prefix}_mae"] = np.full(n, np.nan)
            cols[f"{prefix}_mfe"] = np.full(n, np.nan)
            cols[f"{prefix}_bars"] = np.full(n, np.nan)
            cols[f"{prefix}_timeout"] = np.full(n, np.nan)

    t0_time = time.time()
    
    for i in range(n):
        for scale_name, scale_val in ESCALAS.items():
            for dir_name, blanco in DIRECTIONS.items():
                r = first_passage_bar(close, highs, lows, i, scale_val, blanco)
                if r is None:
                    continue
                prefix = f"{scale_name}_{dir_name}"
                cols[f"{prefix}_hit"][i] = float(r["hit"])
                cols[f"{prefix}_fav"][i] = r["favorable"]
                cols[f"{prefix}_mae"][i] = r["mae"]
                cols[f"{prefix}_mfe"][i] = r["mfe"]
                cols[f"{prefix}_bars"][i] = r["bars"]
                cols[f"{prefix}_timeout"][i] = float(r["timeout"])
        
        if (i + 1) % 2000 == 0:
            elapsed = time.time() - t0_time
            eta = elapsed / (i + 1) * (n - i - 1)
            print(f"  FP: {i+1}/{n} bars ({elapsed:.1f}s elapsed, ~{eta:.1f}s remaining)")

    elapsed = time.time() - t0_time
    print(f"  FP complete: {n} bars × 6 FP calls = {n*6:,} calls in {elapsed:.1f}s")
    
    return pd.DataFrame(cols, index=lake.index)


def build_timing_columns(lake: pd.DataFrame, quants: pd.DataFrame) -> pd.DataFrame:
    """Compute 4 timing columns for every bar.
    
    tim_slot, pivot_nearest_type, pivot_nearest_date, delta_bars_pivot
    """
    lake_idx = pd.DatetimeIndex(lake.index).normalize()
    piv_dates = pd.DatetimeIndex(quants["pivot_date"]).normalize()
    piv_types = quants["pivot_type"].values

    # Use classify_timing_slots for ALL bars (every bar is a "signal")
    timing_df = classify_timing_slots(
        signal_dates=lake_idx,
        pivot_dates=piv_dates,
        pivot_types=piv_types,
        target_pivot_type=None,  # consider both MIN and MAX
        trading_index=lake_idx,
    )

    result = pd.DataFrame(index=lake.index)
    result["tim_slot"] = timing_df["slot"].values
    result["pivot_nearest_type"] = timing_df["pivot_type"].values
    result["pivot_nearest_date"] = timing_df["nearest_pivot_date"].values
    result["delta_bars_pivot"] = timing_df["delta_days"].values.astype(int)

    return result


def build_entry_flags(lake: pd.DataFrame) -> pd.DataFrame:
    """Compute 11 entry flags: True on the first bar where {E}_sk changes.
    
    {E}_entry for each of the 11 stations.
    """
    result = pd.DataFrame(index=lake.index)
    
    for station in STATIONS:
        sk_col = f"{station}_sk"
        if sk_col in lake.columns:
            sk = lake[sk_col]
            result[f"{station}_entry"] = (sk != sk.shift(1)).astype(bool)
            # First row: always True (entry into first state)
            result.loc[result.index[0], f"{station}_entry"] = True
        else:
            result[f"{station}_entry"] = False
            print(f"  WARNING: {sk_col} not found in Lake")
    
    return result


def build_signal_columns(lake: pd.DataFrame) -> pd.DataFrame:
    """Compute signal columns: {S} (bool) + {S}_entry (bool) for each registered signal."""
    result = pd.DataFrame(index=lake.index)
    
    n_registered = 0
    for name, fn in sorted(SEÑALES.items()):
        try:
            mask = fn(lake).values.astype(bool)
            result[name] = mask
            
            # Entry flag: first bar of each episode (transition 0→1)
            entry = np.zeros(len(mask), dtype=bool)
            entry[0] = mask[0]
            for i in range(1, len(mask)):
                entry[i] = mask[i] and not mask[i - 1]
            result[f"{name}_entry"] = entry
            
            n_active = mask.sum()
            n_entries = entry.sum()
            n_registered += 1
            
        except Exception as e:
            print(f"  WARNING: Signal '{name}' failed: {e}")
            result[name] = False
            result[f"{name}_entry"] = False
    
    print(f"  Signals: {n_registered}/{len(SEÑALES)} registered successfully")
    return result


def main():
    print("=" * 70)
    print("SPRINT 1: Build bar_augment.parquet + bar_signals.parquet")
    print("=" * 70)
    
    # ─── Load data ───────────────────────────────────────────────────────
    print("\n[1/5] Loading Lake and pivot data...")
    lake, quants = cargar_entorno_evaluacion()
    print(f"  Lake: {lake.shape[0]} rows × {lake.shape[1]} cols")
    print(f"  Pivots: {len(quants)} ZigZag pivots")
    
    # ─── First-Passage ───────────────────────────────────────────────────
    print("\n[2/5] Computing First-Passage columns (36 cols)...")
    fp_df = build_first_passage_columns(lake)
    print(f"  Shape: {fp_df.shape}")
    
    # ─── Timing ──────────────────────────────────────────────────────────
    print("\n[3/5] Computing Timing columns (4 cols)...")
    timing_df = build_timing_columns(lake, quants)
    print(f"  Shape: {timing_df.shape}")
    print(f"  Timing distribution: {timing_df['tim_slot'].value_counts().to_dict()}")
    
    # ─── Entry Flags ─────────────────────────────────────────────────────
    print("\n[4/5] Computing Entry Flags (11 cols)...")
    entry_df = build_entry_flags(lake)
    print(f"  Shape: {entry_df.shape}")
    for station in STATIONS:
        col = f"{station}_entry"
        if col in entry_df.columns:
            n_entries = entry_df[col].sum()
            print(f"    {station:20s}: {n_entries:5d} entries")
    
    # ─── Concatenate augment ─────────────────────────────────────────────
    augment = pd.concat([fp_df, timing_df, entry_df], axis=1)
    assert len(augment) == len(lake), f"Row mismatch: augment={len(augment)}, lake={len(lake)}"
    
    # Verify no Lake duplication
    lake_cols = set(lake.columns)
    augment_cols = set(augment.columns)
    overlap = lake_cols & augment_cols
    if overlap:
        print(f"  WARNING: Overlapping columns with Lake: {overlap}")
        augment = augment.drop(columns=list(overlap))
    
    augment_path = OUT_DIR / "bar_augment.parquet"
    augment.to_parquet(augment_path)
    print(f"\n  ✅ bar_augment.parquet: {augment.shape[0]} rows × {augment.shape[1]} cols → {augment_path}")
    
    # ─── Signals ─────────────────────────────────────────────────────────
    print("\n[5/5] Computing Signal columns...")
    signals_df = build_signal_columns(lake)
    print(f"  Shape: {signals_df.shape}")
    
    signals_path = OUT_DIR / "bar_signals.parquet"
    signals_df.to_parquet(signals_path)
    print(f"  ✅ bar_signals.parquet: {signals_df.shape[0]} rows × {signals_df.shape[1]} cols → {signals_path}")
    
    # ─── Verification ────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)
    
    aug = pd.read_parquet(augment_path)
    sig = pd.read_parquet(signals_path)
    
    assert len(aug) == 8453, f"Augment rows: {len(aug)} (expected 8453)"
    assert len(sig) == 8453, f"Signals rows: {len(sig)} (expected 8453)"
    assert (aug.index == lake.index).all(), "Augment index mismatch"
    assert (sig.index == lake.index).all(), "Signals index mismatch"
    
    # No Lake duplication
    for col in ["vix_sk", "spy_close", "vix_z_d1", "panic_score"]:
        assert col not in aug.columns, f"LAKE DUPLICATION: {col} in augment!"
    
    # Critical columns present
    assert "zz25_long_hit" in aug.columns, "Missing zz25_long_hit"
    assert "tim_slot" in aug.columns, "Missing tim_slot"
    assert "vix_entry" in aug.columns, "Missing vix_entry"
    
    # Signal columns present
    assert "panico_total" in sig.columns, "Missing panico_total"
    assert "panico_total_entry" in sig.columns, "Missing panico_total_entry"
    
    print("  ✅ All assertions passed!")
    print(f"\n  Augment: {aug.shape[1]} columns")
    print(f"  Signals: {sig.shape[1]} columns")
    print(f"  Total new columns: {aug.shape[1] + sig.shape[1]}")
    
    # Summary stats
    for scale in ["zz25", "zz50", "zz75"]:
        col = f"{scale}_long_hit"
        valid = aug[col].dropna()
        hr = valid.mean()
        print(f"  Baseline {scale} long HR: {hr:.4f} (N={len(valid)})")
    
    return augment, signals_df


if __name__ == "__main__":
    main()
