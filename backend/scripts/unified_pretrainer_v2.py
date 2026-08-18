#!/usr/bin/env python3
"""
Multi-Head Pre-Trainer v2 — 8 Signal Models, Let the Data Decide
====================================================================
Trains 8 independent XGBoost models, each answering a DIFFERENT question
about the same Feature Lake data. Inspired by Simons: "Don't pick one
hypothesis. Train all 8 and let the data tell you which works."

LONG-side heads:
  1. LONG_ENTRY:      "Is this a good time to buy?"
     → 20d forward return > 0 (proven in v1: WR 76.4%)
  2. SWING_EXIT:      "Is this the top of a bullish leg?"
     → Triple Barrier: hits -2% stop before +3% profit in 10d
  3. PULLBACK_DEPTH:  "Will this pullback go deeper?"
     → Max drawdown in 5d > -2%
  4. TREND_REVERSAL:  "Is the macro trend changing?"
     → TSI_tide drops from >50 to <30 within 60d

SHORT-side heads (symmetric mirrors):
  5. SHORT_ENTRY:     "Is this a good time to short?"
     → 20d forward return < 0 (BEAR regime only)
  6. SHORT_COVER:     "Is this the bottom of a bearish leg?"
     → Triple Barrier inverted: hits +2% bounce before -3% drop in 10d
  7. BOUNCE_HEIGHT:   "Will this bounce go higher?"
     → Max runup in 5d > +2% (BEAR bounce context)
  8. TREND_RECOVERY:  "Is the bearish trend ending?"
     → TSI_tide rises from <30 to >60 within 60d

Each head has its own:
  - Context filter (which observations it trains on)
  - Labeling strategy (what "win" means)
  - Forward horizon (5d to 60d)
  - Purged CV gap (= horizon)

Outputs per head:
  - Model pickle
  - Feature importance
  - Optimal threshold
  - Per-ticker stability

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/unified_pretrainer_v2.py
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/unified_pretrainer_v2.py --heads long_entry,swing_exit
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/unified_pretrainer_v2.py --dry-run
"""
import os, sys, warnings, json, pickle, time, argparse
from pathlib import Path
warnings.filterwarnings("ignore")

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import pandas as pd
import numpy as np
from collections import Counter

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore
from backend.modules.shared.domain.rules.trend_strength import compute_tsi, compute_adi

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)

def p(t): print(f"\n{'='*95}\n  {t}\n{'='*95}")
def sp(t): print(f"\n  ── {t} ──")

TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]

# ═══════════════════════════════════════════════════════════════
# FEATURE DEFINITIONS (same as v1 — 49 features)
# ═══════════════════════════════════════════════════════════════

DB_FEATURES = [
    'sigma_tide', 'sigma_current', 'sigma_wave',
    'vwap_sigma_tide', 'vwap_sigma_current', 'vwap_sigma_wave',
    'tension_tide', 'tension_current', 'tension_wave',
    'tide_slope', 'current_slope', 'wave_slope',
    'tide_accel', 'current_accel', 'wave_accel',
    'conj_wave_current', 'conj_wave_tide', 'conj_current_tide',
    'spread_tide_current', 'spread_tide_wave', 'spread_current_wave',
    'vwap_spread_tide_current', 'vwap_spread_tide_wave', 'vwap_spread_current_wave',
    'compression_ratio',
    'fear_level', 'vol_up_down_ratio',
    'wave_flip', 'wave_flip_direction',
    'rsi_value', 'rsi_divergence_strength', 'rsi_conviction',
    'kalman_velocity', 'vol_adj_delta',
    'geo_state_norm', 'geo_velocity_align', 'geo_exit_align',
    'geo_accel_align', 'geo_phase_angle',
    'residual_std_tide', 'residual_std_current', 'residual_std_wave',
    'reg_value_tide', 'reg_value_current', 'reg_value_wave',
    'vwap_tide', 'vwap_current', 'vwap_wave',
]

COMPUTED_FEATURES = [
    'tsi_tide', 'tsi_current', 'tsi_wave',
    'adi_tide', 'adi_current', 'adi_wave',
    'below_all_vwaps_int', 'above_all_vwaps_int',
    'regime_encoded',
]

# Phase 1 derived features (from forensic analysis)
PHASE1_FEATURES = [
    'slope_decel_wave', 'slope_decel_current',
    'sigma_divergence', 'complacency_index',
    'rsi_extreme_zone', 'rsi_trap_zone', 'rsi_bearish_div',
]

# Delta features: bar-over-bar changes of key indicators
# Forensic evidence: d_tide_slope is the strongest precursor (t=-80.96)
DELTA_SOURCES = [
    'sigma_wave', 'kalman_velocity', 'rsi_value', 'compression_ratio',
    'fear_level', 'vol_up_down_ratio', 'tide_slope', 'wave_accel',
]
# Candle structure delta sources (Wyckoff close position, HIGH/LOW divergence)
CANDLE_DELTA_SOURCES = [
    'close_position', 'div_high_close_tide', 'div_close_low_tide',
]
DELTA_FEATURES = [f'd_{col}' for col in DELTA_SOURCES + CANDLE_DELTA_SOURCES]

ALL_FEATURES = DB_FEATURES + COMPUTED_FEATURES + PHASE1_FEATURES + DELTA_FEATURES

# ═══════════════════════════════════════════════════════════════
# OPTIMIZED FEATURE SETS — Challenger v2 Results
# ═══════════════════════════════════════════════════════════════
# Each head uses its own optimized set (selected by greedy forward selection
# + Purged Walk-Forward CV + Deflated Sharpe Ratio).
# Heads set to None fall back to ALL_FEATURES (pending Challenger v3).

OPTIMIZED_FEATURES = {
    # ── GAINS (promoted from Challenger v2) ──
    'long_entry': [  # 6f, DSR: 0.593 → 3.849 (+549%)
        'sigma_high_tide', 'tsi_current', 'reg_value_tide',
        'div_close_low_tide', 'conj_wave_current', 'vol_price_divergence',
    ],
    'pullback_depth': [  # 3f, DSR: 6.226 → 48.578 (+680%)
        'atr_ratio', 'volume_trend', 'sigma_ratio_tw',
    ],
    'bounce_height': [  # 9f, DSR: 2.308 → 19.732 (+755%)
        'atr_ratio', 'above_all_vwaps_int', 'vol_slope_conf',
        'reg_value_wave', 'overnight_gap', 'kalman_slope_conf',
        'overnight_gap_vs_tide', 'close_position', 'conj_wave_current',
    ],
    'trend_reversal': [  # 2f, DSR: 11.573 → 18.492 (+60%)
        'vwap_sigma_high_tide', 'tide_slope_sq',
    ],
    'trend_recovery': [  # 13f, DSR: 4.626 → 7.407 (+60%)
        'vwap_spread_tide_wave', 'd_tide_slope', 'vwap_sigma_low_tide',
        'vwap_sigma_high_current', 'tension_ratio_tw', 'residual_std_current',
        'overnight_gap_vs_tide', 'div_high_close_tide', 'div_close_low_current',
        'vol_up_down_ratio', 'd_compression_ratio', 'volume_trend',
        'rsi_bearish_div',
    ],
    'zz_bottom_detector': [  # 6f, DSR: 20.967 → 32.218 (+54%)
        'rsi_value', 'complacency_index', 'atr_ratio',
        'volume_trend', 'tension_tide', 'sigma_range_tide',
    ],
    'short_entry': [  # 5f, DSR: 1.705 → 1.816 (+7%)
        'compression_ratio', 'fear_level', 'volume_trend',
        'conj_wave_current', 'vol_adj_delta',
    ],
    # ── Challenger v3: optimized from expanded lake (77f) ──
    'swing_exit': [  # 11f, DSR: 12.877 → 13.865 (+7.7%)
        'atr_ratio', 'vwap_spread_tide_wave', 'rsi_value', 'overnight_gap',
        'complacency_index', 'compression_ratio', 'compr_at_extreme',
        'rsi_conviction', 'slope_ratio_tw', 'd_fear_level', 'current_accel',
    ],
    'short_cover': [  # 7f, DSR: 3.888 → 5.132 (+32%)
        'vwap_sigma_wave', 'div_high_close_wave', 'vol_price_regime',
        'sigma_wave', 'slope_diff_tc', 'vwap_sigma_tide', 'd2_current_slope',
    ],
    'zz_top_detector': [  # 12f, DSR: 11.104 → 10.198 (-8%, but 12f vs 72f)
        'atr_ratio', 'sigma_high_current', 'overnight_gap', 'vol_return_interaction',
        'wave_accel', 'rsi_value', 'vol_adj_delta', 'compr_at_extreme',
        'vol_up_down_ratio', 'adi_tide', 'tide_slope_sq', 'volume_trend',
    ],
}


