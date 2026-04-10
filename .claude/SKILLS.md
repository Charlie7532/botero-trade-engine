# Botero Trade — Available Skills

This file documents all slash commands available in this project.
Commands are defined in `.claude/commands/` and invoked by typing `/command-name`.

---

## `/start`
**File:** `.claude/commands/start.md`
**Use when:** Opening the project for the first time, on a new machine, or after a fresh clone.

Runs a full environment startup checklist:
1. Verifies Node, pnpm, Python, Docker are installed — installs any that are missing
2. Creates `.env` from `.env.example` if it doesn't exist and warns about required credentials
3. Installs frontend dependencies via `pnpm install`
4. Creates the Python virtual environment at `backend/.venv` and installs `requirements.txt`
5. Starts all services via `pnpm dev:all`
6. Verifies both services respond (health check)
7. Provides a troubleshooting table for common failures

**Starts:**
- `[web]` Next.js + PayloadCMS → http://localhost:3000
- `[api]` Python FastAPI → http://localhost:8000 (Swagger at `/docs`)

---

## `/context`
**File:** `.claude/commands/context.md`
**Use when:** You need a detailed architecture reference mid-session, or `CLAUDE.md` isn't enough detail.

Loads the full project reference:
- Complete directory tree with per-file descriptions
- All domain entities with their fields
- All API endpoints with methods and paths
- Full environment variable table
- Tech stack summary
- Dev command cheatsheet

> Note: `CLAUDE.md` is auto-loaded and covers the essentials. Use `/context` when you need the deeper reference.

---

## `/dev`
**File:** `.claude/commands/dev.md`
**Use when:** You need a quick reminder of how to start services, run specific tasks, or configure IB ports.

Covers:
- Local dev startup (with and without Docker)
- Service URLs table
- Common task commands (generate types, run migrations, health checks)
- Interactive Brokers port configuration (TWS vs Gateway, paper vs live)
- Environment variable checklist
- Links to other available skills

---

## `/add-strategy`
**File:** `.claude/commands/add-strategy.md`
**Use when:** You want to implement a new trading strategy.

Guided workflow that:
1. Asks for the strategy name and logic
2. Asks for tunable parameters
3. Creates the strategy file in `backend/infrastructure/backtrader/strategies/`
   extending `BaseStrategy` — which already handles order logging, trade tracking, and P&L
4. Registers it in `backend/api/routers/strategy.py`
5. Shows the exact `curl` command to run the backtest via the API

Includes a reference table of common Backtrader indicators (SMA, EMA, RSI, MACD, Bollinger Bands, ATR, Stochastic).

**Clean Architecture:** Strategy files live in infrastructure. They never import from `api/` or `application/`. Use cases in `application/use_cases.py` call `run_backtest()` which accepts any `BaseStrategy` subclass.

---

## `/add-broker`
**File:** `.claude/commands/add-broker.md`
**Use when:** You want to connect a new broker or data source (e.g. Coinbase, Kraken, TD Ameritrade).

Guided workflow that:
1. Asks which broker and which Python SDK to use
2. Adds the broker to the `Broker` enum in `backend/domain/entities.py`
3. Creates the adapter file in `backend/infrastructure/brokers/` implementing all abstract methods from `BrokerAdapter`
4. Registers the adapter in all three routers (`market_data.py`, `portfolio.py`, `strategy.py`)
5. Adds credentials to `.env.example`
6. Adds the SDK to `backend/requirements.txt`
7. Shows how to test the connection

**Clean Architecture:** The adapter implements the `BrokerAdapter` port defined in the domain. Application and API code never reference the concrete adapter — only the abstract interface.

---

## Clean Architecture reminder

All skills generate code that follows the dependency rule:

```
API / UI  →  Infrastructure  →  Application  →  Domain
```

- **Domain** (`backend/domain/`, `src/shared/domain/`) — zero framework imports
- **Application** (`backend/application/`, `src/shared/application/`) — orchestrates domain, no HTTP or broker SDK
- **Infrastructure** (`backend/infrastructure/`, `src/shared/infrastructure/`) — implements ports, uses external libraries
- **API / UI** (`backend/api/`, `src/app/`, `src/components/`) — outermost layer, delegates everything inward

If a skill asks you to place code somewhere that would violate this rule, correct the placement and note why.

---

## Adding a new skill

1. Create `.claude/commands/{skill-name}.md`
2. Add an entry to this file (`SKILLS.md`)
3. Reference it in `CLAUDE.md` under the "Available slash commands" table
4. Commit both files together
