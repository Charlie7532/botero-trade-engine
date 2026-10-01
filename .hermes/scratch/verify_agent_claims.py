import pandas as pd, re
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

# 1) _WAVE_PATH en rc_wave_lookup.py
import pathlib
src = pathlib.Path('backend/modules/quality_swing/domain/rules/rc_wave_lookup.py').read_text(errors='ignore')
for m in re.finditer(r'_WAVE_PATH\s*=.*', src):
    print("  ", m.group(0).strip())

# 2) barras de SPY
conn = TimescaleDataStore()._conn()
q = """
SELECT COUNT(*) AS n_bars, MIN(timestamp) AS t0, MAX(timestamp) AS t1
FROM engine.channel_snapshots
WHERE ticker='SPY' AND timeframe='1d'
"""
print("\n=== SPY ===")
print(pd.read_sql(q, conn).to_string(index=False))
