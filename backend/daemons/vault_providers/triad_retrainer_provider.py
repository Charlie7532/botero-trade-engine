"""
Triad Retrainer Provider — Vault Daemon (Weekly Execution)
=============================================================
Automatically re-trains the S5 and S5V Triad Conditional Probability
and Relative Modifier matrices every weekend (or when > 7 days old).

Artifacts re-generated:
  1. s5_triad_table.json & s5_relative_modifier.json
  2. s5v_triad_table.json & s5v_relative_modifier.json

Integrates seamlessly with the Vault Daemon pipeline.
"""
import logging, os, time, subprocess, sys
from datetime import datetime, UTC, timedelta

from backend.daemons.vault_providers import register_provider
from backend.daemons.data_vault_daemon import _already_vaulted_today
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger(__name__)

# Paths to triad JSON artifacts
TRIAD_DIR = "/root/botero-trade/backend/modules/entry_decision/domain/rules"
S5V_JSON = os.path.join(TRIAD_DIR, "s5v_triad_table.json")
S5_JSON = os.path.join(TRIAD_DIR, "s5_triad_table.json")


def _is_retrain_due() -> bool:
    """Check if retraining is due (Sunday OR any JSON artifact > 7 days old)."""
    now = datetime.now(UTC)
    # Sunday is weekday 6
    if now.weekday() == 6:
        return True
    
    # Check modification time of files
    for json_path in (S5V_JSON, S5_JSON):
        if not os.path.exists(json_path):
            return True
        mtime = datetime.fromtimestamp(os.path.getmtime(json_path), UTC)
        if (now - mtime) > timedelta(days=7):
            return True
            
    return False


class TriadRetrainerProvider:
    """Vault provider for weekly automatic retraining of S5 and S5V triad matrices."""

    name = "triad_retraining"
    categories = ["triad_retraining"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        """Run weekly retraining if due."""
        if not _is_retrain_due():
            logger.info("🧠 Triad Retraining: Not due today (runs Sundays or when >7 days old) — skipping")
            return {"status": "skipped", "reason": "not_due"}

        if _already_vaulted_today(store, "macro/triad_retraining", "WEEKLY_DONE"):
            logger.info("🧠 Triad Retraining already completed today — skipping")
            return {"status": "skipped", "reason": "already_today"}

        return self._execute_retraining(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        """Retraining requires global data — delegates to run_full."""
        return self.run_full(store)

    def _execute_retraining(self, store: TimescaleDataStore) -> dict:
        """Executes train_s5_triad.py and train_s5v_triad.py in subprocesses."""
        logger.info("🧠 Triad Retraining: Starting weekly training of S5 & S5V matrices...")
        t0 = time.time()
        
        try:
            # 1. Retrain S5 Price Triad
            res_s5 = subprocess.run(
                [sys.executable, "/root/botero-trade/backend/scripts/train_s5_triad.py"],
                cwd="/root/botero-trade",
                capture_output=True,
                text=True,
                timeout=300,
            )
            if res_s5.returncode != 0:
                logger.error(f"S5 Triad retraining failed: {res_s5.stderr[:200]}")
                return {"status": "error", "error": res_s5.stderr[:200]}
                
            # 2. Retrain S5V Volume Triad
            res_s5v = subprocess.run(
                [sys.executable, "/root/botero-trade/backend/scripts/train_s5v_triad.py"],
                cwd="/root/botero-trade",
                capture_output=True,
                text=True,
                timeout=300,
            )
            if res_s5v.returncode != 0:
                logger.error(f"S5V Triad retraining failed: {res_s5v.stderr[:200]}")
                return {"status": "error", "error": res_s5v.stderr[:200]}

            # Mark idempotency guard for today
            store.save_mcp_snapshot("macro/triad_retraining", "WEEKLY_DONE", {
                "s5_success": True,
                "s5v_success": True,
                "timestamp": datetime.now(UTC).isoformat(),
            })

            elapsed = time.time() - t0
            logger.info(f"✅ Triad Retraining: S5 and S5V matrices updated successfully in {elapsed:.1f}s")
            return {"status": "ok", "elapsed_seconds": elapsed}

        except Exception as e:
            logger.warning(f"Triad Retraining daemon failed (non-critical): {e}")
            return {"status": "error", "error": str(e)}


register_provider(TriadRetrainerProvider())
