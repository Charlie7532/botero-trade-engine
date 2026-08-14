#!/usr/bin/env python3
"""
Generate Empirical CBOE Volatility Index (VIX) Fact Store Table — V3 Dual-Layer Architecture
=============================================================================
Calculates exact empirical expected values (EV), win probabilities (p_bull),
and physical durations DIRECTLY from confirmed ZigZag legs in Neon Vault (market.zigzag_legs).

Preserves VIX Domain Physics: L0 Levels, L1 72h Velocity, and L2 Volatility Pivots
(VOL_CRUSH_REBOUND, PANIC_SPIKE_CAPITULATION, COMPLACENCY_FLOOR).

Usage:
    python -m backend.scripts.generate_vix_fact_table
"""
import sys
import pandas as pd
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.scripts.v3_fact_table_engine import build_v3_dual_layer_fact_store

OUTPUT_PATH = root_dir / "backend/modules/entry_decision/domain/rules/vix_fact_store.json"
D1_LABELS = ["DEEP_COMPLACENCY", "LOW_VOL", "MODERATE_VOL", "HIGH_VOL", "ELEVATED_PANIC", "CRISIS_SPIKE"]

VIX_PIVOT_OVERRIDES = {
    "VOL_CRUSH_REBOUND": {
        "guidance": "STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION",
        "regime": "FULL_CONVERGENT_BULL",
    },
    "PANIC_SPIKE_CAPITULATION": {
        "guidance": "STK_BLOCK_CRISIS",
        "regime": "FULL_CONVERGENT_BEAR",
    },
}


def vix_pivot_fn(df: pd.DataFrame) -> pd.Series:
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
        station_name="vix",
        ticker="VIX",
        model_purpose="CBOE Volatility Index (VIX) Harmonized V3 Dual-Layer Fact Store.",
        d1_labels=D1_LABELS,
        pivot_fn=vix_pivot_fn,
        pivot_overrides=VIX_PIVOT_OVERRIDES,
        intermarket_notes={
            "vix_spike": "Options Market Panic + S&P 500 Outflow + Gamma Squeeze Risk",
            "vix_crush": "Vol Crush Rally + Systematic Rehedging + Dealer Short Gamma Squeeze",
        },
        output_path=OUTPUT_PATH,
    )


if __name__ == "__main__":
    main()
