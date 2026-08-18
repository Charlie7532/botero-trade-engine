#!/usr/bin/env python3
"""
D2 (VELOCIDAD Δ3d) — QUÉ SIGNIFICA en cada una de las 11 estaciones.
=====================================================================
D2(t) = diff(3) del indicador = close(t) - close(t-3)  → ¿hacia dónde y con qué velocidad?

Para CADA estación:
  A) D2 vs SPY día a día (lead/lag) — ¿anticipa o confirma el movimiento de SPY?
        ρ(D2_t, SPY ret_forward 1d/3d/5d)  → anticipación
        ρ(D2_t, SPY ret_backward 1d/3d/5d) → confirmación
  B) D2 vs tríada zigzag (en pivotes zz25):
        ρ(D2, cascade_50), ρ(D2, cascade_75), ρ(D2, leg_bear)
  C) Percentiles accionables: D2 en tercil alto vs bajo → retorno SPY 5d, cascade rate, %bear.

Reporta ρ (Spearman), p-value nominal, N por estación.
"""
import sys, json
from pathlib import Path
from datetime import timedelta

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

# ── 11 estaciones (ticker autorizado por STATION_CONFIG) ───────────────────
STATION_CONFIG = {
    "vix":            {"ticker": "VIX",            "signo": "miedo opciones (↑ = miedo)"},
    "vvix":           {"ticker": "VVIX",           "signo": "volatilidad del VIX (↑ = miedo agudo)"},
    "pcr":            {"ticker": "CBOE_PCR",       "signo": "posicionamiento put/call (↑ = miedo)"},
    "fg":             {"ticker": "FG",             "signo": "sentimiento CNN (↑ = greed)"},
    "sv5_turbulence": {"ticker": "SV5_TURBULENCE", "signo": "turbulencia/volumen de batalla (↑ = caos)"},
    "skew":           {"ticker": "SKEW",           "signo": "pared gamma/cola (↑ = miedo cola)"},
    "credit":         {"ticker": "CREDIT_RATIO",   "signo": "HYG/LQD (↑ = risk-on)"},
    "yield_curve":    {"ticker": "YIELD_SPREAD",   "signo": "10Y-3M (↑ = steepening)"},
    "rotation":       {"ticker": "ROTATION_INDEX", "signo": "liderazgo sectorial (↑ = risk-on)"},
    "bsi":            {"ticker": "S5TW",           "signo": "amplitud S5TW (↑ = amplitud mejorando)"},
    "dxy":            {"ticker": "DXY",            "signo": "dólar (↑ = dólar fuerte)"},
}
# BSI alterno (decay_check usa S5FI, no S5TW)
BSI_ALT = {"ticker": "S5FI"}

FORWARD = [1, 3, 5]
BACKWARD = [1, 3, 5]


