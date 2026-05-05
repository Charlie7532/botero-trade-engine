# Botero Trade

> **Misión:** Superar consistentemente los retornos del mercado y lograr un crecimiento exponencial del capital (10x) a través de una ejecución institucional impecable. Para **QUALITY**, identificar monopolios naturales inexpugnables, entrar con máxima convicción en el punto de inflexión del ciclo, y permitir que la calidad del negocio genere compounding masivo. Para **SPECULATIVE**, extraer retornos absolutos agresivos capitalizando las dislocaciones temporales, la ignorancia del retail y las obligaciones mecánicas de los dealers, operando siempre bajo un mandato de asimetría 5:1 y riesgo de ruina cero.

> **Visión:** Ser el estándar global de fondos de inversión algorítmicos — reproducible solo por quienes codifiquen principios con la misma disciplina. Una máquina libre de sesgo emocional, gobernada por los modelos decisionales de los mejores inversores de la historia, que se alinea matemáticamente con las leyes físicas del mercado para extraer riqueza de manera predecible, segura e implacable.

### Institutional Values

| Value                          | Definition                                                                            |
| ------------------------------ | ------------------------------------------------------------------------------------- |
| **Zero-Bias**                  | Truth is in the facts, not in opinions.                                               |
| **Radical Concentration**      | 5000 → 5-10. Over-diversification is for those who don't know what they own.          |
| **Defense First**              | Capital must survive before it grows. Waiting IS a position.                          |
| **Asymmetry or Nothing**       | If there's no 5:1, there's no trade.                                                  |
| **Mathematical Truth**         | Nothing reaches production without walk-forward validation.                           |
| **Relentless Forensics**       | Detect → Learn → Retrain → Prevent. Wins are questioned as much as losses.            |
| **Pattern Recognition**        | Everything repeats. Every event is "another one of those."                            |
| **Systematic Anti-Stupidity**  | Always invert: what guarantees failure? Avoid that first.                             |
| **Architectural Purity**       | Clean Hexagonal Architecture. Dependencies point inward.                             |

---

## Architecture

> 📐 Full architecture documentation: [`docs/architecture-diagram.md`](docs/architecture-diagram.md)
> 🧩 Module internals: [`docs/architecture-modules-internal.md`](docs/architecture-modules-internal.md)
> 🧠 Expert committee: [`docs/architecture-expert-committee.md`](docs/architecture-expert-committee.md)

### Dual-Mandate System

The engine operates two **fully independent** trading departments with zero cross-contamination:

| | QUALITY (80%) | SPECULATIVE (20%) |
|---|---|---|
| **Philosophy** | Hohn · Munger · Druckenmiller | Karsan · Eifert · PTJ · Seykota |
| **Selection** | `QualityResearchPipeline` — fundamental only | `SpeculativeScanner` — microstructure only |
| **Qualification** | `QualityQualifier` — daily bars, Grade A | `SpeculativeQualifier` — hourly bars, Grade B |
| **Entry Gate** | `QualityEntryGate` — VP · RSI · Pattern | `SpeculativeEntryHub` — Gamma · Flow · Memory Guard |
| **Orchestrator** | `QualityOrchestrator` — daily cadence | `SpeculativeOrchestrator` — 15min cadence |
| **Surveillance** | `SurveillanceLoop` — moat decay | `SpeculativeSurveillance` — ATR · time · RS stops |
| **Exit Engine** | `QualityExitEngine` — thesis death | `SpeculativeExitEngine` — mechanical stops |
| **Broker** | Alpaca (QUALITY account) | Alpaca (SPECULATIVE account) |

```mermaid
graph TB
    subgraph CIO["🏛️ CIO (Dalio) — Budget Allocation"]
        MANDATE["DailyMandate<br/>80% QUALITY / 20% SPECULATIVE<br/>Regime-aware rebalancing"]
    end

    subgraph QUALITY["QUALITY Department"]
        QR["Research"] --> QQ["Qualifier"] --> QE["Entry Gate"] --> QO["Orchestrator"]
    end

    subgraph SPECULATIVE["SPECULATIVE Department"]
        SS["Scanner"] --> SQ["Qualifier"] --> SE["Entry Hub"] --> SO["Orchestrator"]
    end

    MANDATE -->|"80% budget"| QR
    MANDATE -->|"20% budget"| SS
```

### Hexagonal Architecture — Dependency Rule

