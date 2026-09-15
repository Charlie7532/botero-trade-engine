"""
Signal Discriminator — Pure Domain Rules
==========================================
Classifies a station's current D1×D2×D3 state into signal families:
  STRUCTURAL_FLOOR | MODERATE_FLOOR | PULLBACK | TRAP | NOISE
  (Ceiling rules: Fase 2)

Combines:
  - Empirical D2 rules from signal_discriminator_rules.json
  - D3 stability filter (degrades/enhances confidence)
  - Canary edge from TimingContext (t-1 anticipation)
  - SGS from TimingContext (multi-scale consistency)

Clean Architecture: Pure domain rule. No I/O except JSON load at import time.
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional
import json
from pathlib import Path
from functools import lru_cache

from backend.modules.entry_decision.domain.rules.timing_context import TimingContext


RULES_PATH = Path(__file__).parent.parent.parent.parent.parent.parent / (
    ".agents/references/metar/signal_discriminator_rules.json"
)

D2_LABELS = {0: "FAST_DOWN", 1: "DOWN", 2: "NEUTRAL", 3: "UP", 4: "FAST_UP"}
D3_LABELS = {0: "VERY_STABLE", 1: "STABLE", 2: "NEUTRAL", 3: "VOLATILE", 4: "VERY_VOLATILE"}


@dataclass(frozen=True)
class FloorSignal:
    """Classification of floor signal quality for a station state."""
    station: str
    state_key: str
    d1: int
    d2: int
    d3: int

    # Classification
    signal_class: str           # STRUCTURAL_FLOOR | MODERATE_FLOOR | PULLBACK | TRAP | NOISE
    confidence: str             # HIGH | MODERATE | LOW | INSUFFICIENT
    d3_effect: str              # ENHANCES | NEUTRAL | DEGRADES

    # Evidence from rules JSON
    rule_hr_zz75: float         # HR at zz75 from the rule
    rule_sgs: float             # SGS median from the rule
    rule_n_states: int          # N states that support this rule

    # Live evidence from TimingContext (if available)
    live_sgs: Optional[float]           # SGS from current timing context
    live_canary_edge: Optional[float]   # Canary edge from current timing context
    live_canary_n: int                  # N observations at t-1
    live_timing_mode: str               # ANTICIPATION | CONFIRMATION | NOISE
    n_episodios: int                    # Episodes observed — scarcity indicator

    # Effective confidence (after D3 filter + N scarcity)
    effective_confidence: str   # Final confidence after all filters

    def to_dict(self) -> Dict[str, Any]:
        return {
            "station": self.station,
            "state_key": self.state_key,
            "d1": self.d1, "d2": self.d2, "d3": self.d3,
            "signal_class": self.signal_class,
            "confidence": self.confidence,
            "d3_effect": self.d3_effect,
            "effective_confidence": self.effective_confidence,
            "n_episodios": self.n_episodios,
            "rule_hr_zz75": self.rule_hr_zz75,
            "rule_sgs": self.rule_sgs,
            "rule_n_states": self.rule_n_states,
            "live_sgs": self.live_sgs,
            "live_canary_edge": self.live_canary_edge,
            "live_canary_n": self.live_canary_n,
            "live_timing_mode": self.live_timing_mode,
        }


@lru_cache(maxsize=1)
def _load_rules() -> dict:
    """Load the empirical rules JSON. Cached after first call."""
    if not RULES_PATH.exists():
        return {}
    with open(RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


# Confidence degradation table
_CONF_DEGRADE = {
    "HIGH": "MODERATE",
    "MODERATE": "LOW",
    "LOW": "INSUFFICIENT",
    "INSUFFICIENT": "INSUFFICIENT",
}

_CONF_ENHANCE = {
    "INSUFFICIENT": "LOW",
    "LOW": "MODERATE",
    "MODERATE": "HIGH",
    "HIGH": "HIGH",
}


def classify_floor(
    station: str,
    d1: int,
    d2: int,
    d3: int,
    timing: Optional[TimingContext] = None,
) -> FloorSignal:
    """Classify a station's floor signal quality.

    Args:
        station: Station name (lowercase)
        d1, d2, d3: Current dimensional bins
        timing: TimingContext from timing_context.py (V2 with SGS/canary)

    Returns:
        FloorSignal with classification, confidence, and evidence
    """
    rules = _load_rules()
    floor_rules = rules.get("floor_rules", {}).get(station, {})
    d3_filters = rules.get("floor_d3_filters", {}).get(station, {})

    d2_label = D2_LABELS.get(d2, f"UNKNOWN_{d2}")
    d3_label = D3_LABELS.get(d3, f"UNKNOWN_{d3}")

    # ── Step 1: D1 filter — rules only apply to stress states ──
    d1_range = floor_rules.get("d1_range", [4, 5])
    rule_n = 0
    if d1 not in d1_range:
        # Not in stress territory — use timing context directly if available
        signal_class = "NOISE"
        confidence = "INSUFFICIENT"
        rule_hr = 0.0
        rule_sgs = 0.0

        # But timing context might have a signal even outside stress D1
        if timing and timing.floor_sgs is not None:
            fp_zz75 = timing.first_passage_floor.get("zz75")
            if timing.floor_sgs > 0.30 and fp_zz75 and fp_zz75.hit_rate > 0.60:
                signal_class = "STRUCTURAL_FLOOR"
                confidence = "LOW"  # Lower confidence outside stress D1
                rule_hr = fp_zz75.hit_rate
                rule_sgs = timing.floor_sgs
            elif timing.floor_signal_class == "TACTICAL":
                signal_class = "PULLBACK"
                confidence = "LOW"
                rule_hr = fp_zz75.hit_rate if fp_zz75 else 0
                rule_sgs = timing.floor_sgs or 0
    else:
        # ── Step 2: D2-based rule lookup ──
        by_d2 = floor_rules.get("by_d2", {})
        d2_rule = by_d2.get(d2_label, {})

        signal_class = d2_rule.get("signal_class", "NOISE")
        confidence = d2_rule.get("confidence", "INSUFFICIENT")
        rule_hr = d2_rule.get("hr_zz75", 0.0)
        rule_sgs = d2_rule.get("sgs_median", 0.0)
        rule_n = d2_rule.get("n_states", 0)

    # ── Step 3: D3 stability filter ──
    d3_filter = d3_filters.get(d3_label, {})
    d3_effect = d3_filter.get("effect", "NEUTRAL")

    if d3_effect == "DEGRADES":
        effective_confidence = _CONF_DEGRADE.get(confidence, confidence)
    elif d3_effect == "ENHANCES":
        effective_confidence = _CONF_ENHANCE.get(confidence, confidence)
    else:
        effective_confidence = confidence

    # ── Step 4: Override with live timing if it has direct evidence ──
    live_sgs = timing.floor_sgs if timing else None
    live_canary_edge = timing.floor_canary_edge if timing else None
    live_canary_n = timing.floor_canary_n if timing else 0
    live_timing_mode = timing.floor_timing_mode if timing else "UNKNOWN"

    # When we have live timing, it has the INDIVIDUAL state's data,
    # which is more precise than the D2-group average from the rule.
    #
    # PRINCIPLE: The individual observation is a REAL EVENT that happened.
    # Never kill the signal — classify from the actual data.
    # Degrade confidence for low N to warn about scarcity, but preserve
    # the mathematical observation intact.
    n_episodios = timing.n_episodios if timing else 0

    if timing and timing.first_passage_floor:
        fp_zz75 = timing.first_passage_floor.get("zz75")
        fp_zz25 = timing.first_passage_floor.get("zz25")
        live_hr75 = fp_zz75.hit_rate if fp_zz75 else None
        live_hr25 = fp_zz25.hit_rate if fp_zz25 else None

        if live_hr75 is not None and live_hr25 is not None:
            # ALWAYS classify from individual state data — the event is real
            # live_sgs may be None if hr25=0 (division by zero) — treat as 0
            effective_sgs = live_sgs if live_sgs is not None else 0.0
            if effective_sgs > 0.30:
                signal_class = "STRUCTURAL_FLOOR"
            elif live_hr25 > 0.55 and live_hr75 < 0.55:
                signal_class = "PULLBACK"
            elif live_hr25 < 0.45 and live_hr75 < 0.45:
                signal_class = "TRAP"
            elif live_hr75 > 0.65:
                signal_class = "STRUCTURAL_FLOOR"
            elif live_hr75 > 0.55:
                signal_class = "MODERATE_FLOOR"
            else:
                signal_class = "NOISE"
            # Update the rule evidence with live data
            rule_hr = live_hr75
            rule_sgs = effective_sgs

            # Degrade confidence by N scarcity — the signal is real but rare
            if n_episodios < 5:
                effective_confidence = _CONF_DEGRADE.get(
                    _CONF_DEGRADE.get(effective_confidence, effective_confidence),
                    effective_confidence)  # Two-tier downgrade for very rare
            elif n_episodios < 10:
                effective_confidence = _CONF_DEGRADE.get(effective_confidence, effective_confidence)
            # n_episodios >= 10: full confidence from D3 filter, no further degradation
        else:
            # Has timing but missing scales — use group rule with override checks
            if signal_class == "NOISE" and live_sgs > 0.30:
                if fp_zz75 and fp_zz75.hit_rate > 0.60:
                    signal_class = "STRUCTURAL_FLOOR"
                    effective_confidence = "LOW"

            if signal_class == "STRUCTURAL_FLOOR" and live_sgs < -0.10:
                signal_class = "PULLBACK"
                effective_confidence = _CONF_DEGRADE.get(effective_confidence, effective_confidence)

    return FloorSignal(
        station=station,
        state_key=f"{d1}__{d2}__{d3}",
        d1=d1, d2=d2, d3=d3,
        signal_class=signal_class,
        confidence=confidence,
        d3_effect=d3_effect,
        rule_hr_zz75=rule_hr,
        rule_sgs=rule_sgs,
        rule_n_states=rule_n,
        live_sgs=live_sgs,
        live_canary_edge=live_canary_edge,
        live_canary_n=live_canary_n,
        live_timing_mode=live_timing_mode,
        n_episodios=n_episodios,
        effective_confidence=effective_confidence,
    )
