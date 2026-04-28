"""
ML Confidence Port — Model Abstraction
=========================================
Decouples the Pre-Trade Gate and StrategyCalibrator from concrete
ML implementations (XGBoost, LSTM, ensemble).

Implementors: xgboost_confidence_adapter.py, lstm_confidence_adapter.py (Phase 4)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class MLPrediction:
    """ML model prediction result."""
    confidence: float = 0.0      # 0-1 probability of profitable outcome
    model_name: str = ""         # "xgboost", "lstm", "ensemble"
    features_used: int = 0       # Number of features in the model
    feature_importance: dict = None  # Top features and their importance

    def __post_init__(self):
        if self.feature_importance is None:
            self.feature_importance = {}


class MLConfidencePort(ABC):
    """Port for ML model inference and training."""

    @abstractmethod
    def predict(self, features: pd.DataFrame) -> MLPrediction:
        """
        Predict trade outcome confidence from feature vector.

        Args:
            features: Single-row DataFrame with harmonized features.

        Returns:
            MLPrediction with confidence score and model metadata.
        """

    @abstractmethod
    def train(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        ticker: str,
        category: str,
    ) -> dict:
        """
        Train/retrain the model on labeled data.

        Args:
            X: Feature matrix from DataHarmonizer.build_ml_dataset().
            y: Labels from Oracle (1=profitable, 0=not).
            ticker: Ticker being trained.
            category: InvestmentCategory value.

        Returns:
            Training metrics (accuracy, AUC, feature importance).
        """

    @abstractmethod
    def is_trained(self, ticker: str, category: str) -> bool:
        """Check if a trained model exists for this ticker × category."""
