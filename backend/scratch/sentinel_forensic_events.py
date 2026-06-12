#!/usr/bin/env python3
"""
Sentinel Forensic Backtest — Event-Based Detection vs ZigZag Ground Truth
===========================================================================
METHODOLOGY:
  1. Walk-forward bar-by-bar with stateful Kalman (NO zigzag during detection)
  2. Group detections into EVENTS (SILENCIO → active → SILENCIO transitions)
  3. Each event = lifecycle with phases:
     - DETECCIÓN: first bar prob > threshold
     - CONSOLIDACIÓN: prob sustained above threshold
     - EXPLOSIÓN: density reaches EXPLOSIÓN level
     - DESARROLLO: post-peak, prob declining but still active
  4. Post-hoc: compare events vs zigzag 3%/5%/7% ground truth
  5. Confusion matrix: TP, FN (missed), FP (false alarm), INVERTED

An EVENT is NOT a single bar — it's the entire burst of high-probability bars.
This matches reality: the model fires ~6-7 bars around each turn point.

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scratch/sentinel_forensic_events.py
"""
import os
import sys
import time
import pickle
import logging
from pathlib import Path
from dataclasses import dataclass, field
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
from backend.modules.shared.domain.rules.turn_detector import (
    compute_turn_signal, classify_archetype, assess_density,
    PROB_PISO_THRESHOLD, PROB_TECHO_THRESHOLD,
)
from backend.modules.shared.domain.entities.turn_signal import (
    ARCHETYPE_HL, ARCHETYPE_LL, ARCHETYPE_HH, ARCHETYPE_LH, ARCHETYPE_NONE,
    DENSITY_SILENCE, DENSITY_ALARM, DENSITY_PRESSURIZE, DENSITY_EXPLOSION,
)

logging.basicConfig(level=logging.WARNING)

MODELS_DIR = root_dir / "backend" / "models"
TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]

ZZ_THRESHOLDS = [0.03, 0.05, 0.07]
DEDUP_PROXIMITY = 3  # bars — same as training labeling
DENSITY_HISTORY_LEN = 5


# ── Event Data Structure ──────────────────────────────────────

@dataclass
class SentinelEvent:
    """A burst of Sentinel activity — from first detection to silence."""
    ticker: str
    start_idx: int
    end_idx: int = -1
    start_date: object = None
    end_date: object = None
    duration: int = 0

    # Archetype (most frequent during event)
    archetype: str = ARCHETYPE_NONE
    archetype_counts: dict = field(default_factory=dict)

    # Probabilities
    peak_prob_piso: float = 0.0
    peak_prob_techo: float = 0.0
    peak_bar_idx: int = -1
    avg_prob_piso: float = 0.0
    avg_prob_techo: float = 0.0

    # Density lifecycle
    max_density: str = DENSITY_SILENCE
    reached_pressurise: bool = False
    reached_explosion: bool = False

    # Context
    peak_kf_rsi: float = 50.0
    peak_kf_vel: float = 0.0
    tide_direction: str = "FLAT"
    had_crescendo: bool = False

    # Forward returns (measured at peak bar)
    fwd_5d: float = float("nan")
    fwd_10d: float = float("nan")
    fwd_20d: float = float("nan")

    # Forensic match (filled post-hoc)
    matched_zz: str = ""       # "TP_3%", "TP_5%", etc.
    match_distance: int = -1   # bars between peak and nearest zigzag
    zz_type: str = ""          # MIN/MAX
    verdict: str = ""          # TP, FP, FN, INVERTED

    # Signal side
    @property
    def is_piso(self):
        return self.archetype in (ARCHETYPE_HL, ARCHETYPE_LL)

    @property
    def is_techo(self):
        return self.archetype in (ARCHETYPE_HH, ARCHETYPE_LH)


DENSITY_ORDER = {
    DENSITY_SILENCE: 0, DENSITY_ALARM: 1,
    DENSITY_PRESSURIZE: 2, DENSITY_EXPLOSION: 3,
}

# ── Load Models ───────────────────────────────────────────────

def load_sentinel_models():
    """Load trained Sentinel XGBoost models."""
    models = {}
    for name in ["piso", "techo"]:
        pkl_path = MODELS_DIR / f"sentinel_{name}_v1.pkl"
        with open(pkl_path, "rb") as f:
            models[name] = pickle.load(f)
        print(f"    {name.upper()}: AUC={models[name]['mean_auc']:.4f}, "
              f"threshold={models[name]['threshold']:.4f}, "
              f"features={models[name]['feature_cols']}")
    return models


# ── Step 1: Walk-Forward Detection ────────────────────────────

