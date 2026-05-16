"""Vault Anomaly Scanner — Query today's MCP snapshots for anomalies."""
import json, os, sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

import psycopg2
import psycopg2.extras

dsn = os.environ.get("POSTGRES_URL", "")
conn = psycopg2.connect(dsn, connect_timeout=15)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

today = date.today().isoformat()
print(f"=== VAULT ANOMALY SCAN — {today} ===\n")

# 1. All categories captured today
cur.execute("""
    SELECT category, ticker, time::timestamp(0) as captured_at,
           pg_column_size(data) as data_bytes
    FROM market.mcp_snapshots
    WHERE time::date = %s::date
    ORDER BY category, ticker
""", (today,))
rows = cur.fetchall()
print(f"📦 Total snapshots today: {len(rows)}")
cats = {}
for r in rows:
    cats.setdefault(r['category'], []).append(r['ticker'])
for cat, tickers in sorted(cats.items()):
    print(f"  {cat}: {len(tickers)} snapshots ({', '.join(tickers[:5])}{'...' if len(tickers)>5 else ''})")

# 2. VIX Live
print("\n" + "="*60)
print("🔴 VIX LIVE")
cur.execute("""
    SELECT data FROM market.mcp_snapshots
    WHERE category='macro/vix_live' AND ticker='VIX'
    ORDER BY time DESC LIMIT 1
""")
r = cur.fetchone()
if r:
    d = r['data']
    print(f"  VIX: {d.get('vix')} | High: {d.get('high')} | Low: {d.get('low')}")
    print(f"  Delta: {d.get('delta')} ({d.get('delta_pct')}%) | Regime: {d.get('regime')}")
    print(f"  Regime changed: {d.get('regime_changed')} (prev: {d.get('prev_regime')})")

# 3. FRED Macro
print("\n" + "="*60)
print("📊 FRED MACRO (Real)")
cur.execute("""
    SELECT data FROM market.mcp_snapshots
    WHERE category='macro/fred_real' AND ticker='SUMMARY'
    ORDER BY time DESC LIMIT 1
""")
r = cur.fetchone()
if r:
    d = r['data']
    nl = d.get('net_liquidity')
    print(f"  Net Liquidity: {nl:,.0f}B" if nl else "  Net Liquidity: N/A")
    print(f"  NL Trend: {d.get('net_liquidity_trend')} | Regime: {d.get('macro_regime')}")
    print(f"  Score: {d.get('regime_score')} | Fed Stance: {d.get('fed_stance')}")
    print(f"  Fed Funds: {d.get('fed_funds_rate')} | CPI YoY: {d.get('cpi_yoy')}%")
    print(f"  10Y: {d.get('treasury_10y')} | 2Y: {d.get('treasury_2y')} | Spread: {d.get('yield_spread')}")
    print(f"  Unemployment: {d.get('unemployment_rate')} | Sentiment: {d.get('consumer_sentiment')}")
    print(f"  Liquidity Regime: {d.get('liquidity_regime')}")

# 4. Market Indices
print("\n" + "="*60)
print("📈 MARKET INDICES")
cur.execute("""
    SELECT data FROM market.mcp_snapshots
    WHERE category='macro/market_indices' AND ticker='SUMMARY'
    ORDER BY time DESC LIMIT 1
""")
r = cur.fetchone()
if r:
    d = r['data']
    for label in ['VIX','SP500','DXY','GOLD','OIL_WTI','YIELD_10Y','YIELD_3M']:
        v = d.get(label, {})
        if v:
            print(f"  {label}: close={v.get('close')} high={v.get('high')} low={v.get('low')}")

# 5. Fear & Greed
print("\n" + "="*60)
print("😱 FEAR & GREED")
cur.execute("""
    SELECT data FROM market.mcp_snapshots
    WHERE category='macro/fear_greed' AND ticker='MARKET'
    ORDER BY time DESC LIMIT 1
""")
r = cur.fetchone()
if r:
    d = r['data']
    print(f"  Score: {d.get('score')} | Rating: {d.get('rating')}")
    print(f"  Prev close: {d.get('previous_close')} | 1w ago: {d.get('one_week_ago')} | 1m ago: {d.get('one_month_ago')}")

