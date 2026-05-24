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

HEAD_DESCRIPTIONS = {
    'long_entry': 'Good time to buy? (20d forward return > 0)',
    'swing_exit': 'Top of bullish leg? (Triple Barrier 10d)',
    'pullback_depth': 'Pullback will deepen? (Max DD 5d > -2%)',
    'trend_reversal': 'Macro trend dying? (TSI drops >50 → <30 in 60d)',
    'short_entry': 'Good time to short? (20d forward return < 0)',
    'short_cover': 'Bottom of bearish leg? (Inverted TB 10d)',
    'bounce_height': 'Bounce will go higher? (Max runup 5d > +2%)',
    'trend_recovery': 'Bearish trend ending? (TSI rises <30 → >60 in 60d)',
}


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

    def _snapshot_to_features(self, ticker: str, snapshot: ChannelSnapshot) -> dict:
        """Convert ChannelSnapshot to feature dict matching model expectations."""
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

        return feat

    def score(
        self,
        head_name: str,
        ticker: str,
        snapshot: ChannelSnapshot,
    ) -> Optional[HeadScore]:
        """Score a snapshot with one head."""
        self._ensure_loaded()

        if head_name not in self._models:
            return None

        model_dict = self._models[head_name]
        xgb_model = model_dict['model']
        feature_cols = model_dict['feature_cols']
        threshold = model_dict.get('threshold', 0.5)

        feat = self._snapshot_to_features(ticker, snapshot)
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
    ) -> dict[str, HeadScore]:
        """Score with ALL loaded heads."""
        self._ensure_loaded()
        results = {}
        for head_name in self._models:
            result = self.score(head_name, ticker, snapshot)
            if result is not None:
                results[head_name] = result
        return results

    def available_heads(self) -> list[str]:
        """List loaded head names."""
        self._ensure_loaded()
        return list(self._models.keys())
