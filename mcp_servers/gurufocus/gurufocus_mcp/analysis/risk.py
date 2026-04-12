"""Risk analysis computation from raw GuruFocus data."""

from datetime import date

from gurufocus_api.models import KeyRatios, StockSummary

from ..models.risk import (
    FinancialRisk,
    GrowthRisk,
    MarketRisk,
    QualityRisk,
    RiskAnalysis,
    RiskMatrix,
    RiskMetric,
    RiskRating,
    RiskSummary,
    RiskTrend,
    ValuationRisk,
    rating_to_score,
)


def compute_risk_analysis(
    symbol: str,
    summary: StockSummary,
    keyratios: KeyRatios,
) -> RiskAnalysis:
    """Compute quantitative risk analysis from GuruFocus data.

    Args:
        symbol: Stock ticker symbol
        summary: Stock summary data
        keyratios: Key financial ratios

    Returns:
        Complete RiskAnalysis with all dimensions populated
    """
    analysis = RiskAnalysis(
        symbol=symbol,
        company_name=keyratios.company_name,
        analysis_date=date.today().isoformat(),
    )

    # Build each risk dimension
    analysis.financial = _build_financial_risk(keyratios)
    analysis.quality = _build_quality_risk(keyratios, summary)
    analysis.growth = _build_growth_risk(keyratios)
    analysis.valuation = _build_valuation_risk(keyratios, summary)
    analysis.market = _build_market_risk(keyratios)

    # Build matrix
    analysis.matrix = RiskMatrix(
        financial=analysis.financial.overall_rating,
        quality=analysis.quality.overall_rating,
        growth=analysis.growth.overall_rating,
        valuation=analysis.valuation.overall_rating,
        market=analysis.market.overall_rating,
    )

    # Build summary
    analysis.summary = _build_summary(analysis)

    # Count metrics
    analysis.metrics_available = _count_available_metrics(analysis)
    analysis.metrics_total = 20

    return analysis


def _build_financial_risk(keyratios: KeyRatios) -> FinancialRisk:
    """Build financial risk dimension."""
    solv = keyratios.solvency
    liq = keyratios.liquidity

    risk = FinancialRisk()

    # Altman Z-Score
    risk.altman_z_score = RiskMetric(
        name="Altman Z-Score",
        value=keyratios.altman_z_score,
        threshold_red=1.81,
        threshold_green=2.99,
        higher_is_worse=False,
        interpretation=_interpret_z_score(keyratios.altman_z_score),
    )

    # Debt-to-Equity
    de_value = solv.debt_to_equity if solv else None
    risk.debt_to_equity = RiskMetric(
        name="Debt-to-Equity",
        value=de_value,
        threshold_red=1.5,
        threshold_green=0.5,
        higher_is_worse=True,
        interpretation=_interpret_debt_equity(de_value),
    )

    # Interest Coverage
    ic_value = solv.interest_coverage if solv else None
    risk.interest_coverage = RiskMetric(
        name="Interest Coverage",
        value=ic_value,
        threshold_red=2.0,
        threshold_green=5.0,
        higher_is_worse=False,
        interpretation=_interpret_interest_coverage(ic_value),
    )

    # Current Ratio
    cr_value = liq.current_ratio if liq else None
    risk.current_ratio = RiskMetric(
        name="Current Ratio",
        value=cr_value,
        threshold_red=1.0,
        threshold_green=1.5,
        higher_is_worse=False,
        interpretation=_interpret_current_ratio(cr_value),
    )

    # Debt-to-EBITDA
    de_ebitda = solv.debt_to_ebitda if solv else None
    risk.debt_to_ebitda = RiskMetric(
        name="Debt-to-EBITDA",
        value=de_ebitda,
        threshold_red=4.0,
        threshold_green=2.0,
        higher_is_worse=True,
        interpretation=_interpret_debt_ebitda(de_ebitda),
    )

    # Determine trend from financial strength rank changes (if available)
    risk.trend = RiskTrend.UNKNOWN

    return risk


