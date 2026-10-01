import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
conn = TimescaleDataStore()._conn()
df = pd.read_sql("SELECT ticker, sector, industry FROM market.ticker_metadata WHERE ticker IN ('SPY','QQQ','IWM','DIA','TLT','VIX','VVIX')", conn)
print(df.to_string(index=False))
print("\n--- sectores de los ETFs ---")
df2 = pd.read_sql("SELECT sector, COUNT(*) n FROM market.ticker_metadata GROUP BY sector ORDER BY n DESC", conn)
print(df2.to_string(index=False))
