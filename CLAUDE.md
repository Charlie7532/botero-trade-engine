# Botero Trade — Agent Context

This file is auto-loaded by Claude Code at the start of every session. Read it fully before writing any code.

---

## What this project is

Algorithmic trading monorepo combining:
- **Next.js 16 + PayloadCMS 3** (TypeScript) — trading dashboard UI + CMS admin at `src/`
- **Python FastAPI + Backtrader** — trading engine, backtesting, broker connectivity at `backend/`
- **Docker Compose** — orchestrates `web` (3000) and `api` (8000). PostgreSQL is **external**.

Git remote: `https://github.com/Charlie7532/botero-trade-engine`

---

## Clean Architecture — mandatory for all code

This is the most important section. Every agent must follow these rules without exception.

### The one rule that overrides everything else

**Dependencies point inward.** Outer layers know about inner layers. Inner layers know nothing about outer layers. Never import a framework into the domain.

```
         ┌─────────────────────────┐
         │    API / UI (outer)     │  ← knows about everything below
         ├─────────────────────────┤
         │   Infrastructure        │  ← knows about Application + Domain
         ├─────────────────────────┤
         │   Application           │  ← knows about Domain only
         ├─────────────────────────┤
         │   Domain (inner)        │  ← knows nothing. Zero imports from other layers.
         └─────────────────────────┘
```

### Python backend layer rules

| Layer | Location | Allowed imports | Forbidden |
|---|---|---|---|
| **Domain** | `backend/domain/` | Python stdlib only | fastapi, backtrader, ib_insync, alpaca, pandas |
| **Application** | `backend/application/` | domain, stdlib | fastapi, ib_insync, alpaca |
| **Infrastructure** | `backend/infrastructure/` | domain, application, any library | — |
| **API** | `backend/api/` | application, infrastructure, fastapi | direct broker SDK calls |

**Domain entities** (`backend/domain/entities.py`) are pure Python dataclasses. Never add framework decorators, ORM mappings, or Pydantic models here. Pydantic belongs in the API layer as request/response schemas.

**BrokerAdapter** (`backend/infrastructure/brokers/base.py`) is the critical abstraction. Application and API code must always depend on `BrokerAdapter`, never on `IBAdapter` or `AlpacaAdapter` directly.

**Use cases** (`backend/application/use_cases.py`) are plain async functions. No FastAPI `Request`, no HTTP concepts, no broker SDK types — only domain entities and the `BrokerAdapter` interface.

### TypeScript frontend layer rules

| Layer | Location | Allowed imports | Forbidden |
|---|---|---|---|
| **Domain** | `src/shared/domain/` | TypeScript types only | react, next, payload |
| **Application** | `src/shared/application/` | domain | react, next/server |
| **Infrastructure** | `src/shared/infrastructure/` | domain, application, any lib | react components |
| **UI** | `src/app/`, `src/components/` | everything | direct fetch inside components (use infrastructure) |
| **Modules** | `src/modules/` | own module's layers + shared domain | other modules' internals |

PayloadCMS collections (`src/collections/`) and globals (`src/globals/`) are infrastructure. Keep business rules in `src/shared/domain/rules/` or `src/modules/*/domain/rules/`.

### Where to put new code — decision tree

```
Is it a business concept with no framework dependency?
  → Domain (entities, rules, ports)

Is it orchestration logic that combines domain concepts?
  → Application (use cases)

Is it a connection to something external (broker, DB, cache, Next.js APIs)?
  → Infrastructure (adapters)

Is it an HTTP endpoint or a React component?
  → API router or UI component (outermost layer)
```

### What a port is and why it matters

A port is an interface defined in the domain that infrastructure implements. `BrokerAdapter` is a port. `CacheRevalidator` (in `src/shared/domain/ports/`) is a port. Ports let you swap implementations without touching domain or application code.

When adding a new external dependency, always ask: *does the domain need to define a port for this?* If application code needs to use it, yes.

---

## Project structure

