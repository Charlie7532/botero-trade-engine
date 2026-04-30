"""
Run the Trade Journal migration SQL against the configured PostgreSQL instance.
Reads POSTGRES_URL from .env, executes migrate_journal_to_postgres.sql.
"""
import os
import sys
from pathlib import Path

# Load .env
from dotenv import load_dotenv
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(env_path)

import psycopg2

DSN = os.environ.get("POSTGRES_URL", "")
if not DSN:
    print("❌ POSTGRES_URL not set in .env")
    sys.exit(1)

SQL_FILE = Path(__file__).resolve().parent / "migrate_journal_to_postgres.sql"
if not SQL_FILE.exists():
    print(f"❌ SQL file not found: {SQL_FILE}")
    sys.exit(1)

sql = SQL_FILE.read_text()

print(f"Connecting to PostgreSQL...")
conn = psycopg2.connect(DSN)
conn.autocommit = True

with conn.cursor() as cur:
    # 1. Ensure engine schema exists
    cur.execute("CREATE SCHEMA IF NOT EXISTS engine;")
    print("✅ Schema 'engine' ready")

    # 2. Try pgvector extension (optional — may fail on some plans)
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        print("✅ pgvector extension enabled")
    except Exception as e:
        print(f"⚠️  pgvector not available ({e}). find_similar_trades() will return []. Continuing...")
        conn.rollback()
        conn.autocommit = True

    # 3. Execute migration SQL (skip vector column if extension not available)
    try:
        cur.execute(sql)
        print("✅ Trade Journal tables created successfully")
    except Exception as e:
        # If it fails on vector type, retry without that column
        if "vector" in str(e).lower():
            print(f"⚠️  vector type not available, retrying without entry_vector column...")
            conn.rollback()
            conn.autocommit = True
            sql_no_vector = sql.replace("entry_vector        vector(32)", "-- entry_vector column skipped (pgvector not available)")
            cur.execute(sql_no_vector)
            print("✅ Trade Journal tables created (without vector search)")
        else:
            raise

    # 4. Verify
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'engine'
        ORDER BY table_name
    """)
    tables = [row[0] for row in cur.fetchall()]
    print(f"\n📋 Tables in 'engine' schema:")
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM engine.{t}")
        count = cur.fetchone()[0]
        print(f"   {t}: {count} rows")

conn.close()
print("\n🎉 Migration complete!")
