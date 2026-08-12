"""
METAR Observatory Rules — Pure Domain (No I/O)
===============================================
Probabilistic assessment of turning point conditions based on METAR station signals.

CRITICAL: ZigZag has massive lag (5-30 days) before confirming a turning point.
These rules emit PROBABILITY, not confirmation. Output is P(turning_point) and
direction_bias, used as one of N inputs to the EntryGate.

Confidence Card (Unified Model):
  N=619 | Purged 5-Fold CV + Expanding Window D1 | AUC 0.8387 OOS
  Window: t_-1 to t_-5 (predictive) | 10 METAR Stations + HYG/LQD
  Status: VALIDATED (Grade B) | Decay Check: 2026-11-05
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TurningPointAssessment:
    """Probabilistic assessment. NOT a ZIG/ZAG confirmation."""

    probability: float
    """0.0–1.0 — how similar current conditions are to historical turning points."""

    direction_bias: str
    """BOTTOM_FORMING, TOP_FORMING, or INDETERMINATE."""

    confidence_grade: str
    """DSR Grade: A, B, C, D. Current model: B."""

    drivers: tuple[str, ...]
    """Which stations are firing (e.g., ('VIX_D2', 'BSI', 'ROTATION_D2'))."""

    n_drivers_active: int
    """Convergence count — how many independent signals agree."""

    note: str = ""
    """Operational context (e.g., 'ZZ confirmation lag: 5-30d')."""


# ───────────────────────────────────────────────────────────────
# SHAP-derived thresholds (from GBM V2 + Purged 5-Fold CV)
# Confidence Card: AUC 0.8387 OOS, N=619, Grade B
# ───────────────────────────────────────────────────────────────

# BSI threshold: SHAP #1 unified. Positive = bullish breadth shock.
_BSI_BULLISH_THRESHOLD = 0.0     # Any positive delta in S5TW
_BSI_STRONG_THRESHOLD = 1.5     # ~1.5σ shock

# VIX D2 velocity: SHAP #2. Percentiles from empirical distribution.
_VIX_D2_ACCELERATION_P84 = 2.5   # Approximate P84 of diff(3) distribution
_VIX_D2_QUIET_P16 = -0.5         # Low volatility velocity (complacency)

# Rotation D2: SHAP #7. Negative = defensive rotation.
_ROTATION_DEFENSIVE_THRESHOLD = 0.0  # Negative = rotating to XLU/XLP

# Credit D2: SHAP #10 ZIG exclusive. Positive = credit rebounding.
_CREDIT_REBOUNDING_THRESHOLD = 0.0

# SV5T bimodal thresholds (from Phase 2 Study 2)
_SV5T_CALM_P16 = 3.64
_SV5T_HIGH_P84 = 10.73
_SV5T_EXTREME_P98 = 17.30

# VIX D1 level: SHAP #5 ZAG exclusive. Low = complacency.
_VIX_D1_COMPLACENCY_P16 = 0.1587  # Quantile rank


def assess_turning_probability(
    bsi_yesterday: float,
    vix_d2_yesterday: float,
    vix_d1_yesterday: float,
    rotation_d2_yesterday: float,
    credit_d2_yesterday: float,
    sv5t_level: float,
    yield_inverted: bool,
    credit_trend_60d: float,
) -> TurningPointAssessment:
    """
    Assess probability that a turning point is forming based on METAR signals.

    All inputs are from YESTERDAY (t_-1). The assessment is for TODAY.
    ZigZag confirmation will come 5-30 days later (if ever).

    Returns TurningPointAssessment with probability and direction_bias.
    """
    bottom_drivers: list[str] = []
    top_drivers: list[str] = []

    # ─── Bottom (ZIG) signals ───
    if bsi_yesterday > _BSI_BULLISH_THRESHOLD:
        bottom_drivers.append("BSI_POSITIVE")
    if vix_d2_yesterday > _VIX_D2_ACCELERATION_P84:
        bottom_drivers.append("VIX_D2_ACCELERATING")
    if rotation_d2_yesterday < _ROTATION_DEFENSIVE_THRESHOLD:
        bottom_drivers.append("ROTATION_DEFENSIVE")
    if credit_d2_yesterday > _CREDIT_REBOUNDING_THRESHOLD:
        bottom_drivers.append("CREDIT_REBOUNDING")
    if sv5t_level > _SV5T_HIGH_P84:
        bottom_drivers.append("SV5T_HIGH_CAPITULATION")
    if sv5t_level > _SV5T_EXTREME_P98:
        bottom_drivers.append("SV5T_EXTREME_GUARANTEED")

    # ─── Top (ZAG) signals ───
    if bsi_yesterday < -_BSI_BULLISH_THRESHOLD:
        top_drivers.append("BSI_NEGATIVE")
    if abs(vix_d2_yesterday) < abs(_VIX_D2_QUIET_P16):
        top_drivers.append("VIX_D2_QUIET_COMPLACENCY")
    if vix_d1_yesterday < _VIX_D1_COMPLACENCY_P16:
        top_drivers.append("VIX_D1_LOW_COMPLACENCY")
    if rotation_d2_yesterday > _ROTATION_DEFENSIVE_THRESHOLD:
        top_drivers.append("ROTATION_CYCLICAL")
    if sv5t_level < _SV5T_CALM_P16:
        top_drivers.append("SV5T_CALM_SILENT_DISTRIBUTION")

    # ─── Direction and probability ───
    n_bottom = len(bottom_drivers)
    n_top = len(top_drivers)

    if n_bottom > n_top and n_bottom >= 3:
        direction = "BOTTOM_FORMING"
        drivers = tuple(bottom_drivers)
        # Rough probability based on convergence count
        probability = min(0.5 + n_bottom * 0.10, 0.90)
    elif n_top > n_bottom and n_top >= 3:
        direction = "TOP_FORMING"
        drivers = tuple(top_drivers)
        probability = min(0.5 + n_top * 0.10, 0.90)
    else:
        direction = "INDETERMINATE"
        drivers = tuple(bottom_drivers + top_drivers)
        probability = 0.3 + max(n_bottom, n_top) * 0.05

    # ─── Regime context modifiers ───
    note_parts = []
    if yield_inverted:
        note_parts.append("YIELD_INVERTED (macro contraction bias)")
    if credit_trend_60d < -0.001:
        note_parts.append("CREDIT_CONTRACTING (deeper bottoms, bigger snap-backs)")
    elif credit_trend_60d > 0.001:
        note_parts.append("CREDIT_EXPANDING (healthier bottoms)")

    note = "ZZ confirmation lag: 5-30d. " + "; ".join(note_parts) if note_parts else "ZZ confirmation lag: 5-30d"

    return TurningPointAssessment(
        probability=round(probability, 3),
        direction_bias=direction,
        confidence_grade="B",
        drivers=drivers,
        n_drivers_active=max(n_bottom, n_top),
        note=note,
    )
