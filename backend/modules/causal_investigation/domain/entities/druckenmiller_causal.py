"""
Druckenmiller Causal Domain Entities
======================================
Defines CausalSignal enum, CausalEvidenceMatrix, and CounterVetoResult.
Supports Missing Vectors reporting and Data Completeness tracking.
"""
from dataclasses import dataclass, field
from typing import List
from enum import Enum


class CausalSignal(Enum):
    STRONG_BULLISH = "STRONG_BULLISH"
    MODERATE_BULLISH = "MODERATE_BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"


@dataclass(frozen=True)
class CausalEvidenceMatrix:
    """
    Multi-vector causal evidence matrix evaluated by Stanley Druckenmiller.

    5 Orthogonal Causal Vectors:
      1. options_darkpool_score: UW sweep count, bullish delta, darkpool accumulation (0-1)
      2. macro_liquidity_score: FRED Net Liquidity trend, yield curve slope, rate stance (0-1)
      3. insider_accumulation_score: Net insider buying, cluster buying (0-1)
      4. volume_reabsorption_score: S5/SV5 volume capitulation or re-absorption anomaly (0-1)
      5. narrative_momentum_score: FinBERT sector news sentiment velocity (0-1)
    """
    options_darkpool_score: float = 0.5
    macro_liquidity_score: float = 0.5
    insider_accumulation_score: float = 0.5
    volume_reabsorption_score: float = 0.5
    narrative_momentum_score: float = 0.5
    missing_vectors: List[str] = field(default_factory=list)
    data_completeness_pct: float = 100.0
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CounterVetoResult:
    """Represents Stanley Druckenmiller's counter-veto evaluation."""
    symbol: str
    is_overridden: bool
    causal_score: float
    conviction_level: str               # HIGH, MEDIUM, LOW, NONE
    sizing_factor: float                # 0.5x to 1.25x multiplier
    evidence_matrix: CausalEvidenceMatrix
    missing_vectors: List[str] = field(default_factory=list)
    data_completeness_pct: float = 100.0
    summary: str = ""
