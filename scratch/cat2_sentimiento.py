#!/usr/bin/env python3
"""
CAT 2 — SENTIMIENTO/PROTECCIÓN (Category Agent 2)
===================================================
Determina estado GRADUADO: ¿hay bochorno (protección subiendo) o aire seco (complacencia)?

SENSORES: VIX, VVIX, CBOE_PCR, SKEW.
CAT 2 = SENTIMIENTO/PROTECCIÓN — lead MEDIO.
Estos 4 sensores miden protección: miedo de volatilidad (VIX), estabilidad del miedo
(VVIX), posicionamiento en opciones AMBOS lados (PCR), y miedo de cola institucional (SKEW).

SALIDA (por sensor, día a día):
- Estado graduado de 'protección/miedo' (0-100%) con sigma depth
- SIGMETs: EXTREMO_ALTO/BAJO, ANTICIPACION_ALTA/BAJA, FLIP_D2
- Lead-lag vs pivotes zz50
- Validación GRADE A (CI95 + N)
"""

import sys, json
from pathlib import Path
from collections import Counter, defaultdict
from datetime import timedelta

import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

# ─── Config ─────────────────────────────────────────────────────────────────
SENSORS = ["VIX", "VVIX", "CBOE_PCR", "SKEW"]
TICKER_TO_STATION = {
    "VIX": "vix", "VVIX": "vvix", "CBOE_PCR": "pcr", "SKEW": "skew",
}
FW_HORIZONS = [5, 10, 20, 40, 60]
N_BOOT = 2000
BOOT_SEED = 42
SIG_WINDOW_DAYS = 30       # pre-pivot window for lead-lag
DEDUP_DAYS = 10             # dedup signals ≥10 trading days apart
ZZ_SCALES = ["zz25", "zz50", "zz75"]

# ─── Helpers ─────────────────────────────────────────────────────────────────
def boot_ci(arr, ci=95, n_boot=N_BOOT, seed=BOOT_SEED):
    arr = np.asarray(arr, float); arr = arr[~np.isnan(arr)]
    if len(arr) < 3: return float("nan"), float("nan"), float("nan"), len(arr)
    rng = np.random.default_rng(seed)
    means = rng.choice(arr, size=(n_boot, len(arr)), replace=True).mean(axis=1)
    lo, hi = (100 - ci) / 2, 100 - (100 - ci) / 2
    return float(arr.mean()), float(np.percentile(means, lo)), float(np.percentile(means, hi)), len(arr)

def boot_ci_prop(arr, ci=95, n_boot=N_BOOT, seed=BOOT_SEED):
    arr = np.asarray(arr, float); arr = arr[~np.isnan(arr)]
    if len(arr) < 3: return float("nan"), float("nan"), float("nan"), len(arr)
    rng = np.random.default_rng(seed)
    props = rng.choice(arr, size=(n_boot, len(arr)), replace=True).mean(axis=1)
    lo, hi = (100 - ci) / 2, 100 - (100 - ci) / 2
    return float(arr.mean()), float(np.percentile(props, lo)), float(np.percentile(props, hi)), len(arr)

def boot_diff_mean(arr_a, arr_b, ci=95, n_boot=N_BOOT, seed=BOOT_SEED):
    a = np.asarray(arr_a, float); a = a[~np.isnan(a)]
    b = np.asarray(arr_b, float); b = b[~np.isnan(b)]
    if len(a) < 3 or len(b) < 3: return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    diffs = rng.choice(a, size=(n_boot, len(a)), replace=True).mean(axis=1) - \
            rng.choice(b, size=(n_boot, len(b)), replace=True).mean(axis=1)
    lo, hi = (100 - ci) / 2, 100 - (100 - ci) / 2
    return float(a.mean() - b.mean()), float(np.percentile(diffs, lo)), float(np.percentile(diffs, hi))

def classify(val, edges, labels):
    """Classify a value using edges → labels: value < edges[i] → labels[i]; else → labels[-1]."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    for i, e in enumerate(edges):
        if val < e:
            return labels[i]
    return labels[-1]

def classify_idx(val, edges):
    """Return the integer index (0..len(labels)-1) for a value."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return -1
    for i, e in enumerate(edges):
        if val < e:
            return i
    return len(edges)  # last label = len(edges) (since n edges = n labels - 1)


def fmt_kelly(k):
    """Format Kelly fraction; None/NaN → '  n/a'."""
    if k is None or (isinstance(k, float) and np.isnan(k)):
        return "  n/a"
    return f"{k:.2f}"

# ─── Load calibrated edges ───────────────────────────────────────────────────
def load_calibrated_edges():
    """Load D1/D2/D3 edges+labels from each fact store JSON."""
    result = {}
    for ticker, station in TICKER_TO_STATION.items():
        path = ROOT / f"backend/modules/entry_decision/domain/rules/{station}_fact_store.json"
        try:
            d = json.load(open(path))
            th = d["_documentation"]["dimension_thresholds_definition"]
            out = {}
            for dim in ["d1", "d2", "d3"]:
                ek = f"{station}_edges_{dim}"
                lk = f"{station}_labels_{dim}"
                if ek in th and lk in th:
                    out[dim] = {"edges": th[ek], "labels": th[lk]}
            result[ticker] = out
        except Exception:
            pass
    return result

