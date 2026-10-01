import pandas as pd
import numpy as np
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
c = TimescaleDataStore()._conn()

# 1) REGLA FÍSICA: vel_svw debe ~ la velocidad de vwap_sigma_wave → medir el diff real por ticker
print("=== [A] escala FÍSICA: |Δ vwap_sigma_wave| por barra (muestra de tickers) ===")
q = """
SELECT ticker, timestamp, vwap_sigma_wave
FROM engine.channel_snapshots
WHERE ticker IN ('AAPL','AMCR','AIG','PG','TSLA') AND timeframe='1d' AND vwap_sigma_wave IS NOT NULL
ORDER BY ticker, timestamp
"""
df = pd.read_sql(q, c)
df['diff'] = df.groupby('ticker')['vwap_sigma_wave'].diff()
g = df.groupby('ticker')['diff'].apply(lambda s: pd.Series({
    'p50': s.abs().quantile(.5), 'p99': s.abs().quantile(.99), 'max': s.abs().max()}))
print(g.round(4).to_string())

# 2) obs_vel_svw por ticker (sin los millones) para comparar
print("\n=== [B] obs_vel_svw |v| (excluyendo >100 = corrupción) ===")
q2 = """
SELECT ticker, COUNT(*) n, percentile_cont(0.99) WITHIN GROUP (ORDER BY ABS(obs_vel_svw)) p99, MAX(ABS(obs_vel_svw)) mx
FROM engine.channel_snapshots
WHERE ticker IN ('AAPL','AMCR','AIG','PG','TSLA') AND obs_vel_svw IS NOT NULL AND ABS(obs_vel_svw) <= 100
GROUP BY ticker
"""
print(pd.read_sql(q2, c).round(4).to_string(index=False))

# 3) corrupción por año (patrón temporal)
print("\n=== [C] corrupción (|svw|>100) por año ===")
q3 = """
SELECT EXTRACT(YEAR FROM timestamp)::int y, COUNT(*) n
FROM engine.channel_snapshots WHERE ABS(obs_vel_svw) > 100
GROUP BY 1 ORDER BY 1
"""
print(pd.read_sql(q3, c).to_string(index=False))
