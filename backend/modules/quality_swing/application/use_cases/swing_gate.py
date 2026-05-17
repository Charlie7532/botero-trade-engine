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

Domain rules consumed (pure functions, no mocks needed for testing):
  - regression_channel.linreg_channel, calc_vwap, sigma_position
  - fear_level.compute_ticker_fear_level
  - swing_entry_rules.is_accumulate_signal, is_trim_signal
"""
import logging
import numpy as np
from datetime import date, timedelta
from typing import Optional

from backend.modules.quality_swing.domain.dtos.swing_decision import SwingDecision
from backend.modules.quality_swing.domain.ports.swing_data_port import SwingDataPort
from backend.modules.quality_swing.domain.rules.regression_channel import (
    linreg_channel,
    calc_vwap,
    sigma_position,
)
from backend.modules.quality_swing.domain.rules.fear_level import compute_ticker_fear_level
from backend.modules.quality_swing.domain.rules.swing_entry_rules import (
    is_accumulate_signal,
    is_trim_signal,
)

logger = logging.getLogger(__name__)

_PRIMARY_SIGNAL = "regression_channel"  # The signal passport we read for RC


class SwingGate:
    """Orchestrates swing timing evaluation for a single ticker.

    Constructor injection: receives data port (required) and passport store
    (optional). When passport store is provided, conviction is scaled by
    empirical reliability from the Signal Reliability Passport.
    """

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

        # ── Compute regression channel at the last bar ──
        close = ohlc["close"].values.astype(float)
        high = ohlc["high"].values.astype(float)
        low = ohlc["low"].values.astype(float)
        volume = ohlc["volume"].values.astype(float)

        idx = len(ohlc) - 1
        price_window = close[:idx + 1]
        current_price = close[idx]

        reg_value, slope_long, residual_std = linreg_channel(price_window, 200)
        sig_pos = sigma_position(current_price, reg_value, residual_std)
        vwap = calc_vwap(close[:idx + 1], high[:idx + 1], low[:idx + 1], volume[:idx + 1], 20)
        below_vwap = current_price < vwap
        hookup = close[idx] > close[idx - 1] if idx > 0 else False

        decision.sigma_position = round(sig_pos, 2)

        # ── Compute fear level ──
        fear = compute_ticker_fear_level(ohlc, idx)
        if fear:
            decision.fear_level = fear.fear_level
            decision.fear_label = fear.fear_label
            decision.tide_slope = round(fear.tide_slope, 4)
            decision.wave_slope = round(fear.wave_slope, 4)

        # ── Load vol regime ──
        try:
            vol_label = self._port.load_vol_regime_label()
        except Exception:
            vol_label = "NORMAL"
        decision.vol_regime = vol_label

        # ── Load Signal Reliability Passport (if available) ──
        passport = None
        if self._passports is not None:
            try:
                passport = self._passports.load_passport(
                    ticker, "QUALITY_SWING", _PRIMARY_SIGNAL
                )
                if passport:
                    fear_label = fear.fear_label if fear else "NEUTRAL"
                    expected_wr = passport.wr_by_fear_level.get(fear_label, passport.win_rate)
                    regime_sharpe = passport.sharpe_by_vol_regime.get(vol_label, passport.ceiling_sharpe)
                    passport_context = (
                        f"Passport[grade={passport.grade} "
                        f"reliability={passport.reliability_score:.2f} "
                        f"OOS={passport.oos_sharpe:.2f} "
                        f"expected_WR@{fear_label}={expected_wr:.0f}% "
                        f"Sharpe@{vol_label}={regime_sharpe:.2f}]"
                    )
                    decision.alerts.append(passport_context)
                    logger.debug(f"SwingGate {ticker}: {passport_context}")
            except Exception as e:
                logger.debug(f"SwingGate {ticker}: passport load skipped: {e}")

        # ── Evaluate accumulate ──
        should_accum, conviction, reason_accum = is_accumulate_signal(
            sigma_pos=sig_pos,
            fear=fear,
            below_vwap=below_vwap,
            hookup=hookup,
            vol_regime_label=vol_label,
        )

        if should_accum:
            # ── Passport-scaled conviction ──
            if passport and passport.viable:
                fear_label = fear.fear_label if fear else "NEUTRAL"
                expected_wr = passport.wr_by_fear_level.get(fear_label, passport.win_rate)
                # Scale: conviction × reliability × (expected_wr / 100)
                # Cap at 1.0, floor at 0.1 to never fully suppress a valid signal
                passport_scale = min(
                    passport.reliability_score * (expected_wr / 100.0),
                    1.0,
                )
                scaled_conviction = max(conviction * passport_scale, 0.1)
                if abs(scaled_conviction - conviction) > 0.01:
                    reason_accum += (
                        f" | Passport-scaled: {conviction:.2f}→{scaled_conviction:.2f} "
                        f"(reliability={passport.reliability_score:.2f} "
                        f"expected_WR={expected_wr:.0f}%)"
                    )
                conviction = round(scaled_conviction, 2)
            elif passport and not passport.viable:
                # Signal exists in passport but not viable — downscale sharply
                conviction = round(conviction * 0.3, 2)
                reason_accum += f" | PASSPORT_NOT_VIABLE: conviction reduced to {conviction:.2f}"

            decision.action = "ACCUMULATE"
            decision.conviction = conviction
            decision.reasoning = reason_accum
            logger.info(
                f"SwingGate {ticker}: ACCUMULATE (conviction={conviction:.2f}) — {reason_accum}"
            )
            return decision

        # ── Evaluate trim ──
        should_trim, trim_pct, reason_trim = is_trim_signal(
            sigma_pos=sig_pos,
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
        hold_tide = f"tide={fear.tide_slope:.3f}" if fear else "tide=0.000"
        decision.reasoning = (
            f"HOLD: σ={sig_pos:.1f}, fear={fear.fear_label if fear else '?'}, {hold_tide}"
        )
        return decision
