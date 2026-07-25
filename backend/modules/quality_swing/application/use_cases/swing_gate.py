"""
Swing Gate — Druckenmiller's Tactical Timing Orchestrator
============================================================
Evaluates whether NOW is the right moment to accumulate or trim
a position that Quality Core already approved as a tollkeeper.

This gate does NOT decide WHAT to buy — that's Core's job.
This gate decides WHEN to add or reduce.

Dependencies via Ports (Clean Architecture):
  - SwingDataPort: OHLCV data + vol regime label
  - PassportStorePort (optional): reads Signal Reliability Passports
    to scale conviction by empirical per-fear-level WR and reliability_score.

Production tools consumed:
  - RegressionChannelIntelligence: σ position, fear_level, zone, conviction,
    trim detection, slope_conjugation, vol UP/DOWN ratio — replaces manual
    computation of all these individually.

Domain rules consumed (pure functions, no mocks needed for testing):
  - swing_entry_rules.is_accumulate_signal, is_trim_signal
"""
import logging
from datetime import date, timedelta
from typing import Optional

from backend.modules.quality_swing.domain.dtos.swing_decision import SwingDecision
from backend.modules.quality_swing.domain.ports.swing_data_port import SwingDataPort
from backend.modules.quality_swing.domain.rules.swing_entry_rules import (
    is_accumulate_signal,
    is_trim_signal,
)
from backend.modules.shared.domain.entities.turn_signal import (
    TurnSignal, ACTION_ACCUMULATE, ACTION_TRIM, ACTION_HOLD,
    DENSITY_EXPLOSION, DENSITY_PRESSURIZE,
)

logger = logging.getLogger(__name__)


