"""
Signal Passport Generator — Departmental Calibration Orchestrator
==================================================================
Runs OracleCoreBacktester + OracleSwingBacktester across the Quality universe
and produces a consolidated reliability report.

Usage:
    generator = SignalPassportGenerator(
        store=timescale_store,
        labeler=triple_barrier,
        passport_store=neon_passport_store,
    )
    report = generator.calibrate_quality_universe(tickers)
    print(report.summary())

This is the entry point for the periodic recalibration job.
Recommended frequency: weekly (after market close Friday).
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional

from backend.modules.simulation.application.use_cases.oracle_core import (
    OracleCoreBacktester, create_core_signals,
)
from backend.modules.simulation.application.use_cases.oracle_swing import (
    OracleSwingBacktester, create_swing_signals,
)
from backend.modules.simulation.domain.entities.signal_passport import SignalPassport
from backend.modules.simulation.domain.ports.barrier_labeler_port import BarrierLabelerPort
from backend.modules.simulation.domain.ports.historical_data_port import HistoricalDataPort
from backend.modules.simulation.domain.ports.ml_data_port import MLDataPort
from backend.modules.simulation.domain.ports.passport_store_port import PassportStorePort

logger = logging.getLogger(__name__)


@dataclass
class CalibrationReport:
    """Summary of a full Quality universe calibration run."""
    run_at: str = ""
    tickers_attempted: int = 0
    tickers_calibrated: int = 0

    # Core results
    core_passports: list[SignalPassport] = field(default_factory=list)
    core_viable_count: int = 0
    core_grade_a_count: int = 0

    # Swing results
    swing_passports: list[SignalPassport] = field(default_factory=list)
    swing_viable_count: int = 0
    swing_grade_a_count: int = 0

    # Errors
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Human-readable calibration report."""
        lines = [
            "=" * 70,
            "QUALITY UNIVERSE CALIBRATION REPORT",
            f"Run at: {self.run_at}",
            f"Tickers: {self.tickers_calibrated}/{self.tickers_attempted} calibrated",
            "",
            "── QUALITY CORE ─────────────────────────────────────────────",
            f"  Passports generated: {len(self.core_passports)}",
            f"  Viable: {self.core_viable_count}  Grade A: {self.core_grade_a_count}",
        ]

        if self.core_passports:
            lines.append("  Top performers:")
            top_core = sorted(
                self.core_passports, key=lambda p: p.reliability_score, reverse=True
            )[:5]
            for p in top_core:
                lines.append(
                    f"    {p.ticker}/{p.signal_name}: grade={p.grade} "
                    f"Sharpe={p.ceiling_sharpe:.2f} reliability={p.reliability_score:.2f} "
                    f"survival={p.thesis_survival_rate:.0f}%"
                )

        lines += [
            "",
            "── QUALITY SWING ────────────────────────────────────────────",
            f"  Passports generated: {len(self.swing_passports)}",
            f"  Viable: {self.swing_viable_count}  Grade A: {self.swing_grade_a_count}",
        ]

        if self.swing_passports:
            lines.append("  Top performers:")
            top_swing = sorted(
                self.swing_passports, key=lambda p: p.reliability_score, reverse=True
            )[:5]
            for p in top_swing:
                panic_wr = p.wr_by_fear_level.get("PANIC", 0.0)
                lines.append(
                    f"    {p.ticker}/{p.signal_name}: grade={p.grade} "
                    f"Sharpe={p.ceiling_sharpe:.2f} OOS={p.oos_sharpe:.2f} "
                    f"PANIC_WR={panic_wr:.0f}% wave_flip_edge={p.wave_flip_edge:+.1f}%"
                )

        if self.errors:
            lines += ["", f"── ERRORS ({len(self.errors)}) ───────────────────────────────"]
            lines += [f"  {e}" for e in self.errors[:10]]

        lines.append("=" * 70)
        return "\n".join(lines)


class SignalPassportGenerator:
    """
    Orchestrates full Quality universe calibration.

    Runs Core Oracle and Swing Oracle for each ticker in the Quality universe,
    collects passports, and produces a CalibrationReport.
    """

    def __init__(
        self,
        store: HistoricalDataPort,
        labeler: BarrierLabelerPort,
        passport_store: PassportStorePort,
        ml_store: Optional[MLDataPort] = None,
    ):
        self._core = OracleCoreBacktester(store, labeler, passport_store, ml_store)
        self._swing = OracleSwingBacktester(store, labeler, passport_store, ml_store)

    def calibrate_quality_universe(
        self,
        tickers: list[str],
        tf: str = "1d",
        run_core: bool = True,
        run_swing: bool = True,
    ) -> CalibrationReport:
        """
        Run full calibration for all tickers in the Quality universe.

        Args:
            tickers: Quality-universe tickers. Must be pre-qualified by Core.
            tf: Timeframe (daily for Quality).
            run_core: Whether to run OracleCoreBacktester.
            run_swing: Whether to run OracleSwingBacktester.

        Returns:
            CalibrationReport with all passports and a printable summary.
        """
        report = CalibrationReport(
            run_at=datetime.now(UTC).isoformat(),
            tickers_attempted=len(tickers),
        )

        core_signals = create_core_signals()
        swing_signals = create_swing_signals()
        calibrated: set[str] = set()

        for ticker in tickers:
            ticker_had_results = False

            # ── Core calibration ──
            if run_core:
                try:
                    core_passports = self._core.run_and_passport(ticker, tf, core_signals)
                    if core_passports:
                        report.core_passports.extend(core_passports)
                        report.core_viable_count += sum(1 for p in core_passports if p.viable)
                        report.core_grade_a_count += sum(1 for p in core_passports if p.grade == "A")
                        ticker_had_results = True
                except Exception as e:
                    msg = f"Core/{ticker}: {e}"
                    report.errors.append(msg)
                    logger.error(msg)

            # ── Swing calibration ──
            if run_swing:
                try:
                    swing_passports = self._swing.run_and_passport(ticker, tf, swing_signals)
                    if swing_passports:
                        report.swing_passports.extend(swing_passports)
                        report.swing_viable_count += sum(1 for p in swing_passports if p.viable)
                        report.swing_grade_a_count += sum(1 for p in swing_passports if p.grade == "A")
                        ticker_had_results = True
                except Exception as e:
                    msg = f"Swing/{ticker}: {e}"
                    report.errors.append(msg)
                    logger.error(msg)

            if ticker_had_results:
                calibrated.add(ticker)

        report.tickers_calibrated = len(calibrated)
        logger.info(f"\n{report.summary()}")
        return report

    def calibrate_single(
        self,
        ticker: str,
        tf: str = "1d",
        run_core: bool = True,
        run_swing: bool = True,
    ) -> CalibrationReport:
        """Calibrate a single ticker (convenience method for on-demand re-calibration)."""
        return self.calibrate_quality_universe(
            [ticker], tf, run_core=run_core, run_swing=run_swing
        )
