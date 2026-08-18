#!/usr/bin/env python3
"""
Forensic Lab v3 — SIGMA STRUCTURE ANALYSIS
Analyzes the SEQUENCE of σ peaks and troughs (higher highs/lower lows)
at the moment each forensic signal fires.

Treats σ_tide and σ_wave as stochastic processes with their own trend structure:
  - σ making higher lows (HL) → floor ascending → trend strengthening
  - σ making lower highs (LH) → ceiling descending → trend weakening  
  - σ making higher low AFTER lower low → inflection → slingshot tensing
  - σ making lower high AFTER higher high → reversal → exhaustion

Uses the raw OHLCV from the Vault + linreg_channel functions to compute
full σ time series, then peak/trough detection at each signal timestamp.
"""

import os, sys, json, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import pandas as pd
import numpy as np
import psycopg2, psycopg2.extras
from scipy.signal import argrelextrema

from backend.modules.quality_swing.domain.rules.regression_channel import (
    linreg_channel, sigma_position as calc_sigma,
)
from backend.modules.shared.domain.rules.cycle_detection import detect_dominant_cycle

# ════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════
LONG_WINDOW = 200
PEAK_ORDER = 10  # Local extrema detection window (bars around peak/trough)

def p(t): print(f"\n{'='*80}\n  {t}\n{'='*80}")
def sp(t): print(f"\n  ── {t} ──")


# ════════════════════════════════════════════════════════════
# 1. COMPUTE FULL σ TIME SERIES FROM OHLCV
# ════════════════════════════════════════════════════════════

def compute_sigma_series(close: np.ndarray) -> dict:
    """Compute rolling σ_tide and σ_wave for the entire close series."""
    n = len(close)
    sigma_tide = np.full(n, np.nan)
    sigma_wave = np.full(n, np.nan)
    tide_slope_arr = np.full(n, np.nan)
    wave_slope_arr = np.full(n, np.nan)

    # Pre-compute dominant cycle once (approximation — could vary)
    dom_cycle = detect_dominant_cycle(close)
    short_window = max(10, min(dom_cycle, 60))

    for i in range(LONG_WINDOW + 5, n):
        price_window = close[:i + 1]
        current_price = close[i]

        # Tide (200-bar)
        reg_val, t_slope, res_std = linreg_channel(price_window, LONG_WINDOW)
        sigma_tide[i] = calc_sigma(current_price, reg_val, res_std)
        tide_slope_arr[i] = t_slope

        # Wave (cycle-adaptive)
        if i >= short_window + 5:
            reg_val_s, w_slope, res_std_s = linreg_channel(price_window, short_window)
            sigma_wave[i] = calc_sigma(current_price, reg_val_s, res_std_s)
            wave_slope_arr[i] = w_slope

    return {
        "sigma_tide": sigma_tide,
        "sigma_wave": sigma_wave,
        "tide_slope": tide_slope_arr,
        "wave_slope": wave_slope_arr,
    }


# ════════════════════════════════════════════════════════════
# 2. DETECT PEAKS AND TROUGHS
# ════════════════════════════════════════════════════════════

def detect_extrema(series: np.ndarray, order: int = PEAK_ORDER):
    """Detect local maxima (peaks) and minima (troughs) in a series.
    
    Returns:
        peaks: array of indices where local maxima occur
        troughs: array of indices where local minima occur
    """
    # Remove NaNs for detection
    valid = ~np.isnan(series)
    if valid.sum() < order * 3:
        return np.array([]), np.array([])

    # Detect peaks (local maxima)
    peaks = argrelextrema(series, np.greater, order=order)[0]
    # Filter out NaN positions
    peaks = peaks[valid[peaks]]

    # Detect troughs (local minima)
    troughs = argrelextrema(series, np.less, order=order)[0]
    troughs = troughs[valid[troughs]]

    return peaks, troughs


