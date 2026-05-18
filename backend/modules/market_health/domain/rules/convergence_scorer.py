"""
Convergence Scorer — Domain Rule

Counts how many of the 6 orthogonal dimensions agree on direction.
F&G is NOT included in convergence (would double-count).

Evidence Status: CANDIDATE — convergence scoring needs DSR validation (MH-H05).
"""


def score_convergence(
    cascade_state: int,
    vol_regime_quality: str,
    flow_direction: str,
    credit_regime: str,
    rotation_phase: str,
    yield_curve_signal: str,
    macro_regime: str,
) -> tuple[int, str]:
    """Count converging dimensions and determine overall direction.

    Each dimension votes RISK_ON (+1), NEUTRAL (0), or RISK_OFF (-1).
    Direction is determined by net vote: >0 = RISK_ON, <0 = RISK_OFF.

    Returns:
        (convergence_score, convergence_direction) tuple.
        convergence_score: 0-6 (count of non-neutral votes that agree
                           with the majority direction).
        convergence_direction: RISK_ON / NEUTRAL / RISK_OFF.
    """
    votes = []

    # G1: Breadth
    if cascade_state == 0:       # HEALTH
        votes.append(1)
    elif cascade_state >= 2:     # CORRECTION or BEAR
        votes.append(-1)
    else:
        votes.append(0)

    # G2: Volatility
    vol_risk_off = {"ELEVATED", "CRISIS"}
    vol_risk_on = {"NORMAL", "COMPLACENT"}
    if vol_regime_quality in vol_risk_off:
        votes.append(-1)
    elif vol_regime_quality in vol_risk_on:
        votes.append(1)
    else:
        votes.append(0)

    # G3: Flow
    if flow_direction == "BULLISH":
        votes.append(1)
    elif flow_direction == "BEARISH":
        votes.append(-1)
    else:
        votes.append(0)

    # G4: Credit
    if credit_regime == "STRESS":
        votes.append(-1)
    elif credit_regime == "RISK_ON":
        votes.append(1)
    else:
        votes.append(0)

    # G5: Rotation (Pring cycle phase)
    # Early/Mid expansion = risk on. Late/contraction = risk off.
    expansion_phases = {"EXPANSION", "EARLY_EXPANSION", "MID_EXPANSION",
                        "RECOVERY", "PHASE_1", "PHASE_2", "PHASE_3"}
    contraction_phases = {"CONTRACTION", "LATE_EXPANSION", "RECESSION",
                          "PHASE_4", "PHASE_5", "PHASE_6"}
    if rotation_phase.upper() in expansion_phases:
        votes.append(1)
    elif rotation_phase.upper() in contraction_phases:
        votes.append(-1)
    else:
        votes.append(0)

    # G6: Macro (yield curve + FRED)
    macro_risk_off = yield_curve_signal in ("INVERTED",) or macro_regime == "CONTRACTION"
    macro_risk_on = yield_curve_signal == "NORMAL" and macro_regime in ("EXPANSION", "RECOVERY")
    if macro_risk_off:
        votes.append(-1)
    elif macro_risk_on:
        votes.append(1)
    else:
        votes.append(0)

    # Compute direction
    net = sum(votes)
    if net > 0:
        direction = "RISK_ON"
    elif net < 0:
        direction = "RISK_OFF"
    else:
        direction = "NEUTRAL"

    # Convergence = count of votes that agree with majority direction
    if direction == "RISK_ON":
        convergence = sum(1 for v in votes if v > 0)
    elif direction == "RISK_OFF":
        convergence = sum(1 for v in votes if v < 0)
    else:
        convergence = 0

    return convergence, direction
