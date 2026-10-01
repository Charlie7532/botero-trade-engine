import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
conn = TimescaleDataStore()._conn()
print("=== los '59': asset_type + update_source + release_cadence ===")
q = """
SELECT asset_type, industry, update_source, release_cadence, COUNT(*) n
FROM market.ticker_metadata
WHERE UPPER(asset_type)='STOCK' AND UPPER(industry)='INDICATOR'
GROUP BY 1,2,3,4 ORDER BY n DESC
"""
print(pd.read_sql(q, conn).to_string(index=False))
print("\n=== muestra de tickers + su update_source ===")
q2 = """
SELECT ticker, asset_type, industry, update_source, release_cadence
FROM market.ticker_metadata
WHERE UPPER(asset_type)='STOCK' AND UPPER(industry)='INDICATOR'
ORDER BY ticker LIMIT 12
"""
print(pd.read_sql(q2, conn).to_string(index=False))
print("\n=== SPY/QQQ/AAPL: update_source ===")
print(pd.read_sql("SELECT ticker, asset_type, industry, update_source FROM market.ticker_metadata WHERE ticker IN ('SPY','QQQ','AAPL','VIX')", conn).to_string(index=False))
