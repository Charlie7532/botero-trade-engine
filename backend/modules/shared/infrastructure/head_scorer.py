"""
DEPRECATED — Replaced by SentinelModelLoader (sentinel_model_loader.py)
=========================================================================
This file is preserved for reference. The 10-head HeadScorer system was
deprecated per Committee Dictamen (dictamen_comite_headscorer_legacy.md).
Replaced by 2 Sentinel models (PISO/TECHO) with 4 archetypes.
Backup: _deprecated/head_scorer_legacy.py

Original docstring:
HeadScorer — Infrastructure Implementation for Multi-Head ML Predictions
============================================================================
Loads trained XGBoost models from backend/models/ and emits P(positive)
for each head. Converts a ChannelSnapshot into the feature vector
that the models expect.

Challenger v2 models require derived features (ATR, volume dynamics,
candle structure) beyond the base snapshot. This scorer computes them
from optional OHLCV bar data passed to score()/score_all().

Lazy-loaded: models are loaded on first use. Thread-safe via module-level
singleton. Profiles cached per-ticker.

Clean Architecture: Infrastructure layer. Depends on TickerProfilePort
for TSI/ADI computation.
"""
import logging
import pickle
import json
from pathlib import Path
from typing import Optional
from collections import deque

import numpy as np
import math

from backend.modules.shared.domain.entities.channel_snapshot import ChannelSnapshot
from backend.modules.shared.domain.ports.head_scorer_port import HeadScorerPort, HeadScore
from backend.modules.shared.domain.rules.trend_strength import compute_tsi, compute_adi
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "models"

# Feature columns — must match unified_pretrainer_v2.py exactly
# Includes residual_std_*, reg_value_*, vwap_* which are present in ChannelSnapshot
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
    # ── v2 additions: present in ChannelSnapshot but were missing from this list ──
    'residual_std_tide', 'residual_std_current', 'residual_std_wave',
    'reg_value_tide', 'reg_value_current', 'reg_value_wave',
    'vwap_tide', 'vwap_current', 'vwap_wave',
]

# Delta features: bar-over-bar changes (forensic precursors)
# d_tide_slope is the strongest precursor (t=-80.96, ★★★ in 6/8 heads)
DELTA_SOURCES = [
    'sigma_wave', 'kalman_velocity', 'rsi_value', 'compression_ratio',
    'fear_level', 'vol_up_down_ratio', 'tide_slope', 'wave_accel',
]

# Candle delta sources (only available when OHLCV data is provided)
CANDLE_DELTA_SOURCES = [
    'close_position', 'div_high_close_tide', 'div_close_low_tide',
]

HEAD_DESCRIPTIONS = {
    'long_entry': 'Good time to buy? (20d forward return > 0)',
    'swing_exit': 'Top of bullish leg? (Triple Barrier 10d)',
    'pullback_depth': 'Pullback will deepen? (Max DD 5d > -2%)',
    'trend_reversal': 'Macro trend dying? (TSI drops >50 → <30 in 60d)',
    'short_entry': 'Good time to short? (20d forward return < 0)',
    'short_cover': 'Bottom of bearish leg? (Inverted TB 10d)',
    'bounce_height': 'Bounce will go higher? (Max runup 5d > +2%)',
    'trend_recovery': 'Bearish trend ending? (TSI rises <30 → >60 in 60d)',
    'zz_bottom_detector': 'Near a zigzag 5% bottom? (within 3 bars of MIN)',
    'zz_top_detector': 'Near a zigzag 5% top? (within 3 bars of MAX)',
}

# Phase 1 derived features (must match unified_pretrainer_v2.py)
SLOPE_DECEL_LOOKBACK = 5
RSI_DIV_WINDOW = 60

# Historical buffer size for multi-bar derived features (ATR-14, vol MA-20)
HISTORY_BUFFER_SIZE = 30


def _safe_div(a, b, fill=0.0):
    """Safe scalar division."""
    return a / b if abs(b) > 1e-8 else fill


