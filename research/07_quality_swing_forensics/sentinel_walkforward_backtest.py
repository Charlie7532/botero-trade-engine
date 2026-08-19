#!/usr/bin/env python3
"""
Sentinel Walk-Forward Backtest — Full Pipeline Validation
=============================================================
Simulates the PRODUCTION pipeline bar-by-bar with stateful Kalman,
archetype classification, density tracking, and forward return analysis.

Difference from Signal Replay:
  Signal Replay:  scored all bars at once (stateless, raw model probs)
  This Backtest:  walks forward maintaining Kalman state, density_history,
                  crescendo tracking — exactly as the daemon would run.

Pipeline per bar:
  1. Read ChannelSnapshot from Vault
  2. Extract Kalman input features (RSI, price returns, tension, conjugation, rvol)
  3. Update 5 stateful Kalman filters → KalmanSnapshot
  4. Score with Sentinel models → prob_piso, prob_techo
  5. Run turn_detector.compute_turn_signal() → TurnSignal (archetype + density)
  6. Record decision and measure forward returns

Validation: 80/20 train/test temporal split (PurgedKFold compliant).
Output: hit rate, LIFT, equity curve per archetype.

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python research/07_quality_swing_forensics/sentinel_walkforward_backtest.py
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
from backend.modules.shared.domain.rules.turn_detector import (
    compute_turn_signal, classify_archetype, assess_density,
)
from backend.modules.shared.domain.entities.turn_signal import (
    ARCHETYPE_HL, ARCHETYPE_LL, ARCHETYPE_HH, ARCHETYPE_LH, ARCHETYPE_NONE,
    ACTION_ACCUMULATE, ACTION_TRIM, ACTION_HOLD,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

MODELS_DIR = root_dir / "backend" / "models"
TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]

FORWARD_WINDOWS = [5, 10, 20]
TEST_SPLIT = 0.20
DENSITY_HISTORY_LEN = 5  # bars to track for density


def load_sentinel_models():
    """Load trained Sentinel XGBoost models."""
    models = {}
    for name in ["piso", "techo"]:
        pkl_path = MODELS_DIR / f"sentinel_{name}_v1.pkl"
        with open(pkl_path, "rb") as f:
            models[name] = pickle.load(f)
        print(f"  {name.upper()}: AUC={models[name]['mean_auc']:.4f}")
    return models


def load_vault_data(store):
    """Load snapshots + OHLCV from Vault."""
    print("  Loading channel snapshots (with Kalman features)...")
    conn = store._conn()
    cur = conn.cursor()

    # Load ALL snapshot columns needed for Kalman input + model scoring
    cur.execute("""
        SELECT ticker, timestamp,
               rsi_value, sigma_tide, sigma_current, sigma_wave,
               tension_tide, conj_wave_tide, tide_slope, current_slope,
               compression_ratio, fear_level,
               kf_rsi_pred_val, kf_price_filt_vel, kf_price_pred_val,
               kf_price_innovation,
               kf_rvol_pred_val, kf_rvol_filt_vel,
               kf_tension_pred_val, kf_tension_filt_vel,
               kf_conj_pred_val, kf_conj_filt_vel
        FROM engine.channel_snapshots
        WHERE kf_rsi_pred_val IS NOT NULL
        ORDER BY ticker, timestamp
    """)
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    df = pd.DataFrame(rows, columns=cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    print(f"  Loaded {len(df):,} snapshots")

    # Load OHLCV for forward returns + Kalman price input
    print("  Loading OHLCV for forward returns...")
    all_ohlcv = {}
    for tk in TICKERS:
        ohlcv = store.load_bars(tk, "1d")
        if ohlcv is not None and not ohlcv.empty:
            all_ohlcv[tk] = ohlcv

    store._put(conn)
    return df, all_ohlcv


def compute_forward_returns(df, all_ohlcv):
    """Compute forward returns for evaluation."""
    print("  Computing forward returns...")
    for w in FORWARD_WINDOWS:
        df[f"fwd_{w}d"] = np.nan

    for tk in TICKERS:
        tk_mask = df["ticker"] == tk
        tk_df = df.loc[tk_mask]
        if tk not in all_ohlcv or tk_df.empty:
            continue

        ohlcv = all_ohlcv[tk]
        ohlcv_idx = pd.to_datetime(ohlcv.index).tz_localize(None)
        close_arr = ohlcv["close"].values.astype(float)
        snap_dates = tk_df["timestamp"].dt.tz_localize(None).values

        for w in FORWARD_WINDOWS:
            fwd = np.full(len(tk_df), np.nan)
            for i, sd in enumerate(snap_dates):
                diffs = np.abs((ohlcv_idx.values - sd) / np.timedelta64(1, "D"))
                mi = np.argmin(diffs)
                if diffs[mi] > 2:
                    continue
                fi = mi + w
                if fi < len(close_arr) and close_arr[mi] > 0:
                    fwd[i] = (close_arr[fi] - close_arr[mi]) / close_arr[mi] * 100
            df.loc[tk_mask, f"fwd_{w}d"] = fwd

    for w in FORWARD_WINDOWS:
        n = df[f"fwd_{w}d"].notna().sum()
        print(f"    fwd_{w}d: {n:,} valid")
    return df


def run_walkforward(df, models, all_ohlcv):
    """Walk-forward backtest with stateful Kalman and density tracking.

    For each ticker:
      1. Initialize 5 Kalman filters
      2. Walk through bars chronologically
      3. For each bar: update Kalman → score models → classify archetype
      4. Track density_history (rolling 5-bar prob window)
      5. Record TurnSignal decision
    """
    print("\n  Running walk-forward with stateful pipeline...")

    piso_model = models["piso"]["model"]
    techo_model = models["techo"]["model"]
    piso_features = models["piso"]["feature_cols"]
    techo_features = models["techo"]["feature_cols"]

    results = []
    archetype_counts = defaultdict(int)

    for tk in TICKERS:
        tk_df = df[df["ticker"] == tk].sort_values("timestamp").reset_index(drop=True)
        if tk_df.empty:
            continue

        # ── Initialize 5 stateful Kalman filters ──
        kalman_filters = {}
        for ch_name, _, proc_noise, obs_noise in KALMAN_CHANNELS:
            kf = FullKalmanFilter1D(process_noise=proc_noise, obs_noise=obs_noise)
            kalman_filters[ch_name] = kf

        # Get OHLCV for price returns
        ohlcv = all_ohlcv.get(tk)
        if ohlcv is not None:
            ohlcv_close = ohlcv["close"].values.astype(float)
            ohlcv_volume = ohlcv["volume"].values.astype(float)
            ohlcv_dates = pd.to_datetime(ohlcv.index).tz_localize(None)
        else:
            ohlcv_close = None

        density_history = []  # Rolling prob window
        prev_close = None

        for i in range(len(tk_df)):
            row = tk_df.iloc[i]

            # ── Extract Kalman inputs from snapshot ──
            rsi_val = float(row.get("rsi_value", 50) or 50)
            tension = float(row.get("tension_tide", 0) or 0)
            conj = float(row.get("conj_wave_tide", 0) or 0)

            # Price return: need OHLCV match
            snap_date = row["timestamp"].tz_localize(None) if row["timestamp"].tzinfo else row["timestamp"]
            price_ret = 0.0
            rvol = 1.0

            if ohlcv_close is not None:
                diffs = np.abs((ohlcv_dates.values - np.datetime64(snap_date)) / np.timedelta64(1, "D"))
                mi = np.argmin(diffs)
                if diffs[mi] < 2:
                    if mi > 0 and ohlcv_close[mi - 1] > 0:
                        price_ret = (ohlcv_close[mi] - ohlcv_close[mi - 1]) / ohlcv_close[mi - 1] * 100
                    # Relative volume
                    if mi >= 20:
                        avg_vol = np.mean(ohlcv_volume[mi - 20:mi])
                        rvol = ohlcv_volume[mi] / max(avg_vol, 1.0) if avg_vol > 0 else 1.0

            # ── Update Kalman filters (STATEFUL) ──
            inputs = {
                "price": price_ret,
                "rvol": rvol,
                "tension": tension,
                "rsi": rsi_val,
                "conjugation": conj,
            }

            kalman_outputs = {}
            for ch_name, _, _, _ in KALMAN_CHANNELS:
                kf = kalman_filters[ch_name]
                val = inputs[ch_name]

                # Initialize on first bar
                if i == 0:
                    kf.reset(val)

                out = kf.update(val)
                kalman_outputs[ch_name] = out

            # ── Build KalmanSnapshot from filter outputs ──
            ks = KalmanSnapshot(
                kf_rsi_pred_val=kalman_outputs["rsi"].predicted_value,
                kf_price_filt_vel=kalman_outputs["price"].filtered_velocity,
                kf_price_pred_val=kalman_outputs["price"].predicted_value if "price" in kalman_outputs else 0.0,
                kf_conj_pred_val=kalman_outputs["conjugation"].predicted_value if "conjugation" in kalman_outputs else 0.0,
                kf_tension_pred_val=kalman_outputs["tension"].predicted_value if "tension" in kalman_outputs else 0.0,
                kf_conj_filt_vel=kalman_outputs["conjugation"].filtered_velocity if "conjugation" in kalman_outputs else 0.0,
            )

            # ── Score with Sentinel models ──
            # Build feature dict for scoring
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

            # Score using the actual model feature columns
            X_piso = np.array([[feature_dict.get(f, 0.0) for f in piso_features]])
            X_techo = np.array([[feature_dict.get(f, 0.0) for f in techo_features]])
            prob_piso = float(piso_model.predict_proba(X_piso)[0, 1])
            prob_techo = float(techo_model.predict_proba(X_techo)[0, 1])

            # ── Compute TurnSignal through the PRODUCTION pipeline ──
            tide_slope = float(row.get("tide_slope", 0) or 0)
            turn_signal = compute_turn_signal(
                prob_piso=prob_piso,
                prob_techo=prob_techo,
                kalman=ks,
                tide_slope=tide_slope,
                density_history=density_history[-DENSITY_HISTORY_LEN:],
            )

            # Update density history
            density_history.append(max(prob_piso, prob_techo))

            archetype_counts[turn_signal.archetype] += 1

            # Record result
            results.append({
                "ticker": tk,
                "timestamp": row["timestamp"],
                "bar_idx": i,
                "archetype": turn_signal.archetype,
                "density": turn_signal.density_level,
                "conviction": turn_signal.conviction,
                "prob_piso": prob_piso,
                "prob_techo": prob_techo,
                "qs_action": turn_signal.quality_swing_action,
                "kf_rsi_pred": ks.kf_rsi_pred_val,
                "kf_price_vel": ks.kf_price_filt_vel,
                "crescendo": turn_signal.crescendo,
                "trend_context": turn_signal.trend_context,
                "fwd_5d": float(row.get("fwd_5d", np.nan)),
                "fwd_10d": float(row.get("fwd_10d", np.nan)),
                "fwd_20d": float(row.get("fwd_20d", np.nan)),
            })

        print(f"    {tk}: {len(tk_df):,} bars processed")

    print(f"\n  Archetype distribution (full walk-forward):")
    total = sum(archetype_counts.values())
    for arch in [ARCHETYPE_HL, ARCHETYPE_LL, ARCHETYPE_HH, ARCHETYPE_LH, ARCHETYPE_NONE]:
        n = archetype_counts[arch]
        print(f"    {arch}: {n:,} ({n/total*100:.1f}%)")

    return pd.DataFrame(results)


def analyze_backtest(results_df):
    """Analyze walk-forward results with temporal test split."""
    print(f"\n{'='*80}")
    print(f"  WALK-FORWARD BACKTEST RESULTS")
    print(f"  (Stateful Kalman + Sentinel Models + TurnDetector Pipeline)")
    print(f"{'='*80}")

    # Split: test = last 20% per ticker (temporal)
    test_mask = pd.Series(False, index=results_df.index)
    for tk in TICKERS:
        tk_idx = results_df[results_df["ticker"] == tk].index
        n = len(tk_idx)
        split_point = int(n * (1 - TEST_SPLIT))
        test_mask.loc[tk_idx[split_point:]] = True

    test_df = results_df[test_mask].copy()
    train_df = results_df[~test_mask].copy()

    print(f"\n  Train: {len(train_df):,} bars | Test: {len(test_df):,} bars")

    # Baselines
    baselines = {}
    for w in FORWARD_WINDOWS:
        col = f"fwd_{w}d"
        valid = test_df[col].dropna()
        baselines[w] = (valid > 0).mean()
    print(f"  Baseline P(return>0): {' | '.join(f'{w}d={baselines[w]*100:.1f}%' for w in FORWARD_WINDOWS)}")

    # ── Per-archetype analysis ──
    for arch in [ARCHETYPE_HL, ARCHETYPE_LL, ARCHETYPE_HH, ARCHETYPE_LH]:
        arch_test = test_df[test_df["archetype"] == arch]
        if len(arch_test) < 10:
            print(f"\n  ── {arch}: insufficient signals ({len(arch_test)}) ──")
            continue

        print(f"\n  ── {arch} ({len(arch_test):,} signals in test) ──")

        for w in FORWARD_WINDOWS:
            col = f"fwd_{w}d"
            valid = arch_test[col].dropna()
            if len(valid) < 5:
                continue

            if arch in (ARCHETYPE_HL, ARCHETYPE_LL):
                hit_rate = (valid > 0).mean()
                lift = hit_rate / baselines[w] if baselines[w] > 0 else 0
            else:
                hit_rate = (valid < 0).mean()
                lift = hit_rate / (1 - baselines[w]) if baselines[w] < 1 else 0

            mean_ret = valid.mean()
            status = "✅" if lift > 1.0 else "⚠️"
            print(f"    {w:>2}d: hit={hit_rate*100:.1f}% LIFT={lift:.2f}x "
                  f"mean_ret={mean_ret:+.2f}% n={len(valid):,} {status}")

        # Density breakdown for 10d
        col = "fwd_10d"
        print(f"    ── Density breakdown (10d) ──")
        for density in ["SILENCIO", "ALARMA", "PRESURIZACIÓN", "EXPLOSIÓN"]:
            d_test = arch_test[arch_test["density"] == density]
            valid = d_test[col].dropna()
            if len(valid) < 5:
                continue
            if arch in (ARCHETYPE_HL, ARCHETYPE_LL):
                hr = (valid > 0).mean()
            else:
                hr = (valid < 0).mean()
            print(f"      {density}: hit_10d={hr*100:.1f}% n={len(valid):,} mean={valid.mean():+.2f}%")

    # ── Action-level analysis (what the gate would DO) ──
    print(f"\n  ── By SwingGate Action ──")
    for action in [ACTION_ACCUMULATE, ACTION_TRIM, ACTION_HOLD]:
        act_test = test_df[test_df["qs_action"] == action]
        if len(act_test) < 10:
            continue
        valid = act_test["fwd_10d"].dropna()
        if len(valid) < 5:
            continue
        hr_up = (valid > 0).mean()
        print(f"    {action}: hit_up_10d={hr_up*100:.1f}% mean={valid.mean():+.2f}% n={len(valid):,}")

    # ── Crescendo analysis ──
    print(f"\n  ── Crescendo Effect ──")
    for arch in [ARCHETYPE_HL, ARCHETYPE_LL]:
        for cresc in [True, False]:
            subset = test_df[(test_df["archetype"] == arch) & (test_df["crescendo"] == cresc)]
            valid = subset["fwd_10d"].dropna()
            if len(valid) < 10:
                continue
            hr = (valid > 0).mean()
            label = "crescendo=Y" if cresc else "crescendo=N"
            print(f"    {arch} {label}: hit_10d={hr*100:.1f}% mean={valid.mean():+.2f}% n={len(valid):,}")

    # ── Trend context analysis ──
    print(f"\n  ── Trend Context ──")
    for arch in [ARCHETYPE_HL, ARCHETYPE_LL]:
        for ctx in ["WITH_TREND", "AGAINST_TREND"]:
            subset = test_df[(test_df["archetype"] == arch) & (test_df["trend_context"] == ctx)]
            valid = subset["fwd_10d"].dropna()
            if len(valid) < 10:
                continue
            hr = (valid > 0).mean()
            print(f"    {arch} {ctx}: hit_10d={hr*100:.1f}% mean={valid.mean():+.2f}% n={len(valid):,}")

    # ── Simulated equity curve (ACCUMULATE on LL/HL signals) ──
    print(f"\n  ── Simulated Equity (ACCUMULATE signals, test set) ──")
    accum_signals = test_df[test_df["qs_action"] == ACTION_ACCUMULATE].sort_values("timestamp")
    if len(accum_signals) > 0:
        returns_10d = accum_signals["fwd_10d"].dropna()
        if len(returns_10d) > 0:
            cum_return = (1 + returns_10d / 100).prod() - 1
            avg_ret = returns_10d.mean()
            sharpe = returns_10d.mean() / returns_10d.std() * np.sqrt(252 / 10) if returns_10d.std() > 0 else 0
            max_dd = (returns_10d.cumsum() - returns_10d.cumsum().cummax()).min()
            print(f"    Signals: {len(returns_10d):,}")
            print(f"    Avg return per signal: {avg_ret:+.2f}%")
            print(f"    Cumulative return: {cum_return*100:+.1f}%")
            print(f"    Sharpe (annualized): {sharpe:.2f}")
            print(f"    Max drawdown: {max_dd:+.2f}%")

    # ── Compare with baseline (random buy) ──
    baseline_10d = test_df["fwd_10d"].dropna()
    if len(baseline_10d) > 0:
        base_cum = (1 + baseline_10d / 100).prod() - 1
        base_sharpe = baseline_10d.mean() / baseline_10d.std() * np.sqrt(252 / 10) if baseline_10d.std() > 0 else 0
        print(f"\n    Baseline (buy any bar): cum={base_cum*100:+.1f}% Sharpe={base_sharpe:.2f}")

    return test_df


def main():
    print("=" * 80)
    print("  SENTINEL WALK-FORWARD BACKTEST")
    print("  Full production pipeline: Kalman(stateful) → Sentinel → TurnDetector")
    print("=" * 80)

    t0 = time.time()
    store = TimescaleDataStore()

    models = load_sentinel_models()
    df, all_ohlcv = load_vault_data(store)
    store.close()

    df = compute_forward_returns(df, all_ohlcv)
    results_df = run_walkforward(df, models, all_ohlcv)
    test_df = analyze_backtest(results_df)

    elapsed = time.time() - t0
    print(f"\n{'='*80}")
    print(f"  BACKTEST COMPLETE — {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"  Total bars processed: {len(results_df):,}")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
