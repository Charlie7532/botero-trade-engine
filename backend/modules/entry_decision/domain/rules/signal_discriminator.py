"""
Signal Discriminator — Pure Domain Rules (V3: 7-Condition Concordance + HistoricalContext)
=========================================================================================
Classifies a station's current D1×D2×D3 state into signal families:
  Floor:   STRUCTURAL_FLOOR | MODERATE_FLOOR | PULLBACK | TRAP | NOISE
  Ceiling: STRUCTURAL_CEILING | MODERATE_CEILING | CORRECTION | BULL_TRAP | NOISE

V3 (7 conditions) replaces V2 (6 conditions):
  - REMOVED: C5 overflow (4.4pp spread — too weak to discriminate)
  - ADDED:   C5 Dual Nature (63.3pp spread — ceiling of same state is mirror)
  - ADDED:   C7 p_value (17.5pp spread — statistical significance filter)

Concordance conditions — 7 votes with market meaning:
  C1: RR < 0.8           → opportunity quality (gain vs risk)
  C2: HR75 < 50%         → fundamental probability (does it produce floors?)
  C3: PF < 1.0           → economic viability (does it destroy capital?)
  C4: SGS < -0.05        → scale mismatch (dead cat bounce detector)
  C5: ceil_hr75 > 0.60   → identity inversion (distribution disguised as capitulation)
  C6: MFE < |MAE|        → path hostility (underwater > profit intraday)
  C7: pvalue > 0.80      → statistical insignificance (noise vs signal)

Classification thresholds (validated monotonic on 421 states):
  0/7:   HR75=70.2%  →  STRUCTURAL_FLOOR HIGH (total bullish agreement)
  1/7:   HR75=58.3%  →  STRUCTURAL/MODERATE
  2/7:   HR75=52.0%  →  MODERATE/NOISE
  3-4/7: HR75=50.0%  →  NOISE/PULLBACK (borderline)
  5/7:   HR75=40.0%  →  TRAP MODERATE
  6-7/7: HR75=0.0%   →  TRAP HIGH (near-total bearish agreement)

Station identity (from station_profiles.py):
  Each output carries polarity, CAT, DSR grade, SHAP rank, credibility tier,
  composite weight, and alert priority for downstream consumers.

N_episodios policy:
  n < 5:  signal is RARE — flag it, DON'T degrade. Rarity = purest expression.
  n >= 5: signal has adequate sample.

Historical Context (Fact Store enrichment — V4 addition):
  Attaches backward-looking zigzag context from the fact store.
  Does NOT modify classification — purely additive for downstream consumers.
  Fields: divergence_regime, down_accum_ret, down_ev_structural,
          rr_asymmetry_75, cascade_small, cascade_large,
          lift_vs_baseline, p_bull_75.

Clean Architecture: Pure domain rule. No I/O except JSON load at import time.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
import json
from pathlib import Path
from functools import lru_cache

from backend.modules.entry_decision.domain.rules.timing_context import TimingContext
from backend.modules.entry_decision.domain.rules.station_profiles import (
    get_station_profile, signal_router, StationProfile,
    get_all_stress_bins, get_all_complacent_bins,
)


RULES_PATH = Path(__file__).parent.parent.parent.parent.parent.parent / (
    ".agents/references/metar/signal_discriminator_rules.json"
)
FACT_STORE_DIR = Path(__file__).parent

D2_LABELS = {0: "FAST_DOWN", 1: "DOWN", 2: "NEUTRAL", 3: "UP", 4: "FAST_UP"}
D3_LABELS = {0: "VERY_STABLE", 1: "STABLE", 2: "NEUTRAL", 3: "VOLATILE", 4: "VERY_VOLATILE"}

# Zone bins per station — polarity-aware
# Canonical source: station_profiles.py StationProfile.stress_bins / complacent_bins
# STRESS = extreme values where floor/ceiling signals fire
# COMPLACENT = opposite extreme where accumulation/distribution forms
STRESS_BINS: Dict[str, List[int]] = get_all_stress_bins()
COMPLACENT_BINS: Dict[str, List[int]] = get_all_complacent_bins()


# ── Concordance conditions (V3: 7 conditions) ──────────────────────────
#
# Each condition is a VOTE measuring one dimension of floor/ceiling quality.
# No single condition vetoes — classification emerges from agreement.
#
# Conditions are ordered by discriminating power (STRUCTURAL vs TRAP spread):
#   C1: RR      — 43.6pp  (quality of the opportunity)
#   C2: HR75    — 34.1pp  (fundamental probability)
#   C3: PF      — 31.8pp  (economic viability)
#   C4: SGS     — 14.3pp  (scale mismatch: dead cat bounce detector)
#   C5: DUAL    — 63.3pp  (identity inversion: ceiling disguised as floor)
#   C6: MAE/MFE — 29.0pp  (intraday path hostility)
#   C7: p_value — 17.5pp  (statistical insignificance)
#
# Removed: pct_overflow (4.4pp — too weak to contribute)


# ── D2/D3 Kinematic Modulation (from StationProfile §6 singularities) ──
#
# Post-concordance modulation: after the 7-condition concordance produces
# a signal_class and confidence, D2/D3 singularities can promote or demote
# the classification by one tier. These are station-specific anomalies
# documented in V3 personality dossiers §6 and codified in StationProfile.
#
# Rules:
#   - d2_floor_accelerator match → promote floor one tier (MODERATE→STRUCTURAL)
#   - d2_floor_inhibitor match → demote floor one tier (STRUCTURAL→MODERATE)
#   - d2_continuation_signal → not a floor/ceiling modulator (separate pathway)
#   - D3 squeeze/exhaustion → informational flag, no tier change
#     (concordance already captures D3 through metric distributions)

_FLOOR_PROMOTION = {
    "NOISE": "MODERATE_FLOOR",
    "PULLBACK": "MODERATE_FLOOR",
    "MODERATE_FLOOR": "STRUCTURAL_FLOOR",
    "STRUCTURAL_FLOOR": "STRUCTURAL_FLOOR",  # already max
    "TRAP": "TRAP",  # never promote a trap
}

_FLOOR_DEMOTION = {
    "STRUCTURAL_FLOOR": "MODERATE_FLOOR",
    "MODERATE_FLOOR": "PULLBACK",
    "PULLBACK": "NOISE",
    "NOISE": "NOISE",  # already min
    "TRAP": "TRAP",  # traps stay traps
}

_CEILING_PROMOTION = {
    "NOISE": "MODERATE_CEILING",
    "CORRECTION": "MODERATE_CEILING",
    "MODERATE_CEILING": "STRUCTURAL_CEILING",
    "STRUCTURAL_CEILING": "STRUCTURAL_CEILING",
    "BULL_TRAP": "BULL_TRAP",
}

_CEILING_DEMOTION = {
    "STRUCTURAL_CEILING": "MODERATE_CEILING",
    "MODERATE_CEILING": "CORRECTION",
    "CORRECTION": "NOISE",
    "NOISE": "NOISE",
    "BULL_TRAP": "BULL_TRAP",
}


def _apply_d2d3_modulation(
    station: str,
    d2: int,
    d3: int,
    signal_class: str,
    confidence: str,
    conditions: list,
    is_ceiling: bool,
) -> tuple:
    """Apply D2/D3 kinematic modulation from StationProfile singularities.

    Returns (signal_class, confidence, conditions) — potentially modified.
    Traps are NEVER promoted (empirically validated: traps at any D2 remain traps).
    """
    profile = get_station_profile(station)
    if profile is None:
        return signal_class, confidence, conditions

    modulated = False

    if not is_ceiling:
        # Floor modulation
        if profile.d2_floor_accelerator is not None and d2 == profile.d2_floor_accelerator:
            new_class = _FLOOR_PROMOTION.get(signal_class, signal_class)
            if new_class != signal_class:
                conditions = list(conditions) + [
                    f"D2_ACCEL:d2={d2}→promote ({signal_class}→{new_class})"
                ]
                signal_class = new_class
                modulated = True

        if profile.d2_floor_inhibitor is not None and d2 == profile.d2_floor_inhibitor:
            new_class = _FLOOR_DEMOTION.get(signal_class, signal_class)
            if new_class != signal_class:
                conditions = list(conditions) + [
                    f"D2_INHIB:d2={d2}→demote ({signal_class}→{new_class})"
                ]
                signal_class = new_class
                modulated = True
    else:
        # Ceiling modulation (mirror: inhibitor promotes ceiling, accelerator demotes)
        if profile.d2_floor_inhibitor is not None and d2 == profile.d2_floor_inhibitor:
            # VIX D2=4 (FAST_SPIKE): inhibits floor but ACCELERATES ceiling
            new_class = _CEILING_PROMOTION.get(signal_class, signal_class)
            if new_class != signal_class:
                conditions = list(conditions) + [
                    f"D2_CEIL_ACCEL:d2={d2}→promote ({signal_class}→{new_class})"
                ]
                signal_class = new_class
                modulated = True

    # D3 informational flags (no tier change — already in concordance metrics)
    if d3 == profile.d3_squeeze_bin:
        conditions = list(conditions) if not isinstance(conditions, list) else conditions
        conditions.append(f"D3_SQUEEZE:d3={d3} (coiled_spring)")
    elif d3 == profile.d3_exhaustion_bin:
        conditions = list(conditions) if not isinstance(conditions, list) else conditions
        conditions.append(f"D3_EXHAUST:d3={d3} (absorption)")

    return signal_class, confidence, conditions

def _compute_floor_concordance(
    rr: float,
    hr75: float,
    pf75: float,
    sgs: float,
    mae: float,
    mfe: float,
    ceil_hr75: float,
    pvalue: float,
) -> Tuple[int, List[str]]:
    """Count how many bearish conditions are met for a floor signal.

    Returns (score 0-7, list of condition descriptions with values).

    Market meaning of each condition:

    C1 (RR < 0.8): The average gain when right is < 80% of the average loss
        when wrong. The bounce is shallow relative to the damage when the floor
        fails. The OPPORTUNITY IS NOT WORTH THE RISK.

    C2 (HR75 < 50%): At structural zigzag scale (7.5% moves), less than half
        the time this state produces a floor. The FUNDAMENTAL PROBABILITY says
        this is not a structural reversal point.

    C3 (PF < 1.0): Total gains / Total losses < 1. Following this signal
        DESTROYS CAPITAL. The casino always wins.

    C4 (SGS < -0.05): HR_zz25 > HR_zz75. The state produces small bounces
        (2.5%) that fail at larger scale (7.5%). This is the DEAD CAT BOUNCE:
        looks like a floor tactically, is a trap structurally.

    C5 (ceil_hr > 0.60): The SAME D1×D2×D3 state, measured against zigzag
        peaks, works as a CEILING with >60% hit rate. The market is in
        DISTRIBUTION (ceiling active), not CAPITULATION (floor real).
        Capitulation has ceil_hr=28.6% (ceiling fails = rebound).
        Distribution has ceil_hr=71.4% (ceiling holds = decline continues).

    C6 (MFE < |MAE|): Peak unrealized gain < Peak unrealized loss. Even within
        the episode, you are deeper underwater than you are ever in profit.
        The PATH IS HOSTILE.

    C7 (pvalue > 0.80): The observed hit rate is statistically indistinguishable
        from random chance. EPISTEMIC HUMILITY: we cannot tell this signal apart
        from a coin flip. pvalue=0.42 = "real signal". pvalue=0.99 = "noise".
    """
    score = 0
    conditions: List[str] = []

    # C1: Quality of the opportunity
    if rr < 0.8:
        score += 1
        conditions.append(f"C1:RR<0.8 ({rr:.2f})")

    # C2: Fundamental probability
    if hr75 < 0.50:
        score += 1
        conditions.append(f"C2:HR75<50% ({hr75:.1%})")

    # C3: Economic viability
    if pf75 < 1.0:
        score += 1
        conditions.append(f"C3:PF<1.0 ({pf75:.2f})")

    # C4: Dead cat bounce (scale mismatch)
    if sgs < -0.05:
        score += 1
        conditions.append(f"C4:SGS<-5% ({sgs:+.2f})")

    # C5: Identity inversion (ceiling disguised as floor)
    if ceil_hr75 > 0.60:
        score += 1
        conditions.append(f"C5:DUAL>60% ({ceil_hr75:.1%})")

    # C6: Path hostility
    if mae != 0 and mfe < abs(mae):
        score += 1
        conditions.append(f"C6:MFE<|MAE| ({mfe:.3f}<{abs(mae):.3f})")

    # C7: Statistical insignificance
    if pvalue > 0.80:
        score += 1
        conditions.append(f"C7:pval>0.80 ({pvalue:.3f})")

    return score, conditions


def _compute_ceiling_concordance(
    rr: float,
    hr75: float,
    pf75: float,
    sgs: float,
    mae: float,
    mfe: float,
    floor_hr75: float,
    pvalue: float,
) -> Tuple[int, List[str]]:
    """Count how many bearish conditions are met for a ceiling signal.

    For ceilings, bearish conditions indicate REAL ceiling (market will fall).
    C5 is inverted: floor_hr75 > 0.60 means the floor of the same state is
    strong, so the ceiling is actually a floor disguised as ceiling.
    """
    return _compute_floor_concordance(
        rr, hr75, pf75, sgs, mae, mfe, floor_hr75, pvalue,
    )


def _concordance_to_class_and_confidence(
    score: int,
    hr75: float,
    sgs: float,
    is_ceiling: bool = False,
) -> Tuple[str, str]:
    """Map concordance score (0-7) to signal class and confidence.

    Validated monotonicity (banded):
      0/7: HR75=70.2%  →  STRUCTURAL_FLOOR HIGH
      1/7: HR75=58.3%  →  STRUCTURAL/MODERATE
      2/7: HR75=52.0%  →  MODERATE/NOISE
      3-4/7: HR75=50%  →  NOISE/PULLBACK
      5/7: HR75=40.0%  →  TRAP LOW
      6-7/7: HR75=0.0% →  TRAP HIGH/MODERATE
    """
    if is_ceiling:
        # Ceilings: high bearish score = STRUCTURAL_CEILING (market will fall)
        if score >= 6:
            return "STRUCTURAL_CEILING", "MODERATE"  # cap at MODERATE for ceilings
        elif score == 5:
            return "STRUCTURAL_CEILING", "MODERATE"
        elif score == 4:
            return "MODERATE_CEILING", "LOW"
        elif score == 3:
            return "MODERATE_CEILING", "LOW"
        elif score <= 1 and hr75 < 0.35:
            return "BULL_TRAP", "MODERATE"
        elif hr75 > 0.55:
            return "CORRECTION", "MODERATE"
        else:
            return "NOISE", "LOW"

    # Floor classification (7 conditions, 0-7 scale)
    if score >= 6:
        # 6-7/7: near-total bearish agreement → definitive trap
        return "TRAP", "HIGH"
    elif score == 5:
        # 5/7: strong bearish majority → trap
        return "TRAP", "MODERATE"
    elif score == 4:
        # 4/7: borderline — HR75 and SGS disambiguate
        if hr75 < 0.45:
            return "TRAP", "LOW"
        elif sgs < -0.05:
            return "PULLBACK", "LOW"
        else:
            return "NOISE", "LOW"
    elif score == 3:
        # 3/7: mixed — some bearish signals but not dominant
        if sgs > 0.30 and hr75 > 0.60:
            return "STRUCTURAL_FLOOR", "LOW"
        elif hr75 > 0.55:
            return "MODERATE_FLOOR", "LOW"
        elif sgs < -0.10:
            return "PULLBACK", "LOW"
        else:
            return "NOISE", "LOW"
    elif score == 2:
        # 2/7: mostly clean with minor concerns
        if sgs > 0.30 and hr75 > 0.65:
            return "STRUCTURAL_FLOOR", "MODERATE"
        elif hr75 > 0.60:
            return "MODERATE_FLOOR", "MODERATE"
        elif hr75 > 0.55:
            return "MODERATE_FLOOR", "LOW"
        else:
            return "NOISE", "LOW"
    elif score == 1:
        # 1/7: clean — one minor concern
        if sgs > 0.30 and hr75 > 0.65:
            return "STRUCTURAL_FLOOR", "HIGH"
        elif hr75 > 0.60:
            return "STRUCTURAL_FLOOR", "MODERATE"
        elif hr75 > 0.55:
            return "MODERATE_FLOOR", "MODERATE"
        else:
            return "NOISE", "LOW"
    else:
        # 0/7: total bullish agreement — all 7 metrics confirm floor quality
        if hr75 > 0.70:
            return "STRUCTURAL_FLOOR", "HIGH"
        elif hr75 > 0.60:
            return "STRUCTURAL_FLOOR", "MODERATE"
        elif hr75 > 0.55:
            return "MODERATE_FLOOR", "MODERATE"
        else:
            return "MODERATE_FLOOR", "LOW"


# ── Dataclasses ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class HistoricalContext:
    """Fact store enrichment — backward-looking zigzag context.

    From the fact store's dual-layer architecture:
      Standard Layer:  p_bull_75, lift_vs_baseline, rr_asymmetry_75
                       (forward probability trained on zigzag from pivot forward)
      Kinematic Layer: down_accum_ret, down_ev_structural, cascade_small, cascade_large
                       (backward structure trained on zigzag from point backward)
      Regime:          divergence_regime (convergence/divergence classification)

    Does NOT modify concordance classification. Enriches the signal for:
      1. Urgency in extreme traps: concordance ≥ 6 + lift ≤ 0 → lethal trap (hr75=0%)
      2. Market narrative: divergence_regime = STRUCTURAL_BULL_PULLBACK (good) vs
         FULL_CONVERGENT_BULL (exhaustion)
      3. BOS energy: down_accum_ret > 1.0% → bearish momentum not exhausted
    """
    divergence_regime: str           # STRUCTURAL_BULL_PULLBACK, FULL_CONVERGENT_BULL, etc.
    down_accum_ret: float            # Bearish momentum accumulated (%), higher = more energy
    down_ev_structural: float        # EV of bearish continuation (positive = bear continues)
    rr_asymmetry_75: float           # Forward gain/loss ratio from fact store
    cascade_small: Optional[float]   # Cascade rate of small legs (>0.50 = BOS risk)
    cascade_large: Optional[float]   # Cascade rate of large legs (>0.56 = capitulation)
    lift_vs_baseline: float          # Edge over unconditional (>0 = extended, <0 = depressed)
    p_bull_75: float                 # Forward probability from fact store standard layer

    def to_dict(self) -> Dict[str, Any]:
        return {
            "divergence_regime": self.divergence_regime,
            "down_accum_ret": self.down_accum_ret,
            "down_ev_structural": self.down_ev_structural,
            "rr_asymmetry_75": self.rr_asymmetry_75,
            "cascade_small": self.cascade_small,
            "cascade_large": self.cascade_large,
            "lift_vs_baseline": self.lift_vs_baseline,
            "p_bull_75": self.p_bull_75,
        }


@dataclass(frozen=True)
class FloorSignal:
    """Classification of floor signal quality for a station state.

    V2: Concordance-based. Each signal carries the full evidence trail.
    """
    station: str
    state_key: str
    d1: int
    d2: int
    d3: int

    # Classification (from concordance)
    signal_class: str           # STRUCTURAL_FLOOR | MODERATE_FLOOR | PULLBACK | TRAP | NOISE
    confidence: str             # HIGH | MODERATE | LOW | INSUFFICIENT

    # Concordance evidence
    concordance_score: int      # 0-6 bearish conditions met
    concordance_detail: tuple   # Tuple of condition strings with values
    is_rare: bool               # n_episodios < 5 — purest expression, not degraded

    # Raw metrics (the data behind the concordance)
    hr_zz75: float
    hr_zz25: float
    pf_zz75: float
    rr_asymmetry: float
    sgs: float
    pct_overflow: float
    mae_medio: float
    mfe_medio: float

    # Timing intelligence
    canary_edge: Optional[float]
    canary_n: int
    timing_mode: str            # ANTICIPATION | CONFIRMATION | NOISE | UNKNOWN

    # Backing
    n_episodios: int
    fire_rate_pct: float

    # D3 effect (from rules JSON, still informational)
    d3_effect: str              # ENHANCES | NEUTRAL | DEGRADES

    # Station identity (from station_profiles.py)
    station_polarity: str       # NORMAL | INVERTED | TRANSITIONAL_MACRO
    station_cat: int            # 1=MACRO | 2=SENTIMENT | 3=ACTION
    station_dsr_grade: str      # A | B
    station_shap_rank: int      # 1-15 (lower = more predictive)

    # Credibility routing (from signal_router)
    credibility_tier: str       # EVENT | TRANSITIONAL | CONFIRMED | BASELINE
    composite_weight: float     # 0.0-1.0 (EV contribution weight)
    alert_priority: str         # NONE | MODERATE | HIGH | CRITICAL

    # Proximity context (from TimingContext, previously ignored)
    pct_en_rango: float         # % of time near a floor (0-100)

    # Historical context (from fact store — enrichment, not classification)
    historical_context: Optional[HistoricalContext] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "station": self.station,
            "state_key": self.state_key,
            "d1": self.d1, "d2": self.d2, "d3": self.d3,
            "signal_class": self.signal_class,
            "confidence": self.confidence,
            "concordance_score": self.concordance_score,
            "concordance_detail": list(self.concordance_detail),
            "is_rare": self.is_rare,
            "hr_zz75": self.hr_zz75,
            "hr_zz25": self.hr_zz25,
            "pf_zz75": self.pf_zz75,
            "rr_asymmetry": self.rr_asymmetry,
            "sgs": self.sgs,
            "pct_overflow": self.pct_overflow,
            "mae_medio": self.mae_medio,
            "mfe_medio": self.mfe_medio,
            "canary_edge": self.canary_edge,
            "canary_n": self.canary_n,
            "timing_mode": self.timing_mode,
            "n_episodios": self.n_episodios,
            "fire_rate_pct": self.fire_rate_pct,
            "d3_effect": self.d3_effect,
            "station_polarity": self.station_polarity,
            "station_cat": self.station_cat,
            "station_dsr_grade": self.station_dsr_grade,
            "station_shap_rank": self.station_shap_rank,
            "credibility_tier": self.credibility_tier,
            "composite_weight": self.composite_weight,
            "alert_priority": self.alert_priority,
            "pct_en_rango": self.pct_en_rango,
            "historical_context": self.historical_context.to_dict() if self.historical_context else None,
        }


@dataclass(frozen=True)
class CeilingSignal:
    """Classification of ceiling signal quality for a station state.

    V2: Concordance-based, same framework as FloorSignal.
    NOTE: Ceilings are inherently weaker than floors (distribution vs capitulation).
    Maximum confidence for any ceiling is MODERATE (never HIGH).
    """
    station: str
    state_key: str
    d1: int
    d2: int
    d3: int

    signal_class: str           # STRUCTURAL_CEILING | MODERATE_CEILING | CORRECTION | BULL_TRAP | NOISE
    confidence: str

    concordance_score: int
    concordance_detail: tuple
    is_rare: bool

    hr_zz75: float
    hr_zz25: float
    pf_zz75: float
    rr_asymmetry: float
    sgs: float
    pct_overflow: float
    mae_medio: float
    mfe_medio: float

    canary_edge: Optional[float]
    canary_n: int
    timing_mode: str

    n_episodios: int
    fire_rate_pct: float

    d3_effect: str

    # Station identity
    station_polarity: str
    station_cat: int
    station_dsr_grade: str
    station_shap_rank: int

    # Credibility routing
    credibility_tier: str
    composite_weight: float
    alert_priority: str

    # Proximity context
    pct_en_rango: float

    # Historical context (from fact store — enrichment, not classification)
    historical_context: Optional[HistoricalContext] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "station": self.station,
            "state_key": self.state_key,
            "d1": self.d1, "d2": self.d2, "d3": self.d3,
            "signal_class": self.signal_class,
            "confidence": self.confidence,
            "concordance_score": self.concordance_score,
            "concordance_detail": list(self.concordance_detail),
            "is_rare": self.is_rare,
            "hr_zz75": self.hr_zz75,
            "hr_zz25": self.hr_zz25,
            "pf_zz75": self.pf_zz75,
            "rr_asymmetry": self.rr_asymmetry,
            "sgs": self.sgs,
            "pct_overflow": self.pct_overflow,
            "mae_medio": self.mae_medio,
            "mfe_medio": self.mfe_medio,
            "canary_edge": self.canary_edge,
            "canary_n": self.canary_n,
            "timing_mode": self.timing_mode,
            "n_episodios": self.n_episodios,
            "fire_rate_pct": self.fire_rate_pct,
            "d3_effect": self.d3_effect,
            "station_polarity": self.station_polarity,
            "station_cat": self.station_cat,
            "station_dsr_grade": self.station_dsr_grade,
            "station_shap_rank": self.station_shap_rank,
            "credibility_tier": self.credibility_tier,
            "composite_weight": self.composite_weight,
            "alert_priority": self.alert_priority,
            "pct_en_rango": self.pct_en_rango,
            "historical_context": self.historical_context.to_dict() if self.historical_context else None,
        }


@dataclass(frozen=True)
class ContextSignal:
    """Classification of market CONTEXT for non-stress station states.

    Extends the discriminator beyond stress zones to classify:
      - COMPLACENT states → Accumulation / Distribution forming
      - NEUTRAL states    → Leg direction (upleg / downleg / transition)

    This is the MIRROR of floor/ceiling classification:
      Floor/Ceiling:  "the market is stressed — is this floor real?"
      Context:        "the market is calm/neutral — what's building underneath?"

    Classification families:
      ACCUMULATION_STRUCTURAL: floor_hr > 70%, ceil_hr < 30% (institutional buying)
      ACCUMULATION_ACTIVE:     floor_hr > 60%, ceil_hr < 40% (visible buying)
      EQUILIBRIUM:             |floor_hr - ceil_hr| < 10% (no bias)
      DISTRIBUTION_MODERATE:   ceil_hr > 55% (selling pressure building)
      DISTRIBUTION_FORMING:    ceil_hr > 70%, floor_hr < 30% (institutional selling)
      UPLEG:                   floor_hr > ceil_hr + 5% in NEUTRAL (continuation up)
      DOWNLEG:                 ceil_hr > floor_hr + 5% in NEUTRAL (continuation down)
      TRANSITION:              NEUTRAL without clear direction

    Multi-scale convergence (SGC = Scale Gradient Convergence):
      hr25 < hr50 < hr75 = STRUCTURAL (signal strengthens with scale)
      hr25 > hr50 > hr75 = TACTICAL (signal weakens with scale = dead cat)
      hr25 ≈ hr50 ≈ hr75 = FLAT (no scale dependency)
    """
    station: str
    state_key: str
    d1: int
    d2: int
    d3: int

    # Classification
    signal_class: str           # ACCUMULATION_STRUCTURAL | ACCUMULATION_ACTIVE | ...
    confidence: str             # HIGH | MODERATE | LOW
    zone: str                   # COMPLACENT | NEUTRAL

    # Floor vs Ceiling balance (the core discriminator)
    floor_hr75: float
    ceil_hr75: float
    floor_ev75: float
    ceil_ev75: float

    # Multi-scale convergence
    hr_zz25: float              # Floor HR at tactical scale
    hr_zz50: float              # Floor HR at swing scale
    hr_zz75: float              # Floor HR at structural scale
    scale_gradient: float       # hr75 - hr25: positive = structural, negative = tactical
    scale_pattern: str          # STRUCTURAL | TACTICAL | FLAT

    # Backing
    n_episodios: int
    fire_rate_pct: float
    is_rare: bool

    # Station identity
    station_polarity: str
    station_cat: int
    station_dsr_grade: str
    station_shap_rank: int
    credibility_tier: str
    composite_weight: float
    alert_priority: str

    # Historical context (from fact store — enrichment, not classification)
    historical_context: Optional[HistoricalContext] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "station": self.station,
            "state_key": self.state_key,
            "d1": self.d1, "d2": self.d2, "d3": self.d3,
            "signal_class": self.signal_class,
            "confidence": self.confidence,
            "zone": self.zone,
            "floor_hr75": self.floor_hr75,
            "ceil_hr75": self.ceil_hr75,
            "floor_ev75": self.floor_ev75,
            "ceil_ev75": self.ceil_ev75,
            "hr_zz25": self.hr_zz25,
            "hr_zz50": self.hr_zz50,
            "hr_zz75": self.hr_zz75,
            "scale_gradient": self.scale_gradient,
            "scale_pattern": self.scale_pattern,
            "n_episodios": self.n_episodios,
            "fire_rate_pct": self.fire_rate_pct,
            "is_rare": self.is_rare,
            "station_polarity": self.station_polarity,
            "station_cat": self.station_cat,
            "station_dsr_grade": self.station_dsr_grade,
            "station_shap_rank": self.station_shap_rank,
            "credibility_tier": self.credibility_tier,
            "composite_weight": self.composite_weight,
            "alert_priority": self.alert_priority,
            "historical_context": self.historical_context.to_dict() if self.historical_context else None,
        }


# ── Loaders ──────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_rules() -> dict:
    """Load the empirical rules JSON. Cached after first call."""
    if not RULES_PATH.exists():
        return {}
    with open(RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=11)
def _load_fact_store(station: str) -> dict:
    """Load a station's fact store JSON. Cached per station (11 stations max)."""
    path = FACT_STORE_DIR / f"{station}_fact_store.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get_historical_context(
    station: str,
    state_key: str,
) -> Optional[HistoricalContext]:
    """Extract HistoricalContext from the fact store for a given station state.

    Returns None if the fact store or state is not found.
    Does NOT affect classification — purely additive enrichment.
    """
    fstore = _load_fact_store(station)
    if not fstore:
        return None

    fs_state = fstore.get("states", {}).get(state_key)
    if not fs_state:
        return None

    # Standard layer (forward probability trained on zigzag from pivot forward)
    zz75_std = fs_state.get("zz75", {})
    p_bull_75 = zz75_std.get("p_bull", 0.5)
    lift_vs_baseline = zz75_std.get("lift_vs_baseline", 0.0)
    rr_asymmetry_75 = zz75_std.get("rr_asymmetry", 1.0)

    # Kinematic layer (backward structure from zigzag from point backward)
    zk25 = fs_state.get("zigzag_kinematic", {}).get("zz25", {})
    sm = zk25.get("structural_momentum", {})
    pld = zk25.get("prev_leg_domino", {})
    terciles = pld.get("terciles_domino", {})

    down_legs = sm.get("down_legs", {})
    down_accum_ret = down_legs.get("mean_accum_ret", 0.0)
    down_ev_structural = down_legs.get("ev_structural_pct", 0.0)

    cascade_small = terciles.get("t1_small", {}).get("cascade_rate")
    cascade_large = terciles.get("t3_large", {}).get("cascade_rate")

    # Divergence regime
    divergence_regime = fs_state.get("divergence_regime", "UNKNOWN")

    return HistoricalContext(
        divergence_regime=divergence_regime,
        down_accum_ret=down_accum_ret,
        down_ev_structural=down_ev_structural,
        rr_asymmetry_75=rr_asymmetry_75,
        cascade_small=cascade_small,
        cascade_large=cascade_large,
        lift_vs_baseline=lift_vs_baseline,
        p_bull_75=p_bull_75,
    )


