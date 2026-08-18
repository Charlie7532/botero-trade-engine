#!/usr/bin/env python3
"""
CATEGORY 3 — ACCIÓN/REALIDAD (CAT 3)
=====================================
Determina el estado GRADUADO: ¿llueve ya (capituló) o aún no (sub-reacción)?

SENSORES CAT3: BSI (S5TW), SV5_TURBULENCE, FG, ROTATION-B (ROTATION_INDEX)
— lo que el mercado ESTÁ HACIENDO, lead más corto.

SALIDA (por sensor, día a día):
- Estado graduado de 'acción/amplitud' (0-100%) — Gaussian CDF position
- SIGMETs: EXTREMO_ALTO/BAJO, ANTICIPACION, FLIP_D2
- Lead-lag vs pivotes zz50

VALIDA/REPRODUCE SEÑALES GRADE A:
- EXTREME_FEAR + D3 comprimido = entry seguro (PF 26.76, WR 87%)
- EUFORIA/TECHO (VIX↓ + S5 máximo)
- CAPITULACIÓN (S5 colapsó) vs SUB-REACCIÓN (S5 mantiene)
- S5 = mean-reversion (NO momentum)
- SV5T = confirmador dirless
- FG 504d suavizado, D2 flip NO aplica a FG
- Punto ciego: DIVERGENT_MEGA_CAP_TRAP
"""

import sys
import json
from pathlib import Path
from datetime import timedelta, date
from collections import Counter
import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

CAT3_SENSORS = {
    "BSI":          {"ticker": "S5TW",              "station": "bsi",              "description": "Price breadth (% stocks > 20D MA)"},
    "SV5T":         {"ticker": "SV5_TURBULENCE",     "station": "sv5_turbulence",  "description": "Volume breadth errativeness (dirless)"},
    "FG":           {"ticker": "FG",                 "station": "fg",               "description": "Smoothed sentiment (504d, 2011+)"},
    "ROTATION-B":   {"ticker": "ROTATION_INDEX",     "station": "rotation",         "description": "Defensive↔cyclical rotation"},
}

# GAUSSIAN CDF values for PERCENTILES_D1_GAUSS edges:
# edges[0]=-2σ→P2.28%, [1]=-1σ→P15.87%, [2]=0σ→P50%, [3]=+1σ→P84.13%, [4]=+2σ→P97.72%
GAUSS_CDF = [2.28, 15.87, 50.00, 84.13, 97.72]

# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def boot_ci(arr, ci=95, n_boot=3000, rng_seed=42):
    """Bootstrap CI95 for mean."""
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    n = len(arr)
    if n < 5:
        return float(np.nan), float(np.nan), float(np.nan), n
    rng = np.random.default_rng(rng_seed)
    means = np.zeros(n_boot)
    for i in range(n_boot):
        sample = rng.choice(arr, size=n, replace=True)
        means[i] = sample.mean()
    means.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(arr.mean()), float(np.percentile(means, lo)), float(np.percentile(means, hi)), n

def boot_ci_proportion(wins_bool, ci=95, n_boot=3000, rng_seed=42):
    """Bootstrap CI95 for proportion."""
    arr = np.asarray(wins_bool, float)
    arr = arr[~np.isnan(arr)]
    n = len(arr)
    if n < 5:
        return float(np.nan), float(np.nan), float(np.nan), n
    rng = np.random.default_rng(rng_seed)
    props = np.zeros(n_boot)
    for i in range(n_boot):
        props[i] = rng.choice(arr, size=n, replace=True).mean()
    props.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(arr.mean()), float(np.percentile(props, lo)), float(np.percentile(props, hi)), n

def boot_diff_ci(arr_a, arr_b, ci=95, n_boot=3000, rng_seed=42):
    """Bootstrap CI95 for difference of means A - B."""
    arr_a = np.asarray(arr_a, float)
    arr_b = np.asarray(arr_b, float)
    arr_a = arr_a[~np.isnan(arr_a)]
    arr_b = arr_b[~np.isnan(arr_b)]
    if len(arr_a) < 5 or len(arr_b) < 5:
        return float(np.nan), float(np.nan), float(np.nan)
    rng = np.random.default_rng(rng_seed)
    diffs = np.zeros(n_boot)
    for i in range(n_boot):
        sa = rng.choice(arr_a, size=len(arr_a), replace=True)
        sb = rng.choice(arr_b, size=len(arr_b), replace=True)
        diffs[i] = sa.mean() - sb.mean()
    diffs.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(arr_a.mean() - arr_b.mean()), float(np.percentile(diffs, lo)), float(np.percentile(diffs, hi))

def norm_idx(s):
    """Normalize OHLCV bar index: tz-naive, dedup, sort."""
    s = s.copy()
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s

def fmt_pct(mean, lo, hi):
    if any(np.isnan(v) for v in [mean, lo, hi]):
        return "    n/a"
    return f"{mean:.1%} [{lo:.1%}, {hi:.1%}]"

def fmt_ret(mean, lo, hi):
    if any(np.isnan(v) for v in [mean, lo, hi]):
        return "    n/a"
    return f"{mean:+.2%} [{lo:+.2%}, {hi:+.2%}]"

