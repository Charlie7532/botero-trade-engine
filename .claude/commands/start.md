# Start Botero Trade Dev Environment

Run the following steps in order to bring up the full Botero Trade development environment.

## Step 1 — Verify prerequisites

Run these checks and report what is missing before proceeding:

```bash
node --version        # must be >=20.9.0
pnpm --version        # must be >=9
python3 --version     # must be 3.12+
docker --version
docker compose version
```

If Node.js is missing: install via NodeSource (`curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y nodejs`)
If pnpm is missing: `npm install -g pnpm`
If docker compose is missing: `apt-get install -y docker-compose-v2`

## Step 2 — Check environment file

```bash
ls .env 2>/dev/null || echo "MISSING"
```

If `.env` does not exist, copy the example and alert the user:
```bash
cp .env.example .env
```
Then tell the user: "`.env` was created from `.env.example`. You must fill in `POSTGRES_URL` and `PAYLOAD_SECRET` before the frontend will work. The Python trading engine can start without them."

## Step 3 — Install frontend dependencies

```bash
pnpm install
```

If there are build script warnings, run:
```bash
pnpm approve-builds
pnpm install
```

## Step 4 — Set up Python virtual environment

Check if venv exists:
```bash
ls backend/.venv 2>/dev/null || echo "MISSING"
```

If missing, create it and install:
```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install --upgrade pip -q && .venv/bin/pip install -r requirements.txt
```

## Step 5 — Start all services

```bash
pnpm dev:all
```

This starts:
- **[web]** Next.js + PayloadCMS → http://localhost:3000 (admin at /admin)
- **[api]** Python FastAPI + Backtrader → http://localhost:8000 (docs at /docs)

## Step 6 — Verify services are up

After starting, confirm both services respond:
```bash
curl -s http://localhost:8000/health
```
Expected: `{"status":"ok","service":"botero-trade-engine"}`

## Troubleshooting

| Problem | Fix |
|---|---|
| `POSTGRES_URL` error on web | Fill in `.env` with a valid external Postgres connection string |
| Port 3000 already in use | `lsof -ti:3000 \| xargs kill` |
| Port 8000 already in use | `lsof -ti:8000 \| xargs kill` |
| Python import errors | `cd backend && .venv/bin/pip install -r requirements.txt` |
| pnpm install fails | `pnpm reinstall` |
| IB connection refused | TWS or IB Gateway must run locally — not needed for Alpaca-only usage |

## Quick reference

```
http://localhost:3000        → Trading dashboard + CMS frontend
http://localhost:3000/admin  → PayloadCMS admin panel
http://localhost:8000        → Python trading engine
http://localhost:8000/docs   → FastAPI Swagger UI (interactive API docs)
```
