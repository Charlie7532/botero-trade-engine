"""Stock-related MCP tools.

Tools for fetching stock financial data from GuruFocus API.
"""

from typing import Annotated, Any, Literal

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from gurufocus_api.logging import get_logger

from ..context import get_client
from ..errors import raise_api_error, validate_symbol
from ..formatting import OutputFormat, format_output
from ..query import apply_query

logger = get_logger(__name__)


def register_stock_tools(mcp: FastMCP) -> None:
    """Register stock-related tools with the MCP server.

    Args:
        mcp: The FastMCP server instance to register tools with.
    """

    @mcp.tool()
    async def get_stock_summary(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get comprehensive financial summary for a stock.

        Returns structured data including:
        - Company info: name, sector, industry, market cap, description
        - Current price and daily change percentage
        - Quality scores: GF Score, financial strength, profitability rank, growth rank
        - Valuation metrics: P/E, P/B, P/S ratios, GF Value, DCF estimates
        - Financial ratios with 5/10-year averages and industry medians
        - Institutional activity: guru and fund buying/selling percentages

        Use this tool when you need to analyze a stock's fundamentals,
        valuation, or financial health.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug("get_stock_summary_called", symbol=normalized, format=format)

        try:
            client = get_client(ctx)

            summary = await client.stocks.get_summary(normalized)
            data = summary.model_dump(mode="json", exclude_none=True)
            logger.debug("get_stock_summary_success", symbol=normalized, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_summary_error", symbol=normalized, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_quote(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get real-time stock quote data.

        Returns current market data for a stock:
        - current_price: Current trading price
        - price_change: Absolute price change from previous close
        - price_change_pct: Percentage change from previous close
        - open, high, low: Daily OHLV data
        - volume: Trading volume for the day
        - exchange: Stock exchange (NAS, NYSE, etc.)
        - currency: Price currency (USD, EUR, etc.)

        This is a lightweight alternative to get_stock_summary when you only
        need current price and daily trading data, not full fundamental analysis.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug("get_stock_quote_called", symbol=normalized, format=format)

        try:
            client = get_client(ctx)

            quote = await client.stocks.get_quote(normalized)
            data = quote.model_dump(mode="json", exclude_none=True)
            logger.debug("get_stock_quote_success", symbol=normalized, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_quote_error", symbol=normalized, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_dividend(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        query: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "JMESPath query to filter/transform the response. "
                    "Examples: 'payments[:5]' (recent 5), 'payments[*].amount' (just amounts)"
                ),
            ),
        ] = None,
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get dividend history for a stock.

        Schema: Call get_schema("DividendHistory") to see the full schema.

        Returns historical dividend payment data:
        - payments: Array of historical dividend payments
          - ex_date: Ex-dividend date
          - pay_date: Payment date
          - record_date: Record date
          - amount: Dividend amount per share
          - type: Dividend type (regular, special, etc.)
          - frequency: Payment frequency (quarterly, annual, etc.)

        Use this tool when you need to analyze a stock's dividend history,
        track payout trends, or evaluate income potential.

        Use the 'query' parameter with a JMESPath expression to filter the response.
        Call get_schema() first to understand the data structure.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug("get_stock_dividend_called", symbol=normalized, query=query, format=format)

        try:
            client = get_client(ctx)

            dividends = await client.stocks.get_dividends(normalized)

            # If query provided, apply JMESPath and return result directly
            if query:
                try:
                    result = apply_query(dividends, query)
                    if isinstance(result, dict):
                        return format_output(result, format) if format == "toon" else result
                    wrapped: dict[str, Any] = {"result": result, "query": query}
                    return format_output(wrapped, format) if format == "toon" else wrapped
                except ValueError as e:
                    raise ToolError(str(e)) from e

            data = dividends.model_dump(mode="json", exclude_none=True)
            logger.debug("get_stock_dividend_success", symbol=normalized, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_dividend_error", symbol=normalized, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_current_dividend(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get current dividend information for a stock.

        Returns current dividend data including:
        - dividend_yield: Current dividend yield percentage
        - dividends_per_share_ttm: Trailing twelve months dividend per share
        - dividend_yield_10y_range: 10-year historical yield range
        - dividend_yield_10y_median: 10-year median dividend yield
        - next_payment_date: Next scheduled dividend payment date
        - frequency: Payment frequency (Quarterly, Annual, etc.)
        - currency: Currency symbol

        Use this tool when you need to analyze a stock's current dividend
        yield, compare it to historical ranges, or check payment schedule.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug("get_stock_current_dividend_called", symbol=normalized, format=format)

        try:
            client = get_client(ctx)

            current_div = await client.stocks.get_current_dividend(normalized)
            data = current_div.model_dump(mode="json", exclude_none=True)
            logger.debug("get_stock_current_dividend_success", symbol=normalized, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_current_dividend_error", symbol=normalized, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_financials(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        period_type: Annotated[
            Literal["annual", "quarterly"],
            Field(
                default="annual",
                description="Financial period type: 'annual' for yearly data or 'quarterly' for quarterly data",
            ),
        ] = "annual",
        query: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "JMESPath query to filter/transform the response. "
                    "Examples: 'periods[:5]' (recent 5), 'periods[*].{period: period, revenue: revenue}'"
                ),
            ),
        ] = None,
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get financial statements for a stock.

        Schema: Call get_schema("FinancialStatements") to see the full schema.

        Returns historical financial data including:
        - Per-share metrics: revenue per share, EPS, book value per share, FCF per share
        - Income statement: revenue, gross profit, operating income, net income, EBITDA
        - Balance sheet: total assets, liabilities, equity, debt, cash
        - Cash flow: operating cash flow, capex, free cash flow, dividends paid
        - Margins: gross margin, operating margin, net margin

        Data is organized by fiscal period (most recent first) with both annual
        and quarterly options available.

        Use this tool when you need to analyze a company's financial performance
        over time, track revenue/earnings trends, or evaluate balance sheet health.

        Use the 'query' parameter with a JMESPath expression to filter the response.
        Call get_schema() first to understand the data structure.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug(
            "get_stock_financials_called",
            symbol=normalized,
            period_type=period_type,
            query=query,
            format=format,
        )

        try:
            client = get_client(ctx)

            financials = await client.stocks.get_financials(normalized, period_type=period_type)

            # If query provided, apply JMESPath and return result directly
            if query:
                try:
                    result = apply_query(financials, query)
                    if isinstance(result, dict):
                        return format_output(result, format) if format == "toon" else result
                    wrapped: dict[str, Any] = {"result": result, "query": query}
                    return format_output(wrapped, format) if format == "toon" else wrapped
                except ValueError as e:
                    raise ToolError(str(e)) from e

            data = financials.model_dump(mode="json", exclude_none=True)
            logger.debug(
                "get_stock_financials_success",
                symbol=normalized,
                period_type=period_type,
                format=format,
            )
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_financials_error", symbol=normalized, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_keyratios(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        query: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "JMESPath query to filter/transform the response. "
                    "Examples: 'profitability' (just profitability), 'valuation' (just valuation)"
                ),
            ),
        ] = None,
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get key financial ratios for a stock.

        Schema: Call get_schema("KeyRatios") to see the full schema.

        Returns comprehensive financial ratios organized by category:
        - Quality scores: Piotroski F-Score, Altman Z-Score, GF Score, financial strength
        - Profitability: ROE, ROA, ROIC, gross/operating/net margins
        - Liquidity: current ratio, quick ratio, cash ratio
        - Solvency: debt-to-equity, debt-to-asset, interest coverage
        - Efficiency: asset turnover, inventory turnover, days sales outstanding
        - Growth: 1/3/5/10-year revenue, EPS, and FCF growth rates
        - Valuation: P/E, P/B, P/S, PEG, EV/EBITDA, GF Value
        - Price metrics: 52-week high/low, beta, volatility, returns
        - Dividends: yield, payout ratio, growth rates, years of consecutive growth

        Use this tool when you need to evaluate a company's financial health,
        compare it to peers, or assess investment quality across multiple dimensions.

        Use the 'query' parameter with a JMESPath expression to filter the response.
        Call get_schema() first to understand the data structure.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug("get_stock_keyratios_called", symbol=normalized, query=query, format=format)

        try:
            client = get_client(ctx)

            keyratios = await client.stocks.get_keyratios(normalized)

            # If query provided, apply JMESPath and return result directly
            if query:
                try:
                    result = apply_query(keyratios, query)
                    if isinstance(result, dict):
                        return format_output(result, format) if format == "toon" else result
                    wrapped: dict[str, Any] = {"result": result, "query": query}
                    return format_output(wrapped, format) if format == "toon" else wrapped
                except ValueError as e:
                    raise ToolError(str(e)) from e

            data = keyratios.model_dump(mode="json", exclude_none=True)
            logger.debug("get_stock_keyratios_success", symbol=normalized, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_keyratios_error", symbol=normalized, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_gurus(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get guru (institutional investor) holdings for a stock.

        Returns data about famous investors who hold positions in this stock:
        - Picks: Recent trading activity including buys, sells, and position changes
          - guru: Investor/firm name (e.g., Warren Buffett, BlackRock)
          - action: Trade type (Add, Reduce, New Buy, Sold Out)
          - impact: Position impact percentage
          - price range: Min/max/avg prices during the period
          - current_shares: Shares held after the action
        - Holdings: Current guru positions
          - current_shares: Number of shares held
          - perc_shares: Percentage of company shares owned
          - perc_assets: Percentage of guru's portfolio
          - change: Position change percentage

        Use this tool when you need to see which famous investors own a stock,
        track guru buying/selling activity, or follow institutional investor trends.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug("get_stock_gurus_called", symbol=normalized, format=format)

        try:
            client = get_client(ctx)

            gurus = await client.stocks.get_gurus(normalized)
            data = gurus.model_dump(mode="json", exclude_none=True)
            logger.debug("get_stock_gurus_success", symbol=normalized, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_gurus_error", symbol=normalized, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_executives(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get company executives and directors for a stock.

        Returns a list of company officers and board members:
        - name: Executive name
        - position: Title/role (e.g., 'director, officer: Chief Executive Officer')
        - transaction_date: Date of last insider transaction

        Use this tool when you need to identify company leadership,
        check insider trading activity, or understand corporate governance.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug("get_stock_executives_called", symbol=normalized, format=format)

        try:
            client = get_client(ctx)

            executives = await client.stocks.get_executives(normalized)
            data = executives.model_dump(mode="json", exclude_none=True)
            logger.debug("get_stock_executives_success", symbol=normalized, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_executives_error", symbol=normalized, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_trades_history(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get guru trades history for a stock.

        Returns historical guru trading activity organized by portfolio
        reporting periods:
        - periods: Array of trading activity by date
          - portdate: Portfolio reporting date (YYYY-MM-DD)
          - buy_count: Number of gurus who bought
          - buy_gurus: List of buyers with guru_name and share_change
          - sell_count: Number of gurus who sold
          - sell_gurus: List of sellers with guru_name and share_change

        Use this tool when you need to track guru buying/selling patterns
        over time or identify periods of institutional accumulation/distribution.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug("get_stock_trades_history_called", symbol=normalized, format=format)

        try:
            client = get_client(ctx)

            trades = await client.stocks.get_trades_history(normalized)
            data = trades.model_dump(mode="json", exclude_none=True)
            logger.debug("get_stock_trades_history_success", symbol=normalized, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_trades_history_error", symbol=normalized, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_price_ohlc(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        start_date: Annotated[
            str | None,
            Field(
                default=None,
                description="Start date in YYYYMMDD format (e.g., 20250101). If not provided, returns all available data.",
            ),
        ] = None,
        end_date: Annotated[
            str | None,
            Field(
                default=None,
                description="End date in YYYYMMDD format (e.g., 20251231). If not provided, returns up to current date.",
            ),
        ] = None,
        query: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "JMESPath query to filter/transform the response. "
                    "Examples: 'bars[:5]' (recent 5), 'bars[*].{date: date, close: close}'"
                ),
            ),
        ] = None,
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get OHLC (Open-High-Low-Close) price history for a stock.

        Schema: Call get_schema("OHLCHistory") to see the full schema.

        Returns daily OHLC price bars with volume data:
        - bars: Array of daily price bars
          - date: Trading date (YYYY-MM-DD)
          - open: Opening price
          - high: Highest price of the day
          - low: Lowest price of the day
          - close: Closing price
          - volume: Trading volume
          - unadjusted_close: Unadjusted closing price

        Use this tool when you need historical candlestick/OHLC data for
        technical analysis, charting, or computing price-based indicators.

        Use the 'query' parameter with a JMESPath expression to filter the response.
        Call get_schema() first to understand the data structure.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug(
            "get_stock_price_ohlc_called",
            symbol=normalized,
            start_date=start_date,
            end_date=end_date,
            query=query,
            format=format,
        )

        try:
            client = get_client(ctx)

            ohlc = await client.stocks.get_price_ohlc(
                normalized, start_date=start_date, end_date=end_date
            )

            # If query provided, apply JMESPath and return result directly
            if query:
                try:
                    result = apply_query(ohlc, query)
                    if isinstance(result, dict):
                        return format_output(result, format) if format == "toon" else result
                    wrapped: dict[str, Any] = {"result": result, "query": query}
                    return format_output(wrapped, format) if format == "toon" else wrapped
                except ValueError as e:
                    raise ToolError(str(e)) from e

            data = ohlc.model_dump(mode="json", exclude_none=True)
            logger.debug("get_stock_price_ohlc_success", symbol=normalized, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_price_ohlc_error", symbol=normalized, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_volume(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        start_date: Annotated[
            str | None,
            Field(
                default=None,
                description="Start date in YYYYMMDD format (e.g., 20250101). If not provided, returns all available data.",
            ),
        ] = None,
        end_date: Annotated[
            str | None,
            Field(
                default=None,
                description="End date in YYYYMMDD format (e.g., 20251231). If not provided, returns up to current date.",
            ),
        ] = None,
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get trading volume history for a stock.

        Returns daily trading volume data:
        - data: Array of daily volume points
          - date: Trading date (MM-DD-YYYY)
          - volume: Number of shares traded

        Use this tool when you need to analyze volume patterns,
        identify accumulation/distribution, or study liquidity trends.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug(
            "get_stock_volume_called",
            symbol=normalized,
            start_date=start_date,
            end_date=end_date,
            format=format,
        )

        try:
            client = get_client(ctx)

            volume = await client.stocks.get_volume(
                normalized, start_date=start_date, end_date=end_date
            )
            data = volume.model_dump(mode="json", exclude_none=True)
            logger.debug("get_stock_volume_success", symbol=normalized, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_volume_error", symbol=normalized, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_unadjusted_price(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        start_date: Annotated[
            str | None,
            Field(
                default=None,
                description="Start date in YYYYMMDD format (e.g., 20250101). If not provided, returns all available data.",
            ),
        ] = None,
        end_date: Annotated[
            str | None,
            Field(
                default=None,
                description="End date in YYYYMMDD format (e.g., 20251231). If not provided, returns up to current date.",
            ),
        ] = None,
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get unadjusted (pre-split) price history for a stock.

        Returns daily unadjusted prices:
        - prices: Array of daily price points
          - date: Trading date (MM-DD-YYYY)
          - price: Unadjusted closing price

        Unadjusted prices show the actual historical trading prices without
        adjustments for stock splits or dividends. Use this when you need
        to see the actual price investors paid at a given time, or to
        compare with historical news/events.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug(
            "get_stock_unadjusted_price_called",
            symbol=normalized,
            start_date=start_date,
            end_date=end_date,
            format=format,
        )

        try:
            client = get_client(ctx)

            prices = await client.stocks.get_unadjusted_price(
                normalized, start_date=start_date, end_date=end_date
            )
            data = prices.model_dump(mode="json", exclude_none=True)
            logger.debug("get_stock_unadjusted_price_success", symbol=normalized, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_unadjusted_price_error", symbol=normalized, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_operating_data(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get operating metrics and KPIs for a stock.

        Returns operational data and key performance indicators:
        - metrics: Dictionary of operating metrics by key
          - name: Human-readable metric name
          - key: Metric identifier
          - data: Time series data
            - annual: Annual values by fiscal year (e.g., {"2023-12": 1000000})
            - quarterly: Quarterly values by period (e.g., {"2023-Q4": 250000})

        Common operating metrics include:
        - Revenue per employee, units shipped, active users
        - Production capacity, utilization rates
        - Customer counts, average revenue per user (ARPU)
        - Industry-specific KPIs (e.g., same-store sales, load factor)

        Use this tool when you need to analyze operational efficiency,
        track business KPIs beyond financial statements, or compare
        operating performance across periods.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug("get_stock_operating_data_called", symbol=normalized, format=format)

        try:
            client = get_client(ctx)

            operating_data = await client.stocks.get_operating_data(normalized)
            data = operating_data.model_dump(mode="json", exclude_none=True)
            logger.debug("get_stock_operating_data_success", symbol=normalized, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_operating_data_error", symbol=normalized, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_segments_data(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get business and geographic segment data for a stock.

        Returns revenue breakdown by business segment and geographic region:
        - business: Business segment breakdown
          - annual: Annual revenue by segment and fiscal year
          - quarterly: Quarterly revenue by segment
          - ttm: Trailing twelve months data
          - keys: List of segment names
        - geographic: Geographic segment breakdown
          - annual: Annual revenue by region and fiscal year
          - quarterly: Quarterly revenue by region
          - ttm: Trailing twelve months data
          - keys: List of region names

        Use this tool when you need to understand:
        - Revenue diversification across product lines or services
        - Geographic exposure and international revenue mix
        - Segment growth trends and margin differences
        - Business model composition analysis

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug("get_stock_segments_data_called", symbol=normalized, format=format)

        try:
            client = get_client(ctx)

            segments_data = await client.stocks.get_segments_data(normalized)
            data = segments_data.model_dump(mode="json", exclude_none=True)
            logger.debug("get_stock_segments_data_success", symbol=normalized, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_segments_data_error", symbol=normalized, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_ownership(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        query: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "JMESPath query to filter/transform the response. "
                    "Examples: 'institutional' (just institutional), 'insider' (just insider)"
                ),
            ),
        ] = None,
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get ownership breakdown for a stock.

        Schema: Call get_schema("StockOwnership") to see the full schema.

        Returns current ownership structure including:
        - Shares outstanding
        - Institutional ownership percentage and shares
        - Insider ownership percentage and shares
        - Float percentage

        Use this tool to understand who owns the stock and ownership distribution.

        Use the 'query' parameter with a JMESPath expression to filter the response.
        Call get_schema() first to understand the data structure.
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug("get_stock_ownership_called", symbol=normalized, query=query, format=format)

        try:
            client = get_client(ctx)

            ownership = await client.stocks.get_ownership(normalized)

            # If query provided, apply JMESPath and return result directly
            if query:
                try:
                    result = apply_query(ownership, query)
                    if isinstance(result, dict):
                        return format_output(result, format) if format == "toon" else result
                    wrapped: dict[str, Any] = {"result": result, "query": query}
                    return format_output(wrapped, format) if format == "toon" else wrapped
                except ValueError as e:
                    raise ToolError(str(e)) from e

            data = ownership.model_dump(mode="json", exclude_none=True)
            logger.debug("get_stock_ownership_success", symbol=normalized, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_ownership_error", symbol=normalized, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_indicator_history(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get historical ownership indicator data for a stock.

        Returns time series data including:
        - Historical institutional ownership percentage and shares
        - Historical shares outstanding
        - Historical institution shares held

        Use this tool to analyze ownership trends over time.
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug("get_stock_indicator_history_called", symbol=normalized, format=format)

        try:
            client = get_client(ctx)

            history = await client.stocks.get_indicator_history(normalized)
            data = history.model_dump(mode="json", exclude_none=True)
            logger.debug("get_stock_indicator_history_success", symbol=normalized, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_indicator_history_error", symbol=normalized, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_indicators(
        query: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "JMESPath query to filter/transform the response. "
                    "Examples: 'indicators[:10]' (first 10), 'indicators[*].key' (just keys)"
                ),
            ),
        ] = None,
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get list of available stock indicators.

        Schema: Call get_schema("IndicatorsList") to see the full schema.

        Returns all 240+ available indicators that can be queried for individual stocks.
        Each indicator has:
        - key: The indicator key for API calls (e.g., 'net_income', 'roe')
        - name: Human-readable name

        Use this tool to discover what indicators are available before
        querying specific indicator values with get_stock_indicator.

        Use the 'query' parameter with a JMESPath expression to filter the response.
        Call get_schema() first to understand the data structure.
        """
        logger.debug("get_stock_indicators_called", query=query, format=format)

        try:
            client = get_client(ctx)

            indicators = await client.stocks.get_indicators()

            # If query provided, apply JMESPath and return result directly
            if query:
                try:
                    result = apply_query(indicators, query)
                    if isinstance(result, dict):
                        return format_output(result, format) if format == "toon" else result
                    wrapped: dict[str, Any] = {"result": result, "query": query}
                    return format_output(wrapped, format) if format == "toon" else wrapped
                except ValueError as e:
                    raise ToolError(str(e)) from e

            data = indicators.model_dump(mode="json", exclude_none=True)
            logger.debug("get_stock_indicators_success", format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_indicators_error", error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_indicator(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        indicator_key: Annotated[
            str,
            Field(description="Indicator key (e.g., 'net_income', 'roe', 'gross_margin')"),
        ],
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get time series data for a specific indicator.

        Returns historical values for a specific indicator key.
        Common indicators include:
        - net_income, revenue, gross_profit
        - roe, roa, roic
        - gross_margin, operating_margin, net_margin
        - pettm, ps_ratio, pb_ratio

        Use get_stock_indicators first to see all available indicator keys.
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        if not indicator_key or not indicator_key.strip():
            raise ToolError(
                "Invalid indicator key. Please provide a valid indicator key "
                "(e.g., 'net_income', 'roe'). Use get_stock_indicators to see available options."
            )

        indicator_key = indicator_key.strip().lower()
        logger.debug(
            "get_stock_indicator_called",
            symbol=normalized,
            indicator_key=indicator_key,
            format=format,
        )

        try:
            client = get_client(ctx)

            indicator = await client.stocks.get_indicator(normalized, indicator_key)
            data = indicator.model_dump(mode="json", exclude_none=True)
            logger.debug(
                "get_stock_indicator_success",
                symbol=normalized,
                indicator_key=indicator_key,
                format=format,
            )
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error(
                "get_stock_indicator_error",
                symbol=normalized,
                indicator_key=indicator_key,
                error=str(e),
            )
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_analyst_estimates(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get analyst estimates and ratings for a stock.

        Returns consensus analyst estimates including:
        - current_estimates: Current EPS and revenue estimates
          - eps_current_year: Consensus EPS estimate for current year
          - eps_next_year: Consensus EPS estimate for next year
          - revenue_current_year: Consensus revenue estimate for current year
          - revenue_next_year: Consensus revenue estimate for next year
        - growth_estimates: Expected growth rates
          - eps_growth_current_year: Expected EPS growth for current year
          - eps_growth_next_year: Expected EPS growth for next year
          - revenue_growth_current_year: Expected revenue growth for current year
          - revenue_growth_next_year: Expected revenue growth for next year
        - analyst_coverage: Number of analysts covering the stock
        - target_price: Consensus price target

        Use this tool when you need analyst consensus forecasts, earnings
        expectations, or price targets for investment analysis.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug("get_stock_analyst_estimates_called", symbol=normalized, format=format)

        try:
            client = get_client(ctx)

            estimates = await client.stocks.get_analyst_estimates(normalized)
            data = estimates.model_dump(mode="json", exclude_none=True)
            logger.debug("get_stock_analyst_estimates_success", symbol=normalized, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_analyst_estimates_error", symbol=normalized, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_estimate_history(
        symbol: Annotated[
            str,
            Field(description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"),
        ],
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get historical analyst estimate revisions for a stock.

        Returns historical consensus estimate data showing how analyst
        forecasts have evolved over time:
        - metrics: Dictionary of estimate metrics by key
          - eps_estimate: EPS estimates over time
          - revenue_estimate: Revenue estimates over time
          - periods: Fiscal periods with estimates (annual, quarterly)
            - original: Original estimate when first published
            - current: Current consensus estimate
            - change: Revision from original
            - revision_date: When estimate was last revised
            - num_analysts: Number of analysts contributing

        Use this tool when you need to:
        - Track how analyst expectations have changed over time
        - Identify estimate revisions (upgrades/downgrades)
        - Compare original forecasts vs current consensus
        - Analyze analyst sentiment trends

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        normalized = validate_symbol(symbol)
        if not normalized:
            raise ToolError(
                f"Invalid symbol format: '{symbol}'. "
                "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
            )

        logger.debug("get_stock_estimate_history_called", symbol=normalized, format=format)

        try:
            client = get_client(ctx)

            history = await client.stocks.get_estimate_history(normalized)
            data = history.model_dump(mode="json", exclude_none=True)
            logger.debug("get_stock_estimate_history_success", symbol=normalized, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_estimate_history_error", symbol=normalized, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_stock_news_feed(
        symbol: Annotated[
            str | None,
            Field(
                default=None,
                description="Optional stock ticker to filter news (e.g., AAPL, MSFT). If not provided, returns general market news.",
            ),
        ] = None,
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get latest stock market news feed.

        Returns recent news headlines and articles from GuruFocus covering:
        - Market events and trends
        - Company announcements and analysis
        - Earnings reports and financial news
        - Analyst commentary and ratings

        Each news item includes:
        - date: Publication date/time
        - headline: News headline
        - url: Link to full article

        Use this tool when you need to:
        - Get latest news for a specific stock
        - Monitor market-wide news and events
        - Research recent developments affecting a company
        - Stay updated on financial market trends

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        normalized = None
        if symbol:
            normalized = validate_symbol(symbol)
            if not normalized:
                raise ToolError(
                    f"Invalid symbol format: '{symbol}'. "
                    "Please provide a valid stock ticker symbol (e.g., AAPL, MSFT)."
                )

        logger.debug("get_stock_news_feed_called", symbol=normalized, format=format)

        try:
            client = get_client(ctx)

            news = await client.stocks.get_news_feed(symbol=normalized)
            data = news.model_dump(mode="json", exclude_none=True)
            logger.debug(
                "get_stock_news_feed_success", symbol=normalized, count=news.count, format=format
            )
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_stock_news_feed_error", symbol=normalized, error=str(e))
            raise_api_error(e)
