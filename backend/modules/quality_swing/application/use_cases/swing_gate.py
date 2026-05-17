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
        start = (reference_date or date.today()) - timedelta(days=400)
        ohlc = self._port.load_ohlc(ticker, "1d", start=start)
        if ohlc is None or len(ohlc) < 210:
            decision.reasoning = "INSUFFICIENT_DATA: Need 200+ bars"
            return decision

        # ── RC Intelligence — single tool replaces 6 manual computations ──
        # Replaces: linreg_channel(), calc_vwap(), sigma_position(),
        #           compute_ticker_fear_level(), regime detection, vol ratio
        rc_result = self._get_rc_analysis(ohlc)
        if rc_result is None:
            decision.reasoning = "RC_INTEL_FAILED: Cannot compute channel"
            return decision

        decision.sigma_position = rc_result.sigma_position
        decision.fear_level = rc_result.fear_level
        decision.fear_label = rc_result.fear_label
        decision.tide_slope = rc_result.tide_slope
        decision.wave_slope = rc_result.wave_slope

        below_vwap = rc_result.below_vwap
        idx = len(ohlc) - 1
        hookup = ohlc["close"].iloc[idx] > ohlc["close"].iloc[idx - 1] if idx > 0 else False

        # ── Load vol regime ──
        try:
            vol_label = self._port.load_vol_regime_label()
        except Exception:
            vol_label = "NORMAL"
        decision.vol_regime = vol_label

        # ── Compute fear bias (full entity for entry rules) ──
        from backend.modules.quality_swing.domain.rules.fear_level import compute_ticker_fear_level
        fear = compute_ticker_fear_level(ohlc, idx)

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

        # ── Evaluate accumulate ──
        should_accum, conviction, reason_accum = is_accumulate_signal(
            sigma_pos=rc_result.sigma_position,
            fear=fear,
            below_vwap=below_vwap,
            hookup=hookup,
            vol_regime_label=vol_label,
        )

        if should_accum:
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
            decision.action = "TRIM"
            decision.conviction = trim_pct
            decision.reasoning = reason_trim
            logger.info(
                f"SwingGate {ticker}: TRIM ({trim_pct:.0%}) — {reason_trim}"
            )
            return decision

        # ── Default: HOLD ──
        decision.action = "HOLD"
        decision.reasoning = (
            f"HOLD: σ={rc_result.sigma_position:.1f}, "
            f"fear={rc_result.fear_label}, tide={rc_result.tide_slope:.3f}, "
            f"zone={rc_result.zone}"
        )
        return decision

    # ── Internal: RC Intelligence (lazy) ──────────────────────────

    def _get_rc_analysis(self, ohlc):
        """Lazy-init and call RegressionChannelIntelligence."""
        try:
            if SwingGate._rc_intel is None:
                from backend.modules.price_analysis.application.use_cases.analyze_regression_channel import (
                    RegressionChannelIntelligence,
                )
                SwingGate._rc_intel = RegressionChannelIntelligence()
            return SwingGate._rc_intel.analyze(ohlc)
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
