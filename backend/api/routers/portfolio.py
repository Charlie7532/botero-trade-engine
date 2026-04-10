from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from domain.entities import Broker
from infrastructure.brokers.alpaca_adapter import AlpacaAdapter
from infrastructure.brokers.ib_adapter import IBAdapter

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])

_brokers = {
    Broker.ALPACA: AlpacaAdapter(),
    Broker.INTERACTIVE_BROKERS: IBAdapter(),
}


class PositionResponse(BaseModel):
    symbol: str
    quantity: float
    avg_cost: float
    market_price: float
    market_value: float
    unrealized_pnl: float
    broker: str


class PortfolioResponse(BaseModel):
    broker: str
    cash: float
    total_market_value: float
    total_value: float
    total_unrealized_pnl: float
    positions: list[PositionResponse]


@router.get("/{broker}", response_model=PortfolioResponse)
async def get_portfolio(broker: Broker):
    """Retrieve the current portfolio state from the specified broker."""
    adapter = _brokers.get(broker)
    if not adapter:
        raise HTTPException(status_code=400, detail=f"Unknown broker: {broker}")
    try:
        portfolio = await adapter.get_portfolio()
        return PortfolioResponse(
            broker=portfolio.broker.value,
            cash=portfolio.cash,
            total_market_value=portfolio.total_market_value,
            total_value=portfolio.total_value,
            total_unrealized_pnl=portfolio.total_unrealized_pnl,
            positions=[
                PositionResponse(
                    symbol=p.symbol,
                    quantity=p.quantity,
                    avg_cost=p.avg_cost,
                    market_price=p.market_price,
                    market_value=p.market_value,
                    unrealized_pnl=p.unrealized_pnl,
                    broker=p.broker.value,
                )
                for p in portfolio.positions
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/", response_model=list[PortfolioResponse])
async def get_all_portfolios():
    """Retrieve portfolios from all connected brokers."""
    results = []
    for broker, adapter in _brokers.items():
        try:
            connected = await adapter.is_connected()
            if connected:
                portfolio = await adapter.get_portfolio()
                results.append(PortfolioResponse(
                    broker=portfolio.broker.value,
                    cash=portfolio.cash,
                    total_market_value=portfolio.total_market_value,
                    total_value=portfolio.total_value,
                    total_unrealized_pnl=portfolio.total_unrealized_pnl,
                    positions=[
                        PositionResponse(
                            symbol=p.symbol,
                            quantity=p.quantity,
                            avg_cost=p.avg_cost,
                            market_price=p.market_price,
                            market_value=p.market_value,
                            unrealized_pnl=p.unrealized_pnl,
                            broker=p.broker.value,
                        )
                        for p in portfolio.positions
                    ],
                ))
        except Exception:
            continue
    return results
