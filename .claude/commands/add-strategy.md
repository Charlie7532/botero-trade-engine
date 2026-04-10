# Add a New Trading Strategy

Guide me through adding a new Backtrader trading strategy to the Botero Trade engine.

## Context

Strategies live in `backend/infrastructure/backtrader/strategies/` (create the folder if it doesn't exist).
All strategies extend `BaseStrategy` from `backend/infrastructure/backtrader/base_strategy.py`.
Strategies are registered in `backend/api/routers/strategy.py` in the `_strategy_registry` dict.

`BaseStrategy` already handles:
- Order lifecycle logging via `notify_order()`
- Trade P&L logging via `notify_trade()`
- A `trades_log` list populated automatically
- A `log(message)` helper that prints with date prefix

## Steps

1. Ask the user: **What is the strategy name and what is its logic?** (e.g. SMA crossover, RSI mean reversion, Bollinger Bands breakout)

2. Ask: **What parameters should it expose?** (e.g. period lengths, thresholds)

3. Create the strategy file at `backend/infrastructure/backtrader/strategies/{snake_case_name}.py`:

```python
import backtrader as bt
from infrastructure.backtrader.base_strategy import BaseStrategy

class {ClassName}(BaseStrategy):
    """{Description of the strategy logic}"""

    params = (
        # define tunable parameters here
    )

    def __init__(self):
        super().__init__()
        # define indicators here using bt.indicators.*

    def next(self):
        if self.order:
            return  # wait for pending order to complete

        if not self.position:
            if {buy_condition}:
                self.order = self.buy()
        else:
            if {sell_condition}:
                self.order = self.sell()
```

4. Register it in `backend/api/routers/strategy.py`:

```python
from infrastructure.backtrader.strategies.{snake_case_name} import {ClassName}

_strategy_registry["{registry_key}"] = {ClassName}
```

5. Show the user how to test it via the API:

```bash
curl -X POST http://localhost:8000/api/strategy/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_name": "{registry_key}",
    "symbol": "AAPL",
    "broker": "alpaca",
    "timeframe": "1d",
    "start": "2023-01-01T00:00:00",
    "end": "2024-01-01T00:00:00",
    "initial_cash": 100000,
    "params": {}
  }'
```

## Key Backtrader indicators reference

```python
bt.indicators.SMA(self.data.close, period=self.params.period)
bt.indicators.EMA(self.data.close, period=self.params.period)
bt.indicators.RSI(self.data.close, period=14)
bt.indicators.BollingerBands(self.data.close, period=20, devfactor=2)
bt.indicators.MACD(self.data.close)
bt.indicators.CrossOver(fast_ma, slow_ma)  # returns 1 (cross up), -1 (cross down), 0
bt.indicators.ATR(self.data, period=14)
bt.indicators.Stochastic(self.data)
```

Now ask the user for the strategy details and implement it.
