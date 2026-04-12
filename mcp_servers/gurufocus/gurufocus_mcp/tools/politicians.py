"""Politician trading data MCP tools.

Tools for fetching politician stock transactions from GuruFocus API.
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


def register_politician_tools(mcp: FastMCP) -> None:
    """Register politician trading tools with the MCP server.

    Args:
        mcp: The FastMCP server instance to register tools with.
    """

    @mcp.tool()
    async def get_politicians(
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get list of all tracked politicians (senators and representatives).

        Returns a list of US politicians whose stock transactions are tracked:
        - politicians: List of politician records
        - count: Total number of politicians

        Each politician includes:
        - id: Unique identifier for filtering transactions
        - full_name: Politician's full name
        - position: 'senator' or 'representative'
        - district: Congressional district (e.g., 'CA12', 'TX00' for senators)
        - state: Two-letter state code
        - party: Political party (Democrat, Republican, Independent)

        Use the politician 'id' with get_politician_transactions to filter
        transactions for a specific politician.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        logger.debug("get_politicians_called", format=format)

        try:
            client = get_client(ctx)

            politicians = await client.politicians.get_politicians()
            data = politicians.model_dump(mode="json", exclude_none=True)
            logger.debug("get_politicians_success", format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_politicians_error", error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_politician_transactions(
        page: Annotated[
            int,
            Field(default=1, description="Page number for paginated results"),
        ] = 1,
        politician_id: Annotated[
            int | None,
            Field(
                default=None, description="Filter by specific politician ID (from get_politicians)"
            ),
        ] = None,
        asset_type: Annotated[
            str | None,
            Field(default=None, description="Filter by asset type"),
        ] = None,
        sort: Annotated[
            str | None,
            Field(default=None, description="Field to sort by (e.g., 'transaction_date')"),
        ] = None,
        order: Annotated[
            Literal["asc", "desc"] | None,
            Field(default=None, description="Sort order: 'asc' or 'desc'"),
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
        """Get politician stock transactions with optional filters.

        Returns paginated stock transactions by US politicians:
        - transactions: List of transaction records
        - count: Number of transactions on this page
        - current_page: Current page number
        - last_page: Last available page
        - total: Total number of transactions

        Each transaction includes:
        Stock information:
        - symbol: Stock ticker
        - company: Company name
        - exchange: Exchange (NAS, NYSE, etc.)
        - asset_class: Asset type (Common Stock, etc.)

        Transaction details:
        - trans_type: Transaction type (purchase, sale_full, sale_partial, exchange)
        - amount: Transaction amount range (e.g., '$15,001 - $50,000')
        - disclosure_date: When transaction was disclosed
        - transaction_date: When transaction occurred

        Option details (if applicable):
        - option_type: 'call' or 'put' if option transaction
        - strike_price: Option strike price
        - expiration_date: Option expiration date

        Politician information:
        - politician_id: Politician ID
        - politician_name: Politician name
        - position: 'senator' or 'representative'
        - state: Two-letter state code
        - party: Political party

        Use politician_id filter to track a specific politician's trades.
        Use get_politicians to find politician IDs.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        logger.debug(
            "get_politician_transactions_called",
            page=page,
            politician_id=politician_id,
            format=format,
        )

        try:
            client = get_client(ctx)

            transactions = await client.politicians.get_transactions(
                page=page,
                politician_id=politician_id,
                asset_type=asset_type,
                sort=sort,
                order=order,
            )
            data = transactions.model_dump(mode="json", exclude_none=True)
            logger.debug("get_politician_transactions_success", page=page, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_politician_transactions_error", page=page, error=str(e))
            raise_api_error(e)
