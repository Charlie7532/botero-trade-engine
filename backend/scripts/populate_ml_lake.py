"""
populate_ml_lake.py — Corrected ML Data Lake Population (v2)
==============================================================
Post-audit corrections:
  #1: Includes RegressionChannelAdapter (Sharpe 1.326, orthogonal to RSI)
  #2: Dual geometry for Quality: VALUE (3:1 stop) + THESIS (no stop, 120 bars)
  #3: Features include J8-J11 (VWAP, ChannelSigma, VPShape, SlopeConjugation)
  #4: Forensic fields (MAE, MFE, post-exit, sweep) persisted via updated schema
  #5: BOS excluded — only signals with viable Oracle Sharpe
"""
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("MLDataPopulator")

_root = Path("/root/botero-trade")
sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(_root / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.simulation.infrastructure.triple_barrier_adapter import TripleBarrierAdapter
from backend.modules.simulation.infrastructure.signal_adapters import (
    KalmanSignalAdapter,
    VolumeQualitySignalAdapter,
    RSISignalAdapter,
    PatternSignalAdapter,
    RegressionChannelAdapter,
)
from backend.modules.simulation.application.use_cases.oracle_backtest import OracleBacktester
from backend.modules.simulation.domain.entities.strategy_profile import InvestmentCategory, ORACLE_GEOMETRY


# ── VIABLE SIGNALS ONLY (Oracle Sharpe >= 0.3, BOS excluded per audit) ──
def create_viable_signals():
    """Only signals that have demonstrated empirical viability."""
    return [
        KalmanSignalAdapter(),
        VolumeQualitySignalAdapter(),
        RSISignalAdapter(),
        PatternSignalAdapter(),
        RegressionChannelAdapter(),  # v2: Sharpe 1.326 (THESIS), orthogonal to RSI
        # BOSSignalAdapter EXCLUDED: 0% WR, Sharpe -10 to -26 consistently
        # MeanReversionSignalAdapter EXCLUDED: 0 entries on 5m timeframe
        # FlowSignalAdapter EXCLUDED: requires UW context not available in backtest
    ]


# ── DEPARTMENTAL WATCHLISTS ──
QUALITY_TICKERS = [
    # Original 15
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'BRK-B',
    'LLY', 'JPM', 'UNH', 'V', 'XOM', 'JNJ', 'MA', 'COST',
    # Expansion 15 — Vault-verified (1,264 bars each), QGARP-quality tollkeepers
    'ABBV', 'ACN', 'ADP', 'HD', 'HON', 'IBM', 'INTU',
    'MCD', 'MRK', 'NEE', 'PEP', 'PG', 'TMO', 'TXN', 'WMT',
]

SPECULATIVE_TICKERS = [
    'TSLA', 'AMD', 'AVGO', 'NFLX', 'CRM',
    'QCOM', 'UBER', 'NOW', 'ISRG', 'AXP',
]


def run():
    logger.info("=" * 70)
    logger.info("ML DATA LAKE POPULATION v2 — Post-Audit (J8-J11 + Forensics + RC)")
    logger.info("=" * 70)

    store = TimescaleDataStore()
    labeler = TripleBarrierAdapter()
    oracle = OracleBacktester(store=store, labeler=labeler, ml_store=store)
    signals = create_viable_signals()

    total_entries = 0

    # ── DEPARTMENT 1: SPECULATIVE (5m, SPECULATIVE_SPRING geometry) ──
    spec_geometry = ORACLE_GEOMETRY[InvestmentCategory.SPECULATIVE_SPRING]
    logger.info(f"\n{'─'*60}")
    logger.info(f"SPECULATIVE DEPARTMENT — 5m — geometry: TP={spec_geometry.profit_mult}×ATR "
                f"SL={spec_geometry.loss_mult}×ATR max_bars={spec_geometry.max_bars}")
    logger.info(f"Tickers: {SPECULATIVE_TICKERS}")
    logger.info(f"Signals: {[s.name for s in signals]}")
    logger.info(f"{'─'*60}")

    for ticker in SPECULATIVE_TICKERS:
        logger.info(f"▶ {ticker} (5m, SPECULATIVE)...")
        for signal in signals:
            try:
                result = oracle.run_signal(ticker, "5m", signal, spec_geometry)
                if result.n_entries > 0:
                    total_entries += result.n_entries
            except Exception as e:
                logger.error(f"  Error {signal.name}/{ticker}: {e}")

    # ── DEPARTMENT 2: QUALITY — Dual Geometry ──
    # Geometry A: QUALITY_VALUE (3:1 stop, 60 bars) — measures mechanical signal quality
    qual_value_geom = ORACLE_GEOMETRY[InvestmentCategory.QUALITY_VALUE]
    # Geometry B: QUALITY_THESIS (no stop, 120 bars) — measures conviction patience
    qual_thesis_geom = ORACLE_GEOMETRY[InvestmentCategory.QUALITY_THESIS]

    for geom_name, geom in [("QUALITY_VALUE", qual_value_geom), ("QUALITY_THESIS", qual_thesis_geom)]:
        logger.info(f"\n{'─'*60}")
        logger.info(f"QUALITY DEPARTMENT — 1d — {geom_name} — TP={geom.profit_mult}×ATR "
                    f"SL={geom.loss_mult}×ATR max_bars={geom.max_bars}")
        logger.info(f"Tickers: {QUALITY_TICKERS}")
        logger.info(f"Signals: {[s.name for s in signals]}")
        logger.info(f"{'─'*60}")

        for ticker in QUALITY_TICKERS:
            logger.info(f"▶ {ticker} (1d, {geom_name})...")
            for signal in signals:
                try:
                    result = oracle.run_signal(ticker, "1d", signal, geom)
                    if result.n_entries > 0:
                        total_entries += result.n_entries
                except Exception as e:
                    logger.error(f"  Error {signal.name}/{ticker}: {e}")

    store.close()
    logger.info(f"\n{'='*70}")
    logger.info(f"🎉 ML Data Lake population v2 complete!")
    logger.info(f"   Total feature/label pairs generated: {total_entries}")
    logger.info(f"   Features: QuantFeatureEngineer (FD, MS, TS, CS, VF, MC, CAL, IM, OV, RG, J1-J11, K)")
    logger.info(f"   Forensics: MAE, MFE, post-exit tracking, sweep detection")
    logger.info(f"   Execution: VAEP (delay=1bar)")
    logger.info(f"   Signals: {[s.name for s in signals]}")
    logger.info(f"   Geometries: SPECULATIVE_SPRING (5m) + QUALITY_VALUE (1d) + QUALITY_THESIS (1d)")
    logger.info(f"{'='*70}")


if __name__ == "__main__":
    run()