class SwingGate:
    """Orchestrates swing timing evaluation for a single ticker.

    Constructor injection: receives data port (required) and passport store
    (optional). When passport store is provided, conviction is scaled by
    empirical reliability from the Signal Reliability Passport.
    """

    _rc_intel = None  # RegressionChannelIntelligence (lazy init)

    def __init__(
        self,
        data_port: SwingDataPort,
        passport_store=None,  # PassportStorePort | None
    ):
        self._port = data_port
        self._passports = passport_store  # Optional — degrades gracefully

    def evaluate(
        self,
        ticker: str,
        reference_date: Optional[date] = None,
    ) -> SwingDecision:
        """Evaluate swing timing for a Quality-approved ticker.

        Args:
            ticker: Symbol to evaluate (must be in Quality Core universe).
            reference_date: Optional date override (for backtesting).

        Returns:
            SwingDecision with action=ACCUMULATE|TRIM|HOLD.
            When passport_store is available, conviction is empirically scaled.
        """
        decision = SwingDecision(ticker=ticker)

        # ── Load OHLCV data ──
        start = (reference_date or date.today()) - timedelta(days=450)
        ohlc = self._port.load_ohlc(ticker, "1d", start=start)
        if ohlc is None or len(ohlc) < 250:
            decision.reasoning = "INSUFFICIENT_DATA: Need 245+ bars"
            return decision

        idx = len(ohlc) - 1

        # ── Compute ChannelSnapshot ONCE — single source of truth ──
        from backend.modules.shared.domain.rules.compute_channel import compute_channel_snapshot
        close = ohlc["close"].values.astype(float)
        high = ohlc["high"].values.astype(float)
        low = ohlc["low"].values.astype(float)
        volume = ohlc["volume"].values.astype(float)
        channel = compute_channel_snapshot(close, high, low, volume, idx)

        if channel is None:
            decision.reasoning = "CHANNEL_FAILED: Cannot compute channel snapshot"
            return decision

        # ── RC Intelligence — interprets pre-computed snapshot ──
        rc_result = self._get_rc_analysis(ohlc, channel)
        if rc_result is None:
            decision.reasoning = "RC_INTEL_FAILED: Cannot interpret channel"
            return decision

        decision.sigma_position = rc_result.sigma_position
        decision.fear_level = rc_result.fear_level
        decision.fear_label = rc_result.fear_label
        decision.tide_slope = rc_result.tide_slope
        decision.wave_slope = rc_result.wave_slope

        below_vwap = rc_result.below_vwap

        # ── Slope State: classify_slopes() replaces Unified Tree ──
        # (Committee QS-4: Unified Tree eliminated — 82% of nodes had N<50)
        from backend.modules.quality_swing.domain.rules.rc_slope_classifier import (
            classify_slopes,
        )
        _slope_state = classify_slopes(
            channel.tide_slope, channel.current_slope, channel.wave_slope
        )

        # Load Observer recovery_score and velocities from Vault
        _observer_recovery = self._load_observer_recovery(ticker)
        _vel_sigma_c, _vel_svw = self._load_observer_velocities(ticker)

        # ── Dual Probability: Asymmetric P(piso) / P(techo) ──
        _dual_prob = None
        try:
            from backend.modules.quality_swing.domain.rules.rc_state_probability import (
                lookup_dual_probability,
            )
            # vol_surge: now computed in ChannelSnapshot
            _vol_surge = channel.vol_surge

            # w_duration: compute live from Vault previous + current wave level
            _w_duration = 1
            try:
                curr_slope = _slope_state  # Already computed above
                prev_snap = self._port.load_latest_snapshot(ticker)
                if prev_snap is not None:
                    prev_slope = classify_slopes(
                        prev_snap.tide_slope, prev_snap.current_slope, prev_snap.wave_slope
                    )
                    if prev_slope.wave_level == curr_slope.wave_level:
                        _w_duration = max(prev_snap.w_duration or 1, 1) + 1
            except Exception:
                pass  # Fallback to w_duration=1 if Vault unavailable

            # Velocities: use Observer values when available,
            # fall back to simple diff from channel
            _vel_svw_ema = _vel_svw  # From Observer Kalman (already loaded)
            _vel_sc_diff = _vel_sigma_c  # From Observer Kalman

            # If Observer not available, compute simple diff
            if _vel_svw_ema == 0.0 and idx >= 1:
                prev_ch = compute_channel_snapshot(close, high, low, volume, idx - 1)
                if prev_ch:
                    _vel_svw_ema = channel.vwap_sigma_wave - prev_ch.vwap_sigma_wave
                    _vel_sc_diff = channel.sigma_current - prev_ch.sigma_current

            _dual_prob = lookup_dual_probability(
                tide_slope=channel.tide_slope,
                current_slope=channel.current_slope,
                wave_slope=channel.wave_slope,
                vwap_sigma_current=channel.vwap_sigma_current,
                sigma_current=channel.sigma_current,
                vel_sigma_vw_ema=_vel_svw_ema,
                vel_sigma_c_diff=_vel_sc_diff,
                vol_surge=_vol_surge,
                w_duration=_w_duration,
                sigma_wave=channel.sigma_wave,
            )
            if _dual_prob:
                decision.alerts.append(
                    f"DUAL[{_dual_prob.family}]: "
                    f"P(piso)={_dual_prob.prob_piso:.1%} "
                    f"P(techo)={_dual_prob.prob_techo:.1%} "
                    f"mag={_dual_prob.expected_magnitude:.1%} "
                    f"piso_key={_dual_prob.state_key_piso}({_dual_prob.level_piso}) "
                    f"techo_key={_dual_prob.state_key_techo}({_dual_prob.level_techo}) "
                    f"N_p={_dual_prob.n_piso} N_t={_dual_prob.n_techo}"
                )
        except Exception as e:
            logger.warning(f"SwingGate {ticker}: Dual probability lookup failed: {e}")

        # ── T9: Slope Transition Detector (Canary/Confirmador) ──
        # (QS-4: decoupled from Unified — uses _slope_state directly)
        _transition = None
        if idx >= 2:
            try:
                from backend.modules.quality_swing.domain.rules.slope_transition_detector import detect_transition
                # Get previous bar's slopes from OHLCV data
                prev_channel = compute_channel_snapshot(close, high, low, volume, idx - 1)
                if prev_channel:
                    prev_slopes = classify_slopes(
                        prev_channel.tide_slope, prev_channel.current_slope, prev_channel.wave_slope
                    )
                    _transition = detect_transition(
                        prev_tripleta=prev_slopes.tripleta,
                        curr_tripleta=_slope_state.tripleta,
                    )
                    if _transition.cascade_type != "NONE":
                        decision.alerts.append(
                            f"T9[{_transition.cascade_type}]: "
                            f"{_transition.prev_tripleta} → {_transition.curr_tripleta} "
                            f"wave_flip={'↑' if _transition.wave_flip_direction == 1 else '↓' if _transition.wave_flip_direction == -1 else '='}"
                        )
            except Exception as e:
                logger.debug(f"SwingGate {ticker}: Transition detection failed: {e}")

        hookup = ohlc["close"].iloc[idx] > ohlc["close"].iloc[idx - 1] if idx > 0 else False

        # ── Tide T×C×σVw Signal (committee-approved, 180 states) ──
        _tide = None
        try:
            from backend.modules.quality_swing.domain.rules.rc_tide_lookup import (
                lookup_tide_signal,
            )
            _tide = lookup_tide_signal(
                tide_level=_slope_state.tide_level,
                current_level=_slope_state.current_level,
                vwap_sigma_wave=channel.vwap_sigma_wave,
            )
            if _tide:
                decision.alerts.append(
                    f"TIDE[{_tide.state_key}]: "
                    f"signal={_tide.signal} "
                    f"P_bull={_tide.p_bull:.1f}% "
                    f"zone={_tide.zone} regime={_tide.regime} "
                    f"conv={_tide.conviction}/{_tide.conviction_score} "
                    f"asym={_tide.asymmetry_pp:+.1f}pp "
                    f"N={_tide.n_samples:,}"
                )
        except Exception as e:
            logger.warning(f"SwingGate {ticker}: Tide signal lookup failed: {e}")

        # ── Wave W×σVc×σc×vel Signal (micro timing, 443 L1 states) ──
        # Wave = microscopio del canal: timing de pivots + reversal quality
        _wave = None
        try:
            from backend.modules.quality_swing.domain.rules.rc_wave_lookup import (
                lookup_wave_signal,
            )
            _wave = lookup_wave_signal(
                wave_slope=channel.wave_slope,
                vwap_sigma_current=channel.vwap_sigma_current,
                sigma_current=channel.sigma_current,
                vel_svw=_vel_svw,
            )
            if _wave:
                decision.wave_action_code = _wave.action_code
                decision.alerts.append(
                    f"WAVE[{_wave.state_key}]: "
                    f"action={_wave.action_code} "
                    f"P_bot={_wave.p_any_bottom:.1f}% "
                    f"lift_bot={_wave.lift_best_bottom:.2f}× "
                    f"clean={_wave.bot_pct_clean:.0f}% "
                    f"micro={_wave.microstructure_type} "
                    f"N={_wave.n_samples}"
                )

        # ── Real Point-in-Time EV Signal (Dual Confluence: P(bull) x EV) ──
        _real_ev = None
        try:
            from backend.modules.quality_swing.domain.rules.rc_tide_ev_lookup import lookup_real_ev
            _real_ev = lookup_real_ev(
                tide_slope=_slope_state.tide_level,
                current_slope=_slope_state.current_level,
                vwap_sigma_wave=channel.vwap_sigma_wave,
                level="zz50",
            )
            if _real_ev:
                decision.alerts.append(
                    f"REAL_EV[{_real_ev.state_key}]({_real_ev.fallback_level}): "
                    f"P_bull={_real_ev.p_bull:.1f}% "
                    f"EV={_real_ev.ev:+.4f} "
                    f"Sharpe={_real_ev.sharpe:.3f} "
                    f"R:R={_real_ev.rr_asymmetry:.2f} "
                    f"fatigue={_real_ev.fatigue_type} "
                    f"unobserved={_real_ev.is_unobserved_state}"
                )
        except Exception as e:
            logger.warning(f"SwingGate {ticker}: Real EV lookup failed: {e}")

        # ── Real Point-in-Time Wave EV Signal (Micro Wave Expectancy) ──
        _real_wave_ev = None
        try:
            from backend.modules.quality_swing.domain.rules.rc_wave_ev_lookup import lookup_real_wave_ev
            _real_wave_ev = lookup_real_wave_ev(
                wave_slope=channel.wave_slope,
                vwap_sigma_current=channel.vwap_sigma_current,
                sigma_current=channel.sigma_current,
                vel_svw=_vel_svw,
                level="zz50",
            )
            if _real_wave_ev:
                decision.alerts.append(
                    f"WAVE_EV[{_real_wave_ev.state_key}]: "
                    f"action={_real_wave_ev.action_code} "
                    f"EV={_real_wave_ev.ev:+.4f} "
                    f"Sharpe={_real_wave_ev.sharpe:.3f} "
                    f"fatigue={_real_wave_ev.fatigue_type}"
                )
        except Exception as e:
            logger.warning(f"SwingGate {ticker}: Real Wave EV lookup failed: {e}")


        # ── Load vol regime (Stateful-First: StateSnapshot preferred) ──

        vol_snap = None
        try:
            vol_snap = self._port.load_vol_regime_state()
        except Exception:
            pass

        if vol_snap:
            vol_label = vol_snap.current_state
            decision.vol_regime = vol_label
            decision.alerts.append(
                f"VOL_STATE: {vol_snap.current_state} "
                f"(day {vol_snap.duration_bars}, "
                f"prev={vol_snap.previous_state}, "
                f"trigger={vol_snap.trigger_event})"
            )
        else:
            try:
                vol_label = self._port.load_vol_regime_label()
            except Exception:
                vol_label = "NORMAL"
            decision.vol_regime = vol_label

        # ── Load Market Health snapshot (Persist-then-Read from Vault) ──
        _mh_snapshot = None
        _mh_sizing_mod = 1.0
        try:
            from backend.modules.market_health.domain.entities.health_snapshot import MarketHealthSnapshot
            from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
            _store = TimescaleDataStore()
            mh_raw = _store.load_mcp_latest("market/health", "MARKET")
            _store.close()
            if mh_raw:
                _mh_snapshot = MarketHealthSnapshot.from_dict(mh_raw)

                # HSA SystemicGatekeeper Overlay: Evaluates top-down macro vetoes without blocking pullbacks
                from backend.modules.entry_decision.domain.rules.systemic_gatekeeper import SystemicGatekeeper
                pulse = SystemicGatekeeper.create_pulse(
                    market_health_dict=mh_raw,
                    ast_ticker=ticker,
                    ast_signal=action,
                )
                verdict, _mh_sizing_mod, reason = SystemicGatekeeper.evaluate_overlay_veto(
                    pulse, department="QUALITY_SWING"
                )
                decision.alerts.append(f"HSA_GATEKEEPER: {verdict} ({reason}) | Sizing mod: {_mh_sizing_mod:.1f}")

                # F&G contrarian signals (forensic evidence 2021-2026)
                if _mh_snapshot.fg_action == "CAPITULATION_BUY":
                    # FG-H01 (t=6.39), FG-H07 urgency decay
                    boost = 1.5
                    if _mh_snapshot.fg_urgency == "HIGH":
                        boost = 1.75  # Day 1-3: WR 80.8%
                    elif _mh_snapshot.fg_urgency == "DECAYING":
                        boost = 1.15  # Day 10+: WR 50%
                    _mh_sizing_mod = min(_mh_sizing_mod * boost, 1.0)
                    decision.alerts.append(
                        f"MH_FG_CAPITULATION: F&G={_mh_snapshot.fg_score:.0f} "
                        f"day={_mh_snapshot.fg_duration} urgency={_mh_snapshot.fg_urgency} "
                        f"(WR 75.5%, t=6.39)"
                    )
                elif _mh_snapshot.fg_action == "FEAR_BUY":
                    # VALIDATED (t=5.37, WR=69.9%)
                    _mh_sizing_mod = min(_mh_sizing_mod * 1.2, 1.0)
                    decision.alerts.append(
                        f"MH_FG_FEAR_BUY: F&G={_mh_snapshot.fg_score:.0f} "
                        f"— fear zone accumulation (WR 69.9%)"
                    )
                elif _mh_snapshot.fg_action == "GREED_TRAP":
                    # FG-H08 CANDIDATE (N=6, WR 0%): greed + correction
                    _mh_sizing_mod = 0.0  # Block accumulation
                    decision.alerts.append(
                        f"MH_FG_GREED_TRAP: F&G={_mh_snapshot.fg_score:.0f} + correction "
                        f"— distribution TRAP (WR 0%). Accumulation BLOCKED."
                    )
                elif _mh_snapshot.fg_action == "GREED_CAUTION":
                    # H02 REJECTED (t=0.46): greed ≠ sell
                    _mh_sizing_mod *= 0.7
                    decision.alerts.append(
                        f"MH_FG_GREED: F&G={_mh_snapshot.fg_score:.0f} — sizing -30%"
                    )

                # FG-H14 VALIDATED (t=6.21): stealth accumulation
                if _mh_snapshot.fg_divergence_type == "STEALTH_ACCUMULATION":
                    _mh_sizing_mod = min(_mh_sizing_mod * 1.25, 1.0)
                    decision.alerts.append(
                        f"MH_STEALTH_ACCUM: Institutional accumulation "
                        f"(RISK_ON + public fear, WR 79%, t=6.21)"
                    )
        except Exception as e:
            logger.debug(f"SwingGate: MH snapshot not available: {e}")

        # ── UW IV Rank gate (per-ticker vol pricing) ──
        # Low IV Rank → options are cheap → accumulate (protection is cheap)
        # High IV Rank → options are expensive → reduce conviction (smart money buying puts)
        _iv_rank = None
        try:
            _store = TimescaleDataStore()
            _vol_snap = _store.load_mcp_latest("uw/vol_stats", ticker)
            _store.close()
            if _vol_snap and isinstance(_vol_snap, dict):
                _iv_rank = float(_vol_snap.get("iv_rank", 0) or 0)
                if _iv_rank > 0:
                    decision.alerts.append(
                        f"UW_IV_RANK: {_iv_rank:.0f}/100 "
                        f"(IV={float(_vol_snap.get('iv', 0) or 0):.1f}%, "
                        f"RV={float(_vol_snap.get('rv', 0) or 0):.1f}%)"
                    )
                    if _iv_rank < 20:
                        # Options historically cheap → accumulate with higher conviction
                        _mh_sizing_mod = min(_mh_sizing_mod * 1.15, 1.0)
                        decision.alerts.append(
                            "UW_IV_CHEAP: IV Rank <20 → options cheap, sizing +15%"
                        )
                    elif _iv_rank > 80:
                        # Options historically expensive → smart money hedging
                        _mh_sizing_mod *= 0.75
                        decision.alerts.append(
                            f"UW_IV_EXPENSIVE: IV Rank >80 → protection expensive, "
                            f"sizing {_mh_sizing_mod:.0%}"
                        )
        except Exception as e:
            logger.debug(f"SwingGate: UW IV Rank skipped: {e}")

        # ── Compute fear bias from pre-computed snapshot (0 regression calls) ──
        from backend.modules.quality_swing.domain.rules.fear_level import classify_fear_from_snapshot
        fear = classify_fear_from_snapshot(channel)

        # ── Load Signal Reliability Passports (multi-signal lookup) ──
        passport, passport_signal = self._load_best_passport(ticker, fear, vol_label)
        if passport:
            fear_label = rc_result.fear_label
            expected_wr = passport.wr_by_fear_level.get(fear_label, passport.win_rate)
            regime_sharpe = passport.sharpe_by_vol_regime.get(vol_label, passport.ceiling_sharpe)
            passport_context = (
                f"Passport[signal={passport_signal} grade={passport.grade} "
                f"reliability={passport.reliability_score:.2f} "
                f"OOS={passport.oos_sharpe:.2f} "
                f"expected_WR@{fear_label}={expected_wr:.0f}% "
                f"Sharpe@{vol_label}={regime_sharpe:.2f}]"
            )
            decision.alerts.append(passport_context)

            # RC Intelligence enrichment context
            rc_context = (
                f"RC[zone={rc_result.zone} σ={rc_result.sigma_position:+.1f} "
                f"conj={rc_result.slope_conjugation:+.3f} "
                f"vol_ratio={rc_result.vol_up_down_ratio:.1f} "
                f"conv={rc_result.conviction:+.2f}]"
            )
            decision.alerts.append(rc_context)

            logger.debug(f"SwingGate {ticker}: {passport_context} | {rc_context}")

        # ── Sentinel Turn Signal (reads persisted archetype from Vault) ──
        _turn: Optional[TurnSignal] = None
        try:
            _turn = self._load_turn_signal(ticker, channel)
            if _turn and _turn.is_active:
                decision.alerts.append(
                    f"SENTINEL[{_turn.archetype}]: "
                    f"P_PISO={_turn.prob_piso:.3f} P_TECHO={_turn.prob_techo:.3f} "
                    f"DENSITY={_turn.density_level} CONV={_turn.conviction:.2f}"
                )
        except Exception as e:
            logger.debug(f"SwingGate {ticker}: TurnSignal unavailable: {e}")

        # ── EXPLOSIÓN TECHO: Hard block on accumulation ──
        if (_turn and _turn.is_techo
                and _turn.density_level == DENSITY_EXPLOSION):
            decision.action = "TRIM"
            decision.conviction = _turn.conviction
            decision.reasoning = (
                f"SENTINEL_EXPLOSION: {_turn.archetype} at EXPLOSIÓN "
                f"(prob_techo={_turn.prob_techo:.3f}) | {_turn.diagnosis}"
            )
            return decision

        # ── Evaluate accumulate ──
        # (Observer recovery and velocities pre-loaded early in evaluate)

        should_accum, conviction, reason_accum = is_accumulate_signal(
            sigma_pos=rc_result.sigma_position,
            fear=fear,
            below_vwap=below_vwap,
            hookup=hookup,
            vol_regime_label=vol_label,
            observer_recovery=_observer_recovery,
            vel_sigma_c=_vel_sigma_c,
            vel_svw=_vel_svw,
            transition=_transition,
            dual_prob=_dual_prob,
            tide_signal=_tide,
            wave_signal=_wave,
            real_ev_signal=_real_ev,
        )

        if should_accum:
            # ── MH cascade BEAR blocks accumulation entirely ──
            if _mh_sizing_mod <= 0.0:
                decision.action_code = "STK_HOLD_NEUTRAL"
                decision.reasoning = (
                    f"MH_BLOCK: {reason_accum} — blocked by breadth cascade BEAR"
                )
                return decision


            # ── Passport-scaled conviction ──
            if passport and passport.viable:
                fear_label = rc_result.fear_label
                expected_wr = passport.wr_by_fear_level.get(fear_label, passport.win_rate)
                passport_scale = min(
                    passport.reliability_score * (expected_wr / 100.0),
                    1.0,
                )
                scaled_conviction = max(conviction * passport_scale, 0.1)
                if abs(scaled_conviction - conviction) > 0.01:
                    reason_accum += (
                        f" | Passport-scaled: {conviction:.2f}→{scaled_conviction:.2f} "
                        f"(signal={passport_signal} reliability={passport.reliability_score:.2f} "
                        f"expected_WR={expected_wr:.0f}%)"
                    )
                conviction = round(scaled_conviction, 2)
            elif passport and not passport.viable:
                conviction = round(conviction * 0.3, 2)
                reason_accum += f" | PASSPORT_NOT_VIABLE: conviction reduced to {conviction:.2f}"

            # ── RC Intelligence conviction modulation ──
            if rc_result.conviction > 0.5:
                conviction = min(conviction * 1.15, 1.0)
                reason_accum += f" | RC_HIGH_CONVICTION({rc_result.conviction:+.2f})"
            elif rc_result.conviction < -0.3:
                conviction *= 0.70
                reason_accum += f" | RC_WARNS({rc_result.conviction:+.2f})"

            # ── Sentinel: TurnSignal modulates accumulate conviction ──
            if _turn and _turn.is_active:
                if _turn.quality_swing_action == ACTION_ACCUMULATE:
                    # Sentinel confirms bottom → boost conviction
                    pre_turn = conviction
                    conviction = min(round(conviction * (1.0 + _turn.conviction * 0.3), 2), 1.0)
                    reason_accum += (
                        f" | SENTINEL_{_turn.archetype}: "
                        f"conv {pre_turn:.2f}→{conviction:.2f} "
                        f"({_turn.density_level})"
                    )
                elif _turn.is_techo and _turn.density_level in (DENSITY_PRESSURIZE, DENSITY_EXPLOSION):
                    # Sentinel warns ceiling → reduce conviction
                    pre_turn = conviction
                    conviction = round(conviction * 0.4, 2)
                    reason_accum += (
                        f" | SENTINEL_WARN_{_turn.archetype}: "
                        f"conv {pre_turn:.2f}→{conviction:.2f} "
                        f"(techo {_turn.density_level})"
                    )

            # ── MH sizing modifier (cascade + F&G) ──
            if _mh_sizing_mod < 1.0:
                pre_mh = conviction
                conviction = round(conviction * _mh_sizing_mod, 2)
                reason_accum += f" | MH_MOD: {pre_mh:.2f}→{conviction:.2f}"

            decision.action_code = _tide.action_code if _tide else "STK_ACCUMULATE_STRUCTURAL"
            decision.urgency_level = _tide.urgency_level if _tide else "LOW"
            decision.scope_level = _tide.scope_level if _tide else "STK"
            decision.conviction = round(conviction, 2)
            decision.reasoning = reason_accum
            logger.info(
                f"SwingGate {ticker}: ACCUMULATE ({decision.action_code}, urgency={decision.urgency_level}, conviction={conviction:.2f}) — {reason_accum}"
            )
            return decision

        # ── Evaluate trim ──
        should_trim, trim_pct, reason_trim = is_trim_signal(
            sigma_pos=rc_result.sigma_position,
            fear=fear,
            observer_recovery=_observer_recovery,
            vel_sigma_c=_vel_sigma_c,
            vel_svw=_vel_svw,
            transition=_transition,
            dual_prob=_dual_prob,
            tide_signal=_tide,
            wave_signal=_wave,
            real_ev_signal=_real_ev,
        )

        if should_trim:
            # ── Sentinel: TurnSignal modulates trim ──
            if _turn and _turn.is_active:
                if _turn.quality_swing_action == ACTION_TRIM:
                    # Sentinel confirms ceiling → boost trim
                    pre_turn = trim_pct
                    trim_pct = min(trim_pct * (1.0 + _turn.conviction * 0.5), 0.5)
                    reason_trim += (
                        f" | SENTINEL_{_turn.archetype}: "
                        f"trim {pre_turn:.0%}→{trim_pct:.0%} "
                        f"({_turn.diagnosis})"
                    )
                elif _turn.is_piso and _turn.density_level in (DENSITY_PRESSURIZE, DENSITY_EXPLOSION):
                    # Sentinel says bottom forming → reduce trim urgency
                    pre_turn = trim_pct
                    trim_pct = round(trim_pct * 0.5, 2)
                    reason_trim += (
                        f" | SENTINEL_CONTRA_{_turn.archetype}: "
                        f"trim {pre_turn:.0%}→{trim_pct:.0%} "
                        f"(piso {_turn.density_level})"
                    )

            decision.action_code = _tide.action_code if _tide else "STK_TRIM_TACTICAL"
            decision.urgency_level = _tide.urgency_level if _tide else "LOW"
            decision.scope_level = _tide.scope_level if _tide else "STK"
            decision.conviction = trim_pct
            decision.reasoning = reason_trim
            logger.info(
                f"SwingGate {ticker}: TRIM ({decision.action_code}, urgency={decision.urgency_level}, {trim_pct:.0%}) — {reason_trim}"
            )
            return decision

        # ── Sentinel override: PRESURIZACIÓN techo may promote HOLD → TRIM ──
        if (_turn and _turn.quality_swing_action == ACTION_TRIM
                and _turn.density_level in (DENSITY_PRESSURIZE, DENSITY_EXPLOSION)
                and rc_result.sigma_position > 0):
            decision.action_code = "STK_TRIM_TACTICAL"
            decision.urgency_level = "LOW"
            decision.scope_level = "STK"
            decision.conviction = round(_turn.conviction * 0.4, 2)
            decision.reasoning = (
                f"SENTINEL_OVERRIDE: {_turn.archetype} at {_turn.density_level} "
                f"AND σ={rc_result.sigma_position:.1f}>0 → TRIM | {_turn.diagnosis}"
            )
            logger.info(f"SwingGate {ticker}: {decision.reasoning}")
            return decision

        # ── Default: HOLD ──
        decision.action_code = _tide.action_code if _tide else "STK_HOLD_NEUTRAL"

        decision.urgency_level = _tide.urgency_level if _tide else "PASSIVE"
        decision.scope_level = _tide.scope_level if _tide else "STK"
        _prob_ctx = f" P(bull)={_tide.p_bull:.1f}%" if _tide else ""
        decision.reasoning = (
            f"HOLD ({decision.action_code}): σ={rc_result.sigma_position:.1f}, "
            f"fear={rc_result.fear_label}, tide={rc_result.tide_slope:.3f}, "
            f"zone={rc_result.zone}{_prob_ctx}"
        )
        return decision


    # ── Internal: RC Intelligence (lazy) ──────────────────────────

    def _get_rc_analysis(self, ohlc, channel=None):
        """Lazy-init and call RegressionChannelIntelligence.

        When channel is provided, uses the fast path (0 regression calls).
        Otherwise computes internally (backward compat).
        """
        try:
            if SwingGate._rc_intel is None:
                from backend.modules.price_analysis.application.use_cases.analyze_regression_channel import (
                    RegressionChannelIntelligence,
                )
                SwingGate._rc_intel = RegressionChannelIntelligence()
            return SwingGate._rc_intel.analyze(ohlc, snapshot=channel)
        except Exception as e:
            logger.error(f"SwingGate: RCIntelligence failed: {e}")
            return None

    # ── Internal: Sentinel Turn Signal ─────────────────────────────

    def _load_turn_signal(self, ticker: str, channel=None) -> Optional[TurnSignal]:
        """Load the most recent TurnSignal for this ticker from Vault.

        Reads turn_archetype, turn_prob_piso, turn_prob_techo, turn_density
        from engine.channel_snapshots (populated by the Sentinel daemon step).

        Returns None if columns are not yet populated (backfill pending).
        """
        try:
            latest = self._port.load_latest_snapshot(ticker)
            if latest is None:
                return None

            # Check if Sentinel columns exist and are populated
            archetype = getattr(latest, 'turn_archetype', None)
            if not archetype or archetype == "NONE":
                return None

            prob_piso = getattr(latest, 'turn_prob_piso', 0.0) or 0.0
            prob_techo = getattr(latest, 'turn_prob_techo', 0.0) or 0.0
            density = getattr(latest, 'turn_density', 'SILENCIO') or 'SILENCIO'

            from backend.modules.shared.domain.entities.turn_signal import (
                TurnSignal, ARCHETYPE_NONE,
                DENSITY_SILENCE, DENSITY_ALARM, DENSITY_PRESSURIZE, DENSITY_EXPLOSION,
            )

            # Map density level to conviction
            conviction = {
                DENSITY_SILENCE: 0.0, DENSITY_ALARM: 0.3,
                DENSITY_PRESSURIZE: 0.6, DENSITY_EXPLOSION: 0.9,
            }.get(density, 0.0)

            # Determine actions from archetype
            from backend.modules.shared.domain.rules.turn_detector import _map_actions
            qc, qs, spec = _map_actions(archetype, density)

            return TurnSignal(
                archetype=archetype,
                prob_piso=prob_piso,
                prob_techo=prob_techo,
                density_level=density,
                quality_core_action=qc,
                quality_swing_action=qs,
                speculative_action=spec,
                conviction=conviction,
                kf_rsi_pred=getattr(latest, 'kf_rsi_pred_val', 0.0) or 0.0,
                kf_price_vel=getattr(latest, 'kf_price_filt_vel', 0.0) or 0.0,
                diagnosis=f"FROM_VAULT: {archetype} density={density}",
            )
        except Exception as e:
            logger.debug(f"SwingGate {ticker}: TurnSignal load failed: {e}")
            return None

    def _load_observer_recovery(self, ticker: str) -> float:
        """Load the Unified Observer recovery_score from Vault.

        Reads obs_recovery_score from engine.channel_snapshots
        (populated by backfill_unified_observer or daily daemon).

        Returns 0.0 if column not yet populated.
        """
        try:
            latest = self._port.load_latest_snapshot(ticker)
            if latest is None:
                return 0.0
            return float(getattr(latest, 'obs_recovery_score', 0.0) or 0.0)
        except Exception as e:
            logger.debug(f"SwingGate {ticker}: Observer recovery load failed: {e}")
            return 0.0

    def _load_observer_velocities(self, ticker: str) -> tuple[float, float]:
        """Load vel_sigma_c and vel_svw from Observer output in Vault.

        These velocities (T7) have 21pp spread for timing — 4× better than
        the raw channel accelerations (5pp) they replace.

        Returns (vel_sigma_c, vel_svw). Defaults to (0.0, 0.0) if unavailable.
        """
        try:
            latest = self._port.load_latest_snapshot(ticker)
            if latest is None:
                return 0.0, 0.0
            return (
                float(getattr(latest, 'obs_vel_sigma_c', 0.0) or 0.0),
                float(getattr(latest, 'obs_vel_svw', 0.0) or 0.0),
            )
        except Exception as e:
            logger.debug(f"SwingGate {ticker}: Observer velocities load failed: {e}")
            return 0.0, 0.0

    def _load_best_passport(self, ticker: str, fear, vol_label: str):
        """Load the best passport for current conditions.

        Strategy: load ALL passports for this ticker × QUALITY_SWING,
        then select the one with highest (reliability × expected_WR × regime_sharpe)
        for the CURRENT fear_level.

        Returns: (passport, signal_name) or (None, None)
        """
        if self._passports is None:
            return None, None

        try:
            all_passports = self._passports.load_passports_for_ticker(
                ticker, "QUALITY_SWING"
            )
            if not all_passports:
                return None, None

            fear_label = fear.fear_label if fear else "NEUTRAL"
            best = None
            best_score = -1.0
            best_name = None

            for pp in all_passports:
                if not pp.viable:
                    continue
                expected_wr = pp.wr_by_fear_level.get(fear_label, pp.win_rate)
                regime_sharpe = pp.sharpe_by_vol_regime.get(vol_label, pp.ceiling_sharpe)
                # Combined score: reliability × WR × regime performance
                score = pp.reliability_score * (expected_wr / 100.0) * max(regime_sharpe, 0.1)
                if score > best_score:
                    best_score = score
                    best = pp
                    best_name = pp.signal_name

            return best, best_name
        except Exception as e:
            logger.debug(f"SwingGate {ticker}: multi-passport load failed: {e}")
            return None, None
