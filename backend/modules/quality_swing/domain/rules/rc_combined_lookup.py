"""
RC Combined Lookup — Pure Domain Rule
==========================================
Loads the pre-computed rc_combined_derived.json (v2) and provides
a single function to query it by T×C×σVw state.

This table provides the committee-approved signal for each of the
180 possible states of the Regression Channel model:
  T (Tide slope, 6 levels) × C (Current slope, 6 levels)
  × σVw (VWAP Wave position, 5 bins)

Signals: ACCUMULATE | BUY_DIP | MOMENTUM | BULL_TREND |
         REDUCE | TAKE_PROFIT | WATCH | NO_EDGE

Clean Architecture: Pure domain rule. Loads JSON once, no IO after init.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Singleton table ──
_COMBINED: Optional[dict] = None
_COMBINED_PATH = Path(__file__).parent / "rc_combined_derived.json"


@dataclass(frozen=True)
class CombinedSignal:
    """Result of the combined T×C×σVw lookup.

    Provides the full committee-approved signal with all
    supporting metrics for decision making and logging.
    """
    # Identity
    state_key: str          # "T+++|C---|<<"
    signal: str             # ACCUMULATE / BUY_DIP / TAKE_PROFIT / REDUCE / MOMENTUM / BULL_TREND / WATCH / NO_EDGE
    zone: str               # FLOOR / BELOW / NEUTRAL / ABOVE / CEILING
    regime: str             # ALIGN_BULL / ALIGN_BEAR / DIV_UP / DIV_DOWN / TRANSITION
    conviction: str         # HIGH / MEDIUM / LOW
    conviction_score: int   # 0-100 (statistical: log(N) x z-score)
    signal_confidence: int  # 0-100 (empirical: sample size x edge x stability x repetition penalty)

    # Direction
    p_bull: float           # P(bull) as percentage (0-100)
    odds: float             # bull/bear ratio
    lift_vs_band: float     # lift relative to σVw band baseline
    z_score: float          # z-score vs global P_bull

    # Turn risk
    bottom_25_pct: float    # % of bars that are 2.5% zigzag bottoms
    top_25_pct: float       # % of bars that are 2.5% zigzag tops
    asymmetry_pp: float     # bottom - top density in pp (positive = bottoms dominate)

    # Composition
    momentum_purity: float  # HH / (HH+HL) — how clean is the momentum
    capitulation_purity: float  # LL / (LH+LL) — how pure is the selling

    # Frequency
    n_samples: int          # Number of observations
    rank: int               # Rank 1-180 by frequency

    # Optional flags
    predictive_edge: Optional[str]  # LEADING_BOTTOM / LEADING_TOP / None
    rotation_flag: Optional[str]    # EARLY_ROTATION / LATE_CYCLE_WARNING / None

    # Human reading
    reading: str

    @property
    def is_accumulate(self) -> bool:
        """Signal recommends accumulation."""
        return self.signal in ("ACCUMULATE", "BUY_DIP")

    @property
    def is_trim(self) -> bool:
        """Signal recommends reducing exposure."""
        return self.signal in ("TAKE_PROFIT", "REDUCE")

    @property
    def is_hold(self) -> bool:
        """Signal recommends holding or no action."""
        return self.signal in ("MOMENTUM", "STRONG_TREND", "BULL_TREND", "WATCH", "NO_EDGE")

    @property
    def is_bullish_zone(self) -> bool:
        """Price is in ABOVE or CEILING zone."""
        return self.zone in ("ABOVE", "CEILING")

    @property
    def is_bearish_zone(self) -> bool:
        """Price is in FLOOR or BELOW zone."""
        return self.zone in ("FLOOR", "BELOW")

    @property
    def conviction_factor(self) -> float:
        """conviction_score as 0.0-1.0 factor (statistical: log(N) x z-score)."""
        return self.conviction_score / 100.0

    @property
    def confidence_factor(self) -> float:
        """signal_confidence as 0.0-1.0 factor.

        This is the PREFERRED sizing input: it integrates empirical edge strength,
        sample size, state stability, and pivot repetition penalty — giving a more
        complete picture of the signal quality than conviction_score alone.
        """
        return self.signal_confidence / 100.0


# ── Sigma bin classification (must match training) ──
_SIGMA_BINS = [
    (-999, -1.0, "<<"),
    (-1.0, -0.3, "<"),
    (-0.3,  0.3, "~"),
    ( 0.3,  1.0, ">"),
    ( 1.0,  999, ">>"),
]


def _classify_sigma(value: float) -> str:
    """Classify σVw value into bin label."""
    for lo, hi, label in _SIGMA_BINS:
        if lo <= value < hi:
            return label
    return _SIGMA_BINS[-1][2]


def _load_combined() -> dict:
    """Load the combined derived table (once)."""
    global _COMBINED
    if _COMBINED is not None:
        return _COMBINED

    if not _COMBINED_PATH.exists():
        logger.warning(f"RC combined derived table not found at {_COMBINED_PATH}")
        _COMBINED = {"states": {}}
        return _COMBINED

    with open(_COMBINED_PATH) as f:
        _COMBINED = json.load(f)

    n_states = len(_COMBINED.get("states", {}))
    version = _COMBINED.get("version", "unknown")
    logger.info(f"RC combined derived table loaded: {n_states} states, version={version}")
    return _COMBINED


def _make_result(state_key: str, state: dict) -> CombinedSignal:
    """Convert a raw state dict into CombinedSignal."""
    identity = state["identity"]
    direction = state["direction"]
    turn_risk = state["turn_risk"]
    composition = state["composition"]
    frequency = state["frequency"]

    return CombinedSignal(
        state_key=state_key,
        signal=identity["signal"],
        zone=identity["zone"],
        regime=identity["regime"],
        conviction=identity["conviction"],
        conviction_score=identity["conviction_score"],
        signal_confidence=identity.get("signal_confidence", 0),
        p_bull=direction["p_bull"],
        odds=direction["odds"] or 0.0,
        lift_vs_band=direction["lift_vs_band"] or 1.0,
        z_score=direction["z_score"],
        bottom_25_pct=turn_risk["bottom_25"]["pct"],
        top_25_pct=turn_risk["top_25"]["pct"],
        asymmetry_pp=turn_risk["asymmetry_pp"],
        momentum_purity=composition["momentum_purity"],
        capitulation_purity=composition["capitulation_purity"],
        n_samples=frequency["N"],
        rank=frequency["rank"],
        predictive_edge=identity.get("predictive_edge"),
        rotation_flag=identity.get("rotation_flag"),
        reading=state.get("reading", ""),
    )


# ═══════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════

def lookup_combined_signal(
    tide_level: str,
    current_level: str,
    vwap_sigma_wave: float,
) -> Optional[CombinedSignal]:
    """Look up the combined signal for a T×C×σVw state.

    Args:
        tide_level: Tide slope level from SlopeState (e.g. "T+++", "T-")
        current_level: Current slope level from SlopeState (e.g. "C---", "C++")
        vwap_sigma_wave: σVWAP position in Wave channel (continuous value)

    Returns:
        CombinedSignal or None if state not found in table.
    """
    table = _load_combined()
    states = table.get("states", {})

    if not states:
        return None

    svw_bin = _classify_sigma(vwap_sigma_wave)
    state_key = f"{tide_level}|{current_level}|{svw_bin}"

    state = states.get(state_key)
    if state is None:
        logger.debug(f"Combined state not found: {state_key}")
        return None

    return _make_result(state_key, state)


def get_combined_metadata() -> dict:
    """Return metadata about the loaded table (version, context, baselines)."""
    table = _load_combined()
    return {k: v for k, v in table.items() if k != "states"}
