"""
Timing Context — Pure Domain Rules
=====================================
Loads timing_fact_store JSON for each METAR station and extracts
temporal intelligence for a given 3D state_key.

The timing store answers: "Are you NEAR or FAR from a zigzag turning point,
and how does that change the probability?"

TimingContext is an AMPLIFIER — it does not replace the fact store's EV.
It adds temporal depth: slot proximity, first passage quality, episode
demographics, and overflow history.

V2 Enrichments (Corriente A):
  - Multi-scale first passage: zz25 + zz50 + zz75 (not just zz75)
  - Scale Gradient Score (SGS): (HR_zz75 - HR_zz25) / HR_zz25
    Classifies signal quality: STRUCTURAL (>30%), IMMEDIATE (~0%), TACTICAL (<-5%)
  - Canary signals: t-1 slot edge over ENTRE baseline
  - Signal mode: ANTICIPATION (t-1/t-2 active), CONFIRMATION (t+1/t+2), NOISE

Clean Architecture: Pure Domain Rules. Reads JSON from disk (same pattern
as lookup adapters). No network I/O, no infrastructure dependencies.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
import json
from pathlib import Path
from functools import lru_cache

RULES_DIR = Path(__file__).parent


# ── Dataclasses ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TimingSlot:
    """A single temporal slot relative to a zigzag turning point.

    Slots: t-2, t-1, t=0 (day of turn), t+1, t+2, ENTRE (away from turn).
    The spread between t=0 and ENTRE is the temporal alpha.
    """
    slot: str                    # "t-2" | "t-1" | "t=0" | "t+1" | "t+2" | "ENTRE"
    n: int                       # Number of observations in this slot
    pct: float                   # % of total observations
    hit_rate: Optional[float]    # Hit rate (p_bull for min, p_bear for max)
    ev: Optional[float]          # Expected value at this slot
    bars: Optional[float]        # Average bars to resolution


@dataclass(frozen=True)
class FirstPassage:
    """First passage metrics for a zigzag scale (zz25/zz50/zz75).

    Measures the quality of the temporal signal: how profitable is the
    first touch of a zigzag level from this state.
    """
    scale: str                   # "zz25" | "zz50" | "zz75"
    hit_rate: float
    baseline_hit: float
    hit_neto: float              # hit_rate - baseline_hit
    ev: float
    baseline_ev: float
    ev_neto: float               # ev - baseline_ev
    profit_factor: float
    rr_asymmetry: float
    ev_por_barra: float
    mae_medio: float             # Maximum Adverse Excursion (avg drawdown)
    mae_p90: float               # MAE at 90th percentile
    mfe_medio: float             # Maximum Favorable Excursion (avg gain)
    mfe_p90: float               # MFE at 90th percentile
    bars_medio: float            # Average bars to resolution
    p_value: float               # Statistical significance
    n_timeout: int               # Episodes that timed out
    timeout_rate: float


@dataclass(frozen=True)
class TimingContext:
    """Temporal intelligence for a METAR state.

    Combines episode demographics, overflow history, zigzag proximity slots,
    and first passage quality into a single immutable context object.
    """
    station: str
    state_key: str

    # ── Episode Demographics ──
    n_barras: int                # Total bars observed in this state
    fire_rate_pct: float         # % of time this state is active
    n_episodios: int             # Number of independent episodes
    duracion_media: float        # Average episode duration (days)
    duracion_max: int            # Maximum episode duration

    # ── Overflow History ──
    pct_overflow: float          # % of episodes with overflow
    max_tier_d1: int             # Maximum overflow tier in D1
    max_tier_d2: int             # Maximum overflow tier in D2
    max_tier_d3: int             # Maximum overflow tier in D3

    # ── Zigzag Proximity (medicion_min = FLOOR, medicion_max = CEILING) ──
    floor_pct_en_rango: float    # % of time near a floor
    floor_delta_medio: float     # Average distance to floor (bars)
    floor_slots: Dict[str, TimingSlot]   # t-2..t+2 + ENTRE
    ceiling_pct_en_rango: float
    ceiling_delta_medio: float
    ceiling_slots: Dict[str, TimingSlot]

    # ── First Passage — ALL 3 SCALES (V2) ──
    first_passage_floor: Dict[str, FirstPassage] = field(default_factory=dict)   # {"zz25": ..., "zz50": ..., "zz75": ...}
    first_passage_ceiling: Dict[str, FirstPassage] = field(default_factory=dict)

    # ── Scale Gradient Score (V2) ──
    floor_sgs: Optional[float] = None     # (HR_zz75 - HR_zz25) / HR_zz25  — >0.30=STRUCTURAL, <-0.05=TACTICAL
    ceiling_sgs: Optional[float] = None

    # ── Canary Signals (V2) ──
    floor_canary_edge: Optional[float] = None    # HR_t-1 - HR_ENTRE (pp edge)
    floor_canary_n: int = 0                       # N observations at t-1
    ceiling_canary_edge: Optional[float] = None
    ceiling_canary_n: int = 0

    # ── Signal Classification (V2) ──
    floor_signal_class: str = "UNKNOWN"   # "STRUCTURAL" | "TACTICAL" | "IMMEDIATE" | "UNKNOWN"
    ceiling_signal_class: str = "UNKNOWN"
    floor_timing_mode: str = "UNKNOWN"    # "ANTICIPATION" | "CONFIRMATION" | "NOISE" | "UNKNOWN"
    ceiling_timing_mode: str = "UNKNOWN"

    # Backward compatibility
    @property
    def first_passage_zz75_floor(self) -> Optional[FirstPassage]:
        return self.first_passage_floor.get("zz75")

    @property
    def first_passage_zz75_ceiling(self) -> Optional[FirstPassage]:
        return self.first_passage_ceiling.get("zz75")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for compositor report."""
        d = {
            "station": self.station,
            "state_key": self.state_key,
            "n_barras": self.n_barras,
            "fire_rate_pct": self.fire_rate_pct,
            "n_episodios": self.n_episodios,
            "duracion_media": self.duracion_media,
            "duracion_max": self.duracion_max,
            "pct_overflow": self.pct_overflow,
            "floor_pct_en_rango": self.floor_pct_en_rango,
            "floor_delta_medio": self.floor_delta_medio,
            "ceiling_pct_en_rango": self.ceiling_pct_en_rango,
            "ceiling_delta_medio": self.ceiling_delta_medio,
        }
        # Add key slots (t=0 vs ENTRE spread)
        ft0 = self.floor_slots.get("t=0")
        fentre = self.floor_slots.get("ENTRE")
        ct0 = self.ceiling_slots.get("t=0")
        centre = self.ceiling_slots.get("ENTRE")

        if ft0 and fentre and ft0.ev is not None and fentre.ev is not None:
            d["floor_temporal_spread_ev"] = round(ft0.ev - fentre.ev, 6)
            d["floor_t0_hr"] = ft0.hit_rate
            d["floor_t0_ev"] = ft0.ev
            d["floor_entre_ev"] = fentre.ev
        if ct0 and centre and ct0.ev is not None and centre.ev is not None:
            d["ceiling_temporal_spread_ev"] = round(ct0.ev - centre.ev, 6)
            d["ceiling_t0_hr"] = ct0.hit_rate
            d["ceiling_t0_ev"] = ct0.ev
            d["ceiling_entre_ev"] = centre.ev

        # First passage quality — all 3 scales (V2)
        for side, fp_dict in [("floor", self.first_passage_floor), ("ceiling", self.first_passage_ceiling)]:
            for scale, fp in fp_dict.items():
                d[f"fp_{side}_{scale}"] = {
                    "hit_rate": fp.hit_rate,
                    "hit_neto": fp.hit_neto,
                    "ev": fp.ev,
                    "ev_neto": fp.ev_neto,
                    "profit_factor": fp.profit_factor,
                    "rr_asymmetry": fp.rr_asymmetry,
                    "mae_medio": fp.mae_medio,
                    "mfe_medio": fp.mfe_medio,
                    "bars_medio": fp.bars_medio,
                    "p_value": fp.p_value,
                }

        # V2: Scale Gradient Score
        d["floor_sgs"] = self.floor_sgs
        d["ceiling_sgs"] = self.ceiling_sgs
        d["floor_signal_class"] = self.floor_signal_class
        d["ceiling_signal_class"] = self.ceiling_signal_class

        # V2: Canary signals
        d["floor_canary_edge"] = self.floor_canary_edge
        d["floor_canary_n"] = self.floor_canary_n
        d["ceiling_canary_edge"] = self.ceiling_canary_edge
        d["ceiling_canary_n"] = self.ceiling_canary_n
        d["floor_timing_mode"] = self.floor_timing_mode
        d["ceiling_timing_mode"] = self.ceiling_timing_mode

        # V2: Per-slot detail (for downstream analysis)
        for side, slots in [("floor", self.floor_slots), ("ceiling", self.ceiling_slots)]:
            for slot_name in ["t-2", "t-1", "t=0", "t+1", "t+2", "ENTRE"]:
                s = slots.get(slot_name)
                if s and s.n > 0:
                    d[f"{side}_slot_{slot_name.replace('=','')}_hr"] = s.hit_rate
                    d[f"{side}_slot_{slot_name.replace('=','')}_n"] = s.n

        return d

    @property
    def floor_temporal_spread(self) -> Optional[float]:
        """EV spread between t=0 and ENTRE for floor (positive = timing adds value)."""
        ft0 = self.floor_slots.get("t=0")
        fentre = self.floor_slots.get("ENTRE")
        if ft0 and fentre and ft0.ev is not None and fentre.ev is not None:
            return ft0.ev - fentre.ev
        return None

    @property
    def ceiling_temporal_spread(self) -> Optional[float]:
        """EV spread between t=0 and ENTRE for ceiling."""
        ct0 = self.ceiling_slots.get("t=0")
        centre = self.ceiling_slots.get("ENTRE")
        if ct0 and centre and ct0.ev is not None and centre.ev is not None:
            return ct0.ev - centre.ev
        return None

    @property
    def has_timing_signal(self) -> bool:
        """True if either floor or ceiling has meaningful temporal spread (>0.5% EV)."""
        fs = self.floor_temporal_spread
        cs = self.ceiling_temporal_spread
        return (fs is not None and fs > 0.005) or (cs is not None and cs > 0.005)


