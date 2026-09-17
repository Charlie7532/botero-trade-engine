"""
Station Profiles — Single Source of Truth
=============================================
Encodes each station's identity, empirical validation metrics,
and the credibility tier classification logic.

This module replaces:
  - 10 × *_intelligence.md files (DSR/SHAP/AUC data → StationProfile)
  - reliability_factor() + rarity_amplifier() → signal_router()

Clean Architecture: Pure Domain Rules. No I/O, no infrastructure.
"""
from dataclasses import dataclass
from typing import Tuple, Optional


# ── Station Profile ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class StationProfile:
    """Immutable identity card for each METAR station.

    Absorbs the 4 unique data points that were in intelligence.md files:
    dsr_grade, dsr_pvalue, auc_oos, shap_rank.
    """
    station: str
    polarity: str            # NORMAL (high=bearish) | INVERTED (low=bearish) | TRANSITIONAL_MACRO
    cat: int                 # 1=Economía (lag) | 2=Protección (lead medio) | 3=Acción (lead rápido)
    profession: str          # Human-readable role description
    peak_ic_days: int        # Horizon of maximum Spearman IC predictive power
    temporal_shape: str      # PEAK_DECAY | MONOTONE_RISING
    precursors: Tuple[str, ...]   # Stations that arrive BEFORE this one
    confirmers: Tuple[str, ...]   # Stations that THIS one validates
    sigmet_threshold: float  # Raw value that triggers SIGMET for this station
    # DSR validation (from intelligence files, now here)
    dsr_grade: str           # A | B
    dsr_pvalue: float
    auc_oos: float
    shap_rank: int
    shap_value: float
    # Zone bins — canonical source of truth (replaces hardcoded duplicates
    # in signal_discriminator.py and family_sequence_detector.py)
    stress_bins: Tuple[int, ...]       # D1 bins indicating market stress for this station
    complacent_bins: Tuple[int, ...]   # D1 bins indicating market complacency
    # Floor/Ceiling bins — where floor/ceiling signals physically fire.
    # For most stations: floor_bins = stress_bins, ceiling_bins = complacent_bins.
    # For SKEW: floor_bins = complacent_bins (D1=0,1 = put capitulation = floor),
    #           ceiling_bins = stress_bins (D1=4,5 = peak insurance = ceiling).
    # None = inherit from stress_bins/complacent_bins (backward-compatible).
    floor_bins: Optional[Tuple[int, ...]] = None
    ceiling_bins: Optional[Tuple[int, ...]] = None
    # D2 kinematic singularities (from §6 of V3 dossiers)
    # When station is in stress AND D2 hits these bins, the signal
    # qualitatively changes. None = no special D2 behavior.
    d2_floor_accelerator: Optional[int] = None   # D2 bin that accelerates floor (absorption)
    d2_floor_inhibitor: Optional[int] = None     # D2 bin that inhibits floor (falling knife)
    d2_inhibitor_strength: int = 1               # How many demotion steps (VIX=2: STRUCTURAL→PULLBACK)
    d2_continuation_signal: Optional[int] = None # D2 bin that confirms continuation
    # D3 regime (universal across all stations but documented per-station)
    # D3=0 (VOL_EXTREME_SQUEEZE) = coiled spring, U-Turn potential
    # D3=4 (VOL_PEAK_DECEL) = institutional absorption, exhaustion U-Turn
    d3_squeeze_bin: Optional[int] = 0    # VOL_EXTREME_SQUEEZE
    d3_exhaustion_bin: Optional[int] = 4 # VOL_PEAK_DECEL


# ── 11 Station Profiles ──────────────────────────────────────────────────
# Source: *_intelligence.md (DSR/SHAP/AUC) + *_personalidad.md (polarity/CAT/profession)