# ═══════════════════════════════════════════════════════════════
# HEAD DEFINITIONS
# ═══════════════════════════════════════════════════════════════

HEAD_CONFIGS = {
    # ── LONG-side ──
    'long_entry': {
        'description': 'Is this a good time to buy? (20d forward return > 0)',
        'horizon': 20,  # Tested 12d (median×0.75): DSR dropped 0.84→0.69. 20d kept.
        'context_desc': 'All observations (no filter)',
        'side': 'LONG',
        # exclude_deltas tested: DSR -1.17 without vs 0.69 with. Deltas help.
    },
    'swing_exit': {
        'description': 'Is this the top of a bullish leg? (Triple Barrier 10d)',
        'horizon': 10,
        'context_desc': 'BULL regime AND sigma_tide > 0 (winning positions)',
        'barriers': {'profit': 0.03, 'stop': -0.02, 'time': 10},
        'side': 'LONG',
    },
    'pullback_depth': {
        'description': 'Will this pullback deepen? (Max drawdown 5d > -2%)',
        'horizon': 5,
        'context_desc': 'BULL regime AND sigma_tide < -0.5 (in pullback)',
        'side': 'LONG',
    },
    'trend_reversal': {
        'description': 'Is the macro trend changing? (TSI drops >50 → <30 in 60d)',
        'horizon': 60,
        'context_desc': 'tsi_tide > 50 (established uptrend)',
        'side': 'LONG',
    },
    # ── SHORT-side (symmetric mirrors) ──
    'short_entry': {
        'description': 'Is this a good time to short? (20d forward return < 0)',
        'horizon': 20,
        'context_desc': 'BEAR or FLAT regime (no strong uptrend)',
        'side': 'SHORT',
    },
    'short_cover': {
        'description': 'Is this the bottom of a bearish leg? (Triple Barrier inverted 10d)',
        'horizon': 10,
        'context_desc': 'BEAR regime AND sigma_tide < 0 (in drawdown)',
        'barriers': {'profit': -0.03, 'stop': 0.02, 'time': 10},
        'side': 'SHORT',
    },
    'bounce_height': {
        'description': 'Will this bounce go higher? (Max runup 5d > +2%)',
        'horizon': 5,
        'context_desc': 'BEAR regime AND sigma_tide > 0.5 (counter-trend bounce)',
        'side': 'SHORT',
    },
    'trend_recovery': {
        'description': 'Is the bearish trend ending? (TSI rises <30 → >60 in 60d)',
        'horizon': 60,
        'context_desc': 'tsi_tide < 30 (established downtrend)',
        'side': 'SHORT',
    },
    # ── ZIGZAG TURNING-POINT DETECTORS (Phase 2) ──
    'zz_bottom_detector': {
        'description': 'Are we near a zigzag 5% bottom? (within 3 bars of MIN)',
        'horizon': 3,  # proximity window, not forward-return horizon
        'context_desc': 'All observations (no filter)',
        'side': 'LONG',
        'label_type': 'zigzag',
        'zz_tp_type': 'MIN',
        'proximity_window': 3,  # bars before/after the turning point
    },
    'zz_top_detector': {
        'description': 'Are we near a zigzag 5% top? (within 3 bars of MAX)',
        'horizon': 3,
        'context_desc': 'All observations (no filter)',
        'side': 'SHORT',
        'label_type': 'zigzag',
        'zz_tp_type': 'MAX',
        'proximity_window': 3,
    },
}


# ═══════════════════════════════════════════════════════════════
# STEP 1: Load Full Feature Lake + Enrich
# ═══════════════════════════════════════════════════════════════

def load_feature_lake(store, profile_store):
    """Load ALL channel_snapshots, enrich with TSI/ADI, cache OHLCV."""
    sp("STEP 0: Loading Feature Lake")

    db_cols = ", ".join([f"cs.{c}" for c in DB_FEATURES if c != 'wave_flip'])
    query = f"""
        SELECT cs.ticker, cs.timestamp,
               {db_cols},
               cs.wave_flip,
               cs.below_all_vwaps, cs.above_all_vwaps,
               cs.regime,
               ob.open as open_price,
               ob.high as high_price,
               ob.low as low_price,
               ob.close as price,
               ob.volume as volume
        FROM engine.channel_snapshots cs
        JOIN market.ohlcv_bars ob
            ON ob.ticker = cs.ticker AND ob.timeframe = '1d' AND ob.time = cs.timestamp
        WHERE cs.sigma_tide IS NOT NULL
          AND cs.tide_slope IS NOT NULL
        ORDER BY cs.ticker, cs.timestamp
    """
    df = pd.read_sql(query, store.engine)
    print(f"    Raw observations: {len(df):,d}")

    # Convert types
    df['wave_flip'] = df['wave_flip'].astype(int)
    df['below_all_vwaps_int'] = df['below_all_vwaps'].astype(int)
    df['above_all_vwaps_int'] = df['above_all_vwaps'].astype(int)
    regime_map = {'BEAR': 0, 'FLAT': 1, 'BULL': 2}
    df['regime_encoded'] = df['regime'].map(regime_map).fillna(1).astype(int)

    # Compute TSI/ADI per-ticker
    profiles = {p.ticker: p for p in profile_store.load_all_profiles()}
    print(f"    Loaded {len(profiles)} ticker profiles")

    for col in ['tsi_tide', 'tsi_current', 'tsi_wave',
                'adi_tide', 'adi_current', 'adi_wave']:
        df[col] = 50

    for ticker in df['ticker'].unique():
        profile = profiles.get(ticker)
        if profile is None:
            continue
        mask = df['ticker'] == ticker
        tdf = df.loc[mask]

        df.loc[mask, 'tsi_tide'] = tdf['tide_slope'].apply(
            lambda s: compute_tsi(s, profile.tsi_tide_percentiles))
        df.loc[mask, 'tsi_current'] = tdf['current_slope'].apply(
            lambda s: compute_tsi(s, profile.tsi_current_percentiles))
        df.loc[mask, 'tsi_wave'] = tdf['wave_slope'].apply(
            lambda s: compute_tsi(s, profile.tsi_wave_percentiles))
        df.loc[mask, 'adi_tide'] = tdf['tension_tide'].apply(
            lambda t: compute_adi(t, profile.adi_tide_percentiles))
        df.loc[mask, 'adi_current'] = tdf['tension_current'].apply(
            lambda t: compute_adi(t, profile.adi_current_percentiles))
        df.loc[mask, 'adi_wave'] = tdf['tension_wave'].apply(
            lambda t: compute_adi(t, profile.adi_wave_percentiles))

    # Compute delta features: bar-over-bar changes per ticker
    # Forensic: d_tide_slope (t=-80.96) is the strongest precursor across all heads
    for src in DELTA_SOURCES:
        df[f'd_{src}'] = df.groupby('ticker')[src].diff().fillna(0.0)
    print(f"    Delta features computed: {len(DELTA_FEATURES)} columns")

    # ── Phase 1: Derived features (forensic-based, all purely historical) ──
    SLOPE_DECEL_LOOKBACK = 5
    # Slope deceleration per ticker
    df['slope_decel_wave'] = (df.groupby('ticker')['wave_slope']
                              .diff(SLOPE_DECEL_LOOKBACK).fillna(0.0))
    df['slope_decel_current'] = (df.groupby('ticker')['current_slope']
                                 .diff(SLOPE_DECEL_LOOKBACK).fillna(0.0))
    # Sigma divergence (orthogonal timeframes)
    df['sigma_divergence'] = df['sigma_tide'].fillna(0) - df['sigma_wave'].fillna(0)
    # Complacency index: RSI normalized vs slope decel normalized
    rsi_norm = (df['rsi_value'].fillna(50) - 50.0) / 50.0
    sd_norm = (df['slope_decel_wave'] * 50.0).clip(-1, 1)
    df['complacency_index'] = rsi_norm - sd_norm
    # RSI zones (U-curve discovery)
    df['rsi_extreme_zone'] = (df['rsi_value'].fillna(50) > 80).astype(int)
    df['rsi_trap_zone'] = ((df['rsi_value'].fillna(50) >= 65) &
                           (df['rsi_value'].fillna(50) <= 75)).astype(int)
    # RSI bearish divergence: rolling max (NO zigzag — purely historical)
    RSI_DIV_WINDOW = 60
    rsi_series = df['rsi_value'].fillna(50)
    rsi_rolling_max = rsi_series.groupby(df['ticker']).transform(
        lambda s: s.rolling(RSI_DIV_WINDOW, min_periods=1).max()
    )
    # Current RSI < rolling max by 2+ points = bearish divergence
    df['rsi_bearish_div'] = ((rsi_series < rsi_rolling_max - 2.0)).astype(int)
    print(f"    Phase 1 features computed: {len(PHASE1_FEATURES)} columns")

    # Pre-load OHLCV per-ticker for labeling
    ohlcv_cache = {}
    for ticker in df['ticker'].unique():
        ohlc = store.load_bars(ticker, "1d")
        if ohlc is not None and not ohlc.empty:
            ohlcv_cache[ticker] = ohlc
    print(f"    OHLCV cache: {len(ohlcv_cache)} tickers")

    return df, ohlcv_cache, profiles