# ── Loaders ──────────────────────────────────────────────────────────────

@lru_cache(maxsize=16)
def _load_timing_store(station: str) -> Optional[dict]:
    """Load timing_fact_store JSON for a station. Cached per station."""
    path = RULES_DIR / f"{station}_timing_fact_store.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_slot(slot_name: str, raw: dict) -> TimingSlot:
    """Parse a raw slot dict into a TimingSlot."""
    return TimingSlot(
        slot=slot_name,
        n=raw.get("n", 0),
        pct=raw.get("pct", 0.0),
        hit_rate=raw.get("hit_rate"),
        ev=raw.get("ev"),
        bars=raw.get("bars"),
    )


def _parse_first_passage(scale: str, raw: dict) -> Optional[FirstPassage]:
    """Parse a raw first_passage dict into a FirstPassage."""
    if not raw or raw.get("hit_rate") is None:
        return None
    return FirstPassage(
        scale=scale,
        hit_rate=raw.get("hit_rate", 0.0),
        baseline_hit=raw.get("baseline_hit", 0.0),
        hit_neto=raw.get("hit_neto", 0.0),
        ev=raw.get("ev", 0.0),
        baseline_ev=raw.get("baseline_ev", 0.0),
        ev_neto=raw.get("ev_neto", 0.0),
        profit_factor=raw.get("profit_factor", 1.0),
        rr_asymmetry=raw.get("rr_asymmetry", 1.0),
        ev_por_barra=raw.get("ev_por_barra", 0.0),
        mae_medio=raw.get("mae_medio", 0.0),
        mae_p90=raw.get("mae_p90", 0.0),
        mfe_medio=raw.get("mfe_medio", 0.0),
        mfe_p90=raw.get("mfe_p90", 0.0),
        bars_medio=raw.get("bars_medio", 0.0),
        p_value=raw.get("p_value", 1.0),
        n_timeout=raw.get("n_timeout", 0),
        timeout_rate=raw.get("timeout_rate", 0.0),
    )


