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
│   ├── collections/             # PayloadCMS: Pages, Posts, Media, Users, Categories
│   ├── globals/                 # PayloadCMS: Header, Footer, SiteSettings
│   ├── blocks/                  # Layout builder blocks (20+ blocks)
│   ├── modules/                 # Feature modules: layout, pages, posts, users
│   └── components/              # Shared React components
│
├── backend/                     # Python trading engine
│   ├── modules/                 # Modular hexagonal architecture
│   ├── api/                     # FastAPI routers
│   └── Dockerfile
│
├── docker-compose.yml           # Services: web (3000), api (8000), postgres (5432)
├── package.json                 # pnpm root — name: "botero-trade"
└── .env.example                 # All required env vars documented
```

---

## Domain entities (backend/modules/)

| Entity | Location |
|---|---|
| `Order`, `Trade`, `Broker` | `modules/execution/domain/entities/order_models.py` |
| `Position`, `Portfolio` | `modules/portfolio_management/domain/entities/portfolio_models.py` |
| `Bar` | `modules/shared/domain/entities/market_data.py` |
| `Signal` | `modules/entry_decision/domain/entities/signal.py` |
| `BacktestResult` | `modules/simulation/domain/entities/simulation_models.py` |

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

---

## Environment variables (see .env.example)

| Variable | Purpose |
|---|---|
| `POSTGRES_URL` | PayloadCMS database |
| `PAYLOAD_SECRET` | JWT encryption key |
| `NEXT_PUBLIC_SERVER_URL` | Frontend public URL |
| `TRADING_API_URL` | Python engine URL |
| `IB_HOST/PORT/CLIENT_ID` | Interactive Brokers connection |
| `ALPACA_API_KEY/SECRET_KEY/BASE_URL` | Alpaca credentials |

---

## Tech stack

| | Technology |
|---|---|
| Frontend | Next.js 16, TypeScript, TailwindCSS, HeroUI, Radix UI |
| CMS | PayloadCMS 3 |
| Trading engine | Python 3.12, FastAPI, Backtrader |
| Brokers | ib_insync (Interactive Brokers), alpaca-py (Alpaca) |
| Database | PostgreSQL 16 |
| Deployment | Vercel (frontend) + VPS/Docker (backend) |