def run_walkforward_detection(df, models, all_ohlcv):
    """Walk forward bar-by-bar, emit SentinelEvents."""
    print("\n" + "=" * 70)
    print("  STEP 1: Walk-Forward Detection (Stateful Kalman + Sentinel)")
    print("=" * 70)

    piso_model = models["piso"]["model"]
    techo_model = models["techo"]["model"]
    piso_features = models["piso"]["feature_cols"]
    techo_features = models["techo"]["feature_cols"]

    all_events = []
    all_bar_data = []  # Store per-bar data for forward returns

    for tk in TICKERS:
        tk_df = df[df["ticker"] == tk].sort_values("timestamp").reset_index(drop=True)
        if tk_df.empty:
            continue

        # Initialize Kalman filters
        kalman_filters = {}
        for ch_name, _, proc_noise, obs_noise in KALMAN_CHANNELS:
            kalman_filters[ch_name] = FullKalmanFilter1D(
                process_noise=proc_noise, obs_noise=obs_noise
            )

        # Get OHLCV
        ohlcv = all_ohlcv.get(tk)
        ohlcv_close = ohlcv["close"].values.astype(float) if ohlcv is not None else None
        ohlcv_volume = ohlcv["volume"].values.astype(float) if ohlcv is not None else None
        ohlcv_dates = pd.to_datetime(ohlcv.index).tz_localize(None) if ohlcv is not None else None

        density_history = []
        current_event = None
        tk_events = []

        for i in range(len(tk_df)):
            row = tk_df.iloc[i]

            # Extract Kalman inputs
            rsi_val = float(row.get("rsi_value", 50) or 50)
            tension = float(row.get("tension_tide", 0) or 0)
            conj = float(row.get("conj_wave_tide", 0) or 0)
            tide_slope = float(row.get("tide_slope", 0) or 0)
            sigma_tide = float(row.get("sigma_tide", 0) or 0)

            # Price return from OHLCV
            price_ret, rvol = 0.0, 1.0
            snap_date = row["timestamp"]
            if hasattr(snap_date, 'tz_localize'):
                snap_date_naive = snap_date.tz_localize(None) if snap_date.tzinfo else snap_date
            else:
                snap_date_naive = pd.Timestamp(snap_date).tz_localize(None)

            ohlcv_match_idx = -1
            if ohlcv_close is not None:
                diffs = np.abs((ohlcv_dates.values - np.datetime64(snap_date_naive))
                               / np.timedelta64(1, "D"))
                mi = np.argmin(diffs)
                if diffs[mi] < 2:
                    ohlcv_match_idx = mi
                    if mi > 0 and ohlcv_close[mi - 1] > 0:
                        price_ret = (ohlcv_close[mi] - ohlcv_close[mi - 1]) / ohlcv_close[mi - 1] * 100
                    if mi >= 20:
                        avg_vol = np.mean(ohlcv_volume[mi - 20:mi])
                        rvol = ohlcv_volume[mi] / max(avg_vol, 1.0) if avg_vol > 0 else 1.0

            # Update Kalman (STATEFUL)
            inputs = {"price": price_ret, "rvol": rvol, "tension": tension,
                      "rsi": rsi_val, "conjugation": conj}
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

            # Score with Sentinel
            feat_dict = {
                "kf_rsi_pred_val": ks.kf_rsi_pred_val,
                "kf_price_filt_vel": ks.kf_price_filt_vel,
                "kf_price_pred_val": ks.kf_price_pred_val,
                "kf_conj_pred_val": ks.kf_conj_pred_val,
                "kf_tension_pred_val": ks.kf_tension_pred_val,
                "kf_conj_filt_vel": ks.kf_conj_filt_vel,
                "rsi_value": rsi_val,
                "sigma_tide": sigma_tide,
            }
            X_piso = np.array([[feat_dict.get(f, 0.0) for f in piso_features]])
            X_techo = np.array([[feat_dict.get(f, 0.0) for f in techo_features]])
            prob_piso = float(piso_model.predict_proba(X_piso)[0, 1])
            prob_techo = float(techo_model.predict_proba(X_techo)[0, 1])

            # TurnSignal through production pipeline
            turn = compute_turn_signal(
                prob_piso=prob_piso, prob_techo=prob_techo,
                kalman=ks, tide_slope=tide_slope,
                density_history=density_history[-DENSITY_HISTORY_LEN:],
            )
            density_history.append(max(prob_piso, prob_techo))

            # Compute forward returns at this bar
            fwd = {5: float("nan"), 10: float("nan"), 20: float("nan")}
            if ohlcv_match_idx >= 0 and ohlcv_close is not None:
                for w in [5, 10, 20]:
                    fi = ohlcv_match_idx + w
                    if fi < len(ohlcv_close) and ohlcv_close[ohlcv_match_idx] > 0:
                        fwd[w] = (ohlcv_close[fi] - ohlcv_close[ohlcv_match_idx]) / \
                                 ohlcv_close[ohlcv_match_idx] * 100

            bar_data = {
                "ticker": tk, "bar_idx": i, "timestamp": row["timestamp"],
                "archetype": turn.archetype, "density": turn.density_level,
                "prob_piso": prob_piso, "prob_techo": prob_techo,
                "kf_rsi": ks.kf_rsi_pred_val, "kf_vel": ks.kf_price_filt_vel,
                "crescendo": turn.crescendo, "tide_slope": tide_slope,
                "fwd_5d": fwd[5], "fwd_10d": fwd[10], "fwd_20d": fwd[20],
            }
            all_bar_data.append(bar_data)

            # ── Event state machine ──
            is_active = turn.archetype != ARCHETYPE_NONE

            if is_active and current_event is None:
                # Start new event
                current_event = SentinelEvent(
                    ticker=tk, start_idx=i,
                    start_date=row["timestamp"],
                )

            if current_event is not None:
                if is_active:
                    # Update event
                    current_event.end_idx = i
                    current_event.end_date = row["timestamp"]
                    current_event.duration = i - current_event.start_idx + 1

                    # Track archetype distribution
                    arch = turn.archetype
                    current_event.archetype_counts[arch] = \
                        current_event.archetype_counts.get(arch, 0) + 1

                    # Track peaks
                    if prob_piso > current_event.peak_prob_piso:
                        current_event.peak_prob_piso = prob_piso
                    if prob_techo > current_event.peak_prob_techo:
                        current_event.peak_prob_techo = prob_techo

                    dom_prob = max(prob_piso, prob_techo)
                    prev_peak = max(current_event.peak_prob_piso, current_event.peak_prob_techo)
                    if dom_prob >= prev_peak - 0.01:
                        current_event.peak_bar_idx = i
                        current_event.peak_kf_rsi = ks.kf_rsi_pred_val
                        current_event.peak_kf_vel = ks.kf_price_filt_vel
                        # Forward returns at peak
                        current_event.fwd_5d = fwd[5]
                        current_event.fwd_10d = fwd[10]
                        current_event.fwd_20d = fwd[20]

                    # Track density lifecycle
                    d_order = DENSITY_ORDER.get(turn.density_level, 0)
                    cur_order = DENSITY_ORDER.get(current_event.max_density, 0)
                    if d_order > cur_order:
                        current_event.max_density = turn.density_level
                    if turn.density_level == DENSITY_PRESSURIZE:
                        current_event.reached_pressurise = True
                    if turn.density_level == DENSITY_EXPLOSION:
                        current_event.reached_explosion = True
                    if turn.crescendo:
                        current_event.had_crescendo = True

                    current_event.tide_direction = "UP" if tide_slope > 0 else "DOWN" if tide_slope < 0 else "FLAT"

                else:
                    # Event ended — finalize
                    # Determine dominant archetype
                    if current_event.archetype_counts:
                        current_event.archetype = max(
                            current_event.archetype_counts,
                            key=current_event.archetype_counts.get
                        )

                    tk_events.append(current_event)
                    current_event = None

        # Close last event if still open
        if current_event is not None and current_event.archetype_counts:
            current_event.archetype = max(
                current_event.archetype_counts,
                key=current_event.archetype_counts.get
            )
            tk_events.append(current_event)

        all_events.extend(tk_events)
        print(f"    {tk}: {len(tk_df):,} bars → {len(tk_events)} events")

    print(f"\n  Total events: {len(all_events)}")
    arch_dist = defaultdict(int)
    for ev in all_events:
        arch_dist[ev.archetype] += 1
    for a in [ARCHETYPE_HL, ARCHETYPE_LL, ARCHETYPE_HH, ARCHETYPE_LH]:
        print(f"    {a}: {arch_dist[a]} events")

    return all_events, pd.DataFrame(all_bar_data)