# ── Helpers ──────────────────────────────────────────────────────────────

def _get_station_context(
    station: str,
    d1: int,
    d2: int,
    d3: int,
    n_episodios: int,
) -> dict:
    """Extract station identity and credibility routing.

    Connects station_profiles.py to the signal output without affecting
    concordance logic. Pure enrichment for downstream consumers.
    """
    profile = get_station_profile(station)
    if profile:
        polarity = profile.polarity
        cat = profile.cat
        dsr_grade = profile.dsr_grade
        shap_rank = profile.shap_rank
    else:
        polarity = "UNKNOWN"
        cat = 0
        dsr_grade = "?"
        shap_rank = 99

    routing = signal_router(
        n=n_episodios, d1_bin=d1, station=station,
        d2_bin=d2, d3_bin=d3,
    )

    return {
        "station_polarity": polarity,
        "station_cat": cat,
        "station_dsr_grade": dsr_grade,
        "station_shap_rank": shap_rank,
        "credibility_tier": routing["tier"],
        "composite_weight": routing["composite_weight"],
        "alert_priority": routing["alert_priority"],
    }



def _extract_metrics_from_timing(
    timing: TimingContext,
    side: str,
) -> Tuple[float, float, float, float, float, float, float, float, float]:
    """Extract raw metrics from timing context for concordance computation.

    Args:
        timing: TimingContext object
        side: 'floor' or 'ceiling'

    Returns:
        (hr75, hr25, pf75, rr75, sgs, mae, mfe, dual_hr75, pvalue)

    dual_hr75: For floor classification, this is the CEILING hr75 of the same state.
               For ceiling classification, this is the FLOOR hr75 of the same state.
               Measures identity inversion: is this state the opposite of what it seems?
    """
    if side == "floor":
        fp_dict = timing.first_passage_floor
        dual_dict = timing.first_passage_ceiling
        sgs = timing.floor_sgs
    else:
        fp_dict = timing.first_passage_ceiling
        dual_dict = timing.first_passage_floor
        sgs = timing.ceiling_sgs

    fp75 = fp_dict.get("zz75")
    fp25 = fp_dict.get("zz25")
    dual75 = dual_dict.get("zz75")

    hr75 = fp75.hit_rate if fp75 else 0.0
    hr25 = fp25.hit_rate if fp25 else 0.0
    pf75 = fp75.profit_factor if fp75 else 0.0
    rr75 = fp75.rr_asymmetry if fp75 else 0.0
    mae = fp75.mae_medio if fp75 else 0.0
    mfe = fp75.mfe_medio if fp75 else 0.0
    pvalue = fp75.p_value if fp75 else 1.0
    sgs = sgs if sgs is not None else 0.0
    dual_hr75 = dual75.hit_rate if dual75 else 0.5

    return hr75, hr25, pf75, rr75, sgs, mae, mfe, dual_hr75, pvalue