```
┌─────────────────────────────────────────────────┐
│  API / Daemons (outer — delivery mechanisms)     │
│  ┌───────────────────────────────────────────┐  │
│  │  Infrastructure (adapters, SDKs, PG)       │  │
│  │  ┌─────────────────────────────────────┐  │  │
│  │  │  Application (use_cases, dtos)       │  │  │
│  │  │  ┌───────────────────────────────┐  │  │  │
│  │  │  │  Domain (entities, ports, rules)│  │  │  │
│  │  │  │  • ZERO SDK imports            │  │  │  │
│  │  │  │  • ZERO infrastructure imports │  │  │  │
│  │  │  │  • Dependencies via Ports (ABC)│  │  │  │
│  │  │  └───────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

---

## Project Structure

```
botero-trade/
├── src/                              # Next.js 16 + PayloadCMS 3 (TypeScript)
│   ├── app/
│   │   ├── (frontend)/              # Trading dashboard UI
│   │   ├── (payload)/               # CMS admin panel
│   │   └── api/agent/[slug]/        # Managed Agent Sessions API (streaming)
│   ├── shared/                      # Clean Architecture (TS)
│   │   ├── domain/                  # Types, ports, rules
│   │   │   ├── ports/               # IVaultAdapter, CacheRevalidator
│   │   │   └── rules/               # publishStateRules
│   │   ├── application/             # Use cases
│   │   │   └── useCases/            # assignDefaultPublishTimestamp, revalidateRedirectsState
│   │   ├── infrastructure/          # API clients, adapters
│   │   │   ├── vault/               # claudeVaultAdapter (AES-256-GCM encrypted credentials)
│   │   │   ├── next/                # NextCacheRevalidator
│   │   │   └── vaultFactory.ts      # Vault adapter composition root
│   │   └── handlers/                # Shared lifecycle hook wrappers (operation-filtered, guarded)
│   ├── collections/                 # PayloadCMS collections (15)
│   │   ├── Users/                   # Authentication + roles
│   │   ├── Portfolios/              # Portfolio management (lifecycle manifest)
│   │   ├── PortfolioMemberships/    # Multi-tenant access
│   │   ├── BrokerAccounts/          # Encrypted broker credentials
│   │   ├── Bots/                    # AI trading bots (domain/infrastructure/interface layers)
│   │   ├── BotAssignments/          # Bot ↔ Portfolio mapping
│   │   ├── AgentSkills/             # Skill definitions synced to agent personas
│   │   ├── McpServers/              # MCP server registry (domain rules + sync hooks)
│   │   ├── ProjectVaults/           # Encrypted credential vaults per project
│   │   ├── Instruments/             # Tracked securities
│   │   ├── CalibrationProfiles/     # Strategy calibration
│   │   ├── CandidateScreenings/     # Research pipeline results
│   │   ├── RegimePhases/            # Market regime tracking
│   │   ├── TradeSnapshots/          # Execution snapshots
│   │   └── Media/                   # File uploads
│   ├── globals/                     # Header, SiteSettings
│   ├── modules/                     # Feature modules (auth)
│   └── components/                  # Shared React components
│       ├── AgentChat/               # Managed agent chat (Markdown + Mermaid rendering)
│       ├── Admin/                   # Dashboard customizations
│       ├── BeforeDashboard/         # Admin dashboard widgets
│       ├── ConfigurableLogo/        # Dynamic logo from SiteSettings
│       ├── DynamicColors/           # Theme-aware color system
│       └── ...                      # 25+ reusable components
│
├── backend/                         # Python trading engine
│   ├── modules/                     # 11 Clean Architecture modules
│   │   ├── portfolio_management/    # Selection & qualification (QUALITY + SPECULATIVE)
│   │   ├── entry_decision/          # Entry gates (QualityEntryGate + SpeculativeEntryHub)
│   │   ├── execution/               # Orchestrators, surveillance, journal
│   │   ├── flow_intelligence/       # Whale flow, event calendar, FRED macro
│   │   ├── options_gamma/           # GEX, max pain, gamma regime
│   │   ├── price_analysis/          # Price phase detection, RSI intelligence
│   │   ├── volume_intelligence/     # Kalman volume, volume profile
│   │   ├── pattern_recognition/     # Candlestick, VCP detection
│   │   ├── rotation_intelligence/   # Weinstein stages, Pring cycles
│   │   ├── simulation/              # Walk-forward, triple barrier, LSTM
│   │   └── shared/                  # Cross-module entities, cache utilities
│   ├── api/                         # FastAPI delivery mechanism
│   │   ├── main.py                  # FastAPI app + CORS
│   │   ├── factories/               # Composition Root (dependency injection)
│   │   └── routers/                 # market_data · portfolio · strategy · orders · simulation
│   ├── daemons/                     # Background runners (delivery mechanism)
│   │   ├── quality_daemon.py        # Daily QUALITY scan loop
│   │   └── speculative_daemon.py    # 5-minute SPECULATIVE scan loop
│   ├── sql/                         # Database migrations
│   ├── scripts/                     # Operational utilities
│   ├── tests/                       # Backend test suite
│   ├── _legacy/                     # Deprecated experimental code
│   ├── requirements.txt             # Python dependencies
│   └── Dockerfile                   # API container definition
│
├── docs/                            # Extended documentation (see below)
├── .agents/skills/                  # 18 AI agent specialist skills
├── tests/                           # Root test suite
├── docker-compose.yml               # Orchestrates api + Cloudflare tunnel
└── package.json                     # pnpm workspace root
```

### Backend Module Architecture

Each module follows the same internal structure (some layers optional for pure-computation modules):

```
backend/modules/<module_name>/
├── domain/
│   ├── entities/        # Pure Python dataclasses — business concepts
│   ├── ports/           # Abstract interfaces (ABC) — dependency contracts
│   └── rules/           # Business constants and validation rules
├── application/
│   ├── use_cases/       # Orchestration logic — domain + ports, no infrastructure
│   └── dtos/            # Data transfer objects for cross-layer communication
└── infrastructure/      # Adapters implementing ports — SDKs, databases, APIs
```

**Pure computation modules** (`price_analysis`, `volume_intelligence`, `pattern_recognition`) have no `infrastructure/` folder — they receive data as input and return computed results with zero I/O.

### PayloadCMS Collection Architecture

Complex collections follow Clean Architecture internally with domain/infrastructure/interface layers:

```
src/collections/<CollectionName>/
├── index.ts             # Payload collection config (hooks, access, fields)
├── fields.ts            # Field definitions
├── lifecycle.ts         # Lifecycle manifest (hook composition)
├── domain/
│   └── rules/           # Business rules and validation
├── infrastructure/
│   └── hooks/           # Side-effect hooks (sync, cascade, adapters)
└── interface/
    └── hooks/           # UI-layer hooks (admin customizations)
