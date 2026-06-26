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

Confirmation filters (from deep_mining_audit forensics):
  TIER 1: hookup (close > prev_close) → HR: +1.9pp, %AFTER: +3.6pp
  TIER 2: vel_sigma_c > 0 AND vel_svw > 0 → spread: 21pp (replaces accel 5pp)

Legacy rules (v1, used when rc_prob is None):
  - RC × QUALITY_THESIS: WR=82.2%, Sharpe=1.326, PF=3.583
  - Slope Conjugation: winners enter with wave_slope NEGATIVE + tide_slope POSITIVE
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from backend.modules.quality_swing.domain.entities.swing_bias import TickerSentimentBias

if TYPE_CHECKING:
    from backend.modules.quality_swing.domain.rules.rc_state_probability import (
        DualProbability,
    )
    from backend.modules.quality_swing.domain.rules.rc_unified_lookup import UnifiedProbability
    from backend.modules.quality_swing.domain.rules.rc_combined_lookup import CombinedSignal
    from backend.modules.quality_swing.domain.rules.slope_transition_detector import SlopeTransition


def is_accumulate_signal(
    sigma_pos: float,
    fear: TickerSentimentBias | None,
    below_vwap: bool,
    hookup: bool,
    vol_regime_label: str = "NORMAL",
    observer_recovery: float = 0.0,
    unified_prob: UnifiedProbability | None = None,
    vel_sigma_c: float = 0.0,
    vel_svw: float = 0.0,
    transition: SlopeTransition | None = None,
    dual_prob: DualProbability | None = None,
    combined_signal: CombinedSignal | None = None,
) -> tuple[bool, float, str]:
    """Evaluate whether current conditions favor accumulation.

    Decision cascade (highest priority first):
      1. COMBINED: T×C×σVw committee signal (538 tickers, 628K bars)
      2. DUAL: Asymmetric P(piso) from sign families (AUC=0.8672)
      3. UNIFIED: Slope×sigma×stereotype interactions
      4. LEGACY: Heuristic σ + fear rules

    Args:
        sigma_pos: Price position in σ units within regression channel.
        fear: TickerSentimentBias (or None if insufficient data).
        below_vwap: True if price < VWAP (institutional discount).
        hookup: True if close > prev_close (momentum confirmation).
        vol_regime_label: Volatility regime from Vol Intelligence.
        observer_recovery: Unified Observer recovery_score ∈ [-1, +1].
        unified_prob: Interconected slope×sigma×stereotype probabilities.
        vel_sigma_c: Velocity of σ_Current (from Observer Kalman).
        vel_svw: Velocity of σV_Wave (from Observer Kalman).
        combined_signal: Pre-computed committee signal from T×C×σVw table.

    Returns:
        (should_accumulate, conviction, reasoning)
        - conviction: 0.0-1.0 scaling factor for position sizing.
    """
    # ── Hard blocks (apply regardless of path) ──
    if vol_regime_label == "CRISIS":
        return False, 0.0, "VOL_CRISIS: No accumulation in crisis regime"

    # ════════════════════════════════════════════════════════════
    # COMBINED TABLE PATH (v2): Committee-approved T×C×σVw signal
    #
    # 180 pre-computed states with 8 signals. This is the PRIMARY
    # accumulation path when available. Falls through to legacy
    # paths when combined_signal is None.
    #
    # Source: rc_combined_derived.json (538 tickers, 628K bars)
    # Approved by: Dalio, Druckenmiller, PTJ/Eifert, Weinstein/Pring
    # ════════════════════════════════════════════════════════════
    if combined_signal is not None and combined_signal.is_accumulate:
        sig = combined_signal
        # Use confidence_factor (empirical edge × stability × repetition penalty)
        # rather than conviction_factor (statistical z-score only).
        # Note: In FLOOR state runs of length ≥5, 52% of bottoms occur in the FINAL
        # 20% of the run and 76% in the final 40%. Buying day 1 of a FLOOR entry is
        # statistically premature — the confidence_factor encodes this via w_stability.
        base_conviction = sig.confidence_factor

        # Observer timing modulation
        recovering = observer_recovery > 0.3
        confirmed = observer_recovery > 0
        deteriorating = observer_recovery < -0.3

        # T9 structural filter: block premature bounces
        if transition and transition.cascade_type == "REBOTE_PREMATURO":
            return False, 0.0, (
                f"COMBINED_{sig.signal}_BLOCKED: [{sig.state_key}] "
                f"P_bull={sig.p_bull:.1f}% but T9=REBOTE_PREMATURO "
                f"— wait for Current to confirm"
            )

        # Signal-specific conviction scaling
        if sig.signal == "ACCUMULATE":
            # Extreme capitulation — go for the jugular (Druckenmiller)
            conviction = min(base_conviction * 1.3, 1.0)
            if recovering:
                conviction = min(conviction * 1.15, 1.0)
            elif deteriorating:
                # Still falling but capitulation so extreme it's worth partial entry
                conviction = round(conviction * 0.5, 2)
            elif not confirmed:
                conviction = round(conviction * 0.6, 2)
        else:  # BUY_DIP
            conviction = min(base_conviction * 1.0, 0.8)
            if not confirmed:
                # BUY_DIP requires at least neutral recovery
                return False, 0.0, (
                    f"COMBINED_BUY_DIP_UNCONF: [{sig.state_key}] "
                    f"P_bull={sig.p_bull:.1f}% asym={sig.asymmetry_pp:+.1f}pp "
                    f"but obs={observer_recovery:+.3f} not confirmed"
                )
            if recovering:
                conviction = min(conviction * 1.10, 0.9)

        # T9 boost for healthy pullbacks
        if transition and transition.cascade_type in ("PULLBACK_SANO", "RALLY_VALIDADO"):
            conviction = min(conviction * 1.2, 1.0)

        # Vol regime damping
        if vol_regime_label == "ELEVATED":
            conviction = round(conviction * 0.5, 2)

        # Predictive edge bonus
        pred_tag = ""
        if sig.predictive_edge == "LEADING_BOTTOM":
            conviction = min(conviction * 1.1, 1.0)
            pred_tag = " [LEADING_BOTTOM]"

        conviction = round(conviction, 2)
        return True, conviction, (
            f"COMBINED_{sig.signal}: [{sig.state_key}] "
            f"P_bull={sig.p_bull:.1f}% odds={sig.odds:.1f}:1 "
            f"bot25={sig.bottom_25_pct:.1f}% asym={sig.asymmetry_pp:+.1f}pp "
            f"lift_band={sig.lift_vs_band:.2f} N={sig.n_samples:,} "
            f"zone={sig.zone} regime={sig.regime} "
            f"conv={sig.conviction}/{sig.conviction_score} "
            f"sig_conf={sig.signal_confidence} "
            f"obs={observer_recovery:+.3f}{pred_tag}"
        )

    # ================================================================
    # DUAL PATH: Asymmetric P(piso) tables (sign families)
    #
    # Evidence (Fase 0 walk-forward):
    #   Pisos AUC: 0.8672 (sigma_Vc primary), L1 coverage: 98.6%
    #   Highest P(piso): 42.5% (ALL_NEG sigma_Vc=<< vel+ vol_high)
    # ================================================================
    if dual_prob is not None and dual_prob.prob_piso > 0.0:
        pp = dual_prob.prob_piso

        # Observer timing assessment
        recovering = observer_recovery > 0.3
        confirmed = observer_recovery > 0
        deteriorating = observer_recovery < -0.3

        # T9 structural filter
        if transition and transition.cascade_type == "REBOTE_PREMATURO":
            return False, 0.0, (
                f"DUAL_PISO_BLOCKED: P(piso)={pp:.1%} "
                f"but T9=REBOTE_PREMATURO -- wait for Current to confirm"
            )

        # High conviction piso zone (>= 2.5x base rate of 6.9%)
        if pp >= 0.15:
            conviction = min(pp * 1.5, 1.0)

            # Magnitude modulates sizing
            if dual_prob.expected_magnitude >= 0.075:
                conviction = min(conviction * 1.2, 1.0)

            # Observer modulates timing
            if recovering:
                conviction = min(conviction * 1.15, 1.0)
            elif deteriorating:
                conviction = round(conviction * 0.4, 2)
            elif not confirmed:
                conviction = round(conviction * 0.6, 2)

            # T9 PULLBACK_SANO boosts
            if transition and transition.cascade_type in ("PULLBACK_SANO", "RALLY_VALIDADO"):
                conviction = min(conviction * 1.2, 1.0)

            if vol_regime_label == "ELEVATED":
                conviction = round(conviction * 0.5, 2)

            return True, round(conviction, 2), (
                f"DUAL_PISO: P(piso)={pp:.1%} "
                f"[{dual_prob.state_key_piso}] "
                f"mag={dual_prob.expected_magnitude:.1%} "
                f"fam={dual_prob.family} "
                f"N={dual_prob.n_piso} level={dual_prob.level_piso} "
                f"obs=[recovery={observer_recovery:+.3f}]"
            )

        elif pp >= 0.10:  # ~1.5x base rate -- moderate signal
            if confirmed:
                conviction = round(pp * 1.0, 2)
                if vol_regime_label in ("ELEVATED", "CRISIS"):
                    conviction = round(conviction * 0.4, 2)
                return True, conviction, (
                    f"DUAL_PISO_MOD: P(piso)={pp:.1%} "
                    f"[{dual_prob.state_key_piso}] "
                    f"fam={dual_prob.family} "
                    f"obs=[recovery={observer_recovery:+.3f}]"
                )

    # ════════════════════════════════════════════════════════════
    # SECONDARY PATH: Unified Tree (Slopes × Stereotypes)
    # Fires when combined/dual didn't trigger, but the
    # interconected slope+sigma state has high P(HL) at a bottom
    # or the acceleration signals imminent wave flip.
    # ════════════════════════════════════════════════════════════
    if unified_prob is not None:
        p_hl = unified_prob.prob_hl
        p_bull_unified = unified_prob.prob_bull
        slope = unified_prob.slope_state

        # Observer timing
        recovering = observer_recovery > 0.3
        confirmed = observer_recovery > 0
        conf_tag = f"obs=[recovery={observer_recovery:+.3f}]"

        # T7: sigma velocities (21pp spread) replace accels (5pp spread)
        wave_flip_imminent = vel_sigma_c > 0 and slope.wave_sign < 0

        # Combined P_bull as co-gate (replaces old rc_prob.prob_bull)
        combined_p_bull = (combined_signal.p_bull / 100.0) if combined_signal else 0.5

        # Case 1: Combined near neutral but unified says P(HL) > 50%
        #   + wave deceleration → imminent flip → accumulate
        if (combined_p_bull >= 0.40
                and p_hl >= 0.50
                and unified_prob.n_samples >= 20
                and wave_flip_imminent
                and confirmed):
            conviction = round(min(p_hl * 0.7, 0.8), 2)
            if vol_regime_label == "ELEVATED":
                conviction = round(conviction * 0.5, 2)
            trans_tag = ""
            if transition and transition.cascade_type == "REBOTE_PREMATURO":
                return False, 0.0, (
                    f"UNIFIED_FLIP_BLOCKED: P(HL)={p_hl:.1%} but T9=REBOTE_PREMATURO "
                    f"(W flipped but C={slope.current_level} still negative) "
                    f"— wait for Current to confirm"
                )
            if transition and transition.cascade_type in ("PULLBACK_SANO", "RALLY_VALIDADO"):
                conviction = min(round(conviction * 1.3, 2), 1.0)
                trans_tag = f" T9={transition.cascade_type}"
            return True, conviction, (
                f"UNIFIED_FLIP_ACCUM: P(HL)={p_hl:.1%} [{unified_prob.lookup_key}] "
                f"vel_σc={vel_sigma_c:+.4f} (flip imminent) "
                f"stereo={unified_prob.dominant_stereotype} "
                f"{conf_tag}{trans_tag}"
            )

        # Case 2: Unified tree says strong P(bull) > 70%
        if (p_bull_unified >= 0.70
                and unified_prob.is_high_conviction
                and confirmed):
            conviction = round(unified_prob.conviction * 0.6, 2)
            if recovering:
                conviction = min(round(conviction * 1.15, 2), 1.0)
            if vol_regime_label == "ELEVATED":
                conviction = round(conviction * 0.5, 2)
            return True, conviction, (
                f"UNIFIED_STEREO_ACCUM: P(bull)={p_bull_unified:.1%} "
                f"[{unified_prob.lookup_key}] "
                f"HH={unified_prob.prob_hh:.1%} HL={unified_prob.prob_hl:.1%} "
                f"N={unified_prob.n_samples} slope={slope.tripleta} "
                f"{conf_tag}"
            )

        # Below unified threshold → no signal from any probability model
        return False, 0.0, (
            f"PROB_HOLD: UNIFIED P(bull)={p_bull_unified:.1%} "
            f"stereo={unified_prob.dominant_stereotype} "
            f"slope={slope.tripleta}"
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
    observer_recovery: float = 0.0,
    unified_prob: UnifiedProbability | None = None,
    vel_sigma_c: float = 0.0,
    vel_svw: float = 0.0,
    transition: SlopeTransition | None = None,
    dual_prob: DualProbability | None = None,
    combined_signal: CombinedSignal | None = None,
) -> tuple[bool, float, str]:
    """Evaluate whether current conditions favor trimming.

    Trimming ≠ selling. Trimming = reducing position size at statistical
    extremes to lock in gains and free capital for future accumulation.

    Decision cascade (highest priority first):
      1. COMBINED: T×C×σVw committee signal (TAKE_PROFIT / REDUCE)
      2. DUAL: Asymmetric P(techo)
      3. UNIFIED: Slope×stereotype structural ceiling
      4. LEGACY: Heuristic σ + fear rules

    Args:
        sigma_pos: Price position in σ units within regression channel.
        fear: TickerSentimentBias (or None).
        observer_recovery: Unified Observer recovery_score ∈ [-1, +1].
        unified_prob: Interconected slope×sigma×stereotype probabilities.
        vel_sigma_c: Velocity of σ_Current (from Observer Kalman).
        vel_svw: Velocity of σV_Wave (from Observer Kalman).
        combined_signal: Pre-computed committee signal from T×C×σVw table.

    Returns:
        (should_trim, trim_pct, reasoning)
        - trim_pct: 0.0-0.5 (max trim = 50% of swing allocation, never 100%)
    """
    # ════════════════════════════════════════════════════════════
    # COMBINED TABLE PATH (v2): Committee-approved T×C×σVw trim
    #
    # TAKE_PROFIT: Blow-off top imminent (top_25 > 15%)
    # REDUCE: Preventive distribution (all Ceiling states)
    # ════════════════════════════════════════════════════════════
    if combined_signal is not None and combined_signal.is_trim:
        sig = combined_signal
        deteriorating = observer_recovery < -0.3
        confirmed_down = observer_recovery < 0

        if sig.signal == "TAKE_PROFIT":
            # Aggressive profit-taking — blow-off top risk (PTJ)
            trim_pct = round(min(0.5, sig.conviction_factor * 0.6), 2)
            if deteriorating:
                trim_pct = min(round(trim_pct * 1.3, 2), 0.5)
            if transition and transition.cascade_type == "CORRECCION_REAL":
                trim_pct = min(round(trim_pct * 1.4, 2), 0.5)

            pred_tag = ""
            if sig.predictive_edge == "LEADING_TOP":
                trim_pct = min(round(trim_pct * 1.2, 2), 0.5)
                pred_tag = " [LEADING_TOP]"

            return True, trim_pct, (
                f"COMBINED_TAKE_PROFIT: [{sig.state_key}] "
                f"P_bull={sig.p_bull:.1f}% top25={sig.top_25_pct:.1f}% "
                f"asym={sig.asymmetry_pp:+.1f}pp "
                f"zone={sig.zone} regime={sig.regime} "
                f"N={sig.n_samples:,} obs={observer_recovery:+.3f}{pred_tag}"
            )

        else:  # REDUCE
            # Preventive distribution — Ceiling zone structural risk
            trim_pct = round(min(0.3, sig.conviction_factor * 0.35), 2)
            if deteriorating:
                trim_pct = min(round(trim_pct * 1.2, 2), 0.4)
            if not confirmed_down:
                # REDUCE without observer confirmation → small trim only
                trim_pct = min(trim_pct, 0.15)

            return True, trim_pct, (
                f"COMBINED_REDUCE: [{sig.state_key}] "
                f"P_bull={sig.p_bull:.1f}% top25={sig.top_25_pct:.1f}% "
                f"asym={sig.asymmetry_pp:+.1f}pp "
                f"zone={sig.zone} regime={sig.regime} "
                f"N={sig.n_samples:,} obs={observer_recovery:+.3f}"
            )
    # ================================================================
    # DUAL PATH: Asymmetric P(techo) trim
    # When dual_prob.prob_techo exceeds threshold, trigger trim.
    # Techo AUC is lower (0.6480) so thresholds calibrated higher.
    # ================================================================
    if dual_prob is not None and dual_prob.techo_dominant:
        pt = dual_prob.prob_techo
        deteriorating = observer_recovery < -0.3
        confirmed_down = observer_recovery < 0

        # Observer must confirm downward momentum (backtest: HR=38.7% without)
        if not confirmed_down:
            pass  # Fall through to legacy trim path
        else:
            trim_pct = round(min(0.5, pt * 1.2), 2)
            if deteriorating:
                trim_pct = min(round(trim_pct * 1.3, 2), 0.5)
            if transition and transition.cascade_type == "CORRECCION_REAL":
                trim_pct = min(round(trim_pct * 1.4, 2), 0.5)
            return True, trim_pct, (
                f"DUAL_TECHO: P(techo)={pt:.1%} "
                f"[{dual_prob.state_key_techo}] "
                f"fam={dual_prob.family} "
                f"N={dual_prob.n_techo} level={dual_prob.level_techo} "
                f"obs=[recovery={observer_recovery:+.3f}]"
            )

    # ════════════════════════════════════════════════════════════
    # SECONDARY PATH: Unified Tree → Structural TRIM
    # Fires when combined/dual didn't trigger, but unified detects
    # structural ceiling from slope×stereotype interactions.
    # ════════════════════════════════════════════════════════════
    if unified_prob is not None:
        p_lh = unified_prob.prob_lh
        p_bull_unified = unified_prob.prob_bull
        slope = unified_prob.slope_state
        deteriorating = observer_recovery < -0.3

        # T7: velocity negative + wave still positive → ceiling forming
        ceiling_forming = vel_sigma_c < 0 and slope.wave_sign > 0

        # Case 1: Unified says P(LH) > 50% + ceiling forming + deteriorating
        if (p_lh >= 0.50
                and unified_prob.n_samples >= 20
                and ceiling_forming
                and deteriorating):
            trim_pct = round(min(0.4, p_lh * 0.5), 2)
            trans_tag = ""
            if transition and transition.cascade_type == "CORRECCION_REAL":
                trim_pct = min(round(trim_pct * 1.5, 2), 0.5)
                trans_tag = f" T9=CORRECCION_REAL(boost)"
            return True, trim_pct, (
                f"UNIFIED_CEILING_TRIM: P(LH)={p_lh:.1%} [{unified_prob.lookup_key}] "
                f"vel_σc={vel_sigma_c:+.4f} (ceiling) "
                f"obs_recovery={observer_recovery:+.3f} (deteriorating) "
                f"slope={slope.tripleta}{trans_tag}"
            )

        # Case 1b: T9 EARLY_WARNING — W flipped down, C still positive
        if (transition and transition.cascade_type == "EARLY_WARNING"
                and p_bull_unified < 0.55
                and vel_sigma_c < 0):
            trim_pct = 0.15
            return True, trim_pct, (
                f"T9_EARLY_WARNING_TRIM: W flipped bearish but C+ "
                f"P(bull)={p_bull_unified:.1%} vel_σc={vel_sigma_c:+.4f} "
                f"slope={slope.tripleta} — anticipatory trim"
            )

        # Case 2: Unified says P(bull) < 30%
        if (p_bull_unified <= 0.30
                and unified_prob.is_high_conviction):
            trim_pct = round(min(0.4, (0.5 - p_bull_unified)), 2)
            return True, trim_pct, (
                f"UNIFIED_STEREO_TRIM: P(bull)={p_bull_unified:.1%} "
                f"[{unified_prob.lookup_key}] "
                f"LH={p_lh:.1%} LL={unified_prob.prob_ll:.1%} "
                f"N={unified_prob.n_samples} slope={slope.tripleta}"
            )

        # Case 3: Observer deteriorating + both models pessimistic
        combined_p_bull = (combined_signal.p_bull / 100.0) if combined_signal else 0.5
        if (deteriorating
                and combined_p_bull < 0.50
                and p_bull_unified < 0.45):
            trim_pct = round(min(0.25, abs(observer_recovery) * 0.3), 2)
            return True, trim_pct, (
                f"UNIFIED_OBS_TRIM: obs={observer_recovery:+.3f} (deteriorating) "
                f"combined_P_bull={combined_p_bull:.1%} "
                f"unified_P(bull)={p_bull_unified:.1%} "
                f"slope={slope.tripleta}"
            )

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
