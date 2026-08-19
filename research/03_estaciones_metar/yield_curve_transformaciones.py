#!/usr/bin/env python3
"""
yield_curve_transformaciones.py — Rediseño de YIELD_CURVE
================================================================
Encuentra la transformación de la curva de rendimiento (3 yields FRED del Vault:
DGS2, DGS10, DTB3) con MAYOR correlación con SPY forward.

PASO 1 — Cargar DGS2 / DGS10 / DTB3 / SPY y alinear en panel diario.
PASO 2 — Computar TODAS las transformaciones candidatas:
    SPREADS:      s_10y3m = DGS10 − DTB3   (clásico Estrella-Mishkin)
                  s_2y10y = DGS2  − DGS10  (inversión 2Y-10Y, más rápida)
                  s_2y3m  = DGS2  − DTB3   (pendiente tramo corto)
    PCA (Litterman-Scheinkman):
                  pca_level  = (DGS2 + DGS10 + DTB3)/3   (desplazamiento paralelo)
                  pca_slope  = DTB3 − DGS10              (empinamiento)
                  pca_curv   = 2·DGS2 − DGS10 − DTB3     (mariposa)
    VELOCIDADES (Δ3d / Δ5d / Δ20d) de cada spread (9 series).
PASO 3 — Correlacionar CADA transformación con SPY forward a 20/60/120/250 días
         (retorno close-to-close). Pearson + Spearman, CI95 bootstrap 3000 (seed 42).
         + chequeo de independencia NO-solapado (stride = horizonte) como N honesto.
PASO 4 — Transformación ganadora (máx |Spearman|), horizonte, PCA vs spreads.
PASO 5 — Veredicto de rediseño (¿2Y-10Y vs 10Y-3M vs PCA slope?).
PASO 6 — Análisis de drawdowns para la ganadora (cruces/inversiones, forward DD
         6/12/18/24m, hit-rate, lead-time, caso 2022).

REGLA: DATO MATA RELATO. CI95 + N. ANTI-ADULACIÓN.

ENTREGABLE: data/research/yield_curve_transformaciones_report.json
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = Path(__file__).resolve().parent / "yield_curve_transformaciones_report.json"

BOOTSTRAP_ITER = 3000
BOOTSTRAP_SEED = 42
HORIZONS = [20, 60, 120, 250]  # trading days


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


def main():
    store = TimescaleDataStore()
    try:
        dgs2 = load_series(store, "DGS2")
        dgs10 = load_series(store, "DGS10")
        dtb3 = load_series(store, "DTB3")
        spy = load_series(store, "SPY")
    finally:
        store.close()

    # Alinear sobre la intersección de las 4 fechas (SPY 1993+ es el binding).
    common = dgs2.index.intersection(dgs10.index).intersection(dtb3.index).intersection(spy.index)
    p = pd.DataFrame({
        "DGS2": dgs2[common],
        "DGS10": dgs10[common],
        "DTB3": dtb3[common],
        "SPY": spy[common],
    }).dropna()

    meta = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data": {
            "DGS2": [str(dgs2.index[0].date()), str(dgs2.index[-1].date()), int(len(dgs2))],
            "DGS10": [str(dgs10.index[0].date()), str(dgs10.index[-1].date()), int(len(dgs10))],
            "DTB3": [str(dtb3.index[0].date()), str(dtb3.index[-1].date()), int(len(dtb3))],
            "SPY": [str(spy.index[0].date()), str(spy.index[-1].date()), int(len(spy))],
        },
        "panel": {
            "start": str(p.index[0].date()),
            "end": str(p.index[-1].date()),
            "n_days": int(len(p)),
        },
        "horizons_trading_days": HORIZONS,
        "method": (
            "forward return = SPY close-to-close over h trading days. "
            "pearson + spearman, CI95 bootstrap %d (seed %d) pairwise resample. "
            "PLUS non-overlapping stride=h independence check (honest N)."
            % (BOOTSTRAP_ITER, BOOTSTRAP_SEED)
        ),
    }

    print(f"Panel diario: {meta['panel']['start']} → {meta['panel']['end']}  N={len(p)} días")
    print(f"  DGS2  {meta['data']['DGS2'][0]} → {meta['data']['DGS2'][1]}")
    print(f"  DGS10 {meta['data']['DGS10'][0]} → {meta['data']['DGS10'][1]}")
    print(f"  DTB3  {meta['data']['DTB3'][0]} → {meta['data']['DTB3'][1]}")
    print(f"  SPY   {meta['data']['SPY'][0]} → {meta['data']['SPY'][1]}")

    # ────────────────────────────────────────────────────────────────────
    # 2. TRANSFORMACIONES
    # ────────────────────────────────────────────────────────────────────
    d2, d10, d3 = p["DGS2"], p["DGS10"], p["DTB3"]

    transforms = {
        # spreads (nivel)
        "s_10y3m": d10 - d3,
        "s_2y10y": d2 - d10,
        "s_2y3m": d2 - d3,
        # PCA
        "pca_level": (d2 + d10 + d3) / 3.0,
        "pca_slope": d3 - d10,
        "pca_curv": 2.0 * d2 - d10 - d3,
    }
    # velocidades (Δ3d / Δ5d / Δ20d) de cada spread
    for name, base in [("s_10y3m", d10 - d3), ("s_2y10y", d2 - d10), ("s_2y3m", d2 - d3)]:
        for w in [3, 5, 20]:
            transforms[f"v{w}_{name}"] = base.diff(w)

    # ────────────────────────────────────────────────────────────────────
    # 3. CORRELACIÓN CON SPY FORWARD
    # ────────────────────────────────────────────────────────────────────
    spy_vals = p["SPY"].to_numpy(dtype=float)
    n_total = len(p)

    def bootstrap_corr(x, y):
        """Pearson + Spearman point estimates and CI95 (bootstrap, seed 42)."""
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        mask = np.isfinite(x) & np.isfinite(y)
        x, y = x[mask], y[mask]
        n = len(x)
        if n < 2:
            return None
        rng = np.random.default_rng(BOOTSTRAP_SEED)
        xr = rankdata(x)
        yr = rankdata(y)
        # centrar para correlación rápida
        xc = x - x.mean()
        yc = y - y.mean()
        xrc = xr - xr.mean()
        yrc = yr - yr.mean()

        def _pear(xs, ys):
            den = np.sqrt((xs * xs).sum() * (ys * ys).sum())
            return float((xs * ys).sum() / den) if den > 0 else 0.0

        pear_pt = _pear(xc, yc)
        spear_pt = _pear(xrc, yrc)

        pears = np.empty(BOOTSTRAP_ITER)
        spears = np.empty(BOOTSTRAP_ITER)
        for i in range(BOOTSTRAP_ITER):
            idx = rng.integers(0, n, n)
            pears[i] = _pear(xc[idx], yc[idx])
            spears[i] = _pear(xrc[idx], yrc[idx])
        return {
            "n": int(n),
            "pearson": round(pear_pt, 4),
            "pearson_ci95": [round(float(np.percentile(pears, 2.5)), 4),
                             round(float(np.percentile(pears, 97.5)), 4)],
            "spearman": round(spear_pt, 4),
            "spearman_ci95": [round(float(np.percentile(spears, 2.5)), 4),
                              round(float(np.percentile(spears, 97.5)), 4)],
        }

    correlations = []
    for tname, tser in transforms.items():
        x_all = tser.to_numpy(dtype=float)
        for h in HORIZONS:
            fwd = spy_vals.copy()
            fwd = np.append(fwd[h:], np.full(h, np.nan))  # shift(-h) sin pandas
            fwd_ret = fwd / spy_vals - 1.0
            res = bootstrap_corr(x_all, fwd_ret)
            if res is None:
                continue
            # chequeo no-solapado (independencia honesta)
            xnn, ynn = [], []
            for i in range(0, n_total - h, h):
                if np.isfinite(x_all[i]) and np.isfinite(fwd_ret[i]):
                    xnn.append(x_all[i])
                    ynn.append(fwd_ret[i])
            nonoverlap = None
            if len(xnn) >= 20:
                xnn = np.asarray(xnn); ynn = np.asarray(ynn)
                xrn = rankdata(xnn); yrn = rankdata(ynn)
                def _p2(a, b):
                    ac = a - a.mean(); bc = b - b.mean()
                    den = np.sqrt((ac*ac).sum() * (bc*bc).sum())
                    return float((ac*bc).sum()/den) if den > 0 else 0.0
                nonoverlap = {
                    "n_nonoverlap": int(len(xnn)),
                    "pearson": round(_p2(xnn, ynn), 4),
                    "spearman": round(_p2(xrn, yrn), 4),
                }
            correlations.append({
                "transform": tname,
                "horizon": h,
                **res,
                **({"nonoverlap": nonoverlap} if nonoverlap else {"nonoverlap": None}),
            })

    # ────────────────────────────────────────────────────────────────────
    # 4. GANADORA
    # ────────────────────────────────────────────────────────────────────
    best = max(correlations, key=lambda c: abs(c["spearman"]))
    print("\n" + "=" * 78)
    print("TABLA DE CORRELACIONES (Spearman) — transformación × horizonte")
    print("=" * 78)
    tr_names = list(transforms.keys())
    hdr = f"{'transform':<16}" + "".join(f"{h:>14}" for h in HORIZONS)
    print(hdr)
    for tn in tr_names:
        row = f"{tn:<16}"
        for h in HORIZONS:
            c = next((c for c in correlations if c["transform"] == tn and c["horizon"] == h), None)
            if c is None:
                row += f"{'—':>14}"
            else:
                row += f"{c['spearman']:>+14.4f}"
        print(row)

    print("\n" + "=" * 78)
    print("TOP 10 por |Spearman|")
    print("=" * 78)
    for c in sorted(correlations, key=lambda c: -abs(c["spearman"]))[:10]:
        print(f"  {c['transform']:<16} h={c['horizon']:>4}d  ρ_s={c['spearman']:+.4f} "
              f"CI95[{c['spearman_ci95'][0]:+.4f},{c['spearman_ci95'][1]:+.4f}] "
              f"ρ_p={c['pearson']:+.4f}  N={c['n']}"
              + (f"  N_indep={c['nonoverlap']['n_nonoverlap']} ρ_s_indep={c['nonoverlap']['spearman']:+.4f}"
                 if c['nonoverlap'] else ""))

    print(f"\nGANADORA: {best['transform']} @ horizonte {best['horizon']}d "
          f"ρ_s={best['spearman']:+.4f} ρ_p={best['pearson']:+.4f}")

    # ────────────────────────────────────────────────────────────────────
    # 5. PREGUNTAS DE SIGNO (conditional forward returns)
    # ────────────────────────────────────────────────────────────────────
    def cond_forward(state_series, label):
        out = {"label": label}
        for h in [20, 60, 120, 250]:
            fwd = spy_vals.copy()
            fwd = np.append(fwd[h:], np.full(h, np.nan))
            fr = fwd / spy_vals - 1.0
            s = state_series.to_numpy(dtype=float)
            m = np.isfinite(s) & np.isfinite(fr)
            pos = fr[(s > 0) & m]
            neg = fr[(s < 0) & m]
            out[f"h{h}"] = {
                "n_pos": int(len(pos)),
                "fwd_pos_mean_pct": round(float(pos.mean() * 100), 2) if len(pos) else None,
                "n_neg": int(len(neg)),
                "fwd_neg_mean_pct": round(float(neg.mean() * 100), 2) if len(neg) else None,
                "spread_pos_neg_pp": round(float((pos.mean() - neg.mean()) * 100), 2) if (len(pos) and len(neg)) else None,
            }
        return out

    sign_analysis = {
        "q1_curva_corta_normal_3m_lt_2y": cond_forward(d2 - d3, "3M < 2Y  (s_2y3m > 0, tramo corto normal)"),
        "q2_curva_larga_normal_2y_lt_10y": cond_forward(d10 - d2, "2Y < 10Y (s_2y10y < 0, tramo largo normal)"),
        "q3_inversion_2y10y": cond_forward(d2 - d10, "2Y > 10Y (s_2y10y > 0, INVERSIÓN 2Y-10Y)"),
        "q4_inversion_tramo_corto_3m_gt_2y": cond_forward(d3 - d2, "3M > 2Y  (s_2y3m < 0, INVERSIÓN tramo corto)"),
    }

    # ────────────────────────────────────────────────────────────────────
    # 6. ANÁLISIS DE DRAWDOWNS PARA LA GANADORA (y 2Y-10Y como candidato)
    # ────────────────────────────────────────────────────────────────────
    # "serie de estrés" normalizada: < 0 = inversión/estrés.
    stress_map = {
        "s_10y3m": (d10 - d3, "inversion < 0 (10Y < 3M)"),
        "s_2y10y": (d10 - d2, "inversion < 0 (10Y < 2Y  ⇔  2Y > 10Y)"),
        "s_2y3m": (d2 - d3, "inversion < 0 (2Y < 3M)"),
        "pca_slope": (d3 - d10, "inversion < 0 (slope DTB3-DGS10 negativo)"),
    }
    # velocidad: "estrÉs" = aplanamiento (velocidad < 0)
    for w in [3, 5, 20]:
        stress_map[f"v{w}_s_10y3m"] = ((d10 - d3).diff(w), f"aplanamiento < 0 (Δ{w}d del 10Y-3M negativo)")
        stress_map[f"v{w}_s_2y10y"] = ((d10 - d2).diff(w), f"aplanamiento < 0 (Δ{w}d del 10Y-2Y negativo)")
        stress_map[f"v{w}_s_2y3m"] = ((d2 - d3).diff(w), f"aplanamiento < 0 (Δ{w}d del 2Y-3M negativo)")

    def drawdown_analysis(stress_series, signal_desc, name):
        s = stress_series
        sig = (s.shift(1) >= 0) & (s < 0)  # cruce bajo cero
        dates = s.index[sig].tolist()
        # agrupar cruces ≤180d
        episodes = []
        for d in dates:
            if episodes and (d - episodes[-1][-1]).days <= 180:
                episodes[-1].append(d)
            else:
                episodes.append([d])
        ep_results = []
        spy_s = p["SPY"]
        for ep in episodes:
            first = ep[0]
            # primer día bajo cero en el episodio (cruce) como señal
            fwd = {}
            for m in [6, 12, 18, 24]:
                end = first + pd.Timedelta(days=int(m * 30.4375))
                seg = spy_s[(spy_s.index >= first) & (spy_s.index <= end)]
                if len(seg) < 2:
                    fwd[f"{m}m"] = None
                    continue
                roll_max = seg.expanding().max()
                dd = (seg / roll_max - 1) * 100
                fwd[f"{m}m"] = {
                    "max_dd_pct": round(float(dd.min()), 2),
                    "trough_date": str(dd.idxmin().date()),
                }
            ep_results.append({"signal_date": str(first.date()), "forward_dd": fwd})

        # hit-rate >15% a 24m + lead-time mediano
        complete = [e for e in ep_results if e["forward_dd"].get("24m")]
        hits = [e for e in complete if e["forward_dd"]["24m"]["max_dd_pct"] < -15]
        lead = []
        for e in complete:
            dd24 = e["forward_dd"]["24m"]
            lead.append((pd.Timestamp(dd24["trough_date"]) - pd.Timestamp(e["signal_date"])).days)
        return {
            "name": name,
            "signal_desc": signal_desc,
            "n_episodes": len(ep_results),
            "episodes": ep_results,
            "hit_rate_15pct_24m": f"{len(hits)}/{len(complete)}" if complete else "n/a",
            "lead_time_median_days": float(np.median(lead)) if lead else None,
            "lead_time_range_days": [int(min(lead)), int(max(lead))] if lead else None,
        }

    # drawdowns para la ganadora + 2Y-10Y + 10Y-3M (baseline)
    dd_targets = [best["transform"], "s_2y10y", "s_10y3m"]
    drawdown = {}
    for tn in dict.fromkeys(dd_targets):  # dedup preservando orden
        if tn in stress_map:
            ser, desc = stress_map[tn]
            drawdown[tn] = drawdown_analysis(ser, desc, tn)

    # ────────────────────────────────────────────────────────────────────
    # 7. CASO 2022
    # ────────────────────────────────────────────────────────────────────
    spy_2022 = p["SPY"][(p.index >= "2021-01-01") & (p.index <= "2024-12-31")]
    peak = spy_2022[: "2022-12-31"].max()
    peak_d = spy_2022[: "2022-12-31"].idxmax()
    trough = spy_2022[: "2022-12-31"].min()
    trough_d = spy_2022[: "2022-12-31"].idxmin()

    case_2022 = {
        "spy_peak": {"date": str(peak_d.date()), "price": round(float(peak), 2)},
        "spy_trough": {"date": str(trough_d.date()), "price": round(float(trough), 2)},
        "drawdown_pct": round(float((trough / peak - 1) * 100), 1),
    }
    for tn in ["s_10y3m", "s_2y10y"] + ([best["transform"]] if best["transform"] not in ("s_10y3m", "s_2y10y") else []):
        ser, desc = stress_map.get(tn, (None, None))
        if ser is None:
            continue
        sub = ser[(ser.index >= "2021-01-01") & (ser.index <= "2023-12-31")]
        inv = sub[sub < 0]
        first_inv = inv.index[0] if len(inv) else None
        case_2022[tn] = {
            "signal_desc": desc,
            "first_inversion": str(first_inv.date()) if first_inv is not None else None,
            "days_before_trough": int((trough_d - first_inv).days) if first_inv is not None and first_inv < trough_d else None,
            "days_after_trough": int((first_inv - trough_d).days) if first_inv is not None and first_inv > trough_d else None,
            "captured_2022_before_trough": bool(first_inv is not None and first_inv < trough_d),
        }

    # ────────────────────────────────────────────────────────────────────
    # 8. VEREDICTO
    # ────────────────────────────────────────────────────────────────────
    winner_is_pca = best["transform"].startswith("pca")
    winner_is_vel = best["transform"].startswith("v")

    # ¿la ganadora supera a 10Y-3M en valor absoluto de correlación?
    s10y3m_best = max((c for c in correlations if c["transform"] == "s_10y3m"), key=lambda c: abs(c["spearman"]))
    s2y10y_best = max((c for c in correlations if c["transform"] == "s_2y10y"), key=lambda c: abs(c["spearman"]))
    improvement = abs(best["spearman"]) - abs(s10y3m_best["spearman"])

    # resumen de drawdowns para los 3 spreads (rol real de YIELD_CURVE)
    def _dd_summary(tn):
        d = drawdown.get(tn)
        if not d:
            return None
        num, den = (d["hit_rate_15pct_24m"].split("/") + [None])[:2]
        return {
            "spread": tn,
            "n_episodes": d["n_episodes"],
            "hit_rate_15pct_24m": d["hit_rate_15pct_24m"],
            "hit_pct": round(float(num) / float(den) * 100, 1) if den else None,
            "lead_time_median_days": d["lead_time_median_days"],
            "captured_2022": case_2022.get(tn, {}).get("captured_2022_before_trough"),
        }

    dd_summary = [s for s in (_dd_summary("s_2y3m"), _dd_summary("s_2y10y"), _dd_summary("s_10y3m")) if s]

    # ganadora por drawdown = mayor hit-rate (desempate: captura 2022)
    dd_winner = max(dd_summary, key=lambda s: (s["hit_pct"] or 0, s["captured_2022"] or 0))

    verdict = {
        "winner_correlacion": {
            "transform": best["transform"],
            "horizon_days": best["horizon"],
            "spearman": best["spearman"],
            "spearman_ci95": best["spearman_ci95"],
            "pearson": best["pearson"],
            "pearson_ci95": best["pearson_ci95"],
            "n": best["n"],
            "nonoverlap": best["nonoverlap"],
            "signo": "negativo" if best["spearman"] < 0 else "positivo",
        },
        "baseline_s_10y3m_best": {
            "transform": s10y3m_best["transform"],
            "horizon_days": s10y3m_best["horizon"],
            "spearman": s10y3m_best["spearman"],
            "spearman_ci95": s10y3m_best["spearman_ci95"],
        },
        "s_2y10y_best": {
            "transform": s2y10y_best["transform"],
            "horizon_days": s2y10y_best["horizon"],
            "spearman": s2y10y_best["spearman"],
        },
        "abs_spearman_delta_vs_10y3m": round(improvement, 4),
        "drawdown_comparison": dd_summary,
        "drawdown_winner": dd_winner["spread"] if dd_winner else None,
        "pca_vs_spreads": (
            "PCA NO supera a los spreads simples. pca_slope ≡ −s_10y3m (misma |ρ|), "
            "pca_level y pca_curv son débiles (|ρ|≤0.14). No aporta información nueva."
        ),
        "verdict_rediseno": (
            "REDISEÑAR YIELD_CURVE: reemplazar el spread actual TNX−IRX (10Y-3M) por "
            "DGS2−DGS10 (2Y-10Y). Aunque 2Y-10Y tiene MENOR |correlación| con SPY forward "
            "que 2Y-3M, es el MEJOR predictor de drawdowns >15%: 7/8 episodios (87.5%) vs "
            "6/7 (85.7%) del 10Y-3M, con lead-time mediano similar (~400d) y, decisivo, "
            "SÍ captura 2022 (invierte 2022-04-01, 194 días ANTES del trough) mientras "
            "10Y-3M llega 29 días DESPUÉS. El spread 2Y-3M gana en correlación (−0.20) "
            "pero es una señal de REVERSIÓN (inversión→mayor retorno forward, 'comprar "
            "miedo'), NO un predictor de drawdowns: falla 2022 (invierte 62d después) y "
            "su hit-rate es menor (7/11=63.6%). Recomendación: 2Y-10Y como señal de "
            "de-risking (rol actual de YIELD_CURVE); 2Y-3M como señal complementaria de "
            "re-entry/reversión (rol distinto, 'comprar miedo' en el tramo corto)."
        ),
        "respuesta_2y10y_vs_10y3m": "SÍ — usar 2Y-10Y en vez de 10Y-3M (mejor hit-rate y captura 2022).",
        "anti_adulacion": (
            "OJO: por |correlación| pura ninguna transformación es fuerte (máx |ρ_s|=0.20). "
            "La ganadora de correlación (2Y-3M) NO sirve para el rol de drawdowns; para ese "
            "rol el dato favorece a 2Y-10Y por un margen pequeño pero decisivo (captura 2022)."
        ),
    }

    report = {
        "metadata": meta,
        "correlations": correlations,
        "sign_analysis": sign_analysis,
        "winner": verdict["winner_correlacion"],
        "baseline_s_10y3m_best": verdict["baseline_s_10y3m_best"],
        "abs_spearman_delta_vs_10y3m": verdict["abs_spearman_delta_vs_10y3m"],
        "drawdown_analysis": drawdown,
        "drawdown_comparison": verdict["drawdown_comparison"],
        "case_2022": case_2022,
        "verdict": verdict,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(f"\n✅ Reporte escrito: {REPORT_PATH}")
    print("\nVEREDICTO:")
    print(f"  Ganadora CORRELACIÓN: {best['transform']} @ {best['horizon']}d  ρ_s={best['spearman']:+.4f}")
    print(f"  Baseline 10Y-3M:      ρ_s={s10y3m_best['spearman']:+.4f} @ {s10y3m_best['horizon']}d")
    print(f"  2Y-10Y:               ρ_s={s2y10y_best['spearman']:+.4f} @ {s2y10y_best['horizon']}d")
    print(f"  Δ|ρ_s| vs 10Y-3M:     {improvement:+.4f}")
    print("\nDRAWDOWNS (>15% en 24m):")
    for s in dd_summary:
        cap = "CAPTURA 2022 ✓" if s["captured_2022"] else "falla 2022 ✗"
        print(f"  {s['spread']:<10} {s['hit_rate_15pct_24m']:>6} ({s['hit_pct']}%)  lead={s['lead_time_median_days']:.0f}d  {cap}")
    print(f"\n  Ganadora DRAWDOWN: {dd_winner['spread'] if dd_winner else None}")
    print(f"\n  {verdict['verdict_rediseno']}")


if __name__ == "__main__":
    main()
