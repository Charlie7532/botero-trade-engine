"""
Vault Daily Flow — UW Data Accumulation Cron
================================================
Daily script to capture and vault Unusual Whales flow data.
Run as a cron job or manually to build historical flow data.

Usage:
    python -m backend.scripts.vault_daily_flow \\
        --tickers NVDA,AAPL,MSFT,GOOGL,SPY

Captures:
    - Per-ticker flow alerts → vault/flow/alerts/{TICKER}/{date}.json
    - SPY net-prem ticks → vault/flow/spy/SPY/{date}.json
    - Market tide → vault/flow/tide/MARKET/{date}.json
    - Dark pool prints → vault/flow/darkpool/{TICKER}/{date}.json
    - Market sentiment → vault/flow/sentiment/MARKET/{date}.json
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.modules.simulation.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.simulation.infrastructure.vault_interceptor import VaultInterceptor

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def main():
    parser = argparse.ArgumentParser(description="Vault daily UW flow data")
    parser.add_argument("--tickers", required=True, help="Comma-separated watchlist tickers")
    parser.add_argument("--include-darkpool", action="store_true", help="Also fetch dark pool prints")
    parser.add_argument("--include-gex", action="store_true", help="Also fetch GEX data")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",")]

    store = TimescaleDataStore()
    interceptor = VaultInterceptor(store)

    try:
        from backend.modules.flow_intelligence.infrastructure.uw_mcp_bridge import UWDataBridge
    except ImportError:
        logger.error("UWDataBridge not available")
        return

    bridge = UWDataBridge()
    if not bridge.is_configured():
        logger.error("UW_API_KEY not configured — cannot fetch flow data")
        return

    # 1. Market-wide data
    logger.info("📡 Fetching SPY flow...")
    spy_ticks = bridge.fetch_spy_flow()
    interceptor.intercept_spy_flow(spy_ticks)

    logger.info("📡 Fetching market tide...")
    tide = bridge.fetch_market_tide()
    interceptor.intercept_market_tide(tide)

    # 2. Market-wide sentiment (from flow alerts)
    logger.info("📡 Fetching market-wide flow alerts...")
    all_alerts = bridge.fetch_flow_alerts(limit=200)

    from backend.modules.flow_intelligence.infrastructure.uw_adapter import UnusualWhalesIntelligence
    uw = UnusualWhalesIntelligence()
    sentiment = uw.parse_market_sentiment(all_alerts)
    from dataclasses import asdict
    interceptor.intercept_sentiment(asdict(sentiment))

    # 3. Per-ticker data
    for ticker in tickers:
        logger.info(f"📡 Fetching flow for {ticker}...")

        # Flow alerts
        ticker_alerts = bridge.fetch_flow_alerts(ticker=ticker, limit=100)
        interceptor.intercept_flow_alerts(ticker, ticker_alerts)

        # Dark pool
        if args.include_darkpool:
            dp = bridge.fetch_darkpool_trades(ticker)
            interceptor.intercept_darkpool(ticker, dp)

        # GEX
        if args.include_gex:
            gex = bridge.fetch_ticker_gex(ticker)
            interceptor.intercept_gex(ticker, gex)

    logger.info(f"✅ Vault daily flow complete: {len(tickers)} tickers captured")


if __name__ == "__main__":
    main()
