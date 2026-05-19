"""
ingest_historical_csvs.py — Ingest TradingView CSV exports into Neon Vault
===========================================================================
Reads CSV files from backend/data/imports/, converts Unix timestamps to 
datetime, and upserts into market.ohlcv_bars via TimescaleDataStore.

ONLY backfills bars OLDER than what already exists in the Vault.
Does NOT overwrite existing data (Vault-first integrity).

After successful ingest, deletes the CSV files.
"""
import sys
import os
import glob
import re
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

_root = Path("/root/botero-trade")
sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(_root / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore


# Map filename to ticker symbol
FILENAME_TO_TICKER = {
    "NASDAQ_AAPL": "AAPL",
    "NASDAQ_AMZN": "AMZN",
    "NASDAQ_COST": "COST",
    "NASDAQ_HON": "HON",
    "NASDAQ_MSFT": "MSFT",
    "NASDAQ_PEP": "PEP",
    "NASDAQ_WMT": "WMT",
    "NYSE_HD": "HD",
    "NYSE_IBM": "IBM",
    "NYSE_JNJ": "JNJ",
    "NYSE_JPM": "JPM",
    "NYSE_MCD": "MCD",
    "NYSE_MRK": "MRK",
    "NYSE_PG": "PG",
    "NYSE_XOM": "XOM",
}


def parse_csv(filepath: str) -> pd.DataFrame:
    """Parse a TradingView CSV export.
    
    Format: time (unix epoch seconds), open, high, low, close, Volume
    """
    df = pd.read_csv(filepath)
    
    # Normalize column names
    df.columns = [c.strip().lower() for c in df.columns]
    
    # Convert unix timestamp to datetime
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    
    # Ensure numeric
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    
    df = df.dropna(subset=["open", "high", "low", "close"])
    
    return df[["timestamp", "open", "high", "low", "close", "volume"]]


def main():
    import_dir = _root / "backend" / "data" / "imports"
    csv_files = sorted(glob.glob(str(import_dir / "*.csv")))
    
    if not csv_files:
        print("No CSV files found in backend/data/imports/")
        return
    
    print("=" * 100)
    print(f"{'HISTORICAL CSV INGEST → NEON VAULT':^100}")
    print(f"{'Backfill only (does not overwrite existing data)':^100}")
    print("=" * 100)
    
    store = TimescaleDataStore()
    
    total_inserted = 0
    total_skipped = 0
    files_processed = []
    
    for csv_path in csv_files:
        filename = Path(csv_path).stem  # e.g., "NASDAQ_AAPL, 1D"
        
        # Extract exchange_ticker part
        ticker_key = filename.split(",")[0].strip()
        ticker = FILENAME_TO_TICKER.get(ticker_key)
        
        if ticker is None:
            print(f"  ⚠️  Unknown ticker mapping for: {filename}")
            continue
        
        print(f"\n  Processing {ticker} ({filename})...")
        
        # Parse CSV
        df = parse_csv(csv_path)
        print(f"    CSV: {len(df):,} bars, {df['timestamp'].iloc[0].strftime('%Y-%m-%d')} → {df['timestamp'].iloc[-1].strftime('%Y-%m-%d')}")
        
        # Check existing data in Vault
        existing = store.load_bars(ticker, "1d")
        if existing is not None and not existing.empty:
            existing_start = existing.index[0]
            existing_end = existing.index[-1]
            print(f"    Vault: {len(existing):,} bars, {existing_start.strftime('%Y-%m-%d')} → {existing_end.strftime('%Y-%m-%d')}")
            
            # Only backfill bars BEFORE existing data
            cutoff = existing_start
            backfill = df[df["timestamp"] < cutoff]
            print(f"    Backfill: {len(backfill):,} bars before {cutoff.strftime('%Y-%m-%d')}")
        else:
            backfill = df
            print(f"    Vault: EMPTY — inserting all {len(backfill):,} bars")
        
        if backfill.empty:
            print(f"    ✅ No backfill needed (Vault already has full history)")
            total_skipped += len(df)
            files_processed.append(csv_path)
            continue
        
        # Insert into Vault
        inserted = 0
        errors = 0
        for _, row in backfill.iterrows():
            try:
                store.upsert_ohlcv_bar(
                    ticker=ticker,
                    timeframe="1d",
                    time=row["timestamp"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]) if pd.notna(row["volume"]) else 0,
                )
                inserted += 1
            except Exception as e:
                errors += 1
                if errors <= 3:
                    print(f"    ⚠️  Error at {row['timestamp']}: {e}")
        
        total_inserted += inserted
        print(f"    ✅ Inserted {inserted:,} bars ({errors} errors)")
        files_processed.append(csv_path)
    
    # Verify final state
    print(f"\n{'=' * 100}")
    print(f"{'VERIFICATION — POST-INGEST':^100}")
    print(f"{'=' * 100}")
    
    for csv_path in files_processed:
        filename = Path(csv_path).stem
        ticker_key = filename.split(",")[0].strip()
        ticker = FILENAME_TO_TICKER.get(ticker_key)
        if ticker is None:
            continue
        
        bars = store.load_bars(ticker, "1d")
        if bars is not None and not bars.empty:
            years = (bars.index[-1] - bars.index[0]).days / 365.25
            print(f"    {ticker:<6}: {len(bars):>6,} bars | {bars.index[0].strftime('%Y-%m-%d')} → {bars.index[-1].strftime('%Y-%m-%d')} | {years:.1f} years")
    
    store.close()
    
    # Summary
    print(f"\n  Total inserted: {total_inserted:,} bars")
    print(f"  Total skipped: {total_skipped:,} bars (already in Vault)")
    
    # Delete CSV files after successful ingest
    if total_inserted > 0 or total_skipped > 0:
        print(f"\n  Cleaning up CSV files...")
        for csv_path in files_processed:
            os.remove(csv_path)
            print(f"    🗑️  Deleted: {Path(csv_path).name}")
        print(f"  ✅ All {len(files_processed)} CSV files deleted")
    

if __name__ == "__main__":
    main()
