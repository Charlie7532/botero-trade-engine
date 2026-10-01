import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
conn = TimescaleDataStore()._conn()

# 1) Tablas del esquema engine
q = """
SELECT table_name FROM information_schema.tables
WHERE table_schema IN ('engine','market','public')
ORDER BY table_schema, table_name
"""
df = pd.read_sql(q, conn)
print("=== TABLAS ===")
print(df.to_string(index=False))
