"""
Oracle Forensic Trainer
=======================
The Seykota Loop for Backtesting. Takes raw OracleResults and extracts
actionable anti-patterns (Forensic Diagnoses) to prevent future losses
and train the memory guard.
"""
import logging
from dataclasses import dataclass

from backend.modules.simulation.application.use_cases.oracle_backtest import OracleResult

logger = logging.getLogger(__name__)

@dataclass
class ForensicDiagnosis:
    diagnosis: str
    description: str
    action: str


class OracleForensicTrainer:
    """Extracts mechanical learning from failed Oracle tests."""
    
    def analyze_failure(self, result: OracleResult) -> ForensicDiagnosis | None:
        """
        Diagnoses why a signal failed (Sharpe < 0.5 or WR < 35%).
        Returns None if the signal was successful.
        """
        if result.ceiling_sharpe >= 0.5 and result.win_rate >= 35.0:
            return None # Not a failure
            
        if result.n_entries < 10:
            return ForensicDiagnosis(
                diagnosis="INSUFFICIENT_DATA",
                description="Too few entries to extract a reliable pattern.",
                action="Increase backtest window or loosen entry criteria."
            )
            
        # Diagnosis 1: IMMEDIATE_PULLBACK
        # High loss rate, and average bars to loss is very short.
        if result.pct_loss_hit > 60.0 and result.avg_bars_to_loss <= 3.0:
            return ForensicDiagnosis(
                diagnosis="IMMEDIATE_PULLBACK",
                description=f"Mechanically doomed: {result.pct_loss_hit}% hit STOP within {result.avg_bars_to_loss} bars. Signal buys at local maximums right before a retest.",
                action="Add to Memory Guard. Never buy exact breakout. Wait for pullback."
            )
            
        # Diagnosis 2: BLEED_OUT
        # Low win rate, but mostly hitting time stop rather than stop loss.
        if result.pct_time_hit > 50.0:
            return ForensicDiagnosis(
                diagnosis="BLEED_OUT",
                description=f"{result.pct_time_hit}% of trades expire via TIME STOP. The signal lacks immediate momentum.",
                action="Require a volatility expansion filter (e.g., ATR breakout) before entry."
            )
            
        # Default Fallback
        return ForensicDiagnosis(
            diagnosis="NEGATIVE_EXPECTANCY",
            description=f"Win rate {result.win_rate}% with PF {result.profit_factor}. Mathematical disadvantage.",
            action="Reject signal or explore conjugations."
        )