# ═══════════════════════════════════════════════════════════════
# LABELING FUNCTIONS (one per head)
# ═══════════════════════════════════════════════════════════════


def label_zz_turning_point(df, store, tp_type='MIN', proximity_window=3):
    """Label bars near confirmed zigzag turning points.

    CRITICAL: Zigzag is used ONLY as a LABEL — the training TARGET.
    It is NEVER used as an input feature. The model learns to predict
    proximity to turning points from the 63 channel-snapshot features.

    Args:
        tp_type: 'MIN' (bottoms) or 'MAX' (tops)
        proximity_window: bars before/after the actual turning point

    Returns:
        labels: 1 = within proximity_window of a zigzag turning point, 0 = not
    """
    label_name = 'ZZ_BOTTOM' if tp_type == 'MIN' else 'ZZ_TOP'
    sp(f"Labeling: {label_name} (proximity={proximity_window} bars, tp={tp_type})")

    # Load confirmed zigzag points
    from sqlalchemy import text
    zz = pd.read_sql(
        text("SELECT ticker, timestamp FROM engine.zigzag_points "
             "WHERE min_swing_pct = 0.05 AND tp_type = :tp "
             "ORDER BY ticker, timestamp"),
        store.engine, params={'tp': tp_type}
    )
    print(f"    Loaded {len(zz):,d} zigzag {tp_type} points")

    labels = np.zeros(len(df))

    for ticker in df['ticker'].unique():
        tk_zz = zz[zz['ticker'] == ticker]['timestamp'].values
        if len(tk_zz) == 0:
            continue

        mask = df['ticker'] == ticker
        tk_df = df.loc[mask]
        tk_timestamps = tk_df['timestamp'].values

        for zz_ts in tk_zz:
            # Find bars within proximity_window of this turning point
            time_diffs = np.abs(
                (tk_timestamps - np.datetime64(zz_ts)).astype('timedelta64[D]').astype(int)
            )
            nearby = time_diffs <= proximity_window
            if nearby.any():
                # Map back to df indices
                nearby_indices = tk_df.index[nearby]
                for idx in nearby_indices:
                    labels[df.index.get_loc(idx)] = 1

    n_pos = int(labels.sum())
    pct = n_pos / max(len(labels), 1) * 100
    print(f"    Labeled: {len(labels):,d} total | Positive: {n_pos:,d} ({pct:.1f}%)")
    return labels


def label_long_entry(df, ohlcv_cache, horizon=20):
    """Label 1: price goes UP in `horizon` days."""
    sp(f"Labeling: LONG_ENTRY (horizon={horizon}d)")
    labels = np.full(len(df), np.nan)

    for ticker in df['ticker'].unique():
        ohlc = ohlcv_cache.get(ticker)
        if ohlc is None:
            continue
        closes = ohlc['close']
        mask = df['ticker'] == ticker
        idx_list = df.index[mask]

        for idx in idx_list:
            ts = df.at[idx, 'timestamp']
            if ts in ohlc.index:
                pos = ohlc.index.get_loc(ts)
                if pos + horizon < len(ohlc):
                    future_price = closes.iloc[pos + horizon]
                    current_price = df.at[idx, 'price']
                    labels[df.index.get_loc(idx)] = 1 if future_price > current_price else 0

    n_valid = (~np.isnan(labels)).sum()
    n_win = (labels == 1).sum()
    print(f"    Labeled: {n_valid:,d} / {len(df):,d} | Base WR: {n_win/max(n_valid,1)*100:.1f}%")
    return labels


def label_swing_exit(df, ohlcv_cache, profit=0.03, stop=-0.02, time_limit=10):
    """Label 1: price hits STOP before PROFIT within time_limit days (Triple Barrier).

    If stop is hit first → label=1 (should have exited = good exit signal)
    If profit is hit first → label=0 (should NOT have exited = bad exit signal)
    If neither within time → label=0 (nothing happened = no need to exit)
    """
    sp(f"Labeling: SWING_EXIT (Triple Barrier: profit={profit:+.1%}, stop={stop:+.1%}, time={time_limit}d)")
    labels = np.full(len(df), np.nan)

    for ticker in df['ticker'].unique():
        ohlc = ohlcv_cache.get(ticker)
        if ohlc is None:
            continue
        closes = ohlc['close']
        mask = df['ticker'] == ticker
        idx_list = df.index[mask]

        for idx in idx_list:
            ts = df.at[idx, 'timestamp']
            if ts not in ohlc.index:
                continue
            pos = ohlc.index.get_loc(ts)
            entry_price = df.at[idx, 'price']
            if pos + time_limit >= len(ohlc):
                continue

            label = 0  # Default: no barrier hit → no exit needed
            for j in range(1, time_limit + 1):
                ret = (closes.iloc[pos + j] / entry_price) - 1
                if ret <= stop:
                    label = 1  # Stop hit → SHOULD have exited
                    break
                if ret >= profit:
                    label = 0  # Profit hit → should NOT have exited
                    break

            labels[df.index.get_loc(idx)] = label

    n_valid = (~np.isnan(labels)).sum()
    n_exit = (labels == 1).sum()
    print(f"    Labeled: {n_valid:,d} / {len(df):,d} | Exit rate: {n_exit/max(n_valid,1)*100:.1f}%")
    return labels


def label_pullback_depth(df, ohlcv_cache, depth_threshold=-0.02, horizon=5):
    """Label 1: max drawdown in next `horizon` days exceeds threshold.

    Answers: "Will this pullback go deeper? Should I wait to re-enter?"
    """
    sp(f"Labeling: PULLBACK_DEPTH (threshold={depth_threshold:+.1%}, horizon={horizon}d)")
    labels = np.full(len(df), np.nan)

    for ticker in df['ticker'].unique():
        ohlc = ohlcv_cache.get(ticker)
        if ohlc is None:
            continue
        closes = ohlc['close']
        mask = df['ticker'] == ticker
        idx_list = df.index[mask]

        for idx in idx_list:
            ts = df.at[idx, 'timestamp']
            if ts not in ohlc.index:
                continue
            pos = ohlc.index.get_loc(ts)
            entry_price = df.at[idx, 'price']
            end_pos = min(pos + horizon + 1, len(ohlc))
            if pos + 1 >= end_pos:
                continue

            future_closes = closes.iloc[pos + 1:end_pos]
            min_price = future_closes.min()
            max_drawdown = (min_price / entry_price) - 1

            labels[df.index.get_loc(idx)] = 1 if max_drawdown < depth_threshold else 0

    n_valid = (~np.isnan(labels)).sum()
    n_deep = (labels == 1).sum()
    print(f"    Labeled: {n_valid:,d} / {len(df):,d} | Deep pullback rate: {n_deep/max(n_valid,1)*100:.1f}%")
    return labels


