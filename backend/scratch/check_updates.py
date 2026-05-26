import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

store = TimescaleDataStore()
conn = store._conn()
try:
    with conn.cursor() as cur:
        # Check overall breadth indicators
        cur.execute("""
            SELECT ticker, MAX(time) as latest_date, COUNT(*) as count 
            FROM market.ohlcv_bars 
            WHERE ticker IN ('S5TH', 'S5TW', 'S5FI')
            GROUP BY ticker
            ORDER BY ticker
        """)
        print("--- Global Breadth Indicators ---")
        for row in cur.fetchall():
            print(f"Ticker: {row[0]}, Latest Bar Date: {row[1]}, Total Bars: {row[2]}")
            
        # Check sector breadth indicators (e.g., S5_XLK_TH, etc.)
        cur.execute("""
            SELECT ticker, MAX(time) as latest_date, COUNT(*) as count 
            FROM market.ohlcv_bars 
            WHERE ticker LIKE 'S5_%'
            GROUP BY ticker
            ORDER BY ticker
        """)
        print("\n--- Sector Breadth Indicators ---")
        rows = cur.fetchall()
        if not rows:
            print("No sector breadth indicators found in market.ohlcv_bars!")
        for row in rows:
            print(f"Ticker: {row[0]}, Latest Bar Date: {row[1]}, Total Bars: {row[2]}")
finally:
    store._put(conn)
    store.close()
