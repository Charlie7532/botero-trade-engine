"""
UW FULL API AUDIT — Comprehensive endpoint exploration
========================================================
Tests every major endpoint category on the monthly plan.
Documents response structure, data quality, and integration value.
"""
import os
import sys
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from dotenv import load_dotenv
load_dotenv()

import requests

UW_BASE = "https://api.unusualwhales.com"
API_KEY = os.getenv("UW_API_KEY", "")
HEADERS = {
    "Accept": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}

TICKER = "SPY"
STOCK = "AAPL"
RESULTS = {}
CALL_COUNT = 0


def uw_get(endpoint: str, params: dict = None, label: str = "") -> dict | list | None:
    """Make a request, track rate limits, return data."""
    global CALL_COUNT
    url = f"{UW_BASE}{endpoint}"
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
        CALL_COUNT += 1

        # Extract rate limit headers
        daily_limit = resp.headers.get("x-uw-token-req-limit", "?")
        daily_used = resp.headers.get("x-uw-daily-req-count", "?")
        minute_rem = resp.headers.get("x-uw-req-per-minute-remaining", "?")

        status = resp.status_code
        if status == 200:
            data = resp.json()
            payload = data.get("data", data) if isinstance(data, dict) else data
            return payload
        elif status == 403:
            print(f"  ⛔ 403 FORBIDDEN — endpoint not in plan")
            return None
        elif status == 429:
            print(f"  ⏳ 429 RATE LIMITED — waiting 5s")
            time.sleep(5)
            return None
        else:
            print(f"  ❌ HTTP {status}: {resp.text[:120]}")
            return None
    except Exception as e:
        print(f"  💥 Error: {e}")
        return None


def describe(data, max_items=2):
    """Describe data shape and sample keys."""
    if data is None:
        return "None"
    if isinstance(data, list):
        n = len(data)
        if n == 0:
            return "[] (empty)"
        sample = data[0]
        keys = list(sample.keys()) if isinstance(sample, dict) else ["scalar"]
        return f"[{n} items] keys: {keys}"
    if isinstance(data, dict):
        keys = list(data.keys())
        return f"dict keys: {keys}"
    return str(type(data))


def sample_record(data, n=1):
    """Return first n records for inspection."""
    if isinstance(data, list) and len(data) > 0:
        return data[:n]
    if isinstance(data, dict):
        # Return a subset of keys
        return {k: v for i, (k, v) in enumerate(data.items()) if i < 5}
    return data


def test_section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def test_endpoint(label, endpoint, params=None, ticker_sub=None):
    if ticker_sub:
        endpoint = endpoint.replace("{ticker}", ticker_sub)
    print(f"\n  📡 {label}")
    print(f"     {endpoint}")
    data = uw_get(endpoint, params, label)
    status = "✅" if data is not None and data != [] else "❌"
    shape = describe(data)
    print(f"     {status} Shape: {shape}")
    if data and isinstance(data, list) and len(data) > 0:
        rec = data[0]
        if isinstance(rec, dict):
            # Print first record compactly
            compact = {k: (str(v)[:60] if isinstance(v, str) and len(str(v)) > 60 else v)
                       for k, v in list(rec.items())[:12]}
            print(f"     Sample: {json.dumps(compact, indent=6, default=str)[:500]}")
    elif data and isinstance(data, dict):
        compact = {k: (str(v)[:60] if isinstance(v, str) and len(str(v)) > 60 else v)
                   for k, v in list(data.items())[:8]}
        print(f"     Sample: {json.dumps(compact, indent=6, default=str)[:500]}")

    RESULTS[label] = {"endpoint": endpoint, "status": status, "shape": shape}
    time.sleep(0.6)  # Respect rate limits
    return data


# ═══════════════════════════════════════════════════════════════
# START AUDIT
# ═══════════════════════════════════════════════════════════════

print("🐋 UNUSUAL WHALES — FULL API AUDIT")
print(f"   Timestamp: {datetime.now().isoformat()}")
print(f"   Test tickers: {TICKER} (ETF), {STOCK} (stock)")

# ── CHECK API USAGE FIRST ──
print("\n── API Usage Check ──")
resp = requests.get(f"{UW_BASE}/api/news/headlines", headers=HEADERS, timeout=10)
if resp.ok:
    dl = resp.headers.get("x-uw-token-req-limit", "?")
    du = resp.headers.get("x-uw-daily-req-count", "?")
    mr = resp.headers.get("x-uw-req-per-minute-remaining", "?")
    print(f"   Daily limit: {dl}")
    print(f"   Daily used:  {du}")
    print(f"   Minute remaining: {mr}")
