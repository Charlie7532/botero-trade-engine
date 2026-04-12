"""Error handling utilities for GuruFocus MCP server.

This module provides error handling decorators and utilities for converting
API exceptions into user-friendly MCP responses.
"""

import asyncio
import functools
from collections.abc import Callable
from typing import Any, NoReturn

from fastmcp.exceptions import ToolError

from gurufocus_api.exceptions import (
    APIError,
    AuthenticationError,
    GuruFocusError,
    InvalidSymbolError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from gurufocus_api.logging import get_logger

logger = get_logger(__name__)


class MCPError:
    """Structured error response for MCP tools."""

    def __init__(
        self,
        error_type: str,
        message: str,
        details: dict[str, Any] | None = None,
        suggestions: list[str] | None = None,
    ) -> None:
        self.error_type = error_type
        self.message = message
        self.details = details or {}
        self.suggestions = suggestions or []

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary format for tool response."""
        result: dict[str, Any] = {
            "error": True,
            "error_type": self.error_type,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        if self.suggestions:
            result["suggestions"] = self.suggestions
        return result


def handle_api_error(error: Exception) -> dict[str, Any]:
    """Convert an API exception to a user-friendly error response.

    Args:
        error: The exception to handle

    Returns:
        Dictionary with error information suitable for tool response
    """
    if isinstance(error, InvalidSymbolError):
        return MCPError(
            error_type="invalid_symbol",
            message=f"The symbol '{error.symbol}' was not found or is invalid.",
            details={"symbol": error.symbol},
            suggestions=[
                "Check that the symbol is spelled correctly",
                "Verify the stock is listed on a supported exchange",
                "Try using the full ticker format (e.g., 'AAPL' for Apple)",
                "For international stocks, include the exchange suffix (e.g., 'BMW.DE')",
            ],
        ).to_dict()

    if isinstance(error, AuthenticationError):
        return MCPError(
            error_type="authentication_error",
            message="API authentication failed. Please check your GuruFocus API token.",
            suggestions=[
                "Verify your GURUFOCUS_API_TOKEN environment variable is set",
                "Ensure your API token has not expired",
                "Check that your subscription level supports this endpoint",
            ],
        ).to_dict()

    if isinstance(error, RateLimitError):
        retry_info = ""
        if error.retry_after:
            retry_info = f" Try again in {error.retry_after} seconds."
        return MCPError(
            error_type="rate_limit",
            message=f"API rate limit exceeded.{retry_info}",
            details={"retry_after": error.retry_after} if error.retry_after else {},
            suggestions=[
                "Wait before making additional requests",
                "Consider upgrading your GuruFocus subscription for higher limits",
                "Batch multiple symbol requests where possible",
            ],
        ).to_dict()

    if isinstance(error, NotFoundError):
        return MCPError(
            error_type="not_found",
            message="The requested data was not found.",
            suggestions=[
                "Verify the symbol or identifier is correct",
                "This data may not be available for the requested entity",
            ],
        ).to_dict()

    if isinstance(error, NetworkError):
        return MCPError(
            error_type="network_error",
            message="Network error occurred while connecting to GuruFocus API.",
            suggestions=[
                "Check your internet connection",
                "The GuruFocus API may be temporarily unavailable",
                "Try the request again in a few moments",
            ],
        ).to_dict()

    if isinstance(error, ValidationError):
        return MCPError(
            error_type="validation_error",
            message="The API response could not be processed.",
            details={"original_error": str(error)},
            suggestions=[
                "This may indicate an API change or data issue",
                "Try the request again",
                "If the problem persists, the data format may have changed",
            ],
        ).to_dict()

    if isinstance(error, APIError):
        return MCPError(
            error_type="api_error",
            message=f"API error: {error.message}",
            details={"status_code": error.status_code} if error.status_code else {},
            suggestions=[
                "Try the request again",
                "If the error persists, check the GuruFocus API status",
            ],
        ).to_dict()

    if isinstance(error, GuruFocusError):
        return MCPError(
            error_type="gurufocus_error",
            message=str(error),
            suggestions=["Try the request again"],
        ).to_dict()

    if isinstance(error, asyncio.TimeoutError):
        return MCPError(
            error_type="timeout",
            message="Request timed out while waiting for API response.",
            suggestions=[
                "The API may be experiencing high load",
                "Try the request again",
                "Consider requesting less data at once",
            ],
        ).to_dict()

    # Generic fallback for unexpected errors
    logger.error(
        "unexpected_error_in_tool_handler", error=str(error), error_type=type(error).__name__
    )
    return MCPError(
        error_type="unexpected_error",
        message="An unexpected error occurred.",
        details={"error_class": type(error).__name__, "error_message": str(error)},
        suggestions=["Try the request again", "If the problem persists, report this issue"],
    ).to_dict()


def raise_api_error(error: Exception) -> NoReturn:
    """Convert an API exception to a ToolError and raise it.

    This function converts GuruFocus API exceptions into FastMCP ToolError
    exceptions with user-friendly messages. It integrates with FastMCP's
    error handling middleware.

    Args:
        error: The exception to convert and raise

    Raises:
        ToolError: Always raises a ToolError with appropriate message
    """
    if isinstance(error, InvalidSymbolError):
        raise ToolError(
            f"The symbol '{error.symbol}' was not found or is invalid. "
            "Please check that the symbol is spelled correctly and the stock "
            "is listed on a supported exchange."
        )

    if isinstance(error, AuthenticationError):
        raise ToolError(
            "API authentication failed. Please check your GuruFocus API token "
            "and ensure your subscription level supports this endpoint."
        )

    if isinstance(error, RateLimitError):
        retry_info = f" Try again in {error.retry_after} seconds." if error.retry_after else ""
        raise ToolError(
            f"API rate limit exceeded.{retry_info} Consider waiting before "
            "making additional requests or upgrading your subscription."
        )

    if isinstance(error, NotFoundError):
        raise ToolError(
            "The requested data was not found. Please verify the symbol or identifier is correct."
        )

    if isinstance(error, NetworkError):
        raise ToolError(
            "Network error occurred while connecting to GuruFocus API. "
            "Please check your internet connection and try again."
        )

    if isinstance(error, ValidationError):
        raise ToolError(
            "The API response could not be processed. This may indicate an "
            "API change or data issue. Please try again."
        )

    if isinstance(error, APIError):
        raise ToolError(f"API error: {error.message}")

    if isinstance(error, GuruFocusError):
        raise ToolError(str(error))

    if isinstance(error, asyncio.TimeoutError):
        raise ToolError(
            "Request timed out while waiting for API response. "
            "The API may be experiencing high load. Please try again."
        )

    # Generic fallback for unexpected errors
    logger.error(
        "unexpected_error_in_tool_handler", error=str(error), error_type=type(error).__name__
    )
    raise ToolError(f"An unexpected error occurred: {type(error).__name__}")


def with_error_handling(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that adds standardized error handling to async tool functions.

    Catches GuruFocus API exceptions and converts them to user-friendly
    error dictionaries. Also handles timeouts and unexpected errors.

    Args:
        func: The async function to wrap

    Returns:
        Wrapped function with error handling
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            return handle_api_error(e)

    return wrapper


def validate_symbol(symbol: str) -> str | None:
    """Validate and normalize a stock symbol.

    Args:
        symbol: The symbol to validate

    Returns:
        Normalized symbol or None if invalid
    """
    if not symbol:
        return None

    # Strip whitespace and convert to uppercase
    normalized = symbol.strip().upper()

    # Basic validation: symbols should be alphanumeric with optional exchange suffix
    # Examples: AAPL, BRK.A, BMW.DE, 0700.HK
    if not normalized:
        return None

    # Check for reasonable length (1-15 characters)
    if len(normalized) > 15:
        return None

    return normalized


def validate_symbols(symbols: list[str], max_count: int = 10) -> tuple[list[str], list[str]]:
    """Validate a list of symbols.

    Args:
        symbols: List of symbols to validate
        max_count: Maximum number of symbols allowed

    Returns:
        Tuple of (valid_symbols, invalid_symbols)
    """
    valid = []
    invalid = []

    for symbol in symbols[:max_count]:
        normalized = validate_symbol(symbol)
        if normalized:
            valid.append(normalized)
        else:
            invalid.append(symbol)

    return valid, invalid


def safe_get(
    data: dict[str, Any] | None,
    *keys: str,
    default: Any = None,
) -> Any:
    """Safely get a nested value from a dictionary.

    Handles None values and missing keys gracefully.

    Args:
        data: Dictionary to retrieve from (can be None)
        *keys: Keys to traverse
        default: Default value if key not found

    Returns:
        The value at the nested key path or default
    """
    if data is None:
        return default

    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default

    return current


def safe_float(value: Any, default: float | None = None) -> float | None:
    """Safely convert a value to float.

    Args:
        value: Value to convert
        default: Default if conversion fails

    Returns:
        Float value or default
    """
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int | None = None) -> int | None:
    """Safely convert a value to int.

    Args:
        value: Value to convert
        default: Default if conversion fails

    Returns:
        Int value or default
    """
    if value is None:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def format_error_for_missing_data(
    field_name: str,
    entity: str = "this stock",
) -> str:
    """Format a message for missing data.

    Args:
        field_name: Name of the missing field
        entity: Description of the entity (e.g., "this stock", "AAPL")

    Returns:
        User-friendly message about missing data
    """
    return f"{field_name} data is not available for {entity}"