# ── Step 2: Load ZigZag Ground Truth ─────────────────────────

def load_zigzag_ground_truth(store):
    """Load zigzag turning points for forensic comparison."""
    print("\n" + "=" * 70)
    print("  STEP 2: Load ZigZag Ground Truth")
    print("=" * 70)

    conn = store._conn()
    cur = conn.cursor()

    zz_data = {}
    for threshold in ZZ_THRESHOLDS:
        pct = int(threshold * 100)
        cur.execute("""
            SELECT ticker, timestamp, tp_type
            FROM engine.zigzag_points
            WHERE min_swing_pct = %s
            ORDER BY ticker, timestamp
        """, (threshold,))
        rows = cur.fetchall()
        zz_df = pd.DataFrame(rows, columns=["ticker", "timestamp", "tp_type"])
        zz_df["timestamp"] = pd.to_datetime(zz_df["timestamp"], utc=True)
        zz_data[pct] = zz_df
        print(f"  ZigZag {pct}%: {len(zz_df):,} points ({zz_df['tp_type'].value_counts().to_dict()})")

    store._put(conn)
    return zz_data


# ── Step 3: Match Events vs ZigZag ───────────────────────────

def match_events_vs_zigzag(events, zz_data, snapshot_df):
    """Post-hoc forensic comparison: each event vs nearest zigzag."""
    print("\n" + "=" * 70)
    print("  STEP 3: Forensic Matching — Events vs ZigZag")
    print("=" * 70)

    # Build date lookup per ticker from snapshot_df
    ticker_dates = {}
    for tk in TICKERS:
        tk_snap = snapshot_df[snapshot_df["ticker"] == tk]
        ticker_dates[tk] = tk_snap["timestamp"].dt.tz_localize(None).values

    # For each event, find nearest zigzag across all scales
    matched_events = []
    for ev in events:
        if ev.peak_bar_idx < 0 or ev.ticker not in ticker_dates:
            ev.verdict = "ORPHAN"
            matched_events.append(ev)
            continue

        tk_dates = ticker_dates[ev.ticker]
        if ev.peak_bar_idx >= len(tk_dates):
            ev.verdict = "ORPHAN"
            matched_events.append(ev)
            continue

        event_date = tk_dates[ev.peak_bar_idx]

        best_match = None
        best_distance = 999

        for pct, zz_df in zz_data.items():
            tk_zz = zz_df[zz_df["ticker"] == ev.ticker]
            if tk_zz.empty:
                continue

            zz_dates = tk_zz["timestamp"].dt.tz_localize(None).values
            zz_types = tk_zz["tp_type"].values

            distances = np.abs((zz_dates - event_date) / np.timedelta64(1, "D"))
            min_idx = np.argmin(distances)
            dist_bars = int(distances[min_idx])  # approximate days≈bars

            if dist_bars < best_distance:
                best_distance = dist_bars
                best_match = {
                    "scale": pct,
                    "distance": dist_bars,
                    "zz_type": zz_types[min_idx],
                    "zz_date": zz_dates[min_idx],
                }

        if best_match is None:
            ev.verdict = "ORPHAN"
            matched_events.append(ev)
            continue

        ev.match_distance = best_match["distance"]
        ev.zz_type = best_match["zz_type"]
        ev.matched_zz = f"ZZ_{best_match['scale']}%"

        # Classify: TP, FP, INVERTED
        if best_match["distance"] <= DEDUP_PROXIMITY:
            # Close to a zigzag — check alignment
            if ev.is_piso and best_match["zz_type"] == "MIN":
                ev.verdict = "TP"  # Piso detected near zigzag LOW ✅
            elif ev.is_techo and best_match["zz_type"] == "MAX":
                ev.verdict = "TP"  # Techo detected near zigzag HIGH ✅
            elif ev.is_piso and best_match["zz_type"] == "MAX":
                ev.verdict = "INVERTED"  # Piso detected but it was a HIGH
            elif ev.is_techo and best_match["zz_type"] == "MIN":
                ev.verdict = "INVERTED"  # Techo detected but it was a LOW
            else:
                ev.verdict = "TP_PARTIAL"
        else:
            ev.verdict = "FP"  # No zigzag nearby

        matched_events.append(ev)

    return matched_events


