"""MCP Tools for GuruFocus data.

Tools are model-controlled functions that allow LLMs to fetch financial data.
"""

from .analysis import register_analysis_tools
from .economic import register_economic_tools
from .etfs import register_etf_tools
from .gurus import register_guru_tools
from .insiders import register_insider_tools
from .personal import register_personal_tools
from .politicians import register_politician_tools
from .reference import register_reference_tools
from .schemas import register_schema_tools
from .stocks import register_stock_tools

__all__ = [
    "register_analysis_tools",
    "register_economic_tools",
    "register_etf_tools",
    "register_guru_tools",
    "register_insider_tools",
    "register_personal_tools",
    "register_politician_tools",
    "register_reference_tools",
    "register_schema_tools",
    "register_stock_tools",
]