def load_series(store, tickers):
    """Load bar series, normalize index to tz-naive dates."""
    series = {}
    for t in tickers:
        try:
            b = store.load_bars(t, "1d")
            if len(b) == 0: continue
            s = b["close"].dropna()
            s.index = pd.to_datetime(s.index).normalize()
            if s.index.tz is not None:
                s.index = s.index.tz_localize(None)
            s = s[~s.index.duplicated(keep="last")].sort_index()
            series[t] = s
        except Exception:
            pass
    return series

# ─── Compute D1/D2/D3 classification + sigma depth + graduated % ─────────────
def compute_classification(series_dict, calibrated):
    """
    For each sensor: compute val, d2=diff(3), d3=std(2)/std(10),
    classify D1/D2/D3 using calibrated bins, compute:
    - sigma_depth = (val - μ) / σ  (overflow resolution)
    - graduated_pct = expanding percentile (0-100%)
    - graduated_label = D1 σ-band label
    Returns dict of DataFrames.
    """
    results = {}
    for ticker, s in series_dict.items():
        cal = calibrated.get(ticker, {})
        df = pd.DataFrame({"val": s})
        df["d2"] = df["val"].diff(3)
        df["d3"] = df["val"].rolling(2).std() / df["val"].rolling(10).std()
        df["graduated_pct"] = df["val"].expanding().rank(pct=True, method="average") * 100

        # Sigma depth: (val - μ) / σ  — resolves overflow beyond +2σ saturation
        # For SKEW: use post-2011 μ/σ (structural break at CBOE launch)
        full_vals = df["val"].dropna()
        if ticker == "SKEW":
            post2011 = full_vals[full_vals.index >= pd.Timestamp("2011-02-01")]
            mu, sigma = post2011.mean(), post2011.std()
        else:
            mu, sigma = full_vals.mean(), full_vals.std()
        df["sigma_depth"] = (df["val"] - mu) / sigma

        # D1 classification (calibrated bins)
        if "d1" in cal:
            df["d1_label"] = [classify(v, cal["d1"]["edges"], cal["d1"]["labels"]) for v in df["val"]]
            df["d1_idx"] = [classify_idx(v, cal["d1"]["edges"]) for v in df["val"]]
        else:
            df["d1_label"] = None
            df["d1_idx"] = -1

        # D2 classification
        if "d2" in cal:
            df["d2_label"] = [classify(v, cal["d2"]["edges"], cal["d2"]["labels"]) for v in df["d2"]]
        else:
            df["d2_label"] = None

        # D3 classification
        if "d3" in cal:
            df["d3_label"] = [classify(v, cal["d3"]["edges"], cal["d3"]["labels"]) for v in df["d3"]]
        else:
            df["d3_label"] = None

        # Full state_key: D1__D2__D3
        df["state_key"] = df.apply(
            lambda r: f"{r['d1_label']}__{r['d2_label']}__{r['d3_label']}"
            if r["d1_label"] and r["d2_label"] and r["d3_label"] else None,
            axis=1
        )

        results[ticker] = df
    return results

# ─── SIGMET detection ────────────────────────────────────────────────────────
def detect_sigmets(df, ticker, calibrated):
    """
    Detect SIGMETs for a sensor using FULL calibrated D1×D2×D3 bins.
    SIGMET types:
      EXTREMO_ALTO  = D1 label 5 (> +2σ)
      EXTREMO_BAJO  = D1 label 0 (< -2σ)
      ANTICIPACION_ALTA = D1 label 4 (+1σ..+2σ) AND D2 accelerating AND D3 compressed
      ANTICIPACION_BAJA = D1 label 1 (-2σ..-1σ) AND D2 decelerating AND D3 compressed
      FLIP_D2       = sign change of D2
    """
    cal = calibrated.get(ticker, {})
    d1_labels = cal.get("d1", {}).get("labels", [])
    d2_labels = cal.get("d2", {}).get("labels", [])
    d3_labels = cal.get("d3", {}).get("labels", [])

    # D2 accelerating / decelerating bins
    d2_accel = {"ACCELERATING_UP_3D", "FAST_SPIKE_3D"}
    d2_decel = {"DECELERATING_DOWN_3D", "FAST_CRUSH_3D"}
    # D3 compressed bins
    d3_compressed = {"VOL_EXTREME_SQUEEZE", "VOL_MODERATE_COMPRESSION"}

    events = []
    prev_sign = None

    for ts, row in df.iterrows():
        d2_val = row["d2"]
        if pd.isna(d2_val):
            continue

        sign = 1 if d2_val > 0 else (-1 if d2_val < 0 else 0)
        d1_label = row["d1_label"]
        d1_idx = row["d1_idx"]
        d2_label = row["d2_label"]
        d3_label = row["d3_label"]

        sig_type = None

        # EXTREMO ALTO: D1 label 5
        if d1_idx == 5:
            sig_type = "EXTREMO_ALTO"
        # EXTREMO BAJO: D1 label 0
        elif d1_idx == 0:
            sig_type = "EXTREMO_BAJO"
        # ANTICIPACION_ALTA: D1 label 4 + D2 accelerating + D3 compressed
        elif d1_idx == 4 and d2_label in d2_accel and d3_label in d3_compressed:
            sig_type = "ANTICIPACION_ALTA"
        # ANTICIPACION_BAJA: D1 label 1 + D2 decelerating + D3 compressed
        elif d1_idx == 1 and d2_label in d2_decel and d3_label in d3_compressed:
            sig_type = "ANTICIPACION_BAJA"

        # FLIP_D2
        if prev_sign is not None and sign != 0 and prev_sign != 0 and sign != prev_sign:
            if sig_type is None:
                sig_type = "FLIP_D2"
            else:
                # Combine: EXTREMO_ALTO+FLIP = D2 resolving in extreme
                sig_type = f"{sig_type}+FLIP_D2"

        if sign != 0:
            prev_sign = sign

        if sig_type:
            events.append({
                "timestamp": ts,
                "type": sig_type,
                "d1_label": d1_label,
                "d2_label": d2_label,
                "d3_label": d3_label,
                "sigma_depth": row["sigma_depth"],
                "graduated_pct": row["graduated_pct"],
            })

    return pd.DataFrame(events)

