"""
Conjugation Explorer — Hypothesis Rehabilitation & Potentiation
================================================================
Systematically evaluates pairs of signals to discover conjugations
that yield a higher Sharpe ratio than the individual components.

Used to:
1. Potentiate weak signals (Grade C/D) into strong ones (Grade A/B)
2. Rehabilitate DEGRADED signals before retiring them (REPOSTULATED)
"""
import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from backend.modules.simulation.application.use_cases.oracle_backtest import (
    OracleBacktester, OracleResult, SignalRanking
)
from backend.modules.simulation.domain.entities.strategy_profile import (
    OracleGeometry
)
from backend.modules.simulation.domain.ports.signal_port import SignalPort

logger = logging.getLogger(__name__)


@dataclass
class ConjugationResult:
    """Result of evaluating a pair of signals."""
    signal_a: str
    signal_b: str
    ticker: str
    
    composite_sharpe: float
    composite_win_rate: float
    composite_entries: int
    
    baseline_sharpe: float  # Max of (Sharpe A, Sharpe B)
    improvement_pct: float  # (Composite / Baseline - 1) * 100
    
    correlation: float = 0.0 # Signal correlation (overlap)
    grade: str = "F"
    is_valid: bool = False   # True if improvement >= 20% and correlation < 0.8
    reason: str = ""

    def verdict(self) -> str:
        if not self.is_valid:
            return f"REJECTED: {self.reason}"
        return f"CONJUGATED: Grade {self.grade} (+{self.improvement_pct:.1f}% vs baseline)"


class ConjugationExplorer:
    """Explores signal conjugations using the OracleBacktester."""
    
    def __init__(self, oracle: OracleBacktester):
        self.oracle = oracle

    def explore_pair(
        self,
        ticker: str,
        tf: str,
        sig_a: SignalPort,
        sig_b: SignalPort,
        geometry: OracleGeometry,
        context: dict | None = None,
        min_improvement_pct: float = 20.0,
        max_correlation: float = 0.80
    ) -> ConjugationResult:
        """
        Evaluate if sig_a + sig_b creates a valid conjugation.
        """
        # 1. Evaluate individuals to establish baseline
        res_a = self.oracle.run_signal(ticker, tf, sig_a, geometry, context)
        res_b = self.oracle.run_signal(ticker, tf, sig_b, geometry, context)
        
        baseline_sharpe = max(res_a.ceiling_sharpe, res_b.ceiling_sharpe)
        
        # 2. Evaluate correlation (signal overlap)
        # We need the actual signal series to compute correlation
        ohlc = self.oracle.store.load_bars(ticker, tf)
        if ohlc.empty:
             return ConjugationResult(sig_a.name, sig_b.name, ticker, 0, 0, 0, baseline_sharpe, 0, 0, reason="No data")

        series_a = sig_a.generate(ohlc, context)["signal"]
        series_b = sig_b.generate(ohlc, context)["signal"]
        
        # Calculate Pearson correlation of the signals
        correlation = series_a.corr(series_b)
        if pd.isna(correlation):
            correlation = 0.0
            
        if correlation > max_correlation:
             return ConjugationResult(
                 sig_a.name, sig_b.name, ticker, 0, 0, 0, baseline_sharpe, 0, correlation,
                 reason=f"Highly correlated ({correlation:.2f} > {max_correlation})"
             )

        # 3. Evaluate Composite (Equal weight)
        weights = {sig_a.name: 0.5, sig_b.name: 0.5}
        # Threshold 0.5 means BOTH signals must be active if they output 1.0
        # If they output 1.0 and 0.0, sum is 0.5. To require BOTH, threshold should be > 0.5 (e.g., 0.99)
        # We want AND logic (both agree), so threshold = 0.99
        res_comp = self.oracle.run_composite(
            ticker=ticker,
            tf=tf,
            signals=[sig_a, sig_b],
            weights=weights,
            threshold=0.99,  # Require near-unanimity for equal weights
            geometry=geometry,
            context=context
        )

        # 4. Calculate improvement
        if baseline_sharpe <= 0:
            # If both are negative, any positive composite is infinite improvement
            improvement = 100.0 if res_comp.ceiling_sharpe > 0 else 0.0
        else:
            improvement = ((res_comp.ceiling_sharpe / baseline_sharpe) - 1.0) * 100

        grade = SignalRanking(name="comp", ceiling_sharpe=res_comp.ceiling_sharpe).grade

        is_valid = False
        reason = "Improvement too small"
        
        if res_comp.n_entries < 10:
            reason = "Insufficient composite entries"
        elif res_comp.ceiling_sharpe <= 0:
            reason = "Negative composite Sharpe"
        elif improvement >= min_improvement_pct:
            is_valid = True
            reason = "Valid"

        return ConjugationResult(
            signal_a=sig_a.name,
            signal_b=sig_b.name,
            ticker=ticker,
            composite_sharpe=res_comp.ceiling_sharpe,
            composite_win_rate=res_comp.win_rate,
            composite_entries=res_comp.n_entries,
            baseline_sharpe=baseline_sharpe,
            improvement_pct=improvement,
            correlation=correlation,
            grade=grade,
            is_valid=is_valid,
            reason=reason
        )
