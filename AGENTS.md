# Botero Trade — Agent Context

This file is auto-loaded by OpenAI Codex CLI at the start of every session. Read it fully before writing any code.


---

## CRITICAL DIRECTIVE: ZERO-BIAS TRADING
**Full behavioral rules in `.agents/skills/operational-purpose/SKILL.md`.**
Summary: This is a sandbox calibration environment. Zero disclaimers. The user is the System Architect. Mechanical truth over theory. No Discovery Sabotage. No academic hedging. Deterministic language for deterministic mechanics.

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
**Full structural rules in `.agents/skills/clean-architecture/SKILL.md`.**
Summary: Dependencies point inward. Domain knows nothing about infrastructure. Use Cases depend on Ports (ABCs), never concrete adapters. Module structure follows Screaming Architecture under `backend/modules/`.

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
│   ├── modules/                 # Feature-oriented Hexagonal Architecture Modules
│   │   ├── price_analysis/      # RSI & Phase Timing (Pure Domain)
│   │   ├── volume_intelligence/ # Volume Profile & Kalman Filter (Pure Domain)
│   │   ├── pattern_recognition/ # Candlestick patterns via pandas-ta (Pure Domain)
│   │   ├── flow_intelligence/   # Whale flow (Domain) + Finnhub/UW/FRED (Infra)
│   │   ├── options_gamma/       # Gamma Regime (Domain) + yfinance chain (Infra)
│   │   ├── entry_decision/      # Entry Hub (Domain) + Price/VIX fetcher (Infra)
│   │   ├── portfolio_management/# Universe Filter, Alpha Scanner (Domain) + Finviz (Infra)
│   │   ├── execution/           # Paper Trading, Journal (Domain) + Broker adapters (Infra)
│   │   ├── simulation/          # Backtester, Autopsy (Domain) + Backtrader (Infra)
│   │   ├── volatility_regime/   # Vol Regime Classification (Pure Domain)
│   │   └── shared/              # Cache Utils, Global Ports, Market Data entities
│   ├── _legacy/                 # Deprecated / Experimental code (LSTM, Sequence modeling)
│   ├── daemons/                 # Background runners (Quality, Speculative — delivery mechanism)
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

5. **Pydantic schemas are not domain entities.** Request/response models in `api/routers/` are API contracts. Domain entities in `modules/*/domain/entities/` are business concepts. Keep them separate.

6. **No direct `fetch` in React components.** Data fetching belongs in `src/modules/*/infrastructure/` or `src/shared/infrastructure/`. Components receive data as props or via hooks that call infrastructure.

7. **Do not add error handling for impossible cases.** Trust the layer above to validate. Trust the broker adapter interface. Only handle errors at system boundaries (incoming HTTP, external API responses).

8. **Never read or modify `.env` files.** Only `.env.example` may be edited. See the Security section above.

9. **All MCP adapters receive pre-fetched data.** Infrastructure adapters (`gurufocus_intelligence.py`, `finviz_intelligence.py`, `fred_macro_intelligence.py`) never call MCP tools directly. The orchestrator fetches MCP data and passes it to adapters for structured interpretation. This maintains Clean Architecture boundaries.

10. **Daemon data providers use fallback chains.** Code in `backend/daemons/` and `backend/scripts/` should try MCP first, then fall back to SDK/scraper. Never fail silently — always log the fallback. Module infrastructure adapters (`backend/modules/*/infrastructure/`) read ONLY from the Vault (Neon PostgreSQL via TimescaleDataStore). They do NOT have fallback chains to external APIs. See Rule 13.

11. **Simplicity first.** No features beyond what was asked. No abstractions for single-use code. No speculative "flexibility" or "configurability." If 200 lines could be 50, rewrite it. The test: would a senior engineer say this is overcomplicated? If yes, simplify.

12. **Surgical changes.** Every changed line must trace directly to the user's request. Don't "improve" adjacent code, comments, or formatting. Match existing style. If you notice unrelated dead code, mention it — don't delete it. Remove only imports/variables/functions that YOUR changes made unused.

13. **Vault-First data access.** Production modules (everything under `backend/modules/`) MUST read market data exclusively from `TimescaleDataStore` (Neon PostgreSQL). Direct calls to yfinance, requests, httpx, or any external API for market data are FORBIDDEN in modules. Only `backend/daemons/` and `backend/scripts/` may call external APIs. The Vault Daemon is the single writer; modules are readers only.

- `backend/daemons/` — Delivery mechanism (daemon entry points). Not a Clean Architecture application layer — these are background runners equivalent to API routers.
