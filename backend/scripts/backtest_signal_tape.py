#!/usr/bin/env python3
"""
Backtest Signal Tape Generator
================================
For each ticker × each bar (from idx=250 onwards):
  1. Compute ChannelSnapshot (RC + RSI + Kalman) — our production code
  2. Score all 8 heads via HeadScorer
  3. Compute bar-over-bar deltas (precursors)
  4. Compute regression-based barriers (informative)
  5. Compute forward returns (5d, 10d, 20d) + max DD/runup
  6. Compute optimal points (local min/max for phase offset)
  7. Emit baseline decision_a (pure RC rules, no ML)
  8. Emit decision_b (RC + ML modulation)
  9. Persist to engine.signal_tape

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/backtest_signal_tape.py
"""
import os, sys, time, logging, warnings
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
logger = logging.getLogger("signal_tape")

TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]
START_IDX = 250  # Warmup period for all indicators
SLOPE_DECEL_LOOKBACK = 5  # Bars for slope deceleration computation


def _sanitize(val):
    """Convert numpy types to Python native for psycopg2."""
    if val is None:
        return None
    if isinstance(val, (np.floating, np.float64, np.float32)):
        v = float(val)
        if np.isnan(v) or np.isinf(v):
            return None
        return v
    if isinstance(val, (np.integer, np.int64, np.int32)):
        return int(val)
    if isinstance(val, np.bool_):
        return bool(val)
    return val


def sanitize_row(row: dict) -> dict:
    """Sanitize all values in a row dict."""
    return {k: _sanitize(v) for k, v in row.items()}


# ─── Pure RC-based decision (no external dependencies) ──────────────
def baseline_decision(snap):
    """Decision A: pure channel rules, no ML, no external state."""
    sigma = snap.sigma_tide
    fear = snap.fear_level
    slope = snap.tide_slope
    regime = snap.regime

    if regime == "BEAR":
        return "HOLD", 0.0

    # ACCUMULATE: oversold in bull regime
    if sigma < -1.5 and regime == "BULL" and slope > 0:
        conviction = min(abs(sigma) / 3.0, 1.0)
        if fear >= 4:  # Fear/Panic amplifies
            conviction = min(conviction * 1.3, 1.0)
        return "ACCUMULATE", round(conviction, 3)

    # TRIM: overbought
    if sigma > 2.0 and fear <= 1:
        conviction = min((sigma - 2.0) / 2.0, 0.5)
        return "TRIM", round(conviction, 3)

    return "HOLD", 0.0


def ml_modulated_decision(snap, scores):
    """Decision B: RC rules modulated by ML head probabilities."""
    action_a, conv_a = baseline_decision(snap)

    if not scores:
        return action_a, conv_a

    # Get relevant probabilities
    p_long = scores.get("long_entry", None)
    p_exit = scores.get("swing_exit", None)
    p_depth = scores.get("pullback_depth", None)

    if action_a == "ACCUMULATE":
        # ML confirms: high P(long_entry) AND low P(pullback_depth)
        ml_boost = 1.0
        if p_long and p_long.probability > 0.65:
            ml_boost += 0.2
        if p_depth and p_depth.probability < 0.3:
            ml_boost += 0.1
        if p_depth and p_depth.probability > 0.6:
            ml_boost -= 0.3  # Pullback likely deepens, reduce conviction
        return "ACCUMULATE", round(min(conv_a * ml_boost, 1.0), 3)

    elif action_a == "TRIM":
        ml_boost = 1.0
        if p_exit and p_exit.probability > 0.6:
            ml_boost += 0.3  # ML confirms swing top
        return "TRIM", round(min(conv_a * ml_boost, 0.5), 3)

    elif action_a == "HOLD":
        # ML might override to ACCUMULATE if strong signals
        if p_long and p_long.probability > 0.80:
            if snap.sigma_tide < -0.5 and snap.regime == "BULL":
                return "ACCUMULATE", round(p_long.probability * 0.5, 3)

    return action_a, conv_a


