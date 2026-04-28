"""
Download Historical — OHLCV + Macro Vault Builder
=====================================================
CLI script to populate the vault with historical OHLCV and macro data.

Usage:
    python -m backend.scripts.download_historical \\
        --tickers SPY,QQQ,AAPL,NVDA \\
        --tf 1d,1h \\
        --years 5 \\
        --include-macro

Harmonization Rules Applied:
- R1: All timestamps converted to UTC
- R2: Columns normalized to lowercase (open, high, low, close, volume)
- R6: 4h resampled from 1h, 1W from 1d
- R7: Append-only with deduplication
"""
import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.modules.simulation.infrastructure.parquet_data_store import ParquetDataStore

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def harmonize_yfinance(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Apply harmonization rules R1 + R2 to yfinance DataFrame."""
    if df.empty:
        return df

    # Flatten MultiIndex if present (yfinance multi-ticker download)
    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs(ticker, level=1, axis=1)

    # R2: lowercase columns
    df.columns = [c.lower() for c in df.columns]

    # Keep only OHLCV
    required = ["open", "high", "low", "close", "volume"]
    available = [c for c in required if c in df.columns]
    df = df[available].copy()

    # R1: convert to UTC
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC")
    else:
        df.index = df.index.tz_localize("UTC")

    df.index.name = "timestamp"

    # Dtypes
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            df[col] = df[col].astype("float64")
    if "volume" in df.columns:
        df["volume"] = df["volume"].fillna(0).astype("int64")

    # Drop rows with NaN OHLC
    df.dropna(subset=["open", "high", "low", "close"], inplace=True)

    return df


def download_ticker(ticker: str, tf: str, years: int, store: ParquetDataStore) -> int:
    """Download and vault a single ticker/timeframe."""
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed: pip install yfinance")
        return 0

    # Check last date for incremental download
    last_date = store.bars_last_date(ticker, tf)

    if last_date:
        start_dt = last_date + timedelta(days=1)
        period = None
        start_str = start_dt.strftime("%Y-%m-%d")
        logger.info(f"Incremental: {ticker}/{tf} from {start_str}")
        df = yf.download(
            ticker, start=start_str,
            interval=tf, progress=False, auto_adjust=True,
        )
    else:
        if tf == "1h":
            # Yahoo limits 1h to ~730 days
            period = "730d"
        else:
            period = f"{years}y"
        logger.info(f"Full download: {ticker}/{tf} period={period}")
        df = yf.download(
            ticker, period=period,
            interval=tf, progress=False, auto_adjust=True,
        )

    if df.empty:
        logger.warning(f"No data returned for {ticker}/{tf}")
        return 0

    df = harmonize_yfinance(df, ticker)
    store.save_bars(ticker, tf, df)
    return len(df)


def download_macro(store: ParquetDataStore) -> None:
    """Download VIX and yield curve data."""
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed")
        return

    # VIX
    logger.info("Downloading VIX...")
    vix = yf.download("^VIX", period="5y", interval="1d", progress=False)
    if not vix.empty:
        vix = harmonize_yfinance(vix, "^VIX")
        store.save_macro("vix", vix)
        logger.info(f"VIX: {len(vix)} bars saved")

    # Yields
    logger.info("Downloading yields (TNX, IRX)...")
    tnx = yf.download("^TNX", period="5y", interval="1d", progress=False)
    irx = yf.download("^IRX", period="5y", interval="1d", progress=False)

    if not tnx.empty and not irx.empty:
        tnx = harmonize_yfinance(tnx, "^TNX")
        irx = harmonize_yfinance(irx, "^IRX")
        yields = pd.DataFrame({
            "yield_10y": tnx["close"],
            "yield_3m": irx["close"],
        }).dropna()
        store.save_macro("yields", yields)
        logger.info(f"Yields: {len(yields)} bars saved")


def resample_timeframes(ticker: str, store: ParquetDataStore) -> None:
    """R6: Generate 4h from 1h, 1W from 1d."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}

    # 4h from 1h
    df_1h = store.load_bars(ticker, "1h")
    if not df_1h.empty and len(df_1h) > 10:
        df_4h = df_1h.resample("4h").agg(agg).dropna()
        store.save_features(ticker, "ohlcv_4h", df_4h)
        logger.info(f"{ticker}/4h: {len(df_4h)} bars resampled from 1h")

    # 1W from 1d
    df_1d = store.load_bars(ticker, "1d")
    if not df_1d.empty and len(df_1d) > 10:
        df_1w = df_1d.resample("W-FRI").agg(agg).dropna()
        store.save_features(ticker, "ohlcv_1w", df_1w)
        logger.info(f"{ticker}/1W: {len(df_1w)} bars resampled from 1d")


def main():
    parser = argparse.ArgumentParser(description="Download historical data to vault")
    parser.add_argument("--tickers", required=True, help="Comma-separated tickers")
    parser.add_argument("--tf", default="1d", help="Comma-separated timeframes (1d,1h)")
    parser.add_argument("--years", type=int, default=5, help="Years of history for 1d")
    parser.add_argument("--include-macro", action="store_true", help="Also download VIX, yields")
    parser.add_argument("--resample", action="store_true", help="Generate 4h/1W from 1h/1d")
    args = parser.parse_args()

    store = ParquetDataStore()
    tickers = [t.strip().upper() for t in args.tickers.split(",")]
    timeframes = [t.strip() for t in args.tf.split(",")]

    total_bars = 0
    for ticker in tickers:
        for tf in timeframes:
            n = download_ticker(ticker, tf, args.years, store)
            total_bars += n

        if args.resample:
            resample_timeframes(ticker, store)

    if args.include_macro:
        download_macro(store)

    logger.info(f"✅ Download complete: {total_bars} total bars across {len(tickers)} tickers")


if __name__ == "__main__":
    main()