STATION_PROFILES = {
    "vix": StationProfile(
        station="vix",
        polarity="NORMAL",
        cat=2,
        profession="Floor Detector (panic floor) + Drift Engine (complacency)",
        peak_ic_days=57,
        temporal_shape="PEAK_DECAY",
        precursors=("credit", "yield_curve"),
        confirmers=("bsi", "vvix"),
        sigmet_threshold=28.0,
        dsr_grade="A", dsr_pvalue=0.9947, auc_oos=0.8387, shap_rank=3, shap_value=0.4680,
        stress_bins=(4, 5), complacent_bins=(0, 1),
        # VIX §6: D1=5+D2=0 (absorption→V-bounce), D1=5+D2=4 (falling knife→WAIT)
        # strength=3: STRUCTURAL→MODERATE→PULLBACK→NOISE (dossier: "esperar", MKT_BLOCK_CRISIS)
        d2_floor_accelerator=0, d2_floor_inhibitor=4, d2_inhibitor_strength=3,
    ),
    "vvix": StationProfile(
        station="vvix",
        polarity="NORMAL",
        cat=2,
        profession="Regime Transition Detector — Fear Stability",
        peak_ic_days=57,
        temporal_shape="PEAK_DECAY",
        precursors=("vix",),
        confirmers=("sv5_turbulence",),
        sigmet_threshold=140.0,
        dsr_grade="B", dsr_pvalue=0.8790, auc_oos=0.8387, shap_rank=14, shap_value=0.0520,
        stress_bins=(4, 5), complacent_bins=(0, 1),
    ),
    "bsi": StationProfile(
        station="bsi",
        polarity="INVERTED",
        cat=3,
        profession="Maximum Precision Floor Locator (93.3% in-range)",
        peak_ic_days=24,
        temporal_shape="PEAK_DECAY",
        precursors=("vix", "credit"),
        confirmers=(),
        sigmet_threshold=5.0,  # BSI < 5% = breadth collapse
        dsr_grade="A", dsr_pvalue=0.9980, auc_oos=0.8387, shap_rank=1, shap_value=0.7770,
        stress_bins=(0, 1), complacent_bins=(4, 5),
        # B1: D2=0 (FAST_CRUSH_3D reversal) = breadth crush stops → buy dip
        # Dossier §6: state 0__0__3 has EV=+46.1%, HR=100% (U-Turn trigger)
        d2_floor_accelerator=0,
    ),
    "fg": StationProfile(
        station="fg",
        polarity="INVERTED",
        cat=2,
        profession="Contrarian at Floors (EXTREME_FEAR=floor) + Inertia Engine at Ceilings",
        peak_ic_days=80,
        temporal_shape="PEAK_DECAY",
        precursors=("vix", "pcr"),
        confirmers=("bsi",),
        sigmet_threshold=10.0,  # FG < 10 = extreme fear
        dsr_grade="A", dsr_pvalue=0.9620, auc_oos=0.8387, shap_rank=12, shap_value=0.0680,
        stress_bins=(0, 1), complacent_bins=(4, 5),
    ),
    "pcr": StationProfile(
        station="pcr",
        polarity="NORMAL",
        cat=2,
        profession="Dual Floor/Ceiling Detector (Put Panic=floor, Call Euphoria=ceiling)",
        peak_ic_days=24,
        temporal_shape="PEAK_DECAY",
        precursors=("vix",),
        confirmers=("fg",),
        sigmet_threshold=1.5,  # PCR > 1.5 = extreme put panic
        dsr_grade="B", dsr_pvalue=0.8610, auc_oos=0.8387, shap_rank=13, shap_value=0.0610,
        stress_bins=(4, 5), complacent_bins=(0, 1),
    ),
    "skew": StationProfile(
        station="skew",
        polarity="NORMAL",  # High SKEW = institutional insurance bid / paranoia = STRESS; Low SKEW = put capitulation = FLOOR
        cat=2,
        profession="Tail Risk Precursor (High=Peak Insurance / Ceiling) + Put Capitulation Floor (Low=Floor)",
        peak_ic_days=57,
        temporal_shape="MONOTONE_RISING",
        precursors=(),
        confirmers=("vix",),
        sigmet_threshold=145.0,  # SIGMET fires on high SKEW (ceiling precursor)
        dsr_grade="B", dsr_pvalue=0.8540, auc_oos=0.8387, shap_rank=10, shap_value=0.1123,
        stress_bins=(4, 5), complacent_bins=(0, 1),
        floor_bins=(0, 1),     # Put capitulation = bullish floor
        ceiling_bins=(4, 5),   # Peak insurance = bearish ceiling
        # SKEW §6: D2=0 (FAST_CRUSH: terminal put wash-out) → HR=88.9%, Fwd20d=+5.36% (floor accelerator)
        d2_floor_accelerator=0,
        # SKEW D3 kinematics: D3=4 is institutional absorption (+3.28% fwd20d), NOT exhaustion to demote;
        # D3=0 is lethargy (+0.63% fwd20d), NOT coiled spring to promote. Relies on exact cell concordance.
        d3_squeeze_bin=None,
        d3_exhaustion_bin=None,
    ),
    "credit": StationProfile(
        station="credit",
        polarity="INVERTED",
        cat=1,
        profession="Economic Health Canary — Maximum Asymmetry Floor Trigger at D2=0",
        peak_ic_days=100,
        temporal_shape="MONOTONE_RISING",
        precursors=("yield_curve",),
        confirmers=("vix", "bsi"),
        sigmet_threshold=0.85,  # Credit ratio < 0.85 = stress
        dsr_grade="A", dsr_pvalue=0.9509, auc_oos=0.8387, shap_rank=9, shap_value=0.1150,
        stress_bins=(0, 1), complacent_bins=(4, 5),
        # CREDIT §6: D2=0 (absorption) → HR=80%, PF=51.33 (maximum asymmetry floor)
        d2_floor_accelerator=0,
    ),
    "yield_curve": StationProfile(
        station="yield_curve",
        polarity="TRANSITIONAL_MACRO",
        cat=1,
        profession="Background Macro Regime (D1=0 Inversion=Risk-On; D1=4/5 Steepening=Danger)",
        peak_ic_days=100,
        temporal_shape="MONOTONE_RISING",
        precursors=(),
        confirmers=("credit",),
        sigmet_threshold=-0.5,  # Negative yield spread = inversion
        dsr_grade="A", dsr_pvalue=0.9680, auc_oos=0.8387, shap_rank=8, shap_value=0.1236,
        stress_bins=(0, 1), complacent_bins=(4, 5),
    ),
    "rotation": StationProfile(
        station="rotation",
        polarity="INVERTED",
        cat=1,
        profession="Risk Rotation Canary (D1=0 Defensive=floor; D2=4 Offensive Accel=continuation)",
        peak_ic_days=100,
        temporal_shape="MONOTONE_RISING",
        precursors=(),
        confirmers=("bsi",),
        sigmet_threshold=-2.0,  # Extreme defensive rotation
        dsr_grade="B", dsr_pvalue=0.8750, auc_oos=0.8387, shap_rank=5, shap_value=0.1793,
        stress_bins=(0, 1), complacent_bins=(4, 5),
        # ROTATION §6: D2=4 (FAST_SPIKE_3D) → HR=66.9%, Edge=+13.5% (offensive continuation)
        # From defensive position (D1=0,1), D2=4 spike = floor accelerator
        d2_floor_accelerator=4, d2_continuation_signal=4,
    ),
    "sv5_turbulence": StationProfile(
        station="sv5_turbulence",
        polarity="NORMAL",
        cat=3,
        profession="Institutional Disorder Detector (D1=5 exhaustion=floor; D1=0 silent distribution)",
        peak_ic_days=100,
        temporal_shape="MONOTONE_RISING",
        precursors=("vix", "vvix"),
        confirmers=("bsi",),
        sigmet_threshold=14.87,  # SV5T P95 = institutional turbulence
        dsr_grade="B", dsr_pvalue=0.9170, auc_oos=0.8387, shap_rank=11, shap_value=0.0749,
        stress_bins=(4, 5), complacent_bins=(0, 1),
    ),
    "dxy": StationProfile(
        station="dxy",
        polarity="NORMAL",
        cat=1,
        profession="Liquidity Drain Barometer (D1=5 extreme strength=sell; D1=0 weakness=expansion)",
        peak_ic_days=100,
        temporal_shape="MONOTONE_RISING",
        precursors=("yield_curve",),
        confirmers=("credit",),
        sigmet_threshold=110.0,  # DXY > 110 = extreme dollar strength
        dsr_grade="B", dsr_pvalue=0.8500, auc_oos=0.8387, shap_rank=15, shap_value=0.0450,
        stress_bins=(4, 5), complacent_bins=(0, 1),
    ),
}