def ic(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    m = ~np.isnan(a) & ~np.isnan(b)
    if m.sum() < 10 or np.std(a[m]) == 0 or np.std(b[m]) == 0:
        return np.nan, np.nan, int(m.sum())
    r, p = spearmanr(a[m], b[m])
    return (float(r) if not np.isnan(r) else np.nan), float(p), int(m.sum())


def main():
    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)

    def _naive_idx(s):
        s = s.copy()
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        return s[~s.index.duplicated(keep="last")].sort_index()

    # ── SPY daily series ────────────────────────────────────────────────
    spy = _naive_idx(store.load_bars("SPY", "1d")["close"])

    ind = {}
    for code, cfg in STATION_CONFIG.items():
        s = store.load_bars(cfg["ticker"], "1d")["close"].copy()
        ind[code] = _naive_idx(s)
    # BSI alt
    s_alt = store.load_bars(BSI_ALT["ticker"], "1d")["close"].copy()
    ind["bsi_s5fi"] = _naive_idx(s_alt)

    # ── Zigzag legs ─────────────────────────────────────────────────────
    def _naive(ts):
        """Normalize to tz-naive date."""
        t = pd.to_datetime(ts)
        if t.tz is not None:
            t = t.tz_localize(None)
        return t

    legs25 = sorted(repo.get_confirmed_legs("SPY", "zz25"), key=lambda l: l.start_timestamp)
    legs50 = repo.get_confirmed_legs("SPY", "zz50")
    legs75 = repo.get_confirmed_legs("SPY", "zz75")
    starts50 = set([_naive(l.start_timestamp).date() for l in legs50])
    starts75 = set([_naive(l.start_timestamp).date() for l in legs75])

    df = pd.DataFrame([
        {"start_timestamp": _naive(l.start_timestamp), "start_type": l.start_type,
         "prev_leg_return": l.prev_leg_return}
        for l in legs25
    ])
    df["pivot_date"] = df["start_timestamp"].dt.date
    df["leg_bear"] = (df["start_type"] == "MAX").astype(int)  # leg que ARRANCA en MAX → bajista
    df["cascade_50"] = df["pivot_date"].apply(
        lambda d: int(any(d + timedelta(days=i) in starts50 for i in range(-3, 4))))
    df["cascade_75"] = df["pivot_date"].apply(
        lambda d: int(any(d + timedelta(days=i) in starts75 for i in range(-3, 4))))
    df = df.dropna(subset=["prev_leg_return"]).reset_index(drop=True)

    store.close()

    # ════════════════════════════════════════════════════════════════════
    # PARTE A — D2 vs SPY día a día (lead/lag)
    # ════════════════════════════════════════════════════════════════════
    print("═" * 100)
    print("  PARTE A — D2 vs SPY día a día (¿anticipa o confirma?)")
    print("  ρ(D2_t, SPY_forward) = anticipación (D2 → SPY futuro)")
    print("  ρ(D2_t, SPY_backward) = confirmación (SPY pasado → D2)")
    print("═" * 100)

    results_a = {}
    for code, cfg in STATION_CONFIG.items():
        s = ind[code]
        d2 = s.diff(3)
        # SPY returns
        fwd = {}
        for k in FORWARD:
            fwd[k] = spy.pct_change(k).shift(-k)
        bwd = {}
        for k in BACKWARD:
            bwd[k] = spy.pct_change(k)

        # Align on common dates
        common = d2.index.intersection(spy.index)
        d2a = d2.reindex(common)
        row = {}
        for k in FORWARD:
            r, p, n = ic(d2a, fwd[k].reindex(common))
            row[f"fwd{k}"] = (r, p, n)
        for k in BACKWARD:
            r, p, n = ic(d2a, bwd[k].reindex(common))
            row[f"bwd{k}"] = (r, p, n)
        results_a[code] = row

        # Interpretation: sign of fwd3
        f3 = row["fwd3"][0]
        b3 = row["bwd3"][0]
        if not np.isnan(f3) and not np.isnan(b3):
            if abs(f3) > abs(b3):
                role = "ANTICIPA" if abs(f3) > 0.05 else "anticipa (débil)"
            else:
                role = "CONFIRMA" if abs(b3) > 0.05 else "confirma (débil)"
        else:
            role = "n/a"

        print(f"\n  {code:<14} [{cfg['signo']}]  → {role}")
        line_f = "    forward:  " + "  ".join(f"1d={row[f'fwd{k}'][0]:+.4f}(N={row[f'fwd{k}'][2]})" if not np.isnan(row[f'fwd{k}'][0]) else f"1d= n/a" for k in FORWARD)
        line_b = "    backward: " + "  ".join(f"1d={row[f'bwd{k}'][0]:+.4f}(N={row[f'bwd{k}'][2]})" if not np.isnan(row[f'bwd{k}'][0]) else f"1d= n/a" for k in BACKWARD)
        # rewrite cleanly
        fparts = []
        for k in FORWARD:
            r, p, n = row[f"fwd{k}"]
            if np.isnan(r):
                fparts.append(f"{k}d= n/a")
            else:
                fparts.append(f"{k}d={r:+.4f}(p={p:.2g},N={n})")
        bparts = []
        for k in BACKWARD:
            r, p, n = row[f"bwd{k}"]
            if np.isnan(r):
                bparts.append(f"{k}d= n/a")
            else:
                bparts.append(f"{k}d={r:+.4f}(p={p:.2g},N={n})")
        print("    forward  (D2→SPY futuro): " + "  ".join(fparts))
        print("    backward (SPY pasado→D2): " + "  ".join(bparts))

    # ════════════════════════════════════════════════════════════════════
    # PARTE B — D2 vs tríada zigzag (cascade) + dirección leg
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "═" * 100)
    print("  PARTE B — D2 vs tríada zigzag (en pivotes zz25)")
    print("  cascade_50/75 = el pivote desencadena un zz50/zz75 (±3 días)")
    print("  leg_bear      = el leg que arranca en el pivote es bajista")
    print("═" * 100)
    print(f"  N pivotes zz25 = {len(df)}")
    print(f"\n  {'station':<14}{'ρ(D2,c50)':>12}{'p':>9}{'ρ(D2,c75)':>12}{'p':>9}{'ρ(D2,bear)':>12}{'p':>9}{'N':>6}")

    results_b = {}
    for code in list(STATION_CONFIG.keys()) + ["bsi_s5fi"]:
        s = ind[code]
        d2_series = s.diff(3).dropna()
        d2_asof = d2_series.sort_index()

        # lookup D2 at pivot date using asof
        vals = []
        for _, prow in df.iterrows():
            pdt = pd.Timestamp(prow["pivot_date"])
            # asof returns NaN if no value <= pdt
            v = d2_asof.asof(pdt)
            vals.append(float(v) if not pd.isna(v) else np.nan)
        d2_pivot = pd.Series(vals, index=df.index)

        r50, p50, n50 = ic(d2_pivot, df["cascade_50"])
        r75, p75, n75 = ic(d2_pivot, df["cascade_75"])
        rb, pb, nb = ic(d2_pivot, df["leg_bear"])
        results_b[code] = {"c50": (r50, p50, n50), "c75": (r75, p75, n75), "bear": (rb, pb, nb)}
        def fmt(t):
            r, p, n = t
            return f"n/a" if np.isnan(r) else f"{r:+.4f}"
        def fmtp(t):
            r, p, n = t
            return f"n/a" if np.isnan(r) else f"{p:.2g}"
        print(f"  {code:<14}{fmt((r50,p50,n50)):>12}{fmtp((r50,p50,n50)):>9}{fmt((r75,p75,n75)):>12}{fmtp((r75,p75,n75)):>9}{fmt((rb,pb,nb)):>12}{fmtp((rb,pb,nb)):>9}{n50:>6}")

    # ════════════════════════════════════════════════════════════════════
    # PARTE C — Percentiles accionables (tercil bajo vs alto de D2)
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "═" * 100)
    print("  PARTE C — D2 en tercil BAJO vs ALTO  →  retorno SPY 5d futuro, cascade_50, %bear")
    print("═" * 100)
    print(f"  {'station':<14}{'SPY5d|D2↓':>12}{'SPY5d|D2↑':>12}{'c50|D2↓':>10}{'c50|D2↑':>10}{'bear|D2↓':>10}{'bear|D2↑':>10}")

    for code in list(STATION_CONFIG.keys()) + ["bsi_s5fi"]:
        s = ind[code]
        d2 = s.diff(3).dropna()
        common = d2.index.intersection(spy.index)
        d2a = d2.reindex(common)
        fwd5 = spy.pct_change(5).shift(-5).reindex(common)
        lo = d2a <= d2a.quantile(0.33)
        hi = d2a >= d2a.quantile(0.67)
        def m(series, mask):
            v = series[mask].dropna()
            return v.mean() if len(v) > 5 else np.nan
        s5_lo = m(fwd5, lo); s5_hi = m(fwd5, hi)
        # cascade / bear at pivot for D2 tercile
        qlo, qhi = d2a.quantile(0.33), d2a.quantile(0.67)
        pv = pd.Series([d2a.asof(pd.Timestamp(d)) for d in df["pivot_date"]], index=df.index)
        plo = pv <= qlo; phi = pv >= qhi
        c50_lo = df.loc[plo, "cascade_50"].mean() if plo.sum() > 5 else np.nan
        c50_hi = df.loc[phi, "cascade_50"].mean() if phi.sum() > 5 else np.nan
        b_lo = df.loc[plo, "leg_bear"].mean() if plo.sum() > 5 else np.nan
        b_hi = df.loc[phi, "leg_bear"].mean() if phi.sum() > 5 else np.nan
        def pf(x):
            return f"n/a" if (x is None or (isinstance(x, float) and np.isnan(x))) else f"{x:+.2%}"
        print(f"  {code:<14}{pf(s5_lo):>12}{pf(s5_hi):>12}{pf(c50_lo):>10}{pf(c50_hi):>10}{pf(b_lo):>10}{pf(b_hi):>10}")

    # Dump JSON
    out = {"partA": {}, "partB": {}}
    for code, row in results_a.items():
        out["partA"][code] = {k: {"rho": v[0], "p": v[1], "N": v[2]} for k, v in row.items()}
    for code, row in results_b.items():
        out["partB"][code] = {k: {"rho": v[0], "p": v[1], "N": v[2]} for k, v in row.items()}
    with open(ROOT / "scratch" / "d2_significado_results.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("\n[guardado] scratch/d2_significado_results.json")


if __name__ == "__main__":
    main()
