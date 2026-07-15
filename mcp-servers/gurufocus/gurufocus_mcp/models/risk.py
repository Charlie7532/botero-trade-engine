"""Pydantic models for quantitative risk analysis."""

# mypy: disable-error-code="prop-decorator"

from enum import Enum

from pydantic import BaseModel, Field, computed_field


class RiskRating(str, Enum):
    """Traffic light risk rating."""

    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"


class RiskTrend(str, Enum):
    """Directional risk trend."""

    INCREASING = "INCREASING"  # ↗️
    STABLE = "STABLE"  # ➡️
    DECREASING = "DECREASING"  # ↘️
    UNKNOWN = "UNKNOWN"


# --- Risk Dimension Models ---


class RiskMetric(BaseModel):
    """A single risk metric with value, threshold, and rating."""

    name: str
    value: float | None = None
    threshold_red: float | None = Field(default=None, description="Value at which risk is RED")
    threshold_green: float | None = Field(default=None, description="Value at which risk is GREEN")
    higher_is_worse: bool = Field(default=True, description="If True, higher values = higher risk")
    interpretation: str | None = None

    @computed_field
    @property
    def rating(self) -> RiskRating:
        """Compute rating based on thresholds."""
        if self.value is None:
            return RiskRating.YELLOW
        if self.threshold_red is None or self.threshold_green is None:
            return RiskRating.YELLOW

        if self.higher_is_worse:
            if self.value >= self.threshold_red:
                return RiskRating.RED
            if self.value <= self.threshold_green:
                return RiskRating.GREEN
            return RiskRating.YELLOW
        else:
            # Lower is worse (e.g., interest coverage, current ratio)
            if self.value <= self.threshold_red:
                return RiskRating.RED
            if self.value >= self.threshold_green:
                return RiskRating.GREEN
            return RiskRating.YELLOW


class FinancialRisk(BaseModel):
    """Financial risk assessment: leverage, solvency, bankruptcy probability."""

    altman_z_score: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="Altman Z-Score",
            threshold_red=1.81,
            threshold_green=2.99,
            higher_is_worse=False,
        )
    )
    debt_to_equity: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="Debt-to-Equity",
            threshold_red=1.5,
            threshold_green=0.5,
            higher_is_worse=True,
        )
    )
    interest_coverage: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="Interest Coverage",
            threshold_red=2.0,
            threshold_green=5.0,
            higher_is_worse=False,
        )
    )
    current_ratio: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="Current Ratio",
            threshold_red=1.0,
            threshold_green=1.5,
            higher_is_worse=False,
        )
    )
    debt_to_ebitda: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="Debt-to-EBITDA",
            threshold_red=4.0,
            threshold_green=2.0,
            higher_is_worse=True,
        )
    )

    trend: RiskTrend = RiskTrend.UNKNOWN

    @computed_field
    @property
    def overall_rating(self) -> RiskRating:
        """Weighted overall financial risk rating."""
        metrics = [
            self.altman_z_score,
            self.debt_to_equity,
            self.interest_coverage,
            self.current_ratio,
            self.debt_to_ebitda,
        ]
        return _compute_dimension_rating(metrics)

    @computed_field
    @property
    def key_concern(self) -> str | None:
        """Primary financial risk concern if any."""
        if self.altman_z_score.rating == RiskRating.RED:
            return "Bankruptcy risk (Z-Score in distress zone)"
        if self.interest_coverage.rating == RiskRating.RED:
            return "Debt servicing risk (low interest coverage)"
        if self.debt_to_equity.rating == RiskRating.RED:
            return "High leverage (elevated D/E ratio)"
        return None


class QualityRisk(BaseModel):
    """Quality risk assessment: business fundamentals, earnings quality."""

    piotroski_score: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="Piotroski F-Score",
            threshold_red=3,
            threshold_green=7,
            higher_is_worse=False,
        )
    )
    gf_score: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="GF Score",
            threshold_red=50,
            threshold_green=75,
            higher_is_worse=False,
        )
    )
    beneish_m_score: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="Beneish M-Score",
            threshold_red=-1.78,  # > -1.78 suggests manipulation
            threshold_green=-2.22,  # < -2.22 likely clean
            higher_is_worse=True,
        )
    )
    roe_consistency: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="ROE (profitability)",
            threshold_red=5,
            threshold_green=15,
            higher_is_worse=False,
        )
    )

    trend: RiskTrend = RiskTrend.UNKNOWN

    @computed_field
    @property
    def overall_rating(self) -> RiskRating:
        """Weighted overall quality risk rating."""
        metrics = [
            self.piotroski_score,
            self.gf_score,
            self.beneish_m_score,
            self.roe_consistency,
        ]
        return _compute_dimension_rating(metrics)

    @computed_field
    @property
    def key_concern(self) -> str | None:
        """Primary quality risk concern if any."""
        if self.beneish_m_score.rating == RiskRating.RED:
            return "Earnings manipulation risk (M-Score above threshold)"
        if self.piotroski_score.rating == RiskRating.RED:
            return "Weak fundamentals (low Piotroski score)"
        if self.gf_score.rating == RiskRating.RED:
            return "Below-average quality (low GF Score)"
        return None