def classify_structure(series: np.ndarray, peaks: np.ndarray, troughs: np.ndarray, 
                       at_idx: int, lookback: int = 3) -> dict:
    """Classify the sigma structure at a given index.
    
    Looks at the last `lookback` peaks and troughs before `at_idx`.
    
    Returns dict with:
        - peak_structure: "HH" (higher highs), "LH" (lower highs), "MIXED", "INSUFFICIENT"
        - trough_structure: "HL" (higher lows), "LL" (lower lows), "MIXED", "INSUFFICIENT"
        - combined: "BULL" (HH+HL), "BEAR" (LH+LL), "REVERSAL_UP" (HL after LL), 
                    "REVERSAL_DOWN" (LH after HH), "MIXED"
        - last_peak_val, last_trough_val, prev_peak_val, prev_trough_val
        - peak_delta: last_peak - prev_peak (positive = HH)
        - trough_delta: last_trough - prev_trough (positive = HL)
    """
    result = {
        "peak_structure": "INSUFFICIENT",
        "trough_structure": "INSUFFICIENT",
        "combined": "INSUFFICIENT",
        "last_peak_val": None, "prev_peak_val": None,
        "last_trough_val": None, "prev_trough_val": None,
        "peak_delta": None, "trough_delta": None,
        "n_peaks": 0, "n_troughs": 0,
    }

    # Get peaks before this index
    recent_peaks = peaks[peaks < at_idx]
    recent_troughs = troughs[troughs < at_idx]

    result["n_peaks"] = len(recent_peaks)
    result["n_troughs"] = len(recent_troughs)

    # Analyze peaks (last `lookback` peaks)
    if len(recent_peaks) >= 2:
        last_peaks = recent_peaks[-lookback:]
        peak_vals = series[last_peaks]
        result["last_peak_val"] = float(peak_vals[-1])
        result["prev_peak_val"] = float(peak_vals[-2])
        result["peak_delta"] = float(peak_vals[-1] - peak_vals[-2])

        # Check if peaks are consistently higher or lower
        diffs = np.diff(peak_vals)
        if np.all(diffs > 0):
            result["peak_structure"] = "HH"  # Higher Highs
        elif np.all(diffs < 0):
            result["peak_structure"] = "LH"  # Lower Highs
        else:
            result["peak_structure"] = "MIXED"

    # Analyze troughs (last `lookback` troughs)
    if len(recent_troughs) >= 2:
        last_troughs = recent_troughs[-lookback:]
        trough_vals = series[last_troughs]
        result["last_trough_val"] = float(trough_vals[-1])
        result["prev_trough_val"] = float(trough_vals[-2])
        result["trough_delta"] = float(trough_vals[-1] - trough_vals[-2])

        diffs = np.diff(trough_vals)
        if np.all(diffs > 0):
            result["trough_structure"] = "HL"  # Higher Lows
        elif np.all(diffs < 0):
            result["trough_structure"] = "LL"  # Lower Lows
        else:
            result["trough_structure"] = "MIXED"

    # Combined classification
    ps = result["peak_structure"]
    ts = result["trough_structure"]

    if ps == "HH" and ts == "HL":
        result["combined"] = "BULL_STRUCTURE"       # Classic uptrend
    elif ps == "LH" and ts == "LL":
        result["combined"] = "BEAR_STRUCTURE"       # Classic downtrend
    elif ps == "LH" and ts == "HL":
        result["combined"] = "COMPRESSION"          # Converging — breakout imminent
    elif ps == "HH" and ts == "LL":
        result["combined"] = "EXPANSION"            # Diverging — volatility expansion
    elif ts == "HL" and ps in ("LH", "MIXED"):
        result["combined"] = "REVERSAL_UP"          # Higher lows forming = floor ascending
    elif ps == "LH" and ts in ("HL", "MIXED"):
        result["combined"] = "REVERSAL_DOWN"        # Lower highs forming = ceiling descending  
    elif ps != "INSUFFICIENT" or ts != "INSUFFICIENT":
        result["combined"] = "MIXED"

    return result


# ════════════════════════════════════════════════════════════
# 3. LOAD FORENSIC LABELS AND ENRICH WITH STRUCTURE
# ════════════════════════════════════════════════════════════