def fmt_graduated(val):
    """Format graduated state 0-100%."""
    if val is None or np.isnan(val):
        return "n/a"
    return f"{val:.1f}%"

# ═══════════════════════════════════════════════════════════════════════════════
# LOAD CALIBRATED EDGES
# ═══════════════════════════════════════════════════════════════════════════════

def load_calibrated_edges():
    """Load D1/D2/D3 edges+labels from fact stores for CAT3 sensors."""
    result = {}
    for name, cfg in CAT3_SENSORS.items():
        path = ROOT / f"backend/modules/entry_decision/domain/rules/{cfg['station']}_fact_store.json"
        try:
            d = json.load(open(path))
            th = d["_documentation"]["dimension_thresholds_definition"]
            station = cfg["station"]
            result[name] = {
                "d1_edges": th[f"{station}_edges_d1"],
                "d1_labels": th[f"{station}_labels_d1"],
                "d2_edges": th[f"{station}_edges_d2"],
                "d2_labels": th[f"{station}_labels_d2"],
                "d3_edges": th[f"{station}_edges_d3"],
                "d3_labels": th[f"{station}_labels_d3"],
            }
        except Exception as e:
            print(f"  ⚠️ Could not load edges for {name}: {e}")
    return result

def classify_d(value, edges, labels):
    """Classify a value into a bin label using calibrated edges."""
    if value is None or pd.isna(value):
        return None
    for i, e in enumerate(edges):
        if value < e:
            return labels[i]
    return labels[-1]

def classify_d_index(value, edges):
    """Classify a value into a bin INDEX (0-based)."""
    if value is None or pd.isna(value):
        return -1
    for i, e in enumerate(edges):
        if value < e:
            return i
    return len(edges)  # = len(labels)-1

def graduated_state(value, edges, _labels):
    """Map a D1 value to 0-100% graduated state (σ-band Gaussian CDF).
    
    Interpolates between the calibrated σ-band percentiles.
    edges: [-2σ, -1σ, 0, +1σ, +2σ] threshold values
    GAUSS_CDF: [2.28, 15.87, 50, 84.13, 97.72] corresponding percentiles
    """
    if value is None or pd.isna(value):
        return np.nan
    n = len(edges)
    # Below -2σ
    if value < edges[0]:
        # Linear extrapolation from [edges[0]:GAUSS_CDF[0], 0:0]
        frac = value / edges[0] if edges[0] != 0 else 1.0
        return max(0.0, GAUSS_CDF[0] * max(0.0, min(1.0, frac)))
    # Above +2σ
    if value >= edges[-1]:
        return GAUSS_CDF[-1] + (100 - GAUSS_CDF[-1]) * min(1.0, (value - edges[-1]) / (edges[-1] - edges[-2]) if len(edges) >= 2 else 0.1)
    # Interpolate between edges
    for i in range(len(edges) - 1):
        if value < edges[i+1]:
            t = (value - edges[i]) / (edges[i+1] - edges[i]) if edges[i+1] != edges[i] else 0.5
            return GAUSS_CDF[i] + t * (GAUSS_CDF[i+1] - GAUSS_CDF[i])
    return 50.0