def label_trend_reversal(df, ohlcv_cache, profiles, horizon=60, tsi_drop_to=30):
    """Label 1: TSI_tide drops from current >50 to <tsi_drop_to within horizon days.

    Answers: "Is the macro trend about to reverse?"
    Uses future tide_slope from OHLCV + TickerProfile to compute future TSI.
    """
    sp(f"Labeling: TREND_REVERSAL (TSI_tide drops to <{tsi_drop_to} in {horizon}d)")
    labels = np.full(len(df), np.nan)

    # Pre-load snapshots for future TSI lookup
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    store = TimescaleDataStore()

    for ticker in df['ticker'].unique():
        profile = profiles.get(ticker)
        if profile is None:
            continue

        mask = df['ticker'] == ticker
        idx_list = df.index[mask]

        # Load ALL snapshots for this ticker (for future TSI lookup)
        snaps = store.load_snapshots(ticker, "1d")
        if snaps.empty:
            continue
        snap_slopes = snaps['tide_slope'] if 'tide_slope' in snaps.columns else None
        if snap_slopes is None:
            continue

        for idx in idx_list:
            ts = df.at[idx, 'timestamp']
            if ts not in snaps.index:
                continue
            pos = snaps.index.get_loc(ts)

            # Check if TSI drops below threshold at any point in horizon
            end_pos = min(pos + horizon + 1, len(snaps))
            if pos + 10 >= end_pos:  # Need at least 10 future bars
                continue

            reversed = False
            for j in range(10, end_pos - pos):
                future_slope = snap_slopes.iloc[pos + j]
                future_tsi = compute_tsi(future_slope, profile.tsi_tide_percentiles)
                if future_tsi < tsi_drop_to:
                    reversed = True
                    break

            labels[df.index.get_loc(idx)] = 1 if reversed else 0

    store.close()
    n_valid = (~np.isnan(labels)).sum()
    n_rev = (labels == 1).sum()
    print(f"    Labeled: {n_valid:,d} / {len(df):,d} | Reversal rate: {n_rev/max(n_valid,1)*100:.1f}%")
    return labels


def label_short_entry(df, ohlcv_cache, horizon=20):
    """Label 1: price goes DOWN in `horizon` days (mirror of long_entry)."""
    sp(f"Labeling: SHORT_ENTRY (horizon={horizon}d)")
    labels = np.full(len(df), np.nan)

    for ticker in df['ticker'].unique():
        ohlc = ohlcv_cache.get(ticker)
        if ohlc is None:
            continue
        closes = ohlc['close']
        mask = df['ticker'] == ticker
        idx_list = df.index[mask]

        for idx in idx_list:
            ts = df.at[idx, 'timestamp']
            if ts in ohlc.index:
                pos = ohlc.index.get_loc(ts)
                if pos + horizon < len(ohlc):
                    future_price = closes.iloc[pos + horizon]
                    current_price = df.at[idx, 'price']
                    labels[df.index.get_loc(idx)] = 1 if future_price < current_price else 0

    n_valid = (~np.isnan(labels)).sum()
    n_win = (labels == 1).sum()
    print(f"    Labeled: {n_valid:,d} / {len(df):,d} | Base WR: {n_win/max(n_valid,1)*100:.1f}%")
    return labels


def label_short_cover(df, ohlcv_cache, profit=-0.03, stop=0.02, time_limit=10):
    """Label 1: price hits BOUNCE (stop) before DROP (profit) within time_limit days.

    Inverted Triple Barrier for SHORT positions:
    If price bounces +2% first → label=1 (should have covered short = good cover signal)
    If price drops -3% first → label=0 (short is working = bad time to cover)
    If neither within time → label=0 (nothing happened = hold short)
    """
    sp(f"Labeling: SHORT_COVER (Inverted TB: drop={profit:+.1%}, bounce={stop:+.1%}, time={time_limit}d)")
    labels = np.full(len(df), np.nan)

    for ticker in df['ticker'].unique():
        ohlc = ohlcv_cache.get(ticker)
        if ohlc is None:
            continue
        closes = ohlc['close']
        mask = df['ticker'] == ticker
        idx_list = df.index[mask]

        for idx in idx_list:
            ts = df.at[idx, 'timestamp']
            if ts not in ohlc.index:
                continue
            pos = ohlc.index.get_loc(ts)
            entry_price = df.at[idx, 'price']
            if pos + time_limit >= len(ohlc):
                continue

            label = 0  # Default: hold short
            for j in range(1, time_limit + 1):
                ret = (closes.iloc[pos + j] / entry_price) - 1
                if ret >= stop:      # Bounced UP → should cover
                    label = 1
                    break
                if ret <= profit:    # Dropped further → short working
                    label = 0
                    break

            labels[df.index.get_loc(idx)] = label

    n_valid = (~np.isnan(labels)).sum()
    n_cover = (labels == 1).sum()
    print(f"    Labeled: {n_valid:,d} / {len(df):,d} | Cover rate: {n_cover/max(n_valid,1)*100:.1f}%")
    return labels


def label_bounce_height(df, ohlcv_cache, height_threshold=0.02, horizon=5):
    """Label 1: max runup in next `horizon` days exceeds threshold.

    Answers: "Will this counter-trend bounce go higher? Should I cover my short?"
    Mirror of pullback_depth.
    """
    sp(f"Labeling: BOUNCE_HEIGHT (threshold={height_threshold:+.1%}, horizon={horizon}d)")
    labels = np.full(len(df), np.nan)

    for ticker in df['ticker'].unique():
        ohlc = ohlcv_cache.get(ticker)
        if ohlc is None:
            continue
        closes = ohlc['close']
        mask = df['ticker'] == ticker
        idx_list = df.index[mask]

        for idx in idx_list:
            ts = df.at[idx, 'timestamp']
            if ts not in ohlc.index:
                continue
            pos = ohlc.index.get_loc(ts)
            entry_price = df.at[idx, 'price']
            end_pos = min(pos + horizon + 1, len(ohlc))
            if pos + 1 >= end_pos:
                continue

            future_closes = closes.iloc[pos + 1:end_pos]
            max_price = future_closes.max()
            max_runup = (max_price / entry_price) - 1

            labels[df.index.get_loc(idx)] = 1 if max_runup > height_threshold else 0

    n_valid = (~np.isnan(labels)).sum()
    n_high = (labels == 1).sum()
    print(f"    Labeled: {n_valid:,d} / {len(df):,d} | High bounce rate: {n_high/max(n_valid,1)*100:.1f}%")
    return labels


def label_trend_recovery(df, ohlcv_cache, profiles, horizon=60, tsi_rise_to=60):
    """Label 1: TSI_tide rises from current <30 to >tsi_rise_to within horizon days.

    Answers: "Is the bearish trend about to end?" Mirror of trend_reversal.
    """
    sp(f"Labeling: TREND_RECOVERY (TSI_tide rises to >{tsi_rise_to} in {horizon}d)")
    labels = np.full(len(df), np.nan)

    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    store = TimescaleDataStore()

    for ticker in df['ticker'].unique():
        profile = profiles.get(ticker)
        if profile is None:
            continue

        mask = df['ticker'] == ticker
        idx_list = df.index[mask]

        snaps = store.load_snapshots(ticker, "1d")
        if snaps.empty:
            continue
        snap_slopes = snaps['tide_slope'] if 'tide_slope' in snaps.columns else None
        if snap_slopes is None:
            continue

        for idx in idx_list:
            ts = df.at[idx, 'timestamp']
            if ts not in snaps.index:
                continue
            pos = snaps.index.get_loc(ts)

            end_pos = min(pos + horizon + 1, len(snaps))
            if pos + 10 >= end_pos:
                continue

            recovered = False
            for j in range(10, end_pos - pos):
                future_slope = snap_slopes.iloc[pos + j]
                future_tsi = compute_tsi(future_slope, profile.tsi_tide_percentiles)
                if future_tsi > tsi_rise_to:
                    recovered = True
                    break

            labels[df.index.get_loc(idx)] = 1 if recovered else 0

    store.close()
    n_valid = (~np.isnan(labels)).sum()
    n_rec = (labels == 1).sum()
    print(f"    Labeled: {n_valid:,d} / {len(df):,d} | Recovery rate: {n_rec/max(n_valid,1)*100:.1f}%")
    return labels


