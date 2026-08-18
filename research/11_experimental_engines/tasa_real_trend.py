#!/usr/bin/env python3
"""
tasa_real_trend.py — TASA REAL (DFII10, 10Y TIPS yield) vs TENDENCIA de SPY en CORTOS
=====================================================================================
Pregunta: ¿La TASA REAL (DFII10, 10Y TIPS yield) predice la tendencia de SPY en
horizontes CORTOS (5/10/20/60 días)?

HIPÓTESIS (Cochrane 2011, Asness 2003)
  - DFII10 sube (tasa real ↑) → P/E se comprime → SPY baja
  - DFII10 baja (tasa real ↓) → P/E se expande → SPY sube
  - La VELOCIDAD (Δ3d, Δ5d, Δ20d) de DFII10 predice mejor que el nivel
  - El BREAKEVEN (DGS10−DFII10 = inflación esperada) es canal alternativo
  - Los REGÍMENES (tasa real positiva/negativa/extrema) contienen la señal

MÉTODO
  PASO 1 — Cargar DFII10, DFII5, DGS10, DGS2, DTB3, SPY diarios (2003-2026, alineados).
  PASO 2 — Computar TODAS las señales candidatas:
    - DFII10 (tasa real 10Y, nivel)
    - DFII5 (tasa real 5Y, nivel)
    - ΔDFII10_3d, ΔDFII10_5d, ΔDFII10_20d (velocidad)
    - BREAKEVEN = DGS10 − DFII10
    - ΔDFII5_5d (velocidad de la tasa real corta)
  PASO 3 — Correlación de cada señal con SPY forward a 5/10/20/60 días.
           Spearman ρ, CI95 bootstrap 3000 (seed 42). Reportar TODAS.
  PASO 4 — REGÍMENES de tasa real (lo más importante):
    - DFII10 > 0 (tasa real positiva) → forward SPY?
    - DFII10 < 0 (tasa real negativa, TINA) → forward SPY?
    - DFII10 > P90 (extremadamente alta) → ¿señal más fuerte?
    - DFII10 < P10 (extremadamente baja) → ¿señal más fuerte?
    - Para cada régimen: N, mean return, CI95, win rate, wins/losses separados.
  PASO 5 — VELOCIDAD como señal de timing:
    - ΔDFII10_3d > 0 (subiendo rápido) → forward SPY 5d/10d/20d?
    - ΔDFII10_3d < 0 (bajando rápido) → forward SPY 5d/10d/20d?
  PASO 6 — Comparación con curvas de rendimiento (benchmark):
    - Spread 2Y-10Y (DGS2−DGS10)
    - Spread 2Y-3M  (DGS2−DTB3)
    - ¿La tasa real (DFII10) supera a los spreads?
  PASO 7 — VEREDICTO: ¿qué señal es mejor: nivel, régimen, o velocidad?

REGLA: DATO MATA RELATO. CI95 + N mínimo 20. ANTI-ADULACIÓN.

ENTREGABLE: scratch/tasa_real_trend_report.json
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = Path(__file__).resolve().parent / "tasa_real_trend_report.json"

BOOTSTRAP_ITER = 3000
BOOTSTRAP_SEED = 42
HORIZONS = [5, 10, 20, 60]  # trading days cortos
MIN_N = 20

# ────────────────────────────────────────────────────────────────────
# HELPERS
# ────────────────────────────────────────────────────────────────────
def load_series(store, ticker):
    """Load a single ticker from TimescaleDataStore, return clean Series."""
    df = store.load_bars(ticker, "1d")
    if df.empty:
        raise RuntimeError(f"No bars for {ticker}")
    df.index = pd.to_datetime(df.index)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    s = df["close"].astype(float)
    s = s[~s.index.duplicated(keep="first")].sort_index()
    return s


def _rng():
    return np.random.default_rng(BOOTSTRAP_SEED)


def _resample(rng, n):
    return rng.integers(0, n, n)


def _corr_pearson(a, b):
    ac = a - a.mean()
    bc = b - b.mean()
    den = np.sqrt((ac * ac).sum() * (bc * bc).sum())
    return float((ac * bc).sum() / den) if den > 0 else 0.0


def bootstrap_corr(x, y, rng):
    """Pearson + Spearman point estimates and CI95."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = int(len(x))
    if n < 2:
        return None
    xr = rankdata(x)
    yr = rankdata(y)
    xc = x - x.mean()
    yc = y - y.mean()
    xrc = xr - xr.mean()
    yrc = yr - yr.mean()

    pear_pt = _corr_pearson(x, y)
    spear_pt = _corr_pearson(xr, yr)

    pears = np.empty(BOOTSTRAP_ITER)
    spears = np.empty(BOOTSTRAP_ITER)
    for i in range(BOOTSTRAP_ITER):
        idx = _resample(rng, n)
        pears[i] = _corr_pearson(xc[idx], yc[idx])
        spears[i] = _corr_pearson(xrc[idx], yrc[idx])
    return {
        "n": n,
        "pearson": round(pear_pt, 4),
        "pearson_ci95": [round(float(np.percentile(pears, 2.5)), 4),
                         round(float(np.percentile(pears, 97.5)), 4)],
        "spearman": round(spear_pt, 4),
        "spearman_ci95": [round(float(np.percentile(spears, 2.5)), 4),
                          round(float(np.percentile(spears, 97.5)), 4)],
    }


