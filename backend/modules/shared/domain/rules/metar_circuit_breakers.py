"""
METAR Circuit Breakers — Pure Domain (No I/O)
==============================================
Extreme market events with validated forward returns at tactical horizons (1d, 3d, 5d).
Circuit Breakers operate as priority overrides — when active, they inform the EntryGate
that extreme conditions are present.

All thresholds and WR values are from empirical validation on SPY 1993-2026.
Each alert carries its own Confidence Card embedded in the dataclass.

Status: HYPOTHESIS (Grade D) — unconditional forward returns, not purged-validated.
Requires DSR pipeline for promotion to VALIDATED.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CircuitBreakerAlert:
    """A single active circuit breaker with its statistical backing."""

    name: str
    """Identifier: CB_CREDIT_PANIC, CB_VVIX_EXTREME, etc."""

    condition: str
    """Human-readable condition: 'CREDIT D2 < P2.28', 'VVIX > 140', etc."""

    signal_type: str
    """BULLISH (buy signal) or BEARISH (sell signal)."""

    wr_1d: float
    """Win Rate at 1 day horizon (%)."""

    wr_3d: float
    """Win Rate at 3 day horizon (%)."""

    wr_5d: float
    """Win Rate at 5 day horizon (%)."""

    n_historical: int
    """Historical sample size."""

    optimal_horizon: str
    """Best horizon for this CB: '1-3d' or '3-5d'."""

    confidence_grade: str
    """DSR Grade. Currently D for all (unconditional, not purged-validated)."""

    note: str = ""
    """Operational notes."""


# ═══════════════════════════════════════════════════════════════
# Circuit Breaker Registry (validated 2026-08-05)
# ═══════════════════════════════════════════════════════════════

_CB_REGISTRY = {
    "CB_CREDIT_PANIC": {
        "name": "CB_CREDIT_PANIC",
        "condition": "CREDIT D2 < P2.28 (extreme credit velocity collapse)",
        "signal_type": "BULLISH",
        "wr_1d": 64.9, "wr_3d": 71.2, "wr_5d": 65.8,
        "n_historical": 111,
        "optimal_horizon": "1-3d",
        "confidence_grade": "D",
        "note": "Fastest CB. Peak WR at 3d (71.2%), fades at 5d. "
                "Institutional credit margin calls trigger immediate rebound.",
    },
    "CB_VVIX_EXTREME": {
        "name": "CB_VVIX_EXTREME",
        "condition": "VVIX > 140 (extreme dealer hedging squeeze)",
        "signal_type": "BULLISH",
        "wr_1d": 61.9, "wr_3d": 69.8, "wr_5d": 74.6,
        "n_historical": 63,
        "optimal_horizon": "3-5d",
        "confidence_grade": "D",
        "note": "Scales with time: 62% → 70% → 75%. "
                "Dealer hedging unwind takes 3-5 days to fully resolve.",
    },
    "CB_BSI_REVERSAL": {
        "name": "CB_BSI_REVERSAL",
        "condition": "BSI > +3σ (Δ S5TW > +29pp single-day breadth shock)",
        "signal_type": "BULLISH",
        "wr_1d": 61.3, "wr_3d": 64.5, "wr_5d": 67.7,
        "n_historical": 31,
        "optimal_horizon": "3-5d",
        "confidence_grade": "D",
        "note": "N=31 — near minimum threshold. Seller capitulation shock. "
                "Builds steadily over 5 days.",
    },
    "CB_FEAR_CAPITULATION": {
        "name": "CB_FEAR_CAPITULATION",
        "condition": "FG < 10 (extreme retail fear index)",
        "signal_type": "BULLISH",
        "wr_1d": 53.3, "wr_3d": 61.5, "wr_5d": 60.7,
        "n_historical": 135,
        "optimal_horizon": "3-5d",
        "confidence_grade": "D",
        "note": "USELESS at 1d (53.3% ≈ coin flip). Needs 3+ days. "
                "Retail fear is a lagging indicator of institutional activity.",
    },
    "CB_SKEW_UNHEDGED": {
        "name": "CB_SKEW_UNHEDGED",
        "condition": "SKEW < 110 (tail risk panic cleared)",
        "signal_type": "BULLISH",
        "wr_1d": 56.2, "wr_3d": 58.9, "wr_5d": 60.4,
        "n_historical": 331,
        "optimal_horizon": "3-5d",
        "confidence_grade": "D",
        "note": "Weakest CB. Marginal edge across all horizons. "
                "High N but low WR → low conviction.",
    },
    "CB_YIELD_INVERTED": {
        "name": "CB_YIELD_INVERTED",
        "condition": "YIELD_SPREAD < 0 (inverted yield curve)",
        "signal_type": "REGIME_BIAS",
        "wr_1d": 55.9, "wr_3d": 59.0, "wr_5d": 61.6,
        "n_historical": 923,
        "optimal_horizon": "background",
        "confidence_grade": "D",
        "note": "NOT a tactical signal — this is a regime bias indicator. "
                "Use as context modifier, not as trade trigger.",
    },
}


def evaluate_circuit_breakers(
    vvix: Optional[float] = None,
    bsi: Optional[float] = None,
    skew: Optional[float] = None,
    fg: Optional[float] = None,
    credit_d2: Optional[float] = None,
    credit_d2_p2: Optional[float] = None,
    yield_spread: Optional[float] = None,
) -> list[CircuitBreakerAlert]:
    """
    Evaluate which circuit breakers are currently active.

    All inputs are current values (today or yesterday close).
    Returns list of active alerts sorted by priority (fastest first).

    Confidence Card: N variable (31-923), unconditional forward returns,
    Status: HYPOTHESIS (Grade D), Last Validated: 2026-08-05.
    """
    alerts: list[CircuitBreakerAlert] = []

    if credit_d2 is not None and credit_d2_p2 is not None:
        if credit_d2 < credit_d2_p2:
            alerts.append(CircuitBreakerAlert(**_CB_REGISTRY["CB_CREDIT_PANIC"]))

    if vvix is not None and vvix > 140:
        alerts.append(CircuitBreakerAlert(**_CB_REGISTRY["CB_VVIX_EXTREME"]))

    if bsi is not None and bsi > 3.0:
        alerts.append(CircuitBreakerAlert(**_CB_REGISTRY["CB_BSI_REVERSAL"]))

    if fg is not None and fg < 10:
        alerts.append(CircuitBreakerAlert(**_CB_REGISTRY["CB_FEAR_CAPITULATION"]))

    if skew is not None and skew < 110:
        alerts.append(CircuitBreakerAlert(**_CB_REGISTRY["CB_SKEW_UNHEDGED"]))

    if yield_spread is not None and yield_spread < 0:
        alerts.append(CircuitBreakerAlert(**_CB_REGISTRY["CB_YIELD_INVERTED"]))

    return alerts
