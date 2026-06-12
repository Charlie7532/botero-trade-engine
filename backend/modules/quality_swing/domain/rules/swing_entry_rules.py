"""
Swing Entry Rules — Pure Decision Logic
==========================================
Determines ACCUMULATE / TRIM / HOLD based on:
  - PRIMARY: P(bull|sigma_state) from empirical lookup table (when available)
  - CONFIRMATION: hookup + acceleration filters (forensic-validated)
  - LEGACY FALLBACK: regression channel σ thresholds + fear_level heuristics

These are pure functions. No I/O, no side effects. Testable without mocks.

Probability-based rules (v3):
  P(bull) ≥ 75% + confirmed → HIGH conviction ACCUMULATE
  P(bull) ≥ 75% unconfirmed → MODERATE conviction (reduced)
  P(bull) ≥ 65% + confirmed → MODERATE conviction ACCUMULATE
  P(bull) ≤ 25% → aggressive TRIM
  P(bull) ≤ 35% → moderate TRIM

Confirmation filters (from filter_impact_quantifier forensics):
  TIER 1: hookup (close > prev_close) → HR: +1.9pp, %AFTER: +3.6pp
  TIER 2: wave_accel > 0 AND current_accel > 0 → HR: +4.3pp (84.0%)

Legacy rules (v1, used when rc_prob is None):
  - RC × QUALITY_THESIS: WR=82.2%, Sharpe=1.326, PF=3.583
  - Slope Conjugation: winners enter with wave_slope NEGATIVE + tide_slope POSITIVE
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from backend.modules.quality_swing.domain.entities.swing_bias import TickerSentimentBias

if TYPE_CHECKING:
    from backend.modules.quality_swing.domain.rules.rc_state_probability import RCStateProbability


# ═══════════════════════════════════════════════════════════════
# THRESHOLDS (configurable from a single place)
# ═══════════════════════════════════════════════════════════════

ACCUMULATE_HIGH = 0.75    # P(bull) ≥ 75% → high conviction accumulate
ACCUMULATE_MOD = 0.65     # P(bull) ≥ 65% → moderate conviction accumulate
TRIM_HIGH = 0.25          # P(bull) ≤ 25% → aggressive trim
TRIM_MOD = 0.35           # P(bull) ≤ 35% → moderate trim


def is_accumulate_signal(
    sigma_pos: float,
    fear: TickerSentimentBias | None,
    below_vwap: bool,
    hookup: bool,
    vol_regime_label: str = "NORMAL",
    rc_prob: RCStateProbability | None = None,
    observer_recovery: float = 0.0,
) -> tuple[bool, float, str]:
    """Evaluate whether current conditions favor accumulation.

    Args:
        sigma_pos: Price position in σ units within regression channel.
        fear: TickerSentimentBias (or None if insufficient data).
        below_vwap: Is current price below 20-bar VWAP?
        hookup: Did today's close exceed yesterday's (reversal candle).
        vol_regime_label: Current volatility regime (NORMAL/ELEVATED/CRISIS).
        rc_prob: Empirical P(bull|state) from lookup table (when available).
        observer_recovery: Unified Observer recovery_score ∈ [-1, +1].
            From UnifiedKalmanObserver. Positive = system recovering.
            Replaces hookup + velocity + kf_consensus with ONE signal.

    Returns:
        (should_accumulate, conviction, reasoning)
        - conviction: 0.0-1.0 scaling factor for position sizing.
    """
    # ── Hard blocks (apply regardless of path) ──
    if vol_regime_label == "CRISIS":
        return False, 0.0, "VOL_CRISIS: No accumulation in crisis regime"

    # ════════════════════════════════════════════════════════════
    # PRIMARY PATH: Probability (TABLE) × Timing (OBSERVER)
    #
    # TABLE provides POSITION: P(bull|state) — where you are
    # OBSERVER provides VELOCITY: recovery_score — where you're going
    #
    # Composition:
    #   RECOVERING  (r > 0.3): conviction ×1.15 — piso confirmado
    #   CONFIRMED   (r > 0):   conviction ×1.0  — dirección positiva
    #   UNCONFIRMED (r ≤ 0):   conviction ×0.5  — aún cayendo
    #   DETERIORATING (r <-0.3): near-block      — cuchillo cayendo
    #
    # Evidence: 83K bars, 17 tickers, AUC=0.651
    #   RECOVERING: 69.3% AFTER (+12.5pp vs baseline)
    #   17/17 tickers improve, false alarms −29%
    # ════════════════════════════════════════════════════════════
    if rc_prob is not None:
        p = rc_prob.prob_bull

        # Observer timing assessment
        recovering = observer_recovery > 0.3
        confirmed = observer_recovery > 0
        deteriorating = observer_recovery < -0.3
        conf_tag = f"obs=[recovery={observer_recovery:+.3f}]"

        if p >= ACCUMULATE_HIGH:
            # High conviction: P ≥ 75%
            if confirmed:
                conviction = round(rc_prob.conviction, 2)
                if recovering:
                    # RECOVERING: piso confirmed, flow-weighted velocity positive
                    conviction = min(round(conviction * 1.15, 2), 1.0)
                if vol_regime_label == "ELEVATED":
                    conviction = round(conviction * 0.6, 2)
                return True, conviction, (
                    f"RC_PROB_HIGH: P(bull)={p:.1%} [{rc_prob.state_key}] "
                    f"N={rc_prob.n_samples} level={rc_prob.level} "
                    f"(P_HH={rc_prob.prob_hh:.1%} P_HL={rc_prob.prob_hl:.1%}) "
                    f"{conf_tag}"
                )
            else:
                # UNCONFIRMED: Observer says still falling
                mult = 0.3 if deteriorating else 0.5
                conviction = round(rc_prob.conviction * mult, 2)
                if vol_regime_label == "ELEVATED":
                    conviction = round(conviction * 0.5, 2)
                state_label = "DETERIORATING" if deteriorating else "UNCONFIRMED"
                return True, conviction, (
                    f"RC_PROB_HIGH_{state_label}: P(bull)={p:.1%} [{rc_prob.state_key}] "
                    f"N={rc_prob.n_samples} level={rc_prob.level} "
                    f"REDUCED ({state_label.lower()}) {conf_tag}"
                )

        if p >= ACCUMULATE_MOD:
            # Moderate conviction: 65% ≤ P < 75%
            if not confirmed:
                return False, 0.0, (
                    f"RC_PROB_MOD_UNCONF: P(bull)={p:.1%} [{rc_prob.state_key}] "
                    f"N={rc_prob.n_samples} — needs positive recovery {conf_tag}"
                )
            conviction = round(rc_prob.conviction * 0.6, 2)
            if recovering:
                conviction = min(round(conviction * 1.10, 2), 1.0)
            if vol_regime_label == "ELEVATED":
                conviction = round(conviction * 0.5, 2)
            return True, conviction, (
                f"RC_PROB_MOD: P(bull)={p:.1%} [{rc_prob.state_key}] "
                f"N={rc_prob.n_samples} level={rc_prob.level} {conf_tag}"
            )

        # Below accumulate threshold → no signal
        return False, 0.0, (
            f"RC_PROB_HOLD: P(bull)={p:.1%} < {ACCUMULATE_MOD:.0%} "
            f"[{rc_prob.state_key}] N={rc_prob.n_samples}"
        )

    # ════════════════════════════════════════════════════════════
    # LEGACY FALLBACK: Heuristic rules (v1)
    # Used when probability table is not available
    # ════════════════════════════════════════════════════════════
    if fear is None:
        return False, 0.0, "INSUFFICIENT_DATA: Need 200+ bars for fear_level"

    if fear.tide_slope < -0.03:
        return False, 0.0, (
            f"DEEP_BEAR: tide_slope={fear.tide_slope:.3f} < -0.03. "
            f"Structural collapse — Druckenmiller stays out"
        )

    # ── BULL regime (tide_slope > 0): statistical pullback ──
    if fear.tide_slope > 0.01:
        at_support = sigma_pos <= -1.5
        if at_support and below_vwap and hookup:
            depth_score = min(abs(sigma_pos) / 2.0, 1.0)
            fear_bonus = min(fear.fear_level / 5.0, 1.0) * 0.3
            conviction = round(min(depth_score * 0.5 + fear_bonus + 0.2, 1.0), 2)

            if fear.wave_flip and fear.wave_flip_direction == 1:
                conviction = min(conviction + 0.15, 1.0)

            if vol_regime_label == "ELEVATED":
                conviction *= 0.5

            return True, conviction, (
                f"LEGACY_BULL_DIP: σ={sigma_pos:.1f}, fear={fear.fear_label}, "
                f"tide={fear.tide_slope:.3f}, wave={fear.wave_slope:.3f}, "
                f"vwap={'below' if below_vwap else 'above'}"
            )

    # ── FLAT regime (|tide_slope| <= 0.01): extreme mean reversion ──
    elif abs(fear.tide_slope) <= 0.01:
        if sigma_pos <= -2.0 and hookup:
            conviction = 0.4
            if vol_regime_label == "ELEVATED":
                conviction *= 0.5
            return True, conviction, (
                f"LEGACY_FLAT_EXTREME: σ={sigma_pos:.1f}, mean reversion zone"
            )

    # ── SHALLOW BEAR (-0.03 < tide_slope < -0.01): cautious dip buy ──
    elif fear.tide_slope > -0.03:
        if sigma_pos <= -2.0 and fear.wave_slope > 0 and (below_vwap or hookup):
            conviction = round(min(abs(sigma_pos) / 3.0 + 0.3, 1.0), 2) * 0.7
            if vol_regime_label == "ELEVATED":
                conviction *= 0.5
            return True, conviction, (
                f"LEGACY_SHALLOW_BEAR_DIP: σ={sigma_pos:.1f}, wave turning positive, "
                f"tide={fear.tide_slope:.3f}"
            )

    return False, 0.0, f"NO_SIGNAL: σ={sigma_pos:.1f}, fear={fear.fear_label if fear else '?'}"


def is_trim_signal(
    sigma_pos: float,
    fear: TickerSentimentBias | None,
    rc_prob: RCStateProbability | None = None,
) -> tuple[bool, float, str]:
    """Evaluate whether current conditions favor trimming.

    Trimming ≠ selling. Trimming = reducing position size at statistical
    extremes to lock in gains and free capital for future accumulation.

    Args:
        sigma_pos: Price position in σ units within regression channel.
        fear: TickerSentimentBias (or None).
        rc_prob: Empirical P(bull|state) from lookup table (when available).

    Returns:
        (should_trim, trim_pct, reasoning)
        - trim_pct: 0.0-0.5 (max trim = 50% of swing allocation, never 100%)
    """
    # ════════════════════════════════════════════════════════════
    # PRIMARY PATH: Probability-based trim (v2)
    # ════════════════════════════════════════════════════════════
    if rc_prob is not None:
        p = rc_prob.prob_bull

        if p <= TRIM_HIGH:
            # Aggressive trim: P ≤ 25%
            trim_pct = round(min(0.5, (0.5 - p)), 2)
            return True, trim_pct, (
                f"RC_PROB_TRIM_HIGH: P(bull)={p:.1%} [{rc_prob.state_key}] "
                f"N={rc_prob.n_samples} level={rc_prob.level} "
                f"(P_LH={rc_prob.prob_lh:.1%} P_LL={rc_prob.prob_ll:.1%})"
            )

        if p <= TRIM_MOD:
            # Moderate trim: 25% < P ≤ 35%
            trim_pct = round(min(0.3, (0.5 - p) * 0.8), 2)
            return True, trim_pct, (
                f"RC_PROB_TRIM_MOD: P(bull)={p:.1%} [{rc_prob.state_key}] "
                f"N={rc_prob.n_samples} level={rc_prob.level}"
            )

        # P > 35% → no trim signal from probability model
        # Fall through — legacy rules may still catch extreme σ positions

    # ════════════════════════════════════════════════════════════
    # LEGACY FALLBACK: Heuristic trim rules (v1)
    # ════════════════════════════════════════════════════════════
    if fear is None:
        return False, 0.0, "INSUFFICIENT_DATA"

    # Extreme greed + overextended = trim
    if sigma_pos >= 2.0 and fear.fear_level == 0:
        trim_pct = 0.5  # Max trim at extreme greed
        return True, trim_pct, (
            f"LEGACY_EXTREME_GREED: σ={sigma_pos:.1f}, fear=GREED. "
            f"Druckenmiller: take chips off the table"
        )

    if sigma_pos >= 1.5 and fear.fear_level <= 1:
        trim_pct = 0.25
        return True, trim_pct, (
            f"LEGACY_OVEREXTENDED: σ={sigma_pos:.1f}, fear={fear.fear_label}. "
            f"Statistical resistance zone"
        )

    # Wave flip negative after extended run = early trim
    if (sigma_pos >= 1.0 and fear.wave_flip
            and fear.wave_flip_direction == -1 and fear.fear_level <= 1):
        trim_pct = 0.15
        return True, trim_pct, (
            f"LEGACY_WAVE_REVERSAL: σ={sigma_pos:.1f}, wave flipped negative. "
            f"Early trim before potential correction"
        )

    return False, 0.0, f"HOLD: σ={sigma_pos:.1f}, fear={fear.fear_label if fear else '?'}"
