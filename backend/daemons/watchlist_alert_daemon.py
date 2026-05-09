"""
Watchlist Alert Daemon — Continuous Fundamental Surveillance
==============================================================
Background runner that:
1. Fetches fresh GuruFocus screening for watchlist candidates
2. Re-scores with QualityWatchlistEngine
3. Detects buy-zone entries and fundamental shifts
4. Logs alerts and persists updated scores to Neon

Delivery mechanism (daemon layer) — equivalent to API routers.
"""
import logging
import os
import sys
from datetime import datetime, timezone

# Path setup for standalone execution
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, _repo_root)
from dotenv import load_dotenv
load_dotenv(os.path.join(_repo_root, ".env"))

from backend.modules.portfolio_management.infrastructure.gurufocus_mcp_bridge import GuruFocusMCPBridge
from backend.modules.portfolio_management.application.use_cases.quality_watchlist_engine import QualityWatchlistEngine
from backend.modules.portfolio_management.infrastructure.watchlist_store import WatchlistStore
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)


def run_quality_surveillance(max_tickers: int = 20) -> dict:
    """
    Main surveillance loop for Quality watchlist.

    1. Load current watchlist from Neon
    2. Fetch fresh screening data from GuruFocus API
    3. Re-score each candidate
    4. Detect buy-zone entries and significant changes
    5. Persist updates + alerts

    Returns:
        Summary dict with stats
    """
    bridge = GuruFocusMCPBridge()
    engine = QualityWatchlistEngine()
    store = WatchlistStore()
    vault = TimescaleDataStore()

    stats = {
        "screened": 0,
        "updated": 0,
        "buy_zone_alerts": 0,
        "new_candidates": 0,
        "errors": 0,
    }

    # 1. Load current watchlist
    current = store.load_quality_watchlist()
    current_tickers = {c.ticker for c in current}
    logger.info(f"📋 Quality Watchlist: {len(current)} candidates loaded")

    # 2. Determine tickers to screen
    # - All current watchlist tickers (refresh)
    # - Top holdings from vault if watchlist is small
    tickers_to_screen = list(current_tickers)

    if len(tickers_to_screen) < max_tickers:
        # Add high-GF-score tickers from vault that aren't on watchlist yet
        try:
            v = TimescaleDataStore()
            # Check for any screened tickers in vault
            import psycopg2
            conn = psycopg2.connect(os.getenv("POSTGRES_URL", ""))
            cur = conn.cursor()
            cur.execute("""
                SELECT DISTINCT ticker FROM market.mcp_snapshots
                WHERE category = 'fundamental/screening'
                AND ticker != 'BATCH_DONE'
                ORDER BY ticker
                LIMIT %s
            """, (max_tickers - len(tickers_to_screen),))
            vault_tickers = [r[0] for r in cur.fetchall()]
            conn.close()
            v.close()

            new_from_vault = [t for t in vault_tickers if t not in current_tickers]
            tickers_to_screen.extend(new_from_vault)
        except Exception as e:
            logger.debug(f"Vault ticker discovery failed: {e}")

    logger.info(f"🔍 Screening {len(tickers_to_screen)} tickers")

    # 3. Fetch, score, and persist
    for ticker in tickers_to_screen[:max_tickers]:
        try:
            # Fetch fresh data
            screening = bridge.fetch_quality_screening(ticker)
            if not screening or not screening.get("gf_score"):
                stats["errors"] += 1
                continue

            # Save to vault for history
            vault.save_mcp_snapshot("fundamental/screening", ticker, screening)
            stats["screened"] += 1

            # Score
            candidate = engine.score_candidate(screening)

            # Detect buy-zone entry (new alert)
            was_watching = ticker in current_tickers
            prev = next((c for c in current if c.ticker == ticker), None)

            if candidate.is_in_buy_zone():
                if not prev or prev.status != "BUY_ZONE":
                    alert = {
                        "type": "BUY_ZONE_ENTRY",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "price": candidate.current_price,
                        "fair_value": candidate.fair_value,
                        "buy_zone": f"${candidate.buy_zone_low:.2f}-${candidate.buy_zone_high:.2f}",
                    }
                    candidate.alerts.append(alert)
                    stats["buy_zone_alerts"] += 1
                    logger.info(
                        f"🎯 BUY ZONE: {ticker} at ${candidate.current_price:.2f} "
                        f"(zone: ${candidate.buy_zone_low:.2f}-${candidate.buy_zone_high:.2f}, "
                        f"fair: ${candidate.fair_value:.2f})"
                    )

            if not was_watching:
                stats["new_candidates"] += 1

            # Persist
            store.upsert_quality(candidate)
            stats["updated"] += 1

        except Exception as e:
            logger.warning(f"  {ticker} surveillance failed: {e}")
            stats["errors"] += 1

    vault.close()
    logger.info(
        f"✅ Surveillance complete: {stats['screened']} screened, "
        f"{stats['updated']} updated, {stats['buy_zone_alerts']} buy-zone alerts"
    )
    return stats


if __name__ == "__main__":
    result = run_quality_surveillance(max_tickers=5)
    print(f"\n{'='*50}")
    print(f"Quality Surveillance Results:")
    for k, v in result.items():
        print(f"  {k}: {v}")
