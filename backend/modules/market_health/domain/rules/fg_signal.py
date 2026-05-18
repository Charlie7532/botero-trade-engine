"""
Fear & Greed Signal — Domain Rule

CNN Fear & Greed is a composite of 7 sub-indicators (momentum, breadth,
put/call, junk bond demand, VIX, safe haven demand, 52wk highs/lows).
5 of 7 overlap with our convergence dimensions — so F&G is NOT a
convergence dimension. It is an independent contrarian signal layer.

3 operational roles:
  1. Contrarian extremes: F&G < 20 = capitulation buy, > 80 = euphoria sell
  2. Direction + level: falling from 60→25 ≠ stable at 25
  3. Divergence vs internal convergence_score

Evidence Status: CANDIDATE — all FG-H01 through FG-H05 pending backtest.
"""
import numpy as np


# ── Regime thresholds (from engineer_features L1068-1079) ────
EXTREME_FEAR_THRESHOLD = 15    # CANDIDATE — need DSR validation
FEAR_THRESHOLD = 25            # CANDIDATE
GREED_THRESHOLD = 75           # CANDIDATE
EXTREME_GREED_THRESHOLD = 85   # CANDIDATE

# ── Velocity thresholds (z-scored ROC) ───────────────────────
VELOCITY_PANIC = -2.0          # CANDIDATE — fast drop = panic
VELOCITY_RECOVERY = 1.5       # CANDIDATE — fast rise = recovery


def classify_fg_regime(score: float) -> str:
    """Classify F&G score into 5 regimes."""
    if score < EXTREME_FEAR_THRESHOLD:
        return "EXTREME_FEAR"
    elif score < FEAR_THRESHOLD:
        return "FEAR"
    elif score > EXTREME_GREED_THRESHOLD:
        return "EXTREME_GREED"
    elif score > GREED_THRESHOLD:
        return "GREED"
    else:
        return "NEUTRAL"


def compute_fg_analytics(
    fg_history: list[float],
    lookback_zscore: int = 60,
    lookback_velocity: int = 5,
) -> dict:
    """Compute F&G analytics from historical scores.

    Args:
        fg_history: F&G close prices, most recent last. Min 20 values.
        lookback_zscore: Rolling window for z-score.
        lookback_velocity: Days for rate of change.

    Returns:
        Dict with fg_score, fg_regime, fg_zscore, fg_velocity,
        fg_direction, fg_action.
    """
    if not fg_history or len(fg_history) < 10:
        return {
            "fg_score": 50.0, "fg_regime": "NEUTRAL", "fg_zscore": 0.0,
            "fg_velocity": 0.0, "fg_direction": "STABLE", "fg_action": "NONE",
        }

    arr = np.array(fg_history, dtype=float)
    score = float(arr[-1])
    regime = classify_fg_regime(score)

    # Z-score (rolling 60d)
    window = min(lookback_zscore, len(arr))
    recent = arr[-window:]
    mean = np.mean(recent)
    std = np.std(recent)
    zscore = float((score - mean) / std) if std > 1e-9 else 0.0

    # Velocity (5d ROC, z-scored against its own 60d distribution)
    if len(arr) >= lookback_velocity + 1:
        roc = float(arr[-1] - arr[-1 - lookback_velocity])
        roc_history = np.diff(arr, n=lookback_velocity)
        if len(roc_history) >= 20:
            roc_mean = np.mean(roc_history[-60:])
            roc_std = np.std(roc_history[-60:])
            velocity = float((roc - roc_mean) / roc_std) if roc_std > 1e-9 else 0.0
        else:
            velocity = roc / 10.0  # rough normalization fallback
    else:
        velocity = 0.0

    # Direction
    if velocity < -1.0:
        direction = "FALLING"
    elif velocity > 1.0:
        direction = "RISING"
    else:
        direction = "STABLE"

    # Action (level + direction combined)
    action = _determine_action(score, direction)

    return {
        "fg_score": round(score, 1),
        "fg_regime": regime,
        "fg_zscore": round(zscore, 3),
        "fg_velocity": round(velocity, 3),
        "fg_direction": direction,
        "fg_action": action,
    }


def compute_fg_divergence(
    fg_regime: str,
    convergence_direction: str,
) -> tuple[bool, str]:
    """Detect divergence between F&G and internal convergence.

    Returns:
        (confirms_internal, divergence_type) tuple.
    """
    fg_bullish = fg_regime in ("GREED", "EXTREME_GREED")
    fg_bearish = fg_regime in ("FEAR", "EXTREME_FEAR")
    fg_neutral = fg_regime == "NEUTRAL"

    if convergence_direction == "RISK_ON":
        if fg_bearish:
            # Our data says healthy but market fears — contrarian buy
            return False, "CONTRARIAN_BUY"
        elif fg_bullish or fg_neutral:
            return True, "CONFIRMING"

    elif convergence_direction == "RISK_OFF":
        if fg_bullish:
            # Our data says unhealthy but market euphoric — contrarian sell
            return False, "CONTRARIAN_SELL"
        elif fg_bearish or fg_neutral:
            return True, "CONFIRMING"

    # NEUTRAL convergence
    if fg_bearish or fg_bullish:
        return False, "DIVERGING"

    return True, "NONE"


def _determine_action(score: float, direction: str) -> str:
    """Determine actionable F&G signal from level + direction."""
    # Extreme fear zone
    if score < EXTREME_FEAR_THRESHOLD:
        if direction == "RISING":
            return "CAPITULATION_BUY"   # Bounce confirmed
        else:
            return "NONE"               # Still falling — wait

    if score < FEAR_THRESHOLD:
        if direction != "FALLING":
            return "FEAR_BUY"           # Stabilizing in fear — accumulate
        else:
            return "NONE"               # Still deteriorating

    # Extreme greed zone
    if score > EXTREME_GREED_THRESHOLD:
        if direction == "FALLING":
            return "EUPHORIA_SELL"      # Distribution starting
        else:
            return "NONE"               # Still climbing — hold

    if score > GREED_THRESHOLD:
        if direction != "RISING":
            return "GREED_CAUTION"      # Stabilizing in greed — reduce
        else:
            return "NONE"               # Still climbing

    return "NONE"