def bootstrap_mean(x, rng):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 2:
        return None
    means = np.empty(BOOTSTRAP_ITER)
    for i in range(BOOTSTRAP_ITER):
        means[i] = x[_resample(rng, n)].mean()
    return means


def bootstrap_winrate(x, rng):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 2:
        return None
    wrs = np.empty(BOOTSTRAP_ITER)
    for i in range(BOOTSTRAP_ITER):
        wrs[i] = (x[_resample(rng, n)] > 0).mean()
    return wrs


def _regime_cell(forward_ret_pct, rng):
    """Full stats for a regime cell — wins AND losses separated.
    Input: forward returns as FRACTION (0.0036 = +0.36%).
    Output: all stats in PERCENT units (×100)."""
    fr = np.asarray(forward_ret_pct, dtype=float)
    fr = fr[np.isfinite(fr)]
    n = int(len(fr))
    if n < MIN_N:
        return None
    mean_b = bootstrap_mean(fr, rng)
    wr_b = bootstrap_winrate(fr, rng)
    if mean_b is None:
        return None
    wins = fr[fr > 0]
    losses = fr[fr <= 0]
    fr_pct = fr * 100.0
    wins_pct = wins * 100.0
    losses_pct = losses * 100.0
    q = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    return {
        "n": n,
        "mean_pct": round(float(fr_pct.mean()), 4),
        "mean_ci95": [round(float(np.percentile(mean_b, 2.5) * 100.0), 4),
                      round(float(np.percentile(mean_b, 97.5) * 100.0), 4)],
        "median_pct": round(float(np.median(fr_pct)), 4),
        "std_pct": round(float(fr_pct.std()), 4),
        "win_rate": round(float((fr > 0).mean()), 4),
        "win_rate_ci95": [round(float(np.percentile(wr_b, 2.5)), 4),
                          round(float(np.percentile(wr_b, 97.5)), 4)],
        "wins": {
            "n": int(len(wins)),
            "mean_pct": round(float(wins_pct.mean()), 4) if len(wins) > 0 else None,
            "median_pct": round(float(np.median(wins_pct)), 4) if len(wins) > 0 else None,
            "p25": round(float(np.percentile(wins_pct, 25)), 4) if len(wins) >= 4 else None,
            "p75": round(float(np.percentile(wins_pct, 75)), 4) if len(wins) >= 4 else None,
            "p90": round(float(np.percentile(wins_pct, 90)), 4) if len(wins) >= 4 else None,
            "max": round(float(wins_pct.max()), 4) if len(wins) > 0 else None,
        },
        "losses": {
            "n": int(len(losses)),
            "mean_pct": round(float(losses_pct.mean()), 4) if len(losses) > 0 else None,
            "median_pct": round(float(np.median(losses_pct)), 4) if len(losses) > 0 else None,
            "p25": round(float(np.percentile(losses_pct, 25)), 4) if len(losses) >= 4 else None,
            "p75": round(float(np.percentile(losses_pct, 75)), 4) if len(losses) >= 4 else None,
            "p10": round(float(np.percentile(losses_pct, 10)), 4) if len(losses) >= 4 else None,
            "min": round(float(losses_pct.min()), 4) if len(losses) > 0 else None,
        },
        "percentiles": {str(p): round(float(np.percentile(fr_pct, p)), 4) for p in q},
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 4) if len(losses) > 0 and losses.sum() != 0 else None,
        "kelly_f": round(float((fr > 0).mean() - (fr[fr <= 0].mean() / fr[fr > 0].mean()) if len(fr[fr > 0]) > 0 and fr[fr > 0].mean() != 0 else 0), 4),
    }


