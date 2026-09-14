"""
TAF (Terminal Market Forecast) — Pure Domain Service
=====================================================
Computes the probability dispersion cone for each METAR station from
the fact store cross-scale vectors (zz25/zz50/zz75).

The cone reveals:
- Whether upside or downside grows faster with the horizon (asymmetry)
- Whether p_bull increases or decreases with scale (convergence)  
- Whether the movement scales structurally or exhausts (slope)

Rule 23 (AGENTS.md): TAF = stochastic probability matrix and horizon 
divergence forecast (P_bull, EV, Capital Velocity at 2.5%, 5.0%, 7.5% scales).

Clean Architecture: Pure Domain Service. No I/O — receives pre-computed
ScaleGuidance from lookups.
"""
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, List


@dataclass(frozen=True)
class TafCone:
    """Dispersion cone for a single METAR station at a single state."""
    station: str
    state_key: str

    # Per-scale data (the 3 points of the cone)
    p_bull_zz25: float
    p_bull_zz50: float
    p_bull_zz75: float

    ev_net_zz25: float
    ev_net_zz50: float
    ev_net_zz75: float

    e_ret_max_zz25: float
    e_ret_max_zz50: float
    e_ret_max_zz75: float

    e_ret_min_zz25: float
    e_ret_min_zz50: float
    e_ret_min_zz75: float

    e_days_zz25: float
    e_days_zz50: float
    e_days_zz75: float

    # Derived cone metrics
    cone_asymmetry: float       # |e_ret_max_zz75| / |e_ret_min_zz75|. >1 = upside dominates
    cone_slope: float           # (e_ret_max_zz75 - e_ret_max_zz25) / e_ret_max_zz25. Rate of widening
    convergence_score: float    # Direction of p_bull across scales: +1 = bullish scaling, -1 = bearish scaling
    ev_acceleration: float      # ev_zz75 - ev_zz25. Positive = EV grows with horizon

    # Divergence regime from fact store (already computed)
    divergence_regime: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_taf_cone(
    station: str,
    state_key: str,
    zz25: Dict[str, float],
    zz50: Dict[str, float],
    zz75: Dict[str, float],
    divergence_regime: str = "NEUTRAL",
) -> TafCone:
    """Compute the TAF dispersion cone from three scale guidance dicts.

    Args:
        station: Station code
        state_key: D1__D2__D3 state key
        zz25/zz50/zz75: Scale guidance dicts with p_bull, ev_net, e_ret_max, e_ret_min, e_days
        divergence_regime: Pre-classified regime from fact store
    """
    p25 = zz25.get("p_bull", 0.5)
    p50 = zz50.get("p_bull", 0.5)
    p75 = zz75.get("p_bull", 0.5)

    ev25 = zz25.get("ev_net", 0.0)
    ev50 = zz50.get("ev_net", 0.0)
    ev75 = zz75.get("ev_net", 0.0)

    max25 = zz25.get("e_ret_max", 0.0)
    max50 = zz50.get("e_ret_max", 0.0)
    max75 = zz75.get("e_ret_max", 0.0)

    min25 = zz25.get("e_ret_min", 0.0)
    min50 = zz50.get("e_ret_min", 0.0)
    min75 = zz75.get("e_ret_min", 0.0)

    days25 = zz25.get("e_days", 1.0)
    days50 = zz50.get("e_days", 3.0)
    days75 = zz75.get("e_days", 5.0)

    # Cone asymmetry: upside vs downside at structural scale
    abs_min75 = abs(min75) if min75 != 0 else 0.0001
    cone_asymmetry = abs(max75) / abs_min75 if abs_min75 > 0 else 1.0

    # Cone slope: how fast does the upside widen from tactical to structural
    abs_max25 = abs(max25) if max25 != 0 else 0.0001
    cone_slope = (max75 - max25) / abs_max25 if abs_max25 > 0 else 0.0

    # Convergence score: does p_bull increase or decrease with scale
    # +1 = strongly bullish scaling, -1 = strongly bearish scaling
    convergence_score = (p75 - p25) * 10  # Scale to roughly [-1, +1] range

    # EV acceleration: does EV grow with horizon
    ev_acceleration = ev75 - ev25

    return TafCone(
        station=station,
        state_key=state_key,
        p_bull_zz25=p25, p_bull_zz50=p50, p_bull_zz75=p75,
        ev_net_zz25=ev25, ev_net_zz50=ev50, ev_net_zz75=ev75,
        e_ret_max_zz25=max25, e_ret_max_zz50=max50, e_ret_max_zz75=max75,
        e_ret_min_zz25=min25, e_ret_min_zz50=min50, e_ret_min_zz75=min75,
        e_days_zz25=days25, e_days_zz50=days50, e_days_zz75=days75,
        cone_asymmetry=round(cone_asymmetry, 4),
        cone_slope=round(cone_slope, 4),
        convergence_score=round(convergence_score, 4),
        ev_acceleration=round(ev_acceleration, 6),
        divergence_regime=divergence_regime,
    )


def compute_composite_taf(cones: List[TafCone]) -> Dict[str, Any]:
    """Aggregate individual station TAF cones into a composite market forecast.

    Returns a dict with:
    - Weighted averages of cone metrics
    - Station-by-station cone data
    - Overall market forecast direction
    """
    if not cones:
        return {"n_stations": 0, "composite_asymmetry": 1.0, "composite_convergence": 0.0}

    n = len(cones)
    avg_asym = sum(c.cone_asymmetry for c in cones) / n
    avg_conv = sum(c.convergence_score for c in cones) / n
    avg_ev_accel = sum(c.ev_acceleration for c in cones) / n

    # Count directional consensus
    n_bullish_scaling = sum(1 for c in cones if c.convergence_score > 0.02)
    n_bearish_scaling = sum(1 for c in cones if c.convergence_score < -0.02)
    n_convergent_bull = sum(1 for c in cones if c.divergence_regime == "FULL_CONVERGENT_BULL")
    n_convergent_bear = sum(1 for c in cones if c.divergence_regime == "FULL_CONVERGENT_BEAR")

    return {
        "n_stations": n,
        "composite_asymmetry": round(avg_asym, 4),
        "composite_convergence": round(avg_conv, 4),
        "composite_ev_acceleration": round(avg_ev_accel, 6),
        "n_bullish_scaling": n_bullish_scaling,
        "n_bearish_scaling": n_bearish_scaling,
        "n_convergent_bull": n_convergent_bull,
        "n_convergent_bear": n_convergent_bear,
        "station_cones": {c.station: c.to_dict() for c in cones},
    }