class HeadScorer(HeadScorerPort):
    """Production multi-head scorer.

    Loads models lazily on first score() call. Caches profiles per-ticker.
    Falls back gracefully: if a head or profile is unavailable, returns None.

    Challenger v2 support: accepts optional OHLCV bar data for computing
    derived features (ATR, candle structure, volume dynamics). Maintains
    a per-ticker historical buffer for multi-bar features.
    """

    def __init__(self, models_dir: Path | None = None):
        self._models_dir = models_dir or MODELS_DIR
        self._models: dict[str, dict] = {}       # head_name -> {model, feature_cols, threshold, ...}
        self._profile_store = TickerProfileStore()
        self._profiles: dict[str, object] = {}   # ticker -> TickerProfile (cached)
        self._prev_snapshots: dict[str, dict] = {}  # ticker -> previous snapshot feature dict (for deltas)
        self._feature_cache: dict[str, tuple] = {}  # ticker -> (snapshot, feature_dict)
        self._loaded = False
        # Historical buffers for multi-bar derived features (per-ticker)
        self._bar_history: dict[str, deque] = {}   # ticker -> deque of {close, high, low, open, volume}

    def _ensure_loaded(self):
        """Lazy-load all available head models."""
        if self._loaded:
            return

        for head_name in HEAD_DESCRIPTIONS:
            pkl_path = self._models_dir / f"head_{head_name}_v2.pkl"
            if not pkl_path.exists():
                logger.debug(f"HeadScorer: {head_name} model not found, skipping")
                continue

            try:
                with open(pkl_path, 'rb') as f:
                    model_dict = pickle.load(f)

                self._models[head_name] = model_dict
                logger.debug(
                    f"HeadScorer: loaded {head_name} "
                    f"(threshold={model_dict.get('threshold', 0.5):.2f}, "
                    f"DSR={model_dict.get('dsr', 0):.2f})"
                )
            except Exception as e:
                logger.error(f"HeadScorer: failed to load {head_name}: {e}")

        self._loaded = True
        logger.info(f"HeadScorer: {len(self._models)}/{len(HEAD_DESCRIPTIONS)} heads loaded")

    def _get_profile(self, ticker: str):
        """Get cached ticker profile."""
        if ticker not in self._profiles:
            try:
                self._profiles[ticker] = self._profile_store.load_profile(ticker)
            except Exception:
                self._profiles[ticker] = None
        return self._profiles[ticker]

    def _update_bar_history(self, ticker: str, ohlcv: dict | None):
        """Append OHLCV bar to historical buffer for multi-bar features."""
        if ohlcv is None:
            return
        if ticker not in self._bar_history:
            self._bar_history[ticker] = deque(maxlen=HISTORY_BUFFER_SIZE)
        self._bar_history[ticker].append(ohlcv)

    def _compute_derived_features(self, feat: dict, ticker: str, ohlcv: dict | None) -> None:
        """Compute derived features that Challenger v2 optimized heads require.

        Three tiers:
          1. Instant-derivable: ratios, squares, interactions from snapshot values.
          2. OHLCV-dependent: sigma_high/low, close_position, vwap_sigma_high/low.
             Requires the current bar's high/low/open/close.
          3. Multi-bar historical: ATR, volume_trend, overnight_gap.
             Requires the per-ticker bar history buffer.
        """
        # ── TIER 1: Instant-derivable from snapshot values ──
        sigma_tide = feat.get('sigma_tide', 0)
        sigma_current = feat.get('sigma_current', 0)
        sigma_wave = feat.get('sigma_wave', 0)
        tide_slope = feat.get('tide_slope', 0)
        current_slope = feat.get('current_slope', 0)
        wave_slope = feat.get('wave_slope', 0)

        # Cross-timeframe ratios
        feat['sigma_ratio_tw'] = _safe_div(sigma_tide, sigma_wave)
        feat['slope_ratio_tc'] = _safe_div(tide_slope, current_slope)
        feat['slope_ratio_tw'] = _safe_div(tide_slope, wave_slope)
        feat['tension_ratio_tw'] = _safe_div(feat.get('tension_tide', 0), feat.get('tension_wave', 0))

        # Slope squared (non-linear extreme detection)
        feat['tide_slope_sq'] = tide_slope ** 2
        feat['current_slope_sq'] = current_slope ** 2
        feat['wave_slope_sq'] = wave_slope ** 2
        feat['slope_energy'] = abs(tide_slope) + abs(current_slope) + abs(wave_slope)
        feat['slope_product_tc'] = tide_slope * current_slope

        # Slope differences
        feat['slope_diff_tc'] = tide_slope - current_slope
        feat['slope_diff_tw'] = tide_slope - wave_slope
        feat['slope_diff_cw'] = current_slope - wave_slope

        # Interactions
        feat['kalman_slope_conf'] = feat.get('kalman_velocity', 0) * tide_slope
        feat['vol_slope_conf'] = feat.get('vol_up_down_ratio', 1.0) * tide_slope
        feat['compr_at_extreme'] = feat.get('compression_ratio', 0) * abs(sigma_tide)
        feat['rsi_sigma_interact'] = feat.get('rsi_value', 50) * sigma_tide

        # Alignment
        feat['triple_alignment'] = float(np.sign(tide_slope) * np.sign(current_slope) * np.sign(wave_slope))
        bullish = (float(sigma_tide > 0) + float(sigma_current > 0) + float(sigma_wave > 0)) / 3.0
        feat['bullish_score'] = bullish
        feat['total_displacement'] = abs(sigma_tide) + abs(sigma_current) + abs(sigma_wave)

        # Distance / extremes
        feat['price_vwap_div'] = sigma_tide - feat.get('vwap_sigma_tide', 0)
        feat['sigma_abs_dist'] = abs(sigma_tide)
        feat['sigma_squared'] = sigma_tide ** 2
        feat['sigma_max_tf'] = max(sigma_tide, sigma_current, sigma_wave)
        feat['sigma_min_tf'] = min(sigma_tide, sigma_current, sigma_wave)

        # Angular
        feat['slope_phase_tw'] = math.atan(tide_slope - wave_slope)
        feat['sigma_phase_tc'] = math.atan(sigma_tide - sigma_current)

        # ── TIER 2: OHLCV-dependent features ──
        if ohlcv is not None:
            high = float(ohlcv.get('high', 0))
            low = float(ohlcv.get('low', 0))
            close = float(ohlcv.get('close', 0))
            open_p = float(ohlcv.get('open', close))

            # Close position (Wyckoff): where does price close within bar range
            candle_range = high - low
            if candle_range > 0:
                feat['close_position'] = (close - low) / candle_range
                feat['body_ratio'] = abs(close - open_p) / candle_range
            else:
                feat['close_position'] = 0.5
                feat['body_ratio'] = 0.5

            # Sigma(HIGH) and sigma(LOW) for each regression channel
            for tf in ['tide', 'current', 'wave']:
                reg_val = feat.get(f'reg_value_{tf}', 0)
                residual_std = feat.get(f'residual_std_{tf}', 1.0)
                if abs(residual_std) > 1e-8:
                    sh = (high - reg_val) / residual_std
                    sl = (low - reg_val) / residual_std
                    sc = feat.get(f'sigma_{tf}', 0)
                    feat[f'sigma_high_{tf}'] = sh
                    feat[f'sigma_low_{tf}'] = sl
                    feat[f'sigma_range_{tf}'] = sh - sl
                    feat[f'div_high_close_{tf}'] = sh - sc
                    feat[f'div_close_low_{tf}'] = sc - sl
                else:
                    feat[f'sigma_high_{tf}'] = 0.0
                    feat[f'sigma_low_{tf}'] = 0.0
                    feat[f'sigma_range_{tf}'] = 0.0
                    feat[f'div_high_close_{tf}'] = 0.0
                    feat[f'div_close_low_{tf}'] = 0.0

            # VWAP sigma(HIGH) and sigma(LOW) — institutional rejection
            for tf in ['tide', 'current']:
                vwap_val = feat.get(f'vwap_{tf}', 0)
                residual_std = feat.get(f'residual_std_{tf}', 1.0)
                if abs(residual_std) > 1e-8:
                    feat[f'vwap_sigma_high_{tf}'] = (high - vwap_val) / residual_std
                    feat[f'vwap_sigma_low_{tf}'] = (low - vwap_val) / residual_std
                else:
                    feat[f'vwap_sigma_high_{tf}'] = 0.0
                    feat[f'vwap_sigma_low_{tf}'] = 0.0

        # ── TIER 3: Multi-bar historical features ──
        history = self._bar_history.get(ticker)
        if history and len(history) >= 2:
            bars = list(history)
            n_bars = len(bars)

            # Overnight gap: current open vs previous close
            if ohlcv is not None and n_bars >= 2:
                prev_close = float(bars[-2].get('close', 0))
                curr_open = float(ohlcv.get('open', 0))
                if abs(prev_close) > 1e-8:
                    feat['overnight_gap'] = (curr_open - prev_close) / prev_close
                else:
                    feat['overnight_gap'] = 0.0

            # ATR-14 from history buffer
            if n_bars >= 3:
                trs = []
                for i in range(1, n_bars):
                    h = float(bars[i].get('high', 0))
                    l = float(bars[i].get('low', 0))
                    pc = float(bars[i - 1].get('close', 0))
                    tr = max(h - l, abs(h - pc), abs(l - pc))
                    trs.append(tr)
                window = min(14, len(trs))
                atr_val = sum(trs[-window:]) / window if window > 0 else 0.0
                feat['atr_14'] = atr_val
                price = float(bars[-1].get('close', 1.0))
                feat['atr_ratio'] = _safe_div(atr_val, price)

                # Overnight gap normalized by ATR
                if 'overnight_gap' in feat and feat['atr_ratio'] > 1e-8:
                    feat['overnight_gap_atr'] = _safe_div(feat['overnight_gap'], feat['atr_ratio'])
                    feat['overnight_gap_vs_tide'] = feat.get('overnight_gap_atr', 0) * tide_slope

            # Volume features from history buffer
            if n_bars >= 5:
                volumes = [float(b.get('volume', 0)) for b in bars]
                vol_ma20 = sum(volumes[-min(20, n_bars):]) / min(20, n_bars) if n_bars > 0 else 1.0
                curr_vol = volumes[-1] if volumes else 0.0
                feat['volume_ratio'] = _safe_div(curr_vol, vol_ma20)

                # Volume trend: MA5 / MA20
                vol_ma5 = sum(volumes[-min(5, n_bars):]) / min(5, n_bars)
                feat['volume_trend'] = _safe_div(vol_ma5, vol_ma20)

                # Volume sigma
                if n_bars >= 10:
                    vol_std = float(np.std(volumes[-min(20, n_bars):]))
                    feat['volume_sigma'] = _safe_div(curr_vol - vol_ma20, max(vol_std, 1e-8))

                # Vol-price divergence (last 5 bars)
                closes = [float(b.get('close', 0)) for b in bars]
                if n_bars >= 6:
                    price_dir = float(np.sign(closes[-1] - closes[-5]))
                    vol_dir = float(np.sign(volumes[-1] - volumes[-5]))
                    feat['vol_price_divergence'] = price_dir * vol_dir

                # Volume acceleration
                if n_bars >= 10:
                    vol_ma5_prev = sum(volumes[-min(10, n_bars):-5]) / min(5, n_bars - 5) if n_bars > 5 else vol_ma5
                    feat['vol_accel'] = _safe_div(vol_ma5 - vol_ma5_prev, vol_ma20)

                # ── Vol-Price Forencia features (6 validated) ──
                vol_std = float(np.std(volumes[-min(20, n_bars):])) if n_bars >= 10 else 1.0
                vol_z = _safe_div(curr_vol - vol_ma20, max(vol_std, 1e-8))

                # 1. vol_price_corr_20d: rolling Pearson(vol, returns, 20d)
                if n_bars >= 20:
                    closes = closes if 'closes' in dir() else [float(b.get('close', 0)) for b in bars]
                    rets = [0.0]
                    for ci in range(1, len(closes)):
                        rets.append((closes[ci] - closes[ci-1]) / closes[ci-1] if closes[ci-1] > 0 else 0.0)
                    v_20 = np.array(volumes[-20:])
                    r_20 = np.array(rets[-20:])
                    if np.std(v_20) > 0 and np.std(r_20) > 0:
                        feat['vol_price_corr_20d'] = float(np.corrcoef(v_20, r_20)[0, 1])
                    else:
                        feat['vol_price_corr_20d'] = 0.0

                # 2. effort_vs_result_20d: Wyckoff (log-normalized)
                if n_bars >= 20 and ohlcv is not None:
                    highs = [float(b.get('high', 0)) for b in bars]
                    lows = [float(b.get('low', 0)) for b in bars]
                    ranges = [max(h - l, 1e-8) for h, l in zip(highs[-20:], lows[-20:])]
                    avg_range = sum(ranges) / len(ranges)
                    price = float(bars[-1].get('close', 1.0))
                    raw_effort = _safe_div(vol_ma20, avg_range * max(price, 1e-8))
                    feat['effort_vs_result_20d'] = math.log1p(abs(raw_effort)) * (1.0 if raw_effort >= 0 else -1.0)

                # 3. climax_vol_ratio: current / max(20d)
                vol_max = max(volumes[-min(20, n_bars):]) if n_bars >= 5 else curr_vol
                feat['climax_vol_ratio'] = _safe_div(curr_vol, max(vol_max, 1e-8))

                # 4. vol_return_interaction: vol z-score × return
                if ohlcv is not None:
                    closes = closes if 'closes' in dir() else [float(b.get('close', 0)) for b in bars]
                    if len(closes) >= 2:
                        curr_return = (closes[-1] - closes[-2]) / closes[-2] if closes[-2] > 0 else 0.0
                        feat['vol_return_interaction'] = vol_z * curr_return

                # 5. vol_breakout_signal: vol spike × range expansion
                if ohlcv is not None and n_bars >= 10:
                    highs = [float(b.get('high', 0)) for b in bars]
                    lows = [float(b.get('low', 0)) for b in bars]
                    curr_range = float(ohlcv.get('high', 0)) - float(ohlcv.get('low', 0))
                    ranges = [max(h - l, 1e-8) for h, l in zip(highs[-20:], lows[-20:])]
                    range_mean = sum(ranges) / len(ranges)
                    range_std = float(np.std(ranges)) if len(ranges) > 1 else 1.0
                    range_z = _safe_div(curr_range - range_mean, max(range_std, 1e-8))
                    feat['vol_breakout_signal'] = vol_z * range_z

                # 6. vol_price_regime: categorical Wyckoff state
                if n_bars >= 6:
                    closes = closes if 'closes' in dir() else [float(b.get('close', 0)) for b in bars]
                    ret_5d = (closes[-1] - closes[-6]) / closes[-6] if len(closes) >= 6 and closes[-6] > 0 else 0.0
                    if vol_z > 1.0 and ret_5d > 0.01:
                        feat['vol_price_regime'] = 2.0   # Confirmed rally
                    elif vol_z < -0.5 and ret_5d > 0.01:
                        feat['vol_price_regime'] = 1.0   # Suspicious rally
                    elif vol_z < -0.5 and ret_5d < -0.01:
                        feat['vol_price_regime'] = -1.0  # Orderly decline
                    elif vol_z > 1.0 and ret_5d < -0.01:
                        feat['vol_price_regime'] = -2.0  # Panic selling
                    else:
                        feat['vol_price_regime'] = 0.0   # Neutral

    def _snapshot_to_features(
        self,
        ticker: str,
        snapshot: ChannelSnapshot,
        prev_snapshot: Optional[ChannelSnapshot] = None,
        ohlcv: dict | None = None,
    ) -> dict:
        """Convert ChannelSnapshot to feature dict matching model expectations."""
        # Check cache first (for multi-head scoring determinism & performance)
        cached = self._feature_cache.get(ticker)
        if cached and cached[0] is snapshot:
            return cached[1]

        snap_dict = snapshot.to_dict()

        # DB features: direct from snapshot
        feat = {}
        for f in DB_FEATURES:
            val = snap_dict.get(f, 0.0)
            feat[f] = float(val) if val is not None else 0.0

        # Computed features: TSI/ADI from profile
        profile = self._get_profile(ticker)
        if profile is not None:
            feat['tsi_tide'] = compute_tsi(feat.get('tide_slope', 0), profile.tsi_tide_percentiles)
            feat['tsi_current'] = compute_tsi(feat.get('current_slope', 0), profile.tsi_current_percentiles)
            feat['tsi_wave'] = compute_tsi(feat.get('wave_slope', 0), profile.tsi_wave_percentiles)
            feat['adi_tide'] = compute_adi(feat.get('tension_tide', 0), profile.adi_tide_percentiles)
            feat['adi_current'] = compute_adi(feat.get('tension_current', 0), profile.adi_current_percentiles)
            feat['adi_wave'] = compute_adi(feat.get('tension_wave', 0), profile.adi_wave_percentiles)
        else:
            # Default: midpoint (no information)
            for f in ['tsi_tide', 'tsi_current', 'tsi_wave',
                       'adi_tide', 'adi_current', 'adi_wave']:
                feat[f] = 50

        # Encoded features
        regime_map = {'BULL': 2, 'FLAT': 1, 'BEAR': 0}
        feat['regime_encoded'] = regime_map.get(snapshot.regime, 1)
        feat['below_all_vwaps_int'] = int(snapshot.below_all_vwaps)
        feat['above_all_vwaps_int'] = int(snapshot.above_all_vwaps)

        # Delta features: bar-over-bar changes (forensic precursors)
        if prev_snapshot is not None:
            prev = prev_snapshot.to_dict()
        else:
            prev = self._prev_snapshots.get(ticker, {})

        for src in DELTA_SOURCES:
            curr_val = feat.get(src, 0.0)
            prev_val = prev.get(src, curr_val)  # First bar: delta = 0
            if prev_val is None:
                prev_val = curr_val
            feat[f'd_{src}'] = float(curr_val) - float(prev_val)

        # Candle delta features (only if OHLCV is available, else 0)
        for src in CANDLE_DELTA_SOURCES:
            curr_val = feat.get(src, 0.0)
            prev_val = prev.get(src, curr_val) if prev else curr_val
            if prev_val is None:
                prev_val = curr_val
            feat[f'd_{src}'] = float(curr_val) - float(prev_val)

        # Phase 1 derived features (forensic-validated, match pretrainer)
        prev_feats = self._prev_snapshots.get(ticker, {})
        # slope_decel: change in slope over lookback (approximated by bar-over-bar)
        prev_wave_slope = prev_feats.get('wave_slope', feat.get('wave_slope', 0))
        prev_current_slope = prev_feats.get('current_slope', feat.get('current_slope', 0))
        feat['slope_decel_wave'] = feat.get('wave_slope', 0) - prev_wave_slope
        feat['slope_decel_current'] = feat.get('current_slope', 0) - prev_current_slope
        # sigma_divergence (orthogonal timeframes)
        feat['sigma_divergence'] = feat.get('sigma_tide', 0) - feat.get('sigma_wave', 0)
        # complacency_index: RSI vs slope decel
        rsi_norm = (feat.get('rsi_value', 50) - 50.0) / 50.0
        sd_norm = max(-1, min(1, feat['slope_decel_wave'] * 50.0))
        feat['complacency_index'] = rsi_norm - sd_norm
        # RSI zones
        rsi_val = feat.get('rsi_value', 50)
        feat['rsi_extreme_zone'] = int(rsi_val > 80)
        feat['rsi_trap_zone'] = int(65 <= rsi_val <= 75)
        # RSI bearish divergence (simplified: compare with stored max)
        prev_rsi_max = prev_feats.get('_rsi_rolling_max', rsi_val)
        new_rsi_max = max(rsi_val, prev_rsi_max * 0.99)  # Slow decay
        feat['rsi_bearish_div'] = int(rsi_val < new_rsi_max - 2.0)

        # ── Challenger v2: Derived features (instant + OHLCV + historical) ──
        self._compute_derived_features(feat, ticker, ohlcv)

        # Store current as previous for next bar (only if NOT using an explicit prev_snapshot)
        if prev_snapshot is None:
            prev_store = {src: feat.get(src, 0.0) for src in DELTA_SOURCES}
            prev_store['wave_slope'] = feat.get('wave_slope', 0)
            prev_store['current_slope'] = feat.get('current_slope', 0)
            prev_store['_rsi_rolling_max'] = new_rsi_max
            # Also store candle delta sources if available
            for src in CANDLE_DELTA_SOURCES:
                prev_store[src] = feat.get(src, 0.0)
            self._prev_snapshots[ticker] = prev_store

        # Cache feature dict
        self._feature_cache[ticker] = (snapshot, feat)

        return feat

    def score(
        self,
        head_name: str,
        ticker: str,
        snapshot: ChannelSnapshot,
        prev_snapshot: Optional[ChannelSnapshot] = None,
        ohlcv: dict | None = None,
    ) -> Optional[HeadScore]:
        """Score a snapshot with one head.

        Args:
            ohlcv: Optional dict with keys {open, high, low, close, volume}
                   for the current bar. Enables Challenger v2 derived features.
                   Without OHLCV, derived features default to 0.0.
        """
        self._ensure_loaded()

        if head_name not in self._models:
            return None

        model_dict = self._models[head_name]
        xgb_model = model_dict['model']
        feature_cols = model_dict['feature_cols']
        threshold = model_dict.get('threshold', 0.5)

        # Update bar history buffer for multi-bar features
        self._update_bar_history(ticker, ohlcv)

        feat = self._snapshot_to_features(ticker, snapshot, prev_snapshot, ohlcv)
        X = np.array([[feat.get(f, 0) for f in feature_cols]])

        try:
            prob = float(xgb_model.predict_proba(X)[0][1])
        except Exception as e:
            logger.error(f"HeadScorer: {head_name} predict failed for {ticker}: {e}")
            return None

        return HeadScore(
            head=head_name,
            probability=round(prob, 4),
            threshold=threshold,
            triggered=prob >= threshold,
            description=HEAD_DESCRIPTIONS.get(head_name, ''),
        )

    def score_all(
        self,
        ticker: str,
        snapshot: ChannelSnapshot,
        prev_snapshot: Optional[ChannelSnapshot] = None,
        ohlcv: dict | None = None,
    ) -> dict[str, HeadScore]:
        """Score with ALL loaded heads.

        Args:
            ohlcv: Optional dict with keys {open, high, low, close, volume}.
        """
        self._ensure_loaded()

        # Update bar history once (not per-head)
        self._update_bar_history(ticker, ohlcv)

        results = {}
        for head_name in self._models:
            result = self._score_internal(head_name, ticker, snapshot, prev_snapshot, ohlcv)
            if result is not None:
                results[head_name] = result
        return results

    def _score_internal(
        self,
        head_name: str,
        ticker: str,
        snapshot: ChannelSnapshot,
        prev_snapshot: Optional[ChannelSnapshot] = None,
        ohlcv: dict | None = None,
    ) -> Optional[HeadScore]:
        """Internal scoring that skips bar history update (already done by caller)."""
        if head_name not in self._models:
            return None

        model_dict = self._models[head_name]
        xgb_model = model_dict['model']
        feature_cols = model_dict['feature_cols']
        threshold = model_dict.get('threshold', 0.5)

        feat = self._snapshot_to_features(ticker, snapshot, prev_snapshot, ohlcv)
        X = np.array([[feat.get(f, 0) for f in feature_cols]])

        try:
            prob = float(xgb_model.predict_proba(X)[0][1])
        except Exception as e:
            logger.error(f"HeadScorer: {head_name} predict failed for {ticker}: {e}")
            return None

        return HeadScore(
            head=head_name,
            probability=round(prob, 4),
            threshold=threshold,
            triggered=prob >= threshold,
            description=HEAD_DESCRIPTIONS.get(head_name, ''),
        )

    def available_heads(self) -> list[str]:
        """List loaded head names."""
        self._ensure_loaded()
        return list(self._models.keys())
