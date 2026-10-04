"""
Master Retrain & Update Pipeline Orchestrator (Ruta de Actualización)
========================================================================
Single source of truth pipeline that guarantees future reproducibility,
data integrity, and automated retraining across all 6 core steps:

  Step 1: Rebuild all breadth history with daily-provider parity (rebuild_breadth_history.py):
          global S5/SV5/BSI/SV5_TURBULENCE, sector S5/SV5/S5CAP/VBI, S5_QQQ/SV5_QQQ,
          CREDIT_RATIO, ROTATION_INDEX. Constituent OHLCV is owned by the vault daemon.
  Step 5: Backfill individual Feature Lake channel snapshots (engine.channel_snapshots)
  Step 6: Re-train conditional probability JSON artifacts & relative Z-score modifiers
  Step 7: Run full pytest verification suite

Usage:
  source backend/.venv/bin/activate
  PYTHONPATH=. python3 backend/scripts/master_retrain_pipeline.py [--skip-lake]
"""

import os
import sys
import logging
import time
import subprocess
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

PIPELINE_PREREQUISITES = {
    "step_1_breadth_rebuild": "python3 backend/scripts/backfills/rebuild_breadth_history.py",
    "step_5_feature_lake_snapshots": "python3 backend/scripts/backfills/backfill_channel_snapshots_v2.py",
    "step_6a_s5v_triad_training": "python3 backend/scripts/trainers/train_s5v_triad.py",
    "step_6b_s5_triad_training": "python3 backend/scripts/trainers/train_s5_triad.py",
    "step_6c_fusion_stereotypes": "python3 backend/scripts/research/analyze_fusion_stereotypes.py",
    "step_6d_rc_tables_training": "python3 backend/scripts/retrain_tables.py",
    "master_orchestrator": "python3 backend/scripts/master_retrain_pipeline.py",
    "validation_suite": "PYTHONPATH=. pytest",
}

def run_step(step_name: str, cmd: str):
    logging.info(f"\n" + "="*80)
    logging.info(f"  [PIPELINE STEP] {step_name.upper()}")
    logging.info(f"  Command: {cmd}")
    logging.info("="*80)
    t0 = time.time()
    res = subprocess.run(cmd, shell=True, env=dict(os.environ, PYTHONPATH="."))
    if res.returncode != 0:
        logging.error(f"❌ Step '{step_name}' failed with exit code {res.returncode}")
        sys.exit(res.returncode)
    logging.info(f"✅ Step '{step_name}' completed in {time.time()-t0:.1f}s.")

def main():
    skip_lake = "--skip-lake" in sys.argv
    logging.info("🚀 Starting Master Retrain & Update Pipeline...")
    t_start = time.time()
    
    # Step 1: Breadth history rebuild (single writer, daily-provider parity)
    run_step("Step 1: Breadth History Rebuild", "python3 backend/scripts/backfills/rebuild_breadth_history.py")
    
    # Step 5: Feature Lake Channel Snapshots (Optional skip for fast retrain)
    if not skip_lake:
        run_step("Step 5: Feature Lake Channel Snapshots", "python3 backend/scripts/backfills/backfill_channel_snapshots_v2.py")
    else:
        logging.info("⏩ Skipping Step 5 (--skip-lake specified)")
        
    # Step 6: Retrain S5V, S5 Triad, Fusion Stereotypes & RC Combined/Wave JSON Tables
    run_step("Step 6a: Retrain S5V Triad JSON Table", "python3 backend/scripts/trainers/train_s5v_triad.py")
    run_step("Step 6b: Retrain S5 Triad JSON Table", "python3 backend/scripts/trainers/train_s5_triad.py")
    run_step("Step 6c: Retrain S5 x SV5 Fusion Stereotypes JSON Table", "python3 backend/scripts/research/analyze_fusion_stereotypes.py")
    run_step("Step 6d: Retrain RC Combined & Wave Tables (Quality Swing)", "python3 backend/scripts/retrain_tables.py")
    
    # Step 7: Validation Suite
    run_step("Step 7: Pytest Unit & Integration Suite", "pytest")
    
    logging.info(f"\n🎉 MASTER RETRAIN PIPELINE COMPLETED IN {time.time()-t_start:.1f}s!")

if __name__ == "__main__":
    main()
