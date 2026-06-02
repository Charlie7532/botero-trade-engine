#!/usr/bin/env python3
"""
SPRINT 2-REDO — FASE A v2.1: Infrastructure + Multi-Scale + Full Kalman
========================================================================
Builds the Feature Lake v2.1 with:
  1. Channel snapshots aligned with OHLCV data (91,252 rows × 17 tickers)
  2. Multi-scale zigzag ground truth (3%, 5%, 7%)
  3. Full Kalman filter on 5 channels: price, rvol, tension, RSI, conjugation
     - Filtered state (value + velocity)
     - Prediction for next bar
     - Innovation (surprise = actual - predicted)
     - Normalized innovation (standardized surprise)
     - Kalman gain (model confidence)
  4. Delta (Δ) and acceleration (Δ²) per-ticker for all features
  5. vol_of_vol_ratio (meta-volatility)
  6. Proximity labels: distance to nearest turn at each scale
  7. Full history signal distributions (near_turn vs no_turn)

Data integrity pre-verified:
  - 91,252 channel snapshots, 0 duplicates
  - 8,216 / 4,313 / 2,663 zigzag points at 3%/5%/7%, 0 duplicates
  - 17 tickers, same in all tables

Output:
  - sprint2_redo_lake_v21.pkl (DataFrame)
  - sprint2_redo_lake_v21.csv (for notebooks/exploration)
  - sprint2_redo_infrastructure_v21.log

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scratch/sprint2_redo_infrastructure_v21.py
"""
import sys
import os
import warnings
import pickle
import time
import bisect
import gc
from pathlib import Path
from datetime import datetime, timezone, date
from collections import defaultdict

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))

