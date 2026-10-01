import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
conn = TimescaleDataStore()._conn()
q = """
SELECT COUNT(*) AS n_rows,
       COUNT(DISTINCT ticker) AS n_tickers
FROM engine.channel_snapshots
WHERE obs_vel_svw IS NOT NULL
"""
print(pd.read_sql(q, conn).to_string(index=False))
q2 = """
SELECT COUNT(DISTINCT ticker) AS tickers_total
FROM engine.channel_snapshots
"""
print(pd.read_sql(q2, conn).to_string(index=False))
