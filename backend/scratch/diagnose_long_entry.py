#!/usr/bin/env python3
"""
Diagnose long_entry degradation — compare tape vs fresh HeadScorer output.

For each audit ticker, pick 10 bars and compare:
1. Tape's stored p_long_entry
2. HeadScorer with prev_snapshot (audit mode)
3. HeadScorer without prev_snapshot (tape-generator mode, sequential)

This isolates whether the discrepancy is in delta computation or elsewhere.
"""
import os, sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
import pandas as pd

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.rules.compute_channel import compute_channel_snapshot
from backend.modules.shared.infrastructure.head_scorer import HeadScorer
from backend.modules.price_analysis.application.use_cases.analyze_rsi import RSIIntelligence
from backend.modules.volume_intelligence.application.use_cases.track_volume_dynamics import KalmanVolumeTracker

store = TimescaleDataStore()
scorer_seq = HeadScorer()   # Sequential mode (like tape generator)
scorer_expl = HeadScorer()  # Explicit prev_snapshot mode (like audit)

TICKERS = ["SPY", "AAPL"]
SAMPLE_BARS = 10

print("=" * 110)
print("  DIAGNOSTIC: long_entry tape vs fresh computation")
print("  Comparing sequential (tape) vs explicit prev_snapshot (audit) scoring")
print("=" * 110)

