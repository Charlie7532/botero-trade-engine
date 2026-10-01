import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
c = TimescaleDataStore()._conn()
print("=== AMCR: muestra de obs_vel_svw (¿patrón de corrupción?) ===")
print(pd.read_sql("""SELECT timestamp, obs_vel_svw, obs_vel_sigma_c, obs_vel_tension_w, obs_vel_rsi, obs_vel_conj_wt, obs_velocity_norm, obs_recovery_score
FROM engine.channel_snapshots WHERE ticker='AMCR' AND obs_vel_svw IS NOT NULL ORDER BY ABS(obs_vel_svw) DESC LIMIT 6""", c).to_string(index=False))
print("\n=== ¿Cuántos tickers tienen |obs_vel_svw| > 1? ===")
print(pd.read_sql("SELECT COUNT(DISTINCT ticker) n FROM engine.channel_snapshots WHERE ABS(obs_vel_svw) > 1", c).to_string(index=False))
print("\n=== ¿Cuántas FILAS con |obs_vel_svw| > 1? y vs total ===")
print(pd.read_sql("SELECT COUNT(*) FILTER (WHERE ABS(obs_vel_svw)>1) malas, COUNT(*) total FROM engine.channel_snapshots WHERE obs_vel_svw IS NOT NULL", c).to_string(index=False))
print("\n=== tickers con |v|>1 (¿todos A-H?) ===")
print(pd.read_sql("SELECT DISTINCT ticker FROM engine.channel_snapshots WHERE ABS(obs_vel_svw)>1 ORDER BY ticker", c).ticker.tolist())
