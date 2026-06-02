#!/usr/bin/env python3
"""
Signal Replay — Validate Sentinel Models on Forward Returns
================================================================
BLOQUEANTE: If this fails, we do NOT proceed to production.

For each bar in the test set (last 20% temporal):
  1. Score with Sentinel PISO/TECHO models
  2. Classify archetype (HL/LL/HH/LH)
  3. Measure forward returns at 5/10/20 bars
  4. Compute hit rate and LIFT per archetype × density

Pass criteria:
  - LL hit rate ≥ 55% at 10d (forward return > 0)
  - HH hit rate ≥ 50% at 10d (forward return < 0)
  - LIFT > 1.0 for all archetypes at ALARMA+

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scratch/sprint2_signal_replay.py
"""
import os
import sys
import pickle
import logging
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
import pandas as pd

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]

MODELS_DIR = root_dir / "backend" / "models"
FORWARD_WINDOWS = [5, 10, 20]
TEST_SPLIT = 0.20  # Last 20% for testing

# Density thresholds
PROB_THRESHOLD = 0.5
DENSITY_LEVELS = {
    "SILENCIO": 0,
    "ALARMA": 1,
    "PRESURIZACIÓN": 5,
    "EXPLOSIÓN": 8,
}


def load_models():
    """Load Sentinel models."""
    models = {}
    for name in ["piso", "techo"]:
        pkl_path = MODELS_DIR / f"sentinel_{name}_v1.pkl"
        with open(pkl_path, "rb") as f:
            models[name] = pickle.load(f)
        print(f"  {name.upper()}: AUC={models[name]['mean_auc']:.4f}, threshold={models[name]['threshold']:.4f}")
    return models


