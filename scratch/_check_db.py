import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from dotenv import load_dotenv
load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
store = TimescaleDataStore()
engine = store.engine

# Check for pre-computed synthetic indicator tables
tables = pd.read_sql("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema='market' ORDER BY table_name", engine)
print("Market tables:")
for _, row in tables.iterrows():
    print(f"  {row['table_schema']}.{row['table_name']}")

# Check for synthetic indicator tickers
ticks = pd.read_sql("SELECT DISTINCT ticker FROM market.ohlcv_bars ORDER BY ticker", engine)
print("\nAll tickers in ohlcv_bars:")
for t in ticks['ticker']:
    print(f"  {t}")

store.close()