# ═══════════════════════════════════════════════════════════════
# CONTEXT FILTERS
# ═══════════════════════════════════════════════════════════════

def apply_context(df, head_name):
    """Apply context filter for each head. Returns boolean mask."""
    # LONG-side
    if head_name == 'long_entry':
        return pd.Series(True, index=df.index)
    elif head_name == 'swing_exit':
        return (df['regime_encoded'] == 2) & (df['sigma_tide'] > 0)
    elif head_name == 'pullback_depth':
        return (df['regime_encoded'] == 2) & (df['sigma_tide'] < -0.5)
    elif head_name == 'trend_reversal':
        return df['tsi_tide'] > 50
    # SHORT-side
    elif head_name == 'short_entry':
        return df['regime_encoded'] <= 1  # BEAR or FLAT
    elif head_name == 'short_cover':
        return (df['regime_encoded'] == 0) & (df['sigma_tide'] < 0)
    elif head_name == 'bounce_height':
        return (df['regime_encoded'] == 0) & (df['sigma_tide'] > 0.5)
    elif head_name == 'trend_recovery':
        return df['tsi_tide'] < 30
    # ZIGZAG detectors — all observations (turning points can occur in any regime)
    elif head_name in ('zz_bottom_detector', 'zz_top_detector'):
        return pd.Series(True, index=df.index)
    else:
        raise ValueError(f"Unknown head: {head_name}")


# ═══════════════════════════════════════════════════════════════
# CV + TRAINING (shared across heads)
# ═══════════════════════════════════════════════════════════════

def purged_walk_forward_cv(n, n_splits=5, purge_gap=20):
    """López de Prado's Purged Walk-Forward CV."""
    fold_size = n // (n_splits + 1)
    splits = []
    for i in range(n_splits):
        train_end = fold_size * (i + 1)
        test_start = train_end + purge_gap
        test_end = min(test_start + fold_size, n)
        if test_end > test_start + 20:
            splits.append((list(range(0, train_end)), list(range(test_start, test_end))))
    return splits


def compute_dsr(fold_sharpes):
    """Deflated Sharpe Ratio — corregido para caso degenerado."""
    if len(fold_sharpes) < 2:
        return 0.0
    mean_sr = np.mean(fold_sharpes)
    std_sr = np.std(fold_sharpes, ddof=1)
    if std_sr < 1e-8:
        # Caso degenerado: todos los folds idénticos.
        # No hay evidencia de robustez — retornar mean crudo, no inflado.
        return float(mean_sr) if mean_sr > 0 else 0.0
    t_stat = mean_sr / (std_sr / np.sqrt(len(fold_sharpes)))
    return float(t_stat)


def train_head(head_name, df_head, labels, feature_cols, horizon):
    """Train one head with Purged Walk-Forward CV."""
    sp(f"Training head: {head_name.upper()}")

    # Clean data
    valid_mask = (~np.isnan(labels)) & df_head[feature_cols].notna().all(axis=1)
    df_clean = df_head[valid_mask].copy()
    y = labels[valid_mask.values].astype(int)

    print(f"    Observations: {len(df_clean):,d} | Positive rate: {y.mean()*100:.1f}%")
    if len(df_clean) < 200:
        print(f"    ⚠️ Insufficient data ({len(df_clean)}). Skipping.")
        return None

    X = df_clean[feature_cols].values.astype(np.float32)

    # Sort temporally
    sort_idx = df_clean['timestamp'].argsort().values
    X = X[sort_idx]
    y = y[sort_idx]
    df_sorted = df_clean.iloc[sort_idx].reset_index(drop=True)

    # XGBoost
    try:
        from xgboost import XGBClassifier
        use_xgb = True
    except ImportError:
        from sklearn.ensemble import GradientBoostingClassifier
        use_xgb = False

    # Purged Walk-Forward CV
    splits = purged_walk_forward_cv(len(X), n_splits=5, purge_gap=horizon)
    fold_results = []
    fold_sharpes = []
    all_predictions = np.zeros(len(X))
    all_has_pred = np.zeros(len(X), dtype=bool)

    for fold_idx, (train_idx, test_idx) in enumerate(splits):
        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]

        # Handle class imbalance with scale_pos_weight
        n_pos = y_train.sum()
        n_neg = len(y_train) - n_pos
        scale_weight = max(n_neg / max(n_pos, 1), 1.0)

        if use_xgb:
            model = XGBClassifier(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                min_child_weight=10, subsample=0.8, colsample_bytree=0.7,
                reg_alpha=0.1, reg_lambda=1.0,
                scale_pos_weight=min(scale_weight, 5.0),
                random_state=42, eval_metric='logloss', tree_method='hist',
            )
            model.fit(X_train, y_train, verbose=False)
        else:
            model = GradientBoostingClassifier(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                min_samples_leaf=10, subsample=0.8, random_state=42,
            )
            model.fit(X_train, y_train)

        y_prob = model.predict_proba(X_test)[:, 1]
        y_pred = (y_prob >= 0.5).astype(int)
        acc = (y_pred == y_test).mean()

        # Discrimination: WR at high-P vs low-P
        high_p = y_prob >= 0.65
        low_p = y_prob < 0.35
        wr_high = y_test[high_p].mean() if high_p.sum() > 20 else float('nan')
        wr_low = y_test[low_p].mean() if low_p.sum() > 20 else float('nan')
        spread = wr_high - wr_low if not (np.isnan(wr_high) or np.isnan(wr_low)) else 0.0
        sharpe_fold = spread / max(0.01, y_test.std())
        fold_sharpes.append(sharpe_fold)

        all_predictions[test_idx] = y_prob
        all_has_pred[test_idx] = True

        fold_results.append({
            'fold': fold_idx, 'train_n': len(train_idx), 'test_n': len(test_idx),
            'accuracy': float(acc),
            'wr_high_p': float(wr_high) if not np.isnan(wr_high) else None,
            'wr_low_p': float(wr_low) if not np.isnan(wr_low) else None,
            'spread': float(spread), 'sharpe': float(sharpe_fold),
        })
        wr_h_str = f"{wr_high:.3f}" if not np.isnan(wr_high) else "N/A"
        wr_l_str = f"{wr_low:.3f}" if not np.isnan(wr_low) else "N/A"
        print(f"    Fold {fold_idx}: train={len(train_idx):,d} test={len(test_idx):,d} "
              f"acc={acc:.3f} WR(P≥.65)={wr_h_str} WR(P<.35)={wr_l_str} spread={spread:.3f}")

    dsr = compute_dsr(fold_sharpes)
    dsr_status = '✅ PASS' if dsr > 1.0 else '⚠️ WEAK' if dsr > 0.5 else '❌ FAIL'
    print(f"\n    ★ DSR: {dsr:.3f} {dsr_status}")

    # Train final model on ALL data
    sp(f"Training final {head_name.upper()} model on ALL data")
    scale_weight = max((len(y) - y.sum()) / max(y.sum(), 1), 1.0)
    if use_xgb:
        final_model = XGBClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            min_child_weight=10, subsample=0.8, colsample_bytree=0.7,
            reg_alpha=0.1, reg_lambda=1.0,
            scale_pos_weight=min(scale_weight, 5.0),
            random_state=42, eval_metric='logloss', tree_method='hist',
        )
        final_model.fit(X, y, verbose=False)
    else:
        final_model = GradientBoostingClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            min_samples_leaf=10, subsample=0.8, random_state=42,
        )
        final_model.fit(X, y)

    # Feature importance
    importances = final_model.feature_importances_
    importance_df = pd.DataFrame({
        'feature': feature_cols,
        'importance': importances,
    }).sort_values('importance', ascending=False)

    print(f"\n    {'Feature':<30s} │ {'Imp':>7s} │ {'Rank':>4s}")
    print(f"    {'─'*50}")
    for rank, (_, row) in enumerate(importance_df.head(15).iterrows(), 1):
        tier = "★★★" if row['importance'] > 0.06 else \
               "★★" if row['importance'] > 0.03 else \
               "★" if row['importance'] > 0.015 else "·"
        print(f"    {row['feature']:<30s} │ {row['importance']:>6.4f} │ {rank:>4d} {tier}")

    # Threshold calibration
    sp(f"Threshold calibration: {head_name.upper()}")
    valid = df_sorted[all_has_pred].copy()
    valid['p_win'] = all_predictions[all_has_pred]
    valid_y = y[all_has_pred]

    best_edge = -1
    best_thr = 0.55
    base_wr = valid_y.mean() * 100

    print(f"    Base rate: {base_wr:.1f}%")
    print(f"    {'Thr':>7s} │ {'N':>7s} │ {'WR':>6s} │ {'Edge':>7s}")
    print(f"    {'─'*35}")

    for thr in [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]:
        above = valid_y[valid['p_win'].values >= thr]
        if len(above) < 15:
            continue
        wr = above.mean() * 100
        edge = wr - base_wr
        if edge > best_edge:
            best_edge = edge
            best_thr = thr
        marker = " ← BEST" if thr == best_thr and edge > 0 else ""
        print(f"    {thr:>6.2f} │ {len(above):>7,d} │ {wr:>5.1f}% │ {edge:>+6.1f}%{marker}")

    print(f"\n    ★ Optimal threshold: P ≥ {best_thr:.2f} (edge: +{best_edge:.1f}%)")

    # Per-ticker stability
    sp(f"Per-ticker stability: {head_name.upper()}")
    ticker_results = {}
    tickers_pass = 0
    total_tickers = 0

    for ticker in sorted(valid['ticker'].unique()):
        tdf_y = valid_y[valid['ticker'].values == ticker]
        tdf_p = valid[valid['ticker'] == ticker]['p_win'].values
        total_tickers += 1

        signals = tdf_y[tdf_p >= best_thr]
        wr = signals.mean() * 100 if len(signals) > 5 else float('nan')
        passes = wr > 50 if not np.isnan(wr) else False
        if passes:
            tickers_pass += 1

        marker = "✅" if passes else "⚠️" if (not np.isnan(wr) and wr > 40) else "❌"
        wr_str = f"{wr:.1f}%" if not np.isnan(wr) else "N/A"
        ticker_results[ticker] = {
            'wr': float(wr) if not np.isnan(wr) else None,
            'n_signals': len(signals),
            'pass': passes,
        }
        print(f"    {ticker:>6s}: WR={wr_str:>7s} N={len(signals):>5,d} {marker}")

    pct_pass = tickers_pass / max(total_tickers, 1) * 100
    print(f"\n    ★ Passing: {tickers_pass}/{total_tickers} ({pct_pass:.0f}%)")

    return {
        'model': final_model,
        'feature_cols': feature_cols,
        'importance': importance_df,
        'threshold': best_thr,
        'dsr': dsr,
        'fold_results': fold_results,
        'ticker_results': ticker_results,
        'n_observations': len(df_clean),
        'positive_rate': float(y.mean()),
        'best_edge': best_edge,
    }