else:
    print(f"   ⚠️ Status {resp.status_code}")

# ══════════════════════════════════════════════════════════════
# 1. TECHNICAL INDICATORS
# ══════════════════════════════════════════════════════════════
test_section("1. TECHNICAL INDICATORS")

INDICATORS = ["RSI", "SMA", "EMA", "MACD", "BBANDS", "STOCH", "VWAP", "ADX", "CCI", "WILLR", "ATR", "OBV", "MFI", "AD", "AROON"]

for ind in INDICATORS:
    params = {"interval": "daily", "time_period": 14, "series_type": "close"}
    test_endpoint(
        f"Technical: {ind}",
        f"/api/stock/{TICKER}/technical-indicator/{ind}",
        params=params
    )

# ══════════════════════════════════════════════════════════════
# 2. GEX / GREEKS
# ══════════════════════════════════════════════════════════════
test_section("2. GEX / GREEKS (THE BIG UNLOCK)")

test_endpoint("Greek Exposure (aggregate)", "/api/stock/{ticker}/greek-exposure", ticker_sub=TICKER)
test_endpoint("GEX by Strike", "/api/stock/{ticker}/greek-exposure/strike", ticker_sub=TICKER)
test_endpoint("GEX by Expiry", "/api/stock/{ticker}/greek-exposure/expiry", ticker_sub=TICKER)
test_endpoint("GEX by Strike+Expiry", "/api/stock/{ticker}/greek-exposure/strike-expiry", ticker_sub=TICKER)
test_endpoint("Greek Flow", "/api/stock/{ticker}/greek-flow", ticker_sub=TICKER)
test_endpoint("Spot GEX (1min)", "/api/stock/{ticker}/spot-exposures", ticker_sub=TICKER)
test_endpoint("Spot GEX by Strike", "/api/stock/{ticker}/spot-exposures/strike", ticker_sub=TICKER)
test_endpoint("Spot GEX Strike+Expiry", "/api/stock/{ticker}/spot-exposures/expiry-strike", ticker_sub=TICKER)
test_endpoint("Per-strike Greeks", "/api/stock/{ticker}/greeks", ticker_sub=TICKER)

# ══════════════════════════════════════════════════════════════
# 3. VOLATILITY & IV
# ══════════════════════════════════════════════════════════════
test_section("3. VOLATILITY & IV")

test_endpoint("IV Term Structure", "/api/stock/{ticker}/volatility/term-structure", ticker_sub=TICKER)
test_endpoint("Realized Volatility", "/api/stock/{ticker}/volatility/realized", ticker_sub=TICKER)
test_endpoint("Volatility Stats", "/api/stock/{ticker}/volatility/stats", ticker_sub=TICKER)
test_endpoint("Interpolated IV", "/api/stock/{ticker}/interpolated-iv", ticker_sub=TICKER)
test_endpoint("IV Rank", "/api/stock/{ticker}/iv-rank", ticker_sub=TICKER)
test_endpoint("Historical Risk Reversal Skew", "/api/stock/{ticker}/historical-risk-reversal-skew", ticker_sub=TICKER)

# ══════════════════════════════════════════════════════════════
# 4. OPTIONS DATA
# ══════════════════════════════════════════════════════════════
test_section("4. OPTIONS DATA")

test_endpoint("Option Contracts", "/api/stock/{ticker}/option-contracts", ticker_sub=STOCK)
test_endpoint("Option Chains", "/api/stock/{ticker}/option-chains", ticker_sub=STOCK)
test_endpoint("Max Pain", "/api/stock/{ticker}/max-pain", ticker_sub=TICKER)
test_endpoint("NOPE", "/api/stock/{ticker}/nope", ticker_sub=TICKER)
test_endpoint("ATM Chains", "/api/stock/{ticker}/atm-chains", ticker_sub=TICKER)
test_endpoint("Flow per Expiry", "/api/stock/{ticker}/flow-per-expiry", ticker_sub=TICKER)
test_endpoint("Flow per Strike", "/api/stock/{ticker}/flow-per-strike", ticker_sub=TICKER)
test_endpoint("Flow per Strike Intraday", "/api/stock/{ticker}/flow-per-strike-intraday", ticker_sub=TICKER)
test_endpoint("Expiry Breakdown", "/api/stock/{ticker}/expiry-breakdown", ticker_sub=TICKER)
test_endpoint("OI per Expiry", "/api/stock/{ticker}/oi-per-expiry", ticker_sub=TICKER)
test_endpoint("OI per Strike", "/api/stock/{ticker}/oi-per-strike", ticker_sub=TICKER)
test_endpoint("OI Change (ticker)", "/api/stock/{ticker}/oi-change", ticker_sub=TICKER)
test_endpoint("Options Volume", "/api/stock/{ticker}/options-volume", ticker_sub=TICKER)
test_endpoint("Vol & OI per Expiry", "/api/stock/{ticker}/option/volume-oi-expiry", ticker_sub=TICKER)
test_endpoint("Option Price Levels", "/api/stock/{ticker}/option/stock-price-levels", ticker_sub=TICKER)
test_endpoint("Stock Vol Price Levels", "/api/stock/{ticker}/stock-volume-price-levels", ticker_sub=TICKER)

