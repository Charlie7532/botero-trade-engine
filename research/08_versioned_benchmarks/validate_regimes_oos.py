#!/usr/bin/env python3
"""
VALIDADOR OOS WALK-FORWARD — 5 regímenes de secuencia (Botero Trade)
=====================================================================
Convierte "el régimen es X" en "X es OPERABLE con CI95 y OOS IC>0".

La validación previa medía forward returns DESDE EL PIVOTE zigzag (look-ahead:
el pivote se confirma después de los hechos). Este validador mide DESDE LA
BARRA DE SEÑAL — el instante en que la permutación de activación CAT1/CAT2/CAT3
queda COMPLETA (la 3ª categoría dispara su primer SIGMET en la ventana de 30d).
En esa barra el régimen es identificable en tiempo real → entrada honesta, sin
look-ahead.

MÉTODO:
1. Replica el clasificador de secuencias (permutación de activación CAT1/CAT2/CAT3).
2. Entrada en BARRA DE SEÑAL (barra de la 3ª activación), forward 5/10/20/40d.
3. Walk-forward OOS expanding-window (K folds cronológicos) — el veredicto sale
   de OOS, no de full-sample.
4. Por régimen: N, retorno medio, CI95 bootstrap 3000, WR, PF, Kelly, wins/losses
   separados (full-sample descriptivo) + stats OOS walk-forward.
5. Veredicto: OPERABLE (OOS IC>0 y CI95 no cruza 0) vs NO (ruido) vs INSUFICIENTE.
6. Baseline SPY = TODOS los días (no solo pivotes), en la misma ventana temporal.

Categorías (mapeo exacto del task):
  CAT1 ECONOMIA:    CREDIT_RATIO, YIELD_SPREAD, DXY
  CAT2 SENTIMIENTO: VIX, VVIX, CBOE_PCR, SKEW
  CAT3 ACCION:      S5TW, SV5_TURBULENCE, FG

3 escalas zigzag (zz25/zz50/zz75). Bootstrap CI95 3000.

Uso:
  PYTHONPATH=/root/botero-trade backend/.venv/bin/python scratch/validate_regimes_oos.py
Salida: consola + scratch/validate_regimes_oos_report.json
                       + scratch/validate_regimes_oos_REPORT.md
"""

import sys
import json
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

# ── Config ─────────────────────────────────────────────────────────────────
CATEGORIES = {
    1: {"name": "ECONOMIA",    "tickers": ["CREDIT_RATIO", "YIELD_SPREAD", "DXY"]},
    2: {"name": "SENTIMIENTO", "tickers": ["VIX", "VVIX", "CBOE_PCR", "SKEW"]},
    3: {"name": "ACCION",      "tickers": ["S5TW", "SV5_TURBULENCE", "FG"]},
}

# Los 5 regímenes (explosivo agrupa CAT3-lidera: (3,1,2) y (3,2,1))
REGIMES = {
    "macro-driven":       {"perms": [(1, 2, 3)],            "label": "CAT1→CAT2→CAT3 (macro-driven)"},
    "cuchillo":           {"perms": [(1, 3, 2)],            "label": "CAT1→CAT3→CAT2 (cuchillo cayendo)"},
    "comprar-miedo":      {"perms": [(2, 3, 1)],            "label": "CAT2→CAT3→CAT1 (comprar miedo)"},
    "proteccion-lidera":  {"perms": [(2, 1, 3)],            "label": "CAT2→CAT1→CAT3 (protección lidera)"},
    "explosivo":          {"perms": [(3, 1, 2), (3, 2, 1)], "label": "CAT3-lidera (explosivo/violento)"},
}

PCT_HIGH = 90
PCT_LOW = 10
D3_COMPRESSED = 0.7
STREAK = 3
WINDOW_DAYS = 30

FW_HORIZONS = [5, 10, 20, 40]
SCALES = ["zz25", "zz50", "zz75"]
N_BOOT = 3000
BOOT_SEED = 42
K_FOLDS = 8        # folds cronológicos expanding-window
MIN_TEST_N = 3     # mínimo de entradas por fold para contarlo
MIN_N = 20         # mínimo de entradas totales para veredicto


