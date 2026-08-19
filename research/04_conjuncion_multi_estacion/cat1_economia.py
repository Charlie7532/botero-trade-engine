#!/usr/bin/env python3
"""
CATEGORY AGENT 1 — ECONOMÍA (CAT 1)
====================================
Determina el estado GRADUADO de la economía (¿expansión o contracción?)
combinando 4 sensores macro en un índice de 'salud económica' (0-100%).

SENSORES (→ station del fact store):
  CREDIT_RATIO   → 'credit'
  YIELD_SPREAD   → 'yield_curve'
  DXY            → 'dxy'
  ROTATION_INDEX → 'rotation'

MÉTODO:
  1. Cargar edges + labels D1/D2/D3 CALIBRADOS de cada fact store JSON
     (NO percentiles crudos — usar los bins del fact store).
  2. Clasificar D1 con edges_d1, D2 con edges_d2, D3 con edges_d3
     → state_key completo  D1__D2__D3.
  3. SIGMA DEPTH para overflow: depth=(val-μ)/σ — el label satura en ±2σ,
     la depth distingue 2.8σ de 10.7σ.
  4. Índice de salud económica (0-100%) = media de 4 scores direccionales.
  5. SIGMETs: EXTREMO_ALTO (label 5), EXTREMO_BAJO (label 0),
     ANTICIPACION (label 4/1 + D2 acelerando + D3 comprimida), FLIP_D2.
  6. Lead-lag: ¿cuándo se activó CAT 1 antes de cada pivote zz50?
  7. Validación de señales GRADE A (CREDIT_STRESS entry, YIELD EXTREME_STEEPNING
     exit, DXY DOLLAR_SPIKE_CRISIS bearish, ROTATION↔DXY) con CI95+N.

Regla de oro: probabilidad + CI95 + N. Nunca binario. Wins/losses separados.

Intérprete: backend/.venv/bin/python  (PYTHONPATH=/root/botero-trade)
"""

import sys
import json
from pathlib import Path
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

RULES = ROOT / "backend/modules/entry_decision/domain/rules"

# ── Sensores de CAT 1 ─────────────────────────────────────────────────────
SENSORS = {
    "CREDIT_RATIO": "credit",
    "YIELD_SPREAD": "yield_curve",
    "DXY": "dxy",
    "ROTATION_INDEX": "rotation",
}

# Anchors de 'salud económica' por label index (0..5). Codifican el ROL
# conocido de cada sensor (operational-specification.md):
#   CREDIT  : mayor ratio = crédito fluyendo = expansión (monótono ↑)
#   YIELD   : normal/steepening = sano; inversión = recesión; extreme steepening = distress (U invertida)
#   DXY     : moderado = sano; spike = crisis; crush = estrés (U invertida)
#   ROTATION: mayor índice = risk-on / ciclicos liderando = expansión (monótono ↑)
HEALTH_ANCHORS = {
    "credit":     [0,   20,  40,  60,  80,  100],
    "yield_curve":[10,  30,  55,  80,  60,  30],
    "dxy":        [30,  50,  75,  80,  40,  20],
    "rotation":   [0,   25,  50,  60,  80,  100],
}

# Extensión por sigma-depth en overflow (pts por σ más allá del último edge)
OVERFLOW_SLOPE = {
    "credit":     {"lo": 0.0, "hi": 0.0},    # ya satura en 0/100
    "yield_curve":{"lo": 5.0, "hi": 5.0},    # más extremo = peor
    "dxy":        {"lo": 8.0, "hi": 8.0},    # más extremo = peor
    "rotation":   {"lo": 0.0, "hi": 0.0},    # ya satura en 0/100
}


