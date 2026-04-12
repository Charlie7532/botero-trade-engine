"""Personal/User data MCP tools.

Tools for fetching user-specific data from GuruFocus API.
"""

from typing import Annotated, Any

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from gurufocus_api.logging import get_logger

from ..context import get_client
from ..errors import raise_api_error
from ..formatting import OutputFormat, format_output

logger = get_logger(__name__)


def register_personal_tools(mcp: FastMCP) -> None:
    """Register personal/user data tools with the MCP server.

    Args:
        mcp: The FastMCP server instance to register tools with.
    """

    @mcp.tool()
    async def get_api_usage(
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get API usage statistics for the current API token.

        Returns information about your API quota:
        - api_usage: Number of API requests made
        - api_requests_remaining: Number of API requests remaining

        Use this to monitor your API usage and avoid hitting rate limits.
        Note that the result may be cached for up to 5 minutes.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        logger.debug("get_api_usage_called", format=format)

        try:
            client = get_client(ctx)

            result = await client.personal.get_api_usage()
            data = result.model_dump(mode="json", exclude_none=True)
            logger.debug("get_api_usage_success", format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_api_usage_error", error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_user_screeners(
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get the current user's saved stock screeners.

        Returns a list of screeners saved by the user:
        - screeners: List of screener objects
        - count: Total number of screeners

        Each screener includes:
        - id: Unique screener ID
        - name: Screener name
        - short_description: Brief description (if set)
        - note: User notes (if set)
        - is_public: Whether screener is publicly shared
        - is_predefined: Whether it's a built-in screener
        - default_exchanges: List of exchanges to search
        - created_at: Creation timestamp
        - updated_at: Last update timestamp

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        logger.debug("get_user_screeners_called", format=format)

        try:
            client = get_client(ctx)

            result = await client.personal.get_user_screeners()
            data = result.model_dump(mode="json", exclude_none=True)
            logger.debug("get_user_screeners_success", format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_user_screeners_error", error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_user_screener_results(
        screener_id: Annotated[
            int,
            Field(description="The screener ID to get results for"),
        ],
        page: Annotated[
            int,
            Field(default=1, description="Page number (default: 1)"),
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
        """Get results from a user screener.

        Returns stocks that match the screener criteria:
        - screener_id: The screener ID
        - page: Current page number
        - stocks: List of matching stocks
        - count: Number of stocks on this page

        Each stock includes:
        - symbol: Stock ticker
        - exchange: Exchange code
        - company: Company name
        - sector: Sector classification
        - industry: Industry classification

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        logger.debug(
            "get_user_screener_results_called",
            screener_id=screener_id,
            page=page,
            format=format,
        )

        try:
            client = get_client(ctx)

            result = await client.personal.get_user_screener_results(screener_id, page=page)
            data = result.model_dump(mode="json", exclude_none=True)
            logger.debug(
                "get_user_screener_results_success",
                screener_id=screener_id,
                page=page,
                count=result.count,
            )
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error(
                "get_user_screener_results_error",
                screener_id=screener_id,
                page=page,
                error=str(e),
            )
            raise_api_error(e)

    # NOTE: Portfolio endpoints commented out as of 2025-12-29.
    # The V2 API endpoint (https://api.gurufocus.com/v2/{token}/portfolios) is not
    # returning a valid response. Re-enable when the API is fixed.
    #
    # @mcp.tool()
    # async def get_portfolios(
    #     format: Annotated[
    #         OutputFormat,
    #         Field(
    #             default="toon",
    #             description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
    #         ),
    #     ] = "toon",
    #     ctx: Context = None,  # type: ignore[assignment]
    # ) -> str | dict[str, Any]:
    #     """Get the current user's portfolios.
    #
    #     Returns a list of user portfolios:
    #     - portfolios: List of portfolio objects
    #     - count: Total number of portfolios
    #
    #     Each portfolio includes:
    #     - id: Portfolio ID (use with get_portfolio_detail)
    #     - name: Portfolio name
    #     - currency: Portfolio currency (USD, EUR, etc.)
    #     - note: User notes
    #
    #     The 'format' parameter controls output encoding:
    #     - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
    #     - 'json': Standard JSON format for debugging or compatibility
    #     """
    #     logger.debug("get_portfolios_called", format=format)
    #
    #     try:
    #         client = get_client(ctx)
    #
    #         result = await client.personal.get_portfolios()
    #         data = result.model_dump(mode="json", exclude_none=True)
    #         logger.debug("get_portfolios_success", count=result.count)
    #         return format_output(data, format)
    #
    #     except ToolError:
    #         raise
    #     except Exception as e:
    #         logger.error("get_portfolios_error", error=str(e))
    #         raise_api_error(e)
    #
    # @mcp.tool()
    # async def get_portfolio_detail(
    #     portfolio_id: Annotated[
    #         int,
    #         Field(description="The portfolio ID to get details for"),
    #     ],
    #     format: Annotated[
    #         OutputFormat,
    #         Field(
    #             default="toon",
    #             description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
    #         ),
    #     ] = "toon",
    #     ctx: Context = None,  # type: ignore[assignment]
    # ) -> str | dict[str, Any]:
    #     """Get detailed portfolio information including all holdings.
    #
    #     Returns portfolio detail:
    #     - portfolio_id: Portfolio ID
    #     - name: Portfolio name
    #     - currency: Portfolio currency
    #     - total_value: Total current market value
    #     - total_cost: Total cost basis
    #     - total_gain_loss: Total gain/loss
    #     - holdings: List of holdings
    #     - holdings_count: Number of holdings
    #
    #     Each holding includes:
    #     - symbol: Stock ticker
    #     - exchange: Exchange code
    #     - company: Company name
    #     - shares: Number of shares
    #     - cost_basis: Cost basis per share
    #     - current_price: Current price
    #     - market_value: Current market value
    #     - gain_loss: Gain/loss amount
    #     - gain_loss_percent: Gain/loss percentage
    #     - weight: Weight in portfolio (%)
    #
    #     The 'format' parameter controls output encoding:
    #     - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
    #     - 'json': Standard JSON format for debugging or compatibility
    #     """
    #     logger.debug("get_portfolio_detail_called", portfolio_id=portfolio_id, format=format)
    #
    #     try:
    #         client = get_client(ctx)
    #
    #         result = await client.personal.get_portfolio_detail(portfolio_id)
    #         data = result.model_dump(mode="json", exclude_none=True)
    #         logger.debug(
    #             "get_portfolio_detail_success",
    #             portfolio_id=portfolio_id,
    #             holdings_count=result.holdings_count,
    #         )
    #         return format_output(data, format)
    #
    #     except ToolError:
    #         raise
    #     except Exception as e:
    #         logger.error("get_portfolio_detail_error", portfolio_id=portfolio_id, error=str(e))
    #         raise_api_error(e)

    @mcp.tool()
    async def get_usage_estimate(
        ctx: Context = None,  # type: ignore[assignment]
    ) -> dict[str, Any]:
        """Get estimated API usage WITHOUT making an API call.

        Returns the locally tracked estimate of remaining API calls.
        This tool does NOT consume an API call - it uses cached/tracked values.

        Returns:
        - remaining_estimate: Estimated remaining API calls (null if never synced)
        - local_consumed_since_sync: Calls made since last sync
        - last_sync_timestamp: Unix timestamp of last sync with API
        - tracking_enabled: Whether usage tracking is enabled
        - note: Explanation of estimate accuracy

        Use this tool to check quota without consuming calls. For accurate
        current data, use get_api_usage() instead (which makes an API call).

        Note: The estimate accuracy depends on:
        1. How recently get_api_usage() was called (syncs the tracker)
        2. Whether all API calls go through this client (external calls not tracked)
        """
        logger.debug("get_usage_estimate_called")

        try:
            client = get_client(ctx)

            # Check if usage tracker is initialized
            tracker = getattr(client, "_usage_tracker", None)
            if tracker is None:
                logger.debug("get_usage_estimate_no_tracker")
                return {
                    "remaining_estimate": None,
                    "local_consumed_since_sync": 0,
                    "last_sync_timestamp": None,
                    "tracking_enabled": False,
                    "note": "Usage tracking not initialized. Call get_api_usage() to sync.",
                }

            remaining = await tracker.get_remaining()
            logger.debug(
                "get_usage_estimate_success",
                remaining_estimate=remaining,
                local_consumed=tracker._local_consumed,
            )

            return {
                "remaining_estimate": remaining,
                "local_consumed_since_sync": tracker._local_consumed,
                "last_sync_timestamp": tracker._last_sync if tracker._last_sync > 0 else None,
                "tracking_enabled": tracker._config.enabled,
                "note": "This is an estimate. Call get_api_usage() for accurate data.",
            }

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_usage_estimate_error", error=str(e))
            raise_api_error(e)
