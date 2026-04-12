"""Analysis MCP tools providing composite investment analysis.

Tools that combine multiple data sources and compute derived metrics
for investment screening and decision support.
"""

import asyncio
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from gurufocus_api.logging import get_logger

from ..analysis.qgarp import compute_qgarp_analysis
from ..analysis.risk import compute_risk_analysis
from ..context import get_client
from ..errors import raise_api_error, validate_symbol
from ..formatting import OutputFormat, format_output

logger = get_logger(__name__)


def register_analysis_tools(mcp: FastMCP) -> None:
    """Register analysis tools with the MCP server.

    Args:
        mcp: The FastMCP server instance to register tools with.
    """

    @mcp.tool()
    async def get_qgarp_analysis(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json'",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Generate a QGARP (Quality Growth at Reasonable Price) investment scorecard.

        Fetches summary, key ratios, and financial statements, then computes:

        **Screening (Sections 1-2)**:
        - Company overview (name, sector, market cap, 52-week range)
        - QGARP screen: ROIC >10%, Revenue/EPS growth >10%, D/E <0.5, P/E <40
        - Pass count and overall screen result

        **Quality (Sections 3-4)**:
        - GF Score, Piotroski F-Score, Altman Z-Score with interpretations
        - Financial strength: debt ratios, interest coverage, liquidity ratios
        - Red flag detection (high debt >0.8 D/E, low coverage <2x)

        **Growth (Section 5)**:
        - Rule #1 "Big Four": Revenue, EPS, Book Value, FCF growth (1/3/5/10yr)
        - Calculated book value/share CAGR from historical financials
        - Growth consistency rating (Excellent/Good/Inconsistent/Poor)
        - Conservative growth rate for valuation

        **Valuation (Sections 6-8)**:
        - Profitability metrics (ROE, ROA, ROIC, margins) with industry comparison
        - Moat indicators (quantitative signals only)
        - Valuation multiples vs historical/industry medians
        - Rule #1 Sticker Price and Buy Price calculation
        - GF Value discount and valuation verdict

        **Decision (Sections 9-12)**:
        - Business cycle phase classification (1-6)
        - Institutional sentiment (guru/fund/ETF activity)
        - Weighted overall score (0-100)
        - Gate decision: PROCEED / WATCHLIST / DISCARD
        - Suggested areas for moat investigation and risk review
        - Price targets (buy price, sticker price, sell price)

        Use this tool for systematic investment screening using the QGARP methodology.
        One API call replaces multiple get_stock_* calls with pre-computed analysis.
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug("get_qgarp_analysis_called", symbol=normalized, format=format)

        try:
            client = get_client(ctx)

            # Fetch all required data in parallel (leverages caching)
            summary, keyratios, financials = await asyncio.gather(
                client.stocks.get_summary(normalized),
                client.stocks.get_keyratios(normalized),
                client.stocks.get_financials(normalized, period_type="annual"),
            )

            # Compute QGARP analysis
            analysis = compute_qgarp_analysis(
                symbol=normalized,
                summary=summary,
                keyratios=keyratios,
                financials=financials,
            )

            data: dict[str, Any] = analysis.model_dump(mode="json", exclude_none=True)
            logger.debug("get_qgarp_analysis_success", symbol=normalized, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_qgarp_analysis_error", symbol=normalized, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_risk_analysis(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json'",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Quantitative risk analysis using GuruFocus metrics.

        Analyzes five risk dimensions with RED/YELLOW/GREEN ratings:

        **Financial Risk**:
        - Altman Z-Score (bankruptcy probability)
        - Debt-to-Equity, Debt-to-EBITDA (leverage)
        - Interest Coverage (debt servicing ability)
        - Current Ratio (liquidity)

        **Quality Risk**:
        - Piotroski F-Score (fundamental strength)
        - GF Score (overall quality)
        - Beneish M-Score (earnings manipulation)
        - ROE (profitability)

        **Growth Risk**:
        - Revenue, EPS, FCF growth (3-year CAGR)
        - Revenue momentum (1Y vs 3Y)

        **Valuation Risk**:
        - Price/GF Value ratio
        - PEG ratio
        - P/E vs historical median
        - Margin of safety

        **Market Risk**:
        - Beta (systematic risk)
        - 1Y Volatility
        - Drawdown from 52-week high

        Returns a risk matrix with ratings and evidence for each dimension.
        Use as quantitative foundation for investment risk assessment.
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug("get_stock_risk_analysis_called", symbol=normalized, format=format)

        try:
            client = get_client(ctx)

            # Fetch required data in parallel
            summary, keyratios = await asyncio.gather(
                client.stocks.get_summary(normalized),
                client.stocks.get_keyratios(normalized),
            )

            # Compute risk analysis
            analysis = compute_risk_analysis(
                symbol=normalized,
                summary=summary,
                keyratios=keyratios,
            )

            data: dict[str, Any] = analysis.model_dump(mode="json", exclude_none=True)
            logger.debug("get_stock_risk_analysis_success", symbol=normalized, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_risk_analysis_error", symbol=normalized, error=str(e))
            raise_api_error(e)