# ══════════════════════════════════════════════════════════════
# 5. FLOW & DARK POOL
# ══════════════════════════════════════════════════════════════
test_section("5. FLOW & DARK POOL")

test_endpoint("Flow Alerts (market)", "/api/option-trades/flow-alerts", params={"limit": 5})
test_endpoint("Flow Recent (ticker)", "/api/stock/{ticker}/flow-recent", ticker_sub=TICKER)
test_endpoint("Flow Alerts (ticker)", "/api/stock/{ticker}/flow-alerts", ticker_sub=TICKER)
test_endpoint("Net Prem Ticks", "/api/stock/{ticker}/net-prem-ticks", ticker_sub=TICKER)
test_endpoint("Full Tape", "/api/option-trades/full-tape/2026-05-28")
test_endpoint("Dark Pool Recent", "/api/darkpool/recent")
test_endpoint("Dark Pool (ticker)", "/api/darkpool/{ticker}", ticker_sub=TICKER)
test_endpoint("Lit Flow Recent", "/api/lit-flow/recent")
test_endpoint("Lit Flow (ticker)", "/api/lit-flow/{ticker}", ticker_sub=TICKER)

# ══════════════════════════════════════════════════════════════
# 6. MARKET INTELLIGENCE
# ══════════════════════════════════════════════════════════════
test_section("6. MARKET INTELLIGENCE")

test_endpoint("Market Tide", "/api/market/market-tide")
test_endpoint("OI Change (market)", "/api/market/oi-change")
test_endpoint("Top Movers", "/api/market/movers")
test_endpoint("Sector ETFs", "/api/market/sector-etfs")
test_endpoint("Total Options Volume", "/api/market/total-options-volume")
test_endpoint("Top Net Impact", "/api/market/top-net-impact")
test_endpoint("Correlations", "/api/market/correlations")
test_endpoint("Insider Buy/Sells (mkt)", "/api/market/insider-buy-sells")
test_endpoint("Economic Calendar", "/api/market/economic-calendar")
test_endpoint("FDA Calendar", "/api/market/fda-calendar")
test_endpoint("Sector Tide (Tech)", "/api/market/Technology/sector-tide")
test_endpoint("ETF Tide (SPY)", "/api/market/{ticker}/etf-tide", ticker_sub=TICKER)
test_endpoint("Net Flow Expiry", "/api/net-flow/expiry")

# ══════════════════════════════════════════════════════════════
# 7. SHORTS
# ══════════════════════════════════════════════════════════════
test_section("7. SHORTS")

test_endpoint("Short Data", "/api/shorts/{ticker}/data", ticker_sub=STOCK)
test_endpoint("Short Interest Float v2", "/api/shorts/{ticker}/interest-float/v2", ticker_sub=STOCK)
test_endpoint("Short Volume & Ratio", "/api/shorts/{ticker}/volume-and-ratio", ticker_sub=STOCK)
test_endpoint("Short FTDs", "/api/shorts/{ticker}/ftds", ticker_sub=STOCK)
test_endpoint("Short Vol by Exchange", "/api/shorts/{ticker}/volumes-by-exchange", ticker_sub=STOCK)
test_endpoint("Short Screener", "/api/short_screener")

# ══════════════════════════════════════════════════════════════
# 8. FUNDAMENTALS & COMPANY
# ══════════════════════════════════════════════════════════════
test_section("8. FUNDAMENTALS & COMPANY")

