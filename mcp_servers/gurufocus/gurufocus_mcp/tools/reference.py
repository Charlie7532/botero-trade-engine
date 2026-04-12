"""Reference data MCP tools (exchanges and indexes).

Tools for fetching exchange and index information from GuruFocus API.
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


def register_reference_tools(mcp: FastMCP) -> None:
    """Register reference data tools with the MCP server.

    Args:
        mcp: The FastMCP server instance to register tools with.
    """

    @mcp.tool()
    async def get_exchange_list(
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get list of worldwide stock exchanges grouped by country.

        Returns a map of countries to their stock exchanges:
        - exchanges_by_country: Map of country name to list of exchange codes
        - total_countries: Number of countries with exchanges
        - total_exchanges: Total number of exchanges

        Exchange codes can be used with get_exchange_stocks to list stocks
        on a specific exchange.

        Common exchange codes:
        - USA: NAS (NASDAQ), NYSE (New York Stock Exchange), AMEX
        - UK: LSE (London Stock Exchange)
        - Germany: FRA (Frankfurt), XTER (XETRA)
        - Japan: TSE (Tokyo Stock Exchange)
        - Canada: TSX, TSXV (Toronto Stock Exchange)

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        logger.debug("get_exchange_list_called", format=format)

        try:
            client = get_client(ctx)

            result = await client.reference.get_exchange_list()
            data = result.model_dump(mode="json", exclude_none=True)
            logger.debug("get_exchange_list_success", format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_exchange_list_error", error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_exchange_stocks(
        exchange: Annotated[
            str,
            Field(description="Exchange code (e.g., 'NYSE', 'NAS', 'LSE')"),
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
        """Get all stocks listed on a specific exchange.

        Args:
            exchange: Exchange code from get_exchange_list (e.g., 'NYSE', 'NAS', 'LSE')

        Returns list of stocks on the exchange:
        - exchange: Exchange code
        - stocks: List of stock records
        - count: Number of stocks

        Each stock includes:
        - symbol: Stock ticker symbol
        - exchange: Exchange code
        - company: Company name
        - currency: Trading currency (USD, EUR, GBP, etc.)
        - industry: Industry classification
        - sector: Sector classification
        - subindustry: Sub-industry classification

        Use get_exchange_list to find available exchange codes.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        logger.debug("get_exchange_stocks_called", exchange=exchange, format=format)

        try:
            client = get_client(ctx)

            result = await client.reference.get_exchange_stocks(exchange)
            data = result.model_dump(mode="json", exclude_none=True)
            logger.debug("get_exchange_stocks_success", exchange=exchange, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_exchange_stocks_error", exchange=exchange, error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_index_list(
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get list of worldwide market indexes.

        Returns list of major market indexes:
        - indexes: List of index records
        - count: Number of indexes

        Each index includes:
        - name: Index name (e.g., 'S&P 500', 'Dow 30')
        - symbol: Index symbol (e.g., '^GSPC', '^DJI')

        Use index symbols with get_index_stocks to get constituent stocks.

        Common index symbols:
        - ^GSPC: S&P 500
        - ^DJI: Dow Jones Industrial Average (Dow 30)
        - ^NDX: NASDAQ 100
        - ^RUT: Russell 2000
        - ^FTSE: FTSE 100 (UK)

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        logger.debug("get_index_list_called", format=format)

        try:
            client = get_client(ctx)

            result = await client.reference.get_index_list()
            data = result.model_dump(mode="json", exclude_none=True)
            logger.debug("get_index_list_success", format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_index_list_error", error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_index_stocks(
        index_symbol: Annotated[
            str,
            Field(description="Index symbol (e.g., '^GSPC', '^DJI', '^NDX')"),
        ],
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
        """Get stocks that are constituents of a market index.

        Args:
            index_symbol: Index symbol from get_index_list (e.g., '^GSPC', '^DJI')
            page: Page number for paginated results (default: 1)

        Returns list of constituent stocks:
        - index_symbol: Index symbol
        - stocks: List of stock records
        - count: Number of stocks on this page

        Each stock includes:
        - symbol: Stock ticker symbol
        - exchange: Exchange code (NAS, NYSE, etc.)
        - company: Company name
        - currency: Trading currency
        - industry: Industry classification
        - sector: Sector classification
        - subindustry: Sub-industry classification

        Use get_index_list to find available index symbols.
        Large indexes like S&P 500 may require multiple pages.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        logger.debug("get_index_stocks_called", index_symbol=index_symbol, page=page, format=format)

        try:
            client = get_client(ctx)

            result = await client.reference.get_index_stocks(index_symbol, page=page)
            data = result.model_dump(mode="json", exclude_none=True)
            logger.debug(
                "get_index_stocks_success", index_symbol=index_symbol, page=page, format=format
            )
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error(
                "get_index_stocks_error", index_symbol=index_symbol, page=page, error=str(e)
            )
            raise_api_error(e)

    @mcp.tool()
    async def get_country_currency(
        format: Annotated[
            OutputFormat,
            Field(
                default="toon",
                description="Output format: 'toon' (default, token-efficient) or 'json' (standard)",
            ),
        ] = "toon",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str | dict[str, Any]:
        """Get list of country to currency mappings.

        Returns worldwide country/currency reference data:
        - currencies: List of country/currency records
        - count: Number of countries

        Each country includes:
        - country: Country name
        - country_iso: ISO 3-letter country code (e.g., 'USA', 'GBR')
        - currency: ISO 3-letter currency code (e.g., 'USD', 'GBP', 'EUR')

        Use this to look up which currency is used in a specific country,
        or to map between country codes and currency codes.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        logger.debug("get_country_currency_called", format=format)

        try:
            client = get_client(ctx)

            result = await client.reference.get_country_currency()
            data = result.model_dump(mode="json", exclude_none=True)
            logger.debug("get_country_currency_success", format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_country_currency_error", error=str(e))
            raise_api_error(e)

    @mcp.tool()
    async def get_funda_updated(
        date: Annotated[
            str,
            Field(description="Date in YYYY-MM-DD format (e.g., '2025-01-15')"),
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
        """Get stocks that had fundamentals updated on a specific date.

        Args:
            date: Date in YYYY-MM-DD format

        Returns list of stocks with updated fundamentals:
        - date: The queried date
        - stocks: List of stock records
        - count: Number of stocks with updates

        Each stock includes:
        - symbol: Stock ticker symbol
        - exchange: Exchange code
        - company: Company name

        Use this to track which stocks had new fundamental data published
        on a given date. This is useful for monitoring data freshness.

        Note: Returns an empty list if no fundamentals were updated on that date.

        The 'format' parameter controls output encoding:
        - 'toon': Token-efficient format (30-60% smaller), recommended for AI contexts
        - 'json': Standard JSON format for debugging or compatibility
        """
        logger.debug("get_funda_updated_called", date=date, format=format)

        try:
            client = get_client(ctx)

            result = await client.reference.get_funda_updated(date)
            data = result.model_dump(mode="json", exclude_none=True)
            logger.debug("get_funda_updated_success", date=date, format=format)
            return format_output(data, format)

        except ToolError:
            raise
        except Exception as e:
            logger.error("get_funda_updated_error", date=date, error=str(e))
            raise_api_error(e)
