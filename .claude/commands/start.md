# Start Botero Trade — Production Mode

Launch all Botero Trade services in production mode.

## Prerequisites

Before starting production, ensure:
- `.env` is configured with real credentials (never edit it directly — ask the user)
- Dependencies are installed (`pnpm install` + `backend/.venv`)

## Start Production via Docker Compose

```bash
pnpm docker:build
docker compose up -d
```

This starts:
- **[web]** Next.js + PayloadCMS → http://localhost:3000 (production build)
- **[api]** Python FastAPI → http://localhost:8000 (uvicorn production)
- **[db]** PostgreSQL 16 → port 5432

## Start Production Locally (no Docker)

### Frontend (production build)
```bash
pnpm build
pnpm start
```
→ http://localhost:3000

### Python trading engine (production)
```bash
cd backend && .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
```
→ http://localhost:8000

## Health Check

```bash
curl -s http://localhost:8000/health
# Expected: {"status":"ok","service":"botero-trade-engine"}

curl -s http://localhost:3000
# Expected: 200 OK
```

## Service URLs

| Service | URL |
|---|---|
| Trading Dashboard | http://localhost:3000 |
| PayloadCMS Admin | http://localhost:3000/admin |
| Trading Engine API | http://localhost:8000 |
| Swagger Docs | http://localhost:8000/docs |
