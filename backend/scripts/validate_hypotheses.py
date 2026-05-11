"""
Hypothesis Validation Runner — Oracle Alpha Ceiling
=======================================================
Connects to Neon PostgreSQL Vault and runs OracleBacktester
against each signal adapter that operates on pure OHLCV data.

Signals requiring external context (UW flow, SMC structure) are
tested with OHLCV-only data and annotated as limited validation.

Usage:
    cd /root/botero-trade
    backend/.venv/bin/python backend/scripts/validate_hypotheses.py
"""
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
import logging
import sys
from datetime import datetime, UTC
from dataclasses import dataclass, field

import numpy as np

# Infrastructure
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.simulation.infrastructure.triple_barrier_adapter import TripleBarrierAdapter
from backend.modules.simulation.application.use_cases.oracle_backtest import (
    OracleBacktester, OracleResult, SignalRanking,
)
from backend.modules.simulation.domain.entities.strategy_profile import (
    InvestmentCategory, OracleGeometry, ORACLE_GEOMETRY,
)

# Signal Adapters (only those that work with pure OHLCV)
from backend.modules.simulation.infrastructure.signal_adapters import (
    KalmanSignalAdapter,
    MeanReversionSignalAdapter,
    VolumeQualitySignalAdapter,
    RSISignalAdapter,
    PatternSignalAdapter,
    BOSSignalAdapter,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


@dataclass
class HypothesisResult:
    """Complete result for one hypothesis validation."""
    signal_name: str
    ticker: str
    category: str
    evidence_status: str  # HYPOTHESIS, VALIDATED, etc.

    # Oracle results
    oracle_sharpe: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    n_entries: int = 0
    avg_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_bars_held: float = 0.0
    grade: str = "—"

    # Validation metadata
    data_source: str = "Vault (Neon PostgreSQL)"
    data_limitation: str = ""  # Annotation if data was insufficient
    validated_at: str = ""
    bars_available: int = 0

    def verdict(self) -> str:
        if self.n_entries < 10:
            return "INSUFFICIENT_DATA"
        if self.oracle_sharpe >= 1.5:
            return "STRONG_CANDIDATE (Grade A ceiling)"
        if self.oracle_sharpe >= 1.0:
            return "VIABLE (Grade B ceiling)"
        if self.oracle_sharpe >= 0.5:
            return "MARGINAL (Grade C ceiling)"
        if self.oracle_sharpe >= 0.3:
            return "WEAK (Grade D ceiling)"
        return "NO_EDGE (retire or conjugate)"


def run_validation():
    """Execute Oracle validation against Vault data."""
    logger.info("=" * 70)
    logger.info("HYPOTHESIS VALIDATION RUNNER — Oracle Alpha Ceiling")
    logger.info("=" * 70)

    # Connect to Vault
    store = TimescaleDataStore()
    labeler = TripleBarrierAdapter()
    oracle = OracleBacktester(store=store, labeler=labeler)

    # Test tickers — representative universe
    # Diversified across sectors to avoid single-stock bias
    test_tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
                    "JPM", "XOM", "UNH", "JNJ", "PG",
                    "SPY", "QQQ"]

    # Geometries for both departments
    spec_geometry = ORACLE_GEOMETRY[InvestmentCategory.SPECULATIVE_SPRING]
    qual_geometry = ORACLE_GEOMETRY[InvestmentCategory.QUALITY_VALUE]

    # Signal adapters that work with PURE OHLCV (no external context needed)
    pure_ohlcv_signals = [
        (KalmanSignalAdapter(), "HYPOTHESIS", "wyckoff-kalman", ""),
        (MeanReversionSignalAdapter(), "HYPOTHESIS", "mean-reversion", ""),
        (VolumeQualitySignalAdapter(), "HYPOTHESIS", "volume-quality", ""),
        (RSISignalAdapter(), "HYPOTHESIS", "rsi-cardwell", ""),
        (PatternSignalAdapter(), "HYPOTHESIS", "pattern-recognition", ""),
    ]

    # Signals that REQUIRE external context — tested with empty context
    context_dependent_signals = [
        (BOSSignalAdapter(), "HYPOTHESIS", "smc-structure",
         "⚠️ LIMITED: Requires SMC structure context (smc_structure dict). "
         "Tested with empty context — 0 entries expected. "
         "Full validation requires SMC adapter pre-computation."),
    ]

    all_signals = pure_ohlcv_signals + context_dependent_signals
    all_results: list[HypothesisResult] = []

    for ticker in test_tickers:
        logger.info(f"\n{'─' * 50}")
        logger.info(f"TICKER: {ticker}")
        logger.info(f"{'─' * 50}")

        # Load data to check availability
        ohlc = store.load_bars(ticker, "1d")
        bars_available = len(ohlc) if not ohlc.empty else 0
        logger.info(f"  Vault data: {bars_available} daily bars")

        if bars_available < 100:
            logger.warning(f"  ⚠️ Insufficient data for {ticker} ({bars_available} bars). Skipping.")
            for sig, status, indicator_id, limitation in all_signals:
                all_results.append(HypothesisResult(
                    signal_name=sig.name,
                    ticker=ticker,
                    category="SPECULATIVE",
                    evidence_status=status,
                    data_limitation=f"Only {bars_available} bars available (need ≥100)",
                    validated_at=datetime.now(UTC).isoformat(),
                    bars_available=bars_available,
                ))
            continue

        for sig, status, indicator_id, limitation in all_signals:
            # Run SPECULATIVE geometry
            try:
                result = oracle.run_signal(
                    ticker=ticker,
                    tf="1d",
                    signal=sig,
                    geometry=spec_geometry,
                    context={"ticker": ticker},
                )

                hr = HypothesisResult(
                    signal_name=sig.name,
                    ticker=ticker,
                    category="SPECULATIVE",
                    evidence_status=status,
                    oracle_sharpe=result.ceiling_sharpe,
                    win_rate=result.win_rate,
                    profit_factor=result.profit_factor,
                    n_entries=result.n_entries,
                    avg_return_pct=result.avg_return_pct,
                    max_drawdown_pct=result.max_drawdown_pct,
                    avg_bars_held=result.avg_bars_held,
                    grade=SignalRanking(
                        name=sig.name,
                        ceiling_sharpe=result.ceiling_sharpe,
                    ).grade,
                    data_limitation=limitation,
                    validated_at=datetime.now(UTC).isoformat(),
                    bars_available=bars_available,
                )
                all_results.append(hr)

            except Exception as e:
                logger.error(f"  ❌ {sig.name}/{ticker} failed: {e}")
                all_results.append(HypothesisResult(
                    signal_name=sig.name,
                    ticker=ticker,
                    category="SPECULATIVE",
                    evidence_status=status,
                    data_limitation=f"Error: {str(e)[:100]}",
                    validated_at=datetime.now(UTC).isoformat(),
                    bars_available=bars_available,
                ))

    # ── Generate Report ──────────────────────────────────────
    logger.info("\n" + "=" * 70)
    logger.info("VALIDATION REPORT")
    logger.info("=" * 70)

    # Aggregate by signal
    signal_names = sorted(set(r.signal_name for r in all_results))
    report_lines = []
    report_lines.append(f"# Hypothesis Validation Report — {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    report_lines.append("")
    report_lines.append("## Methodology")
    report_lines.append("- **Engine**: OracleBacktester with Triple Barrier labeling")
    report_lines.append("- **Data Source**: Vault (Neon PostgreSQL) — `market.ohlcv_bars`")
    report_lines.append(f"- **Test Universe**: {', '.join(test_tickers)}")
    report_lines.append(f"- **Geometry**: SPECULATIVE_SPRING (TP={spec_geometry.profit_mult}×ATR, "
                        f"SL={spec_geometry.loss_mult}×ATR, max_bars={spec_geometry.max_bars})")
    report_lines.append("")
    report_lines.append("## Results by Signal")
    report_lines.append("")

    for sig_name in signal_names:
        sig_results = [r for r in all_results if r.signal_name == sig_name]
        valid_results = [r for r in sig_results if r.n_entries >= 10]

        report_lines.append(f"### `{sig_name}`")

        if not valid_results:
            insufficient = [r for r in sig_results if r.n_entries < 10]
            report_lines.append(f"- **Status**: INSUFFICIENT_DATA across all tickers")
            if insufficient and insufficient[0].data_limitation:
                report_lines.append(f"- **Limitation**: {insufficient[0].data_limitation}")
            report_lines.append("")
            continue

        avg_sharpe = np.mean([r.oracle_sharpe for r in valid_results])
        avg_wr = np.mean([r.win_rate for r in valid_results])
        avg_pf = np.mean([r.profit_factor for r in valid_results])
        total_entries = sum(r.n_entries for r in valid_results)
        tickers_tested = len(valid_results)

        # Determine aggregate grade
        if avg_sharpe >= 1.5:
            agg_grade = "A"
        elif avg_sharpe >= 1.0:
            agg_grade = "B"
        elif avg_sharpe >= 0.5:
            agg_grade = "C"
        elif avg_sharpe >= 0.3:
            agg_grade = "D"
        else:
            agg_grade = "F"

        report_lines.append(f"- **Avg Oracle Sharpe**: {avg_sharpe:.4f} → Grade **{agg_grade}**")
        report_lines.append(f"- **Avg Win Rate**: {avg_wr:.1f}%")
        report_lines.append(f"- **Avg Profit Factor**: {avg_pf:.2f}")
        report_lines.append(f"- **Total Entries**: {total_entries} across {tickers_tested} tickers")
        report_lines.append(f"- **Verdict**: {valid_results[0].verdict()}")

        if valid_results[0].data_limitation:
            report_lines.append(f"- **⚠️ Limitation**: {valid_results[0].data_limitation}")

        # Per-ticker breakdown
        report_lines.append("")
        report_lines.append("| Ticker | Sharpe | WR% | PF | Entries | Grade |")
        report_lines.append("|---|---|---|---|---|---|")
        for r in sorted(sig_results, key=lambda x: x.oracle_sharpe, reverse=True):
            if r.n_entries >= 10:
                report_lines.append(
                    f"| {r.ticker} | {r.oracle_sharpe:.4f} | {r.win_rate:.1f} | "
                    f"{r.profit_factor:.2f} | {r.n_entries} | {r.grade} |"
                )
            else:
                report_lines.append(f"| {r.ticker} | — | — | — | {r.n_entries} | N/A |")
        report_lines.append("")

    # Summary
    report_lines.append("## Summary")
    report_lines.append("")
    report_lines.append("| Signal | Avg Sharpe | Grade | Verdict |")
    report_lines.append("|---|---|---|---|")
    for sig_name in signal_names:
        valid = [r for r in all_results if r.signal_name == sig_name and r.n_entries >= 10]
        if valid:
            avg_s = np.mean([r.oracle_sharpe for r in valid])
            grade = "A" if avg_s >= 1.5 else "B" if avg_s >= 1.0 else "C" if avg_s >= 0.5 else "D" if avg_s >= 0.3 else "F"
            report_lines.append(f"| {sig_name} | {avg_s:.4f} | {grade} | {valid[0].verdict()} |")
        else:
            report_lines.append(f"| {sig_name} | — | — | INSUFFICIENT_DATA |")
    report_lines.append("")

    # Data source annotation
    report_lines.append("## Data Source Annotations")
    report_lines.append("")
    report_lines.append("- ✅ All validation data sourced from **Vault (Neon PostgreSQL)**")
    report_lines.append("- ✅ No simulated or synthetic data used")
    report_lines.append("- ⚠️ Signals requiring external context (SMC, UW Flow) tested with empty context")
    report_lines.append("- ⚠️ This is **Step 1 only** (Oracle Alpha Ceiling). Full validation requires Steps 2-5.")
    report_lines.append("")

    report_text = "\n".join(report_lines)

    # Write report
    report_path = "/root/botero-trade/.agents/knowledge/indicators/_validation_log.md"
    with open(report_path, "w") as f:
        f.write(report_text)

    logger.info(f"\n📄 Report written to: {report_path}")
    logger.info("\n" + report_text)

    # Cleanup
    store.close()
    return all_results


if __name__ == "__main__":
    results = run_validation()
    sys.exit(0)
