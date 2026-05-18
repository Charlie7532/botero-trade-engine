"""
Import CSV OHLCV data into Neon Vault (market.ohlcv_bars).
Handles TradingView-style CSVs with Unix epoch timestamps.

Usage:
    PYTHONPATH=. python backend/scripts/import_csv_ohlcv.py
"""
import logging
import pandas as pd
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

IMPORT_DIR = Path(__file__).parent.parent / "data" / "imports"

# Map CSV filenames → (ticker, asset_type, sector)
FILE_MAP = {
    "AMEX_SPY, 1D (2).csv":    ("SPY",  "ETF", "Broad Market"),
    "NASDAQ_QQQ, 1D (1).csv":  ("QQQ",  "ETF", "Technology"),
}


def import_csv(filepath: Path, ticker: str, asset_type: str, sector: str):
    """Read a TradingView CSV and upsert into Vault."""
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

    logger.info(f"Reading {filepath.name} → {ticker}")
    raw = pd.read_csv(filepath)

    # Convert Unix epoch to datetime index
    raw["time"] = pd.to_datetime(raw["time"], unit="s")
    raw = raw.set_index("time")

    # Normalize column names to lowercase
    raw.columns = [c.lower() for c in raw.columns]

    # Ensure required columns
    for col in ["open", "high", "low", "close"]:
        if col not in raw.columns:
            raise ValueError(f"Missing column: {col}")

    if "volume" not in raw.columns:
        raw["volume"] = 0

    raw["volume"] = raw["volume"].fillna(0).astype(int)

    logger.info(f"  {ticker}: {len(raw)} bars ({raw.index[0].date()} → {raw.index[-1].date()})")
    logger.info(f"  Volume range: {raw['volume'].min():,.0f} → {raw['volume'].max():,.0f}")

    # Save to Vault
    store = TimescaleDataStore()
    store.save_bars(ticker, "1d", raw)

    # Update ticker metadata
    try:
        store.upsert_ticker_metadata(
            ticker=ticker,
            sector=sector,
            industry=asset_type,
            market_cap_bucket="MEGA",
        )
        logger.info(f"  Metadata: {ticker} → {asset_type}/{sector}")
    except Exception as e:
        logger.warning(f"  Metadata upsert skipped: {e}")

    # Verify
    count_result = store._execute_query(
        "SELECT COUNT(*) FROM market.ohlcv_bars WHERE ticker = %s AND timeframe = '1d'",
        (ticker,)
    ) if hasattr(store, '_execute_query') else None

    store.close()
    logger.info(f"  ✅ {ticker} imported successfully")


def main():
    logger.info("═══ CSV OHLCV Import to Neon Vault ═══\n")

    imported = []
    for filename, (ticker, asset_type, sector) in FILE_MAP.items():
        filepath = IMPORT_DIR / filename
        if not filepath.exists():
            logger.warning(f"  ⚠️ {filename} not found, skipping")
            continue
        import_csv(filepath, ticker, asset_type, sector)
        imported.append(filepath)
        print()

    # Cleanup imported CSVs
    for fp in imported:
        fp.unlink()
        logger.info(f"  🗑️ Deleted {fp.name}")

    logger.info("═══ Import Complete ═══")


if __name__ == "__main__":
    main()
