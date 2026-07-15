"""QGARP analysis computation from raw GuruFocus data."""

from datetime import date

from gurufocus_api.models import FinancialStatements, KeyRatios, StockSummary

from ..models.qgarp import (
    BigFourGrowth,
    BusinessCyclePhase,
    CompanyOverview,
    FinancialStrength,
    GateDecision,
    GrowthMetric,
    InstitutionalActivity,
    InvestmentDecision,
    MoatIndicators,
    PriceTargets,
    ProfitabilityMetrics,
    QGARPAnalysis,
    QGARPScreen,
    QualityScores,
    Rule1Valuation,
    ScreenCriterion,
    ScreenResult,
    SummaryScore,
    ValuationAnalysis,
    ValuationMultiple,
)


def compute_qgarp_analysis(
    symbol: str,
    summary: StockSummary,
    keyratios: KeyRatios,
    financials: FinancialStatements,
) -> QGARPAnalysis:
    """Compute complete QGARP analysis from GuruFocus data.

    Args:
        symbol: Stock ticker symbol
        summary: Stock summary data
        keyratios: Key financial ratios
        financials: Historical financial statements

    Returns:
        Complete QGARPAnalysis with all sections populated
    """
    analysis = QGARPAnalysis(
        symbol=symbol,
        analysis_date=date.today().isoformat(),
    )

    # Section 1: Company Overview
    analysis.overview = _build_overview(summary, keyratios)

    # Section 2: QGARP Screen
    analysis.screen = _build_screen(keyratios)

    # Section 3: Quality Scores
    analysis.quality = _build_quality_scores(summary, keyratios)

    # Section 4: Financial Strength
    analysis.financial_strength = _build_financial_strength(keyratios)

    # Section 5: Big Four Growth
    analysis.growth = _build_growth(keyratios, financials)

    # Section 6: Profitability
    analysis.profitability = _build_profitability(keyratios, summary)

    # Section 7: Moat Indicators
    analysis.moat = _build_moat_indicators(keyratios, summary)

    # Section 8: Valuation
    analysis.valuation = _build_valuation(summary, keyratios, analysis.growth)

    # Section 9: Business Cycle
    analysis.business_cycle = _build_business_cycle(keyratios)

    # Section 10: Institutional Activity
    analysis.institutional = _build_institutional(summary)

    # Section 11: Summary Score
    analysis.summary = _build_summary_score(analysis)

    # Section 12: Investment Decision
    analysis.decision = _build_decision(analysis)

    return analysis


def _build_overview(summary: StockSummary, keyratios: KeyRatios) -> CompanyOverview:
    """Build company overview section."""
    return CompanyOverview(
        company_name=summary.general.company_name if summary.general else None,
        sector=summary.general.sector if summary.general else None,
        industry=summary.general.industry if summary.general else None,
        market_cap=summary.general.market_cap if summary.general else None,
        currency=summary.general.currency if summary.general else None,
        current_price=summary.price.current if summary.price else None,
        high_52week=keyratios.price.high_52week if keyratios.price else None,
        low_52week=keyratios.price.low_52week if keyratios.price else None,
        description=summary.general.short_description if summary.general else None,
    )


def _build_screen(keyratios: KeyRatios) -> QGARPScreen:
    """Build QGARP screening criteria with pass/fail results."""
    screen = QGARPScreen()

    # ROIC > 10%
    roic = keyratios.profitability.roic if keyratios.profitability else None
    screen.roic = ScreenCriterion(
        name="ROIC",
        value=roic,
        threshold=">10%",
        result=_check_threshold(roic, ">", 10),
    )

    # Revenue Growth 5yr > 10%
    rev_growth = keyratios.growth.revenue_growth_5y if keyratios.growth else None
    screen.revenue_growth_5y = ScreenCriterion(
        name="Revenue Growth (5yr)",
        value=rev_growth,
        threshold=">10%",
        result=_check_threshold(rev_growth, ">", 10),
    )

    # EPS Growth 5yr > 10%
    eps_growth = keyratios.growth.eps_growth_5y if keyratios.growth else None
    screen.eps_growth_5y = ScreenCriterion(
        name="EPS Growth (5yr)",
        value=eps_growth,
        threshold=">10%",
        result=_check_threshold(eps_growth, ">", 10),
    )

    # Debt-to-Equity < 0.5
    de = keyratios.solvency.debt_to_equity if keyratios.solvency else None
    screen.debt_to_equity = ScreenCriterion(
        name="Debt-to-Equity",
        value=de,
        threshold="<0.5",
        result=_check_threshold(de, "<", 0.5),
    )

    # P/E < 40
    pe = keyratios.valuation.pe_ratio if keyratios.valuation else None
    screen.pe_ratio = ScreenCriterion(
        name="P/E Ratio",
        value=pe,
        threshold="<40",
        result=_check_threshold(pe, "<", 40),
    )

    return screen


