# Botero Trade — Agent Context

This file is auto-loaded by Claude Code at the start of every session. Read it fully before writing any code.

---

## What this project is

Algorithmic trading monorepo combining:
- **Next.js 16 + PayloadCMS 3** (TypeScript) — trading dashboard UI + CMS admin at `src/`
- **Python Trading Engine** — institutional-grade engine with MCP data pipelines at `backend/`
- **8 MCP Servers** (~200+ tools) — Alpaca, GuruFocus, Finviz, Finnhub, FRED, Yahoo Finance, News, Unusual Whales
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

### Python backend layer rules (Modular Clean Architecture)

The backend is now structured into feature **modules**. Each module can be either *pure domain* (flat structure) or *hybrid* (split into `domain/` and `infrastructure/`).

| Layer | Location | Allowed imports | Forbidden |
|---|---|---|---|
| **Global Domain** | `backend/domain/entities.py` | Python stdlib only | any external library |
| **Module Domain** | `backend/modules/*/domain/` or `backend/modules/*.py` | stdlib, pandas, numpy, entities | any external API or SDK (e.g. yfinance, requests, finnhub) |
| **Module Infra** | `backend/modules/*/infrastructure/` | module domain, any library | — |
| **API** | `backend/api/` | modules, fastapi | direct broker SDK calls |

**Domain entities** (`backend/domain/entities.py`) are pure Python dataclasses. Never add framework decorators, ORM mappings, or Pydantic models here. Pydantic belongs in the API layer.

**Infrastructure Adapters** (e.g., `market_data_fetcher.py`, `finnhub_adapter.py`) are the ONLY files allowed to touch external APIs like yfinance, requests, or broker SDKs. The domain code must remain pure and fully testable without network access.

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
Is it a business concept or calculation with no API dependency?
  → Module Domain (e.g., modules/price_analysis/rsi_engine.py)

Is it orchestration logic that combines multiple module signals?
  → Hub / Engine within a Module Domain (e.g., modules/entry_decision/hub.py)

Is it a connection to something external (broker, DB, REST API, yfinance)?
  → Module Infrastructure (e.g., modules/flow_intelligence/infrastructure/uw_adapter.py)
```

---

## Project structure

```
botero-trade/
├── src/                          # Next.js + PayloadCMS (TypeScript)
│   ├── app/(frontend)/          # Trading dashboard pages
│   ├── app/(payload)/           # CMS admin panel
│   ├── shared/                  # Cross-cutting Clean Architecture (TS)
│   ├── modules/                 # Feature modules
│   ├── collections/             # PayloadCMS collections (infrastructure)
│   └── components/              # Shared React components (UI layer)
│
├── backend/                     # Python trading engine
│   ├── domain/entities.py       # Portfolio, Position, Order, Signal, Trade, Bar
│   ├── modules/                 # Feature-oriented Clean Architecture Modules
│   │   ├── price_analysis/      # RSI & Phase Timing (Pure Domain)
│   │   ├── volume_intelligence/ # Volume Profile & Kalman Filter (Pure Domain)
│   │   ├── pattern_recognition/ # Candlestick patterns via pandas-ta (Pure Domain)
│   │   ├── flow_intelligence/   # Whale flow (Domain) + Finnhub/UW/FRED (Infra)
│   │   ├── options_gamma/       # Gamma Regime (Domain) + yfinance chain (Infra)
│   │   ├── entry_decision/      # Entry Hub (Domain) + Price/VIX fetcher (Infra)
│   │   ├── portfolio_management/# Universe Filter, Alpha Scanner (Domain) + Finviz (Infra)
│   │   ├── execution/           # Paper Trading, Journal (Domain) + Broker adapters (Infra)
│   │   ├── simulation/          # Backtester, Autopsy (Domain) + Backtrader (Infra)
│   │   └── shared/              # Cache Utils, Global Ports
│   ├── _legacy/                 # Deprecated / Experimental code (LSTM, Sequence modeling)
│   └── api/
│       ├── main.py              # FastAPI app + CORS
│       └── routers/
│

├── tests/                       # Pytest suite (20 tests)
│   ├── conftest.py              # Shared fixtures (MongoDB test DB)
│   ├── test_risk_guardian.py     # 7 tests: DD, VIX, anti-martingale
│   ├── test_trailing_stop.py     # 5 tests: regime adaptation, floor/ceiling
│   └── test_trade_journal.py     # 6 tests: MongoDB persistence, patterns
│
├── .mcp.json                    # 7 MCP server configs (secrets via env vars)
├── pytest.ini
└── package.json
```

---

## MCP Servers (8 active)

All configured in `.mcp.json` with secrets via environment variables.

| Server | Tools | Plan | Primary Use |
|---|:-:|---|---|
| **Finviz** | 35 | Elite | Screening, sector performance, SEC filings |
| **GuruFocus** | 55 | Premium (USA) | QGARP scoring, insider tracking, guru analysis |
| **Alpaca** | 61 | Free (paper) | Execution + basic OHLCV data |
| **Finnhub** | 45 | Free | Earnings calendar, insider transactions, news |
| **FRED** | 12 | Free | Macro indicators (GDP, CPI, FFR, yield curve) |
| **Yahoo Finance** | 9 | Free | VIX, options chains, fallback data |
| **News Sentiment** | 4 | Free | FinBERT sentiment scoring |
| **Unusual Whales** | 20+ | Premium | Institutional flow, market tide, SPY delta, options alerts |

### Data Provider Hierarchy

1. **Finviz Elite** → PRIMARY for screening, sectors, market overview
2. **GuruFocus Premium** → PRIMARY for fundamentals, insiders, gurus (USA only)
3. **FRED** → PRIMARY for macro indicators
4. **Finnhub** → Earnings calendar + insider redundancy
5. **Alpaca** → Execution only (future: migrate to Interactive Brokers)
6. **Unusual Whales** → Institutional flow, macro gates, market sentiment
7. **Yahoo Finance** → Last resort fallback

---

## Key domain entities (Python)

```python
Bar(symbol, timestamp, open, high, low, close, volume)
Order(symbol, side, quantity, order_type, broker, status, ...)
Position(symbol, quantity, avg_cost, market_price, broker)
Trade(order_id, symbol, side, quantity, price, broker, executed_at)
Signal(symbol, side, strength 0–1, strategy_name)
Portfolio(broker, cash, positions[], trades[])
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