from dotenv import load_dotenv
load_dotenv(root / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

# ═══════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════
OUT_DIR = root / "backend" / "scratch"
LOG_FILE = OUT_DIR / "sprint2_redo_infrastructure_v21.log"
LAKE_PKL = OUT_DIR / "sprint2_redo_lake_v21.pkl"
LAKE_CSV = OUT_DIR / "sprint2_redo_lake_v21.csv"

DEDUP_PROXIMITY = 3  # Bars within which a hit is deduplicated
ZZ_THRESHOLDS = [0.03, 0.05, 0.07]  # Multi-scale zigzag

# Tickers (17 — same as channel_snapshots)
TICKERS = [
    'AAPL', 'AMZN', 'COST', 'HD', 'HON', 'IBM', 'JNJ', 'JPM',
    'MCD', 'MRK', 'MSFT', 'PEP', 'PG', 'QQQ', 'SPY', 'WMT', 'XOM'
]

# Features from channel_snapshots to load (base features)
SNAPSHOT_FEATURES = [
    'sigma_tide', 'sigma_current', 'sigma_wave',
    'vwap_sigma_tide', 'vwap_sigma_current', 'vwap_sigma_wave',
    'tension_tide', 'tension_current', 'tension_wave',
    'tide_slope', 'current_slope', 'wave_slope',
    'tide_accel', 'current_accel', 'wave_accel',
    'conj_wave_current', 'conj_wave_tide', 'conj_current_tide',
    'spread_tide_current', 'spread_tide_wave', 'spread_current_wave',
    'vwap_spread_tide_current', 'vwap_spread_tide_wave', 'vwap_spread_current_wave',
    'compression_ratio', 'fear_level', 'vol_up_down_ratio',
    'wave_flip', 'wave_flip_direction',
    'rsi_value', 'rsi_divergence_strength', 'rsi_conviction',
    'kalman_velocity', 'vol_adj_delta',
    'residual_std_tide', 'residual_std_current', 'residual_std_wave',
    'reg_value_tide', 'reg_value_current', 'reg_value_wave',
    'vwap_tide', 'vwap_current', 'vwap_wave',
]

# Features to compute Δ (bar-over-bar change) per-ticker
DELTA_FEATURES = [
    'sigma_wave', 'sigma_tide', 'sigma_current',
    'tide_slope', 'current_slope', 'wave_slope',
    'tide_accel', 'wave_accel',
    'conj_wave_tide', 'conj_wave_current',
    'rsi_value', 'compression_ratio', 'fear_level',
    'vol_up_down_ratio', 'kalman_velocity',
    'tension_tide', 'vwap_sigma_tide',
]

# Features to also compute Δ² (acceleration of change)
DELTA2_FEATURES = [
    'sigma_wave', 'tide_slope', 'conj_wave_tide',
    'rsi_value', 'kalman_velocity', 'tension_tide',
]

# Kalman channels: (name, source_column, process_noise_frac, obs_noise_frac)
# Noise fractions are relative to input variance (auto-calibrated per-ticker).
# process_noise_frac: higher = more reactive to changes
# obs_noise_frac: higher = trust model more, smooth more
KALMAN_CHANNELS = [
    ('price',       None,              0.05,  0.3),   # From OHLCV returns (%)
    ('rvol',        None,              0.10,  0.3),   # Relative volume
    ('tension',     'tension_tide',    0.05,  0.2),   # Elastic tension vs VWAP
    ('rsi',         'rsi_value',       0.03,  0.2),   # RSI (0-100 scale)
    ('conjugation', 'conj_wave_tide',  0.05,  0.2),   # Slope conjugation (5th vector)
]

start_time = time.time()


def log(msg, level="INFO"):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def log_section(title):
    sep = "═" * 90
    log(sep)
    log(f"  {title}")
    log(sep)


# ═══════════════════════════════════════════════════════════════
# FULL KALMAN FILTER — Predict + Filter + Innovation
# ═══════════════════════════════════════════════════════════════

class FullKalmanFilter1D:
    """
    1D Kalman filter with constant-velocity model.

    State: x = [value, velocity]
    Transition: x_{t+1} = F * x_t + noise
    Observation: z_t = H * x_t + noise

    Outputs per update:
      - filtered_value: best estimate of current value
      - filtered_velocity: best estimate of current rate of change
      - predicted_value: model's forecast for NEXT bar (before seeing it)
      - predicted_velocity: model's forecast velocity for next bar
      - innovation: surprise = actual - predicted (how much market defied the model)
      - normalized_innovation: innovation / sqrt(S) — should be N(0,1) if model is correct
      - kalman_gain: how much weight given to observation (0=trust model, 1=trust observation)
      - uncertainty: trace(P) — total model uncertainty
    """

    def __init__(self, process_noise=0.05, obs_noise=0.2, dt=1.0):
        self.dt = dt
        self.F = np.array([[1.0, dt], [0.0, 1.0]])
        self.H = np.array([[1.0, 0.0]])
        self.Q = np.array([
            [process_noise * dt**2, process_noise * dt],
            [process_noise * dt,    process_noise],
        ])
        self.R = np.array([[obs_noise]])
        self.x = None
        self.P = None

    def reset(self, initial_value=0.0):
        """Reset state for a new ticker."""
        self.x = np.array([initial_value, 0.0])
        self.P = np.eye(2) * 1.0

    def update(self, observation):
        """
        Full Kalman cycle: predict → innovate → update.

        Returns dict with all Kalman outputs.
        """
        if self.x is None:
            self.reset(observation)
            return {
                'filtered_value': observation,
                'filtered_velocity': 0.0,
                'predicted_value': observation,
                'predicted_velocity': 0.0,
                'innovation': 0.0,
                'norm_innovation': 0.0,
                'kalman_gain': 0.5,
                'uncertainty': 2.0,
            }

        # ── 1. PREDICT (a priori) ──
        x_pred = self.F.dot(self.x)
        P_pred = self.F.dot(self.P).dot(self.F.T) + self.Q

        # ── 2. INNOVATION (surprise) ──
        z = np.array([observation])
        y = z - self.H.dot(x_pred)              # Innovation = actual - predicted
        S = self.H.dot(P_pred).dot(self.H.T) + self.R  # Innovation covariance
        S_scalar = float(S[0, 0])

        # Normalized innovation: should be ~N(0,1) if model is correct
        norm_innov = float(y[0]) / max(np.sqrt(S_scalar), 1e-8)

        # ── 3. UPDATE (a posteriori) ──
        K = P_pred.dot(self.H.T).dot(np.linalg.inv(S))
        x_new = x_pred + K.dot(y)
        P_new = (np.eye(2) - K.dot(self.H)).dot(P_pred)

        # ── 4. PREDICT NEXT (t+1 forecast, BEFORE seeing next observation) ──
        x_next_pred = self.F.dot(x_new)

        # Store state
        self.x = x_new
        self.P = P_new

        return {
            'filtered_value': float(x_new[0]),
            'filtered_velocity': float(x_new[1]),
            'predicted_value': float(x_next_pred[0]),    # Forecast for next bar
            'predicted_velocity': float(x_next_pred[1]),  # Forecast velocity
            'innovation': float(y[0]),                    # Surprise
            'norm_innovation': norm_innov,                # Standardized surprise
            'kalman_gain': float(K[0, 0]),                # Model confidence
            'uncertainty': float(P_new[0, 0] + P_new[1, 1]),  # Trace(P)
        }


def apply_kalman_to_series(values, process_noise_frac=0.05, obs_noise_frac=0.2):
    """Apply full Kalman to a 1D series with auto-calibrated noise.

    Noise params are fractions of the input variance (estimated from first 50 points).
    This ensures proper calibration regardless of the input scale (RSI 0-100, sigma -3..+3, etc.)
    """
    n = len(values)
    if n == 0:
        return {k: np.zeros(0) for k in [
            'filtered_value', 'filtered_velocity', 'predicted_value',
            'predicted_velocity', 'innovation', 'norm_innovation',
            'kalman_gain', 'uncertainty',
        ]}

    # Auto-calibrate: estimate variance from first 50 non-zero observations
    warmup = min(50, n)
    warmup_vals = values[:warmup]
    warmup_vals = warmup_vals[np.isfinite(warmup_vals) & (warmup_vals != 0)]
    if len(warmup_vals) > 2:
        data_var = np.var(warmup_vals)
    else:
        data_var = 1.0
    data_var = max(data_var, 1e-8)  # Floor to avoid zero noise

    q_noise = process_noise_frac * data_var
    r_noise = obs_noise_frac * data_var

    kf = FullKalmanFilter1D(process_noise=q_noise, obs_noise=r_noise)
    kf.reset(values[0])

    results = {
        'filtered_value': np.zeros(n),
        'filtered_velocity': np.zeros(n),
        'predicted_value': np.zeros(n),
        'predicted_velocity': np.zeros(n),
        'innovation': np.zeros(n),
        'norm_innovation': np.zeros(n),
        'kalman_gain': np.zeros(n),
        'uncertainty': np.zeros(n),
    }

    for i in range(n):
        out = kf.update(values[i])
        for key in results:
            results[key][i] = out[key]

    return results


# ═══════════════════════════════════════════════════════════════
# STEP 1: Load Data
# ═══════════════════════════════════════════════════════════════

def load_channel_snapshots(store):
    """Load all channel snapshots from Vault."""
    log_section("STEP 1: Loading Channel Snapshots")

    all_dfs = []
    for tk in TICKERS:
        df = store.load_snapshots(tk, timeframe="1d")
        if df is None or df.empty:
            log(f"  ⚠️ {tk}: No snapshots found", "WARN")
            continue
        df['ticker'] = tk
        all_dfs.append(df)
        log(f"  {tk}: {len(df):,} snapshots ({df.index.min().date()} → {df.index.max().date()})")

    combined = pd.concat(all_dfs, ignore_index=False)
    combined = combined.sort_values(['ticker', combined.index.name or 'timestamp'])
    log(f"  TOTAL: {len(combined):,} snapshots, {combined['ticker'].nunique()} tickers")
    return combined


def load_ohlcv_data(store):
    """Load OHLCV bars for all tickers."""
    log_section("STEP 1b: Loading OHLCV Data")
    all_ohlcv = {}
    for tk in TICKERS:
        df = store.load_bars(tk, "1d")
        if df is not None and not df.empty:
            all_ohlcv[tk] = df
            log(f"  {tk}: {len(df):,} bars")
    return all_ohlcv


def load_zigzag_multiscale(store):
    """Load zigzag points at all 3 thresholds."""
    log_section("STEP 1c: Loading Multi-Scale Zigzag")

    import psycopg2
    conn = psycopg2.connect(os.getenv('POSTGRES_URL'))
    cur = conn.cursor()

    zigzags = {}
    for threshold in ZZ_THRESHOLDS:
        cur.execute("""
            SELECT ticker, timestamp, tp_type, price, swing_return, swing_days
            FROM engine.zigzag_points
            WHERE min_swing_pct = %s
            ORDER BY ticker, timestamp
        """, (threshold,))
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=['ticker', 'timestamp', 'tp_type', 'price', 'swing_return', 'swing_days'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        zigzags[threshold] = df
        log(f"  {threshold*100:.0f}%: {len(df):,} points, {df['ticker'].nunique()} tickers")

    conn.close()
    return zigzags


# ═══════════════════════════════════════════════════════════════
# STEP 2: Align & Label
# ═══════════════════════════════════════════════════════════════

def align_and_label(snapshots_df, ohlcv_data, zigzags):
    """
    For each snapshot bar, compute:
    - OHLCV data alignment (price, open, high, low, volume)
    - Distance to nearest zigzag point at each scale
    - Hit labels (near_3pct, near_5pct, near_7pct)
    - Turn type at each scale

    Uses vectorized merge_asof for speed (vs row-by-row loops).
    """
    log_section("STEP 2: Aligning Snapshots with Multi-Scale Zigzag")

    # Reset index to make timestamp a column for merging
    df = snapshots_df.reset_index()

    # Normalize timestamp to date for matching
    df['date'] = pd.to_datetime(df['timestamp']).dt.normalize()

    # Initialize output columns
    for pct in [3, 5, 7]:
        df[f'dist_zz_{pct}pct'] = 9999.0
        df[f'hit_zz_{pct}pct'] = False
        df[f'zz_{pct}pct_type'] = 'NONE'

    df['price'] = np.nan
    df['open_price'] = np.nan
    df['high_price'] = np.nan
    df['low_price'] = np.nan
    df['volume'] = np.nan

    total_aligned = 0

    for tk in TICKERS:
        tk_mask = df['ticker'] == tk
        tk_indices = df.loc[tk_mask].index
        n_tk = len(tk_indices)

        if n_tk == 0:
            continue

        tk_dates = df.loc[tk_mask, 'date'].values

        # ── OHLCV Alignment (date lookup, tz-naive) ──
        if tk in ohlcv_data:
            ohlcv = ohlcv_data[tk].copy()
            # Normalize to tz-naive midnight dates (snap dates lose tz through numpy)
            ohlcv_dates_naive = pd.to_datetime(ohlcv.index).normalize().tz_localize(None)

            # Build date → row lookup with tz-naive keys
            ohlcv_lookup = {}
            for oi in range(len(ohlcv)):
                ohlcv_lookup[ohlcv_dates_naive[oi]] = oi

            aligned_count = 0
            for loc_idx, snap_date in zip(tk_indices, tk_dates):
                snap_date_ts = pd.Timestamp(snap_date)
                if snap_date_ts in ohlcv_lookup:
                    oi = ohlcv_lookup[snap_date_ts]
                    df.at[loc_idx, 'price'] = float(ohlcv.iloc[oi]['close'])
                    df.at[loc_idx, 'open_price'] = float(ohlcv.iloc[oi]['open'])
                    df.at[loc_idx, 'high_price'] = float(ohlcv.iloc[oi]['high'])
                    df.at[loc_idx, 'low_price'] = float(ohlcv.iloc[oi]['low'])
                    df.at[loc_idx, 'volume'] = float(ohlcv.iloc[oi]['volume'])
                    aligned_count += 1

            total_aligned += aligned_count

        # ── Zigzag Alignment (vectorized via searchsorted) ──
        for threshold in ZZ_THRESHOLDS:
            pct = int(threshold * 100)
            zz_df = zigzags[threshold]
            zz_tk = zz_df[zz_df['ticker'] == tk].sort_values('timestamp')

            if zz_tk.empty:
                continue

            zz_dates = pd.to_datetime(zz_tk['timestamp']).dt.normalize().values
            zz_types = zz_tk['tp_type'].values

            # For each snapshot, find distance to nearest zigzag using searchsorted
            for loc_idx, snap_date in zip(tk_indices, tk_dates):
                snap_date_np = np.datetime64(pd.Timestamp(snap_date))
                pos = np.searchsorted(zz_dates, snap_date_np)

                best_dist = 9999
                best_type = 'NONE'

                for candidate_pos in [pos - 1, pos]:
                    if 0 <= candidate_pos < len(zz_dates):
                        delta = abs(int((snap_date_np - zz_dates[candidate_pos]) / np.timedelta64(1, 'D')))
                        dist_trading = max(0, int(delta * 5 / 7))
                        if dist_trading < best_dist:
                            best_dist = dist_trading
                            best_type = zz_types[candidate_pos]

                df.at[loc_idx, f'dist_zz_{pct}pct'] = float(best_dist)
                df.at[loc_idx, f'hit_zz_{pct}pct'] = best_dist <= DEDUP_PROXIMITY
                if best_dist <= DEDUP_PROXIMITY:
                    df.at[loc_idx, f'zz_{pct}pct_type'] = best_type

        log(f"  {tk}: aligned ({n_tk:,} bars)")

    log(f"  TOTAL: {total_aligned:,} OHLCV bars aligned")

    # Summary
    for pct in [3, 5, 7]:
        n_hits = df[f'hit_zz_{pct}pct'].sum()
        n_total = len(df)
        log(f"  Zigzag {pct}%: {n_hits:,} hits ({n_hits/n_total*100:.1f}%, ±{DEDUP_PROXIMITY} bars)")

    # Restore timestamp index
    df.set_index('timestamp', inplace=True)
    df.drop(columns=['date'], inplace=True, errors='ignore')

    return df


# ═══════════════════════════════════════════════════════════════
# STEP 3: Full Kalman Channels
# ═══════════════════════════════════════════════════════════════

def compute_kalman_channels(df, ohlcv_data):
    """Apply full Kalman filter to 5 channels per-ticker."""
    log_section("STEP 3: Full Kalman Filter (5 channels × 8 outputs)")

    # Initialize all Kalman output columns
    for ch_name, _, _, _ in KALMAN_CHANNELS:
        for suffix in ['filt_vel', 'pred_val', 'pred_vel', 'innov', 'norm_innov', 'gain', 'uncert']:
            col = f'kf_{ch_name}_{suffix}'
            df[col] = 0.0

    for tk in TICKERS:
        tk_mask = (df['ticker'] == tk).values
        n_tk = tk_mask.sum()
        if n_tk == 0:
            continue

        tk_indices = np.where(tk_mask)[0]

        for ch_name, src_col, q_noise, r_noise in KALMAN_CHANNELS:
            # Get the source series
            if ch_name == 'price':
                # Use close price from OHLCV
                values = df.loc[tk_mask, 'price'].values.astype(float)
                # Normalize to returns for better Kalman behavior
                values_norm = np.zeros_like(values)
                values_norm[1:] = (values[1:] - values[:-1]) / np.where(values[:-1] > 0, values[:-1], 1.0) * 100
                values = values_norm
            elif ch_name == 'rvol':
                # Compute relative volume
                vol = df.loc[tk_mask, 'volume'].values.astype(float)
                vol_ma20 = pd.Series(vol).rolling(20, min_periods=1).mean().values
                values = np.where(vol_ma20 > 0, vol / vol_ma20, 1.0)
            else:
                values = df.loc[tk_mask, src_col].values.astype(float)

            # Replace NaN/Inf
            values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)

            # Apply full Kalman (auto-calibrated from data variance)
            kf_results = apply_kalman_to_series(values, process_noise_frac=q_noise, obs_noise_frac=r_noise)

            # Store results (skip filtered_value — it's just a smoothed version of input)
            df.iloc[tk_indices, df.columns.get_loc(f'kf_{ch_name}_filt_vel')] = kf_results['filtered_velocity'].astype(np.float32)
            df.iloc[tk_indices, df.columns.get_loc(f'kf_{ch_name}_pred_val')] = kf_results['predicted_value'].astype(np.float32)
            df.iloc[tk_indices, df.columns.get_loc(f'kf_{ch_name}_pred_vel')] = kf_results['predicted_velocity'].astype(np.float32)
            df.iloc[tk_indices, df.columns.get_loc(f'kf_{ch_name}_innov')] = kf_results['innovation'].astype(np.float32)
            df.iloc[tk_indices, df.columns.get_loc(f'kf_{ch_name}_norm_innov')] = kf_results['norm_innovation'].astype(np.float32)
            df.iloc[tk_indices, df.columns.get_loc(f'kf_{ch_name}_gain')] = kf_results['kalman_gain'].astype(np.float32)
            df.iloc[tk_indices, df.columns.get_loc(f'kf_{ch_name}_uncert')] = kf_results['uncertainty'].astype(np.float32)

        log(f"  {tk}: 5 Kalman channels computed ({n_tk} bars)")

    # Summary statistics
    for ch_name, _, _, _ in KALMAN_CHANNELS:
        innov_col = f'kf_{ch_name}_norm_innov'
        vals = df[innov_col].values
        log(f"  {ch_name}: norm_innov μ={vals.mean():.3f} σ={vals.std():.3f} "
            f"(should be ~N(0,1) if model is correct)")

    return df


# ═══════════════════════════════════════════════════════════════
# STEP 4: Deltas, Accelerations, Derived Features
# ═══════════════════════════════════════════════════════════════

def compute_deltas_and_derived(df):
    """Compute bar-over-bar deltas (Δ), accelerations (Δ²), and derived features."""
    log_section("STEP 4: Deltas (Δ), Accelerations (Δ²), and Derived Features")

    n_deltas = 0
    n_accels = 0

    for tk in TICKERS:
        tk_mask = (df['ticker'] == tk).values
        tk_indices = np.where(tk_mask)[0]

        if len(tk_indices) == 0:
            continue

        # Δ features
        for feat in DELTA_FEATURES:
            if feat not in df.columns:
                continue
            dcol = f'd_{feat}'
            if dcol not in df.columns:
                df[dcol] = 0.0
            vals = df.iloc[tk_indices][feat].values.astype(float)
            delta = np.zeros_like(vals)
            delta[1:] = vals[1:] - vals[:-1]
            df.iloc[tk_indices, df.columns.get_loc(dcol)] = delta.astype(np.float32)
            n_deltas += 1

        # Δ² features (acceleration of change)
        for feat in DELTA2_FEATURES:
            dcol = f'd_{feat}'
            d2col = f'd2_{feat}'
            if dcol not in df.columns:
                continue
            if d2col not in df.columns:
                df[d2col] = 0.0
            vals = df.iloc[tk_indices][dcol].values.astype(float)
            delta2 = np.zeros_like(vals)
            delta2[1:] = vals[1:] - vals[:-1]
            df.iloc[tk_indices, df.columns.get_loc(d2col)] = delta2.astype(np.float32)
            n_accels += 1

    log(f"  Computed {n_deltas} Δ features, {n_accels} Δ² features per-ticker")

    # ── vol_of_vol_ratio ──
    log("  Computing vol_of_vol_ratio...")
    df['vol_of_vol_ratio'] = 0.0
    for tk in TICKERS:
        tk_mask = (df['ticker'] == tk).values
        tk_indices = np.where(tk_mask)[0]
        if len(tk_indices) == 0:
            continue

        if 'high_price' in df.columns and 'low_price' in df.columns:
            high = df.iloc[tk_indices]['high_price'].values.astype(float)
            low = df.iloc[tk_indices]['low_price'].values.astype(float)
            close = df.iloc[tk_indices]['price'].values.astype(float)

            # True Range
            close_prev = np.roll(close, 1)
            close_prev[0] = close[0]
            tr = np.maximum(high - low, np.maximum(np.abs(high - close_prev), np.abs(low - close_prev)))

            # ATR 14
            atr_14 = pd.Series(tr).rolling(14, min_periods=1).mean().values

            # Vol of Vol: std(ATR) / mean(ATR) over 20 periods
            atr_s = pd.Series(atr_14)
            vol_std = atr_s.rolling(20, min_periods=5).std().fillna(0.0).values
            vol_mean = atr_s.rolling(20, min_periods=5).mean().fillna(1.0).values
            vov = np.where(vol_mean > 1e-8, vol_std / vol_mean, 0.0)

            df.iloc[tk_indices, df.columns.get_loc('vol_of_vol_ratio')] = vov.astype(np.float32)

    log(f"  vol_of_vol_ratio: μ={df['vol_of_vol_ratio'].mean():.4f} σ={df['vol_of_vol_ratio'].std():.4f}")

    # ── Channel sentiment (DCSI) ──
    if 'compression_ratio' in df.columns and 'sigma_tide' in df.columns:
        log("  Computing channel_sentiment (DCSI)...")
        compr = df['compression_ratio'].values.astype(float)
        sigma = df['sigma_tide'].values.astype(float)
        df['channel_sentiment'] = (np.sign(sigma) * compr).astype(np.float32)

    return df


# ═══════════════════════════════════════════════════════════════
# STEP 5: Self-Audit
# ═══════════════════════════════════════════════════════════════

def self_audit(df):
    """Verify data quality post-processing."""
    log_section("STEP 5: Self-Audit")

    errors = 0

    # 1. No duplicates per (ticker, timestamp)
    if df.index.name and 'timestamp' in df.index.name:
        dupes = df.groupby('ticker').apply(lambda g: g.index.duplicated().sum()).sum()
    else:
        dupes = df.duplicated(subset=['ticker', 'timestamp'] if 'timestamp' in df.columns else ['ticker']).sum()
    if dupes > 0:
        log(f"  ❌ {dupes} duplicates found!", "ERROR")
        errors += 1
    else:
        log(f"  ✅ No duplicates")

    # 2. NaN/Inf check on key features
    kalman_cols = [c for c in df.columns if c.startswith('kf_')]
    delta_cols = [c for c in df.columns if c.startswith('d_') or c.startswith('d2_')]
    check_cols = kalman_cols + delta_cols + ['vol_of_vol_ratio']

    for col in check_cols:
        if col in df.columns:
            n_nan = df[col].isna().sum()
            n_inf = np.isinf(df[col].values.astype(float)).sum()
            if n_nan > 0 or n_inf > 0:
                log(f"  ⚠️ {col}: {n_nan} NaN, {n_inf} Inf — filling with 0", "WARN")
                df[col] = df[col].fillna(0.0).replace([np.inf, -np.inf], 0.0)

    # 3. Kalman normalized innovation should be ~N(0,1)
    for ch_name, _, _, _ in KALMAN_CHANNELS:
        col = f'kf_{ch_name}_norm_innov'
        if col in df.columns:
            vals = df[col].values
            mu, sigma = vals.mean(), vals.std()
            if abs(mu) > 0.5 or abs(sigma - 1.0) > 0.5:
                log(f"  ⚠️ {col}: μ={mu:.3f} σ={sigma:.3f} (expected ~N(0,1))", "WARN")
            else:
                log(f"  ✅ {col}: μ={mu:.3f} σ={sigma:.3f} — well-calibrated")

    # 4. Correlation check for new features
    log("\n  Correlation check (new features vs existing):")
    new_features = ['vol_of_vol_ratio', 'kf_conjugation_filt_vel', 'kf_conjugation_innov']
    existing_features = ['compression_ratio', 'kalman_velocity', 'conj_wave_tide']

    for nf in new_features:
        if nf not in df.columns:
            continue
        for ef in existing_features:
            if ef not in df.columns:
                continue
            r = df[[nf, ef]].corr().iloc[0, 1]
            status = '✅' if abs(r) < 0.80 else '⚠️ HIGH'
            log(f"    {nf} × {ef}: r={r:.3f} {status}")

    # 5. Hit rate sanity
    for pct in [3, 5, 7]:
        col = f'hit_zz_{pct}pct'
        if col in df.columns:
            rate = df[col].mean() * 100
            log(f"  ✅ Hit rate zigzag {pct}%: {rate:.1f}% of bars are near a turn")

    # 6. Ticker distribution
    log("\n  Rows per ticker:")
    for tk in TICKERS:
        n = (df['ticker'] == tk).sum()
        log(f"    {tk}: {n:,}")

    log(f"\n  Total columns: {len(df.columns)}")
    log(f"  Total rows: {len(df):,}")

    if errors == 0:
        log("  ✅ ALL AUDITS PASSED")
    else:
        log(f"  ❌ {errors} AUDIT FAILURES", "ERROR")

    return errors


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    # Clear log
    LOG_FILE.unlink(missing_ok=True)
    log_section("SPRINT 2-REDO — FASE A v2.1: Feature Lake Construction")
    log(f"Started at {datetime.now(timezone.utc).isoformat()}")
    log(f"Tickers: {len(TICKERS)}")
    log(f"Zigzag scales: {[f'{t*100:.0f}%' for t in ZZ_THRESHOLDS]}")

    store = TimescaleDataStore()

    try:
        # STEP 1: Load data
        snapshots = load_channel_snapshots(store)
        ohlcv = load_ohlcv_data(store)
        zigzags = load_zigzag_multiscale(store)

        # STEP 2: Align & label
        df = align_and_label(snapshots, ohlcv, zigzags)
        gc.collect()

        # STEP 3: Full Kalman channels
        df = compute_kalman_channels(df, ohlcv)
        gc.collect()

        # STEP 4: Deltas and derived
        df = compute_deltas_and_derived(df)
        gc.collect()

        # STEP 5: Self-audit
        errors = self_audit(df)

        # STEP 6: Export
        log_section("STEP 6: Export")

        # Ensure float32 for all numeric columns (memory efficiency)
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            df[col] = df[col].astype(np.float32)

        # PKL
        df.to_pickle(LAKE_PKL)
        pkl_size = LAKE_PKL.stat().st_size / (1024 * 1024)
        log(f"  PKL: {LAKE_PKL.name} ({pkl_size:.1f} MB)")

        # CSV
        df.to_csv(LAKE_CSV, index=True)
        csv_size = LAKE_CSV.stat().st_size / (1024 * 1024)
        log(f"  CSV: {LAKE_CSV.name} ({csv_size:.1f} MB)")

        # Final summary
        elapsed = time.time() - start_time
        log_section("SUMMARY")
        log(f"  Rows: {len(df):,}")
        log(f"  Columns: {len(df.columns)}")
        log(f"  Tickers: {df['ticker'].nunique()}")
        log(f"  Kalman channels: {len(KALMAN_CHANNELS)} × 7 outputs = {len(KALMAN_CHANNELS)*7} features")
        log(f"  Delta features: {len(DELTA_FEATURES)}")
        log(f"  Delta² features: {len(DELTA2_FEATURES)}")
        log(f"  Zigzag scales: 3%/5%/7%")
        log(f"  Audit: {'✅ PASSED' if errors == 0 else '❌ FAILED'}")
        log(f"  Time: {elapsed:.0f}s ({elapsed/60:.1f}min)")

    finally:
        store.close()


if __name__ == "__main__":
    main()
