import time
import logging
import argparse
from datetime import datetime, UTC
from backend.api.factories.execution_factory import build_orchestrator
from backend.modules.execution.application.use_cases.orchestrate_scans import ScanOrchestrator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SpeculativeDaemon")

def run(loop_seconds: int = 300):
    logger.info("Initializing Speculative Daemon (Eifert/PTJ Mode)...")
    paper_orchestrator = build_orchestrator()
    scanner = ScanOrchestrator(paper_orchestrator)
    
    while True:
        try:
            logger.info(f"[{datetime.now(UTC).isoformat()}] Running Speculative Scan...")
            # En la versión final, aquí se inyectan los datos en vivo de Unusual Whales
            # Por ahora, el scanner usa sus fallbacks internos
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