```
botero-trade/
├── src/                          # Next.js + PayloadCMS (TypeScript)
│   ├── app/(frontend)/          # Trading dashboard pages
│   ├── app/(payload)/           # CMS admin panel
│   ├── shared/                  # Cross-cutting Clean Architecture (TS)
│   │   ├── domain/              # Ports, rules — no framework imports
│   │   ├── application/         # Use cases
│   │   ├── infrastructure/      # Next.js adapters
│   │   └── handlers/
│   ├── modules/                 # Feature modules (layout, pages, posts, users)
│   │   └── {module}/
│   │       ├── domain/
│   │       ├── application/
│   │       ├── infrastructure/
│   │       └── interface/       # React components for this module
│   ├── collections/             # PayloadCMS collections (infrastructure)
│   ├── globals/                 # PayloadCMS globals (infrastructure)
│   └── components/              # Shared React components (UI layer)
│
├── backend/                     # Python trading engine
│   ├── domain/entities.py       # Portfolio, Position, Order, Signal, Trade, Bar, BacktestResult
│   ├── application/use_cases.py # run_backtest(), fetch_market_data(), place_order(), get_portfolio()
│   ├── infrastructure/
│   │   ├── brokers/
│   │   │   ├── base.py          # BrokerAdapter — the port all brokers implement
│   │   │   ├── ib_adapter.py    # Interactive Brokers
│   │   │   └── alpaca_adapter.py# Alpaca
│   │   └── backtrader/
│   │       ├── base_strategy.py # BaseStrategy(bt.Strategy)
│   │       └── data_feeds.py    # create_data_feed(bars) → bt.feeds.PandasData
│   └── api/
│       ├── main.py              # FastAPI app + CORS
│       └── routers/
│           ├── market_data.py   # GET /api/market-data/{symbol}[/price]
│           ├── portfolio.py     # GET /api/portfolio/{broker}
│           └── strategy.py      # GET /api/strategy/list, POST /api/strategy/backtest
│
├── .claude/commands/            # Slash commands (see below)
├── docker-compose.yml           # web + api only (no DB)
├── Dockerfile                   # Next.js standalone image
├── backend/Dockerfile           # Python uvicorn image
├── backend/requirements.txt
├── backend/.venv/               # Python virtual environment (not committed)
└── package.json                 # pnpm root — name: "botero-trade"
```

---

## Key domain entities (Python)

```python
Bar(symbol, timestamp, open, high, low, close, volume)
Order(symbol, side, quantity, order_type, broker, status, ...)
Position(symbol, quantity, avg_cost, market_price, broker)
Trade(order_id, symbol, side, quantity, price, broker, executed_at)
Signal(symbol, side, strength 0–1, strategy_name)
Portfolio(broker, cash, positions[], trades[])
BacktestResult(strategy_name, symbol, initial_cash, final_value, trades[], metrics{})
Broker(enum): interactive_brokers | alpaca
```

---

## API endpoints (port 8000)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/market-data/{symbol}` | Historical OHLCV bars |
| GET | `/api/market-data/{symbol}/price` | Current price |
| GET | `/api/portfolio/{broker}` | Portfolio from one broker |
| GET | `/api/portfolio/` | All connected broker portfolios |
| GET | `/api/strategy/list` | Registered strategies |
| POST | `/api/strategy/backtest` | Run Backtrader backtest |
| — | `/api/docs` | Swagger UI |

---

## Dev commands

```bash
pnpm dev:all          # start everything (Next.js + Python API) — use this first
pnpm dev              # frontend only
pnpm dev:api          # Python API only (uses backend/.venv)
pnpm docker:up        # Docker Compose (web + api)
pnpm generate         # regenerate PayloadCMS types + importmap
```

---

## Available slash commands

| Command | Purpose |
|---|---|
| `/start` | Full startup checklist — prerequisites, env, install, launch |
| `/context` | Detailed architecture reference (entities, endpoints, env vars) |
| `/dev` | Dev environment reference and common task cheatsheet |
| `/add-strategy` | Guided workflow: add a new Backtrader strategy |
| `/add-broker` | Guided workflow: add a new broker adapter |

---

## Coding rules every agent must follow

1. **Never bypass the layer boundary.** If `api/routers/strategy.py` needs market data, it calls a use case, which calls the broker adapter — not the broker SDK directly.

2. **Never put business logic in routers or components.** HTTP handlers validate input and delegate. React components render and delegate. Logic lives in use cases or domain rules.

3. **New broker = new adapter only.** Adding Coinbase, Kraken, or any other broker means one new file in `infrastructure/brokers/`. Nothing else changes.

4. **New strategy = new file + one registry line.** Create the strategy in `infrastructure/backtrader/strategies/`, register it in `api/routers/strategy.py`. Nothing else changes.

5. **Pydantic schemas are not domain entities.** Request/response models in `api/routers/` are API contracts. Domain entities in `domain/entities.py` are business concepts. Keep them separate.

6. **No direct `fetch` in React components.** Data fetching belongs in `src/modules/*/infrastructure/` or `src/shared/infrastructure/`. Components receive data as props or via hooks that call infrastructure.

7. **Do not add error handling for impossible cases.** Trust the layer above to validate. Trust the broker adapter interface. Only handle errors at system boundaries (incoming HTTP, external API responses).
