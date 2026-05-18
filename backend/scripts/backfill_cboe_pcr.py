"""
BACKFILL CBOE PUT/CALL RATIO — EODHD API → Neon Vault
========================================================
Fetches the full CBOE Equity Put/Call Ratio (CPCE) historical series
from EODHD and persists it as OHLCV bars in market.ohlcv_bars.

BUDGET: Uses exactly 1 API call to EODHD (free tier = 20/day).
        The /api/eod/{ticker} endpoint returns full history in one shot.

EODHD ticker format:
  - CPC.INDX   → CBOE Total Put/Call Ratio (equity + index options)
  - CPCE.INDX  → CBOE Equity-Only Put/Call Ratio (more predictive)

We fetch BOTH in 2 API calls total. The data is stored as:
  - ticker='CBOE_PCR'   timeframe='1d'  (Total)
  - ticker='CBOE_CPCE'  timeframe='1d'  (Equity-Only)

Usage:
    python -m backend.scripts.backfill_cboe_pcr
    python -m backend.scripts.backfill_cboe_pcr --dry-run
    python -m backend.scripts.backfill_cboe_pcr --ticker CPC.INDX
"""
import argparse
import logging
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

EODHD_BASE = "https://eodhd.com/api"

# Map EODHD tickers to our Vault naming convention
TICKER_MAP = {
    "CPC.INDX": "CBOE_PCR",     # Total Put/Call Ratio
    "CPCE.INDX": "CBOE_CPCE",   # Equity-Only Put/Call Ratio
}


def fetch_eod_history(eodhd_ticker: str, api_key: str) -> list[dict]:
    """
    Fetch full EOD history from EODHD in ONE API call.
    Returns list of {date, open, high, low, close, adjusted_close, volume}.
    """
    url = f"{EODHD_BASE}/eod/{eodhd_ticker}"
    params = {
        "api_token": api_key,
        "fmt": "json",
        "period": "d",
        "order": "a",  # ascending (oldest first)
        "from": "2003-01-01",  # CBOE PCR data starts ~2003
    }

    logger.info(f"📡 Fetching {eodhd_ticker} from EODHD (1 API call)...")
    resp = requests.get(url, params=params, timeout=30)

    if resp.status_code == 402:
        logger.error(
            "❌ EODHD returned 402 — API call limit reached or plan restriction. "
            "Free plan allows 20 calls/day. Try again tomorrow."
        )
        return []

    if resp.status_code != 200:
        logger.error(f"❌ EODHD error {resp.status_code}: {resp.text[:300]}")
        return []

    data = resp.json()
    if isinstance(data, dict) and "error" in data:
        logger.error(f"❌ EODHD API error: {data}")
        return []

    if not isinstance(data, list):
        logger.error(f"❌ Unexpected response type: {type(data)}")
        return []

    logger.info(f"✅ Received {len(data)} bars for {eodhd_ticker}")
    if data:
        logger.info(f"   Date range: {data[0].get('date')} → {data[-1].get('date')}")

    return data


def persist_to_vault(bars: list[dict], vault_ticker: str, dry_run: bool = False):
    """
    Persist EODHD bars into Neon PostgreSQL as OHLCV bars.

    The PCR is stored as a synthetic OHLCV bar where:
      - open/high/low/close = the PCR ratio value
      - volume = 0 (not applicable for a ratio)
    """
    if not bars:
        logger.warning(f"⚠️  No bars to persist for {vault_ticker}")
        return

    if dry_run:
        logger.info(f"🔍 DRY RUN: Would persist {len(bars)} bars as {vault_ticker}/1d")
        for bar in bars[:3]:
            logger.info(f"   Sample: {bar['date']} close={bar.get('close', '?')}")
        logger.info(f"   ... and {len(bars) - 3} more")
        return

    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    import pandas as pd

    store = TimescaleDataStore()

    # Check existing data to avoid re-inserting
    existing_last = store.bars_last_date(vault_ticker, "1d")
    if existing_last:
        logger.info(f"📊 Existing data for {vault_ticker}: last bar = {existing_last}")
        # Filter to only new bars
        cutoff = str(existing_last)
        bars = [b for b in bars if b.get("date", "") > cutoff]
        if not bars:
            logger.info(f"✅ {vault_ticker} already up to date — nothing to insert")
            store.close()
            return
        logger.info(f"📊 Inserting {len(bars)} NEW bars after {cutoff}")

    # Build DataFrame in the format save_bars expects
    rows = []
    for bar in bars:
        try:
            close = float(bar.get("close", 0) or 0)
            adj_close = float(bar.get("adjusted_close", close) or close)
            rows.append({
                "date": bar["date"],
                "open": float(bar.get("open", close) or close),
                "high": float(bar.get("high", close) or close),
                "low": float(bar.get("low", close) or close),
                "close": adj_close,  # Use adjusted_close for consistency
                "volume": int(float(bar.get("volume", 0) or 0)),
            })
        except (ValueError, TypeError) as e:
            logger.warning(f"Skipping malformed bar: {bar} — {e}")
            continue

    if not rows:
        logger.warning(f"⚠️  No valid rows after parsing for {vault_ticker}")
        store.close()
        return

    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["date"])
    df = df.drop(columns=["date"])
    df.index.name = "time"

    store.save_bars(vault_ticker, "1d", df)
    store.close()

    logger.info(
        f"✅ Persisted {len(df)} bars → {vault_ticker}/1d "
        f"({df.index.min().date()} → {df.index.max().date()})"
    )


def main():
    parser = argparse.ArgumentParser(description="Backfill CBOE Put/Call Ratio from EODHD")
    parser.add_argument(
        "--ticker", type=str, default=None,
        help="Specific EODHD ticker to fetch (e.g. CPC.INDX). Default: fetch both CPC and CPCE."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch data but don't persist to database"
    )
    args = parser.parse_args()

    api_key = os.getenv("EODHD_API_KEY", "")
    if not api_key or api_key == "your-eodhd-api-key":
        logger.error("❌ EODHD_API_KEY not configured in .env")
        sys.exit(1)

    # Determine which tickers to fetch
    if args.ticker:
        tickers = {args.ticker: TICKER_MAP.get(args.ticker, args.ticker.replace(".", "_"))}
    else:
        tickers = TICKER_MAP

    print("=" * 70)
    print("CBOE PUT/CALL RATIO BACKFILL — EODHD → Neon Vault")
    print(f"API calls budget: {len(tickers)} of 20/day")
    print("=" * 70)

    total_bars = 0
    for eodhd_ticker, vault_ticker in tickers.items():
        print(f"\n{'─' * 50}")
        print(f"  {eodhd_ticker} → {vault_ticker}/1d")
        print(f"{'─' * 50}")

        bars = fetch_eod_history(eodhd_ticker, api_key)
        if bars:
            total_bars += len(bars)
            persist_to_vault(bars, vault_ticker, dry_run=args.dry_run)

    print(f"\n{'=' * 70}")
    print(f"DONE — {total_bars} total bars fetched, {len(tickers)} API calls used")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
