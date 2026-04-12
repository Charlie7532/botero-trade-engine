"""MCP Resources for GuruFocus data.

Resources are application-controlled contextual data (schemas, documentation).
"""

from .schemas import register_schema_resources
from .stocks import register_stock_resources

__all__ = ["register_schema_resources", "register_stock_resources"]
