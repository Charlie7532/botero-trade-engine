"""Schema resources exposing Pydantic model JSON schemas.

These resources allow AI agents to understand the exact structure of data
returned by tools, enabling them to write correct JMESPath queries.
"""

from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel

from gurufocus_api import models

# All exportable model classes from gurufocus_api.models
# Organized by category for discoverability
SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    # Core Stock Data
    "StockSummary": models.StockSummary,
    "StockQuote": models.StockQuote,
    "GeneralInfo": models.GeneralInfo,
    "PriceInfo": models.PriceInfo,
    "QualityScores": models.QualityScores,
    "ValuationMetrics": models.ValuationMetrics,
    "FinancialRatios": models.FinancialRatios,
    "InstitutionalActivity": models.InstitutionalActivity,
    # Financial Statements
    "FinancialStatements": models.FinancialStatements,
    "FinancialPeriod": models.FinancialPeriod,
    # Key Ratios
    "KeyRatios": models.KeyRatios,
    "ProfitabilityRatios": models.ProfitabilityRatios,
    "LiquidityRatios": models.LiquidityRatios,
    "SolvencyRatios": models.SolvencyRatios,
    "EfficiencyRatios": models.EfficiencyRatios,
    "GrowthRatios": models.GrowthRatios,
    "ValuationRatios": models.ValuationRatios,
    "DividendMetrics": models.DividendMetrics,
    "PriceMetrics": models.PriceMetrics,
    "PerShareData": models.PerShareData,
    # Dividends
    "DividendHistory": models.DividendHistory,
    "DividendPayment": models.DividendPayment,
    "CurrentDividend": models.CurrentDividend,
    # Price/Volume History
    "OHLCHistory": models.OHLCHistory,
    "OHLCBar": models.OHLCBar,
    "VolumeHistory": models.VolumeHistory,
    "VolumePoint": models.VolumePoint,
    "PriceHistory": models.PriceHistory,
    "PricePoint": models.PricePoint,
    "UnadjustedPriceHistory": models.UnadjustedPriceHistory,
    "UnadjustedPricePoint": models.UnadjustedPricePoint,
    # Guru/Institutional Data
    "GuruList": models.GuruList,
    "GuruListItem": models.GuruListItem,
    "GuruPicks": models.GuruPicks,
    "GuruPickItem": models.GuruPickItem,
    "GuruHolding": models.GuruHolding,
    "GuruInfo": models.GuruInfo,
    "GuruTrades": models.GuruTrades,
    "GuruTrade": models.GuruTrade,
    "GuruTradesHistory": models.GuruTradesHistory,
    "TradesHistoryPeriod": models.TradesHistoryPeriod,
    "GuruAggregatedPortfolio": models.GuruAggregatedPortfolio,
    "GuruAggregatedHolding": models.GuruAggregatedHolding,
    "StockGurus": models.StockGurus,
    "StockGuruPick": models.StockGuruPick,
    "StockGuruHolding": models.StockGuruHolding,
    # Insider Data
    "InsiderTrades": models.InsiderTrades,
    "InsiderTrade": models.InsiderTrade,
    "InsiderUpdatesResponse": models.InsiderUpdatesResponse,
    "InsiderUpdate": models.InsiderUpdate,
    "InsiderBuysResponse": models.InsiderBuysResponse,
    "InsiderBuyTransaction": models.InsiderBuyTransaction,
    "DoubleBuyResponse": models.DoubleBuyResponse,
    "DoubleBuySignal": models.DoubleBuySignal,
    "TripleBuyResponse": models.TripleBuyResponse,
    "TripleBuySignal": models.TripleBuySignal,
    "ClusterBuyResponse": models.ClusterBuyResponse,
    "ClusterBuySignal": models.ClusterBuySignal,
    # Operating Data
    "OperatingData": models.OperatingData,
    "OperatingMetric": models.OperatingMetric,
    "OperatingMetricData": models.OperatingMetricData,
    "SegmentData": models.SegmentData,
    "SegmentPeriodData": models.SegmentPeriodData,
    # Ownership
    "StockOwnership": models.StockOwnership,
    "OwnershipBreakdown": models.OwnershipBreakdown,
    "OwnershipHistory": models.OwnershipHistory,
    "OwnershipHistoryPoint": models.OwnershipHistoryPoint,
    # Indicators
    "IndicatorsList": models.IndicatorsList,
    "IndicatorDefinition": models.IndicatorDefinition,
    "IndicatorTimeSeries": models.IndicatorTimeSeries,
    "IndicatorDataPoint": models.IndicatorDataPoint,
    # Estimates
    "AnalystEstimates": models.AnalystEstimates,
    "EstimatePeriod": models.EstimatePeriod,
    "GrowthEstimates": models.GrowthEstimates,
    "EstimateHistoryResponse": models.EstimateHistoryResponse,
    "EstimateMetric": models.EstimateMetric,
    "EstimatePeriodData": models.EstimatePeriodData,
    # Executives
    "ExecutiveList": models.ExecutiveList,
    "Executive": models.Executive,
    # News
    "NewsFeedResponse": models.NewsFeedResponse,
    "NewsItem": models.NewsItem,
    # Economic Data
    "EconomicIndicatorsListResponse": models.EconomicIndicatorsListResponse,
    "EconomicIndicatorResponse": models.EconomicIndicatorResponse,
    "EconomicDataPoint": models.EconomicDataPoint,
    "CalendarResponse": models.CalendarResponse,
    "EarningsEvent": models.EarningsEvent,
    "DividendEvent": models.DividendEvent,
    "EconomicEvent": models.EconomicEvent,
    "IPOEvent": models.IPOEvent,
    "SplitEvent": models.SplitEvent,
    # ETF Data
    "ETFListResponse": models.ETFListResponse,
    "ETFInfo": models.ETFInfo,
    "ETFSectorWeightingResponse": models.ETFSectorWeightingResponse,
    "SectorWeighting": models.SectorWeighting,
    "IndustryWeighting": models.IndustryWeighting,
    # Politicians
    "PoliticiansListResponse": models.PoliticiansListResponse,
    "Politician": models.Politician,
    "PoliticianTransactionsResponse": models.PoliticianTransactionsResponse,
    "PoliticianTransaction": models.PoliticianTransaction,
    # Reference Data
    "ExchangeListResponse": models.ExchangeListResponse,
    "ExchangeStocksResponse": models.ExchangeStocksResponse,
    "ExchangeStock": models.ExchangeStock,
    "IndexListResponse": models.IndexListResponse,
    "IndexInfo": models.IndexInfo,
    "IndexStocksResponse": models.IndexStocksResponse,
    "IndexStock": models.IndexStock,
    "CountryCurrencyResponse": models.CountryCurrencyResponse,
    "CountryCurrency": models.CountryCurrency,
    "FundaUpdatedResponse": models.FundaUpdatedResponse,
    "FundaUpdatedStock": models.FundaUpdatedStock,
    # Personal/User Data
    "APIUsageResponse": models.APIUsageResponse,
    "PortfoliosResponse": models.PortfoliosResponse,
    "Portfolio": models.Portfolio,
    "PortfolioDetailResponse": models.PortfolioDetailResponse,
    "PortfolioHolding": models.PortfolioHolding,
    "UserScreenersResponse": models.UserScreenersResponse,
    "UserScreener": models.UserScreener,
    "UserScreenerResultsResponse": models.UserScreenerResultsResponse,
    "ScreenerResultStock": models.ScreenerResultStock,
    # Screener
    "ScreenerResults": models.ScreenerResults,
    "ScreenerStock": models.ScreenerStock,
    "ScreenerRequest": models.ScreenerRequest,
    "ScreenerFilter": models.ScreenerFilter,
}