# ── Derived bin dicts (backward-compatible access for consumers) ─────────

def get_all_stress_bins() -> dict:
    """Returns {station: list[int]} for all stations' stress bins."""
    return {s: list(p.stress_bins) for s, p in STATION_PROFILES.items()}


def get_all_complacent_bins() -> dict:
    """Returns {station: list[int]} for all stations' complacent bins."""
    return {s: list(p.complacent_bins) for s, p in STATION_PROFILES.items()}


def get_all_floor_bins() -> dict:
    """Returns {station: list[int]} — bins where floor signals physically fire."""
    return {
        s: list(p.floor_bins if p.floor_bins is not None else p.stress_bins)
        for s, p in STATION_PROFILES.items()
    }


def get_all_ceiling_bins() -> dict:
    """Returns {station: list[int]} — bins where ceiling signals physically fire."""
    return {
        s: list(p.ceiling_bins if p.ceiling_bins is not None else p.complacent_bins)
        for s, p in STATION_PROFILES.items()
    }


def get_station_profile(station: str) -> Optional[StationProfile]:
    """Returns the StationProfile for a given station code, or None."""
    return STATION_PROFILES.get(station.lower())


# ── Credibility Tier Classification ──────────────────────────────────────

def classify_tier(n: int, d1_bin: int) -> str:
    """Single source of truth for credibility tier classification.

    EVENT (N<10):
        Historical record with individual significance. Each episode is a
        verifiable FACT (crisis, generational floor, blow-off). Statistical
        inference is inappropriate — frequentist methods require N≥30 for
        robust estimates. These states are NOT noise — they are the most
        important structural fractures in 33 years of market history.
        Treatment: Zero weight in composite EV. Full weight in alert channel.

    TRANSITIONAL (10 ≤ N < 30):
        Direction reliable, magnitude uncertain. Wilson CI95 is wide.
        Treatment: Composite weight 0.5 (attenuated). Alert if D1 extreme.

    CONFIRMED (N ≥ 30, D1 extreme):
        Robust statistics in an alert/extreme zone (D1 bins 0, 1, 4, 5).
        Treatment: Composite weight 1.0. Active alert monitoring.

    BASELINE (N ≥ 30, D1 central):
        Ordinary market weather. Central bins (2, 3) with high N.
        Treatment: Composite weight 1.0. No alert.
    """
    if n < 10:
        return "EVENT"
    if n < 30:
        return "TRANSITIONAL"
    if d1_bin in (0, 1, 4, 5):
        return "CONFIRMED"
    return "BASELINE"


