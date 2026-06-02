#!/usr/bin/env python3
"""
Sentinel vs ZigZag — Confusion Matrix Forensics
====================================================
Compares Sentinel archetype signals against zigzag ground truth.

For each zigzag turning point (MIN/MAX):
  - Was there a Sentinel signal within ±PROXIMITY bars?
  - TP: Correct direction (PISO at MIN, TECHO at MAX)
  - FN: No Sentinel signal near this turning point (MISSED)
  - INVERTED: Wrong direction (PISO at MAX, TECHO at MIN) ← MOST DANGEROUS

For each Sentinel signal:
  - Was there a zigzag turn within ±PROXIMITY bars?
  - FP: Signal fired with no actual turn nearby (FALSE ALARM)

Metrics: Precision, Recall, F1, Inversion Rate, Lead/Lag (how many bars early/late)

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scratch/sentinel_vs_zigzag_forensics.py
"""
import os
import sys
import time
import pickle
import logging
from pathlib import Path
from collections import defaultdict

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
import pandas as pd

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.rules.kalman_5channel import (
    FullKalmanFilter1D, KalmanSnapshot, KALMAN_CHANNELS,
)
from backend.modules.shared.domain.rules.turn_detector import compute_turn_signal
from backend.modules.shared.domain.entities.turn_signal import (
    ARCHETYPE_HL, ARCHETYPE_LL, ARCHETYPE_HH, ARCHETYPE_LH, ARCHETYPE_NONE,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

MODELS_DIR = root_dir / "backend" / "models"
TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]

PROXIMITY_BARS = 3  # ±3 bars to consider a "match"
ZZ_THRESHOLDS = [0.03, 0.05, 0.07]
DENSITY_HISTORY_LEN = 5
TEST_SPLIT = 0.20  # Only evaluate on OOS test set


def load_models():
    models = {}
    for name in ["piso", "techo"]:
        with open(MODELS_DIR / f"sentinel_{name}_v1.pkl", "rb") as f:
            models[name] = pickle.load(f)
    return models