def _get_d3_effect(rules: dict, station: str, d3: int, side: str) -> str:
    """Get D3 stability effect from rules JSON."""
    d3_label = D3_LABELS.get(d3, f"UNKNOWN_{d3}")
    filter_key = f"{side}_d3_filters"
    d3_filters = rules.get(filter_key, {}).get(station, {})
    d3_filter = d3_filters.get(d3_label, {})
    return d3_filter.get("effect", "NEUTRAL")


# ── Public API ───────────────────────────────────────────────────────────

def classify_floor(
    station: str,
    d1: int,
    d2: int,
    d3: int,
    timing: Optional[TimingContext] = None,
) -> FloorSignal:
    """Classify a station's floor signal quality using concordance framework.

    The concordance of 7 independent metrics determines classification.
    No single metric can veto — classification emerges from agreement.

    Rare events (n_episodios < 5) are the purest expression of the signal.
    They are flagged as is_rare=True but NEVER mathematically degraded.
    Their rarity implies fast mean reversion once D2 changes direction.

    Args:
        station: Station name (lowercase)
        d1, d2, d3: Current dimensional bins
        timing: TimingContext from timing_context.py (V2 with SGS/canary)

    Returns:
        FloorSignal with concordance-based classification and full evidence
    """
    rules = _load_rules()
    state_key = f"{d1}__{d2}__{d3}"

    # D3 effect from rules (informational)
    d3_effect = _get_d3_effect(rules, station, d3, "floor")

    # ── Without timing: fall back to rules JSON ──
    if not timing or not timing.first_passage_floor:
        floor_rules = rules.get("floor_rules", {}).get(station, {})
        d1_range = floor_rules.get("d1_range", [4, 5])
        d2_label = D2_LABELS.get(d2, f"UNKNOWN_{d2}")

        if d1 in d1_range:
            by_d2 = floor_rules.get("by_d2", {})
            d2_rule = by_d2.get(d2_label, {})
            signal_class = d2_rule.get("signal_class", "NOISE")
            confidence = d2_rule.get("confidence", "INSUFFICIENT")
            hr75 = d2_rule.get("hr_zz75", 0.0)
            sgs = d2_rule.get("sgs_median", 0.0)
        else:
            signal_class = "NOISE"
            confidence = "INSUFFICIENT"
            hr75 = 0.0
            sgs = 0.0

        ctx = _get_station_context(station, d1, d2, d3, 0)
        hctx = _get_historical_context(station, state_key)
        return FloorSignal(
            station=station, state_key=state_key,
            d1=d1, d2=d2, d3=d3,
            signal_class=signal_class, confidence=confidence,
            concordance_score=-1,  # -1 = no timing data, using rules fallback
            concordance_detail=("NO_TIMING_DATA",),
            is_rare=False,
            hr_zz75=hr75, hr_zz25=0.0, pf_zz75=0.0,
            rr_asymmetry=0.0, sgs=sgs, pct_overflow=0.0,
            mae_medio=0.0, mfe_medio=0.0,
            canary_edge=None, canary_n=0,
            timing_mode="UNKNOWN",
            n_episodios=0, fire_rate_pct=0.0,
            d3_effect=d3_effect,
            pct_en_rango=0.0,
            historical_context=hctx,
            **ctx,
        )

    # ── With timing: use concordance framework (7 conditions) ──
    hr75, hr25, pf75, rr75, sgs, mae, mfe, dual_hr75, pvalue = _extract_metrics_from_timing(
        timing, "floor"
    )

    score, conditions = _compute_floor_concordance(
        rr=rr75, hr75=hr75, pf75=pf75, sgs=sgs,
        mae=mae, mfe=mfe, ceil_hr75=dual_hr75, pvalue=pvalue,
    )

    signal_class, confidence = _concordance_to_class_and_confidence(
        score, hr75, sgs, is_ceiling=False,
    )

    # D2/D3 kinematic modulation (from StationProfile §6 singularities)
    # Post-concordance: adjusts signal_class by one tier based on
    # empirically documented D2 behavior (VIX/CREDIT absorption, ROTATION continuation)
    signal_class, confidence, conditions = _apply_d2d3_modulation(
        station, d2, d3, signal_class, confidence, conditions, is_ceiling=False,
    )

    # Canary intelligence
    canary_edge = timing.floor_canary_edge
    canary_n = timing.floor_canary_n
    timing_mode = timing.floor_timing_mode

    # Rarity flag — the signal is the purest expression, not degraded
    n_episodios = timing.n_episodios
    is_rare = n_episodios < 5

    ctx = _get_station_context(station, d1, d2, d3, n_episodios)
    hctx = _get_historical_context(station, state_key)
    return FloorSignal(
        station=station, state_key=state_key,
        d1=d1, d2=d2, d3=d3,
        signal_class=signal_class, confidence=confidence,
        concordance_score=score,
        concordance_detail=tuple(conditions),
        is_rare=is_rare,
        hr_zz75=hr75, hr_zz25=hr25, pf_zz75=pf75,
        rr_asymmetry=rr75, sgs=sgs, pct_overflow=timing.pct_overflow,
        mae_medio=mae, mfe_medio=mfe,
        canary_edge=canary_edge, canary_n=canary_n,
        timing_mode=timing_mode,
        n_episodios=n_episodios, fire_rate_pct=timing.fire_rate_pct,
        d3_effect=d3_effect,
        pct_en_rango=timing.floor_pct_en_rango,
        historical_context=hctx,
        **ctx,
    )


