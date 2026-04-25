import os
from datetime import datetime

from domain.entities import Bar, Broker, Order, OrderStatus, Portfolio, Position
from modules.execution.infrastructure.brokers.base import BrokerAdapter


class IBAdapter(BrokerAdapter):
    """Interactive Brokers adapter using ib_insync.

    Requires TWS or IB Gateway running locally.
    Set IB_HOST, IB_PORT, IB_CLIENT_ID in environment.
    """

    def __init__(self):
        self._host = os.getenv("IB_HOST", "127.0.0.1")
        self._port = int(os.getenv("IB_PORT", "7497"))
        self._client_id = int(os.getenv("IB_CLIENT_ID", "1"))
        self._ib = None

    @property
    def broker(self) -> Broker:
        return Broker.INTERACTIVE_BROKERS

    def _get_client(self):
        """Lazy-connect to IB on first use."""
        if self._ib is None:
            try:
                import ib_insync
                self._ib = ib_insync.IB()
                self._ib.connect(self._host, self._port, clientId=self._client_id)
            except Exception as e:
                raise ConnectionError(
                    f"Cannot connect to IB at {self._host}:{self._port}. "
                    f"Ensure TWS or IB Gateway is running. Error: {e}"
                )
        return self._ib

    async def is_connected(self) -> bool:
        try:
            ib = self._get_client()
            return ib.isConnected()
        except Exception:
            return False

    async def get_price(self, symbol: str) -> float:
        import ib_insync
        ib = self._get_client()
        contract = ib_insync.Stock(symbol, "SMART", "USD")
        ib.qualifyContracts(contract)
        ticker = ib.reqMktData(contract, "", False, False)
        ib.sleep(1)
        price = ticker.last or ticker.close
        ib.cancelMktData(contract)
        if price is None:
            raise ValueError(f"Could not fetch price for {symbol}")
        return float(price)

    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Bar]:
        import ib_insync
        ib = self._get_client()
        contract = ib_insync.Stock(symbol, "SMART", "USD")
        ib.qualifyContracts(contract)

        duration = f"{(end - start).days + 1} D"
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=end,
            durationStr=duration,
            barSizeSetting=timeframe,
            whatToShow="TRADES",
            useRTH=True,
        )
        return [
            Bar(
                symbol=symbol,
                timestamp=b.date,
                open=b.open,
                high=b.high,
                low=b.low,
                close=b.close,
                volume=b.volume,
            )
            for b in bars
        ]

    async def place_order(self, order: Order) -> Order:
        import ib_insync
        ib = self._get_client()
        contract = ib_insync.Stock(order.symbol, "SMART", "USD")
        ib.qualifyContracts(contract)

        action = "BUY" if order.side.value == "buy" else "SELL"
        ib_order = ib_insync.MarketOrder(action, order.quantity)
        trade = ib.placeOrder(contract, ib_order)
        ib.sleep(1)

        order.order_id = str(trade.order.orderId)
        order.status = OrderStatus.PENDING
        return order

    async def cancel_order(self, order_id: str) -> bool:
        import ib_insync
        ib = self._get_client()
        for trade in ib.trades():
            if str(trade.order.orderId) == order_id:
                ib.cancelOrder(trade.order)
                return True
        return False

    async def get_portfolio(self) -> Portfolio:
        ib = self._get_client()
        account_values = ib.accountValues()
        cash = next(
            (float(v.value) for v in account_values if v.tag == "CashBalance" and v.currency == "USD"),
            0.0,
        )
        positions = [
            Position(
                symbol=p.contract.symbol,
                quantity=p.position,
                avg_cost=p.avgCost,
                market_price=p.marketPrice,
                broker=Broker.INTERACTIVE_BROKERS,
            )
            for p in ib.positions()
        ]
        return Portfolio(broker=Broker.INTERACTIVE_BROKERS, cash=cash, positions=positions)
