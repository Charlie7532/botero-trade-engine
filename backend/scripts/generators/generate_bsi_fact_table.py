#!/usr/bin/env python3
"""
Generate Empirical Breadth Sector Index (BSI / S5TW) Fact Store Table — V3 Dual-Layer Architecture
=============================================================================
Tactical Breadth station measuring % S&P 500 stocks above 20-day MA.
Usage:
    python -m backend.scripts.generate_bsi_fact_table
"""
import sys
import pandas as pd
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.scripts._lib.v3_fact_table_engine import build_v3_dual_layer_fact_store

OUTPUT_PATH = root_dir / "modules/entry_decision/domain/rules/bsi_fact_store.json"
D1_LABELS = ["BREADTH_WASHED_OUT", "OVERSOLD_BREADTH", "NEUTRAL_LOW_BREADTH", "NEUTRAL_HIGH_BREADTH", "EXPANSIVE_BREADTH", "HYPER_EXPANSIVE_BREADTH"]

BSI_PIVOT_OVERRIDES = {
    "BREADTH_THRUST": {
        "guidance": "STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION",
        "regime": "FULL_CONVERGENT_BULL",
    },
    "BREADTH_COLLAPSE": {
        "guidance": "STK_BLOCK_CRISIS",
        "regime": "FULL_CONVERGENT_BEAR",
    },
}


def bsi_pivot_fn(df: pd.DataFrame) -> pd.Series:
    v = df["val"]
    d5 = v.diff(5)

    pivots = []
    for i in range(len(df)):
        val = v.iloc[i]
        diff5 = d5.iloc[i]

        if pd.isna(val) or pd.isna(diff5):
            pivots.append("STABLE_CONTINUATION")
        elif diff5 >= 20.0:
            pivots.append("BREADTH_THRUST")
        elif diff5 <= -20.0:
            pivots.append("BREADTH_COLLAPSE")
        else:
            pivots.append("STABLE_CONTINUATION")
    return pd.Series(pivots, index=df.index)


def main():
    build_v3_dual_layer_fact_store(
        station_name="bsi",
        ticker="S5TW",
        model_purpose="Breadth Sector Index (S5TW) Harmonized V3 Dual-Layer Fact Store.",
        d1_labels=D1_LABELS,
        pivot_fn=bsi_pivot_fn,
        pivot_overrides=BSI_PIVOT_OVERRIDES,
        intermarket_notes={
            "breadth_thrust": "S5TW +20pp Surge in 5d -> Powerful Breadth Thrust Buy Signal",
            "breadth_washout": "S5TW < 15% -> Washed Out Oversold Breadth",
        },
        output_path=OUTPUT_PATH,
    )


if __name__ == "__main__":
    main()
