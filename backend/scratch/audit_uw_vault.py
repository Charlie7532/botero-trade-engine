"""
UW Vault Deep Audit — Verify all 14 categories in the Vault
================================================================
Checks:
  1. Which categories have data and which are empty
  2. Date ranges and freshness per category/ticker
  3. Data schema (sample fields) per category
  4. Row counts and snapshot frequency
  5. Identifies gaps for historical backfill
"""
import json
import os
import sys
from pathlib import Path

# ── Standard project env loading (matches all other scratch scripts) ──
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
from dotenv import load_dotenv
load_dotenv(root / ".env")
load_dotenv(root / ".env.local", override=True)  # .env.local takes precedence

import psycopg2
from datetime import datetime, timedelta

POSTGRES_URL = os.getenv("POSTGRES_URL")
if not POSTGRES_URL:
    print("ERROR: POSTGRES_URL not set — check .env and .env.local")
    sys.exit(1)

conn = psycopg2.connect(POSTGRES_URL)
cur = conn.cursor()

UW_CATEGORIES = [
    "uw/spot_gex", "uw/greeks", "uw/gex_aggregate", "uw/gex_by_expiry",
    "uw/iv_term_structure", "uw/vol_stats", "uw/risk_reversal",
    "uw/max_pain", "uw/oi_per_strike", "uw/nope",
    "uw/sector_tide", "uw/sector_etfs", "uw/top_impact",
    "uw/short_interest",
]

TICKERS = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]

print("=" * 90)
print("🐋 UW VAULT DEEP AUDIT")
print("=" * 90)

# ─── 1. Global inventory: all UW categories ───
print("\n── 1. GLOBAL INVENTORY ──\n")
cur.execute("""
    SELECT category, ticker, COUNT(*) as cnt,
           MIN(time) as first_snapshot,
           MAX(time) as last_snapshot
    FROM market.mcp_snapshots
    WHERE category LIKE 'uw/%%'
    GROUP BY category, ticker
    ORDER BY category, ticker
""")
rows = cur.fetchall()

if not rows:
    print("⚠️  NO UW DATA FOUND IN VAULT")
else:
    print(f"{'Category':<25} {'Ticker':<15} {'Count':>6} {'First Snapshot':<28} {'Last Snapshot':<28}")
    print("-" * 110)
    for row in rows:
        cat, ticker, cnt, first, last = row[0], row[1], row[2], row[3], row[4]
        print(f"{cat:<25} {ticker:<15} {cnt:>6} {str(first):<28} {str(last):<28}")

# ─── 2. Which categories are MISSING ───
print("\n── 2. MISSING CATEGORIES ──\n")
cur.execute("""
    SELECT DISTINCT category FROM market.mcp_snapshots
    WHERE category LIKE 'uw/%%'
""")
existing = {r[0] for r in cur.fetchall()}
missing = [c for c in UW_CATEGORIES if c not in existing]
if missing:
    print(f"❌ Missing categories ({len(missing)}):")
    for c in missing:
        print(f"   - {c}")
else:
    print("✅ All 14 UW categories have data")

# ─── 3. Per-ticker coverage ───
print("\n── 3. PER-TICKER COVERAGE ──\n")
for ticker in TICKERS:
    cur.execute("""
        SELECT category, COUNT(*) as cnt,
               MIN(time)::date as first_date,
               MAX(time)::date as last_date
        FROM market.mcp_snapshots
        WHERE category LIKE 'uw/%%' AND ticker = %s
        GROUP BY category
        ORDER BY category
    """, (ticker,))
    ticker_rows = cur.fetchall()
    if not ticker_rows:
        print(f"  ❌ {ticker}: NO DATA")
        continue
    print(f"  📊 {ticker}: {len(ticker_rows)}/14 categories")
    for row in ticker_rows:
        cat, cnt, first, last = row[0], row[1], row[2], row[3]
        print(f"     {cat:<25} {cnt:>4} snapshots  [{first} → {last}]")

