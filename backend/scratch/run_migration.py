"""Run SQL migration 006_regime_states.sql against Neon PostgreSQL."""
import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

dsn = os.environ.get("POSTGRES_URL", "")
if not dsn:
    raise RuntimeError("POSTGRES_URL not set after loading .env")

conn = psycopg2.connect(dsn)
cur = conn.cursor()

with open("backend/sql/006_regime_states.sql") as f:
    sql = f.read()

cur.execute(sql)
conn.commit()

# Verify
cur.execute("SELECT COUNT(*) FROM market.regime_states")
count = cur.fetchone()[0]
print(f"✅ market.regime_states created — {count} rows")

# Verify indexes
cur.execute("""
    SELECT indexname FROM pg_indexes 
    WHERE tablename = 'regime_states' AND schemaname = 'market'
    ORDER BY indexname
""")
for row in cur.fetchall():
    print(f"   Index: {row[0]}")

cur.close()
conn.close()