# ── Helpers estadísticos ───────────────────────────────────────────────────
def boot_ci_mean(arr, ci=95, n_boot=N_BOOT, seed=BOOT_SEED):
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    means = rng.choice(arr, size=(n_boot, len(arr)), replace=True).mean(axis=1)
    lo, hi = np.percentile(means, [(100 - ci) / 2, 100 - (100 - ci) / 2])
    return float(arr.mean()), float(lo), float(hi)


def boot_ci_diff(a, b, ci=95, n_boot=N_BOOT, seed=BOOT_SEED):
    a = np.asarray(a, float); b = np.asarray(b, float)
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    if len(a) < 3 or len(b) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    ma = rng.choice(a, size=(n_boot, len(a)), replace=True).mean(axis=1)
    mb = rng.choice(b, size=(n_boot, len(b)), replace=True).mean(axis=1)
    diffs = ma - mb
    lo, hi = np.percentile(diffs, [(100 - ci) / 2, 100 - (100 - ci) / 2])
    return float(a.mean() - b.mean()), float(lo), float(hi)


def regime_stats(returns):
    """Full-sample descriptivo de un régimen a un horizonte."""
    arr = np.asarray(returns, float)
    arr = arr[~np.isnan(arr)]
    n = len(arr)
    if n < 1:
        return None
    wins = arr[arr > 0]
    losses = arr[arr <= 0]
    gw = float(np.sum(wins)) if len(wins) else 0.0
    gl = float(abs(np.sum(losses))) if len(losses) else 0.0
    pf = gw / gl if gl > 0 else float("inf")
    wr_up = float(np.mean(arr > 0))
    avg_w = float(np.mean(wins)) if len(wins) else 0.0
    avg_l = float(abs(np.mean(losses))) if len(losses) else 0.0
    wlr = avg_w / avg_l if avg_l > 0 else float("inf")
    kelly = (wr_up - (1 - wr_up) / wlr) if (avg_l > 0 and wlr > 0) else np.nan
    mean, lo, hi = boot_ci_mean(arr)
    wipe = losses[losses < -0.20]
    return {
        "N": n,
        "mean": mean, "ci95": [lo, hi],
        "wr": wr_up,
        "pf": None if np.isinf(pf) else pf,
        "kelly": None if (kelly is None or (isinstance(kelly, float) and np.isnan(kelly))) else float(kelly),
        "std": float(np.std(arr)),
        "wins": {
            "n": int(len(wins)),
            "mean": float(np.mean(wins)) if len(wins) else None,
            "median": float(np.median(wins)) if len(wins) else None,
            "p75": float(np.percentile(wins, 75)) if len(wins) >= 4 else None,
            "p90": float(np.percentile(wins, 90)) if len(wins) >= 10 else None,
            "max": float(np.max(wins)) if len(wins) else None,
        },
        "losses": {
            "n": int(len(losses)),
            "mean": float(np.mean(losses)) if len(losses) else None,
            "median": float(np.median(losses)) if len(losses) else None,
            "p25": float(np.percentile(losses, 25)) if len(losses) >= 4 else None,
            "p10": float(np.percentile(losses, 10)) if len(losses) >= 10 else None,
            "min": float(np.min(losses)) if len(losses) else None,
            "wipeouts_gt20pct": int(len(wipe)),
        },
    }


# ── Carga y cálculo de series ──────────────────────────────────────────────
def load_series(store, tickers):
    series = {}
    for t in tickers:
        try:
            b = store.load_bars(t, "1d")
            if b is not None and len(b) > 0:
                c = b["close"].copy()
                c.index = pd.to_datetime(c.index).tz_localize(None).normalize()
                c = c[~c.index.duplicated(keep="last")].sort_index().dropna()
                if len(c) > 0:
                    series[t] = c
        except Exception:
            pass
    return series


def compute_d1_d2_d3(series):
    df = pd.DataFrame({"val": series})
    df["d2"] = df["val"].diff(3)
    s2 = df["val"].rolling(2).std()
    s10 = df["val"].rolling(10).std()
    d3 = (s2 / s10).replace([np.inf, -np.inf], np.nan)
    df["d3"] = d3.fillna(1.0)
    df["d1_pct"] = df["val"].expanding().rank(pct=True) * 100
    return df


