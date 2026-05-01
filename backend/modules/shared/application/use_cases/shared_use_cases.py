"""
Shared Use Cases — Thin Delegation Layer
===========================================
Convenience functions for API routers. They depend on
domain ports (BrokerPort), not concrete infrastructure.
"""
from datetime import datetime

from backend.modules.execution.domain.ports.broker_port import BrokerPort
from backend.modules.shared.domain.entities.market_data import Bar
from backend.modules.execution.domain.entities.order_models import Order
from backend.modules.portfolio_management.domain.entities.portfolio_models import Portfolio


async def fetch_market_data(
    broker: BrokerPort,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> list[Bar]:
    """Fetch historical bars from any broker via the port interface."""
    return await broker.get_bars(symbol, timeframe, start, end)


async def place_order(broker: BrokerPort, order: Order) -> Order:
    """Submit an order through the given broker port."""
    return await broker.place_order(order)


async def get_portfolio(broker: BrokerPort) -> Portfolio:
    """Retrieve the current portfolio state from the given broker."""
    return await broker.get_portfolio()

