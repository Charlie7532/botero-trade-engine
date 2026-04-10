# Botero Trade — Dev Environment

Print the following dev environment reference for this project and offer to run any of the commands.

---

## Start options

### Local development (no Docker)
Requires: Node ≥20, pnpm ≥9, Python 3.12, PostgreSQL running on port 5432

```bash
# Terminal 1 — Frontend + PayloadCMS
cp .env.example .env   # first time only — fill in credentials
pnpm install           # first time only
pnpm dev               # → http://localhost:3000
                       # → http://localhost:3000/admin (CMS)

# Terminal 2 — Python trading engine
cd backend
pip install -r requirements.txt   # first time only
uvicorn api.main:app --reload --port 8000
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)
```

### Docker Compose (everything in one command)
Requires: Docker + Docker Compose

```bash
cp .env.example .env   # first time only — fill in credentials
docker compose up      # starts web (3000) + api (8000) + postgres (5432)
```

| Service | URL |
|---|---|
| Frontend + CMS | http://localhost:3000 |
| PayloadCMS admin | http://localhost:3000/admin |
| Trading Engine API | http://localhost:8000 |
| Swagger docs | http://localhost:8000/docs |

---

## Common tasks

```bash
# Regenerate PayloadCMS types after schema changes
pnpm generate

# Create a DB migration after changing Payload collections
pnpm payload migrate:create
pnpm payload migrate

# Rebuild Docker images after changing dependencies
pnpm docker:build

# Check Python API health
curl http://localhost:8000/health

# List available trading strategies
curl http://localhost:8000/api/strategy/list

# Fetch market data (requires broker credentials in .env)
curl "http://localhost:8000/api/market-data/AAPL/price?broker=alpaca"
```

---

## Interactive Brokers note

IB TWS or IB Gateway must run **on your local machine** — it cannot run inside Docker.
Set in `.env`:
```
IB_HOST=127.0.0.1   # or host.docker.internal when using Docker
IB_PORT=7497        # TWS paper: 7497 | TWS live: 7496 | Gateway paper: 4002 | Gateway live: 4001
IB_CLIENT_ID=1
```

---

## Environment variables checklist

Copy `.env.example` to `.env` and fill in:

- [ ] `POSTGRES_URL` — connection string for PayloadCMS
- [ ] `PAYLOAD_SECRET` — any long random string
- [ ] `NEXT_PUBLIC_SERVER_URL` — `http://localhost:3000` for local dev
- [ ] `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` — from alpaca.markets (free paper account)
- [ ] `IB_*` — only needed if connecting to Interactive Brokers
- [ ] `POSTGRES_PASSWORD` — only needed for Docker Compose postgres service

---

## Related skills

- `/add-strategy` — add a new Backtrader trading strategy
- `/add-broker` — add a new broker integration
- `/context` — full project architecture reference
