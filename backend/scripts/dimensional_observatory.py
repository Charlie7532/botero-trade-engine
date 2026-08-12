#!/usr/bin/env python3
"""
Dimensional Observatory — Cross-Reference D1×D2×D3 States with ZigZag Legs
==========================================================================
Computes the 3 dimensional states (D1 Magnitude, D2 Velocity, D3 Station Vol)
for all 9 METAR indicators on every trading day, then cross-references with
active ZigZag legs at all 3 scales (2.5%, 5.0%, 7.5%) to discover:

1. Which indicators get excited at each ZigZag scale
2. Whether D2/D3 lead ZigZag turning points
3. Multi-scale convergence patterns
4. Per-indicator excitation signatures near MAX vs MIN turns

Usage:
    cd /root/botero-trade
    python -m backend.scripts.dimensional_observatory
"""
import os, sys, json, logging
from pathlib import Path
import numpy as np
import pandas as pd

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DimensionalObservatory")

RULES_DIR = root_dir / "backend/modules/entry_decision/domain/rules"

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

ZZ_SCALES = [("zz25", "zz25"), ("zz50", "zz50"), ("zz75", "zz75")]


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


def compute_dimensional_states(store):
    """Compute D1/D2/D3 for all indicators, return a DataFrame with date index."""
    all_frames = []

    for name, cfg in STATIONS.items():
        series = build_indicator_series(store, cfg)
        df = pd.DataFrame({"val": series})
        df.sort_index(inplace=True)
        df["date"] = df.index.date

        # D2: velocity (diff 3d)
        df["d2_raw"] = df["val"].diff(3)
        # D3: vol ratio
        vol5 = df["val"].rolling(5).std()
        vol20 = df["val"].rolling(20).std().replace(0, np.nan)
        df["d3_raw"] = (vol5 / vol20).fillna(1.0)

        df = df.dropna(subset=["d2_raw", "d3_raw"]).copy()

        # Compute edges from full population (Rule S2)
        d1_edges = [float(x) for x in df["val"].quantile(PERCENTILES_D1)]
        d2_edges = [float(x) for x in df["d2_raw"].quantile(PERCENTILES_D2)]
        d3_edges = [float(x) for x in df["d3_raw"].quantile(PERCENTILES_D3)]

        # Classify
        labels_d1 = cfg["labels_d1"]
        df["d1_label"] = df["val"].apply(lambda v: classify_bin(v, d1_edges, labels_d1))
        df["d2_label"] = df["d2_raw"].apply(lambda v: classify_bin(v, d2_edges, LABELS_D2))
        df["d3_label"] = df["d3_raw"].apply(lambda v: classify_bin(v, d3_edges, LABELS_D3))

        # Extreme flags
        df["d1_extreme"] = df["d1_label"].isin([labels_d1[0], labels_d1[-1]])
        df["d2_extreme"] = df["d2_label"].isin([LABELS_D2[0], LABELS_D2[-1]])
        df["d3_extreme"] = df["d3_label"].isin([LABELS_D3[0], LABELS_D3[-1]])
        df["n_extreme"] = df["d1_extreme"].astype(int) + df["d2_extreme"].astype(int) + df["d3_extreme"].astype(int)

        df["station"] = name
        df["d1_bin_idx"] = df["d1_label"].apply(lambda x: labels_d1.index(x) if x in labels_d1 else 2)

        all_frames.append(df[["date", "station", "val", "d2_raw", "d3_raw",
                              "d1_label", "d2_label", "d3_label",
                              "d1_extreme", "d2_extreme", "d3_extreme", "n_extreme",
                              "d1_bin_idx"]].copy())

    return pd.concat(all_frames, ignore_index=True)


def load_zigzag_legs(store):
    """Load all SPY zigzag legs from Vault."""
    conn = store._conn()
    try:
        query = """
            SELECT ticker, scale, start_timestamp, start_type, start_price,
                   end_timestamp, end_type, end_price, confirmed_at_timestamp
            FROM market.zigzag_legs
            WHERE ticker = 'SPY'
            ORDER BY scale, start_timestamp
        """
        df = pd.read_sql(query, conn)
        df["start_date"] = pd.to_datetime(df["start_timestamp"]).dt.date
        df["end_date"] = pd.to_datetime(df["end_timestamp"]).dt.date
        # scale is stored as string 'zz25', 'zz50', 'zz75' — keep as-is
        df["scale_str"] = df["scale"].astype(str).str.strip()
        df["return_pct"] = (df["end_price"].astype(float) / df["start_price"].astype(float) - 1.0) * 100
        df["duration_days"] = (pd.to_datetime(df["end_timestamp"]) - pd.to_datetime(df["start_timestamp"])).dt.days
        return df
    finally:
        store._put(conn)