# ── Step 4: Find Missed ZigZags (FN) ─────────────────────────

def find_missed_zigzags(events, zz_data, snapshot_df):
    """Find zigzag points that no event detected."""
    print("\n" + "=" * 70)
    print("  STEP 4: Find Missed ZigZags (FN)")
    print("=" * 70)

    ticker_dates = {}
    for tk in TICKERS:
        tk_snap = snapshot_df[snapshot_df["ticker"] == tk]
        ticker_dates[tk] = tk_snap["timestamp"].dt.tz_localize(None).values

    fn_records = []

    for pct, zz_df in zz_data.items():
        for tk in TICKERS:
            tk_zz = zz_df[zz_df["ticker"] == tk]
            if tk_zz.empty or tk not in ticker_dates:
                continue

            tk_events = [e for e in events if e.ticker == tk]
            tk_dates = ticker_dates[tk]

            for _, zz_row in tk_zz.iterrows():
                zz_date = zz_row["timestamp"].tz_localize(None)

                # Check if any event's peak is within proximity
                matched = False
                for ev in tk_events:
                    if ev.peak_bar_idx >= 0 and ev.peak_bar_idx < len(tk_dates):
                        ev_date = tk_dates[ev.peak_bar_idx]
                        dist = abs((ev_date - np.datetime64(zz_date)) / np.timedelta64(1, "D"))
                        if dist <= DEDUP_PROXIMITY:
                            matched = True
                            break

                if not matched:
                    fn_records.append({
                        "ticker": tk,
                        "zz_date": zz_date,
                        "zz_type": zz_row["tp_type"],
                        "zz_scale": pct,
                    })

    fn_df = pd.DataFrame(fn_records)
    print(f"  Missed zigzags (FN): {len(fn_df):,}")
    if not fn_df.empty:
        for pct in [3, 5, 7]:
            n = len(fn_df[fn_df["zz_scale"] == pct])
            print(f"    ZZ {pct}%: {n} missed")
        for tp in ["MIN", "MAX"]:
            n = len(fn_df[fn_df["zz_type"] == tp])
            print(f"    {tp}: {n} missed")

    return fn_df


# ── Step 5: Full Report ──────────────────────────────────────

