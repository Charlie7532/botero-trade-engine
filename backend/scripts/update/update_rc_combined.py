#!/usr/bin/env python3
"""
Update RC Combined Table — Full Pipeline
==========================================
Single script that runs the COMPLETE data refresh and model rebuild:

  Step 1: Backfill Feature Lake (engine.channel_snapshots)
          Computes ChannelSnapshot for all bars of all tickers.
          Includes Triple Regression, Triple VWAP, RSI, Kalman.
          Idempotent: skips tickers already backfilled.

  Step 2: Backfill Zigzag Points (engine.zigzag_points)
          Canonical zigzag at 2.5%, 5%, 7.5% levels.
          Idempotent: skips existing (ticker, level) combos.

  Step 3: Backfill Unified Observer (obs_* columns)
          Adds obs_recovery_score, obs_velocity_norm, obs_state
          to channel_snapshots where missing.

  Step 4: Retrain rc_combined_probability_table.json
          T(6)×C(6)×σVw(5) = 180 L1 states from ALL Vault data.

  Step 5: Generate rc_combined_derived.json
          Self-documenting 180-state table with committee signals.

Both table outputs written to:
  backend/modules/quality_swing/domain/rules/

Usage:
  # Full pipeline (all 5 steps):
  PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
    backend/scripts/update/update_rc_combined.py

  # Tables only (skip feature lake updates):
  PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
    backend/scripts/update/update_rc_combined.py --skip-lake

  # Derive only (regenerate from existing raw table):
  PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
    backend/scripts/update/update_rc_combined.py --only-derive

  # Background (nohup):
  nohup bash -c 'PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
    backend/scripts/update/update_rc_combined.py' \
    > /tmp/update_rc_combined.log 2>&1 &
"""
import argparse
import importlib.util
import json
import logging
import sys
import time
from pathlib import Path

# ── Project setup ──
ROOT = Path(__file__).resolve().parent.parent.parent.parent  # botero-trade/
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("update_rc_combined")

# ── Paths ──
RULES_DIR = ROOT / "backend/modules/quality_swing/domain/rules"
RAW_TABLE = RULES_DIR / "rc_combined_probability_table.json"
DERIVED_TABLE = RULES_DIR / "rc_combined_derived.json"
SCRIPTS_DIR = ROOT / "backend/scripts"


# ═══════════════════════════════════════════════════════════════
# Step runners
# ═══════════════════════════════════════════════════════════════