def cross_reference_zz_dimensions(dim_states, zz_legs):
    """For each ZZ turning point, examine which dimensions were extreme in the 1-10 days before."""
    results = []

    for scale_name, scale_val in ZZ_SCALES:
        legs = zz_legs[zz_legs["scale_str"] == scale_val].copy()
        if legs.empty:
            continue

        # Get turning points (leg ends = giros)
        for _, leg in legs.iterrows():
            turn_date = leg["end_date"]
            turn_type = leg["end_type"]  # MAX or MIN
            turn_return = float(leg["return_pct"])

            for station_name in STATIONS.keys():
                station_data = dim_states[dim_states["station"] == station_name].copy()
                station_data = station_data[station_data["date"] <= turn_date].sort_values("date")

                if len(station_data) < 2:
                    continue

                # Look at the 10 days up to and including the turn
                last_10 = station_data.tail(12)
                last_10 = last_10[last_10["date"] <= turn_date].tail(10)

                if last_10.empty:
                    continue

                # At the turn itself
                at_turn = last_10.iloc[-1]

                # Any dimension extreme in last 5 days?
                last_5 = last_10.tail(5)
                d1_excited = last_5["d1_extreme"].any()
                d2_excited = last_5["d2_extreme"].any()
                d3_excited = last_5["d3_extreme"].any()
                max_n_extreme = int(last_5["n_extreme"].max())

                # D2 label at turn
                d2_at_turn = at_turn["d2_label"]
                d3_at_turn = at_turn["d3_label"]
                d1_bin = int(at_turn["d1_bin_idx"])

                results.append({
                    "scale": scale_name,
                    "turn_date": turn_date,
                    "turn_type": turn_type,
                    "turn_return": turn_return,
                    "station": station_name,
                    "d1_excited_5d": d1_excited,
                    "d2_excited_5d": d2_excited,
                    "d3_excited_5d": d3_excited,
                    "max_resonance_5d": max_n_extreme,
                    "d1_bin_at_turn": d1_bin,
                    "d2_at_turn": d2_at_turn,
                    "d3_at_turn": d3_at_turn,
                })

    return pd.DataFrame(results)


