"""Pydantic models for QGARP (Quality Growth at Reasonable Price) analysis."""

# mypy: disable-error-code="prop-decorator"

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, computed_field


class ScreenResult(str, Enum):
    """Screen criterion result."""

    PASS = "PASS"
    FAIL = "FAIL"
    NA = "N/A"


class GateDecision(str, Enum):
    """Final investment gate decision."""

    PROCEED = "PROCEED"
    WATCHLIST = "WATCHLIST"
    DISCARD = "DISCARD"


# --- Section Models ---


class CompanyOverview(BaseModel):
    """Section 1: Company overview."""

    company_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = Field(default=None, description="Market cap in millions")
    currency: str | None = None
    current_price: float | None = None
    high_52week: float | None = None
    low_52week: float | None = None
    description: str | None = Field(default=None, description="1-2 sentence summary")


class ScreenCriterion(BaseModel):
    """A single QGARP screening criterion with pass/fail."""

    name: str
    value: float | None = None
    threshold: str = Field(description="e.g., '>10%' or '<0.5'")
    result: ScreenResult = ScreenResult.NA


class QGARPScreen(BaseModel):
    """Section 2: QGARP screening criteria."""

    roic: ScreenCriterion = Field(
        default_factory=lambda: ScreenCriterion(name="ROIC", threshold=">10%")
    )
    revenue_growth_5y: ScreenCriterion = Field(
        default_factory=lambda: ScreenCriterion(name="Revenue Growth (5yr)", threshold=">10%")
    )
    eps_growth_5y: ScreenCriterion = Field(
        default_factory=lambda: ScreenCriterion(name="EPS Growth (5yr)", threshold=">10%")
    )
    debt_to_equity: ScreenCriterion = Field(
        default_factory=lambda: ScreenCriterion(name="Debt-to-Equity", threshold="<0.5")
    )
    pe_ratio: ScreenCriterion = Field(
        default_factory=lambda: ScreenCriterion(name="P/E Ratio", threshold="<40")
    )

    @computed_field
    @property
    def pass_count(self) -> int:
        """Number of criteria that passed."""
        criteria = [
            self.roic,
            self.revenue_growth_5y,
            self.eps_growth_5y,
            self.debt_to_equity,
            self.pe_ratio,
        ]
        return sum(1 for c in criteria if c.result == ScreenResult.PASS)

    @computed_field
    @property
    def screen_passed(self) -> bool:
        """Whether overall screen passed (>=4/5)."""
        return self.pass_count >= 4


class QualityScores(BaseModel):
    """Section 3: Quality scores from GuruFocus."""

    gf_score: int | None = Field(default=None, ge=0, le=100)
    financial_strength: int | None = Field(default=None, ge=0, le=10)
    profitability_rank: int | None = Field(default=None, ge=0, le=10)
    growth_rank: int | None = Field(default=None, ge=0, le=10)
    piotroski_score: int | None = Field(default=None, ge=0, le=9)
    altman_z_score: float | None = None

    @computed_field
    @property
    def altman_status(self) -> str:
        """Altman Z-Score interpretation."""
        if self.altman_z_score is None:
            return "N/A"
        if self.altman_z_score > 2.99:
            return "Safe"
        if self.altman_z_score >= 1.81:
            return "Grey Zone"
        return "Distress"

    @computed_field
    @property
    def quality_assessment(self) -> str:
        """Overall quality assessment."""
        if self.gf_score is None:
            return "Unknown"
        if self.gf_score >= 80:
            return "Strong"
        if self.gf_score >= 60:
            return "Moderate"
        return "Weak"


class FinancialStrength(BaseModel):
    """Section 4: Financial strength and risk analysis."""

    # Balance sheet health
    debt_to_equity: float | None = None
    debt_to_ebitda: float | None = None
    interest_coverage: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    cash_ratio: float | None = None

    # Red flags
    high_debt_flag: bool = False  # D/E > 0.8
    low_coverage_flag: bool = False  # Interest coverage < 2x

    @computed_field
    @property
    def verdict(self) -> str:
        """Financial strength verdict."""
        if self.high_debt_flag or self.low_coverage_flag:
            return "FAIL"
        if self.debt_to_equity is not None and self.debt_to_equity > 0.5:
            return "PASS WITH CAUTION"
        return "PASS"


class GrowthMetric(BaseModel):
    """A single growth metric across time periods."""

    name: str
    year_1: float | None = None
    year_3: float | None = None
    year_5: float | None = None
    year_10: float | None = None

    @computed_field
    @property
    def consistent_above_10(self) -> bool:
        """Whether growth is consistently above 10% across available periods."""
        values = [v for v in [self.year_1, self.year_3, self.year_5, self.year_10] if v is not None]
        if not values:
            return False
        return all(v > 10 for v in values)


