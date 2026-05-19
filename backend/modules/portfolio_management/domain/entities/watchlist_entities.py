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

    # Keyratios deep fields (from /keyratios endpoint)
    wacc: float = 0.0
    operating_margin: float = 0.0
    operating_margin_5y_med: float = 0.0
    fcf_margin: float = 0.0
    fcf_margin_5y_med: float = 0.0
    beneish_m_score: float = -999.0  # Default safe (< -1.78)

    # Forward-Looking Estimate Fields (yfinance earnings_estimate + eps_trend)
    eps_estimate_current_q: float = 0.0     # Avg EPS estimate for current quarter
    eps_estimate_next_y: float = 0.0        # Avg EPS estimate for next year
    eps_growth_estimate: float = 0.0        # YoY EPS growth expected (current year)
    revenue_growth_estimate: float = 0.0    # YoY revenue growth expected

    # Revision Momentum — the derivative signal (eps_trend current vs 30d/90d ago)
    eps_revision_pct_30d: float = 0.0       # % change in EPS estimate vs 30 days ago
    eps_revision_pct_90d: float = 0.0       # % change in EPS estimate vs 90 days ago
    eps_revisions_up_30d: int = 0           # Count of upward revisions in 30 days
    eps_revisions_down_30d: int = 0         # Count of downward revisions in 30 days
    num_analysts: int = 0                   # Number of analysts covering

    # Credibility Gate (Munger "Ver Para Creer" — cross-validated trust level)
    analyst_credibility_score: float = 50.0  # 0-100, from post-hoc accuracy tracking
    credibility_gate: str = "MODERATE"       # LOW | MODERATE | HIGH

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
        if self.beneish_m_score <= -999:
            return True  # No data available — assume safe
        return self.beneish_m_score < -1.78

    @property
    def roic_wacc_spread(self) -> float:
        """Value creation spread: ROIC - WACC."""
        return self.roic - self.wacc if self.wacc > 0 else self.roic

    @property
    def moat_stable(self) -> bool:
        """Moat stability: operating margin not wildly expanding (PLTR trap)."""
        if self.operating_margin_5y_med <= 0:
            return True  # No 5Y data
        ratio = self.operating_margin / self.operating_margin_5y_med if self.operating_margin_5y_med > 0 else 1
        return ratio < 3.0  # If TTM is 3x the 5Y median, flag as unstable


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
