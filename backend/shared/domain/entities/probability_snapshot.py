"""
ProbabilitySnapshot — Pure Quantitative Measurement Vector Entity
================================================================
Clean Architecture Domain Entity.

Represents a 100% empirical, objective physical measurement vector.
Contains ZERO narrative heuristic assumptions and ZERO action strings.

Temporal Dynamics reflect the TRUE data narration:
  - Current State Duration (tau)
  - Duration Bin (Fresh 1-3d, Mature 4-10d, Exhausted >10d)
  - Regime Inertia Probability: P(S_{t+1} == S_t | tau)
  - Duration-Conditioned Transition Matrix: P(S_{t+1} | S_t, tau)
"""
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class ProbabilitySnapshot:
    """Pure Quantitative Measurement Vector."""

    # 1. Physical State Discretization
    state_key: str  # e.g. "T+++|C---|<<"

    # 2. Probability Mass (Dynamic Volatility Triple Barrier Outcome)
    p_take_profit: float  # P(reaching +2.0x ATR before -1.0x ATR)
    p_stop_loss: float    # P(reaching -1.0x ATR first)
    p_timeout: float      # P(expiring at time horizon)

    # 3. Sample Volume & LLN Certainty Score
    sample_size_n: int     # Historical observations backing this state
    certainty_score: float # Sample credibility score in [0.0, 1.0]

    # 4. Expected Value & Asymmetry
    expected_gain_atr: float # Expected upside gain (% or ATR multiple)
    expected_loss_atr: float # Expected drawdown (% or ATR multiple)
    ev_net_atr: float        # Net Expected Value after 10bps friction
    rr_asymmetry: float      # Risk/Reward ratio: expected_gain / |expected_loss|

    # 5. True Temporal Dynamics (Empirical State Duration & Inertia)
    current_state_duration: int    # Daily bars spent in current state (tau)
    duration_bin: str              # "1-3d (Fresh)" | "4-10d (Mature)" | ">10d (Exhausted)"
    regime_inertia_prob: float     # P(S_{t+1} == S_t | tau) -> Prob of staying in state
    most_likely_next_state: str    # State with max P(S_{t+1} | S_t, tau) upon transition

    # 6. Duration-Conditioned Transition Matrix P(S_{t+1} | S_t, tau)
    transition_matrix: Optional[Dict[str, float]] = None
