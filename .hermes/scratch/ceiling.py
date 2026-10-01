import pandas as pd, numpy as np
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
c = TimescaleDataStore()._conn()

# TECHO FÍSICO: máxima |Δ| por barra de las columnas FUENTE (excluyendo filas corruptas de fuente)
print("=== TECHO FÍSICO de |Δ| por barra (columnas fuente, sin filas >1e4) ===")
src = ['vwap_sigma_wave','tide_slope','current_slope','wave_slope','sigma_current','sigma_wave']
for col in src:
    q = f"""
    WITH s AS (
      SELECT ticker, timestamp, {col} v FROM engine.channel_snapshots
      WHERE {col} IS NOT NULL AND ABS({col}) < 1e4 AND timeframe='1d'
    ), d AS (
      SELECT ABS(v - LAG(v) OVER (PARTITION BY ticker ORDER BY timestamp)) a FROM s
    )
    SELECT MAX(a) mx, percentile_cont(0.999) WITHIN GROUP (ORDER BY a) p999 FROM d WHERE a IS NOT NULL
    """
    r = pd.read_sql(q, c).iloc[0]
    print(f"  {col:20s} |Δ| p99.9={r.p999:.3f}  máx={r.mx:.3f}")

print("\n=== obs_vel_* : cuántas filas por encima de cada umbral ===")
for col in ['obs_vel_svw','obs_vel_tension_w','obs_vel_sigma_c','obs_vel_conj_wt','obs_vel_rsi','obs_velocity_norm']:
    s = pd.read_sql(f'SELECT ABS({col}) v FROM engine.channel_snapshots WHERE {col} IS NOT NULL', c).v
    print(f"  {col:22s} " + " ".join([f">{t}:{int((s>t).sum()):,}" for t in [1,5,10,20,50,100]]))