def generate_report(events, fn_df):
    """Generate comprehensive forensic report."""
    print("\n" + "=" * 70)
    print("  STEP 5: SENTINEL FORENSIC REPORT")
    print("=" * 70)

    # ── Confusion Matrix ──
    print("\n  ── Confusion Matrix ──")
    verdicts = defaultdict(int)
    for ev in events:
        verdicts[ev.verdict] += 1

    total = len(events)
    tp = verdicts["TP"] + verdicts.get("TP_PARTIAL", 0)
    fp = verdicts["FP"]
    inv = verdicts["INVERTED"]
    orphan = verdicts["ORPHAN"]
    fn = len(fn_df) if not fn_df.empty else 0

    precision = tp / max(tp + fp + inv, 1)
    recall_approx = tp / max(tp + fn, 1)

    print(f"    TP (correct detection):     {tp:>5} ({tp/max(total,1)*100:.1f}%)")
    print(f"    FP (false alarm):           {fp:>5} ({fp/max(total,1)*100:.1f}%)")
    print(f"    INVERTED (wrong direction): {inv:>5} ({inv/max(total,1)*100:.1f}%)")
    print(f"    ORPHAN (no match data):     {orphan:>5}")
    print(f"    FN (missed zigzags):        {fn:>5}")
    print(f"    Precision: {precision*100:.1f}%")
    print(f"    Recall (approx): {recall_approx*100:.1f}%")

    # ── Per-Archetype Breakdown ──
    print("\n  ── Per-Archetype Precision ──")
    for arch in [ARCHETYPE_HL, ARCHETYPE_LL, ARCHETYPE_HH, ARCHETYPE_LH]:
        arch_evts = [e for e in events if e.archetype == arch]
        if not arch_evts:
            continue

        n = len(arch_evts)
        tp_a = sum(1 for e in arch_evts if e.verdict in ("TP", "TP_PARTIAL"))
        fp_a = sum(1 for e in arch_evts if e.verdict == "FP")
        inv_a = sum(1 for e in arch_evts if e.verdict == "INVERTED")
        prec_a = tp_a / max(tp_a + fp_a + inv_a, 1)

        # Forward returns at peak for TP events
        tp_fwd = [e.fwd_10d for e in arch_evts if e.verdict in ("TP", "TP_PARTIAL")
                   and not np.isnan(e.fwd_10d)]

        print(f"\n    {arch}: {n} events | TP={tp_a} FP={fp_a} INV={inv_a} | prec={prec_a*100:.1f}%")

        if tp_fwd:
            tp_arr = np.array(tp_fwd)
            if arch in (ARCHETYPE_HL, ARCHETYPE_LL):
                hit = (tp_arr > 0).mean()
            else:
                hit = (tp_arr < 0).mean()
            print(f"      TP fwd_10d: hit={hit*100:.1f}% mean={tp_arr.mean():+.2f}% n={len(tp_arr)}")

        # Density lifecycle
        n_alarm = sum(1 for e in arch_evts if e.max_density == DENSITY_ALARM)
        n_press = sum(1 for e in arch_evts if e.reached_pressurise)
        n_explode = sum(1 for e in arch_evts if e.reached_explosion)
        n_cresc = sum(1 for e in arch_evts if e.had_crescendo)
        print(f"      Density: ALARMA={n_alarm} PRESURIZACIÓN={n_press} EXPLOSIÓN={n_explode}")
        print(f"      Crescendo: {n_cresc} ({n_cresc/max(n,1)*100:.0f}%)")

        # Duration
        durations = [e.duration for e in arch_evts]
        print(f"      Duration: μ={np.mean(durations):.1f} bars, median={np.median(durations):.0f}")

    # ── FP Analysis (False Alarms) ──
    print("\n  ── FP Analysis (False Alarms) ──")
    fp_events = [e for e in events if e.verdict == "FP"]
    if fp_events:
        fp_archs = defaultdict(int)
        fp_distances = []
        for e in fp_events:
            fp_archs[e.archetype] += 1
            fp_distances.append(e.match_distance)
        print(f"    Total: {len(fp_events)}")
        for a, c in sorted(fp_archs.items(), key=lambda x: -x[1]):
            print(f"      {a}: {c}")
        print(f"    Distance to nearest ZZ: μ={np.mean(fp_distances):.1f} days, "
              f"median={np.median(fp_distances):.0f}")

        # Were the FP actually profitable anyway?
        fp_fwd = [e.fwd_10d for e in fp_events if not np.isnan(e.fwd_10d)]
        if fp_fwd:
            fp_arr = np.array(fp_fwd)
            print(f"    FP fwd_10d: mean={fp_arr.mean():+.2f}% (profitable even without ZZ match?)")

    # ── INVERTED Analysis ──
    print("\n  ── INVERTED Analysis (Wrong Direction) ──")
    inv_events = [e for e in events if e.verdict == "INVERTED"]
    if inv_events:
        for e in inv_events[:10]:  # Show first 10
            print(f"    {e.ticker} {e.start_date}: arch={e.archetype} but ZZ={e.zz_type} "
                  f"(prob_p={e.peak_prob_piso:.2f} prob_t={e.peak_prob_techo:.2f} "
                  f"kf_rsi={e.peak_kf_rsi:.1f})")
        if len(inv_events) > 10:
            print(f"    ... and {len(inv_events) - 10} more")

    # ── Density vs Precision ──
    print("\n  ── Density Level vs Precision ──")
    for density in [DENSITY_ALARM, DENSITY_PRESSURIZE, DENSITY_EXPLOSION]:
        d_evts = [e for e in events if e.max_density == density or
                  (density == DENSITY_PRESSURIZE and e.reached_pressurise) or
                  (density == DENSITY_EXPLOSION and e.reached_explosion)]
        if not d_evts:
            continue
        d_tp = sum(1 for e in d_evts if e.verdict in ("TP", "TP_PARTIAL"))
        d_prec = d_tp / max(len(d_evts), 1)
        print(f"    {density}: {len(d_evts)} events, precision={d_prec*100:.1f}%")

    # ── FN Analysis ──
    if not fn_df.empty:
        print("\n  ── FN Analysis (Missed Turns) ──")
        # Breakdown by scale
        for pct in [3, 5, 7]:
            scale_fn = fn_df[fn_df["zz_scale"] == pct]
            if scale_fn.empty:
                continue
            for tp in ["MIN", "MAX"]:
                n = len(scale_fn[scale_fn["zz_type"] == tp])
                if n > 0:
                    print(f"    ZZ {pct}% {tp}: {n} missed")

        # Sample missed turns
        print(f"\n    Sample missed turns:")
        for _, row in fn_df.head(15).iterrows():
            print(f"      {row['ticker']} {row['zz_date']}: {row['zz_type']} (ZZ {row['zz_scale']}%)")

    # ── Lifecycle Phase Analysis ──
    print("\n  ── Lifecycle Phase Analysis ──")
    print("  Each event progresses through phases based on sustained density:")
    print("    DETECCIÓN:      prob > threshold (1 bar)")
    print("    CONSOLIDACIÓN:  sustained 2-4 bars above threshold")
    print("    PRESURIZACIÓN:  density_count ≥ 5 (rolling)")
    print("    EXPLOSIÓN:      density_count ≥ 8 (rare, high conviction)")
    print()

    # Classify each event by max lifecycle phase reached
    phase_labels = []
    for ev in events:
        if ev.reached_explosion:
            phase = "EXPLOSIÓN"
        elif ev.reached_pressurise:
            phase = "PRESURIZACIÓN"
        elif ev.duration >= 2:
            phase = "CONSOLIDACIÓN"
        else:
            phase = "DETECCIÓN"
        phase_labels.append(phase)

    # Phase × verdict cross-tab
    phase_order = ["DETECCIÓN", "CONSOLIDACIÓN", "PRESURIZACIÓN", "EXPLOSIÓN"]
    print(f"    {'Phase':<18} {'Total':>6} {'TP':>5} {'FP':>5} {'INV':>5} {'Prec':>7} {'μ dur':>6} {'μ fwd10d':>9}")
    print("    " + "─" * 72)

    for phase in phase_order:
        ph_evts = [ev for ev, pl in zip(events, phase_labels) if pl == phase]
        if not ph_evts:
            continue
        n = len(ph_evts)
        tp_n = sum(1 for e in ph_evts if e.verdict in ("TP", "TP_PARTIAL"))
        fp_n = sum(1 for e in ph_evts if e.verdict == "FP")
        inv_n = sum(1 for e in ph_evts if e.verdict == "INVERTED")
        prec = tp_n / max(tp_n + fp_n + inv_n, 1) * 100
        avg_dur = np.mean([e.duration for e in ph_evts])
        fwd_vals = [e.fwd_10d for e in ph_evts if not np.isnan(e.fwd_10d)]
        avg_fwd = np.mean(fwd_vals) if fwd_vals else float("nan")
        fwd_str = f"{avg_fwd:+.2f}%" if not np.isnan(avg_fwd) else "  N/A"

        print(f"    {phase:<18} {n:>6} {tp_n:>5} {fp_n:>5} {inv_n:>5} {prec:>6.1f}% {avg_dur:>5.1f}b {fwd_str:>9}")

    # Phase × archetype detail
    print(f"\n    ── Phase × Archetype Detail ──")
    for arch in [ARCHETYPE_HL, ARCHETYPE_LL, ARCHETYPE_HH, ARCHETYPE_LH]:
        arch_phases = [(ev, pl) for ev, pl in zip(events, phase_labels) if ev.archetype == arch]
        if not arch_phases:
            continue
        print(f"\n    {arch}:")
        for phase in phase_order:
            ph_evts = [ev for ev, pl in arch_phases if pl == phase]
            if not ph_evts:
                continue
            n = len(ph_evts)
            tp_n = sum(1 for e in ph_evts if e.verdict in ("TP", "TP_PARTIAL"))
            prec = tp_n / max(n, 1) * 100

            # Forward returns for this phase+archetype
            fwd_vals = [e.fwd_10d for e in ph_evts if e.verdict in ("TP", "TP_PARTIAL")
                        and not np.isnan(e.fwd_10d)]
            if fwd_vals:
                fwd_arr = np.array(fwd_vals)
                if arch in (ARCHETYPE_HL, ARCHETYPE_LL):
                    hit = (fwd_arr > 0).mean() * 100
                else:
                    hit = (fwd_arr < 0).mean() * 100
                print(f"      {phase:<18} n={n:>4} TP={tp_n:>4} prec={prec:>5.1f}% "
                      f"hit_10d={hit:.0f}% μ_ret={fwd_arr.mean():+.2f}%")
            else:
                print(f"      {phase:<18} n={n:>4} TP={tp_n:>4} prec={prec:>5.1f}%")

    # ── Crescendo + Phase interaction ──
    print(f"\n    ── Crescendo × Phase ──")
    for phase in phase_order:
        cresc_evts = [ev for ev, pl in zip(events, phase_labels)
                      if pl == phase and ev.had_crescendo]
        no_cresc = [ev for ev, pl in zip(events, phase_labels)
                    if pl == phase and not ev.had_crescendo]
        if cresc_evts:
            tp_c = sum(1 for e in cresc_evts if e.verdict in ("TP", "TP_PARTIAL"))
            print(f"      {phase} + crescendo: n={len(cresc_evts):>4} TP={tp_c:>4} "
                  f"prec={tp_c/max(len(cresc_evts),1)*100:.0f}%")
        if no_cresc and len(no_cresc) > 5:
            tp_nc = sum(1 for e in no_cresc if e.verdict in ("TP", "TP_PARTIAL"))
            print(f"      {phase} - crescendo: n={len(no_cresc):>4} TP={tp_nc:>4} "
                  f"prec={tp_nc/max(len(no_cresc),1)*100:.0f}%")

    # ── Summary ──
    print(f"\n{'=' * 70}")
    print(f"  SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Total events detected:     {len(events)}")
    print(f"  Precision (TP / detected): {precision*100:.1f}%")
    print(f"  Recall (TP / real turns):  {recall_approx*100:.1f}%")
    print(f"  F1 Score:                  {2*precision*recall_approx/max(precision+recall_approx, 0.001)*100:.1f}%")

    # Per-archetype summary
    for arch in [ARCHETYPE_HL, ARCHETYPE_LL, ARCHETYPE_HH, ARCHETYPE_LH]:
        arch_evts = [e for e in events if e.archetype == arch]
        if arch_evts:
            tp_a = sum(1 for e in arch_evts if e.verdict in ("TP", "TP_PARTIAL"))
            print(f"  {arch}: {len(arch_evts)} events, {tp_a} TP ({tp_a/len(arch_evts)*100:.0f}%)")