def load_ohlcv(ticker: str) -> pd.DataFrame:
    """Load OHLCV from Vault."""
    pg_url = os.environ.get("POSTGRES_URL", "")
    conn = psycopg2.connect(pg_url)
    df = pd.read_sql(
        "SELECT time, open, high, low, close, volume FROM market.ohlcv_bars "
        "WHERE ticker = %s ORDER BY time",
        conn, params=(ticker,)
    )
    conn.close()
    df["time"] = pd.to_datetime(df["time"])
    return df


def load_forensic_labels(table: str) -> pd.DataFrame:
    pg_url = os.environ.get("POSTGRES_URL", "")
    conn = psycopg2.connect(pg_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(f"SELECT * FROM engine.{table}")
    rows = cur.fetchall()
    conn.close()
    records = []
    for row in rows:
        flat = {
            "ticker": row["ticker"], "signal_name": row["signal_name"],
            "signal_direction": row["signal_direction"],
            "signal_time": row["signal_time"],
            "classification": row["classification"],
        }
        snap = row["snapshot"]
        if isinstance(snap, str): snap = json.loads(snap)
        if snap:
            for k, v in snap.items(): flat[f"snap_{k}"] = v
        horizons = row["horizons"]
        if isinstance(horizons, str): horizons = json.loads(horizons)
        if horizons:
            for h_key, h_val in horizons.items():
                for m, mv in h_val.items():
                    flat[f"h{h_key}_{m}"] = mv
        records.append(flat)
    df = pd.DataFrame(records)
    df["signal_time"] = pd.to_datetime(df["signal_time"])
    return df


# ════════════════════════════════════════════════════════════
# 4. MAIN ANALYSIS
# ════════════════════════════════════════════════════════════

def analyze_sigma_structure(ticker: str, entry_labels: pd.DataFrame):
    """Full sigma structure analysis for a ticker."""
    sp(f"SIGMA STRUCTURE ANALYSIS: {ticker}")

    # Load OHLCV
    ohlcv = load_ohlcv(ticker)
    if len(ohlcv) < LONG_WINDOW + 50:
        print(f"    ⚠ Insufficient OHLCV data for {ticker}")
        return
    
    close = ohlcv["close"].values.astype(float)
    times = ohlcv["time"].values

    print(f"    OHLCV: {len(ohlcv)} bars ({ohlcv['time'].min()} → {ohlcv['time'].max()})")

    # Compute full σ series
    print(f"    Computing σ time series (this takes a moment)...")
    sigma_data = compute_sigma_series(close)
    sigma_tide = sigma_data["sigma_tide"]
    sigma_wave = sigma_data["sigma_wave"]

    # Detect extrema
    tide_peaks, tide_troughs = detect_extrema(sigma_tide)
    wave_peaks, wave_troughs = detect_extrema(sigma_wave)

    print(f"    σ_tide: {len(tide_peaks)} peaks, {len(tide_troughs)} troughs")
    print(f"    σ_wave: {len(wave_peaks)} peaks, {len(wave_troughs)} troughs")

    # Get entry labels for this ticker
    ticker_labels = entry_labels[
        (entry_labels["ticker"] == ticker) & (entry_labels["signal_direction"] == 1)
    ].copy()

    if len(ticker_labels) == 0:
        print(f"    ⚠ No entry labels for {ticker}")
        return

    ticker_labels["is_win"] = ticker_labels["classification"].isin(
        ["GOLDEN_RUN", "SOLID_MOVE"]
    ).astype(int)

    # Map each signal to the nearest OHLCV bar index
    time_index = pd.DatetimeIndex(times)

    tide_structures = []
    wave_structures = []

    for _, row in ticker_labels.iterrows():
        signal_time = row["signal_time"]
        # Find nearest bar
        # Handle timezone: strip tz for comparison
        if hasattr(signal_time, 'tz') and signal_time.tz is not None:
            signal_time_naive = signal_time.tz_localize(None)
        else:
            signal_time_naive = signal_time
        
        idx_candidates = np.where(pd.DatetimeIndex(times).normalize() == 
                                   pd.Timestamp(signal_time_naive).normalize())[0]
        if len(idx_candidates) == 0:
            # Try closest match
            diffs = np.abs(pd.DatetimeIndex(times) - pd.Timestamp(signal_time_naive))
            bar_idx = int(diffs.argmin())
        else:
            bar_idx = int(idx_candidates[0])

        tide_struct = classify_structure(sigma_tide, tide_peaks, tide_troughs, bar_idx)
        wave_struct = classify_structure(sigma_wave, wave_peaks, wave_troughs, bar_idx)

        tide_structures.append(tide_struct)
        wave_structures.append(wave_struct)

    # Add structure columns to labels
    ticker_labels["tide_combined"] = [s["combined"] for s in tide_structures]
    ticker_labels["wave_combined"] = [s["combined"] for s in wave_structures]
    ticker_labels["tide_peak_struct"] = [s["peak_structure"] for s in tide_structures]
    ticker_labels["tide_trough_struct"] = [s["trough_structure"] for s in tide_structures]
    ticker_labels["wave_peak_struct"] = [s["peak_structure"] for s in wave_structures]
    ticker_labels["wave_trough_struct"] = [s["trough_structure"] for s in wave_structures]
    ticker_labels["tide_peak_delta"] = [s["peak_delta"] for s in tide_structures]
    ticker_labels["tide_trough_delta"] = [s["trough_delta"] for s in tide_structures]
    ticker_labels["wave_peak_delta"] = [s["peak_delta"] for s in wave_structures]
    ticker_labels["wave_trough_delta"] = [s["trough_delta"] for s in wave_structures]

    # ═══ ANALYSIS BY SIGNAL ═══
    for signal in ticker_labels["signal_name"].unique():
        sig_df = ticker_labels[ticker_labels["signal_name"] == signal]
        n = len(sig_df)
        if n < 10: continue

        print(f"\n    ┌───────────────────────────────────────────────┐")
        print(f"    │ {signal} × {ticker} ({n} signals)")
        print(f"    └───────────────────────────────────────────────┘")

        # ── σ_tide structure vs win rate ──
        print(f"\n    σ_TIDE Structure at Signal Time:")
        for struct in ["BULL_STRUCTURE", "BEAR_STRUCTURE", "COMPRESSION", 
                        "EXPANSION", "REVERSAL_UP", "REVERSAL_DOWN", "MIXED"]:
            mask = sig_df["tide_combined"] == struct
            if mask.sum() < 3: continue
            wr = sig_df.loc[mask, "is_win"].mean() * 100
            cnt = mask.sum()
            bar = "█" * int(wr / 5)
            marker = " ★" if wr > 60 else " ✗" if wr < 40 else ""
            print(f"      {struct:>20s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # ── σ_wave structure vs win rate ──
        print(f"\n    σ_WAVE Structure at Signal Time:")
        for struct in ["BULL_STRUCTURE", "BEAR_STRUCTURE", "COMPRESSION", 
                        "EXPANSION", "REVERSAL_UP", "REVERSAL_DOWN", "MIXED"]:
            mask = sig_df["wave_combined"] == struct
            if mask.sum() < 3: continue
            wr = sig_df.loc[mask, "is_win"].mean() * 100
            cnt = mask.sum()
            bar = "█" * int(wr / 5)
            marker = " ★" if wr > 60 else " ✗" if wr < 40 else ""
            print(f"      {struct:>20s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # ── Peak/Trough granular analysis ──
        print(f"\n    σ_TIDE Peak Structure (HH/LH) × Trough Structure (HL/LL):")
        for ps in ["HH", "LH", "MIXED"]:
            for ts in ["HL", "LL", "MIXED"]:
                mask = (sig_df["tide_peak_struct"] == ps) & (sig_df["tide_trough_struct"] == ts)
                if mask.sum() < 3: continue
                wr = sig_df.loc[mask, "is_win"].mean() * 100
                cnt = mask.sum()
                label = f"{ps}+{ts}"
                bar = "█" * int(wr / 5)
                marker = " ★ BULL FLOOR" if (ps == "HH" and ts == "HL" and wr > 55) else \
                         " ★ REVERSAL" if (ps == "LH" and ts == "HL" and wr > 55) else \
                         " ✗ BEAR TRAP" if (ps == "LH" and ts == "LL" and wr < 45) else ""
                print(f"      {label:>10s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        print(f"\n    σ_WAVE Peak Structure × Trough Structure:")
        for ps in ["HH", "LH", "MIXED"]:
            for ts in ["HL", "LL", "MIXED"]:
                mask = (sig_df["wave_peak_struct"] == ps) & (sig_df["wave_trough_struct"] == ts)
                if mask.sum() < 3: continue
                wr = sig_df.loc[mask, "is_win"].mean() * 100
                cnt = mask.sum()
                label = f"{ps}+{ts}"
                bar = "█" * int(wr / 5)
                marker = " ★" if wr > 60 else " ✗" if wr < 40 else ""
                print(f"      {label:>10s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # ── Delta analysis: magnitude of the structural change ──
        for delta_col, delta_name in [("tide_trough_delta", "σ_tide trough Δ (HL/LL magnitude)"),
                                       ("wave_trough_delta", "σ_wave trough Δ (HL/LL magnitude)")]:
            vals = pd.to_numeric(sig_df[delta_col], errors="coerce").dropna()
            if len(vals) < 10: continue

            print(f"\n    {delta_name}:")
            bins = [-999, -0.5, -0.1, 0.1, 0.5, 999]
            labels_b = ["Strong LL", "Mild LL", "~Same", "Mild HL", "Strong HL"]
            buckets = pd.cut(vals, bins=bins, labels=labels_b)
            for b in labels_b:
                mask_b = buckets == b
                idx_match = vals.index[mask_b]
                if len(idx_match) < 3: continue
                wr = sig_df.loc[idx_match, "is_win"].mean() * 100
                cnt = len(idx_match)
                bar = "█" * int(wr / 5)
                marker = " ← RISING FLOOR" if ("HL" in b and wr > 55) else \
                         " ← SINKING FLOOR" if ("LL" in b and wr < 45) else ""
                print(f"      {b:>12s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")

        # ── COMBINED: Structure + Fear Level ──
        if "snap_fear_level" in sig_df.columns:
            fl = pd.to_numeric(sig_df["snap_fear_level"], errors="coerce")
            print(f"\n    COMBINED: σ_wave Structure + Fear Level:")

            # REVERSAL_UP + Fear elevated = maximum slingshot
            for struct in ["BULL_STRUCTURE", "COMPRESSION", "REVERSAL_UP", "BEAR_STRUCTURE"]:
                for fear_cond, fear_label in [(fl >= 3, "Fear≥ANX"), (fl < 2, "Fear<NEU")]:
                    mask = (sig_df["wave_combined"] == struct) & fear_cond
                    if mask.sum() < 3: continue
                    wr = sig_df.loc[mask, "is_win"].mean() * 100
                    cnt = mask.sum()
                    bar = "█" * int(wr / 5)
                    marker = " ★ SLINGSHOT" if (struct in ("REVERSAL_UP", "COMPRESSION") 
                                                and "Fear≥" in fear_label and wr > 60) else ""
                    label = f"{struct} + {fear_label}"
                    print(f"      {label:<38s} │ WR={wr:5.1f}% n={cnt:3d}  {bar}{marker}")


# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    p("FORENSIC LAB v3 — SIGMA STRUCTURE: Higher Highs / Lower Lows")

    print("\n  Loading forensic labels from Neon...")
    entry_labels = load_forensic_labels("entry_forensic_labels")
    print(f"  → {len(entry_labels)} entry labels loaded")

    tickers = ["COST", "SPY", "AAPL", "QQQ"]

    for ticker in tickers:
        analyze_sigma_structure(ticker, entry_labels)

    p("SIGMA STRUCTURE ANALYSIS COMPLETE")
    print("  The structure of σ peaks/troughs reveals:")
    print("    1. BULL_STRUCTURE (HH+HL): ascending floor = safe entry environment")
    print("    2. BEAR_STRUCTURE (LH+LL): descending ceiling = dangerous entries")
    print("    3. COMPRESSION (LH+HL): converging = breakout imminent")
    print("    4. REVERSAL_UP (HL forming): floor ascending = slingshot tensing")
    print("    5. The MAGNITUDE of trough deltas = how fast the floor rises/falls")
    print()
