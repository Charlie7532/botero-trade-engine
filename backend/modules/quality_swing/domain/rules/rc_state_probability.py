"""
RC State Probability — Pure Domain Rule
==========================================
Loads the empirical P(bull|sigma_state) lookup table and provides
a single function to query it.

State dimensions (from audit §22):
  1. σVWAP_wave  (IG=0.3942, TOP predictor)
  2. σ_current   (IG=0.2986)
  3. σ_wave      (IG=0.2894)
  4. tide_slope  (context macro)

Hierarchical fallback:
  L1: Full 4D (Tide × σ_c × σ_w × σVw) — max precision
  L2: 3D (σ_c × σ_w × σVw) — robust when L1 sparse
  L3: 2D (σ_c × σVw) — core pair
  L4: 1D (σVw) — ultimate fallback

Clean Architecture: Pure domain rule. Loads JSON once, no IO after init.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Singleton table ──
_TABLE: Optional[dict] = None
_TABLE_PATH = Path(__file__).parent / "rc_probability_table.json"


@dataclass(frozen=True)
class RCStateProbability:
    """Result of the P(bull|state) lookup.

    Bidirectional: the same state simultaneously informs long and short
    strategies. prob_bull drives accumulation; prob_bear drives trimming
    or short entries. Consumers decide based on their department rules.
    """
    prob_bull: float        # P(HH + HL) — probability of bullish outcome
    prob_hh: float          # P(Higher High) — breakout
    prob_hl: float          # P(Higher Low)  — healthy pullback
    prob_lh: float          # P(Lower High)  — distribution / ceiling
    prob_ll: float          # P(Lower Low)   — breakdown
    confidence: float       # Wilson interval lower bound
    n_samples: int          # Number of observations backing this cell
    state_key: str          # Full state key for logging
    level: str              # L1_full / L2_no_tide / L3_sc_svw / L4_svw
    action: str             # ACCUMULATE / TRIM / HOLD
    conviction: float       # 0.0-1.0 based on distance from 50%

    @property
    def prob_bear(self) -> float:
        """P(LH) + P(LL) — probability of bearish outcome.

        Same event, opposite perspective:
          prob_bull high → ACCUMULATE long / EXIT short
          prob_bear high → TRIM long / ENTRY short
        """
        return round(self.prob_lh + self.prob_ll, 4)


# ── Bin configuration (must match training script) ──

_SIGMA_BINS = [
    (-999, -1.0, "<<"),
    (-1.0, -0.3, "<"),
    (-0.3,  0.3, "~"),
    ( 0.3,  1.0, ">"),
    ( 1.0,  999, ">>"),
]

_TIDE_BINS = [
    (-999,  -0.03, "T---"),
    (-0.03, -0.01, "T--"),
    (-0.01,  0.0,  "T-"),
    ( 0.0,   0.01, "T+"),
    ( 0.01,  0.03, "T++"),
    ( 0.03,  999,  "T+++"),
]

# ── Thresholds ──
ACCUMULATE_THRESHOLD = 0.70   # P(bull) >= 70% → ACCUMULATE
TRIM_THRESHOLD = 0.30         # P(bull) <= 30% → TRIM


def _classify_sigma(value: float) -> str:
    """Classify sigma value into bin label."""
    for lo, hi, label in _SIGMA_BINS:
        if lo <= value < hi:
            return label
    return _SIGMA_BINS[-1][2]


def _classify_tide(value: float) -> str:
    """Classify tide slope into bin label."""
    for lo, hi, label in _TIDE_BINS:
        if lo <= value < hi:
            return label
    return _TIDE_BINS[-1][2]


def _load_table() -> dict:
    """Load the probability table JSON (once)."""
    global _TABLE
    if _TABLE is not None:
        return _TABLE

    if not _TABLE_PATH.exists():
        logger.warning(f"RC probability table not found at {_TABLE_PATH}")
        _TABLE = {"cells": {}}
        return _TABLE

    with open(_TABLE_PATH) as f:
        _TABLE = json.load(f)

    n_cells = len(_TABLE.get("cells", {}))
    logger.info(f"RC probability table loaded: {n_cells} cells from {_TABLE_PATH.name}")
    return _TABLE


def _make_result(cell: dict, state_key: str) -> RCStateProbability:
    """Convert a raw cell dict into RCStateProbability."""
    p_bull = cell["P_bull"]

    # Conviction: distance from 50%, normalized to 0-1
    conviction = min(abs(p_bull - 0.5) * 2.0, 1.0)

    # Action based on thresholds
    if p_bull >= ACCUMULATE_THRESHOLD:
        action = "ACCUMULATE"
    elif p_bull <= TRIM_THRESHOLD:
        action = "TRIM"
    else:
        action = "HOLD"

    return RCStateProbability(
        prob_bull=round(p_bull, 4),
        prob_hh=round(cell.get("P_HH", 0.0), 4),
        prob_hl=round(cell.get("P_HL", 0.0), 4),
        prob_lh=round(cell.get("P_LH", 0.0), 4),
        prob_ll=round(cell.get("P_LL", 0.0), 4),
        confidence=round(cell.get("confidence", 0.0), 3),
        n_samples=cell.get("N", 0),
        state_key=state_key,
        level=cell.get("level", "unknown"),
        action=action,
        conviction=round(conviction, 3),
    )


# ═══════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════

def lookup_probability(
    tide_slope: float,
    sigma_current: float,
    sigma_wave: float,
    vwap_sigma_wave: float,
) -> Optional[RCStateProbability]:
    """Look up P(bull|state) with hierarchical fallback.

    Tries L1 (4D) first, falls back to L2 (3D), L3 (2D), L4 (1D).
    Returns None only if even L4 has no data (should never happen
    with a properly trained table).

    Args:
        tide_slope: Tide regression slope (from channel_snapshot)
        sigma_current: σ position in Current channel
        sigma_wave: σ position in Wave channel
        vwap_sigma_wave: σVWAP position in Wave channel

    Returns:
        RCStateProbability or None if table is empty/missing.
    """
    table = _load_table()
    cells = table.get("cells", {})

    if not cells:
        return None

    # Classify into bins
    sc = _classify_sigma(sigma_current)
    sw = _classify_sigma(sigma_wave)
    svw = _classify_sigma(vwap_sigma_wave)
    tide = _classify_tide(tide_slope)

    # Hierarchical lookup: L1 → L2 → L3 → L4
    keys_to_try = [
        (f"L1_full:{tide}|{sc}|{sw}|{svw}", f"{tide}|{sc}|{sw}|{svw}"),
        (f"L2_no_tide:{sc}|{sw}|{svw}", f"{sc}|{sw}|{svw}"),
        (f"L3_sc_svw:{sc}|{svw}", f"{sc}|{svw}"),
        (f"L4_svw:{svw}", f"{svw}"),
    ]

    for lookup_key, display_key in keys_to_try:
        if lookup_key in cells:
            return _make_result(cells[lookup_key], display_key)

    # Should never reach here with a properly trained table
    return None


def get_table_metadata() -> dict:
    """Return metadata about the loaded table (version, n_cells, etc.)."""
    table = _load_table()
    return {k: v for k, v in table.items() if k != "cells"}