def load_data(store):
    """Load snapshots with Kalman + OHLCV for forward returns."""
    print("  Loading snapshots with Kalman features...")
    conn = store._conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT ticker, timestamp,
               kf_rsi_pred_val, kf_price_filt_vel, kf_price_pred_val,
               kf_conj_pred_val, kf_tension_pred_val, kf_conj_filt_vel,
               rsi_value, sigma_tide, tide_slope, conj_wave_tide
        FROM engine.channel_snapshots
        WHERE kf_rsi_pred_val IS NOT NULL
        ORDER BY ticker, timestamp
    """)
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    df = pd.DataFrame(rows, columns=cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    print(f"  Loaded {len(df):,} snapshots")

    # Load OHLCV for forward returns
    print("  Loading OHLCV for forward returns...")
    all_ohlcv = {}
    for tk in TICKERS:
        ohlcv = store.load_bars(tk, "1d")
        if ohlcv is not None and not ohlcv.empty:
            all_ohlcv[tk] = ohlcv

    store._put(conn)
    return df, all_ohlcv


def compute_forward_returns(df, all_ohlcv):
    """Compute forward returns at 5/10/20 bars for each snapshot."""
    print("  Computing forward returns...")

    for window in FORWARD_WINDOWS:
        df[f"fwd_{window}d"] = np.nan

    for tk in TICKERS:
        tk_mask = df["ticker"] == tk
        tk_df = df.loc[tk_mask]
        if tk not in all_ohlcv or tk_df.empty:
            continue

        ohlcv = all_ohlcv[tk]
        ohlcv_dates = pd.to_datetime(ohlcv.index).tz_localize(None)
        close_arr = ohlcv["close"].values

        snap_dates = tk_df["timestamp"].dt.tz_localize(None).values

        for window in FORWARD_WINDOWS:
            fwd_col = f"fwd_{window}d"
            fwd_returns = np.full(len(tk_df), np.nan)

            for i, snap_date in enumerate(snap_dates):
                # Find this date in OHLCV
                diffs = np.abs((ohlcv_dates.values - snap_date) / np.timedelta64(1, "D"))
                match_idx = np.argmin(diffs)
                if diffs[match_idx] > 2:  # No match within 2 days
                    continue

                future_idx = match_idx + window
                if future_idx < len(close_arr):
                    current_price = float(close_arr[match_idx])
                    future_price = float(close_arr[future_idx])
                    if current_price > 0:
                        fwd_returns[i] = (future_price - current_price) / current_price * 100

            df.loc[tk_mask, fwd_col] = fwd_returns

    for window in FORWARD_WINDOWS:
        n_valid = df[f"fwd_{window}d"].notna().sum()
        print(f"  fwd_{window}d: {n_valid:,} valid ({n_valid/len(df)*100:.1f}%)")

    return df


def score_and_classify(df, models):
    """Score each bar with Sentinel models and classify archetype."""
    print("  Scoring with Sentinel models...")

    piso_model = models["piso"]["model"]
    techo_model = models["techo"]["model"]
    piso_features = models["piso"]["feature_cols"]
    techo_features = models["techo"]["feature_cols"]

    X_piso = df[piso_features].fillna(0.0).values
    X_techo = df[techo_features].fillna(0.0).values

    df["prob_piso"] = piso_model.predict_proba(X_piso)[:, 1]
    df["prob_techo"] = techo_model.predict_proba(X_techo)[:, 1]

    # Classify archetype
    df["archetype"] = "NONE"
    df["dominant_prob"] = df[["prob_piso", "prob_techo"]].max(axis=1)

    for idx in df.index:
        pp = df.at[idx, "prob_piso"]
        pt = df.at[idx, "prob_techo"]
        rsi_pred = df.at[idx, "kf_rsi_pred_val"]
        tide = df.at[idx, "tide_slope"]

        if pp > pt and pp > PROB_THRESHOLD:
            if rsi_pred < 40:
                df.at[idx, "archetype"] = "LL"
            else:
                df.at[idx, "archetype"] = "HL"
        elif pt > pp and pt > PROB_THRESHOLD:
            if rsi_pred > 60:
                df.at[idx, "archetype"] = "HH"
            else:
                df.at[idx, "archetype"] = "LH"

    # Summary
    for arch in ["HL", "LL", "HH", "LH", "NONE"]:
        n = (df["archetype"] == arch).sum()
        pct = n / len(df) * 100
        print(f"  {arch}: {n:,} ({pct:.1f}%)")

    return df


def analyze_results(df):
    """Compute hit rate and LIFT per archetype × forward window."""
    print(f"\n{'='*80}")
    print(f"  SIGNAL REPLAY RESULTS")
    print(f"{'='*80}")

    # Split: test = last 20% per ticker
    test_mask = pd.Series(False, index=df.index)
    for tk in TICKERS:
        tk_idx = df[df["ticker"] == tk].index
        n = len(tk_idx)
        split_point = int(n * (1 - TEST_SPLIT))
        test_mask.loc[tk_idx[split_point:]] = True

    test_df = df[test_mask].copy()
    print(f"\n  Test set: {len(test_df):,} bars ({TEST_SPLIT*100:.0f}% per ticker)")

    # Baseline hit rates (unconditional P(return > 0))
    baselines = {}
    for window in FORWARD_WINDOWS:
        col = f"fwd_{window}d"
        valid = test_df[col].dropna()
        baselines[window] = (valid > 0).mean()
        print(f"  Baseline P(return>0) at {window}d: {baselines[window]*100:.1f}%")

    # Per-archetype analysis
    results = []
    for arch in ["HL", "LL", "HH", "LH"]:
        arch_df = test_df[test_df["archetype"] == arch]
        if len(arch_df) == 0:
            print(f"\n  {arch}: NO SIGNALS in test set")
            continue

        print(f"\n  ── {arch} ({len(arch_df):,} signals) ──")

        for window in FORWARD_WINDOWS:
            col = f"fwd_{window}d"
            valid = arch_df[col].dropna()
            if len(valid) == 0:
                continue

            if arch in ("HL", "LL"):
                # Piso: hit = forward return > 0
                hit_rate = (valid > 0).mean()
                mean_ret = valid.mean()
                lift = hit_rate / baselines[window] if baselines[window] > 0 else 0
            else:
                # Techo: hit = forward return < 0
                hit_rate = (valid < 0).mean()
                mean_ret = -valid.mean()  # Invert for reporting
                lift = hit_rate / (1 - baselines[window]) if baselines[window] < 1 else 0

            results.append({
                "archetype": arch,
                "window": window,
                "n_signals": len(valid),
                "hit_rate": hit_rate,
                "mean_return": valid.mean(),
                "lift": lift,
            })

            status = "✅" if (arch in ("HL", "LL") and hit_rate > 0.55) or (arch in ("HH", "LH") and hit_rate > 0.50) else "⚠️"
            print(f"    {window:>2}d: hit={hit_rate*100:.1f}% mean_ret={valid.mean():+.2f}% "
                  f"LIFT={lift:.2f}x n={len(valid):,} {status}")

    # ── By density level ──
    print(f"\n  ── By Density Level ──")
    for min_prob in [0.5, 0.6, 0.7, 0.8]:
        high_prob = test_df[test_df["dominant_prob"] >= min_prob]
        if len(high_prob) == 0:
            continue
        for arch in ["HL", "LL", "HH", "LH"]:
            arch_hp = high_prob[high_prob["archetype"] == arch]
            if len(arch_hp) < 10:
                continue
            col = "fwd_10d"
            valid = arch_hp[col].dropna()
            if len(valid) < 10:
                continue
            if arch in ("HL", "LL"):
                hr = (valid > 0).mean()
            else:
                hr = (valid < 0).mean()
            print(f"    P≥{min_prob:.1f} {arch}: hit_10d={hr*100:.1f}% n={len(valid)} mean={valid.mean():+.2f}%")

    # ── PASS/FAIL verdict ──
    print(f"\n{'='*80}")
    print(f"  VERDICT")
    print(f"{'='*80}")

    passed = True
    for r in results:
        if r["window"] == 10:
            if r["archetype"] in ("HL", "LL") and r["hit_rate"] < 0.55:
                print(f"  ❌ {r['archetype']} hit_10d = {r['hit_rate']*100:.1f}% < 55%")
                passed = False
            elif r["archetype"] in ("HH", "LH") and r["hit_rate"] < 0.50:
                print(f"  ❌ {r['archetype']} hit_10d = {r['hit_rate']*100:.1f}% < 50%")
                passed = False
            elif r["lift"] < 1.0:
                print(f"  ❌ {r['archetype']} LIFT = {r['lift']:.2f}x < 1.0x")
                passed = False
            else:
                print(f"  ✅ {r['archetype']} hit_10d = {r['hit_rate']*100:.1f}% LIFT={r['lift']:.2f}x")

    if passed:
        print(f"\n  ✅ SIGNAL REPLAY PASSED — Proceed to production")
    else:
        print(f"\n  ⚠️ SIGNAL REPLAY: Some criteria not met — review needed")

    return passed


def main():
    print("=" * 80)
    print("  SIGNAL REPLAY — Sentinel Model Validation")
    print("  Forward return analysis per archetype")
    print("=" * 80)

    store = TimescaleDataStore()

    # Load
    models = load_models()
    df, all_ohlcv = load_data(store)
    store.close()

    # Compute forward returns
    df = compute_forward_returns(df, all_ohlcv)

    # Score and classify
    df = score_and_classify(df, models)

    # Analyze
    passed = analyze_results(df)

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
