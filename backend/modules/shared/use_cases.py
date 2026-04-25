# Re-export for backward compatibility — canonical location is domain/use_cases/shared_use_cases.py
from backend.modules.shared.domain.use_cases.shared_use_cases import (
    fetch_market_data, place_order, get_portfolio, run_backtest,
)

__all__ = ["fetch_market_data", "place_order", "get_portfolio", "run_backtest"]
