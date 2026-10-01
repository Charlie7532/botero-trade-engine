import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
conn = TimescaleDataStore()._conn()
print("=== tickers con sector 'Broad Market' ===")
df = pd.read_sql("SELECT ticker, sector, industry FROM market.ticker_metadata WHERE UPPER(sector)='BROAD MARKET'", conn)
print(df.to_string(index=False) if len(df) else "(ninguno)")
print("\n=== tickers con industry='ETF' (sector != ETF) ===")
df2 = pd.read_sql("SELECT sector, COUNT(*) n FROM market.ticker_metadata WHERE UPPER(industry)='ETF' GROUP BY sector ORDER BY n DESC", conn)
print(df2.to_string(index=False))
print("\n=== todos los sector='ETF' ===")
df3 = pd.read_sql("SELECT ticker FROM market.ticker_metadata WHERE UPPER(sector)='ETF' ORDER BY ticker", conn)
print(", ".join(df3.ticker.tolist()))
