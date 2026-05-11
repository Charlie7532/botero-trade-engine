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
logging.getLogger("yfinance").setLevel(logging.CRITICAL)


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


# Module-level flag: when True, _already_vaulted_today always returns False
_FORCE_REFRESH = False


def _already_vaulted_today(store: TimescaleDataStore, category: str, ticker: str) -> bool:
    """Check if we already have a snapshot for this category/ticker today."""
    if _FORCE_REFRESH:
        return False
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
        # 1. VIX snapshot (full OHLCV — high/low needed for intraday spike detection)
        vix = yf.Ticker("^VIX")
        vix_hist = vix.history(period="1d")
        if not vix_hist.empty:
            if isinstance(vix_hist.columns, pd.MultiIndex):
                vix_hist.columns = vix_hist.columns.get_level_values(0)
            row = vix_hist.iloc[-1]
            interceptor.store.save_mcp_snapshot("yahoo/vix", "VIX", {
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "timestamp": datetime.now(UTC).isoformat(),
            })
            stats["vix"] = True
            logger.info(f"📊 VIX snapshot: O={row['Open']:.2f} H={row['High']:.2f} L={row['Low']:.2f} C={row['Close']:.2f}")

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
# 3B. SEC 8-K FILINGS — Material Event Surveillance
# ═══════════════════════════════════════════════════════════════

