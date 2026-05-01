# Botero Trade

> **Misión:** Superar consistentemente los retornos del mercado y lograr un crecimiento exponencial del capital (10x) a través de una ejecución institucional impecable. Para **QUALITY**, identificar monopolios naturales inexpugnables, entrar con máxima convicción en el punto de inflexión del ciclo, y permitir que la calidad del negocio genere compounding masivo. Para **SPECULATIVE**, extraer retornos absolutos agresivos capitalizando las dislocaciones temporales, la ignorancia del retail y las obligaciones mecánicas de los dealers, operando siempre bajo un mandato de asimetría 5:1 y riesgo de ruina cero.

> **Visión:** Ser el estándar global de fondos de inversión algorítmicos — reproducible solo por quienes codifiquen principios con la misma disciplina. Una máquina libre de sesgo emocional, gobernada por los modelos decisionales de los mejores inversores de la historia, que se alinea matemáticamente con las leyes físicas del mercado para extraer riqueza de manera predecible, segura e implacable.

### Valores Institucionales

| Valor                          | Definición                                                                            |
| ------------------------------ | ------------------------------------------------------------------------------------- |
| **Zero-Bias**                  | La verdad está en los hechos, no en las opiniones.                                    |
| **Concentración Radical**      | 5000 → 5-10. La diversificación excesiva es para quienes no saben qué poseen.         |
| **Defensa Primero**            | El capital debe sobrevivir antes de crecer. Esperar ES una posición.                  |
| **Asimetría o Nada**           | Si no hay 5:1, no hay trade.                                                          |
| **Verdad Matemática**          | Nada llega a producción sin validación walk-forward.                                  |
| **Forensia Implacable**        | Detect → Learn → Retrain → Prevent. Los éxitos se cuestionan tanto como los fracasos. |
| **Reconocimiento de Patrones** | Todo se repite. Cada evento es "another one of those".                                |
| **Anti-Estupidez Sistemática** | Invertir siempre: ¿qué garantiza que fracasemos? Evitar eso primero.                  |
| **Pureza Arquitectónica**      | Clean Architecture Hexagonal. Las dependencias apuntan hacia adentro.                 |

---

## Architecture

> 📐 Full architecture diagrams: [`docs/architecture-diagram.md`](docs/architecture-diagram.md) (V14 — Graphify verified: 2821 nodes, 524 files)

### Dual-Mandate Architecture

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

### Clean Architecture — 12 Modules

```
backend/modules/
├── portfolio_management/    # Selection & qualification (QUALITY + SPECULATIVE)
├── entry_decision/          # Entry gates (QualityEntryGate + SpeculativeEntryHub)
├── execution/               # Orchestrators, surveillance, smart entry, journal
├── flow_intelligence/       # Whale flow, persistence, event calendar
├── options_gamma/           # GEX, max pain, gamma regime
├── price_analysis/          # Price phase detection, RSI intelligence
├── volume_intelligence/     # Kalman volume, volume profile
├── pattern_recognition/     # Candlestick, VCP detection
├── rotation_intelligence/   # Weinstein stages, Pring cycles
├── simulation/              # Walk-forward, triple barrier, LSTM, features
├── shared/                  # Cross-module entities, cache
└── (8 MCP Servers)          # ~241 tools — Alpaca, GuruFocus, Finviz, Finnhub, FRED, Yahoo, UW, News
```

## Project Structure