# ── Signal Router ────────────────────────────────────────────────────────

def signal_router(n: int, d1_bin: int, station: str,
                  sigma_depth_d1: float = 0.0,
                  d2_bin: int = -1, d3_bin: int = -1) -> dict:
    """Routes signal through the correct processing channels.

    Decouples THREE orthogonal dimensions:

    DIMENSION 1 — Statistical Weight (how much to trust the EV number):
        Governed by N only. N<10 → 0.0 (can't do frequentist inference with
        3-9 samples). N>=10 → 0.5. N>=30 → 1.0.
        This is IDENTICAL to the old reliability_factor() behavior.

    DIMENSION 2 — Alert Channel (should the system report this state?):
        Governed by D1 severity AND sigma depth. INDEPENDENT of N.
        A VIX at +6σ is a crisis whether we've seen it 3 times or 30 times.
        The old system multiplied N<10 states by zero, effectively silencing
        them. Now they contribute zero to composite EV (correct — can't do
        stats) but they DO generate crisis alerts (correct — they are facts).

    DIMENSION 3 — Kinematic Anomaly (D2/D3 extremes at central D1):
        When D1 is central (bins 2,3) but D2 or D3 is extreme (bins 0 or 4
        in 5-bin scale), the indicator is "vibrating" without leaving its
        normal range — a precursor of regime transition. Empirically validated
        in 6/11 stations (PCR, FG, SKEW, DXY, ROTATION, BSI) with EV spread
        > 0.005 vs baseline. Generates MODERATE alert.

    Returns dict with:
        tier: str              — EVENT | TRANSITIONAL | CONFIRMED | BASELINE
        composite_weight: float — 0.0 to 1.0 (EV contribution weight)
        alert_channel: str     — composite_only | alert_and_composite | alert_only
        alert_priority: str    — NONE | MODERATE | HIGH | CRITICAL
    """
    tier = classify_tier(n, d1_bin)

    # Dimension 1: Statistical weight (unchanged from reliability_factor)
    if n >= 30:
        composite_weight = 1.0
    elif n >= 10:
        composite_weight = 0.5
    else:
        composite_weight = 0.0

    # Dimension 2: Alert channel (based on SEVERITY, not sample size)
    is_extreme_d1 = d1_bin in (0, 5)
    is_alert_d1 = d1_bin in (1, 4)
    is_overflow = abs(sigma_depth_d1) >= 3.0

    # Dimension 3: Kinematic anomaly (D2/D3 extreme at central D1)
    is_central_d1 = d1_bin in (2, 3)
    is_extreme_d2 = d2_bin in (0, 4)
    is_extreme_d3 = d3_bin in (0, 4)
    is_kinematic_anomaly = is_central_d1 and (is_extreme_d2 or is_extreme_d3)

    if is_extreme_d1 or is_overflow:
        alert_priority = "CRITICAL"
    elif is_alert_d1:
        alert_priority = "HIGH" if tier in ("EVENT", "TRANSITIONAL") else "MODERATE"
    elif is_kinematic_anomaly:
        alert_priority = "MODERATE"
    else:
        alert_priority = "NONE"

    # Channel routing
    if composite_weight == 0.0 and alert_priority != "NONE":
        alert_channel = "alert_only"
    elif composite_weight > 0.0 and alert_priority != "NONE":
        alert_channel = "alert_and_composite"
    else:
        alert_channel = "composite_only"

    return {
        "tier": tier,
        "composite_weight": composite_weight,
        "alert_channel": alert_channel,
        "alert_priority": alert_priority,
    }



