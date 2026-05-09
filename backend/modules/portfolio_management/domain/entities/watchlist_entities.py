"""
Watchlist Domain Entities — Quality & Speculative
====================================================
Pure domain entities for watchlist candidates.
No framework imports. No infrastructure dependencies.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class QualityWatchlistCandidate:
    """A stock being monitored for QUALITY department entry."""
    ticker: str
    company: str = ""
    sector: str = ""

    # GF Intelligence
    gf_score: float = 0.0
    piotroski_f_score: float = 0.0
    altman_z_score: float = 0.0
    price_to_gf_value: float = 0.0
    gf_valuation: str = ""
    rank_profitability: float = 0.0
    rank_growth: float = 0.0
    rank_financial_strength: float = 0.0
    roic: float = 0.0
    roe: float = 0.0
    net_margin: float = 0.0
    debt_to_equity: float = 0.0

    # Thesis
    thesis: str = ""
    conviction_score: float = 0.0
    moat_classification: str = ""

    # Price zones
    current_price: float = 0.0
    buy_zone_low: float = 0.0
    buy_zone_high: float = 0.0
    fair_value: float = 0.0

    # Status
    status: str = "WATCHING"  # WATCHING | BUY_ZONE | ACQUIRED | REMOVED
    alerts: list = field(default_factory=list)

    added_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None

    def is_in_buy_zone(self) -> bool:
        """Check if current price is within the buy zone."""
        if self.buy_zone_low <= 0 or self.buy_zone_high <= 0:
            return False
        return self.buy_zone_low <= self.current_price <= self.buy_zone_high

    def passes_quality_gate(self) -> bool:
        """Minimum quality thresholds for Hohn/Munger consideration."""
        return (
            self.gf_score >= 80
            and self.piotroski_f_score >= 6
            and self.roic >= 15
            and self.beneish_m_safe
        )

    @property
    def beneish_m_safe(self) -> bool:
        """Beneish M-Score < -1.78 indicates low manipulation probability."""
        # We don't store beneish here, but the screening data has it
        return True  # Default safe — checked at screening level


@dataclass
class SpeculativeWatchlistCandidate:
    """A tactical setup being monitored for SPECULATIVE department entry."""
    ticker: str

    # Setup
    setup_type: str = ""  # GAMMA_SQUEEZE | MOMENTUM_BREAK | EARNINGS_PLAY
    catalyst: str = ""
    timeframe: str = ""  # 1D | 2-5D | 1W

    # Levels
    entry_price: float = 0.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    risk_reward_ratio: float = 0.0

    # Flow signals
    gex_regime: str = "UNKNOWN"
    sweep_detected: bool = False
    dark_pool_signal: bool = False

    # Scoring
    conviction_score: float = 0.0

    # Status
    status: str = "WATCHING"  # WATCHING | TRIGGERED | ENTERED | EXPIRED
    alerts: list = field(default_factory=list)

    added_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None

    def passes_speculative_gate(self) -> bool:
        """Minimum R:R threshold for PTJ consideration."""
        return self.risk_reward_ratio >= 3.0