def _build_quality_risk(keyratios: KeyRatios, summary: StockSummary) -> QualityRisk:
    """Build quality risk dimension."""
    risk = QualityRisk()

    # Piotroski F-Score
    risk.piotroski_score = RiskMetric(
        name="Piotroski F-Score",
        value=float(keyratios.piotroski_score) if keyratios.piotroski_score else None,
        threshold_red=3,
        threshold_green=7,
        higher_is_worse=False,
        interpretation=_interpret_piotroski(keyratios.piotroski_score),
    )

    # GF Score
    gf_score = summary.quality.gf_score if summary.quality else None
    risk.gf_score = RiskMetric(
        name="GF Score",
        value=float(gf_score) if gf_score else None,
        threshold_red=50,
        threshold_green=75,
        higher_is_worse=False,
        interpretation=_interpret_gf_score(gf_score),
    )

    # Beneish M-Score (earnings manipulation detector)
    risk.beneish_m_score = RiskMetric(
        name="Beneish M-Score",
        value=keyratios.beneish_m_score,
        threshold_red=-1.78,
        threshold_green=-2.22,
        higher_is_worse=True,
        interpretation=_interpret_beneish(keyratios.beneish_m_score),
    )

    # ROE as quality proxy
    roe = keyratios.profitability.roe if keyratios.profitability else None
    risk.roe_consistency = RiskMetric(
        name="ROE",
        value=roe,
        threshold_red=5,
        threshold_green=15,
        higher_is_worse=False,
        interpretation=_interpret_roe(roe),
    )

    risk.trend = RiskTrend.UNKNOWN
    return risk


def _build_growth_risk(keyratios: KeyRatios) -> GrowthRisk:
    """Build growth risk dimension."""
    g = keyratios.growth
    risk = GrowthRisk()

    # Revenue Growth 3Y
    rev_3y = g.revenue_growth_3y if g else None
    risk.revenue_growth_3y = RiskMetric(
        name="Revenue Growth (3Y)",
        value=rev_3y,
        threshold_red=-5,
        threshold_green=10,
        higher_is_worse=False,
        interpretation=_interpret_growth(rev_3y, "Revenue"),
    )

    # EPS Growth 3Y
    eps_3y = g.eps_growth_3y if g else None
    risk.eps_growth_3y = RiskMetric(
        name="EPS Growth (3Y)",
        value=eps_3y,
        threshold_red=-10,
        threshold_green=15,
        higher_is_worse=False,
        interpretation=_interpret_growth(eps_3y, "EPS"),
    )

    # FCF Growth 3Y
    fcf_3y = g.fcf_growth_3y if g else None
    risk.fcf_growth_3y = RiskMetric(
        name="FCF Growth (3Y)",
        value=fcf_3y,
        threshold_red=-15,
        threshold_green=10,
        higher_is_worse=False,
        interpretation=_interpret_growth(fcf_3y, "FCF"),
    )

    # Revenue momentum (1Y vs 3Y)
    rev_1y = g.revenue_growth_1y if g else None
    momentum = None
    if rev_1y is not None and rev_3y is not None:
        momentum = rev_1y - rev_3y  # Positive = accelerating
    risk.revenue_growth_consistency = RiskMetric(
        name="Revenue Momentum",
        value=momentum,
        threshold_red=-20,
        threshold_green=0,
        higher_is_worse=False,
        interpretation=_interpret_momentum(momentum),
    )

    # Determine trend from growth direction
    if rev_1y is not None and rev_3y is not None:
        if rev_1y > rev_3y:
            risk.trend = RiskTrend.DECREASING  # Growth accelerating = risk decreasing
        elif rev_1y < rev_3y - 10:
            risk.trend = RiskTrend.INCREASING  # Growth decelerating = risk increasing
        else:
            risk.trend = RiskTrend.STABLE
    else:
        risk.trend = RiskTrend.UNKNOWN

    return risk


def _build_valuation_risk(keyratios: KeyRatios, summary: StockSummary) -> ValuationRisk:
    """Build valuation risk dimension."""
    v = keyratios.valuation
    risk = ValuationRisk()

    # Price to GF Value
    current_price = keyratios.price.current_price if keyratios.price else None
    gf_value = v.gf_value if v else None
    price_to_gf = None
    if current_price and gf_value and gf_value > 0:
        price_to_gf = current_price / gf_value
    risk.price_to_gf_value = RiskMetric(
        name="Price/GF Value",
        value=price_to_gf,
        threshold_red=1.3,
        threshold_green=0.8,
        higher_is_worse=True,
        interpretation=_interpret_price_to_value(price_to_gf),
    )

    # PEG Ratio
    peg = v.peg_ratio if v else None
    risk.peg_ratio = RiskMetric(
        name="PEG Ratio",
        value=peg,
        threshold_red=2.0,
        threshold_green=1.0,
        higher_is_worse=True,
        interpretation=_interpret_peg(peg),
    )

    # P/E vs Historical
    pe_current = v.pe_ratio if v else None
    pe_historical = None
    if summary.ratios and summary.ratios.pe_ttm and summary.ratios.pe_ttm.his:
        pe_historical = summary.ratios.pe_ttm.his.med
    pe_vs_hist = None
    if pe_current and pe_historical and pe_historical > 0:
        pe_vs_hist = pe_current / pe_historical
    risk.pe_vs_historical = RiskMetric(
        name="P/E vs Historical",
        value=pe_vs_hist,
        threshold_red=1.5,
        threshold_green=0.8,
        higher_is_worse=True,
        interpretation=_interpret_pe_vs_history(pe_vs_hist),
    )

    # Margin of Safety
    mos = None
    if price_to_gf is not None:
        mos = (1 - price_to_gf) * 100  # Positive = undervalued
    risk.margin_of_safety = RiskMetric(
        name="Margin of Safety",
        value=mos,
        threshold_red=-10,
        threshold_green=30,
        higher_is_worse=False,
        interpretation=_interpret_mos(mos),
    )

    risk.trend = RiskTrend.UNKNOWN
    return risk