class BigFourGrowth(BaseModel):
    """Section 5: Rule #1 Big Four growth analysis."""

    revenue: GrowthMetric = Field(default_factory=lambda: GrowthMetric(name="Revenue"))
    eps: GrowthMetric = Field(default_factory=lambda: GrowthMetric(name="EPS"))
    book_value: GrowthMetric = Field(default_factory=lambda: GrowthMetric(name="Book Value/Share"))
    fcf: GrowthMetric = Field(default_factory=lambda: GrowthMetric(name="FCF"))

    @computed_field
    @property
    def consistent_count(self) -> int:
        """Number of Big Four with consistent >10% growth."""
        return sum(
            1 for m in [self.revenue, self.eps, self.book_value, self.fcf] if m.consistent_above_10
        )

    @computed_field
    @property
    def consistency_rating(self) -> str:
        """Growth consistency rating."""
        if self.consistent_count >= 4:
            return "Excellent"
        if self.consistent_count >= 3:
            return "Good"
        if self.consistent_count >= 2:
            return "Inconsistent"
        return "Poor"

    @computed_field
    @property
    def conservative_growth_rate(self) -> float | None:
        """Conservative growth rate for valuation (lowest of available 5yr rates)."""
        rates = [
            self.revenue.year_5,
            self.eps.year_5,
            self.book_value.year_5,
            self.fcf.year_5,
        ]
        valid_rates = [r for r in rates if r is not None and r > 0]
        return min(valid_rates) if valid_rates else None


class ProfitabilityMetrics(BaseModel):
    """Section 6: Profitability metrics."""

    roe: float | None = None
    roa: float | None = None
    roic: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    fcf_margin: float | None = None

    # Industry comparison
    roe_vs_industry: float | None = Field(default=None, description="Industry median ROE")
    roic_vs_industry: float | None = Field(default=None, description="Industry median ROIC")


class MoatIndicators(BaseModel):
    """Section 7: Moat indicators (quantitative signals only)."""

    roic_current: float | None = None
    roic_above_wacc: bool | None = Field(default=None, description="ROIC > 10% (proxy WACC)")
    gross_margin: float | None = None
    gross_margin_industry: float | None = None
    cash_conversion_cycle: float | None = None

    @computed_field
    @property
    def preliminary_rating(self) -> str:
        """Preliminary moat rating based on quantitative factors."""
        if self.roic_current is None:
            return "Unknown"
        if self.roic_current > 20 and self.roic_above_wacc:
            return "Narrow (Potential Wide)"
        if self.roic_current > 15 and self.roic_above_wacc:
            return "Narrow"
        if self.roic_above_wacc:
            return "Weak"
        return "None"


class ValuationMultiple(BaseModel):
    """A valuation multiple with historical and industry context."""

    name: str
    current: float | None = None
    historical_median: float | None = None
    industry_median: float | None = None

    @computed_field
    @property
    def vs_history(self) -> str:
        """Assessment vs historical median."""
        if self.current is None or self.historical_median is None:
            return "N/A"
        if self.historical_median == 0:
            return "N/A"
        ratio = self.current / self.historical_median
        if ratio < 0.8:
            return "Undervalued"
        if ratio > 1.2:
            return "Overvalued"
        return "Fair"


class Rule1Valuation(BaseModel):
    """Rule #1 Sticker Price calculation."""

    eps_ttm: float | None = None
    growth_rate: float | None = Field(default=None, description="Conservative growth rate used")
    future_pe: float | None = Field(default=None, description="2x growth rate, max 40")
    future_eps_10y: float | None = None
    future_price_10y: float | None = None
    sticker_price: float | None = Field(default=None, description="15% annual return target")
    buy_price: float | None = Field(default=None, description="50% margin of safety")


class ValuationAnalysis(BaseModel):
    """Section 8: Valuation analysis."""

    # Multiples
    pe: ValuationMultiple = Field(default_factory=lambda: ValuationMultiple(name="P/E"))
    pb: ValuationMultiple = Field(default_factory=lambda: ValuationMultiple(name="P/B"))
    ps: ValuationMultiple = Field(default_factory=lambda: ValuationMultiple(name="P/S"))
    ev_ebitda: ValuationMultiple = Field(
        default_factory=lambda: ValuationMultiple(name="EV/EBITDA")
    )
    peg: ValuationMultiple = Field(default_factory=lambda: ValuationMultiple(name="PEG"))

    # Intrinsic value estimates
    current_price: float | None = None
    gf_value: float | None = None
    dcf_earnings: float | None = None
    dcf_fcf: float | None = None

    # Rule #1
    rule1: Rule1Valuation = Field(default_factory=Rule1Valuation)

    @computed_field
    @property
    def gf_value_discount(self) -> float | None:
        """Discount to GF Value (positive = undervalued)."""
        if self.current_price and self.gf_value and self.gf_value > 0:
            return round(((self.gf_value - self.current_price) / self.gf_value) * 100, 1)
        return None

    @computed_field
    @property
    def verdict(self) -> str:
        """Valuation verdict."""
        discount = self.gf_value_discount
        if discount is None:
            return "Unknown"
        if discount > 20:
            return "Undervalued"
        if discount < -20:
            return "Overvalued"
        return "Fairly Valued"