# ═══════════════════════════════════════════════════════════════
# PERSIST
# ═══════════════════════════════════════════════════════════════

def persist_head(head_name, result, dry_run=False):
    """Save model and config for one head."""
    if result is None:
        return

    model_dir = root_dir / "data" / "models"
    model_dir.mkdir(exist_ok=True)

    if dry_run:
        print(f"    [DRY RUN] Would save {head_name}")
        return

    # Model pickle
    model_path = model_dir / f"head_{head_name}_v2.pkl"
    with open(model_path, 'wb') as f:
        pickle.dump({
            'model': result['model'],
            'feature_cols': result['feature_cols'],
            'head': head_name,
            'version': 2,
            'threshold': result['threshold'],
            'dsr': result['dsr'],
            'trained_at': pd.Timestamp.now().isoformat(),
        }, f)
    print(f"    ✅ {model_path.name}")

    # Config JSON
    config = {
        'head': head_name,
        'version': 2,
        'description': HEAD_CONFIGS[head_name]['description'],
        'context': HEAD_CONFIGS[head_name]['context_desc'],
        'horizon': HEAD_CONFIGS[head_name]['horizon'],
        'threshold': result['threshold'],
        'dsr': result['dsr'],
        'n_observations': result['n_observations'],
        'positive_rate': result['positive_rate'],
        'best_edge': result['best_edge'],
        'feature_importance': result['importance'].set_index('feature')['importance'].to_dict(),
        'fold_results': result['fold_results'],
        'per_ticker': result['ticker_results'],
    }
    if 'barriers' in HEAD_CONFIGS[head_name]:
        config['barriers'] = HEAD_CONFIGS[head_name]['barriers']

    config_path = model_dir / f"head_{head_name}_config.json"
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2, default=str)
    print(f"    ✅ {config_path.name}")


# ═══════════════════════════════════════════════════════════════
# STATEFUL CONFIDENCE ASSESSMENT
# ═══════════════════════════════════════════════════════════════

READINESS_PATH = root_dir / "data" / "models" / "training_readiness.json"

# Statistical thresholds for grading
GRADE_THRESHOLDS = {
    'n_obs': {'A': 10000, 'B': 5000, 'C': 2000, 'D': 500},     # Minimum observations
    'balance': {'A': 0.15, 'B': 0.25, 'C': 0.35, 'D': 0.45},   # Max deviation from 50%
    'tickers': {'A': 15, 'B': 12, 'C': 8, 'D': 4},              # Tickers with ≥50 obs
    'per_fold': {'A': 2000, 'B': 1000, 'C': 500, 'D': 100},     # Min test fold size
}


def compute_statistical_power(n, positive_rate, alpha=0.05, mde=0.05):
    """Estimate statistical power to detect a minimum detectable effect (MDE).

    Uses normal approximation for proportions test.
    Returns: power (0-1), mde_at_80_power
    """
    from scipy.stats import norm

    p0 = positive_rate  # null proportion
    p1 = p0 + mde       # alternative proportion
    if p1 >= 1.0:
        p1 = 0.99

    z_alpha = norm.ppf(1 - alpha / 2)

    # Standard error under null
    se_null = np.sqrt(p0 * (1 - p0) / max(n, 1))
    # Standard error under alternative
    se_alt = np.sqrt(p1 * (1 - p1) / max(n, 1))

    if se_null < 1e-10 or se_alt < 1e-10:
        return 1.0, 0.0

    # Power = P(reject H0 | H1 is true)
    z_power = (abs(p1 - p0) - z_alpha * se_null) / se_alt
    power = float(norm.cdf(z_power))

    # MDE at 80% power
    z_beta = norm.ppf(0.80)
    mde_80 = (z_alpha * se_null + z_beta * se_alt)
    mde_80 = max(mde_80, 0.001)

    return power, float(mde_80)


def compute_confidence_interval(wr, n, confidence=0.95):
    """Wilson score interval for binomial proportion."""
    from scipy.stats import norm
    if n == 0:
        return 0.0, 1.0
    z = norm.ppf(1 - (1 - confidence) / 2)
    p = wr
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    spread = z * np.sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denom
    return max(0, float(center - spread)), min(1, float(center + spread))


def grade_metric(value, metric_name, higher_is_better=True):
    """Assign A/B/C/D/F grade based on thresholds."""
    thresholds = GRADE_THRESHOLDS[metric_name]
    for grade, threshold in thresholds.items():
        if higher_is_better:
            if value >= threshold:
                return grade
        else:
            if value <= threshold:
                return grade
    return 'F'