def detect_sigmet(df, pct_high=PCT_HIGH, pct_low=PCT_LOW, d3_comp=D3_COMPRESSED, streak=STREAK):
    events = []
    prev_sign = None
    d2_streak = 0
    d3_streak = 0
    for row in df.itertuples():
        pct = row.d1_pct
        d2 = row.d2
        d3 = row.d3
        if pd.isna(pct) or pd.isna(d2):
            continue
        sign = 1 if d2 > 0 else (-1 if d2 < 0 else 0)
        if sign != 0:
            d2_streak = d2_streak + 1 if sign == prev_sign else 1
        else:
            d2_streak = 0
        d3_streak = d3_streak + 1 if (pd.notna(d3) and d3 < d3_comp) else 0
        sig_type = None
        if 70 <= pct < pct_high and d2_streak >= streak and d3_streak >= streak:
            sig_type = "ANTICIPACION_ALTA"
        elif pct_low < pct <= 30 and d2_streak >= streak and d3_streak >= streak and sign < 0:
            sig_type = "ANTICIPACION_BAJA"
        elif pct >= pct_high:
            sig_type = "EXTREMO_ALTO"
        elif pct <= pct_low:
            sig_type = "EXTREMO_BAJO"
        if prev_sign is not None and sign != 0 and prev_sign != 0 and sign != prev_sign:
            if sig_type is None:
                sig_type = "FLIP_D2"
        if sign != 0:
            prev_sign = sign
        if sig_type:
            events.append({"timestamp": row.Index, "type": sig_type})
    return pd.DataFrame(events)


# ── Clasificador de secuencias con entrada en barra de señal ──────────────
def build_regime_entries(pivots_df, sigmets, window_days=WINDOW_DAYS):
    """Por cada pivote, permutación de 1ª activación + barra de señal (3ª activación)."""
    cat_ts = {}
    for cat_id in [1, 2, 3]:
        ev = sigmets.get(cat_id)
        if ev is None or len(ev) == 0:
            cat_ts[cat_id] = None
        else:
            cat_ts[cat_id] = np.sort(pd.to_datetime(ev["timestamp"]).values)

    entries = []
    for _, leg in pivots_df.iterrows():
        pivot_ts = pd.to_datetime(leg["start_timestamp"]).tz_localize(None).normalize()
        lo = np.datetime64(pivot_ts - pd.Timedelta(days=window_days))
        hi = np.datetime64(pivot_ts)
        first = {}
        for cat_id in [1, 2, 3]:
            arr = cat_ts[cat_id]
            if arr is None:
                continue
            i = np.searchsorted(arr, lo)
            if i < len(arr) and arr[i] <= hi:
                first[cat_id] = pd.Timestamp(arr[i])
        if len(first) == 3:
            ordered = sorted(first.items(), key=lambda x: x[1])
            perm = tuple(c for c, _ in ordered)
            signal_bar = ordered[-1][1]  # barra donde la permutación queda completa
            entries.append({
                "signal_bar": signal_bar,
                "perm": perm,
                "pivot": pivot_ts,
                "type": leg.get("start_type", None),
                "cat_times": first,
            })
    return entries


def fwd_from_bar(bar_ts, spy_index_vals, spy_values, h):
    pos = int(np.searchsorted(spy_index_vals, np.datetime64(bar_ts)))
    if pos >= len(spy_values):
        return None
    if pos + h < len(spy_values):
        return float(spy_values[pos + h] / spy_values[pos] - 1.0)
    return None


