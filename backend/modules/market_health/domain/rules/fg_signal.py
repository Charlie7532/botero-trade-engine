"""Fear & Greed Signal — Domain Rule

CNN Fear & Greed is a composite of 7 sub-indicators (momentum, breadth,
put/call, junk bond demand, VIX, safe haven demand, 52wk highs/lows).
5 of 7 overlap with our convergence dimensions — so F&G is NOT a
convergence dimension. It is an independent contrarian signal layer.

F&G is a LAGGING indicator (corr +0.61 same-day, zero predictive power).
BUT extreme LEVELS identify exhausted markets — and exhausted markets bounce.
F&G measures sentiment exhaustion, not future direction.

Forensic Evidence (2021-2026, N=1237, Neon Vault):
  FG-H01: VALIDATED  — F&G<20 → Ret20d +3.56%, WR 75.5%, t=6.39
  FG-H02: REJECTED   — F&G>80 → Ret20d +0.32%, t=0.46 (not significant)
  FG-H03: CORRECTED  — FALLING at extreme fear has HIGHER WR (80.6%) than RISING
  FG-H05: CONFIRMED  — QQQ/SPY = 1.18x magnitude at extremes
  FG-H06: CANDIDATE  — F&G 0-10 → WR 90.5%, Ret20d +5.92% (N=21)
  FG-H07: VALIDATED  — Duration: first 3d in fear WR=80.8%, decays after d10
  FG-H08: CANDIDATE  — Greed + Correction = TRAP (WR 0%, N=6)
  FG-H11: VALIDATED  — Pullback + F&G<15 = Ret20d +4.39%, WR 75.5%, t=5.24
  FG-H12: VALIDATED  — Velocity crash (<-20pts/5d) → Ret20d +3.87%, t=4.64
  FG-H13: VALIDATED  — Signal STRENGTHENS over time (5d→60d all t>3.5)
  FG-H14: VALIDATED  — "Bearish" div (SPY↑ F&G↓) is BULLISH (WR 79%, t=6.21)
"""
import numpy as np


# ── Regime thresholds ────────────────────────────────────────
EXTREME_FEAR_THRESHOLD = 15    # FG-H01 VALIDATED
FEAR_THRESHOLD = 25            # FG-H01 VALIDATED
GREED_THRESHOLD = 75           # FG-H02 REJECTED as sell signal
EXTREME_GREED_THRESHOLD = 85   # FG-H02 REJECTED as sell signal

# ── Velocity thresholds (z-scored ROC) ───────────────────────
VELOCITY_PANIC = -2.0          # FG-H12: crash (<-20pts/5d) = buy signal
VELOCITY_RECOVERY = 1.5       # not significant per forensics