def assess_readiness(df, ohlcv_cache, profiles):
    """Compute and persist statistical readiness for all 8 heads."""
    sp("STATISTICAL CONFIDENCE ASSESSMENT")

    readiness = {
        'assessed_at': pd.Timestamp.now().isoformat(),
        'total_observations': len(df),
        'total_tickers': len(df['ticker'].unique()),
        'heads': {},
    }

    grade_map = {'A': 4, 'B': 3, 'C': 2, 'D': 1, 'F': 0}
    grade_emoji = {'A': '🟢', 'B': '🔵', 'C': '🟡', 'D': '🟠', 'F': '🔴'}

    print(f"\n    {'Head':<20s} │ {'N Obs':>7s} │ {'Pos%':>5s} │ {'Balance':>7s} │ {'Tickers':>7s} │ "
          f"{'Power':>5s} │ {'MDE':>5s} │ {'CI±':>5s} │ {'Grade':>5s}")
    print(f"    {'─'*90}")

    for head_name, cfg in HEAD_CONFIGS.items():
        # 1. Context filter
        context_mask = apply_context(df, head_name)
        n_context = int(context_mask.sum())

        # 2. Ticker distribution within context
        if n_context == 0:
            readiness['heads'][head_name] = {
                'status': 'NO_DATA', 'grade': 'F', 'n_obs': 0,
            }
            print(f"    {head_name:<20s} │ {'0':>7s} │ {'—':>5s} │ {'—':>7s} │ {'—':>7s} │ "
                  f"{'—':>5s} │ {'—':>5s} │ {'—':>5s} │ 🔴 F")
            continue

        df_head = df[context_mask]
        ticker_counts = df_head['ticker'].value_counts()
        tickers_with_50 = int((ticker_counts >= 50).sum())
        tickers_with_100 = int((ticker_counts >= 100).sum())

        # 3. Quick label sampling (use first 200 rows per ticker to estimate positive rate)
        sample_size = min(200 * len(df_head['ticker'].unique()), n_context)
        # Estimate positive rate from regime distribution for non-label-dependent metrics
        if head_name in ('long_entry', 'short_entry'):
            # Use regime as proxy: BULL → more LONG wins
            bull_pct = (df_head['regime_encoded'] == 2).mean()
            est_pos_rate = bull_pct if head_name == 'long_entry' else 1 - bull_pct
        elif head_name in ('swing_exit', 'short_cover'):
            # Exit/cover depends on volatility — estimate ~30-40% exit rate
            est_pos_rate = 0.35
        elif head_name in ('pullback_depth', 'bounce_height'):
            est_pos_rate = 0.40
        elif head_name in ('trend_reversal', 'trend_recovery'):
            est_pos_rate = 0.25  # Reversals are rare events
        else:
            est_pos_rate = 0.50

        # 4. Statistical metrics
        balance_dev = abs(est_pos_rate - 0.5)  # Deviation from 50/50
        power, mde_80 = compute_statistical_power(n_context, est_pos_rate, mde=0.05)
        ci_low, ci_high = compute_confidence_interval(est_pos_rate, n_context)
        ci_width = ci_high - ci_low

        # 5. Fold viability
        fold_size = n_context // 6  # 5 folds + 1 for expanding window
        n_folds_viable = sum(1 for _ in range(5)
                            if fold_size * (_ + 1) + cfg['horizon'] + fold_size <= n_context)

        # 6. Grades
        g_n = grade_metric(n_context, 'n_obs')
        g_bal = grade_metric(balance_dev, 'balance', higher_is_better=False)
        g_tick = grade_metric(tickers_with_50, 'tickers')
        g_fold = grade_metric(fold_size, 'per_fold')

        # Overall grade = weighted average
        grades = [g_n, g_bal, g_tick, g_fold]
        scores = [grade_map[g] for g in grades]
        avg_score = np.mean(scores)
        overall = 'A' if avg_score >= 3.5 else 'B' if avg_score >= 2.5 else \
                  'C' if avg_score >= 1.5 else 'D' if avg_score >= 0.5 else 'F'

        head_readiness = {
            'status': 'READY' if overall in ('A', 'B') else 'MARGINAL' if overall == 'C' else 'INSUFFICIENT',
            'grade': overall,
            'side': cfg['side'],
            'n_obs': n_context,
            'n_obs_grade': g_n,
            'est_positive_rate': round(est_pos_rate, 3),
            'balance_deviation': round(balance_dev, 3),
            'balance_grade': g_bal,
            'tickers_with_50_obs': tickers_with_50,
            'tickers_with_100_obs': tickers_with_100,
            'ticker_grade': g_tick,
            'statistical_power_at_5pct': round(power, 3),
            'mde_at_80pct_power': round(mde_80, 4),
            'ci_95_width': round(ci_width, 4),
            'fold_size': fold_size,
            'fold_grade': g_fold,
            'n_folds_viable': n_folds_viable,
            'horizon': cfg['horizon'],
            'description': cfg['description'],
        }
        readiness['heads'][head_name] = head_readiness

        emoji = grade_emoji[overall]
        print(f"    {head_name:<20s} │ {n_context:>7,d} │ {est_pos_rate*100:>4.1f}% │ "
              f"{'±'+f'{balance_dev*100:.0f}%':>7s} │ {tickers_with_50:>3d}/17  │ "
              f"{power:>4.1%} │ {mde_80:>4.2%} │ {ci_width:>4.2%} │ {emoji} {overall}")

    # Persist
    model_dir = root_dir / "data" / "models"
    model_dir.mkdir(exist_ok=True)
    with open(READINESS_PATH, 'w') as f:
        json.dump(readiness, f, indent=2, default=str)
    print(f"\n    ★ Readiness persisted to {READINESS_PATH.name}")

    # Summary
    heads_ready = sum(1 for h in readiness['heads'].values() if h.get('status') == 'READY')
    heads_marginal = sum(1 for h in readiness['heads'].values() if h.get('status') == 'MARGINAL')
    heads_insuff = sum(1 for h in readiness['heads'].values() if h.get('status') in ('INSUFFICIENT', 'NO_DATA'))
    print(f"    ★ Ready: {heads_ready} | Marginal: {heads_marginal} | Insufficient: {heads_insuff}")

    return readiness


def load_readiness():
    """Load persisted readiness assessment (stateful query)."""
    if not READINESS_PATH.exists():
        return None
    with open(READINESS_PATH) as f:
        return json.load(f)


