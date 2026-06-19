"""
RC Slope Classifier — Pure Domain Rule
==========================================
Classifies T/C/W slopes into 6 levels each:
  +++ / ++ / + / - / -- / ---

Uses empirically calibrated P33/P66 thresholds from 91K bars,
17 tickers, 2007-2026.

Input: 3 floats (tide_slope, current_slope, wave_slope)
Output: SlopeState dataclass with levels, tripleta, and semantics

This is PIEZA 2 of the unified model:
  PIEZA 1: ChannelSnapshot (compute_channel.py) — raw computation
  PIEZA 2: SlopeClassifier (this file) — state classification
  PIEZA 3: UnifiedLookup (rc_unified_lookup.py) — probability tree
"""
from dataclasses import dataclass


# ══════════════════════════════════════════════════════════════
# THRESHOLDS — Calibrated P33/P66 (asymmetric positive/negative)
# Source: rc_model_synthesis.md, 91K observations, 17 tickers
# ══════════════════════════════════════════════════════════════
_SLOPE_TH = {
    "T": {"+": (0.0456, 0.0983), "-": (0.0263, 0.0765)},
    "C": {"+": (0.0845, 0.1749), "-": (0.0613, 0.1583)},
    "W": {"+": (0.1262, 0.2717), "-": (0.1032, 0.2598)},
}


@dataclass(frozen=True)
class SlopeState:
    """Classified slope state for T/C/W channels."""
    tide_level: str      # T+++, T++, T+, T-, T--, T---
    current_level: str   # C+++, C++, C+, C-, C--, C---
    wave_level: str      # W+++, W++, W+, W-, W--, W---
    tripleta: str        # "T+/C-/W---"

    @property
    def tide_sign(self) -> int:
        return 1 if "+" in self.tide_level else -1

    @property
    def current_sign(self) -> int:
        return 1 if "+" in self.current_level else -1

    @property
    def wave_sign(self) -> int:
        return 1 if "+" in self.wave_level else -1

    @property
    def all_positive(self) -> bool:
        return self.tide_sign > 0 and self.current_sign > 0 and self.wave_sign > 0

    @property
    def all_negative(self) -> bool:
        return self.tide_sign < 0 and self.current_sign < 0 and self.wave_sign < 0

    @property
    def wave_diverges_tide(self) -> bool:
        """Wave opposes Tide — pullback or reversal."""
        return self.tide_sign != self.wave_sign


def _classify_one(value: float, channel: str) -> str:
    """Classify a single slope into +++/++/+/-/--/---."""
    th = _SLOPE_TH[channel]
    if value >= 0:
        p33, p66 = th["+"]
        if value >= p66:
            return f"{channel}+++"
        elif value >= p33:
            return f"{channel}++"
        else:
            return f"{channel}+"
    else:
        p33, p66 = th["-"]
        av = abs(value)
        if av >= p66:
            return f"{channel}---"
        elif av >= p33:
            return f"{channel}--"
        else:
            return f"{channel}-"


def classify_slopes(
    tide_slope: float,
    current_slope: float,
    wave_slope: float,
) -> SlopeState:
    """Classify 3 slopes into a unified SlopeState.

    Args:
        tide_slope: 240-bar regression slope
        current_slope: 60-bar regression slope
        wave_slope: cycle-adaptive regression slope

    Returns:
        SlopeState with levels, tripleta, and derived properties
    """
    t = _classify_one(tide_slope, "T")
    c = _classify_one(current_slope, "C")
    w = _classify_one(wave_slope, "W")
    return SlopeState(
        tide_level=t,
        current_level=c,
        wave_level=w,
        tripleta=f"{t}/{c}/{w}",
    )
