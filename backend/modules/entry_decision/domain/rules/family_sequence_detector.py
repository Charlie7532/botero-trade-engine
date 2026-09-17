"""
Family Sequence Detector — Pure Domain Rules
===============================================
Two-layer intelligence for cross-station family analysis:

  Layer 1 (Per-Station):
    - Scale Gradient Score (SGS) from timing stores
    - Structural momentum (HH/HL/LH/LL) from fact store kinematic layer
    - Floor/Ceiling type classification (from signal_discriminator)
    - Accumulation/Distribution context (from signal_discriminator)

  Layer 2 (Cross-Station):
    - Inter-category sequencing: CAT1_MACRO → CAT2_SENTIMENT → CAT3_ACTION
    - Dynamic consensus ratios normalized by active stations
    - Context consensus: accumulation/distribution across zones
    - Causal phase emission based on validated study
      (docs/research/04_conjuncion_multi_estacion/)

V2 additions:
  - Accumulation/distribution consensus from complacent+neutral zones
  - New phases: ACCUMULATION_CONFIRMED, DISTRIBUTION_STEALTH
  - Per-station context_class from classify_context()

Clean Architecture: Pure Domain Rules. No I/O. Receives pre-computed data
from compositor station_summaries and fact store lookups.

Empirical Foundation:
  - D2 direction (not flip event) discriminates: VIX D2>0 = short ON
    (PF 4.91-6.49), VIX D2<0 = short weak
  - Macro-driven (CAT1→CAT2→CAT3) = 95% of validated signals
  - Structural momentum HH at ceiling = 90.2% fall probability (Regla de Oro)
  - Accumulation in complacency: floor_hr=100%, EV=+0.066 (validated 306 states)
  - Distribution forming: ceil_hr=100%, EV=-0.072 (validated 23 states)
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

from backend.modules.entry_decision.domain.rules.station_profiles import (
    get_all_stress_bins, get_all_complacent_bins,
    get_all_floor_bins, get_all_ceiling_bins,
)


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
    "rotation":        Category.CAT1_MACRO,
    "bsi":             Category.CAT3_ACTION,
    "sv5_turbulence":  Category.CAT3_ACTION,
    "fg":              Category.CAT3_ACTION,
}

# D1 bins considered "extreme" (bearish stress for the station)
# Canonical source: station_profiles.py StationProfile.stress_bins
STATION_STRESS_BINS: Dict[str, List[int]] = get_all_stress_bins()

# D1 bins considered "extreme" on the complacent/optimistic side
# Canonical source: station_profiles.py StationProfile.complacent_bins
STATION_COMPLACENT_BINS: Dict[str, List[int]] = get_all_complacent_bins()

# Floor/Ceiling bins where signals physically fire (polarity & SKEW aware)
STATION_FLOOR_BINS: Dict[str, List[int]] = get_all_floor_bins()
STATION_CEILING_BINS: Dict[str, List[int]] = get_all_ceiling_bins()


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

    # Structural floor/ceiling consensus (E2.2) — backward-looking (structural_guidance)
    n_floor_structural: int = 0    # Stations with floor_type=STRUCTURAL
    n_floor_trap: int = 0          # Stations with floor_type=TRAP
    n_ceiling_structural: int = 0  # Stations with ceiling_type=STRUCTURAL
    n_ceiling_trap: int = 0        # Stations with ceiling_type=TRAP

    # Floor/ceiling quality (signal_discriminator concordance) — forward-looking evidence
    n_fq_structural: int = 0       # Stations with floor_quality=STRUCTURAL_FLOOR
    n_fq_trap: int = 0             # Stations with floor_quality=TRAP
    n_cq_structural: int = 0       # Stations with ceiling_quality=STRUCTURAL_CEILING
    n_cq_trap: int = 0             # Stations with ceiling_quality=BULL_TRAP

    # Accumulation/Distribution context (from classify_context)
    n_accumulation: int = 0        # Stations with ACCUMULATION_* in complacent/neutral
    n_distribution: int = 0        # Stations with DISTRIBUTION_* in complacent/neutral
    n_upleg: int = 0               # Stations in UPLEG (neutral zone)
    n_downleg: int = 0             # Stations in DOWNLEG (neutral zone)
    n_transition: int = 0          # Stations in TRANSITION

    # Per-station context classification (signal_discriminator output)
    station_context: Dict[str, str] = field(default_factory=dict)

    # Co-occurrence conviction (Phase 5 validated rules)
    # R1: ≥3 floors AND 0 traps = STRUCTURAL (p=0.014, zz75 HR=66.5%)
    # R3: n_upleg≥1 + n_floor_structural≥2 = MAX_CONVICTION (p=0.019, zz75 HR=71.2%)
    # R7: n_floor_trap > n_floor_structural AND n_floor_trap≥2 = TRAP_DOMINANT (SGS=-0.162)
    cooccurrence_conviction: str = "NONE"  # NONE | STRUCTURAL | MAX_CONVICTION | TRAP_DOMINANT

    # Validated station pairs (Phase 5: cross-category pairs with p<0.05)
    # VIX+SKEW both in stress: p=0.008, zz75 HR=87%, SGS=+0.218
    # PCR+YIELD_CURVE both in stress: p=0.001, zz75 HR=79.2%, SGS=+0.221
    # PCR+CREDIT both in stress: p=0.008, zz50 HR=88.2%
    active_pairs: List[str] = field(default_factory=list)

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
            "n_accumulation": self.n_accumulation,
            "n_distribution": self.n_distribution,
            "n_upleg": self.n_upleg,
            "n_downleg": self.n_downleg,
            "n_transition": self.n_transition,
            "n_fq_structural": self.n_fq_structural,
            "n_fq_trap": self.n_fq_trap,
            "n_cq_structural": self.n_cq_structural,
            "n_cq_trap": self.n_cq_trap,
            "station_context": self.station_context,
            "cooccurrence_conviction": self.cooccurrence_conviction,
            "active_pairs": self.active_pairs,
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
    floor_bins = STATION_FLOOR_BINS.get(station, STATION_STRESS_BINS.get(station, []))
    ceiling_bins = STATION_CEILING_BINS.get(station, STATION_COMPLACENT_BINS.get(station, []))

    if d1_bin in floor_bins:
        if sm_p_up is not None and sm_p_up < 0.45:
            floor_type = "TRAP"      # P(HL) < 0.45 → bear trap / false floor
        elif sm_p_up is not None and sm_p_up > 0.55:
            floor_type = "STRUCTURAL" # P(HL) > 0.55 → real structural floor
        else:
            floor_type = "TACTICAL"   # Intermediate

    if d1_bin in ceiling_bins:
        if sm_p_down is not None and sm_p_down > 0.55:
            ceiling_type = "TRAP"      # P(HH) > 0.55 → Regla de Oro (90.2% fall)
        elif sm_p_down is not None and sm_p_down < 0.45:
            ceiling_type = "STRUCTURAL" # P(HH) < 0.45 → real structural ceiling
        else:
            ceiling_type = "TACTICAL"

    # Timing mode from D2
    # At floor:
    #   For low-floor stations (SKEW, or INVERTED stations where floor is at D1=0,1):
    #     D2 in [0, 1] = falling deeper into capitulation (ANTICIPATION)
    #     D2 in [3, 4] = rebounding UP out of capitulation (CONFIRMATION)
    #   For high-floor stations (VIX, PCR where floor is at D1=4,5):
    #     D2 in [3, 4] = panic accelerating (ANTICIPATION)
    #     D2 in [0, 1] = panic decelerating / past peak (CONFIRMATION)
    # At ceiling:
    #   For high-ceiling stations (SKEW where ceiling is at D1=4,5):
    #     D2 in [3, 4] = insurance bid accelerating (ANTICIPATION)
    #     D2 in [0, 1] = insurance peak passed / crash unfolding (CONFIRMATION)
    #   For low-ceiling stations (complacency at D1=0,1):
    #     D2 in [0, 1] = complacency building (ANTICIPATION)
    #     D2 in [3, 4] = complacency breaking (CONFIRMATION)
    is_low_floor = any(b in (0, 1) for b in floor_bins)
    is_high_ceiling = any(b in (4, 5) for b in ceiling_bins)

    if d1_bin in floor_bins:
        if is_low_floor:
            if d2_bin in [0, 1]:
                timing_mode = "ANTICIPATION"
            elif d2_bin in [3, 4]:
                timing_mode = "CONFIRMATION"
            else:
                timing_mode = "NEUTRAL"
        else:
            if d2_bin in [3, 4]:
                timing_mode = "ANTICIPATION"
            elif d2_bin in [0, 1]:
                timing_mode = "CONFIRMATION"
            else:
                timing_mode = "NEUTRAL"
    elif d1_bin in ceiling_bins:
        if is_high_ceiling:
            if d2_bin in [3, 4]:
                timing_mode = "ANTICIPATION"
            elif d2_bin in [0, 1]:
                timing_mode = "CONFIRMATION"
            else:
                timing_mode = "NEUTRAL"
        else:
            if d2_bin in [0, 1]:
                timing_mode = "ANTICIPATION"
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

    # Context classification from signal_discriminator (accumulation/leg)
    n_accumulation = 0
    n_distribution = 0
    n_upleg = 0
    n_downleg = 0
    n_transition = 0
    station_context: Dict[str, str] = {}

    for station, summary in station_summaries.items():
        ctx_class = summary.get("context_class")
        if ctx_class:
            station_context[station] = ctx_class
            if ctx_class.startswith("ACCUMULATION"):
                n_accumulation += 1
            elif ctx_class.startswith("DISTRIBUTION"):
                n_distribution += 1
            elif ctx_class == "UPLEG":
                n_upleg += 1
            elif ctx_class == "DOWNLEG":
                n_downleg += 1
            elif ctx_class == "TRANSITION":
                n_transition += 1

    # Floor/ceiling quality from signal_discriminator (forward-looking concordance)
    n_fq_structural = 0
    n_fq_trap = 0
    n_cq_structural = 0
    n_cq_trap = 0
    for station, summary in station_summaries.items():
        fq = summary.get("floor_quality", "")
        if fq.startswith("STRUCTURAL"):
            n_fq_structural += 1
        elif fq == "TRAP":
            n_fq_trap += 1
        cq = summary.get("ceiling_quality", "")
        if cq.startswith("STRUCTURAL"):
            n_cq_structural += 1
        elif cq == "BULL_TRAP":
            n_cq_trap += 1

    # Phase detection (inter-category sequencing + accumulation context)
    phase = _detect_phase(cat1_stress, cat2_fear, cat3_cap,
                          cat1_comp, cat2_comp, cat3_comp,
                          vix_d2_building,
                          n_accumulation, n_distribution)

    # Co-occurrence conviction (Phase 5 validated rules)
    cooccurrence_conviction = _assess_cooccurrence(
        n_floor_structural, n_floor_trap, n_upleg,
    )

    # Validated station pairs
    active_pairs = _detect_validated_pairs(station_summaries)

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
        n_accumulation=n_accumulation,
        n_distribution=n_distribution,
        n_upleg=n_upleg,
        n_downleg=n_downleg,
        n_transition=n_transition,
        n_fq_structural=n_fq_structural,
        n_fq_trap=n_fq_trap,
        n_cq_structural=n_cq_structural,
        n_cq_trap=n_cq_trap,
        station_context=station_context,
        cooccurrence_conviction=cooccurrence_conviction,
        active_pairs=active_pairs,
    )


# ── Co-occurrence Rules (Phase 5 validated) ──────────────────────────────


def _assess_cooccurrence(
    n_floor_structural: int,
    n_floor_trap: int,
    n_upleg: int,
) -> str:
    """Assess co-occurrence conviction from validated empirical rules.

    Rules from Phase 5 multi-station co-occurrence study (Sep 2026):

    R7: Trap dominant (n_trap > n_structural AND n_trap >= 2)
        SGS = -0.162. HR: zz25=32.4%, zz50=32.4%, zz75=16.2%.
        Anti-scalable — the larger the scale, the more destructive.
        This is a SHORT signal, not a failed FLOOR.
        Priority: checked FIRST (trap cancels everything).

    R3: UPLEG + FLOOR + FLOOR (n_upleg >= 1 AND n_structural >= 2)
        p=0.019 (zz50), p=0.039 (zz75). HR: zz50=71.2%, zz75=72.7%.
        SGS = +0.151 — the highest of any pattern. Purely structural.
        Context: neutral stations in upleg + stressed stations show real floor.

    R1: Pure floor (n_structural >= 3 AND n_trap == 0)
        p=0.045 (zz50), p=0.014 (zz75). HR: zz50=61.9%, zz75=66.5%.
        SGS = +0.106. Signal strengthens with scale — confirmed structural.

    Returns: TRAP_DOMINANT | MAX_CONVICTION | STRUCTURAL | NONE
    """
    # R7: Trap dominant — checked first (trap cancels everything)
    if n_floor_trap > n_floor_structural and n_floor_trap >= 2:
        return "TRAP_DOMINANT"

    # R3: UPLEG + structural floors = maximum conviction
    if n_upleg >= 1 and n_floor_structural >= 2:
        return "MAX_CONVICTION"

    # R1: Pure floor without any traps
    if n_floor_structural >= 3 and n_floor_trap == 0:
        return "STRUCTURAL"

    return "NONE"


# ── Validated Station Pairs ──────────────────────────────────────────────

# Cross-category pairs with p < 0.05 at structural scale (zz75).
# Source: Phase 5 co-occurrence study, First-Passage Triple Barrier.
# pair_mode: "CO_STRESS" = both stations in stress_bins (default)
#            "DIVERGENT" = station_a in stress_bins, station_b in FLOOR_bins (e.g. VIX/PCR panic + SKEW capitulation)
_VALIDATED_PAIRS: List[Tuple[str, str, str, float, float, str]] = [
    # (station_a, station_b, pair_name, zz75_hr, zz75_p_value, pair_mode)
    ("vix",  "skew",        "VIX_SKEW",        0.870, 0.008, "DIVERGENT"),
    ("pcr",  "yield_curve", "PCR_YIELD_CURVE", 0.792, 0.001, "CO_STRESS"),
    ("pcr",  "skew",        "PCR_SKEW",        0.796, 0.006, "DIVERGENT"),
    ("pcr",  "credit",      "PCR_CREDIT",      0.824, 0.060, "CO_STRESS"),  # zz50 optimal (p=0.008)
    ("fg",   "sv5_turbulence", "FG_SV5T",       0.750, 0.029, "CO_STRESS"),
]


def _detect_validated_pairs(
    station_summaries: Dict[str, Any],
) -> List[str]:
    """Detect which validated station pairs are active.

    For CO_STRESS pairs: BOTH stations have D1 in their respective stress_bins.
    For DIVERGENT pairs: station_a in stress_bins, station_b in FLOOR_bins (e.g. panic in A + capitulation in B).
    Returns list of active pair names.
    """
    active = []
    for sta, stb, pair_name, _, _, pair_mode in _VALIDATED_PAIRS:
        d1_a = station_summaries.get(sta, {}).get("d1_bin_numeric")
        d1_b = station_summaries.get(stb, {}).get("d1_bin_numeric")
        if d1_a is None or d1_b is None:
            continue
        stress_a = STATION_STRESS_BINS.get(sta, [])
        if pair_mode == "DIVERGENT":
            bins_b = STATION_FLOOR_BINS.get(stb, [])
        else:
            bins_b = STATION_STRESS_BINS.get(stb, [])
        if d1_a in stress_a and d1_b in bins_b:
            active.append(pair_name)
    return active


def _detect_phase(
    cat1_stress: float, cat2_fear: float, cat3_cap: float,
    cat1_comp: float, cat2_comp: float, cat3_comp: float,
    vix_d2_building: bool,
    n_accumulation: int = 0,
    n_distribution: int = 0,
) -> str:
    """Detect causal phase from category ratios + accumulation context.

    Based on validated study (timing_derisking_REPORT.md):
    - Macro-driven = CAT1 first, then CAT2, then CAT3 (95% of signals)
    - VIX D2>0 (building) = optimal timing for short

    V2 additions:
    - ACCUMULATION_CONFIRMED: >3 stations in accumulation, no stress
    - DISTRIBUTION_STEALTH:   >2 stations in distribution, complacent
    """
    STRESS_THRESH = 0.34      # 1/3 minimum — allows 1-of-3 category detection
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

    # Only CAT2 stressed (fear without macro cause) → sentiment early warning
    if cat2_fear >= STRESS_THRESH and cat1_stress < STRESS_THRESH:
        return "EARLY_WARNING_SENTIMENT"

    # Only CAT3 stressed (action without fear or macro) → action early warning
    if cat3_cap >= STRESS_THRESH and cat1_stress < STRESS_THRESH and cat2_fear < STRESS_THRESH:
        return "EARLY_WARNING_ACTION"

    # Complacent side: check context FIRST (richer than binary ratio)
    # Accumulation confirmed: multiple stations showing institutional buying
    # with no stress present → market is loading underneath calm surface
    if n_accumulation >= 4 and cat1_stress < STRESS_THRESH:
        return "ACCUMULATION_CONFIRMED"

    # Distribution stealth: stations in complacent zone but distribute
    if cat1_comp >= COMPLACENT_THRESH and cat2_comp >= COMPLACENT_THRESH:
        if n_distribution >= 3:
            return "DISTRIBUTION_STEALTH"
        return "COMPLACENT_DISTRIBUTION"

    # Complacent drift: sentiment complacent without macro confirmation
    # (euphoria phase where VIX/VVIX/PCR are low but macro isn't complacent yet)
    if cat2_comp >= COMPLACENT_THRESH:
        return "COMPLACENT_DRIFT"

    return "NEUTRAL"