# ─── Forward returns computation ────────────────────────────────────
def compute_forward_returns(close, idx):
    """Compute forward returns and optimal points from current bar."""
    n = len(close)
    result = {}

    for horizon in [5, 10, 20]:
        end = min(idx + horizon, n - 1)
        if end <= idx:
            result[f"fwd_return_{horizon}d"] = None
            if horizon <= 10:
                result[f"fwd_max_dd_{horizon}d"] = None
                result[f"fwd_max_runup_{horizon}d"] = None
            continue

        fwd_prices = close[idx + 1 : end + 1]
        if len(fwd_prices) == 0:
            result[f"fwd_return_{horizon}d"] = None
            if horizon <= 10:
                result[f"fwd_max_dd_{horizon}d"] = None
                result[f"fwd_max_runup_{horizon}d"] = None
            continue

        base = close[idx]
        fwd_returns = (fwd_prices - base) / base

        result[f"fwd_return_{horizon}d"] = round(float(fwd_returns[-1]), 6)
        if horizon <= 10:
            result[f"fwd_max_dd_{horizon}d"] = round(float(np.min(fwd_returns)), 6)
            result[f"fwd_max_runup_{horizon}d"] = round(float(np.max(fwd_returns)), 6)

    # Optimal points (10d window)
    end_10 = min(idx + 10, n - 1)
    if end_10 > idx:
        fwd_10 = close[idx + 1 : end_10 + 1]
        base = close[idx]
        fwd_ret = (fwd_10 - base) / base

        min_idx = int(np.argmin(fwd_ret))
        max_idx = int(np.argmax(fwd_ret))

        result["bars_to_local_min_10d"] = min_idx + 1
        result["bars_to_local_max_10d"] = max_idx + 1
        result["local_min_pct"] = round(float(fwd_ret[min_idx]), 6)
        result["local_max_pct"] = round(float(fwd_ret[max_idx]), 6)
    else:
        result["bars_to_local_min_10d"] = None
        result["bars_to_local_max_10d"] = None
        result["local_min_pct"] = None
        result["local_max_pct"] = None

    return result


