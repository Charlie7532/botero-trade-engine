#!/usr/bin/env python3
"""
CONJUNCIÓN BSI × SV5T — par natural de amplitud (precio × volumen)
==================================================================
BSI  = S5TW            = amplitud de PRECIO (% stocks sobre MA20)
       → D1 extremo: BREADTH_WASHED_OUT (edge < 11.0)
SV5T = SV5_TURBULENCE  = turbulencia de VOLUMEN (std del cambio de volume breadth)
       → D1 extremo: CRISIS_TURBULENCE (edge >= 17.34)

Preguntas:
  1. Correlación BSI vs SV5T (raw + diffs)
  2. Conjunción: ambos en extremo → forward SPY 20d, win rate, CI95, N
  3. ¿Complementarios (precio+volumen) o redundantes?
  4. ¿La conjunción reduce wipeouts vs BSI solo?
  5. Recomendar: ¿usar juntos o separados?

Metodología (v2 — entrada en barra de señal, NO pivote zigzag):
  - Entrada: barra donde D1 = extremo (clasificado con adapters del fact store)
  - Salida: forward SPY a 5/10/20/40d trading
  - Dedup: >= 10 trading days entre señales
  - D2 = diff(3d), D3 = std(2d)/std(10d)  [pitfall #46]
  - CI95 bootstrap 2000 iter

Dato mata relato. Nada de supuestos — todo medido.
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
from backend.modules.entry_decision.domain.rules.bsi_lookup import BSILookupAdapter
from backend.modules.entry_decision.domain.rules.sv5_turbulence_lookup import SV5TurbulenceLookupAdapter

# ─── Config ─────────────────────────────────────────────────────────────────
FW_HORIZONS = [5, 10, 20, 40]
N_BOOT = 2000
SEED = 42
MIN_SIGNAL_SPACING = 10   # trading days between signals
WIPEOUT_THRESHOLD = -0.20  # -20% forward return = wipeout

BSI_EXTREME = "BREADTH_WASHED_OUT"
SV5T_EXTREME = "CRISIS_TURBULENCE"

# ─── Helpers ─────────────────────────────────────────────────────────────────

def boot_ci(arr, ci=95, n_boot=N_BOOT, seed=SEED):
    """CI95 for mean via bootstrap."""
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


def boot_ci_proportion(wins_bool, ci=95, n_boot=N_BOOT, seed=SEED):
    """CI95 for win rate (proportion) via bootstrap."""
    arr = np.asarray(wins_bool, float)
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


def boot_ci_diff(mean_a, mean_b, ci=95, n_boot=N_BOOT, seed=SEED):
    """Bootstrap CI95 for the DIFFERENCE of two means (paired-independent approximation).
    Uses the difference of independent bootstrap resamples of each distribution.
    Returns (diff, lo, hi, p_positive)."""
    a = np.asarray(mean_a, float)
    b = np.asarray(mean_b, float)
    a = a[~np.isnan(a)]
    b = b[~np.isnan(b)]
    if len(a) < 3 or len(b) < 3:
        return np.nan, np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        da = rng.choice(a, size=len(a), replace=True).mean()
        db = rng.choice(b, size=len(b), replace=True).mean()
        diffs[i] = da - db
    diffs.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    p_pos = float(np.mean(diffs > 0))
    return float(a.mean() - b.mean()), float(np.percentile(diffs, lo)), float(np.percentile(diffs, hi)), p_pos


def compute_d2_d3(series):
    """D2 = diff(3d), D3 = std(2d)/std(10d). Pitfall #46."""
    d2 = series.diff(3)
    s2 = series.rolling(2).std()
    s10 = series.rolling(10).std()
    d3 = (s2 / s10).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    return d2, d3


def kelly_fraction(wr, avg_win, avg_loss):
    if avg_loss <= 0:
        return float('inf')
    wl = avg_win / avg_loss
    if wl <= 0:
        return 0.0
    f = wr - (1 - wr) / wl
    return max(0.0, f)


# ─── Load Data ───────────────────────────────────────────────────────────────
print("═══ CARGANDO DATOS ═══")
store = TimescaleDataStore()

# SPY
spy_raw = store.load_bars("SPY", "1d")["close"].copy()
spy_raw.index = pd.to_datetime(spy_raw.index).normalize()
spy = spy_raw[~spy_raw.index.duplicated(keep="last")].sort_index()
spy_dates = list(spy.index)
spy_values = spy.values
spy_date_to_idx = {d: i for i, d in enumerate(spy_dates)}
print(f"  SPY: {spy_dates[0].date()} → {spy_dates[-1].date()} ({len(spy)} bars)")


