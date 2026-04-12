"""Context utilities for GuruFocus MCP server.

This module provides helpers for working with FastMCP context in tools.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastmcp import Context
from fastmcp.exceptions import ToolError

if TYPE_CHECKING:
    from gurufocus_api.client import GuruFocusClient


def get_client(ctx: Context) -> GuruFocusClient:
    """Get the GuruFocus client from MCP context.

    This helper extracts the shared client instance from the FastMCP state,
    raising a user-friendly ToolError if not initialized.

    Args:
        ctx: The FastMCP context from the tool call

    Returns:
        The initialized GuruFocusClient instance

    Raises:
        ToolError: If the client is not initialized
    """
    client: GuruFocusClient | None = getattr(ctx.fastmcp, "state", {}).get("client")
    if client is None:
        raise ToolError(
            "GuruFocus client not initialized. "
            "Please ensure GURUFOCUS_API_TOKEN environment variable is set."
        )
    return client
