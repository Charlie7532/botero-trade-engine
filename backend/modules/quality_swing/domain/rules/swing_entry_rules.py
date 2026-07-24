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
    from backend.modules.quality_swing.domain.rules.rc_combined_lookup import CombinedSignal
    from backend.modules.quality_swing.domain.rules.rc_wave_lookup import WaveSignal
    from backend.modules.quality_swing.domain.rules.slope_transition_detector import SlopeTransition


def is_accumulate_signal(
    sigma_pos: float,
    fear: TickerSentimentBias | None,
    below_vwap: bool,
    hookup: bool,
    vol_regime_label: str = "NORMAL",
    observer_recovery: float = 0.0,
    vel_sigma_c: float = 0.0,
    vel_svw: float = 0.0,
    transition: SlopeTransition | None = None,
    dual_prob: DualProbability | None = None,
    combined_signal: CombinedSignal | None = None,
    wave_signal: WaveSignal | None = None,
) -> tuple[bool, float, str]:
    """Evaluate whether current conditions favor accumulation.

    Decision cascade (committee-approved, 4 paths):
      1. COMBINED + WAVE: T×C×σVw macro context + W×σVc×σc×vel micro timing
         - Combined ACCUM + Wave BOTTOM → HIGH conviction (confluence)
         - Combined ACCUM + Wave NO_EDGE → REDUCED conviction (×0.5) [QS-1]
         - Combined ACCUM + Wave TOP → BLOCK (conflict) [Issue 5]
      2. WAVE STANDALONE: micro dip buying when Combined is passive
         - Combined P_bull < 40% → BLOCK (Weinstein Stage 4 veto) [ROT-1]
         - LATE_CYCLE_WARNING → conviction ×0.3 [ROT-2]
         - wave_flip_imminent → +15% bonus [QS-2]
      3. DUAL vol_surge: bonus to existing conviction (+10-15%) [QS-5]
         Never primary, never blocks.
      4. LEGACY: heuristic σ + fear rules (unchanged)

    Args:
        sigma_pos: Price position in σ units within regression channel.
        fear: TickerSentimentBias (or None if insufficient data).
        below_vwap: True if price < VWAP (institutional discount).
        hookup: True if close > prev_close (momentum confirmation).
        vol_regime_label: Volatility regime from Vol Intelligence.
        observer_recovery: Unified Observer recovery_score ∈ [-1, +1].
        vel_sigma_c: Velocity of σ_Current (from Observer Kalman).
        vel_svw: Velocity of σV_Wave (from Observer Kalman).
        combined_signal: Pre-computed committee signal from T×C×σVw table.
        wave_signal: Pre-computed Wave signal from W×σVc×σc×vel table.

    Returns:
        (should_accumulate, conviction, reasoning)
        - conviction: 0.0-1.0 scaling factor for position sizing.
    """
    # ── Hard blocks (apply regardless of path) ──
    if vol_regime_label == "CRISIS":
        return False, 0.0, "VOL_CRISIS: No accumulation in crisis regime"

    # ════════════════════════════════════════════════════════════
    # PATH 1: COMBINED + WAVE (macro context + micro timing)
    #
    # Combined provides the macro direction (180 states, 628K bars).
    # Wave modulates timing based on pivot proximity (443 states).
    #
    # QS-1: "The value of Wave is in SUPPRESSING false positives
    #        of Combined when micro doesn't confirm."
    # ════════════════════════════════════════════════════════════
    if combined_signal is not None and combined_signal.is_accumulate:
        sig = combined_signal
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

        # ── Wave modulation (QS-1 + Issue 5) ──
        wave_tag = ""
        if wave_signal is not None:
            if wave_signal.is_top_signal:
                # Issue 5: CONFLICT — macro ACCUM + micro TOP → BLOCK
                return False, 0.0, (
                    f"COMBINED_WAVE_CONFLICT: [{sig.state_key}] {sig.signal} "
                    f"P_bull={sig.p_bull:.1f}% but Wave [{wave_signal.state_key}] "
                    f"says {wave_signal.signal} (lift_top={wave_signal.lift_best_top:.2f}×)"
                )
            elif wave_signal.is_bottom_signal:
                # Confluence: macro + micro align → BOOST
                base_conviction *= 1.15
                wave_tag = (
                    f" [WAVE_CONFIRMS: {wave_signal.signal} "
                    f"lift={wave_signal.lift_best_bottom:.2f}× "
                    f"clean={wave_signal.bot_pct_clean:.0f}%]"
                )
            else:
                # QS-1: Wave NO_EDGE — macro wants to buy, micro doesn't confirm
                # This is THE key value of Wave: filtering premature entries
                base_conviction *= 0.5
                wave_tag = " [WAVE_NO_EDGE: timing premature]"

        # Signal-specific conviction scaling
        if sig.signal == "ACCUMULATE":
            conviction = min(base_conviction * 1.3, 1.0)
            if recovering:
                conviction = min(conviction * 1.15, 1.0)
            elif deteriorating:
                conviction = round(conviction * 0.5, 2)
            elif not confirmed:
                conviction = round(conviction * 0.6, 2)
        else:  # BUY_DIP
            conviction = min(base_conviction * 1.0, 0.8)
            if not confirmed:
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

        # ── QS-5: Dual as BONUS (never primary, never blocks) ──
        dual_tag = ""
        if dual_prob is not None and dual_prob.prob_piso > 0.10:
            conviction = min(conviction * 1.10, 1.0)
            if dual_prob.expected_magnitude >= 0.075:
                conviction = min(conviction * 1.05, 1.0)
            dual_tag = f" [DUAL_BONUS: P_piso={dual_prob.prob_piso:.1%}]"

        # ── Extreme velocity modifier (P10/P90 tails) ──
        vel_ext_tag = ""
        if wave_signal is not None and wave_signal.extreme_vel_tag:
            conviction = min(conviction * wave_signal.extreme_vel_modifier, 1.0)
            vel_ext_tag = f" [{wave_signal.extreme_vel_tag}]"

        conviction = round(conviction, 2)
        return True, conviction, (
            f"COMBINED_{sig.signal}: [{sig.state_key}] "
            f"P_bull={sig.p_bull:.1f}% odds={sig.odds:.1f}:1 "
            f"bot25={sig.bottom_25_pct:.1f}% asym={sig.asymmetry_pp:+.1f}pp "
            f"lift_band={sig.lift_vs_band:.2f} N={sig.n_samples:,} "
            f"zone={sig.zone} regime={sig.regime} "
            f"conv={sig.conviction}/{sig.conviction_score} "
            f"sig_conf={sig.signal_confidence} "
            f"obs={observer_recovery:+.3f}{pred_tag}{wave_tag}{dual_tag}{vel_ext_tag}"
        )

    # ════════════════════════════════════════════════════════════
    # PATH 2: WAVE STANDALONE (micro timing without macro ACCUM)
    #
    # Wave APPROACHING_BOTTOM can detect dips in uptrends that
    # Combined NEVER sees (P_bull 50-83% range).
    #
    # ROT-1: "Wave standalone in Stage 4 = value trap"
    #   → Combined P_bull < 40% → BLOCK
    # ROT-2: LATE_CYCLE_WARNING → conviction ×0.3
    # QS-2: wave_flip_imminent preserved as inflection bonus
    # QS-3: conviction 0.3-0.5 scaled by cell metrics
    # ════════════════════════════════════════════════════════════
    if wave_signal is not None and wave_signal.is_bottom_signal:
        # ROT-1: Weinstein Stage 4 Veto
        combined_p = (combined_signal.p_bull / 100.0) if combined_signal else 0.5
        if combined_p < 0.40:
            return False, 0.0, (
                f"WAVE_TRAP: [{wave_signal.state_key}] {wave_signal.signal} "
                f"lift={wave_signal.lift_best_bottom:.2f}× "
                f"but Combined P_bull={combined_p:.1%} < 40% "
                f"— micro bottom in macro downtrend (Weinstein veto)"
            )

        # Observer confirmation required
        confirmed = observer_recovery > 0
        recovering = observer_recovery > 0.3
        if not confirmed:
            return False, 0.0, (
                f"WAVE_STANDALONE_UNCONF: [{wave_signal.state_key}] "
                f"{wave_signal.signal} but obs={observer_recovery:+.3f} not confirmed"
            )

        # Cell-level conviction (replaces fixed 0.3-0.5 cap — QS-3/Issue 2)
        conviction = wave_signal.bottom_conviction  # 0.2-0.6 range

        # ROT-2: LATE_CYCLE_WARNING reduces conviction dramatically
        rot_tag = ""
        if combined_signal and combined_signal.rotation_flag == "LATE_CYCLE_WARNING":
            conviction *= 0.3
            rot_tag = " [LATE_CYCLE_WARNING: cycle turning]"

        # QS-2: wave_flip_imminent — σc rising within falling wave = inflection
        flip_tag = ""
        wave_flip_imminent = vel_sigma_c > 0 and wave_signal.momentum_state == "FALLING"
        if wave_flip_imminent:
            conviction = min(conviction * 1.15, 0.6)
            flip_tag = " [WAVE_FLIP_IMMINENT]"

        if recovering:
            conviction = min(conviction * 1.15, 0.6)

        # T9 boost for pullback sano
        trans_tag = ""
        if transition and transition.cascade_type in ("PULLBACK_SANO", "RALLY_VALIDADO"):
            conviction = min(conviction * 1.2, 0.7)
            trans_tag = f" T9={transition.cascade_type}"
        elif transition and transition.cascade_type == "REBOTE_PREMATURO":
            return False, 0.0, (
                f"WAVE_STANDALONE_BLOCKED: [{wave_signal.state_key}] "
                f"{wave_signal.signal} but T9=REBOTE_PREMATURO"
            )

        if vol_regime_label == "ELEVATED":
            conviction = round(conviction * 0.5, 2)

        # QS-5: Dual bonus
        dual_tag = ""
        if dual_prob is not None and dual_prob.prob_piso > 0.10:
            conviction = min(conviction * 1.10, 0.7)
            dual_tag = f" [DUAL_BONUS: P_piso={dual_prob.prob_piso:.1%}]"

        # Extreme velocity modifier (P10/P90 tails)
        vel_ext_tag = ""
        if wave_signal.extreme_vel_tag:
            conviction = min(conviction * wave_signal.extreme_vel_modifier, 0.7)
            vel_ext_tag = f" [{wave_signal.extreme_vel_tag}]"

        conviction = round(conviction, 2)
        return True, conviction, (
            f"WAVE_STANDALONE_{wave_signal.signal}: [{wave_signal.state_key}] "
            f"lift_bot={wave_signal.lift_best_bottom:.2f}× "
            f"clean={wave_signal.bot_pct_clean:.0f}% "
            f"P_bull_wave={wave_signal.p_bull:.1f}% "
            f"P_bull_combined={combined_p:.1%} "
            f"micro={wave_signal.microstructure_type} "
            f"obs={observer_recovery:+.3f}"
            f"{flip_tag}{rot_tag}{trans_tag}{dual_tag}{vel_ext_tag}"
        )

    # ════════════════════════════════════════════════════════════
    # LEGACY FALLBACK: Heuristic rules (v1)
    # Used when neither Combined nor Wave produce a signal.
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
    vel_sigma_c: float = 0.0,
    vel_svw: float = 0.0,
    transition: SlopeTransition | None = None,
    dual_prob: DualProbability | None = None,
    combined_signal: CombinedSignal | None = None,
    wave_signal: WaveSignal | None = None,
) -> tuple[bool, float, str]:
    """Evaluate whether current conditions favor trimming.

    Trimming ≠ selling. Trimming = reducing position size at statistical
    extremes to lock in gains and free capital for future accumulation.

    Decision cascade (committee-approved):
      1. COMBINED + WAVE: T×C×σVw trim signal + W micro modulation
         - Combined TRIM + Wave TOP → HARD TRIM (boost ×1.3) [Issue 3]
         - Combined TRIM + Wave NO_EDGE → MODERATE TRIM (×0.7) [Issue 3]
         - Combined TRIM + Wave BOTTOM → DELAY TRIM (×0.5) [Issue 3]
      2. DUAL: Asymmetric P(techo)
      3. LEGACY: Heuristic σ + fear rules

    Args:
        sigma_pos: Price position in σ units within regression channel.
        fear: TickerSentimentBias (or None).
        observer_recovery: Unified Observer recovery_score ∈ [-1, +1].
        vel_sigma_c: Velocity of σ_Current (from Observer Kalman).
        vel_svw: Velocity of σV_Wave (from Observer Kalman).
        combined_signal: Pre-computed committee signal from T×C×σVw table.
        wave_signal: Pre-computed Wave signal from W×σVc×σc×vel table.

    Returns:
        (should_trim, trim_pct, reasoning)
        - trim_pct: 0.0-0.5 (max trim = 50% of swing allocation, never 100%)
    """
    # ════════════════════════════════════════════════════════════
    # PATH 1: COMBINED + WAVE TRIM
    #
    # TAKE_PROFIT: Blow-off top imminent (top_25 > 15%)
    # REDUCE: Preventive distribution (all Ceiling states)
    # Wave modulates trim conviction symmetrically to ACCUM [Issue 3]
    # ════════════════════════════════════════════════════════════
    if combined_signal is not None and combined_signal.is_trim:
        sig = combined_signal
        deteriorating = observer_recovery < -0.3
        confirmed_down = observer_recovery < 0

        if sig.signal == "TAKE_PROFIT":
            trim_pct = round(min(0.5, sig.confidence_factor * 0.6), 2)
            if deteriorating:
                trim_pct = min(round(trim_pct * 1.3, 2), 0.5)
            if transition and transition.cascade_type == "CORRECCION_REAL":
                trim_pct = min(round(trim_pct * 1.4, 2), 0.5)

            pred_tag = ""
            if sig.predictive_edge == "LEADING_TOP":
                trim_pct = min(round(trim_pct * 1.2, 2), 0.5)
                pred_tag = " [LEADING_TOP]"

            # ── Issue 3: Wave modulates trim symmetrically ──
            wave_tag = ""
            if wave_signal is not None:
                if wave_signal.is_top_signal:
                    # Wave confirms top → HARD TRIM
                    trim_pct = min(round(trim_pct * 1.3, 2), 0.5)
                    wave_tag = (
                        f" [WAVE_CONFIRMS_TOP: {wave_signal.signal} "
                        f"lift_top={wave_signal.lift_best_top:.2f}×]"
                    )
                elif wave_signal.is_bottom_signal:
                    # CONFLICT: macro TRIM + micro BOTTOM → delay trim
                    trim_pct = round(trim_pct * 0.5, 2)
                    wave_tag = (
                        f" [WAVE_BOTTOM: delaying trim, "
                        f"lift_bot={wave_signal.lift_best_bottom:.2f}×]"
                    )
                else:  # NO_EDGE
                    trim_pct = round(trim_pct * 0.7, 2)
                    wave_tag = " [WAVE_NO_EDGE: moderate trim]"

            return True, trim_pct, (
                f"COMBINED_TAKE_PROFIT: [{sig.state_key}] "
                f"P_bull={sig.p_bull:.1f}% top25={sig.top_25_pct:.1f}% "
                f"asym={sig.asymmetry_pp:+.1f}pp "
                f"zone={sig.zone} regime={sig.regime} "
                f"N={sig.n_samples:,} obs={observer_recovery:+.3f}"
                f"{pred_tag}{wave_tag}"
            )

        else:  # REDUCE
            trim_pct = round(min(0.3, sig.confidence_factor * 0.35), 2)
            if deteriorating:
                trim_pct = min(round(trim_pct * 1.2, 2), 0.4)
            if not confirmed_down:
                trim_pct = min(trim_pct, 0.15)

            # ── Issue 3: Wave modulates REDUCE symmetrically ──
            wave_tag = ""
            if wave_signal is not None:
                if wave_signal.is_top_signal:
                    trim_pct = min(round(trim_pct * 1.2, 2), 0.4)
                    wave_tag = f" [WAVE_CONFIRMS_TOP: {wave_signal.signal}]"
                elif wave_signal.is_bottom_signal:
                    trim_pct = round(trim_pct * 0.5, 2)
                    wave_tag = f" [WAVE_BOTTOM: reducing trim urgency]"

            return True, trim_pct, (
                f"COMBINED_REDUCE: [{sig.state_key}] "
                f"P_bull={sig.p_bull:.1f}% top25={sig.top_25_pct:.1f}% "
                f"asym={sig.asymmetry_pp:+.1f}pp "
                f"zone={sig.zone} regime={sig.regime} "
                f"N={sig.n_samples:,} obs={observer_recovery:+.3f}"
                f"{wave_tag}"
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