# Categorized schema listing for discoverability
SCHEMA_CATEGORIES: dict[str, list[str]] = {
    "stock_fundamentals": [
        "StockSummary",
        "StockQuote",
        "FinancialStatements",
        "FinancialPeriod",
        "KeyRatios",
    ],
    "ratios": [
        "ProfitabilityRatios",
        "LiquidityRatios",
        "SolvencyRatios",
        "EfficiencyRatios",
        "GrowthRatios",
        "ValuationRatios",
        "DividendMetrics",
        "PriceMetrics",
        "PerShareData",
    ],
    "price_volume": [
        "OHLCHistory",
        "OHLCBar",
        "VolumeHistory",
        "PriceHistory",
        "UnadjustedPriceHistory",
    ],
    "dividends": [
        "DividendHistory",
        "DividendPayment",
        "CurrentDividend",
    ],
    "guru_institutional": [
        "GuruList",
        "GuruPicks",
        "GuruHolding",
        "GuruTrades",
        "GuruTradesHistory",
        "StockGurus",
    ],
    "insider": [
        "InsiderTrades",
        "InsiderUpdatesResponse",
        "InsiderBuysResponse",
        "DoubleBuyResponse",
        "TripleBuyResponse",
        "ClusterBuyResponse",
    ],
    "operating": [
        "OperatingData",
        "SegmentData",
    ],
    "estimates": [
        "AnalystEstimates",
        "EstimateHistoryResponse",
    ],
    "economic": [
        "EconomicIndicatorsListResponse",
        "EconomicIndicatorResponse",
        "CalendarResponse",
    ],
}