def point_biserial(indicator, target):
    """Correlación punto-biserial (Pearson con indicador binario)."""
    x = np.asarray(indicator, float)
    y = np.asarray(target, float)
    m = ~np.isnan(x) & ~np.isnan(y)
    x, y = x[m], y[m]
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    print("═" * 86)
    print("VALIDADOR OOS WALK-FORWARD — 5 regímenes de secuencia")
    print("Entrada en BARRA DE SEÑAL (no pivote) · expanding-window folds")
    print("═" * 86)

    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)

    # 1. SPY
    spy_raw = store.load_bars("SPY", "1d")["close"].copy()
    spy_raw.index = pd.to_datetime(spy_raw.index).tz_localize(None).normalize()
    spy = spy_raw[~spy_raw.index.duplicated(keep="last")].sort_index()
    spy_values = spy.values
    spy_idx_vals = spy.index.values
    print(f"SPY: {spy.index[0].date()} → {spy.index[-1].date()} ({len(spy)} barras)")

    # 2. Series + SIGMETs por categoría
    sigmets = {}
    for cat_id, cat in CATEGORIES.items():
        series = load_series(store, cat["tickers"])
        cat_events = []
        for t, s in series.items():
            df = compute_d1_d2_d3(s)
            ev = detect_sigmet(df)
            if len(ev) > 0:
                ev = ev.copy()
                ev["ticker"] = t
                cat_events.append(ev)
        if cat_events:
            sigmets[cat_id] = pd.concat(cat_events).sort_values("timestamp")
        else:
            sigmets[cat_id] = pd.DataFrame(columns=["timestamp", "type", "ticker"])
        n_tickers = len(series)
        print(f"CAT {cat_id} ({cat['name']}): {len(sigmets[cat_id])} SIGMETs, "
              f"{n_tickers} tickers ({', '.join(series.keys())})")

    # 3. Pivotes por escala → entradas (barra de señal)
    entries_by_scale = {}
    for scale in SCALES:
        pivots_df = repo.get_confirmed_legs_dataframe("SPY", scale)
        if pivots_df is None or len(pivots_df) == 0:
            print(f"{scale}: 0 legs")
            entries_by_scale[scale] = []
            continue
        ents = build_regime_entries(pivots_df, sigmets)
        entries_by_scale[scale] = ents
        n_full = len(ents)
        perm_counts = Counter(e["perm"] for e in ents)
        print(f"{scale}: {len(pivots_df)} legs → {n_full} entradas con 3 categorías "
              f"({dict(sorted(perm_counts.items(), key=lambda x: -x[1]))})")

    store.close()

    # 4. Baseline SPY — TODOS los días (no solo pivotes)
    #    Ventana elegible: desde la 1ª entrada (todas escalas) hasta la última.
    all_signal_bars = [e["signal_bar"] for ents in entries_by_scale.values() for e in ents]
    if not all_signal_bars:
        print("\n⚠ SIN ENTRADAS — abortando")
        return
    eligible_start = min(all_signal_bars)
    eligible_end = max(all_signal_bars)
    eligible_mask = (spy.index >= eligible_start) & (spy.index <= eligible_end)
    eligible_days = spy.index[eligible_mask]
    print(f"\nVentana elegible (donde las 3 categorías coexisten): "
          f"{eligible_start.date()} → {eligible_end.date()} ({len(eligible_days)} días)")

    baseline = {}
    for h in FW_HORIZONS:
        rets = []
        for i in range(len(spy_values)):
            if not (eligible_start <= spy.index[i] <= eligible_end):
                continue
            if i + h < len(spy_values):
                rets.append(spy_values[i + h] / spy_values[i] - 1.0)
        arr = np.array(rets)
        mean, lo, hi = boot_ci_mean(arr)
        baseline[h] = {"N": len(arr), "mean": mean, "ci95": [lo, hi]}
        print(f"  baseline SPY {h:>2}d (todos los días): {mean*100:+.2f}% "
              f"CI95[{lo*100:+.2f},{hi*100:+.2f}] N={len(arr)}")

    # 5. Análisis por régimen × escala × horizonte
    report = {"baseline": baseline, "regimes": {}}
    verdict_rows = []

    for scale in SCALES:
        ents = entries_by_scale.get(scale, [])
        if not ents:
            continue
        report["regimes"][scale] = {}
        for rname, rcfg in REGIMES.items():
            perms = set(rcfg["perms"])
            r_entries = [e for e in ents if e["perm"] in perms]
            report["regimes"][scale][rname] = {"label": rcfg["label"],
                                               "N_entries": len(r_entries),
                                               "horizons": {}}
            if len(r_entries) == 0:
                continue

            # forward returns por horizonte (full-sample, entrada barra de señal)
            fwd = {h: [] for h in FW_HORIZONS}
            fwd_dates = {h: [] for h in FW_HORIZONS}
            for e in r_entries:
                for h in FW_HORIZONS:
                    r = fwd_from_bar(e["signal_bar"], spy_idx_vals, spy_values, h)
                    if r is not None:
                        fwd[h].append(r)
                        fwd_dates[h].append(e["signal_bar"])

            for h in FW_HORIZONS:
                arr = np.array(fwd[h])
                if len(arr) == 0:
                    report["regimes"][scale][rname]["horizons"][h] = None
                    continue

                st = regime_stats(arr)
                # excess vs baseline
                base_mean = baseline[h]["mean"]
                st["excess_vs_baseline"] = float(st["mean"] - base_mean)

                # ── Walk-forward OOS (expanding window, K folds) ──
                wf = walkforward_oos(
                    fwd_dates[h], arr, spy_idx_vals, spy_values, h,
                    eligible_start, eligible_end,
                )
                st["walkforward"] = wf

                # ── Veredicto ──
                verdict = make_verdict(st, wf, len(r_entries))
                st["verdict"] = verdict
                report["regimes"][scale][rname]["horizons"][h] = st

                verdict_rows.append({
                    "scale": scale, "regime": rname, "horizon": h,
                    "label": rcfg["label"], **verdict,
                })

    # 6. Salida consola compacta
    print("\n" + "═" * 86)
    print("TABLA DE VEREDICTOS (full-sample descriptivo + OOS walk-forward)")
    print("═" * 86)
    hdr = (f"{'Escala':<6}{'Régimen':<18}{'h':>3} | {'N':>4} {'mean%':>8} "
           f"{'CI95%':>16} {'WR':>5} {'PF':>5} {'Kelly':>6} | "
           f"{'OOS mean%':>9} {'OOS CI95%':>17} {'folds+':>6} {'OOS IC':>7} | Verdict")
    print(hdr)
    print("─" * 130)
    for v in verdict_rows:
        s = v["scale"]; r = v["regime"]; h = v["horizon"]
        st = report["regimes"][s][r]["horizons"][h]
        wf = st["walkforward"]
        def f3(x): return f"{x*100:+.2f}"
        ci = st["ci95"]
        ci_s = f"[{f3(ci[0])},{f3(ci[1])}]" if not np.isnan(ci[0]) else "      —        "
        wf_ci = wf.get("oos_ci95")
        wf_ci_s = f"[{f3(wf_ci[0])},{f3(wf_ci[1])}]" if wf_ci and not np.isnan(wf_ci[0]) else "      —        "
        kelly = st.get("kelly")
        kelly_s = f"{kelly:+.2f}" if kelly is not None else "  —  "
        pf = st.get("pf")
        pf_s = f"{pf:.2f}" if pf is not None else "  ∞  "
        ic = wf.get("oos_ic")
        ic_s = f"{ic:+.3f}" if ic is not None and not np.isnan(ic) else "   —  "
        vd = v["verdict_short"]
        print(f"{s:<6}{r:<18}{h:>3} | {st['N']:>4} {f3(st['mean']):>8} {ci_s:>16} "
              f"{st['wr']*100:>4.0f}% {pf_s:>5} {kelly_s:>6} | "
              f"{f3(wf['oos_mean']):>9} {wf_ci_s:>17} {wf['pct_pos']:>5.0%} {ic_s:>7} | {vd}")

    print("\n" + "═" * 86)
    print("RESUMEN DE VEREDICTOS — ¿OPERABLE o ruido?")
    print("═" * 86)
    for scale in SCALES:
        print(f"\n  ESCALA {scale}:")
        for rname in REGIMES:
            for h in [10, 20, 40]:
                key = next((v for v in verdict_rows
                            if v["scale"] == scale and v["regime"] == rname and v["horizon"] == h), None)
                if key is None:
                    continue
                st = report["regimes"][scale][rname]["horizons"][h]
                wf = st["walkforward"]
                ci = st["ci95"]
                oos = wf["oos_mean"]
                print(f"    {key['label']:<38} {h:>2}d  N={st['N']:>4}  "
                      f"mean={st['mean']*100:+.2f}% CI95[{ci[0]*100:+.2f},{ci[1]*100:+.2f}]  "
                      f"OOS={oos*100:+.2f}%  →  {key['verdict_short']}")

    # ── Comparativa: pivot-entry (look-ahead) vs signal-bar ──────
    print("\n" + "═" * 86)
    print("LOOK-AHEAD PREMIUM — forward desde PIVOTE vs desde BARRA DE SEÑAL")
    print("═" * 86)
    print(f"{'Escala':<6}{'Régimen':<22}{'h':>3} | {'N':>4} {'PIVOTE':>8} {'SEÑAL':>8} {'Δ':>8} | Señal↔Pivote(d)")
    print("─" * 76)
    for scale in SCALES:
        ents = entries_by_scale.get(scale, [])
        if not ents:
            continue
        for rname, rcfg in REGIMES.items():
            perms = set(rcfg["perms"])
            r_entries = [e for e in ents if e["perm"] in perms]
            if len(r_entries) < 5:
                # gap stats anyway
                gaps = [(e["pivot"] - e["signal_bar"]).days for e in r_entries]
                gap_med = int(np.median(gaps)) if gaps else None
                if gap_med is not None:
                    print(f"{scale:<6}{rname:<22}{40:>3} | {len(r_entries):>4} {'—':>8} {'—':>8} {'—':>8} | {gap_med:>4}d mediana")
                continue
            gaps = [(e["pivot"] - e["signal_bar"]).days for e in r_entries]
            gap_med = int(np.median(gaps))
            for h in [20, 40]:
                pivot_ret = []
                signal_ret = []
                for e in r_entries:
                    pr = fwd_from_bar(e["pivot"], spy_idx_vals, spy_values, h)
                    sr = fwd_from_bar(e["signal_bar"], spy_idx_vals, spy_values, h)
                    if pr is not None:
                        pivot_ret.append(pr)
                    if sr is not None:
                        signal_ret.append(sr)
                if len(pivot_ret) >= 3 and len(signal_ret) >= 3:
                    pm, _lo, _hi = boot_ci_mean(np.array(pivot_ret))
                    sm, _lo2, _hi2 = boot_ci_mean(np.array(signal_ret))
                    delta = pm - sm
                    print(f"{scale:<6}{rname:<22}{h:>3} | {len(r_entries):>4} {pm*100:>+7.2f}% {sm*100:>+7.2f}% {delta*100:>+7.2f}% | {gap_med:>4}d mediana")
            # composición MIN/MAX
            types = Counter(e["type"] for e in r_entries if e.get("type"))
            print(f"{'':>6}{'':>22}{'':>3} | {'':>4} {'':>8} {'':>8} {'':>8} | comp: {dict(types)}")

    # 7. Persistir JSON + Markdown
    json_path = ROOT / "scratch" / "validate_regimes_oos_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nJSON → {json_path}")

    md_path = ROOT / "scratch" / "validate_regimes_oos_REPORT.md"
    write_markdown(md_path, report, verdict_rows)
    print(f"Markdown → {md_path}")


