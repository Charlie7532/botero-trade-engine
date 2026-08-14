#!/usr/bin/env python3
"""
Master Orchestrator — Retrain All 10 METAR Stations V3 Dual-Layer Fact Stores
========================================================================================
Sequentially executes all station trainers to generate V3 Dual-Layer Fact Stores
with Standard Layer (forward bar returns), Kinematic Layer (SPY ZigZag legs),
and Structural Momentum (MIN->MIN / MAX->MAX accumulated returns).

Rule 26 Compliant: Preserves 100% of station-specific domain physics (pivots, overrides, thresholds).

Usage:
    python -m backend.scripts.generate_all_150_state_fact_stores
"""
import sys
import logging
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.scripts.generate_vix_fact_table import main as retrain_vix
from backend.scripts.generate_vvix_fact_table import main as retrain_vvix
from backend.scripts.generate_pcr_fact_table import main as retrain_pcr
from backend.scripts.generate_fg_fact_table import main as retrain_fg
from backend.scripts.generate_sv5_turbulence_fact_table import main as retrain_sv5_turbulence
from backend.scripts.generate_skew_fact_table import main as retrain_skew
from backend.scripts.generate_credit_fact_table import main as retrain_credit
from backend.scripts.generate_yield_curve_fact_table import main as retrain_yield_curve
from backend.scripts.generate_rotation_fact_table import main as retrain_rotation
from backend.scripts.generate_bsi_fact_table import main as retrain_bsi

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MasterV3Orchestrator")


def generate_all():
    logger.info("🚀 Starting Master V3 Dual-Layer Retraining across all 10 METAR stations...")

    trainers = [
        ("VIX", retrain_vix),
        ("VVIX", retrain_vvix),
        ("PCR", retrain_pcr),
        ("FG", retrain_fg),
        ("SV5_TURBULENCE", retrain_sv5_turbulence),
        ("SKEW", retrain_skew),
        ("CREDIT", retrain_credit),
        ("YIELD_CURVE", retrain_yield_curve),
        ("ROTATION", retrain_rotation),
        ("BSI", retrain_bsi),
    ]

    for name, trainer_fn in trainers:
        logger.info(f"► Retraining Station: {name}...")
        try:
            trainer_fn()
            logger.info(f"✅ Station {name} completed successfully.")
        except Exception as e:
            logger.error(f"❌ Error retraining station {name}: {e}", exc_info=True)

    logger.info("🎉 ✅ ALL 10 METAR Stations retrained cleanly into V3 Dual-Layer Fact Stores!")


if __name__ == "__main__":
    generate_all()