# ─── 4. Sector Tide coverage ───
print("\n── 4. SECTOR TIDE COVERAGE ──\n")
cur.execute("""
    SELECT ticker, COUNT(*) as cnt,
           MIN(time)::date as first_date,
           MAX(time)::date as last_date
    FROM market.mcp_snapshots
    WHERE category = 'uw/sector_tide'
    GROUP BY ticker
    ORDER BY ticker
""")
sector_rows = cur.fetchall()
if sector_rows:
    for row in sector_rows:
        print(f"  {row[0]:<20} {row[1]:>4} snapshots  [{row[2]} → {row[3]}]")
    # Check missing sector: "Financials" vs "Financial"
    sector_tickers = {r[0] for r in sector_rows}
    print(f"\n  Tracked sectors found: {sector_tickers}")
    expected = {"TECHNOLOGY", "FINANCIALS", "HEALTHCARE", "ENERGY", "CONSUMER CYCLICAL"}
    missing_sectors = expected - sector_tickers
    if missing_sectors:
        print(f"  ⚠️  Missing sectors: {missing_sectors}")
else:
    print("  ❌ No sector_tide data")

# ─── 5. Data schema sample per category ───
print("\n── 5. DATA SCHEMA SAMPLES ──\n")
for cat in UW_CATEGORIES:
    cur.execute("""
        SELECT ticker, data, time
        FROM market.mcp_snapshots
        WHERE category = %s
        ORDER BY time DESC LIMIT 1
    """, (cat,))
    row = cur.fetchone()
    if not row:
        print(f"  ❌ {cat}: NO DATA")
        continue

    ticker, data, ts = row[0], row[1], row[2]
    print(f"  📋 {cat} (ticker={ticker}, time={ts})")

    if isinstance(data, list):
        print(f"     Type: LIST, {len(data)} items")
        if len(data) > 0:
            sample = data[0]
            if isinstance(sample, dict):
                keys = list(sample.keys())[:15]
                print(f"     Keys: {keys}")
                # Check for date fields
                date_fields = [k for k in sample.keys() if any(d in k.lower() for d in ['date', 'time', 'expir', 'settlement'])]
                if date_fields:
                    for df in date_fields:
                        print(f"     📅 {df}: {sample[df]} (type: {type(sample[df]).__name__})")
    elif isinstance(data, dict):
        print(f"     Type: DICT, {len(data)} keys")
        keys = list(data.keys())[:15]
        print(f"     Keys: {keys}")
        for k, v in list(data.items())[:6]:
            print(f"     {k}: {str(v)[:60]}")
    print()

# ─── 6. Freshness check ───
print("\n── 6. FRESHNESS CHECK ──\n")
now = datetime.utcnow()
cur.execute("""
    SELECT category, ticker, MAX(time) as latest
    FROM market.mcp_snapshots
    WHERE category LIKE 'uw/%%'
    GROUP BY category, ticker
    ORDER BY latest DESC
    LIMIT 20
""")
fresh_rows = cur.fetchall()
if fresh_rows:
    print(f"{'St':<3} {'Category':<25} {'Ticker':<15} {'Latest':<28} {'Age'}")
    print("-" * 90)
    for row in fresh_rows:
        cat, ticker, latest = row[0], row[1], row[2]
        age = now - latest.replace(tzinfo=None) if latest else timedelta(days=999)
        status = "🟢" if age < timedelta(hours=4) else "🟡" if age < timedelta(days=1) else "🔴"
        print(f"{status} {cat:<23} {ticker:<15} {str(latest):<28} {age}")

# ─── 7. SPOT GEX FIELD AUDIT (critical for adapter) ───
print("\n── 7. SPOT GEX FIELD AUDIT (adapter parsing) ──\n")
cur.execute("""
    SELECT data FROM market.mcp_snapshots
    WHERE category = 'uw/spot_gex' AND ticker = 'SPY'
    ORDER BY time DESC LIMIT 1
""")
row = cur.fetchone()
if row and isinstance(row[0], list) and len(row[0]) > 0:
    sample = row[0][0]
    print(f"  Total fields per strike: {len(sample)}")
    print(f"  ALL field names:")
    for k in sorted(sample.keys()):
        v = sample[k]
        print(f"    {k}: {str(v)[:50]} ({type(v).__name__})")
    
    # Check specific fields the adapter uses
    print("\n  🔍 Adapter field verification (UWGammaAdapter.get_spot_gex):")
    adapter_fields = [
        "call_gamma_oi", "put_gamma_oi",
        "call_charm_oi", "put_charm_oi",
        "call_vanna_oi", "put_vanna_oi",
    ]
    for f in adapter_fields:
        if f in sample:
            print(f"    ✅ {f}: {sample[f]}")
        else:
            print(f"    ❌ {f}: MISSING — adapter returns 0.0!")
