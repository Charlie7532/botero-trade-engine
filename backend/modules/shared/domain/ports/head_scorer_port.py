"""
HeadScorerPort — Domain Port for Multi-Head ML Predictions
=============================================================
ABC defining the contract for scoring observations with the
Multi-Head Pre-Trainer v2 models.

Each head answers a DIFFERENT question about the same market state:
  - swing_exit: "Should I trim this winning swing?"
  - pullback_depth: "Will this pullback deepen?"
  - trend_reversal: "Is the macro trend dying?"
  - etc.

Consumers (SwingGate, CIO, SpeculativeHub) call score() with the
relevant head name and a ChannelSnapshot.

Clean Architecture: Domain layer. No infrastructure dependencies.
"""
import abc
from dataclasses import dataclass
from typing import Optional

from backend.modules.shared.domain.entities.channel_snapshot import ChannelSnapshot


@dataclass
class HeadScore:
    """Result from a single head prediction."""
    head: str           # Head name (e.g., 'swing_exit')
    probability: float  # P(positive) from XGBoost: 0.0 → 1.0
    threshold: float    # Calibrated threshold from training
    triggered: bool     # probability >= threshold
    description: str    # Human-readable head description


class HeadScorerPort(abc.ABC):
    """Port for multi-head ML scoring."""

    @abc.abstractmethod
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
            head_name: Which head to use (e.g., 'swing_exit')
            ticker: Ticker symbol (needed for per-ticker TSI/ADI)
            snapshot: Current market state
            prev_snapshot: Optional previous market state (for stateless deltas)
            ohlcv: Optional dict {open, high, low, close, volume} for
                   current bar. Enables Challenger v2 derived features.

        Returns:
            HeadScore with probability, or None if head unavailable.
        """
        ...

    @abc.abstractmethod
    def score_all(
        self,
        ticker: str,
        snapshot: ChannelSnapshot,
        prev_snapshot: Optional[ChannelSnapshot] = None,
        ohlcv: dict | None = None,
    ) -> dict[str, HeadScore]:
        """Score a snapshot with ALL available heads.

        Args:
            ohlcv: Optional dict {open, high, low, close, volume}.

        Returns dict of head_name -> HeadScore.
        """
        ...

    @abc.abstractmethod
    def available_heads(self) -> list[str]:
        """List all loaded head names."""
        ...
