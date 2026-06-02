"""
Turn Detector — Pure Domain Rule
====================================
Complete turn-proximity detection pipeline.

Entry:  ChannelSnapshot + KalmanSnapshot + model scores
Exit:   TurnSignal (archetype + density + action per department)

Pipeline:
  1. detect_turn()       → prob_piso, prob_techo
  2. classify_archetype() → HL / LL / HH / LH / NONE
  3. assess_density()     → SILENCIO / ALARMA / PRESURIZACIÓN / EXPLOSIÓN
  4. map_actions()        → action per department
  5. compute_turn_signal() → TurnSignal (main entry point)

Evidence basis:
  Signal Replay (91K bars, 17 tickers, 20% OOS test):
  LL: hit_10d=59.3%, LIFT=1.03x, mean_ret=+1.09% → ACCUMULATE ✅
  HL: hit_10d=56.1%, LIFT=0.98x, mean_ret=+0.74% → ACCUMULATE (marginal)
  HH: hit_10d=41.2%, LIFT=0.97x → conviction reducer only
  LH: hit_10d=44.0%, LIFT=1.04x → conviction reducer only
  PISO model AUC=0.836, TECHO model AUC=0.720

Clean Architecture: Domain rule. Pure functions, no IO.
"""
from backend.modules.shared.domain.entities.turn_signal import (
    TurnSignal,
    ARCHETYPE_HL, ARCHETYPE_LL, ARCHETYPE_HH, ARCHETYPE_LH, ARCHETYPE_NONE,
    DENSITY_SILENCE, DENSITY_ALARM, DENSITY_PRESSURIZE, DENSITY_EXPLOSION,
    ACTION_ACCUMULATE, ACTION_TRIM, ACTION_SHORT, ACTION_COVER, ACTION_HOLD,
)
from backend.modules.shared.domain.rules.kalman_5channel import KalmanSnapshot


# ── Thresholds (calibrated from Sprint 2 Phase J) ──
PROB_THRESHOLD = 0.5           # Minimum to activate ALARMA
DENSITY_PRESSURIZE_MIN = 5     # 3-bar rolling density for PRESURIZACIÓN
DENSITY_EXPLOSION_MIN = 8      # 3-bar rolling density for EXPLOSIÓN

# Archetype classification thresholds
RSI_OVERSOLD_THRESHOLD = 40.0  # Below → LL candidate
RSI_NEUTRAL_LOW = 45.0         # Above → HL candidate
RSI_OVERBOUGHT_THRESHOLD = 60.0  # Above → HH candidate


def classify_archetype(
    prob_piso: float,
    prob_techo: float,
    kf_rsi_pred: float,
    tide_slope: float,
    crescendo: bool,
) -> str:
    """Classify turn archetype from probabilities + context.

    Rules calibrated from Sprint 2 Phase J archetype analysis:
      HL: piso detected + RSI neutral + tide bullish → pullback in uptrend
      LL: piso detected + RSI oversold + crescendo → capitulation
      HH: techo detected + RSI overbought + tide bullish → exhaustion
      LH: techo detected + tide bearish + crescendo → failed rally
    """
    # ── PISO archetypes ──
    if prob_piso > prob_techo and prob_piso > PROB_THRESHOLD:
        if kf_rsi_pred < RSI_OVERSOLD_THRESHOLD and crescendo:
            return ARCHETYPE_LL  # Capitulation: RSI collapsing + crescendo
        if kf_rsi_pred >= RSI_NEUTRAL_LOW:
            return ARCHETYPE_HL  # Pullback: RSI neutral, orderly dip
        # Default piso without clear archetype signature
        if tide_slope > 0:
            return ARCHETYPE_HL  # In uptrend → most likely pullback
        return ARCHETYPE_LL      # In downtrend → likely capitulation

    # ── TECHO archetypes ──
    if prob_techo > prob_piso and prob_techo > PROB_THRESHOLD:
        if tide_slope < 0 and crescendo:
            return ARCHETYPE_LH  # Failed rally: bear trend + crescendo
        if kf_rsi_pred > RSI_OVERBOUGHT_THRESHOLD:
            return ARCHETYPE_HH  # Exhaustion: RSI high, complacency
        # Default techo without clear signature
        if tide_slope > 0:
            return ARCHETYPE_HH  # In uptrend → likely exhaustion/top
        return ARCHETYPE_LH      # In downtrend → likely failed rally

    return ARCHETYPE_NONE


def assess_density(
    prob: float,
    density_history: list[float],
) -> tuple[str, int, bool]:
    """3-level density gate from Sprint 2 thresholds.

    Args:
        prob: max(prob_piso, prob_techo) for the current bar
        density_history: list of max(prob_piso, prob_techo) for last 5 bars

    Returns:
        (density_level, density_count, crescendo)
    """
    # Count bars with prob > threshold in last 3 bars (including current)
    recent = density_history[-2:] + [prob] if len(density_history) >= 2 else [prob]
    density_count = sum(1 for p in recent if p > PROB_THRESHOLD)

    # Crescendo: density increasing over last 5 bars
    all_probs = density_history + [prob]
    crescendo = False
    if len(all_probs) >= 3:
        # Check if the last 3 values are monotonically increasing
        tail = all_probs[-3:]
        crescendo = tail[-1] > tail[-2] > tail[-3]

    # Classify density level
    if prob <= PROB_THRESHOLD:
        return DENSITY_SILENCE, 0, crescendo
    if density_count >= DENSITY_EXPLOSION_MIN:
        return DENSITY_EXPLOSION, density_count, crescendo
    if density_count >= DENSITY_PRESSURIZE_MIN:
        return DENSITY_PRESSURIZE, density_count, crescendo
    return DENSITY_ALARM, density_count, crescendo


