"""
Generate DXY 150-State Fact Table (Gaussian Quantile Calibrated)
===============================================================
Computes the 150-state Fact Store for the 11th METAR station: DXY (US Dollar Index).
Incorporates Intermarket Mechanics: Dollar vs Commodities Inflation & Interest Rate Differentials.

Gaussian Edges (Empirical Quantiles from 14,008 bars in Neon Vault 1971-2026):
  D1 (Value):  [76.1231, 84.2773, 95.9630, 108.5600, 135.5228]
  D2 (Delta3d): [-1.8200, -0.7200, 0.7300, 1.8000]
  D3 (VolRatio): [0.0114, 0.1024, 0.8888, 1.6066]

Taxonomy Mapping:
  D1=0 (DEEP_DOLLAR_CRUSH)     -> STK_BUY_DIP_TACTICAL (Commodity Reflation / EM Capital Surge)
  D1=1 (WEAK_DOLLAR)           -> STK_ACCUMULATE_STRUCTURAL (Fluid Global Liquidity)
  D1=2 (MODERATE_LOW_DOLLAR)   -> STK_HOLD_STABLE (Goldilocks Zone)
  D1=3 (MODERATE_HIGH_DOLLAR)  -> STK_HOLD_STABLE (Moderate Pressure)
  D1=4 (ELEVATED_DOLLAR_STRESS)-> STK_TRIM_TACTICAL (Corporate Margin Compression / Tightening)
  D1=5 (DOLLAR_SPIKE_CRISIS)   -> STK_BLOCK_CRISIS (Global Liquidity & Deflationary Squeeze)
"""
import os
import json
import numpy as np
import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

D1_BINS = [
    "DEEP_DOLLAR_CRUSH",
    "WEAK_DOLLAR",
    "MODERATE_LOW_DOLLAR",
    "MODERATE_HIGH_DOLLAR",
    "ELEVATED_DOLLAR_STRESS",
    "DOLLAR_SPIKE_CRISIS",
]

D2_BINS = [
    "FAST_CRUSH_3D",
    "DECELERATING_DOWN_3D",
    "STABLE_CONTINUATION_3D",
    "ACCELERATING_UP_3D",
    "FAST_SPIKE_3D",
]

D3_BINS = [
    "VOL_EXTREME_SQUEEZE",
    "VOL_MODERATE_COMPRESSION",
    "VOL_NEUTRAL_BASELINE",
    "VOL_ACCELERATING_EXPANSION",
    "VOL_PEAK_DECELERATION",
]

# Canonical Edges from Vault Population (14,008 bars)
D1_EDGES = [76.1231, 84.2773, 95.9630, 108.5600, 135.5228]
D2_EDGES = [-1.8200, -0.7200, 0.7300, 1.8000]
D3_EDGES = [0.0114, 0.1024, 0.8888, 1.6066]


def classify_d1(val: float) -> str:
    if val < D1_EDGES[0]:
        return D1_BINS[0]
    elif val < D1_EDGES[1]:
        return D1_BINS[1]
    elif val < D1_EDGES[2]:
        return D1_BINS[2]
    elif val < D1_EDGES[3]:
        return D1_BINS[3]
    elif val < D1_EDGES[4]:
        return D1_BINS[4]
    else:
        return D1_BINS[5]


def classify_d2(diff3: float) -> str:
    if diff3 < D2_EDGES[0]:
        return D2_BINS[0]
    elif diff3 < D2_EDGES[1]:
        return D2_BINS[1]
    elif diff3 < D2_EDGES[2]:
        return D2_BINS[2]
    elif diff3 < D2_EDGES[3]:
        return D2_BINS[3]
    else:
        return D2_BINS[4]


def classify_d3(vratio: float) -> str:
    if vratio < D3_EDGES[0]:
        return D3_BINS[0]
    elif vratio < D3_EDGES[1]:
        return D3_BINS[1]
    elif vratio < D3_EDGES[2]:
        return D3_BINS[2]
    elif vratio < D3_EDGES[3]:
        return D3_BINS[3]
    else:
        return D3_BINS[4]