```

Collections with this layered structure: **Bots**, **McpServers**, **AgentSkills**.

---

## Getting Started

### Prerequisites

- [Node.js](https://nodejs.org) `>=20.9.0` (tested on 22.x)
- [pnpm](https://pnpm.io) `>=9`
- [Python](https://python.org) `3.12+`
- [Docker + Docker Compose](https://docs.docker.com/compose/) (optional — for containerized API)
- An external PostgreSQL database (see [Database](#database) below)

### 1. Clone and configure environment

```bash
git clone https://github.com/Charlie7532/botero-trade-engine.git
cd botero-trade-engine
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

| Service            | URL                         |
| ------------------ | --------------------------- |
| Frontend + CMS     | http://localhost:3000       |
| PayloadCMS admin   | http://localhost:3000/admin |
| Trading Engine API | http://localhost:8000       |
| API docs (Swagger) | http://localhost:8000/docs  |

### 2b. Docker Compose (containerized API)

```bash
docker compose up
```

Starts the `api` service (port 8000) and optionally a Cloudflare tunnel for remote access. The database is **not** managed by Docker — set `POSTGRES_URL` in `.env` to your external database.

> **Note:** The frontend (Next.js) is deployed separately to Vercel and is not included in the Docker Compose setup.

---

## Database

PostgreSQL is hosted **externally** (Neon) — not inside Docker — so your data survives container rebuilds and deployments.

The database stores:
- **PayloadCMS data** (`public.*`) — 15 collections, users, CMS content
- **Trading engine data** (`engine.*`) — trade journals, OHLCV bars (662K+), macro indicators, features, trading state
- **TimescaleDB** — time-series optimized hypertables for market data
- **pgvector** — 9-dimensional embeddings for trade similarity search

