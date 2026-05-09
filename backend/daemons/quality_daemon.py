import time
import logging
import argparse
from datetime import datetime, UTC
from backend.api.factories.execution_factory import (
    build_orchestrator, synthesize_live_mandate, build_finnhub,
)
from backend.modules.execution.application.use_cases.orchestrate_scans import ScanOrchestrator
from backend.modules.portfolio_management.application.use_cases.cio_orchestrator import CIOOrchestrator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("QualityDaemon")

def _prefetch_guru_data(tickers: list[str]) -> dict:
    """Pre-fetch GuruFocus data for quality candidates via MCP bridge."""
    try:
        from backend.modules.portfolio_management.infrastructure.gurufocus_mcp_bridge import GuruFocusMCPBridge
        bridge = GuruFocusMCPBridge()
        data = {}
        for t in tickers[:20]:  # Cap to avoid rate limits
            try:
                screening = bridge.fetch_quality_screening(t)
                if screening:
                    data[t] = screening
            except Exception as e:
                logger.debug(f"GuruFocus fetch failed for {t}: {e}")
        logger.info(f"GuruFocus pre-fetch: {len(data)}/{len(tickers)} tickers")
        return data
    except ImportError:
        logger.warning("GuruFocus MCP bridge not available, skipping pre-fetch")
        return {}

def run(loop_seconds: int = 86400):
    logger.info("Initializing Quality Daemon (Hohn/Munger Mode)...")
    paper_orchestrator = build_orchestrator()
    cio = CIOOrchestrator()
    scanner = ScanOrchestrator(paper_orchestrator, cio)
    
    while True:
        try:
            logger.info(f"[{datetime.now(UTC).isoformat()}] Running Quality Scan...")
            
            # 1. Synthesize live CIO mandate (FRED + VIX + Rotation)
            mandate = synthesize_live_mandate(cio)
            logger.info(
                f"CIO Mandate: {mandate.regime} | "
                f"Q={mandate.quality_budget_pct*100:.0f}% "
                f"S={mandate.speculative_budget_pct*100:.0f}%"
            )
            
            # 2. Pre-fetch GuruFocus data for guru gems
            guru_data = _prefetch_guru_data(["AAPL", "MSFT", "GOOGL", "BRK-B", "V"])
            
            # 3. Pre-fetch Finnhub macro sentiment
            finnhub = build_finnhub()
            macro_sentiment = 0.0
            try:
                spy_intel = finnhub.get_ticker_intelligence("SPY")
                macro_sentiment = (spy_intel.get("conviction_score", 50) - 50) / 50
            except Exception:
                pass
            
            # 4. Run quality scan with pre-fetched data
            result = scanner.run_quality_scan(
                guru_mcp_data=guru_data,
            )
            logger.info(f"Scan complete: {result}")
        except Exception as e:
            logger.error(f"Error during quality scan: {e}")
            
        if loop_seconds <= 0:
            break
            
        logger.info(f"Sleeping for {loop_seconds} seconds (next run tomorrow)...")
        time.sleep(loop_seconds)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Botero Trade Quality Daemon")
    parser.add_argument("--loop", type=int, default=86400, help="Loop interval in seconds (default 86400 - 1 day)")
    args = parser.parse_args()
    run(loop_seconds=args.loop)
