"""
Helmer Protocol Domain Entities
================================
Data structures for the Helmer Protocol: financial snapshots, growth profiles,
operating KPIs, segment breakdowns, warning signals, and full QGARP analysis.

These are pure value objects — no I/O, no business logic.
"""
from dataclasses import dataclass, field


@dataclass
class FinancialSnapshot:
    """Income, Balance, Cash Flow snapshot."""
    ticker: str
    period: str
    revenue: float = 0.0
    net_income: float = 0.0
    fcf: float = 0.0
    total_assets: float = 0.0
    total_liabilities: float = 0.0
    raw_data: dict = field(default_factory=dict)


@dataclass
class GrowthProfile:
    """CAGR growth rates for 1/3/5/10 years."""
    ticker: str
    revenue_cagr: dict = field(default_factory=dict)
    eps_cagr: dict = field(default_factory=dict)
    fcf_cagr: dict = field(default_factory=dict)
    raw_data: dict = field(default_factory=dict)


@dataclass
class OperatingKPIs:
    """SaaS metrics like ARPU, NRR, RPO."""
    ticker: str
    kpis: dict = field(default_factory=dict)
    raw_data: dict = field(default_factory=dict)


@dataclass
class SegmentBreakdown:
    """Revenue decomposition by business line and geography."""
    ticker: str
    business_segments: dict = field(default_factory=dict)
    geographic_segments: dict = field(default_factory=dict)
    raw_data: dict = field(default_factory=dict)


@dataclass
class WarningSignals:
    """GuruFocus good signs + warning signs (from get_stock_summary → company_data)."""
    ticker: str
    num_good_signs: int = 0
    num_warnings_medium: int = 0
    num_warnings_severe: int = 0
    good_signs: list = field(default_factory=list)
    warning_signs: list = field(default_factory=list)
    net_signal_score: float = 0.0
    raw_data: dict = field(default_factory=dict)
