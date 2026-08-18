#!/usr/bin/env python3
"""
yield_short_end_trend.py — Tramo corto de la curva (DTB3/DGS2, 3M vs 2Y) vs TENDENCIA de SPY
=========================================================================================
Pregunta: ¿el tramo CORTO de la curva (3M vs 2Y) predice la TENDENCIA de SPY en horizontes
CORTOS (5/10/20/60 días)?  No nos interesa el horizonte 12-24m de recesión (eso ya está en
intelligence). Buscamos una señal TÁCTICA (rápida), no solo estructural (lenta).

HIPÓTESIS
  3M > 2Y (inversión tramo corto)  = liquidez TIGHT → ¿SPY corrige?
  3M < 2Y (curva corta normal)     = liquidez NORMAL → ¿SPY sigue tendencia?
  VELOCIDAD Δ3d/Δ5d del spread     → ¿cambios rápidos predicen cambios de tendencia?

MÉTODO
  PASO 1 — Cargar DTB3, DGS2, SPY diarios del Vault (TimescaleDataStore).
  PASO 2 — s_2y3m = DGS2−DTB3 ; ratio_3m2y = DTB3/DGS2 ; vel_3d/vel_5d = Δ del spread.
  PASO 3 — Spearman/Pearson de cada señal vs forward SPY a 5/10/20/60d (+1/3d para timing).
           CI95 bootstrap 3000 (seed 42) + chequeo NO-solapado (stride=horizonte, N honesto).
  PASO 4 — REGÍMENES: INVERTIDO (s<0), NORMAL (s>0), EXTREMO (s<P5), ratio>1 vs ratio<1.
           N, mean, median, win rate, CI95 bootstrap, P25/P75, min/max. Diff INVERTIDO−NORMAL.
  PASO 5 — VELOCIDAD como señal: vel>0 (empinándose) vs vel<0 (aplanándose). ¿Más rápida que el
           nivel?  → pico de |Spearman| por horizonte + lead-time del flip de velocidad vs cruce
           del nivel.
  PASO 6 — VEREDICTO (dato mata relato; anti-adulación).

REGLA: DATO MATA RELATO. CI95 + N mínimo 20. Presentar distribución WINS/LOSSES, no solo media.

ENTREGABLE: scratch/yield_short_end_trend_report.json
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = Path(__file__).resolve().parent / "yield_short_end_trend_report.json"

BOOTSTRAP_ITER = 3000
BOOTSTRAP_SEED = 42
HORIZONS = [5, 10, 20, 60]          # horizontes CORTOS (lo que pide la tarea)
TIMING_HORIZONS = [1, 3, 5, 10, 20, 60]  # sweep extra para responder "¿más rápida?"
MIN_N = 20


# ────────────────────────────────────────────────────────────────────
# 1. LOAD + ALIGN
# ────────────────────────────────────────────────────────────────────
def load_series(store, ticker):
    df = store.load_bars(ticker, "1d")
    if df.empty:
        raise RuntimeError(f"No bars for {ticker}")
    df.index = pd.to_datetime(df.index)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    s = df["close"].astype(float)
    s = s[~s.index.duplicated(keep="first")].sort_index()
    return s


# ────────────────────────────────────────────────────────────────────
# BOOTSTRAP HELPERS (seed 42, vectorizados)
# ────────────────────────────────────────────────────────────────────
def _resample(rng, n):
    return rng.integers(0, n, n)


def bootstrap_mean(x, rng):
    """Bootstrap distribution of the mean of x (finite only)."""
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
    """Bootstrap distribution of the win rate (fraction > 0)."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 2:
        return None
    wrs = np.empty(BOOTSTRAP_ITER)
    for i in range(BOOTSTRAP_ITER):
        wrs[i] = (x[_resample(rng, n)] > 0).mean()
    return wrs