# ── Walk-forward OOS ───────────────────────────────────────────────────────
def walkforward_oos(entry_dates, returns, spy_idx_vals, spy_values, h,
                    eligible_start, eligible_end):
    """Expanding-window: K folds cronológicos sobre la ventana elegible.
    Por fold: media del régimen (solo entradas en test) + baseline (todos los
    días del fold) + IC punto-biserial (día señal=1 vs resto=0)."""
    entry_dates = list(entry_dates)
    returns = np.asarray(returns, float)

    # timeline elegible → K folds
    mask = (spy_idx_vals >= np.datetime64(eligible_start)) & (spy_idx_vals <= np.datetime64(eligible_end))
    timeline_idx = np.where(mask)[0]
    if len(timeline_idx) == 0:
        return {"valid_folds": 0, "oos_mean": np.nan, "oos_ci95": [np.nan, np.nan],
                "pct_pos": np.nan, "oos_excess": np.nan, "oos_ic": np.nan, "folds": []}

    fold_edges = np.array_split(timeline_idx, K_FOLDS)
    entry_ns = np.array([np.datetime64(d).astype("datetime64[ns]").astype("int64")
                         for d in entry_dates])
    timeline_ns = spy_idx_vals.astype("datetime64[ns]").astype("int64")

    fold_means, fold_excess, fold_ics, fold_n = [], [], [], []
    for fi in range(1, K_FOLDS):  # expanding: fold 0 es "pasado", test desde fold 1
        t_idx = fold_edges[fi]
        if len(t_idx) == 0:
            continue
        t0, t1 = timeline_ns[t_idx[0]], timeline_ns[t_idx[-1]]

        # entradas del régimen en el fold
        sel = (entry_ns >= t0) & (entry_ns <= t1)
        fold_ret = returns[sel]
        fold_ret = fold_ret[~np.isnan(fold_ret)]
        if len(fold_ret) < MIN_TEST_N:
            continue
        fold_n.append(len(fold_ret))
        fold_means.append(float(np.mean(fold_ret)))

        # baseline del fold (todos los días con forward disponible)
        base_ret = []
        for i in t_idx:
            if i + h < len(spy_values):
                base_ret.append(spy_values[i + h] / spy_values[i] - 1.0)
        base_ret = np.array(base_ret)
        base_ret = base_ret[~np.isnan(base_ret)]
        if len(base_ret) >= 3:
            fold_excess.append(float(np.mean(fold_ret) - np.mean(base_ret)))

        # IC punto-biserial en el fold (día señal vs resto)
        entry_set = set(entry_ns[sel].tolist())
        ind = np.array([1.0 if timeline_ns[di] in entry_set else 0.0 for di in t_idx])
        tgt = np.array([(spy_values[i + h] / spy_values[i] - 1.0) if i + h < len(spy_values) else np.nan
                        for i in t_idx])
        ic = point_biserial(ind, tgt)
        if not np.isnan(ic):
            fold_ics.append(ic)

    n_valid = len(fold_means)
    if n_valid == 0:
        return {"valid_folds": 0, "oos_mean": np.nan, "oos_ci95": [np.nan, np.nan],
                "pct_pos": np.nan, "oos_excess": np.nan, "oos_ic": np.nan, "folds": []}

    oos_mean = float(np.mean(fold_means))
    pct_pos = float(np.mean([m > 0 for m in fold_means]))
    oos_excess = float(np.mean(fold_excess)) if fold_excess else np.nan
    oos_ic = float(np.mean(fold_ics)) if fold_ics else np.nan

    if n_valid >= 3:
        m, lo, hi = boot_ci_mean(np.array(fold_means))
        oos_ci = [lo, hi]
    else:
        oos_ci = [np.nan, np.nan]

    return {"valid_folds": n_valid, "oof_folds_total": K_FOLDS - 1,
            "oos_mean": oos_mean, "oos_ci95": oos_ci, "pct_pos": pct_pos,
            "oos_excess": oos_excess, "oos_ic": oos_ic,
            "fold_means": fold_means, "fold_n": fold_n}