def _check_threshold(value: float | None, operator: str, threshold: float) -> ScreenResult:
    """Check if value passes threshold."""
    if value is None:
        return ScreenResult.NA
    if operator == ">":
        return ScreenResult.PASS if value > threshold else ScreenResult.FAIL
    if operator == "<":
        return ScreenResult.PASS if value < threshold else ScreenResult.FAIL
    if operator == ">=":
        return ScreenResult.PASS if value >= threshold else ScreenResult.FAIL
    if operator == "<=":
        return ScreenResult.PASS if value <= threshold else ScreenResult.FAIL
    return ScreenResult.NA


def _build_quality_scores(summary: StockSummary, keyratios: KeyRatios) -> QualityScores:
    """Build quality scores section."""
    return QualityScores(
        gf_score=summary.quality.gf_score if summary.quality else None,
        financial_strength=summary.quality.financial_strength if summary.quality else None,
        profitability_rank=summary.quality.profitability_rank if summary.quality else None,
        growth_rank=summary.quality.growth_rank if summary.quality else None,
        piotroski_score=keyratios.piotroski_score,
        altman_z_score=keyratios.altman_z_score,
    )


def _build_financial_strength(keyratios: KeyRatios) -> FinancialStrength:
    """Build financial strength section."""
    solv = keyratios.solvency
    liq = keyratios.liquidity

    de = solv.debt_to_equity if solv else None
    ic = solv.interest_coverage if solv else None

    return FinancialStrength(
        debt_to_equity=de,
        debt_to_ebitda=solv.debt_to_ebitda if solv else None,
        interest_coverage=ic,
        current_ratio=liq.current_ratio if liq else None,
        quick_ratio=liq.quick_ratio if liq else None,
        cash_ratio=liq.cash_ratio if liq else None,
        high_debt_flag=de is not None and de > 0.8,
        low_coverage_flag=ic is not None and ic < 2,
    )


def _build_growth(keyratios: KeyRatios, financials: FinancialStatements) -> BigFourGrowth:
    """Build Big Four growth section with calculated BV/share growth."""
    g = keyratios.growth

    # Calculate book value per share growth from financials
    bv_growth = _calculate_bv_growth(financials)

    return BigFourGrowth(
        revenue=GrowthMetric(
            name="Revenue",
            year_1=g.revenue_growth_1y if g else None,
            year_3=g.revenue_growth_3y if g else None,
            year_5=g.revenue_growth_5y if g else None,
            year_10=g.revenue_growth_10y if g else None,
        ),
        eps=GrowthMetric(
            name="EPS",
            year_1=g.eps_growth_1y if g else None,
            year_3=g.eps_growth_3y if g else None,
            year_5=g.eps_growth_5y if g else None,
            year_10=g.eps_growth_10y if g else None,
        ),
        book_value=bv_growth,
        fcf=GrowthMetric(
            name="FCF",
            year_1=g.fcf_growth_1y if g else None,
            year_3=g.fcf_growth_3y if g else None,
            year_5=g.fcf_growth_5y if g else None,
            year_10=None,  # Not available from keyratios
        ),
    )


def _calculate_bv_growth(financials: FinancialStatements) -> GrowthMetric:
    """Calculate book value per share CAGR from historical data."""
    periods = financials.periods
    if len(periods) < 2:
        return GrowthMetric(name="Book Value/Share")

    # Get BV/share for different periods (periods are most recent first)
    current_bv = periods[0].book_value_per_share if periods else None

    def get_cagr(years: int) -> float | None:
        if current_bv is None or current_bv <= 0:
            return None
        if len(periods) <= years:
            return None
        past_bv = periods[years].book_value_per_share
        if past_bv is None or past_bv <= 0:
            return None
        return float(round((((current_bv / past_bv) ** (1 / years)) - 1) * 100, 2))

    return GrowthMetric(
        name="Book Value/Share",
        year_1=get_cagr(1),
        year_3=get_cagr(3),
        year_5=get_cagr(5),
        year_10=get_cagr(10),
    )


def _build_profitability(keyratios: KeyRatios, summary: StockSummary) -> ProfitabilityMetrics:
    """Build profitability metrics section."""
    p = keyratios.profitability

    # Get industry medians from summary ratios if available
    roe_industry = None
    roic_industry = None
    if summary.ratios:
        if summary.ratios.roe and summary.ratios.roe.indu:
            roe_industry = summary.ratios.roe.indu.indu_med
        if summary.ratios.roic and summary.ratios.roic.indu:
            roic_industry = summary.ratios.roic.indu.indu_med

    return ProfitabilityMetrics(
        roe=p.roe if p else None,
        roa=p.roa if p else None,
        roic=p.roic if p else None,
        gross_margin=p.gross_margin if p else None,
        operating_margin=p.operating_margin if p else None,
        net_margin=p.net_margin if p else None,
        fcf_margin=p.fcf_margin if p else None,
        roe_vs_industry=roe_industry,
        roic_vs_industry=roic_industry,
    )


