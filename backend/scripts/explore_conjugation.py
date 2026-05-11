"""
Conjugation Explorer Script
==============================
Tests pairwise combinations of signals to discover valid conjugations.
"""
import logging
import sys
from datetime import datetime, UTC
from pathlib import Path
import warnings

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
warnings.filterwarnings('ignore')

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.simulation.infrastructure.triple_barrier_adapter import TripleBarrierAdapter
from backend.modules.simulation.application.use_cases.oracle_backtest import OracleBacktester
from backend.modules.simulation.domain.entities.strategy_profile import InvestmentCategory, ORACLE_GEOMETRY
from backend.modules.simulation.infrastructure.signal_adapters import (
    KalmanSignalAdapter, MeanReversionSignalAdapter, VolumeQualitySignalAdapter,
    RSISignalAdapter, PatternSignalAdapter, BOSSignalAdapter
)
from backend.modules.simulation.application.use_cases.explore_conjugations import ConjugationExplorer

logging.basicConfig(level=logging.WARNING, format='%(message)s')
logging.getLogger('backend.modules.simulation.application.use_cases.oracle_backtest').setLevel(logging.WARNING)

def run_exploration():
    print("=" * 60)
    print("CONJUGATION EXPLORER")
    print("=" * 60)
    
    store = TimescaleDataStore()
    labeler = TripleBarrierAdapter()
    oracle = OracleBacktester(store=store, labeler=labeler)
    explorer = ConjugationExplorer(oracle)
    geo = ORACLE_GEOMETRY[InvestmentCategory.SPECULATIVE_SPRING]
    
    signals = [
        RSISignalAdapter(),
        KalmanSignalAdapter(),
        BOSSignalAdapter()
    ]
    
    tickers = ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "SPY"]
    
    # We'll test:
    # 1. RSI (B) + Kalman (C)
    # 2. RSI (B) + BOS (F - REPOSTULATION test)
    
    pairs = [
        (RSISignalAdapter(), KalmanSignalAdapter()),
        (RSISignalAdapter(), BOSSignalAdapter())
    ]
    
    for sig_a, sig_b in pairs:
        print(f"\\nExploring Pair: {sig_a.name} + {sig_b.name}")
        print("-" * 60)
        
        for ticker in tickers:
            try:
                res = explorer.explore_pair(
                    ticker=ticker,
                    tf="1d",
                    sig_a=sig_a,
                    sig_b=sig_b,
                    geometry=geo,
                    context={"ticker": ticker}
                )
                print(f"{ticker:6s} | Base: {res.baseline_sharpe:.2f} | Comp: {res.composite_sharpe:.2f} | "
                      f"Corr: {res.correlation:5.2f} | N: {res.composite_entries:3d} | "
                      f"Verdict: {res.verdict()}")
            except Exception as e:
                print(f"{ticker:6s} | ERROR: {e}")

    store.close()

if __name__ == "__main__":
    run_exploration()
