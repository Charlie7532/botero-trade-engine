from dataclasses import dataclass, field
from backend.modules.execution.domain.entities.order_models import Broker, Trade

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
