"""Verify backfill results in market.regime_states."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv
load_dotenv()

import psycopg2
dsn = os.environ["POSTGRES_URL"]
conn = psycopg2.connect(dsn)
cur = conn.cursor()

# Summary by key
cur.execute("""
    SELECT key, COUNT(*) as transitions,
           MIN(entered_at)::date as first_date,
           MAX(entered_at)::date as last_date
    FROM market.regime_states
    GROUP BY key
    ORDER BY key
""")
print("=== Regime State Summary ===")
for row in cur.fetchall():
    print(f"  {row[0]:30s} → {row[1]:4d} transitions ({row[2]} → {row[3]})")

# Currently active states
print("\n=== Currently Active States ===")
cur.execute("""
    SELECT key, current_state, previous_state, duration_bars,
           entered_at::date, trigger_event
    FROM market.regime_states
    WHERE closed_at IS NULL
    ORDER BY key
""")
for row in cur.fetchall():
    print(f"  {row[0]:30s} → {row[1]:12s} (day {row[3]:4d}, prev={row[2]}, since={row[4]}, trigger={row[5]})")

# State distribution
print("\n=== Quality State Distribution ===")
cur.execute("""
    SELECT current_state, COUNT(*), AVG(duration_bars)::int
    FROM market.regime_states
    WHERE key = 'vol:quality:MARKET'
    GROUP BY current_state
    ORDER BY COUNT(*) DESC
""")
for row in cur.fetchall():
    print(f"  {row[0]:12s} → {row[1]:4d} episodes, avg duration={row[2]:4d} bars")

print("\n=== Speculative State Distribution ===")
cur.execute("""
    SELECT current_state, COUNT(*), AVG(duration_bars)::int
    FROM market.regime_states
    WHERE key = 'vol:speculative:MARKET'
    GROUP BY current_state
    ORDER BY COUNT(*) DESC
""")
for row in cur.fetchall():
    print(f"  {row[0]:12s} → {row[1]:4d} episodes, avg duration={row[2]:4d} bars")

cur.close()
conn.close()
