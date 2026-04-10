# Botero Trade — Full Project Context

You are working on **Botero Trade**, an algorithmic trading monorepo at `/root/botero-trade/`.

## What this project is

A full-stack trading system combining:
- **Next.js 16 + PayloadCMS 3** frontend (TypeScript) — trading dashboard UI + headless CMS admin panel
- **Python FastAPI + Backtrader** trading engine — backtesting, live trading, broker connectivity
- **PostgreSQL 16** — database for PayloadCMS
- **Docker Compose** — orchestrates all three services

The Python backend exposes a REST API that the Next.js frontend consumes via `TRADING_API_URL`.

---

## Monorepo layout

```
botero-trade/
├── src/                          # Next.js + PayloadCMS (TypeScript)
│   ├── app/(frontend)/          # Trading dashboard UI pages
│   ├── app/(payload)/           # PayloadCMS admin panel
│   ├── shared/                  # Clean Architecture (TS side)
│   │   ├── domain/              # Domain types, ports, rules
│   │   ├── application/         # Use cases
│   │   ├── infrastructure/      # Adapters (Next cache, etc.)
│   │   └── handlers/
│   ├── collections/             # PayloadCMS: Pages, Posts, Media, Users, Categories
│   ├── globals/                 # PayloadCMS: Header, Footer, SiteSettings
│   ├── blocks/                  # Layout builder blocks (20+ blocks)
│   ├── modules/                 # Feature modules: layout, pages, posts, users
│   └── components/              # Shared React components
│
├── backend/                     # Python trading engine
│   ├── domain/entities.py       # Portfolio, Position, Order, Signal, Trade, Bar, BacktestResult
│   ├── application/use_cases.py # run_backtest(), fetch_market_data(), place_order(), get_portfolio()
│   ├── infrastructure/
│   │   ├── brokers/
│   │   │   ├── base.py          # Abstract BrokerAdapter (interface all brokers must implement)
│   │   │   ├── ib_adapter.py    # Interactive Brokers via ib_insync
│   │   │   └── alpaca_adapter.py# Alpaca via alpaca-py
│   │   └── backtrader/
│   │       ├── base_strategy.py # BaseStrategy(bt.Strategy) — extend this for new strategies
│   │       └── data_feeds.py    # create_data_feed(bars) → bt.feeds.PandasData
│   └── api/
│       ├── main.py              # FastAPI app, CORS config
│       └── routers/
│           ├── market_data.py   # GET /api/market-data/{symbol}, GET /api/market-data/{symbol}/price
│           ├── portfolio.py     # GET /api/portfolio/{broker}, GET /api/portfolio/
│           └── strategy.py      # GET /api/strategy/list, POST /api/strategy/backtest
│
├── docker-compose.yml           # Services: web (3000), api (8000), postgres (5432)
├── Dockerfile                   # Next.js standalone production image
├── backend/Dockerfile           # Python uvicorn image
├── package.json                 # pnpm root — name: "botero-trade"
└── .env.example                 # All required env vars documented
```

---

## Key architectural decisions

**Broker Adapter Pattern** — All trading logic depends on the abstract `BrokerAdapter` interface (`backend/infrastructure/brokers/base.py`), never on concrete broker implementations. Swap or combine brokers without touching strategy code.

**Clean Architecture** — Both the Python backend and TypeScript frontend follow Clean Architecture. Dependencies point inward: API/UI → Application → Infrastructure → Domain. Domain layer has zero framework imports.

**Strategy Registry** — Trading strategies are registered in `backend/api/routers/strategy.py` in `_strategy_registry`. New strategies extend `BaseStrategy` and are added to the registry — nothing else changes.

**PayloadCMS is the content backend** — The Next.js app and PayloadCMS run in the same process (same port 3000). The Python FastAPI engine (port 8000) is a separate service for trading logic only.

**Vercel for frontend, self-hosted for backend** — The Next.js + Payload app deploys to Vercel (auto-detects from repo root). The Python trading engine requires a persistent server (VPS/Docker) since it connects to broker APIs.

---

## Domain entities (backend/domain/entities.py)

| Entity | Key fields |
|---|---|
| `Bar` | symbol, timestamp, open, high, low, close, volume |
| `Order` | symbol, side (buy/sell), quantity, order_type, broker, status |
| `Position` | symbol, quantity, avg_cost, market_price, broker |
| `Trade` | order_id, symbol, side, quantity, price, broker, executed_at |
| `Signal` | symbol, side, strength (0–1), strategy_name |
| `Portfolio` | broker, cash, positions[], trades[] |
| `BacktestResult` | strategy_name, symbol, initial_cash, final_value, trades[], metrics{} |
| `Broker` | enum: `interactive_brokers`, `alpaca` |

---

## API endpoints (Python FastAPI, port 8000)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/market-data/{symbol}` | Historical OHLCV bars |
| GET | `/api/market-data/{symbol}/price` | Current price |
| GET | `/api/portfolio/{broker}` | Portfolio from one broker |
| GET | `/api/portfolio/` | All connected broker portfolios |
| GET | `/api/strategy/list` | Registered strategies |
| POST | `/api/strategy/backtest` | Run Backtrader backtest |
| GET | `/api/docs` | Swagger UI |

---

## Environment variables (see .env.example)

| Variable | Purpose |
|---|---|
| `POSTGRES_URL` | PayloadCMS database |
| `PAYLOAD_SECRET` | JWT encryption key |
| `NEXT_PUBLIC_SERVER_URL` | Frontend public URL |
| `TRADING_API_URL` | Python engine URL (Docker: `http://api:8000`, local: `http://localhost:8000`) |
| `IB_HOST/PORT/CLIENT_ID` | Interactive Brokers TWS/Gateway connection |
| `ALPACA_API_KEY/SECRET_KEY/BASE_URL` | Alpaca credentials (defaults to paper trading) |
| `POSTGRES_PASSWORD` | PostgreSQL password (Docker only) |

---

## Dev commands

```bash
# Frontend only
pnpm dev                        # Next.js dev server → localhost:3000

# Python engine only  
pnpm dev:api                    # uvicorn with --reload → localhost:8000

# Everything via Docker
pnpm docker:up                  # docker compose up (web + api + postgres)
pnpm docker:build               # rebuild images
pnpm docker:down                # stop all

# PayloadCMS
pnpm generate                   # regenerate Payload types + import map
pnpm payload migrate:create     # create DB migration
pnpm payload migrate            # run pending migrations
```

---

## Tech stack

| | Technology |
|---|---|
| Frontend | Next.js 16, TypeScript, TailwindCSS, HeroUI, Radix UI |
| CMS | PayloadCMS 3 |
| Trading engine | Python 3.12, FastAPI, Backtrader |
| Brokers | ib_insync (Interactive Brokers), alpaca-py (Alpaca) |
| Data | pandas, numpy |
| Database | PostgreSQL 16 |
| Containers | Docker Compose |
| Deployment | Vercel (frontend) + VPS/Docker (backend) |
| Package manager | pnpm ≥9 |
| Git remote | https://github.com/Charlie7532/botero-trade-engine |