def main():
    store = TimescaleDataStore()
    df_dxy = store.load_bars("DXY", "1d")
    if df_dxy.empty:
        df_dxy = store.load_bars("DX-Y.NYB", "1d")
    
    df_spy = store.load_bars("SPY", "1d")

    print(f"Loaded DXY bars: {len(df_dxy)}, SPY bars: {len(df_spy)}")

    df_dxy = df_dxy.sort_index()
    df_spy = df_spy.sort_index()

    close_dxy = df_dxy["close"].dropna()
    diff3_dxy = close_dxy.diff(3)

    v2 = close_dxy.rolling(2).std()
    v10 = close_dxy.rolling(10).std().replace(0, np.nan)
    vratio_dxy = v2 / v10

    df_feat = pd.DataFrame({
        "dxy_close": close_dxy,
        "dxy_diff3": diff3_dxy,
        "dxy_vratio": vratio_dxy,
    }).dropna()

    # Calculate SPY Returns for Stochastic Targets (2.5%, 5.0%, 7.5% scales)
    spy_close = df_spy["close"].dropna()
    spy_fwd_2d = (spy_close.shift(-2) / spy_close - 1.0)
    spy_fwd_5d = (spy_close.shift(-5) / spy_close - 1.0)
    spy_fwd_10d = (spy_close.shift(-10) / spy_close - 1.0)

    df_joined = df_feat.join(pd.DataFrame({
        "ret_2d": spy_fwd_2d,
        "ret_5d": spy_fwd_5d,
        "ret_10d": spy_fwd_10d,
    })).dropna()

    print(f"Joined samples for Fact Store training: {len(df_joined)}")

    states = {}
    for d1 in D1_BINS:
        for d2 in D2_BINS:
            for d3 in D3_BINS:
                key = f"{d1}__{d2}__{d3}"
                states[key] = {
                    "d1_bin": d1,
                    "d2_bin": d2,
                    "d3_bin": d3,
                    "n_samples": 0,
                    "returns_2d": [],
                    "returns_5d": [],
                    "returns_10d": [],
                }

    for _, row in df_joined.iterrows():
        b1 = classify_d1(row["dxy_close"])
        b2 = classify_d2(row["dxy_diff3"])
        b3 = classify_d3(row["dxy_vratio"])
        k = f"{b1}__{b2}__{b3}"
        states[k]["n_samples"] += 1
        states[k]["returns_2d"].append(row["ret_2d"])
        states[k]["returns_5d"].append(row["ret_5d"])
        states[k]["returns_10d"].append(row["ret_10d"])

    fact_store_data = {}
    for k, v in states.items():
        n = v["n_samples"]
        if n > 0:
            r2 = np.array(v["returns_2d"])
            r5 = np.array(v["returns_5d"])
            r10 = np.array(v["returns_10d"])

            p_bull_2d = float(np.mean(r2 > 0))
            p_bull_5d = float(np.mean(r5 > 0))
            p_bull_10d = float(np.mean(r10 > 0))

            ev_2d = float(np.mean(r2))
            ev_5d = float(np.mean(r5))
            ev_10d = float(np.mean(r10))

            pos_mean = float(np.mean(r5[r5 > 0])) if np.any(r5 > 0) else 0.01
            neg_mean = float(abs(np.mean(r5[r5 < 0]))) if np.any(r5 < 0) else 0.01
            rr_ratio = round(pos_mean / neg_mean, 2)
        else:
            p_bull_2d = p_bull_5d = p_bull_10d = 0.50
            ev_2d = ev_5d = ev_10d = 0.0
            rr_ratio = 1.0

        # Taxonomy assignment based on D1 state & Intermarket Logic
        d1 = v["d1_bin"]
        if d1 == "DOLLAR_SPIKE_CRISIS":
            guidance = "STK_BLOCK_CRISIS"
            regime = "GLOBAL_DOLLAR_LIQUIDITY_SQUEEZE"
        elif d1 == "ELEVATED_DOLLAR_STRESS":
            guidance = "STK_TRIM_TACTICAL"
            regime = "CORPORATE_MARGIN_COMPRESSION"
        elif d1 in ("WEAK_DOLLAR", "DEEP_DOLLAR_CRUSH"):
            guidance = "STK_BUY_DIP_TACTICAL" if v["d2_bin"] == "FAST_CRUSH_3D" else "STK_ACCUMULATE_STRUCTURAL"
            regime = "COMMODITY_REFLATION_EM_SURGE"
        else:
            guidance = "STK_HOLD_STABLE"
            regime = "GOLDILOCKS_CURRENCY_BALANCED"

        fact_store_data[k] = {
            "d1_bin": d1,
            "d2_bin": v["d2_bin"],
            "d3_bin": v["d3_bin"],
            "n_samples": n,
            "operational_guidance": guidance,
            "divergence_regime": regime,
            "p_bull": {
                "zz25": round(p_bull_2d, 4),
                "zz50": round(p_bull_5d, 4),
                "zz75": round(p_bull_10d, 4),
            },
            "ev_net": {
                "zz25": round(ev_2d, 6),
                "zz50": round(ev_5d, 6),
                "zz75": round(ev_10d, 6),
            },
            "capital_velocity": round(ev_5d / 5.0, 6),
            "rr_asymmetry": rr_ratio,
        }

    output_payload = {
        "_documentation": {
            "model_purpose": "11th METAR Station: DXY (US Dollar Index) Global Sovereign Liquidity & Commodity Inflation Engine",
            "intermarket_mechanics": "Surging DXY (+2σ) = Global Liquidity Squeeze + Commodity Deflation. Crushing DXY (-2σ) = EM Capital Inflow + Commodity Inflation (Oil/Gold Cost-Push).",
            "state_hierarchy": "150 Gaussian States (6 D1 Magnitude x 5 D2 Velocity x 5 D3 Volatility)",
            "dimension_thresholds_definition": {
                "d1_edges": D1_EDGES,
                "d2_edges": D2_EDGES,
                "d3_edges": D3_EDGES,
            },
            "signal_interpretation_policy": "Strict Gaussian quantile edges derived from 14,008 historical DXY bars (1971-2026).",
        },
        "fact_store": fact_store_data,
    }

    target_path = os.path.join(
        os.path.dirname(__file__),
        "../modules/entry_decision/domain/rules/dxy_fact_store.json",
    )
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    with open(target_path, "w") as f:
        json.dump(output_payload, f, indent=2)

    print(f"✅ Generated DXY 150-State Fact Store with {len(fact_store_data)} states -> {target_path}")


if __name__ == "__main__":
    main()