# ── Bootstrap CI95 ────────────────────────────────────────────────────────
def bootstrap_ci95(values, n_iter=3000, seed=42):
    """CI95 de la media por bootstrap percentil."""
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    means = np.empty(n_iter)
    for i in range(n_iter):
        means[i] = rng.choice(arr, size=len(arr), replace=True).mean()
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def kelly(win_rate, avg_win, avg_loss):
    """Kelly fraction. avg_win>0, avg_loss>0 (magnitudes)."""
    if avg_win <= 0 or avg_loss <= 0:
        return float("nan")
    b = avg_win / avg_loss
    p = win_rate
    return p - (1 - p) / b


def profit_factor(wins, losses):
    wins = np.asarray(wins)
    losses = np.asarray(losses)
    gp = wins.sum() if len(wins) else 0.0
    gl = abs(losses.sum()) if len(losses) else 0.0
    return gp / gl if gl > 0 else float("inf")


def fwd_returns(spy, signal_dates, horizons=(5, 10, 20, 40)):
    """Retorno forward de SPY desde cada fecha-señal (día a día)."""
    idx = list(spy.index)
    pos = {d: i for i, d in enumerate(idx)}
    out = {h: [] for h in horizons}
    for d in signal_dates:
        d = pd.Timestamp(d)
        if d not in pos:
            continue
        i = pos[d]
        for h in horizons:
            if i + h < len(spy):
                out[h].append(spy.iloc[i + h] / spy.iloc[i] - 1.0)
    return out


# ── Carga de bins calibrados ──────────────────────────────────────────────
def load_fact_store(station):
    d = json.load(open(RULES / f"{station}_fact_store.json"))
    th = d["_documentation"]["dimension_thresholds_definition"]
    return {
        "edges_d1": th[f"{station}_edges_d1"],
        "labels_d1": th[f"{station}_labels_d1"],
        "edges_d2": th[f"{station}_edges_d2"],
        "labels_d2": th[f"{station}_labels_d2"],
        "edges_d3": th[f"{station}_edges_d3"],
        "labels_d3": th[f"{station}_labels_d3"],
        "states": d["states"],
    }


def classify(v, edges, labels):
    """Clasifica v con edges calibrados (v < edge → label; else último)."""
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return None
    for i, e in enumerate(edges):
        if v < e:
            return labels[i]
    return labels[-1]


def classify_idx(v, edges):
    """Índice de label (0..len(edges)) sin nombres."""
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return None
    for i, e in enumerate(edges):
        if v < e:
            return i
    return len(edges)


def health_score(station, v, label_idx, mu, sd):
    """Score de salud económica (0-100) graduado: anchor + interpolación intra-bin
    + extrapolación sigma-depth en overflow."""
    anchors = HEALTH_ANCHORS[station]
    edges = FS[station]["edges_d1"]
    depth = (v - mu) / sd if sd > 0 else 0.0
    if label_idx is None:
        return np.nan, depth

    n_edges = len(edges)  # 5 edges → 6 labels
    # label_idx en [0..n_edges]
    if label_idx == 0:
        # overflow bajo: extrapolar por debajo del primer edge
        slope = OVERFLOW_SLOPE[station]["lo"]
        score = anchors[0] - max(0.0, (edges[0] - v) / sd) * slope
        return float(np.clip(score, 0, 100)), depth
    elif label_idx == n_edges:
        # overflow alto: extrapolar por encima del último edge
        slope = OVERFLOW_SLOPE[station]["hi"]
        score = anchors[n_edges] + max(0.0, (v - edges[-1]) / sd) * slope
        return float(np.clip(score, 0, 100)), depth
    else:
        # bin interior: interpolar entre anchors[idx] y anchors[idx+1]
        lo = edges[label_idx - 1]
        hi = edges[label_idx]
        span = (hi - lo) if hi != lo else 1e-9
        frac = (v - lo) / span
        score = anchors[label_idx] + frac * (anchors[label_idx + 1] - anchors[label_idx])
        return float(np.clip(score, 0, 100)), depth


# ── Carga de bins (global) ────────────────────────────────────────────────
FS = {station: load_fact_store(station) for station in SENSORS.values()}