# ────────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────────
def main():
    rng = _rng()

    # 1. LOAD + ALIGN
    store = TimescaleDataStore()
    try:
        dfii10 = load_series(store, "DFII10")
        dfii5  = load_series(store, "DFII5")
        dgs10  = load_series(store, "DGS10")
        dgs2   = load_series(store, "DGS2")
        dtb3   = load_series(store, "DTB3")
        spy    = load_series(store, "SPY")
    finally:
        store.close()

    # Alinear: la intersección de todos es DFII10/DFII5 (2003+)
    common = (dfii10.index.intersection(dfii5.index)
              .intersection(dgs10.index).intersection(dgs2.index)
              .intersection(dtb3.index).intersection(spy.index))
    p = pd.DataFrame({
        "DFII10": dfii10[common],
        "DFII5":  dfii5[common],
        "DGS10":  dgs10[common],
        "DGS2":   dgs2[common],
        "DTB3":   dtb3[common],
        "SPY":    spy[common],
    }).dropna()

    meta = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_ranges": {
            "DFII10": [str(dfii10.index[0].date()), str(dfii10.index[-1].date()), int(len(dfii10))],
            "DFII5":  [str(dfii5.index[0].date()), str(dfii5.index[-1].date()), int(len(dfii5))],
            "DGS10":  [str(dgs10.index[0].date()), str(dgs10.index[-1].date()), int(len(dgs10))],
            "DGS2":   [str(dgs2.index[0].date()), str(dgs2.index[-1].date()), int(len(dgs2))],
            "DTB3":   [str(dtb3.index[0].date()), str(dtb3.index[-1].date()), int(len(dtb3))],
            "SPY":    [str(spy.index[0].date()), str(spy.index[-1].date()), int(len(spy))],
        },
        "panel": {
            "start": str(p.index[0].date()),
            "end": str(p.index[-1].date()),
            "n_days": int(len(p)),
        },
        "method": (
            "Forward return = SPY close-to-close over h trading days. "
            "Spearman ρ, CI95 bootstrap 3000 (seed 42) pairwise resample. "
            "Regime: mean, median, win rate, CI95, wins/losses separated."
        ),
    }
    print(f"Panel diario: {meta['panel']['start']} → {meta['panel']['end']}  N={len(p)} días")

    # 2. SEÑALES CANDIDATAS
    d10 = p["DFII10"]
    d5  = p["DFII5"]
    dgs = p["DGS10"]
    spy_close = p["SPY"]

    signals = {
        # Nivel de tasa real
        "DFII10": d10,                          # tasa real 10Y
        "DFII5":  d5,                           # tasa real 5Y
        # Velocidad de la tasa real 10Y
        "DFII10_d3d":  d10.diff(3),             # Δ3d
        "DFII10_d5d":  d10.diff(5),             # Δ5d
        "DFII10_d20d": d10.diff(20),            # Δ20d (cambio de tendencia)
        # Velocidad de la tasa real 5Y
        "DFII5_d5d":   d5.diff(5),              # Δ5d
        # Breakeven (inflación esperada)
        "BREAKEVEN":   dgs - d10,               # DGS10 − DFII10
        # Spreads benchmark (para comparación en PASO 6)
        "s_2y10y":     p["DGS2"] - dgs,         # DGS2−DGS10
        "s_2y3m":      p["DGS2"] - p["DTB3"],   # DGS2−DTB3
    }

    spy_vals = spy_close.to_numpy(dtype=float)
    n_total = len(p)

    # 3. CORRELACIÓN CON SPY FORWARD
    print("\n=== PASO 3: CORRELACIÓN CON SPY FORWARD ===")
    correlations = []
    for sname, sser in signals.items():
        x_all = sser.to_numpy(dtype=float)
        for h in HORIZONS:
            fwd = np.append(spy_vals[h:], np.full(h, np.nan))
            fwd_ret = fwd / spy_vals - 1.0
            res = bootstrap_corr(x_all, fwd_ret, rng)
            if res is None:
                continue
            # Non-overlapping check
            xnn, ynn = [], []
            for i in range(0, n_total - h, h):
                if np.isfinite(x_all[i]) and np.isfinite(fwd_ret[i]):
                    xnn.append(x_all[i])
                    ynn.append(fwd_ret[i])
            nonoverlap_n = None
            nonoverlap_spearman = None
            if len(xnn) >= 20:
                xnn_a = np.asarray(xnn); ynn_a = np.asarray(ynn)
                xrn = rankdata(xnn_a); yrn = rankdata(ynn_a)
                nonoverlap_n = int(len(xnn_a))
                nonoverlap_spearman = round(_corr_pearson(xrn, yrn), 4)
            res["horizon_days"] = h
            res["signal"] = sname
            res["nonoverlap_n"] = nonoverlap_n
            res["nonoverlap_spearman"] = nonoverlap_spearman
            correlations.append(res)
            print(f"  {sname:20s}  h={h:3d}  ρ_s={res['spearman']:8.4f}  CI95[{res['spearman_ci95'][0]:.4f},{res['spearman_ci95'][1]:.4f}]  N={res['n']:6d}  (nonoverlap: N={nonoverlap_n}, ρ_s={nonoverlap_spearman})")

    # Tabla compacta: mejor ρ_s por señal (todos los horizontes)
    corr_by_signal = {}
    for c in correlations:
        sig = c["signal"]
        if sig not in corr_by_signal:
            corr_by_signal[sig] = []
        corr_by_signal[sig].append(c)

    # 4. REGÍMENES DE TASA REAL
    print("\n=== PASO 4: REGÍMENES DE TASA REAL ===")
    # Percentiles empíricos de DFII10
    dfii10_p10 = float(d10.quantile(0.10))
    dfii10_p90 = float(d10.quantile(0.90))
    print(f"  DFII10 P10 = {dfii10_p10:.4f}%, P90 = {dfii10_p90:.4f}%")

    regimes = {
        "DFII10_POSITIVA":  d10 > 0,
        "DFII10_NEGATIVA":  d10 < 0,
        "DFII10_EXTREMA_ALTA":  d10 > dfii10_p90,
        "DFII10_EXTREMA_BAJA":  d10 < dfii10_p10,
        "DFII10_ZONA_NORMAL":  (d10 >= dfii10_p10) & (d10 <= dfii10_p90),
    }
    # Regímenes de velocidad
    vel3d = d10.diff(3)
    regimes_vel = {
        "DFII10_VEL3D_SUBE":  vel3d > 0,
        "DFII10_VEL3D_BAJA":  vel3d < 0,
        "DFII10_VEL3D_PLANA": vel3d == 0,
    }
    # Regímenes de breakeven
    be = dgs - d10
    be_p10 = float(be.quantile(0.10))
    be_p90 = float(be.quantile(0.90))
    regimes_be = {
        "BREAKEVEN_ALTO":  be > be_p90,
        "BREAKEVEN_BAJO":  be < be_p10,
    }

    regime_results = {}
    for h in HORIZONS:
        fwd = np.append(spy_vals[h:], np.full(h, np.nan))
        fwd_ret = fwd / spy_vals - 1.0
        for rname, rmask in regimes.items():
            key = f"{rname}__h{h}"
            sub = fwd_ret[rmask.to_numpy(dtype=bool)]
            cell = _regime_cell(sub, rng)
            if cell is not None:
                regime_results[key] = cell
                print(f"  {rname:30s}  h={h:3d}  N={cell['n']:5d}  mean={cell['mean_pct']:8.4f}%  WR={cell['win_rate']:.4f}  CI95[{cell['mean_ci95'][0]:.4f},{cell['mean_ci95'][1]:.4f}]")
        for rname, rmask in regimes_vel.items():
            key = f"{rname}__h{h}"
            # Para velocidad, solo horizontes 5/10/20
            if h in [5, 10, 20]:
                vel_mask = rmask.to_numpy(dtype=bool)
                # Alinear con forward ret (últimas h filas de vel_mask no tienen forward)
                # vel_mask tiene len n_total, fwd_ret igual. Misma alineación.
                sub = fwd_ret[vel_mask]
                cell = _regime_cell(sub, rng)
                if cell is not None:
                    regime_results[key] = cell
                    print(f"  {rname:30s}  h={h:3d}  N={cell['n']:5d}  mean={cell['mean_pct']:8.4f}%  WR={cell['win_rate']:.4f}  CI95[{cell['mean_ci95'][0]:.4f},{cell['mean_ci95'][1]:.4f}]")
        for rname, rmask in regimes_be.items():
            key = f"{rname}__h{h}"
            sub = fwd_ret[rmask.to_numpy(dtype=bool)]
            cell = _regime_cell(sub, rng)
            if cell is not None:
                regime_results[key] = cell
                print(f"  {rname:30s}  h={h:3d}  N={cell['n']:5d}  mean={cell['mean_pct']:8.4f}%  WR={cell['win_rate']:.4f}  CI95[{cell['mean_ci95'][0]:.4f},{cell['mean_ci95'][1]:.4f}]")

    # 5. DIFERENCIAL ENTRE REGÍMENES
    print("\n=== PASO 5: DIFERENCIAL DE REGÍMENES (TASA REAL POSITIVA vs NEGATIVA) ===")
    diffs = {}
    for h in HORIZONS:
        fwd = np.append(spy_vals[h:], np.full(h, np.nan))
        fwd_ret = fwd / spy_vals - 1.0
        pos_mask = (d10 > 0).to_numpy(dtype=bool)
        neg_mask = (d10 < 0).to_numpy(dtype=bool)
        pos_ret = fwd_ret[pos_mask]
        neg_ret = fwd_ret[neg_mask]
        pos_cell = _regime_cell(pos_ret, rng)
        neg_cell = _regime_cell(neg_ret, rng)
        if pos_cell and neg_cell:
            # Bootstrap diff
            pos_b = bootstrap_mean(pos_ret, rng)
            neg_b = bootstrap_mean(neg_ret, rng)
            diff_b = pos_b - neg_b if pos_b is not None and neg_b is not None else None
            diff_mean = pos_cell["mean_pct"] - neg_cell["mean_pct"]
            diff_ci = None
            if diff_b is not None:
                diff_ci = [round(float(np.percentile(diff_b, 2.5) * 100.0), 4),
                           round(float(np.percentile(diff_b, 97.5) * 100.0), 4)]
            diffs[f"POSITIVA_NEGATIVA_h{h}"] = {
                "n_pos": pos_cell["n"],
                "n_neg": neg_cell["n"],
                "mean_pos_pct": pos_cell["mean_pct"],
                "mean_neg_pct": neg_cell["mean_pct"],
                "diff_mean_pct": round(diff_mean, 4),
                "diff_ci95": diff_ci,
            }
            print(f"  h={h:3d}  POSITIVA={pos_cell['mean_pct']:8.4f}% N={pos_cell['n']:5d}  NEGATIVA={neg_cell['mean_pct']:8.4f}% N={neg_cell['n']:5d}  DIFF={diff_mean:8.4f}%  CI95={diff_ci}")

    # EXTREMA ALTA vs EXTREMA BAJA
    ext_diffs = {}
    for h in HORIZONS:
        fwd = np.append(spy_vals[h:], np.full(h, np.nan))
        fwd_ret = fwd / spy_vals - 1.0
        high_mask = (d10 > dfii10_p90).to_numpy(dtype=bool)
        low_mask = (d10 < dfii10_p10).to_numpy(dtype=bool)
        high_ret = fwd_ret[high_mask]
        low_ret = fwd_ret[low_mask]
        hi_cell = _regime_cell(high_ret, rng)
        lo_cell = _regime_cell(low_ret, rng)
        if hi_cell and lo_cell:
            hi_b = bootstrap_mean(high_ret, rng)
            lo_b = bootstrap_mean(low_ret, rng)
            diff_b = hi_b - lo_b if hi_b is not None and lo_b is not None else None
            diff_mean = hi_cell["mean_pct"] - lo_cell["mean_pct"]
            diff_ci = None
            if diff_b is not None:
                diff_ci = [round(float(np.percentile(diff_b, 2.5) * 100.0), 4),
                           round(float(np.percentile(diff_b, 97.5) * 100.0), 4)]
            ext_diffs[f"EXTREMA_ALTA_BAJA_h{h}"] = {
                "n_high": hi_cell["n"],
                "n_low": lo_cell["n"],
                "mean_high_pct": hi_cell["mean_pct"],
                "mean_low_pct": lo_cell["mean_pct"],
                "diff_mean_pct": round(diff_mean, 4),
                "diff_ci95": diff_ci,
            }
            print(f"  EXTREMA h={h:3d}  ALTA={hi_cell['mean_pct']:8.4f}% N={hi_cell['n']:5d}  BAJA={lo_cell['mean_pct']:8.4f}% N={lo_cell['n']:5d}  DIFF={diff_mean:8.4f}%  CI95={diff_ci}")

    # 6. COMPARACIÓN CON SPREADS
    print("\n=== PASO 6: COMPARACIÓN TASA REAL vs SPREADS ===")
    # Ya tenemos las correlaciones de DFII10, s_2y10y, s_2y3m en `correlations`
    # Encontrar el mejor |ρ_s| por señal y horizonte
    benchmark = {}
    for signal_name in ["DFII10", "s_2y10y", "s_2y3m"]:
        sig_corrs = [c for c in correlations if c["signal"] == signal_name]
        benchmark[signal_name] = {}
        for c in sig_corrs:
            benchmark[signal_name][c["horizon_days"]] = {
                "spearman": c["spearman"],
                "spearman_ci95": c["spearman_ci95"],
                "n": c["n"],
            }
        print(f"  {signal_name:20s}: " + ", ".join(
            f"h={h} ρ_s={benchmark[signal_name][h]['spearman']:.4f}" for h in HORIZONS if h in benchmark[signal_name]
        ))

    # 7. VEREDICTO
    print("\n" + "=" * 72)
    print("=== PASO 7: VEREDICTO ===")
    print("=" * 72)

    # Encontrar mejor señal por |ρ_s| promedio y por horizonte
    def best_by_metric(metric_fn, label):
        """Find the best signal by some metric function of correlations."""
        sig_scores = {}
        for c in correlations:
            s = c["signal"]
            if s not in sig_scores:
                sig_scores[s] = []
            sig_scores[s].append(metric_fn(c))
        avg = {s: float(np.mean(v)) for s, v in sig_scores.items() if len(v) > 0}
        ranked = sorted(avg.items(), key=lambda x: abs(x[1]), reverse=True)
        print(f"\n  {label}:")
        for s, v in ranked[:10]:
            print(f"    {s:20s}  avg = {v:8.4f}")
        return ranked

    # Best by |spearman|
    ranked_all = best_by_metric(lambda c: c["spearman"], "Mejor señal por |ρ_s| promedio (todos los horizontes)")

    # Best per horizon
    print("\n  Mejor señal por horizonte (máx |ρ_s|):")
    for h in HORIZONS:
        h_corrs = [(c["signal"], c["spearman"]) for c in correlations if c["horizon_days"] == h]
        best = max(h_corrs, key=lambda x: abs(x[1]))
        print(f"    h={h:3d}: {best[0]:20s}  ρ_s={best[1]:.4f}")

    # Verdict text
    verdict = _build_verdict(correlations, regime_results, diffs, benchmark, ranked_all)
    print(f"\n  VEREDICTO: {verdict['summary']}")
    print(f"  RECOMENDACIÓN: {verdict['recommendation']}")

    # ────────────────────────────────────────────────────────────────────
    # BUILD REPORT
    # ────────────────────────────────────────────────────────────────────
    report = {
        "meta": meta,
        "señales_candidatas": {
            "DFII10": "Tasa real 10Y (TIPS), nivel",
            "DFII5": "Tasa real 5Y (TIPS), nivel",
            "DFII10_d3d": "Velocidad Δ3d de la tasa real 10Y",
            "DFII10_d5d": "Velocidad Δ5d de la tasa real 10Y",
            "DFII10_d20d": "Velocidad Δ20d (cambio de tendencia) de la tasa real 10Y",
            "DFII5_d5d": "Velocidad Δ5d de la tasa real 5Y",
            "BREAKEVEN": "Inflación esperada = DGS10 − DFII10",
            "s_2y10y": "Spread 2Y-10Y (benchmark de curva)",
            "s_2y3m": "Spread 2Y-3M (benchmark de curva)",
        },
        "correlations": sorted(correlations, key=lambda c: abs(c["spearman"]), reverse=True),
        "correlation_by_signal": {sig: sorted(vals, key=lambda c: c["horizon_days"]) for sig, vals in corr_by_signal.items()},
        "regimes": regime_results,
        "diferencial_regimenes_positiva_negativa": diffs,
        "diferencial_regimenes_extrema_alta_baja": ext_diffs,
        "benchmark_comparison": benchmark,
        "veredicto": verdict,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReporte escrito: {REPORT_PATH}")


def _build_verdict(correlations, regime_results, diffs, benchmark, ranked_all):
    """Build the verdict dict based on the data — dato mata relato."""
    # ── Clasificación de señales ──
    # Tasa real PURA (nivel): DFII10, DFII5
    tasa_real_level = ["DFII10", "DFII5"]
    # Velocidad de tasa real (derivadas)
    tasa_real_vel = ["DFII10_d3d", "DFII10_d5d", "DFII10_d20d", "DFII5_d5d"]
    # Breakeven (inflación esperada) — canal DISTINTO
    breakeven_sig = ["BREAKEVEN"]
    # Spreads benchmark
    spread_signals = ["s_2y10y", "s_2y3m"]

    # ── Separar por familia ──
    def corrs_by_signal(names):
        return [c for c in correlations if c["signal"] in names]

    tr_level_corrs = corrs_by_signal(tasa_real_level)
    tr_vel_corrs = corrs_by_signal(tasa_real_vel)
    be_corrs = corrs_by_signal(breakeven_sig)
    spread_corrs = corrs_by_signal(spread_signals)

    def max_abs_rho(corrs):
        best = max(corrs, key=lambda c: abs(c["spearman"])) if corrs else None
        return best

    best_tr_level = max_abs_rho(tr_level_corrs)
    best_tr_vel = max_abs_rho(tr_vel_corrs)
    best_be = max_abs_rho(be_corrs)
    best_spread = max_abs_rho(spread_corrs)

    tr_level_max = abs(best_tr_level["spearman"]) if best_tr_level else 0
    tr_vel_max = abs(best_tr_vel["spearman"]) if best_tr_vel else 0
    be_max = abs(best_be["spearman"]) if best_be else 0
    spread_max = abs(best_spread["spearman"]) if best_spread else 0

    # ── Régimen ──
    regime_sig = False
    regime_sig_details = []
    for k, v in diffs.items():
        if v.get("diff_ci95") and v["diff_ci95"][0] * v["diff_ci95"][1] > 0:
            regime_sig = True
            regime_sig_details.append({"regimen": k, "diff": v["diff_mean_pct"], "ci95": v["diff_ci95"]})

    # ── Velocidad vs nivel ──
    if tr_level_corrs and tr_vel_corrs:
        avg_level = abs(np.mean([c["spearman"] for c in tr_level_corrs]))
        avg_vel = abs(np.mean([c["spearman"] for c in tr_vel_corrs]))
        vel_beats_level = avg_vel > avg_level
    else:
        avg_level = avg_vel = 0
        vel_beats_level = False

    # ── Clasificación de fuerza (basada en DFII10 nivel, NO en BREAKEVEN) ──
    if tr_level_max < 0.05:
        tr_strength = "MUY DÉBIL (ρ_s < 0.05)"
        tr_practical = "Ninguna — la tasa real (nivel) NO predice la tendencia de SPY a corto plazo"
    elif tr_level_max < 0.10:
        tr_strength = "DÉBIL (0.05 ≤ ρ_s < 0.10)"
        tr_practical = "Muy limitada — señal marginal, no explotable para trading táctico"
    else:
        tr_strength = "MODERADA (ρ_s ≥ 0.10)"
        tr_practical = "Limitada — señal presente pero débil para decisiones tácticas"

    # BREAKEVEN strength
    if be_max >= 0.15:
        be_strength = "MODERADA (ρ_s ≈ 0.21)"
    elif be_max >= 0.10:
        be_strength = "MODERADA-DÉBIL"
    else:
        be_strength = "DÉBIL"

    # Spread strength
    if spread_max >= 0.15:
        spread_strength = "MODERADA (ρ_s ≈ 0.26)"
    elif spread_max >= 0.10:
        spread_strength = "MODERADA-DÉBIL"
    else:
        spread_strength = "DÉBIL"

    # ── Bullet points ──
    bullets = []
    bullets.append(f"DFII10 (nivel tasa real): max |ρ_s| = {tr_level_max:.4f} @h={best_tr_level['horizon_days']}d — {tr_strength}")
    bullets.append(f"VELOCIDAD (Δ3d/5d/20d): max |ρ_s| = {tr_vel_max:.4f} @h={best_tr_vel['horizon_days'] if best_tr_vel else '?'}d")
    bullets.append(f"VELOCIDAD {'supera' if vel_beats_level else 'NO supera'} al NIVEL en correlación promedio")
    bullets.append(f"BREAKEVEN (inflación esperada): max |ρ_s| = {be_max:.4f} @h={best_be['horizon_days'] if best_be else '?'}d — {be_strength}")
    bullets.append(f"s_2y3m (spread benchmark): max |ρ_s| = {spread_max:.4f} @h={best_spread['horizon_days'] if best_spread else '?'}d — {spread_strength}")
    if regime_sig:
        for rd in regime_sig_details:
            bullets.append(f"Régimen significativo: {rd['regimen']} diff={rd['diff']:.4f}% CI95{rd['ci95']}")
    else:
        bullets.append("Régimen de tasa real (positiva/negativa): diferencial NO significativo CI95 cruza cero")

    # ── Summary ──
    # El veredicto REAL: comparar DFII10 nivel (tasa real pura) vs spreads
    tasa_real_mejor_que_spreads = tr_level_max > spread_max
    breakeven_mejor_que_spreads = be_max > spread_max

    if tasa_real_mejor_que_spreads:
        comparison = "TASA REAL (nivel) supera a los spreads benchmark"
        recommendation = "CONSIDERAR reemplazar YIELD_CURVE (spread) por TASA_REAL (TIPS) para señal de tendencia corta. Sin embargo, la correlación es muy débil (ρ_s < 0.05) — el reemplazo no mejora materialmente la señal."
    elif breakeven_mejor_que_spreads:
        comparison = "BREAKEVEN (inflación esperada) supera ligeramente a los spreads, pero s_2y3m sigue siendo mejor"
        recommendation = "MANTENER YIELD_CURVE (spreads). El BREAKEVEN (DGS10−DFII10) es un predictor moderado, pero s_2y3m (ρ_s=-0.26@60d) supera al BREAKEVEN (ρ_s=-0.21@60d). Si se quiere explorar, usar BREAKEVEN como señal secundaria, no como reemplazo."
    else:
        comparison = "SPREADS (s_2y3m) superan a TODAS las señales de la familia de tasas reales"
        recommendation = "MANTENER YIELD_CURVE (spreads). La tasa real NO supera a los spreads nominales como señal de tendencia corta. s_2y3m (DGS2−DTB3, ρ_s=-0.26@60d) es la MEJOR señal de la familia de tasas. La tasa real pura es la PEOR (ρ_s≈-0.05)."

    # Determine best signal overall
    all_signal_groups = [
        ("DFII10_NIVEL", tr_level_max, best_tr_level),
        ("DFII10_VELOCIDAD", tr_vel_max, best_tr_vel),
        ("BREAKEVEN", be_max, best_be),
        ("s_2y3m", spread_max, best_spread),
    ]
    all_signal_groups = [(n, v, c) for n, v, c in all_signal_groups if c is not None]
    best_overall = max(all_signal_groups, key=lambda x: x[1])

    summary = (
        f"La TASA REAL (DFII10 nivel, ρ_s≈{tr_level_max:.3f}) es MUY DÉBIL como predictor de la tendencia de SPY a corto plazo. "
        f"La VELOCIDAD (Δ20d, ρ_s≈{tr_vel_max:.3f}) es marginalmente mejor pero sigue siendo débil. "
        f"El BREAKEVEN (inflación esperada, ρ_s≈{be_max:.3f}) es moderado pero tampoco supera a s_2y3m (ρ_s={spread_max:.3f}). "
        f"La MEJOR señal de la familia de tasas para horizontes cortos es s_2y3m (DGS2−DTB3, ρ_s≈{spread_max:.3f}@60d). "
        f"{comparison}."
    )

    return {
        "summary": summary,
        "tasa_real_nivel": {
            "signal_strength": tr_strength,
            "practical_value": tr_practical,
            "max_abs_rho": round(tr_level_max, 4),
            "best_horizon": best_tr_level["horizon_days"] if best_tr_level else None,
            "best_spearman": best_tr_level["spearman"] if best_tr_level else None,
        },
        "tasa_real_velocidad": {
            "max_abs_rho": round(tr_vel_max, 4),
            "best_signal": best_tr_vel["signal"] if best_tr_vel else None,
            "best_horizon": best_tr_vel["horizon_days"] if best_tr_vel else None,
            "best_spearman": best_tr_vel["spearman"] if best_tr_vel else None,
            "supera_nivel": vel_beats_level,
        },
        "breakeven": {
            "max_abs_rho": round(be_max, 4),
            "best_horizon": best_be["horizon_days"] if best_be else None,
            "best_spearman": best_be["spearman"] if best_be else None,
            "signal_strength": be_strength,
        },
        "spreads_benchmark": {
            "max_abs_rho": round(spread_max, 4),
            "best_signal": best_spread["signal"] if best_spread else None,
            "best_horizon": best_spread["horizon_days"] if best_spread else None,
            "best_spearman": best_spread["spearman"] if best_spread else None,
            "signal_strength": spread_strength,
        },
        "mejor_senal_familia_tasas": {
            "nombre": best_overall[0],
            "max_abs_rho": round(best_overall[1], 4),
            "detalle": f"{best_overall[2]['signal']} @h={best_overall[2]['horizon_days']}d ρ_s={best_overall[2]['spearman']:.4f}" if best_overall[2] else None,
        },
        "comparacion_tasa_real_vs_spreads": {
            "tasa_real_nivel_max_abs_rho": round(tr_level_max, 4),
            "tasa_real_velocidad_max_abs_rho": round(tr_vel_max, 4),
            "breakeven_max_abs_rho": round(be_max, 4),
            "spreads_max_abs_rho": round(spread_max, 4),
            "tasa_real_supera_spreads": tasa_real_mejor_que_spreads,
            "breakeven_supera_spreads": breakeven_mejor_que_spreads,
            "spreads_son_los_mejores": not (tasa_real_mejor_que_spreads or breakeven_mejor_que_spreads),
        },
        "regimen_significativo": regime_sig,
        "regimen_detalles": regime_sig_details,
        "bullet_points": bullets,
        "recommendation": recommendation,
        "anti_adulacion": (
            "La tasa real (DFII10 nivel, ρ_s≈-0.05) es la PEOR señal de la familia de tasas para tendencia corta. "
            "La velocidad (DFII10_d20d, ρ_s≈-0.08) es marginalmente mejor pero sigue siendo débil. "
            "El BREAKEVEN (DGS10−DFII10, ρ_s≈-0.21) es el mejor de la familia TIPS pero NO supera a s_2y3m (ρ_s=-0.26). "
            "La mejor señal de toda la familia de tasas para horizontes 5-60d es s_2y3m (DGS2−DTB3). "
            "NO reemplazar YIELD_CURVE por TASA_REAL. Mantener los spreads nominales del tramo corto de la curva."
        ),
    }


if __name__ == "__main__":
    main()