from dataclasses import dataclass, field
from datetime import datetime
from backend.modules.execution.domain.entities.order_models import OrderSide

@dataclass
class Signal:
    symbol: str
    side: OrderSide
    strength: float  # 0.0 to 1.0
    strategy_name: str
    generated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)
