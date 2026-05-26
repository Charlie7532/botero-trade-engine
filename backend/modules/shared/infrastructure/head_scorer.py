"""
HeadScorer — Infrastructure Implementation for Multi-Head ML Predictions
============================================================================
Loads trained XGBoost models from backend/models/ and emits P(positive)
for each head. Converts a ChannelSnapshot into the 48-feature vector
that the models expect.

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

import numpy as np

from backend.modules.shared.domain.entities.channel_snapshot import ChannelSnapshot
from backend.modules.shared.domain.ports.head_scorer_port import HeadScorerPort, HeadScore
from backend.modules.shared.domain.rules.trend_strength import compute_tsi, compute_adi
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "models"

# Feature columns — must match unified_pretrainer_v2.py exactly
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
]

# Delta features: bar-over-bar changes (forensic precursors)
# d_tide_slope is the strongest precursor (t=-80.96, ★★★ in 6/8 heads)
DELTA_SOURCES = [
    'sigma_wave', 'kalman_velocity', 'rsi_value', 'compression_ratio',
    'fear_level', 'vol_up_down_ratio', 'tide_slope', 'wave_accel',
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


class HeadScorer(HeadScorerPort):
    """Production multi-head scorer.

    Loads models lazily on first score() call. Caches profiles per-ticker.
    Falls back gracefully: if a head or profile is unavailable, returns None.
    """

    def __init__(self, models_dir: Path | None = None):
        self._models_dir = models_dir or MODELS_DIR
        self._models: dict[str, dict] = {}       # head_name -> {model, feature_cols, threshold, ...}
        self._profile_store = TickerProfileStore()
        self._profiles: dict[str, object] = {}   # ticker -> TickerProfile (cached)
        self._prev_snapshots: dict[str, dict] = {}  # ticker -> previous snapshot feature dict (for deltas)
        self._feature_cache: dict[str, tuple] = {}  # ticker -> (snapshot, feature_dict)
        self._loaded = False

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

    def _snapshot_to_features(
        self,
        ticker: str,
        snapshot: ChannelSnapshot,
        prev_snapshot: Optional[ChannelSnapshot] = None,
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

        # Store current as previous for next bar (only if NOT using an explicit prev_snapshot)
        if prev_snapshot is None:
            prev_store = {src: feat.get(src, 0.0) for src in DELTA_SOURCES}
            prev_store['wave_slope'] = feat.get('wave_slope', 0)
            prev_store['current_slope'] = feat.get('current_slope', 0)
            prev_store['_rsi_rolling_max'] = new_rsi_max
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
    ) -> Optional[HeadScore]:
        """Score a snapshot with one head."""
        self._ensure_loaded()

        if head_name not in self._models:
            return None

        model_dict = self._models[head_name]
        xgb_model = model_dict['model']
        feature_cols = model_dict['feature_cols']
        threshold = model_dict.get('threshold', 0.5)

        feat = self._snapshot_to_features(ticker, snapshot, prev_snapshot)
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
    ) -> dict[str, HeadScore]:
        """Score with ALL loaded heads."""
        self._ensure_loaded()
        results = {}
        for head_name in self._models:
            result = self.score(head_name, ticker, snapshot, prev_snapshot)
            if result is not None:
                results[head_name] = result
        return results

    def available_heads(self) -> list[str]:
        """List loaded head names."""
        self._ensure_loaded()
        return list(self._models.keys())