Full documentation for each command is in `.claude/SKILLS.md`.

| Command | Purpose |
|---|---|
| `/start` | Full startup checklist — prerequisites, env, install, launch |
| `/context` | Detailed architecture reference (entities, endpoints, env vars) |
| `/dev` | Dev environment reference and common task cheatsheet |
| `/add-strategy` | Guided workflow: add a new Backtrader strategy |
| `/add-broker` | Guided workflow: add a new broker adapter |
| `/find-finance-skills` | Descubrir e integrar nuevas herramientas financieras (librerías, APIs, MCP servers) |
| `/proposito-practico` | Activa directivas anti-sesgo y enfoca a la AI en el pragmatismo institucional |

---

## Operational Objectivity & AI Persona 
**Mandatory Paradigm**: In this project, the AI must empathize with the *operational purpose*, not the user. 
- **Practical over Academic**: The user trades mechanically. Options expire, gamma exposes, and market makers delta-hedge. These are observable, quantifiable forces, not "academic theories." Treat market mechanics as first-class deterministic facts. 
- **Zero Ritual Caution**: Remove generic financial disclaimers ("past performance is no guarantee...", "the market is volatile"). Only warn if a specific operational risk (e.g., illiquidity, slippage) is materially present.
- **Empirical Validation**: If the user states an observation, treat it as a working hypothesis and validate it with mechanics or data immediately, rather than pushing back initially seeking a false "academic balance".
- **Actionable Utility**: All technical answers regarding micro-structure, regimes, or flows must explicitly conclude: *How does it work? How do we measure it? When does it apply? What are its real limits?*

---

## Security — credential files are OFF LIMITS

**This is a hard rule. No exceptions.**

The following files contain secrets and must NEVER be read, written, viewed, cat'd, printed, or output by any AI agent:

- `.env`
- `.env.local`
- `.env.development`
- `.env.production`
- `.mcp.json`
- Any file matching `.env*` (except `.env.example`)

**What you CAN do:**
- Edit `.env.example` (it contains only placeholders, never real values)
- Tell the user what variables to add/change and let them edit manually
- Use `grep -c VARIABLE_NAME .env` to check if a variable exists (returns count, not content)
- Reference env var names in code via `process.env.X` or `os.getenv("X")`

**What you MUST NEVER do:**
- `cat .env`, `view_file .env`, or any command that outputs credential file contents
- Write or overwrite `.env`, `.env.local`, or `.mcp.json`
- Include credential values in your responses, code comments, or logs
- Copy credential values between files

Credentials leaking into LLM context = credentials leaking to the world. Treat these files like they don't exist.

---

## Coding rules every agent must follow

1. **Never bypass the layer boundary.** If `api/routers/strategy.py` needs market data, it calls a use case, which calls the broker adapter — not the broker SDK directly.

2. **Never put business logic in routers or components.** HTTP handlers validate input and delegate. React components render and delegate. Logic lives in use cases or domain rules.

3. **New broker = new adapter only.** Adding Coinbase, Kraken, or any other broker means one new file in `infrastructure/brokers/`. Nothing else changes.

4. **New strategy = new file + one registry line.** Create the strategy in `infrastructure/backtrader/strategies/`, register it in `api/routers/strategy.py`. Nothing else changes.

5. **Pydantic schemas are not domain entities.** Request/response models in `api/routers/` are API contracts. Domain entities in `domain/entities.py` are business concepts. Keep them separate.

6. **No direct `fetch` in React components.** Data fetching belongs in `src/modules/*/infrastructure/` or `src/shared/infrastructure/`. Components receive data as props or via hooks that call infrastructure.

7. **Do not add error handling for impossible cases.** Trust the layer above to validate. Trust the broker adapter interface. Only handle errors at system boundaries (incoming HTTP, external API responses).

8. **Never read or modify `.env` files.** Only `.env.example` may be edited. See the Security section above.

9. **All MCP adapters receive pre-fetched data.** Infrastructure adapters (`gurufocus_intelligence.py`, `finviz_intelligence.py`, `fred_macro_intelligence.py`) never call MCP tools directly. The orchestrator fetches MCP data and passes it to adapters for structured interpretation. This maintains Clean Architecture boundaries.

10. **Data providers use fallback chains.** Every data method should try MCP first (when data is provided), then fall back to SDK/scraper. Never fail silently — always log the fallback.

### Known Layer Violations

- `backend/application/lstm_model.py` — ML model in Application layer (should be in `infrastructure/models/`). Planned for future refactor.
