#!/usr/bin/env python3
"""
Generate All Timing Fact Stores (Chronos Engine Producer)
==========================================================
Encapsulates and runs the canonical generator for all 11 METAR timing fact stores:
[vix, vvix, pcr, fg, sv5_turbulence, skew, credit, yield_curve, rotation, bsi, dxy].

Produces:
  backend/modules/entry_decision/domain/rules/*_timing_fact_store.json

Data Sources:
  - data/research/continuous_metar_lake.parquet
  - data/research/pivots/quants_obs.pkl (1584 clean canonical pivots)
"""
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

def main():
    script_path = ROOT / "research" / "01_señales_entry_exit" / "generar_timing_fact_stores.py"
    if not script_path.exists():
        raise FileNotFoundError(f"Canonical generator not found at: {script_path}")

    print("=" * 80)
    print("REGENERATING ALL 11 METAR TIMING FACT STORES (CHRONOS ENGINE)")
    print("=" * 80)
    cmd = [sys.executable, str(script_path), "--todas"]
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print(f"❌ Error generating timing fact stores (exit code {result.returncode})")
        sys.exit(result.returncode)
    print("\n✅ All 11 timing fact stores successfully generated.")

if __name__ == "__main__":
    main()