| Provider                                               | Free tier | Notes                                     |
| ------------------------------------------------------ | --------- | ----------------------------------------- |
| [Neon](https://neon.tech)                              | Yes       | Serverless, branching (current setup)     |
| [Vercel Postgres](https://vercel.com/storage/postgres) | Yes       | Best for Vercel deployments               |
| [Supabase](https://supabase.com)                       | Yes       | Includes auth, storage, realtime          |
| Local instance                                         | —         | `postgres://user:pw@127.0.0.1:5432/botero`|

Set the connection string in `.env`:

```
POSTGRES_URL=postgres://user:password@host:5432/database
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values. Key variables grouped by service:

### Core Infrastructure

| Variable                 | Description                               |
| ------------------------ | ----------------------------------------- |
| `POSTGRES_URL`           | External PostgreSQL connection string     |
| `DATABASE_URL`           | Neon pooled connection (PayloadCMS)       |
| `DATABASE_URL_UNPOOLED`  | Neon direct connection (migrations)       |
| `PAYLOAD_SECRET`         | Secret key for JWT encryption             |
| `NEXT_PUBLIC_SERVER_URL` | Public URL of the frontend                |
| `TRADING_API_URL`        | URL of the Python trading engine          |

### Broker Credentials

| Variable                          | Description                               |
| --------------------------------- | ----------------------------------------- |
| `ALPACA_API_KEY`                  | Alpaca API key                            |
| `ALPACA_SECRET_KEY`               | Alpaca secret key                         |
| `ALPACA_BASE_URL`                 | Alpaca endpoint (default: paper trading)  |
| `IB_HOST` / `IB_PORT` / `IB_CLIENT_ID` | Interactive Brokers TWS/Gateway     |
| `BROKER_CREDENTIAL_ENCRYPTION_KEY`| AES key for broker credential storage     |

### MCP Data Providers

| Variable                 | Description                               |
| ------------------------ | ----------------------------------------- |
| `FINNHUB_API_KEY`        | Finnhub API key                           |
| `FINVIZ_API_KEY`         | Finviz Elite API key                      |
| `GURUFOCUS_API_TOKEN`    | GuruFocus Premium API token               |
| `FRED_API_KEY`           | FRED (Federal Reserve) API key            |

### AI & Agent Infrastructure

| Variable                 | Description                               |
| ------------------------ | ----------------------------------------- |
| `ANTHROPIC_API_KEY`      | Anthropic API key for managed agent sessions |
| `ANTHROPIC_ADMIN_KEY`    | Admin key for usage dashboard widget      |

### Deployment

| Variable                      | Description                               |
| ----------------------------- | ----------------------------------------- |
| `CLOUDFLARE_TUNNEL_TOKEN`     | Cloudflare tunnel for API exposure        |
| `BLOB_READ_WRITE_TOKEN`       | Vercel Blob storage token                 |
| `BREVO_API_KEY`               | Transactional email (Brevo)               |

---

## Managed Agent Sessions

The platform integrates **Anthropic Claude** as the backbone for AI-powered trading bots. Each bot is a managed agent with its own encrypted credential vault and skill configuration.

```mermaid
graph LR
    subgraph CMS["PayloadCMS Collections"]
        BOTS["Bots"] --> SKILLS["AgentSkills"]
        BOTS --> MCP["McpServers"]
        BOTS --> VAULT["ProjectVaults"]
    end

    subgraph SHARED["Shared Infrastructure"]
        VPORT["IVaultAdapter (port)"] --> VADAPT["claudeVaultAdapter"]
        VADAPT --> ENC["AES-256-GCM encryption"]
    end

    subgraph API["Next.js API"]
        ROUTE["/api/agent/[slug]"] --> VADAPT
    end

    BOTS -->|"lifecycle hooks"| VADAPT
```

| Component | Location | Role |
|---|---|---|
| **Bots** collection | `src/collections/Bots/` | Bot definitions with domain rules, Anthropic adapter, lifecycle hooks |
| **AgentSkills** collection | `src/collections/AgentSkills/` | Skill definitions synced from `.agents/skills/` |
| **McpServers** collection | `src/collections/McpServers/` | MCP server registry with domain rules and sync hooks |
| **ProjectVaults** collection | `src/collections/ProjectVaults/` | Encrypted credential vaults per project |
| **IVaultAdapter** port | `src/shared/domain/ports/` | Abstract vault interface |
| **claudeVaultAdapter** | `src/shared/infrastructure/vault/` | AES-256-GCM encrypted credential injection |
| **AgentChat** component | `src/components/AgentChat/` | Streaming chat UI with Markdown + Mermaid rendering |
| **Agent API** | `src/app/api/agent/[slug]/` | Managed agent session endpoint |

---

## MCP Servers (8 active)

All configured in `.mcp.json` with secrets via environment variables.

| Server | Tools | Plan | Primary Use |
|---|:-:|---|---|
| **Finviz** | 35 | Elite | Screening, sector performance, SEC filings |
| **GuruFocus** | 55 | Premium (USA) | QGARP scoring, insider tracking, guru analysis |
| **Alpaca** | 61 | Free (paper) | Execution + OHLCV data |
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
5. **Unusual Whales** → Institutional flow, macro gates, market sentiment
6. **Alpaca** → Execution only (future: migrate to Interactive Brokers)
7. **Yahoo Finance** → Last resort fallback

---

## API Endpoints (port 8000)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/market-data/{symbol}` | Historical OHLCV bars |
| GET | `/api/market-data/{symbol}/price` | Current price |
| GET | `/api/portfolio/{broker}` | Portfolio from one broker |
| GET | `/api/portfolio/` | All connected broker portfolios |
| GET | `/api/strategy/list` | Registered strategies |
| POST | `/api/strategy/backtest` | Run backtest |
| POST | `/api/orders/` | Submit an order |
| — | `/api/docs` | Swagger UI |

### Next.js API Routes

| Method | Path | Description |
|---|---|---|
| POST | `/api/agent/[slug]` | Managed agent session (streaming Anthropic chat) |

---

## Port / Adapter Map

| Module | Port (domain) | Adapter (infrastructure) | Source |
|---|---|---|---|
| **entry_decision** | `EntryMarketDataPort` | `MarketDataFetcher` | yfinance |
| **entry_decision** | `FlowDataPort` | `UnusualWhalesIntelligence` | UW MCP |
| **execution** | `BrokerPort` | `AlpacaAdapter` × 2 | Alpaca SDK |
| **execution** | `TradeJournalPort` | `PostgresTradeJournalAdapter` | PostgreSQL |
| **execution** | `InstrumentBlacklistPort` | `PostgresBlacklistAdapter` | PostgreSQL |
| **options_gamma** | `OptionsDataPort` | `YFinanceOptionsAdapter` | yfinance |
| **flow_intelligence** | `CalendarDataPort` | `FinnhubAdapter` | Finnhub MCP |
| **portfolio_management** | `FundamentalDataPort` | `GuruFocusAdapter` | GuruFocus MCP |
| **portfolio_management** | `ScreenerPort` | `FinvizAdapter` | Finviz MCP |
| **portfolio_management** | `SectorDataPort` | `SectorFlowAdapter` | Finviz + UW |
| **portfolio_management** | `MacroDataPort` | `MacroDataAdapter` | FRED MCP |
| **portfolio_management** | `InstrumentRepoPort` | `PayloadInstrumentsAdapter` | PayloadCMS |
| **rotation_intelligence** | `RotationDataPort` | `YahooRotationAdapter` | yfinance |
| **simulation** | `HistoricalDataPort` + 9 more | TimescaleDB adapters | PostgreSQL |

### TypeScript Port / Adapter Map

| Layer | Port (domain) | Adapter (infrastructure) | Source |
|---|---|---|---|
| **Vault** | `IVaultAdapter` | `claudeVaultAdapter` | PayloadCMS + AES-256-GCM |
| **Cache** | `CacheRevalidator` | `NextCacheRevalidator` | Next.js `revalidateTag` |

---

## Scripts Reference

| Command             | Description                                                      |
| ------------------- | ---------------------------------------------------------------- |
| `pnpm dev:all`      | Start frontend + Python API together (recommended for local dev) |
| `pnpm dev`          | Frontend only (Next.js dev server with Turbopack)                |
| `pnpm dev:api`      | Python API only (uvicorn with hot reload)                        |
| `pnpm build`        | Build Next.js for production                                     |
| `pnpm start`        | Start Next.js production server                                  |
| `pnpm generate`     | Regenerate PayloadCMS types + importmap                          |
| `pnpm docker:up`    | Start API via Docker Compose                                     |
| `pnpm docker:build` | Rebuild Docker images                                            |
| `pnpm docker:down`  | Stop all Docker services                                         |
| `pnpm graphify`     | Scan codebase and generate knowledge graph                       |

---

## Deployment

### Frontend → Vercel

The frontend (Next.js + PayloadCMS) deploys to Vercel:

1. Push this repo to GitHub
2. Import it on [vercel.com](https://vercel.com)
3. Set **Root Directory** to `/` (the repo root — Vercel auto-detects Next.js)
4. Add all environment variables from `.env.example` in the Vercel dashboard
5. Vercel handles builds and deploys automatically on push

The project is configured for `@payloadcms/db-vercel-postgres` and `@payloadcms/storage-vercel-blob`.

### Trading Engine → Self-hosted

The Python `api` service requires persistent server infrastructure (it connects to broker APIs and runs long-lived daemon processes):

```bash
docker compose up -d api
```

Set `TRADING_API_URL` in your Vercel environment variables to point to your server's public IP/domain.

For remote access without a static IP, the included Cloudflare tunnel service exposes the API through your domain:

```bash
docker compose up -d  # starts api + tunnel
```

---

## Tech Stack

| Layer                   | Technology                                |
| ----------------------- | ----------------------------------------- |
| Frontend framework      | Next.js 16.1 (App Router, Turbopack)      |
| CMS                     | PayloadCMS 3                              |
| UI components           | HeroUI 3, Radix UI, Tailwind CSS 4        |
| Animations              | Framer Motion                             |
| Language (frontend)     | TypeScript 5.7                            |
| React                   | React 19.2                                |
| Trading engine          | Python 3.12 + FastAPI                     |
| Architecture            | Modular Clean / Hexagonal (11 modules)    |
| ML Pipeline             | PyTorch LSTM + GradientBoosting           |
| Data processing         | pandas, numpy, scikit-learn               |
| Market data             | 8 MCP Servers (~241 tools)                |
| AI agents               | Anthropic Claude (managed sessions)       |
| Broker                  | Alpaca × 2 (QUALITY + SPECULATIVE)        |
| Database                | PostgreSQL 16 (Neon) + TimescaleDB        |
| Vector search           | pgvector (9D embeddings)                  |
| Credential security     | AES-256-GCM vault encryption              |
| Codebase graph          | Graphify                                  |
| Container orchestration | Docker Compose                            |
| Frontend deployment     | Vercel                                    |
| API tunneling           | Cloudflare Tunnel                         |
| Email                   | Brevo (transactional)                     |
| Rich text rendering     | react-markdown + remark-gfm + Mermaid     |

---

## Documentation Index

Detailed documentation lives in [`docs/`](docs/):

| Document | Description |
|---|---|
| [architecture-diagram.md](docs/architecture-diagram.md) | System-level architecture: dual-mandate flow, composition root, entry/exit pipelines, storage layout, port/adapter map |
| [architecture-modules-internal.md](docs/architecture-modules-internal.md) | Internal structure of each backend module: entities, ports, adapters, cross-module dependencies |
| [architecture-expert-committee.md](docs/architecture-expert-committee.md) | Expert personas (Dalio, Hohn, Munger, Druckenmiller, Karsan, Eifert, PTJ, Seykota, Weinstein, Pring), decision chains, and skill mappings |
| [CLEAN-Payload.md](docs/CLEAN-Payload.md) | Clean Architecture patterns for PayloadCMS: lifecycle manifests, hook extraction, route boundaries |
| [PR_DESCRIPTION.md](docs/PR_DESCRIPTION.md) | Hexagonal architecture migration changelog (Phases 1-3) |
| [dynamic-font-strategy.md](docs/dynamic-font-strategy.md) | Dynamic Google Fonts integration via SiteSettings |
| [how-to-add-blocks.md](docs/how-to-add-blocks.md) | Guide for adding new PayloadCMS content blocks |
| [session-portfolio-intelligence.md](docs/session-portfolio-intelligence.md) | Historical session notes: portfolio intelligence system implementation |

### AI Agent Context Files

| File | Loaded by |
|---|---|
| [AGENTS.md](AGENTS.md) | OpenAI Codex CLI |
| [GEMINI.md](GEMINI.md) | Gemini CLI / Code Assist |
| [CLAUDE.md](CLAUDE.md) | Claude Code |

These files contain the same core rules (Clean Architecture, security, coding standards) tailored to each AI agent's format. See `.agents/skills/` for 18 specialist skill definitions.
