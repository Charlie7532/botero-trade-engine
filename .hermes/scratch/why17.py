import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
conn = TimescaleDataStore()._conn()

q1 = """
SELECT ticker, COUNT(*) AS n, MIN(timestamp) AS t0, MAX(timestamp) AS t1
FROM engine.channel_snapshots
WHERE obs_vel_svw IS NOT NULL
GROUP BY ticker ORDER BY ticker
"""
print("=== LOS 17 TICKERS con obs_vel_svw ===")
print(pd.read_sql(q1, conn).to_string(index=False))

for tbl in ('engine.kalman_state', 'engine.ml_features', 'engine.ticker_fact_states', 'engine.regime_states'):
    try:
        cols = pd.read_sql(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='engine' AND table_name='{tbl.split('.')[1]}'
        """, conn)['column_name'].tolist()
        has = [c for c in cols if 'vel' in c.lower() or 'svw' in c.lower()]
        n = pd.read_sql(f"SELECT COUNT(*) AS n FROM {tbl}", conn)['n'][0]
        print(f"\n{tbl}: {n:,} filas | cols vel/svw: {has}")
    except Exception as e:
        print(f"\n{tbl}: ERR {str(e)[:80]}")
