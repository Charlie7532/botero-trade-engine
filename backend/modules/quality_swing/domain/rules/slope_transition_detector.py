"""
Slope Transition Detector — Pure Domain Rule (T9)
====================================================
Detects slope state CHANGES between consecutive bars to identify
cascade patterns (Canary/Confirmador model).

Evidence (5,831 transitions, 91K bars, 17 tickers):
  W- → W+ with C+ = PULLBACK_SANO (65-71% HL)
  W- → W+ with C- = REBOTE_PREMATURO (wait for C confirm)
  W+ → W- with C+ = EARLY_WARNING (canary alerts, current ok)
  W+ → W- with C- = CORRECCION_REAL (63-72% LL)
  Sequences of 2-3 steps → 96% HL/LH

Clean Architecture: Pure domain rule. No IO, no side effects.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SlopeTransition:
    """Detected slope state change between consecutive bars.

    Consumed by swing_entry_rules for ACCUMULATE/TRIM modulation.
    """
    # Wave channel flipped sign?
    wave_flipped: bool = False
    wave_flip_direction: int = 0     # +1=bullish flip (W- → W+), -1=bearish flip (W+ → W-)

    # Current channel confirmed the wave's direction?
    current_confirmed: bool = False

    # Cascade classification
    cascade_type: str = "NONE"
    # PULLBACK_SANO: W flipped up, C still positive → shallow dip (65-71% HL)
    # RALLY_VALIDADO: W flipped up AND C flipped up → confirmed recovery
    # EARLY_WARNING: W flipped down, C still positive → canary alerts
    # CORRECCION_REAL: W flipped down AND C negative → real correction (63-72% LL)
    # REBOTE_PREMATURO: W flipped up but C still negative → premature bounce
    # DETERIORO_ACELERADO: W already negative AND C flipped negative → acceleration

    prev_tripleta: str = ""
    curr_tripleta: str = ""

    # Magnitude of change (number of levels changed in Wave)
    wave_magnitude: int = 0          # e.g., W- → W+++ = 4 levels


def _sign_from_state(state: str) -> int:
    """Extract sign from a slope state like 'W+++' or 'C--'."""
    if "+" in state:
        return 1
    elif "-" in state:
        return -1
    return 0


def _level_from_state(state: str) -> int:
    """Convert slope state to numeric level: --- = -3, ++ = 2, etc."""
    prefix = state[0]  # T, C, or W
    rest = state[1:]
    if rest.startswith("+"):
        return len(rest)  # + = 1, ++ = 2, +++ = 3
    elif rest.startswith("-"):
        return -len(rest)  # - = -1, -- = -2, --- = -3
    return 0


def detect_transition(
    prev_tripleta: str,
    curr_tripleta: str,
) -> SlopeTransition:
    """Detect slope state transitions between two consecutive bars.

    Args:
        prev_tripleta: Previous bar's slope tripleta (e.g., "T+/C-/W---")
        curr_tripleta: Current bar's slope tripleta (e.g., "T+/C-/W++")

    Returns:
        SlopeTransition with cascade classification.
    """
    result = SlopeTransition(
        prev_tripleta=prev_tripleta,
        curr_tripleta=curr_tripleta,
    )

    if not prev_tripleta or not curr_tripleta:
        return result

    # Parse tripletas
    try:
        prev_parts = prev_tripleta.split("/")
        curr_parts = curr_tripleta.split("/")
        if len(prev_parts) != 3 or len(curr_parts) != 3:
            return result

        prev_t, prev_c, prev_w = prev_parts
        curr_t, curr_c, curr_w = curr_parts
    except (ValueError, IndexError):
        return result

    # Wave flip detection
    prev_w_sign = _sign_from_state(prev_w)
    curr_w_sign = _sign_from_state(curr_w)

    if prev_w_sign != curr_w_sign and prev_w_sign != 0 and curr_w_sign != 0:
        result.wave_flipped = True
        result.wave_flip_direction = curr_w_sign  # +1 = bullish flip, -1 = bearish

    # Wave magnitude (how many levels changed)
    prev_w_level = _level_from_state(prev_w)
    curr_w_level = _level_from_state(curr_w)
    result.wave_magnitude = abs(curr_w_level - prev_w_level)

    # Current sign for cascade classification
    curr_c_sign = _sign_from_state(curr_c)
    prev_c_sign = _sign_from_state(prev_c)

    current_flipped = (prev_c_sign != curr_c_sign and prev_c_sign != 0 and curr_c_sign != 0)
    result.current_confirmed = current_flipped and (curr_c_sign == result.wave_flip_direction)

    # ── Cascade classification ──
    if result.wave_flipped:
        if result.wave_flip_direction == 1:
            # Wave flipped BULLISH (W- → W+)
            if curr_c_sign > 0:
                if current_flipped:
                    # C also flipped positive → RALLY VALIDADO
                    result.cascade_type = "RALLY_VALIDADO"
                else:
                    # C was already positive → PULLBACK SANO
                    result.cascade_type = "PULLBACK_SANO"
            else:
                # C still negative → premature bounce
                result.cascade_type = "REBOTE_PREMATURO"
        else:
            # Wave flipped BEARISH (W+ → W-)
            if curr_c_sign < 0:
                if current_flipped:
                    # C also flipped negative → CORRECCION REAL
                    result.cascade_type = "CORRECCION_REAL"
                else:
                    # C was already negative → deterioro acelerado
                    result.cascade_type = "DETERIORO_ACELERADO"
            else:
                # C still positive → early warning only
                result.cascade_type = "EARLY_WARNING"
    else:
        # No wave flip — check if Current flipped independently
        if current_flipped:
            if curr_c_sign < 0:
                # Current just went negative without Wave flipping → confirmador late warning
                result.cascade_type = "CONFIRMADOR_LATE_WARNING"
            elif curr_c_sign > 0:
                # Current recovered → confirmador validates
                result.cascade_type = "CONFIRMADOR_RECOVERY"

    return result