else:
    print("  ❌ No spot_gex data found for SPY")

# ─── 8. Vol Stats field audit ───
print("\n── 8. VOL STATS FIELD AUDIT ──\n")
cur.execute("""
    SELECT data FROM market.mcp_snapshots
    WHERE category = 'uw/vol_stats' AND ticker = 'SPY'
    ORDER BY time DESC LIMIT 1
""")
row = cur.fetchone()
if row and isinstance(row[0], dict):
    print(f"  Vol Stats SPY fields:")
    for k, v in sorted(row[0].items()):
        print(f"    {k}: {v} ({type(v).__name__})")
    
    adapter_fields = ["iv", "iv_high", "iv_low", "iv_rank", "rv", "rv_high", "rv_low"]
    print("\n  🔍 Adapter field verification:")
    for f in adapter_fields:
        if f in row[0]:
            print(f"    ✅ {f}: {row[0][f]}")
        else:
            print(f"    ❌ {f}: MISSING")
elif row and isinstance(row[0], list):
    print(f"  ⚠️  vol_stats returned as LIST (expected DICT)")
    print(f"     Items: {len(row[0])}")
    if len(row[0]) > 0:
        print(f"     First item keys: {list(row[0][0].keys()) if isinstance(row[0][0], dict) else type(row[0][0])}")
else:
    print("  ❌ No vol_stats data found for SPY")

# ─── 9. Greeks field audit ───
print("\n── 9. GREEKS FIELD AUDIT (for get_options_chain) ──\n")
cur.execute("""
    SELECT data FROM market.mcp_snapshots
    WHERE category = 'uw/greeks' AND ticker = 'SPY'
    ORDER BY time DESC LIMIT 1
""")
row = cur.fetchone()
if row and isinstance(row[0], list) and len(row[0]) > 0:
    sample = row[0][0]
    print(f"  Total fields per greek entry: {len(sample)}")
    print(f"  ALL field names:")
    for k in sorted(sample.keys()):
        v = sample[k]
        print(f"    {k}: {str(v)[:50]} ({type(v).__name__})")
    
    adapter_fields = [
        "expiry", "strike",
        "call_volatility", "put_volatility",
        "call_delta", "put_delta",
        "call_gamma", "put_gamma",
        "call_theta", "put_theta",
        "call_vega", "put_vega",
        "call_rho", "put_rho",
    ]
    print("\n  🔍 Adapter field verification:")
    for f in adapter_fields:
        if f in sample:
            print(f"    ✅ {f}: {sample[f]}")
        else:
            print(f"    ❌ {f}: MISSING — adapter parsing will fail!")
else:
    print("  ❌ No greeks data found for SPY")

# ─── 10. Short Interest field audit (days_to_cover / float) ───
print("\n── 10. SHORT INTEREST FIELD AUDIT ──\n")
cur.execute("""
    SELECT data FROM market.mcp_snapshots
    WHERE category = 'uw/short_interest' AND ticker = 'SPY'
    ORDER BY time DESC LIMIT 1
""")
row = cur.fetchone()
if row and isinstance(row[0], list) and len(row[0]) > 0:
    sample = row[0][0]
    print(f"  Short Interest SPY fields ({len(sample)} total):")
    for k in sorted(sample.keys()):
        v = sample[k]
        print(f"    {k}: {str(v)[:60]} ({type(v).__name__})")
    # Check date format
    date_fields = [k for k in sample.keys() if 'date' in k.lower()]
    if date_fields:
        print(f"\n  📅 Date fields and formats:")
        for df in date_fields:
            print(f"    {df}: {sample[df]}")
else:
    print("  ❌ No short_interest data found for SPY")

