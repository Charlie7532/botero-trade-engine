"""
Data Vault Daemon — Automated MCP Snapshot Accumulation
=========================================================
Runs on a loop, capturing ALL MCP data sources into
Neon PostgreSQL (market.mcp_snapshots):

  - Unusual Whales: flow alerts, SPY, tide, dark pool, sentiment
  - Yahoo Finance: options chains, VIX
  - Finnhub: earnings calendar, company news
  - FRED (via yfinance): macro VIX live
  - Alpaca: portfolio snapshots (position reconciliation)
  - GuruFocus: fundamental screening (daily, from cache)

Strategy: capture EVERYTHING — no hardcoded watchlists.
The market tells us what to capture.

Usage:
    pnpm dev:vault      # loop every 5 min
    pnpm vault:once     # one-shot
    docker compose up vault
"""
import argparse
import logging
import math
import sys
import time
from dataclasses import asdict
from datetime import datetime, date, UTC
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.simulation.infrastructure.vault_interceptor import VaultInterceptor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger("DataVaultDaemon")


def _sanitize_for_json(obj):
    """Recursively replace NaN/Inf with None so PostgreSQL JSONB accepts it."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def _already_vaulted_today(store: TimescaleDataStore, category: str, ticker: str) -> bool:
    """Check if we already have a snapshot for this category/ticker today."""
    today_str = date.today().isoformat()
    existing = store.load_mcp_snapshot(category, ticker, today_str)
    return existing is not None


# ═══════════════════════════════════════════════════════════════
# 1. UNUSUAL WHALES — Flow, SPY, Tide, Dark Pool, Sentiment
# ═══════════════════════════════════════════════════════════════

def vault_uw_data(interceptor: VaultInterceptor) -> dict:
    """Fetch and vault ALL Unusual Whales data (market-driven, no watchlist)."""
    try:
        from backend.modules.flow_intelligence.infrastructure.uw_mcp_bridge import UWDataBridge
        from backend.modules.flow_intelligence.infrastructure.uw_adapter import UnusualWhalesIntelligence

        bridge = UWDataBridge()
        if not bridge.is_configured():
            logger.warning("UW_API_KEY not configured — skipping UW vault")
            return {"status": "skipped", "reason": "no_api_key"}

        uw = UnusualWhalesIntelligence()
        stats = {"spy_ticks": 0, "tide": 0, "sentiment": False, "tickers_captured": 0}

        # 1. SPY flow (macro gate)
        spy_ticks = bridge.fetch_spy_flow()
        interceptor.intercept_spy_flow(spy_ticks)
        stats["spy_ticks"] = len(spy_ticks)

        # 2. Market tide
        tide = bridge.fetch_market_tide()
        interceptor.intercept_market_tide(tide)
        stats["tide"] = len(tide)

        # 3. Market-wide flow alerts
        all_alerts = bridge.fetch_flow_alerts(limit=500)

        # 3a. Vault market sentiment
        sentiment = uw.parse_market_sentiment(all_alerts)
        interceptor.intercept_sentiment(asdict(sentiment))
        stats["sentiment"] = True

        # 3b. Vault raw market-wide alerts
        interceptor.store.save_mcp_snapshot("flow/alerts", "MARKET", all_alerts)

        # 4. Extract unique tickers from the flow
        index_tickers = {"SPY", "QQQ", "IWM", "SPX", "SPXW", "NDX", "RUT", "VIX", "DIA"}
        active_tickers = set()
        for alert in all_alerts:
            ticker = alert.get("ticker")
            if ticker and ticker not in index_tickers:
                active_tickers.add(ticker)

        logger.info(f"🐋 {len(active_tickers)} unique tickers detected in flow")

        # 5. Per-ticker flow alerts + dark pool
        for ticker in sorted(active_tickers):
            try:
                ticker_alerts = bridge.fetch_flow_alerts(ticker=ticker, limit=100)
                interceptor.intercept_flow_alerts(ticker, ticker_alerts)
                dp = bridge.fetch_darkpool_trades(ticker)
                if dp:
                    interceptor.intercept_darkpool(ticker, dp)
                stats["tickers_captured"] += 1
            except Exception as e:
                logger.debug(f"  {ticker} vault failed: {e}")

        logger.info(
            f"🐋 UW vault complete: SPY={stats['spy_ticks']} ticks, "
            f"tide={stats['tide']} pts, "
            f"{stats['tickers_captured']}/{len(active_tickers)} tickers captured"
        )
        return {"status": "ok", **stats}

    except Exception as e:
        logger.error(f"UW vault failed: {e}")
        return {"status": "error", "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# 2. YAHOO FINANCE — Options Chains + VIX
# ═══════════════════════════════════════════════════════════════

def vault_yahoo_data(interceptor: VaultInterceptor, tickers: list[str]) -> dict:
    """Fetch and vault Yahoo Finance options chain snapshots."""
    stats = {"chains": 0, "vix": False}

    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        logger.warning("yfinance not installed — skipping Yahoo vault")
        return {"status": "skipped", "reason": "no_yfinance"}

    try:
        # 1. VIX snapshot
        vix = yf.Ticker("^VIX")
        vix_hist = vix.history(period="1d")
        if not vix_hist.empty:
            if isinstance(vix_hist.columns, pd.MultiIndex):
                vix_hist.columns = vix_hist.columns.get_level_values(0)
            vix_close = float(vix_hist["Close"].iloc[-1])
            interceptor.store.save_mcp_snapshot("yahoo/vix", "VIX", {
                "close": vix_close,
                "timestamp": datetime.now(UTC).isoformat(),
            })
            stats["vix"] = True
            logger.info(f"📊 VIX snapshot: {vix_close:.2f}")

        # 2. Options chains per ticker
        for ticker in tickers:
            try:
                t = yf.Ticker(ticker)
                exps = t.options
                if not exps:
                    continue
                exp = exps[0]
                chain = t.option_chain(exp)
                chain_data = {
                    "expiration": exp,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "calls_count": len(chain.calls),
                    "puts_count": len(chain.puts),
                    "calls": _sanitize_for_json(chain.calls.to_dict(orient="records")),
                    "puts": _sanitize_for_json(chain.puts.to_dict(orient="records")),
                }
                hist = t.history(period="1d")
                if not hist.empty:
                    if isinstance(hist.columns, pd.MultiIndex):
                        hist.columns = hist.columns.get_level_values(0)
                    chain_data["underlying_price"] = float(hist["Close"].iloc[-1])
                interceptor.store.save_mcp_snapshot("yahoo/options", ticker, chain_data)
                stats["chains"] += 1
            except Exception as e:
                logger.debug(f"  {ticker} options chain failed: {e}")

        logger.info(
            f"📊 Yahoo vault complete: VIX={'✓' if stats['vix'] else '✗'}, "
            f"{stats['chains']}/{len(tickers)} chains captured"
        )
        return {"status": "ok", **stats}
    except Exception as e:
        logger.error(f"Yahoo vault failed: {e}")
        return {"status": "error", "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# 3. FINNHUB — Earnings Calendar + Company News
# ═══════════════════════════════════════════════════════════════

def vault_finnhub_data(store: TimescaleDataStore, tickers: list[str]) -> dict:
    """Vault Finnhub earnings calendar and news."""
    stats = {"earnings": False, "news": 0}

    try:
        from backend.modules.flow_intelligence.infrastructure.finnhub_api import FinnhubIntelligence
        fh = FinnhubIntelligence()
        if not fh._available:
            logger.warning("Finnhub not available — skipping")
            return {"status": "skipped", "reason": "no_api_key"}

        # 1. Earnings calendar (market-wide, 1x per day)
        if not _already_vaulted_today(store, "finnhub/earnings", "MARKET"):
            from datetime import timedelta
            today = datetime.now()
            earnings = fh._client.earnings_calendar(
                _from=today.strftime("%Y-%m-%d"),
                to=(today + timedelta(days=14)).strftime("%Y-%m-%d"),
                symbol="",
            )
            events = earnings.get("earningsCalendar", [])
            store.save_mcp_snapshot("finnhub/earnings", "MARKET", events)
            stats["earnings"] = True
            logger.info(f"📅 Finnhub earnings: {len(events)} events (next 14 days)")

        # 2. News for active tickers (cap at 30 to respect rate limits)
        news_tickers = tickers[:30]
        for ticker in news_tickers:
            try:
                news = fh.get_recent_news(ticker, days_back=1, max_headlines=10)
                if news:
                    store.save_mcp_snapshot("finnhub/news", ticker, news)
                    stats["news"] += 1
            except Exception as e:
                logger.debug(f"  {ticker} news failed: {e}")

        logger.info(
            f"📰 Finnhub vault complete: earnings={'✓' if stats['earnings'] else 'skip'}, "
            f"{stats['news']} tickers with news"
        )
        return {"status": "ok", **stats}

    except Exception as e:
        logger.error(f"Finnhub vault failed: {e}")
        return {"status": "error", "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# 4. FRED / MACRO — VIX live + macro series
# ═══════════════════════════════════════════════════════════════

def vault_fred_data(store: TimescaleDataStore) -> dict:
    """Vault FRED macro data (1x per day)."""
    stats = {"series": 0}

    if _already_vaulted_today(store, "macro/fred", "SUMMARY"):
        logger.info("📊 FRED macro already vaulted today — skipping")
        return {"status": "skipped", "reason": "already_today"}

    try:
        import yfinance as yf

        # Fetch key macro indicators via yfinance (free, no API key)
        macro_tickers = {
            "^VIX": "VIX",
            "^TNX": "YIELD_10Y",  # 10Y Treasury
            "^IRX": "YIELD_3M",   # 3M Treasury
            "^GSPC": "SP500",     # S&P 500
            "DX-Y.NYB": "DXY",   # Dollar Index
            "GC=F": "GOLD",      # Gold futures
            "CL=F": "OIL_WTI",   # WTI crude
            "^SKEW": "SKEW",     # CBOE Skew Index (tail risk)
        }

        macro_snapshot = {}
        for yf_ticker, label in macro_tickers.items():
            try:
                t = yf.Ticker(yf_ticker)
                hist = t.history(period="5d")
                if not hist.empty:
                    import pandas as pd
                    if isinstance(hist.columns, pd.MultiIndex):
                        hist.columns = hist.columns.get_level_values(0)
                    latest = hist.iloc[-1]
                    macro_snapshot[label] = {
                        "close": float(latest["Close"]),
                        "high": float(latest["High"]),
                        "low": float(latest["Low"]),
                        "volume": int(latest["Volume"]) if latest["Volume"] else 0,
                    }
                    stats["series"] += 1
            except Exception as e:
                logger.debug(f"  Macro {label}: {e}")

        if macro_snapshot:
            macro_snapshot["timestamp"] = datetime.now(UTC).isoformat()
            store.save_mcp_snapshot("macro/fred", "SUMMARY", macro_snapshot)
            logger.info(f"📊 FRED macro vault: {stats['series']} series captured")

        return {"status": "ok", **stats}

    except Exception as e:
        logger.error(f"FRED vault failed: {e}")
        return {"status": "error", "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# 5. ALPACA — Portfolio Snapshot (Position Reconciliation)
# ═══════════════════════════════════════════════════════════════

def vault_portfolio_data(store: TimescaleDataStore) -> dict:
    """Vault Alpaca portfolio snapshot for position reconciliation."""
    stats = {"positions": 0, "cash": 0}

    try:
        import os
        api_key = os.getenv("ALPACA_API_KEY", "")
        secret_key = os.getenv("ALPACA_SECRET_KEY", "")

        if not api_key or not secret_key:
            logger.debug("Alpaca keys not configured — skipping portfolio vault")
            return {"status": "skipped", "reason": "no_api_key"}

        from backend.modules.execution.infrastructure.brokers.alpaca_adapter import AlpacaAdapter
        import asyncio

        adapter = AlpacaAdapter(api_key, secret_key)
        portfolio = asyncio.get_event_loop().run_until_complete(adapter.get_portfolio())

        snapshot = {
            "timestamp": datetime.now(UTC).isoformat(),
            "cash": portfolio.cash,
            "positions": [
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "avg_cost": p.avg_cost,
                    "market_price": p.market_price,
                    "pnl": round((p.market_price - p.avg_cost) * p.quantity, 2),
                }
                for p in portfolio.positions
            ],
            "total_value": portfolio.cash + sum(
                p.market_price * p.quantity for p in portfolio.positions
            ),
        }

        store.save_mcp_snapshot("portfolio/snapshot", "ALPACA", snapshot)
        stats["positions"] = len(portfolio.positions)
        stats["cash"] = portfolio.cash

        logger.info(
            f"💼 Portfolio vault: {stats['positions']} positions, "
            f"${stats['cash']:,.0f} cash"
        )
        return {"status": "ok", **stats}

    except Exception as e:
        logger.error(f"Portfolio vault failed: {e}")
        return {"status": "error", "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# 6. GURUFOCUS — Fundamental Screening (daily, from cache)
# ═══════════════════════════════════════════════════════════════

def vault_gurufocus_screening(store: TimescaleDataStore, tickers: list[str]) -> dict:
    """Vault GuruFocus fundamental screening (1x/day, 20 tickers max per cycle)."""
    stats = {"screened": 0}

    if _already_vaulted_today(store, "fundamental/screening", "BATCH_DONE"):
        logger.info("📊 GuruFocus screening already done today — skipping")
        return {"status": "skipped", "reason": "already_today"}

    try:
        from backend.modules.portfolio_management.infrastructure.gurufocus_adapter import GuruFocusIntelligence

        gf = GuruFocusIntelligence()

        # Screen top 20 tickers (rate limit safe)
        batch = tickers[:20]
        for ticker in batch:
            try:
                summary = gf.get_quality_summary(ticker)
                if summary and isinstance(summary, dict) and summary.get("gf_score"):
                    store.save_mcp_snapshot("fundamental/screening", ticker, summary)
                    stats["screened"] += 1
            except Exception as e:
                logger.debug(f"  {ticker} GF screening failed: {e}")

        # Mark batch as done for today
        if stats["screened"] > 0:
            store.save_mcp_snapshot("fundamental/screening", "BATCH_DONE", {
                "timestamp": datetime.now(UTC).isoformat(),
                "tickers_screened": stats["screened"],
                "batch": batch,
            })

        logger.info(f"🔬 GuruFocus screening: {stats['screened']}/{len(batch)} tickers")
        return {"status": "ok", **stats}

    except Exception as e:
        logger.error(f"GuruFocus vault failed: {e}")
        return {"status": "error", "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# 7. OHLCV BARS — Daily update (yfinance + Alpaca enrichment)
# ═══════════════════════════════════════════════════════════════

def vault_ohlcv_bars(store: TimescaleDataStore, tickers: list[str]) -> dict:
    """Update OHLCV bars with today's candle. 1x/day after market close."""
    stats = {"updated": 0, "enriched": 0}

    # Only run once per day
    if _already_vaulted_today(store, "ohlcv/update", "BATCH_DONE"):
        logger.info("📈 OHLCV bars already updated today — skipping")
        return {"status": "skipped", "reason": "already_today"}

    try:
        import yfinance as yf
        import pandas as pd
        import os
    except ImportError:
        return {"status": "skipped", "reason": "no_yfinance"}

    # Process in batches of 20 to avoid yfinance rate limits
    batch_size = 20
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        for ticker in batch:
            try:
                # Get last date in Neon
                last = store.bars_last_date(ticker, "1d")
                if not last:
                    continue

                from datetime import timedelta
                start_str = (last + timedelta(days=1)).strftime("%Y-%m-%d")

                # Download new bars from yfinance
                df = yf.download(ticker, start=start_str, interval="1d",
                                 progress=False, auto_adjust=True)
                if df.empty:
                    continue

                # Harmonize
                if isinstance(df.columns, pd.MultiIndex):
                    df = df.xs(ticker, level=1, axis=1)
                df.columns = [c.lower() for c in df.columns]
                required = ["open", "high", "low", "close", "volume"]
                available = [c for c in required if c in df.columns]
                df = df[available].copy()
                if df.index.tz is not None:
                    df.index = df.index.tz_convert("UTC")
                else:
                    df.index = df.index.tz_localize("UTC")
                df.index.name = "timestamp"
                df.dropna(subset=["open", "high", "low", "close"], inplace=True)

                if df.empty:
                    continue

                store.save_bars(ticker, "1d", df)
                stats["updated"] += 1

                # Enrich with Alpaca trade_count + vwap
                api_key = os.environ.get("ALPACA_API_KEY", "")
                if api_key:
                    try:
                        from alpaca.data.historical import StockHistoricalDataClient
                        from alpaca.data.requests import StockBarsRequest
                        from alpaca.data.timeframe import TimeFrame

                        client = StockHistoricalDataClient(
                            api_key, os.environ.get("ALPACA_SECRET_KEY", "")
                        )
                        first_date = df.index.min()
                        last_date = df.index.max()
                        request = StockBarsRequest(
                            symbol_or_symbols=ticker,
                            timeframe=TimeFrame.Day,
                            start=first_date,
                            end=last_date + pd.Timedelta(days=1),
                            limit=10,
                        )
                        alpaca_bars = client.get_stock_bars(request)
                        if alpaca_bars and ticker in alpaca_bars.data:
                            conn = store._conn()
                            try:
                                with conn.cursor() as cur:
                                    for bar in alpaca_bars.data[ticker]:
                                        vwap = float(bar.vwap) if hasattr(bar, 'vwap') and bar.vwap else None
                                        tc = int(bar.trade_count) if hasattr(bar, 'trade_count') and bar.trade_count else None
                                        if vwap or tc:
                                            cur.execute(
                                                """UPDATE market.ohlcv_bars
                                                   SET vwap = %s, trade_count = %s
                                                   WHERE ticker = %s AND timeframe = '1d'
                                                   AND time::date = %s""",
                                                (vwap, tc, ticker, bar.timestamp.date()),
                                            )
                                conn.commit()
                                stats["enriched"] += 1
                            except Exception:
                                conn.rollback()
                            finally:
                                store._put(conn)
                    except Exception:
                        pass  # Enrichment is best-effort

            except Exception as e:
                logger.debug(f"  {ticker} OHLCV update failed: {e}")

    # Mark as done for today
    if stats["updated"] > 0:
        store.save_mcp_snapshot("ohlcv/update", "BATCH_DONE", {
            "timestamp": datetime.now(UTC).isoformat(),
            "tickers_updated": stats["updated"],
            "tickers_enriched": stats["enriched"],
        })

    logger.info(
        f"📈 OHLCV vault: {stats['updated']} tickers updated, "
        f"{stats['enriched']} enriched with trade_count+vwap"
    )
    return {"status": "ok", **stats}


