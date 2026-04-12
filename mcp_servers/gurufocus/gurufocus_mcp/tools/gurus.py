"""Guru/institutional investor MCP tools.

Tools for fetching guru portfolio and trading data from GuruFocus API.
"""

from typing import Annotated, Any

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from gurufocus_api.logging import get_logger

from ..context import get_client
from ..errors import raise_api_error
from ..formatting import OutputFormat, format_output
from ..query import apply_query

logger = get_logger(__name__)


def register_guru_tools(mcp: FastMCP) -> None:
    """Register guru/institutional investor tools with the MCP server.

    Args:
        mcp: The FastMCP server instance to register tools with.
    """

    @mcp.tool()
    async def get_gurulist(
        query: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "JMESPath query to filter/transform the response. "
                    "Examples: 'us_gurus[:10]' (first 10), 'us_gurus[*].name' (just names)"
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
        """Get list of all tracked institutional gurus (Super Investors).

        Schema: Call get_schema("GuruList") to see the full schema.

        Returns a comprehensive list of tracked institutional investors:
        - us_gurus: US institutional gurus (13F filers)
        - plus_gurus: GuruFocus Plus category gurus
        - total_count: Total number of gurus

        Each guru includes:
        - guru_id: Unique identifier for API calls
        - name: Guru or fund name
        - firm: Investment firm/company
        - num_stocks: Number of stocks in portfolio
        - equity: Portfolio value in millions USD
        - turnover: Portfolio turnover rate (%)
        - last_updated: Date of last portfolio update
        - cik: SEC CIK number

        Note: This is a large dataset (~2.6MB) - cache is recommended.

        Use the 'query' parameter with a JMESPath expression to filter the response.
        Call get_schema() first to understand the data structure.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        logger.debug("get_gurulist_called", query=query, format=format)

        try:
            client = get_client(ctx)

            gurulist = await client.gurus.get_gurulist()

            # If query provided, apply JMESPath and return result directly
            if query:
                try:
                    result = apply_query(gurulist, query)
                    if isinstance(result, dict):
                        return format_output(result, format) if format == "toon" else result
                    wrapped: dict[str, Any] = {"result": result, "query": query}
                    return format_output(wrapped, format) if format == "toon" else wrapped
                except ValueError as e:
                    raise ToolError(str(e)) from e

            data = gurulist.model_dump(mode="json", exclude_none=True)
            logger.debug("get_gurulist_success", format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_gurulist_error", error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_guru_picks(
        guru_id: Annotated[
            str,
            Field(description="Guru ID (numeric identifier from gurulist)"),
        ],
        start_date: Annotated[
            str,
            Field(
                default="all",
                description="Start date filter (YYYY-MM-DD format) or 'all' for all picks",
            ),
        ] = "all",
        page: Annotated[
            int,
            Field(default=1, description="Page number for paginated results"),
        ] = 1,
        query: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "JMESPath query to filter/transform the response. "
                    "Examples: 'picks[:10]' (first 10), 'picks[*].symbol' (just symbols)"
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
        """Get a guru's stock picks and trading activity.

        Schema: Call get_schema("GuruPicks") to see the full schema.

        Returns the guru's stock picks with detailed transaction info:
        - guru_id: Guru identifier
        - guru_name: Guru or fund name
        - picks: List of stock picks

        Each pick includes:
        - symbol: Stock ticker
        - company: Company name
        - action: Trade action (Buy, Sell, Add, Reduce)
        - trade_type: 'quarterly' (13F) or 'realtime' (Form 4)
        - date: Transaction date
        - current_shares: Shares held after transaction
        - share_change: Change in shares
        - price: Current stock price
        - rec_price: Price at recommendation

        Use guru_id from get_gurulist to look up specific investors.
        Common guru IDs: 7 (Warren Buffett/Berkshire), 4 (Bill Ackman).

        Use the 'query' parameter with a JMESPath expression to filter the response.
        Call get_schema() first to understand the data structure.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        logger.debug(
            "get_guru_picks_called",
            guru_id=guru_id,
            start_date=start_date,
            page=page,
            query=query,
            format=format,
        )

        try:
            client = get_client(ctx)

            picks = await client.gurus.get_guru_picks(guru_id, start_date, page)

            # If query provided, apply JMESPath and return result directly
            if query:
                try:
                    result = apply_query(picks, query)
                    if isinstance(result, dict):
                        return format_output(result, format) if format == "toon" else result
                    wrapped: dict[str, Any] = {"result": result, "query": query}
                    return format_output(wrapped, format) if format == "toon" else wrapped
                except ValueError as e:
                    raise ToolError(str(e)) from e

            data = picks.model_dump(mode="json", exclude_none=True)
            logger.debug("get_guru_picks_success", guru_id=guru_id, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_guru_picks_error", guru_id=guru_id, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_guru_aggregated(
        guru_id: Annotated[
            str,
            Field(description="Guru ID (numeric identifier from gurulist)"),
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
        """Get a guru's complete aggregated portfolio.

        Returns the guru's full portfolio with summary and all holdings:

        Summary includes:
        - firm: Investment firm name
        - num_new: Number of new positions this quarter
        - number_of_stocks: Total stocks in portfolio
        - equity: Total portfolio value (millions USD)
        - turnover: Portfolio turnover rate (%)
        - date: Portfolio snapshot date

        Each holding includes:
        - symbol: Stock ticker
        - company: Company name
        - shares: Number of shares held
        - price: Current stock price
        - value: Position value (thousands USD)
        - position: Portfolio weight (%)
        - change: Change from prior quarter (or 'New Buy'/'Sold Out')
        - impact: Impact on portfolio (%)
        - sector/industry: Classification

        Use guru_id from get_gurulist to look up specific investors.
        Common guru IDs: 7 (Warren Buffett/Berkshire), 4 (Bill Ackman).

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        logger.debug("get_guru_aggregated_called", guru_id=guru_id, format=format)

        try:
            client = get_client(ctx)

            portfolio = await client.gurus.get_guru_aggregated(guru_id)
            data = portfolio.model_dump(mode="json", exclude_none=True)
            logger.debug("get_guru_aggregated_success", guru_id=guru_id, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_guru_aggregated_error", guru_id=guru_id, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_guru_realtime_picks(
        page: Annotated[
            int,
            Field(default=1, description="Page number for paginated results"),
        ] = 1,
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get real-time guru trading activity across all tracked investors.

        Returns recent trading activity from Form 4 filings (real-time):
        - picks: List of recent trades
        - total: Total number of picks
        - current_page: Current page number
        - last_page: Last page number

        Each pick includes:
        - symbol: Stock ticker
        - company: Company name
        - guru_name: Guru who made the trade
        - action: Trade action (Add, Reduce, Buy, Sell)
        - date: Portfolio date
        - shares: Current shares held
        - price: Current stock price
        - price_avg: Average purchase price
        - impact: Portfolio impact (%)
        - comment: Action description

        This tool shows the most recent guru trades across all tracked
        investors. Use it to monitor what super investors are buying/selling.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        logger.debug("get_guru_realtime_picks_called", page=page, format=format)

        try:
            client = get_client(ctx)

            realtime = await client.gurus.get_realtime_picks(page=page)
            data = realtime.model_dump(mode="json", exclude_none=True)
            logger.debug("get_guru_realtime_picks_success", page=page, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_guru_realtime_picks_error", page=page, error=str(e))
            raise_api_error(e)