def load_ticker(ticker):
    raw = store.load_bars(ticker, "1d")["close"].copy()
    raw.index = pd.to_datetime(raw.index).normalize()
    s = raw[~raw.index.duplicated(keep="last")].sort_index()
    return s

s5tw = load_ticker("S5TW")
sv5t_raw = load_ticker("SV5_TURBULENCE")
print(f"  S5TW: {s5tw.index[0].date()} → {s5tw.index[-1].date()} ({len(s5tw)} bars)")
print(f"  SV5_TURBULENCE: {sv5t_raw.index[0].date()} → {sv5t_raw.index[-1].date()} ({len(sv5t_raw)} bars)")

# Align all three on common dates
common = sorted(set(s5tw.index) & set(sv5t_raw.index) & set(spy.index))
s5tw_a = pd.Series([float(s5tw.loc[d]) for d in common], index=common)
sv5t_a = pd.Series([float(sv5t_raw.loc[d]) for d in common], index=common)
print(f"  Fechas alineadas (S5TW ∩ SV5T ∩ SPY): {len(common)}")

store.close()

# D2 / D3
bsi_d2, bsi_d3 = compute_d2_d3(s5tw_a)
sv5t_d2, sv5t_d3 = compute_d2_d3(sv5t_a)

# ─── 1. CORRELACIÓN BSI vs SV5T (raw + diffs) ───────────────────────────────
print("\n\n" + "═" * 90)
print("  1. CORRELACIÓN BSI (S5TW) vs SV5T (SV5_TURBULENCE)")
print("═" * 90)

# Raw (levels)
raw_pearson = float(np.corrcoef(s5tw_a.values, sv5t_a.values)[0, 1])
raw_spearman = float(pd.Series(s5tw_a.values).corr(pd.Series(sv5t_a.values), method="spearman"))

# Diffs (daily change and D2 velocity)
d1_bsi = s5tw_a.diff(1)
d1_sv5t = sv5t_a.diff(1)
d1_pearson = float(np.corrcoef(d1_bsi.dropna().values, d1_sv5t.dropna().values)[0, 1])

# D2 velocity (diff 3d) — the project's velocity dimension
valid_d2 = ~(bsi_d2.isna() | sv5t_d2.isna())
d2_pearson = float(np.corrcoef(bsi_d2[valid_d2].values, sv5t_d2[valid_d2].values)[0, 1])
d2_spearman = float(pd.Series(bsi_d2[valid_d2].values).corr(pd.Series(sv5t_d2[valid_d2].values), method="spearman"))

print(f"  Raw (niveles):          Pearson = {raw_pearson:+.3f}   Spearman = {raw_spearman:+.3f}")
print(f"  Diff 1d (cambio diario): Pearson = {d1_pearson:+.3f}")
print(f"  D2 velocity (diff 3d):   Pearson = {d2_pearson:+.3f}   Spearman = {d2_spearman:+.3f}")

# ─── Classify every bar with adapters ───────────────────────────────────────
bsi_adapter = BSILookupAdapter()
sv5t_adapter = SV5TurbulenceLookupAdapter()

bar_classification = []  # per-date D1 bins
for i, dt in enumerate(common):
    bsi_val = float(s5tw_a.loc[dt])
    sv5t_val = float(sv5t_a.loc[dt])
    b_vel = float(bsi_d2.loc[dt]) if not pd.isna(bsi_d2.loc[dt]) else 0.0
    b_vol = float(bsi_d3.loc[dt]) if not pd.isna(bsi_d3.loc[dt]) else 1.0
    s_vel = float(sv5t_d2.loc[dt]) if not pd.isna(sv5t_d2.loc[dt]) else 0.0
    s_vol = float(sv5t_d3.loc[dt]) if not pd.isna(sv5t_d3.loc[dt]) else 1.0

    try:
        bg = bsi_adapter.lookup_bsi_guidance(val=bsi_val, d3_speed=b_vel, vol_norm=b_vol)
    except Exception:
        bg = None
    try:
        sg = sv5t_adapter.lookup_sv5_turbulence_guidance(val=sv5t_val, d3_speed=s_vel, vol_norm=s_vol)
    except Exception:
        sg = None

    bsi_d1 = bg.state_key.split("__")[0] if bg else None
    sv5t_d1 = sg.state_key.split("__")[0] if sg else None
    bsi_d2_bin = bg.state_key.split("__")[1] if bg and "__" in bg.state_key else "?"
    sv5t_d2_bin = sg.state_key.split("__")[1] if sg and "__" in sg.state_key else "?"

    bar_classification.append({
        "date": dt,
        "spy_idx": spy_date_to_idx.get(dt),
        "bsi_val": bsi_val,
        "sv5t_val": sv5t_val,
        "bsi_d2": b_vel,
        "sv5t_d2": s_vel,
        "bsi_d1": bsi_d1,
        "sv5t_d1": sv5t_d1,
        "bsi_d2_bin": bsi_d2_bin,
        "sv5t_d2_bin": sv5t_d2_bin,
    })

