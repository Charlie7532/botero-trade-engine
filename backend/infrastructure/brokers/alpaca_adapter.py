import os
from datetime import datetime

from domain.entities import Bar, Broker, Order, OrderSide, OrderStatus, OrderType, Portfolio, Position
from infrastructure.brokers.base import BrokerAdapter


class AlpacaAdapter(BrokerAdapter):
    """Alpaca broker adapter using alpaca-py.

    Set ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL in environment.
    Defaults to paper trading endpoint.
    """

    def __init__(self):
        self._api_key = os.getenv("ALPACA_API_KEY", "")
        self._secret_key = os.getenv("ALPACA_SECRET_KEY", "")
        self._base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
        self._trading_client = None
        self._data_client = None

    @property
    def broker(self) -> Broker:
        return Broker.ALPACA

    def _get_trading_client(self):
        if self._trading_client is None:
            from alpaca.trading.client import TradingClient
            self._trading_client = TradingClient(self._api_key, self._secret_key, paper=True)
        return self._trading_client

    def _get_data_client(self):
        if self._data_client is None:
            from alpaca.data.historical import StockHistoricalDataClient
            self._data_client = StockHistoricalDataClient(self._api_key, self._secret_key)
        return self._data_client

    async def is_connected(self) -> bool:
        try:
            client = self._get_trading_client()
            client.get_account()
            return True
        except Exception:
            return False

    async def get_price(self, symbol: str) -> float:
        from alpaca.data.requests import StockLatestQuoteRequest
        client = self._get_data_client()
        request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        quote = client.get_stock_latest_quote(request)
        return float(quote[symbol].ask_price)

    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Bar]:
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        timeframe_map = {
            "1m": TimeFrame.Minute,
            "1h": TimeFrame.Hour,
            "1d": TimeFrame.Day,
        }
        tf = timeframe_map.get(timeframe, TimeFrame.Day)
        client = self._get_data_client()
        request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf, start=start, end=end)
        bars_response = client.get_stock_bars(request)
        return [
            Bar(
                symbol=symbol,
                timestamp=b.timestamp,
                open=float(b.open),
                high=float(b.high),
                low=float(b.low),
                close=float(b.close),
                volume=float(b.volume),
            )
            for b in bars_response[symbol]
        ]

    async def place_order(self, order: Order) -> Order:
        from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
        from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce

        client = self._get_trading_client()
        side = AlpacaSide.BUY if order.side == OrderSide.BUY else AlpacaSide.SELL
        # Crypto symbols contain "/" (e.g. "BTC/USD"); crypto requires GTC, not DAY
        is_crypto = "/" in order.symbol
        tif = TimeInForce.GTC if is_crypto else TimeInForce.DAY

        if order.order_type == OrderType.MARKET:
            kwargs: dict = {"symbol": order.symbol, "side": side, "time_in_force": tif}
            if order.notional is not None:
                kwargs["notional"] = order.notional
            else:
                kwargs["qty"] = order.quantity
            request = MarketOrderRequest(**kwargs)
        else:
            request = LimitOrderRequest(
                symbol=order.symbol,
                qty=order.quantity,
                side=side,
                time_in_force=tif,
                limit_price=order.limit_price,
            )

        result = client.submit_order(request)
        order.order_id = str(result.id)
        order.status = OrderStatus.PENDING
        return order

    async def cancel_order(self, order_id: str) -> bool:
        try:
            client = self._get_trading_client()
            client.cancel_order_by_id(order_id)
            return True
        except Exception:
            return False

    async def get_portfolio(self) -> Portfolio:
        client = self._get_trading_client()
        account = client.get_account()
        cash = float(account.cash)

        all_positions = client.get_all_positions()
        positions = [
            Position(
                symbol=p.symbol,
                quantity=float(p.qty),
                avg_cost=float(p.avg_entry_price),
                market_price=float(p.current_price),
                broker=Broker.ALPACA,
            )
            for p in all_positions
        ]
        return Portfolio(broker=Broker.ALPACA, cash=cash, positions=positions)
