# Botero Trade

An algorithmic trading system built as a monorepo, combining a **Next.js + PayloadCMS** frontend with a **Python FastAPI + Backtrader** trading engine. Connect to Interactive Brokers and Alpaca, run backtests, and visualize your portfolios — all from a single repository.

---

## Architecture

### System Overview

```mermaid
graph TB
    subgraph Frontend ["Frontend — Next.js + PayloadCMS (port 3000)"]
        UI["Trading Dashboard\n(src/app/frontend)"]
        CMS["Admin Panel\n(src/app/payload)"]
    end

    subgraph Backend ["Trading Engine — Python FastAPI (port 8000)"]
        API["FastAPI\n/api/market-data\n/api/portfolio\n/api/strategy"]
        UC["Use Cases\napplication/use_cases.py"]
        BT["Backtrader\nbacktest engine"]
        BA["Broker Adapters"]
    end

    subgraph Brokers ["External Brokers"]
        IB["Interactive Brokers\nTWS / IB Gateway"]
        ALP["Alpaca\npaper & live"]
    end

    subgraph Infra ["Infrastructure"]
        PG["PostgreSQL\n(port 5432)"]
    end

    UI -->|HTTP / fetch| API
    API --> UC
    UC --> BT
    UC --> BA
    BA -->|ib_insync| IB
    BA -->|alpaca-py| ALP
    Frontend -->|Payload DB| PG
```

### Clean Architecture Layers

```mermaid
graph LR
    subgraph Python Backend
        D["Domain\nentities.py\nPortfolio · Order · Signal · Bar"]
        A["Application\nuse_cases.py\nrun_backtest · place_order"]
        I["Infrastructure\nbrokers/ · backtrader/"]
        API2["API Layer\nFastAPI routers"]

        API2 --> I
        API2 --> A
        A --> I
        A --> D
        I --> D
    end

    subgraph TypeScript Frontend
        TD["Domain\nTS types / interfaces"]
        TA["Application\nstate · UI use cases"]
        TI["Infrastructure\nAPI client · storage"]
        TUI["UI Layer\nReact components"]

        TUI --> TI
        TUI --> TA
        TA --> TI
        TA --> TD
        TI --> TD
    end
```

### Broker Adapter Pattern

```mermaid
classDiagram
    class BrokerAdapter {
        <<abstract>>
        +broker() Broker
        +get_price(symbol) float
        +get_bars(symbol, timeframe, start, end) list[Bar]
        +place_order(order) Order
        +cancel_order(order_id) bool
        +get_portfolio() Portfolio
        +is_connected() bool
    }

    class IBAdapter {
        -host: str
        -port: int
        -client_id: int
        +broker() INTERACTIVE_BROKERS
    }

    class AlpacaAdapter {
        -api_key: str
        -secret_key: str
        -base_url: str
        +broker() ALPACA
    }

    BrokerAdapter <|-- IBAdapter
    BrokerAdapter <|-- AlpacaAdapter

    class UseCase {
        +fetch_market_data(broker, symbol)
        +place_order(broker, order)
        +run_backtest(strategy, bars)
    }

    UseCase --> BrokerAdapter : depends on interface
```

### Request Flow — Backtest

```mermaid
sequenceDiagram
    participant UI as Dashboard (Next.js)
    participant API as FastAPI
    participant UC as Use Cases
    participant Broker as BrokerAdapter
    participant BT as Backtrader

    UI->>API: POST /api/strategy/backtest
    API->>UC: run_backtest(strategy, bars, ...)
    UC->>Broker: get_bars(symbol, timeframe, start, end)
    Broker-->>UC: list[Bar]
    UC->>BT: cerebro.run()
    BT-->>UC: BacktestResult + metrics
    UC-->>API: BacktestResult
    API-->>UI: BacktestResponse (JSON)
```

---

## Project Structure