def _build_market_risk(keyratios: KeyRatios) -> MarketRisk:
    """Build market/volatility risk dimension."""
    p = keyratios.price
    risk = MarketRisk()

    # Beta
    beta = p.beta if p else None
    risk.beta = RiskMetric(
        name="Beta",
        value=beta,
        threshold_red=1.5,
        threshold_green=0.8,
        higher_is_worse=True,
        interpretation=_interpret_beta(beta),
    )

    # 1Y Volatility
    vol = p.volatility_1y if p else None
    risk.volatility_1y = RiskMetric(
        name="1Y Volatility",
        value=vol,
        threshold_red=50,
        threshold_green=25,
        higher_is_worse=True,
        interpretation=_interpret_volatility(vol),
    )

    # Drawdown from 52W High
    current = p.current_price if p else None
    high_52w = p.high_52week if p else None
    drawdown = None
    if current and high_52w and high_52w > 0:
        drawdown = ((high_52w - current) / high_52w) * 100
    risk.drawdown_from_high = RiskMetric(
        name="Drawdown from 52W High",
        value=drawdown,
        threshold_red=40,
        threshold_green=15,
        higher_is_worse=True,
        interpretation=_interpret_drawdown(drawdown),
    )

    risk.trend = RiskTrend.UNKNOWN
    return risk


def _build_summary(analysis: RiskAnalysis) -> RiskSummary:
    """Build overall risk summary."""
    # Calculate weighted score
    dimension_ratings = [
        analysis.financial.overall_rating,
        analysis.quality.overall_rating,
        analysis.growth.overall_rating,
        analysis.valuation.overall_rating,
        analysis.market.overall_rating,
    ]

    scores = [rating_to_score(r) for r in dimension_ratings]
    avg_score = sum(scores) / len(scores)

    # Determine overall rating
    if avg_score >= 2.5:
        overall = RiskRating.RED
    elif avg_score >= 1.5:
        overall = RiskRating.YELLOW
    else:
        overall = RiskRating.GREEN

    # Collect red flags (concerns from RED-rated dimensions)
    red_flags = []
    if analysis.financial.key_concern:
        red_flags.append(analysis.financial.key_concern)
    if analysis.quality.key_concern:
        red_flags.append(analysis.quality.key_concern)
    if analysis.growth.key_concern:
        red_flags.append(analysis.growth.key_concern)
    if analysis.valuation.key_concern:
        red_flags.append(analysis.valuation.key_concern)
    if analysis.market.key_concern:
        red_flags.append(analysis.market.key_concern)

    # Collect green flags (strengths from GREEN-rated dimensions)
    green_flags = []
    if analysis.financial.overall_rating == RiskRating.GREEN:
        green_flags.append("Strong financial position")
    if analysis.quality.overall_rating == RiskRating.GREEN:
        green_flags.append("High-quality business metrics")
    if analysis.growth.overall_rating == RiskRating.GREEN:
        green_flags.append("Healthy growth trajectory")
    if analysis.valuation.overall_rating == RiskRating.GREEN:
        green_flags.append("Attractive valuation")
    if analysis.market.overall_rating == RiskRating.GREEN:
        green_flags.append("Low market/volatility risk")

    return RiskSummary(
        overall_rating=overall,
        overall_score=round(avg_score, 2),
        red_flags=red_flags,
        green_flags=green_flags,
    )


def _count_available_metrics(analysis: RiskAnalysis) -> int:
    """Count metrics that have values."""
    count = 0

    # Financial
    for m in [
        analysis.financial.altman_z_score,
        analysis.financial.debt_to_equity,
        analysis.financial.interest_coverage,
        analysis.financial.current_ratio,
        analysis.financial.debt_to_ebitda,
    ]:
        if m.value is not None:
            count += 1

    # Quality
    for m in [
        analysis.quality.piotroski_score,
        analysis.quality.gf_score,
        analysis.quality.beneish_m_score,
        analysis.quality.roe_consistency,
    ]:
        if m.value is not None:
            count += 1

    # Growth
    for m in [
        analysis.growth.revenue_growth_3y,
        analysis.growth.eps_growth_3y,
        analysis.growth.fcf_growth_3y,
        analysis.growth.revenue_growth_consistency,
    ]:
        if m.value is not None:
            count += 1

    # Valuation
    for m in [
        analysis.valuation.price_to_gf_value,
        analysis.valuation.peg_ratio,
        analysis.valuation.pe_vs_historical,
        analysis.valuation.margin_of_safety,
    ]:
        if m.value is not None:
            count += 1

    # Market
    for m in [
        analysis.market.beta,
        analysis.market.volatility_1y,
        analysis.market.drawdown_from_high,
    ]:
        if m.value is not None:
            count += 1

    return count


