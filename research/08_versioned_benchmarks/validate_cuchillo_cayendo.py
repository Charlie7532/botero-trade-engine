#!/usr/bin/env python3
"""
VALIDACIÓN RÉGIMEN "CUCHILLO CAYENDO" (CAT1→CAT3→CAT2)
========================================================
HIPÓTESIS: cuando la ACCIÓN (CAT 3) se activa ANTES que el SENTIMIENTO (CAT 2),
el mercado está cayendo sin que el miedo haya reaccionado aún → warning BAJISTA.
El "cuchillo cayendo".

Se compara el régimen CAT1→CAT3→CAT2 (acción adelanta sentimiento) contra
CAT1→CAT2→CAT3 (normal) y contra el baseline SPY, en las 3 escalas zigzag
(zz25 / zz50 / zz75) y 4 horizontes fijos (5/10/20/40d), con CI95 bootstrap.

8 dimensiones (wins-losses framework):
  A. Win rate + CI95 (alcista y bajista)
  B. Distribución de WINS (fwd > 0)
  C. Distribución de LOSSES + wipeouts (>20%)
  D. Profit factor (long & short) + Kelly + EV + CI95
  E. Rachas (streaks de pérdidas)
  F. Timing vs zigzag (días de cada categoría al pivote + gap de inversión)
  G. Cuchillo cayendo (drawdown forward máximo >5%)
  H. Calidad de muestra (N por régimen + por década)

Categorías (7 tickers — mapeo conforme station-ticker-mapping):
  CAT 1 ECONOMIA:    CREDIT_RATIO, YIELD_SPREAD
  CAT 2 SENTIMIENTO: VIX, SKEW
  CAT 3 ACCION:      S5TW, SV5_TURBULENCE, FG

SIGMET con TRAYECTORIA (D2 streak≥3 + D3 compresión streak≥3 + D1 acercándose
al extremo), misma lógica del prototipo `metar_skeleton.py` / `secuencias_classifier.py`.

Salida: reporte por consola + JSON en data/research/validate_cuchillo_cayendo_report.json
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
    1: {"name": "ECONOMIA", "tickers": ["CREDIT_RATIO", "YIELD_SPREAD"]},
    2: {"name": "SENTIMIENTO", "tickers": ["VIX", "SKEW"]},
    3: {"name": "ACCION", "tickers": ["S5TW", "SV5_TURBULENCE", "FG"]},
}

# Parámetros SIGMET (idénticos a metar_skeleton.py / secuencias_classifier.py)
PCT_HIGH = 90
PCT_LOW = 10
D3_COMPRESSED = 0.7
STREAK = 3
WINDOW_DAYS = 30  # ventana lookback antes de cada pivote

FW_HORIZONS = [5, 10, 20, 40]
SCALES = ["zz25", "zz50", "zz75"]
N_BOOT = 3000
BOOT_SEED = 42

# Regímenes de interés
CUCHILLO = (1, 3, 2)   # CAT1→CAT3→CAT2  (acción adelanta sentimiento)
NORMAL = (1, 2, 3)     # CAT1→CAT2→CAT3  (secuencia clásica)


# ── Helpers estadísticos ──────────────────────────────────────────────────
def boot_ci_mean(arr, ci=95, n_boot=N_BOOT, seed=BOOT_SEED):
    """Bootstrap CI95 de la media."""
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    for i in range(n_boot):
        means[i] = rng.choice(arr, size=len(arr), replace=True).mean()
    means.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(arr.mean()), float(np.percentile(means, lo)), float(np.percentile(means, hi))


def boot_ci_prop(bool_arr, ci=95, n_boot=N_BOOT, seed=BOOT_SEED):
    """Bootstrap CI95 de una proporción (win rate)."""
    arr = np.asarray(bool_arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    props = np.empty(n_boot)
    for i in range(n_boot):
        props[i] = rng.choice(arr, size=len(arr), replace=True).mean()
    props.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(arr.mean()), float(np.percentile(props, lo)), float(np.percentile(props, hi))


def boot_ci_diff(a, b, ci=95, n_boot=N_BOOT, seed=BOOT_SEED):
    """Bootstrap CI95 de la DIFERENCIA de medias (a - b), muestras independientes."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    a = a[~np.isnan(a)]
    b = b[~np.isnan(b)]
    if len(a) < 3 or len(b) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        ra = rng.choice(a, size=len(a), replace=True).mean()
        rb = rng.choice(b, size=len(b), replace=True).mean()
        diffs[i] = ra - rb
    diffs.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(a.mean() - b.mean()), float(np.percentile(diffs, lo)), float(np.percentile(diffs, hi))