def print_readiness_status():
    """Print current training readiness from persisted state."""
    readiness = load_readiness()
    if readiness is None:
        print("  No readiness assessment found. Run with --assess first.")
        return

    p("TRAINING READINESS STATUS (Stateful)")
    print(f"  Assessed at: {readiness['assessed_at']}")
    print(f"  Total observations: {readiness['total_observations']:,d}")

    grade_emoji = {'A': '🟢', 'B': '🔵', 'C': '🟡', 'D': '🟠', 'F': '🔴'}

    print(f"\n  {'Head':<20s} │ {'Side':<6s} │ {'N Obs':>7s} │ {'Status':<12s} │ {'Grade':>5s} │ {'Power':>6s} │ {'MDE':>6s}")
    print(f"  {'─'*75}")

    for head_name in HEAD_CONFIGS:
        h = readiness['heads'].get(head_name, {})
        if not h:
            continue
        grade = h.get('grade', 'F')
        emoji = grade_emoji.get(grade, '⚪')
        status = h.get('status', 'UNKNOWN')
        n = h.get('n_obs', 0)
        side = h.get('side', '?')
        power = h.get('statistical_power_at_5pct', 0)
        mde = h.get('mde_at_80pct_power', 0)
        print(f"  {head_name:<20s} │ {side:<6s} │ {n:>7,d} │ {status:<12s} │ {emoji} {grade:>2s} │ {power:>5.1%} │ {mde:>5.2%}")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Multi-Head Pre-Trainer v2")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--heads", type=str, default=None,
                        help="Comma-separated heads to train (default: all)")
    parser.add_argument("--assess", action="store_true",
                        help="Only run statistical readiness assessment (no training)")
    parser.add_argument("--status", action="store_true",
                        help="Print current readiness status from last assessment (no DB query)")
    args = parser.parse_args()

    # Quick status check from persisted state
    if args.status:
        print_readiness_status()
        return

    heads_to_train = args.heads.split(",") if args.heads else list(HEAD_CONFIGS.keys())

    p("MULTI-HEAD PRE-TRAINER v2 — 8 Models, Let the Data Decide")
    print(f"  Heads: {', '.join(heads_to_train)}")
    for h in heads_to_train:
        cfg = HEAD_CONFIGS[h]
        print(f"    • {h} [{cfg['side']}]: {cfg['description']}")

    t0 = time.time()
    store = TimescaleDataStore()
    profile_store = TickerProfileStore()

    # Load Feature Lake (shared across all heads)
    df, ohlcv_cache, profiles = load_feature_lake(store, profile_store)

    # Expand feature lake with derived features (ATR, candle structure, volume dynamics, etc.)
    # These are required by the optimized feature sets from Challenger v2.
    # Lazy import to avoid circular dependency (feature_optimizer imports from this module).
    from backend.scripts.feature_optimizer import expand_feature_lake
    derived_features = expand_feature_lake(df)
    all_available = ALL_FEATURES + derived_features
    feature_cols = [f for f in all_available if f in df.columns]
    print(f"    Features: {len(feature_cols)} available ({len(ALL_FEATURES)} base + {len(derived_features)} derived)")

    # ── ALWAYS run readiness assessment first ──
    readiness = assess_readiness(df, ohlcv_cache, profiles)

    if args.assess:
        store.close()
        profile_store.close()
        elapsed = time.time() - t0
        print(f"\n  Assessment complete in {elapsed:.1f}s")
        return

    # ── TRAINING ──
    results = {}
    for head_name in heads_to_train:
        p(f"HEAD: {head_name.upper()}")
        cfg = HEAD_CONFIGS[head_name]

        # Check readiness before training
        head_ready = readiness['heads'].get(head_name, {})
        head_grade = head_ready.get('grade', 'F')
        if head_grade == 'F':
            print(f"  🔴 SKIPPING — Grade F (insufficient data)")
            results[head_name] = None
            continue
        elif head_grade == 'D':
            print(f"  🟠 WARNING — Grade D (marginal data, results may be unreliable)")

        # 1. Apply context filter
        context_mask = apply_context(df, head_name)
        df_head = df[context_mask].reset_index(drop=True)
        print(f"  Context: {context_mask.sum():,d} obs ({cfg['context_desc']})")

        if len(df_head) < 200:
            print(f"  ⚠️ Insufficient data ({len(df_head)}). Skipping.")
            results[head_name] = None
            continue

        # 2. Compute labels
        if head_name == 'long_entry':
            labels = label_long_entry(df_head, ohlcv_cache, horizon=cfg['horizon'])
        elif head_name == 'swing_exit':
            b = cfg['barriers']
            labels = label_swing_exit(df_head, ohlcv_cache,
                                       profit=b['profit'], stop=b['stop'], time_limit=b['time'])
        elif head_name == 'pullback_depth':
            labels = label_pullback_depth(df_head, ohlcv_cache, horizon=cfg['horizon'])
        elif head_name == 'trend_reversal':
            labels = label_trend_reversal(df_head, ohlcv_cache, profiles, horizon=cfg['horizon'])
        elif head_name == 'short_entry':
            labels = label_short_entry(df_head, ohlcv_cache, horizon=cfg['horizon'])
        elif head_name == 'short_cover':
            b = cfg['barriers']
            labels = label_short_cover(df_head, ohlcv_cache,
                                        profit=b['profit'], stop=b['stop'], time_limit=b['time'])
        elif head_name == 'bounce_height':
            labels = label_bounce_height(df_head, ohlcv_cache, horizon=cfg['horizon'])
        elif head_name == 'trend_recovery':
            labels = label_trend_recovery(df_head, ohlcv_cache, profiles, horizon=cfg['horizon'])
        elif head_name in ('zz_bottom_detector', 'zz_top_detector'):
            labels = label_zz_turning_point(
                df_head, store,
                tp_type=cfg['zz_tp_type'],
                proximity_window=cfg['proximity_window']
            )

        # 3. Per-head feature selection (Challenger v2 optimized sets)
        optimized = OPTIMIZED_FEATURES.get(head_name)
        if optimized is not None:
            # Use Challenger v2 optimized set — only the features that were selected
            head_feature_cols = [f for f in optimized if f in df.columns]
            missing = [f for f in optimized if f not in df.columns]
            if missing:
                print(f"  ⚠️ {head_name}: {len(missing)} optimized features missing: {missing}")
            print(f"  ⚡ {head_name}: using OPTIMIZED set ({len(head_feature_cols)}f vs {len(feature_cols)} total)")
        elif cfg.get('exclude_deltas', False):
            head_feature_cols = [f for f in feature_cols if not f.startswith('d_')]
            print(f"  ⚡ {head_name}: excluding delta features ({len(feature_cols)}→{len(head_feature_cols)})")
        else:
            # Fallback: use ONLY base features (no derived) to match current production models.
            # This prevents training on expand_feature_lake() features that head_scorer can't compute yet.
            base_feature_cols = [f for f in ALL_FEATURES if f in df.columns]
            head_feature_cols = base_feature_cols
            print(f"  📋 {head_name}: using BASE features ({len(head_feature_cols)}f) — pending Challenger v3")

        # 4. Train
        result = train_head(head_name, df_head, labels, head_feature_cols, cfg['horizon'])
        results[head_name] = result

        # 4. Persist
        persist_head(head_name, result, dry_run=args.dry_run)

    # ── Update readiness with actual training results ──
    for head_name, result in results.items():
        if result is not None and head_name in readiness['heads']:
            readiness['heads'][head_name]['trained'] = True
            readiness['heads'][head_name]['dsr'] = result['dsr']
            readiness['heads'][head_name]['actual_positive_rate'] = result['positive_rate']
            readiness['heads'][head_name]['best_edge'] = result['best_edge']
            readiness['heads'][head_name]['threshold'] = result['threshold']
            readiness['heads'][head_name]['trained_at'] = pd.Timestamp.now().isoformat()
    with open(READINESS_PATH, 'w') as f:
        json.dump(readiness, f, indent=2, default=str)

    store.close()
    profile_store.close()
    elapsed = time.time() - t0

    # ═══ SUMMARY ═══
    p("MULTI-HEAD PRE-TRAINER v2 — SUMMARY")
    print(f"  Total time: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"\n  {'Head':<20s} │ {'Side':<6s} │ {'N Obs':>7s} │ {'Pos%':>5s} │ {'DSR':>6s} │ {'Thr':>5s} │ {'Edge':>6s} │ {'Grade':>5s}")
    print(f"  {'─'*80}")

    grade_emoji = {'A': '🟢', 'B': '🔵', 'C': '🟡', 'D': '🟠', 'F': '🔴'}
    for head_name in heads_to_train:
        result = results.get(head_name)
        grade = readiness['heads'].get(head_name, {}).get('grade', '?')
        side = HEAD_CONFIGS[head_name]['side']
        emoji = grade_emoji.get(grade, '⚪')
        if result is None:
            print(f"  {head_name:<20s} │ {side:<6s} │ {'SKIP':>7s} │ {'—':>5s} │ {'—':>6s} │ {'—':>5s} │ {'—':>6s} │ {emoji} {grade}")
            continue
        dsr_s = '✅' if result['dsr'] > 1.0 else '⚠️' if result['dsr'] > 0.5 else '❌'
        print(f"  {head_name:<20s} │ {side:<6s} │ {result['n_observations']:>7,d} │ {result['positive_rate']*100:>4.1f}% │ "
              f"{result['dsr']:>5.2f} │ {result['threshold']:>4.2f} │ {result['best_edge']:>+5.1f}% │ {emoji} {grade} {dsr_s}")

    # Top features per head
    print(f"\n  Top-5 Features per Head:")
    for head_name, result in results.items():
        if result is None:
            continue
        top5 = result['importance'].head(5)['feature'].tolist()
        print(f"    {head_name:<20s}: {', '.join(top5)}")


if __name__ == "__main__":
    main()

