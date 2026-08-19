#!/usr/bin/env python3
"""
EXPERTO D2/D3 en DIVERGENCIA VIX×S5 — discriminación del forward return en 4 regímenes.
=====================================================================================

S5  = S5TW = price breadth (% acciones > 20-DMA)  → lo que el mercado HACE.
VIX = fear → lo que el mercado SIENTE.

4 REGÍMENES DE DIVERGENCIA (nivel de VIX × velocidad de S5):
  1. MIEDO SIN VENTA     : VIX↑ (>P66 nivel) + S5 mantiene   (ΔS5 ≥ −2pp)
  2. MIEDO CON VENTA     : VIX↑ (>P66 nivel) + S5 colapsa     (ΔS5 < −2pp)
  3. CALMA CON AMPLITUD  : VIX↓ (<P33 nivel) + S5 recupera    (ΔS5 ≥ +2pp)
  4. CALMA SIN CONVICCIÓN: VIX↓ (<P33 nivel) + S5 no reacciona (ΔS5 < +2pp)

PREGUNTA: dentro de cada régimen, ¿D2 (velocidad) y D3 (volatilidad) de VIX y S5
discriminan el forward return de SPY?

SPLITS dentro de cada régimen:
  - D2 de VIX : subiendo (Δ3d > +0.5) / bajando (Δ3d < −0.5) / estable (|Δ3d| ≤ 0.5)
  - D3 de VIX : comprimido (<P33) / normal (P33–P66) / expandido (>P66)
  - D2 de S5  : acelerando (Δ3d > 0) / decelerando (Δ3d < 0)

MÉTRICAS (por celda):
  - Horizontes fijos: SPY forward 5/10/20/40 días de trading.
  - Escalas zigzag: retorno del signal bar al próximo pivote zz25/zz50/zz75.
  - Stats: N, media, CI95 (bootstrap 3000), win rate + CI95, mediana,
    P25/P75/P90, min/max, profit factor, Kelly, wipeouts (>20%).

Dato mata relato — todo medido sobre datos reales del vault.
"""

import sys
import json
from pathlib import Path
from bisect import bisect_right

import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

# ── Config ─────────────────────────────────────────────────────────────────────
FW_HORIZONS = [5, 10, 20, 40]          # días de trading
ZZ_SCALES = ["zz25", "zz50", "zz75"]   # 2.5% / 5.0% / 7.5%
N_BOOT = 3000
BOOT_SEED = 42
VIX_D2_STABLE = 0.5                    # banda "estable" para D2 de VIX (pts VIX / 3d)
S5_COLLAPSE = -2.0                     # pp — S5 colapsa
S5_RECOVER = 2.0                       # pp — S5 recupera

REGIMES = [
    {"key": "MIEDO_SIN_VENTA",      "vix_cond": "up",   "s5_cond": "hold"},
    {"key": "MIEDO_CON_VENTA",      "vix_cond": "up",   "s5_cond": "collapse"},
    {"key": "CALMA_CON_AMPLITUD",   "vix_cond": "down", "s5_cond": "recover"},
    {"key": "CALMA_SIN_CONVICCION", "vix_cond": "down", "s5_cond": "flat"},
]

