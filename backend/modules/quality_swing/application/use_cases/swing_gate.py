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
from backend.modules.shared.domain.ports.head_scorer_port import HeadScorerPort
from backend.modules.quality_swing.domain.rules.meta_signals import detect_meta_signals

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
        head_scorer: Optional[HeadScorerPort] = None,
    ):
        self._port = data_port
        self._passports = passport_store  # Optional — degrades gracefully
        self._head_scorer = head_scorer   # Optional — ML conviction modulation

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
        hookup = ohlc["close"].iloc[idx] > ohlc["close"].iloc[idx - 1] if idx > 0 else False

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

                # Cascade gate: BEAR blocks accumulation, CORRECTION reduces
                if _mh_snapshot.cascade_state == 3:  # BEAR
                    _mh_sizing_mod = 0.0
                    decision.alerts.append(
                        f"MH_CASCADE_BEAR: Accumulation BLOCKED "
                        f"(S5 participation={_mh_snapshot.breadth_participation:.1%})"
                    )
                elif _mh_snapshot.cascade_state == 2:  # CORRECTION
                    _mh_sizing_mod = 0.5
                    decision.alerts.append("MH_CASCADE_CORRECTION: Sizing 50%")

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

        # ── ML Head Scores (optional, modulates conviction) ──
        _ml_scores = {}
        if self._head_scorer is not None:
            try:
                _ml_scores = self._head_scorer.score_all(ticker, channel)
                for hn, hs in _ml_scores.items():
                    marker = "★" if hs.triggered else ""
                    decision.alerts.append(
                        f"ML[{hn}]: P={hs.probability:.3f} "
                        f"(thr={hs.threshold:.2f}){marker}"
                    )
            except Exception as e:
                logger.debug(f"SwingGate {ticker}: HeadScorer unavailable: {e}")

        # ── Meta-Signal Detection (second-order constellations) ──
        _meta_signals = []
        if _ml_scores and channel:
            _meta_signals = detect_meta_signals(_ml_scores, channel)
            for ms in _meta_signals:
                decision.alerts.append(
                    f"META[{ms.name}]: {ms.level} → {ms.action} | {ms.description}"
                )

        # ── DANGER CONSTELLATION: Hard block (43.9% crash, 2.8x lift) ──
        _danger_block = any(ms.level == "DANGER" for ms in _meta_signals)
        if _danger_block:
            decision.action = "HOLD"
            danger_ms = next(ms for ms in _meta_signals if ms.level == "DANGER")
            decision.reasoning = (
                f"DANGER_BLOCK: {danger_ms.description} | "
                f"Evidence: {danger_ms.evidence}"
            )
            decision.ml_scores = {
                hn: hs.probability for hn, hs in _ml_scores.items()
            }
            return decision

        # ── Evaluate accumulate ──
        should_accum, conviction, reason_accum = is_accumulate_signal(
            sigma_pos=rc_result.sigma_position,
            fear=fear,
            below_vwap=below_vwap,
            hookup=hookup,
            vol_regime_label=vol_label,
        )

        if should_accum:
            # ── MH cascade BEAR blocks accumulation entirely ──
            if _mh_sizing_mod <= 0.0:
                decision.action = "HOLD"
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

            # ── ML conviction modulation (Druckenmiller: model MODULATES, not DECIDES) ──
            if 'pullback_depth' in _ml_scores:
                pd_score = _ml_scores['pullback_depth']
                if pd_score.triggered:
                    # Model says pullback will deepen → reduce conviction
                    pre_ml = conviction
                    conviction = round(conviction * 0.5, 2)
                    reason_accum += (
                        f" | ML_PULLBACK_WARN: P(deeper)={pd_score.probability:.2f}≥{pd_score.threshold:.2f} "
                        f"→ conviction {pre_ml:.2f}→{conviction:.2f}"
                    )

            # ── ML: zz_bottom_detector boosts accumulate (Phase 2 forensic) ──
            # DSR=13.89, edge=+41.3%, fires 3d BEFORE bottom in 89% of cases.
            if 'zz_bottom_detector' in _ml_scores:
                zz_bot = _ml_scores['zz_bottom_detector']
                if zz_bot.probability >= 0.65:
                    pre_zz = conviction
                    conviction = min(round(conviction * 1.25, 2), 1.0)
                    reason_accum += (
                        f" | ZZ_BOTTOM: P={zz_bot.probability:.2f}≥0.65 "
                        f"→ conviction {pre_zz:.2f}→{conviction:.2f} "
                        f"(turning point ~3d ahead, DSR=13.89)"
                    )

            # ── MH sizing modifier (cascade + F&G) ──
            if _mh_sizing_mod < 1.0:
                pre_mh = conviction
                conviction = round(conviction * _mh_sizing_mod, 2)
                reason_accum += f" | MH_MOD: {pre_mh:.2f}→{conviction:.2f}"

            decision.action = "ACCUMULATE"
            decision.conviction = round(conviction, 2)
            decision.reasoning = reason_accum
            logger.info(
                f"SwingGate {ticker}: ACCUMULATE (conviction={conviction:.2f}) — {reason_accum}"
            )
            return decision

        # ── Evaluate trim ──
        should_trim, trim_pct, reason_trim = is_trim_signal(
            sigma_pos=rc_result.sigma_position,
            fear=fear,
        )

        if should_trim:
            # ── ML: short_entry as exit proxy (r=-0.14, 2.3x stronger than swing_exit) ──
            if 'short_entry' in _ml_scores:
                se_prob = _ml_scores['short_entry'].probability
                if se_prob > 0.65:
                    # Strong short signal confirms exit → boost trim
                    pre_ml = trim_pct
                    trim_pct = min(trim_pct * 1.5, 0.5)
                    reason_trim += (
                        f" | SHORT_EXIT_PROXY: P(short)={se_prob:.2f}>0.65 "
                        f"→ trim {pre_ml:.0%}→{trim_pct:.0%} (r=-0.14, forensic-validated)"
                    )
                elif se_prob < 0.35:
                    # No short pressure → reduce trim urgency
                    pre_ml = trim_pct
                    trim_pct = round(trim_pct * 0.6, 2)
                    reason_trim += (
                        f" | SHORT_EXIT_CONTRA: P(short)={se_prob:.2f}<0.35 "
                        f"→ trim {pre_ml:.0%}→{trim_pct:.0%}"
                    )

            # ── LONG_SQUEEZE alert modulation ──
            if any(ms.name == "LONG_SQUEEZE" for ms in _meta_signals):
                pre_sq = trim_pct
                trim_pct = min(trim_pct * 1.3, 0.5)
                reason_trim += (
                    f" | LONG_SQUEEZE: trim {pre_sq:.0%}→{trim_pct:.0%}"
                )

            # ── ML: zz_top_detector confirms trim (Phase 2 forensic) ──
            # DSR=30.06, 69% fires before top. Confirms ceiling → boost trim.
            if 'zz_top_detector' in _ml_scores:
                zz_top = _ml_scores['zz_top_detector']
                if zz_top.probability >= 0.65:
                    pre_zz = trim_pct
                    trim_pct = min(round(trim_pct * 1.3, 2), 0.5)
                    reason_trim += (
                        f" | ZZ_TOP: P={zz_top.probability:.2f}≥0.65 "
                        f"→ trim {pre_zz:.0%}→{trim_pct:.0%} "
                        f"(ceiling ~3d ahead, DSR=30.06)"
                    )

            decision.action = "TRIM"
            decision.conviction = trim_pct
            decision.reasoning = reason_trim
            logger.info(
                f"SwingGate {ticker}: TRIM ({trim_pct:.0%}) — {reason_trim}"
            )
            return decision

        # ── Short_entry exit proxy: may override HOLD → TRIM ──
        # Forensic: P(short_entry) r=-0.14 with fwd_10d (2.3x stronger than swing_exit)
        if 'short_entry' in _ml_scores:
            p_short = _ml_scores['short_entry'].probability
            if p_short > 0.55 and rc_result.sigma_position > 0:
                # In profit + short signal rising → TRIM suggestion
                trim_conv = round(min(p_short * 0.4, 0.3), 2)
                decision.action = "TRIM"
                decision.conviction = trim_conv
                decision.reasoning = (
                    f"SHORT_EXIT_PROXY: P(short)={p_short:.2f}>0.55 AND σ={rc_result.sigma_position:.1f}>0 "
                    f"→ TRIM {trim_conv:.0%} (forensic: r=-0.14, stronger than swing_exit)"
                )
                decision.ml_scores = {
                    hn: hs.probability for hn, hs in _ml_scores.items()
                }
                logger.info(f"SwingGate {ticker}: {decision.reasoning}")
                return decision

        # ── Default: HOLD ──
        decision.action = "HOLD"
        decision.reasoning = (
            f"HOLD: σ={rc_result.sigma_position:.1f}, "
            f"fear={rc_result.fear_label}, tide={rc_result.tide_slope:.3f}, "
            f"zone={rc_result.zone}"
        )
        decision.ml_scores = {
            hn: hs.probability for hn, hs in _ml_scores.items()
        } if _ml_scores else {}
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

    # ── Internal: Multi-passport lookup ───────────────────────────

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
