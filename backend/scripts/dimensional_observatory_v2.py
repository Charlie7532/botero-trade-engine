#!/usr/bin/env python3
"""
Dimensional Observatory V2 — VECTORIZED Cross-Reference D1×D2×D3 × ZigZag
==========================================================================
Optimized version: uses merge_asof and vectorized operations instead of
row-by-row iteration. ~100x faster than V1.

Outputs full results to a JSON file for later analysis.

Usage:
    cd /root/botero-trade
    python -m backend.scripts.dimensional_observatory_v2
"""
import os, sys, json, logging, time
from pathlib import Path
import numpy as np
import pandas as pd

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DimensionalObservatoryV2")

RULES_DIR = root_dir / "backend/modules/entry_decision/domain/rules"
OUTPUT_DIR = root_dir / "backend/scripts/observatory_output"
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Gaussian sigma percentiles (Rule 24) ──────────────────────────
PERCENTILES_D1 = [0.0228, 0.1587, 0.5000, 0.8413, 0.9772]
PERCENTILES_D2 = [0.0228, 0.1587, 0.8413, 0.9772]
PERCENTILES_D3 = [0.0228, 0.1587, 0.8413, 0.9772]

LABELS_D2 = ["FAST_CRUSH_3D", "DECELERATING_DOWN_3D", "STABLE_CONTINUATION_3D",
             "ACCELERATING_UP_3D", "FAST_SPIKE_3D"]
LABELS_D3 = ["VOL_EXTREME_SQUEEZE", "VOL_MODERATE_COMPRESSION", "VOL_NEUTRAL_BASELINE",
             "VOL_ACCELERATING_EXPANSION", "VOL_PEAK_DECELERATION"]

STATIONS = {
    "vix":            {"ticker": "VIX",
                       "labels_d1": ["DEEP_COMPLACENCY","LOW_VOL","MODERATE_VOL","HIGH_VOL","ELEVATED_PANIC","CRISIS_SPIKE"]},
    "vvix":           {"ticker": "VVIX",
                       "labels_d1": ["EXTREME_COMPLACENCY","LOW_VVIX","MODERATE_VVIX","HIGH_VVIX","ELEVATED_VVIX","EXTREME_VVIX"]},
    "pcr":            {"ticker": "CBOE_PCR",
                       "labels_d1": ["EXTREME_CALL_HEAVY","BULLISH_PCR","NEUTRAL_PCR","ELEVATED_PCR","HIGH_PUT_PANIC","EXTREME_PUT_PANIC"]},
    "fg":             {"ticker": "FG",
                       "labels_d1": ["EXTREME_FEAR","FEAR","NEUTRAL_FEAR","GREED","EXTREME_GREED","EUPHORIA"]},
    "sv5_turbulence": {"ticker": "SV5_TURBULENCE",
                       "labels_d1": ["QUIET_FLOW","LOW_TURBULENCE","MODERATE_TURBULENCE","HIGH_TURBULENCE","ELEVATED_TURBULENCE","CRISIS_TURBULENCE"]},
    "skew":           {"ticker": "SKEW",
                       "labels_d1": ["LOW_TAIL_RISK","NORMAL_TAIL_RISK","ELEVATED_TAIL_RISK","HIGH_TAIL_RISK","TAIL_PARANOIA","BLACK_SWAN_PARANOIA"]},
    "credit":         {"ticker": "CREDIT_RATIO",
                       "labels_d1": ["DEEP_CREDIT_EASE","CREDIT_EASE","STABLE_CREDIT","ELEVATED_CREDIT_STRESS","CREDIT_STRESS","CREDIT_CRISIS"]},
    "yield_curve":    {"ticker": "YIELD_SPREAD",
                       "labels_d1": ["DEEP_INVERSION","MODERATE_INVERSION","FLAT_CURVE","NORMAL_CURVE","STEEPNING_CURVE","EXTREME_STEEPNING"]},
    "rotation":       {"ticker": "ROTATION_INDEX",
                       "labels_d1": ["DEFENSIVE_CAPITULATION","DEFENSIVE","NEUTRAL_ROTATION","BALANCED","CYCLICAL_LEADERSHIP","AGGRESSIVE_ROTATION"]},
}


