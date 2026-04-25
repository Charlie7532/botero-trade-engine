# Add a New Broker Adapter

Guide me through adding a new broker integration to the Botero Trade engine.

## Context

The broker adapter pattern lives in `backend/infrastructure/brokers/`.
All brokers implement the abstract `BrokerAdapter` from `backend/infrastructure/brokers/base.py`.
The `BrokerAdapter` interface requires these methods:

```python
broker(self) -> Broker                                    # property
get_price(self, symbol: str) -> float
get_bars(self, symbol, timeframe, start, end) -> list[Bar]
place_order(self, order: Order) -> Order
cancel_order(self, order_id: str) -> bool
get_portfolio(self) -> Portfolio
is_connected(self) -> bool
```

Domain entities are in `backend/domain/entities.py`: `Bar`, `Order`, `Portfolio`, `Position`, `Broker` (enum).

## Steps

1. Ask the user: **What broker are they adding?** (name, Python SDK to use, auth method)

2. Add the broker to the `Broker` enum in `backend/domain/entities.py`:
```python
class Broker(str, Enum):
    INTERACTIVE_BROKERS = "interactive_brokers"
    ALPACA = "alpaca"
    {NEW_BROKER} = "{new_broker_value}"   # ← add here
```

3. Create the adapter at `backend/infrastructure/brokers/{broker_name}_adapter.py`

4. Add the adapter to the `_brokers` registry in all three routers:
   - `backend/api/routers/market_data.py`
   - `backend/api/routers/portfolio.py`
   - `backend/api/routers/strategy.py`

5. Add credentials to `.env.example`

6. Add the SDK to `backend/requirements.txt`

7. Show the user how to test: `curl http://localhost:8000/api/portfolio/{new_broker_value}`

## Important rules

- The adapter must never raise unhandled exceptions — wrap broker SDK calls in try/except
- `is_connected()` must be safe to call at any time without side effects
- `get_portfolio()` must return a valid `Portfolio` even if positions list is empty
- All methods are `async` — use `await` for any I/O

Now ask the user which broker they want to add and implement it.