```
botero-trade/
├── src/                              # Next.js + PayloadCMS (TypeScript)
│   ├── app/
│   │   ├── (frontend)/              # Trading dashboard UI
│   │   └── (payload)/               # CMS admin panel
│   ├── shared/                      # Clean Architecture (TS)
│   │   ├── domain/                  # Domain types and rules
│   │   ├── application/             # UI use cases
│   │   ├── infrastructure/          # API clients, adapters
│   │   └── handlers/
│   ├── collections/                 # PayloadCMS collections
│   ├── globals/                     # Header, Footer, SiteSettings
│   └── components/                  # Shared React components
│
├── backend/                         # Python trading engine
│   ├── domain/
│   │   └── entities.py              # Portfolio, Order, Signal, Bar, Trade
│   ├── application/
│   │   └── use_cases.py             # run_backtest, fetch_market_data, place_order
│   ├── infrastructure/
│   │   ├── brokers/
│   │   │   ├── base.py              # Abstract BrokerAdapter
│   │   │   ├── ib_adapter.py        # Interactive Brokers (ib_insync)
│   │   │   └── alpaca_adapter.py    # Alpaca (alpaca-py)
│   │   └── backtrader/
│   │       ├── base_strategy.py     # BaseStrategy — extend this for new strategies
│   │       └── data_feeds.py        # Bar → Backtrader PandasData bridge
│   ├── api/
│   │   ├── main.py                  # FastAPI app + CORS
│   │   └── routers/
│   │       ├── market_data.py       # GET /api/market-data/{symbol}
│   │       ├── portfolio.py         # GET /api/portfolio/{broker}
│   │       └── strategy.py          # POST /api/strategy/backtest
│   ├── requirements.txt
│   └── Dockerfile
│
├── docker-compose.yml               # Orchestrates web + api (DB is external)
├── Dockerfile                       # Next.js production image (standalone)
├── package.json                     # pnpm root — pnpm start runs Next.js
├── .env.example                     # All required environment variables
└── next.config.js
```

---

## Getting Started

### Prerequisites