def _parse_medicion(raw: dict) -> tuple:
    """Parse medicion_min or medicion_max into full multi-scale metrics.

    Returns:
        (pct_en_rango, delta_medio, slots, first_passage_dict, sgs, canary_edge, canary_n, signal_class, timing_mode)
    """
    resumen = raw.get("resumen_rango", {})
    pct_en_rango = resumen.get("pct_en_rango", 0.0)
    delta_medio = resumen.get("delta_medio", 0.0)

    # ── Slots (all 6) ──
    slots_raw = raw.get("slots_zz25", {})
    slots = {}
    for slot_name in ["t-2", "t-1", "t=0", "t+1", "t+2", "ENTRE"]:
        if slot_name in slots_raw:
            slots[slot_name] = _parse_slot(slot_name, slots_raw[slot_name])

    # ── First Passage — ALL 3 SCALES (V2) ──
    fp_dict: Dict[str, FirstPassage] = {}
    fp_raw_all = raw.get("first_passage", {})
    for scale in ["zz25", "zz50", "zz75"]:
        fp_raw = fp_raw_all.get(scale, {})
        fp = _parse_first_passage(scale, fp_raw)
        if fp:
            fp_dict[scale] = fp

    # ── Scale Gradient Score (V2) ──
    sgs = None
    fp_zz25 = fp_dict.get("zz25")
    fp_zz75 = fp_dict.get("zz75")
    if fp_zz25 and fp_zz75 and fp_zz25.hit_rate > 0:
        sgs = round((fp_zz75.hit_rate - fp_zz25.hit_rate) / fp_zz25.hit_rate, 4)

    # ── Signal Class from SGS ──
    if sgs is not None:
        if sgs > 0.30:
            signal_class = "STRUCTURAL"   # Patience rewarded: zz75 >> zz25
        elif sgs < -0.05:
            signal_class = "TACTICAL"     # Scalp only: zz25 > zz75
        else:
            signal_class = "IMMEDIATE"    # Equal across scales: act now
    else:
        signal_class = "UNKNOWN"

    # ── Canary Signal — t-1 edge over ENTRE (V2) ──
    canary_edge = None
    canary_n = 0
    t_minus_1 = slots.get("t-1")
    entre = slots.get("ENTRE")
    if t_minus_1 and t_minus_1.n >= 3 and entre and entre.hit_rate is not None:
        if t_minus_1.hit_rate is not None:
            canary_edge = round(t_minus_1.hit_rate - entre.hit_rate, 4)
            canary_n = t_minus_1.n

    # ── Timing Mode from slots (V2) ──
    # ANTICIPATION: t-1 or t-2 has strong edge (signal BEFORE the turn)
    # CONFIRMATION: t+1 or t+2 has strong edge (signal AFTER the turn)
    # NOISE: no meaningful slot edge
    timing_mode = "NOISE"
    t_minus_2 = slots.get("t-2")
    t_plus_1 = slots.get("t+1")
    t_plus_2 = slots.get("t+2")

    # Check anticipation (pre-turn)
    has_anticipation = False
    if canary_edge is not None and canary_edge > 0.15 and canary_n >= 5:
        has_anticipation = True
    elif t_minus_2 and t_minus_2.n >= 5 and entre and entre.hit_rate is not None:
        if t_minus_2.hit_rate is not None and (t_minus_2.hit_rate - entre.hit_rate) > 0.15:
            has_anticipation = True

    # Check confirmation (post-turn)
    has_confirmation = False
    if t_plus_1 and t_plus_1.n >= 5 and entre and entre.hit_rate is not None:
        if t_plus_1.hit_rate is not None and (t_plus_1.hit_rate - entre.hit_rate) > 0.15:
            has_confirmation = True

    if has_anticipation and has_confirmation:
        timing_mode = "ANTICIPATION"  # Both pre and post, but pre takes priority
    elif has_anticipation:
        timing_mode = "ANTICIPATION"
    elif has_confirmation:
        timing_mode = "CONFIRMATION"

    return (pct_en_rango, delta_medio, slots, fp_dict,
            sgs, canary_edge, canary_n, signal_class, timing_mode)


