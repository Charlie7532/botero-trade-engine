"""
Family Sequence Detector — Pure Domain Rules
===============================================
Two-layer intelligence for cross-station family analysis:

  Layer 1 (Per-Station):
    - Scale Gradient Score (SGS) from timing stores
    - Structural momentum (HH/HL/LH/LL) from fact store kinematic layer
    - Floor/Ceiling type classification

  Layer 2 (Cross-Station):
    - Inter-category sequencing: CAT1_MACRO → CAT2_SENTIMENT → CAT3_ACTION
    - Dynamic consensus ratios normalized by active stations
    - Causal phase emission based on validated study
      (docs/research/04_conjuncion_multi_estacion/)

Clean Architecture: Pure Domain Rules. No I/O. Receives pre-computed data
from compositor station_summaries and fact store lookups.

Empirical Foundation:
  - D2 direction (not flip event) discriminates: VIX D2>0 = short ON
    (PF 4.91-6.49), VIX D2<0 = short weak
  - Macro-driven (CAT1→CAT2→CAT3) = 95% of validated signals
  - Structural momentum HH at ceiling = 90.2% fall probability (Regla de Oro)
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum


# ── Category Assignments (Validated by conjuncion_derisking study) ──────

class Category(str, Enum):
    CAT1_MACRO = "CAT1_MACRO"          # Slow macro: credit, yield_curve, dxy
    CAT2_SENTIMENT = "CAT2_SENTIMENT"  # Derivative fear: vix, vvix, pcr, skew
    CAT3_ACTION = "CAT3_ACTION"        # Market action: bsi, sv5_turbulence, fg

STATION_CATEGORIES: Dict[str, Category] = {
    "credit":          Category.CAT1_MACRO,
    "yield_curve":     Category.CAT1_MACRO,
    "dxy":             Category.CAT1_MACRO,
    "vix":             Category.CAT2_SENTIMENT,
    "vvix":            Category.CAT2_SENTIMENT,
    "pcr":             Category.CAT2_SENTIMENT,
    "skew":            Category.CAT2_SENTIMENT,
    "bsi":             Category.CAT3_ACTION,
    "sv5_turbulence":  Category.CAT3_ACTION,
    "fg":              Category.CAT3_ACTION,
}

# D1 bins considered "extreme" (bearish stress for the station)
# Each station has specific bins that indicate stress direction
STATION_STRESS_BINS: Dict[str, List[int]] = {
    # VIX/VVIX/PCR/SKEW: high values = stress → bins 4,5
    "vix": [4, 5], "vvix": [4, 5], "pcr": [4, 5], "skew": [4, 5],
    # SV5_TURBULENCE: high = stress → bins 4,5
    "sv5_turbulence": [4, 5],
    # FG: low values = fear → bins 0,1
    "fg": [0, 1],
    # BSI: low values = weak breadth → bins 0,1
    "bsi": [0, 1],
    # Credit: low ratio = stress → bins 0,1
    "credit": [0, 1],
    # Yield Curve: low spread = inversion = stress → bins 0,1
    "yield_curve": [0, 1],
    # DXY: high = dollar strength = EM stress → bins 4,5
    "dxy": [4, 5],
}

# D1 bins considered "extreme" on the complacent/optimistic side
STATION_COMPLACENT_BINS: Dict[str, List[int]] = {
    "vix": [0, 1], "vvix": [0, 1], "pcr": [0, 1], "skew": [0, 1],
    "sv5_turbulence": [0, 1],
    "fg": [4, 5],
    "bsi": [4, 5],
    "credit": [4, 5],
    "yield_curve": [4, 5],
    "dxy": [0, 1],
}


# ── Output Dataclasses ──────────────────────────────────────────────────

@dataclass(frozen=True)
class StationFloorCeiling:
    """Per-station floor/ceiling classification using fact store kinematic layer."""
    station: str
    d1_bin: int
    d2_bin: int

    # Structural momentum from kinematic layer (if available)
    sm_p_continuation_up: Optional[float] = None    # P(HL) for up_legs at MIN→MIN
    sm_p_continuation_down: Optional[float] = None  # P(HH) for down_legs at MAX→MAX
    sm_ev_structural_up: Optional[float] = None
    sm_ev_structural_down: Optional[float] = None

    # Floor/Ceiling type inference
    floor_type: Optional[str] = None   # "STRUCTURAL" | "TACTICAL" | "TRAP"
    ceiling_type: Optional[str] = None # "STRUCTURAL" | "TACTICAL" | "TRAP"

    # Timing mode
    timing_mode: Optional[str] = None  # "ANTICIPATION" | "CONFIRMATION" | "NEUTRAL"


@dataclass(frozen=True)
class FamilySequenceReport:
    """Cross-station family intelligence report."""

    # Category consensus ratios (normalized by active stations per category)
    cat1_stress_ratio: float     # CAT1_MACRO: ratio of stations in stress bins
    cat2_fear_ratio: float       # CAT2_SENTIMENT: ratio of stations in fear bins
    cat3_capitulation_ratio: float  # CAT3_ACTION: ratio of stations in action bins

    n_cat1_active: int
    n_cat2_active: int
    n_cat3_active: int

    # Complacent ratios (mirror of stress)
    cat1_complacent_ratio: float
    cat2_complacent_ratio: float
    cat3_complacent_ratio: float

    # VIX D2 direction (validated as timing discriminator)
    vix_d2_building: bool        # True = D2>0 = fear building → short signal strong
    vix_d2_bin: Optional[int] = None

    # Causal phase
    phase: str = "NEUTRAL"
    # "MACRO_PRECURSOR"           — CAT1 stressed, CAT2/3 not yet
    # "VOLATILITY_ACCELERATING"   — CAT1+CAT2 stressed, CAT3 not yet
    # "CAPITULATION_BUILDING"     — All three stressed + VIX D2 building
    # "CAPITULATION_RESOLVING"    — All three stressed + VIX D2 resolving
    # "COMPLACENT_DISTRIBUTION"   — CAT1+CAT2 complacent, action weak
    # "NEUTRAL"                   — No clear pattern

    # Per-station floor/ceiling details
    station_details: Dict[str, StationFloorCeiling] = field(default_factory=dict)

    # Structural momentum signals (from Regla de Oro)
    hh_exit_amplify: bool = False   # Any station with P(HH) > 0.55 at ceiling
    ll_trap_veto: bool = False      # Any station with P(HL) < 0.45 at floor

    # Divergence regime consensus (E2.2)
    n_convergent_bull: int = 0     # Stations with FULL_CONVERGENT_BULL
    n_convergent_bear: int = 0     # Stations with FULL_CONVERGENT_BEAR
    n_tactical_rebound: int = 0    # Stations with TACTICAL_REBOUND_IN_BEAR
    n_structural_pullback: int = 0 # Stations with STRUCTURAL_BULL_PULLBACK

    # Structural floor/ceiling consensus (E2.2)
    n_floor_structural: int = 0    # Stations with floor_type=STRUCTURAL
    n_floor_trap: int = 0          # Stations with floor_type=TRAP
    n_ceiling_structural: int = 0  # Stations with ceiling_type=STRUCTURAL
    n_ceiling_trap: int = 0        # Stations with ceiling_type=TRAP

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "cat1_stress_ratio": round(self.cat1_stress_ratio, 4),
            "cat2_fear_ratio": round(self.cat2_fear_ratio, 4),
            "cat3_capitulation_ratio": round(self.cat3_capitulation_ratio, 4),
            "cat1_complacent_ratio": round(self.cat1_complacent_ratio, 4),
            "cat2_complacent_ratio": round(self.cat2_complacent_ratio, 4),
            "cat3_complacent_ratio": round(self.cat3_complacent_ratio, 4),
            "n_cat1_active": self.n_cat1_active,
            "n_cat2_active": self.n_cat2_active,
            "n_cat3_active": self.n_cat3_active,
            "vix_d2_building": self.vix_d2_building,
            "vix_d2_bin": self.vix_d2_bin,
            "phase": self.phase,
            "hh_exit_amplify": self.hh_exit_amplify,
            "ll_trap_veto": self.ll_trap_veto,
            "n_convergent_bull": self.n_convergent_bull,
            "n_convergent_bear": self.n_convergent_bear,
            "n_tactical_rebound": self.n_tactical_rebound,
            "n_structural_pullback": self.n_structural_pullback,
            "n_floor_structural": self.n_floor_structural,
            "n_floor_trap": self.n_floor_trap,
            "n_ceiling_structural": self.n_ceiling_structural,
            "n_ceiling_trap": self.n_ceiling_trap,
        }
        return d


# ── Layer 1: Per-Station Analysis ───────────────────────────────────────

def _classify_station(
    station: str,
    d1_bin: int,
    d2_bin: int,
    kinematic_data: Optional[Dict[str, Any]] = None,
) -> StationFloorCeiling:
    """Classify a single station's floor/ceiling type and timing mode.

    Args:
        station: Station code (e.g. "vix")
        d1_bin: Current D1 bin (0-5)
        d2_bin: Current D2 bin (0-4)
        kinematic_data: zigzag_kinematic dict from the fact store state
    """
    sm_p_up = sm_p_down = sm_ev_up = sm_ev_down = None
    floor_type = ceiling_type = None

    if kinematic_data:
        # Extract structural momentum from zz25 (tactical) as primary
        for scale in ["zz25", "zz50", "zz75"]:
            scale_data = kinematic_data.get(scale, {})
            sm = scale_data.get("structural_momentum")
            if sm:
                up = sm.get("up_legs", {})
                down = sm.get("down_legs", {})
                if sm_p_up is None and "p_continuation" in up:
                    sm_p_up = up["p_continuation"]
                    sm_ev_up = up.get("ev_structural_pct")
                if sm_p_down is None and "p_continuation" in down:
                    sm_p_down = down["p_continuation"]
                    sm_ev_down = down.get("ev_structural_pct")

    # Floor type classification
    stress_bins = STATION_STRESS_BINS.get(station, [])
    complacent_bins = STATION_COMPLACENT_BINS.get(station, [])

    if d1_bin in stress_bins:
        if sm_p_up is not None and sm_p_up < 0.45:
            floor_type = "TRAP"      # P(HL) < 0.45 → bear trap / false floor
        elif sm_p_up is not None and sm_p_up > 0.55:
            floor_type = "STRUCTURAL" # P(HL) > 0.55 → real structural floor
        else:
            floor_type = "TACTICAL"   # Intermediate

    if d1_bin in complacent_bins:
        if sm_p_down is not None and sm_p_down > 0.55:
            ceiling_type = "TRAP"      # P(HH) > 0.55 → Regla de Oro (90.2% fall)
        elif sm_p_down is not None and sm_p_down < 0.45:
            ceiling_type = "STRUCTURAL" # P(HH) < 0.45 → real structural ceiling
        else:
            ceiling_type = "TACTICAL"

    # Timing mode from D2
    # D2 bin 0,1 = negative velocity (building stress for inverted stations)
    # D2 bin 3,4 = positive velocity (building stress for normal stations)
    if d1_bin in stress_bins:
        if d2_bin in [3, 4]:
            timing_mode = "ANTICIPATION"   # Stress accelerating
        elif d2_bin in [0, 1]:
            timing_mode = "CONFIRMATION"   # Stress decelerating (past peak)
        else:
            timing_mode = "NEUTRAL"
    elif d1_bin in complacent_bins:
        if d2_bin in [0, 1]:
            timing_mode = "ANTICIPATION"   # Complacency building
        elif d2_bin in [3, 4]:
            timing_mode = "CONFIRMATION"
        else:
            timing_mode = "NEUTRAL"
    else:
        timing_mode = "NEUTRAL"

    return StationFloorCeiling(
        station=station,
        d1_bin=d1_bin,
        d2_bin=d2_bin,
        sm_p_continuation_up=sm_p_up,
        sm_p_continuation_down=sm_p_down,
        sm_ev_structural_up=sm_ev_up,
        sm_ev_structural_down=sm_ev_down,
        floor_type=floor_type,
        ceiling_type=ceiling_type,
        timing_mode=timing_mode,
    )


# ── Layer 2: Cross-Station Family Analysis ──────────────────────────────

def detect_family_sequence(
    station_summaries: Dict[str, Dict[str, Any]],
) -> FamilySequenceReport:
    """Detect causal family sequence from compositor station summaries.

    This is the main entry point. It receives station_summaries from the
    ConvergenceReport and produces a FamilySequenceReport with:
    - Per-category consensus ratios
    - Causal phase detection
    - Structural momentum signals (Regla de Oro)

    Args:
        station_summaries: Dict of station code → summary dict from compositor.
            Each summary must contain: d1_bin_numeric, d2_bin_numeric,
            and optionally zigzag_kinematic from the fact store state.
    """
    # Counters per category
    cat_stressed: Dict[Category, int] = {c: 0 for c in Category}
    cat_complacent: Dict[Category, int] = {c: 0 for c in Category}
    cat_active: Dict[Category, int] = {c: 0 for c in Category}

    station_details: Dict[str, StationFloorCeiling] = {}
    vix_d2_building = False
    vix_d2_bin = None
    hh_exit_amplify = False
    ll_trap_veto = False
    n_convergent_bull = 0
    n_convergent_bear = 0
    n_tactical_rebound = 0
    n_structural_pullback = 0
    n_floor_structural = 0
    n_floor_trap = 0
    n_ceiling_structural = 0
    n_ceiling_trap = 0

    for station, summary in station_summaries.items():
        if station not in STATION_CATEGORIES:
            continue

        cat = STATION_CATEGORIES[station]

        # Extract D1/D2 bins from summary
        d1_bin = summary.get("d1_bin_numeric")
        d2_bin = summary.get("d2_bin_numeric")
        if d1_bin is None or d2_bin is None:
            # Try parsing from state_key
            sk = summary.get("state_key", "")
            parts = sk.split("__")
            if len(parts) >= 3:
                try:
                    d1_bin = int(parts[0])
                    d2_bin = int(parts[1])
                except (ValueError, IndexError):
                    continue
            else:
                continue

        cat_active[cat] += 1

        # Check stress/complacent status
        stress_bins = STATION_STRESS_BINS.get(station, [])
        complacent_bins = STATION_COMPLACENT_BINS.get(station, [])

        if d1_bin in stress_bins:
            cat_stressed[cat] += 1
        if d1_bin in complacent_bins:
            cat_complacent[cat] += 1

        # VIX D2 direction (validated discriminator)
        if station == "vix":
            vix_d2_bin = d2_bin
            # D2 bins 3,4 = positive velocity = fear building
            vix_d2_building = d2_bin in [3, 4]

        # Kinematic layer from fact store
        kinematic = summary.get("zigzag_kinematic")
        sfc = _classify_station(station, d1_bin, d2_bin, kinematic)
        station_details[station] = sfc

        # Structural momentum signals
        if sfc.ceiling_type == "TRAP" and sfc.sm_p_continuation_down is not None:
            if sfc.sm_p_continuation_down > 0.55:
                hh_exit_amplify = True
        if sfc.floor_type == "TRAP" and sfc.sm_p_continuation_up is not None:
            if sfc.sm_p_continuation_up < 0.45:
                ll_trap_veto = True

        # E2.2: Divergence regime consensus
        div_regime = summary.get("divergence_regime", "")
        if div_regime == "FULL_CONVERGENT_BULL":
            n_convergent_bull += 1
        elif div_regime == "FULL_CONVERGENT_BEAR":
            n_convergent_bear += 1
        elif div_regime == "TACTICAL_REBOUND_IN_BEAR":
            n_tactical_rebound += 1
        elif div_regime == "STRUCTURAL_BULL_PULLBACK":
            n_structural_pullback += 1

        # E2.2: Floor/ceiling consensus
        if sfc.floor_type == "STRUCTURAL":
            n_floor_structural += 1
        elif sfc.floor_type == "TRAP":
            n_floor_trap += 1
        if sfc.ceiling_type == "STRUCTURAL":
            n_ceiling_structural += 1
        elif sfc.ceiling_type == "TRAP":
            n_ceiling_trap += 1

    # Category ratios (normalized by active count per category)
    def _ratio(stressed: int, active: int) -> float:
        return float(stressed / active) if active > 0 else 0.0

    cat1_stress = _ratio(cat_stressed[Category.CAT1_MACRO], cat_active[Category.CAT1_MACRO])
    cat2_fear = _ratio(cat_stressed[Category.CAT2_SENTIMENT], cat_active[Category.CAT2_SENTIMENT])
    cat3_cap = _ratio(cat_stressed[Category.CAT3_ACTION], cat_active[Category.CAT3_ACTION])

    cat1_comp = _ratio(cat_complacent[Category.CAT1_MACRO], cat_active[Category.CAT1_MACRO])
    cat2_comp = _ratio(cat_complacent[Category.CAT2_SENTIMENT], cat_active[Category.CAT2_SENTIMENT])
    cat3_comp = _ratio(cat_complacent[Category.CAT3_ACTION], cat_active[Category.CAT3_ACTION])

    # Phase detection (inter-category sequencing)
    phase = _detect_phase(cat1_stress, cat2_fear, cat3_cap,
                          cat1_comp, cat2_comp, cat3_comp,
                          vix_d2_building)

    return FamilySequenceReport(
        cat1_stress_ratio=cat1_stress,
        cat2_fear_ratio=cat2_fear,
        cat3_capitulation_ratio=cat3_cap,
        n_cat1_active=cat_active[Category.CAT1_MACRO],
        n_cat2_active=cat_active[Category.CAT2_SENTIMENT],
        n_cat3_active=cat_active[Category.CAT3_ACTION],
        cat1_complacent_ratio=cat1_comp,
        cat2_complacent_ratio=cat2_comp,
        cat3_complacent_ratio=cat3_comp,
        vix_d2_building=vix_d2_building,
        vix_d2_bin=vix_d2_bin,
        phase=phase,
        station_details=station_details,
        hh_exit_amplify=hh_exit_amplify,
        ll_trap_veto=ll_trap_veto,
        n_convergent_bull=n_convergent_bull,
        n_convergent_bear=n_convergent_bear,
        n_tactical_rebound=n_tactical_rebound,
        n_structural_pullback=n_structural_pullback,
        n_floor_structural=n_floor_structural,
        n_floor_trap=n_floor_trap,
        n_ceiling_structural=n_ceiling_structural,
        n_ceiling_trap=n_ceiling_trap,
    )


def _detect_phase(
    cat1_stress: float, cat2_fear: float, cat3_cap: float,
    cat1_comp: float, cat2_comp: float, cat3_comp: float,
    vix_d2_building: bool,
) -> str:
    """Detect causal phase from category ratios.

    Based on validated study (timing_derisking_REPORT.md):
    - Macro-driven = CAT1 first, then CAT2, then CAT3 (95% of signals)
    - VIX D2>0 (building) = optimal timing for short
    """
    # Stress thresholds: >= 0.5 means majority of category is stressed
    STRESS_THRESH = 0.50
    COMPLACENT_THRESH = 0.50

    # All three categories stressed
    all_stressed = (cat1_stress >= STRESS_THRESH and
                    cat2_fear >= STRESS_THRESH and
                    cat3_cap >= STRESS_THRESH)

    if all_stressed:
        if vix_d2_building:
            return "CAPITULATION_BUILDING"
        else:
            return "CAPITULATION_RESOLVING"

    # CAT1+CAT2 stressed, CAT3 not yet
    if cat1_stress >= STRESS_THRESH and cat2_fear >= STRESS_THRESH and cat3_cap < STRESS_THRESH:
        return "VOLATILITY_ACCELERATING"

    # Only CAT1 stressed → macro precursor
    if cat1_stress >= STRESS_THRESH and cat2_fear < STRESS_THRESH:
        return "MACRO_PRECURSOR"

    # Complacent side: distribution pattern
    if cat1_comp >= COMPLACENT_THRESH and cat2_comp >= COMPLACENT_THRESH:
        return "COMPLACENT_DISTRIBUTION"

    return "NEUTRAL"