bars = pd.DataFrame(bar_classification).dropna(subset=["spy_idx"])
bars["spy_idx"] = bars["spy_idx"].astype(int)
bars = bars.sort_values("spy_idx").reset_index(drop=True)

# ─── D1 distribution + contingency (complementariedad) ─────────────────────
print("\n\n" + "═" * 90)
print("  2. DISTRIBUCIÓN D1 Y CONTINGENCIA (¿se solapan los extremos?)")
print("═" * 90)

n_bsi_ext = int((bars["bsi_d1"] == BSI_EXTREME).sum())
n_sv5t_ext = int((bars["sv5t_d1"] == SV5T_EXTREME).sum())
n_both_ext = int(((bars["bsi_d1"] == BSI_EXTREME) & (bars["sv5t_d1"] == SV5T_EXTREME)).sum())
n_total = len(bars)

print(f"  Total barras alineadas: {n_total}")
print(f"  BSI extremo (BREADTH_WASHED_OUT):  {n_bsi_ext}  ({n_bsi_ext/n_total*100:.1f}%)")
print(f"  SV5T extremo (CRISIS_TURBULENCE):  {n_sv5t_ext}  ({n_sv5t_ext/n_total*100:.1f}%)")
print(f"  CONJUNCIÓN (ambos extremo):        {n_both_ext}  ({n_both_ext/n_total*100:.1f}%)")
if n_bsi_ext > 0:
    print(f"  % de días BSI-extremo que también son SV5T-extremo: {n_both_ext/n_bsi_ext*100:.1f}%")
if n_sv5t_ext > 0:
    print(f"  % de días SV5T-extremo que también son BSI-extremo: {n_both_ext/n_sv5t_ext*100:.1f}%")

# Expected overlap under independence (for complementarity judgment)
p_bsi = n_bsi_ext / n_total
p_sv5t = n_sv5t_ext / n_total
expected_both = p_bsi * p_sv5t * n_total
print(f"\n  Bajo independencia, esperaríamos {expected_both:.1f} días de conjunción; observamos {n_both_ext}.")
print(f"  Ratio observado/esperado = {n_both_ext/expected_both:.2f}×" if expected_both > 0 else "  (esperado ~0)")

# ─── Build signals (dedup) ──────────────────────────────────────────────────
def build_signals(mask_bool, min_spacing=MIN_SIGNAL_SPACING):
    """Given a boolean mask over `bars`, build deduped signal list with forward returns."""
    idxs = bars.index[mask_bool].tolist()
    if not idxs:
        return []
    deduped_idx = []
    last_spy_idx = -min_spacing - 1
    for bi in idxs:
        row = bars.loc[bi]
        si = int(row["spy_idx"])
        if si - last_spy_idx >= min_spacing:
            deduped_idx.append(bi)
            last_spy_idx = si

    signals = []
    for bi in deduped_idx:
        row = bars.loc[bi]
        entry_idx = int(row["spy_idx"])
        entry_price = spy_values[entry_idx]
        fwd = {}
        for h in FW_HORIZONS:
            fi = entry_idx + h
            fwd[h] = (spy_values[fi] / entry_price - 1.0) if fi < len(spy_values) else None
        signals.append({
            "date": row["date"],
            "spy_idx": entry_idx,
            "bsi_d1": row["bsi_d1"],
            "sv5t_d1": row["sv5t_d1"],
            "bsi_d2_bin": row["bsi_d2_bin"],
            "sv5t_d2_bin": row["sv5t_d2_bin"],
            "fwd": fwd,
        })
    return signals


mask_bsi = bars["bsi_d1"] == BSI_EXTREME
mask_sv5t = bars["sv5t_d1"] == SV5T_EXTREME
mask_both = mask_bsi & mask_sv5t

signals_bsi = build_signals(mask_bsi)
signals_sv5t = build_signals(mask_sv5t)
signals_both = build_signals(mask_both)

print("\n\n" + "═" * 90)
print("  3. SEÑALES DEDUP (>= 10 días de separación)")
print("═" * 90)
print(f"  BSI solo:     {len(signals_bsi)} señales")
print(f"  SV5T solo:    {len(signals_sv5t)} señales")
print(f"  CONJUNCIÓN:   {len(signals_both)} señales")


