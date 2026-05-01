import time
import logging
import argparse
from datetime import datetime, UTC
from backend.api.factories.execution_factory import build_orchestrator
from backend.modules.execution.application.use_cases.orchestrate_scans import ScanOrchestrator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("QualityDaemon")

def run(loop_seconds: int = 86400):
    logger.info("Initializing Quality Daemon (Hohn/Munger Mode)...")
    paper_orchestrator = build_orchestrator()
    scanner = ScanOrchestrator(paper_orchestrator)
    
    while True:
        try:
            logger.info(f"[{datetime.now(UTC).isoformat()}] Running Quality Scan...")
            # En la versión final, aquí se inyectan los datos de GuruFocus y SEC
            result = scanner.run_quality_scan()
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
