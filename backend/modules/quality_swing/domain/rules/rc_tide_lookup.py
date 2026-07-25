"""
RC Tide Lookup — Pure Domain Rule
==========================================
Loads the pre-computed rc_tide_derived.json (v2) and provides
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
_TIDE: Optional[dict] = None
_TIDE_PATH = Path(__file__).parent / "rc_tide_derived.json"


ACTION_CODE_MAP = {
    "ACCUMULATE": ("STK_ACCUMULATE_STRUCTURAL", "LOW", "STK"),
    "BUY_DIP": ("STK_BUY_DIP_TACTICAL", "HIGH", "STK"),
    "MOMENTUM": ("STK_ACCUMULATE_PASSIVE", "LOW", "STK"),
    "BULL_TREND": ("STK_HOLD_STABLE", "PASSIVE", "STK"),
    "STRONG_TREND": ("STK_HOLD_EXTENDED", "PASSIVE", "STK"),
    "WATCH": ("STK_WATCH_PASSIVE", "PASSIVE", "STK"),
    "NO_EDGE": ("STK_HOLD_NEUTRAL", "PASSIVE", "STK"),
    "REDUCE": ("STK_DISTRIBUTE_DECAY", "NORMAL", "STK"),
    "TAKE_PROFIT": ("STK_TRIM_TACTICAL", "LOW", "STK"),
    "CRISIS_VETO": ("STK_BLOCK_CRISIS", "IMMEDIATE", "STK"),
    # Direct Universal Taxonomy mapping
    "STK_ACCUMULATE_STRUCTURAL": ("STK_ACCUMULATE_STRUCTURAL", "LOW", "STK"),
    "STK_BUY_DIP_TACTICAL": ("STK_BUY_DIP_TACTICAL", "HIGH", "STK"),
    "STK_ACCUMULATE_PASSIVE": ("STK_ACCUMULATE_PASSIVE", "LOW", "STK"),
    "STK_HOLD_STABLE": ("STK_HOLD_STABLE", "PASSIVE", "STK"),
    "STK_HOLD_EXTENDED": ("STK_HOLD_EXTENDED", "PASSIVE", "STK"),
    "STK_WATCH_PASSIVE": ("STK_WATCH_PASSIVE", "PASSIVE", "STK"),
    "STK_HOLD_NEUTRAL": ("STK_HOLD_NEUTRAL", "PASSIVE", "STK"),
    "STK_DISTRIBUTE_DECAY": ("STK_DISTRIBUTE_DECAY", "NORMAL", "STK"),
    "STK_TRIM_TACTICAL": ("STK_TRIM_TACTICAL", "LOW", "STK"),
    "STK_BLOCK_CRISIS": ("STK_BLOCK_CRISIS", "IMMEDIATE", "STK"),
}



@dataclass(frozen=True)
class TideSignal:
    """Result of the tide T×C×σVw lookup.

    Provides the full committee-approved signal with all
    supporting metrics for decision making and logging.
    """
    # Identity
    state_key: str          # "T+++|C---|<<"
    signal: str             # ACCUMULATE / BUY_DIP / TAKE_PROFIT / REDUCE / MOMENTUM / BULL_TREND / WATCH / NO_EDGE
    action_code: str        # STK_ACCUMULATE_STRUCTURAL / STK_BUY_DIP_TACTICAL / STK_HOLD_STABLE / STK_TRIM_TACTICAL / etc.
    urgency_level: str      # LOW / HIGH / PASSIVE / NORMAL / IMMEDIATE
    scope_level: str        # STK / SEC / MKT
    zone: str               # FLOOR / BELOW / NEUTRAL / ABOVE / CEILING
    regime: str             # ALIGN_BULL / ALIGN_BEAR / DIV_UP / DIV_DOWN / TRANSITION
    conviction: str         # HIGH / MEDIUM / LOW
    conviction_score: int   # 0-100 (statistical: log(N) x z-score)
    signal_confidence: int  # 0-100 (empirical: sample size x edge x stability x repetition penalty)

    # Direction
    p_bull: float           # P(bull) as percentage (0-100)
    odds: float             # tide/bear ratio
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
        return self.signal in ("ACCUMULATE", "BUY_DIP") or self.action_code in ("STK_ACCUMULATE_STRUCTURAL", "STK_BUY_DIP_TACTICAL")

    @property
    def is_trim(self) -> bool:
        """Signal recommends reducing exposure."""
        return self.signal in ("TAKE_PROFIT", "REDUCE") or self.action_code in ("STK_TRIM_TACTICAL", "STK_DISTRIBUTE_DECAY")

    @property
    def is_hold(self) -> bool:
        """Signal recommends holding or no action."""
        return self.signal in ("MOMENTUM", "STRONG_TREND", "BULL_TREND", "WATCH", "NO_EDGE") or self.action_code in ("STK_HOLD_STABLE", "STK_HOLD_EXTENDED", "STK_ACCUMULATE_PASSIVE")

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
        """signal_confidence as 0.0-1.0 factor."""
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


def _load_tide() -> dict:
    """Load the tide derived table (once)."""
    global _TIDE
    if _TIDE is not None:
        return _TIDE

    if not _TIDE_PATH.exists():
        logger.warning(f"RC tide derived table not found at {_TIDE_PATH}")
        _TIDE = {"states": {}}
        return _TIDE

    with open(_TIDE_PATH) as f:
        _TIDE = json.load(f)

    n_states = len(_TIDE.get("states", {}))
    version = _TIDE.get("version", "unknown")
    logger.info(f"RC tide derived table loaded: {n_states} states, version={version}")
    return _TIDE


from backend.modules.quality_swing.domain.rules.signal_cataloger import SignalCataloger, TideFeatureVector


def classify_tide_signal_from_features(identity: dict, direction: dict, turn_risk: dict, composition: dict) -> tuple[str, str, str, str]:
    """Pure Python classifier for Tide Features (Delegates to SignalCataloger)."""
    if "signal" in identity:
        sig = identity["signal"]
        ac, urg, sc = ACTION_CODE_MAP.get(sig, ("STK_HOLD_STABLE", "PASSIVE", "STK"))
        return sig, ac, urg, sc

    features = TideFeatureVector(
        zone=identity["zone"],
        p_bull=direction["p_bull"],
        asymmetry_pp=turn_risk["asymmetry_pp"],
        zz25_min_pct=turn_risk["bottom_25"]["pct"],
        zz25_max_pct=turn_risk["top_25"]["pct"],
        zz50_min_pct=turn_risk.get("bottom_50", {}).get("pct", 0.0),
        zz50_max_pct=turn_risk.get("top_50", {}).get("pct", 0.0),
        zz75_min_pct=turn_risk.get("bottom_75", {}).get("pct", 0.0),
        momentum_purity=composition["momentum_purity"],
    )
    return SignalCataloger.classify_tide(features)



def _make_result(state_key: str, state: dict) -> TideSignal:
    """Convert a raw state dict into TideSignal."""
    identity = state["identity"]
    direction = state["direction"]
    turn_risk = state["turn_risk"]
    composition = state["composition"]
    frequency = state["frequency"]

    sig, ac, urg, sc = classify_tide_signal_from_features(identity, direction, turn_risk, composition)

    return TideSignal(
        state_key=state_key,
        signal=sig,
        action_code=ac,
        urgency_level=urg,
        scope_level=sc,
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

def lookup_tide_signal(
    tide_level: str,
    current_level: str,
    vwap_sigma_wave: float,
) -> Optional[TideSignal]:
    """Look up the tide signal for a T×C×σVw state.

    Args:
        tide_level: Tide slope level from SlopeState (e.g. "T+++", "T-")
        current_level: Current slope level from SlopeState (e.g. "C---", "C++")
        vwap_sigma_wave: σVWAP position in Wave channel (continuous value)

    Returns:
        TideSignal or None if state not found in table.
    """
    table = _load_tide()
    states = table.get("states", {})

    if not states:
        return None

    svw_bin = _classify_sigma(vwap_sigma_wave)
    state_key = f"{tide_level}|{current_level}|{svw_bin}"

    state = states.get(state_key)
    if state is None:
        logger.debug(f"Tide state not found: {state_key}")
        return None

    return _make_result(state_key, state)


def get_tide_metadata() -> dict:
    """Return metadata about the loaded table (version, context, baselines)."""
    table = _load_tide()
    return {k: v for k, v in table.items() if k != "states"}
