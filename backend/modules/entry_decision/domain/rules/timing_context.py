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

Clean Architecture: Pure Domain Rules. Reads JSON from disk (same pattern
as lookup adapters). No network I/O, no infrastructure dependencies.
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional
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

    # ── First Passage (best scale: zz75) ──
    first_passage_zz75_floor: Optional[FirstPassage]
    first_passage_zz75_ceiling: Optional[FirstPassage]

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

        # First passage quality
        if self.first_passage_zz75_floor:
            fp = self.first_passage_zz75_floor
            d["fp_floor_zz75"] = {
                "profit_factor": fp.profit_factor,
                "p_value": fp.p_value,
                "ev": fp.ev,
                "hit_rate": fp.hit_rate,
                "mae_medio": fp.mae_medio,
                "mfe_medio": fp.mfe_medio,
                "bars_medio": fp.bars_medio,
            }
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
    """Parse medicion_min or medicion_max into (pct_en_rango, delta_medio, slots, fp_zz75)."""
    resumen = raw.get("resumen_rango", {})
    pct_en_rango = resumen.get("pct_en_rango", 0.0)
    delta_medio = resumen.get("delta_medio", 0.0)

    slots_raw = raw.get("slots_zz25", {})
    slots = {}
    for slot_name in ["t-2", "t-1", "t=0", "t+1", "t+2", "ENTRE"]:
        if slot_name in slots_raw:
            slots[slot_name] = _parse_slot(slot_name, slots_raw[slot_name])

    fp_raw = raw.get("first_passage", {}).get("zz75", {})
    fp = _parse_first_passage("zz75", fp_raw)

    return pct_en_rango, delta_medio, slots, fp


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
    floor_pct, floor_delta, floor_slots, fp_floor = _parse_medicion(med_min)

    # Ceiling (medicion_max)
    med_max = state_data.get("medicion_max", {})
    ceil_pct, ceil_delta, ceil_slots, fp_ceil = _parse_medicion(med_max)

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
        first_passage_zz75_floor=fp_floor,
        first_passage_zz75_ceiling=fp_ceil,
    )
