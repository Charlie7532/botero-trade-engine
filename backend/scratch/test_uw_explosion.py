"""
Test: Verify historical data explosion from mcp_snapshots → ohlcv_bars
Reads existing UW vault blobs and explodes them to ohlcv_bars.
"""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
from dotenv import load_dotenv
load_dotenv(root / ".env")
load_dotenv(root / ".env.local", override=True)

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.daemons.vault_providers.uw_gamma_provider import (
    _explode_gex_to_ohlcv, _explode_skew_to_ohlcv, _explode_si_to_ohlcv,
    _is_market_hours, _is_extended_hours,
)

store = TimescaleDataStore()

print("=" * 80)
print("🧪 TEST: Historical Data Explosion (Rule 14)")
print("=" * 80)

# 1. Market hours check
print(f"\n⏰ Market hours: {_is_market_hours()}")
print(f"⏰ Extended hours: {_is_extended_hours()}")

# 2. GEX Aggregate
print("\n── GEX Aggregate → ohlcv_bars ──")
for ticker in ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]:
    data = store.load_mcp_latest("uw/gex_aggregate", ticker)
    if data:
        n = _explode_gex_to_ohlcv(store, ticker, data)
        print(f"  ✅ UW_GEX_{ticker}: {n} bars exploded")
    else:
        print(f"  ⚠️  {ticker}: no gex_aggregate data in vault")

# 3. Risk Reversal
print("\n── Risk Reversal → ohlcv_bars ──")
for ticker in ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]:
    data = store.load_mcp_latest("uw/risk_reversal", ticker)
    if data:
        n = _explode_skew_to_ohlcv(store, ticker, data)
        print(f"  ✅ UW_SKEW_{ticker}: {n} bars exploded")
    else:
        print(f"  ⚠️  {ticker}: no risk_reversal data in vault")

# 4. Short Interest
print("\n── Short Interest → ohlcv_bars ──")
for ticker in ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]:
    data = store.load_mcp_latest("uw/short_interest", ticker)
    if data:
        n = _explode_si_to_ohlcv(store, ticker, data)
        print(f"  ✅ UW_SI_{ticker}: {n} bars exploded")
    else:
        print(f"  ⚠️  {ticker}: no short_interest data in vault")

# 5. Verify ohlcv_bars
print("\n── Verification: ohlcv_bars indicators ──")
import psycopg2
conn = psycopg2.connect(os.getenv("POSTGRES_URL"))
cur = conn.cursor()
cur.execute("""
    SELECT ticker, COUNT(*) as bars, MIN(time)::date as first, MAX(time)::date as last
    FROM market.ohlcv_bars
    WHERE ticker LIKE 'UW_%%'
    GROUP BY ticker
    ORDER BY ticker
""")
rows = cur.fetchall()
if rows:
    print(f"  {'Ticker':<20} {'Bars':>6}  {'First':<12} {'Last':<12}")
    print("  " + "-" * 55)
    for r in rows:
        print(f"  {r[0]:<20} {r[1]:>6}  {r[2]}  {r[3]}")
else:
    print("  ⚠️  No UW indicators found in ohlcv_bars")

# 6. Verify ticker_metadata
print("\n── Verification: ticker_metadata ──")
cur.execute("""
    SELECT ticker, sector, industry
    FROM market.ticker_metadata
    WHERE ticker LIKE 'UW_%%'
    ORDER BY ticker
""")
meta = cur.fetchall()
if meta:
    for m in meta:
        print(f"  {m[0]:<20} sector={m[1]:<15} industry={m[2]}")
else:
    print("  ⚠️  No UW metadata found")

# 7. Sample data check
print("\n── Sample: UW_GEX_SPY (first 5 + last 5) ──")
cur.execute("""
    SELECT time::date, open, close, volume
    FROM market.ohlcv_bars
    WHERE ticker = 'UW_GEX_SPY' AND timeframe = '1d'
    ORDER BY time
    LIMIT 5
""")
for r in cur.fetchall():
    print(f"  {r[0]}  call_gamma={r[1]:>15.2f}  net_gex={r[2]:>15.2f}")

cur.execute("""
    SELECT time::date, open, close, volume
    FROM market.ohlcv_bars
    WHERE ticker = 'UW_GEX_SPY' AND timeframe = '1d'
    ORDER BY time DESC
    LIMIT 5
""")
print("  ...")
for r in reversed(cur.fetchall()):
    print(f"  {r[0]}  call_gamma={r[1]:>15.2f}  net_gex={r[2]:>15.2f}")

print("\n── Sample: UW_SI_SPY (last 5 reports) ──")
cur.execute("""
    SELECT time::date, open as days_to_cover, close as si_pct, volume as short_shares
    FROM market.ohlcv_bars
    WHERE ticker = 'UW_SI_SPY' AND timeframe = '1d'
    ORDER BY time DESC
    LIMIT 5
""")
for r in cur.fetchall():
    print(f"  {r[0]}  days_to_cover={r[1]:<6}  si_pct={r[2]:.6f}  short_shares={r[3]:>12,}")

conn.close()
store.close()

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
