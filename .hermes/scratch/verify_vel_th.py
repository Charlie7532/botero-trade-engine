import json
th = json.load(open('backend/modules/quality_swing/domain/rules/rc_vol_normalized_thresholds.json'))
print("=== NORMATIVO vwap_sigma_wave (percentiles REALES) ===")
print("  ", th.get('vwap_sigma_wave'))
print("=== NORMATIVO kalman_velocity ===")
print("  ", th.get('kalman_velocity'))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
import pandas as pd
conn = TimescaleDataStore()._conn()
# conteo y percentiles REALES de obs_vel_svw
q = """
SELECT
  COUNT(*) FILTER (WHERE obs_vel_svw IS NOT NULL AND obs_vel_svw <> 0) AS n_nonzero,
  COUNT(*) AS n_total,
  percentile_cont(0.33) WITHIN GROUP (ORDER BY obs_vel_svw) AS p33,
  percentile_cont(0.50) WITHIN GROUP (ORDER BY obs_vel_svw) AS p50,
  percentile_cont(0.67) WITHIN GROUP (ORDER BY obs_vel_svw) AS p67
FROM engine.channel_snapshots
WHERE obs_vel_svw IS NOT NULL
"""
df = pd.read_sql(q, conn)
print("\n=== obs_vel_svw en engine.channel_snapshots ===")
print(df.to_string(index=False))
