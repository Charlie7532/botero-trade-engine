"""
Backtest Runner — Infrastructure Adapter
==========================================
Wraps Backtrader (external library) to execute backtests.
This is infrastructure because it depends on a concrete framework (backtrader).

Consumers: API routers call this via the simulation module.
"""
from datetime import datetime

from backend.modules.shared.domain.entities.market_data import Bar


def run_backtest(
    strategy_class,
    bars: list[Bar],
    initial_cash: float = 100_000.0,
    commission: float = 0.001,
    strategy_params: dict | None = None,
):
    """Run a Backtrader backtest for the given strategy and bar data."""
    import backtrader as bt
    from backend._legacy.backtrader.data_feeds import create_data_feed
    from backend.modules.execution.domain.entities.order_models import Broker, Trade
    from backend.modules.simulation.domain.entities.simulation_models import BacktestResult

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
