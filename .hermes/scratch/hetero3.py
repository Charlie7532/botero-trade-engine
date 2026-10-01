import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
c = TimescaleDataStore()._conn()
q = """
SELECT ticker, COUNT(*) n, STDDEV(obs_vel_svw) std,
  percentile_cont(0.33) WITHIN GROUP (ORDER BY obs_vel_svw) p33,
  percentile_cont(0.67) WITHIN GROUP (ORDER BY obs_vel_svw) p67,
  MIN(obs_vel_svw) mn, MAX(obs_vel_svw) mx
FROM engine.channel_snapshots WHERE obs_vel_svw IS NOT NULL
GROUP BY ticker HAVING COUNT(*) > 30
"""
df = pd.read_sql(q, c)
print("=== EXTREMOS de p33 (los umbrales MAS distintos) ===")
print("--- 5 p33 mas NEGATIVOS (alta vol) ---")
print(df.nsmallest(5,'p33')[['ticker','std','p33','p67']].to_string(index=False))
print("--- 5 p33 mas suaves (baja vol) ---")
print(df.nlargest(5,'p33')[['ticker','std','p33','p67']].to_string(index=False))
print("\n=== simulacion: clasificar con umbral GLOBAL (-0.133/+0.129) ===")
print("Un ticker con p33 propio -0.05/+0.07 quedaria SIEMPRE en ~ (el umbral global es 2.5x mas ancho)")
print("\n=== outliers: extremos crudos ===")
o = df[df['std']>1].sort_values('std',ascending=False)
print(o[['ticker','n','std','mn','mx','p33','p67']].to_string(index=False))
