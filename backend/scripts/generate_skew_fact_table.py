#!/usr/bin/env python3
"""
Generate Empirical CBOE SKEW Fact Store Table — V3 Dual-Layer Architecture
=============================================================================
CBOE SKEW Index measuring tail risk paranoia and OTM put buying intensity.
Usage:
    python -m backend.scripts.generate_skew_fact_table
"""
import sys
import pandas as pd
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.scripts.v3_fact_table_engine import build_v3_dual_layer_fact_store

OUTPUT_PATH = root_dir / "backend/modules/entry_decision/domain/rules/skew_fact_store.json"
D1_LABELS = ["LOW_TAIL_RISK", "NORMAL_TAIL_RISK", "ELEVATED_TAIL_RISK", "HIGH_TAIL_RISK", "TAIL_PARANOIA", "BLACK_SWAN_PARANOIA"]

SKEW_PIVOT_OVERRIDES = {
    "FALLING_KNIFE": {
        "guidance": "STK_BUY_DIP_TACTICAL",
        "regime": "TACTICAL_REBOUND_IN_BEAR",
    },
    "FLOOR_CONFIRMED": {
        "guidance": "STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION",
        "regime": "FULL_CONVERGENT_BULL",
    },
}


def skew_pivot_fn(df: pd.DataFrame) -> pd.Series:
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
        elif val >= max_val - 2.0 and diff_val >= 0:
            pivots.append("FALLING_KNIFE")
        elif prev_val >= max_val - 2.0 and diff_val < 0:
            pivots.append("FLOOR_CONFIRMED")
        elif val <= min_val + 2.0 and diff_val <= 0:
            pivots.append("BLOW_OFF_TOP")
        else:
            pivots.append("STABLE_CONTINUATION")
    return pd.Series(pivots, index=df.index)


def main():
    build_v3_dual_layer_fact_store(
        station_name="skew",
        ticker="SKEW",
        model_purpose="CBOE SKEW Index Harmonized V3 Dual-Layer Fact Store.",
        d1_labels=D1_LABELS,
        pivot_fn=skew_pivot_fn,
        pivot_overrides=SKEW_PIVOT_OVERRIDES,
        intermarket_notes={
            "skew_high": "SKEW > 140 -> Institutional OTM Put Hedging Active",
        },
        output_path=OUTPUT_PATH,
    )


if __name__ == "__main__":
    main()