def _map_conviction(density_level: str) -> float:
    """Map density level to conviction score."""
    return {
        DENSITY_SILENCE: 0.0,
        DENSITY_ALARM: 0.3,
        DENSITY_PRESSURIZE: 0.6,
        DENSITY_EXPLOSION: 0.9,
    }.get(density_level, 0.0)


def _map_actions(
    archetype: str,
    density_level: str,
) -> tuple[str, str, str]:
    """Map archetype to action per department.

    Signal Replay calibration (91K bars, 17 tickers, 20% OOS):
      LL: hit_10d=59.3%, LIFT=1.03x → ACCUMULATE ✅
      HL: hit_10d=56.1%, LIFT=0.98x → ACCUMULATE (marginal) ✅
      HH: hit_10d=41.2%, LIFT=0.97x → HOLD (conviction reducer only)
      LH: hit_10d=44.0%, LIFT=1.04x → HOLD (conviction reducer only)

    TECHO archetypes are too weak for hard TRIM. They modulate
    conviction in the SwingGate but don't override the decision.
    Exception: EXPLOSIÓN density TECHO → TRIM (rare, high conviction).

    Returns (quality_core_action, quality_swing_action, speculative_action).
    """
    if density_level == DENSITY_SILENCE:
        return ACTION_HOLD, ACTION_HOLD, ACTION_HOLD

    # ── PISO: validated for ACCUMULATE ──
    if archetype == ARCHETYPE_HL:
        return ACTION_ACCUMULATE, ACTION_HOLD, ACTION_HOLD

    if archetype == ARCHETYPE_LL:
        return ACTION_HOLD, ACTION_ACCUMULATE, ACTION_COVER

    # ── TECHO: conviction reducer, NOT hard TRIM ──
    # Exception: EXPLOSIÓN density = rare enough to be actionable
    if archetype == ARCHETYPE_HH:
        if density_level == DENSITY_EXPLOSION:
            return ACTION_HOLD, ACTION_TRIM, ACTION_HOLD
        return ACTION_HOLD, ACTION_HOLD, ACTION_HOLD  # SwingGate reads conviction

    if archetype == ARCHETYPE_LH:
        if density_level == DENSITY_EXPLOSION:
            return ACTION_HOLD, ACTION_HOLD, ACTION_SHORT
        return ACTION_HOLD, ACTION_HOLD, ACTION_HOLD  # SwingGate reads conviction

    return ACTION_HOLD, ACTION_HOLD, ACTION_HOLD


def _assess_trend_context(tide_slope: float, archetype: str) -> str:
    """Determine if signal is with or against the macro trend."""
    if archetype in (ARCHETYPE_HL, ARCHETYPE_LL):
        # Piso signals: WITH_TREND if tide is bullish
        if tide_slope > 0:
            return "WITH_TREND"
        return "AGAINST_TREND"
    if archetype in (ARCHETYPE_HH, ARCHETYPE_LH):
        # Techo signals: WITH_TREND if tide is bearish
        if tide_slope < 0:
            return "WITH_TREND"
        return "AGAINST_TREND"
    return "NEUTRAL"


def compute_turn_signal(
    prob_piso: float,
    prob_techo: float,
    kalman: KalmanSnapshot,
    tide_slope: float,
    density_history: list[float],
) -> TurnSignal:
    """Main entry point: compute full TurnSignal from model outputs.

    Args:
        prob_piso: P(near bottom) from Sentinel PISO model
        prob_techo: P(near top) from Sentinel TECHO model
        kalman: KalmanSnapshot with all 5 channel outputs
        tide_slope: from ChannelSnapshot (macro trend direction)
        density_history: max(prob_piso, prob_techo) for last 5 bars

    Returns:
        TurnSignal with archetype, density, actions, and conviction.
    """
    # Dominant probability
    dominant_prob = max(prob_piso, prob_techo)

    # Density assessment
    density_level, density_count, crescendo = assess_density(
        dominant_prob, density_history
    )

    # Archetype classification
    archetype = classify_archetype(
        prob_piso, prob_techo,
        kalman.kf_rsi_pred_val,
        tide_slope,
        crescendo,
    )

    # Force NONE if density is SILENCE
    if density_level == DENSITY_SILENCE:
        archetype = ARCHETYPE_NONE

    # Actions per department
    qc_action, qs_action, spec_action = _map_actions(archetype, density_level)

    # Conviction from density
    conviction = _map_conviction(density_level)

    # Trend context
    trend_context = _assess_trend_context(tide_slope, archetype)

    # Diagnosis string (Rule 17)
    diagnosis = (
        f"ARCH={archetype} P_PISO={prob_piso:.3f} P_TECHO={prob_techo:.3f} "
        f"DENSITY={density_level}({density_count}) "
        f"KF_RSI={kalman.kf_rsi_pred_val:.1f} TIDE={tide_slope:.6f} "
        f"CRESC={'Y' if crescendo else 'N'} TREND={trend_context}"
    )

    return TurnSignal(
        archetype=archetype,
        prob_piso=prob_piso,
        prob_techo=prob_techo,
        density_level=density_level,
        density_count=density_count,
        trend_context=trend_context,
        crescendo=crescendo,
        quality_core_action=qc_action,
        quality_swing_action=qs_action,
        speculative_action=spec_action,
        conviction=conviction,
        kf_rsi_pred=kalman.kf_rsi_pred_val,
        kf_price_vel=kalman.kf_price_filt_vel,
        diagnosis=diagnosis,
    )