# ─── Analysis ───────────────────────────────────────────────────────────────
def analyze(signals, label):
    """Full metrics for a signal list at every horizon."""
    if len(signals) < 3:
        return {"label": label, "N": len(signals), "insufficient": True}

    R = {"label": label, "N": len(signals)}
    for h in FW_HORIZONS:
        arr = np.array([s["fwd"][h] for s in signals if s["fwd"][h] is not None])
        if len(arr) < 3:
            R[h] = None
            continue
        wins = arr > 0
        losses = arr[arr <= 0]
        wr, wr_lo, wr_hi = boot_ci_proportion(wins)
        ev, ev_lo, ev_hi = boot_ci(arr)
        gross_win = arr[arr > 0].sum()
        gross_loss = abs(arr[arr <= 0].sum())
        pf = gross_win / gross_loss if gross_loss > 0 else float('inf')
        avg_w = arr[arr > 0].mean() if (arr > 0).any() else 0.0
        avg_l = abs(arr[arr <= 0].mean()) if (arr <= 0).any() else 0.0
        wipeouts = arr[arr <= WIPEOUT_THRESHOLD]
        R[h] = {
            "N": len(arr),
            "wr": wr, "wr_ci95": [wr_lo, wr_hi],
            "ev": ev, "ev_ci95": [ev_lo, ev_hi],
            "median": float(np.median(arr)),
            "win_mean": float(avg_w),
            "loss_mean": float(avg_l),
            "min": float(arr.min()),
            "max": float(arr.max()),
            "pf": float(pf),
            "kelly": float(kelly_fraction(wr, avg_w, avg_l)) if avg_l > 0 else None,
            "wipeouts_n": int(len(wipeouts)),
            "wipeouts_pct": float(len(wipeouts) / len(arr) * 100),
            "wipeouts_vals": [float(v) for v in wipeouts],
        }
    return R


res_bsi = analyze(signals_bsi, "BSI solo (BREADTH_WASHED_OUT)")
res_sv5t = analyze(signals_sv5t, "SV5T solo (CRISIS_TURBULENCE)")
res_both = analyze(signals_both, "CONJUNCIÓN BSI×SV5T")

# ─── Print results ──────────────────────────────────────────────────────────
def print_block(res, title):
    print(f"\n{'─'*90}")
    print(f"  {title}  (N={res.get('N')})")
    print(f"{'─'*90}")
    if res.get("insufficient"):
        print("  INSUFICIENTE (<3)")
        return
    print(f"  {'H':>4} │ {'WR':>7} {'CI95':>22} │ {'EV':>8} {'EV CI95':>24} │ {'Med':>8} {'Min':>8} {'Max':>8} │ {'PF':>6} {'Kelly':>7} │ {'Wipe>20%':>9}")
    print(f"  {'─'*4}─┼─{'─'*7}─{'─'*22}─┼─{'─'*8}─{'─'*24}─┼─{'─'*8}─{'─'*8}─{'─'*8}─┼─{'─'*6}─{'─'*7}─┼─{'─'*9}")
    for h in FW_HORIZONS:
        d = res.get(h)
        if not d:
            continue
        wr = f"{d['wr']*100:.0f}%"
        ci = f"[{d['wr_ci95'][0]*100:.0f}%,{d['wr_ci95'][1]*100:.0f}%]"
        ev = f"{d['ev']*100:+.2f}%"
        evci = f"[{d['ev_ci95'][0]*100:+.1f}%,{d['ev_ci95'][1]*100:+.1f}%]"
        med = f"{d['median']*100:+.2f}%"
        mn = f"{d['min']*100:+.2f}%"
        mx = f"{d['max']*100:+.2f}%"
        pf = f"{d['pf']:.2f}" if d['pf'] != float('inf') else "∞"
        kl = f"{d['kelly']*100:.0f}%" if d['kelly'] is not None and d['kelly'] != float('inf') else "∞"
        wipe = f"{d['wipeouts_n']} ({d['wipeouts_pct']:.0f}%)"
        print(f"  {f'{h}d':>4} │ {wr:>7} {ci:>22} │ {ev:>8} {evci:>24} │ {med:>8} {mn:>8} {mx:>8} │ {pf:>6} {kl:>7} │ {wipe:>9}")
    # wipeout detail at 20d
    d20 = res.get(20)
    if d20 and d20["wipeouts_n"] > 0:
        print(f"\n  WIPEOUTS 20d: {[f'{v*100:.1f}%' for v in d20['wipeouts_vals']]}")