# 6. Breadth
print("\n" + "="*60)
print("📊 BREADTH (SP500)")
cur.execute("""
    SELECT data FROM market.mcp_snapshots
    WHERE category='macro/breadth' AND ticker='SP500'
    ORDER BY time DESC LIMIT 1
""")
r = cur.fetchone()
if r:
    d = r['data']
    print(f"  S5TH (>200DMA): {d.get('s5th'):.1f}%" if d.get('s5th') else "  S5TH: N/A")
    print(f"  S5TW (>20DMA):  {d.get('s5tw'):.1f}%" if d.get('s5tw') else "  S5TW: N/A")
    print(f"  S5FI (>50DMA):  {d.get('s5fi'):.1f}%" if d.get('s5fi') else "  S5FI: N/A")
    print(f"  Tickers counted: {d.get('tickers_counted')}")

# 7. CBOE SKEW + VVIX (latest bars)
print("\n" + "="*60)
print("📉 CBOE SKEW + VVIX (latest bars)")
for ticker in ['SKEW', 'VVIX']:
    cur.execute("""
        SELECT time::date, close FROM market.ohlcv_bars
        WHERE ticker=%s AND timeframe='1d'
        ORDER BY time DESC LIMIT 5
    """, (ticker,))
    rows = cur.fetchall()
    if rows:
        latest = rows[0]
        print(f"  {ticker}: {latest['close']:.2f} (as of {latest['time']})")
        vals = [r['close'] for r in rows]
        print(f"    Last 5 days: {[f'{v:.1f}' for v in vals]}")

# 8. UW Flow — top tickers by alert count
print("\n" + "="*60)
print("🐋 UNUSUAL WHALES FLOW (today)")
cur.execute("""
    SELECT ticker, jsonb_array_length(data) as alert_count
    FROM market.mcp_snapshots
    WHERE category='flow/alerts' AND time::date = %s::date
    AND ticker != 'MARKET'
    ORDER BY jsonb_array_length(data) DESC
    LIMIT 15
""", (today,))
rows = cur.fetchall()
if rows:
    for r in rows:
        print(f"  {r['ticker']}: {r['alert_count']} flow alerts")
else:
    print("  No UW flow data today")

# 9. UW Market Sentiment
print("\n" + "="*60)
print("🐋 UW MARKET SENTIMENT")
cur.execute("""
    SELECT data FROM market.mcp_snapshots
    WHERE category='flow/sentiment' AND ticker='MARKET'
    ORDER BY time DESC LIMIT 1
""")
r = cur.fetchone()
if r:
    d = r['data']
    print(f"  {json.dumps(d, indent=2, default=str)[:800]}")

# 10. UW Market-wide alerts summary
print("\n" + "="*60)
print("🐋 UW MARKET-WIDE FLOW (top premiums)")
cur.execute("""
    SELECT data FROM market.mcp_snapshots
    WHERE category='flow/alerts' AND ticker='MARKET'
    ORDER BY time DESC LIMIT 1
""")
r = cur.fetchone()
if r and isinstance(r['data'], list):
    alerts = r['data']
    print(f"  Total market alerts: {len(alerts)}")
    # Sort by premium (absolute value)
    big = sorted(alerts, key=lambda x: abs(float(x.get('total_premium', x.get('premium', 0)) or 0)), reverse=True)[:10]
    for a in big:
        prem = a.get('total_premium', a.get('premium', 'N/A'))
        print(f"  {a.get('ticker','?'):6s} | {a.get('sentiment','?'):5s} | prem=${prem} | {a.get('option_type','')} {a.get('strike','')} {a.get('expiry','')}")

# 11. Dark Pool activity
print("\n" + "="*60)
print("🌑 DARK POOL (today)")
cur.execute("""
    SELECT ticker, data->0->>'notional_value' as notional
    FROM market.mcp_snapshots
    WHERE category='flow/darkpool' AND time::date = %s::date
    ORDER BY (data->0->>'notional_value')::numeric DESC NULLS LAST
    LIMIT 10
""", (today,))
rows = cur.fetchall()
if rows:
    for r in rows:
        print(f"  {r['ticker']}: notional=${r['notional']}")
else:
    print("  No dark pool data today")

# 12. Guru Picks
print("\n" + "="*60)
print("🎓 GURU PICKS (latest)")
cur.execute("""
    SELECT data FROM market.mcp_snapshots
    WHERE category='sourcing/guru_picks' AND ticker='MARKET'
    ORDER BY time DESC LIMIT 1
""")
r = cur.fetchone()
if r:
    d = r['data']
    picks = d.get('picks', [])
    print(f"  Total picks: {d.get('count', len(picks))}")
    for p in picks[:8]:
        print(f"  {p.get('stock','?'):6s} | {p.get('guru','?')[:30]:30s} | {p.get('action','?')} | {p.get('date','')}")

