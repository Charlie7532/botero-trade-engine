import os, time, psycopg2
from dotenv import load_dotenv

# Load env variables (use .env not .env.local for safety)
load_dotenv(dotenv_path='/root/botero-trade/.env')

url = os.getenv('POSTGRES_URL')
if not url:
    raise RuntimeError('POSTGRES_URL not set')

# Measure connection time
start = time.time()
conn = psycopg2.connect(url, connect_timeout=10)
conn_time = time.time() - start

cur = conn.cursor()
# Simple lightweight query
start = time.time()
cur.execute('SELECT 1')
cur.fetchone()
query_time = time.time() - start

# Larger query: count rows in market.ohlcv_bars
start = time.time()
cur.execute('SELECT COUNT(*) FROM market.ohlcv_bars')
rows = cur.fetchone()[0]
count_time = time.time() - start

print(f'Connection latency: {conn_time*1000:.2f} ms')
print(f'Simple query latency (SELECT 1): {query_time*1000:.2f} ms')
print(f'Count rows latency (market.ohlcv_bars ~{rows:,} rows): {count_time*1000:.2f} ms')

cur.close()
conn.close()
