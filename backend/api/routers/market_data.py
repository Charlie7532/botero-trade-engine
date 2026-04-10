from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from domain.entities import Bar, Broker
from infrastructure.brokers.alpaca_adapter import AlpacaAdapter
from infrastructure.brokers.ib_adapter import IBAdapter

router = APIRouter(prefix="/market-data", tags=["Market Data"])

_brokers = {
    Broker.ALPACA: AlpacaAdapter(),
    Broker.INTERACTIVE_BROKERS: IBAdapter(),
}


class BarResponse(BaseModel):
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@router.get("/{symbol}", response_model=list[BarResponse])
async def get_bars(
    symbol: str,
    broker: Broker = Query(Broker.ALPACA),
    timeframe: str = Query("1d", description="Bar timeframe: 1m, 1h, 1d"),
    start: datetime = Query(..., description="Start datetime (ISO 8601)"),
    end: datetime = Query(..., description="End datetime (ISO 8601)"),
):
    """Fetch historical OHLCV bars for a symbol from the specified broker."""
    adapter = _brokers.get(broker)
    if not adapter:
        raise HTTPException(status_code=400, detail=f"Unknown broker: {broker}")
    try:
        bars: list[Bar] = await adapter.get_bars(symbol.upper(), timeframe, start, end)
        return [BarResponse(**b.__dict__) for b in bars]
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/{symbol}/price")
async def get_price(symbol: str, broker: Broker = Query(Broker.ALPACA)):
    """Get the current market price for a symbol."""
    adapter = _brokers.get(broker)
    if not adapter:
        raise HTTPException(status_code=400, detail=f"Unknown broker: {broker}")
    try:
        price = await adapter.get_price(symbol.upper())
        return {"symbol": symbol.upper(), "price": price, "broker": broker}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