# ── Main ──────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  SENTINEL FORENSIC BACKTEST — Event-Based Detection")
    print("  Full pipeline: Kalman(stateful) → Sentinel → TurnDetector")
    print("  Post-hoc comparison vs ZigZag 3%/5%/7%")
    print("=" * 70)

    t0 = time.time()
    store = TimescaleDataStore()

    # Load models
    print("\n  Loading Sentinel models...")
    models = load_sentinel_models()

    # Load snapshots
    print("  Loading Vault data...")
    conn = store._conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT ticker, timestamp,
               rsi_value, sigma_tide, sigma_current, sigma_wave,
               tension_tide, conj_wave_tide, tide_slope, current_slope,
               compression_ratio, fear_level
        FROM engine.channel_snapshots
        ORDER BY ticker, timestamp
    """)
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    df = pd.DataFrame(rows, columns=cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    store._put(conn)
    print(f"  Loaded {len(df):,} snapshots")

    # Load OHLCV
    print("  Loading OHLCV...")
    all_ohlcv = {}
    for tk in TICKERS:
        ohlcv = store.load_bars(tk, "1d")
        if ohlcv is not None and not ohlcv.empty:
            all_ohlcv[tk] = ohlcv

    # Step 1: Walk-forward detection
    events, bar_df = run_walkforward_detection(df, models, all_ohlcv)

    # Step 2: Load zigzag ground truth
    zz_data = load_zigzag_ground_truth(store)
    store.close()

    # Step 3: Match events vs zigzag
    events = match_events_vs_zigzag(events, zz_data, df)

    # Step 4: Find missed zigzags
    fn_df = find_missed_zigzags(events, zz_data, df)

    # Step 5: Report
    generate_report(events, fn_df)

    # Step 6: Persist to Vault
    persist_events(events, df)
    persist_bar_signals(bar_df)

    elapsed = time.time() - t0
    print(f"\n  Total time: {elapsed:.0f}s ({elapsed/60:.1f}min)")


# ── Step 6: Persist to Vault ─────────────────────────────────

def persist_events(events, snapshot_df):
    """Persist events to engine.sentinel_events."""
    print(f"\n{'=' * 70}")
    print(f"  STEP 6: Persist Events to Vault")
    print(f"{'=' * 70}")

    import json

    def _f(v):
        """Convert numpy types to native Python for psycopg2."""
        if v is None:
            return None
        if isinstance(v, (np.floating, np.float64, np.float32)):
            if np.isnan(v):
                return None
            return float(v)
        if isinstance(v, (np.integer, np.int64, np.int32)):
            return int(v)
        return v

    # Build date lookup
    ticker_dates = {}
    for tk in TICKERS:
        tk_snap = snapshot_df[snapshot_df["ticker"] == tk]
        ticker_dates[tk] = tk_snap["timestamp"].values

    store = TimescaleDataStore()
    conn = store._conn()
    cur = conn.cursor()

    # Clear previous run
    cur.execute("DELETE FROM engine.sentinel_events")
    inserted = 0

    for ev in events:
        tk_dates = ticker_dates.get(ev.ticker)
        peak_date = None
        if tk_dates is not None and 0 <= ev.peak_bar_idx < len(tk_dates):
            peak_date = pd.Timestamp(tk_dates[ev.peak_bar_idx]).to_pydatetime()

        try:
            cur.execute("""
                INSERT INTO engine.sentinel_events (
                    ticker, start_date, end_date, peak_date, duration_bars,
                    archetype, archetype_counts,
                    peak_prob_piso, peak_prob_techo,
                    max_density, reached_pressurise, reached_explosion, had_crescendo,
                    peak_kf_rsi, peak_kf_vel, tide_direction,
                    fwd_5d, fwd_10d, fwd_20d,
                    verdict, matched_zz, match_distance, zz_type
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s
                )
                ON CONFLICT (ticker, start_date) DO UPDATE SET
                    archetype = EXCLUDED.archetype,
                    verdict = EXCLUDED.verdict,
                    peak_prob_piso = EXCLUDED.peak_prob_piso,
                    peak_prob_techo = EXCLUDED.peak_prob_techo
            """, (
                ev.ticker,
                pd.Timestamp(ev.start_date).to_pydatetime() if ev.start_date else None,
                pd.Timestamp(ev.end_date).to_pydatetime() if ev.end_date else None,
                peak_date,
                ev.duration,
                ev.archetype,
                json.dumps(ev.archetype_counts) if ev.archetype_counts else None,
                _f(ev.peak_prob_piso), _f(ev.peak_prob_techo),
                ev.max_density, ev.reached_pressurise, ev.reached_explosion, ev.had_crescendo,
                _f(ev.peak_kf_rsi), _f(ev.peak_kf_vel), ev.tide_direction,
                _f(ev.fwd_5d), _f(ev.fwd_10d), _f(ev.fwd_20d),
                ev.verdict, ev.matched_zz,
                int(ev.match_distance) if ev.match_distance >= 0 else None,
                ev.zz_type or None,
            ))
            inserted += 1
        except Exception as e:
            print(f"    WARN: Failed to insert event {ev.ticker} {ev.start_date}: {e}")
            conn.rollback()

    conn.commit()
    store._put(conn)
    store.close()
    print(f"  Persisted {inserted} events to engine.sentinel_events")


def persist_bar_signals(bar_df):
    """Persist per-bar Kalman signals to engine.sentinel_bar_signals."""
    print(f"\n  Persisting bar-level signals...")

    if bar_df.empty:
        print("    No bar data to persist")
        return

    store = TimescaleDataStore()
    conn = store._conn()
    cur = conn.cursor()

    # Clear previous run
    cur.execute("DELETE FROM engine.sentinel_bar_signals")

    # Only persist bars with active signals (non-NONE archetype)
    active_bars = bar_df[bar_df["archetype"] != ARCHETYPE_NONE]

    batch = []
    for _, row in active_bars.iterrows():
        batch.append((
            row["ticker"],
            pd.Timestamp(row["timestamp"]).to_pydatetime(),
            float(row["prob_piso"]),
            float(row["prob_techo"]),
            row["archetype"],
            row["density"],
            float(row["kf_rsi"]) if not np.isnan(row["kf_rsi"]) else None,
            float(row["kf_vel"]) if not np.isnan(row["kf_vel"]) else None,
            float(row["tide_slope"]) if not np.isnan(row["tide_slope"]) else None,
            bool(row["crescendo"]),
            float(row["fwd_5d"]) if not np.isnan(row["fwd_5d"]) else None,
            float(row["fwd_10d"]) if not np.isnan(row["fwd_10d"]) else None,
            float(row["fwd_20d"]) if not np.isnan(row["fwd_20d"]) else None,
        ))

        if len(batch) >= 1000:
            _insert_bar_batch(cur, batch)
            batch = []

    if batch:
        _insert_bar_batch(cur, batch)

    conn.commit()
    store._put(conn)
    store.close()
    print(f"  Persisted {len(active_bars):,} active bar signals to engine.sentinel_bar_signals")


def _insert_bar_batch(cur, batch):
    """Bulk insert bar signals."""
    from psycopg2.extras import execute_values
    execute_values(cur, """
        INSERT INTO engine.sentinel_bar_signals (
            ticker, timestamp, prob_piso, prob_techo,
            archetype, density, kf_rsi_pred, kf_price_vel,
            tide_slope, crescendo, fwd_5d, fwd_10d, fwd_20d
        ) VALUES %s
        ON CONFLICT (ticker, timestamp) DO UPDATE SET
            prob_piso = EXCLUDED.prob_piso,
            prob_techo = EXCLUDED.prob_techo,
            archetype = EXCLUDED.archetype,
            density = EXCLUDED.density
    """, batch)


if __name__ == "__main__":
    main()
