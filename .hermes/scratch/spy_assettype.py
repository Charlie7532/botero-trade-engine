import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
conn = TimescaleDataStore()._conn()
print("=== ticker_metadata: columnas ===")
cols = pd.read_sql("SELECT column_name FROM information_schema.columns WHERE table_schema='market' AND table_name='ticker_metadata' ORDER BY ordinal_position", conn)
print(", ".join(cols.column_name.tolist()))
print("\n=== SPY/QQQ/DIA/IWM (asset_type, sector, industry) ===")
print(pd.read_sql("SELECT ticker, asset_type, sector, industry FROM market.ticker_metadata WHERE ticker IN ('SPY','QQQ','DIA','IWM','AAPL','VIX') ORDER BY ticker", conn).to_string(index=False))
print("\n=== ¿hay ETFs en engine.zigzag_points? ===")
print(pd.read_sql("SELECT COUNT(DISTINCT ticker) n FROM engine.zigzag_points WHERE ticker IN ('SPY','QQQ','DIA','IWM')", conn).to_string(index=False))
print("\n=== conteo asset_type ===")
print(pd.read_sql("SELECT asset_type, COUNT(*) n FROM market.ticker_metadata GROUP BY asset_type ORDER BY n DESC", conn).to_string(index=False))
