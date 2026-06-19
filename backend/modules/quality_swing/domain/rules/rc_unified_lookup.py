"""
RC Unified Lookup — Interconected Probability Tree
=====================================================
Hierarchical lookup combining:
  Layer 1: Slope states (T/C/W +++/++/+/-/--/---)
  Layer 2: Sigma bins (σ_current, σ_wave, σVWAP_wave)
  Layer 3: Stereotypes (HH/HL/LH/LL)

Trained on zigzag 2.5%, 15,194 points, 17 tickers, 2007-2026.

Lookup hierarchy (falls through until N >= min_n):
  S1: tripleta + σ_current + σ_wave + σVWAP_wave  (most specific)
  S2: tripleta + σ_current + σVWAP_wave
  S7: tripleta + σ_current
  S3: tripleta alone
  S4: T_level + W_level (drop Current)
  S5: W_level only (broadest)

This is PIEZA 3 of the unified model.
"""
import json
import math
import os
from dataclasses import dataclass
from typing import Optional

from backend.modules.quality_swing.domain.rules.rc_slope_classifier import (
    classify_slopes,
    SlopeState,
)


@dataclass
class UnifiedProbability:
    """Result from the unified probability tree.

    Provides BIDIRECTIONAL probability criteria. The same market event
    is simultaneously a long exit and a short entry (peak), or a long
    entry and a short exit (trough). Consumers decide which side to act on
    based on their strategy (Quality Swing, Speculative Short, etc.).
    """
    # Stereotype probabilities
    prob_bull: float      # P(HH) + P(HL) — bullish continuation
    prob_hh: float        # P(Higher High) — breakout
    prob_hl: float        # P(Higher Low)  — healthy pullback
    prob_lh: float        # P(Lower High)  — distribution / ceiling
    prob_ll: float        # P(Lower Low)   — breakdown / continuation down

    # Metadata
    n_samples: int
    confidence: float     # Wilson lower bound
    level: str            # S1_full, S2_trip_sc_svw, S3_tripleta, ...
    lookup_key: str       # Exact key used

    # Slope state
    slope_state: SlopeState

    @property
    def prob_bear(self) -> float:
        """P(LH) + P(LL) — probability of bearish outcome.

        Same event, opposite perspective:
          prob_bull high → ACCUMULATE long / EXIT short
          prob_bear high → TRIM long / ENTRY short
        """
        return round(self.prob_lh + self.prob_ll, 4)

    @property
    def action(self) -> str:
        """Directional bias from probability."""
        if self.prob_bull >= 0.65:
            return "ACCUMULATE"
        elif self.prob_bull <= 0.35:
            return "TRIM"
        return "HOLD"

    @property
    def conviction(self) -> float:
        """Conviction from probability distance to 50%."""
        return round(abs(self.prob_bull - 0.5) * 2, 3)

    @property
    def dominant_stereotype(self) -> str:
        """Most probable stereotype."""
        probs = {"HH": self.prob_hh, "HL": self.prob_hl,
                 "LH": self.prob_lh, "LL": self.prob_ll}
        return max(probs, key=probs.get)

    @property
    def is_high_conviction(self) -> bool:
        """N >= 30 and confidence > 0.3."""
        return self.n_samples >= 30 and self.confidence > 0.3


# ── Sigma bin classification ──
_SIGMA_BINS = [
    (-999, -1.0, "<<"),
    (-1.0, -0.3, "<"),
    (-0.3,  0.3, "~"),
    ( 0.3,  1.0, ">"),
    ( 1.0,  999, ">>"),
]


def _sigma_bin(value: float) -> str:
    for lo, hi, label in _SIGMA_BINS:
        if lo <= value < hi:
            return label
    return _SIGMA_BINS[-1][2]


# ── Load tree (singleton) ──
_TREE: dict = {}
_TREE_PATH = os.path.join(
    os.path.dirname(__file__), "rc_unified_tree.json"
)


def _load_tree() -> dict:
    global _TREE
    if not _TREE:
        with open(_TREE_PATH) as f:
            _TREE = json.load(f)
    return _TREE


def lookup_unified(
    tide_slope: float,
    current_slope: float,
    wave_slope: float,
    sigma_current: float,
    sigma_wave: float,
    vwap_sigma_wave: float,
    min_n: int = 10,
) -> Optional[UnifiedProbability]:
    """Hierarchical lookup in the unified probability tree.

    Falls through levels until finding a cell with N >= min_n.

    Args:
        tide_slope: 240-bar regression slope
        current_slope: 60-bar regression slope
        wave_slope: cycle-adaptive regression slope
        sigma_current: Price position in current channel (σ units)
        sigma_wave: Price position in wave channel (σ units)
        vwap_sigma_wave: Price position relative to wave VWAP (σ units)
        min_n: Minimum samples for a cell to be valid

    Returns:
        UnifiedProbability or None if no valid cell found
    """
    tree = _load_tree()
    cells = tree.get("cells", {})

    # Classify slopes
    slope = classify_slopes(tide_slope, current_slope, wave_slope)
    trip = slope.tripleta

    # Classify sigmas
    sc = _sigma_bin(sigma_current)
    sw = _sigma_bin(sigma_wave)
    svw = _sigma_bin(vwap_sigma_wave)

    # Lookup hierarchy: most specific → broadest
    candidates = [
        (f"S1:{trip}|{sc}|{sw}|{svw}", "S1_full"),
        (f"S2:{trip}|{sc}|{svw}", "S2_trip_sc_svw"),
        (f"S7:{trip}|{sc}", "S7_trip_sc"),
        (f"S3:{trip}", "S3_tripleta"),
        (f"S4:{slope.tide_level}/{slope.wave_level}", "S4_TW"),
        (f"S5:{slope.wave_level}", "S5_W"),
    ]

    for key, level in candidates:
        cell = cells.get(key)
        if cell and cell.get("N", 0) >= min_n:
            return UnifiedProbability(
                prob_bull=cell["P_bull"],
                prob_hh=cell["P_HH"],
                prob_hl=cell["P_HL"],
                prob_lh=cell["P_LH"],
                prob_ll=cell["P_LL"],
                n_samples=cell["N"],
                confidence=cell["confidence"],
                level=level,
                lookup_key=key,
                slope_state=slope,
            )

    return None
