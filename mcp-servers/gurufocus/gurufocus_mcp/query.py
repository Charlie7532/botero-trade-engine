"""JMESPath query support for filtering and transforming tool responses.

JMESPath is a query language for JSON that allows extracting and
transforming data. It's the same query language used by AWS CLI's
--query parameter.

See: https://jmespath.org/tutorial.html
"""

from typing import Any

import jmespath  # type: ignore[import-untyped]
from jmespath.exceptions import JMESPathError  # type: ignore[import-untyped]
from pydantic import BaseModel


def apply_query(data: BaseModel | dict[str, Any], query: str | None) -> Any:
    """Apply a JMESPath query to data.

    Args:
        data: Pydantic model or dict to query
        query: JMESPath query string, or None to return data as-is

    Returns:
        Query result (can be dict, list, scalar, or None)

    Raises:
        ValueError: If the query is invalid JMESPath syntax
    """
    # Convert to dict if needed
    if isinstance(data, BaseModel):
        data_dict = data.model_dump(mode="json", exclude_none=True)
    else:
        data_dict = data

    # No query - return full data
    if query is None:
        return data_dict

    # Apply JMESPath query
    try:
        result = jmespath.search(query, data_dict)
        return result
    except JMESPathError as e:
        raise ValueError(f"Invalid JMESPath query: {e}") from e


# Example queries for documentation and hints
QUERY_EXAMPLES = {
    "financials": {
        "recent_5_periods": "periods[:5]",
        "revenue_trend": "periods[*].{period: period, revenue: revenue}",
        "margins_only": "periods[*].{period: period, gross_margin: gross_margin, operating_margin: operating_margin, net_margin: net_margin}",
        "per_share_data": "periods[*].{period: period, eps: eps, revenue_per_share: revenue_per_share, fcf_per_share: fcf_per_share}",
    },
    "keyratios": {
        "quality_scores": "{gf_score: gf_score, piotroski: piotroski_score, financial_strength: financial_strength, profitability_rank: profitability_rank}",
        "profitability": "profitability",
        "valuation": "valuation",
        "growth_rates": "growth",
    },
    "ohlc": {
        "recent_5_bars": "bars[:5]",
        "close_prices": "bars[*].{date: date, close: close}",
        "volume_data": "bars[*].{date: date, volume: volume}",
        "price_range": "bars[*].{date: date, high: high, low: low}",
    },
}