- [Node.js](https://nodejs.org) `>=20.9.0`
- [pnpm](https://pnpm.io) `>=9`
- [Python](https://python.org) `3.12+`
- [Docker + Docker Compose](https://docs.docker.com/compose/) (optional)
- An external PostgreSQL database (see [Database](#database) below)

### 1. Clone and configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials — especially `POSTGRES_URL` (see [Environment Variables](#environment-variables)).

### 2a. Local development — all services in one command

```bash
pnpm install
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && cd ..
pnpm dev:all
```

`pnpm dev:all` starts both services concurrently with labeled, colored output:

```
[web] ▶ Next.js ready on http://localhost:3000
[api] ▶ Uvicorn running on http://0.0.0.0:8000
```

| Service | URL |
|---|---|
| Frontend + CMS | http://localhost:3000 |
| PayloadCMS admin | http://localhost:3000/admin |
| Trading Engine API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |

### 2b. Docker Compose (containerized)

```bash
docker compose up
```

Starts `web` (port 3000) and `api` (port 8000). The database is not managed by Docker — set `POSTGRES_URL` in `.env` to your external database.

---

## Database

PostgreSQL is hosted **externally** — not inside Docker — so your data is never tied to this project's containers and survives migrations, rebuilds, and deployments.

Recommended providers:

| Provider | Free tier | Notes |
|---|---|---|
| [Vercel Postgres](https://vercel.com/storage/postgres) | Yes | Best for Vercel deployments — zero config |
| [Neon](https://neon.tech) | Yes | Serverless, branching support |
| [Supabase](https://supabase.com) | Yes | Includes auth, storage, realtime |
| Local instance | — | `postgres://postgres:<pw>@127.0.0.1:5432/botero_trade` |

Set the connection string in `.env`:
```
POSTGRES_URL=postgres://user:password@host:5432/database
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values:

| Variable | Description |
|---|---|
| `POSTGRES_URL` | External PostgreSQL connection string |
| `PAYLOAD_SECRET` | Secret key for JWT encryption |
| `NEXT_PUBLIC_SERVER_URL` | Public URL of the frontend |
| `TRADING_API_URL` | URL of the Python trading engine |
| `IB_HOST` | IB TWS/Gateway host (default `127.0.0.1`) |
| `IB_PORT` | IB TWS/Gateway port (default `7497`) |
| `IB_CLIENT_ID` | IB client ID (default `1`) |
| `ALPACA_API_KEY` | Alpaca API key |
| `ALPACA_SECRET_KEY` | Alpaca secret key |
| `ALPACA_BASE_URL` | Alpaca endpoint (default: paper trading) |

> **Interactive Brokers note:** TWS or IB Gateway must run on your local machine — it cannot run inside Docker. The `api` container connects to it via `host.docker.internal` or your machine's LAN IP.

---

## Adding a Trading Strategy

1. Create a new file in `backend/infrastructure/backtrader/strategies/`:

```python
# backend/infrastructure/backtrader/strategies/sma_crossover.py
import backtrader as bt
from infrastructure.backtrader.base_strategy import BaseStrategy

class SMACrossover(BaseStrategy):
    """Simple Moving Average crossover strategy."""

    params = (
        ("fast", 10),
        ("slow", 30),
    )

    def __init__(self):
        super().__init__()
        self.fast_ma = bt.indicators.SMA(period=self.params.fast)
        self.slow_ma = bt.indicators.SMA(period=self.params.slow)
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)

    def next(self):
        if not self.position and self.crossover > 0:
            self.order = self.buy()
        elif self.position and self.crossover < 0:
            self.order = self.sell()
```

2. Register it in `backend/api/routers/strategy.py`:

```python
from infrastructure.backtrader.strategies.sma_crossover import SMACrossover

_strategy_registry["sma_crossover"] = SMACrossover
```

3. Run a backtest via the API:

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

---

## Adding a Broker

1. Create a new adapter extending `BrokerAdapter`:

```python
# backend/infrastructure/brokers/my_broker_adapter.py
from infrastructure.brokers.base import BrokerAdapter

class MyBrokerAdapter(BrokerAdapter):
    @property
    def broker(self) -> Broker:
        return Broker.MY_BROKER

    async def get_price(self, symbol: str) -> float: ...
    # implement all abstract methods
```

2. Add the broker to the `Broker` enum in `backend/domain/entities.py`.

3. Register the adapter in the relevant routers (`market_data.py`, `portfolio.py`, `strategy.py`).

---

## Deployment

### Frontend → Vercel

The frontend (Next.js + PayloadCMS) deploys to Vercel out of the box:

1. Push this repo to GitHub
2. Import it on [vercel.com](https://vercel.com)
3. Set **Root Directory** to `/` (the repo root — Vercel auto-detects Next.js)
4. Add all environment variables from `.env.example` in the Vercel dashboard
5. Vercel handles builds and deploys automatically on push

The template is already configured for `@payloadcms/db-vercel-postgres` and `@payloadcms/storage-vercel-blob`.

### Trading Engine → Self-hosted

The Python `api` service requires persistent server infrastructure (it connects to broker APIs and runs long-lived processes). Deploy it to any VPS, DigitalOcean Droplet, or similar:

```bash
docker compose up -d api
```

Set `TRADING_API_URL` in your Vercel environment variables to point to your server's public IP/domain.

### Scripts reference

| Command | Description |
|---|---|
| `pnpm dev:all` | Start frontend + Python API together (recommended for local dev) |
| `pnpm dev` | Frontend only (Next.js dev server) |
| `pnpm dev:api` | Python API only (uvicorn with hot reload) |
| `pnpm start` | Start Next.js production server |
| `pnpm build` | Build Next.js for production |
| `pnpm docker:up` | Start web + api via Docker Compose |
| `pnpm docker:build` | Rebuild Docker images |
| `pnpm docker:down` | Stop all Docker services |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend framework | Next.js 16 (App Router) |
| CMS | PayloadCMS 3 |
| UI components | HeroUI, Radix UI, Tailwind CSS |
| Language (frontend) | TypeScript |
| Trading engine | Python 3.12 + FastAPI |
| Backtesting | Backtrader |
| Interactive Brokers | ib_insync |
| Alpaca | alpaca-py |
| Data processing | pandas, numpy |
| Database | PostgreSQL 16 |
| Container orchestration | Docker Compose |
| Frontend deployment | Vercel |
