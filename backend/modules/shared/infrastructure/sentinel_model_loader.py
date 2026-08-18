"""
Sentinel Model Loader — Infrastructure
==========================================
Loads the 2 Sentinel XGBoost models (PISO/TECHO) from disk.

Replaces HeadScorer (609 lines, 10 models) with ~30 lines, 2 models.

Models are lazy-loaded on first use and cached for the process lifetime.

Clean Architecture: Infrastructure layer. Only reads files.
"""
import logging
import pickle
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "models"


class SentinelModelLoader:
    """Loads Sentinel PISO and TECHO models from pkl files.

    Usage:
        loader = SentinelModelLoader()
        prob_piso = loader.score_piso(features_dict)
        prob_techo = loader.score_techo(features_dict)
    """

    def __init__(self, models_dir: Path | None = None):
        self._models_dir = models_dir or MODELS_DIR
        self._piso_model = None
        self._techo_model = None
        self._piso_features: list[str] = []
        self._techo_features: list[str] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Lazy-load both models on first use."""
        if self._loaded:
            return

        for name, attr_model, attr_feats in [
            ("piso", "_piso_model", "_piso_features"),
            ("techo", "_techo_model", "_techo_features"),
        ]:
            pkl_path = self._models_dir / f"sentinel_{name}_v1.pkl"
            if not pkl_path.exists():
                logger.warning(f"Sentinel {name} model not found at {pkl_path}")
                continue

            try:
                with open(pkl_path, "rb") as f:
                    model_dict = pickle.load(f)

                setattr(self, attr_model, model_dict["model"])
                setattr(self, attr_feats, model_dict.get("feature_cols", []))
                logger.info(
                    f"Sentinel {name}: loaded "
                    f"(threshold={model_dict.get('threshold', 0.5):.2f}, "
                    f"DSR={model_dict.get('dsr', 0):.2f}, "
                    f"features={len(model_dict.get('feature_cols', []))})"
                )
            except Exception as e:
                logger.error(f"Sentinel {name}: failed to load: {e}")

        self._loaded = True

    def is_available(self) -> bool:
        """True if at least one model is loaded."""
        self._ensure_loaded()
        return self._piso_model is not None or self._techo_model is not None

    def score_piso(self, features: dict) -> float:
        """P(near bottom) from the PISO model. Returns 0.0 if model unavailable."""
        self._ensure_loaded()
        if self._piso_model is None:
            return 0.0
        return self._score(self._piso_model, self._piso_features, features)

    def score_techo(self, features: dict) -> float:
        """P(near top) from the TECHO model. Returns 0.0 if model unavailable."""
        self._ensure_loaded()
        if self._techo_model is None:
            return 0.0
        return self._score(self._techo_model, self._techo_features, features)

    @staticmethod
    def _score(model, feature_cols: list[str], features: dict) -> float:
        """Score a feature dict with a model."""
        import numpy as np
        X = np.array([[features.get(f, 0.0) for f in feature_cols]])
        try:
            prob = float(model.predict_proba(X)[0][1])
            return round(prob, 4)
        except Exception:
            return 0.0