```
botero-trade/
├── src/                              # Next.js 16 + PayloadCMS 3 (TypeScript)
│   ├── app/
│   │   ├── (frontend)/              # Trading dashboard UI
│   │   └── (payload)/               # CMS admin panel
│   ├── shared/                      # Clean Architecture (TS)
│   │   ├── domain/                  # Domain types and rules
│   │   ├── application/             # UI use cases
│   │   ├── infrastructure/          # API clients, adapters
│   │   └── handlers/
│   ├── collections/                 # PayloadCMS collections (12)
│   ├── globals/                     # Header, Footer, SiteSettings
│   └── components/                  # Shared React components
│
├── backend/                         # Python trading engine
│   ├── modules/                     # 12 Clean Architecture modules
│   │   ├── */domain/                # entities/ · ports/ · rules/
│   │   ├── */application/           # use_cases/ · dtos/
│   │   └── */infrastructure/        # adapters (SDKs, PostgreSQL)
│   ├── api/
│   │   ├── main.py                  # FastAPI app + CORS
│   │   ├── factories/               # Composition Root (DI)
│   │   └── routers/                 # market_data · portfolio · strategy · orders · simulation
│   ├── requirements.txt
│   └── Dockerfile
│
├── docs/                            # Architecture diagrams (V14)
├── .agents/skills/                  # 17 AI agent skills
├── docker-compose.yml               # Orchestrates web + api
├── graphify-out/                    # Codebase knowledge graph
└── package.json                     # pnpm root
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

| Service            | URL                         |
| ------------------ | --------------------------- |
| Frontend + CMS     | http://localhost:3000       |
| PayloadCMS admin   | http://localhost:3000/admin |
| Trading Engine API | http://localhost:8000       |
| API docs (Swagger) | http://localhost:8000/docs  |

### 2b. Docker Compose (containerized)

```bash
docker compose up
```

Starts `web` (port 3000) and `api` (port 8000). The database is not managed by Docker — set `POSTGRES_URL` in `.env` to your external database.

---

## Database

PostgreSQL is hosted **externally** — not inside Docker — so your data is never tied to this project's containers and survives migrations, rebuilds, and deployments.

Recommended providers:

| Provider                                               | Free tier | Notes                                                  |
| ------------------------------------------------------ | --------- | ------------------------------------------------------ |
| [Vercel Postgres](https://vercel.com/storage/postgres) | Yes       | Best for Vercel deployments — zero config              |
| [Neon](https://neon.tech)                              | Yes       | Serverless, branching support                          |
| [Supabase](https://supabase.com)                       | Yes       | Includes auth, storage, realtime                       |
| Local instance                                         | —         | `postgres://postgres:<pw>@127.0.0.1:5432/botero_trade` |

Set the connection string in `.env`:

```
POSTGRES_URL=postgres://user:password@host:5432/database
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values:

| Variable                 | Description                               |
| ------------------------ | ----------------------------------------- |
| `POSTGRES_URL`           | External PostgreSQL connection string     |
| `PAYLOAD_SECRET`         | Secret key for JWT encryption             |
| `NEXT_PUBLIC_SERVER_URL` | Public URL of the frontend                |
| `TRADING_API_URL`        | URL of the Python trading engine          |
| `IB_HOST`                | IB TWS/Gateway host (default `127.0.0.1`) |
| `IB_PORT`                | IB TWS/Gateway port (default `7497`)      |
| `IB_CLIENT_ID`           | IB client ID (default `1`)                |
| `ALPACA_API_KEY`         | Alpaca API key                            |
| `ALPACA_SECRET_KEY`      | Alpaca secret key                         |
| `ALPACA_BASE_URL`        | Alpaca endpoint (default: paper trading)  |

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

| Command             | Description                                                      |
| ------------------- | ---------------------------------------------------------------- |
| `pnpm dev:all`      | Start frontend + Python API together (recommended for local dev) |
| `pnpm dev`          | Frontend only (Next.js dev server)                               |
| `pnpm dev:api`      | Python API only (uvicorn with hot reload)                        |
| `pnpm start`        | Start Next.js production server                                  |
| `pnpm build`        | Build Next.js for production                                     |
| `pnpm docker:up`    | Start web + api via Docker Compose                               |
| `pnpm docker:build` | Rebuild Docker images                                            |
| `pnpm docker:down`  | Stop all Docker services                                         |

---

## Tech Stack

| Layer                   | Technology                         |
| ----------------------- | ---------------------------------- |
| Frontend framework      | Next.js 16 (App Router)            |
| CMS                     | PayloadCMS 3                       |
| UI components           | HeroUI, Radix UI, Tailwind CSS     |
| Language (frontend)     | TypeScript                         |
| Trading engine          | Python 3.12 + FastAPI              |
| Architecture            | Modular Clean / Hexagonal (12 mod) |
| ML Pipeline             | PyTorch LSTM + GradientBoosting    |
| Data processing         | pandas, numpy, scikit-learn        |
| Market data             | 8 MCP Servers (~241 tools)         |
| Broker                  | Alpaca × 2 (QUALITY + SPECULATIVE) |
| Database                | PostgreSQL 16 + TimescaleDB        |
| Vector search           | pgvector (9D embeddings)           |
| Codebase graph          | Graphify (2821 nodes)              |
| Container orchestration | Docker Compose                     |
| Frontend deployment     | Vercel                             |