# ── Duration thresholds (FG-H07) ─────────────────────────────
DURATION_PEAK_WR_DAYS = 3      # WR 80.8% in first 3 days of extreme fear
DURATION_DECAY_DAYS = 10       # WR drops to 50% after day 10


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
    spy_dd_pct: float = 0.0,
) -> dict:
    """Compute F&G analytics from historical scores.

    Args:
        fg_history: F&G close prices, most recent last. Min 20 values.
        lookback_zscore: Rolling window for z-score.
        lookback_velocity: Days for rate of change.
        spy_dd_pct: SPY drawdown from 52-week high (e.g. -5.0 for -5%).
            Used for FG-H08: greed + correction = TRAP.

    Returns:
        Dict with fg_score, fg_regime, fg_zscore, fg_velocity,
        fg_direction, fg_action, fg_duration, fg_urgency.
    """
    if not fg_history or len(fg_history) < 10:
        return {
            "fg_score": 50.0, "fg_regime": "NEUTRAL", "fg_zscore": 0.0,
            "fg_velocity": 0.0, "fg_direction": "STABLE", "fg_action": "NONE",
            "fg_duration": 0, "fg_urgency": "NORMAL",
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
    roc_raw = 0.0
    if len(arr) >= lookback_velocity + 1:
        roc_raw = float(arr[-1] - arr[-1 - lookback_velocity])
        roc_history = np.diff(arr, n=lookback_velocity)
        if len(roc_history) >= 20:
            roc_mean = np.mean(roc_history[-60:])
            roc_std = np.std(roc_history[-60:])
            velocity = float((roc_raw - roc_mean) / roc_std) if roc_std > 1e-9 else 0.0
        else:
            velocity = roc_raw / 10.0  # rough normalization fallback
    else:
        velocity = 0.0

    # Direction
    if velocity < -1.0:
        direction = "FALLING"
    elif velocity > 1.0:
        direction = "RISING"
    else:
        direction = "STABLE"

    # ── FG-H07: Duration — consecutive days in current regime ──
    duration = _compute_duration(arr, score)

    # ── FG-H07: Urgency — decay after day 10 ──
    urgency = "NORMAL"
    if regime in ("EXTREME_FEAR", "FEAR"):
        if duration <= DURATION_PEAK_WR_DAYS:
            urgency = "HIGH"   # WR 80.8% — act NOW
        elif duration <= DURATION_DECAY_DAYS:
            urgency = "NORMAL"  # WR 75% — still good
        else:
            urgency = "DECAYING"  # WR drops to 50% — signal exhausted

    # Action (level + direction + context)
    action = _determine_action(score, direction, spy_dd_pct, duration)

    return {
        "fg_score": round(score, 1),
        "fg_regime": regime,
        "fg_zscore": round(zscore, 3),
        "fg_velocity": round(velocity, 3),
        "fg_direction": direction,
        "fg_action": action,
        "fg_duration": duration,
        "fg_urgency": urgency,
    }


def compute_fg_divergence(
    fg_regime: str,
    convergence_direction: str,
) -> tuple[bool, str]:
    """Detect divergence between F&G and internal convergence.

    FG-H14 forensic correction (2021-2026, N=81, t=6.21):
      "Bearish" divergence (internal RISK_ON but F&G bearish) is actually
      the STRONGEST bullish signal (WR 79%). When data says healthy but
      market is fearful = institutional accumulation with retail combustible.

      "Bullish" divergence (internal RISK_OFF but F&G greedy) = genuine
      contrarian sell signal. Market euphoric while fundamentals deteriorate.

    Returns:
        (confirms_internal, divergence_type) tuple.
    """
    fg_bullish = fg_regime in ("GREED", "EXTREME_GREED")
    fg_bearish = fg_regime in ("FEAR", "EXTREME_FEAR")
    fg_neutral = fg_regime == "NEUTRAL"

    if convergence_direction == "RISK_ON":
        if fg_bearish:
            # FG-H14 VALIDATED (t=6.21, WR 79%): Internal healthy + public
            # fearful = institutional accumulation. Retail panic creates
            # combustible for further upside. STRONGEST BUY signal.
            return False, "STEALTH_ACCUMULATION"
        elif fg_bullish or fg_neutral:
            return True, "CONFIRMING"

    elif convergence_direction == "RISK_OFF":
        if fg_bullish:
            # Internal unhealthy + public euphoric = distribution.
            # Smart money exiting while retail buys the top.
            return False, "DISTRIBUTION_WARNING"
        elif fg_bearish or fg_neutral:
            return True, "CONFIRMING"

    # NEUTRAL convergence
    if fg_bearish:
        # FG-H14: F&G fearish during neutral convergence → contrarian buy
        return False, "CONTRARIAN_BUY"
    if fg_bullish:
        return False, "DIVERGING"

    return True, "NONE"


def _compute_duration(arr: np.ndarray, score: float) -> int:
    """Count consecutive days in current extreme regime.

    FG-H07: Duration effect matters — WR peaks in first 3 days (80.8%)
    and decays to 50% after day 10 in extreme fear.
    """
    if score >= FEAR_THRESHOLD and score <= GREED_THRESHOLD:
        return 0  # not in any extreme

    is_fear = score < 20
    is_greed = score > 80

    if not is_fear and not is_greed:
        return 0

    # Count backwards from end
    count = 0
    for i in range(len(arr) - 1, -1, -1):
        if is_fear and arr[i] < 20:
            count += 1
        elif is_greed and arr[i] > 80:
            count += 1
        else:
            break
    return count


def _determine_action(
    score: float,
    direction: str,
    spy_dd_pct: float = 0.0,
    duration: int = 0,
) -> str:
    """Determine actionable F&G signal from level + direction + context.

    Forensic evidence (2021-2026, N=1237):

    FEAR ZONE:
      - EXTREME_FEAR (all directions): WR=76.9%, Mean=+4.31%, t=5.43
      - FALLING has HIGHEST WR (80.6%) — buy INTO panic
      - FG-H07: first 3 days → WR 80.8%, after day 10 → WR 50%
      - FG-H11: Pullback + F&G<15 → Ret20d +4.39%, WR 75.5%, t=5.24
      → CAPITULATION_BUY always (do NOT wait for RISING)

    GREED ZONE:
      - FG-H02 REJECTED (t=0.46): extreme greed ≠ sell
      - FG-H08: Greed + SPY correction (<-5%) = TRAP (WR 0%, N=6)
      → GREED_CAUTION only (sizing reduction)
      → GREED_TRAP if in drawdown (hard block)
    """
    # ── FEAR ZONE ──
    # VALIDATED (FG-H01, t=6.39): All extreme fear = capitulation buy
    # H03 forensic correction: FALLING = HIGHEST WR (80.6%)
    if score < EXTREME_FEAR_THRESHOLD:
        # FG-H07: Signal decays after day 10
        if duration > DURATION_DECAY_DAYS:
            return "FEAR_BUY"  # Downgrade from CAPITULATION to FEAR_BUY
        return "CAPITULATION_BUY"

    # VALIDATED: Fear zone accumulation (WR 69.9%, t=5.37)
    if score < FEAR_THRESHOLD:
        return "FEAR_BUY"

    # ── GREED ZONE ──
    # REJECTED (FG-H02, t=0.46): Extreme greed does NOT predict declines.
    # FG-H08 (CANDIDATE, N=6): Greed + correction = TRAP (WR 0%).
    if score > GREED_THRESHOLD:
        if spy_dd_pct < -5.0:
            # FG-H08: Greed during SPY correction → distribution trap
            return "GREED_TRAP"
        return "GREED_CAUTION"

    return "NONE"