def make_verdict(st, wf, n_entries_total):
    """Veredicto: OPERABLE(LONG/SHORT) si OOS IC en dirección y CI95 no cruza 0."""
    ci = st["ci95"]
    lo, hi = ci[0], ci[1]
    mean = st["mean"]
    oos_ic = wf.get("oos_ic")
    n_folds = wf.get("valid_folds", 0)
    oos_mean = wf.get("oos_mean")

    # fallback a full-sample si OOS no tiene folds suficientes
    ci_usable = not np.isnan(lo) and not np.isnan(hi)
    oos_ci = wf.get("oos_ci95", [np.nan, np.nan])
    oos_ci_usable = not np.isnan(oos_ci[0]) and not np.isnan(oos_ci[1])

    if st["N"] < MIN_N:
        return {"verdict": "INSUFICIENTE", "verdict_short": "INSUF",
                "direction": "na", "reason": f"N={st['N']}<{MIN_N}"}

    # Criterio principal: CI95 de la media (OOS si hay, si no full-sample) no cruza 0
    if oos_ci_usable and n_folds >= 3:
        lo_v, hi_v = oos_ci[0], oos_ci[1]
        if lo_v > 0:
            return {"verdict": "OPERABLE", "verdict_short": "OP-LONG",
                    "direction": "long",
                    "reason": f"OOS mean CI95[{lo_v*100:+.2f},{hi_v*100:+.2f}] > 0 ({n_folds} folds)"}
        if hi_v < 0:
            return {"verdict": "OPERABLE", "verdict_short": "OP-SHORT",
                    "direction": "short",
                    "reason": f"OOS mean CI95[{lo_v*100:+.2f},{hi_v*100:+.2f}] < 0 ({n_folds} folds)"}
        return {"verdict": "NO", "verdict_short": "RUIDO",
                "direction": "na",
                "reason": f"OOS CI95 cruza 0 [{lo_v*100:+.2f},{hi_v*100:+.2f}]"}

    # Fallback full-sample CI95
    if ci_usable:
        if lo > 0:
            return {"verdict": "OPERABLE", "verdict_short": "OP-LONG",
                    "direction": "long",
                    "reason": f"full CI95[{lo*100:+.2f},{hi*100:+.2f}] > 0 (OOS folds < 3)"}
        if hi < 0:
            return {"verdict": "OPERABLE", "verdict_short": "OP-SHORT",
                    "direction": "short",
                    "reason": f"full CI95[{lo*100:+.2f},{hi*100:+.2f}] < 0 (OOS folds < 3)"}

    return {"verdict": "NO", "verdict_short": "RUIDO", "direction": "na",
            "reason": "CI95 cruza 0"}


