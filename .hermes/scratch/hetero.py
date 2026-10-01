import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
c = TimescaleDataStore()._conn()
df = pd.read_sql("""SELECT ticker, COUNT(*) n, STDDEV(obs_vel_svw) std,
  percentile_cont(0.33) WITHIN GROUP (ORDER BY obs_vel_svw) p33,
  percentile_cont(0.67) WITHIN GROUP (ORDER BY obs_vel_svw) p67,
  AVG(obs_vel_svw) avg
FROM engine.channel_snapshots WHERE obs_vel_svw IS NOT NULL
GROUP BY ticker HAVING COUNT(*)>30 ORDER BY std DESC""", c)
print("### HETEROCEDASTICIDAD de obs_vel_svw por ticker ###")
print(df.to_string(index=False))
print()
print("ratio max/min de std:", round(df['std'].max()/df['std'].min(),1) if len(df)>1 else 'n/a')
print("tickers con datos:", len(df))
g = pd.read_sql("SELECT COUNT(*), STDDEV(obs_vel_svw), percentile_cont(0.33) WITHIN GROUP (ORDER BY obs_vel_svw) p33, percentile_cont(0.67) WITHIN GROUP (ORDER BY obs_vel_svw) p67 FROM engine.channel_snapshots WHERE obs_vel_svw IS NOT NULL", c)
print("\nGLOBAL (pooled): n=%s std=%s p33=%s p67=%s" % (g.iloc[0,0], round(float(g.iloc[0,1]),4), round(float(g.iloc[0,2]),4), round(float(g.iloc[0,3]),4)))
