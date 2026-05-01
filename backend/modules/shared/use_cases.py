# Re-export for backward compatibility
from backend.modules.shared.application.use_cases.shared_use_cases import (
    fetch_market_data, place_order, get_portfolio,
)
from backend.modules.simulation.infrastructure.backtest_runner import run_backtest

__all__ = ["fetch_market_data", "place_order", "get_portfolio", "run_backtest"]

