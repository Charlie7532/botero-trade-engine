"""
Populate Missing QQQ Constituents into Vault
============================================
Downloads max history for missing QQQ constituent stocks:
['ARM', 'ASML', 'AZN', 'CCEP', 'ILMN', 'MDB', 'MELI', 'PDD', 'TEAM', 'ZS']
and upserts them to market.ohlcv_bars and market.ticker_metadata.
"""

import logging
import os
import psycopg2
import psycopg2.extras
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

MISSING_TICKERS = {
    'ARM': ('Technology', 'Semiconductors', 'MEGA'),
    'ASML': ('Technology', 'Semiconductors', 'MEGA'),
    'AZN': ('Healthcare', 'Pharmaceuticals', 'MEGA'),
    'CCEP': ('Consumer Defensive', 'Beverages', 'LARGE'),
    'ILMN': ('Healthcare', 'Diagnostics & Research', 'LARGE'),
    'MDB': ('Technology', 'Software - Infrastructure', 'LARGE'),
    'MELI': ('Consumer Cyclical', 'Internet Retail', 'MEGA'),
    'PDD': ('Consumer Cyclical', 'Internet Retail', 'MEGA'),
    'TEAM': ('Technology', 'Software - Application', 'LARGE'),
    'ZS': ('Technology', 'Software - Infrastructure', 'LARGE'),
}

def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is missing")
    
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    
    # 1. Upsert metadata
    logging.info("Upserting ticker metadata for missing QQQ constituents...")
    for ticker, (sector, industry, cap_bucket) in MISSING_TICKERS.items():
        cur.execute("""
            INSERT INTO market.ticker_metadata (ticker, sector, industry, market_cap_bucket, updated_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (ticker) DO UPDATE SET
                sector = EXCLUDED.sector,
                industry = EXCLUDED.industry,
                market_cap_bucket = EXCLUDED.market_cap_bucket,
                updated_at = NOW();
        """, (ticker, sector, industry, cap_bucket))
    conn.commit()
    
    # 2. Ingest OHLCV bars
    for ticker in MISSING_TICKERS.keys():
        logging.info(f"Downloading history for {ticker}...")
        tk = yf.Ticker(ticker)
        df = tk.history(period="max")
        if df.empty:
            logging.warning(f"No data returned for {ticker}")
            continue
        
        logging.info(f"Writing {len(df)} bars for {ticker} (Range: {df.index.min().date()} -> {df.index.max().date()})...")
        
        records = []
        for idx, row in df.iterrows():
            dt_str = idx.strftime("%Y-%m-%d 00:00:00+00")
            records.append((
                ticker,
                '1d',
                dt_str,
                float(row['Open']),
                float(row['High']),
                float(row['Low']),
                float(row['Close']),
                float(row['Volume'])
            ))
        
        insert_query = """
            INSERT INTO market.ohlcv_bars (ticker, timeframe, time, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, timeframe, time) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume;
        """
        psycopg2.extras.execute_batch(cur, insert_query, records, page_size=1000)
        conn.commit()
        logging.info(f"✅ {ticker} successfully saved to Vault!")

    cur.close()
    conn.close()
    logging.info("🎉 All missing QQQ constituents ingested and metadata updated successfully!")

if __name__ == "__main__":
    main()