def register_schema_resources(mcp: FastMCP) -> None:
    """Register schema resources for Pydantic model type information.

    These resources expose JSON schemas for all data models, enabling AI agents
    to understand data structures and write correct JMESPath queries.

    Args:
        mcp: The FastMCP server instance to register resources with.
    """

    @mcp.resource("gurufocus://schemas")
    async def list_all_schemas() -> dict[str, Any]:
        """List all available model schemas.

        Returns a categorized list of all schema names that can be queried via
        gurufocus://schemas/{model_name}. Use this to discover available schemas
        before fetching specific ones.
        """
        return {
            "total_schemas": len(SCHEMA_MODELS),
            "categories": SCHEMA_CATEGORIES,
            "all_schemas": sorted(SCHEMA_MODELS.keys()),
            "usage": (
                "Read a specific schema with: gurufocus://schemas/{model_name}\n"
                "Example: gurufocus://schemas/FinancialStatements"
            ),
        }

    @mcp.resource("gurufocus://schemas/{model_name}")
    async def get_schema(model_name: str) -> dict[str, Any]:
        """Get JSON Schema for a specific Pydantic model.

        Use this to understand the exact structure of data returned by tools.
        The schema includes field names, types, descriptions, and constraints.

        This enables you to write correct JMESPath queries to filter the data, e.g.:
        - Know exact field names for JMESPath expressions
        - Understand nested structure for JSON traversal
        - See which fields are optional vs required

        Args:
            model_name: Name of the model (e.g., 'FinancialStatements', 'KeyRatios')

        Returns:
            JSON Schema for the model with metadata
        """
        model_class = SCHEMA_MODELS.get(model_name)

        if model_class is None:
            # Provide helpful error with suggestions
            available = sorted(SCHEMA_MODELS.keys())
            # Find similar names
            lower_name = model_name.lower()
            suggestions = [n for n in available if lower_name in n.lower()][:5]

            error_msg = f"Unknown model: '{model_name}'."
            if suggestions:
                error_msg += f" Did you mean: {', '.join(suggestions)}?"
            error_msg += " Use gurufocus://schemas to list all available schemas."

            raise ValueError(error_msg)

        schema = model_class.model_json_schema()

        return {
            "model_name": model_name,
            "python_import": f"from gurufocus_api.models import {model_name}",
            "schema": schema,
        }

    @mcp.resource("gurufocus://schemas/category/{category_name}")
    async def get_category_schemas(category_name: str) -> dict[str, Any]:
        """Get all schemas for a specific category.

        Useful for understanding related data models together.

        Args:
            category_name: Category name (e.g., 'stock_fundamentals', 'ratios')

        Returns:
            All schemas in the category
        """
        if category_name not in SCHEMA_CATEGORIES:
            available = sorted(SCHEMA_CATEGORIES.keys())
            raise ValueError(
                f"Unknown category: '{category_name}'. Available categories: {', '.join(available)}"
            )

        model_names = SCHEMA_CATEGORIES[category_name]
        schemas = {}

        for name in model_names:
            model_class = SCHEMA_MODELS.get(name)
            if model_class:
                schemas[name] = model_class.model_json_schema()

        return {
            "category": category_name,
            "model_count": len(schemas),
            "schemas": schemas,
        }