# ═══════════════════════════════════════════════════════════════
# 8. CNN FEAR & GREED — Market Sentiment (daily)
# ═══════════════════════════════════════════════════════════════

def vault_fear_greed(store: TimescaleDataStore) -> dict:
    """Vault CNN Fear & Greed Index (1x per day)."""
    if _already_vaulted_today(store, "macro/fear_greed", "MARKET"):
        logger.info("😱 Fear & Greed already vaulted today — skipping")
        return {"status": "skipped", "reason": "already_today"}

    try:
        import requests as req
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        r = req.get(url, timeout=10, headers=headers)
        r.raise_for_status()
        data = r.json()

        fg = data.get("fear_and_greed", {})
        hist = data.get("fear_and_greed_historical", {})

        snapshot = {
            "score": fg.get("score", 50.0),
            "rating": fg.get("rating", "neutral"),
            "previous_close": hist.get("previousClose", {}).get("score"),
            "one_week_ago": hist.get("oneWeekAgo", {}).get("score"),
            "one_month_ago": hist.get("oneMonthAgo", {}).get("score"),
            "one_year_ago": hist.get("oneYearAgo", {}).get("score"),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        store.save_mcp_snapshot("macro/fear_greed", "MARKET", snapshot)
        logger.info(f"😱 Fear & Greed vault: {snapshot['score']:.1f} ({snapshot['rating']})")
        return {"status": "ok", "score": snapshot["score"]}

    except Exception as e:
        logger.warning(f"Fear & Greed vault failed (non-critical): {e}")
        return {"status": "error", "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# CYCLE ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

def _get_neon_universe(store: TimescaleDataStore) -> list[str]:
    """Pull the list of all tickers in Neon OHLCV bars."""
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT ticker FROM market.ohlcv_bars ORDER BY ticker")
            return [row[0] for row in cur.fetchall()]
    finally:
        store._put(conn)


def run_cycle(store: TimescaleDataStore) -> None:
    """Run one full vault cycle — ALL data sources."""
    interceptor = VaultInterceptor(store)
    ts = datetime.now(UTC).isoformat()
    logger.info(f"═══ Vault cycle started at {ts} ═══")

    neon_tickers = _get_neon_universe(store)
    logger.info(f"📊 Neon universe: {len(neon_tickers)} tickers")

    results = {}

    # Every cycle (5 min):
    results["uw"] = vault_uw_data(interceptor)
    results["yahoo"] = vault_yahoo_data(interceptor, neon_tickers)
    results["portfolio"] = vault_portfolio_data(store)
    results["finnhub"] = vault_finnhub_data(store, neon_tickers)

    # 1x per day (internal check):
    results["fred"] = vault_fred_data(store)
    results["fear_greed"] = vault_fear_greed(store)
    results["gurufocus"] = vault_gurufocus_screening(store, neon_tickers)
    results["ohlcv"] = vault_ohlcv_bars(store, neon_tickers)

    summary = " | ".join(f"{k}={v.get('status', '?')}" for k, v in results.items())
    logger.info(f"═══ Vault cycle complete: {summary} ═══")


def main():
    parser = argparse.ArgumentParser(
        description="Data Vault Daemon — accumulate ALL MCP snapshots"
    )
    parser.add_argument(
        "--loop", type=int, default=300,
        help="Loop interval in seconds (0 = one-shot, default 300 = 5 min)",
    )
    args = parser.parse_args()

    logger.info(f"Loop: {'one-shot' if args.loop <= 0 else f'{args.loop}s'}")

    store = TimescaleDataStore()

    while True:
        run_cycle(store)

        if args.loop <= 0:
            break

        logger.info(f"Sleeping {args.loop}s until next cycle...")
        time.sleep(args.loop)

    store.close()


if __name__ == "__main__":
    main()