# ─── Main per-ticker processing ─────────────────────────────────────
def process_ticker(store, scorer, ticker):
    """Generate full signal tape for one ticker."""
    ohlc = store.load_bars(ticker, "1d")
    if ohlc is None or len(ohlc) < START_IDX + 50:
        logger.warning(f"{ticker}: insufficient OHLCV ({len(ohlc) if ohlc is not None else 0})")
        return 0

    close = ohlc["close"].values.astype(float)
    high = ohlc["high"].values.astype(float)
    low = ohlc["low"].values.astype(float)
    volume = ohlc["volume"].values.astype(float)
    timestamps = ohlc.index.tolist()

    # Pre-compute RSI full series
    intel = RSIIntelligence()
    raw_rsi = intel._calc_rsi_series(close, 14)
    rsi_full = np.concatenate(([50.0], raw_rsi))

    # Pre-compute Kalman full series
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

    # Previous bar state for deltas
    prev = {}
    rows = []

    # ── Slope history for deceleration computation ──
    wave_slope_history = []   # Rolling history of wave_slope values
    current_slope_history = []  # Rolling history of current_slope values

    # ── RSI rolling max for bearish divergence (purely historical) ──
    RSI_DIV_WINDOW = 60  # Look at RSI max over last 60 bars
    rsi_history = []  # Rolling RSI values

    for idx in range(START_IDX, len(ohlc)):
        ts = timestamps[idx]

        # 1. Compute snapshot
        snap = compute_channel_snapshot(close, high, low, volume, idx)
        if snap is None:
            continue

        # Inject RSI + Kalman
        snap.rsi_value = round(float(rsi_full[idx]), 2)
        snap.kalman_velocity = round(float(kalman_vel[idx]), 6)
        snap.vol_adj_delta = round(float(kalman_vad[idx]), 6)

        # 2. Score all 8 heads
        scores = scorer.score_all(ticker, snap)

        # 3. Compute deltas
        curr = {
            "sigma_wave": snap.sigma_wave,
            "kalman_velocity": snap.kalman_velocity,
            "rsi_value": snap.rsi_value,
            "compression_ratio": snap.compression_ratio,
            "fear_level": snap.fear_level,
            "vol_up_down_ratio": snap.vol_up_down_ratio,
            "tide_slope": snap.tide_slope,
            "wave_accel": snap.wave_accel,
        }
        deltas = {}
        if prev:
            for k in curr:
                pv = prev.get(k, 0) or 0
                cv = curr[k] or 0
                deltas[f"d_{k}"] = round(float(cv) - float(pv), 6)
        prev = curr.copy()

        # 4. Regression barriers
        exp_return = (snap.tide_slope or 0) * 20  # 20d horizon
        residual = snap.residual_std_tide or 0.01

        # 5. Forward returns
        fwd = compute_forward_returns(close, idx)

        # 6. Decisions
        action_a, conv_a = baseline_decision(snap)
        action_b, conv_b = ml_modulated_decision(snap, scores)

        # ── Phase 1: Derived features (all purely historical) ──

        # Slope deceleration: wave_slope[t] - wave_slope[t-5]
        wave_slope_history.append(snap.wave_slope or 0.0)
        current_slope_history.append(snap.current_slope or 0.0)
        if len(wave_slope_history) > SLOPE_DECEL_LOOKBACK:
            slope_decel_wave = (wave_slope_history[-1]
                                - wave_slope_history[-1 - SLOPE_DECEL_LOOKBACK])
            slope_decel_current = (current_slope_history[-1]
                                   - current_slope_history[-1 - SLOPE_DECEL_LOOKBACK])
        else:
            slope_decel_wave = 0.0
            slope_decel_current = 0.0

        # Sigma divergence: tide vs wave (orthogonal timeframes)
        sigma_divergence = ((snap.sigma_tide or 0.0)
                            - (snap.sigma_wave or 0.0))

        # Complacency index: RSI normalized vs slope decel normalized
        rsi_val = snap.rsi_value or 50.0
        rsi_norm = (rsi_val - 50.0) / 50.0  # [-1, +1]
        sd_norm = max(-1.0, min(1.0, slope_decel_wave * 50.0))  # Normalize
        complacency_index = rsi_norm - sd_norm  # High RSI + flat slope = high

        # RSI zones (U-curve discovery)
        rsi_extreme_zone = 1 if rsi_val > 80.0 else 0
        rsi_trap_zone = 1 if 65.0 <= rsi_val <= 75.0 else 0

        # RSI bearish divergence (rolling max — NO zigzag, purely historical)
        rsi_history.append(rsi_val)
        rsi_bearish_div = 0
        if len(rsi_history) >= RSI_DIV_WINDOW:
            rsi_rolling_max = max(rsi_history[-RSI_DIV_WINDOW:])
            # Current RSI lower than its recent 60-bar max = bearish divergence
            if rsi_val < rsi_rolling_max - 2.0:  # 2-point threshold to avoid noise
                rsi_bearish_div = 1

        # 7. Build row
        row = {
            "timestamp": ts,
            "bar_index": idx,
            # Head probabilities
            "p_long_entry": scores.get("long_entry", None) and scores["long_entry"].probability,
            "p_swing_exit": scores.get("swing_exit", None) and scores["swing_exit"].probability,
            "p_pullback_depth": scores.get("pullback_depth", None) and scores["pullback_depth"].probability,
            "p_trend_reversal": scores.get("trend_reversal", None) and scores["trend_reversal"].probability,
            "p_short_entry": scores.get("short_entry", None) and scores["short_entry"].probability,
            "p_short_cover": scores.get("short_cover", None) and scores["short_cover"].probability,
            "p_bounce_height": scores.get("bounce_height", None) and scores["bounce_height"].probability,
            "p_trend_recovery": scores.get("trend_recovery", None) and scores["trend_recovery"].probability,
            # Core features
            "sigma_tide": snap.sigma_tide,
            "sigma_current": snap.sigma_current,
            "sigma_wave": snap.sigma_wave,
            "tide_slope": snap.tide_slope,
            "current_slope": snap.current_slope,
            "wave_slope": snap.wave_slope,
            "kalman_velocity": snap.kalman_velocity,
            "rsi_value": snap.rsi_value,
            "fear_level": snap.fear_level,
            "compression_ratio": snap.compression_ratio,
            "vol_up_down_ratio": snap.vol_up_down_ratio,
            "regime": snap.regime,
            "vol_regime": None,  # Not available in backtest mode
            # Deltas
            **deltas,
            # Phase 1: Derived features
            "slope_decel_wave": round(float(slope_decel_wave), 6),
            "slope_decel_current": round(float(slope_decel_current), 6),
            "sigma_divergence": round(float(sigma_divergence), 6),
            "complacency_index": round(float(complacency_index), 6),
            "rsi_extreme_zone": rsi_extreme_zone,
            "rsi_trap_zone": rsi_trap_zone,
            "rsi_bearish_div": rsi_bearish_div,
            # Barriers
            "barrier_reg_profit": round(exp_return + 1.5 * residual, 6),
            "barrier_reg_stop": round(exp_return - 1.5 * residual, 6),
            "expected_return": round(exp_return, 6),
            # Forward returns
            **fwd,
            # Decisions
            "decision_a": action_a,
            "conviction_a": conv_a,
            "decision_b": action_b,
            "conviction_b": conv_b,
        }
        rows.append(sanitize_row(row))

    # Persist
    if rows:
        n = store.save_signal_tape_batch(ticker, rows)
        return n
    return 0


def main():
    print("=" * 90)
    print("  BACKTEST SIGNAL TAPE GENERATOR")
    print("  17 tickers × ~4,800 bars × 8 heads = ~1.3M predictions")
    print("  All indicators from production code. No external dependencies.")
    print("=" * 90)

    t0 = time.time()
    store = TimescaleDataStore()
    store.ensure_signal_tape_table()
    scorer = HeadScorer()

    grand_total = 0
    for ticker in TICKERS:
        t1 = time.time()
        n = process_ticker(store, scorer, ticker)
        elapsed = time.time() - t1
        grand_total += n
        print(f"  {'✅' if n > 0 else '⚠️'} {ticker:>5s}: {n:>6,d} rows in {elapsed:.1f}s")

    store.close()
    total_time = time.time() - t0

    print(f"\n{'=' * 90}")
    print(f"  SIGNAL TAPE COMPLETE: {grand_total:,d} rows in {total_time:.1f}s ({total_time/60:.1f} min)")
    print(f"{'=' * 90}")


if __name__ == "__main__":
    main()
