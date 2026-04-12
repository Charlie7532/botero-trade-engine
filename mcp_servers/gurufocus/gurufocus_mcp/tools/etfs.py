"""ETF MCP tools.

Tools for fetching ETF information from GuruFocus API.
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


def register_etf_tools(mcp: FastMCP) -> None:
    """Register ETF tools with the MCP server.

    Args:
        mcp: The FastMCP server instance to register tools with.
    """

    @mcp.tool()
    async def get_etf_list(
        page: Annotated[
            int,
            Field(default=1, description="Page number (default: 1)"),
        ] = 1,
        per_page: Annotated[
            int,
            Field(default=50, description="Items per page (default: 50, max: 100)"),
        ] = 50,
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get paginated list of all ETFs.

        Returns a paginated list of ETFs tracked by GuruFocus:
        - etfs: List of ETF records
        - current_page: Current page number
        - per_page: Items per page
        - last_page: Total number of pages
        - total: Total number of ETFs (typically 6000+)

        Each ETF includes:
        - name: ETF name

        Use pagination to iterate through the full list. With default page size
        of 50 and 6000+ ETFs, there are ~127 pages.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        logger.debug("get_etf_list_called", page=page, per_page=per_page, format=format)

        try:
            client = get_client(ctx)

            result = await client.etfs.get_etf_list(page=page, per_page=per_page)
            data = result.model_dump(mode="json", exclude_none=True)
            logger.debug("get_etf_list_success", page=page, per_page=per_page, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_etf_list_error", page=page, per_page=per_page, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_etf_sector_weighting(
        etf_name: Annotated[
            str,
            Field(description="Full ETF name (e.g., 'Vanguard 500 Index Fund')"),
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
        """Get sector and industry weightings for an ETF.

        Returns the allocation breakdown of the ETF showing how assets are
        distributed across market sectors and industries:

        - name: ETF name
        - sectors: List of sector allocations, each containing:
          - sector: Sector name (e.g., "Technology", "Healthcare")
          - weightings: Date-keyed percentages (e.g., {"2025-09-30": 35.68})
          - industries: List of industries within the sector
            - industry: Industry name (e.g., "Semiconductors", "Software")
            - weightings: Date-keyed percentages

        Use this tool to analyze:
        - ETF sector allocation and diversification
        - Industry-level exposure within sectors
        - Historical weighting changes over time

        Note: ETF names must match exactly as listed in the get_etf_list tool.
        Names with spaces are handled automatically.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        if not etf_name or not etf_name.strip():
            raise ToolError("ETF name is required and cannot be empty.")

        logger.debug("get_etf_sector_weighting_called", etf_name=etf_name, format=format)

        try:
            client = get_client(ctx)

            result = await client.etfs.get_sector_weighting(etf_name)
            data = result.model_dump(mode="json", exclude_none=True)
            logger.debug(
                "get_etf_sector_weighting_success",
                etf_name=etf_name,
                sector_count=len(result.sectors),
                format=format,
            )
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_etf_sector_weighting_error", etf_name=etf_name, error=str(e))
            raise_api_error(e)
