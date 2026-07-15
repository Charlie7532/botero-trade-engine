"""Schema discovery MCP tools.

Tools for discovering Pydantic model JSON schemas, enabling AI agents to
understand data structures and write correct JMESPath queries.

These tools duplicate the functionality of schema resources as a workaround
for Claude Desktop not supporting MCP resource templates.
"""

from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from pydantic import Field

from gurufocus_api.logging import get_logger

from ..resources.schemas import SCHEMA_CATEGORIES, SCHEMA_MODELS

logger = get_logger(__name__)


def register_schema_tools(mcp: FastMCP) -> None:
    """Register schema discovery tools with the MCP server.

    Args:
        mcp: The FastMCP server instance to register tools with.
    """

    @mcp.tool()
    async def list_schemas() -> dict[str, Any]:
        """List all available model schemas.

        Returns a categorized list of all schema names that can be queried
        via get_schema(). Use this to discover available schemas before
        fetching specific ones.

        Returns:
            - total_schemas: Number of available schemas
            - categories: Map of category name to list of schema names
            - all_schemas: Alphabetized list of all schema names

        Categories include:
            - stock_fundamentals: StockSummary, FinancialStatements, KeyRatios
            - ratios: ProfitabilityRatios, LiquidityRatios, GrowthRatios, etc.
            - price_volume: OHLCHistory, VolumeHistory, PriceHistory
            - dividends: DividendHistory, CurrentDividend
            - guru_institutional: GuruList, GuruTrades, StockGurus
            - insider: InsiderTrades, ClusterBuyResponse
            - operating: OperatingData, SegmentData
            - estimates: AnalystEstimates, EstimateHistoryResponse
            - economic: CalendarResponse, EconomicIndicatorResponse
        """
        logger.debug("list_schemas_called")

        return {
            "total_schemas": len(SCHEMA_MODELS),
            "categories": SCHEMA_CATEGORIES,
            "all_schemas": sorted(SCHEMA_MODELS.keys()),
            "usage": "Call get_schema(model_name) to get the JSON schema for a specific model.",
        }

    @mcp.tool()
    async def get_schema(
        model_name: Annotated[
            str,
            Field(
                description=(
                    "Name of the model to get schema for. "
                    "Examples: 'FinancialStatements', 'KeyRatios', 'StockSummary'. "
                    "Use list_schemas() to see all available model names."
                )
            ),
        ],
    ) -> dict[str, Any]:
        """Get JSON Schema for a specific Pydantic model.

        Use this to understand the exact structure of data returned by tools.
        The schema includes field names, types, descriptions, and constraints.

        This enables you to write correct JMESPath queries to filter data:
        - Know exact field names for JMESPath expressions
        - Understand nested structure for JSON traversal
        - See which fields are optional vs required

        Common schemas to query:
        - FinancialStatements: periods[], revenue, net_income, etc.
        - KeyRatios: profitability.roe, liquidity.current_ratio, etc.
        - StockSummary: general, quality, valuation, ratios
        - OHLCHistory: bars[] with open, high, low, close, volume
        - GuruTrades: trades[] with guru_name, action, shares

        Args:
            model_name: Name of the model (case-sensitive)

        Returns:
            - model_name: The requested model name
            - schema: Full JSON Schema with properties, types, descriptions
        """
        logger.debug("get_schema_called", model_name=model_name)

        model_class = SCHEMA_MODELS.get(model_name)

        if model_class is None:
            available = sorted(SCHEMA_MODELS.keys())
            lower_name = model_name.lower()
            suggestions = [n for n in available if lower_name in n.lower()][:5]

            error_msg = f"Unknown model: '{model_name}'."
            if suggestions:
                error_msg += f" Did you mean: {', '.join(suggestions)}?"
            error_msg += " Use list_schemas() to see all available model names."

            raise ValueError(error_msg)

        schema = model_class.model_json_schema()

        return {
            "model_name": model_name,
            "schema": schema,
        }

    @mcp.tool()
    async def get_schemas_by_category(
        category: Annotated[
            Literal[
                "stock_fundamentals",
                "ratios",
                "price_volume",
                "dividends",
                "guru_institutional",
                "insider",
                "operating",
                "estimates",
                "economic",
            ],
            Field(
                description=(
                    "Category of schemas to retrieve. Use list_schemas() to see all categories."
                )
            ),
        ],
    ) -> dict[str, Any]:
        """Get all schemas for a specific category.

        Useful for understanding related data models together. For example,
        get all ratio-related schemas to understand the full KeyRatios structure.

        Categories:
        - stock_fundamentals: Core stock data (StockSummary, FinancialStatements, KeyRatios)
        - ratios: Financial ratios (ProfitabilityRatios, LiquidityRatios, etc.)
        - price_volume: Price/volume history (OHLCHistory, VolumeHistory)
        - dividends: Dividend data (DividendHistory, CurrentDividend)
        - guru_institutional: Guru/fund holdings (GuruList, GuruTrades, StockGurus)
        - insider: Insider trading (InsiderTrades, ClusterBuyResponse)
        - operating: Operating metrics (OperatingData, SegmentData)
        - estimates: Analyst estimates (AnalystEstimates, EstimateHistoryResponse)
        - economic: Economic data (CalendarResponse, EconomicIndicatorResponse)

        Args:
            category: Category name

        Returns:
            - category: The requested category name
            - model_count: Number of schemas in the category
            - schemas: Map of model name to JSON schema
        """
        logger.debug("get_schemas_by_category_called", category=category)

        if category not in SCHEMA_CATEGORIES:
            available = sorted(SCHEMA_CATEGORIES.keys())
            raise ValueError(
                f"Unknown category: '{category}'. Available categories: {', '.join(available)}"
            )

        model_names = SCHEMA_CATEGORIES[category]
        schemas = {}

        for name in model_names:
            model_class = SCHEMA_MODELS.get(name)
            if model_class:
                schemas[name] = model_class.model_json_schema()

        return {
            "category": category,
            "model_count": len(schemas),
            "schemas": schemas,
        }