# ── Markdown ───────────────────────────────────────────────────────────────
def write_markdown(path, report, verdict_rows):
    lines = []
    lines.append("# Validación OOS walk-forward — 5 regímenes de secuencia\n")
    lines.append("Entrada en **barra de señal** (3ª activación CAT1/CAT2/CAT3), no pivote.")
    lines.append("Walk-forward expanding-window (K=%d folds). Bootstrap CI95 3000.\n" % K_FOLDS)
    lines.append(f"Categorías: CAT1=CREDIT+YIELD+DXY · CAT2=VIX+VVIX+PCR+SKEW · CAT3=S5TW+SV5T+FG\n")
    lines.append("## Baseline SPY (todos los días)\n")
    lines.append("| h | N | mean | CI95 |")
    lines.append("|---|---|---|---|")
    for h in FW_HORIZONS:
        b = report["baseline"][h]
        lines.append(f"| {h}d | {b['N']} | {b['mean']*100:+.2f}% | "
                     f"[{b['ci95'][0]*100:+.2f},{b['ci95'][1]*100:+.2f}] |")
    lines.append("")

    for scale in SCALES:
        if scale not in report["regimes"]:
            continue
        lines.append(f"\n## Escala {scale}\n")
        for rname in REGIMES:
            if rname not in report["regimes"][scale]:
                continue
            r = report["regimes"][scale][rname]
            lines.append(f"\n### {r['label']}  (N entradas = {r['N_entries']})\n")
            lines.append("| h | N | mean | CI95 | WR | PF | Kelly | exceso | OOS mean | OOS CI95 | folds+ | OOS IC | Veredicto |")
            lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
            for h in FW_HORIZONS:
                st = r["horizons"].get(h)
                if st is None:
                    continue
                wf = st["walkforward"]
                def f3(x): return f"{x*100:+.2f}"
                ci = st["ci95"]
                ci_s = f"[{f3(ci[0])},{f3(ci[1])}]"
                kelly = st.get("kelly")
                kelly_s = f"{kelly:+.2f}" if kelly is not None else "—"
                pf = st.get("pf")
                pf_s = f"{pf:.2f}" if pf is not None else "∞"
                oos_ci = wf.get("oos_ci95", [np.nan, np.nan])
                oos_ci_s = f"[{f3(oos_ci[0])},{f3(oos_ci[1])}]" if not np.isnan(oos_ci[0]) else "—"
                ic = wf.get("oos_ic")
                ic_s = f"{ic:+.3f}" if ic is not None and not np.isnan(ic) else "—"
                vd = st["verdict"]["verdict_short"]
                lines.append(f"| {h}d | {st['N']} | {f3(st['mean'])} | {ci_s} | "
                             f"{st['wr']*100:.0f}% | {pf_s} | {kelly_s} | {f3(st['excess_vs_baseline'])} | "
                             f"{f3(wf['oos_mean'])} | {oos_ci_s} | {wf['pct_pos']*100:.0f}% | {ic_s} | {vd} |")
            # wins/losses para 20d
            st20 = r["horizons"].get(20)
            if st20 is not None:
                w = st20["wins"]; l = st20["losses"]
                def fp(x):
                    return f"{x*100:+.2f}%" if x is not None else "—"
                lines.append(f"\n**20d wins/losses separados** — WINS n={w['n']} mean={fp(w['mean'])} "
                             f"med={fp(w['median'])} p90={fp(w['p90'])} max={fp(w['max'])} · "
                             f"LOSSES n={l['n']} mean={fp(l['mean'])} med={fp(l['median'])} "
                             f"p10={fp(l['p10'])} min={fp(l['min'])} wipeouts>20%={l['wipeouts_gt20pct']}\n")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
