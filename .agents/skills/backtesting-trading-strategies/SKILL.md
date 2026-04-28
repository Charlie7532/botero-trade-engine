---
name: backtesting-trading-strategies
description: |
  Backtest trading strategies against historical data using the Botero Trade simulation engine.
  Use when user wants to test a trading strategy, validate signals, or run a walk-forward analysis.
  Relies entirely on the native Clean Architecture backend module (backend/modules/simulation).
---
# Backtesting Trading Strategies

## Overview

Validate trading strategies against historical data before risking real capital. This skill instructs the agent to use the native Botero Trade simulation engine powered by Backtrader.

**Key Features:**
- Seamless integration with existing `backend/modules/simulation/`
- Full walk-forward analysis capabilities
- Trade autopsy to analyze failed trades
- Direct access via FastAPI (`POST /api/strategy/backtest`)

## Instructions

To run a backtest, you must use the backend's simulation module. You can either:

1. **Use the FastAPI Endpoint**:
   If the API is running (port 8000), send a request to `/api/strategy/backtest`.
   ```bash
   curl -X POST http://localhost:8000/api/strategy/backtest \
     -H "Content-Type: application/json" \
     -d '{
       "strategy_name": "sma_crossover",
       "symbol": "AAPL",
       "broker": "alpaca",
       "timeframe": "1d",
       "start": "2023-01-01T00:00:00",
       "end": "2024-01-01T00:00:00",
       "initial_cash": 100000,
       "params": { "fast": 10, "slow": 30 }
     }'
   ```

2. **Use the Domain Use Case Directly**:
   If you need to write a custom script, interact directly with the domain layer using `backend/modules/simulation/domain/use_cases/run_backtest.py`.

## Creating a New Strategy

To add a new strategy, DO NOT create standalone scripts. Follow the project architecture:
1. Create a new file inheriting from `BaseStrategy` in `backend/modules/simulation/infrastructure/backtrader/strategies/`.
2. Register the new strategy in `backend/api/routers/strategy.py` inside the `_strategy_registry`.

## Prohibited Behavior

- DO NOT write standalone python scripts that fetch data and run backtests outside of the `backend/modules/simulation` directory.
- DO NOT use generic `yfinance` fetchers that bypass the domain `MarketDataPort`.
- DO NOT break Clean Architecture rules.