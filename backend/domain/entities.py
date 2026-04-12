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
class Bar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Position:
    symbol: str
    quantity: float
    avg_cost: float
    market_price: float
    broker: Broker

    @property
    def market_value(self) -> float:
        return self.quantity * self.market_price

    @property
    def unrealized_pnl(self) -> float:
        return (self.market_price - self.avg_cost) * self.quantity


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


@dataclass
class Signal:
    symbol: str
    side: OrderSide
    strength: float  # 0.0 to 1.0
    strategy_name: str
    generated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)


@dataclass
class Portfolio:
    broker: Broker
    cash: float
    positions: list[Position] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)

    @property
    def total_market_value(self) -> float:
        return sum(p.market_value for p in self.positions)

    @property
    def total_value(self) -> float:
        return self.cash + self.total_market_value

    @property
    def total_unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions)


@dataclass
class BacktestResult:
    strategy_name: str
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_cash: float
    final_value: float
    trades: list[Trade]
    metrics: dict = field(default_factory=dict)

    @property
    def total_return(self) -> float:
        return (self.final_value - self.initial_cash) / self.initial_cash
