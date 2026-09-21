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


def _derive_composite_divergence_regime(cones: List[TafCone]) -> str:
    """Synthesize per-station divergence_regime values into a composite market verdict.

    Uses majority voting of the 6 possible fact-store regimes, weighted by the
    EV acceleration vector to break ties.

    Returns one of:
      CONVERGENT_MOMENTUM_EXPANSION  — majority bull across all scales
      CONVERGENT_CONTRACTION_EXHAUSTION — majority bear across all scales
      STRUCTURAL_BULL_TACTICAL_DIP   — structural bull with tactical pullback
      STRUCTURAL_BEAR_TACTICAL_BOUNCE — structural bear with tactical rebound
      EQUILIBRIUM                     — no dominant regime (|ev_accel| < 0.005)
    """
    if not cones:
        return "EQUILIBRIUM"

    # Count per-station regimes
    counts: Dict[str, int] = {}
    for c in cones:
        r = c.divergence_regime
        counts[r] = counts.get(r, 0) + 1

    n = len(cones)
    n_bull = counts.get("FULL_CONVERGENT_BULL", 0)
    n_bear = counts.get("FULL_CONVERGENT_BEAR", 0)
    n_pullback = counts.get("STRUCTURAL_BULL_PULLBACK", 0)
    n_rebound = counts.get("TACTICAL_REBOUND_IN_BEAR", 0)

    # Majority threshold: > 40% of stations agreeing on one regime
    threshold = 0.40

    if n_bull / n >= threshold:
        return "CONVERGENT_MOMENTUM_EXPANSION"
    if n_bear / n >= threshold:
        return "CONVERGENT_CONTRACTION_EXHAUSTION"
    if (n_bull + n_pullback) / n >= threshold and n_pullback > 0:
        return "STRUCTURAL_BULL_TACTICAL_DIP"
    if (n_bear + n_rebound) / n >= threshold and n_rebound > 0:
        return "STRUCTURAL_BEAR_TACTICAL_BOUNCE"

    # Fallback: use aggregate EV acceleration as tiebreaker
    avg_ev_accel = sum(c.ev_acceleration for c in cones) / n
    if abs(avg_ev_accel) < 0.005:
        return "EQUILIBRIUM"
    elif avg_ev_accel > 0:
        return "STRUCTURAL_BULL_TACTICAL_DIP"
    else:
        return "STRUCTURAL_BEAR_TACTICAL_BOUNCE"


def compute_composite_taf(cones: List[TafCone]) -> Dict[str, Any]:
    """Aggregate individual station TAF cones into a composite market forecast.

    Returns a dict with:
    - Weighted averages of cone metrics
    - Station-by-station cone data
    - Composite divergence regime (synthesized from per-station regimes)
    - Overall market forecast direction
    """
    if not cones:
        return {
            "n_stations": 0,
            "composite_asymmetry": 1.0,
            "composite_convergence": 0.0,
            "composite_divergence_regime": "EQUILIBRIUM",
        }

    n = len(cones)
    avg_asym = sum(c.cone_asymmetry for c in cones) / n
    avg_conv = sum(c.convergence_score for c in cones) / n
    avg_ev_accel = sum(c.ev_acceleration for c in cones) / n

    # Count directional consensus
    n_bullish_scaling = sum(1 for c in cones if c.convergence_score > 0.02)
    n_bearish_scaling = sum(1 for c in cones if c.convergence_score < -0.02)
    n_convergent_bull = sum(1 for c in cones if c.divergence_regime == "FULL_CONVERGENT_BULL")
    n_convergent_bear = sum(1 for c in cones if c.divergence_regime == "FULL_CONVERGENT_BEAR")

    # Composite divergence regime
    composite_regime = _derive_composite_divergence_regime(cones)

    return {
        "n_stations": n,
        "composite_asymmetry": round(avg_asym, 4),
        "composite_convergence": round(avg_conv, 4),
        "composite_ev_acceleration": round(avg_ev_accel, 6),
        "composite_divergence_regime": composite_regime,
        "n_bullish_scaling": n_bullish_scaling,
        "n_bearish_scaling": n_bearish_scaling,
        "n_convergent_bull": n_convergent_bull,
        "n_convergent_bear": n_convergent_bear,
        "station_cones": {c.station: c.to_dict() for c in cones},
    }



# ── Lookup adapter registry (lazy-loaded) ────────────────────────────
_STATION_ADAPTERS: Dict[str, Any] = {}

_ADAPTER_REGISTRY = {
    "vix": ("backend.modules.entry_decision.domain.rules.vix_lookup", "vix_lookup"),
    "vvix": ("backend.modules.entry_decision.domain.rules.vvix_lookup", "vvix_lookup"),
    "pcr": ("backend.modules.entry_decision.domain.rules.pcr_lookup", "pcr_lookup"),
    "fg": ("backend.modules.entry_decision.domain.rules.fg_lookup", "fg_lookup"),
    "sv5_turbulence": ("backend.modules.entry_decision.domain.rules.sv5_turbulence_lookup", "sv5_turbulence_lookup"),
    "skew": ("backend.modules.entry_decision.domain.rules.skew_lookup", "skew_lookup"),
    "credit": ("backend.modules.entry_decision.domain.rules.credit_lookup", "credit_lookup"),
    "yield_curve": ("backend.modules.entry_decision.domain.rules.yield_curve_lookup", "yield_curve_lookup"),
    "rotation": ("backend.modules.entry_decision.domain.rules.rotation_lookup", "rotation_lookup"),
    "bsi": ("backend.modules.entry_decision.domain.rules.bsi_lookup", "bsi_lookup"),
    "dxy": ("backend.modules.entry_decision.domain.rules.dxy_lookup", "dxy_lookup"),
}


def _get_adapter(station: str):
    """Lazy-load and cache a station's lookup adapter."""
    if station not in _STATION_ADAPTERS:
        entry = _ADAPTER_REGISTRY.get(station)
        if not entry:
            return None
        import importlib
        mod = importlib.import_module(entry[0])
        _STATION_ADAPTERS[station] = getattr(mod, entry[1])
    return _STATION_ADAPTERS[station]


def compute_composite_taf_from_summaries(
    station_summaries: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute composite TAF from pre-computed station_summaries (from Compositor).

    This avoids re-calling ConvergenceCompositor.compute(). Each station's
    state_key is used to look up zz25/zz50/zz75 data from the in-memory
    fact store adapters.

    Args:
        station_summaries: Dict mapping station code → station summary dict.
                           Each must have a "state_key" field.
    """
    cones: List[TafCone] = []

    for station, summary in station_summaries.items():
        state_key = summary.get("state_key", "")
        if not state_key:
            continue

        adapter = _get_adapter(station)
        if adapter is None:
            continue

        state_data = adapter.states.get(state_key, {})
        if not state_data:
            continue

        zz25 = state_data.get("zz25", {})
        zz50 = state_data.get("zz50", {})
        zz75 = state_data.get("zz75", {})
        div = state_data.get("divergence_regime", "NEUTRAL")

        cone = compute_taf_cone(station, state_key, zz25, zz50, zz75, div)
        cones.append(cone)

    return compute_composite_taf(cones)