def classify_ceiling(
    station: str,
    d1: int,
    d2: int,
    d3: int,
    timing: Optional[TimingContext] = None,
) -> CeilingSignal:
    """Classify a station's ceiling signal quality using concordance framework.

    Uses medicion_max (proximity to zigzag peaks).
    Complacent states (low D1 for vol indicators) are the primary domain.

    Maximum confidence for any ceiling is MODERATE (never HIGH).
    Ceilings are inherently diffuse (distribution) vs floors (capitulation).
    """
    rules = _load_rules()
    state_key = f"{d1}__{d2}__{d3}"
    d3_effect = _get_d3_effect(rules, station, d3, "ceiling")

    # ── Without timing: fall back to rules JSON ──
    if not timing or not timing.first_passage_ceiling:
        ceiling_rules = rules.get("ceiling_rules", {}).get(station, {})
        d1_range = ceiling_rules.get("d1_range", [0, 1])
        d2_label = D2_LABELS.get(d2, f"UNKNOWN_{d2}")

        if d1 in d1_range:
            by_d2 = ceiling_rules.get("by_d2", {})
            d2_rule = by_d2.get(d2_label, {})
            signal_class = d2_rule.get("signal_class", "NOISE")
            confidence = d2_rule.get("confidence", "INSUFFICIENT")
            hr75 = d2_rule.get("hr_zz75", 0.0)
            sgs = d2_rule.get("sgs_median", 0.0)
        else:
            signal_class = "NOISE"
            confidence = "INSUFFICIENT"
            hr75 = 0.0
            sgs = 0.0

        # Cap ceiling confidence
        if confidence == "HIGH":
            confidence = "MODERATE"

        ctx = _get_station_context(station, d1, d2, d3, 0)
        hctx = _get_historical_context(station, state_key)
        return CeilingSignal(
            station=station, state_key=state_key,
            d1=d1, d2=d2, d3=d3,
            signal_class=signal_class, confidence=confidence,
            concordance_score=-1,
            concordance_detail=("NO_TIMING_DATA",),
            is_rare=False,
            hr_zz75=hr75, hr_zz25=0.0, pf_zz75=0.0,
            rr_asymmetry=0.0, sgs=sgs, pct_overflow=0.0,
            mae_medio=0.0, mfe_medio=0.0,
            canary_edge=None, canary_n=0,
            timing_mode="UNKNOWN",
            n_episodios=0, fire_rate_pct=0.0,
            d3_effect=d3_effect,
            pct_en_rango=0.0,
            historical_context=hctx,
            **ctx,
        )

    # ── With timing: use concordance framework (7 conditions) ──
    hr75, hr25, pf75, rr75, sgs, mae, mfe, dual_hr75, pvalue = _extract_metrics_from_timing(
        timing, "ceiling"
    )

    score, conditions = _compute_ceiling_concordance(
        rr=rr75, hr75=hr75, pf75=pf75, sgs=sgs,
        mae=mae, mfe=mfe, floor_hr75=dual_hr75, pvalue=pvalue,
    )

    signal_class, confidence = _concordance_to_class_and_confidence(
        score, hr75, sgs, is_ceiling=True,
    )

    # Cap ceiling confidence at MODERATE
    if confidence == "HIGH":
        confidence = "MODERATE"

    # D2/D3 kinematic modulation (from StationProfile §6 singularities)
    signal_class, confidence, conditions = _apply_d2d3_modulation(
        station, d2, d3, signal_class, confidence, conditions, is_ceiling=True,
    )

    canary_edge = timing.ceiling_canary_edge
    canary_n = timing.ceiling_canary_n
    timing_mode = timing.ceiling_timing_mode
    n_episodios = timing.n_episodios
    is_rare = n_episodios < 5

    ctx = _get_station_context(station, d1, d2, d3, n_episodios)
    hctx = _get_historical_context(station, state_key)
    return CeilingSignal(
        station=station, state_key=state_key,
        d1=d1, d2=d2, d3=d3,
        signal_class=signal_class, confidence=confidence,
        concordance_score=score,
        concordance_detail=tuple(conditions),
        is_rare=is_rare,
        hr_zz75=hr75, hr_zz25=hr25, pf_zz75=pf75,
        rr_asymmetry=rr75, sgs=sgs, pct_overflow=timing.pct_overflow,
        mae_medio=mae, mfe_medio=mfe,
        canary_edge=canary_edge, canary_n=canary_n,
        timing_mode=timing_mode,
        n_episodios=n_episodios, fire_rate_pct=timing.fire_rate_pct,
        d3_effect=d3_effect,
        pct_en_rango=timing.ceiling_pct_en_rango,
        historical_context=hctx,
        **ctx,
    )


