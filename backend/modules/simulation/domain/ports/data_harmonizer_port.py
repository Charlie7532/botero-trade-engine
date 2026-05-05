"""
Data Harmonizer Port — Interface for building ML-ready datasets.

Domain Use Cases depend on this ABC for feature engineering.
Implementations: DataHarmonizer (infrastructure/)
"""
from abc import ABC, abstractmethod

import pandas as pd


class DataHarmonizerPort(ABC):
    """Interface for building ML-ready datasets from vault data."""

    @abstractmethod
    def build_ml_dataset(self, ticker: str, tf: str) -> pd.DataFrame:
        """
        Build feature-enriched dataset for ML training/prediction.

        Returns:
            DataFrame with OHLCV + signal features, ready for ML.
            Empty DataFrame if insufficient data.
        """
        ...