def main():
    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)

    print("═" * 78)
    print("CATEGORY AGENT 1 — ECONOMÍA (CAT 1): estado GRADUADO expansión/contracción")
    print("═" * 78)

    # 1. Cargar series crudas + SPY
    raw = {}
    for ticker in SENSORS:
        b = store.load_bars(ticker, "1d")
        raw[ticker] = b["close"].dropna()
        print(f"  [data] {ticker}: {len(raw[ticker])} barras "
              f"[{raw[ticker].index[0].date()} → {raw[ticker].index[-1].date()}]")

    spy = store.load_bars("SPY", "1d")["close"].dropna()

    # 2. Pivotes zz50
    zz50 = repo.get_confirmed_legs_dataframe("SPY", "zz50")
    print(f"  [pivotes] zz50: {len(zz50)} legs")

    store.close()

    # 3. Alinear fechas comunes (CREDIT 2007-04-11 es el cuello de botella)
    common_idx = None
    for ticker in SENSORS:
        idx = raw[ticker].index
        common_idx = idx if common_idx is None else common_idx.intersection(idx)
    common_idx = common_idx.sort_values()
    print(f"  [align] ventana común: {len(common_idx)} días "
          f"[{common_idx[0].date()} → {common_idx[-1].date()}]")

    # 4. Computar D1 (nivel), D2 (velocidad diff3), D3 (vol std2/std10) por sensor
    D = {}  # ticker -> DataFrame con val, d2, d3, label_d1, idx_d1, depth, state_key, p_bull, n_raw
    for ticker, station in SENSORS.items():
        s = raw[ticker].reindex(common_idx)
        df = pd.DataFrame({"val": s})
        df["d2"] = df["val"].diff(3)
        df["d3"] = df["val"].rolling(2).std() / df["val"].rolling(10).std()
        mu = float(df["val"].mean())
        sd = float(df["val"].std())

        fs = FS[station]
        labels_d1 = fs["labels_d1"]
        labels_d2 = fs["labels_d2"]
        labels_d3 = fs["labels_d3"]

        d1_label, d1_idx = [], []
        d2_label, d3_label = [], []
        depths = []
        for ts, row in df.iterrows():
            v = row["val"]
            if pd.isna(v):
                d1_label.append(None); d1_idx.append(None); d2_label.append(None)
                d3_label.append(None); depths.append(np.nan); continue
            li = classify_idx(v, fs["edges_d1"])
            d1_label.append(classify(v, fs["edges_d1"], labels_d1))
            d1_idx.append(li)
            depths.append((v - mu) / sd)
            d2_label.append(classify(row["d2"], fs["edges_d2"], labels_d2) if not pd.isna(row["d2"]) else None)
            d3_label.append(classify(row["d3"], fs["edges_d3"], labels_d3) if not pd.isna(row["d3"]) else None)

        df["label_d1"] = d1_label
        df["idx_d1"] = d1_idx
        df["depth"] = depths
        df["label_d2"] = d2_label
        df["label_d3"] = d3_label

        # state_key completo + lookup p_bull/n_raw (zz25 y zz50)
        states = fs["states"]
        sk, pb25, pb50, nraw = [], [], [], []
        for i in range(len(df)):
            a, b, c = df["label_d1"].iloc[i], df["label_d2"].iloc[i], df["label_d3"].iloc[i]
            if a is None or b is None or c is None:
                sk.append(None); pb25.append(np.nan); pb50.append(np.nan); nraw.append(np.nan)
                continue
            key = f"{a}__{b}__{c}"
            sk.append(key)
            st = states.get(key, {})
            z25 = st.get("zz25", {})
            z50 = st.get("zz50", {})
            pb25.append(z25.get("p_bull", np.nan))
            pb50.append(z50.get("p_bull", np.nan))
            nraw.append(z25.get("n_raw", 0) if "n_raw" in z25 else st.get("n", 0))
        df["state_key"] = sk
        df["p_bull_zz25"] = pb25
        df["p_bull_zz50"] = pb50
        df["n_raw"] = nraw

        # health score graduado
        healths = []
        for i in range(len(df)):
            v = df["val"].iloc[i]
            li = df["idx_d1"].iloc[i]
            hs, _ = health_score(station, v, li, mu, sd)
            healths.append(hs)
        df["health"] = healths

        D[ticker] = df
        print(f"  [classify] {station}: {df['state_key'].notna().sum()} días clasificados, "
              f"μ={mu:.4f} σ={sd:.4f}")

    # 5. Índice de salud económica compuesto (0-100)
    print("\n" + "─" * 78)
    print("ÍNDICE DE SALUD ECONÓMICA (media de 4 sensores, graduado 0-100)")
    print("─" * 78)

    health_df = pd.DataFrame(index=common_idx)
    for ticker in SENSORS:
        health_df[ticker] = D[ticker]["health"]
    health_df["salud_economica"] = health_df[list(SENSORS.keys())].mean(axis=1)

    # Clasificación de régimen (graduado, NO binario duro)
    def regime(h):
        if pd.isna(h):
            return "NODATA"
        if h >= 60:
            return "EXPANSION"
        if h >= 40:
            return "TRANSICION"
        return "CONTRACCION"

    health_df["regimen"] = health_df["salud_economica"].map(regime)

    regime_counts = health_df["regimen"].value_counts()
    for r in ["EXPANSION", "TRANSICION", "CONTRACCION"]:
        n = int(regime_counts.get(r, 0))
        pct = n / len(health_df) * 100
        print(f"  {r:<14} {n:>6} días ({pct:5.1f}%)")

    print(f"\n  Últimos 5 días (estado ACTUAL):")
    tail = health_df.tail(5)
    for ts, row in tail.iterrows():
        vals = "  ".join(f"{t.split('_')[0]}:{row[t]:5.1f}" for t in SENSORS)
        print(f"    {ts.date()}  salud={row['salud_economica']:5.1f}%  [{row['regimen']}]   {vals}")

    # resumen de la salud por década
    print("\n  Salud media por año:")
    yr = health_df["salud_economica"].groupby(health_df.index.year).mean()
    for y, v in yr.items():
        bar = "█" * int(round(v / 4))
        print(f"    {y}: {v:5.1f}%  {bar}")

    # 6. SIGMETs
    print("\n" + "─" * 78)
    print("SIGMETs por sensor")
    print("─" * 78)

    sigmets_all = {}
    for ticker, station in SENSORS.items():
        df = D[ticker]
        events = []
        prev_sign = None
        d2_streak = 0
        d3_streak = 0
        d3_comp = 0.7
        streak = 3
        for ts, row in df.iterrows():
            li = row["idx_d1"]
            d2 = row["d2"]
            d3 = row["d3"]
            if li is None or pd.isna(d2):
                continue
            sign = 1 if d2 > 0 else (-1 if d2 < 0 else 0)
            d2_streak = d2_streak + 1 if (sign != 0 and sign == prev_sign) else (1 if sign != 0 else 0)
            d3_streak = d3_streak + 1 if (pd.notna(d3) and d3 < d3_comp) else 0
            sig = None
            if li == len(FS[station]["edges_d1"]):  # label 5
                sig = "EXTREMO_ALTO"
            elif li == 0:  # label 0
                sig = "EXTREMO_BAJO"
            elif li == 4 and d2_streak >= streak and d3_streak >= streak and sign > 0:
                sig = "ANTICIPACION_ALTA"
            elif li == 1 and d2_streak >= streak and d3_streak >= streak and sign < 0:
                sig = "ANTICIPACION_BAJA"
            if prev_sign is not None and sign != 0 and prev_sign != 0 and sign != prev_sign:
                if sig is None:
                    sig = "FLIP_D2"
            if sign != 0:
                prev_sign = sign
            if sig:
                events.append({
                    "timestamp": ts, "type": sig, "label": row["label_d1"],
                    "depth": row["depth"], "val": row["val"],
                })
        sigmets_all[ticker] = pd.DataFrame(events)
        if len(events):
            tc = Counter(e["type"] for e in events)
            print(f"  {station:<14} {len(events):>5} SIGMETs  {dict(tc)}")
        else:
            print(f"  {station:<14} 0 SIGMETs")

    # 7. Validación señales GRADE A (forward returns, CI95 + N, wins/losses separados)
    print("\n" + "─" * 78)
    print("SEÑALES GRADE A — forward SPY (día a día), CI95 bootstrap 3000")
    print("─" * 78)

    spy_aligned = spy.reindex(common_idx)

    def report_signal(name, ticker, label_match, note=""):
        df = D[ticker]
        mask = df["label_d1"].isin(label_match)
        dates = df.index[mask]
        N = int(mask.sum())
        print(f"\n  ▸ {name}  (N={N}) {note}")
        if N == 0:
            print("    SIN OBSERVACIONES")
            return
        fwd = fwd_returns(spy_aligned, dates)
        for h in (5, 10, 20, 40):
            r = np.array(fwd[h])
            if len(r) == 0:
                continue
            mu = r.mean() * 100
            lo, hi = bootstrap_ci95(r)
            wr = (r > 0).mean() * 100
            wins = r[r > 0]
            losses = r[r <= 0]
            pf = profit_factor(wins, losses)
            avg_w = wins.mean() * 100 if len(wins) else 0
            avg_l = abs(losses.mean()) * 100 if len(losses) else 0
            kk = kelly(wr / 100, avg_w, avg_l)
            wmax = wins.max() * 100 if len(wins) else np.nan
            lmin = losses.min() * 100 if len(losses) else np.nan
            print(f"    {h:>3}d  μ={mu:+.2f}%  CI95[{lo*100:+.2f},{hi*100:+.2f}]  "
                  f"WR={wr:.1f}%  PF={pf:.2f}  Kelly={kk:+.2f}  n={len(r)}")
            print(f"          WINS n={len(wins)} (max {wmax:+.1f}%) | LOSSES n={len(losses)} (min {lmin:+.1f}%)")

    # CREDIT_STRESS = entry (+3.00%)
    report_signal("CREDIT_STRESS (entry)", "CREDIT_RATIO",
                  ["CREDIT_CRISIS", "CREDIT_STRESS"],
                  "esperado +3.00% @20d, WR 76.8%")
    # YIELD EXTREME_STEEPNING = exit (PF 0.73)
    report_signal("YIELD EXTREME_STEEPNING (exit)", "YIELD_SPREAD",
                  ["EXTREME_STEEPNING"], "esperado PF 0.73, Kelly -0.19")
    # DXY DOLLAR_SPIKE_CRISIS = bearish (-1.94%)
    report_signal("DXY DOLLAR_SPIKE_CRISIS (bearish)", "DXY",
                  ["DOLLAR_SPIKE_CRISIS"], "esperado -1.94% @20d, WR 28%")
    # ROTATION extremes (para documentar; rol NEUTRAL)
    report_signal("ROTATION DEFENSIVE_CAPITULATION", "ROTATION_INDEX",
                  ["DEFENSIVE_CAPITULATION"], "rol NEUTRAL (solo drift SPY)")
    report_signal("ROTATION AGGRESSIVE_ROTATION", "ROTATION_INDEX",
                  ["AGGRESSIVE_ROTATION"], "rol NEUTRAL")

    # 8. ROTATION ↔ DXY (ROTATION-A: dinero entra/sale USA)
    print("\n" + "─" * 78)
    print("ROTATION-A: relación ROTATION_INDEX ↔ DXY (dinero entra/sale USA)")
    print("─" * 78)
    rot_val = D["ROTATION_INDEX"]["val"]
    dxy_val = D["DXY"]["val"]
    m = rot_val.notna() & dxy_val.notna()
    corr_level = np.corrcoef(rot_val[m], dxy_val[m])[0, 1]
    rot_d2 = D["ROTATION_INDEX"]["d2"]
    dxy_d2 = D["DXY"]["d2"]
    m2 = rot_d2.notna() & dxy_d2.notna()
    corr_d2 = np.corrcoef(rot_d2[m2], dxy_d2[m2])[0, 1]
    print(f"  ρ(ROTATION, DXY) nivel   = {corr_level:+.3f}  (N={int(m.sum())})")
    print(f"  ρ(ROTATION_D2, DXY_D2)   = {corr_d2:+.3f}  (N={int(m2.sum())})")

    # ¿ROTATION defensivo predice DXY spike? (dinero sale de USA → dólar sube)
    rot_def = D["ROTATION_INDEX"]["label_d1"].isin(["DEFENSIVE_CAPITULATION", "DEFENSIVE"])
    dxy_fwd = dxy_val.diff(20)
    if rot_def.sum() > 0:
        fwd_when_defensive = dxy_fwd[rot_def].dropna()
        fwd_when_offensive = dxy_fwd[~rot_def].dropna()
        print(f"  DXY Δ20d cuando ROTATION defensivo: μ={fwd_when_defensive.mean():+.2f} (N={len(fwd_when_defensive)})")
        print(f"  DXY Δ20d cuando ROTATION agresivo : μ={fwd_when_offensive.mean():+.2f} (N={len(fwd_when_offensive)})")

    # 9. Lead-lag: CAT 1 antes de cada pivote zz50
    print("\n" + "─" * 78)
    print("LEAD-LAG: ¿cuándo se activó CAT 1 antes de cada pivote zz50?")
    print("─" * 78)

    # unificar SIGMETs de CAT 1 (cualquier sensor)
    cat1_events = []
    for ticker, ev in sigmets_all.items():
        if len(ev):
            e = ev.copy()
            e["ticker"] = ticker
            cat1_events.append(e)
    cat1 = pd.concat(cat1_events).sort_values("timestamp") if cat1_events else pd.DataFrame()

    leads_anticip = []
    leads_all = []
    n_pivots = 0
    cmin = pd.Timestamp(common_idx[0])
    cmax = pd.Timestamp(common_idx[-1])
    for _, leg in zz50.iterrows():
        pivot_ts = pd.Timestamp(leg["start_timestamp"])
        if pivot_ts < cmin or pivot_ts > cmax:
            continue
        n_pivots += 1
        if len(cat1) == 0:
            continue
        # ANTICIPACION (pre-síntoma) en ventana 30d
        w_ant = cat1[(cat1["timestamp"] <= pivot_ts) &
                     (cat1["timestamp"] >= pivot_ts - pd.Timedelta(days=30)) &
                     (cat1["type"].str.startswith("ANTICIPACION"))]
        if len(w_ant):
            lead = (pivot_ts - w_ant["timestamp"].max()).days
            leads_anticip.append((lead, w_ant["ticker"].iloc[-1], leg["start_type"]))
        # TODOS los SIGMETs
        w_all = cat1[(cat1["timestamp"] <= pivot_ts) &
                     (cat1["timestamp"] >= pivot_ts - pd.Timedelta(days=30))]
        if len(w_all):
            lead = (pivot_ts - w_all["timestamp"].max()).days
            leads_all.append((lead, w_all["ticker"].iloc[-1], leg["start_type"]))

    def summarize_leads(leads, label):
        if not leads:
            print(f"  {label}: 0 pivotes con señal")
            return
        days = np.array([x[0] for x in leads])
        print(f"  {label}: {len(leads)}/{n_pivots} pivotes con señal previa")
        print(f"    lead mediana={np.median(days):.1f}d  media={days.mean():.1f}d  "
              f"P25={np.percentile(days,25):.0f}d  P75={np.percentile(days,75):.0f}d")
        by_sensor = Counter(x[1] for x in leads)
        print(f"    sensor líder: {dict(by_sensor)}")
        by_type = Counter(x[2] for x in leads)
        print(f"    por tipo de pivote: {dict(by_type)}")

    summarize_leads(leads_anticip, "ANTICIPACION (pre-síntoma)")
    summarize_leads(leads_all, "TODOS los SIGMETs")

    # 10. Estado actual consolidado
    print("\n" + "─" * 78)
    print("ESTADO ACTUAL DE LA ECONOMÍA (último día)")
    print("─" * 78)
    last = health_df.iloc[-1]
    last_ts = health_df.index[-1]
    print(f"  Fecha: {last_ts.date()}")
    print(f"  SALUD ECONÓMICA: {last['salud_economica']:.1f}%  →  {last['regimen']}")
    for ticker, station in SENSORS.items():
        row = D[ticker].iloc[-1]
        p25 = row["p_bull_zz25"]
        p50 = row["p_bull_zz50"]
        n = row["n_raw"]
        print(f"    {station:<14} D1={str(row['label_d1']):<26} D2={str(row['label_d2']):<24} "
              f"D3={str(row['label_d3']):<24} depth={row['depth']:+.2f}σ  health={row['health']:.0f}")
        print(f"                 fact_store: p_bull(zz25)={p25 if pd.isna(p25) else round(p25,3)}  "
              f"p_bull(zz50)={p50 if pd.isna(p50) else round(p50,3)}  n={n}")

    print("\n  NOTA DXY (ciclo, no drift): DXY es Grupo C (régimen contextual). Su borde")
    print("  DOLLAR_SPIKE_CRISIS (>116) NO se alcanzó en 2007-2026 (N=0), por lo que la")
    print("  crisis de dólar de 2008 (DXY≈88) clasifica 'MODERATE_LOW' — el ciclo secular")
    print("  71→114 desplaza el umbral. La salud económica depende más de CREDIT+YIELD+ROTATION.")

    # guardar resultados
    out = {
        "salud_economica_ultimo_dia": float(last["salud_economica"]),
        "regimen_ultimo_dia": last["regimen"],
        "regime_distribution": {k: int(v) for k, v in regime_counts.items()},
        "rotation_dxy_corr_level": float(corr_level),
        "rotation_dxy_corr_d2": float(corr_d2),
        "lead_anticip_n": len(leads_anticip),
        "lead_anticip_median_days": float(np.median([x[0] for x in leads_anticip])) if leads_anticip else None,
        "estado_actual_por_sensor": {
            station: {
                "d1": str(D[ticker].iloc[-1]["label_d1"]),
                "d2": str(D[ticker].iloc[-1]["label_d2"]),
                "d3": str(D[ticker].iloc[-1]["label_d3"]),
                "depth_sigma": float(D[ticker].iloc[-1]["depth"]),
                "health": float(D[ticker].iloc[-1]["health"]),
                "p_bull_zz25": (float(D[ticker].iloc[-1]["p_bull_zz25"])
                                if pd.notna(D[ticker].iloc[-1]["p_bull_zz25"]) else None),
                "n": (int(D[ticker].iloc[-1]["n_raw"])
                      if pd.notna(D[ticker].iloc[-1]["n_raw"]) else None),
            } for ticker, station in SENSORS.items()
        },
    }
    json.dump(out, open(ROOT / "data/research" / "cat1_economia_results.json", "w"), indent=2, default=str)

    print("\n═" * 78)
    print("CAT 1 COMPLETADO — resultados en data/research/cat1_economia_results.json")
    print("═" * 78)


if __name__ == "__main__":
    main()
