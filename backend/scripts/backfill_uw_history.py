"""
UW Historical Backfill — One-shot script
==========================================
Fetches 6 days of historical Unusual Whales data and vaults it
into Neon PostgreSQL (market.mcp_snapshots) with CORRECT historical timestamps.

Usage:
    PYTHONPATH=. backend/.venv/bin/python backend/scripts/backfill_uw_history.py
"""
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.flow_intelligence.infrastructure.uw_mcp_bridge import UWDataBridge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Backfill] %(levelname)s — %(message)s",
)
logger = logging.getLogger("Backfill")


def backfill_day(bridge: UWDataBridge, store: TimescaleDataStore, target_date: date):
    """Backfill all UW data for a single historical date."""
    ds = target_date.isoformat()
    # Use 16:00 UTC (market close) as the canonical timestamp for this day
    historical_ts = f"{ds}T16:00:00+00:00"
    logger.info(f"═══ Backfilling {ds} ═══")

    saved = 0

    # 1. SPY net-prem-ticks for this date
    spy_ticks = bridge.fetch_ticker_net_prem_ticks("SPY", date=ds)
    if spy_ticks:
        store.save_mcp_snapshot("flow/spy", "SPY", spy_ticks, timestamp=historical_ts)
        saved += 1
        logger.info(f"  SPY ticks: {len(spy_ticks)}")
    else:
        logger.info(f"  SPY ticks: 0 (weekend/holiday?)")
        return 0

    # 2. Market-wide flow alerts for this date
    all_alerts = bridge._request(
        "/api/option-trades/flow-alerts",
        {"limit": 500, "date": ds},
    )
    if all_alerts:
        alerts = all_alerts.get("data", all_alerts) if isinstance(all_alerts, dict) else all_alerts
        if isinstance(alerts, list) and alerts:
            store.save_mcp_snapshot("flow/alerts", "MARKET", alerts, timestamp=historical_ts)
            saved += 1
            logger.info(f"  Market alerts: {len(alerts)}")

            # 3. Extract unique tickers
            index_tickers = {"SPY", "QQQ", "IWM", "SPX", "SPXW", "NDX", "RUT", "VIX", "DIA"}
            active_tickers = set()
            for alert in alerts:
                ticker = alert.get("ticker")
                if ticker and ticker not in index_tickers:
                    active_tickers.add(ticker)

            logger.info(f"  {len(active_tickers)} tickers in flow for {ds}")

            # 4. Per-ticker options-volume for this date
            for ticker in sorted(active_tickers):
                try:
                    data = bridge._request(
                        f"/api/stock/{ticker}/options-volume",
                        {"date": ds},
                    )
                    if data:
                        vol = data.get("data", data) if isinstance(data, dict) else data
                        if vol:
                            store.save_mcp_snapshot("flow/alerts", ticker, vol, timestamp=historical_ts)
                            saved += 1
                except Exception as e:
                    logger.debug(f"  {ticker}: {e}")

    logger.info(f"═══ {ds} complete: {saved} snapshots saved ═══")
    return saved


def main():
    bridge = UWDataBridge()
    if not bridge.is_configured():
        logger.error("UW_API_KEY not configured")
        sys.exit(1)

    store = TimescaleDataStore()
    today = date.today()
    total = 0

    for d in range(1, 8):
        target = today - timedelta(days=d)
        if target.weekday() >= 5:
            logger.info(f"Skipping {target.isoformat()} (weekend)")
            continue
        saved = backfill_day(bridge, store, target)
        total += saved
        time.sleep(1)

    store.close()
    logger.info(f"✅ Backfill complete: {total} total snapshots saved across trading days")


if __name__ == "__main__":
    main()
