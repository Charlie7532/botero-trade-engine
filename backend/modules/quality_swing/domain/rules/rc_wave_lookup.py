"""
RC Wave Lookup — Pure Domain Rule
==========================================
Loads the pre-computed rc_wave_derived.json and provides a single function
to query it by W×σVc×σc×vel state.

This table classifies the *microstructure* of the Wave channel:
  W (Wave slope, 6 levels) × σVc (VWAP sigma current, 5 bins)
  × σc (sigma current, 5 bins) × vel (velocity of σVw, 3 bins)

Signals: APPROACHING_BOTTOM | WATCH_BOTTOM | APPROACHING_TOP |
         WATCH_TOP | CONTINUATION | NO_EDGE

Relationship to Combined:
  - Combined = "WHERE" (macro position via Tide×Current×σVw)
  - Wave = "WHEN" (micro timing via W×σVc×σc×vel)
  Wave operates as a sub-gate of Combined, modulating conviction
  based on pivot proximity and reversal quality.

Clean Architecture: Pure domain rule. Loads JSON once, no IO after init.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Singleton table ──
_WAVE: Optional[dict] = None
_WAVE_PATH = Path(__file__).parent / "rc_wave_derived.json"


@dataclass(frozen=True)
class WaveSignal:
    """Result of the Wave W×σVc×σc×vel lookup.

    Provides pivot prediction and reversal quality metrics
    for micro-level timing of entries and exits.
    """
    # Identity
    state_key: str            # "L1:W+++|σVc:<<|σc:<|vel:▼"
    level: str                # "L1", "L2", "L3"
    signal: str               # APPROACHING_BOTTOM / WATCH_BOTTOM / APPROACHING_TOP / WATCH_TOP / CONTINUATION / NO_EDGE
    wave_direction: str       # STRONG_UP / UP / MILD_UP / MILD_DOWN / DOWN / STRONG_DOWN
    wave_zone: str            # DEEP_DISCOUNT / DISCOUNT / NEUTRAL / PREMIUM / DEEP_PREMIUM
    channel_zone: str         # DEEP_DISCOUNT / DISCOUNT / NEUTRAL / PREMIUM / DEEP_PREMIUM
    momentum_state: str       # FALLING / FLAT / RISING
    conviction: str           # HIGH / MEDIUM / LOW
    conviction_score: int     # 0-100
    microstructure_type: str  # REVERSAL_BOTTOM / CONTINUATION_BULL / etc.

    # Frequency
    n_samples: int
    p_bull: float             # P(bull) percentage 0-100

    # Pivot prediction (composite)
    p_any_bottom: float       # P(any zigzag bottom near this state)
    p_any_top: float          # P(any zigzag top near this state)
    lift_best_bottom: float   # Best lift across zz levels for bottom
    lift_best_top: float      # Best lift across zz levels for top

    # Reversal quality (bottom)
    bot_pct_clean: float      # % of reversals that are clean (not double bottom)
    bot_avg_bars_to_turn: float  # Avg bars until confirmed turn

    # Reversal quality (top)
    top_pct_clean: float
    top_avg_bars_to_turn: float

    # Extreme velocity modifier (P10/P90 tails)
    # Data: lift(▼▼)=2.08× vs lift(▼)=1.63× for bottoms (+28%)
    #        lift(▲▲)=1.76× vs lift(▲)=1.56× for tops (+13%)
    extreme_vel_modifier: float = 1.0   # 1.0=no modifier, 1.25=extreme down, 1.15=extreme up
    extreme_vel_tag: str = ""           # "VEL_EXTREME_DOWN" or "VEL_EXTREME_UP" or ""

    @property
    def is_bottom_signal(self) -> bool:
        """Signal indicates pivot bottom proximity."""
        return self.signal in ("APPROACHING_BOTTOM", "WATCH_BOTTOM")

    @property
    def is_top_signal(self) -> bool:
        """Signal indicates pivot top proximity."""
        return self.signal in ("APPROACHING_TOP", "WATCH_TOP")

    @property
    def is_actionable(self) -> bool:
        """Signal is either bottom or top (not NO_EDGE/CONTINUATION)."""
        return self.is_bottom_signal or self.is_top_signal

    @property
    def conviction_factor(self) -> float:
        """conviction_score as 0.0-1.0 factor."""
        return self.conviction_score / 100.0

    @property
    def bottom_conviction(self) -> float:
        """Cell-level conviction for bottom signals.

        Scales by lift (predictive power) and clean% (reversal quality)
        rather than a fixed cap.  Range: ~0.2-0.6 for actionable signals.
        """
        return min(0.6, self.lift_best_bottom * 0.15 + self.bot_pct_clean * 0.003)

    @property
    def top_conviction(self) -> float:
        """Cell-level conviction for top signals."""
        return min(0.6, self.lift_best_top * 0.15 + self.top_pct_clean * 0.003)


# ── Extreme velocity thresholds (P10/P90 of Kalman obs_vel_svw) ──
# From empirical analysis: 640K bars, 539 tickers
_VEL_EXTREME_TH = (-0.434, 0.439)


# ── Wave slope thresholds (must match training) ──
_SLOPE_TH_W = {
    "+": (0.1262, 0.2717),
    "-": (0.1032, 0.2598),
}

# ── Sigma bins (must match training) ──
_SIGMA_BINS = [
    (-999.0, -1.0, "<<"),
    ( -1.0, -0.3, "<"),
    ( -0.3,  0.3, "~"),
    (  0.3,  1.0, ">"),
    (  1.0, 999.0, ">>"),
]

# ── Velocity thresholds (loaded from JSON metadata when available) ──
_VEL_SVW_TH = (-0.091, 0.091)


def _classify_wave_slope(value: float) -> str:
    """Classify wave_slope into W+++/W++/W+/W-/W--/W---."""
    if value >= 0:
        t1, t2 = _SLOPE_TH_W["+"]
        if value >= t2:
            return "W+++"
        elif value >= t1:
            return "W++"
        else:
            return "W+"
    else:
        t1, t2 = _SLOPE_TH_W["-"]
        av = abs(value)
        if av >= t2:
            return "W---"
        elif av >= t1:
            return "W--"
        else:
            return "W-"


def _classify_sigma(value: float) -> str:
    """Classify σ value into bin label."""
    for lo, hi, label in _SIGMA_BINS:
        if lo <= value < hi:
            return label
    return _SIGMA_BINS[-1][2]


def _classify_vel_svw(vel: float) -> str:
    """Classify vel_σVw into ▼/~/▲."""
    if vel < _VEL_SVW_TH[0]:
        return "▼"
    elif vel > _VEL_SVW_TH[1]:
        return "▲"
    return "~"


def _load_wave() -> dict:
    """Load the wave derived table (once)."""
    global _WAVE, _VEL_SVW_TH
    if _WAVE is not None:
        return _WAVE

    if not _WAVE_PATH.exists():
        logger.warning(f"RC wave derived table not found at {_WAVE_PATH}")
        _WAVE = {"states": {}}
        return _WAVE

    with open(_WAVE_PATH) as f:
        _WAVE = json.load(f)

    # Load velocity thresholds from metadata if present (Phase 1 fix)
    if "vel_thresholds" in _WAVE:
        global _VEL_SVW_TH
        th = _WAVE["vel_thresholds"]
        _VEL_SVW_TH = (th["lower"], th["upper"])
        logger.info(f"RC wave vel thresholds from metadata: {_VEL_SVW_TH}")

    n_states = len(_WAVE.get("states", {}))
    version = _WAVE.get("version", "unknown")
    logger.info(f"RC wave derived table loaded: {n_states} states, version={version}")
    return _WAVE


def _make_result(state_key: str, state: dict,
                 vel_modifier: float = 1.0, vel_tag: str = "") -> WaveSignal:
    """Convert a raw state dict into WaveSignal."""
    identity = state["identity"]
    frequency = state["frequency"]
    pivot = state["pivot_prediction"]
    composite = pivot["composite"]
    rq = state["reversal_quality"]

    # Extract reversal quality safely (some cells may not have enough data)
    bot_rq = rq.get("bottom", {})
    top_rq = rq.get("top", {})

    level = state_key.split(":")[0] if ":" in state_key else "L1"

    return WaveSignal(
        state_key=state_key,
        level=level,
        signal=identity["signal"],
        wave_direction=identity["wave_direction"],
        wave_zone=identity["wave_zone"],
        channel_zone=identity["channel_zone"],
        momentum_state=identity["momentum_state"],
        conviction=identity["conviction"],
        conviction_score=identity["conviction_score"],
        microstructure_type=identity["microstructure_type"],
        n_samples=frequency["N"],
        p_bull=frequency["p_bull"],
        p_any_bottom=composite["p_any_bottom"],
        p_any_top=composite["p_any_top"],
        lift_best_bottom=composite["lift_best_bottom"],
        lift_best_top=composite["lift_best_top"],
        bot_pct_clean=bot_rq.get("pct_clean", 0.0),
        bot_avg_bars_to_turn=bot_rq.get("avg_bars_to_turn", 0.0),
        top_pct_clean=top_rq.get("pct_clean", 0.0),
        top_avg_bars_to_turn=top_rq.get("avg_bars_to_turn", 0.0),
        extreme_vel_modifier=vel_modifier,
        extreme_vel_tag=vel_tag,
    )


# ═══════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════

def lookup_wave_signal(
    wave_slope: float,
    vwap_sigma_current: float,
    sigma_current: float,
    vel_svw: float,
) -> Optional[WaveSignal]:
    """Look up the wave signal for a W×σVc×σc×vel state.

    Implements L1→L2→L3 fallback cascade:
      L1: Full W×σVc×σc×vel key (443 states, most granular)
      L2: Aggregated key (30 states, moderate granularity)
      L3: Broad key (5 states, maximum coverage)

    Args:
        wave_slope: Wave regression slope (continuous value).
        vwap_sigma_current: σ position of VWAP in Current channel.
        sigma_current: σ position of price in Current channel.
        vel_svw: Velocity of σV_Wave (from Observer Kalman or EMA diff).

    Returns:
        WaveSignal or None if state not found at any level.
    """
    table = _load_wave()
    states = table.get("states", {})

    if not states:
        return None

    # Classify into bins
    w_bin = _classify_wave_slope(wave_slope)
    svc_bin = _classify_sigma(vwap_sigma_current)
    sc_bin = _classify_sigma(sigma_current)
    vel_bin = _classify_vel_svw(vel_svw)

    # Compute extreme velocity modifier (P10/P90 tails)
    # Data: lift(▼▼)=2.08× vs lift(▼)=1.63× for bottoms (+28%)
    #        lift(▲▲)=1.76× vs lift(▲)=1.56× for tops (+13%)
    vel_modifier = 1.0
    vel_tag = ""
    if vel_svw < _VEL_EXTREME_TH[0]:       # < P10: extreme deceleration
        vel_modifier = 1.25
        vel_tag = "VEL_EXTREME_DOWN"
    elif vel_svw > _VEL_EXTREME_TH[1]:      # > P90: extreme acceleration
        vel_modifier = 1.15
        vel_tag = "VEL_EXTREME_UP"

    # L1: Full resolution
    l1_key = f"L1:{w_bin}|σVc:{svc_bin}|σc:{sc_bin}|vel:{vel_bin}"
    state = states.get(l1_key)
    if state is not None:
        return _make_result(l1_key, state, vel_modifier, vel_tag)

    # L2: Drop vel dimension (30 states = W×σVc)
    l2_key = f"L2:{w_bin}|σVc:{svc_bin}"
    state = states.get(l2_key)
    if state is not None:
        return _make_result(l2_key, state, vel_modifier, vel_tag)

    # L3: Wave direction only (5 states)
    l3_key = f"L3:{w_bin}"
    state = states.get(l3_key)
    if state is not None:
        return _make_result(l3_key, state, vel_modifier, vel_tag)

    logger.debug(f"Wave state not found at any level: {l1_key}")
    return None


def get_wave_metadata() -> dict:
    """Return metadata about the loaded table (version, context, baselines)."""
    table = _load_wave()
    return {k: v for k, v in table.items() if k != "states"}
