import os

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()  # reads ../.env (or any .env found walking up from cwd)
from fastapi.middleware.cors import CORSMiddleware

from api.routers import market_data, orders, portfolio, strategy

app = FastAPI(
    title="Botero Trade Engine",
    description="Python trading engine API — connects to Interactive Brokers and Alpaca.",
    version="0.1.0",
)

# Allow requests from the Next.js frontend (local dev + Vercel)
allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
vercel_url = os.getenv("VERCEL_URL")
if vercel_url:
    allowed_origins.append(f"https://{vercel_url}")

frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    allowed_origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market_data.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(portfolio.router, prefix="/api")
app.include_router(strategy.router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "botero-trade-engine"}
