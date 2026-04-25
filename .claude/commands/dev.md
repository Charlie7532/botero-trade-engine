# Start Botero Trade — Development Mode

Bring up the full development environment with hot reload.

## Step 1 — Verify prerequisites

Run these checks and report what is missing:

```bash
node --version        # must be >=20.9.0
pnpm --version        # must be >=9
python3 --version     # must be 3.12+
```

If Node.js is missing: `curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y nodejs`
If pnpm is missing: `npm install -g pnpm`

## Step 2 — Check environment file

```bash
ls .env 2>/dev/null || echo "MISSING"
```

If `.env` does not exist:
```bash
cp .env.example .env
```
Tell the user: "`.env` was created from `.env.example`. Fill in `POSTGRES_URL` and `PAYLOAD_SECRET` for the frontend. The Python engine can start without them."

## Step 3 — Install dependencies

```bash
pnpm install
```

If build script warnings appear:
```bash
pnpm approve-builds
pnpm install
```

## Step 4 — Set up Python virtual environment

```bash
ls backend/.venv 2>/dev/null || echo "MISSING"
```

If missing:
```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install --upgrade pip -q && .venv/bin/pip install -r requirements.txt
```

## Step 5 — Start all dev services

```bash
pnpm dev:all
```

This starts with hot reload:
- **[web]** Next.js + PayloadCMS → http://localhost:3000 (admin at /admin)
- **[api]** Python FastAPI + Backtrader → http://localhost:8000 (docs at /docs)

## Step 6 — Verify services

```bash
curl -s http://localhost:8000/health
```
Expected: `{"status":"ok","service":"botero-trade-engine"}`

## Troubleshooting

| Problem | Fix |
|---|---|
| `POSTGRES_URL` error on web | Fill in `.env` with a valid Postgres connection string |
| Port 3000 in use | `lsof -ti:3000 \| xargs kill` |
| Port 8000 in use | `lsof -ti:8000 \| xargs kill` |
| Python import errors | `cd backend && .venv/bin/pip install -r requirements.txt` |
| pnpm install fails | `pnpm reinstall` |
| IB connection refused | TWS/IB Gateway must run locally — not needed for Alpaca-only |

## Common dev tasks

```bash
pnpm generate                   # Regenerate Payload types
pnpm payload migrate:create     # Create DB migration
pnpm payload migrate            # Run pending migrations
curl http://localhost:8000/api/strategy/list   # List strategies
```

## Interactive Brokers note

IB TWS or Gateway must run **on your local machine** — it cannot run inside Docker.
```
IB_HOST=127.0.0.1
IB_PORT=7497        # TWS paper: 7497 | TWS live: 7496 | Gateway paper: 4002 | Gateway live: 4001
IB_CLIENT_ID=1
```
