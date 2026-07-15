"""Output formatting utilities for GuruFocus MCP server.

This module provides format conversion for tool outputs, supporting
both JSON and TOON formats for token-efficient responses.
"""

from typing import Any, Literal

try:
    from toon import decode as toon_decode  # type: ignore[import-untyped]
    from toon import encode as toon_encode
except ImportError:
    # Fallback for older versions or if toon is not available
    def toon_encode(data: Any) -> str:
        import json

        return json.dumps(data)

    def toon_decode(data: str) -> Any:
        import json

        return json.loads(data)


__all__ = ["DEFAULT_FORMAT", "OutputFormat", "format_output", "toon_decode", "toon_encode"]

# Type alias for supported output formats
OutputFormat = Literal["toon", "json"]

# Default format when not specified
DEFAULT_FORMAT: OutputFormat = "toon"


def format_output(
    data: dict[str, Any], format: OutputFormat = DEFAULT_FORMAT
) -> str | dict[str, Any]:
    """Format output data in the specified format.

    Args:
        data: Dictionary data to format
        format: Output format - "toon" for token-efficient or "json" for standard

    Returns:
        Formatted output - string for TOON, dict for JSON

    Raises:
        ValueError: If format is not supported
    """
    if format == "json":
        return data

    if format == "toon":
        return str(toon_encode(data))

    # Should not reach here due to Literal type, but defensive
    raise ValueError(f"Unsupported format: {format}")
