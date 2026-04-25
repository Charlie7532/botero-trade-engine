from abc import ABC, abstractmethod
from datetime import datetime

from domain.entities import Bar, Broker, Order, Portfolio


class BrokerAdapter(ABC):
    """Abstract interface for all broker integrations.
    All trading logic depends on this interface, never on concrete implementations.
    """

    @property
    @abstractmethod
    def broker(self) -> Broker:
        """Identifies which broker this adapter represents."""
        ...

    @abstractmethod
    async def get_price(self, symbol: str) -> float:
        """Fetch the current market price for a symbol."""
        ...

    @abstractmethod
    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Bar]:
        """Fetch historical OHLCV bars for a symbol."""
        ...

    @abstractmethod
    async def place_order(self, order: Order) -> Order:
        """Submit an order. Returns the order with updated status and order_id."""
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order. Returns True if successfully cancelled."""
        ...

    @abstractmethod
    async def get_portfolio(self) -> Portfolio:
        """Fetch the current portfolio state (cash + positions)."""
        ...

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check whether the broker connection is active."""
        ...
