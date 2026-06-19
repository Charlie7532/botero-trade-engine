"""
Buy 1 IBIT (iShares Bitcoin Trust ETF) — Speculative department.
Market order via Alpaca paper trading.
"""
import os, sys, asyncio

api_key = os.getenv("ALPACA_API_KEY", "")
secret_key = os.getenv("ALPACA_SECRET_KEY", "")

if not api_key or not secret_key:
    print("ERROR: ALPACA_API_KEY or ALPACA_SECRET_KEY not set")
    sys.exit(1)

# Use the adapter directly
from backend.modules.execution.infrastructure.brokers.alpaca_adapter import AlpacaAdapter
from backend.modules.execution.domain.entities.order_models import (
    Order, OrderSide, OrderType, Broker,
)

adapter = AlpacaAdapter(api_key=api_key, secret_key=secret_key)

order = Order(
    symbol="IBIT",
    side=OrderSide.BUY,
    order_type=OrderType.MARKET,
    broker=Broker.ALPACA,
    quantity=1,
)

async def execute():
    # 1. Get current price
    try:
        price = await adapter.get_price("IBIT")
        print(f"IBIT current ask: ${price:.2f}")
    except Exception as e:
        print(f"Price fetch warning: {e}")
        price = None

    # 2. Place order
    print(f"\nPlacing MARKET BUY order: 1 x IBIT (Speculative)")
    result = await adapter.place_order(order)
    print(f"  Order ID: {result.order_id}")
    print(f"  Status: {result.status.value}")

    # 3. Verify position
    import time
    time.sleep(2)  # Wait for fill
    portfolio = await adapter.get_portfolio()
    print(f"\nPOST-TRADE PORTFOLIO:")
    print(f"  Cash: ${portfolio.cash:,.2f}")
    for p in portfolio.positions:
        marker = " ◄◄◄" if p.symbol == "IBIT" else ""
        print(
            f"  {p.symbol:>6} | Qty={p.quantity:.2f} | "
            f"Avg=${p.avg_cost:.2f} | Now=${p.market_price:.2f}{marker}"
        )

asyncio.run(execute())
