from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class Broker(str, Enum):
    INTERACTIVE_BROKERS = "interactive_brokers"
    ALPACA = "alpaca"


@dataclass
class Order:
    symbol: str
    side: OrderSide
    order_type: OrderType
    broker: Broker
    quantity: Optional[float] = None
    notional: Optional[float] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Trade:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    broker: Broker
    executed_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def value(self) -> float:
        return self.quantity * self.price
