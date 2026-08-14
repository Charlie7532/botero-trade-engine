#!/usr/bin/env python3
"""
Generate Empirical Sector Rotation Fact Store Table — V3 Dual-Layer Architecture
=============================================================================
Sector Rotation Index z(XLY/XLP) + z(XLK/XLU) measuring Risk-on vs Defensive positioning.
Usage:
    python -m backend.scripts.generate_rotation_fact_table
"""
import sys
import pandas as pd
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.scripts.v3_fact_table_engine import build_v3_dual_layer_fact_store

OUTPUT_PATH = root_dir / "backend/modules/entry_decision/domain/rules/rotation_fact_store.json"
D1_LABELS = ["DEFENSIVE_CAPITULATION", "DEFENSIVE", "NEUTRAL_ROTATION", "BALANCED", "CYCLICAL_LEADERSHIP", "AGGRESSIVE_ROTATION"]

ROTATION_PIVOT_OVERRIDES = {
    "FALLING_KNIFE": {
        "guidance": "STK_TRIM_TACTICAL",
        "regime": "STRUCTURAL_BULL_PULLBACK",
    },
    "FLOOR_CONFIRMED": {
        "guidance": "STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION",
        "regime": "FULL_CONVERGENT_BULL",
    },
}


def rotation_pivot_fn(df: pd.DataFrame) -> pd.Series:
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
        elif val <= min_val + 0.1 and diff_val <= 0:
            pivots.append("FALLING_KNIFE")
        elif prev_val <= min_val + 0.1 and diff_val > 0:
            pivots.append("FLOOR_CONFIRMED")
        elif val >= max_val - 0.1 and diff_val >= 0:
            pivots.append("BLOW_OFF_TOP")
        else:
            pivots.append("STABLE_CONTINUATION")
    return pd.Series(pivots, index=df.index)


def main():
    build_v3_dual_layer_fact_store(
        station_name="rotation",
        ticker="ROTATION_INDEX",
        model_purpose="Sector Rotation Index Harmonized V3 Dual-Layer Fact Store.",
        d1_labels=D1_LABELS,
        pivot_fn=rotation_pivot_fn,
        pivot_overrides=ROTATION_PIVOT_OVERRIDES,
        intermarket_notes={
            "risk_on": "Cyclical / Tech Leadership (XLY/XLP + XLK/XLU > 0)",
            "risk_off": "Defensive / Utility Leadership (XLY/XLP + XLK/XLU < 0)",
        },
        output_path=OUTPUT_PATH,
    )


if __name__ == "__main__":
    main()
