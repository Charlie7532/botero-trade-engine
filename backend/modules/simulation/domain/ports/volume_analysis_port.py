"""
Volume Analysis Port — Kalman/Wyckoff Abstraction
====================================================
Decouples simulation from the concrete KalmanVolumeTracker.

Implementor: wraps volume_intelligence/track_volume_dynamics.py
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class VolumeAnalysisResult:
    """Typed output from volume dynamics analysis."""
    wyckoff_state: str = "UNKNOWN"     # ACCUMULATION, DISTRIBUTION, MARKUP, etc.
    wyckoff_velocity: float = 0.0      # Rate of state change
    volume_quality: float = 0.0        # Volume quality score
    relative_volume: float = 1.0       # Current vs average volume


class VolumeAnalysisPort(ABC):
    """Port for Kalman-filtered volume analysis."""

    @abstractmethod
    def analyze(self, ohlc: pd.DataFrame) -> VolumeAnalysisResult:
        """
        Run Kalman volume tracking on OHLCV data.

        Args:
            ohlc: Canonical OHLCV DataFrame with DatetimeIndex UTC.

        Returns:
            VolumeAnalysisResult with Wyckoff state and quality metrics.
        """

    @abstractmethod
    def reset(self) -> None:
        """Reset internal Kalman filter state for a new ticker/window."""
