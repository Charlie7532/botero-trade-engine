import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
c = TimescaleDataStore()._conn()
print("=== [D] ¿corrupción en la FUENTE (vwap_sigma_wave / slopes)? ===")
print(pd.read_sql("""
SELECT
  COUNT(*) FILTER (WHERE ABS(vwap_sigma_wave) > 100)  svw_100,
  COUNT(*) FILTER (WHERE ABS(vwap_sigma_wave) > 10)   svw_10,
  COUNT(*) FILTER (WHERE ABS(tide_slope_norm) > 100)  tide_100,
  COUNT(*) FILTER (WHERE ABS(current_slope_norm) > 100) curr_100,
  COUNT(*) FILTER (WHERE ABS(wave_slope) > 100)       wave_100,
  COUNT(*) FILTER (WHERE ABS(sigma_current) > 100)    sigc_100,
  COUNT(*) FILTER (WHERE ABS(sigma_wave) > 100)       sigw_100
FROM engine.channel_snapshots WHERE vwap_sigma_wave IS NOT NULL
""", c).to_string(index=False))

print("\n=== [E] tickers con |vwap_sigma_wave| > 100 ===")
df = pd.read_sql("SELECT ticker, COUNT(*) n, MAX(ABS(vwap_sigma_wave)) mx FROM engine.channel_snapshots WHERE ABS(vwap_sigma_wave)>100 GROUP BY ticker ORDER BY mx DESC", c)
print(df.head(12).to_string(index=False)); print("total tickers:", len(df))

print("\n=== [F] ¿en qué años está la corrupción? (|svw|>100) ===")
print(pd.read_sql("SELECT EXTRACT(YEAR FROM timestamp)::int y, COUNT(*) n FROM engine.channel_snapshots WHERE ABS(vwap_sigma_wave)>100 GROUP BY 1 ORDER BY 1", c).head(20).to_string(index=False))
