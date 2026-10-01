import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
c = TimescaleDataStore()._conn()

# POBLACIÓN COMPLETA de tickers con obs_vel_svw (sin ordenar por std)
q = """
SELECT ticker, COUNT(*) n, STDDEV(obs_vel_svw) std,
  percentile_cont(0.33) WITHIN GROUP (ORDER BY obs_vel_svw) p33,
  percentile_cont(0.67) WITHIN GROUP (ORDER BY obs_vel_svw) p67,
  MIN(obs_vel_svw) mn, MAX(obs_vel_svw) mx
FROM engine.channel_snapshots WHERE obs_vel_svw IS NOT NULL
GROUP BY ticker HAVING COUNT(*) > 30
"""
df = pd.read_sql(q, c)
print("TICKERS CON DATOS (n>30):", len(df))
print("\n=== distribucion de std per-ticker ===")
print(df['std'].describe(percentiles=[.1,.25,.5,.75,.9,.99]).round(4).to_string())
print("\n=== distribucion de p33 per-ticker ===")
print(df['p33'].describe(percentiles=[.1,.25,.5,.75,.9]).round(4).to_string())
print("\n=== distribucion de p67 per-ticker ===")
print(df['p67'].describe(percentiles=[.1,.25,.5,.75,.9]).round(4).to_string())
print("\n=== ratio de spread (p67-p33) max/min ===")
sp = df['p67']-df['p33']
print(sp.describe(percentiles=[.1,.5,.9]).round(4).to_string())
print("ratio p90/p10:", round(sp.quantile(.9)/sp.quantile(.1),1))
print("\n=== los 7 outliers: valores extremos ===")
print(df[df['ticker'].isin(['AMCR','AIG','CRH','BRO','FICO','FITB','HBAN'])].to_string(index=False))