# ── Public API ───────────────────────────────────────────────────────────

def get_timing_context(station: str, state_key: str) -> Optional[TimingContext]:
    """Get temporal intelligence for a station + state_key combination.

    Returns None if:
    - No timing store exists for this station
    - The state_key doesn't exist in the timing store

    This is the ONLY public entry point. Compositor and other consumers
    call this function to enrich their output with timing data.
    """
    store = _load_timing_store(station.lower())
    if not store:
        return None

    states = store.get("states", {})
    state_data = states.get(state_key)
    if not state_data:
        return None

    # Demographics
    pob = state_data.get("poblacion", {})
    ovf = state_data.get("overflows", {})

    # Floor (medicion_min)
    med_min = state_data.get("medicion_min", {})
    (floor_pct, floor_delta, floor_slots, floor_fps,
     floor_sgs, floor_canary_edge, floor_canary_n,
     floor_signal_class, floor_timing_mode) = _parse_medicion(med_min)

    # Ceiling (medicion_max)
    med_max = state_data.get("medicion_max", {})
    (ceil_pct, ceil_delta, ceil_slots, ceil_fps,
     ceil_sgs, ceil_canary_edge, ceil_canary_n,
     ceil_signal_class, ceil_timing_mode) = _parse_medicion(med_max)

    return TimingContext(
        station=station.lower(),
        state_key=state_key,
        n_barras=pob.get("barras", 0),
        fire_rate_pct=pob.get("fire_rate_pct", 0.0),
        n_episodios=pob.get("n_episodios", 0),
        duracion_media=pob.get("duracion_media", 0.0),
        duracion_max=pob.get("duracion_max", 0),
        pct_overflow=ovf.get("pct_episodios_overflow", 0.0),
        max_tier_d1=ovf.get("max_tier_d1", 0),
        max_tier_d2=ovf.get("max_tier_d2", 0),
        max_tier_d3=ovf.get("max_tier_d3", 0),
        floor_pct_en_rango=floor_pct,
        floor_delta_medio=floor_delta,
        floor_slots=floor_slots,
        ceiling_pct_en_rango=ceil_pct,
        ceiling_delta_medio=ceil_delta,
        ceiling_slots=ceil_slots,
        # V2: Multi-scale first passage
        first_passage_floor=floor_fps,
        first_passage_ceiling=ceil_fps,
        # V2: Scale Gradient Score
        floor_sgs=floor_sgs,
        ceiling_sgs=ceil_sgs,
        # V2: Canary signals
        floor_canary_edge=floor_canary_edge,
        floor_canary_n=floor_canary_n,
        ceiling_canary_edge=ceil_canary_edge,
        ceiling_canary_n=ceil_canary_n,
        # V2: Signal classification
        floor_signal_class=floor_signal_class,
        ceiling_signal_class=ceil_signal_class,
        floor_timing_mode=floor_timing_mode,
        ceiling_timing_mode=ceil_timing_mode,
    )