def classify_bin(val, edges, labels):
    if pd.isna(val):
        return labels[len(labels) // 2]
    for i, e in enumerate(edges):
        if val < e:
            return labels[i]
    return labels[-1]


def build_indicator_series(store, cfg):
    """All stations now read directly from Vault tickers (Rule 13).
    Synthetic indicators (CREDIT_RATIO, YIELD_SPREAD, ROTATION_INDEX)
    are pre-computed by the daemon and stored as pseudo-OHLCV."""
    df = store.load_bars(cfg["ticker"], "1d")
    return df["close"].dropna()


def compute_all_dimensional_states(store):
    """Vectorized: compute D1/D2/D3 for all stations → single DataFrame with DatetimeIndex."""
    all_frames = []
    for name, cfg in STATIONS.items():
        series = build_indicator_series(store, cfg)
        df = pd.DataFrame({"val": series})
        df.sort_index(inplace=True)
        df["d2_raw"] = df["val"].diff(3)
        vol5 = df["val"].rolling(5).std()
        vol20 = df["val"].rolling(20).std().replace(0, np.nan)
        df["d3_raw"] = (vol5 / vol20).fillna(1.0)
        df = df.dropna(subset=["d2_raw", "d3_raw"]).copy()

        d1_edges = [float(x) for x in df["val"].quantile(PERCENTILES_D1)]
        d2_edges = [float(x) for x in df["d2_raw"].quantile(PERCENTILES_D2)]
        d3_edges = [float(x) for x in df["d3_raw"].quantile(PERCENTILES_D3)]
        labels_d1 = cfg["labels_d1"]

        df["d1_label"] = df["val"].apply(lambda v: classify_bin(v, d1_edges, labels_d1))
        df["d2_label"] = df["d2_raw"].apply(lambda v: classify_bin(v, d2_edges, LABELS_D2))
        df["d3_label"] = df["d3_raw"].apply(lambda v: classify_bin(v, d3_edges, LABELS_D3))
        df["d1_extreme"] = df["d1_label"].isin([labels_d1[0], labels_d1[-1]])
        df["d2_extreme"] = df["d2_label"].isin([LABELS_D2[0], LABELS_D2[-1]])
        df["d3_extreme"] = df["d3_label"].isin([LABELS_D3[0], LABELS_D3[-1]])
        df["n_extreme"] = df["d1_extreme"].astype(int) + df["d2_extreme"].astype(int) + df["d3_extreme"].astype(int)
        df["d1_bin_idx"] = df["d1_label"].apply(lambda x: labels_d1.index(x) if x in labels_d1 else 2)

        # Rolling 5-day extreme flags (vectorized)
        df["d1_ext_5d"] = df["d1_extreme"].rolling(5, min_periods=1).max().astype(bool)
        df["d2_ext_5d"] = df["d2_extreme"].rolling(5, min_periods=1).max().astype(bool)
        df["d3_ext_5d"] = df["d3_extreme"].rolling(5, min_periods=1).max().astype(bool)
        df["max_res_5d"] = df["n_extreme"].rolling(5, min_periods=1).max().astype(int)

        df["station"] = name
        all_frames.append(df)
    return pd.concat(all_frames)


def load_zigzag_legs_vectorized(store):
    """Load ZZ legs using store's engine for proper SQLAlchemy support."""
    query = """
        SELECT ticker, scale, start_timestamp, start_type, start_price,
               end_timestamp, end_type, end_price
        FROM market.zigzag_legs
        WHERE ticker = 'SPY'
        ORDER BY scale, start_timestamp
    """
    df = pd.read_sql(query, store.engine)
    df["end_ts"] = pd.to_datetime(df["end_timestamp"])
    df["return_pct"] = (df["end_price"].astype(float) / df["start_price"].astype(float) - 1.0) * 100
    df["duration_days"] = (pd.to_datetime(df["end_timestamp"]) - pd.to_datetime(df["start_timestamp"])).dt.days
    df["scale_str"] = df["scale"].astype(str).str.strip()
    return df


def vectorized_cross_reference(dim_states, zz_legs):
    """VECTORIZED: merge_asof each ZZ turn with each station's dimensional state."""
    results = []
    scales = zz_legs["scale_str"].unique()

    for scale in scales:
        legs = zz_legs[zz_legs["scale_str"] == scale].copy()
        legs = legs.sort_values("end_ts")

        for station_name in STATIONS.keys():
            st_data = dim_states[dim_states["station"] == station_name].copy()
            st_data = st_data.sort_index()

            # merge_asof: for each ZZ turn timestamp, find the nearest (<=) dimensional state
            merged = pd.merge_asof(
                legs[["end_ts", "end_type", "return_pct"]].rename(columns={"end_ts": "ts"}),
                st_data[["d1_label", "d2_label", "d3_label",
                         "d1_ext_5d", "d2_ext_5d", "d3_ext_5d",
                         "max_res_5d", "d1_bin_idx", "n_extreme"]].reset_index().rename(columns={"time": "ts"}),
                on="ts",
                direction="backward",
                tolerance=pd.Timedelta(days=3)
            )

            merged["scale"] = scale
            merged["station"] = station_name
            results.append(merged)

    return pd.concat(results, ignore_index=True)


def print_analysis(xref, zz_legs):
    """Print all analysis sections."""

    # ── Section 1: Per-scale excitation ──
    print("\n" + "=" * 120)
    print("🔬 OBSERVATORIO DIMENSIONAL: ¿QUÉ INDICADOR SE EXCITA EN CADA ESCALA ZZ?")
    print("=" * 120)

    for scale in ["zz25", "zz50", "zz75"]:
        sub = xref[xref["scale"] == scale]
        if sub.empty:
            continue
        n_turns = sub["ts"].nunique()
        print(f"\n{'─'*100}")
        print(f"📐 ESCALA {scale.upper()} ({n_turns} giros)")
        print(f"{'─'*100}")

        for st in STATIONS.keys():
            s = sub[sub["station"] == st].dropna(subset=["d1_label"])
            if s.empty:
                continue
            d1p = s["d1_ext_5d"].mean() * 100
            d2p = s["d2_ext_5d"].mean() * 100
            d3p = s["d3_ext_5d"].mean() * 100
            rp = (s["max_res_5d"] >= 2).mean() * 100
            f1 = "🔥" if d1p > 15 else "  "
            f2 = "🔥" if d2p > 15 else "  "
            f3 = "🔥" if d3p > 15 else "  "
            print(f"  {st:18s} | {f1}D1={d1p:5.1f}% | {f2}D2={d2p:5.1f}% | {f3}D3={d3p:5.1f}% | Resonancia≥2: {rp:.1f}%")

    # ── Section 2: MAX vs MIN ──
    print("\n" + "=" * 120)
    print("🔬 ¿SE EXCITAN DIFERENTE EN TECHOS (MAX) vs SUELOS (MIN)?")
    print("=" * 120)

    for scale in ["zz25", "zz50", "zz75"]:
        sub = xref[xref["scale"] == scale]
        if sub.empty:
            continue
        print(f"\n{'─'*100}")
        print(f"📐 ESCALA {scale.upper()}")
        print(f"{'─'*100}")

        for tt in ["MAX", "MIN"]:
            ts = sub[sub["end_type"] == tt].dropna(subset=["d1_label"])
            if ts.empty:
                continue
            n = ts["ts"].nunique()
            print(f"\n  {'📈 TECHOS (MAX)' if tt == 'MAX' else '📉 SUELOS (MIN)'} — {n} giros")
            for st in STATIONS.keys():
                s = ts[ts["station"] == st]
                if s.empty:
                    continue
                d1p = s["d1_ext_5d"].mean() * 100
                d2p = s["d2_ext_5d"].mean() * 100
                d3p = s["d3_ext_5d"].mean() * 100
                flag = "💥" if (d1p > 15 or d2p > 20 or d3p > 20) else "  "
                print(f"    {flag} {st:18s} | D1={d1p:5.1f}% | D2={d2p:5.1f}% | D3={d3p:5.1f}%")

    # ── Section 3: D2 label distribution at turns ──
    print("\n" + "=" * 120)
    print("🔬 ¿QUÉ VELOCIDAD CINEMÁTICA (D2) PREVALECE EN CADA GIRO?")
    print("=" * 120)

    for scale in ["zz25", "zz50", "zz75"]:
        sub = xref[xref["scale"] == scale].dropna(subset=["d2_label"])
        if sub.empty:
            continue
        print(f"\n📐 {scale.upper()}")
        for tt in ["MAX", "MIN"]:
            ts = sub[sub["end_type"] == tt]
            if ts.empty:
                continue
            print(f"  {'TECHOS' if tt == 'MAX' else 'SUELOS'}:")
            d2_dist = ts["d2_label"].value_counts()
            total = d2_dist.sum()
            for lbl in LABELS_D2:
                ct = d2_dist.get(lbl, 0)
                pct = ct / total * 100 if total > 0 else 0
                bar = "█" * int(pct / 2)
                print(f"    {lbl:30s} {pct:5.1f}% {bar}")

    # ── Section 4: Multi-scale convergence ──
    print("\n" + "=" * 120)
    print("🔬 CONVERGENCIA MULTI-ESCALA: ¿CUÁNDO 2.5% Y 5.0% GIRAN JUNTOS?")
    print("=" * 120)

    for s1, s2, label in [("zz25", "zz50", "ZZ25+ZZ50"), ("zz50", "zz75", "ZZ50+ZZ75")]:
        t1 = zz_legs[zz_legs["scale_str"] == s1]["end_ts"].values
        t2 = zz_legs[zz_legs["scale_str"] == s2]["end_ts"].values

        count = 0
        for d1 in t1:
            for d2 in t2:
                if abs((pd.Timestamp(d1) - pd.Timestamp(d2)).days) <= 3:
                    count += 1
                    break
        print(f"  {label} convergen (±3 días): {count} episodios")


def main():
    t0 = time.time()
    store = TimescaleDataStore()

    # Step 1
    logger.info("Step 1: Computing dimensional states (vectorized)...")
    dim_states = compute_all_dimensional_states(store)
    logger.info(f"  → {len(dim_states)} records, {dim_states['station'].nunique()} stations, {time.time()-t0:.1f}s")

    # Step 2
    logger.info("Step 2: Loading ZigZag legs...")
    zz_legs = load_zigzag_legs_vectorized(store)
    for s in ["zz25", "zz50", "zz75"]:
        logger.info(f"  → {s}: {len(zz_legs[zz_legs['scale_str']==s])} legs")

    # Step 3
    logger.info("Step 3: Vectorized cross-reference (merge_asof)...")
    xref = vectorized_cross_reference(dim_states, zz_legs)
    logger.info(f"  → {len(xref)} cross-reference records in {time.time()-t0:.1f}s")

    # Step 4: Print analysis
    print_analysis(xref, zz_legs)

    # Step 5: Save results
    out_path = OUTPUT_DIR / "observatory_xref.parquet"
    xref.to_parquet(out_path, index=False)
    logger.info(f"✅ Results saved to {out_path}")
    logger.info(f"✅ Total runtime: {time.time()-t0:.1f}s")

    store.close()


if __name__ == "__main__":
    main()