def classify_context(
    station: str,
    d1: int,
    d2: int,
    d3: int,
    timing: Optional[TimingContext] = None,
) -> Optional[ContextSignal]:
    """Classify market CONTEXT for non-stress station states.

    Covers two zones:
      COMPLACENT → Accumulation vs Distribution forming
      NEUTRAL    → Leg direction (upleg / downleg / transition)

    Returns None for STRESS states (use classify_floor/classify_ceiling instead).

    Multi-scale convergence:
      The gradient hr75-hr25 tells us if the signal strengthens with scale
      (structural) or weakens (dead cat bounce). Validated:
        STRUCTURAL: spread=+40pp, EV=+0.044
        TACTICAL:   spread=-39pp, EV=-0.015

    Market interpretation:
      ACCUMULATION_STRUCTURAL: institutional buying underneath complacency.
        floor_hr=100%, ceil_hr=0%. The market looks calm but institutions
        are loading. Multi-scale confirms: hr25=60%→hr75=100%.

      DISTRIBUTION_FORMING: institutional selling underneath complacency.
        floor_hr=0%, ceil_hr=100%. The market looks calm but institutions
        are distributing. Multi-scale confirms: hr25=39%→hr75=0%.

      UPLEG: in neutral territory, floor_hr > ceil_hr = support active.
        The market is in a continuation upward. Floors hold, ceilings fail.

      DOWNLEG: in neutral territory, ceil_hr > floor_hr = resistance active.
        The market is in a continuation downward. Ceilings hold, floors fail.
    """
    stress_bins = STRESS_BINS.get(station, [])
    complacent_bins = COMPLACENT_BINS.get(station, [])

    # Determine zone
    if d1 in stress_bins:
        return None  # Use classify_floor/classify_ceiling for stress
    elif d1 in complacent_bins:
        zone = "COMPLACENT"
    else:
        zone = "NEUTRAL"

    state_key = f"{d1}__{d2}__{d3}"

    if not timing:
        return None

    # Extract floor and ceiling metrics at all 3 scales
    fp_f = timing.first_passage_floor or {}
    fp_c = timing.first_passage_ceiling or {}

    fp25_f = fp_f.get("zz25")
    fp50_f = fp_f.get("zz50")
    fp75_f = fp_f.get("zz75")
    fp75_c = fp_c.get("zz75")

    if not fp75_f or not fp75_c:
        return None

    floor_hr75 = fp75_f.hit_rate
    ceil_hr75 = fp75_c.hit_rate
    floor_ev75 = fp75_f.ev if fp75_f.ev is not None else 0.0
    ceil_ev75 = fp75_c.ev if fp75_c.ev is not None else 0.0

    hr25 = fp25_f.hit_rate if fp25_f else floor_hr75
    hr50 = fp50_f.hit_rate if fp50_f else floor_hr75

    # Multi-scale gradient
    scale_gradient = floor_hr75 - hr25
    if scale_gradient > 0.10:
        scale_pattern = "STRUCTURAL"
    elif scale_gradient < -0.10:
        scale_pattern = "TACTICAL"
    else:
        scale_pattern = "FLAT"

    n_episodios = timing.n_episodios
    is_rare = n_episodios < 5

    # ── Classification ──
    if zone == "COMPLACENT":
        signal_class, confidence = _classify_accumulation(
            floor_hr75, ceil_hr75, scale_pattern,
        )
    else:
        signal_class, confidence = _classify_leg(
            floor_hr75, ceil_hr75, d2, scale_pattern,
        )

    ctx = _get_station_context(station, d1, d2, d3, n_episodios)
    hctx = _get_historical_context(station, state_key)
    return ContextSignal(
        station=station, state_key=state_key,
        d1=d1, d2=d2, d3=d3,
        signal_class=signal_class, confidence=confidence,
        zone=zone,
        floor_hr75=floor_hr75, ceil_hr75=ceil_hr75,
        floor_ev75=floor_ev75, ceil_ev75=ceil_ev75,
        hr_zz25=hr25, hr_zz50=hr50, hr_zz75=floor_hr75,
        scale_gradient=scale_gradient, scale_pattern=scale_pattern,
        n_episodios=n_episodios, fire_rate_pct=timing.fire_rate_pct,
        is_rare=is_rare,
        historical_context=hctx,
        **ctx,
    )


