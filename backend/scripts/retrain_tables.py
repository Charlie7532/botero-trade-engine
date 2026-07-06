#!/usr/bin/env python3
"""
Retrain All RC Tables — Production Pipeline
=============================================
Single entry point to regenerate all RC probability tables and their derived
versions. Runs the full pipeline:

  1. Combined: train_combined_table.py  → rc_combined_probability_table.json
  2. Combined: generate_derived_table.py → rc_combined_derived.json
  3. Wave:     train_wave_table.py       → rc_wave_probability_table.json
  4. Wave:     generate_wave_derived_table.py → rc_wave_derived.json

Usage:
  # Full retrain (both tables)
  PYTHONPATH=$(pwd) backend/.venv/bin/python backend/scripts/retrain_tables.py

  # Combined only
  PYTHONPATH=$(pwd) backend/.venv/bin/python backend/scripts/retrain_tables.py --combined

  # Wave only
  PYTHONPATH=$(pwd) backend/.venv/bin/python backend/scripts/retrain_tables.py --wave

  # Derived only (skip expensive training, just regenerate signals)
  PYTHONPATH=$(pwd) backend/.venv/bin/python backend/scripts/retrain_tables.py --derived-only

Data source: engine.channel_snapshots + engine.zigzag_points (Neon PostgreSQL)
Output:      backend/modules/quality_swing/domain/rules/*.json
"""
import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = ROOT / "backend" / "scripts"
VENV_PYTHON = ROOT / "backend" / ".venv" / "bin" / "python"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("retrain_tables")


def _run_script(name: str, script_path: Path) -> bool:
    """Run a training/generation script as a subprocess.

    Returns True on success, False on failure.
    """
    logger.info(f"{'─' * 70}")
    logger.info(f"  RUNNING: {name}")
    logger.info(f"  Script:  {script_path.relative_to(ROOT)}")
    logger.info(f"{'─' * 70}")

    t0 = time.time()
    env = {
        "PYTHONPATH": str(ROOT),
        "PATH": "/usr/bin:/bin:/usr/local/bin",
    }
    # Inherit POSTGRES_URL and other env vars from parent process
    import os
    for key in os.environ:
        if key not in env:
            env[key] = os.environ[key]

    result = subprocess.run(
        [str(VENV_PYTHON), str(script_path)],
        cwd=str(ROOT),
        env=env,
        capture_output=False,  # stream to stdout/stderr
    )

    elapsed = time.time() - t0
    if result.returncode == 0:
        logger.info(f"  ✅ {name} completed in {elapsed:.1f}s")
        return True
    else:
        logger.error(f"  ❌ {name} FAILED (exit code {result.returncode}) after {elapsed:.1f}s")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Retrain RC probability tables (Combined and/or Wave)."
    )
    parser.add_argument(
        "--combined", action="store_true",
        help="Retrain Combined table only (T×C×σVw)."
    )
    parser.add_argument(
        "--wave", action="store_true",
        help="Retrain Wave table only (W×σVc×σc×vel)."
    )
    parser.add_argument(
        "--derived-only", action="store_true",
        help="Skip training, only regenerate derived tables from existing raw."
    )
    args = parser.parse_args()

    # Default: run both if neither flag is set
    run_combined = args.combined or (not args.combined and not args.wave)
    run_wave = args.wave or (not args.combined and not args.wave)
    skip_training = args.derived_only

    t0 = time.time()
    logger.info("=" * 70)
    logger.info("  RETRAIN RC TABLES — Production Pipeline")
    logger.info(f"  Combined: {'YES' if run_combined else 'skip'}")
    logger.info(f"  Wave:     {'YES' if run_wave else 'skip'}")
    logger.info(f"  Training: {'SKIP (derived-only)' if skip_training else 'YES'}")
    logger.info("=" * 70)

    steps = []
    failures = []

    # ── Combined ──
    if run_combined:
        if not skip_training:
            steps.append(("Combined Train", SCRIPTS_DIR / "train_combined_table.py"))
        steps.append(("Combined Derived", SCRIPTS_DIR / "generate_derived_table.py"))

    # ── Wave ──
    if run_wave:
        if not skip_training:
            steps.append(("Wave Train", SCRIPTS_DIR / "train_wave_table.py"))
        steps.append(("Wave Derived", SCRIPTS_DIR / "generate_wave_derived_table.py"))

    for name, script in steps:
        if not script.exists():
            logger.error(f"  Script not found: {script}")
            failures.append(name)
            continue

        ok = _run_script(name, script)
        if not ok:
            failures.append(name)
            if "Train" in name:
                # If training fails, skip the derived step for that table
                logger.warning(f"  Skipping derived step due to training failure")
                break

    elapsed = time.time() - t0
    logger.info("\n" + "=" * 70)
    if failures:
        logger.error(f"  PIPELINE FAILED — {len(failures)} step(s) failed: {failures}")
        logger.info(f"  Total time: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    else:
        logger.info(f"  ✅ PIPELINE COMPLETE — all {len(steps)} steps succeeded")
        logger.info(f"  Total time: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    logger.info("=" * 70)

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