# ── Verification Dates (Signal Preservation Ledger) ──────────────────────

VERIFICATION_DATES = {
    "crisis": [
        "2008-10-10", "2009-03-09", "2020-03-16", "2020-03-23", "2025-04-07",
    ],
    "correction": [
        "2015-08-24", "2018-02-05", "2018-12-24", "2020-09-23",
        "2022-06-16", "2023-10-27", "2024-08-05",
    ],
    "baseline": [
        "2024-01-15", "2026-08-15", "2026-09-05",
    ],
    "euphoria": [
        "2021-11-19", "2024-12-16", "2025-02-18",
    ],
}

ERA_RANGES = {
    "PRE_QE":       ("1993-01-01", "2008-09-14"),
    "GFC":          ("2008-09-15", "2009-06-30"),
    "POST_GFC_QE":  ("2009-07-01", "2020-02-19"),
    "COVID":        ("2020-02-20", "2020-06-30"),
    "POST_COVID":   ("2020-07-01", "2022-01-03"),
    "RATE_HIKES":   ("2022-01-04", "2024-09-17"),
    "POST_PIVOT":   ("2024-09-18", "2025-04-01"),
    "TARIFF_ERA":   ("2025-04-02", "2025-07-31"),
    "CURRENT":      ("2025-08-01", "2099-12-31"),
}