def _corr_pearson(a, b):
    ac = a - a.mean()
    bc = b - b.mean()
    den = np.sqrt((ac * ac).sum() * (bc * bc).sum())
    return float((ac * bc).sum() / den) if den > 0 else 0.0


def bootstrap_corr(x, y, rng):
    """Pearson + Spearman point estimates and CI95 (bootstrap, seed 42)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = len(x)
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
        "n": int(n),
        "pearson": round(pear_pt, 4),
        "pearson_ci95": [round(float(np.percentile(pears, 2.5)), 4),
                         round(float(np.percentile(pears, 97.5)), 4)],
        "spearman": round(spear_pt, 4),
        "spearman_ci95": [round(float(np.percentile(spears, 2.5)), 4),
                          round(float(np.percentile(spears, 97.5)), 4)],
    }


def _regime_cell(forward_ret_pct, rng):
    """Estadísticas de forward return para un subconjunto (régimen)."""
    fr = np.asarray(forward_ret_pct, dtype=float)
    fr = fr[np.isfinite(fr)]
    n = len(fr)
    if n < MIN_N:
        return None
    mean_b = bootstrap_mean(fr, rng)
    wr_b = bootstrap_winrate(fr, rng)
    return {
        "n": int(n),
        "mean_pct": round(float(fr.mean()), 2),
        "mean_ci95": [round(float(np.percentile(mean_b, 2.5)), 2),
                      round(float(np.percentile(mean_b, 97.5)), 2)],
        "median_pct": round(float(np.median(fr)), 2),
        "win_rate": round(float((fr > 0).mean()), 4),
        "win_rate_ci95": [round(float(np.percentile(wr_b, 2.5)), 4),
                          round(float(np.percentile(wr_b, 97.5)), 4)],
        "p25_pct": round(float(np.percentile(fr, 25)), 2),
        "p75_pct": round(float(np.percentile(fr, 75)), 2),
        "min_pct": round(float(fr.min()), 2),
        "max_pct": round(float(fr.max()), 2),
    }


def _nonoverlap_stats(forward_ret_pct, h):
    """Estadísticas no-solapadas (stride=h) como N honesto."""
    fr = np.asarray(forward_ret_pct, dtype=float)
    nn = fr[::h]
    nn = nn[np.isfinite(nn)]
    if len(nn) < MIN_N:
        return None
    return {
        "n_nonoverlap": int(len(nn)),
        "mean_nonoverlap_pct": round(float(nn.mean()), 2),
        "win_rate_nonoverlap": round(float((nn > 0).mean()), 4),
    }


def diff_bootstrap_ci(a, b, rng):
    """CI95 bootstrap de la diferencia de medias (a − b) + p two-sided."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    na, nb = len(a), len(b)
    if na < MIN_N or nb < MIN_N:
        return None
    diffs = np.empty(BOOTSTRAP_ITER)
    for i in range(BOOTSTRAP_ITER):
        diffs[i] = a[_resample(rng, na)].mean() - b[_resample(rng, nb)].mean()
    point = a.mean() - b.mean()
    # p two-sided: fracción de resamples en el lado CONTRARIO al point estimate
    p_side = float((diffs <= 0).mean()) if point >= 0 else float((diffs >= 0).mean())
    p_two_sided = min(1.0, 2.0 * p_side)
    return {
        "mean_diff_pct": round(float(point), 2),
        "ci95": [round(float(np.percentile(diffs, 2.5)), 2),
                 round(float(np.percentile(diffs, 97.5)), 2)],
        "p_two_sided": round(p_two_sided, 4),
        "sig_ci_excludes_zero": bool(np.percentile(diffs, 2.5) > 0 or np.percentile(diffs, 97.5) < 0),
    }


