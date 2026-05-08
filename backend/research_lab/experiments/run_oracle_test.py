"""
Quaternion Oracle Test — Measure Alpha Ceiling (Phase 1)
===========================================================
One-shot script to measure the pure 4D quaternion's predictive
power on real data from Neon, using the existing Oracle Backtest
infrastructure with Triple Barrier labeling.

Usage:
    PYTHONPATH=. backend/.venv/bin/python backend/research_lab/experiments/run_oracle_test.py
    PYTHONPATH=. backend/.venv/bin/python backend/research_lab/experiments/run_oracle_test.py --ticker AAPL
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger("QuaternionOracle")


def run_oracle_test(ticker: str = "SPY", timeframe: str = "1d") -> None:
    """Run Oracle Alpha Ceiling measurement for the Quaternion signal."""
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    from backend.modules.simulation.application.use_cases.oracle_backtest import (
        OracleBacktester, OracleResult,
    )
    from backend.modules.simulation.infrastructure.triple_barrier_adapter import TripleBarrierAdapter
    from backend.modules.simulation.domain.entities.strategy_profile import (
        InvestmentCategory, ORACLE_GEOMETRY,
    )
    from backend.research_lab.experiments.quaternion_signal import QuaternionSignalAdapter
    from backend.research_lab.experiments.experiment_registry import ExperimentRegistry

    store = TimescaleDataStore()
    labeler = TripleBarrierAdapter()
    oracle = OracleBacktester(store, labeler)
    registry = ExperimentRegistry()

    logger.info(f"═══ Quaternion Oracle Test: {ticker}/{timeframe} ═══")

    # Test with two representative geometries (one per department)
    test_categories = [
        InvestmentCategory.SPECULATIVE_SPRING,   # Speculative: tighter, faster
        InvestmentCategory.QUALITY_VALUE,         # Quality: wider, more patient
    ]
    for category in test_categories:
        geometry = ORACLE_GEOMETRY[category]
        signal = QuaternionSignalAdapter(include_predictions=False)

        logger.info(f"\n── {category.value} geometry: profit={geometry.profit_mult}x, "
                     f"loss={geometry.loss_mult}x, max_bars={geometry.max_bars} ──")

        result: OracleResult = oracle.run_signal(
            ticker, timeframe, signal, geometry,
        )

        # Log results
        logger.info(f"  Entries:       {result.n_entries}")
        logger.info(f"  Win Rate:      {result.win_rate:.1f}%")
        logger.info(f"  Avg Return:    {result.avg_return_pct:.2f}%")
        logger.info(f"  Profit Factor: {result.profit_factor:.2f}")
        logger.info(f"  Ceiling Sharpe:{result.ceiling_sharpe:.2f}")
        logger.info(f"  Max Drawdown:  {result.max_drawdown_pct:.2f}%")
        logger.info(f"  Avg Bars Held: {result.avg_bars_held:.1f}")

        # Verdict
        if result.ceiling_sharpe >= 0.5:
            verdict = "🟢 PROMOTED — Alpha detected, proceed to Phase 2"
        elif result.ceiling_sharpe >= 0.3:
            verdict = "🟡 OBSERVATION — Marginal alpha, tune parameters"
        else:
            verdict = "🔴 REJECTED — Insufficient alpha, pivot approach"

        logger.info(f"  Verdict: {verdict}")

        # Record in registry
        registry.record(
            description=f"Oracle {category.value} {ticker}",
            dimensions_used=["Q_w", "Q_x", "Q_y", "Q_z",
                             "Q_norm", "Q_rotation_angle", "Q_money_flow", "Q_divergence"],
            dimensions_excluded=[],
            ticker=ticker, timeframe=timeframe,
            n_samples=result.n_entries,
            accuracy=result.win_rate / 100,
            sharpe=result.ceiling_sharpe,
            profit_factor=result.profit_factor,
            win_rate=result.win_rate,
            max_drawdown=result.max_drawdown_pct,
            n_trades=result.n_entries,
        )

    logger.info("\n" + registry.summary_table())
    store.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Quaternion Oracle Alpha Ceiling")
    parser.add_argument("--ticker", default="SPY", help="Ticker to test")
    parser.add_argument("--tf", default="1d", help="Timeframe")
    args = parser.parse_args()

    run_oracle_test(ticker=args.ticker, timeframe=args.tf)