class GrowthRisk(BaseModel):
    """Growth risk assessment: revenue/earnings trajectory, sustainability."""

    revenue_growth_3y: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="Revenue Growth (3Y)",
            threshold_red=-5,
            threshold_green=10,
            higher_is_worse=False,
        )
    )
    eps_growth_3y: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="EPS Growth (3Y)",
            threshold_red=-10,
            threshold_green=15,
            higher_is_worse=False,
        )
    )
    fcf_growth_3y: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="FCF Growth (3Y)",
            threshold_red=-15,
            threshold_green=10,
            higher_is_worse=False,
        )
    )
    revenue_growth_consistency: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="Revenue Momentum (1Y vs 3Y)",
            threshold_red=-20,  # 1Y significantly below 3Y average
            threshold_green=0,  # 1Y at or above 3Y average
            higher_is_worse=False,
        )
    )

    trend: RiskTrend = RiskTrend.UNKNOWN

    @computed_field
    @property
    def overall_rating(self) -> RiskRating:
        """Weighted overall growth risk rating."""
        metrics = [
            self.revenue_growth_3y,
            self.eps_growth_3y,
            self.fcf_growth_3y,
            self.revenue_growth_consistency,
        ]
        return _compute_dimension_rating(metrics)

    @computed_field
    @property
    def key_concern(self) -> str | None:
        """Primary growth risk concern if any."""
        if self.revenue_growth_3y.rating == RiskRating.RED:
            return "Revenue decline (negative 3Y growth)"
        if self.eps_growth_3y.rating == RiskRating.RED:
            return "Earnings decline (negative 3Y EPS growth)"
        if self.fcf_growth_3y.rating == RiskRating.RED:
            return "Cash flow deterioration (negative FCF growth)"
        return None


class ValuationRisk(BaseModel):
    """Valuation risk assessment: price vs intrinsic value, margin of safety."""

    price_to_gf_value: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="Price/GF Value",
            threshold_red=1.3,  # >30% overvalued
            threshold_green=0.8,  # >20% undervalued
            higher_is_worse=True,
        )
    )
    peg_ratio: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="PEG Ratio",
            threshold_red=2.0,
            threshold_green=1.0,
            higher_is_worse=True,
        )
    )
    pe_vs_historical: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="P/E vs Historical Median",
            threshold_red=1.5,  # 50% above historical
            threshold_green=0.8,  # 20% below historical
            higher_is_worse=True,
        )
    )
    margin_of_safety: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="Margin of Safety",
            threshold_red=-10,  # 10% overvalued = red
            threshold_green=30,  # 30% undervalued = green
            higher_is_worse=False,
        )
    )

    trend: RiskTrend = RiskTrend.UNKNOWN

    @computed_field
    @property
    def overall_rating(self) -> RiskRating:
        """Weighted overall valuation risk rating."""
        metrics = [
            self.price_to_gf_value,
            self.peg_ratio,
            self.pe_vs_historical,
            self.margin_of_safety,
        ]
        return _compute_dimension_rating(metrics)

    @computed_field
    @property
    def key_concern(self) -> str | None:
        """Primary valuation risk concern if any."""
        if self.price_to_gf_value.rating == RiskRating.RED:
            return "Overvalued vs intrinsic value (price > GF Value)"
        if self.peg_ratio.rating == RiskRating.RED:
            return "Expensive relative to growth (high PEG)"
        if self.margin_of_safety.rating == RiskRating.RED:
            return "No margin of safety (trading above fair value)"
        return None


