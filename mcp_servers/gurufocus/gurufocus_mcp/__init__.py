"""GuruFocus MCP Server.

An MCP server exposing GuruFocus financial data to AI assistants.
"""

from .config import MCPServerSettings, get_settings
from .errors import (
    MCPError,
    handle_api_error,
    safe_float,
    safe_get,
    safe_int,
    validate_symbol,
    validate_symbols,
    with_error_handling,
)
from .formatting import (
    OutputFormat,
    format_output,
    toon_decode,
    toon_encode,
)
from .resources import register_stock_resources
from .server import create_server, main, mcp

__version__ = "0.1.0"
__all__ = [
    "MCPError",
    "MCPServerSettings",
    "OutputFormat",
    "__version__",
    "create_server",
    "format_output",
    "get_settings",
    "handle_api_error",
    "main",
    "mcp",
    "register_stock_resources",
    "safe_float",
    "safe_get",
    "safe_int",
    "toon_decode",
    "toon_encode",
    "validate_symbol",
    "validate_symbols",
    "with_error_handling",
]