def _classify_accumulation(
    floor_hr75: float,
    ceil_hr75: float,
    scale_pattern: str,
) -> Tuple[str, str]:
    """Classify complacent state as accumulation/distribution.

    Validated thresholds from 306 complacent states:
      ACCUM_STRUCTURAL: N=135, floor_hr=100%, ceil_hr=0%, EV=+0.066
      ACCUM_ACTIVE:     N=59,  floor_hr=67%,  ceil_hr=33%, EV=+0.027
      DISTRIB_FORMING:  N=23,  floor_hr=0%,   ceil_hr=100%, EV=-0.072
    """
    if floor_hr75 > 0.70 and ceil_hr75 < 0.30:
        conf = "HIGH" if scale_pattern == "STRUCTURAL" else "MODERATE"
        return "ACCUMULATION_STRUCTURAL", conf
    elif floor_hr75 > 0.60 and ceil_hr75 < 0.40:
        return "ACCUMULATION_ACTIVE", "MODERATE"
    elif floor_hr75 > 0.55:
        return "ACCUMULATION_MODERATE", "LOW"
    elif ceil_hr75 > 0.70 and floor_hr75 < 0.30:
        conf = "HIGH" if scale_pattern == "TACTICAL" else "MODERATE"
        return "DISTRIBUTION_FORMING", conf
    elif ceil_hr75 > 0.55:
        return "DISTRIBUTION_MODERATE", "LOW"
    elif abs(floor_hr75 - ceil_hr75) < 0.10:
        return "EQUILIBRIUM", "LOW"
    else:
        return "NOISE", "LOW"