# ─── Lead-lag vs zz50 ────────────────────────────────────────────────────────
def lead_lag_analysis(sigmets_db, pivots_df, scale_name, window_days=SIG_WINDOW_DAYS):
    """For each pivot, find first SIGMET from each sensor in the pre-pivot window."""
    lead_data = defaultdict(list)
    all_leads = []
    sensor_first = []

    for _, leg in pivots_df.iterrows():
        pivot_ts = pd.Timestamp(leg["start_timestamp"])
        if pivot_ts.tz is not None:
            pivot_ts = pivot_ts.tz_localize(None)
        pivot_type = leg.get("start_type", None)
        first_sensor = None
        earliest_ts = None

        for ticker in SENSORS:
            if ticker not in sigmets_db or len(sigmets_db[ticker]) == 0:
                continue
            ev = sigmets_db[ticker]
            # Lead-lag uses SIGNIFICANT SIGMETs only (EXTREMO/ANTICIPACION).
            # FLIP_D2 fires on every D2 sign change (~2000×/sensor) → noise for lead-lag.
            ev = ev[ev["type"].str.startswith(("EXTREMO", "ANTICIPACION"))]
            if len(ev) == 0:
                continue
            win = ev[(ev["timestamp"] >= pivot_ts - pd.Timedelta(days=window_days)) &
                     (ev["timestamp"] <= pivot_ts + pd.Timedelta(days=1))]
            if len(win) > 0:
                first = win["timestamp"].min()
                lead_days = (pivot_ts - first).days
                lead_data[ticker].append(lead_days)
                all_leads.append({"ticker": ticker, "lead_days": lead_days, "pivot_ts": pivot_ts, "pivot_type": pivot_type})
                if earliest_ts is None or first < earliest_ts:
                    earliest_ts = first
                    first_sensor = ticker
        if first_sensor:
            sensor_first.append(first_sensor)

    results = {"scale": scale_name, "n_pivots": len(pivots_df)}
    for ticker in SENSORS:
        arr = np.array(lead_data.get(ticker, []))
        if len(arr) >= 3:
            results[f"{ticker}_lead"] = {
                "n": len(arr), "mean": float(arr.mean()), "median": float(np.median(arr)),
                "p25": float(np.percentile(arr, 25)), "p75": float(np.percentile(arr, 75)),
            }
        else:
            results[f"{ticker}_lead"] = {"n": len(arr)}

    cnt = Counter(sensor_first)
    results["sensor_first"] = {k: int(v) for k, v in cnt.most_common()}
    results["n_with_sigmet"] = len(sensor_first)
    return results

# ─── GRADE A validation ──────────────────────────────────────────────────────
def measure_forward(spy, signal_dates, dedup_days=DEDUP_DAYS):
    """For a list of signal timestamps, produce deduplicated forward returns."""
    # Sort and dedup
    dates = sorted(set(d for d in signal_dates if d in spy.index))
    dedup = []
    last = -dedup_days - 1
    spy_idx_list = list(spy.index)
    date_to_i = {d: i for i, d in enumerate(spy_idx_list)}
    for d in dates:
        i = date_to_i[d]
        if i - last >= dedup_days:
            dedup.append(d)
            last = i

    fwd = {h: [] for h in FW_HORIZONS}
    spy_vals = spy.values
    for d in dedup:
        i = date_to_i[d]
        for h in FW_HORIZONS:
            if i + h < len(spy_vals):
                fwd[h].append(spy_vals[i + h] / spy_vals[i] - 1.0)
    return dedup, fwd

