"""
Sigma-Overflow Validation Module
=================================
Validates empirical ±3σ statistical tail overflows across all 11 METAR stations
for dimensions D1 (Level), D2 (3d Velocity), and D3 (std(2)/std(10) Instability).

Rule:
- Pure software layer. Fact stores are UNTOUCHED.
- Values within ±3σ return (None, None).
- Values > +3σ return (round(z_score, 2), "UPPER").
- Values < -3σ return (round(z_score, 2), "LOWER").
"""
from typing import Dict, Tuple, Optional

STATION_MU_SIGMA: Dict[str, Dict[str, Tuple[float, float]]] = {
    "vix": {
        "d1": (19.4419, 7.7300),
        "d2": (-0.0012, 2.5911),
        "d3": (0.5399, 0.4583),
    },
    "vvix": {
        "d1": (93.4701, 16.3885),
        "d2": (0.0295, 8.7782),
        "d3": (0.5268, 0.4535),
    },
    "pcr": {
        "d1": (0.9445, 0.1747),
        "d2": (0.0, 0.1765),
        "d3": (0.7357, 0.5432),
    },
    "fg": {
        "d1": (48.8497, 21.0618),
        "d2": (-0.0119, 8.9751),
        "d3": (0.4525, 0.4315),
    },
    "sv5_turbulence": {
        "d1": (7.0381, 3.9006),
        "d2": (0.0066, 2.5386),
        "d3": (0.3924, 0.5172),
    },
    "skew": {
        "d1": (132.1308, 11.9337),
        "d2": (0.0066, 5.3562),
        "d3": (0.5709, 0.4866),
    },
    "credit": {
        "d1": (0.6241, 0.0502),
        "d2": (0.0001, 0.0064),
        "d3": (0.5344, 0.4325),
    },
    "yield_curve": {
        "d1": (1.3942, 1.2675),
        "d2": (-0.0001, 0.1506),
        "d3": (0.4868, 0.4206),
    },
    "rotation": {
        "d1": (0.5301, 2.4011),
        "d2": (0.0006, 0.6358),
        "d3": (0.5065, 0.4118),
    },
    "bsi": {
        "d1": (56.6184, 20.7608),
        "d2": (0.0014, 14.8147),
        "d3": (0.4936, 0.4375),
    },
    "dxy": {
        "d1": (97.4445, 14.0207),
        "d2": (-0.0044, 0.8609),
        "d3": (0.4854, 0.4207),
    },
}


def validate_overflow(station: str, dim: str, value: Optional[float]) -> Tuple[Optional[float], Optional[str]]:
    """
    Validates whether a specific station and dimension value exceeds ±3σ.
    Returns:
        (sigma_depth, overflow_flag) where:
        - sigma_depth: float representing distance in sigma units (e.g. 8.1 for 8.1σ)
        - overflow_flag: "UPPER" | "LOWER" | None
    """
    if value is None:
        return None, None
    st_data = STATION_MU_SIGMA.get(station.lower())
    if not st_data:
        return None, None
    dim_data = st_data.get(dim.lower())
    if not dim_data:
        return None, None
    mu, sigma = dim_data
    if sigma <= 0:
        return None, None

    z_score = (value - mu) / sigma
    if z_score > 3.0:
        return round(float(z_score), 2), "UPPER"
    elif z_score < -3.0:
        return round(float(z_score), 2), "LOWER"
    return None, None


def classify_overflow_tier(z_score: Optional[float]) -> Tuple[int, str, str]:
    """
    Classify absolute sigma distance into standardized 5-tier hazard scale.

    Scale (from overflow_taxonomy.md):
        Tier 1 (3σ - 4σ): OVERFLOW_MODERADO (WARNING)
        Tier 2 (4σ - 5σ): OVERFLOW_EXTREMO (CRITICAL)
        Tier 3 (5σ - 7σ): BLOW_OFF_SEVERE (EMERGENCY)
        Tier 4 (7σ - 10σ): BLOW_OFF_EXTREME (CATASTROPHIC)
        Tier 5 (>= 10σ): BLOW_OFF_SYSTEMIC (SYSTEMIC)

    Returns:
        (tier_level, hazard_type, severity)
        tier_level: 0 (Normal < 3σ), 1 (T1), 2 (T2), 3 (T3), 4 (T4), 5 (T5)
    """
    if z_score is None:
        return 0, "NORMAL", "NORMAL"
    abs_z = abs(z_score)
    if abs_z >= 10.0:
        return 5, "BLOW_OFF_SYSTEMIC", "SYSTEMIC"
    elif abs_z >= 7.0:
        return 4, "BLOW_OFF_EXTREME", "CATASTROPHIC"
    elif abs_z >= 5.0:
        return 3, "BLOW_OFF_SEVERE", "EMERGENCY"
    elif abs_z >= 4.0:
        return 2, "OVERFLOW_EXTREMO", "CRITICAL"
    elif abs_z >= 3.0:
        return 1, "OVERFLOW_MODERADO", "WARNING"
    return 0, "NORMAL", "NORMAL"


def get_overflow_tier(station: str, dim: str, value: Optional[float]) -> int:
    """Convenience helper returning integer Tier (0-5) directly."""
    if value is None:
        return 0
    st_data = STATION_MU_SIGMA.get(station.lower())
    if not st_data:
        return 0
    dim_data = st_data.get(dim.lower())
    if not dim_data:
        return 0
    mu, sigma = dim_data
    if sigma <= 0:
        return 0
    z_score = (value - mu) / sigma
    tier, _, _ = classify_overflow_tier(z_score)
    return tier

