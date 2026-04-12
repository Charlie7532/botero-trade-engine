"""Stock-related MCP resources.

Resources providing schema and documentation for stock data.
"""

from fastmcp import FastMCP


def register_stock_resources(mcp: FastMCP) -> None:
    """Register stock-related resources with the MCP server.

    Args:
        mcp: The FastMCP server instance to register resources with.
    """
    # No resources currently registered.
    # Schema resources were removed as TOON format is now the default output.
    pass
