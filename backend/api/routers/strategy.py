from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from domain.entities import Broker
from infrastructure.brokers.alpaca_adapter import AlpacaAdapter
from infrastructure.brokers.ib_adapter import IBAdapter
from application.use_cases import fetch_market_data, run_backtest
from infrastructure.backtrader.base_strategy import BaseStrategy

router = APIRouter(prefix="/strategy", tags=["Strategy"])

_brokers = {
    Broker.ALPACA: AlpacaAdapter(),
    Broker.INTERACTIVE_BROKERS: IBAdapter(),
}

# Registry of available strategies — add new strategies here
_strategy_registry: dict[str, type[BaseStrategy]] = {}


class BacktestRequest(BaseModel):
    strategy_name: str
    symbol: str
    broker: Broker = Broker.ALPACA
    timeframe: str = "1d"
    start: datetime
    end: datetime
    initial_cash: float = 100_000.0
    commission: float = 0.001
    params: dict = {}


class TradeLog(BaseModel):
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    broker: str
    executed_at: datetime


class BacktestResponse(BaseModel):
    strategy_name: str
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_cash: float
    final_value: float
    total_return_pct: float
    metrics: dict
    trade_count: int
    trades: list[TradeLog]


class StrategyInfo(BaseModel):
    name: str
    description: str


@router.get("/list", response_model=list[StrategyInfo])
async def list_strategies():
    """List all available registered strategies."""
    return [
        StrategyInfo(name=name, description=cls.__doc__ or "No description.")
        for name, cls in _strategy_registry.items()
    ]


@router.post("/backtest", response_model=BacktestResponse)
async def backtest(request: BacktestRequest):
    """Run a backtest for a registered strategy against historical market data."""
    strategy_class = _strategy_registry.get(request.strategy_name)
    if not strategy_class:
        available = list(_strategy_registry.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Strategy '{request.strategy_name}' not found. Available: {available}",
        )

    adapter = _brokers.get(request.broker)
    if not adapter:
        raise HTTPException(status_code=400, detail=f"Unknown broker: {request.broker}")

    try:
        bars = await fetch_market_data(adapter, request.symbol, request.timeframe, request.start, request.end)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch market data: {e}")

    if not bars:
        raise HTTPException(status_code=404, detail=f"No data found for {request.symbol} in the given range.")

    try:
        result = run_backtest(
            strategy_class=strategy_class,
            bars=bars,
            initial_cash=request.initial_cash,
            commission=request.commission,
            strategy_params=request.params,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")

    return BacktestResponse(
        strategy_name=result.strategy_name,
        symbol=result.symbol,
        start_date=result.start_date,
        end_date=result.end_date,
        initial_cash=result.initial_cash,
        final_value=result.final_value,
        total_return_pct=result.total_return,
        metrics=result.metrics,
        trade_count=len(result.trades),
        trades=[
            TradeLog(
                order_id=t.order_id,
                symbol=t.symbol,
                side=t.side if isinstance(t.side, str) else t.side.value,
                quantity=t.quantity,
                price=t.price,
                broker=t.broker.value,
                executed_at=t.executed_at,
            )
            for t in result.trades
        ],
    )