def _build_moat_indicators(keyratios: KeyRatios, summary: StockSummary) -> MoatIndicators:
    """Build moat indicators section."""
    roic = keyratios.profitability.roic if keyratios.profitability else None

    # Get gross margin industry median if available
    gross_margin_industry = None
    if summary.ratios and hasattr(summary.ratios, "gross_margin"):
        gm_ratio = getattr(summary.ratios, "gross_margin", None)
        if gm_ratio and hasattr(gm_ratio, "indu") and gm_ratio.indu:
            gross_margin_industry = gm_ratio.indu.indu_med

    return MoatIndicators(
        roic_current=roic,
        roic_above_wacc=roic is not None and roic > 10,
        gross_margin=keyratios.profitability.gross_margin if keyratios.profitability else None,
        gross_margin_industry=gross_margin_industry,
        cash_conversion_cycle=(
            keyratios.efficiency.cash_conversion_cycle if keyratios.efficiency else None
        ),
    )


def _build_valuation(
    summary: StockSummary,
    keyratios: KeyRatios,
    growth: BigFourGrowth,
) -> ValuationAnalysis:
    """Build valuation analysis section."""
    v = keyratios.valuation
    sr = summary.ratios

    current_price = summary.price.current if summary.price else None

    # Build multiples with historical/industry context
    def build_multiple(
        name: str, current: float | None, ratio_data: object | None
    ) -> ValuationMultiple:
        hist_med = None
        indu_med = None
        if ratio_data:
            if hasattr(ratio_data, "his") and ratio_data.his:
                hist_med = ratio_data.his.med
            if hasattr(ratio_data, "indu") and ratio_data.indu:
                indu_med = ratio_data.indu.indu_med
        return ValuationMultiple(
            name=name,
            current=current,
            historical_median=hist_med,
            industry_median=indu_med,
        )

    valuation = ValuationAnalysis(
        pe=build_multiple("P/E", v.pe_ratio if v else None, sr.pe_ttm if sr else None),
        pb=build_multiple("P/B", v.pb_ratio if v else None, sr.pb_ratio if sr else None),
        ps=build_multiple("P/S", v.ps_ratio if v else None, sr.ps_ratio if sr else None),
        ev_ebitda=build_multiple(
            "EV/EBITDA", v.ev_to_ebitda if v else None, sr.ev_ebitda if sr else None
        ),
        peg=build_multiple("PEG", v.peg_ratio if v else None, sr.peg_ratio if sr else None),
        current_price=current_price,
        gf_value=summary.valuation.gf_value if summary.valuation else None,
        dcf_earnings=summary.valuation.dcf_earnings_based if summary.valuation else None,
        dcf_fcf=summary.valuation.dcf_fcf_based if summary.valuation else None,
    )

    # Rule #1 Sticker Price calculation
    valuation.rule1 = _calculate_rule1(keyratios, growth)

    return valuation


def _calculate_rule1(keyratios: KeyRatios, growth: BigFourGrowth) -> Rule1Valuation:
    """Calculate Rule #1 sticker price and buy price."""
    eps = keyratios.per_share.eps_ttm if keyratios.per_share else None
    growth_rate = growth.conservative_growth_rate

    if eps is None or growth_rate is None or eps <= 0 or growth_rate <= 0:
        return Rule1Valuation(eps_ttm=eps, growth_rate=growth_rate)

    # Future P/E = 2x growth rate, capped at 40
    future_pe = min(growth_rate * 2, 40)

    # Future EPS after 10 years
    future_eps = eps * ((1 + growth_rate / 100) ** 10)

    # Future price
    future_price = future_eps * future_pe

    # Sticker price (15% annual return = divide by 4.05)
    sticker_price = future_price / 4.05

    # Buy price (50% margin of safety)
    buy_price = sticker_price * 0.5

    return Rule1Valuation(
        eps_ttm=round(eps, 2),
        growth_rate=round(growth_rate, 2),
        future_pe=round(future_pe, 2),
        future_eps_10y=round(future_eps, 2),
        future_price_10y=round(future_price, 2),
        sticker_price=round(sticker_price, 2),
        buy_price=round(buy_price, 2),
    )


def _build_business_cycle(keyratios: KeyRatios) -> BusinessCyclePhase:
    """Build business cycle phase section."""
    fcf_per_share = keyratios.per_share.fcf_per_share if keyratios.per_share else None
    dividend_yield = keyratios.dividends.dividend_yield if keyratios.dividends else None

    return BusinessCyclePhase(
        revenue_growth_5y=keyratios.growth.revenue_growth_5y if keyratios.growth else None,
        operating_margin=(
            keyratios.profitability.operating_margin if keyratios.profitability else None
        ),
        margin_trend="Unknown",  # Would need historical comparison
        fcf_positive=fcf_per_share is not None and fcf_per_share > 0,
        pays_dividends=dividend_yield is not None and dividend_yield > 0,
    )


