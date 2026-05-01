"""
Retrain Trigger — Automated Decay Detection
===============================================
Monitors signal precision over time and triggers recalibration
when performance degrades below acceptable thresholds.
"""
import logging
from datetime import datetime, UTC
from typing import Optional

from backend.modules.simulation.application.use_cases.analyze_indicators import (
    IndicatorAnalyzer, QualityReport,
)
from backend.modules.simulation.domain.ports.historical_data_port import HistoricalDataPort

logger = logging.getLogger(__name__)


class RetrainTrigger:
    """
    Monitors signal precision and triggers recalibration.

    Rules for triggering retrain:
    1. Any signal precision drops below 35% (with ≥10 appearances)
    2. Overall win rate drops below 40%
    3. Profile is older than 90 days
    4. Signal lift turns negative (signal is hurting performance)
    """

    # Configurable thresholds
    MIN_PRECISION = 0.35
    MIN_WIN_RATE = 0.40
    MAX_PROFILE_AGE_DAYS = 90
    MIN_APPEARANCES = 10

    def __init__(self, store: HistoricalDataPort, analyzer: IndicatorAnalyzer):
        self.store = store
        self.analyzer = analyzer

    def check(
        self,
        ticker: str,
        category: str,
    ) -> dict:
        """
        Check if recalibration is needed.

        Returns:
            {
                "needs_retrain": bool,
                "reasons": list[str],
                "signal_quality": QualityReport,
                "profile_age_days": int | None,
            }
        """
        reasons = []

        # 1. Quality report
        report = self.analyzer.quality_report(ticker=ticker, category=category)

        # 2. Check individual signal precision
        for sig in report.signals:
            if sig.total_appearances >= self.MIN_APPEARANCES:
                if sig.precision < self.MIN_PRECISION:
                    reasons.append(
                        f"Signal '{sig.name}' precision={sig.precision:.1%} "
                        f"< {self.MIN_PRECISION:.0%} ({sig.total_appearances} trades)"
                    )
                if sig.lift < 0:
                    reasons.append(
                        f"Signal '{sig.name}' has negative lift={sig.lift:.2f} "
                        f"(hurting performance)"
                    )

        # 3. Overall win rate
        if report.total_with_outcomes >= 10:
            total_wins = sum(s.correct_predictions for s in report.signals)
            total_trades = sum(s.total_appearances for s in report.signals)
            if total_trades > 0:
                overall_wr = total_wins / total_trades
                if overall_wr < self.MIN_WIN_RATE:
                    reasons.append(
                        f"Overall win rate={overall_wr:.1%} < {self.MIN_WIN_RATE:.0%}"
                    )

        # 4. Profile age
        profile_age = None
        profile = self.store.load_profile(category, ticker)
        if profile:
            cal_date = profile.get("calibrated_at", "")
            if cal_date:
                try:
                    cal_dt = datetime.fromisoformat(cal_date)
                    age = (datetime.now(UTC) - cal_dt).days
                    profile_age = age
                    if age > self.MAX_PROFILE_AGE_DAYS:
                        reasons.append(
                            f"Profile age={age} days > {self.MAX_PROFILE_AGE_DAYS} days"
                        )
                except (ValueError, TypeError):
                    pass

        needs_retrain = len(reasons) > 0

        if needs_retrain:
            logger.warning(
                f"⚠️ RETRAIN NEEDED for {ticker}/{category}: "
                + "; ".join(reasons)
            )
        else:
            logger.info(f"✅ {ticker}/{category}: all signals performing within range")

        return {
            "needs_retrain": needs_retrain,
            "reasons": reasons,
            "signal_quality": report,
            "profile_age_days": profile_age,
        }