class MarketRisk(BaseModel):
    """Market/volatility risk assessment."""

    beta: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="Beta",
            threshold_red=1.5,
            threshold_green=0.8,
            higher_is_worse=True,
        )
    )
    volatility_1y: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="1Y Volatility",
            threshold_red=50,  # 50% annualized volatility
            threshold_green=25,
            higher_is_worse=True,
        )
    )
    drawdown_from_high: RiskMetric = Field(
        default_factory=lambda: RiskMetric(
            name="Drawdown from 52W High",
            threshold_red=40,  # >40% drawdown
            threshold_green=15,
            higher_is_worse=True,
        )
    )

    trend: RiskTrend = RiskTrend.UNKNOWN

    @computed_field
    @property
    def overall_rating(self) -> RiskRating:
        """Weighted overall market risk rating."""
        metrics = [self.beta, self.volatility_1y, self.drawdown_from_high]
        return _compute_dimension_rating(metrics)

    @computed_field
    @property
    def key_concern(self) -> str | None:
        """Primary market risk concern if any."""
        if self.beta.rating == RiskRating.RED:
            return "High systematic risk (elevated beta)"
        if self.volatility_1y.rating == RiskRating.RED:
            return "High price volatility"
        if self.drawdown_from_high.rating == RiskRating.RED:
            return "Significant drawdown from recent high"
        return None


# --- Summary Models ---


class RiskSummary(BaseModel):
    """Overall risk summary with weighted scoring."""

    overall_rating: RiskRating = RiskRating.YELLOW
    overall_score: float = Field(default=2.0, description="Weighted score: 1=Low, 2=Medium, 3=High")
    red_flags: list[str] = Field(default_factory=list, description="RED-rated concerns")
    green_flags: list[str] = Field(default_factory=list, description="GREEN-rated strengths")


class RiskMatrix(BaseModel):
    """Risk matrix for quick reference."""

    financial: RiskRating = RiskRating.YELLOW
    quality: RiskRating = RiskRating.YELLOW
    growth: RiskRating = RiskRating.YELLOW
    valuation: RiskRating = RiskRating.YELLOW
    market: RiskRating = RiskRating.YELLOW


# --- Main Analysis Model ---


class RiskAnalysis(BaseModel):
    """Complete quantitative risk analysis for a stock.

    Analyzes five risk dimensions using GuruFocus data:
    - Financial Risk: Leverage, solvency, bankruptcy probability
    - Quality Risk: Business fundamentals, earnings quality
    - Growth Risk: Revenue/earnings trajectory, sustainability
    - Valuation Risk: Price vs intrinsic value, margin of safety
    - Market Risk: Beta, volatility, price drawdown

    Each dimension receives a RED/YELLOW/GREEN rating with evidence.
    """

    symbol: str
    company_name: str | None = None
    analysis_date: str = Field(description="ISO date of analysis")

    # Risk dimensions
    financial: FinancialRisk = Field(default_factory=FinancialRisk)
    quality: QualityRisk = Field(default_factory=QualityRisk)
    growth: GrowthRisk = Field(default_factory=GrowthRisk)
    valuation: ValuationRisk = Field(default_factory=ValuationRisk)
    market: MarketRisk = Field(default_factory=MarketRisk)

    # Summary
    summary: RiskSummary = Field(default_factory=RiskSummary)
    matrix: RiskMatrix = Field(default_factory=RiskMatrix)

    # Data completeness
    metrics_available: int = Field(default=0, description="Number of metrics with data")
    metrics_total: int = Field(default=20, description="Total metrics evaluated")


# --- Helper Functions ---


def _compute_dimension_rating(metrics: list[RiskMetric]) -> RiskRating:
    """Compute overall rating for a dimension from its metrics.

    Uses weighted average: RED=3, YELLOW=2, GREEN=1
    - >= 2.5 = RED
    - >= 1.5 = YELLOW
    - < 1.5 = GREEN
    """
    scores = []
    for m in metrics:
        if m.value is not None:
            if m.rating == RiskRating.RED:
                scores.append(3)
            elif m.rating == RiskRating.GREEN:
                scores.append(1)
            else:
                scores.append(2)

    if not scores:
        return RiskRating.YELLOW

    avg = sum(scores) / len(scores)
    if avg >= 2.5:
        return RiskRating.RED
    if avg >= 1.5:
        return RiskRating.YELLOW
    return RiskRating.GREEN


def rating_to_score(rating: RiskRating) -> int:
    """Convert rating to numeric score."""
    if rating == RiskRating.RED:
        return 3
    if rating == RiskRating.GREEN:
        return 1
    return 2