REGIME_LABEL = {
    "MIEDO_SIN_VENTA":      "MIEDO SIN VENTA (VIX↑ + S5 mantiene)",
    "MIEDO_CON_VENTA":      "MIEDO CON VENTA (VIX↑ + S5 colapsa)",
    "CALMA_CON_AMPLITUD":   "CALMA CON AMPLITUD (VIX↓ + S5 recupera)",
    "CALMA_SIN_CONVICCION": "CALMA SIN CONVICCIÓN (VIX↓ + S5 no reacciona)",
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def boot_ci(arr, ci=95, n_boot=N_BOOT, seed=BOOT_SEED, stat="mean"):
    """Bootstrap CI para media o win-rate de un array."""
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    n = len(arr)
    if n < 5:
        return float(np.nan), float(np.nan), float(np.nan), n
    rng = np.random.default_rng(seed)
    stats = np.empty(n_boot)
    for i in range(n_boot):
        s = rng.choice(arr, size=n, replace=True)
        stats[i] = s.mean() if stat == "mean" else (s > 0).mean()
    stats.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    point = arr.mean() if stat == "mean" else (arr > 0).mean()
    return float(point), float(np.percentile(stats, lo)), float(np.percentile(stats, hi)), n


def cell_stats(rets):
    """Stats completas de una celda de retornos (forward)."""
    arr = np.asarray(rets, float)
    arr = arr[~np.isnan(arr)]
    n = len(arr)
    if n < 5:
        return {"N": n, "insufficient": True}
    mean, m_lo, m_hi, _ = boot_ci(arr, stat="mean")
    wr, wr_lo, wr_hi, _ = boot_ci(arr, stat="winrate")
    wins = arr[arr > 0]
    losses = arr[arr <= 0]
    gross_win = wins.sum() if len(wins) else 0.0
    gross_loss = abs(losses.sum()) if len(losses) else 0.0
    pf = float(gross_win / gross_loss) if gross_loss > 0 else float("inf")
    avg_w = wins.mean() if len(wins) else 0.0
    avg_l = abs(losses.mean()) if len(losses) else 0.0
    wlr = avg_w / avg_l if avg_l > 0 else float("inf")
    kelly = wr - (1 - wr) / wlr if (avg_l > 0 and wlr > 0 and wlr != float("inf")) else float("nan")
    wipe = losses[losses < -0.20]
    return {
        "N": n,
        "mean": float(mean), "mean_ci95": [float(m_lo), float(m_hi)],
        "win_rate": float(wr), "win_rate_ci95": [float(wr_lo), float(wr_hi)],
        "median": float(np.median(arr)),
        "p25": float(np.percentile(arr, 25)), "p75": float(np.percentile(arr, 75)),
        "p90": float(np.percentile(arr, 90)),
        "min": float(arr.min()), "max": float(arr.max()),
        "wins": {"n": int(len(wins)), "median": float(np.median(wins)) if len(wins) else None,
                 "p90": float(np.percentile(wins, 90)) if len(wins) >= 10 else None,
                 "max": float(wins.max()) if len(wins) else None},
        "losses": {"n": int(len(losses)), "median": float(np.median(losses)) if len(losses) else None,
                   "min": float(losses.min()) if len(losses) else None,
                   "wipeouts_n": int(len(wipe)), "wipeouts_pct": float(len(wipe) / n * 100)},
        "profit_factor": pf,
        "kelly": float(kelly) if not np.isnan(kelly) else None,
        "ev": float(mean),
    }


def fmt_pct(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "     n/a"
    return f"{x*100:+7.2f}%"


def fmt_ci(lo, hi):
    if lo is None or (isinstance(lo, float) and np.isnan(lo)):
        return "            n/a"
    return f"[{lo*100:+5.1f},{hi*100:+5.1f}]"


# ── Load data ─────────────────────────────────────────────────────────────────

print("═" * 100)
print("  D2/D3 EN DIVERGENCIA VIX×S5 — 4 regímenes")
print("═" * 100)

store = TimescaleDataStore()
repo = ZigzagLegRepository(store)


def norm_series(bars):
    s = bars["close"].copy()
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s


vix = norm_series(store.load_bars("VIX", "1d"))
s5 = norm_series(store.load_bars("S5TW", "1d"))
spy = norm_series(store.load_bars("SPY", "1d"))

spy_dates = list(spy.index)
spy_vals = spy.values.astype(float)
spy_date_to_idx = {d: i for i, d in enumerate(spy_dates)}

# Alinear VIX y S5 a las fechas de SPY
common = sorted(set(vix.index) & set(s5.index) & set(spy.index))
df = pd.DataFrame(index=common)
df["vix"] = [float(vix.loc[d]) for d in common]
df["s5"] = [float(s5.loc[d]) for d in common]
df["spy"] = [float(spy.loc[d]) for d in common]

# D2 = diff(3d), D3 = std(2d)/std(10d) — pitfall #46
df["vix_d2"] = df["vix"].diff(3)
df["s5_d2"] = df["s5"].diff(3)
for name in ["vix", "s5"]:
    s2 = df[name].rolling(2).std()
    s10 = df[name].rolling(10).std()
    df[f"{name}_d3"] = (s2 / s10).replace([np.inf, -np.inf], np.nan).fillna(1.0)

# Percentiles globales (sobre historia alineada)
vix_p33 = df["vix"].quantile(0.33)
vix_p66 = df["vix"].quantile(0.66)
vix_d3_p33 = df["vix_d3"].quantile(0.33)
vix_d3_p66 = df["vix_d3"].quantile(0.66)

print(f"\n  Barras alineadas (VIX∩S5TW∩SPY): {len(df)}")
print(f"  Rango: {df.index[0].date()} → {df.index[-1].date()}")
print(f"  VIX nivel: P33={vix_p33:.2f}  P66={vix_p66:.2f}")
print(f"  VIX D3:    P33={vix_d3_p33:.3f}  P66={vix_d3_p66:.3f}")

# ── Clasificar regímenes ──────────────────────────────────────────────────────

vix_up = df["vix"] > vix_p66
vix_down = df["vix"] < vix_p33

regime_col = pd.Series("NEUTRAL", index=df.index, dtype=object)
regime_col[(vix_up) & (df["s5_d2"] >= S5_COLLAPSE)] = "MIEDO_SIN_VENTA"
regime_col[(vix_up) & (df["s5_d2"] < S5_COLLAPSE)] = "MIEDO_CON_VENTA"
regime_col[(vix_down) & (df["s5_d2"] >= S5_RECOVER)] = "CALMA_CON_AMPLITUD"
regime_col[(vix_down) & (df["s5_d2"] < S5_RECOVER)] = "CALMA_SIN_CONVICCION"
df["regime"] = regime_col

# Splits intra-régimen
df["vix_d2_split"] = np.where(df["vix_d2"] > VIX_D2_STABLE, "subiendo",
                     np.where(df["vix_d2"] < -VIX_D2_STABLE, "bajando", "estable"))
df["vix_d3_split"] = np.where(df["vix_d3"] > vix_d3_p66, "expandido",
                     np.where(df["vix_d3"] < vix_d3_p33, "comprimido", "normal"))
df["s5_d2_split"] = np.where(df["s5_d2"] > 0, "acelerando", "decelerando")

# ── Forward returns fijos ─────────────────────────────────────────────────────

spy_arr = df["spy"].values.astype(float)
for h in FW_HORIZONS:
    df[f"fwd_{h}d"] = np.nan
    df.iloc[:-h, df.columns.get_loc(f"fwd_{h}d")] = (spy_arr[h:] / spy_arr[:-h] - 1.0)

# ── Forward returns zigzag (signal bar → próximo pivote) ──────────────────────

def build_zz_lookup(scale):
    """Para cada fecha de SPY, retorno del signal bar al cierre de la pierna activa."""
    legs = repo.get_confirmed_legs("SPY", scale)
    starts = []
    end_prices = []
    for l in legs:
        s_ts = pd.to_datetime(l.start_timestamp).tz_localize(None).normalize()
        e_ts = pd.to_datetime(l.end_timestamp).tz_localize(None).normalize()
        starts.append((s_ts, e_ts, float(l.end_price)))
    starts.sort(key=lambda x: x[0])
    start_ts = [x[0] for x in starts]
    out = {}
    for d in common:
        i = bisect_right(start_ts, d) - 1
        if i < 0:
            out[d] = np.nan
            continue
        s_ts, e_ts, e_px = starts[i]
        if e_ts < d:  # hueco (no debería pasar en un zigzag limpio)
            out[d] = np.nan
            continue
        spx = float(df.loc[d, "spy"])
        out[d] = e_px / spx - 1.0
    return out

zz_returns = {}
for sc in ZZ_SCALES:
    zz_returns[sc] = build_zz_lookup(sc)
    df[f"zz_{sc}"] = [zz_returns[sc].get(d, np.nan) for d in common]

print(f"\n  Lookups zigzag construidos. Columnas forward: "
      f"{[f'fwd_{h}d' for h in FW_HORIZONS] + [f'zz_{sc}' for sc in ZZ_SCALES]}")

store.close()

# ── Análisis ──────────────────────────────────────────────────────────────────

OUTCOMES = [f"fwd_{h}d" for h in FW_HORIZONS] + [f"zz_{sc}" for sc in ZZ_SCALES]
OUTCOME_LABEL = {**{f"fwd_{h}d": f"{h}d" for h in FW_HORIZONS},
                 **{f"zz_{sc}": sc for sc in ZZ_SCALES}}

SPLITS = [
    {"name": "D2 VIX", "col": "vix_d2_split", "groups": ["subiendo", "estable", "bajando"],
     "labels": {"subiendo": "D2 VIX subiendo", "estable": "D2 VIX estable", "bajando": "D2 VIX bajando"}},
    {"name": "D3 VIX", "col": "vix_d3_split", "groups": ["comprimido", "normal", "expandido"],
     "labels": {"comprimido": "D3 VIX comprimido", "normal": "D3 VIX normal", "expandido": "D3 VIX expandido"}},
    {"name": "D2 S5", "col": "s5_d2_split", "groups": ["acelerando", "decelerando"],
     "labels": {"acelerando": "D2 S5 acelerando", "decelerando": "D2 S5 decelerando"}},
]


def boot_gap(arr_a, arr_b, ci=95, n_boot=N_BOOT, seed=BOOT_SEED):
    """Bootstrap CI para la diferencia de medias A − B."""
    a = np.asarray(arr_a, float); b = np.asarray(arr_b, float)
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    if len(a) < 5 or len(b) < 5:
        return float(np.nan), float(np.nan), float(np.nan)
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        diffs[i] = rng.choice(a, len(a), replace=True).mean() - rng.choice(b, len(b), replace=True).mean()
    diffs.sort()
    lo = (100 - ci) / 2; hi = 100 - lo
    return float(a.mean() - b.mean()), float(np.percentile(diffs, lo)), float(np.percentile(diffs, hi))


full_report = {"meta": {
    "script": "research/04_conjuncion_multi_estacion/s5_vix_d2d3.py",
    "vix_level_p33": float(vix_p33), "vix_level_p66": float(vix_p66),
    "vix_d3_p33": float(vix_d3_p33), "vix_d3_p66": float(vix_d3_p66),
    "s5_collapse_pp": S5_COLLAPSE, "s5_recover_pp": S5_RECOVER,
    "vix_d2_stable_band": VIX_D2_STABLE,
    "n_bars": int(len(df)),
    "outcomes": OUTCOMES,
    "bootstrap": f"{N_BOOT} iter, CI95",
    "zigzag_return_definition": "retorno del signal bar al cierre de la pierna activa (próximo pivote) en cada escala",
}, "regimes": {}}

for reg in REGIMES:
    rkey = reg["key"]
    sub = df[df["regime"] == rkey]
    n_reg = len(sub)
    print(f"\n{'═' * 100}")
    print(f"  {REGIME_LABEL[rkey]}   —   N = {n_reg}")
    print(f"{'═' * 100}")

    reg_report = {"label": REGIME_LABEL[rkey], "N": int(n_reg), "splits": {}}

    if n_reg < 10:
        print("  N < 10 — insuficiente.")
        full_report["regimes"][rkey] = reg_report
        continue

    # ── Baseline ──
    print(f"\n  BASELINE (todo el régimen, N={n_reg}):")
    reg_report["baseline"] = {}
    for oc in OUTCOMES:
        cs = cell_stats(sub[oc].values)
        reg_report["baseline"][OUTCOME_LABEL[oc]] = cs
        if cs.get("insufficient"):
            continue
        print(f"    {OUTCOME_LABEL[oc]:>5}: mean={fmt_pct(cs['mean'])}  CI95={fmt_ci(*cs['mean_ci95'])}  "
              f"WR={cs['win_rate']*100:5.1f}%  N={cs['N']:>4}  PF={cs['profit_factor']:>5.2f}")

    # ── Splits ──
    for split in SPLITS:
        print(f"\n  ── SPLIT POR {split['name']} ──")
        sp_report = {"name": split["name"], "groups": {}}
        group_means = {}  # outcome -> {group: mean}
        for g in split["groups"]:
            sub_g = sub[sub[split["col"]] == g]
            n_g = len(sub_g)
            sp_report["groups"][g] = {"N": int(n_g)}
            if n_g < 5:
                print(f"    {split['labels'][g]:<24}: N={n_g} (insuficiente)")
                continue
            line = f"    {split['labels'][g]:<24}: N={n_g:>4}  "
            for oc in OUTCOMES:
                cs = cell_stats(sub_g[oc].values)
                sp_report["groups"][g][OUTCOME_LABEL[oc]] = cs
                group_means.setdefault(OUTCOME_LABEL[oc], {})[g] = (sub_g[oc].dropna(), cs)
                line += f"| {OUTCOME_LABEL[oc]}:{fmt_pct(cs['mean'])} "
            print(line)
        # Discriminación: gap max−min por outcome
        sp_report["discrimination"] = {}
        for oc_label in [OUTCOME_LABEL[oc] for oc in OUTCOMES]:
            gm = group_means.get(oc_label, {})
            means = {g: gm[g][1]["mean"] for g in gm if not gm[g][1].get("insufficient")}
            if len(means) < 2:
                continue
            gmax = max(means, key=means.get)
            gmin = min(means, key=means.get)
            arr_max = gm[gmax][0]; arr_min = gm[gmin][0]
            gap, gap_lo, gap_hi = boot_gap(arr_max, arr_min)
            sp_report["discrimination"][oc_label] = {
                "max_group": gmax, "min_group": gmin, "gap": gap, "gap_ci95": [gap_lo, gap_hi],
                "max_mean": means[gmax], "min_mean": means[gmin],
            }
        reg_report["splits"][split["name"]] = sp_report

    full_report["regimes"][rkey] = reg_report


# ── Resumen de discriminación (gaps significativos) ───────────────────────────

print(f"\n{'═' * 100}")
print("  RESUMEN DE DISCRIMINACIÓN — gap (max−min) con CI95 bootstrap")
print("═" * 100)
for rkey in [r["key"] for r in REGIMES]:
    reg_report = full_report["regimes"].get(rkey, {})
    for split in SPLITS:
        sp = reg_report.get("splits", {}).get(split["name"], {})
        disc = sp.get("discrimination", {})
        for oc_label, d in disc.items():
            sig = "✅" if (d["gap_ci95"][0] > 0 or d["gap_ci95"][1] < 0) else "  "
            print(f"  {rkey:<24} {split['name']:<8} {oc_label:>5}: gap={fmt_pct(d['gap'])} "
                  f"CI95={fmt_ci(*d['gap_ci95'])}  ({d['max_group']} > {d['min_group']}) {sig}")

# ── Guardar JSON ──────────────────────────────────────────────────────────────

out_path = Path("/root/botero-trade/data/research/s5_vix_d2d3_report.json")
with open(out_path, "w") as f:
    json.dump(full_report, f, indent=2, default=lambda x: float(x) if isinstance(x, (np.floating, np.integer)) else str(x))

print(f"\n  Reporte JSON guardado: {out_path}")
print("═" * 100)
print("  FIN")
print("═" * 100)