def grade_a_report(fwd_arrays, label, n_signals):
    """Produce 8-dimension report for a signal. Returns dict."""
    R = {"label": label, "N": n_signals}
    for h in FW_HORIZONS:
        arr = np.asarray(fwd_arrays.get(h, []), float)
        arr_clean = arr[~np.isnan(arr)]
        if len(arr_clean) < 3:
            R[f"h{h}"] = {"insufficient": True, "n": len(arr_clean)}
            continue
        wins_bool = arr_clean > 0
        wr_m, wr_lo, wr_hi, _ = boot_ci_prop(wins_bool)
        ev_m, ev_lo, ev_hi, _ = boot_ci(arr_clean)
        w = arr_clean[arr_clean > 0]
        l = arr_clean[arr_clean <= 0]
        gross_w = float(w.sum()) if len(w) else 0.0
        gross_l = abs(float(l.sum())) if len(l) else 0.0
        pf = gross_w / gross_l if gross_l > 0 else float("inf")
        avg_w = float(w.mean()) if len(w) else 0.0
        avg_l = abs(float(l.mean())) if len(l) else 0.0
        wlr = avg_w / avg_l if avg_l > 0 else float("inf")
        kelly = wr_m - (1 - wr_m) / wlr if (avg_l > 0 and wlr > 0) else float("nan")
        wipes = int(len(l[l < -0.20]))
        R[f"h{h}"] = {
            "n": len(arr_clean),
            "ev_pct": ev_m * 100,
            "ci95_pct": [ev_lo * 100, ev_hi * 100],
            "wr_pct": wr_m * 100,
            "pf": pf if pf != float("inf") else 999.0,
            "kelly": float(kelly) if not np.isnan(kelly) else None,
            "min_pct": float(arr_clean.min()) * 100,
            "wipeouts_gt20": wipes,
            "wins_mean_pct": float(w.mean()) * 100 if len(w) else None,
            "losses_mean_pct": float(l.mean()) * 100 if len(l) else None,
            "win_p50_pct": float(np.median(w)) * 100 if len(w) else None,
            "loss_p50_pct": float(np.median(l)) * 100 if len(l) else None,
        }
    return R

# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)

    print("=" * 80)
    print("CAT 2 — SENTIMIENTO/PROTECCIÓN")
    print("Sensors: VIX | VVIX | CBOE_PCR | SKEW")
    print("¿Bochorno (protección subiendo) o aire seco (complacencia)?")
    print("=" * 80)

    # 1. Load calibrated edges
    print("\n[1] Cargando edges calibrados de fact stores...")
    calibrated = load_calibrated_edges()
    for t in SENSORS:
        if t in calibrated:
            cal = calibrated[t]
            print(f"  {t}: D1={len(cal['d1']['edges'])} edges, D2={len(cal['d2']['edges'])}, D3={len(cal['d3']['edges'])}")
        else:
            print(f"  {t}: NO edges! ⚠️")

    # 2. Load series
    print("\n[2] Cargando series de barras...")
    all_tickers = SENSORS + ["S5TW", "SPY"]
    series = load_series(store, all_tickers)
    for t in SENSORS + ["S5TW", "SPY"]:
        if t in series:
            print(f"  {t}: {len(series[t])} bars, {series[t].index[0].date()} → {series[t].index[-1].date()}")
        else:
            print(f"  {t}: NOT FOUND")

    spy = series.get("SPY")
    if spy is None:
        print("ERROR: SPY not found")
        return

    # 3. Compute classification + sigma depth + graduated %
    print("\n[3] Clasificando D1×D2×D3 + sigma depth + graduated %...")
    sensor_dfs = compute_classification(
        {t: series[t] for t in SENSORS if t in series}, calibrated
    )
    # Also compute S5TW for CAPITULACIÓN/SUB-REACCIÓN
    s5 = None
    if "S5TW" in series:
        s5 = pd.DataFrame({"val": series["S5TW"]})
        s5["d2"] = s5["val"].diff(3)
        s5["graduated_pct"] = s5["val"].expanding().rank(pct=True, method="average") * 100

    for t, df in sensor_dfs.items():
        n_states = df["state_key"].dropna().nunique() if "state_key" in df.columns else 0
        print(f"  {t}: {len(df)} bars, {n_states} states populated")

    # 4. SIGMET detection
    print("\n[4] Detectando SIGMETs (calibrated D1×D2×D3)...")
    sigmets_db = {}
    for t, df in sensor_dfs.items():
        ev = detect_sigmets(df, t, calibrated)
        sigmets_db[t] = ev
        type_counts = Counter(ev["type"]) if len(ev) > 0 else {}
        print(f"  {t}: {len(ev)} SIGMETs — {dict(type_counts)}")
    # Category-level SIGMET = any sensor fires
    all_cat2 = []
    for t, ev in sigmets_db.items():
        if len(ev) > 0:
            ev_copy = ev.copy()
            ev_copy["ticker"] = t
            all_cat2.append(ev_copy)
    cat2_sigmets = pd.concat(all_cat2) if all_cat2 else pd.DataFrame()
    if len(cat2_sigmets) > 0:
        cat2_sigmets = cat2_sigmets.sort_values("timestamp")

    # 5. Day-by-day graduating state (last 30 trading days)
    print("\n[5] Estado GRADUADO — últimos 30 días hábiles")
    common_dates = sorted(set.intersection(
        *[set(df.dropna(subset=["val"]).index) for df in sensor_dfs.values()]
    ))
    last30 = common_dates[-30:]
    print(f"\n  {'Date':<12} {'VIX':>8} {'σ':>6} {'%':>5} {'D1':<22} {'VVIX':>8} {'σ':>6} {'PCR':>7} {'σ':>6} {'SKEW':>7} {'σ':>6}")
    print(f"  {'─'*12} {'─'*8} {'─'*6} {'─'*5} {'─'*22} {'─'*8} {'─'*6} {'─'*7} {'─'*6} {'─'*7} {'─'*6}")
    for d in last30[-15:]:  # last 15 for brevity
        parts = [str(d.date())]
        for t in SENSORS:
            df = sensor_dfs[t]
            if d in df.index:
                row = df.loc[d]
                parts.append(f"{row['val']:>8.2f}")
                parts.append(f"{row['sigma_depth']:>+5.1f}")
                parts.append(f"{row['graduated_pct']:>4.0f}%")
                parts.append(f"{(row['d1_label'] or '?'):<22}")
            else:
                parts.extend(["     N/A", "  N/A", " N/A", "N/A"])
        print("  " + " ".join(parts))

    # Print the full 30-day table
    print(f"\n  FULL 30-DAY TABLE (abbreviated):")
    print(f"  {'Date':<12} {'VIX_σ':>7} {'VIX%':>5} {'VVIX_σ':>7} {'VVIX%':>5} {'PCR_σ':>7} {'PCR%':>5} {'SKEW_σ':>7} {'SKEW%':>5}")
    print(f"  {'─'*12} {'─'*7} {'─'*5} {'─'*7} {'─'*5} {'─'*7} {'─'*5} {'─'*7} {'─'*5}")
    for d in last30:
        parts = [str(d.date())]
        for t in SENSORS:
            df = sensor_dfs[t]
            if d in df.index:
                row = df.loc[d]
                sd = float(row["sigma_depth"])
                gp = float(row["graduated_pct"])
                parts.append(f"{sd:>+6.1f}")
                parts.append(f"{gp:>4.0f}%")
            else:
                parts.extend(["   N/A", " N/A"])
        print("  " + " ".join(parts))

    # Category-level protection index (mean of VIX+VVIX+SKEW percentiles — the "fear" sensors)
    # PCR is positioning, shown separately
    cat2_pct = defaultdict(list)
    for d in common_dates:
        for t in ["VIX", "VVIX", "SKEW"]:
            if t in sensor_dfs and d in sensor_dfs[t].index:
                cat2_pct[d].append(sensor_dfs[t].loc[d, "graduated_pct"])
    last_cat2 = np.mean(cat2_pct.get(last30[-1], [50.0])) if last30 else 50.0
    print(f"\n  → CAT2 PROTECTION INDEX (mean VIX+VVIX+SKEW %): último día = {last_cat2:.1f}%")
    if last_cat2 > 80:
        print(f"  🔴 BOCHORNO ALTO — protección elevada, miedo presente")
    elif last_cat2 > 60:
        print(f"  🟠 BOCHORNO MODERADO — protección subiendo")
    elif last_cat2 > 40:
        print(f"  🟡 NORMAL")
    elif last_cat2 > 20:
        print(f"  🟢 AIRE SECO MODERADO — complacencia presente")
    else:
        print(f"  🔵 AIRE SECO EXTREMO — complacencia profunda, peligro latente")

    # 6. Lead-lag vs zz50 pivots
    print(f"\n{'=' * 80}")
    print("[6] LEAD-LAG vs pivotes zz50")
    print(f"{'=' * 80}")
    for scale in ZZ_SCALES:
        pivots_df = repo.get_confirmed_legs_dataframe("SPY", scale)
        if len(pivots_df) == 0:
            continue
        ll = lead_lag_analysis(sigmets_db, pivots_df, scale)
        print(f"\n  {scale} ({ll['n_pivots']} pivotes):")
        for t in SENSORS:
            if f"{t}_lead" in ll and isinstance(ll[f"{t}_lead"], dict) and "n" in ll[f"{t}_lead"]:
                ld = ll[f"{t}_lead"]
                if ld["n"] >= 3:
                    print(f"    {t:<12}: n={ld['n']:<5} lead med={ld['median']:>+5.0f}d (mean={ld['mean']:>+5.0f}d, P25={ld['p25']:>+5.0f}d, P75={ld['p75']:>+5.0f}d)")
                else:
                    print(f"    {t:<12}: n={ld['n']} (insufficient)")
        print(f"    First sensor: {ll.get('sensor_first', {})}")

    # 7. GRADE A validation
    print(f"\n{'=' * 80}")
    print("[7] VALIDACIÓN SEÑALES GRADE A")
    print(f"{'=' * 80}")

    grade_a_results = {}

    # Helper: align sensor data to common SPY dates (shared across 7a-7f)
    common_idx = spy.index
    vix_df = sensor_dfs["VIX"].reindex(common_idx)
    skew_df = sensor_dfs["SKEW"].reindex(common_idx)
    pcr_df = sensor_dfs["CBOE_PCR"].reindex(common_idx)
    vix_pct_aligned = vix_df["graduated_pct"]
    skew_pct_aligned = skew_df["graduated_pct"]
    if s5 is not None:
        s5_aligned = s5.reindex(common_idx)
        s5_pct_aligned = s5_aligned["graduated_pct"]
    else:
        s5_aligned = None
        s5_pct_aligned = None

    # ── 7a. PÁNICO TOTAL ──
    print("\n  7a. PÁNICO TOTAL (VIX↑ + SKEW↑ simultáneo)")
    # Definition: VIX D1 ∈ {ELEVATED_PANIC, CRISIS_SPIKE} (label 4-5)
    #             AND SKEW D1 ∈ {TAIL_PARANOIA, BLACK_SWAN_PARANOIA} (label 4-5)
    #             + dedup ≥10 days
    vix_high = vix_df["d1_idx"] >= 4
    skew_high = skew_df["d1_idx"] >= 4
    panico_mask = vix_high & skew_high
    panico_dates = [d for d, m in zip(common_idx, panico_mask) if m]
    panico_dedup, panico_fwd = measure_forward(spy, panico_dates)
    panico_rpt = grade_a_report(panico_fwd, "PANICO_TOTAL (VIX↑+SKEW↑, bins calibrados label 4-5)", len(panico_dedup))
    grade_a_results["PANICO_TOTAL"] = panico_rpt

    # Also: PÁNICO TOTAL with raw percentiles ≥P90 (for comparison with documented PF 8.09)
    vix_pct = vix_df["graduated_pct"]
    skew_pct = skew_df["graduated_pct"]
    panico_pct_mask = (vix_pct >= 90) & (skew_pct >= 90)
    panico_pct_dates = [d for d, m in zip(common_idx, panico_pct_mask) if m]
    panico_pct_dedup, panico_pct_fwd = measure_forward(spy, panico_pct_dates)
    panico_pct_rpt = grade_a_report(panico_pct_fwd, "PANICO_TOTAL (pct≥90 both)", len(panico_pct_dedup))
    grade_a_results["PANICO_TOTAL_PCT90"] = panico_pct_rpt

    print(f"    Bins (label 4-5): N={panico_rpt['N']} días, {len(panico_dedup)} señales dedup")
    for h in FW_HORIZONS:
        d = panico_rpt.get(f"h{h}")
        if d and not d.get("insufficient"):
            print(f"      {h:>3}d: EV={d['ev_pct']:>+7.2f}% CI95[{d['ci95_pct'][0]:+.1f},{d['ci95_pct'][1]:+.1f}] "
                  f"WR={d['wr_pct']:.0f}% PF={d['pf']:.2f} Kelly={fmt_kelly(d['kelly'])} "
                  f"min={d['min_pct']:+.1f}% wipes={d['wipeouts_gt20']}")
    print(f"    Pct≥90: N={panico_pct_rpt['N']} días, {len(panico_pct_dedup)} señales")
    for h in FW_HORIZONS:
        d = panico_pct_rpt.get(f"h{h}")
        if d and not d.get("insufficient"):
            print(f"      {h:>3}d: EV={d['ev_pct']:>+7.2f}% CI95[{d['ci95_pct'][0]:+.1f},{d['ci95_pct'][1]:+.1f}] "
                  f"WR={d['wr_pct']:.0f}% PF={d['pf']:.2f} Kelly={fmt_kelly(d['kelly'])} "
                  f"min={d['min_pct']:+.1f}% wipes={d['wipeouts_gt20']}")

    # ── 7a-cont. PÁNICO TOTAL — reproducción EXACTA skew_profundo.py ──
    print("\n    Reproducción EXACTA skew_profundo (raw diario ≥ P85 full-history, sin dedup):")
    vx_p85 = vix_df["val"].quantile(0.85)
    sk_p85 = skew_df["val"].quantile(0.85)
    panico_exact_mask = (vix_df["val"] >= vx_p85) & (skew_df["val"] >= sk_p85)
    panico_exact_dates = [d for d, m in zip(common_idx, panico_exact_mask) if m]
    spy_vals_all = spy.values
    date_to_i_all = {d: i for i, d in enumerate(spy.index)}
    fwd_smooth = {h: [] for h in FW_HORIZONS}
    for d in panico_exact_dates:
        i = date_to_i_all[d]
        for h in FW_HORIZONS:
            if i + h < len(spy_vals_all):
                fwd_smooth[h].append(spy_vals_all[i + h] / spy_vals_all[i] - 1.0)
    smooth_rpt = grade_a_report(fwd_smooth, "PANICO_TOTAL (raw ≥P85 full-history, sin dedup)", len(panico_exact_dates))
    grade_a_results["PANICO_TOTAL_EXACT_P85"] = smooth_rpt
    print(f"    VIX P85={vx_p85:.1f}, SKEW P85={sk_p85:.1f} → N={smooth_rpt['N']} días (esperado ≈55)")
    for h in FW_HORIZONS:
        d = smooth_rpt.get(f"h{h}")
        if d and not d.get("insufficient"):
            print(f"      {h:>3}d: EV={d['ev_pct']:>+7.2f}% CI95[{d['ci95_pct'][0]:+.1f},{d['ci95_pct'][1]:+.1f}] "
                  f"WR={d['wr_pct']:.0f}% PF={d['pf']:.2f} Kelly={fmt_kelly(d['kelly'])} "
                  f"min={d['min_pct']:+.1f}% wipes={d['wipeouts_gt20']}")

    # ── 7b/7c. CAPITULACIÓN vs SUB-REACCIÓN — régimen diff(5) en pivotes zz25 ──
    # Método EXACTO de s5_vix_divergencia.py: signo de VIX diff(5) × S5TW diff(5) en cada pivote.
    #   CAPITULACIÓN  = MIEDO CON VENTA   (VIX↑ + S5 colapsa) → rebote (buy)
    #   SUB-REACCIÓN  = MIEDO SIN VENTA   (VIX↑ + S5 mantiene) → bearish
    print("\n  7b/7c. CAPITULACIÓN vs SUB-REACCIÓN (régimen VIX diff5 × S5TW diff5 en pivotes zz25)")
    if s5 is not None:
        vix_diff5 = sensor_dfs["VIX"]["val"].diff(5)
        s5_diff5 = s5["val"].diff(5)
        vix_d5 = {ts: float(v) for ts, v in vix_diff5.items() if not pd.isna(v)}
        s5_d5 = {ts: float(v) for ts, v in s5_diff5.items() if not pd.isna(v)}

        legs25 = repo.get_confirmed_legs_dataframe("SPY", "zz25")
        regime_fwd = {"CAPITULACION": {h: [] for h in FW_HORIZONS},
                      "SUB_REACCION": {h: [] for h in FW_HORIZONS}}
        regime_n = {"CAPITULACION": 0, "SUB_REACCION": 0}
        for _, leg in legs25.iterrows():
            ts = pd.Timestamp(leg["start_timestamp"])
            if ts.tz is not None:
                ts = ts.tz_localize(None)
            vd = vix_d5.get(ts)
            sd = s5_d5.get(ts)
            if vd is None or sd is None:
                continue
            vix_up = vd > 0
            s5_up = sd > 0
            if vix_up and not s5_up:
                key = "CAPITULACION"
            elif vix_up and s5_up:
                key = "SUB_REACCION"
            else:
                continue
            regime_n[key] += 1
            if ts in date_to_i_all:
                i = date_to_i_all[ts]
                for h in FW_HORIZONS:
                    if i + h < len(spy_vals_all):
                        regime_fwd[key][h].append(spy_vals_all[i + h] / spy_vals_all[i] - 1.0)

        for key, label in [("CAPITULACION", "CAPITULACIÓN (VIX↑ + S5 colapsó = MIEDO CON VENTA)"),
                            ("SUB_REACCION", "SUB-REACCIÓN (VIX↑ + S5 mantiene = MIEDO SIN VENTA)")]:
            rpt = grade_a_report(regime_fwd[key], label, regime_n[key])
            grade_a_results[key] = rpt
            print(f"\n    {label}: N={regime_n[key]} pivotes zz25")
            for h in FW_HORIZONS:
                d = rpt.get(f"h{h}")
                if d and not d.get("insufficient"):
                    print(f"      {h:>3}d: EV={d['ev_pct']:>+7.2f}% CI95[{d['ci95_pct'][0]:+.1f},{d['ci95_pct'][1]:+.1f}] "
                          f"WR={d['wr_pct']:.0f}% PF={d['pf']:.2f} Kelly={fmt_kelly(d['kelly'])} "
                          f"min={d['min_pct']:+.1f}% wipes={d['wipeouts_gt20']}")
    else:
        print("    S5TW no disponible")

    # ── 7d. PCR AMBOS lados ──
    print("\n  7d. PCR AMBOS lados (EXTREME_PUT_PANIC=piso, EXTREME_CALL_HEAVY=techo)")
    pcr_put_mask = pcr_df["d1_idx"] == 5  # EXTREME_PUT_PANIC
    pcr_call_mask = pcr_df["d1_idx"] == 0  # EXTREME_CALL_HEAVY
    for name, mask in [("EXTREME_PUT_PANIC (piso)", pcr_put_mask), ("EXTREME_CALL_HEAVY (techo)", pcr_call_mask)]:
        dates = [d for d, m in zip(common_idx, mask) if m]
        dedup, fwd = measure_forward(spy, dates)
        rpt = grade_a_report(fwd, f"PCR {name}", len(dedup))
        grade_a_results[f"PCR_{name.split()[0]}"] = rpt
        print(f"    {name}: N={rpt['N']} días, {len(dedup)} señales")
        for h in FW_HORIZONS:
            d = rpt.get(f"h{h}")
            if d and not d.get("insufficient"):
                print(f"      {h:>3}d: EV={d['ev_pct']:>+7.2f}% CI95[{d['ci95_pct'][0]:+.1f},{d['ci95_pct'][1]:+.1f}] "
                      f"WR={d['wr_pct']:.0f}% PF={d['pf']:.2f} Kelly={fmt_kelly(d['kelly'])} "
                      f"min={d['min_pct']:+.1f}% wipes={d['wipeouts_gt20']}")

    # ── 7e. SKEW contrarian post-2011 + VIX-SKEW orthogonality ──
    print("\n  7e. SKEW contrarian post-2011 + ortogonalidad VIX×SKEW")
    # Correlation VIX vs SKEW
    valid_idx = vix_df.dropna(subset=["val"]).index.intersection(skew_df.dropna(subset=["val"]).index)
    vx = vix_df.loc[valid_idx, "val"].values
    sk = skew_df.loc[valid_idx, "val"].values
    rho_vix_skew = np.corrcoef(vx, sk)[0, 1]
    print(f"    ρ(VIX, SKEW) = {rho_vix_skew:.4f} (esperado ≈ -0.185)")
    # Post-2011
    post11_idx = [d for d in valid_idx if d >= pd.Timestamp("2011-02-01")]
    vx11 = vix_df.loc[post11_idx, "val"].values
    sk11 = skew_df.loc[post11_idx, "val"].values
    rho_post11 = np.corrcoef(vx11, sk11)[0, 1]
    print(f"    ρ(VIX, SKEW) post-2011 = {rho_post11:.4f}")
    # χ² contingency on events
    vx_hi = vix_df.loc[valid_idx, "d1_idx"] >= 4
    sk_hi = skew_df.loc[valid_idx, "d1_idx"] >= 4
    from scipy.stats import chi2_contingency
    tab = pd.crosstab(vx_hi, sk_hi)
    if tab.shape == (2, 2):
        chi2, p, _, _ = chi2_contingency(tab)
        print(f"    χ²(VIX↑, SKEW↑) = {chi2:.1f}, p={p:.2e}")
        p_both = (vx_hi & sk_hi).mean() * 100
        print(f"    P(PÁNICO TOTAL) = {p_both:.2f}% de días")
    # SKEW D1 extremes forward
    for label_name, idx_val in [("BLACK_SWAN_PARANOIA", 5), ("TAIL_PARANOIA", 4),
                                 ("LOW_TAIL_RISK", 0), ("NORMAL_TAIL_RISK", 1)]:
        mask = skew_df["d1_idx"] == idx_val
        dates = [d for d, m in zip(common_idx, mask) if m]
        dedup, fwd = measure_forward(spy, dates)
        if len(dedup) >= 3:
            ev20, lo20, hi20, n20 = boot_ci(np.array(fwd[20]))
            print(f"    SKEW {label_name}: {len(dedup)} señales, 20d EV={ev20*100:+.2f}% CI95[{lo20*100:+.1f},{hi20*100:+.1f}] N={n20}")

    # ── 7f. VIX D2 flip↓ = timing (elimina wipeouts) ──
    print("\n  7f. VIX D2 flip↓ = timing (elimina wipeouts en CRISIS_SPIKE)")
    vix_crisis = vix_df[vix_df["d1_idx"] == 5].copy()
    if len(vix_crisis) >= 3:
        # D2 "building" (FAST_SPIKE / ACCELERATING) vs "resolving" (FAST_CRUSH / DECELERATING)
        vix_crisis["d2_resolving"] = vix_crisis["d2_label"].isin({"FAST_CRUSH_3D", "DECELERATING_DOWN_3D"})
        # Previous-day D2 sign for flip detection
        vix_crisis["d2_sign"] = np.sign(vix_crisis["d2"].values)
        # D2 flip: current D2 sign is opposite of previous-bar D2 sign
        # Simpler: classify D2 label into building vs resolving
        n_building = (~vix_crisis["d2_resolving"]).sum()
        n_resolving = vix_crisis["d2_resolving"].sum()
        print(f"    CRISIS_SPIKE days: {len(vix_crisis)} total, D2 building={n_building}, D2 resolving={n_resolving}")
        # Forward returns: building vs resolving (dedup)
        for label, mask in [("building (NO entrar)", ~vix_crisis["d2_resolving"]),
                            ("resolving (ENTRAR)", vix_crisis["d2_resolving"])]:
            dates = [d for d, m in zip(vix_crisis.index, mask) if m and d in spy.index]
            dedup, fwd = measure_forward(spy, dates)
            if len(dedup) >= 3:
                for h in FW_HORIZONS:
                    arr = np.array(fwd.get(h, []))
                    arr = arr[~np.isnan(arr)]
                    if len(arr) >= 3:
                        ev, lo, hi, n = boot_ci(arr)
                        wipes = int((arr < -0.20).sum())
                        wins = (arr > 0).mean()
                        print(f"      D2 {label:<25} {h:>3}d: EV={ev*100:>+7.2f}% CI95[{lo*100:+.1f},{hi*100:+.1f}] "
                              f"WR={wins*100:.0f}% wipes={wipes} N={n}")

    # 8. Save JSON report
    report = {
        "title": "CAT 2 — SENTIMIENTO/PROTECCIÓN",
        "sensors": SENSORS,
        "sigmet_summary": {t: {"total": len(sigmets_db[t]), "by_type": dict(Counter(sigmets_db[t]["type"])) if len(sigmets_db[t]) > 0 else {}}
                          for t in SENSORS if t in sigmets_db},
        "grade_a": grade_a_results,
        "cat2_protection_index_last": float(last_cat2),
    }
    out_path = ROOT / "scratch" / "cat2_sentimiento_report.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n{'=' * 80}")
    print(f"Reporte JSON: {out_path}")
    print(f"{'=' * 80}")

    store.close()


if __name__ == "__main__":
    main()