def vault_sec_8k_filings(store: TimescaleDataStore) -> dict:
    """Vault recent 8-K filings for quality watchlist tickers (1x per day).

    8-K filings disclose material corporate events that can signal
    moat decay: executive departures, regulatory actions, M&A,
    debt covenant violations, revenue guidance changes.

    Scans top 20 quality watchlist tickers via Finnhub free tier.
    """
    if _already_vaulted_today(store, "sec/8k_filings", "BATCH_DONE"):
        logger.info("📄 SEC 8-K filings already vaulted today — skipping")
        return {"status": "skipped", "reason": "already_today"}

    stats = {"tickers_scanned": 0, "filings_found": 0}

    try:
        from backend.modules.flow_intelligence.infrastructure.finnhub_api import FinnhubIntelligence
        fh = FinnhubIntelligence()
        if not fh._available:
            logger.warning("Finnhub not available — skipping 8-K vault")
            return {"status": "skipped", "reason": "no_api_key"}

        # Get quality watchlist tickers
        conn = store._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ticker FROM market.quality_watchlist "
                    "ORDER BY conviction_score DESC LIMIT 20"
                )
                tickers = [r[0] for r in cur.fetchall()]
        finally:
            store._put(conn)

        if not tickers:
            logger.info("📄 No watchlist tickers — skipping 8-K scan")
            return {"status": "ok", **stats}

        import time
        for ticker in tickers:
            try:
                filings = fh.get_recent_filings(ticker, form="8-K", days_back=90)
                if filings:
                    store.save_mcp_snapshot("sec/8k_filings", ticker, {
                        "filings": filings,
                        "count": len(filings),
                        "latest_date": filings[0].get("filed_date", ""),
                        "timestamp": datetime.now(UTC).isoformat(),
                    })
                    stats["filings_found"] += len(filings)
                stats["tickers_scanned"] += 1
                time.sleep(0.5)  # Respect Finnhub rate limits (60/min free)
            except Exception as e:
                logger.debug(f"  8-K {ticker}: {e}")

        # Mark batch as done
        store.save_mcp_snapshot("sec/8k_filings", "BATCH_DONE", {
            "timestamp": datetime.now(UTC).isoformat(),
            **stats,
        })

        logger.info(
            f"📄 SEC 8-K vault: {stats['tickers_scanned']} tickers scanned, "
            f"{stats['filings_found']} filings found"
        )
        return {"status": "ok", **stats}

    except Exception as e:
        logger.error(f"SEC 8-K vault failed: {e}")
        return {"status": "error", "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# 4A. FRED MACRO — Real Federal Reserve data via MCP
# ═══════════════════════════════════════════════════════════════

def vault_fred_macro(store: TimescaleDataStore) -> dict:
    """Vault real FRED macro data via FRED MCP (1x per day).
    
    This is the TRUE macro intelligence source — Net Liquidity,
    Fed Funds Rate, CPI, unemployment, yield curve.
    Druckenmiller directive #8: 'Liquidity is the tide.'
    """
    stats = {"series": 0}

    if _already_vaulted_today(store, "macro/fred_real", "SUMMARY"):
        logger.info("📊 FRED macro (real) already vaulted today — skipping")
        return {"status": "skipped", "reason": "already_today"}

    try:
        from backend.modules.flow_intelligence.infrastructure.fred_adapter import (
            FREDMacroIntelligence, FRED_SERIES,
        )

        # Fetch each series individually via FRED MCP bridge
        # The FRED MCP server exposes get_economic_indicator(series_id)
        fred_data = {}

        # Try to use fredapi if available (direct FRED API access)
        fred_client = None
        try:
            from fredapi import Fred
            import os
            api_key = os.getenv("FRED_API_KEY", "")
            if api_key:
                fred_client = Fred(api_key=api_key)
                logger.info("FRED API client initialized")
        except ImportError:
            logger.info("fredapi not installed — attempting yfinance fallback for FRED series")

        # Priority series for Net Liquidity formula
        priority_series = [
            ("WALCL", "fed_balance_sheet"),
            ("RRPONTSYD", "reverse_repo"),
            ("WTREGEN", "tga_balance"),
            ("FEDFUNDS", "fed_funds_rate"),
            ("DGS10", "treasury_10y"),
            ("DGS2", "treasury_2y"),
            ("T10Y2Y", "yield_spread"),
            ("CPIAUCSL", "cpi_yoy"),
            ("UNRATE", "unemployment_rate"),
            ("UMCSENT", "consumer_sentiment"),
            ("WM2NS", "m2_money_supply"),
        ]

        if fred_client:
            for series_id, field_name in priority_series:
                try:
                    data = fred_client.get_series(series_id, observation_start="2024-01-01")
                    if data is not None and len(data) > 0:
                        latest = float(data.dropna().iloc[-1])
                        fred_data[field_name] = latest
                        stats["series"] += 1
                        # Store previous value for trend calculation
                        if len(data.dropna()) >= 5:
                            prev = float(data.dropna().iloc[-5])
                            fred_data[f"{field_name}_prev"] = prev
                except Exception as e:
                    logger.debug(f"  FRED {series_id}: {e}")

            # CPI: convert absolute index to YoY% change
            # CPIAUCSL returns ~330, not 2.5%. We need the percentage.
            try:
                cpi_series = fred_client.get_series("CPIAUCSL", observation_start="2024-01-01")
                cpi_clean = cpi_series.dropna()
                if len(cpi_clean) >= 12:
                    current_cpi = float(cpi_clean.iloc[-1])
                    year_ago_cpi = float(cpi_clean.iloc[-12])
                    cpi_yoy = ((current_cpi - year_ago_cpi) / year_ago_cpi) * 100
                    fred_data["cpi_yoy"] = round(cpi_yoy, 2)
                    logger.info(f"  CPI YoY: {cpi_yoy:.2f}% (index {current_cpi:.1f} vs {year_ago_cpi:.1f})")
            except Exception as e:
                logger.debug(f"  CPI YoY calculation: {e}")

            # Calculate previous Net Liquidity for trend
            if "fed_balance_sheet_prev" in fred_data:
                prev_walcl = fred_data.get("fed_balance_sheet_prev", 0)
                prev_rrp = fred_data.get("reverse_repo_prev", 0)
                prev_tga = fred_data.get("tga_balance_prev", 0)
                fred_data["_net_liquidity_prev"] = prev_walcl - prev_rrp - prev_tga

        if fred_data:
            # Parse through the intelligence adapter for classification
            intel = FREDMacroIntelligence()
            snapshot = intel.parse_macro_snapshot(individual_series=fred_data)

            # Persist the enriched snapshot
            vault_payload = {
                **fred_data,
                "net_liquidity": snapshot.net_liquidity,
                "net_liquidity_trend": snapshot.net_liquidity_trend,
                "liquidity_regime": snapshot.liquidity_regime,
                "macro_regime": snapshot.macro_regime,
                "regime_score": snapshot.regime_score,
                "fed_stance": snapshot.fed_stance,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            store.save_mcp_snapshot("macro/fred_real", "SUMMARY", vault_payload)
            nl_str = f"{snapshot.net_liquidity:,.0f}B" if snapshot.net_liquidity else "N/A"
            logger.info(
                f"📊 FRED macro vault (REAL): {stats['series']} series, "
                f"NetLiq={nl_str} regime={snapshot.macro_regime} "
                f"(score={snapshot.regime_score:.0f})"
            )
        else:
            logger.warning("FRED macro: no data retrieved — check FRED_API_KEY and fredapi")

        return {"status": "ok", **stats}

    except Exception as e:
        logger.error(f"FRED macro vault failed: {e}")
        return {"status": "error", "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# 4B. MARKET INDICES — VIX, S&P500, DXY, Gold, Oil via yfinance
# ═══════════════════════════════════════════════════════════════

def vault_market_indices(store: TimescaleDataStore) -> dict:
    """Vault market indices via yfinance (VIX, yields, S&P500, DXY, gold, oil)."""
    stats = {"series": 0}

    if _already_vaulted_today(store, "macro/market_indices", "SUMMARY"):
        logger.info("📈 Market indices already vaulted today — skipping")
        return {"status": "skipped", "reason": "already_today"}

    try:
        import yfinance as yf

        # Fetch key macro indicators via yfinance (free, no API key)
        # NOTE: SKEW and VVIX are fetched directly from CBOE CSV
        # (vault_cboe_indices). Yahoo delisted these tickers.
        macro_tickers = {
            "^VIX": "VIX",
            "^TNX": "YIELD_10Y",  # 10Y Treasury
            "^IRX": "YIELD_3M",   # 3M Treasury
            "^GSPC": "SP500",     # S&P 500
            "DX-Y.NYB": "DXY",   # Dollar Index
            "GC=F": "GOLD",      # Gold futures
            "CL=F": "OIL_WTI",   # WTI crude
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
            store.save_mcp_snapshot("macro/market_indices", "SUMMARY", macro_snapshot)
            # Also write to macro/fred for backward compatibility
            store.save_mcp_snapshot("macro/fred", "SUMMARY", macro_snapshot)
            logger.info(f"📈 Market indices vault: {stats['series']} series captured")

        return {"status": "ok", **stats}

    except Exception as e:
        logger.error(f"FRED vault failed: {e}")
        return {"status": "error", "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# 4C. VIX LIVE — High-frequency volatility monitor
# ═══════════════════════════════════════════════════════════════

# VIX regime thresholds (institutional standard)
_VIX_THRESHOLDS = {
    "calm":     (0,    18),
    "elevated": (18,   25),
    "panic":    (25,   35),
    "crisis":   (35,   float("inf")),
}

def vault_vix_live(store: TimescaleDataStore) -> dict:
    """High-frequency VIX snapshot — runs EVERY cycle (no daily skip).

    VIX is the single most important real-time risk signal.
    A regime change from 'calm' to 'panic' must be detected
    within minutes, not hours.

    Thresholds:
      0-18:  calm     → full allocation
      18-25: elevated → reduce new entries
      25-35: panic    → halt new entries
      35+:   crisis   → consider hedging

    Saves to macro/vix_live (overwrites each cycle).
    """
    try:
        import yfinance as yf
        import pandas as pd

        t = yf.Ticker("^VIX")
        hist = t.history(period="5d")
        if hist.empty:
            return {"status": "error", "error": "no VIX data"}

        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)

        latest = hist.iloc[-1]
        vix = float(latest["Close"])
        vix_high = float(latest["High"])
        vix_low = float(latest["Low"])

        # Previous close for delta
        prev_close = float(hist.iloc[-2]["Close"]) if len(hist) >= 2 else vix
        vix_delta = vix - prev_close
        vix_delta_pct = (vix_delta / prev_close * 100) if prev_close > 0 else 0

        # Classify regime
        regime = "calm"
        for name, (lo, hi) in _VIX_THRESHOLDS.items():
            if lo <= vix < hi:
                regime = name
                break

        # Alert on regime transitions
        # Check previous regime from vault
        prev_regime = "unknown"
        try:
            conn = store._conn()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT data->>'regime' FROM market.mcp_snapshots
                    WHERE category = 'macro/vix_live' AND ticker = 'VIX'
                    ORDER BY time DESC LIMIT 1
                """)
                row = cur.fetchone()
                if row and row[0]:
                    prev_regime = row[0]
            store._put(conn)
        except Exception:
            pass

        regime_changed = prev_regime != "unknown" and prev_regime != regime

        snapshot = {
            "vix": round(vix, 2),
            "high": round(vix_high, 2),
            "low": round(vix_low, 2),
            "delta": round(vix_delta, 2),
            "delta_pct": round(vix_delta_pct, 2),
            "regime": regime,
            "prev_regime": prev_regime,
            "regime_changed": regime_changed,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        store.save_mcp_snapshot("macro/vix_live", "VIX", snapshot)

        # Persist VIX as OHLCV bar for historical analysis
        # (enables VIX vs breadth vs RSI time-series correlation)
        try:
            latest_date = hist.index[-1].to_pydatetime()
            vix_df = pd.DataFrame({
                "open": [float(latest["Open"])],
                "high": [vix_high],
                "low": [vix_low],
                "close": [vix],
                "volume": [0],
            }, index=[latest_date])
            store.save_bars("VIX", "1d", vix_df)
            logger.debug(f"VIX OHLCV bar persisted for {latest_date.date()}")
        except Exception as e:
            logger.debug(f"VIX OHLCV persistence skipped: {e}")

        # Log with appropriate severity
        if regime == "crisis":
            logger.critical(
                f"🔴 VIX CRISIS: {vix:.1f} (Δ{vix_delta:+.1f}) — "
                f"HALT ALL NEW ENTRIES"
            )
        elif regime == "panic":
            logger.warning(
                f"🟠 VIX PANIC: {vix:.1f} (Δ{vix_delta:+.1f}) — "
                f"halt new entries recommended"
            )
        elif regime == "elevated":
            logger.warning(
                f"🟡 VIX ELEVATED: {vix:.1f} (Δ{vix_delta:+.1f}) — "
                f"reduce exposure"
            )
        else:
            logger.info(f"🟢 VIX: {vix:.1f} (Δ{vix_delta:+.1f}) — {regime}")

        if regime_changed:
            logger.warning(
                f"⚡ VIX REGIME SHIFT: {prev_regime} → {regime} "
                f"(VIX={vix:.1f})"
            )
            # Dispatch alert for regime change
            try:
                from backend.modules.shared.domain.entities.alert_entities import Alert
                from backend.modules.shared.infrastructure.postgres_alert_adapter import PostgresAlertAdapter

                severity = "critical" if regime in ("panic", "crisis") else "warning"
                alert = Alert(
                    category="vix",
                    severity=severity,
                    ticker="MARKET",
                    title=f"VIX Regime Shift: {prev_regime} → {regime}",
                    message=(
                        f"VIX moved from {prev_regime} to {regime}. "
                        f"Current: {vix:.1f} (Δ{vix_delta:+.1f}, {vix_delta_pct:+.1f}%)"
                    ),
                    source="vault_vix_live",
                    metric_name="vix",
                    metric_value=vix,
                    previous_value=prev_close,
                )
                adapter = PostgresAlertAdapter(pool=store._pool)
                adapter.save_alert(alert)
            except Exception as e:
                logger.debug(f"VIX alert dispatch failed: {e}")

        return {"status": "ok", "vix": vix, "regime": regime}

    except Exception as e:
        logger.error(f"VIX live vault failed: {e}")
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
        portfolio = asyncio.run(adapter.get_portfolio())

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
    """Vault GuruFocus deep screening (summary + keyratios). 1x/day, 20 tickers/cycle.

    Uses fetch_deep_screening() which combines /summary (40 fields) +
    /keyratios (888 fields) into a unified screening object with 70+ curated
    fields needed by the recalibrated QualityWatchlistEngine.

    Rate limit: 2 API calls per ticker × 1.5s = 3s/ticker. 20 tickers = ~60s.
    """
    stats = {"screened": 0}

    if _already_vaulted_today(store, "fundamental/screening", "BATCH_DONE"):
        logger.info("📊 GuruFocus screening already done today — skipping")
        return {"status": "skipped", "reason": "already_today"}

    try:
        from backend.modules.portfolio_management.infrastructure.gurufocus_mcp_bridge import GuruFocusMCPBridge

        bridge = GuruFocusMCPBridge()

        # Screen top 20 tickers (rate limit safe: 20 × 3s = 60s)
        batch = tickers[:20]
        for ticker in batch:
            try:
                screening = bridge.fetch_deep_screening(ticker)
                if screening and isinstance(screening, dict) and screening.get("gf_score"):
                    store.save_mcp_snapshot("fundamental/screening", ticker, screening)
                    stats["screened"] += 1
                    logger.debug(f"  {ticker}: GF={screening.get('gf_score')}, ROIC={screening.get('roic')}")
            except Exception as e:
                logger.debug(f"  {ticker} GF screening failed: {e}")

        # Mark batch as done for today
        if stats["screened"] > 0:
            store.save_mcp_snapshot("fundamental/screening", "BATCH_DONE", {
                "timestamp": datetime.now(UTC).isoformat(),
                "tickers_screened": stats["screened"],
                "batch": batch,
            })

        logger.info(f"🔬 GuruFocus deep screening: {stats['screened']}/{len(batch)} tickers")
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
# 9. MARKET BREADTH — S5TH / S5TW / S5FI (daily, calculated from OHLCV)
#    EXECUTION ORDER: MUST run AFTER vault_ohlcv_bars() so breadth
#    is computed from today's closes, not yesterday's.
# ═══════════════════════════════════════════════════════════════

def vault_breadth_indicators(store: TimescaleDataStore) -> dict:
    """Calculate S5TH, S5TW, and S5FI from existing OHLCV bars. Runs 1x/day.

    Only uses stocks marked as SP500 members (asset_type='STOCK' + index_membership contains 'SP500').
    Writes results as OHLCV bars to maintain continuity with TradingView-imported historical data.
    """
    if _already_vaulted_today(store, "macro/breadth", "SP500"):
        logger.info("📊 Breadth already vaulted today — skipping")
        return {"status": "skipped", "reason": "already_today"}

    try:
        from backend.modules.shared.domain.rules.macro_trend_calculator import calculate_breadth

        # 300 calendar days ≈ 210 trading days — enough for 200-DMA
        all_closes = store.load_all_latest_closes(days=300, sp500_only=True)
        if not all_closes:
            logger.warning("Breadth: no SP500 OHLCV data available")
            return {"status": "error", "reason": "no_data"}

        s5th = calculate_breadth(all_closes, ma_length=200)
        s5tw = calculate_breadth(all_closes, ma_length=20)
        s5fi = calculate_breadth(all_closes, ma_length=50)

        if s5th is None and s5tw is None and s5fi is None:
            logger.warning("Breadth: insufficient history for MA calculation")
            return {"status": "error", "reason": "insufficient_history"}

        snapshot = {
            "s5th": s5th,
            "s5tw": s5tw,
            "s5fi": s5fi,
            "tickers_counted": len(all_closes),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        store.save_mcp_snapshot("macro/breadth", "SP500", snapshot)

        # Write as OHLCV bars (OHLC all = close, volume=0) for continuity
        # with TradingView-imported historical data
        now = datetime.now(UTC)
        for ticker, value in [("S5TH", s5th), ("S5TW", s5tw), ("S5FI", s5fi)]:
            if value is not None:
                store.upsert_ohlcv_bar(
                    ticker=ticker, timeframe="1d", time=now,
                    open=value, high=value, low=value, close=value, volume=0,
                )

        s5th_str = f"{s5th:.1f}%" if s5th is not None else "N/A"
        s5tw_str = f"{s5tw:.1f}%" if s5tw is not None else "N/A"
        s5fi_str = f"{s5fi:.1f}%" if s5fi is not None else "N/A"
        logger.info(
            f"📊 Breadth vault: S5TH={s5th_str} S5TW={s5tw_str} S5FI={s5fi_str} "
            f"({len(all_closes)} SP500 tickers)"
        )
        return {"status": "ok", "s5th": s5th, "s5tw": s5tw, "s5fi": s5fi}

    except Exception as e:
        logger.warning(f"Breadth vault failed (non-critical): {e}")
        return {"status": "error", "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# 10. CBOE INDICES — SKEW + VVIX (daily, authoritative source)
# ═══════════════════════════════════════════════════════════════

def vault_cboe_indices(store: TimescaleDataStore) -> dict:
    """
    Download SKEW and VVIX historical data directly from CBOE
    (Chicago Board Options Exchange) — the authoritative source.

    Yahoo Finance delisted these tickers. CBOE publishes free daily CSVs
    with full history back to 1990 (SKEW) and 2006 (VVIX).

    On first run: backfills entire history.
    On subsequent runs: only inserts new dates (ON CONFLICT DO NOTHING).

    Stores as OHLCV bars in market.ohlcv_bars with open=high=low=close=value.
    """
    if _already_vaulted_today(store, "cboe/indices", "BATCH_DONE"):
        logger.info("📉 CBOE indices already vaulted today — skipping")
        return {"status": "skipped", "reason": "already_today"}

    import pandas as pd
    import requests

    CBOE_BASE = "https://cdn.cboe.com/api/global/us_indices/daily_prices"
    indices = {
        "SKEW": f"{CBOE_BASE}/SKEW_History.csv",
        "VVIX": f"{CBOE_BASE}/VVIX_History.csv",
    }

    stats = {"indices_updated": 0, "total_bars": 0}

    for ticker, url in indices.items():
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()

            df = pd.read_csv(
                pd.io.common.StringIO(resp.text),
                parse_dates=["DATE"],
                dayfirst=False,
            )

            if df.empty:
                logger.warning(f"CBOE {ticker}: empty CSV")
                continue

            # Rename columns to OHLCV format (single value → all equal)
            value_col = [c for c in df.columns if c != "DATE"][0]
            df = df.rename(columns={"DATE": "timestamp", value_col: "close"})
            df["open"] = df["close"]
            df["high"] = df["close"]
            df["low"] = df["close"]
            df["volume"] = 0

            # Set timezone-aware UTC index
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp")
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            df = df[["open", "high", "low", "close", "volume"]]
            df.dropna(subset=["close"], inplace=True)

            # Only insert dates we don't already have
            last_date = store.bars_last_date(ticker, "1d")
            if last_date:
                cutoff = pd.Timestamp(last_date, tz="UTC")
                df = df[df.index > cutoff]

            if df.empty:
                logger.debug(f"CBOE {ticker}: already up to date")
                stats["indices_updated"] += 1
                continue

            store.save_bars(ticker, "1d", df)
            stats["indices_updated"] += 1
            stats["total_bars"] += len(df)
            logger.info(f"📉 CBOE {ticker}: {len(df)} new bars stored")

        except Exception as e:
            logger.warning(f"CBOE {ticker} fetch failed: {e}")

    # Also update the macro snapshot with today's close for quick access
    try:
        for ticker in indices:
            last = store.bars_last_date(ticker, "1d")
            if last:
                bars = store.load_bars(ticker, "1d", start=last, end=last)
                if not bars.empty:
                    close_val = float(bars["close"].iloc[-1])
                    # Inject into macro/fred snapshot for backward compat
                    existing = store.load_mcp_snapshot(
                        "macro/fred", "SUMMARY", date.today().isoformat()
                    )
                    if existing and isinstance(existing, dict):
                        existing[ticker] = {
                            "close": close_val,
                            "high": close_val,
                            "low": close_val,
                            "volume": 0,
                        }
                        existing["timestamp"] = datetime.now(UTC).isoformat()
                        store.save_mcp_snapshot("macro/fred", "SUMMARY", existing)
    except Exception as e:
        logger.debug(f"CBOE macro snapshot enrichment skipped: {e}")

    # Mark done for today
    if stats["indices_updated"] > 0:
        store.save_mcp_snapshot("cboe/indices", "BATCH_DONE", {
            "timestamp": datetime.now(UTC).isoformat(),
            **stats,
        })

    logger.info(
        f"📉 CBOE vault: {stats['indices_updated']} indices, "
        f"{stats['total_bars']} new bars"
    )
    return {"status": "ok", **stats}


# ═══════════════════════════════════════════════════════════════
# 11. SOURCING — Guru Picks + Insider Activity
# ═══════════════════════════════════════════════════════════════
#
# API AUDIT (2026-05-09):
#   ✅ guru_realtime_picks  — Works. Returns {data: list, total, currentPage}.
#   ✅ stock/{ticker}/insider — Works. Returns {TICKER: list[trades]}.
#   🔴 insider/cluster       — WEB-ONLY, 404 on API. Clusters computed locally.
#   🔴 insider/ceo           — WEB-ONLY, 404 on API.
#   🔴 politician/transactions — WEB-ONLY, 404 on API. No programmatic access.
#

def vault_guru_picks(store: TimescaleDataStore) -> dict:
    """Vault guru realtime picks (Form 4). 1x/day, 3 pages (~60 records).

    Relevance: PRIMARY for Quality (believability-weighted sourcing).
    Speculative ignores GuruFocus entirely.
    """
    if _already_vaulted_today(store, "sourcing/guru_picks", "MARKET"):
        logger.info("🎓 Guru picks already vaulted today — skipping")
        return {"status": "skipped", "reason": "already_today"}

    try:
        from backend.modules.portfolio_management.infrastructure.gurufocus_mcp_bridge import GuruFocusMCPBridge
        bridge = GuruFocusMCPBridge()

        all_picks = []
        for page in range(1, 4):  # 3 pages
            picks = bridge.fetch_guru_realtime_picks(page=page)
            if picks and isinstance(picks, (list, dict)):
                items = picks if isinstance(picks, list) else picks.get("data", [])
                all_picks.extend(items)
            time.sleep(1.5)

        if all_picks:
            store.save_mcp_snapshot("sourcing/guru_picks", "MARKET", {
                "picks": all_picks,
                "count": len(all_picks),
                "pages_fetched": 3,
                "timestamp": datetime.now(UTC).isoformat(),
            })
            logger.info(f"🎓 Guru picks vault: {len(all_picks)} picks (3 pages)")
        else:
            logger.warning("🎓 Guru picks: API returned 0 picks — not vaulting empty")

        return {"status": "ok", "picks": len(all_picks)}

    except Exception as e:
        logger.error(f"Guru picks vault failed: {e}")
        return {"status": "error", "error": str(e)}


def vault_insider_activity(store: TimescaleDataStore, watchlist_tickers: list[str] = None) -> dict:
    """Vault insider trading for Quality watchlist tickers. 1x/day.

    Uses per-stock endpoint (stock/{ticker}/insider) because the
    market-wide insider/cluster endpoint is web-only (404 on API).

    Cluster detection is computed locally: ≥3 unique insiders buying
    within 30 days = cluster signal.

    Relevance: HIGH for Quality (thesis confirmation via skin-in-the-game).
    """
    if _already_vaulted_today(store, "sourcing/insider_activity", "MARKET"):
        logger.info("🔍 Insider activity already vaulted today — skipping")
        return {"status": "skipped", "reason": "already_today"}

    try:
        from backend.modules.portfolio_management.infrastructure.gurufocus_mcp_bridge import GuruFocusMCPBridge
        bridge = GuruFocusMCPBridge()

        # Default to quality watchlist tickers if none provided
        if not watchlist_tickers:
            conn = store._conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT ticker FROM market.quality_watchlist ORDER BY conviction_score DESC LIMIT 30")
                    watchlist_tickers = [r[0] for r in cur.fetchall()]
            finally:
                store._put(conn)

        if not watchlist_tickers:
            logger.info("🔍 No watchlist tickers — skipping insider vault")
            return {"status": "ok", "tickers": 0, "clusters": 0}

        all_insider_data = {}
        clusters_detected = []

        for ticker in watchlist_tickers:
            raw = bridge.fetch_insider_trades(ticker)
            if not raw or not isinstance(raw, dict):
                continue

            trades = raw.get(ticker, [])
            if not trades:
                continue

            # Store per-ticker insider snapshot
            store.save_mcp_snapshot("sourcing/insider", ticker, {
                "trades": trades[:50],  # Cap at 50 most recent
                "total_count": len(trades),
                "timestamp": datetime.now(UTC).isoformat(),
            })

            # Cluster detection: ≥3 unique insiders buying within 30 days
            from datetime import timedelta
            cutoff = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%d")
            recent_buys = [
                t for t in trades
                if t.get("type") == "P" and t.get("date", "") >= cutoff
            ]
            unique_buyers = {t.get("insider", "") for t in recent_buys}
            if len(unique_buyers) >= 3:
                clusters_detected.append({
                    "ticker": ticker,
                    "buyer_count": len(unique_buyers),
                    "buyers": list(unique_buyers),
                    "total_buys": len(recent_buys),
                })

            all_insider_data[ticker] = len(trades)

        # Vault aggregate cluster summary
        store.save_mcp_snapshot("sourcing/insider_activity", "MARKET", {
            "tickers_scanned": len(all_insider_data),
            "clusters": clusters_detected,
            "cluster_count": len(clusters_detected),
            "ticker_trade_counts": all_insider_data,
            "timestamp": datetime.now(UTC).isoformat(),
        })

        logger.info(
            f"🔍 Insider vault: {len(all_insider_data)} tickers scanned, "
            f"{len(clusters_detected)} clusters detected"
        )
        return {"status": "ok", "tickers": len(all_insider_data), "clusters": len(clusters_detected)}

    except Exception as e:
        logger.error(f"Insider activity vault failed: {e}")
        return {"status": "error", "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# CYCLE ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

def _get_neon_universe(store: TimescaleDataStore) -> list[str]:
    """Pull the list of tickers eligible for OHLCV bar updates from Alpaca/yfinance.

    Uses update_source = 'vault_ohlcv_bars' from ticker_metadata as the single
    source of truth for which tickers this function should update.
    Excludes INDICATOR and INDEX tickers that have their own update paths.
    """
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ticker FROM market.ticker_metadata
                WHERE update_source = 'vault_ohlcv_bars'
                ORDER BY ticker
            """)
            return [row[0] for row in cur.fetchall()]
    finally:
        store._put(conn)


def drain_refresh_queue(store: TimescaleDataStore) -> dict:
    """Process pending on-demand refresh requests from vault.refresh_queue.

    Uses modular VaultProviders to handle each request category.
    Called at the START of each cycle so urgent requests don't wait.
    """
    try:
        from backend.modules.shared.infrastructure.vault_refresh_adapter import VaultRefreshAdapter
        from backend.daemons.vault_providers import get_provider
        # Ensure all providers are registered
        import backend.daemons.vault_providers.ohlcv_provider  # noqa: F401
        import backend.daemons.vault_providers.breadth_provider  # noqa: F401
        import backend.daemons.vault_providers.remaining_providers  # noqa: F401

        adapter = VaultRefreshAdapter(store)
        pending = adapter.pending_requests(limit=20)

        if not pending:
            return {"status": "ok", "processed": 0}

        logger.info(f"📥 VRR: {len(pending)} pending refresh requests")
        processed = 0
        failed = 0

        for req in pending:
            provider = get_provider(req.category)
            if not provider:
                adapter.mark_failed(req.request_id, f"No provider for category '{req.category}'")
                failed += 1
                continue

            adapter.mark_processing(req.request_id)
            try:
                result = provider.run_ticker(store, req.ticker)
                if result.get("status") == "ok":
                    adapter.mark_done(req.request_id)
                    processed += 1
                else:
                    adapter.mark_failed(req.request_id, str(result))
                    failed += 1
            except Exception as e:
                adapter.mark_failed(req.request_id, str(e))
                failed += 1

        logger.info(f"📥 VRR drain: {processed} processed, {failed} failed")
        return {"status": "ok", "processed": processed, "failed": failed}

    except ImportError:
        return {"status": "skipped", "reason": "vrr_not_installed"}
    except Exception as e:
        logger.warning(f"VRR drain failed (non-critical): {e}")
        return {"status": "error", "error": str(e)}


def run_cycle(store: TimescaleDataStore) -> None:
    """Run one full vault cycle — ALL data sources."""
    interceptor = VaultInterceptor(store)
    ts = datetime.now(UTC).isoformat()
    logger.info(f"═══ Vault cycle started at {ts} ═══")

    neon_tickers = _get_neon_universe(store)
    logger.info(f"📊 Neon universe: {len(neon_tickers)} tickers")

    results = {}

    # ── Tier 0: On-demand refresh requests (VRR) ──
    results["vrr"] = drain_refresh_queue(store)

    # ── Tier 1: Instant + Decision-Critical (~15s) ──
    results["vix_live"] = vault_vix_live(store)
    results["fred_macro"] = vault_fred_macro(store)
    results["cboe"] = vault_cboe_indices(store)
    results["fear_greed"] = vault_fear_greed(store)
    results["portfolio"] = vault_portfolio_data(store)

    # ── Tier 2: Moderate (~1 min) ──
    results["finnhub"] = vault_finnhub_data(store, neon_tickers)
    results["sec_8k"] = vault_sec_8k_filings(store)
    results["market_indices"] = vault_market_indices(store)
    results["guru_picks"] = vault_guru_picks(store)
    results["insider_activity"] = vault_insider_activity(store)

    # ── Tier 3: Heavy (~5-20 min) ──
    results["ohlcv"] = vault_ohlcv_bars(store, neon_tickers)
    results["gurufocus"] = vault_gurufocus_screening(store, neon_tickers)

    # ── Tier 3b: Breadth (MUST run AFTER ohlcv to use fresh closes) ──
    results["breadth"] = vault_breadth_indicators(store)

    # ── Tier 4: Very heavy + rate limited ──
    results["yahoo"] = vault_yahoo_data(interceptor, neon_tickers)
    results["uw"] = vault_uw_data(interceptor)

    summary = " | ".join(f"{k}={v.get('status', '?')}" for k, v in results.items())
    logger.info(f"═══ Vault cycle complete: {summary} ═══")


def main():
    global _FORCE_REFRESH
    parser = argparse.ArgumentParser(
        description="Data Vault Daemon — accumulate ALL MCP snapshots"
    )
    parser.add_argument(
        "--loop", type=int, default=300,
        help="Loop interval in seconds (0 = one-shot, default 300 = 5 min)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force refresh: bypass _already_vaulted_today checks",
    )
    args = parser.parse_args()

    if args.force:
        _FORCE_REFRESH = True
        logger.info("⚡ Force refresh enabled — bypassing daily guards")

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
