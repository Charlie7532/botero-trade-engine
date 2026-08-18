"""
Backfill Max History — Extend ALL stocks + ETFs to max yfinance range
======================================================================
Downloads period="max" for every STOCK and ETF in ticker_metadata.
Safe to re-run: uses ON CONFLICT DO NOTHING (append-only).

Usage:
    python -m backend.scripts.backfill_max_history
    python -m backend.scripts.backfill_max_history --type ETF
    python -m backend.scripts.backfill_max_history --type STOCK
    python -m backend.scripts.backfill_max_history --tickers AAPL,MSFT,SPY
    python -m backend.scripts.backfill_max_history --dry-run
"""
import argparse
import logging
import os
import sys
import time
from datetime import datetime, UTC
from pathlib import Path

import pandas as pd

_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(_root / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ETFs that use Yahoo-style tickers (prefix ^ or different symbol)
YF_TICKER_MAP = {
    # Indices stored with custom names in the Vault
    "SPX": "^GSPC",
    "NDQ": "^IXIC",
    "DXY": "DX-Y.NYB",
    "TNX": "^TNX",
    "SKEW": "^SKEW",
    "TRIN": "^TRIN",
}


def get_yf_ticker(vault_ticker: str) -> str:
    """Map vault ticker name to yfinance downloadable symbol."""
    return YF_TICKER_MAP.get(vault_ticker, vault_ticker)


def harmonize(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Normalize yfinance DataFrame to Vault schema."""
    if df.empty:
        return df

    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs(ticker, level=1, axis=1)

    df.columns = [c.lower() for c in df.columns]
    required = ["open", "high", "low", "close", "volume"]
    available = [c for c in required if c in df.columns]
    df = df[available].copy()

    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC")
    else:
        df.index = df.index.tz_localize("UTC")
    df.index.name = "timestamp"

    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            df[col] = df[col].astype("float64")
    if "volume" in df.columns:
        df["volume"] = df["volume"].fillna(0).astype("int64")

    df.dropna(subset=["open", "high", "low", "close"], inplace=True)
    return df


def get_eligible_tickers(store: TimescaleDataStore, asset_type: str | None = None) -> list[dict]:
    """Get tickers that need backfilling, with their current bar count."""
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            type_filter = ""
            params = ()
            if asset_type:
                type_filter = "AND m.industry = %s"
                params = (asset_type,)

            cur.execute(f"""
                SELECT m.ticker, m.industry, m.sector,
                       COALESCE(stats.bars, 0) as bars,
                       stats.first_date, stats.last_date
                FROM market.ticker_metadata m
                LEFT JOIN (
                    SELECT ticker, COUNT(*) as bars,
                           MIN(time)::date as first_date,
                           MAX(time)::date as last_date
                    FROM market.ohlcv_bars
                    WHERE timeframe = '1d'
                    GROUP BY ticker
                ) stats ON stats.ticker = m.ticker
                WHERE m.industry IS NOT NULL
                  AND m.industry NOT IN ('INDICATOR')
                  {type_filter}
                ORDER BY COALESCE(stats.bars, 0) ASC, m.ticker
            """, params)

            return [
                {
                    "ticker": r[0],
                    "industry": r[1],
                    "sector": r[2],
                    "bars": r[3],
                    "first_date": r[4],
                    "last_date": r[5],
                }
                for r in cur.fetchall()
            ]
    finally:
        store._put(conn)


def backfill_ticker(ticker_info: dict, store: TimescaleDataStore) -> dict:
    """Download max history for a single ticker and save to Vault."""
    import yfinance as yf

    vault_ticker = ticker_info["ticker"]
    yf_ticker = get_yf_ticker(vault_ticker)
    current_bars = ticker_info["bars"]
    first_date = ticker_info["first_date"]

    result = {
        "ticker": vault_ticker,
        "yf_ticker": yf_ticker,
        "before_bars": current_bars,
        "new_bars": 0,
        "total_bars": current_bars,
        "status": "skipped",
        "range": "",
    }

    try:
        df = yf.download(
            yf_ticker, period="max", interval="1d",
            progress=False, auto_adjust=True,
        )

        if df.empty:
            result["status"] = "no_data"
            return result

        df = harmonize(df, yf_ticker)

        if df.empty:
            result["status"] = "no_valid_data"
            return result

        # If we already have data, only insert bars BEFORE our earliest date
        # (save_bars uses ON CONFLICT DO NOTHING, so duplicates are safe)
        pre_existing = len(df)

        if first_date and current_bars > 0:
            # Filter to only bars we DON'T have (before first_date)
            first_date_ts = pd.Timestamp(first_date, tz="UTC")
            new_bars_df = df[df.index < first_date_ts]
            if new_bars_df.empty:
                result["status"] = "already_maxed"
                result["range"] = f"{df.index.min().date()} → {df.index.max().date()}"
                return result
            # Save only the historical backfill portion
            store.save_bars(vault_ticker, "1d", new_bars_df)
            result["new_bars"] = len(new_bars_df)
        else:
            # No existing data — save everything
            store.save_bars(vault_ticker, "1d", df)
            result["new_bars"] = len(df)

        result["total_bars"] = current_bars + result["new_bars"]
        result["status"] = "ok"
        result["range"] = f"{df.index.min().date()} → {df.index.max().date()}"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:100]

    return result


def main():
    parser = argparse.ArgumentParser(description="Backfill max history for all stocks + ETFs")
    parser.add_argument("--type", choices=["ETF", "STOCK", "ALL"], default="ALL",
                        help="Filter by asset type (default: ALL)")
    parser.add_argument("--tickers", help="Comma-separated tickers (overrides --type)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--batch-delay", type=float, default=1.0,
                        help="Seconds between batches (rate limiting)")
    parser.add_argument("--batch-size", type=int, default=10,
                        help="Tickers per batch")
    args = parser.parse_args()

    store = TimescaleDataStore()

    if args.tickers:
        # Manual ticker list
        explicit = [t.strip().upper() for t in args.tickers.split(",")]
        all_tickers = get_eligible_tickers(store)
        tickers = [t for t in all_tickers if t["ticker"] in explicit]
        # Add any tickers not in metadata
        known = {t["ticker"] for t in tickers}
        for t in explicit:
            if t not in known:
                tickers.append({
                    "ticker": t, "industry": "?", "sector": "?",
                    "bars": 0, "first_date": None, "last_date": None,
                })
    else:
        asset_type = None if args.type == "ALL" else args.type
        tickers = get_eligible_tickers(store, asset_type)

    logger.info(f"{'='*70}")
    logger.info(f"Backfill Max History — {len(tickers)} tickers ({args.type})")
    logger.info(f"{'='*70}")

    if args.dry_run:
        print(f"\n{'Ticker':<8} {'Type':<6} {'Current':>8} {'First Date':>12}")
        print("-" * 40)
        for t in tickers:
            print(f"{t['ticker']:<8} {str(t['industry'])[:6]:<6} {t['bars']:>8} {str(t['first_date'] or 'NONE'):>12}")
        print(f"\nTotal: {len(tickers)} tickers would be backfilled")
        return

    results = {"ok": 0, "already_maxed": 0, "error": 0, "no_data": 0}
    total_new = 0

    for i in range(0, len(tickers), args.batch_size):
        batch = tickers[i:i + args.batch_size]
        batch_num = i // args.batch_size + 1
        total_batches = (len(tickers) + args.batch_size - 1) // args.batch_size

        logger.info(f"\n--- Batch {batch_num}/{total_batches} ---")

        for t in batch:
            r = backfill_ticker(t, store)
            results[r["status"]] = results.get(r["status"], 0) + 1
            total_new += r["new_bars"]

            icon = {"ok": "✅", "already_maxed": "⏩", "error": "❌", "no_data": "⚠️"}.get(r["status"], "?")
            if r["status"] == "ok":
                logger.info(
                    f"  {icon} {r['ticker']:<8} +{r['new_bars']:>5} bars "
                    f"({r['before_bars']:>5} → {r['total_bars']:>5}) "
                    f"range: {r['range']}"
                )
            elif r["status"] == "already_maxed":
                logger.info(f"  {icon} {r['ticker']:<8} already maxed ({r['range']})")
            elif r["status"] == "error":
                logger.warning(f"  {icon} {r['ticker']:<8} ERROR: {r.get('error', '?')}")
            else:
                logger.info(f"  {icon} {r['ticker']:<8} {r['status']}")

        # Rate limiting between batches
        if i + args.batch_size < len(tickers):
            time.sleep(args.batch_delay)

    logger.info(f"\n{'='*70}")
    logger.info(f"BACKFILL COMPLETE")
    logger.info(f"  ✅ Updated:       {results.get('ok', 0)}")
    logger.info(f"  ⏩ Already maxed:  {results.get('already_maxed', 0)}")
    logger.info(f"  ❌ Errors:         {results.get('error', 0)}")
    logger.info(f"  ⚠️  No data:       {results.get('no_data', 0)}")
    logger.info(f"  📊 New bars added: {total_new:,}")
    logger.info(f"{'='*70}")


if __name__ == "__main__":
    main()