def _classify_leg(
    floor_hr75: float,
    ceil_hr75: float,
    d2: int,
    scale_pattern: str,
) -> Tuple[str, str]:
    """Classify neutral state as upleg/downleg/transition.

    D2 (velocity) modulates confidence:
      D2=UP/FAST_UP + floor_hr > ceil_hr → confirmed upleg
      D2=DOWN/FAST_DOWN + ceil_hr > floor_hr → confirmed downleg
      D2 contradicts floor/ceil balance → lower confidence

    Validated from 462 neutral states:
      floor_hr consistently > ceil_hr across all D2 values (market has
      an inherent upward bias at structural scale). Discrimination comes
      from the MAGNITUDE of the spread.
    """
    spread = floor_hr75 - ceil_hr75
    d2_bullish = d2 >= 3   # UP or FAST_UP
    d2_bearish = d2 <= 1   # DOWN or FAST_DOWN

    if spread > 0.15:
        # Strong floor bias — upleg
        if d2_bullish:
            return "UPLEG", "MODERATE"
        elif d2_bearish:
            # Floor is strong but velocity is down → pullback in upleg
            return "UPLEG", "LOW"
        else:
            return "UPLEG", "LOW"
    elif spread < -0.05:
        # Ceiling bias — downleg (rare at structural scale)
        if d2_bearish:
            return "DOWNLEG", "MODERATE"
        else:
            return "DOWNLEG", "LOW"
    elif abs(spread) < 0.05:
        return "TRANSITION", "LOW"
    else:
        # Slight upward bias — the default
        if d2_bullish and scale_pattern == "STRUCTURAL":
            return "UPLEG", "LOW"
        elif d2_bearish:
            return "TRANSITION", "LOW"
        else:
            return "TRANSITION", "LOW"