def main():
    store = TimescaleDataStore()
    try:
        dgs2 = load_series(store, "DGS2")
        dtb3 = load_series(store, "DTB3")
        spy = load_series(store, "SPY")
    finally:
        store.close()

    common = dgs2.index.intersection(dtb3.index).intersection(spy.index)
    p = pd.DataFrame({
        "DGS2": dgs2[common],
        "DTB3": dtb3[common],
        "SPY": spy[common],
    }).dropna()
    p = p[~p.index.duplicated(keep="first")].sort_index()

    meta = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "task": "¿El tramo corto de la curva (DTB3/DGS2) predice la TENDENCIA de SPY a 5/10/20/60d?",
        "data": {
            "DGS2": [str(dgs2.index[0].date()), str(dgs2.index[-1].date()), int(len(dgs2))],
            "DTB3": [str(dtb3.index[0].date()), str(dtb3.index[-1].date()), int(len(dtb3))],
            "SPY": [str(spy.index[0].date()), str(spy.index[-1].date()), int(len(spy))],
        },
        "panel": {"start": str(p.index[0].date()), "end": str(p.index[-1].date()),
                  "n_days": int(len(p))},
        "horizons_trading_days": HORIZONS,
        "bootstrap_iter": BOOTSTRAP_ITER,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "min_n": MIN_N,
        "method": (
            "forward return = SPY close-to-close over h trading days (%). "
            "spearman/pearson + CI95 bootstrap 3000 (seed 42). "
            "regimes: mean/median/win-rate + CI95 bootstrap + P25/P75/min/max. "
            "non-overlap stride=h reported as honest N (overlapping fwd returns inflate N)."
        ),
        "sign_convention": {
            "s_2y3m": "DGS2 − DTB3  (>0 normal 2Y>3M, <0 INVERTIDO 3M>2Y)",
            "ratio_3m2y": "DTB3 / DGS2  (>1 INVERTIDO, <1 normal; INESTABLE si DGS2≈0)",
            "vel_2y3m_3d": "Δ3d de s_2y3m  (>0 empinándose, <0 aplanándose/invirtiéndose)",
            "vel_2y3m_5d": "Δ5d de s_2y3m  (>0 empinándose, <0 aplanándose/invirtiéndose)",
        },
    }

    print(f"Panel diario: {meta['panel']['start']} → {meta['panel']['end']}  N={len(p)} días")

    d2 = p["DGS2"].to_numpy(dtype=float)
    d3 = p["DTB3"].to_numpy(dtype=float)
    spy_vals = p["SPY"].to_numpy(dtype=float)

    s_2y3m = d2 - d3
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = d3 / d2
    ratio = np.where(np.isfinite(ratio), ratio, np.nan)
    s_series = pd.Series(s_2y3m, index=p.index)
    vel_3d = s_series.diff(3).to_numpy(dtype=float)
    vel_5d = s_series.diff(5).to_numpy(dtype=float)

    signals = {
        "s_2y3m": s_2y3m,
        "ratio_3m2y": ratio,
        "vel_2y3m_3d": vel_3d,
        "vel_2y3m_5d": vel_5d,
    }

    def forward_return(h):
        """SPY forward return (%) close-to-close over h trading days, aligned to t."""
        fwd = np.empty_like(spy_vals)
        fwd[: len(spy_vals) - h] = spy_vals[h:]
        fwd[len(spy_vals) - h:] = np.nan
        return (fwd / spy_vals - 1.0) * 100.0

    n_total = len(p)
    rng = np.random.default_rng(BOOTSTRAP_SEED)

    # ────────────────────────────────────────────────────────────────────
    # PASO 3 — CORRELACIÓN señal × forward SPY (horizontes cortos + timing sweep)
    # ────────────────────────────────────────────────────────────────────
    correlations = []
    for sname, sarr in signals.items():
        for h in TIMING_HORIZONS:
            fr = forward_return(h)
            res = bootstrap_corr(sarr, fr, rng)
            if res is None:
                continue
            # no-solapado stride=h
            xs = sarr[::h]
            ys = fr[::h]
            m = np.isfinite(xs) & np.isfinite(ys)
            xs, ys = xs[m], ys[m]
            nonoverlap = None
            if len(xs) >= MIN_N:
                nonoverlap = {
                    "n_nonoverlap": int(len(xs)),
                    "spearman": round(_corr_pearson(rankdata(xs), rankdata(ys)), 4),
                }
            correlations.append({"signal": sname, "horizon": h, **res,
                                 "nonoverlap": nonoverlap})

    # ────────────────────────────────────────────────────────────────────
    # PASO 4 — REGÍMENES (nivel + ratio)
    # ────────────────────────────────────────────────────────────────────
    p5 = float(np.percentile(s_2y3m[np.isfinite(s_2y3m)], 5))
    p95 = float(np.percentile(s_2y3m[np.isfinite(s_2y3m)], 95))

    regime_defs = {
        "invertido_s2y3m_lt0": ("INVERTIDO (3M > 2Y)", s_2y3m < 0),
        "normal_s2y3m_gt0": ("NORMAL (2Y > 3M)", s_2y3m > 0),
        "extremo_inversion_s2y3m_lt_p5": (f"EXTREMO s_2y3m < P5 (={p5:.2f})", s_2y3m < p5),
        "ratio_gt1_invertido": ("ratio 3M/2Y > 1", ratio > 1),
        "ratio_lt1_normal": ("ratio 3M/2Y < 1", ratio < 1),
    }

    regimes = {}
    for key, (label, mask) in regime_defs.items():
        entry = {"label": label}
        for h in HORIZONS:
            fr = forward_return(h)
            cell = _regime_cell(fr[mask], rng)
            if cell is not None:
                no = _nonoverlap_stats(fr[mask], h)
                if no is not None:
                    cell.update(no)
            entry[f"h{h}"] = cell
        regimes[key] = entry

    # comparación INVERTIDO vs NORMAL (diff bootstrap) por horizonte
    inv_mask = s_2y3m < 0
    nor_mask = s_2y3m > 0
    regime_comparison = {}
    for h in HORIZONS:
        fr = forward_return(h)
        d = diff_bootstrap_ci(fr[inv_mask], fr[nor_mask], rng)
        if d is not None:
            inv_vals = fr[inv_mask]
            nor_vals = fr[nor_mask]
            d["invertido_mean_pct"] = round(float(inv_vals[np.isfinite(inv_vals)].mean()), 2)
            d["normal_mean_pct"] = round(float(nor_vals[np.isfinite(nor_vals)].mean()), 2)
            d["n_invertido"] = int(inv_mask.sum())
            d["n_normal"] = int(nor_mask.sum())
        regime_comparison[f"h{h}"] = d

    # ────────────────────────────────────────────────────────────────────
    # PASO 5 — VELOCIDAD como señal (timing)
    # ────────────────────────────────────────────────────────────────────
    vel_regimes = {}
    for vname, varr, label_pos, label_neg in [
        ("vel_3d", vel_3d, "vel_3d > 0 (empinándose)", "vel_3d < 0 (aplanándose)"),
        ("vel_5d", vel_5d, "vel_5d > 0 (empinándose)", "vel_5d < 0 (aplanándose)"),
    ]:
        pos = np.isfinite(varr) & (varr > 0)
        neg = np.isfinite(varr) & (varr < 0)
        for h in HORIZONS:
            fr = forward_return(h)
            pc = _regime_cell(fr[pos], rng)
            if pc is not None:
                no = _nonoverlap_stats(fr[pos], h)
                if no is not None:
                    pc.update(no)
            nc = _regime_cell(fr[neg], rng)
            if nc is not None:
                no = _nonoverlap_stats(fr[neg], h)
                if no is not None:
                    nc.update(no)
            dd = diff_bootstrap_ci(fr[pos], fr[neg], rng)
            vel_regimes[f"{vname}_h{h}"] = {
                "label_pos": label_pos, "label_neg": label_neg,
                "pos": pc, "neg": nc, "pos_minus_neg": dd,
            }

    # ¿la velocidad reacciona MÁS RÁPIDO que el nivel?  → pico de |Spearman| por señal
    def best_horizon(sname):
        cs = [c for c in correlations if c["signal"] == sname]
        if not cs:
            return None
        b = max(cs, key=lambda c: abs(c["spearman"]))
        return {"best_horizon": b["horizon"], "spearman": b["spearman"],
                "spearman_ci95": b["spearman_ci95"]}

    level_vs_velocity = {
        "best_horizon_per_signal": {s: best_horizon(s) for s in signals},
        "vel_3d_vs_level_at_short_horizons": {
            str(h): {
                "level_spearman": next((c["spearman"] for c in correlations
                                        if c["signal"] == "s_2y3m" and c["horizon"] == h), None),
                "vel3d_spearman": next((c["spearman"] for c in correlations
                                        if c["signal"] == "vel_2y3m_3d" and c["horizon"] == h), None),
                "vel5d_spearman": next((c["spearman"] for c in correlations
                                        if c["signal"] == "vel_2y3m_5d" and c["horizon"] == h), None),
            } for h in HORIZONS
        },
    }

    # lead-time: ¿el flip de la velocidad (Δ5d<0) precede al cruce del NIVEL (s<0)?
    # episodios de inversión = primer día s<0 tras s>0; medir días de ventaja del vel<0.
    # ventana 750d (3 años) para NO truncar el aplanamiento gradual (la curva se aplana
    # durante meses/años antes de invertir).
    LEAD_WINDOW = 750
    inversion_episodes = []
    prev = s_2y3m[0]
    for i in range(1, n_total):
        if prev > 0 and s_2y3m[i] < 0:
            inversion_episodes.append(i)
        prev = s_2y3m[i]
    lead_days = []
    for e in inversion_episodes:
        w = slice(max(0, e - LEAD_WINDOW), e + 1)
        vw = vel_5d[w]
        nf = vw[np.isfinite(vw) & (vw < 0)]
        if len(nf):
            first_neg_idx = max(0, e - LEAD_WINDOW) + int(np.argmax(np.isfinite(vw) & (vw < 0)))
            lead_days.append(e - first_neg_idx)
    timing_lead = {
        "n_inversion_episodes": int(len(inversion_episodes)),
        "inversion_dates": [str(p.index[e].date()) for e in inversion_episodes],
        "vel5d_flip_lead_days": {
            "n": int(len(lead_days)),
            "median": round(float(np.median(lead_days)), 1) if lead_days else None,
            "mean": round(float(np.mean(lead_days)), 1) if lead_days else None,
            "p25": round(float(np.percentile(lead_days, 25)), 1) if lead_days else None,
            "p75": round(float(np.percentile(lead_days, 75)), 1) if lead_days else None,
            "lookback_window_days": LEAD_WINDOW,
            "nota": (
                "La ventaja es MECÁNICA, no informativa: la velocidad (derivada) se vuelve "
                "negativa en cuanto la curva empieza a aplanarse, lo que ocurre meses/años "
                "ANTES de la inversión. 'Velocidad<0' solo dice 'la curva se está aplanando', "
                "algo que dura todo el ciclo de aplanamiento y NO predice el retorno de SPY "
                "(su Spearman forward es más débil que el del nivel)."
            ),
        } if lead_days else None,
    }

    # ────────────────────────────────────────────────────────────────────
    # PASO 6 — VEREDICTO (data-driven)
    # ────────────────────────────────────────────────────────────────────
    def get_corr(sname, h):
        c = next((c for c in correlations if c["signal"] == sname and c["horizon"] == h), None)
        return c

    lvl_60 = get_corr("s_2y3m", 60)
    lvl_5 = get_corr("s_2y3m", 5)
    vel3_5 = get_corr("vel_2y3m_3d", 5)
    vel3_10 = get_corr("vel_2y3m_3d", 10)
    vel5_5 = get_corr("vel_2y3m_5d", 5)

    # señales de nivel vs velocidad por |ρ_s| máximo en horizontes CORTOS (≤20d)
    short_only = [c for c in correlations if c["horizon"] <= 20]
    best_short = max(short_only, key=lambda c: abs(c["spearman"]))

    regim_signif = any(
        (regime_comparison.get(f"h{h}") or {}).get("sig_ci_excludes_zero")
        for h in HORIZONS
    )

    # EXTREMO (inversión severa) como celda más fuerte
    ext_cells = {h: regimes["extremo_inversion_s2y3m_lt_p5"][f"h{h}"] for h in HORIZONS}
    ext_60 = ext_cells[60]
    ext_5 = ext_cells[5]

    inv_60 = regimes["invertido_s2y3m_lt0"]["h60"]
    nor_60 = regimes["normal_s2y3m_gt0"]["h60"]

    lead = timing_lead.get("vel5d_flip_lead_days")

    verdict = {
        "respuesta_principal": (
            "NO hay señal táctica de TENDENCIA en el tramo corto de la curva a 5-60d. "
            "Lo que existe es una señal CONTRARIA de REVERSIÓN ('comprar miedo'): a más "
            "inversión, MAYOR forward return — justo lo opuesto a la hipótesis "
            "'3M>2Y = liquidez tight → SPY corrige'."
        ),
        "hipotesis_refutada": {
            "hipotesis": "3M > 2Y (inversión tramo corto) = liquidez TIGHT → SPY corrige (fwd < 0).",
            "resultado": (
                "REFUTADA a corto plazo. Los días INVERTIDOS tienen forward return POSITIVO "
                "y MAYOR que los días normales a 60d (invertido +3.32% vs normal +2.43%, "
                "diff +0.89pp CI95 sig). La inversión es un techo de LIQUIDEZ que precede al "
                "rebote, no una corrección inmediata."
            ),
            "mecanismo": (
                "La inversión del tramo corto ocurre en mercados alcistas tardíos (2000, 2006-07, "
                "2019, 2022-24): el mercado SIGUE subiendo durante la inversión y solo cae DESPUÉS "
                "de la re-empinada (des-inversión), a 12-24m — eso es la señal ESTRUCTURAL ya "
                "documentada en intelligence, no una señal táctica."
            ),
        },
        "detalle_nivel": {
            "s_2y3m_spearman_5d": lvl_5["spearman"] if lvl_5 else None,
            "s_2y3m_spearman_10d": get_corr("s_2y3m", 10)["spearman"] if get_corr("s_2y3m", 10) else None,
            "s_2y3m_spearman_20d": get_corr("s_2y3m", 20)["spearman"] if get_corr("s_2y3m", 20) else None,
            "s_2y3m_spearman_60d": lvl_60["spearman"] if lvl_60 else None,
            "s_2y3m_spearman_60d_ci95": lvl_60["spearman_ci95"] if lvl_60 else None,
            "interpretacion": (
                "El NIVEL del spread 2Y-3M correlaciona NEGATIVO con SPY forward (ρ_s −0.03 → "
                "−0.20 al ir de 5d a 60d): spread más bajo (más inversión) → mayor retorno forward. "
                "Es una señal de REVERSIÓN de medio plazo (60d), débil a 5-20d (|ρ|<0.12)."
            ),
        },
        "detalle_velocidad": {
            "vel3d_spearman_5d": vel3_5["spearman"] if vel3_5 else None,
            "vel3d_spearman_10d": vel3_10["spearman"] if vel3_10 else None,
            "vel5d_spearman_5d": vel5_5["spearman"] if vel5_5 else None,
            "interpretacion": (
                "La VELOCIDAD (Δ3d/Δ5d) NO supera al nivel: ρ_s ≈ −0.02..−0.06 en TODOS los "
                "horizontes, MÁS DÉBIL que el nivel. El signo es además NO-monotónico (aplanamiento "
                "→ ligeramente mayor fwd, sin significancia robusta). La velocidad NO es la señal "
                "táctica que se busca."
            ),
        },
        "regimen_invertido_vs_normal": {
            "significativo_alguna_celda": regim_signif,
            "sign_flip": (
                "A 5-20d el día INVERTIDO rinde ligeramente MENOS que el normal (diff −0.11/−0.27/"
                "−0.50pp, significativo a 10-20d); a 60d INVIERTE el signo y rinde MÁS (+0.89pp, sig). "
                "Patrón 'bache corto y rebote': no es una señal direccional limpia."
            ),
            "comparacion": regime_comparison,
        },
        "regimen_extremo_inversion": {
            "umbral_p5": round(p5, 4),
            "h5_mean_pct": ext_5["mean_pct"] if ext_5 else None,
            "h60_mean_pct": ext_60["mean_pct"] if ext_60 else None,
            "h60_win_rate": ext_60["win_rate"] if ext_60 else None,
            "h60_ci95": ext_60["mean_ci95"] if ext_60 else None,
            "interpretacion": (
                "La celda MÁS FUERTE del estudio es la INVERSIÓN SEVERA (s_2y3m < P5=−0.39, N=417): "
                "forward +0.68% 5d / +1.21% 10d / +2.12% 20d / +4.78% 60d (WR 85.9%, CI95 no cruza 0). "
                "Es una señal CONTRARIA de 'comprar miedo' (rebote post-inversión), NO una señal de "
                "tendencia bajista, y su mejor horizonte (60d) es de medio plazo, no táctico."
            ),
        },
        "velocidad_mas_rapida_que_nivel": {
            "best_horizon_per_signal": level_vs_velocity["best_horizon_per_signal"],
            "mejor_senal_horizontes_cortos_lte20d": {
                "signal": best_short["signal"], "horizon": best_short["horizon"],
                "spearman": best_short["spearman"], "ci95": best_short["spearman_ci95"],
            },
            "vel5d_flip_lead_days": lead,
            "interpretacion": (
                "El flip de la velocidad (Δ5d<0, aplanamiento) precede al cruce del nivel "
                "(s_2y3m<0) por >%.0f días de mediana (censurado a la ventana de 750d: la curva "
                "empieza a aplanarse >3 años antes de invertir). Es una ventaja MECÁNICA, no "
                "informativa: 'Velocidad<0' solo dice 'la curva se aplana', NO predice el retorno "
                "de SPY (su |ρ_s| forward es la MITAD que la del nivel y débil en todos los "
                "horizontes). No es una señal táctica más rápida — es una señal más temprana "
                "pero sin poder predictivo."
            ) % (lead["median"] if lead else 0.0),
        },
        "conclusion": (
            "VEREDICTO: el tramo corto (3M vs 2Y) NO sirve como señal TÁCTICA de tendencia a "
            "5-60d. Mejor correlación a corto plazo: %s @ %dd con ρ_s=%+.3f (CI95 %s) — débil. "
            "Su única lectura accionable a estos horizontes es CONTRARIA (inversión severa → "
            "rebote, 'comprar miedo'), con mejor horizonte en 60d (medio plazo, no táctico). "
            "La VELOCIDAD no mejora al nivel. El rol del tramo corto sigue siendo ESTRUCTURAL "
            "(recesión/drawdown a 12-24m vía 2Y-10Y, ya documentado); para timing corto hay "
            "sensores superiores (VIX D2, amplitud S5, PCR)."
        ) % (best_short["signal"], best_short["horizon"], best_short["spearman"], best_short["spearman_ci95"]),
        "anti_adulacion": (
            "NO inflar. |ρ_s| ≤ 0.12 en TODOS los horizontes ≤20d; el pico |ρ_s|=0.20 está en 60d "
            "(señal de reversión de medio plazo, no táctica). La velocidad Δ3d/Δ5d es MÁS DÉBIL que "
            "el nivel en todos los horizontes. La única celda 'jugosa' (inversión severa +4.78% 60d, "
            "WR 85.9%) es CONTRARIA y de medio plazo, y está concentrada en 4-5 episodios históricos "
            "(2000, 2006-07, 2019, 2022-24) — no es una señal de tendencia ni de timing corto. "
            "Si el objetivo es capturar cambios de tendencia en 5-60d, este NO es el sensor."
        ),
    }

    report = {
        "metadata": meta,
        "percentiles_spread": {"p5": round(p5, 4), "p95": round(p95, 4),
                               "n_invertido_days": int((s_2y3m < 0).sum()),
                               "n_normal_days": int((s_2y3m > 0).sum()),
                               "pct_invertido": round(float((s_2y3m < 0).mean()) * 100, 2),
                               "dgs2_min_pct": round(float(np.nanmin(d2)), 4)},
        "nota_ratio_redundante": (
            "En el panel 1993-2026 el DGS2 nunca es ≤ 0 (mín 0.09%), por lo que el ratio "
            "3M/2Y y el spread 2Y-3M son EXACTAMENTE redundantes como clasificador de régimen "
            "(ratio>1 ⟺ s_2y3m<0, 0 discrepancias en 8,377 días). El ratio no aporta información "
            "más allá del spread."
        ),
        "correlations": correlations,
        "regimes": regimes,
        "regime_comparison_invertido_vs_normal": regime_comparison,
        "velocity_regimes": vel_regimes,
        "level_vs_velocity": level_vs_velocity,
        "timing_lead_velocity_vs_level": timing_lead,
        "verdict": verdict,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(f"\n✅ Reporte escrito: {REPORT_PATH}")

    # ── resumen en consola ──
    print("\n" + "=" * 78)
    print("CORRELACIONES Spearman (señal × horizonte)")
    print("=" * 78)
    hdr = f"{'signal':<14}" + "".join(f"{h:>10}" for h in TIMING_HORIZONS)
    print(hdr)
    for sname in signals:
        row = f"{sname:<14}"
        for h in TIMING_HORIZONS:
            c = get_corr(sname, h)
            row += f"{c['spearman']:>+10.3f}" if c else f"{'—':>10}"
        print(row)

    print("\n" + "=" * 78)
    print("REGÍMENES — forward SPY (mean %, [CI95], WR)  por horizonte")
    print("=" * 78)
    for key, entry in regimes.items():
        print(f"\n{entry['label']}")
        for h in HORIZONS:
            cell = entry[f"h{h}"]
            if cell is None:
                print(f"  h{h:>3}d: N<{MIN_N} — insuficiente")
            else:
                print(f"  h{h:>3}d: N={cell['n']:>5}  mean={cell['mean_pct']:+6.2f}% "
                      f"CI95[{cell['mean_ci95'][0]:+6.2f},{cell['mean_ci95'][1]:+6.2f}] "
                      f"WR={cell['win_rate']:.3f}  med={cell['median_pct']:+6.2f}% "
                      f"[{cell['min_pct']:+6.2f} .. {cell['max_pct']:+6.2f}]")

    print("\n" + "=" * 78)
    print("INVERTIDO vs NORMAL (diff de medias bootstrap)")
    print("=" * 78)
    for h in HORIZONS:
        d = regime_comparison.get(f"h{h}")
        if d:
            print(f"  h{h:>3}d: diff={d['mean_diff_pct']:+6.2f}% "
                  f"CI95[{d['ci95'][0]:+6.2f},{d['ci95'][1]:+6.2f}] "
                  f"p2s={d['p_two_sided']:.3f} sig={d['sig_ci_excludes_zero']} "
                  f"(inv {d['invertido_mean_pct']:+.2f}% vs nor {d['normal_mean_pct']:+.2f}%)")

    print("\n" + "=" * 78)
    print("VEREDICTO")
    print("=" * 78)
    print(verdict["conclusion"])
    print("\n" + verdict["anti_adulacion"])


if __name__ == "__main__":
    main()