def _run_script(name: str, script_path: Path):
    """Import and execute a script's main() function."""
    spec = importlib.util.spec_from_file_location(name, str(script_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()


def step1_backfill_feature_lake():
    """Step 1: Backfill engine.channel_snapshots (Feature Lake).

    Reads:  market.ohlcv_bars (Vault)
    Writes: engine.channel_snapshots (Triple RC + RSI + Kalman)

    Idempotent: skips tickers already present. Re-runnable.
    Expected time: ~2-5 min for incremental, ~30 min for full universe.
    """
    logger.info("=" * 90)
    logger.info("  STEP 1: Backfill Feature Lake (engine.channel_snapshots)")
    logger.info("  Source: market.ohlcv_bars → compute_channel_snapshot + RSI + Kalman")
    logger.info("=" * 90)

    script = SCRIPTS_DIR / "backfill_channel_snapshots.py"
    if not script.exists():
        raise RuntimeError(f"Step 1: Script not found: {script}")

    _run_script("backfill_channel_snapshots", script)
    logger.info("  ✅ Step 1 complete: Feature Lake updated")


def step2_backfill_zigzag():
    """Step 2: Backfill engine.zigzag_points.

    Reads:  market.ohlcv_bars (Vault)
    Writes: engine.zigzag_points (3 levels: 2.5%, 5%, 7.5%)

    Idempotent: skips existing (ticker, level) combos.
    Expected time: ~2-5 min incremental, ~20 min full.
    """
    logger.info("\n" + "=" * 90)
    logger.info("  STEP 2: Backfill Zigzag Points (engine.zigzag_points)")
    logger.info("  Source: market.ohlcv_bars → canonical zigzag (2.5%, 5%, 7.5%)")
    logger.info("=" * 90)

    script = SCRIPTS_DIR / "backfill_zigzag_points.py"
    if not script.exists():
        raise RuntimeError(f"Step 2: Script not found: {script}")

    _run_script("backfill_zigzag_points", script)
    logger.info("  ✅ Step 2 complete: Zigzag points updated")


def step3_backfill_observer():
    """Step 3: Backfill Unified Observer (obs_* columns).

    Reads:  engine.channel_snapshots (sigma_current, vwap_sigma_wave)
    Writes: engine.channel_snapshots (obs_recovery_score, obs_velocity_norm, obs_state)

    Only processes tickers where obs_recovery_score IS NULL.
    Expected time: ~2-5 min incremental.
    """
    logger.info("\n" + "=" * 90)
    logger.info("  STEP 3: Backfill Unified Observer (obs_* columns)")
    logger.info("  Source: engine.channel_snapshots → UnifiedKalmanObserver")
    logger.info("=" * 90)

    script = SCRIPTS_DIR / "backfill_unified_observer.py"
    if not script.exists():
        raise RuntimeError(f"Step 3: Script not found: {script}")

    _run_script("backfill_unified_observer", script)
    logger.info("  ✅ Step 3 complete: Observer columns backfilled")


def step4_retrain():
    """Step 4: Retrain rc_combined_probability_table.json.

    Reads:  engine.channel_snapshots + engine.zigzag_points (Vault)
    Writes: rc_combined_probability_table.json (180 L1 cells + L2 + L3)
            rc_zigzag_audit.json (pivot-state coincidence audit)

    Expected time: ~3-8 min.
    """
    logger.info("\n" + "=" * 90)
    logger.info("  STEP 4: Retrain rc_combined_probability_table.json")
    logger.info("  Source: Vault (engine.channel_snapshots + engine.zigzag_points)")
    logger.info("=" * 90)

    script = SCRIPTS_DIR / "train_combined_table.py"
    if not script.exists():
        raise RuntimeError(f"Step 4: Script not found: {script}")

    _run_script("train_combined_table", script)

    if not RAW_TABLE.exists():
        raise RuntimeError(f"Step 4 FAILED: {RAW_TABLE} not found after training")

    size_kb = RAW_TABLE.stat().st_size / 1024
    logger.info(f"  ✅ Step 4 complete: {RAW_TABLE.name} ({size_kb:.0f} KB)")


def step5_derive():
    """Step 5: Generate rc_combined_derived.json.

    Reads:  rc_combined_probability_table.json (from Step 4)
    Writes: rc_combined_derived.json (180 states, committee signals)

    Expected time: ~5 seconds.
    """
    logger.info("\n" + "=" * 90)
    logger.info("  STEP 5: Generate rc_combined_derived.json")
    logger.info("  Source: rc_combined_probability_table.json")
    logger.info("=" * 90)

    if not RAW_TABLE.exists():
        raise RuntimeError(f"Step 5: {RAW_TABLE} not found. Run Step 4 first.")

    script = SCRIPTS_DIR / "generate_derived_table.py"
    if not script.exists():
        raise RuntimeError(f"Step 5: Script not found: {script}")

    _run_script("generate_derived_table", script)

    if not DERIVED_TABLE.exists():
        raise RuntimeError(f"Step 5 FAILED: {DERIVED_TABLE} not found after generation")

    size_kb = DERIVED_TABLE.stat().st_size / 1024
    logger.info(f"  ✅ Step 5 complete: {DERIVED_TABLE.name} ({size_kb:.0f} KB)")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Update RC Combined Table — Full Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Step reference:
  Step 1: Backfill Feature Lake    (~2-30 min)
  Step 2: Backfill Zigzag Points   (~2-20 min)
  Step 3: Backfill Unified Observer (~2-5 min)
  Step 4: Retrain probability table (~3-8 min)
  Step 5: Generate derived table    (~5 sec)

Examples:
  # Full pipeline (all 5 steps):
  python backend/scripts/update/update_rc_combined.py

  # Tables only (Steps 4+5, skip feature lake updates):
  python backend/scripts/update/update_rc_combined.py --skip-lake

  # Feature lake only (Steps 1+2+3, no table generation):
  python backend/scripts/update/update_rc_combined.py --only-lake

  # Derive only (Step 5, regenerate from existing raw table):
  python backend/scripts/update/update_rc_combined.py --only-derive
        """,
    )
    parser.add_argument("--skip-lake", action="store_true",
                        help="Skip Steps 1-3 (feature lake + zigzag + observer)")
    parser.add_argument("--only-lake", action="store_true",
                        help="Only run Steps 1-3 (update feature lake, skip table generation)")
    parser.add_argument("--only-derive", action="store_true",
                        help="Only run Step 5 (regenerate derived from existing raw table)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan without executing")
    args = parser.parse_args()

    t0 = time.time()

    # ── Build step plan ──
    ALL_STEPS = [
        ("Step 1", "Backfill Feature Lake (channel_snapshots)", step1_backfill_feature_lake),
        ("Step 2", "Backfill Zigzag Points (3 levels)", step2_backfill_zigzag),
        ("Step 3", "Backfill Unified Observer (velocities)", step3_backfill_observer),
        ("Step 4", "Retrain rc_combined_probability_table.json", step4_retrain),
        ("Step 5", "Generate rc_combined_derived.json", step5_derive),
    ]

    if args.only_derive:
        steps = ALL_STEPS[4:]  # Step 5 only
    elif args.only_lake:
        steps = ALL_STEPS[:3]  # Steps 1-3
    elif args.skip_lake:
        steps = ALL_STEPS[3:]  # Steps 4-5
    else:
        steps = ALL_STEPS  # All 5

    # ── Print banner ──
    logger.info("╔" + "═" * 88 + "╗")
    logger.info("║  RC COMBINED TABLE — UPDATE PIPELINE" + " " * 51 + "║")
    logger.info("╠" + "═" * 88 + "╣")

    for name, desc, _ in ALL_STEPS:
        active = any(n == name for n, _, _ in steps)
        marker = "▶" if active else "○"
        tag = "" if active else " (SKIPPED)"
        line = f"║  {marker} {name}: {desc}{tag}"
        logger.info(f"{line:<89}║")

    logger.info("╠" + "═" * 88 + "╣")
    logger.info(f"║  Output dir: {str(RULES_DIR)[-74:]:<74}║")
    logger.info("╚" + "═" * 88 + "╝")

    if args.dry_run:
        logger.info("\n  DRY RUN — would execute:")
        for name, desc, _ in steps:
            logger.info(f"    {name}: {desc}")
        return

    # ── Execute pipeline ──
    completed = []
    for name, desc, fn in steps:
        step_t0 = time.time()
        try:
            fn()
            elapsed_step = time.time() - step_t0
            completed.append((name, desc, elapsed_step))
        except Exception as e:
            logger.error(f"\n  ❌ {name} FAILED after {time.time() - step_t0:.1f}s: {e}")
            logger.error(f"  Completed steps: {[n for n, _, _ in completed]}")
            raise

    elapsed = time.time() - t0

    # ── Final summary ──
    logger.info("\n" + "=" * 90)
    logger.info(f"  ✅ PIPELINE COMPLETE — {elapsed:.1f}s ({elapsed/60:.1f} min)")
    logger.info("")

    for name, desc, dt in completed:
        logger.info(f"    {name}: {desc} ({dt:.1f}s)")

    # Show derived table summary if it exists
    if DERIVED_TABLE.exists():
        try:
            with open(DERIVED_TABLE) as f:
                d = json.load(f)
            states = d.get("states", {})
            from collections import Counter
            sigs = Counter(s["identity"]["signal"] for s in states.values())
            logger.info("")
            logger.info(f"  Derived table: {len(states)} states")
            logger.info(f"  Signals: {dict(sigs.most_common())}")
            logger.info(f"  Version: {d.get('version', 'unknown')}")
            n_obs = d.get("context", {}).get("n_observations", 0)
            n_tickers = d.get("context", {}).get("n_tickers", 0)
            logger.info(f"  Training data: {n_obs:,} bars from {n_tickers} tickers")
        except Exception:
            pass

    logger.info("=" * 90)


if __name__ == "__main__":
    main()