test_endpoint("Full Financials", "/api/stock/{ticker}/financials", ticker_sub=STOCK)
test_endpoint("Income Statements", "/api/stock/{ticker}/income-statements", ticker_sub=STOCK)
test_endpoint("Balance Sheets", "/api/stock/{ticker}/balance-sheets", ticker_sub=STOCK)
test_endpoint("Cash Flows", "/api/stock/{ticker}/cash-flows", ticker_sub=STOCK)
test_endpoint("Earnings History", "/api/stock/{ticker}/earnings", ticker_sub=STOCK)
test_endpoint("Fundamental Breakdown", "/api/stock/{ticker}/fundamental-breakdown", ticker_sub=STOCK)
test_endpoint("Stock Info", "/api/stock/{ticker}/info", ticker_sub=STOCK)
test_endpoint("Ownership", "/api/stock/{ticker}/ownership", ticker_sub=STOCK)
test_endpoint("Stock State", "/api/stock/{ticker}/stock-state", ticker_sub=STOCK)
test_endpoint("Company Profile", "/api/companies/{ticker}/profile", ticker_sub=STOCK)
test_endpoint("Earnings Estimates", "/api/companies/{ticker}/earnings-estimates", ticker_sub=STOCK)
test_endpoint("Dividends", "/api/companies/{ticker}/dividends", ticker_sub=STOCK)
test_endpoint("Splits", "/api/companies/{ticker}/splits", ticker_sub=STOCK)

# ══════════════════════════════════════════════════════════════
# 9. INSIDERS & INSTITUTIONS
# ══════════════════════════════════════════════════════════════
test_section("9. INSIDERS & INSTITUTIONS")

test_endpoint("Insider Transactions (mkt)", "/api/insider/transactions")
test_endpoint("Insiders (ticker)", "/api/insider/{ticker}", ticker_sub=STOCK)
test_endpoint("Insider Ticker Flow", "/api/insider/{ticker}/ticker-flow", ticker_sub=STOCK)
test_endpoint("Insider Sector Flow", "/api/insider/Technology/sector-flow")
test_endpoint("Institutions List", "/api/institutions")
test_endpoint("Latest 13F Filings", "/api/institutions/latest_filings")
test_endpoint("Inst. Ownership (ticker)", "/api/institution/{ticker}/ownership", ticker_sub=STOCK)

# ══════════════════════════════════════════════════════════════
# 10. CONGRESS & POLITICIANS
# ══════════════════════════════════════════════════════════════
test_section("10. CONGRESS & POLITICIANS")

test_endpoint("Congress Recent Trades", "/api/congress/recent-trades")
test_endpoint("Congress Unusual Trades", "/api/congress/unusual-trades")
test_endpoint("Congress Late Reports", "/api/congress/late-reports")
test_endpoint("Politicians List", "/api/congress/politicians")

# ══════════════════════════════════════════════════════════════
# 11. SEASONALITY
# ══════════════════════════════════════════════════════════════
test_section("11. SEASONALITY")

test_endpoint("Market Seasonality", "/api/seasonality/market")
test_endpoint("June Performers", "/api/seasonality/6/performers")
test_endpoint("Monthly Returns (SPY)", "/api/seasonality/{ticker}/monthly", ticker_sub=TICKER)
test_endpoint("Year-Month (SPY)", "/api/seasonality/{ticker}/year-month", ticker_sub=TICKER)

# ══════════════════════════════════════════════════════════════
# 12. SCREENER & ANALYTICS
# ══════════════════════════════════════════════════════════════
test_section("12. SCREENER & ANALYTICS")

test_endpoint("Stock Screener", "/api/screener/stocks", params={"limit": 5})
test_endpoint("Option Contract Screener", "/api/screener/option-contracts", params={"limit": 5})
test_endpoint("Analyst Ratings", "/api/screener/analysts", params={"limit": 5})
test_endpoint("Sliding Analytics", "/api/analytics/sliding")
test_endpoint("Fixed Analytics", "/api/analytics/window")
test_endpoint("IPO Calendar", "/api/calendar/ipo")
test_endpoint("Active Listings", "/api/companies/listings", params={"limit": 5})

# ══════════════════════════════════════════════════════════════
# 13. EARNINGS CALENDAR
# ══════════════════════════════════════════════════════════════
test_section("13. EARNINGS CALENDAR")

test_endpoint("Earnings Premarket", "/api/earnings/premarket")
test_endpoint("Earnings Afterhours", "/api/earnings/afterhours")
test_endpoint("Earnings (ticker)", "/api/earnings/{ticker}", ticker_sub=STOCK)