class BusinessCyclePhase(BaseModel):
    """Section 9: Business cycle phase classification."""

    revenue_growth_5y: float | None = None
    operating_margin: float | None = None
    margin_trend: Literal["Expanding", "Stable", "Contracting", "Unknown"] = "Unknown"
    fcf_positive: bool | None = None
    pays_dividends: bool | None = None

    @computed_field
    @property
    def phase(self) -> str:
        """Business cycle phase (1-6)."""
        if self.revenue_growth_5y is None or self.operating_margin is None:
            return "Unknown"

        # Simplified classification logic
        if self.revenue_growth_5y > 30:
            return "2-Hypergrowth"
        if self.fcf_positive and self.revenue_growth_5y > 15:
            return "3-Self-Funding"
        if self.fcf_positive and self.margin_trend == "Expanding":
            return "4-Operating Leverage"
        if self.pays_dividends and self.fcf_positive:
            return "5-Capital Return"
        if self.revenue_growth_5y < 0:
            return "6-Decline"
        return "3-Self-Funding"  # Default for mature companies

    @computed_field
    @property
    def recommended_mos(self) -> int:
        """Recommended margin of safety percentage."""
        phase = self.phase
        if "Hypergrowth" in phase or "Startup" in phase:
            return 60
        if "Decline" in phase:
            return 70
        return 50


class InstitutionalActivity(BaseModel):
    """Section 10: Institutional activity."""

    guru_buys_pct: float | None = None
    guru_sells_pct: float | None = None
    fund_buys_pct: float | None = None
    fund_sells_pct: float | None = None
    etf_buys_pct: float | None = None
    etf_sells_pct: float | None = None

    @computed_field
    @property
    def sentiment(self) -> str:
        """Institutional sentiment."""
        if self.guru_buys_pct is None:
            return "Unknown"

        net_guru = (self.guru_buys_pct or 0) - (self.guru_sells_pct or 0)
        net_fund = (self.fund_buys_pct or 0) - (self.fund_sells_pct or 0)

        if net_guru > 10 and net_fund > 10:
            return "Accumulation"
        if net_guru < -10 and net_fund < -10:
            return "Distribution"
        return "Mixed"


class SummaryScore(BaseModel):
    """Section 11: Summary scorecard."""

    qgarp_screen_score: int = Field(default=0, ge=0, le=5)
    quality_score: int = Field(default=0, ge=0, le=10)
    financial_strength_pass: bool = False
    growth_consistency_score: int = Field(default=0, ge=0, le=4)
    profitability_score: int = Field(default=0, ge=0, le=10)
    valuation_score: int = Field(default=0, ge=0, le=10)

    @computed_field
    @property
    def overall_score(self) -> int:
        """Weighted overall score (0-100)."""
        # Weights: QGARP 20%, Quality 15%, Financial 20%, Growth 15%, Profit 10%, Valuation 20%
        score = 0.0
        score += (self.qgarp_screen_score / 5) * 20
        score += (self.quality_score / 10) * 15
        score += 20 if self.financial_strength_pass else 0
        score += (self.growth_consistency_score / 4) * 15
        score += (self.profitability_score / 10) * 10
        score += (self.valuation_score / 10) * 20
        return round(score)


class PriceTargets(BaseModel):
    """Price targets for investment decision."""

    buy_price: float | None = Field(default=None, description="50% MOS")
    sticker_price: float | None = Field(default=None, description="Fair value")
    sell_price: float | None = Field(default=None, description="150% of fair value")


class InvestmentDecision(BaseModel):
    """Section 12: Investment decision."""

    qgarp_passed: bool = False
    financial_passed: bool = False
    quality_passed: bool = False  # GF Score >= 70
    growth_passed: bool = False  # >= 2/4 Big Four > 10%

    gate_decision: GateDecision = GateDecision.DISCARD
    price_targets: PriceTargets = Field(default_factory=PriceTargets)

    # Areas for deep dive if proceeding
    moat_investigation: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)


# --- Main Analysis Model ---


class QGARPAnalysis(BaseModel):
    """Complete QGARP investment analysis for a stock.

    Combines data from summary, keyratios, and financials endpoints
    with computed metrics for investment screening.
    """

    symbol: str
    analysis_date: str = Field(description="ISO date of analysis")

    # Sections
    overview: CompanyOverview = Field(default_factory=CompanyOverview)
    screen: QGARPScreen = Field(default_factory=QGARPScreen)
    quality: QualityScores = Field(default_factory=QualityScores)
    financial_strength: FinancialStrength = Field(default_factory=FinancialStrength)
    growth: BigFourGrowth = Field(default_factory=BigFourGrowth)
    profitability: ProfitabilityMetrics = Field(default_factory=ProfitabilityMetrics)
    moat: MoatIndicators = Field(default_factory=MoatIndicators)
    valuation: ValuationAnalysis = Field(default_factory=ValuationAnalysis)
    business_cycle: BusinessCyclePhase = Field(default_factory=BusinessCyclePhase)
    institutional: InstitutionalActivity = Field(default_factory=InstitutionalActivity)
    summary: SummaryScore = Field(default_factory=SummaryScore)
    decision: InvestmentDecision = Field(default_factory=InvestmentDecision)
