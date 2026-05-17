"""
Swing Entry Rules — Pure Decision Logic
==========================================
Determines ACCUMULATE / TRIM / HOLD based on regression channel
statistics, fear level, and optional market context.

These are pure functions. No I/O, no side effects. Testable without mocks.

Rules based on empirically validated forensic findings:
  - RC × QUALITY_THESIS: WR=82.2%, Sharpe=1.326, PF=3.583
  - fear_level PANIC: P(↑)=47.6%, best forward return
  - Slope Conjugation: winners enter with wave_slope NEGATIVE + tide_slope POSITIVE
"""
from backend.modules.quality_swing.domain.entities.swing_bias import TickerSentimentBias


def is_accumulate_signal(
    sigma_pos: float,
    fear: TickerSentimentBias | None,
    below_vwap: bool,
    hookup: bool,
    vol_regime_label: str = "NORMAL",
) -> tuple[bool, float, str]:
    """Evaluate whether current conditions favor accumulation.

    Args:
        sigma_pos: Price position in σ units within regression channel.
        fear: TickerSentimentBias (or None if insufficient data).
        below_vwap: Is current price below 20-bar VWAP?
        hookup: Did today's close exceed yesterday's (reversal candle)?
        vol_regime_label: Current volatility regime (NORMAL/ELEVATED/CRISIS).

    Returns:
        (should_accumulate, conviction, reasoning)
        - conviction: 0.0-1.0 scaling factor for position sizing.
    """
    if fear is None:
        return False, 0.0, "INSUFFICIENT_DATA: Need 200+ bars for fear_level"

    # ── Hard blocks ──
    if vol_regime_label == "CRISIS":
        return False, 0.0, "VOL_CRISIS: No accumulation in crisis regime"

    if fear.tide_slope < -0.03:
        return False, 0.0, (
            f"DEEP_BEAR: tide_slope={fear.tide_slope:.3f} < -0.03. "
            f"Structural collapse — Druckenmiller stays out"
        )

    # ── BULL regime (tide_slope > 0): statistical pullback ──
    if fear.tide_slope > 0.01:
        at_support = sigma_pos <= -1.5
        # Forensic: winners enter with wave_slope NEGATIVE (slope conjugation)
        # The dip itself IS the signal — don't wait for the turn
        if at_support and below_vwap and hookup:
            # Conviction based on depth + fear level
            depth_score = min(abs(sigma_pos) / 2.0, 1.0)
            fear_bonus = min(fear.fear_level / 5.0, 1.0) * 0.3
            conviction = round(min(depth_score * 0.5 + fear_bonus + 0.2, 1.0), 2)

            # Wave flip positive = knife stopped falling = extra conviction
            if fear.wave_flip and fear.wave_flip_direction == 1:
                conviction = min(conviction + 0.15, 1.0)

            # ELEVATED regime reduces sizing
            if vol_regime_label == "ELEVATED":
                conviction *= 0.5

            return True, conviction, (
                f"BULL_DIP: σ={sigma_pos:.1f}, fear={fear.fear_label}, "
                f"tide={fear.tide_slope:.3f}, wave={fear.wave_slope:.3f}, "
                f"vwap={'below' if below_vwap else 'above'}"
            )

    # ── FLAT regime (|tide_slope| <= 0.01): extreme mean reversion ──
    elif abs(fear.tide_slope) <= 0.01:
        # Forensic: FLAT regime WR=91.7% (THESIS). Mean reversion is strong.
        if sigma_pos <= -2.0 and hookup:
            conviction = 0.4
            if vol_regime_label == "ELEVATED":
                conviction *= 0.5
            return True, conviction, (
                f"FLAT_EXTREME: σ={sigma_pos:.1f}, mean reversion zone"
            )

    # ── SHALLOW BEAR (-0.03 < tide_slope < -0.01): cautious dip buy ──
    elif fear.tide_slope > -0.03:
        # Forensic: shallow bear winners had σ < -2.0 AND wave turning positive
        if sigma_pos <= -2.0 and fear.wave_slope > 0 and (below_vwap or hookup):
            conviction = round(min(abs(sigma_pos) / 3.0 + 0.3, 1.0), 2) * 0.7
            if vol_regime_label == "ELEVATED":
                conviction *= 0.5
            return True, conviction, (
                f"SHALLOW_BEAR_DIP: σ={sigma_pos:.1f}, wave turning positive, "
                f"tide={fear.tide_slope:.3f}"
            )

    return False, 0.0, f"NO_SIGNAL: σ={sigma_pos:.1f}, fear={fear.fear_label if fear else '?'}"


def is_trim_signal(
    sigma_pos: float,
    fear: TickerSentimentBias | None,
) -> tuple[bool, float, str]:
    """Evaluate whether current conditions favor trimming.

    Trimming ≠ selling. Trimming = reducing position size at statistical
    extremes to lock in gains and free capital for future accumulation.

    Args:
        sigma_pos: Price position in σ units within regression channel.
        fear: TickerSentimentBias (or None).

    Returns:
        (should_trim, trim_pct, reasoning)
        - trim_pct: 0.0-0.5 (max trim = 50% of swing allocation, never 100%)
    """
    if fear is None:
        return False, 0.0, "INSUFFICIENT_DATA"

    # Extreme greed + overextended = trim
    if sigma_pos >= 2.0 and fear.fear_level == 0:
        trim_pct = 0.5  # Max trim at extreme greed
        return True, trim_pct, (
            f"EXTREME_GREED: σ={sigma_pos:.1f}, fear=GREED. "
            f"Druckenmiller: take chips off the table"
        )

    if sigma_pos >= 1.5 and fear.fear_level <= 1:
        trim_pct = 0.25
        return True, trim_pct, (
            f"OVEREXTENDED: σ={sigma_pos:.1f}, fear={fear.fear_label}. "
            f"Statistical resistance zone"
        )

    # Wave flip negative after extended run = early trim
    if (sigma_pos >= 1.0 and fear.wave_flip
            and fear.wave_flip_direction == -1 and fear.fear_level <= 1):
        trim_pct = 0.15
        return True, trim_pct, (
            f"WAVE_REVERSAL: σ={sigma_pos:.1f}, wave flipped negative. "
            f"Early trim before potential correction"
        )

    return False, 0.0, f"HOLD: σ={sigma_pos:.1f}, fear={fear.fear_label if fear else '?'}"
