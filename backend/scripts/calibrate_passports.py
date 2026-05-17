"""
calibrate_passports.py — Quality Universe Passport Calibration
================================================================
Creates the Neon schema (if needed) and runs the dual-Oracle calibration
for the Quality universe: OracleCoreBacktester + OracleSwingBacktester.

Produces engine.signal_passports rows with per-regime, per-fear-level,
per-sigma-band breakdowns + Walk-Forward OOS validation for Swing.

Usage:
    # Full Quality universe (30 tickers × 2 departments × ~5 signals each)
    python backend/scripts/calibrate_passports.py

    # Single ticker (on-demand recalibration)
    python backend/scripts/calibrate_passports.py --ticker COST

    # Core only / Swing only
    python backend/scripts/calibrate_passports.py --core-only
    python backend/scripts/calibrate_passports.py --swing-only

Recommended frequency: weekly (after market close Friday).
Estimated runtime: ~2-5 min per ticker depending on Vault data size.
"""
import sys
import logging
import argparse
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("PassportCalibrator")

_root = Path("/root/botero-trade")
sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(_root / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.simulation.infrastructure.triple_barrier_adapter import TripleBarrierAdapter
from backend.modules.simulation.infrastructure.neon_passport_store import NeonPassportStore
from backend.modules.simulation.application.use_cases.signal_passport_generator import (
    SignalPassportGenerator,
)


# ── QUALITY UNIVERSE (same as populate_ml_lake.py — single source of truth) ──
QUALITY_TICKERS = [
    # Original 15
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'BRK-B',
    'LLY', 'JPM', 'UNH', 'V', 'XOM', 'JNJ', 'MA', 'COST',
    # Expansion 15 — Vault-verified, QGARP-quality tollkeepers
    'ABBV', 'ACN', 'ADP', 'HD', 'HON', 'IBM', 'INTU',
    'MCD', 'MRK', 'NEE', 'PEP', 'PG', 'TMO', 'TXN', 'WMT',
]


def main():
    parser = argparse.ArgumentParser(description="Calibrate Signal Reliability Passports")
    parser.add_argument("--ticker", type=str, help="Single ticker to calibrate (skip universe)")
    parser.add_argument("--core-only", action="store_true", help="Run Core Oracle only")
    parser.add_argument("--swing-only", action="store_true", help="Run Swing Oracle only")
    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("SIGNAL PASSPORT CALIBRATION")
    logger.info("=" * 70)

    # ── Step 1: Create infrastructure ──
    store = TimescaleDataStore()
    labeler = TripleBarrierAdapter()
    passport_store = NeonPassportStore()

    logger.info("Step 1: Ensuring Neon schema (engine.signal_passports)...")
    passport_store.ensure_schema()
    logger.info("Schema ready.")

    # ── Step 2: Build generator ──
    generator = SignalPassportGenerator(
        store=store,
        labeler=labeler,
        passport_store=passport_store,
        ml_store=store,  # TimescaleDataStore also implements MLDataPort
    )

    # ── Step 3: Determine scope ──
    run_core = not args.swing_only
    run_swing = not args.core_only

    if args.ticker:
        tickers = [args.ticker.upper()]
        logger.info(f"Single ticker mode: {tickers[0]}")
    else:
        tickers = QUALITY_TICKERS
        logger.info(f"Full universe mode: {len(tickers)} tickers")

    if run_core and run_swing:
        logger.info("Departments: QUALITY_CORE + QUALITY_SWING")
    elif run_core:
        logger.info("Departments: QUALITY_CORE only")
    elif run_swing:
        logger.info("Departments: QUALITY_SWING only")

    # ── Step 4: Calibrate ──
    logger.info(f"\nStarting calibration...")
    report = generator.calibrate_quality_universe(
        tickers=tickers,
        tf="1d",
        run_core=run_core,
        run_swing=run_swing,
    )

    # ── Step 5: Print report ──
    print(report.summary())

    # ── Summary stats ──
    total_passports = len(report.core_passports) + len(report.swing_passports)
    total_viable = report.core_viable_count + report.swing_viable_count
    total_a = report.core_grade_a_count + report.swing_grade_a_count

    logger.info(f"\nCalibration complete:")
    logger.info(f"  Total passports: {total_passports}")
    logger.info(f"  Viable: {total_viable}")
    logger.info(f"  Grade A: {total_a}")
    logger.info(f"  Errors: {len(report.errors)}")

    if report.errors:
        logger.warning(f"\nErrors encountered ({len(report.errors)}):")
        for e in report.errors:
            logger.warning(f"  {e}")

    return 0 if not report.errors else 1


if __name__ == "__main__":
    sys.exit(main())
