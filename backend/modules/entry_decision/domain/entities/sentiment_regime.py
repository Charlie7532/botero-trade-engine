"""
Sentiment Regime — Domain Entity
=================================
Pure dataclass + IntEnum for the 8-state market sentiment classifier.

Forensic evidence (backtest_fg_deep_forensics.py, 3,843 days, 2011-2026):
- CAPITULATION: Ret=+4.29%, WR=75.9%, N=112 (strongest buy signal)
- COMPLACENCY:  Ret=-0.14%, WR=57.3%, N=211 (ONLY negative regime)
- Evidence Status: FG-H15 CONFIRMED (232% alpha vs raw F&G)

This is NOT the same as flow_intelligence's MarketSentiment.regime (BULL/NEUTRAL/BEAR)
which measures intraday options flow. This measures macro sentiment cycle (daily/weekly).
"""
from dataclasses import dataclass
from enum import IntEnum


class SentimentRegime(IntEnum):
    """8-state market sentiment regime. Ordinal encoding for ML consumption."""
    CAPITULATION = 0    # F&G<20 + VIX>25 + SPY crashed >2%/5d
    STRESS = 1          # F&G<35 + VIX rising + SPY falling
    RECOVERY = 2        # F&G 20-40 + VIX falling + SPY bouncing
    WALL_OF_WORRY = 3   # F&G 30-55 + SPY rising + VIX > 60d avg
    NORMAL_BULL = 4     # Default — no extreme conditions
    COMPLACENCY = 5     # F&G 55-75 + VIX<15 + PCR<0.85
    EUPHORIA = 6        # F&G>75 + VIX<18 + SPY near highs
    DISTRIBUTION = 7    # F&G>65 + VIX rising + PCR rising


SENTIMENT_LABELS = {
    SentimentRegime.CAPITULATION: "CAPITULATION",
    SentimentRegime.STRESS: "STRESS",
    SentimentRegime.RECOVERY: "RECOVERY",
    SentimentRegime.WALL_OF_WORRY: "WALL_OF_WORRY",
    SentimentRegime.NORMAL_BULL: "NORMAL_BULL",
    SentimentRegime.COMPLACENCY: "COMPLACENCY",
    SentimentRegime.EUPHORIA: "EUPHORIA",
    SentimentRegime.DISTRIBUTION: "DISTRIBUTION",
}


@dataclass
class SentimentRegimeState:
    """Snapshot of the current market sentiment regime with observable inputs."""
    regime: SentimentRegime = SentimentRegime.NORMAL_BULL
    urgency: str = "NONE"       # NONE | LOW | HIGH | MAXIMUM
    fg_level: float = 50.0
    vix_level: float = 18.0
    pcr_level: float = 0.92
    spy_mom5d: float = 0.0
    consec_fear_days: int = 0

    @property
    def label(self) -> str:
        return SENTIMENT_LABELS.get(self.regime, "UNKNOWN")

    @property
    def is_actionable_buy(self) -> bool:
        """CAPITULATION or RECOVERY — regimes with positive alpha."""
        return self.regime in (
            SentimentRegime.CAPITULATION,
            SentimentRegime.RECOVERY,
        )

    @property
    def is_warning(self) -> bool:
        """COMPLACENCY or DISTRIBUTION — regimes requiring exposure reduction."""
        return self.regime in (
            SentimentRegime.COMPLACENCY,
            SentimentRegime.DISTRIBUTION,
        )

    @property
    def sizing_modifier(self) -> float:
        """Position sizing multiplier based on regime + urgency.

        Forensic calibration (overlapping-adjusted):
          CAPITULATION day 11+: ×1.75   (WR=73-86%, Ret=+3-4%)
          CAPITULATION day 1-10: ×1.25  (WR=60-68%, immature)
          RECOVERY: ×1.30              (WR=69.4%, confirming reversal)
          COMPLACENCY: ×0.70           (WR=57.3%, only negative regime)
          DISTRIBUTION: ×0.80          (WR=63.3%, smart money hedging)
          Others: ×1.00                (no edge vs base rate)
        """
        if self.regime == SentimentRegime.CAPITULATION:
            if self.urgency == "MAXIMUM":
                return 1.75
            elif self.urgency == "HIGH":
                return 1.75
            else:
                return 1.25
        elif self.regime == SentimentRegime.RECOVERY:
            return 1.30
        elif self.regime == SentimentRegime.COMPLACENCY:
            return 0.70
        elif self.regime == SentimentRegime.DISTRIBUTION:
            return 0.80
        return 1.00