def pct(x):
    return f"{x*100:+.2f}%"


# ── Carga y cálculo de series ──────────────────────────────────────────────
def load_series(store, tickers):
    series = {}
    for t in tickers:
        try:
            b = store.load_bars(t, "1d")
            if b is not None and len(b) > 0:
                c = b["close"].copy()
                c.index = pd.to_datetime(c.index).normalize()
                c = c[~c.index.duplicated(keep="last")].sort_index()
                c = c.dropna()
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
    """SIGMET con trayectoria D2/D3 (misma lógica del skeleton)."""
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


# ── Análisis de un régimen (8 dimensiones) ─────────────────────────────────
def analyze_regime(pivots_meta, spy, spy_date_to_idx, spy_values, label):
    """
    pivots_meta: lista de dicts con:
        'date' (Timestamp), 'type' (MIN/MAX), 'cat_times' {1:ts,2:ts,3:ts}
    Devuelve el reporte 8-dimensiones.
    """
    n = len(pivots_meta)
    R = {"label": label, "N": n}
    if n < 3:
        R["insufficient"] = True
        return R

    fwd_arrays = {h: [] for h in FW_HORIZONS}
    fwd_path_min = {h: [] for h in FW_HORIZONS}  # drawdown forward máximo
    for pm in pivots_meta:
        dt = pm["date"]
        idx = spy_date_to_idx.get(dt)
        if idx is None:
            # pivote fuera del rango SPY → buscar primera barra >= dt
            pos = spy.index.searchsorted(dt)
            if pos >= len(spy_values):
                continue
            idx = pos
        entry = spy_values[idx]
        for h in FW_HORIZONS:
            if idx + h < len(spy_values):
                ret = spy_values[idx + h] / entry - 1.0
                fwd_arrays[h].append(ret)
                # drawdown máximo dentro de la ventana (cuchillo forward)
                window = spy_values[idx:idx + h + 1]
                fwd_path_min[h].append(window.min() / entry - 1.0)

    # ── Dimensión A: win rate (alcista fwd>0 y bajista fwd<0) + CI95
    R["A_winrate"] = {}
    for h in FW_HORIZONS:
        arr = np.array(fwd_arrays[h])
        if len(arr) < 3:
            R["A_winrate"][h] = None
            continue
        up, up_lo, up_hi = boot_ci_prop(arr > 0)
        dn, dn_lo, dn_hi = boot_ci_prop(arr < 0)
        R["A_winrate"][h] = {
            "pct_up": up, "pct_up_ci95": [up_lo, up_hi],
            "pct_down": dn, "pct_down_ci95": [dn_lo, dn_hi],
        }

    # ── Dimensión B: distribución de WINS (fwd > 0)
    R["B_wins"] = {}
    for h in FW_HORIZONS:
        arr = np.array(fwd_arrays[h])
        win = arr[arr > 0]
        if len(win) < 2:
            R["B_wins"][h] = None
            continue
        R["B_wins"][h] = {
            "n": len(win),
            "mean": float(np.mean(win)), "median": float(np.median(win)),
            "p25": float(np.percentile(win, 25)) if len(win) >= 4 else np.nan,
            "p75": float(np.percentile(win, 75)) if len(win) >= 4 else np.nan,
            "p90": float(np.percentile(win, 90)) if len(win) >= 10 else np.nan,
            "max": float(np.max(win)),
        }

    # ── Dimensión C: distribución de LOSSES + wipeouts
    R["C_losses"] = {}
    for h in FW_HORIZONS:
        arr = np.array(fwd_arrays[h])
        loss = arr[arr <= 0]
        if len(loss) < 2:
            R["C_losses"][h] = None
            continue
        wipe = loss[loss < -0.20]
        R["C_losses"][h] = {
            "n": len(loss),
            "mean": float(np.mean(loss)), "median": float(np.median(loss)),
            "p25": float(np.percentile(loss, 25)) if len(loss) >= 4 else np.nan,
            "p75": float(np.percentile(loss, 75)) if len(loss) >= 4 else np.nan,
            "p90": float(np.percentile(loss, 90)) if len(loss) >= 10 else np.nan,
            "min": float(np.min(loss)),
            "wipeouts_n": int(len(wipe)), "wipeouts_pct": float(len(wipe) / len(arr) * 100),
        }

    # ── Dimensión D: PF (long & short), Kelly, EV + CI95
    R["D_metrics"] = {}
    for h in FW_HORIZONS:
        arr = np.array(fwd_arrays[h])
        if len(arr) < 3:
            R["D_metrics"][h] = None
            continue
        wins = arr[arr > 0]
        losses = arr[arr <= 0]
        gw = float(np.sum(wins)) if len(wins) else 0.0
        gl = float(abs(np.sum(losses))) if len(losses) else 0.0
        pf_long = gw / gl if gl > 0 else float("inf")
        pf_short = gl / gw if gw > 0 else float("inf")  # short: gana cuando cae
        wr_up = float(np.mean(arr > 0))
        wr_dn = float(np.mean(arr < 0))
        avg_w = float(np.mean(wins)) if len(wins) else 0.0
        avg_l = float(abs(np.mean(losses))) if len(losses) else 0.0
        wlr = avg_w / avg_l if avg_l > 0 else float("inf")
        kelly_long = (wr_up - (1 - wr_up) / wlr) if (avg_l > 0 and wlr > 0) else np.nan
        # Kelly del short (invertir signos)
        avg_w_short = avg_l
        avg_l_short = avg_w
        wlr_short = avg_w_short / avg_l_short if avg_l_short > 0 else float("inf")
        kelly_short = (wr_dn - (1 - wr_dn) / wlr_short) if (avg_l_short > 0 and wlr_short > 0) else np.nan
        ev, ev_lo, ev_hi = boot_ci_mean(arr)
        R["D_metrics"][h] = {
            "pf_long": pf_long, "pf_short": pf_short,
            "kelly_long": float(kelly_long) if not np.isnan(kelly_long) else None,
            "kelly_short": float(kelly_short) if not np.isnan(kelly_short) else None,
            "ev_long": ev, "ev_long_ci95": [ev_lo, ev_hi],
            "std": float(np.std(arr)),
        }

    # ── Dimensión E: rachas (streaks de pérdidas a 20d)
    arr20 = np.array(fwd_arrays[20])
    if len(arr20) >= 3:
        streaks = []
        cur = 0
        for r in arr20:
            if r <= 0:
                cur += 1
            else:
                if cur > 0:
                    streaks.append(cur)
                cur = 0
        if cur > 0:
            streaks.append(cur)
        R["E_streaks"] = {
            "n_loss_streaks": len(streaks),
            "max_loss_streak": max(streaks) if streaks else 0,
            "mean_loss_streak": float(np.mean(streaks)) if streaks else 0.0,
        }
    else:
        R["E_streaks"] = None

    # ── Dimensión F: timing vs zigzag (días de cada categoría al pivote + gap)
    cat1_gap = [ (pm["date"] - pm["cat_times"][1]).days for pm in pivots_meta if 1 in pm["cat_times"] ]
    cat3_gap = [ (pm["date"] - pm["cat_times"][3]).days for pm in pivots_meta if 3 in pm["cat_times"] ]
    cat2_gap = [ (pm["date"] - pm["cat_times"][2]).days for pm in pivots_meta if 2 in pm["cat_times"] ]
    # gap de inversión: días entre CAT3 y CAT2 (positivo = CAT3 adelanta a CAT2)
    inv_gap = [ (pm["cat_times"][2] - pm["cat_times"][3]).days
                for pm in pivots_meta if 2 in pm["cat_times"] and 3 in pm["cat_times"] ]
    R["F_timing"] = {
        "cat1_days_median": float(np.median(cat1_gap)) if cat1_gap else np.nan,
        "cat2_days_median": float(np.median(cat2_gap)) if cat2_gap else np.nan,
        "cat3_days_median": float(np.median(cat3_gap)) if cat3_gap else np.nan,
        "inversion_gap_median": float(np.median(inv_gap)) if inv_gap else np.nan,
        "inversion_gap_mean": float(np.mean(inv_gap)) if inv_gap else np.nan,
    }

    # ── Dimensión G: cuchillo cayendo (drawdown forward máximo >5%)
    R["G_knife"] = {}
    for h in FW_HORIZONS:
        pm = np.array(fwd_path_min[h])
        if len(pm) < 3:
            R["G_knife"][h] = None
            continue
        knife = pm[pm < -0.05]
        R["G_knife"][h] = {
            "max_dd_median": float(np.median(pm)),
            "max_dd_p90": float(np.percentile(pm, 90)),
            "pct_knife_gt5": float(len(knife) / len(pm) * 100),
            "worst": float(np.min(pm)),
        }

    # ── Dimensión H: calidad de muestra (por década)
    decades = Counter(str(pm["date"].year // 10 * 10) for pm in pivots_meta)
    R["H_quality"] = {"n_total": n, "by_decade": {k: v for k, v in sorted(decades.items())}}

    # raw forward arrays (para recomparaciones en main)
    R["_fwd"] = {h: list(fwd_arrays[h]) for h in FW_HORIZONS}

    return R


def fwd_of(R, h):
    """Extrae array de forward returns del reporte de un régimen."""
    if R is None or "_fwd" not in R:
        return np.array([])
    arr = np.array(R["_fwd"].get(h, []), dtype=float)
    return arr[~np.isnan(arr)]


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    print("═" * 78)
    print("VALIDACIÓN RÉGIMEN CUCHILLO CAYENDO (CAT1→CAT3→CAT2)")
    print("═" * 78)

    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)

    # 1. Cargar SPY
    spy_raw = store.load_bars("SPY", "1d")["close"].copy()
    spy_raw.index = pd.to_datetime(spy_raw.index).normalize()
    spy = spy_raw[~spy_raw.index.duplicated(keep="last")].sort_index()
    spy_values = spy.values
    spy_date_to_idx = {d: i for i, d in enumerate(spy.index)}
    print(f"SPY: {spy.index[0].date()} → {spy.index[-1].date()} ({len(spy)} barras)")

    # 2. Cargar series + SIGMETs por categoría
    sigmets = {}
    for cat_id, cat in CATEGORIES.items():
        series = load_series(store, cat["tickers"])
        cat_events = []
        for t, s in series.items():
            df = compute_d1_d2_d3(s)
            ev = detect_sigmet(df)
            if len(ev) > 0:
                ev["ticker"] = t
                cat_events.append(ev)
        if cat_events:
            sigmets[cat_id] = pd.concat(cat_events).sort_values("timestamp")
            print(f"CAT {cat_id} ({cat['name']}): {len(sigmets[cat_id])} SIGMETs "
                  f"({', '.join(series.keys())})")
        else:
            sigmets[cat_id] = pd.DataFrame()
            print(f"CAT {cat_id} ({cat['name']}): 0 SIGMETs")

    # 3. Pivotes por escala
    pivots_by_scale = {}
    for scale in SCALES:
        df = repo.get_confirmed_legs_dataframe("SPY", scale)
        pivots_by_scale[scale] = df
        print(f"{scale}: {len(df)} legs")

    # Baseline SPY por escala: retorno forward de TODOS los pivotes de la escala
    def all_pivots_fwd(df, h):
        rets = []
        for ts in df["start_timestamp"]:
            dt = pd.to_datetime(ts).normalize()
            idx = spy_date_to_idx.get(dt)
            if idx is None:
                pos = spy.index.searchsorted(dt)
                if pos >= len(spy_values):
                    continue
                idx = pos
            if idx + h < len(spy_values):
                rets.append(spy_values[idx + h] / spy_values[idx] - 1.0)
        return np.array(rets)

    # 4. Clasificar pivotes por permutación (3 escalas)
    report = {}
    for scale in SCALES:
        legs = pivots_by_scale[scale]
        if len(legs) == 0:
            continue
        seq = []  # (date, type, cat_times dict)
        for _, leg in legs.iterrows():
            pivot_ts = pd.to_datetime(leg["start_timestamp"]).normalize()
            first = {}
            for cat_id in [1, 2, 3]:
                ev = sigmets.get(cat_id)
                if ev is not None and len(ev) > 0:
                    window = ev[(ev["timestamp"] >= pivot_ts - pd.Timedelta(days=WINDOW_DAYS)) &
                                (ev["timestamp"] <= pivot_ts)]
                    if len(window) > 0:
                        first[cat_id] = window["timestamp"].min()
            if len(first) == 3:
                ordered = sorted(first.items(), key=lambda x: x[1])
                perm = tuple(c for c, _ in ordered)
                seq.append({"date": pivot_ts, "type": leg["start_type"],
                            "perm": perm, "cat_times": first})

        # Conteo de permutaciones
        perm_counts = Counter(s["perm"] for s in seq)
        print(f"\n{'─'*78}")
        print(f"ESCALA {scale} — {len(seq)} pivotes con 3 categorías activas")
        print(f"{'─'*78}")
        for perm, c in sorted(perm_counts.items(), key=lambda x: -x[1]):
            tag = "CUCHILLO" if perm == CUCHILLO else ("NORMAL" if perm == NORMAL else "")
            arrow = "→".join(f"CAT{c}" for c in perm)
            print(f"  {arrow:<16} N={c:<4} {tag}")

        cuchillo = [s for s in seq if s["perm"] == CUCHILLO]
        normal = [s for s in seq if s["perm"] == NORMAL]

        # Composición del régimen cuchillo (MIN/MAX + fechas + gap de inversión)
        if cuchillo:
            print(f"\n  [COMPOSICIÓN CUCHILLO @ {scale}]")
            from collections import Counter as _C
            tt = _C(s["type"] for s in cuchillo)
            inv_gaps = [ (s["cat_times"][2] - s["cat_times"][3]).days
                         for s in cuchillo if 2 in s["cat_times"] and 3 in s["cat_times"] ]
            g13 = [ (s["cat_times"][3] - s["cat_times"][1]).days
                    for s in cuchillo if 3 in s["cat_times"] and 1 in s["cat_times"] ]
            print(f"    MIN/MAX: {dict(tt)}")
            print(f"    gap CAT3→CAT2 (días): med {np.median(inv_gaps):.0f} mean {np.mean(inv_gaps):.1f} "
                  f"P25/P75 {np.percentile(inv_gaps,25):.0f}/{np.percentile(inv_gaps,75):.0f} "
                  f"min/max {min(inv_gaps)}/{max(inv_gaps)}")
            print(f"    gap CAT1→CAT3 (días): med {np.median(g13):.0f} mean {np.mean(g13):.1f}")
            yrs = _C(s["date"].year for s in cuchillo)
            print(f"    Años: {dict(sorted(yrs.items()))}")
            print(f"    Fechas ({len(cuchillo)}):")
            for s in sorted(cuchillo, key=lambda x: x["date"]):
                g32 = (s["cat_times"][2] - s["cat_times"][3]).days
                print(f"      {s['date'].date()}  {s['type']:4s}  gap32={g32:3d}d")

        # Baseline SPY de la escala
        base = {h: all_pivots_fwd(legs, h) for h in FW_HORIZONS}

        rc = analyze_regime(cuchillo, spy, spy_date_to_idx, spy_values,
                            f"CUCHILLO CAT1→CAT3→CAT2 @ {scale}")
        rn = analyze_regime(normal, spy, spy_date_to_idx, spy_values,
                            f"NORMAL CAT1→CAT2→CAT3 @ {scale}")

        report[scale] = {"n_total_pivots": len(legs), "n_3cat": len(seq),
                         "perm_counts": {("→".join(f"C{c}" for c in k)): v
                                         for k, v in perm_counts.items()},
                         "cuchillo": rc, "normal": rn, "baseline": {}}

        # ── Impresión ──
        print(f"\n  CUCHILLO (N={len(cuchillo)}) vs NORMAL (N={len(normal)}) — forward returns:")
        hdr = f"  {'Horiz':<6} {'Cuchillo':>12} {'CI95':>20} {'Normal':>12} {'CI95':>20} {'Δ(c-n)':>10} {'Δ CI95':>22} {'Base SPY':>12}"
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for h in FW_HORIZONS:
            ca = fwd_of(rc, h)
            na = fwd_of(rn, h)
            cm, clo, chi = boot_ci_mean(ca) if len(ca) >= 3 else (np.nan,) * 3
            nm, nlo, nhi = boot_ci_mean(na) if len(na) >= 3 else (np.nan,) * 3
            dm, dlo, dhi = boot_ci_diff(ca, na) if (len(ca) >= 3 and len(na) >= 3) else (np.nan,) * 3
            bm = float(base[h].mean()) if len(base[h]) else np.nan
            cs = f"{cm*100:+.2f}%" if not np.isnan(cm) else "n/d"
            ns = f"{nm*100:+.2f}%" if not np.isnan(nm) else "n/d"
            bs = f"{bm*100:+.2f}%" if not np.isnan(bm) else "n/d"
            cci = f"[{clo*100:+.1f},{chi*100:+.1f}]" if not np.isnan(cm) else ""
            nci = f"[{nlo*100:+.1f},{nhi*100:+.1f}]" if not np.isnan(nm) else ""
            dci = f"[{dlo*100:+.1f},{dhi*100:+.1f}]" if not np.isnan(dm) else ""
            print(f"  {h:<6}d {cs:>12} {cci:>20} {ns:>12} {nci:>20} {dm*100:>+9.1f}% {dci:>22} {bs:>12}")
            report[scale]["baseline"][h] = bm

        # Verdict por escala
        print(f"\n  ── VEREDICTO {scale} ──")
        c20 = fwd_of(rc, 20)
        n20 = fwd_of(rn, 20)
        if len(c20) >= 3:
            m20, lo20, hi20 = boot_ci_mean(c20)
            dm20, dlo20, dhi20 = boot_ci_diff(c20, n20)
            reliable_bear = (hi20 < 0)
            diff_sig = (dhi20 < 0) or (dlo20 > 0)
            print(f"    Cuchillo 20d: {m20*100:+.2f}% CI95[{lo20*100:+.1f},{hi20*100:+.1f}] "
                  f"→ {'RELIABLE BEARISH' if reliable_bear else 'NO confiable (CI95 cruza 0)'}")
            print(f"    Δ vs Normal: {dm20*100:+.2f}pp CI95[{dlo20*100:+.1f},{dhi20*100:+.1f}] "
                  f"→ {'SIGNIFICATIVO' if diff_sig else 'NO significativo'}")

        # Imprimir 8 dimensiones del cuchillo (resumen)
        print(f"\n  [8 dimensiones — CUCHILLO @ 20d]")
        if rc.get("A_winrate") and rc["A_winrate"].get(20):
            a = rc["A_winrate"][20]
            print(f"    A. Win rate: up {a['pct_up']*100:.0f}% CI95[{a['pct_up_ci95'][0]*100:.0f},{a['pct_up_ci95'][1]*100:.0f}]"
                  f" | down {a['pct_down']*100:.0f}% CI95[{a['pct_down_ci95'][0]*100:.0f},{a['pct_down_ci95'][1]*100:.0f}]")
        if rc.get("B_wins") and rc["B_wins"].get(20):
            b = rc["B_wins"][20]
            print(f"    B. WINS (n={b['n']}): med {b['median']*100:+.1f}% P90 {b['p90']*100:+.1f}% max {b['max']*100:+.1f}%")
        if rc.get("C_losses") and rc["C_losses"].get(20):
            c = rc["C_losses"][20]
            print(f"    C. LOSSES (n={c['n']}): med {c['median']*100:+.1f}% min {c['min']*100:+.1f}% wipeouts {c['wipeouts_n']} ({c['wipeouts_pct']:.0f}%)")
        if rc.get("D_metrics") and rc["D_metrics"].get(20):
            d = rc["D_metrics"][20]
            kls = f"{d['kelly_long']*100:+.0f}%" if d['kelly_long'] is not None else "n/d"
            kss = f"{d['kelly_short']*100:+.0f}%" if d['kelly_short'] is not None else "n/d"
            print(f"    D. PF long {d['pf_long']:.2f} | PF short {d['pf_short']:.2f} | Kelly long {kls} | Kelly short {kss}")
        if rc.get("E_streaks"):
            e = rc["E_streaks"]
            print(f"    E. Rachas: max {e['max_loss_streak']} pérdidas consecutivas ({e['n_loss_streaks']} rachas)")
        if rc.get("F_timing"):
            f = rc["F_timing"]
            print(f"    F. Timing: CAT1 med {f['cat1_days_median']:.0f}d CAT3 med {f['cat3_days_median']:.0f}d "
                  f"CAT2 med {f['cat2_days_median']:.0f}d | gap inv {f['inversion_gap_median']:.0f}d")
        if rc.get("G_knife") and rc["G_knife"].get(20):
            g = rc["G_knife"][20]
            print(f"    G. Cuchillo fwd: maxDD med {g['max_dd_median']*100:+.1f}% P90 {g['max_dd_p90']*100:+.1f}% "
                  f"knife>5% {g['pct_knife_gt5']:.0f}%")
        if rc.get("H_quality"):
            h = rc["H_quality"]
            print(f"    H. Muestra: N={h['n_total']} por década {h['by_decade']}")

    store.close()

    # Serializar reporte (limpiar no-JSON)
    out = "/root/botero-trade/data/research/validate_cuchillo_cayendo_report.json"
    def clean(obj):
        if isinstance(obj, dict):
            return {str(k): clean(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [clean(v) for v in obj]
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, (np.ndarray,)):
            return obj.tolist()
        if isinstance(obj, float) and np.isnan(obj):
            return None
        return obj
    with open(out, "w") as f:
        json.dump(clean(report), f, indent=2, default=str)
    print(f"\nReporte JSON: {out}")

    print("\n" + "═" * 78)
    print("VALIDACIÓN COMPLETADA")
    print("═" * 78)


if __name__ == "__main__":
    main()