print("\n\n" + "═" * 90)
print("  4. RESULTADOS — FORWARD SPY")
print("═" * 90)
print_block(res_bsi, "BSI SOLO")
print_block(res_sv5t, "SV5T SOLO")
print_block(res_both, "CONJUNCIÓN BSI × SV5T")

# ─── 5. Conjunción vs BSI solo (diferencia, bootstrap) ─────────────────────
print("\n\n" + "═" * 90)
print("  5. ¿LA CONJUNCIÓN MEJORA vs BSI SOLO? (bootstrap diff de medias)")
print("═" * 90)

if len(signals_both) >= 3 and len(signals_bsi) >= 3:
    for h in FW_HORIZONS:
        a = np.array([s["fwd"][h] for s in signals_bsi if s["fwd"][h] is not None])
        b = np.array([s["fwd"][h] for s in signals_both if s["fwd"][h] is not None])
        if len(a) < 3 or len(b) < 3:
            continue
        diff, lo, hi, p_pos = boot_ci_diff(b, a)  # b - a: conjunción - BSI solo
        wr_a = np.mean(a > 0)
        wr_b = np.mean(b > 0)
        wipe_a = np.mean(a <= WIPEOUT_THRESHOLD) * 100
        wipe_b = np.mean(b <= WIPEOUT_THRESHOLD) * 100
        print(f"\n  {h}d:")
        print(f"    EV  BSI={np.mean(a)*100:+.2f}%  CONJ={np.mean(b)*100:+.2f}%  ΔEV={diff*100:+.2f}%  CI95=[{lo*100:+.1f}%,{hi*100:+.1f}%]  P(Δ>0)={p_pos*100:.1f}%")
        print(f"    WR  BSI={wr_a*100:.0f}%  CONJ={wr_b*100:.0f}%")
        print(f"    Wipe>20%  BSI={wipe_a:.1f}%  CONJ={wipe_b:.1f}%")

# ─── 6. ¿Reduce wipeouts? ───────────────────────────────────────────────────
print("\n\n" + "═" * 90)
print("  6. WIPEOUTS (pérdida forward > 20%) — comparación directa")
print("═" * 90)
for h in FW_HORIZONS:
    for name, res in [("BSI solo", res_bsi), ("SV5T solo", res_sv5t), ("CONJUNCIÓN", res_both)]:
        d = res.get(h) if not res.get("insufficient") else None
        if not d:
            print(f"  {h}d {name}: N/A")
            continue
        print(f"  {h}d {name:<12}: N={d['N']:>3}  wipeouts={d['wipeouts_n']} ({d['wipeouts_pct']:.1f}%)  min={d['min']*100:.1f}%  losses={[f'{v*100:.1f}%' for v in d['wipeouts_vals']]}")
    print()

# ─── Save JSON ──────────────────────────────────────────────────────────────
def ser(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if np.isnan(obj) else float(obj)
    if isinstance(obj, np.ndarray):
        return [ser(x) for x in obj]
    if isinstance(obj, list):
        return [ser(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): ser(v) for k, v in obj.items()}
    if isinstance(obj, tuple):
        return [ser(x) for x in obj]
    if isinstance(obj, (pd.Timestamp,)):
        return str(obj.date())
    return obj

report = {
    "correlation": {
        "raw_pearson": raw_pearson,
        "raw_spearman": raw_spearman,
        "diff1d_pearson": d1_pearson,
        "d2_pearson": d2_pearson,
        "d2_spearman": d2_spearman,
    },
    "contingency": {
        "n_total_bars": n_total,
        "n_bsi_extreme": n_bsi_ext,
        "n_sv5t_extreme": n_sv5t_ext,
        "n_both_extreme": n_both_ext,
        "pct_bsi_also_sv5t": n_both_ext / n_bsi_ext * 100 if n_bsi_ext else None,
        "pct_sv5t_also_bsi": n_both_ext / n_sv5t_ext * 100 if n_sv5t_ext else None,
        "expected_overlap_indep": expected_both,
        "ratio_obs_exp": n_both_ext / expected_both if expected_both > 0 else None,
    },
    "signals": {
        "bsi_only": res_bsi,
        "sv5t_only": res_sv5t,
        "conjunction": res_both,
        "n_bsi": len(signals_bsi),
        "n_sv5t": len(signals_sv5t),
        "n_both": len(signals_both),
    },
    "conjunction_dates": [str(s["date"].date()) for s in signals_both],
}

out = ROOT / "data/research/stations/bsi_sv5t_conjuncion_report.json"
with open(out, "w") as f:
    json.dump(ser(report), f, indent=2, default=str)
print(f"\n\nReporte guardado en: {out}")
print("DONE.")
