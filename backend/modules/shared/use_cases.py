from datetime import datetime
from typing import Type

import backtrader as bt

from domain.entities import BacktestResult, Bar, Broker, Order, Portfolio, Trade
from modules.simulation.infrastructure.backtrader.data_feeds import create_data_feed
from modules.simulation.infrastructure.backtrader.base_strategy import BaseStrategy
from modules.execution.infrastructure.brokers.base import BrokerAdapter


async def fetch_market_data(
    broker: BrokerAdapter,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> list[Bar]:
    """Fetch historical bars from any broker via the adapter interface."""
    return await broker.get_bars(symbol, timeframe, start, end)


async def place_order(broker: BrokerAdapter, order: Order) -> Order:
    """Submit an order through the given broker adapter."""
    return await broker.place_order(order)


async def get_portfolio(broker: BrokerAdapter) -> Portfolio:
    """Retrieve the current portfolio state from the given broker."""
    return await broker.get_portfolio()


def run_backtest(
    strategy_class: Type[BaseStrategy],
    bars: list[Bar],
    initial_cash: float = 100_000.0,
    commission: float = 0.001,
    strategy_params: dict | None = None,
) -> BacktestResult:
    """Run a Backtrader backtest for the given strategy and bar data.

    Args:
        strategy_class: A subclass of BaseStrategy to run.
        bars: Historical OHLCV bars (from any broker adapter).
        initial_cash: Starting cash for the simulation.
        commission: Per-trade commission as a fraction (0.001 = 0.1%).
        strategy_params: Optional kwargs forwarded to the strategy.

    Returns:
        BacktestResult with performance metrics and trade log.
    """
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=commission)

    feed = create_data_feed(bars)
    cerebro.adddata(feed)

    params = strategy_params or {}
    cerebro.addstrategy(strategy_class, **params)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

    results = cerebro.run()
    strategy_instance = results[0]

    final_value = cerebro.broker.getvalue()
    analyzers = strategy_instance.analyzers

    metrics = {
        "sharpe_ratio": analyzers.sharpe.get_analysis().get("sharperatio"),
        "max_drawdown_pct": analyzers.drawdown.get_analysis().get("max", {}).get("drawdown"),
        "total_return_pct": analyzers.returns.get_analysis().get("rtot"),
    }

    symbol = bars[0].symbol if bars else "unknown"
    trades = [
        Trade(
            order_id=f"bt-{i}",
            symbol=symbol,
            side=t["type"],
            quantity=t["size"],
            price=t["price"],
            broker=Broker.ALPACA,
            executed_at=datetime.fromisoformat(t["date"]) if isinstance(t["date"], str) else t["date"],
        )
        for i, t in enumerate(strategy_instance.trades_log)
    ]

    return BacktestResult(
        strategy_name=strategy_class.__name__,
        symbol=symbol,
        start_date=bars[0].timestamp,
        end_date=bars[-1].timestamp,
        initial_cash=initial_cash,
        final_value=final_value,
        trades=trades,
        metrics=metrics,
    )