for ticker in TICKERS:
    ohlc = store.load_bars(ticker, "1d")
    if ohlc is None or len(ohlc) < 300:
        continue

    close = ohlc["close"].values.astype(float)
    high = ohlc["high"].values.astype(float)
    low = ohlc["low"].values.astype(float)
    volume = ohlc["volume"].values.astype(float)
    timestamps = ohlc.index.tolist()

    # Pre-compute RSI
    intel = RSIIntelligence()
    raw_rsi = intel._calc_rsi_series(close, 14)
    rsi_full = np.concatenate(([50.0], raw_rsi))

    # Pre-compute Kalman
    tracker = KalmanVolumeTracker(dt=1.0, process_noise=0.05, obs_noise=0.2)
    vol_s = pd.Series(volume)
    vol_m = vol_s.rolling(window=20, min_periods=1).mean()
    returns = pd.Series(close).pct_change()
    kalman_vel = np.zeros(len(close))
    kalman_vad = np.zeros(len(close))
    for i in range(len(close)):
        rv = float(volume[i])
        av = float(vol_m.iloc[i])
        orvol = rv / av if av > 0 else 1.0
        pc = float(close[max(0, i - 1)])
        cc = float(close[i])
        chg = ((cc - pc) / pc * 100) if pc > 0 else 0.0
        st = tracker.update(ticker, orvol, chg)
        kalman_vel[i] = st.get("velocity", 0.0)
        if i >= 20:
            v20 = returns.iloc[max(0, i - 19) : i + 1].std()
            kalman_vad[i] = kalman_vel[i] / max(v20 * 100, 0.01)

    # Load tape
    q = f"SELECT timestamp, p_long_entry, p_swing_exit, p_pullback_depth, p_short_entry FROM engine.signal_tape WHERE ticker = '{ticker}' ORDER BY timestamp"
    tape = pd.read_sql(q, store.engine, parse_dates=['timestamp'])

    # Sample bars from the middle (not first/last)
    mid = len(ohlc) // 2
    sample_indices = list(range(mid, mid + SAMPLE_BARS))

    # Run sequential scoring for all bars from 250 up to max sample idx
    # (to build up internal state like the tape generator)
    max_idx = max(sample_indices) + 1
    seq_scores_cache = {}

    print(f"\n{'─' * 110}")
    print(f"  {ticker}: Running sequential scoring from idx=250 to idx={max_idx}...")

    for idx in range(250, max_idx):
        snap = compute_channel_snapshot(close, high, low, volume, idx)
        if snap is None:
            continue
        snap.rsi_value = round(float(rsi_full[idx]), 2)
        snap.kalman_velocity = round(float(kalman_vel[idx]), 6)
        snap.vol_adj_delta = round(float(kalman_vad[idx]), 6)

        # Sequential scoring (no prev_snapshot — like tape generator)
        scores = scorer_seq.score_all(ticker, snap)
        if idx in sample_indices:
            seq_scores_cache[idx] = {h: s.probability for h, s in scores.items()}

    print(f"  {ticker}: Sequential scoring complete. Now computing explicit prev_snapshot scores...")

    # Now score with explicit prev_snapshot (like audit)
    print(f"\n  {'idx':>5s} │ {'Head':>16s} │ {'tape':>8s} │ {'seq(no-prev)':>12s} │ {'expl(prev)':>10s} │ {'seq-tape':>8s} │ {'expl-tape':>9s}")
    print(f"  {'─' * 100}")

    for idx in sample_indices:
        ts = timestamps[idx]

        snap = compute_channel_snapshot(close, high, low, volume, idx)
        if snap is None:
            continue
        snap.rsi_value = round(float(rsi_full[idx]), 2)
        snap.kalman_velocity = round(float(kalman_vel[idx]), 6)
        snap.vol_adj_delta = round(float(kalman_vad[idx]), 6)

        prev_snap = compute_channel_snapshot(close, high, low, volume, idx - 1)
        if prev_snap is not None:
            prev_snap.rsi_value = round(float(rsi_full[idx - 1]), 2)
            prev_snap.kalman_velocity = round(float(kalman_vel[idx - 1]), 6)
            prev_snap.vol_adj_delta = round(float(kalman_vad[idx - 1]), 6)

        # Explicit prev_snapshot scoring (like audit)
        expl_scores = scorer_expl.score_all(ticker, snap, prev_snapshot=prev_snap)

        # Get tape values
        tape_row = tape[tape['timestamp'] == ts]
        tape_vals = {}
        if not tape_row.empty:
            tape_vals = {
                'long_entry': tape_row.iloc[0].get('p_long_entry'),
                'swing_exit': tape_row.iloc[0].get('p_swing_exit'),
                'pullback_depth': tape_row.iloc[0].get('p_pullback_depth'),
                'short_entry': tape_row.iloc[0].get('p_short_entry'),
            }

        for head in ['long_entry', 'swing_exit', 'pullback_depth', 'short_entry']:
            t_val = tape_vals.get(head)
            s_val = seq_scores_cache.get(idx, {}).get(head)
            e_val = expl_scores[head].probability if head in expl_scores else None

            t_str = f"{t_val:.4f}" if t_val is not None else "N/A"
            s_str = f"{s_val:.4f}" if s_val is not None else "N/A"
            e_str = f"{e_val:.4f}" if e_val is not None else "N/A"

            diff_st = ""
            diff_et = ""
            if t_val is not None and s_val is not None:
                d = s_val - t_val
                diff_st = f"{d:+.4f}" if abs(d) > 0.0001 else "≈0"
            if t_val is not None and e_val is not None:
                d = e_val - t_val
                diff_et = f"{d:+.4f}" if abs(d) > 0.0001 else "≈0"

            print(f"  {idx:>5d} │ {head:>16s} │ {t_str:>8s} │ {s_str:>12s} │ {e_str:>10s} │ {diff_st:>8s} │ {diff_et:>9s}")

    # Also: inspect the feature dicts to see delta differences
    print(f"\n  ── {ticker}: Delta feature comparison at idx={sample_indices[0]} ──")
    idx = sample_indices[0]
    snap = compute_channel_snapshot(close, high, low, volume, idx)
    snap.rsi_value = round(float(rsi_full[idx]), 2)
    snap.kalman_velocity = round(float(kalman_vel[idx]), 6)
    snap.vol_adj_delta = round(float(kalman_vad[idx]), 6)

    prev_snap = compute_channel_snapshot(close, high, low, volume, idx - 1)
    if prev_snap is not None:
        prev_snap.rsi_value = round(float(rsi_full[idx - 1]), 2)
        prev_snap.kalman_velocity = round(float(kalman_vel[idx - 1]), 6)
        prev_snap.vol_adj_delta = round(float(kalman_vad[idx - 1]), 6)

    # Get sequential features (from scorer_seq internal state)
    feat_seq = scorer_seq._snapshot_to_features(ticker, snap)
    # Get explicit features
    scorer_fresh = HeadScorer()
    scorer_fresh._ensure_loaded()
    feat_expl = scorer_fresh._snapshot_to_features(ticker, snap, prev_snapshot=prev_snap)

    DELTA_SOURCES = ['sigma_wave', 'kalman_velocity', 'rsi_value', 'compression_ratio',
                     'fear_level', 'vol_up_down_ratio', 'tide_slope', 'wave_accel']

    print(f"  {'delta':>25s} │ {'sequential':>12s} │ {'explicit':>12s} │ {'diff':>10s}")
    print(f"  {'─' * 70}")
    for src in DELTA_SOURCES:
        key = f"d_{src}"
        sv = feat_seq.get(key, 0)
        ev = feat_expl.get(key, 0)
        diff = sv - ev
        marker = " ← DIFFERS" if abs(diff) > 0.0001 else ""
        print(f"  {key:>25s} │ {sv:>12.6f} │ {ev:>12.6f} │ {diff:>+10.6f}{marker}")

store.close()
print(f"\n{'=' * 110}")
print("  DIAGNOSTIC COMPLETE")
print(f"{'=' * 110}")
