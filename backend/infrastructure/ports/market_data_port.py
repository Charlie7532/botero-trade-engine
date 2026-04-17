"""
Market Data Port — Clean Architecture Abstraction
====================================================
This is the PORT (interface) that all market data providers must implement.

Current implementations:
- AlpacaMarketData (FREE plan, paper trading)
- YFinanceFallback (free, no rate limit)

Future implementations:
- InteractiveBrokersMarketData (production)

The Application layer (UniverseFilter, AlphaScanner, PaperTrading)
depends on THIS interface, never on concrete implementations.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import pandas as pd


class MarketDataPort(ABC):
    """
    Interface for market data providers.

    Any broker/data provider must implement these methods.
    This enables swapping Alpaca → Interactive Brokers without
    changing any Application layer code.
    """

    @abstractmethod
    def get_bars(
        self,
        ticker: str,
        timeframe: str = "1Day",
        start: datetime = None,
        end: datetime = None,
        limit: int = 200,
    ) -> pd.DataFrame:
        """Get historical OHLCV bars."""
        ...

    @abstractmethod
    def get_bars_multi(
        self,
        tickers: list[str],
        timeframe: str = "1Day",
        start: datetime = None,
        limit: int = 100,
    ) -> dict[str, pd.DataFrame]:
        """Get bars for multiple tickers."""
        ...

    @abstractmethod
    def get_latest_quote(self, ticker: str) -> dict:
        """Get latest quote."""
        ...

    @abstractmethod
    def get_account_summary(self) -> dict:
        """Get account equity, cash, buying power."""
        ...

    @abstractmethod
    def get_positions(self) -> list[dict]:
        """Get all open positions."""
        ...


class ExecutionPort(ABC):
    """
    Interface for order execution.

    Separates market data from execution — essential because
    data may come from Finviz/Yahoo while execution goes through
    the broker (Alpaca now, IB in the future).
    """

    @abstractmethod
    def submit_order(
        self,
        ticker: str,
        qty: float,
        side: str,  # "buy" or "sell"
        order_type: str = "market",  # "market", "limit", "stop", "stop_limit"
        limit_price: float = None,
        stop_price: float = None,
        time_in_force: str = "day",
    ) -> dict:
        """Submit an order. Returns order details dict."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        ...

    @abstractmethod
    def get_order(self, order_id: str) -> dict:
        """Get order status."""
        ...

    @abstractmethod
    def get_open_orders(self) -> list[dict]:
        """Get all open orders."""
        ...
