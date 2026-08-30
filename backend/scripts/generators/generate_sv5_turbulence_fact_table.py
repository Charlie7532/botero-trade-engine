#!/usr/bin/env python3
"""
Generate Empirical SV5 Turbulence Fact Store Table — V3 Dual-Layer Architecture
=============================================================================
Institutional volume turbulence metric measuring erratic changes in volume dynamics.
Usage:
    python -m backend.scripts.generate_sv5_turbulence_fact_table
"""
import sys
import pandas as pd
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.scripts._lib.v3_fact_table_engine import build_v3_dual_layer_fact_store

OUTPUT_PATH = root_dir / "modules/entry_decision/domain/rules/sv5_turbulence_fact_store.json"
D1_LABELS = ["EXTREME_CALM", "CALM", "NEUTRAL_CALM", "NEUTRAL_TURBULENT", "TURBULENT", "EXTREME_TURBULENT"]

TURB_PIVOT_OVERRIDES = {
    "VOL_CRUSH_REBOUND": {
        "guidance": "STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION",
        "regime": "FULL_CONVERGENT_BULL",
    },
    "PANIC_SPIKE_CAPITULATION": {
        "guidance": "STK_BLOCK_CRISIS",
        "regime": "FULL_CONVERGENT_BEAR",
    },
}


def turb_pivot_fn(df: pd.DataFrame) -> pd.Series:
    v = df["val"]
    mx5 = v.rolling(5).max()
    m5 = v.rolling(5).min()
    d1 = v.diff(1)

    pivots = []
    for i in range(len(df)):
        val = v.iloc[i]
        max_val = mx5.iloc[i]
        min_val = m5.iloc[i]
        diff_val = d1.iloc[i]
        prev_val = v.iloc[i - 1] if i > 0 else val

        if pd.isna(val) or pd.isna(min_val):
            pivots.append("STABLE_CONTINUATION")
        elif val >= max_val - 0.5 and diff_val >= 0:
            pivots.append("PANIC_SPIKE_CAPITULATION")
        elif prev_val >= max_val - 0.5 and diff_val < 0:
            pivots.append("VOL_CRUSH_REBOUND")
        elif val <= min_val + 0.5 and diff_val <= 0:
            pivots.append("COMPLACENCY_FLOOR")
        else:
            pivots.append("STABLE_CONTINUATION")
    return pd.Series(pivots, index=df.index)


def main():
    build_v3_dual_layer_fact_store(
        station_name="sv5_turbulence",
        ticker="SV5_TURBULENCE",
        model_purpose="SV5 Institutional Volume Turbulence Harmonized V3 Dual-Layer Fact Store.",
        d1_labels=D1_LABELS,
        pivot_fn=turb_pivot_fn,
        pivot_overrides=TURB_PIVOT_OVERRIDES,
        intermarket_notes={
            "turbulence_spike": "Institutional Volume Disruption > 10.0 -> Liquidity Stress",
        },
        output_path=OUTPUT_PATH,
    )


if __name__ == "__main__":
    main()
