"""
RC State Probability — Pure Domain Rule
==========================================

DEPRECATION NOTICE (2026-06-25):
  The lookup_probability() function and RCStateProbability dataclass
  below are DEPRECATED. They read from rc_probability_table.json
  (17 tickers, 91K bars, 4D: Tide×σc×σw×σVw) which has been
#   superseded by rc_tide_derived.json (538 tickers, 628K bars,
#   3D: T×C×σVw, 180 committee-approved states).
#
#   Use rc_tide_lookup.lookup_tide_signal() instead.

  The DualProbability model (lookup_dual_probability) below is
  STILL ACTIVE — it uses rc_piso_table.json + rc_techo_table.json
  which capture different features (sign families × σVc × velocity).

Original docs:
  Loads the empirical P(bull|sigma_state) lookup table and provides
  a single function to query it.
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


# ═══════════════════════════════════════════════════════════════
# DUAL PROBABILITY MODEL (v2) — Asymmetric P(piso) / P(techo)
# ═══════════════════════════════════════════════════════════════
#
# Empirically validated features (Fase 0, walk-forward AUC):
#   PISOS:  sign_family × σVc_bin × vel_σVw_ema_sign × vol_surge_bin
#   TECHOS: sign_family × σc_bin × vel_σc_diff_sign × W_duration_bin
#
# Sign families (8 categories) replace 216 tripletas:
#   ALL_POS, ALL_NEG, T+C+W-, T+C-W+, T+C-W-, T-C+W+, T-C+W-, T-C-W+
#
# Evidence:
#   σVc replaces σVw for pisos: +0.0215 AUC (0.8457→0.8672)
#   rolling_corr eliminated: AUC Δ = 0.000
#   W_duration for techos: +0.0207 AUC
#   Sign families: L1 coverage 98.6% (vs 3% with full tripleta)

@dataclass(frozen=True)
class DualProbability:
    """Asymmetric P(piso) and P(techo) from empirical lookup tables.

    Pisos (fear/capitulation) and Techos (greed/fatigue) are physically
    distinct phenomena requiring different features. This dataclass
    captures both simultaneously from separate lookup tables.

    Consumed by swing_entry_rules for ACCUMULATE/TRIM decisions.
    Composed with TurnSignal (confirmation) and T9 (structural filter).
    """
    prob_piso: float          # P(near 7.5% MIN | state)
    prob_techo: float         # P(near 7.5% MAX | state)
    prob_piso_25: float       # P(near 2.5% MIN | state) — magnitude discrimination
    prob_piso_50: float       # P(near 5.0% MIN | state)
    prob_techo_50: float      # P(near 5.0% MAX | state)
    expected_magnitude: float  # Most likely correction depth (0.025/0.05/0.075)
    state_key_piso: str
    state_key_techo: str
    level_piso: str           # L1/L2/L3
    level_techo: str          # L1/L2/L3/L4
    n_piso: int
    n_techo: int
    family: str               # Sign family for logging

    @property
    def piso_dominant(self) -> bool:
        """P(piso) significantly exceeds base rate (~6%)."""
        return self.prob_piso > 0.10

    @property
    def techo_dominant(self) -> bool:
        """P(techo) significantly exceeds base rate (~7%).

        Threshold raised to 0.20 (from 0.12) based on walk-forward backtest:
        at 0.12 HR(down)=38.7% (worse than random in bull markets).
        At 0.20 only extreme techo states trigger trim.
        """
        return self.prob_techo > 0.20

    @property
    def net_bias(self) -> float:
        """Positive = piso likely, Negative = techo likely."""
        return self.prob_piso - self.prob_techo


# ── Singleton dual tables ──
_PISO_TABLE: Optional[dict] = None
_TECHO_TABLE: Optional[dict] = None
_PISO_PATH = Path(__file__).parent / "rc_piso_table.json"
_TECHO_PATH = Path(__file__).parent / "rc_techo_table.json"


def _load_dual_tables() -> tuple[dict, dict]:
    """Load both probability tables (once)."""
    global _PISO_TABLE, _TECHO_TABLE

    if _PISO_TABLE is None:
        if _PISO_PATH.exists():
            with open(_PISO_PATH) as f:
                _PISO_TABLE = json.load(f)
            n = len(_PISO_TABLE.get("cells", {}))
            logger.info(f"Piso table loaded: {n} cells from {_PISO_PATH.name}")
        else:
            logger.warning(f"Piso table not found: {_PISO_PATH}")
            _PISO_TABLE = {"cells": {}, "metadata": {}}

    if _TECHO_TABLE is None:
        if _TECHO_PATH.exists():
            with open(_TECHO_PATH) as f:
                _TECHO_TABLE = json.load(f)
            n = len(_TECHO_TABLE.get("cells", {}))
            logger.info(f"Techo table loaded: {n} cells from {_TECHO_PATH.name}")
        else:
            logger.warning(f"Techo table not found: {_TECHO_PATH}")
            _TECHO_TABLE = {"cells": {}, "metadata": {}}

    return _PISO_TABLE, _TECHO_TABLE


def _sign_family(tide_sign: int, current_sign: int, wave_sign: int) -> str:
    """Classify T/C/W signs into 8 families."""
    t = 1 if tide_sign > 0 else -1
    c = 1 if current_sign > 0 else -1
    w = 1 if wave_sign > 0 else -1

    if t > 0 and c > 0 and w > 0: return 'ALL_POS'
    if t < 0 and c < 0 and w < 0: return 'ALL_NEG'
    if t > 0 and c > 0 and w < 0: return 'T+C+W-'
    if t > 0 and c < 0 and w > 0: return 'T+C-W+'
    if t > 0 and c < 0 and w < 0: return 'T+C-W-'
    if t < 0 and c > 0 and w > 0: return 'T-C+W+'
    if t < 0 and c > 0 and w < 0: return 'T-C+W-'
    if t < 0 and c < 0 and w > 0: return 'T-C-W+'
    return 'OTHER'


def _vol_surge_bin(vol_surge: float, thresholds: dict) -> str:
    """Classify volume surge into 3 bins using training thresholds."""
    q33 = thresholds.get('q33', 0.82)
    q66 = thresholds.get('q66', 1.06)
    if vol_surge <= q33: return 'low'
    if vol_surge <= q66: return 'mid'
    return 'high'


def _w_duration_bin(w_duration: int, thresholds: dict) -> str:
    """Classify W_duration into 3 bins using training thresholds."""
    q33 = thresholds.get('q33', 3)
    q66 = thresholds.get('q66', 7)
    if w_duration <= q33: return 'short'
    if w_duration <= q66: return 'mid'
    return 'long'


def _lookup_cell(cells: dict, candidates: list[tuple[str, str]]) -> tuple[Optional[dict], str, str]:
    """Try hierarchical lookup, return (cell, key, level) or (None, '', '')."""
    for key, level in candidates:
        cell = cells.get(key)
        if cell is not None:
            return cell, key, level
    return None, '', ''


def lookup_dual_probability(
    tide_slope: float,
    current_slope: float,
    wave_slope: float,
    vwap_sigma_current: float,
    sigma_current: float,
    vel_sigma_vw_ema: float,
    vel_sigma_c_diff: float,
    vol_surge: float = 1.0,
    w_duration: int = 4,
    sigma_wave: float = 0.0,
) -> Optional[DualProbability]:
    """Look up dual P(piso) and P(techo) with hierarchical fallback.

    Each table uses DIFFERENT features (asymmetric by design):
      P(piso): family × σVc_bin × vel_σVw_ema_sign × vol_surge_bin
      P(techo): family × σc_bin × vel_σc_diff_sign × W_duration_bin
      L2 techo fallback: family × σc_bin × σw_bin

    Args:
        tide_slope: 240-bar regression slope
        current_slope: 60-bar regression slope
        wave_slope: Cycle-adaptive regression slope
        vwap_sigma_current: σVc — VWAP Current sigma (piso primary feature)
        sigma_current: σc — Price Current sigma (techo primary feature)
        vel_sigma_vw_ema: EMA-smoothed velocity of σVw (piso velocity)
        vel_sigma_c_diff: Raw diff of σc (techo velocity)
        vol_surge: Volume / SMA(volume, 20) — capitulation intensity
        w_duration: Consecutive bars at current W level
        sigma_wave: σw — Price Wave sigma (used in techo L2 fallback)

    Returns:
        DualProbability or None if tables are empty/missing.
    """
    piso_tbl, techo_tbl = _load_dual_tables()
    piso_cells = piso_tbl.get("cells", {})
    techo_cells = techo_tbl.get("cells", {})

    if not piso_cells and not techo_cells:
        return None

    # ── Classify inputs ──
    from backend.modules.quality_swing.domain.rules.rc_slope_classifier import classify_slopes
    slope = classify_slopes(tide_slope, current_slope, wave_slope)
    family = _sign_family(slope.tide_sign, slope.current_sign, slope.wave_sign)

    svc = _classify_sigma(vwap_sigma_current)
    sc = _classify_sigma(sigma_current)
    sw = _classify_sigma(sigma_wave)

    vel_vw_sign = '+' if vel_sigma_vw_ema > 0 else '-'
    vel_c_sign = '+' if vel_sigma_c_diff > 0 else '-'

    # Bin thresholds from training metadata
    piso_meta = piso_tbl.get("metadata", {})
    techo_meta = techo_tbl.get("metadata", {})
    bin_th = piso_meta.get("bin_thresholds", {})

    vs_bin = _vol_surge_bin(vol_surge, bin_th.get('vol_surge', {}))
    wd_bin = _w_duration_bin(w_duration, bin_th.get('W_duration', {}))

    # ── Piso lookup (family × σVc_bin × vel_sign × vol_bin) ──
    piso_candidates = [
        (f"L1:{family}|{svc}|{vel_vw_sign}|{vs_bin}", "L1"),
        (f"L2:{family}|{svc}", "L2"),
        (f"L3:{family}", "L3"),
    ]
    piso_cell, piso_key, piso_level = _lookup_cell(piso_cells, piso_candidates)

    # ── Techo lookup (family × σc_bin × vel_sign × W_dur_bin) ──
    techo_candidates = [
        (f"L1:{family}|{sc}|{vel_c_sign}|{wd_bin}", "L1"),
        (f"L2:{family}|{sc}|{sw}", "L2"),
        (f"L3:{family}|{sc}", "L3"),
        (f"L4:{family}", "L4"),
    ]
    techo_cell, techo_key, techo_level = _lookup_cell(techo_cells, techo_candidates)

    if piso_cell is None and techo_cell is None:
        return None

    # ── Extract probabilities ──
    p_piso = piso_cell["P_target"] if piso_cell else 0.0
    n_piso = piso_cell["N"] if piso_cell else 0
    p_techo = techo_cell["P_target"] if techo_cell else 0.0
    n_techo = techo_cell["N"] if techo_cell else 0

    # ── Magnitude discrimination from L2 magnitude-specific cells ──
    p_piso_25 = 0.0
    p_piso_50 = 0.0
    p_techo_50 = 0.0

    mag_piso_key = f"M0.025|L2:{family}|{svc}"
    if mag_piso_key in piso_cells:
        p_piso_25 = piso_cells[mag_piso_key]["P_target"]
    mag_piso50_key = f"M0.05|L2:{family}|{svc}"
    if mag_piso50_key in piso_cells:
        p_piso_50 = piso_cells[mag_piso50_key]["P_target"]
    mag_techo50_key = f"M0.05|L2:{family}|{sc}|{sw}"
    if mag_techo50_key in techo_cells:
        p_techo_50 = techo_cells[mag_techo50_key]["P_target"]

    # Determine expected magnitude from piso probabilities
    if p_piso_25 > 0 and p_piso_50 > 0 and p_piso > 0:
        # Higher magnitudes are subsets: P(7.5%) ⊂ P(5%) ⊂ P(2.5%)
        # Use the ratio to estimate expected depth
        if p_piso > 0.15:
            expected_mag = 0.075
        elif p_piso_50 > 0.15:
            expected_mag = 0.05
        elif p_piso_25 > 0.20:
            expected_mag = 0.025
        else:
            expected_mag = 0.025
    else:
        expected_mag = 0.025

    return DualProbability(
        prob_piso=round(p_piso, 4),
        prob_techo=round(p_techo, 4),
        prob_piso_25=round(p_piso_25, 4),
        prob_piso_50=round(p_piso_50, 4),
        prob_techo_50=round(p_techo_50, 4),
        expected_magnitude=expected_mag,
        state_key_piso=piso_key,
        state_key_techo=techo_key,
        level_piso=piso_level,
        level_techo=techo_level,
        n_piso=n_piso,
        n_techo=n_techo,
        family=family,
    )