def main():
    store = TimescaleDataStore()

    # ── Step 1: Compute all dimensional states ────────────────────
    logger.info("Step 1: Computing dimensional states for all 9 indicators...")
    dim_states = compute_dimensional_states(store)
    logger.info(f"  → {len(dim_states)} dimensional state records across {dim_states['station'].nunique()} stations")
    logger.info(f"  → Date range: {dim_states['date'].min()} → {dim_states['date'].max()}")

    # ── Step 2: Load ZigZag legs ──────────────────────────────────
    logger.info("Step 2: Loading ZigZag legs from Vault...")
    zz_legs = load_zigzag_legs(store)
    for sn, sv in ZZ_SCALES:
        n = len(zz_legs[zz_legs["scale_str"] == sv])
        logger.info(f"  → {sn}: {n} legs")

    # ── Step 3: Cross-reference ───────────────────────────────────
    logger.info("Step 3: Cross-referencing dimensions × ZigZag turns...")
    xref = cross_reference_zz_dimensions(dim_states, zz_legs)
    logger.info(f"  → {len(xref)} cross-reference records")

    # ── Step 4: Analysis ──────────────────────────────────────────
    print("\n" + "=" * 120)
    print("🔬 OBSERVATORIO DIMENSIONAL: ¿QUÉ INDICADOR SE EXCITA EN CADA ESCALA ZZ?")
    print("=" * 120)

    for scale_name, _ in ZZ_SCALES:
        sub = xref[xref["scale"] == scale_name]
        if sub.empty:
            continue

        n_turns = sub["turn_date"].nunique()
        print(f"\n{'─'*100}")
        print(f"📐 ESCALA {scale_name.upper()} ({n_turns} giros)")
        print(f"{'─'*100}")

        # Per station: % of turns where each dimension was excited
        for st in STATIONS.keys():
            st_sub = sub[sub["station"] == st]
            if st_sub.empty:
                continue
            n = len(st_sub)
            d1_pct = st_sub["d1_excited_5d"].mean() * 100
            d2_pct = st_sub["d2_excited_5d"].mean() * 100
            d3_pct = st_sub["d3_excited_5d"].mean() * 100
            res_pct = (st_sub["max_resonance_5d"] >= 2).mean() * 100

            flag_d1 = "🔥" if d1_pct > 15 else "  "
            flag_d2 = "🔥" if d2_pct > 15 else "  "
            flag_d3 = "🔥" if d3_pct > 15 else "  "

            print(f"  {st:18s} | {flag_d1}D1={d1_pct:5.1f}% | {flag_d2}D2={d2_pct:5.1f}% | {flag_d3}D3={d3_pct:5.1f}% | Resonancia≥2: {res_pct:.1f}%")

    # ── Step 5: MAX vs MIN differentiation ────────────────────────
    print("\n" + "=" * 120)
    print("🔬 ¿SE EXCITAN DIFERENTE EN TECHOS (MAX) vs SUELOS (MIN)?")
    print("=" * 120)

    for scale_name, _ in ZZ_SCALES:
        sub = xref[xref["scale"] == scale_name]
        if sub.empty:
            continue

        print(f"\n{'─'*100}")
        print(f"📐 ESCALA {scale_name.upper()}")
        print(f"{'─'*100}")

        for turn_type in ["MAX", "MIN"]:
            t_sub = sub[sub["turn_type"] == turn_type]
            if t_sub.empty:
                continue
            n_turns = t_sub["turn_date"].nunique()
            print(f"\n  {'📈 TECHOS (MAX)' if turn_type == 'MAX' else '📉 SUELOS (MIN)'} — {n_turns} giros")

            for st in STATIONS.keys():
                st_sub = t_sub[t_sub["station"] == st]
                if st_sub.empty:
                    continue
                d1_pct = st_sub["d1_excited_5d"].mean() * 100
                d2_pct = st_sub["d2_excited_5d"].mean() * 100
                d3_pct = st_sub["d3_excited_5d"].mean() * 100
                flag = "💥" if (d1_pct > 15 or d2_pct > 20 or d3_pct > 20) else "  "
                print(f"    {flag} {st:18s} | D1={d1_pct:5.1f}% | D2={d2_pct:5.1f}% | D3={d3_pct:5.1f}%")

    # ── Step 6: D2 label distribution at turns ────────────────────
    print("\n" + "=" * 120)
    print("🔬 ¿QUÉ VELOCIDAD CINEMÁTICA (D2) PREVALECE EN CADA GIRO?")
    print("=" * 120)

    for scale_name, _ in ZZ_SCALES:
        sub = xref[xref["scale"] == scale_name]
        if sub.empty:
            continue
        print(f"\n📐 {scale_name.upper()}")
        for turn_type in ["MAX", "MIN"]:
            t_sub = sub[sub["turn_type"] == turn_type]
            if t_sub.empty:
                continue
            print(f"  {'TECHOS' if turn_type == 'MAX' else 'SUELOS'}:")

            # Aggregate D2 distribution across ALL stations
            d2_dist = t_sub.groupby("d2_at_turn").size()
            total = d2_dist.sum()
            for label in LABELS_D2:
                ct = d2_dist.get(label, 0)
                pct = ct / total * 100 if total > 0 else 0
                bar = "█" * int(pct / 2)
                print(f"    {label:30s} {pct:5.1f}% {bar}")

    # ── Step 7: Multi-scale convergence ───────────────────────────
    print("\n" + "=" * 120)
    print("🔬 CONVERGENCIA MULTI-ESCALA: ¿CUÁNDO 2.5% Y 5.0% GIRAN JUNTOS?")
    print("=" * 120)

    zz25_turns = set(zz_legs[zz_legs["scale_str"] == "zz25"]["end_date"].values)
    zz50_turns = set(zz_legs[zz_legs["scale_str"] == "zz50"]["end_date"].values)
    zz75_turns = set(zz_legs[zz_legs["scale_str"] == "zz75"]["end_date"].values)

    # Find dates within 3 days of each other
    convergence_25_50 = []
    for d25 in zz25_turns:
        for d50 in zz50_turns:
            diff = abs((pd.Timestamp(d50) - pd.Timestamp(d25)).days)
            if diff <= 3:
                convergence_25_50.append((d25, d50, diff))
    
    convergence_50_75 = []
    for d50 in zz50_turns:
        for d75 in zz75_turns:
            diff = abs((pd.Timestamp(d75) - pd.Timestamp(d50)).days)
            if diff <= 3:
                convergence_50_75.append((d50, d75, diff))

    convergence_all = []
    for d25 in zz25_turns:
        for d50 in zz50_turns:
            d25_50 = abs((pd.Timestamp(d50) - pd.Timestamp(d25)).days)
            if d25_50 > 3:
                continue
            for d75 in zz75_turns:
                d50_75 = abs((pd.Timestamp(d75) - pd.Timestamp(d50)).days)
                if d50_75 <= 5:
                    convergence_all.append((d25, d50, d75))

    print(f"\n  ZZ25 + ZZ50 convergen (±3 días): {len(convergence_25_50)} episodios")
    print(f"  ZZ50 + ZZ75 convergen (±3 días): {len(convergence_50_75)} episodios")
    print(f"  ZZ25 + ZZ50 + ZZ75 convergen (±5 días): {len(convergence_all)} episodios (MEGA-CONVERGENCIA)")

    # For mega-convergence dates, check dimensional state
    if convergence_all:
        print(f"\n  📊 En las MEGA-CONVERGENCIAS, ¿cuántas dimensiones están excitadas?")
        mega_dates = set()
        for d25, d50, d75 in convergence_all:
            mega_dates.add(d50)
        
        for st in ["vix", "sv5_turbulence", "skew", "pcr", "credit"]:
            st_data = dim_states[dim_states["station"] == st]
            excited_counts = []
            for md in mega_dates:
                row = st_data[st_data["date"] == md]
                if not row.empty:
                    excited_counts.append(int(row.iloc[0]["n_extreme"]))
            if excited_counts:
                avg = np.mean(excited_counts)
                pct_any = sum(1 for x in excited_counts if x > 0) / len(excited_counts) * 100
                print(f"    {st:18s} | Avg dims excited: {avg:.1f} | Any excited: {pct_any:.0f}%")

    store.close()
    logger.info("✅ Observatory complete.")


if __name__ == "__main__":
    main()