# --- Interpretation helpers (brief, factual descriptions) ---


def _interpret_z_score(value: float | None) -> str | None:
    if value is None:
        return None
    if value > 2.99:
        return "Safe zone"
    if value >= 1.81:
        return "Grey zone"
    return "Distress zone"


def _interpret_debt_equity(value: float | None) -> str | None:
    if value is None:
        return None
    if value <= 0.5:
        return "Conservative leverage"
    if value <= 1.0:
        return "Moderate leverage"
    if value <= 1.5:
        return "Elevated leverage"
    return "High leverage"


def _interpret_interest_coverage(value: float | None) -> str | None:
    if value is None:
        return None
    if value >= 5:
        return "Strong coverage"
    if value >= 2:
        return "Adequate coverage"
    return "Weak coverage"


def _interpret_current_ratio(value: float | None) -> str | None:
    if value is None:
        return None
    if value >= 1.5:
        return "Strong liquidity"
    if value >= 1.0:
        return "Adequate liquidity"
    return "Weak liquidity"


def _interpret_debt_ebitda(value: float | None) -> str | None:
    if value is None:
        return None
    if value <= 2:
        return "Low debt burden"
    if value <= 4:
        return "Moderate debt burden"
    return "High debt burden"


def _interpret_piotroski(value: int | None) -> str | None:
    if value is None:
        return None
    if value >= 7:
        return "Strong fundamentals"
    if value >= 4:
        return "Mixed fundamentals"
    return "Weak fundamentals"


def _interpret_gf_score(value: int | None) -> str | None:
    if value is None:
        return None
    if value >= 75:
        return "High quality"
    if value >= 50:
        return "Average quality"
    return "Below average"


def _interpret_beneish(value: float | None) -> str | None:
    if value is None:
        return None
    if value < -2.22:
        return "Unlikely manipulator"
    if value <= -1.78:
        return "Inconclusive"
    return "Possible manipulator"


def _interpret_roe(value: float | None) -> str | None:
    if value is None:
        return None
    if value >= 15:
        return "Strong profitability"
    if value >= 10:
        return "Adequate profitability"
    if value >= 5:
        return "Low profitability"
    return "Weak profitability"


def _interpret_growth(value: float | None, metric: str) -> str | None:
    if value is None:
        return None
    if value >= 15:
        return f"Strong {metric} growth"
    if value >= 5:
        return f"Moderate {metric} growth"
    if value >= 0:
        return f"Flat {metric}"
    return f"Declining {metric}"


def _interpret_momentum(value: float | None) -> str | None:
    if value is None:
        return None
    if value > 5:
        return "Accelerating"
    if value > -5:
        return "Stable"
    return "Decelerating"


def _interpret_price_to_value(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 0.8:
        return "Significantly undervalued"
    if value < 1.0:
        return "Modestly undervalued"
    if value <= 1.1:
        return "Fairly valued"
    if value <= 1.3:
        return "Modestly overvalued"
    return "Significantly overvalued"


def _interpret_peg(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 1:
        return "Cheap relative to growth"
    if value <= 1.5:
        return "Fair relative to growth"
    if value <= 2:
        return "Elevated relative to growth"
    return "Expensive relative to growth"


def _interpret_pe_vs_history(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 0.8:
        return "Below historical average"
    if value <= 1.2:
        return "Near historical average"
    return "Above historical average"


def _interpret_mos(value: float | None) -> str | None:
    if value is None:
        return None
    if value >= 30:
        return "Large margin of safety"
    if value >= 10:
        return "Moderate margin of safety"
    if value >= 0:
        return "Minimal margin of safety"
    return "Negative margin of safety"


def _interpret_beta(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 0.8:
        return "Low systematic risk"
    if value <= 1.2:
        return "Market-like risk"
    if value <= 1.5:
        return "Above-market risk"
    return "High systematic risk"


def _interpret_volatility(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 25:
        return "Low volatility"
    if value < 40:
        return "Moderate volatility"
    if value < 50:
        return "Elevated volatility"
    return "High volatility"


def _interpret_drawdown(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 10:
        return "Near highs"
    if value < 20:
        return "Modest pullback"
    if value < 40:
        return "Significant drawdown"
    return "Deep drawdown"