# 13. Insider Clusters
print("\n" + "="*60)
print("🔍 INSIDER CLUSTERS")
cur.execute("""
    SELECT data FROM market.mcp_snapshots
    WHERE category='sourcing/insider_activity' AND ticker='MARKET'
    ORDER BY time DESC LIMIT 1
""")
r = cur.fetchone()
if r:
    d = r['data']
    clusters = d.get('clusters', [])
    print(f"  Tickers scanned: {d.get('tickers_scanned')} | Clusters: {d.get('cluster_count')}")
    for c in clusters:
        print(f"  🚨 {c.get('ticker')}: {c.get('buyer_count')} unique buyers, {c.get('total_buys')} buys")

# 14. Finnhub Earnings (next 14 days)
print("\n" + "="*60)
print("📅 UPCOMING EARNINGS")
cur.execute("""
    SELECT data FROM market.mcp_snapshots
    WHERE category='finnhub/earnings' AND ticker='MARKET'
    ORDER BY time DESC LIMIT 1
""")
r = cur.fetchone()
if r and isinstance(r['data'], list):
    events = r['data']
    print(f"  Total events: {len(events)}")
    from collections import Counter
    dates = Counter(e.get('date','?') for e in events)
    for d, c in sorted(dates.items())[:7]:
        print(f"  {d}: {c} companies reporting")

# 15. OHLCV freshness
print("\n" + "="*60)
print("📈 OHLCV FRESHNESS")
cur.execute("""
    SELECT COUNT(*), COUNT(DISTINCT ticker), MAX(time)::date as latest
    FROM market.ohlcv_bars WHERE timeframe='1d'
""")
r = cur.fetchone()
print(f"  Total bars: {r['count']:,} | Tickers: {r['count_1']} | Latest: {r['latest']}")

# 16. Alerts table
print("\n" + "="*60)
print("⚡ ALERTS (last 24h)")
try:
    cur.execute("""
        SELECT category, severity, ticker, title, metric_value, created_at::timestamp(0)
        FROM market.alerts
        WHERE created_at >= NOW() - INTERVAL '24 hours'
        ORDER BY created_at DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f"  [{r['severity']}] {r['category']} | {r['ticker']} | {r['title']} | val={r['metric_value']}")
    else:
        print("  No alerts in last 24h")
except Exception as e:
    print(f"  (alerts table not available: {e})")
    conn.rollback()

# 17. Portfolio snapshot
print("\n" + "="*60)
print("💼 PORTFOLIO")
cur.execute("""
    SELECT data FROM market.mcp_snapshots
    WHERE category='portfolio/snapshot' AND ticker='ALPACA'
    ORDER BY time DESC LIMIT 1
""")
r = cur.fetchone()
if r:
    d = r['data']
    print(f"  Cash: ${d.get('cash',0):,.2f} | Total: ${d.get('total_value',0):,.2f}")
    for p in d.get('positions', []):
        print(f"  {p['symbol']:6s} | qty={p['quantity']} | avg=${p['avg_cost']:.2f} | mkt=${p['market_price']:.2f} | pnl=${p['pnl']:.2f}")
else:
    print("  No portfolio snapshot")

# 18. Options chains captured
print("\n" + "="*60)
print("📊 OPTIONS CHAINS (today)")
cur.execute("""
    SELECT ticker, data->>'underlying_price' as price,
           data->>'calls_count' as calls, data->>'puts_count' as puts,
           data->>'expiration' as exp
    FROM market.mcp_snapshots
    WHERE category='yahoo/options' AND time::date = %s::date
    ORDER BY ticker
    LIMIT 20
""", (today,))
rows = cur.fetchall()
if rows:
    for r in rows:
        pc_ratio = int(r['puts'])/int(r['calls']) if int(r['calls'])>0 else 0
        flag = " ⚠️ HIGH P/C" if pc_ratio > 1.2 else ""
        print(f"  {r['ticker']:6s} | price=${r['price']} | C={r['calls']} P={r['puts']} (P/C={pc_ratio:.2f}){flag}")
else:
    print("  No options chains today")

print("\n" + "="*60)
print("=== SCAN COMPLETE ===")

cur.close()
conn.close()
