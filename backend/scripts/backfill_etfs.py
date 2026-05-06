"""
Backfill Missing ETFs into Neon OHLCV — Run Once
==================================================
Adds RSP, TLT, HYG, IEF, IWM, DIA, VGK, EFA to market.ohlcv_bars
with 5 years of daily data from yfinance.

Usage:
    cd /root/botero-trade
    PYTHONPATH=. backend/.venv/bin/python backend/scripts/backfill_etfs.py
"""
import logging
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

BACKFILL_TICKERS = ["RSP", "TLT", "HYG", "IEF", "IWM", "DIA", "VGK", "EFA"]


def main():
    import yfinance as yf
    import pandas as pd
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")

    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

    store = TimescaleDataStore()
    stats = {"added": 0, "skipped": 0, "failed": 0}

    for ticker in BACKFILL_TICKERS:
        try:
            # Check if already exists
            last = store.bars_last_date(ticker, "1d")
            if last:
                logger.info(f"  {ticker}: already in OHLCV (last={last}) — skipping")
                stats["skipped"] += 1
                continue

            logger.info(f"  {ticker}: downloading 5y daily from yfinance...")
            df = yf.download(ticker, period="5y", interval="1d",
                             progress=False, auto_adjust=True)

            if df.empty:
                logger.warning(f"  {ticker}: no data returned — skipping")
                stats["failed"] += 1
                continue

            # Harmonize columns
            if isinstance(df.columns, pd.MultiIndex):
                df = df.xs(ticker, level=1, axis=1)
            df.columns = [c.lower() for c in df.columns]
            required = ["open", "high", "low", "close", "volume"]
            available = [c for c in required if c in df.columns]
            df = df[available].copy()

            # Timezone
            if df.index.tz is not None:
                df.index = df.index.tz_convert("UTC")
            else:
                df.index = df.index.tz_localize("UTC")
            df.index.name = "timestamp"
            df.dropna(subset=["open", "high", "low", "close"], inplace=True)

            if df.empty:
                logger.warning(f"  {ticker}: all rows NaN after cleanup — skipping")
                stats["failed"] += 1
                continue

            store.save_bars(ticker, "1d", df)
            logger.info(f"  ✅ {ticker}: {len(df)} bars saved ({df.index.min().date()} → {df.index.max().date()})")
            stats["added"] += 1

        except Exception as e:
            logger.error(f"  ❌ {ticker}: {e}")
            stats["failed"] += 1

    store.close()
    logger.info(f"Backfill complete: {stats}")


if __name__ == "__main__":
    main()