# ─── 11. GEX Aggregate — internal date analysis ───
print("\n── 11. GEX AGGREGATE — INTERNAL HISTORY ANALYSIS ──\n")
cur.execute("""
    SELECT data FROM market.mcp_snapshots
    WHERE category = 'uw/gex_aggregate' AND ticker = 'SPY'
    ORDER BY time DESC LIMIT 1
""")
row = cur.fetchone()
if row and isinstance(row[0], list) and len(row[0]) > 0:
    items = row[0]
    print(f"  Total items: {len(items)}")
    sample = items[0]
    print(f"  First item keys: {list(sample.keys())}")
    # Find date key
    date_key = None
    for k in ['date', 'settlement_date', 'time', 'reported_date']:
        if k in sample:
            date_key = k
            break
    if date_key:
        dates = sorted([x.get(date_key) for x in items if x.get(date_key)])
        print(f"  Date key: '{date_key}'")
        print(f"  Date range: {dates[0]} → {dates[-1]} ({len(dates)} records)")
        print(f"  Date format example: {dates[0]} (type: {type(items[0][date_key]).__name__})")
    else:
        print(f"  ⚠️  No recognizable date key found. Available keys:")
        for k, v in sample.items():
            print(f"    {k}: {str(v)[:50]}")
else:
    print("  ❌ No gex_aggregate data found for SPY")

# ─── 12. Risk Reversal — internal date analysis ───
print("\n── 12. RISK REVERSAL — INTERNAL HISTORY ANALYSIS ──\n")
cur.execute("""
    SELECT data FROM market.mcp_snapshots
    WHERE category = 'uw/risk_reversal' AND ticker = 'SPY'
    ORDER BY time DESC LIMIT 1
""")
row = cur.fetchone()
if row and isinstance(row[0], list) and len(row[0]) > 0:
    items = row[0]
    print(f"  Total items: {len(items)}")
    sample = items[0]
    print(f"  First item keys: {list(sample.keys())}")
    date_key = None
    for k in ['date', 'settlement_date', 'time']:
        if k in sample:
            date_key = k
            break
    if date_key:
        dates = sorted([x.get(date_key) for x in items if x.get(date_key)])
        print(f"  Date key: '{date_key}'")
        print(f"  Date range: {dates[0]} → {dates[-1]} ({len(dates)} records)")
    else:
        print(f"  ⚠️  No date key found. Sample item:")
        for k, v in sample.items():
            print(f"    {k}: {str(v)[:50]}")
else:
    print("  ❌ No risk_reversal data found for SPY")

# ─── 13. IV Term Structure — date format check ───
print("\n── 13. IV TERM STRUCTURE — DATE FORMAT CHECK ──\n")
cur.execute("""
    SELECT data FROM market.mcp_snapshots
    WHERE category = 'uw/iv_term_structure' AND ticker = 'SPY'
    ORDER BY time DESC LIMIT 1
""")
row = cur.fetchone()
if row and isinstance(row[0], list) and len(row[0]) > 0:
    items = row[0]
    print(f"  Total expiries: {len(items)}")
    sample = items[0]
    print(f"  Sample item:")
    for k, v in sample.items():
        print(f"    {k}: {v} ({type(v).__name__})")
    # Check DTE=0 items (0DTE concern)
    dte0 = [x for x in items if str(x.get('dte', '')) == '0']
    print(f"\n  0DTE entries: {len(dte0)}")
    if dte0:
        print(f"  0DTE sample: {dte0[0]}")
else:
    print("  ❌ No iv_term_structure data found for SPY")

# ─── 14. Existing non-UW flow data ───
print("\n── 14. EXISTING FLOW VAULT DATA (pre-Phase 1) ──\n")
cur.execute("""
    SELECT category, COUNT(*) as cnt,
           MIN(time)::date as first,
           MAX(time)::date as last
    FROM market.mcp_snapshots
    WHERE category NOT LIKE 'uw/%%'
    GROUP BY category
    ORDER BY category
""")
flow_rows = cur.fetchall()
if flow_rows:
    for row in flow_rows:
        print(f"  {row[0]:<30} {row[1]:>6} snapshots  [{row[2]} → {row[3]}]")
else:
    print("  No pre-existing non-UW vault data found")

# ─── 15. Total vault size ───
print("\n── 15. TOTAL VAULT SIZE ──\n")
cur.execute("SELECT COUNT(*) FROM market.mcp_snapshots")
total = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM market.mcp_snapshots WHERE category LIKE 'uw/%%'")
uw_total = cur.fetchone()[0]
print(f"  Total mcp_snapshots rows: {total}")
print(f"  UW-specific rows: {uw_total}")
print(f"  Non-UW rows: {total - uw_total}")

cur.close()
conn.close()
print("\n" + "=" * 90)
print("AUDIT COMPLETE")
print("=" * 90)