def load_data(store):
    """Load snapshots, OHLCV, and zigzag points."""
    conn = store._conn()
    cur = conn.cursor()

    # Snapshots
    print("  Loading channel snapshots...")
    cur.execute("""
        SELECT ticker, timestamp,
               rsi_value, sigma_tide, tension_tide, conj_wave_tide,
               tide_slope, compression_ratio, fear_level
        FROM engine.channel_snapshots
        WHERE kf_rsi_pred_val IS NOT NULL
        ORDER BY ticker, timestamp
    """)
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    df = pd.DataFrame(rows, columns=cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    print(f"  {len(df):,} snapshots loaded")

    # OHLCV
    print("  Loading OHLCV...")
    all_ohlcv = {}
    for tk in TICKERS:
        ohlcv = store.load_bars(tk, "1d")
        if ohlcv is not None and not ohlcv.empty:
            all_ohlcv[tk] = ohlcv

    # Zigzag points
    print("  Loading zigzag turning points...")
    zigzag = {}
    for threshold in ZZ_THRESHOLDS:
        pct = int(threshold * 100)
        cur.execute("""
            SELECT ticker, timestamp, tp_type
            FROM engine.zigzag_points
            WHERE min_swing_pct = %s
            ORDER BY ticker, timestamp
        """, (threshold,))
        zz_rows = cur.fetchall()
        zz_df = pd.DataFrame(zz_rows, columns=["ticker", "timestamp", "tp_type"])
        zz_df["timestamp"] = pd.to_datetime(zz_df["timestamp"], utc=True)
        zigzag[pct] = zz_df
        print(f"  Zigzag {pct}%: {len(zz_df):,} points ({(zz_df['tp_type']=='MIN').sum()} MIN, {(zz_df['tp_type']=='MAX').sum()} MAX)")

    store._put(conn)
    return df, all_ohlcv, zigzag


def generate_sentinel_signals(df, models, all_ohlcv):
    """Walk-forward to generate Sentinel signals with stateful Kalman."""
    print("\n  Generating Sentinel signals (stateful walk-forward)...")

    piso_model = models["piso"]["model"]
    techo_model = models["techo"]["model"]
    piso_features = models["piso"]["feature_cols"]
    techo_features = models["techo"]["feature_cols"]

    signals = []

    for tk in TICKERS:
        tk_df = df[df["ticker"] == tk].sort_values("timestamp").reset_index(drop=True)
        if tk_df.empty:
            continue

        # Initialize Kalman filters
        kalman_filters = {}
        for ch_name, _, proc_noise, obs_noise in KALMAN_CHANNELS:
            kf = FullKalmanFilter1D(process_noise=proc_noise, obs_noise=obs_noise)
            kalman_filters[ch_name] = kf

        ohlcv = all_ohlcv.get(tk)
        if ohlcv is not None:
            ohlcv_close = ohlcv["close"].values.astype(float)
            ohlcv_volume = ohlcv["volume"].values.astype(float)
            ohlcv_dates = pd.to_datetime(ohlcv.index).tz_localize(None)
        else:
            ohlcv_close = None

        density_history = []

        for i in range(len(tk_df)):
            row = tk_df.iloc[i]
            rsi_val = float(row.get("rsi_value", 50) or 50)
            tension = float(row.get("tension_tide", 0) or 0)
            conj = float(row.get("conj_wave_tide", 0) or 0)

            snap_date = row["timestamp"]
            if snap_date.tzinfo:
                snap_date_naive = snap_date.tz_localize(None)
            else:
                snap_date_naive = snap_date

            price_ret = 0.0
            rvol = 1.0
            if ohlcv_close is not None:
                diffs = np.abs((ohlcv_dates.values - np.datetime64(snap_date_naive)) / np.timedelta64(1, "D"))
                mi = np.argmin(diffs)
                if diffs[mi] < 2:
                    if mi > 0 and ohlcv_close[mi - 1] > 0:
                        price_ret = (ohlcv_close[mi] - ohlcv_close[mi - 1]) / ohlcv_close[mi - 1] * 100
                    if mi >= 20:
                        avg_vol = np.mean(ohlcv_volume[mi - 20:mi])
                        rvol = ohlcv_volume[mi] / max(avg_vol, 1.0) if avg_vol > 0 else 1.0

            inputs = {"price": price_ret, "rvol": rvol, "tension": tension, "rsi": rsi_val, "conjugation": conj}

            kalman_outputs = {}
            for ch_name, _, _, _ in KALMAN_CHANNELS:
                kf = kalman_filters[ch_name]
                if i == 0:
                    kf.reset(inputs[ch_name])
                kalman_outputs[ch_name] = kf.update(inputs[ch_name])

            ks = KalmanSnapshot(
                kf_rsi_pred_val=kalman_outputs["rsi"].predicted_value,
                kf_price_filt_vel=kalman_outputs["price"].filtered_velocity,
                kf_price_pred_val=kalman_outputs["price"].predicted_value,
                kf_conj_pred_val=kalman_outputs["conjugation"].predicted_value,
                kf_tension_pred_val=kalman_outputs["tension"].predicted_value,
                kf_conj_filt_vel=kalman_outputs["conjugation"].filtered_velocity,
            )

            feature_dict = {
                "kf_rsi_pred_val": ks.kf_rsi_pred_val,
                "kf_price_filt_vel": ks.kf_price_filt_vel,
                "kf_price_pred_val": ks.kf_price_pred_val,
                "kf_conj_pred_val": ks.kf_conj_pred_val,
                "kf_tension_pred_val": ks.kf_tension_pred_val,
                "kf_conj_filt_vel": ks.kf_conj_filt_vel,
                "rsi_value": rsi_val,
                "sigma_tide": float(row.get("sigma_tide", 0) or 0),
            }

            X_piso = np.array([[feature_dict.get(f, 0.0) for f in piso_features]])
            X_techo = np.array([[feature_dict.get(f, 0.0) for f in techo_features]])
            prob_piso = float(piso_model.predict_proba(X_piso)[0, 1])
            prob_techo = float(techo_model.predict_proba(X_techo)[0, 1])

            tide_slope = float(row.get("tide_slope", 0) or 0)
            turn = compute_turn_signal(prob_piso, prob_techo, ks, tide_slope,
                                       density_history[-DENSITY_HISTORY_LEN:])
            density_history.append(max(prob_piso, prob_techo))

            if turn.archetype != ARCHETYPE_NONE:
                signals.append({
                    "ticker": tk,
                    "timestamp": row["timestamp"],
                    "bar_idx": i,
                    "archetype": turn.archetype,
                    "density": turn.density_level,
                    "prob_piso": prob_piso,
                    "prob_techo": prob_techo,
                    "conviction": turn.conviction,
                    "is_piso_signal": turn.archetype in (ARCHETYPE_HL, ARCHETYPE_LL),
                    "is_techo_signal": turn.archetype in (ARCHETYPE_HH, ARCHETYPE_LH),
                })

        print(f"    {tk}: {len(tk_df):,} bars → {sum(1 for s in signals if s['ticker']==tk)} signals")

    return pd.DataFrame(signals)


def confusion_matrix_analysis(signals_df, zigzag, snapshots_df, zz_pct=5):
    """Compare Sentinel signals against zigzag ground truth."""
    zz_df = zigzag[zz_pct]

    print(f"\n{'='*80}")
    print(f"  CONFUSION MATRIX: Sentinel vs ZigZag {zz_pct}%")
    print(f"  Proximity window: ±{PROXIMITY_BARS} bars")
    print(f"{'='*80}")

    # Apply test split (last 20% per ticker)
    test_signals = []
    test_zz = []
    for tk in TICKERS:
        tk_snaps = snapshots_df[snapshots_df["ticker"] == tk]
        n = len(tk_snaps)
        split_ts = tk_snaps.iloc[int(n * (1 - TEST_SPLIT))]["timestamp"]

        tk_sig = signals_df[(signals_df["ticker"] == tk) & (signals_df["timestamp"] >= split_ts)]
        tk_zz = zz_df[(zz_df["ticker"] == tk) & (zz_df["timestamp"] >= split_ts)]
        test_signals.append(tk_sig)
        test_zz.append(tk_zz)

    test_signals_df = pd.concat(test_signals, ignore_index=True) if test_signals else pd.DataFrame()
    test_zz_df = pd.concat(test_zz, ignore_index=True) if test_zz else pd.DataFrame()

    print(f"\n  Test set: {len(test_signals_df):,} Sentinel signals, {len(test_zz_df):,} zigzag points")
    if test_zz_df.empty or test_signals_df.empty:
        print("  ❌ No data for comparison")
        return

    # ═══════════════════════════════════════════
    # A) For each ZIGZAG point: was it detected?
    # ═══════════════════════════════════════════
    tp_correct = 0       # Zigzag detected, correct direction
    tp_inverted = 0      # Zigzag detected, WRONG direction
    fn_missed = 0        # Zigzag not detected at all
    lead_lags = []       # Signed: negative = Sentinel was early, positive = late

    missed_examples = []
    inverted_examples = []

    for _, zz_row in test_zz_df.iterrows():
        tk = zz_row["ticker"]
        zz_ts = zz_row["timestamp"]
        zz_type = zz_row["tp_type"]  # MIN or MAX

        # Find Sentinel signals within ±PROXIMITY bars for same ticker
        tk_signals = test_signals_df[test_signals_df["ticker"] == tk]
        if tk_signals.empty:
            fn_missed += 1
            missed_examples.append({"ticker": tk, "zz_ts": zz_ts, "zz_type": zz_type})
            continue

        # Compute temporal distance (in days as proxy for bars)
        zz_ts_naive = zz_ts.tz_localize(None) if zz_ts.tzinfo else zz_ts
        sig_ts_naive = tk_signals["timestamp"].dt.tz_localize(None)
        distances = (sig_ts_naive.values - np.datetime64(zz_ts_naive)) / np.timedelta64(1, "D")
        abs_distances = np.abs(distances)

        # Find closest signal within proximity
        within_mask = abs_distances <= PROXIMITY_BARS + 1  # +1 day tolerance
        if not within_mask.any():
            fn_missed += 1
            missed_examples.append({"ticker": tk, "zz_ts": zz_ts, "zz_type": zz_type})
            continue

        closest_idx = abs_distances[within_mask].values.argmin()
        closest_signal = tk_signals[within_mask].iloc[closest_idx]
        lead_lag = float(distances[within_mask].values[closest_idx])

        # Check direction alignment
        if zz_type == "MIN" and closest_signal["is_piso_signal"]:
            tp_correct += 1
            lead_lags.append(lead_lag)
        elif zz_type == "MAX" and closest_signal["is_techo_signal"]:
            tp_correct += 1
            lead_lags.append(lead_lag)
        elif zz_type == "MIN" and closest_signal["is_techo_signal"]:
            tp_inverted += 1
            inverted_examples.append({
                "ticker": tk, "zz_ts": zz_ts, "zz_type": zz_type,
                "signal_arch": closest_signal["archetype"],
                "lead_lag": lead_lag,
            })
        elif zz_type == "MAX" and closest_signal["is_piso_signal"]:
            tp_inverted += 1
            inverted_examples.append({
                "ticker": tk, "zz_ts": zz_ts, "zz_type": zz_type,
                "signal_arch": closest_signal["archetype"],
                "lead_lag": lead_lag,
            })
        else:
            fn_missed += 1

    total_zz = tp_correct + tp_inverted + fn_missed
    recall = tp_correct / total_zz * 100 if total_zz > 0 else 0

    print(f"\n  ── A) ZIGZAG Detection Rate (Recall) ──")
    print(f"    Total zigzag points (test): {total_zz}")
    print(f"    ✅ Correctly detected (TP):  {tp_correct} ({tp_correct/total_zz*100:.1f}%)")
    print(f"    ❌ Missed (FN):              {fn_missed} ({fn_missed/total_zz*100:.1f}%)")
    print(f"    🔄 Inverted (WRONG dir):     {tp_inverted} ({tp_inverted/total_zz*100:.1f}%)")
    print(f"    RECALL = {recall:.1f}%")

    if lead_lags:
        ll_arr = np.array(lead_lags)
        print(f"\n    Lead/Lag analysis (negative=early, positive=late):")
        print(f"      Mean: {ll_arr.mean():+.1f} days")
        print(f"      Median: {np.median(ll_arr):+.1f} days")
        print(f"      Early (Sentinel before ZZ): {(ll_arr < 0).sum()} ({(ll_arr < 0).mean()*100:.0f}%)")
        print(f"      Same day: {(np.abs(ll_arr) < 1).sum()} ({(np.abs(ll_arr) < 1).mean()*100:.0f}%)")
        print(f"      Late (Sentinel after ZZ):  {(ll_arr > 0).sum()} ({(ll_arr > 0).mean()*100:.0f}%)")

    # ═══════════════════════════════════════════
    # B) For each SENTINEL signal: was it real?
    # ═══════════════════════════════════════════
    fp_false_alarm = 0
    tp_signal = 0

    for _, sig_row in test_signals_df.iterrows():
        tk = sig_row["ticker"]
        tk_zz = test_zz_df[test_zz_df["ticker"] == tk]
        if tk_zz.empty:
            fp_false_alarm += 1
            continue

        sig_ts_naive = sig_row["timestamp"].tz_localize(None) if sig_row["timestamp"].tzinfo else sig_row["timestamp"]
        zz_ts_naive = tk_zz["timestamp"].dt.tz_localize(None)
        abs_distances = np.abs((zz_ts_naive.values - np.datetime64(sig_ts_naive)) / np.timedelta64(1, "D"))

        if abs_distances.min() <= PROXIMITY_BARS + 1:
            tp_signal += 1
        else:
            fp_false_alarm += 1

    total_signals = tp_signal + fp_false_alarm
    precision = tp_signal / total_signals * 100 if total_signals > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    print(f"\n  ── B) SENTINEL Precision (False Alarm Rate) ──")
    print(f"    Total Sentinel signals (test): {total_signals}")
    print(f"    ✅ Near a real turn (TP):      {tp_signal} ({tp_signal/total_signals*100:.1f}%)")
    print(f"    ❌ False alarm (FP):            {fp_false_alarm} ({fp_false_alarm/total_signals*100:.1f}%)")
    print(f"    PRECISION = {precision:.1f}%")

    print(f"\n  ── C) COMBINED METRICS ──")
    print(f"    RECALL:    {recall:.1f}% (of zigzag turns detected)")
    print(f"    PRECISION: {precision:.1f}% (of Sentinel signals that were real)")
    print(f"    F1 SCORE:  {f1:.1f}%")
    print(f"    INVERSION: {tp_inverted/total_zz*100:.1f}% (WRONG direction — MOST DANGEROUS)")

    # ═══════════════════════════════════════════
    # D) Per-archetype breakdown
    # ═══════════════════════════════════════════
    print(f"\n  ── D) Per-Archetype Breakdown ──")
    for arch in [ARCHETYPE_HL, ARCHETYPE_LL, ARCHETYPE_HH, ARCHETYPE_LH]:
        arch_signals = test_signals_df[test_signals_df["archetype"] == arch]
        if len(arch_signals) == 0:
            continue

        near_turn = 0
        false_alarm = 0
        for _, sig_row in arch_signals.iterrows():
            tk = sig_row["ticker"]
            tk_zz = test_zz_df[test_zz_df["ticker"] == tk]
            if tk_zz.empty:
                false_alarm += 1
                continue
            sig_ts_naive = sig_row["timestamp"].tz_localize(None) if sig_row["timestamp"].tzinfo else sig_row["timestamp"]
            zz_ts_naive = tk_zz["timestamp"].dt.tz_localize(None)
            abs_dist = np.abs((zz_ts_naive.values - np.datetime64(sig_ts_naive)) / np.timedelta64(1, "D"))
            if abs_dist.min() <= PROXIMITY_BARS + 1:
                near_turn += 1
            else:
                false_alarm += 1

        prec = near_turn / len(arch_signals) * 100 if len(arch_signals) > 0 else 0
        print(f"    {arch}: {len(arch_signals):,} signals | "
              f"near_turn={near_turn} ({prec:.1f}%) | "
              f"false_alarm={false_alarm} ({100-prec:.1f}%)")

    # ═══════════════════════════════════════════
    # E) By zigzag type breakdown
    # ═══════════════════════════════════════════
    print(f"\n  ── E) By Zigzag Type ──")
    for zz_type in ["MIN", "MAX"]:
        type_zz = test_zz_df[test_zz_df["tp_type"] == zz_type]
        detected = 0
        missed = 0
        inverted = 0

        for _, zz_row in type_zz.iterrows():
            tk = zz_row["ticker"]
            zz_ts = zz_row["timestamp"]
            tk_signals = test_signals_df[test_signals_df["ticker"] == tk]
            if tk_signals.empty:
                missed += 1
                continue

            zz_ts_naive = zz_ts.tz_localize(None) if zz_ts.tzinfo else zz_ts
            sig_ts_naive = tk_signals["timestamp"].dt.tz_localize(None)
            abs_dist = np.abs((sig_ts_naive.values - np.datetime64(zz_ts_naive)) / np.timedelta64(1, "D"))

            if abs_dist.min() > PROXIMITY_BARS + 1:
                missed += 1
                continue

            closest_idx = abs_dist.argmin()
            closest = tk_signals.iloc[closest_idx]

            if zz_type == "MIN" and closest["is_piso_signal"]:
                detected += 1
            elif zz_type == "MAX" and closest["is_techo_signal"]:
                detected += 1
            elif (zz_type == "MIN" and closest["is_techo_signal"]) or \
                 (zz_type == "MAX" and closest["is_piso_signal"]):
                inverted += 1
            else:
                missed += 1

        total = detected + missed + inverted
        expected_sentinel = "PISO (LL/HL)" if zz_type == "MIN" else "TECHO (HH/LH)"
        print(f"    ZZ {zz_type} (expects {expected_sentinel}):")
        print(f"      Total: {total} | Detected: {detected} ({detected/max(total,1)*100:.1f}%) | "
              f"Missed: {missed} ({missed/max(total,1)*100:.1f}%) | "
              f"Inverted: {inverted} ({inverted/max(total,1)*100:.1f}%)")

    # ═══════════════════════════════════════════
    # F) Example missed turns (for forensic investigation)
    # ═══════════════════════════════════════════
    if missed_examples:
        print(f"\n  ── F) Sample Missed Turns (first 10) ──")
        for ex in missed_examples[:10]:
            print(f"    {ex['ticker']:>5} | {ex['zz_ts']} | {ex['zz_type']}")

    if inverted_examples:
        print(f"\n  ── G) Sample Inverted Signals (first 10) ── ⚠️ MOST DANGEROUS")
        for ex in inverted_examples[:10]:
            print(f"    {ex['ticker']:>5} | ZZ={ex['zz_type']} but Sentinel={ex['signal_arch']} | "
                  f"lag={ex['lead_lag']:+.1f}d")


def main():
    print("=" * 80)
    print("  SENTINEL vs ZIGZAG — Confusion Matrix Forensics")
    print("  Full pipeline (stateful Kalman) vs ground truth")
    print("=" * 80)

    t0 = time.time()
    store = TimescaleDataStore()

    models = load_models()
    df, all_ohlcv, zigzag = load_data(store)
    store.close()

    signals_df = generate_sentinel_signals(df, models, all_ohlcv)

    print(f"\n  Total Sentinel signals: {len(signals_df):,}")
    for arch in [ARCHETYPE_HL, ARCHETYPE_LL, ARCHETYPE_HH, ARCHETYPE_LH]:
        n = (signals_df["archetype"] == arch).sum()
        print(f"    {arch}: {n:,}")

    # Run confusion matrix for each zigzag scale
    for zz_pct in [3, 5, 7]:
        confusion_matrix_analysis(signals_df, zigzag, df, zz_pct=zz_pct)

    elapsed = time.time() - t0
    print(f"\n{'='*80}")
    print(f"  FORENSICS COMPLETE — {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
