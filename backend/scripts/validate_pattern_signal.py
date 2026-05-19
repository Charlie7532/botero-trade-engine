"""
validate_pattern_signal.py — Focused Oracle Validation for PatternSignalAdapter
==================================================================================
Runs OracleCoreBacktester with ONLY PatternSignalAdapter on a small set of
tickers to empirically validate the adapter before universe-wide calibration.

Usage:
    python backend/scripts/validate_pattern_signal.py
    python backend/scripts/validate_pattern_signal.py --ticker COST
    python backend/scripts/validate_pattern_signal.py --all
"""
import sys
import logging
import argparse
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("PatternValidator")

_root = Path("/root/botero-trade")
sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(_root / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.simulation.infrastructure.triple_barrier_adapter import TripleBarrierAdapter
from backend.modules.simulation.infrastructure.neon_passport_store import NeonPassportStore
from backend.modules.simulation.application.use_cases.oracle_core import OracleCoreBacktester
from backend.modules.simulation.infrastructure.signal_adapters import PatternSignalAdapter

# Validation set: 5 tickers across sectors (quick validation, ~2 min)
VALIDATION_TICKERS = ["COST", "AAPL", "JPM", "XOM", "NVDA"]


def main():
    parser = argparse.ArgumentParser(description="Validate PatternSignalAdapter via Oracle Core")
    parser.add_argument("--ticker", type=str, help="Single ticker to validate")
    parser.add_argument("--all", action="store_true", help="Run full 30-ticker universe")
    args = parser.parse_args()

    store = TimescaleDataStore()
    labeler = TripleBarrierAdapter()
    passport_store = NeonPassportStore()
    passport_store.ensure_schema()

    oracle = OracleCoreBacktester(store, labeler, passport_store)
    pattern_signal = [PatternSignalAdapter()]

    if args.ticker:
        tickers = [args.ticker.upper()]
    elif args.all:
        from backend.scripts.calibrate_passports import QUALITY_TICKERS
        tickers = QUALITY_TICKERS
    else:
        tickers = VALIDATION_TICKERS

    logger.info("=" * 70)
    logger.info("PATTERN SIGNAL ADAPTER — FOCUSED ORACLE VALIDATION")
    logger.info(f"Tickers: {tickers}")
    logger.info(f"Geometry: QUALITY_THESIS (no stop, 120-bar horizon)")
    logger.info(f"Signal: PatternSignalAdapter (dual-layer: micro+macro)")
    logger.info("=" * 70)

    results = {}
    for ticker in tickers:
        logger.info(f"\n{'─' * 50}")
        logger.info(f"Validating: {ticker}")
        logger.info(f"{'─' * 50}")

        try:
            passports = oracle.run_and_passport(ticker, "1d", pattern_signal)
            if passports:
                p = passports[0]
                results[ticker] = p
                logger.info(
                    f"  ✓ {ticker}: Grade={p.grade} "
                    f"Sharpe={p.ceiling_sharpe:.3f} WR={p.win_rate:.1f}% "
                    f"PF={p.profit_factor:.2f} N={p.n_entries} "
                    f"Reliability={p.reliability_score:.3f} "
                    f"Survival={p.thesis_survival_rate:.0f}%"
                )
                if p.wr_by_vol_regime:
                    logger.info(f"    Vol regimes: {p.wr_by_vol_regime}")
            else:
                logger.warning(f"  ✗ {ticker}: No passport (insufficient entries or data)")
        except Exception as e:
            logger.error(f"  ✗ {ticker}: FAILED — {e}")

    # ── Summary ──
    print("\n" + "=" * 70)
    print("PATTERN SIGNAL VALIDATION SUMMARY")
    print("=" * 70)
    print(f"{'Ticker':<8} {'Grade':>5} {'Sharpe':>8} {'WR%':>6} {'PF':>6} {'N':>4} {'Reliab':>7} {'Surv%':>6}")
    print("-" * 55)

    for ticker, p in sorted(results.items(), key=lambda x: x[1].ceiling_sharpe, reverse=True):
        print(
            f"{ticker:<8} {p.grade:>5} {p.ceiling_sharpe:>8.3f} {p.win_rate:>6.1f} "
            f"{p.profit_factor:>6.2f} {p.n_entries:>4} {p.reliability_score:>7.3f} "
            f"{p.thesis_survival_rate:>6.0f}"
        )

    viable = sum(1 for p in results.values() if p.viable)
    grade_a = sum(1 for p in results.values() if p.grade == "A")
    print("-" * 55)
    print(f"Tested: {len(tickers)} | Results: {len(results)} | Viable: {viable} | Grade A: {grade_a}")
    print("=" * 70)

    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
