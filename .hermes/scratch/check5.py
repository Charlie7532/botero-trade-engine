import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
conn = TimescaleDataStore()._conn()
qs = """
SELECT t.ticker,
  (SELECT COUNT(*) FROM engine.channel_snapshots c WHERE c.ticker=t.ticker AND c.timeframe='1d') AS snaps,
  (SELECT COUNT(*) FROM engine.zigzag_points z WHERE z.ticker=t.ticker) AS zz,
  (SELECT COUNT(*) FROM market.ohlcv_bars b WHERE b.ticker=t.ticker AND b.timeframe='1d') AS bars
FROM (SELECT unnest(ARRAY['SPY','TLT','LQD','DBA','UUP','AAPL','QQQ']) AS ticker) t
"""
print(pd.read_sql(qs, conn).to_string(index=False))
print("\n=== ¿obs_vel_svw ya presente para esos? ===")
q2 = """
SELECT ticker, COUNT(*) n FROM engine.channel_snapshots
WHERE ticker IN ('SPY','TLT','LQD','DBA','UUP') AND obs_vel_svw IS NOT NULL
GROUP BY ticker
"""
print(pd.read_sql(q2, conn).to_string(index=False) if True else "")