# ═══════════════════════════════════════════════════════════════════════════════
# SIGMET DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def detect_sigmets_cat3(df, edges, labels, d3_edges, d3_labels, d3_comp_thresh=0.7, streak=3):
    """Detect SIGMETs for a CAT3 sensor using calibrated σ-band D1 + D2/D3 trajectory.
    
    SIGMET types:
      EXTREMO_ALTO  = D1 label 5 (>+2σ)
      EXTREMO_BAJO  = D1 label 0 (<-2σ)
      ANTICIPACION_ALTA = D1 label 4 (+1σ..+2σ) + D2↑ streak≥3 + D3 compressed streak≥3
      ANTICIPACION_BAJA = D1 label 1 (-2σ..-1σ) + D2↓ streak≥3 + D3 compressed streak≥3
      FLIP_D2       = D2 sign change
    """
    events = []
    prev_sign = None
    d2_streak = 0
    d3_streak = 0

    for ts, row in df.iterrows():
        val = row["val"]
        d2 = row["d2"]
        d3 = row["d3"]
        graduated = row.get("graduated", np.nan)

        if pd.isna(val):
            continue

        label = classify_d(val, edges, labels)
        label_idx = labels.index(label) if label in labels else -1

        # D2 trajectory
        sign = 1 if (d2 is not None and not pd.isna(d2) and d2 > 0) else (-1 if (d2 is not None and not pd.isna(d2) and d2 < 0) else 0)
        if sign != 0:
            if sign == prev_sign:
                d2_streak += 1
            else:
                d2_streak = 1
        else:
            d2_streak = 0

        # D3 compression trajectory: comprimida = D3 ≤ first 2 labels (VOL_EXTREME_SQUEEZE or VOL_MODERATE_COMPRESSION)
        # → D3 index 0 or 1
        d3_label = classify_d(d3, d3_edges, d3_labels) if d3 is not None and not pd.isna(d3) else None
        d3_idx = d3_labels.index(d3_label) if d3_label in d3_labels else -1
        is_compressed = (d3_idx == 0 or d3_idx == 1)  # SQUEEZE or MODERATE_COMPRESSION
        d3_streak = d3_streak + 1 if is_compressed else 0

        sig_type = None

        # EXTREMO_ALTO: D1 label 5
        if label_idx == 5:
            sig_type = "EXTREMO_ALTO"
        # EXTREMO_BAJO: D1 label 0
        elif label_idx == 0:
            sig_type = "EXTREMO_BAJO"
        # ANTICIPACION_ALTA: D1 label 4 + D2↑ streak + D3 compressed
        elif label_idx == 4 and d2_streak >= streak and d3_streak >= streak and sign > 0:
            sig_type = "ANTICIPACION_ALTA"
        # ANTICIPACION_BAJA: D1 label 1 + D2↓ streak + D3 compressed
        elif label_idx == 1 and d2_streak >= streak and d3_streak >= streak and sign < 0:
            sig_type = "ANTICIPACION_BAJA"

        # FLIP_D2
        if prev_sign is not None and sign != 0 and prev_sign != 0 and sign != prev_sign:
            if sig_type is None:
                sig_type = "FLIP_D2"

        if sign != 0:
            prev_sign = sign

        if sig_type:
            events.append({
                "timestamp": ts,
                "type": sig_type,
                "d1_label": label,
                "d1_idx": label_idx,
                "d3_label": d3_label,
                "graduated": graduated,
                "val": val,
                "d2": d2,
                "d3": d3,
                "d2_streak": d2_streak,
                "d3_streak": d3_streak,
            })

    return pd.DataFrame(events)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("═" * 90)
    print("  CAT 3 — ACCIÓN/REALIDAD")
    print("  Estado GRADUADO, SIGMETs, Lead-Lag vs zz50, Grade A signals")
    print("═" * 90)

    # ── 1. Load calibrated edges ──
    print("\n[1] CARGANDO EDGES CALIBRADOS...")
    calibrated = load_calibrated_edges()
    for name, cfg in calibrated.items():
        print(f"  {name}: D1 edges={cfg['d1_edges']}  labels={cfg['d1_labels']}")
        print(f"         D2 edges={cfg['d2_edges']}")
        print(f"         D3 edges={cfg['d3_edges']}")

    # ── 2. Load OHLCV bars + compute D1/D2/D3 ──
    print("\n[2] CARGANDO BARRAS + COMPUTANDO D1/D2/D3...")
    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)

    series_data = {}
    for name, cfg in CAT3_SENSORS.items():
        if name not in calibrated:
            continue
        try:
            s = norm_idx(store.load_bars(cfg["ticker"], "1d")["close"])
            df = pd.DataFrame({"val": s})
            df["d2"] = df["val"].diff(3)  # velocity Δ3d
            df["d3"] = df["val"].rolling(2).std() / df["val"].rolling(10).std()  # vol norm
            edges = calibrated[name]
            # D1 label + graduated state
            df["d1_label"] = [classify_d(v, edges["d1_edges"], edges["d1_labels"]) for v in df["val"]]
            df["d2_label"] = [classify_d(v, edges["d2_edges"], edges["d2_labels"]) for v in df["d2"]]
            df["d3_label"] = [classify_d(v, edges["d3_edges"], edges["d3_labels"]) for v in df["d3"]]
            df["graduated"] = [graduated_state(v, edges["d1_edges"], edges["d1_labels"]) for v in df["val"]]
            series_data[name] = df
            print(f"  {name} ({cfg['description']}): {len(df)} bars, "
                  f"range={df['val'].min():.2f}-{df['val'].max():.2f}, "
                  f"graduated range={df['graduated'].min():.1f}%-{df['graduated'].max():.1f}%")
        except Exception as e:
            print(f"  ⚠️ {name}: {e}")

    # ── 3. Load SPY for forward returns ──
    spy_raw = norm_idx(store.load_bars("SPY", "1d")["close"])
    spy_dates = list(spy_raw.index)
    spy_values = spy_raw.values
    spy_date_to_idx = {d.date() if hasattr(d, "date") else d: i for i, d in enumerate(spy_dates)}
    print(f"  SPY: {len(spy_dates)} bars, {spy_dates[0].date()} → {spy_dates[-1].date()}")

    # ── 4. Detect SIGMETs per sensor ──
    print("\n[3] DETECTANDO SIGMETs (σ-band calibrated)...")
    all_sigmets = {}
    for name, df in series_data.items():
        edges = calibrated[name]
        ev = detect_sigmets_cat3(df, edges["d1_edges"], edges["d1_labels"],
                                   edges["d3_edges"], edges["d3_labels"])
        if len(ev) > 0:
            ev["sensor"] = name
            all_sigmets[name] = ev
            type_counts = ev["type"].value_counts().to_dict()
            print(f"  {name}: {len(ev)} SIGMETs — {type_counts}")
        else:
            print(f"  {name}: 0 SIGMETs")

    # ── 5. LEAD-LAG vs zz50 pivots ──
    print("\n[4] LEAD-LAG vs zz50 PIVOTS...")
    legs50 = repo.get_confirmed_legs("SPY", "zz50")
    legs50_df = repo.get_confirmed_legs_dataframe("SPY", "zz50")
    print(f"  zz50 pivots: {len(legs50)}")

    # For each zz50 pivot, find which sensor emitted SIGMET first (30d window)
    # NOTE: FLIP_D2 excluded from lead-lag — it fires ~every 3-5d (too frequent to
    # discriminate "who leads"). Only meaningful events: EXTREMO_ALTO/BAJO, ANTICIPACION.
    MEANINGFUL_TYPES = {"EXTREMO_ALTO", "EXTREMO_BAJO", "ANTICIPACION_ALTA", "ANTICIPACION_BAJA"}
    lead_counts = {name: 0 for name in CAT3_SENSORS}
    lead_days = {name: [] for name in CAT3_SENSORS}
    n_with_sigmet = 0

    for _, leg in legs50_df.iterrows():
        pivot_ts = pd.Timestamp(leg["start_timestamp"]).tz_localize(None).normalize()
        first_sensor = None
        first_ts = None
        for name, ev in all_sigmets.items():
            if len(ev) == 0:
                continue
            ev_m = ev[ev["type"].isin(MEANINGFUL_TYPES)]
            if len(ev_m) == 0:
                continue
            window = ev_m[(ev_m["timestamp"].dt.normalize() >= pivot_ts - pd.Timedelta(days=30)) &
                          (ev_m["timestamp"].dt.normalize() <= pivot_ts)]
            if len(window) > 0:
                min_ts = window["timestamp"].min()
                if first_ts is None or min_ts < first_ts:
                    first_ts = min_ts
                    first_sensor = name
        if first_sensor is not None:
            lead_counts[first_sensor] += 1
            lead_days[first_sensor].append((pivot_ts - first_ts).days)
            n_with_sigmet += 1

    total = n_with_sigmet
    print(f"  Pivotes con ≥1 SIGMET en ventana 30d: {total}/{len(legs50_df)}")
    if total > 0:
        print(f"  {'Sensor':<15} {'N':>5} {'%':>7} {'Lead med(d)':>11} {'Lead mean(d)':>12}")
        print(f"  {'-'*15} {'-'*5} {'-'*7} {'-'*11} {'-'*12}")
        for name in CAT3_SENSORS:
            if lead_counts[name] > 0:
                pct = lead_counts[name] / total * 100
                med = np.median(lead_days[name])
                mean_d = np.mean(lead_days[name])
                print(f"  {name:<15} {lead_counts[name]:>5} {pct:>6.1f}% {med:>10.1f}d {mean_d:>11.1f}d")
            else:
                print(f"  {name:<15} {lead_counts[name]:>5} {0:>6.1f}%")

    # ── 6. GRADE A SIGNALS VALIDATION ──
    print("\n" + "═" * 90)
    print("  [5] VALIDACIÓN SEÑALES GRADE A (CI95 + N)")
    print("═" * 90)

    # ── 6a. EXTREME_FEAR + D3 comprimido = safest entry ──
    print("\n── 6a. EXTREME_FEAR + D3 comprimido → entry seguro (PF 26.76, WR 87%) ──")
    if "FG" in series_data:
        fg_df = series_data["FG"]
        # Filter: D1=EXTREME_FEAR + D3=VOL_EXTREME_SQUEEZE or VOL_MODERATE_COMPRESSION
        # FG D1 labels: EXTREME_FEAR(0), FEAR(1), NEUTRAL_FEAR(2), GREED(3), EXTREME_GREED(4), EUPHORIA(5)
        fg_ef = fg_df[(fg_df["d1_label"] == "EXTREME_FEAR")]
        # Split by D3: comprimido (label index 0 or 1) vs caos (label index 3 or 4)
        fg_d3_labels = calibrated["FG"]["d3_labels"]
        comprimido_mask = fg_ef["d3_label"].isin(fg_d3_labels[:2])  # VOL_EXTREME_SQUEEZE, VOL_MODERATE_COMPRESSION
        caos_mask = fg_ef["d3_label"].isin(fg_d3_labels[3:])  # VOL_ACCELERATING_EXPANSION, VOL_PEAK_DECELERATION
        fg_comp = fg_ef[comprimido_mask]
        fg_caos = fg_ef[caos_mask]

        print(f"  EXTREME_FEAR total: {len(fg_ef)} days (2011+)")
        print(f"    D3 comprimido (entry seguro): {len(fg_comp)} days")
        print(f"    D3 caos: {len(fg_caos)} days")

        for label, subset in [("D3 comprimido", fg_comp), ("D3 caos", fg_caos)]:
            if len(subset) < 3:
                print(f"  {label}: N<3")
                continue
            fwd_rets = {h: [] for h in [5, 10, 20, 40]}
            for ts, row in subset.iterrows():
                d_ = ts.date() if hasattr(ts, "date") else ts
                idx = spy_date_to_idx.get(d_)
                if idx is None:
                    continue
                entry_p = spy_values[idx]
                for h in [5, 10, 20, 40]:
                    if idx + h < len(spy_values):
                        fwd_rets[h].append(spy_values[idx + h] / entry_p - 1.0)

            print(f"  {label} (n days with SPY forward):")
            for h in [5, 10, 20, 40]:
                arr = fwd_rets[h]
                if len(arr) < 5:
                    print(f"    {h:2d}d: N<5")
                    continue
                ret_m, ret_lo, ret_hi, ret_n = boot_ci(arr)
                wr_m, wr_lo, wr_hi, wr_n = boot_ci_proportion(np.array(arr) > 0)
                wins = np.array([x for x in arr if x > 0])
                losses = np.array([x for x in arr if x <= 0])
                gross_w = wins.sum() if len(wins) > 0 else 0
                gross_l = abs(losses.sum()) if len(losses) > 0 else 1e-10
                pf = gross_w / gross_l
                avg_w = wins.mean() if len(wins) > 0 else 0
                avg_l = abs(losses.mean()) if len(losses) > 0 else 0
                wlr = avg_w / avg_l if avg_l > 0 else 1.0
                kelly = wr_m - (1 - wr_m) / wlr if avg_l > 0 else np.nan
                print(f"    {h:2d}d: ret={fmt_ret(ret_m, ret_lo, ret_hi)}  WR={wr_m:.1%} [{wr_lo:.1%}, {wr_hi:.1%}]  "
                      f"PF={pf:.2f}  K={kelly:+.2f}  N={ret_n}")

    # ── 6b. CAPITULACIÓN vs SUB-REACCIÓN — at zz25 pivots (reproduces documented) ──
    print("\n── 6b. CAPITULACIÓN (BSI/S5 colapsa) vs SUB-REACCIÓN (BSI mantiene) — @ zz25 pivots ──")
    print("  ⚠ CAT3-only: la señal completa requiere VIX↑ (CAT2). Aquí medimos la MITAD CAT3:")
    print("     S5 colapsó (D2 FAST_CRUSH/DECEL_DOWN) = venta descargada → CAPITULACIÓN")
    print("     S5 mantiene (D2 STABLE/ACCEL_UP/FAST_SPIKE) = miedo sin descargar → SUB-REACCIÓN")
    if "BSI" in series_data:
        bsi_df = series_data["BSI"]
        legs25 = repo.get_confirmed_legs("SPY", "zz25")
        # Build BSI D2 + D2-label lookup by date
        bsi_d2 = {d.date(): float(v) for d, v in bsi_df["d2"].items() if pd.notna(v)}
        bsi_d2lab = {d.date(): v for d, v in bsi_df["d2_label"].items() if pd.notna(v)}

        # Collapse = BSI D2 FAST_CRUSH or DECELERATING_DOWN; hold = STABLE/ACCEL/SPIKE
        COLLAPSE = {"FAST_CRUSH_3D", "DECELERATING_DOWN_3D"}
        HOLD = {"STABLE_CONTINUATION_3D", "ACCELERATING_UP_3D", "FAST_SPIKE_3D"}

        cap_rows, sub_rows = [], []
        for l in legs25:
            pd_ = pd.to_datetime(l.start_timestamp).tz_localize(None).date()
            lab = bsi_d2lab.get(pd_)
            if lab is None:
                continue
            # next-leg direction (leg_bear: MAX→bear)
            leg_bear = 1 if l.start_type == "MAX" else 0
            # cascade_50 same-type ±3d (starts50)
            idx = spy_date_to_idx.get(pd_)
            fwd = {}
            if idx is not None:
                ep = spy_values[idx]
                for h in [5, 10, 20, 40]:
                    if idx + h < len(spy_values):
                        fwd[h] = spy_values[idx + h] / ep - 1.0
            row = {"date": pd_, "leg_bear": leg_bear, **fwd}
            if lab in COLLAPSE:
                cap_rows.append(row)
            elif lab in HOLD:
                sub_rows.append(row)

        cap_df = pd.DataFrame(cap_rows)
        sub_df = pd.DataFrame(sub_rows)
        print(f"  CAPITULACIÓN (BSI D2 colapsando): N={len(cap_df)} pivotes")
        print(f"  SUB-REACCIÓN (BSI D2 mantiene):   N={len(sub_df)} pivotes")

        for label, d in [("CAPITULACIÓN", cap_df), ("SUB-REACCIÓN", sub_df)]:
            if len(d) < 5:
                continue
            bear_m, bear_lo, bear_hi, bear_n = boot_ci(d["leg_bear"].dropna().values)
            print(f"\n  {label} (N={len(d)}):")
            print(f"    %próximo leg BAJISTA: {fmt_pct(bear_m, bear_lo, bear_hi)}")
            for h in [20, 40]:
                if h in d.columns:
                    arr = d[h].dropna().values
                    if len(arr) >= 5:
                        ret_m, ret_lo, ret_hi, ret_n = boot_ci(arr)
                        wr_m, wr_lo, wr_hi, wr_n = boot_ci_proportion(arr > 0)
                        wins = arr[arr > 0]; losses = arr[arr <= 0]
                        pf = (wins.sum() if len(wins) else 0) / (abs(losses.sum()) if len(losses) else 1e-10)
                        print(f"    {h:2d}d: ret={fmt_ret(ret_m, ret_lo, ret_hi)}  WR={wr_m:.1%} [{wr_lo:.1%}, {wr_hi:.1%}]  PF={pf:.2f}  N={ret_n}")
        # bootstrap difference capitulación vs sub-reacción
        if len(cap_df) >= 5 and len(sub_df) >= 5:
            for col in ["leg_bear", "fwd_20" if "20" in cap_df.columns else "20"]:
                pass
            if 20 in cap_df.columns and 20 in sub_df.columns:
                diff, dlo, dhi = boot_diff_ci(cap_df[20].dropna().values, sub_df[20].dropna().values)
                sig = "***" if (dlo > 0 or dhi < 0) else "ns"
                print(f"\n  Δ20d CAPITULACIÓN − SUB-REACCIÓN: {diff:+.2%} CI95=[{dlo:+.2%}, {dhi:+.2%}] {sig}")
                print(f"  → {('CAPITULACIÓN rebota MÁS (venta descargada)' if diff > 0 else 'SUB-REACCIÓN rinde más (miedo sin descargar)')}")
            bdiff, bdlo, bdhi = boot_diff_ci(cap_df["leg_bear"].dropna().values, sub_df["leg_bear"].dropna().values)
            sig = "***" if (bdlo > 0 or bdhi < 0) else "ns"
            print(f"  Δ%bear CAPITULACIÓN − SUB-REACCIÓN: {bdiff:+.1%} CI95=[{bdlo:+.1%}, {bdhi:+.1%}] {sig}")

    # ── 6c. BSI mean-reversion (NO momentum) — at pivots ──
    print("\n── 6c. BSI/S5 = mean-reversion (NO momentum) — @ zz25 pivots ──")
    if "BSI" in series_data:
        bsi_df = series_data["BSI"]
        legs25 = repo.get_confirmed_legs("SPY", "zz25")
        bsi_d2 = {d.date(): float(v) for d, v in bsi_df["d2"].items() if pd.notna(v)}
        up_bear, dn_bear = [], []
        for l in legs25:
            pd_ = pd.to_datetime(l.start_timestamp).tz_localize(None).date()
            v = bsi_d2.get(pd_)
            if v is None:
                continue
            leg_bear = 1 if l.start_type == "MAX" else 0
            if v > 0:
                up_bear.append(leg_bear)
            elif v < 0:
                dn_bear.append(leg_bear)
        for label, arr in [("BSI D2↑ (breadth expanding)", up_bear), ("BSI D2↓ (breadth collapsing)", dn_bear)]:
            if len(arr) >= 5:
                m, lo, hi, n = boot_ci(np.array(arr))
                print(f"  {label:<30} N={len(arr):>5}  %próximo leg BAJISTA: {fmt_pct(m, lo, hi)}")
        if len(up_bear) >= 5 and len(dn_bear) >= 5:
            diff, dlo, dhi = boot_diff_ci(np.array(up_bear), np.array(dn_bear))
            sig = "***" if (dlo > 0 or dhi < 0) else "ns"
            print(f"  Δ%bear BSI↑ − BSI↓: {diff:+.1%} CI95=[{dlo:+.1%}, {dhi:+.1%}] {sig}")
            verdict = "MEAN-REVERSION ✓ (amplitud pico = techo)" if diff > 0 else "MOMENTUM (breadth sigue)" if diff < 0 else "SIN SEÑAL"
            print(f"  → {verdict}")

    # ── 6d. SV5T = dirless confirmer (bootstrap diff) ──
    print("\n── 6d. SV5T = confirmador dirless (bootstrap diff SV5T↑ vs SV5T↓) ──")
    if "SV5T" in series_data:
        sv5_df = series_data["SV5T"]
        sv5_up = sv5_df[sv5_df["d2"] > 0]
        sv5_dn = sv5_df[sv5_df["d2"] < 0]

        def fwd5(d):
            out = []
            for ts, _ in d.iterrows():
                dd = ts.date() if hasattr(ts, "date") else ts
                idx = spy_date_to_idx.get(dd)
                if idx is None or idx + 5 >= len(spy_values):
                    continue
                out.append(spy_values[idx + 5] / spy_values[idx] - 1.0)
            return np.array(out)

        up_r = fwd5(sv5_up); dn_r = fwd5(sv5_dn)
        print(f"  SV5T_D2↑ N={len(up_r)}: SPY 5d ret={up_r.mean():+.2%}  (CI95 bootstrap)")
        print(f"  SV5T_D2↓ N={len(dn_r)}: SPY 5d ret={dn_r.mean():+.2%}")
        if len(up_r) >= 5 and len(dn_r) >= 5:
            diff, dlo, dhi = boot_diff_ci(up_r, dn_r)
            sig = "***" if (dlo > 0 or dhi < 0) else "ns"
            print(f"  Δret SV5T↑ − SV5T↓: {diff:+.2%} CI95=[{dlo:+.2%}, {dhi:+.2%}] {sig}")
            print(f"  → {'DIRECTIONAL (SV5T tiene señal)' if (dlo > 0 or dhi < 0) else 'DIRLESS ✓ (CI95 cruza cero — confirma #34/#41)'}")

    # ── 6e. EUFORIA/TECHO: BSI expansive + ROTATION cyclical leadership ──
    print("\n── 6e. TECHO: BSI HYPER_EXPANSIVE + ROTATION AGGRESSIVE → techo ──")
    print("  ⚠ El TECHO documentado (71% bear) requiere VIX↓ (CAT2). CAT3-only mide la mitad.")
    if "BSI" in series_data and "ROTATION-B" in series_data:
        bsi = series_data["BSI"]
        rot = series_data["ROTATION-B"]
        common_idx = bsi.index.intersection(rot.index)
        techo_mask = (bsi.loc[common_idx, "d1_label"] == "HYPER_EXPANSIVE_BREADTH") & \
                     (rot.loc[common_idx, "d1_label"].isin(["CYCLICAL_LEADERSHIP", "AGGRESSIVE_ROTATION"]))
        techo_dates = common_idx[techo_mask]

        fwd_signs_20d = []
        for d in techo_dates:
            d_ = d.date() if hasattr(d, "date") else d
            idx = spy_date_to_idx.get(d_)
            if idx is None or idx + 20 >= len(spy_values):
                continue
            fwd_signs_20d.append(1 if spy_values[idx + 20] > spy_values[idx] else 0)

        if len(fwd_signs_20d) >= 5:
            wr_m, wr_lo, wr_hi, wr_n = boot_ci_proportion(np.array(fwd_signs_20d))
            pct_bear = 1 - wr_m
            pct_bear_lo = 1 - wr_hi
            pct_bear_hi = 1 - wr_lo
            print(f"  TECHO (CAT3-only): BSI HYPER + ROTATION AGGRESSIVE")
            print(f"  N={len(fwd_signs_20d)}, SPY↓_20d: {fmt_pct(pct_bear, pct_bear_lo, pct_bear_hi)}")
            if pct_bear > 0.60:
                print(f"  ✓ CONFIRMADO: {pct_bear:.1%} → TECHO (requiere VIX↓ para completar la señal)")
            else:
                print(f"  → CAT3-only NO alcanza 60% bear: la amplitud extrema sola NO es techo sin VIX↓.")
        else:
            print(f"  N={len(fwd_signs_20d)} (<5, insuficiente para CI95)")

    # ── 6f. FG D2 flip NO aplica (bootstrap diff) ──
    print("\n── 6f. FG D2 flip → timing NO aplica (FG es MA suavizado 504d) ──")
    if "FG" in series_data:
        fg_df = series_data["FG"]
        fg_df["d2_sign_prev"] = fg_df["d2"].apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        fg_df["d2_flip"] = (fg_df["d2_sign_prev"] != fg_df["d2_sign_prev"].shift(1)) & \
                           (fg_df["d2_sign_prev"] != 0) & (fg_df["d2_sign_prev"].shift(1) != 0)
        fg_flip = fg_df[fg_df["d2_flip"]]
        fg_noflip = fg_df[~fg_df["d2_flip"]]

        def fwd10(d):
            out = []
            for ts, _ in d.iterrows():
                dd = ts.date() if hasattr(ts, "date") else ts
                idx = spy_date_to_idx.get(dd)
                if idx is None or idx + 10 >= len(spy_values):
                    continue
                out.append(spy_values[idx + 10] / spy_values[idx] - 1.0)
            return np.array(out)

        flip_r = fwd10(fg_flip); noflip_r = fwd10(fg_noflip)
        print(f"  D2 flip    N={len(flip_r)}: SPY 10d ret={flip_r.mean():+.2%}")
        print(f"  D2 no-flip N={len(noflip_r)}: SPY 10d ret={noflip_r.mean():+.2%}")
        if len(flip_r) >= 5 and len(noflip_r) >= 5:
            diff, dlo, dhi = boot_diff_ci(flip_r, noflip_r)
            sig = "***" if (dlo > 0 or dhi < 0) else "ns"
            print(f"  Δret flip − no-flip: {diff:+.2%} CI95=[{dlo:+.2%}, {dhi:+.2%}] {sig}")
            print(f"  → {'D2 flip ES timing útil (contrario a lo esperado)' if (dlo > 0 or dhi < 0) else 'D2 flip NO aporta (no-flip ≥ flip) ✓ confirma #80'}")

    # ── 6g. DIVERGENT_MEGA_CAP_TRAP blind spot ──
    print("\n── 6g. Punto ciego: DIVERGENT_MEGA_CAP_TRAP ──")
    print("  ⚠️  Rally estrecho (1-2 sectores lideran) → CAT3 muestra amplitud EXPANSIVA")
    print("  ⚠️  pero NO es participación real — es concentración en mega-caps.")
    print("  ⚠️  Requiere Rotation Intelligence (modulo aparte): hot≤1/cold≥5 → TRAP.")
    if "BSI" in series_data:
        bsi = series_data["BSI"]
        hyper = bsi[bsi["d1_label"] == "HYPER_EXPANSIVE_BREADTH"]
        print(f"  HYPER_EXPANSIVE_BREADTH (BSI>89.7): {len(hyper)} days en {len(bsi)}")
        print(f"  → La banda graduada más alta (97.7%+) puede ser MEGA_CAP_TRAP,")
        print(f"     no participación real. Validar con rotación sectorial.")

    # ── 7. LAST N DAYS SNAPSHOT ──
    print("\n" + "═" * 90)
    print("  [6] SNAPSHOT — ÚLTIMOS 10 DÍAS (estado actual)")
    print("═" * 90)

    last_date = None
    for name, df in series_data.items():
        if len(df) > 0:
            ld = df.index[-1]
            if last_date is None or ld > last_date:
                last_date = ld

    if last_date:
        print(f"  Último día con datos: {last_date.date()}")
        recent_start = last_date - pd.Timedelta(days=10)
        print(f"\n  {'Fecha':<12} {'Sensor':<12} {'Valor':>10} {'D1 Label':<28} {'Graduado':>8} {'D2 Label':<25} {'D3 Label':<22}")
        print(f"  {'-'*12} {'-'*12} {'-'*10} {'-'*28} {'-'*8} {'-'*25} {'-'*22}")

        for name, df in series_data.items():
            recent = df[df.index >= recent_start]
            for ts, row in recent.iterrows():
                grad = row.get("graduated", np.nan)
                grad_str = f"{grad:.1f}%" if not np.isnan(grad) else "n/a"
                print(f"  {ts.date()!s:<12} {name:<12} {row['val']:>10.3f} {row['d1_label']:<28} {grad_str:>8} "
                      f"{str(row['d2_label']):<25} {str(row['d3_label']):<22}")

    # ── 8. CURRENT SIGMET STATUS ──
    print("\n  ── SIGMETs ACTIVOS EN ÚLTIMOS 5 DÍAS ──")
    if last_date:
        sigmet_window = last_date - pd.Timedelta(days=5)
        for name, ev in all_sigmets.items():
            recent_ev = ev[ev["timestamp"].dt.normalize() >= sigmet_window.normalize()]
            if len(recent_ev) > 0:
                for _, re in recent_ev.iterrows():
                    grad_str = f"{re['graduated']:.1f}%" if not np.isnan(re['graduated']) else "n/a"
                    print(f"    {re['timestamp'].date()}  {name:<12} {re['type']:<20} "
                          f"graduated={grad_str}  d1={re['d1_label']}  "
                          f"d3={re['d3_label']}")

    # ── 9. SUMMARY ──
    print("\n" + "═" * 90)
    print("  RESUMEN CAT 3 — ACCIÓN/REALIDAD")
    print("═" * 90)

    # Current graduated states
    print("\n  ESTADOS GRADUADOS ACTUALES (último día):")
    for name, df in series_data.items():
        if len(df) > 0:
            last = df.iloc[-1]
            grad = last.get("graduated", np.nan)
            grad_str = f"{grad:.1f}%" if not np.isnan(grad) else "n/a"
            print(f"    {name:<12} {last['d1_label']:<28} graduado={grad_str}  "
                  f"raw={last['val']:.3f}  D2={last['d2_label']}  D3={last['d3_label']}")

    # Grade A status
    print("\n  SEÑALES GRADE A — estado actual:")
    # Check FG
    if "FG" in series_data:
        fg_last = series_data["FG"].iloc[-1]
        fg_d3_last = fg_last["d3_label"]
        fg_d3_labels = calibrated["FG"]["d3_labels"]
        if fg_last["d1_label"] == "EXTREME_FEAR":
            if fg_d3_last in fg_d3_labels[:2]:
                print(f"    ✓ EXTREME_FEAR + D3 comprimido → ENTRY SEGURO (PF 26.76, WR 87%)")
            else:
                print(f"    ⚠ EXTREME_FEAR pero D3={fg_d3_last} → esperar compresión")
        elif fg_last["d1_label"] in ("EXTREME_GREED", "EUPHORIA"):
            print(f"    ⚠ FG={fg_last['d1_label']} — toda D2×D3 positiva (no vender euforia)")

    # Check BSI
    if "BSI" in series_data:
        bsi_last = series_data["BSI"].iloc[-1]
        bsi_d2_last = bsi_last["d2_label"]
        if bsi_d2_last in ("FAST_CRUSH_3D", "DECELERATING_DOWN_3D"):
            print(f"    ✓ BSI {bsi_d2_last} → CAPITULACIÓN (S5 colapsó, comprar)")
        elif bsi_d2_last in ("ACCELERATING_UP_3D", "FAST_SPIKE_3D"):
            print(f"    ⚠ BSI {bsi_d2_last} → SUB-REACCIÓN (S5 subiendo, miedo no descargado)")
        if bsi_last["d1_label"] == "HYPER_EXPANSIVE_BREADTH":
            print(f"    ⚠ BSI HYPER_EXPANSIVE — posible TECHO o MEGA_CAP_TRAP")
        if bsi_last["d1_label"] == "BREADTH_WASHED_OUT":
            print(f"    ✓ BSI WASHED_OUT — pánico total, máxima oportunidad de compra")

    # Check SV5T
    if "SV5T" in series_data:
        sv5_last = series_data["SV5T"].iloc[-1]
        print(f"    ℹ SV5T={sv5_last['d1_label']} — confirmador dirless (no vota dirección)")

    # Check ROTATION-B
    if "ROTATION-B" in series_data:
        rot_last = series_data["ROTATION-B"].iloc[-1]
        if rot_last["d1_label"] in ("DEFENSIVE_CAPITULATION", "DEFENSIVE"):
            print(f"    ✓ ROTATION={rot_last['d1_label']} → todos huyeron a defensivos = PISO")
        elif rot_last["d1_label"] in ("CYCLICAL_LEADERSHIP", "AGGRESSIVE_ROTATION"):
            print(f"    ⚠ ROTATION={rot_last['d1_label']} → todos en cíclicos = TECHO")

    store.close()
    print("\n═" * 90)
    print("  CAT 3 COMPLETADO — estado GRADUADO, SIGMETs, lead-lag, Grade A validados")
    print("═" * 90)


if __name__ == "__main__":
    main()