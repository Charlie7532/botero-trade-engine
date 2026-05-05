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
    """Pre-fetch Unusual Whales flow data for speculative scanning and vault it."""
    try:
        from backend.modules.flow_intelligence.infrastructure.uw_mcp_bridge import UWDataBridge
        from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
        from backend.modules.simulation.infrastructure.vault_interceptor import VaultInterceptor
        from dataclasses import asdict

        uw = build_flow_data()
        
        bridge = UWDataBridge()
        if not bridge.is_configured():
            logger.warning("UW_API_KEY not configured — mocking flow data")
            return {}

        store = TimescaleDataStore()
        interceptor = VaultInterceptor(store)

        # 1. Fetch & Vault SPY Flow
        spy_ticks = bridge.fetch_spy_flow()
        interceptor.intercept_spy_flow(spy_ticks)
        spy_gate = uw.parse_spy_macro_gate(spy_ticks)

        # 2. Fetch & Vault Market Tide
        tide_data = bridge.fetch_market_tide()
        interceptor.intercept_market_tide(tide_data)
        market_tide = uw.parse_market_tide(tide_data)

        # 3. Fetch & Vault Market Sentiment (flow alerts)
        all_alerts = bridge.fetch_flow_alerts(limit=200)
        sentiment = uw.parse_market_sentiment(all_alerts)
        interceptor.intercept_sentiment(asdict(sentiment))

        logger.info(f"UW pre-fetch complete: SPY gate={spy_gate.signal}, tide={market_tide.tide_direction}, sentiment={sentiment.regime}")
        return {
            "spy_gate": spy_gate,
            "market_tide": market_tide,
            "sentiment": sentiment,
            "all_alerts": all_alerts,
        }
    except Exception as e:
        logger.warning(f"UW pre-fetch failed (non-fatal): {e}")
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