# ══════════════════════════════════════════════════════════════
# 14. ETFs
# ══════════════════════════════════════════════════════════════
test_section("14. ETFs")

test_endpoint("ETF Holdings", "/api/etfs/{ticker}/holdings", ticker_sub=TICKER)
test_endpoint("ETF Exposure", "/api/etfs/{ticker}/exposure", ticker_sub=TICKER)
test_endpoint("ETF In/Outflow", "/api/etfs/{ticker}/in-outflow", ticker_sub=TICKER)
test_endpoint("ETF Info", "/api/etfs/{ticker}/info", ticker_sub=TICKER)
test_endpoint("ETF Weights", "/api/etfs/{ticker}/weights", ticker_sub=TICKER)

# ══════════════════════════════════════════════════════════════
# 15. ECONOMY / MACRO
# ══════════════════════════════════════════════════════════════
test_section("15. ECONOMY / MACRO")

ECON_INDICATORS = ["GDP", "CPI", "INFLATION", "UNEMPLOYMENT", "RETAIL_SALES", "FEDERAL_FUNDS_RATE", "TREASURY_YIELD"]
for ind in ECON_INDICATORS:
    test_endpoint(f"Economy: {ind}", f"/api/economy/{ind}")

# ══════════════════════════════════════════════════════════════
# 16. COMMODITIES
# ══════════════════════════════════════════════════════════════
test_section("16. COMMODITIES")

for c in ["WTI", "BRENT", "NATURAL_GAS", "COPPER", "ALUMINUM", "WHEAT", "CORN", "COTTON", "SUGAR", "COFFEE"]:
    test_endpoint(f"Commodity: {c}", f"/api/commodities/{c}")

# ══════════════════════════════════════════════════════════════
# 17. FOREX
# ══════════════════════════════════════════════════════════════
test_section("17. FOREX")

test_endpoint("FX Spot Rate", "/api/forex/rate", params={"from_currency": "EUR", "to_currency": "USD"})
test_endpoint("FX Intraday", "/api/forex/intraday", params={"from_currency": "EUR", "to_currency": "USD"})
test_endpoint("FX History", "/api/forex/history", params={"from_currency": "EUR", "to_currency": "USD"})

# ══════════════════════════════════════════════════════════════
# 18. OTHER: NEWS, ALERTS, WEBSOCKET, PREDICTIONS
# ══════════════════════════════════════════════════════════════
test_section("18. NEWS, ALERTS, PREDICTIONS & MISC")

test_endpoint("News Headlines", "/api/news/headlines")
test_endpoint("Alerts", "/api/alerts")
test_endpoint("Alert Configs", "/api/alerts/configuration")
test_endpoint("WebSocket Channels", "/api/socket")
test_endpoint("Predictions Unusual", "/api/predictions/unusual")
test_endpoint("Predictions Smart Money", "/api/predictions/smart-money")
test_endpoint("Predictions Whales", "/api/predictions/whales")
test_endpoint("Ticker Exchanges", "/api/stock-directory/ticker-exchanges")
test_endpoint("Tickers in Sector", "/api/stock/Technology/tickers")

# ══════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ══════════════════════════════════════════════════════════════

print(f"\n{'='*70}")
print(f"  FINAL SUMMARY")
print(f"{'='*70}")

ok = sum(1 for r in RESULTS.values() if r["status"] == "✅")
fail = sum(1 for r in RESULTS.values() if r["status"] == "❌")
total = len(RESULTS)

print(f"\n  Total endpoints tested: {total}")
print(f"  ✅ Working: {ok}")
print(f"  ❌ Failed/Empty: {fail}")
print(f"  API calls made: {CALL_COUNT}")

# Final usage check
resp2 = requests.get(f"{UW_BASE}/api/news/headlines", headers=HEADERS, timeout=10)
if resp2.ok:
    dl = resp2.headers.get("x-uw-token-req-limit", "?")
    du = resp2.headers.get("x-uw-daily-req-count", "?")
    print(f"  Daily usage after audit: {du} / {dl}")

print(f"\n  ── FAILED ENDPOINTS ──")
for label, r in RESULTS.items():
    if r["status"] == "❌":
        print(f"     {label}: {r['endpoint']}")

print(f"\n  ── WORKING ENDPOINTS (by category) ──")
for label, r in RESULTS.items():
    if r["status"] == "✅":
        print(f"     ✅ {label}: {r['shape'][:80]}")
