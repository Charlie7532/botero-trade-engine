from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator

from application.use_cases import place_order
from domain.entities import Broker, Order, OrderSide, OrderStatus, OrderType
from infrastructure.brokers.alpaca_adapter import AlpacaAdapter
from infrastructure.brokers.ib_adapter import IBAdapter

router = APIRouter(prefix="/orders", tags=["Orders"])

_brokers = {
    Broker.ALPACA: AlpacaAdapter(),
    Broker.INTERACTIVE_BROKERS: IBAdapter(),
}


class PlaceOrderRequest(BaseModel):
    symbol: str
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    broker: Broker = Broker.ALPACA
    quantity: Optional[float] = None
    notional: Optional[float] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None

    @model_validator(mode="after")
    def require_quantity_or_notional(self) -> "PlaceOrderRequest":
        if self.quantity is None and self.notional is None:
            raise ValueError("Provide either quantity or notional.")
        if self.notional is not None and self.order_type != OrderType.MARKET:
            raise ValueError("notional is only valid for market orders.")
        return self


class OrderResponse(BaseModel):
    order_id: Optional[str]
    symbol: str
    side: str
    order_type: str
    broker: str
    quantity: Optional[float]
    notional: Optional[float]
    status: str


@router.post("/", response_model=OrderResponse, status_code=201)
async def create_order(body: PlaceOrderRequest):
    """Submit a new order through the specified broker."""
    adapter = _brokers.get(body.broker)
    if not adapter:
        raise HTTPException(status_code=400, detail=f"Unknown broker: {body.broker}")

    order = Order(
        symbol=body.symbol,
        side=body.side,
        order_type=body.order_type,
        broker=body.broker,
        quantity=body.quantity,
        notional=body.notional,
        limit_price=body.limit_price,
        stop_price=body.stop_price,
    )

    try:
        result = await place_order(adapter, order)
        return OrderResponse(
            order_id=result.order_id,
            symbol=result.symbol,
            side=result.side.value,
            order_type=result.order_type.value,
            broker=result.broker.value,
            quantity=result.quantity,
            notional=result.notional,
            status=result.status.value,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
