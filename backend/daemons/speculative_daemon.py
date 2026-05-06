import time
import logging
import argparse
from datetime import datetime, UTC
from backend.api.factories.execution_factory import (
    build_orchestrator, synthesize_live_mandate, build_flow_data,
)
from backend.modules.execution.application.use_cases.orchestrate_scans import ScanOrchestrator
from backend.modules.portfolio_management.application.use_cases.cio_orchestrator import CIOOrchestrator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SpeculativeDaemon")

def _prefetch_uw_data() -> dict:
    """Load latest UW flow data from Neon (populated by data_vault_daemon)."""
    try:
        from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
        from datetime import date

        uw = build_flow_data()
        store = TimescaleDataStore()
        today = date.today().isoformat()

        # Read from Neon instead of fetching from UW API
        spy_ticks = store.load_mcp_snapshot("flow/spy", "SPY", today) or []
        tide_data = store.load_mcp_snapshot("flow/tide", "MARKET", today) or []
        sentiment_data = store.load_mcp_snapshot("flow/sentiment", "MARKET", today) or {}

        spy_gate = uw.parse_spy_macro_gate(spy_ticks) if spy_ticks else None
        market_tide = uw.parse_market_tide(tide_data) if tide_data else None

        # Reconstruct sentiment from stored data
        from backend.modules.flow_intelligence.infrastructure.uw_adapter import MarketSentiment
        if sentiment_data:
            sentiment = MarketSentiment(**{k: v for k, v in sentiment_data.items() if k in MarketSentiment.__dataclass_fields__})
        else:
            sentiment = MarketSentiment()

        # Load market-wide alerts for downstream use
        all_alerts = store.load_mcp_snapshot("flow/alerts", "MARKET", today) or []

        logger.info(
            f"UW data loaded from Neon: SPY={'ok' if spy_gate else 'none'}, "
            f"tide={'ok' if market_tide else 'none'}, sentiment={sentiment.regime}, "
            f"alerts={len(all_alerts)}"
        )
        return {
            "spy_gate": spy_gate,
            "market_tide": market_tide,
            "sentiment": sentiment,
            "all_alerts": all_alerts,
        }
    except Exception as e:
        logger.warning(f"UW Neon load failed (non-fatal): {e}")
        return {}

def run(loop_seconds: int = 300):
    logger.info("Initializing Speculative Daemon (Eifert/PTJ Mode)...")
    paper_orchestrator = build_orchestrator()
    cio = CIOOrchestrator()
    scanner = ScanOrchestrator(paper_orchestrator, cio)
    
    while True:
        try:
            logger.info(f"[{datetime.now(UTC).isoformat()}] Running Speculative Scan...")
            
            # 1. Synthesize live CIO mandate (shared with quality)
            mandate = synthesize_live_mandate(cio)
            logger.info(
                f"CIO Mandate: {mandate.regime} | "
                f"S={mandate.speculative_budget_pct*100:.0f}%"
            )
            
            # 2. Pre-fetch UW flow data
            uw_data = _prefetch_uw_data()
            
            # 3. Run speculative scan
            result = scanner.run_speculative_scan()
            logger.info(f"Scan complete: {result}")
        except Exception as e:
            logger.error(f"Error during speculative scan: {e}")
            
        if loop_seconds <= 0:
            break
            
        logger.info(f"Sleeping for {loop_seconds} seconds...")
        time.sleep(loop_seconds)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Botero Trade Speculative Daemon")
    parser.add_argument("--loop", type=int, default=300, help="Loop interval in seconds (default 300)")
    args = parser.parse_args()
    run(loop_seconds=args.loop)
