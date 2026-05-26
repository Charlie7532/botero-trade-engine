"""Quick test: run SectorBreadthProvider.run_full() and verify it writes bars."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s — %(message)s")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.daemons.vault_providers.sector_breadth_provider import SectorBreadthProvider

store = TimescaleDataStore()
provider = SectorBreadthProvider()

print(f"Provider name: {provider.name}")
print(f"Provider categories: {provider.categories}")

result = provider.run_full(store)
print(f"\nResult: {result}")

# Now verify what's in the DB
conn = store._conn()
try:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ticker, MAX(time) as latest_date, 
                   (SELECT close FROM market.ohlcv_bars b2 
                    WHERE b2.ticker = b.ticker AND b2.timeframe='1d' 
                    ORDER BY time DESC LIMIT 1) as latest_close
            FROM market.ohlcv_bars b
            WHERE ticker LIKE 'S5_%%'
            GROUP BY ticker
            ORDER BY ticker
        """)
        print("\n--- Sector Breadth After Update ---")
        for row in cur.fetchall():
            print(f"  {row[0]:15s}  latest={str(row[1])[:10]}  breadth={row[2]:.1f}%")
finally:
    store._put(conn)
    store.close()
