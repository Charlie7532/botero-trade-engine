"""
Generate S5_QQQ & SV5_QQQ Breadth Indicators (1999 - 2026)
=========================================================
Computes daily breadth indicators for the 98 QQQ constituent stocks:
- S5_QQQ_TH: % of QQQ constituents > 200-DMA (Equal-weighted)
- S5_QQQ_FI: % of QQQ constituents > 50-DMA (Equal-weighted)
- S5_QQQ_TW: % of QQQ constituents > 20-DMA (Equal-weighted)
- SV5_QQQ_TH: Volume-weighted % > 200-DMA
- SV5_QQQ_FI: Volume-weighted % > 50-DMA
- SV5_QQQ_TW: Volume-weighted % > 20-DMA

Upserts all 6 indicators into market.ohlcv_bars with industry='INDICATOR' & sector='QQQ Breadth'.
"""

import logging
import os
import psycopg2
import psycopg2.extras
import pandas as pd
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

QQQ_TICKERS = [
    'AAPL', 'ABNB', 'ADBE', 'ADI', 'ADP', 'ADSK', 'AEP', 'AMAT', 'AMD', 'AMGN',
    'AMZN', 'APP', 'ARM', 'ASML', 'AVGO', 'AZN', 'BIIB', 'BKNG', 'BKR', 'CCEP',
    'CDNS', 'CDW', 'CEG', 'CHTR', 'CMCSA', 'COST', 'CPRT', 'CRWD', 'CSCO', 'CSGP',
    'CSX', 'CTAS', 'CTSH', 'DASH', 'DDOG', 'DLTR', 'DXCM', 'EA', 'EXC', 'FANG',
    'FAST', 'FTNT', 'GEHC', 'GILD', 'GOOG', 'GOOGL', 'HON', 'IDXX', 'ILMN', 'INTC',
    'INTU', 'ISRG', 'KDP', 'KHC', 'KLAC', 'LRCX', 'MAR', 'MDB', 'MDLZ', 'MELI',
    'MCHP', 'MNST', 'MRNA', 'MSFT', 'MU', 'NFLX', 'NXPI', 'NVDA', 'ODFL', 'ON',
    'ORLY', 'PANW', 'PAYX', 'PCAR', 'PDD', 'PEP', 'PLTR', 'PYPL', 'QCOM', 'REGN',
    'ROP', 'ROST', 'SBUX', 'SMCI', 'SNPS', 'TEAM', 'TMUS', 'TSLA', 'TTD', 'TXN',
    'VRSK', 'VRTX', 'WBD', 'WDAY', 'WDC', 'XEL', 'ZS'
]

def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is missing")
    
    conn = psycopg2.connect(db_url)
    
    logging.info(f"Loading OHLCV bars for {len(QQQ_TICKERS)} QQQ constituents from Vault...")
    
    query = """
        SELECT ticker, time::date as date, close, volume
        FROM market.ohlcv_bars
        WHERE ticker = ANY(%s) AND timeframe = '1d' AND time >= '1998-01-01'
        ORDER BY date, ticker;
    """
    df = pd.read_sql(query, conn, params=(QQQ_TICKERS,))
    logging.info(f"Loaded {len(df)} total rows across QQQ constituents.")
    
    # Pivot close and volume
    p_close = df.pivot(index='date', columns='ticker', values='close')
    p_vol = df.pivot(index='date', columns='ticker', values='volume').fillna(0)
    
    # Compute moving averages per ticker
    ma200 = p_close.rolling(200, min_periods=50).mean()
    ma50 = p_close.rolling(50, min_periods=20).mean()
    ma20 = p_close.rolling(20, min_periods=10).mean()
    
    # Flags above DMAs (True/False)
    above_200 = (p_close > ma200)
    above_50 = (p_close > ma50)
    above_20 = (p_close > ma20)
    
    # Valid active constituent count per day
    valid_mask = ~p_close.isna()
    valid_count = valid_mask.sum(axis=1)
    
    # 1. Equal-weighted breadth (% above DMA)
    s5_qqq_th = (above_200.sum(axis=1) / valid_count.replace(0, np.nan) * 100.0).fillna(0.0)
    s5_qqq_fi = (above_50.sum(axis=1) / valid_count.replace(0, np.nan) * 100.0).fillna(0.0)
    s5_qqq_tw = (above_20.sum(axis=1) / valid_count.replace(0, np.nan) * 100.0).fillna(0.0)
    
    # 2. Volume-weighted breadth
    vol_valid = p_vol * valid_mask
    vol_sum = vol_valid.sum(axis=1).replace(0, np.nan)
    
    sv5_qqq_th = ((above_200 * p_vol).sum(axis=1) / vol_sum * 100.0).fillna(0.0)
    sv5_qqq_fi = ((above_50 * p_vol).sum(axis=1) / vol_sum * 100.0).fillna(0.0)
    sv5_qqq_tw = ((above_20 * p_vol).sum(axis=1) / vol_sum * 100.0).fillna(0.0)
    
    # Filter for dates >= 1999-01-01
    s5_df = pd.DataFrame({
        'S5_QQQ_TH': s5_qqq_th,
        'S5_QQQ_FI': s5_qqq_fi,
        'S5_QQQ_TW': s5_qqq_tw,
        'SV5_QQQ_TH': sv5_qqq_th,
        'SV5_QQQ_FI': sv5_qqq_fi,
        'SV5_QQQ_TW': sv5_qqq_tw,
        'n_constituents': valid_count
    }).loc[datetime.strptime('1999-01-01', '%Y-%m-%d').date():]
    
    logging.info(f"Generated {len(s5_df)} daily indicator rows from {s5_df.index.min()} to {s5_df.index.max()}.")
    
    cur = conn.cursor()
    
    # Upsert indicator metadata into market.ticker_metadata
    indicators = ['S5_QQQ_TH', 'S5_QQQ_FI', 'S5_QQQ_TW', 'SV5_QQQ_TH', 'SV5_QQQ_FI', 'SV5_QQQ_TW']
    for ind in indicators:
        cur.execute("""
            INSERT INTO market.ticker_metadata (ticker, sector, industry, market_cap_bucket, updated_at)
            VALUES (%s, 'QQQ Breadth', 'INDICATOR', NULL, NOW())
            ON CONFLICT (ticker) DO UPDATE SET
                sector = 'QQQ Breadth',
                industry = 'INDICATOR',
                updated_at = NOW();
        """, (ind,))
    conn.commit()
    
    # Save to market.ohlcv_bars
    for ind in indicators:
        logging.info(f"Upserting {ind} into Vault...")
        records = []
        for dt, row in s5_df.iterrows():
            val = float(row[ind])
            n_const = int(row['n_constituents'])
            dt_str = f"{dt} 00:00:00+00"
            records.append((
                ind, '1d', dt_str, val, val, val, val, float(n_const)
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
        psycopg2.extras.execute_batch(cur, insert_query, records, page_size=2000)
        conn.commit()
        logging.info(f"✅ {ind} saved ({len(records)} bars).")
        
    cur.close()
    conn.close()
    logging.info("🎉 All 6 S5_QQQ and SV5_QQQ indicators successfully computed and stored in Vault!")

if __name__ == "__main__":
    main()