def _build_institutional(summary: StockSummary) -> InstitutionalActivity:
    """Build institutional activity section."""
    inst = summary.institutional
    if not inst:
        return InstitutionalActivity()

    return InstitutionalActivity(
        guru_buys_pct=inst.guru_buys_pct,
        guru_sells_pct=inst.guru_sells_pct,
        fund_buys_pct=inst.fund_buys_pct,
        fund_sells_pct=inst.fund_sells_pct,
        etf_buys_pct=inst.etf_buys_pct,
        etf_sells_pct=inst.etf_sells_pct,
    )


def _build_summary_score(analysis: QGARPAnalysis) -> SummaryScore:
    """Build summary scorecard."""
    # Quality score: normalize GF score to 0-10
    quality = analysis.quality.gf_score
    quality_score = int(quality / 10) if quality else 0

    # Profitability score based on ROIC
    roic = analysis.profitability.roic
    if roic is None:
        profit_score = 0
    elif roic > 20:
        profit_score = 10
    elif roic > 15:
        profit_score = 8
    elif roic > 10:
        profit_score = 6
    else:
        profit_score = 4

    # Valuation score based on GF Value discount
    discount = analysis.valuation.gf_value_discount
    if discount is None:
        val_score = 5
    elif discount > 30:
        val_score = 10
    elif discount > 20:
        val_score = 8
    elif discount > 0:
        val_score = 6
    elif discount > -20:
        val_score = 4
    else:
        val_score = 2

    return SummaryScore(
        qgarp_screen_score=analysis.screen.pass_count,
        quality_score=quality_score,
        financial_strength_pass=analysis.financial_strength.verdict
        in ("PASS", "PASS WITH CAUTION"),
        growth_consistency_score=analysis.growth.consistent_count,
        profitability_score=profit_score,
        valuation_score=val_score,
    )


def _build_decision(analysis: QGARPAnalysis) -> InvestmentDecision:
    """Build investment decision section."""
    qgarp_passed = analysis.screen.pass_count >= 4
    financial_passed = analysis.financial_strength.verdict in ("PASS", "PASS WITH CAUTION")
    quality_passed = (analysis.quality.gf_score or 0) >= 70
    growth_passed = analysis.growth.consistent_count >= 2

    # Determine gate decision
    if qgarp_passed and financial_passed and quality_passed and growth_passed:
        gate = GateDecision.PROCEED
    elif qgarp_passed and financial_passed:
        gate = GateDecision.WATCHLIST
    else:
        gate = GateDecision.DISCARD

    # Price targets
    rule1 = analysis.valuation.rule1
    price_targets = PriceTargets(
        buy_price=rule1.buy_price,
        sticker_price=rule1.sticker_price,
        sell_price=round(rule1.sticker_price * 1.5, 2) if rule1.sticker_price else None,
    )

    return InvestmentDecision(
        qgarp_passed=qgarp_passed,
        financial_passed=financial_passed,
        quality_passed=quality_passed,
        growth_passed=growth_passed,
        gate_decision=gate,
        price_targets=price_targets,
        moat_investigation=_suggest_moat_areas(analysis),
        risk_factors=_suggest_risk_areas(analysis),
    )


def _suggest_moat_areas(analysis: QGARPAnalysis) -> list[str]:
    """Suggest areas to investigate for moat analysis."""
    areas = []

    roic = analysis.profitability.roic
    if roic and roic > 15:
        areas.append("High ROIC - investigate source of competitive advantage")

    gm = analysis.profitability.gross_margin
    if gm and gm > 40:
        areas.append("High gross margin - evaluate pricing power")

    ccc = analysis.moat.cash_conversion_cycle
    if ccc and ccc < 0:
        areas.append("Negative cash conversion cycle - analyze working capital advantage")

    return areas or ["Standard competitive analysis required"]


def _suggest_risk_areas(analysis: QGARPAnalysis) -> list[str]:
    """Suggest risk areas to investigate."""
    risks = []

    if analysis.financial_strength.high_debt_flag:
        risks.append("High debt levels - review debt covenants and refinancing risk")

    if analysis.financial_strength.low_coverage_flag:
        risks.append("Low interest coverage - assess cash flow stability")

    if analysis.growth.consistent_count < 2:
        risks.append("Inconsistent growth - investigate cyclicality or disruption risk")

    if analysis.valuation.verdict == "Overvalued":
        risks.append("Elevated valuation - consider margin of safety requirements")

    return risks or ["Standard 10-K risk factor review"]
