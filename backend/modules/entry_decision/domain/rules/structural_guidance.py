"""
Structural Momentum Guidance — Pure Domain Entity
====================================================
Typed dataclass that extracts and interprets the structural_momentum,
ftt_bull/bear_days, and prev_leg_domino layers from zigzag_kinematic.

Replaces untyped Dict[str, Any] navigation with first-class attributes.

Clean Architecture: Pure Domain entity. No I/O. Imported by lookup adapters
and consumed by family_sequence_detector and convergence_compositor.

Interpretation guide:
  - p_continuation_hl > 0.55  →  P(Higher Low)  →  Structural floor
  - p_continuation_hl < 0.45  →  P(Lower Low)   →  Trap floor (cuchillo cayendo)
  - p_continuation_hh > 0.55  →  P(Higher High)  →  Expansion / Regla de Oro
  - p_continuation_hh < 0.45  →  P(Lower High)   →  Structural ceiling (techo descendente)
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class StructuralMomentumGuidance:
    """Per-state structural momentum intelligence extracted from zigzag_kinematic."""

    # ── Structural Direction (from structural_momentum) ──
    p_continuation_hl: Optional[float]   # P(next MIN > current MIN) = P(Higher Low)
    p_continuation_hh: Optional[float]   # P(next MAX > current MAX) = P(Higher High)
    ev_structural_up: Optional[float]    # EV of MIN→MIN movement (% log)
    ev_structural_down: Optional[float]  # EV of MAX→MAX movement (% log)
    structural_trend: str                # "UPTREND" | "DOWNTREND" | "DIVERGENCE" | "RANGE" | "INSUFFICIENT_DATA"
    floor_type: str                      # "STRUCTURAL" | "TRAP" | "TACTICAL"
    ceiling_type: str                    # "STRUCTURAL" | "TRAP" | "TACTICAL"

    # ── Temporal Asymmetry (from kinematic scale metrics) ──
    ftt_bull_days: Optional[float]       # Median duration of bull legs
    ftt_bear_days: Optional[float]       # Median duration of bear legs
    time_asymmetry: Optional[float]      # ftt_bear / ftt_bull (< 1 = crashes faster)

    # ── Domino Context (from prev_leg_domino) ──
    domino_cascade_rate_t3: Optional[float]  # Cascade rate in extreme tercile
    domino_p_extreme: Optional[float]        # P(|prev_leg| > P90)

    # ── Magnitude Terciles (from structural_momentum) ──
    accum_ret_t3_strong_up: Optional[float]   # Mean accum ret, strong tercile (up_legs)
    accum_ret_t3_strong_down: Optional[float] # Mean accum ret, strong tercile (down_legs)

    # ── Metadata ──
    n_measured_up: Optional[int]         # N of up_legs measured
    n_measured_down: Optional[int]       # N of down_legs measured
    is_fallback_l1: bool = False         # True if inherited from D1 bin aggregate
    source_scale: str = "zz25"           # ZigZag scale of provenance


def _classify_trend(p_hl: Optional[float], p_hh: Optional[float]) -> str:
    """Classify structural trend from P(HL) and P(HH)."""
    if p_hl is None and p_hh is None:
        return "INSUFFICIENT_DATA"

    hl_up = (p_hl or 0.5) > 0.52
    hl_down = (p_hl or 0.5) < 0.48
    hh_up = (p_hh or 0.5) > 0.52
    hh_down = (p_hh or 0.5) < 0.48

    if hl_up and hh_up:
        return "UPTREND"      # HH + HL = classic bull
    if hl_down and hh_down:
        return "DOWNTREND"    # LH + LL = classic bear
    if hl_up and hh_down:
        return "RANGE"        # HL but LH = compression / range
    if hl_down and hh_up:
        return "DIVERGENCE"   # LL but HH = broadening / instability
    return "RANGE"            # Neutral zone


def _classify_floor(p_hl: Optional[float]) -> str:
    """Classify floor type from P(Higher Low)."""
    if p_hl is None:
        return "TACTICAL"
    if p_hl > 0.55:
        return "STRUCTURAL"   # Solid floor, high probability of HL
    if p_hl < 0.45:
        return "TRAP"         # False floor, high probability of LL
    return "TACTICAL"         # Intermediate


def _classify_ceiling(p_hh: Optional[float]) -> str:
    """Classify ceiling type from P(Higher High)."""
    if p_hh is None:
        return "TACTICAL"
    if p_hh > 0.55:
        return "TRAP"         # Regla de Oro: P(HH) > 0.55 at ceiling → 90.2% fall
    if p_hh < 0.45:
        return "STRUCTURAL"   # Real ceiling, expansion exhausted
    return "TACTICAL"


def extract_structural_guidance(
    zigzag_kinematic: Optional[Dict[str, Any]],
    preferred_scale: str = "zz25",
) -> Optional[StructuralMomentumGuidance]:
    """Extract StructuralMomentumGuidance from a zigzag_kinematic dict.

    Scans scales in order of preference, taking the first scale that has
    structural_momentum data. Falls through zz25 → zz50 → zz75.

    Args:
        zigzag_kinematic: The raw zigzag_kinematic dict from the fact store state.
        preferred_scale: Starting scale for the search. Default "zz25".

    Returns:
        StructuralMomentumGuidance or None if zigzag_kinematic is empty/None.
    """
    if not zigzag_kinematic or not isinstance(zigzag_kinematic, dict):
        return None

    # Scale search order based on preference
    scale_order = ["zz25", "zz50", "zz75"]
    if preferred_scale in scale_order:
        idx = scale_order.index(preferred_scale)
        scale_order = scale_order[idx:] + scale_order[:idx]

    # ── Extract structural_momentum from best available scale ──
    p_hl = p_hh = ev_up = ev_down = None
    n_up = n_down = None
    t3_up = t3_down = None
    source_scale = scale_order[0]
    is_fallback = False

    for scale in scale_order:
        scale_data = zigzag_kinematic.get(scale)
        if not scale_data or not isinstance(scale_data, dict):
            continue

        sm = scale_data.get("structural_momentum")
        if not sm or not isinstance(sm, dict):
            continue

        up = sm.get("up_legs", {})
        down = sm.get("down_legs", {})

        if p_hl is None and "p_continuation" in up:
            p_hl = up["p_continuation"]
            ev_up = up.get("ev_structural_pct")
            n_up = up.get("n_measured")
            terciles = up.get("terciles_pct", {})
            t3_up = terciles.get("t3_strong")
            source_scale = scale

        if p_hh is None and "p_continuation" in down:
            p_hh = down["p_continuation"]
            ev_down = down.get("ev_structural_pct")
            n_down = down.get("n_measured")
            terciles = down.get("terciles_pct", {})
            t3_down = terciles.get("t3_strong")
            if p_hl is None:
                source_scale = scale

        if p_hl is not None and p_hh is not None:
            break

    # ── Extract ftt_bull/bear_days from the source scale ──
    ftt_bull = ftt_bear = time_asym = None
    src_data = zigzag_kinematic.get(source_scale, {})
    if isinstance(src_data, dict):
        ftt_bull = src_data.get("ftt_bull_days")
        ftt_bear = src_data.get("ftt_bear_days")
        if ftt_bull and ftt_bear and ftt_bull > 0:
            time_asym = round(ftt_bear / ftt_bull, 4)

    # ── Extract prev_leg_domino from the source scale ──
    cascade_t3 = p_extreme = None
    domino = src_data.get("prev_leg_domino") if isinstance(src_data, dict) else None
    if domino and isinstance(domino, dict):
        p_extreme = domino.get("p_extreme_prev")
        terciles_dom = domino.get("terciles_domino", {})
        t3_data = terciles_dom.get("t3_large", {})
        cascade_t3 = t3_data.get("cascade_rate") if isinstance(t3_data, dict) else None

    # ── Check for is_fallback_l1 flag ──
    sm_data = src_data.get("structural_momentum", {}) if isinstance(src_data, dict) else {}
    if isinstance(sm_data, dict):
        is_fallback = sm_data.get("is_fallback_l1", False)

    # If no structural data at all, return minimal guidance
    if p_hl is None and p_hh is None and ftt_bull is None and cascade_t3 is None:
        return None

    return StructuralMomentumGuidance(
        p_continuation_hl=p_hl,
        p_continuation_hh=p_hh,
        ev_structural_up=ev_up,
        ev_structural_down=ev_down,
        structural_trend=_classify_trend(p_hl, p_hh),
        floor_type=_classify_floor(p_hl),
        ceiling_type=_classify_ceiling(p_hh),
        ftt_bull_days=ftt_bull,
        ftt_bear_days=ftt_bear,
        time_asymmetry=time_asym,
        domino_cascade_rate_t3=cascade_t3,
        domino_p_extreme=p_extreme,
        accum_ret_t3_strong_up=t3_up,
        accum_ret_t3_strong_down=t3_down,
        n_measured_up=n_up,
        n_measured_down=n_down,
        is_fallback_l1=is_fallback,
        source_scale=source_scale,
    )
