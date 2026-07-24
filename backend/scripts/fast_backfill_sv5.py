"""
Fast Vectorized SV5 Historical Backfill (1999 - 2026)
=====================================================
Computes all 33 sector & market volume breadth indicators (SV5TH, SV5FI, SV5TW, SV5_XLK_TH, etc.)
in less than 5 seconds using Pandas rolling matrix operations.
"""

import os
import sys
import logging
import time
import psycopg2
import psycopg2.extras
import pandas as pd
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from backend.modules.shared.domain.constants.sectors import (
    SECTOR_ETFS,
    SECTOR_VOLUME_BREADTH_TICKERS,
    VOLUME_BREADTH_MA_CONFIG,
    canonicalize,
)

_SECTOR_TO_ETF = {v: k for k, v in SECTOR_ETFS.items()}

def main():
    pg_url = os.getenv("DATABASE_URL")
    if not pg_url:
        raise ValueError("DATABASE_URL is missing")
        
    conn = psycopg2.connect(pg_url)
    cur = conn.cursor()
    
    logging.info("Loading OHLCV volumes for SP500 + QQQ tickers from Vault...")
    t0 = time.time()
    
    cur.execute("""
        SELECT b.ticker, m.sector, b.time::date as date, b.volume
        FROM market.ohlcv_bars b
        JOIN market.ticker_metadata m ON b.ticker = m.ticker
        WHERE b.timeframe = '1d'
          AND m.asset_type = 'STOCK'
          AND ('SP500' = ANY(m.index_membership) OR 'QQQ' = ANY(m.index_membership))
          AND m.sector IS NOT NULL
          AND b.volume > 0
          AND b.time >= '1998-01-01'
        ORDER BY date, b.ticker
    """)
    rows = cur.fetchall()
    logging.info(f"Loaded {len(rows):,} volume rows in {time.time()-t0:.1f}s.")
    
    df = pd.DataFrame(rows, columns=['ticker', 'sector', 'date', 'volume'])
    df['sector_canon'] = df['sector'].apply(canonicalize)
    df['etf'] = df['sector_canon'].map(_SECTOR_TO_ETF)
    
    # Pivot volume matrix: index = date, columns = ticker
    p_vol = df.pivot(index='date', columns='ticker', values='volume')
    
    # Ticker to ETF map
    ticker_etf = df.groupby('ticker')['etf'].first().to_dict()
    
    indicators = {}
    
    logging.info("Computing vectorized rolling MAs for SV5 indicators...")
    for scale_key, config in VOLUME_BREADTH_MA_CONFIG.items():
        fast = config['fast']
        slow = config['slow']
        
        fast_ma = p_vol.rolling(fast, min_periods=fast//2).mean()
        slow_ma = p_vol.rolling(slow, min_periods=slow//2).mean()
        
        above = (fast_ma > slow_ma).astype(float)
        valid = ~fast_ma.isna() & ~slow_ma.isna()
        above_valid = above.where(valid)
        
        # 1. Market aggregate (SV5TH, SV5FI, SV5TW)
        mkt_ind = {"tactical": "SV5TW", "intermediate": "SV5FI", "structural": "SV5TH"}[scale_key]
        mkt_breadth = (above_valid.sum(axis=1) / valid.sum(axis=1).replace(0, np.nan) * 100.0).round(1)
        indicators[mkt_ind] = (mkt_breadth, valid.sum(axis=1))
        
        # 2. Per-sector indicators
        for etf in SECTOR_VOLUME_BREADTH_TICKERS.keys():
            sec_tickers = [t for t, e in ticker_etf.items() if e == etf]
            if not sec_tickers:
                continue
            
            ind_ticker = SECTOR_VOLUME_BREADTH_TICKERS[etf][scale_key]
            sec_above = above_valid[sec_tickers]
            sec_valid = valid[sec_tickers]
            
            sec_cnt = sec_valid.sum(axis=1)
            sec_breadth = (sec_above.sum(axis=1) / sec_cnt.replace(0, np.nan) * 100.0).round(1)
            indicators[ind_ticker] = (sec_breadth, sec_cnt)
            
    # Filter for dates >= 1999-01-01
    dates_filter = p_vol.index[p_vol.index >= datetime.strptime('1999-01-01', '%Y-%m-%d').date()]
    
    logging.info(f"Upserting {len(indicators)} indicators into Vault ({len(dates_filter)} dates)...")
    
    for ind_ticker, (series, cnt_series) in indicators.items():
        records = []
        for dt in dates_filter:
            if dt not in series.index:
                continue
            val = series.loc[dt]
            if pd.isna(val):
                continue
            cnt = int(cnt_series.loc[dt]) if dt in cnt_series.index else 0
            dt_str = f"{dt} 00:00:00+00"
            records.append((dt_str, ind_ticker, '1d', float(val), float(val), float(val), float(val), float(cnt)))
            
        if records:
            insert_query = """
                INSERT INTO market.ohlcv_bars (time, ticker, timeframe, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, timeframe, time) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume;
            """
            psycopg2.extras.execute_batch(cur, insert_query, records, page_size=2000)
            conn.commit()
            logging.info(f"  ✅ {ind_ticker}: {len(records)} bars saved.")
            
    cur.close()
    conn.close()
    logging.info("🎉 All SV5 volume breadth indicators 100% vectorised and saved to Vault!")

if __name__ == "__main__":
    main()
