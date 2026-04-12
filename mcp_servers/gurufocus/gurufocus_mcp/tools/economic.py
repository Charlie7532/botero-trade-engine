"""Economic data MCP tools (indicators and calendar).

Tools for fetching economic indicators and financial calendar data from GuruFocus API.
"""

from typing import Annotated, Any, Literal

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from gurufocus_api.logging import get_logger

from ..context import get_client
from ..errors import raise_api_error
from ..formatting import OutputFormat, format_output

logger = get_logger(__name__)


def register_economic_tools(mcp: FastMCP) -> None:
    """Register economic data tools with the MCP server.

    Args:
        mcp: The FastMCP server instance to register tools with.
    """

    @mcp.tool()
    async def get_economic_indicators(
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get list of available economic indicators.

        Returns a list of economic indicator names that can be queried with
        get_economic_indicator.

        Response includes:
        - indicators: List of indicator names (e.g., 'US GDP', 'Civilian Unemployment Rate')
        - count: Number of available indicators

        Common indicators include:
        - US GDP: Gross Domestic Product
        - 10 Year Treasury Yield: Interest rate benchmark
        - S&P 500 Index: Market benchmark
        - Civilian Unemployment Rate: Labor market indicator
        - Consumer Price Index: Inflation measure
        - Federal Funds Rate: Fed interest rate target
        - US Trade Balance: Import/export difference

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        logger.debug("get_economic_indicators_called", format=format)

        try:
            client = get_client(ctx)

            result = await client.economic.get_indicators_list()
            data = result.model_dump(mode="json", exclude_none=True)
            logger.debug("get_economic_indicators_success", format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_economic_indicators_error", error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_economic_indicator(
        indicator: Annotated[
            str,
            Field(
                description="Name of the economic indicator (e.g., 'US GDP', 'Consumer Price Index')"
            ),
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
        """Get data for a specific economic indicator.

        Args:
            indicator: Name of the indicator from get_economic_indicators
                       (e.g., 'US GDP', 'Consumer Price Index')

        Returns historical time series data for the indicator:
        - name: Indicator name
        - unit: Unit of measurement (e.g., 'Billions of Dollars', 'Percent')
        - frequency: Data frequency (Daily, Monthly, Quarterly, etc.)
        - source: Data source (e.g., 'Bureau of Economic Analysis')
        - data: Time series of data points with date and value

        Use get_economic_indicators to see available indicator names.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        logger.debug("get_economic_indicator_called", indicator=indicator, format=format)

        try:
            client = get_client(ctx)

            result = await client.economic.get_indicator(indicator)
            data = result.model_dump(mode="json", exclude_none=True)
            logger.debug("get_economic_indicator_success", indicator=indicator, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_economic_indicator_error", indicator=indicator, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_financial_calendar(
        date: Annotated[
            str,
            Field(description="Date in YYYY-MM-DD format (e.g., '2025-01-10')"),
        ],
        event_type: Annotated[
            Literal["all", "economic", "ipo", "earning", "dividend", "split"],
            Field(
                default="all",
                description="Type of events to include: 'all', 'economic', 'ipo', 'earning', 'dividend', or 'split'",
            ),
        ] = "all",
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get financial calendar events for a specific date.

        Args:
            date: Date in YYYY-MM-DD format
            event_type: Filter by event type (default: 'all')

        Returns calendar events organized by category:
        - economic: Economic reports and announcements
        - ipo: Initial public offerings
        - earning: Earnings announcements
        - dividend: Dividend events (ex-date, record date, pay date)
        - split: Stock splits

        Economic events include:
        - date: Event date
        - event: Event name (e.g., 'Employment Report')
        - actual: Actual reported value
        - forecast: Consensus forecast
        - previous: Previous period value

        IPO events include:
        - symbol: Stock ticker
        - company: Company name
        - exchange: Exchange code
        - date: IPO date
        - price_range: Expected price range
        - shares: Number of shares offered

        Earnings events include:
        - symbol: Stock ticker
        - company: Company name
        - date: Earnings date
        - time: Timing (before_market, after_market)
        - eps_estimate: EPS estimate

        Dividend events include:
        - symbol: Stock ticker
        - company: Company name
        - declaration_date, ex_date, record_date, pay_date
        - cash_amount: Dividend amount
        - frequency: Payment frequency per year

        Split events include:
        - symbol: Stock ticker
        - company: Company name
        - date: Split date
        - ratio: Split ratio (e.g., '4:1')

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        logger.debug(
            "get_financial_calendar_called", date=date, event_type=event_type, format=format
        )

        try:
            client = get_client(ctx)

            result = await client.economic.get_calendar(date, event_type=event_type)
            data = result.model_dump(mode="json", exclude_none=True)
            logger.debug(
                "get_financial_calendar_success",
                date=date,
                event_type=event_type,
                format=format,
            )
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error(
                "get_financial_calendar_error",
                date=date,
                event_type=event_type,
                error=str(e),
            )
            raise_api_error(e)
