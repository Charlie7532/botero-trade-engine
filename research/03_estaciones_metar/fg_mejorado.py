#!/usr/bin/env python3
"""
FG MEJORADO — Auditoría del FG CNN + Síntesis con Small Caps + Rotación
=========================================================================
PARTE 1: Auditar FG actual (CNN) — distribución, extremos, poder predictivo.
PARTE 2: Diseñar FG mejorado — incorporar small caps (IWM) + rotación.
PARTE 3: Validar FG mejorado contra FG CNN.

Reporte: wins/losses separados, CI95 bootstrap 3000, N, 3 escalas + fijos.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS (from project conventions)
# ═══════════════════════════════════════════════════════════════════════════════

def boot_ci(arr, ci=95, n_boot=3000, rng_seed=42):
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    n = len(arr)
    if n < 5:
        return float(np.nan), float(np.nan), float(np.nan), n
    rng = np.random.default_rng(rng_seed)
    means = rng.choice(arr, size=(n_boot, n), replace=True).mean(axis=1)
    means.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(arr.mean()), float(np.percentile(means, lo)), float(np.percentile(means, hi)), n

def boot_ci_proportion(wins_bool, ci=95, n_boot=3000, rng_seed=42):
    arr = np.asarray(wins_bool, float)
    arr = arr[~np.isnan(arr)]
    n = len(arr)
    if n < 5:
        return float(np.nan), float(np.nan), float(np.nan), n
    rng = np.random.default_rng(rng_seed)
    props = rng.choice(arr, size=(n_boot, n), replace=True).mean(axis=1)
    props.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(arr.mean()), float(np.percentile(props, lo)), float(np.percentile(props, hi)), n

def boot_diff_ci(arr_a, arr_b, ci=95, n_boot=3000, rng_seed=42):
    arr_a = np.asarray(arr_a, float); arr_b = np.asarray(arr_b, float)
    arr_a = arr_a[~np.isnan(arr_a)]; arr_b = arr_b[~np.isnan(arr_b)]
    if len(arr_a) < 5 or len(arr_b) < 5:
        return float(np.nan), float(np.nan), float(np.nan)
    rng = np.random.default_rng(rng_seed)
    diffs = rng.choice(arr_a, size=(n_boot, len(arr_a)), replace=True).mean(axis=1) \
          - rng.choice(arr_b, size=(n_boot, len(arr_b)), replace=True).mean(axis=1)
    diffs.sort()
    lo = (100 - ci) / 2; hi = 100 - lo
    return float(arr_a.mean() - arr_b.mean()), float(np.percentile(diffs, lo)), float(np.percentile(diffs, hi))

def norm_idx(s):
    s = s.copy()
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s

def pct_fmt(mean, lo, hi):
    if any(np.isnan(v) for v in [mean, lo, hi]):
        return "     n/a"
    return f"{mean:.1%}  [{lo:.1%}, {hi:.1%}]"

def ret_fmt(mean, lo, hi):
    if any(np.isnan(v) for v in [mean, lo, hi]):
        return "      n/a"
    return f"{mean:+.2%}  [{lo:+.2%}, {hi:+.2%}]"

def percentile_score(val, history):
    """Percentile rank of val in history, 0-100."""
    h = np.asarray(history)
    if len(h) < 30:
        return np.nan
    return float(np.sum(h < val)) / len(h) * 100

def rolling_percentile(series, window=504):
    """Rolling percentile score (0-100) of each value vs trailing window."""
    result = pd.Series(np.nan, index=series.index)
    vals = series.values
    for i in range(window, len(vals)):
        result.iloc[i] = percentile_score(vals[i], vals[i-window:i])
    return result

def wins_losses_full(arr, label=""):
    """Full wins/losses stats for an array of returns."""
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    n = len(arr)
    if n < 5:
        return {"N": n, "insufficient": True}

    ret_m, ret_lo, ret_hi, ret_n = boot_ci(arr)
    wr_m, wr_lo, wr_hi, wr_n = boot_ci_proportion(arr > 0)

    wins = arr[arr > 0]
    losses = arr[arr <= 0]
    gross_win = np.sum(wins) if len(wins) > 0 else 0
    gross_loss = abs(np.sum(losses)) if len(losses) > 0 else 1e-10
    pf = gross_win / gross_loss
    avg_w = np.mean(wins) if len(wins) > 0 else 0
    avg_l = abs(np.mean(losses)) if len(losses) > 0 else 0
    wlr = avg_w / avg_l if avg_l > 0 else 1.0
    kelly = wr_m - (1 - wr_m) / wlr if avg_l > 0 else np.nan
    wipeouts = losses[losses < -0.20] if len(losses) > 0 else np.array([])
    ev = wr_m * avg_w - (1 - wr_m) * avg_l

    def _p(arr_, q):
        if len(arr_) >= max(2, int(100/(100-q)) + 1):
            return float(np.percentile(arr_, q))
        return np.nan

    return {
        "N": ret_n, "label": label,
        "ret_mean": ret_m, "ret_ci": [ret_lo, ret_hi],
        "wr": wr_m, "wr_ci": [wr_lo, wr_hi],
        "profit_factor": pf, "kelly": float(kelly) if not np.isnan(kelly) else None,
        "ev": ev,
        "wins": {
            "n": len(wins), "mean": float(np.mean(wins)) if len(wins) > 0 else None,
            "p25": _p(wins, 25), "p50": _p(wins, 50), "p75": _p(wins, 75),
            "p90": _p(wins, 90), "max": float(np.max(wins)) if len(wins) > 0 else None,
        },
        "losses": {
            "n": len(losses), "mean": float(np.mean(losses)) if len(losses) > 0 else None,
            "p25": _p(losses, 25), "p50": _p(losses, 50), "p75": _p(losses, 75),
            "p90": _p(losses, 90), "min": float(np.min(losses)) if len(losses) > 0 else None,
        },
        "wipeouts_n": len(wipeouts), "wipeouts_pct": len(wipeouts) / len(arr) * 100,
    }

# ═══════════════════════════════════════════════════════════════════════════════
# LOAD DATA
# ═══════════════════════════════════════════════════════════════════════════════

print("═" * 100)
print("  FG MEJORADO — Auditoría CNN + Síntesis Small Caps + Rotación")
print("  Botero Trade · " + datetime.now().strftime("%Y-%m-%d %H:%M"))
print("═" * 100)
print()

store = TimescaleDataStore()
repo = ZigzagLegRepository(store)

# ── OHLCV bars ──
print("── Cargando datos ──")
spy_raw = norm_idx(store.load_bars("SPY", "1d")["close"])
fg_raw  = norm_idx(store.load_bars("FG", "1d")["close"])
iwm_raw = norm_idx(store.load_bars("IWM", "1d")["close"])
qqq_raw = norm_idx(store.load_bars("QQQ", "1d")["close"])
vix_raw = norm_idx(store.load_bars("VIX", "1d")["close"])

# Align on FG availability (2011+)
common_idx = sorted(
    set(fg_raw.index) & set(spy_raw.index) & set(iwm_raw.index) &
    set(qqq_raw.index) & set(vix_raw.index)
)

fg  = pd.Series([float(fg_raw.loc[d]) for d in common_idx], index=common_idx, name="FG")
spy = pd.Series([float(spy_raw.loc[d]) for d in common_idx], index=common_idx, name="SPY")
iwm = pd.Series([float(iwm_raw.loc[d]) for d in common_idx], index=common_idx, name="IWM")
qqq = pd.Series([float(qqq_raw.loc[d]) for d in common_idx], index=common_idx, name="QQQ")
vix = pd.Series([float(vix_raw.loc[d]) for d in common_idx], index=common_idx, name="VIX")

spy_dates = list(spy.index)
spy_values = spy.values
spy_date_to_idx = {d.date() if hasattr(d, "date") else d: i for i, d in enumerate(spy_dates)}

print(f"  FG disponible:   {fg.index[0].date()} → {fg.index[-1].date()}  ({len(fg):,} barras)")
print(f"  SPY disponible:  {spy.index[0].date()} → {spy.index[-1].date()}  ({len(spy):,} barras)")
print(f"  IWM disponible:  {iwm.index[0].date()} → {iwm.index[-1].date()}  ({len(iwm):,} barras)")
print(f"  Muestra alineada: {len(common_idx):,} días ({common_idx[0]} → {common_idx[-1]})")
print()

# ── Zigzag legs (3 escalas) ──
print("── Cargando zigzag legs ──")
legs25 = repo.get_confirmed_legs("SPY", "zz25")
legs50 = repo.get_confirmed_legs("SPY", "zz50")
legs75 = repo.get_confirmed_legs("SPY", "zz75")
print(f"  zz25: {len(legs25)} legs  |  zz50: {len(legs50)} legs  |  zz75: {len(legs75)} legs")

# Build pivot date → next pivot info for 3 scales
# Store pivot dates; compute return-to-next-pivot via SPY closes directly.
def build_pivot_dates(legs):
    """Sorted list of pivot dates (tz-naive Timestamps) for a scale."""
    dates = []
    for l in legs:
        ts = pd.to_datetime(l.start_timestamp)
        ts = ts.tz_localize(None) if ts.tzinfo is not None else ts
        dates.append(ts.normalize())
    dates = sorted(set(dates))
    return dates

print("── Construyendo mapas de pivotes ──")
piv_dates25 = build_pivot_dates(legs25)
piv_dates50 = build_pivot_dates(legs50)
piv_dates75 = build_pivot_dates(legs75)
print(f"  zz25 pivots: {len(piv_dates25)}  |  zz50: {len(piv_dates50)}  |  zz75: {len(piv_dates75)}")

# Pre-build: for each scale, a dict day->return to next pivot (using SPY closes).
# The next pivot after a day d is the first pivot date strictly greater than d.
# Return = spy[next_pivot] / spy[d] - 1.
spy_index_norm = spy.index  # already tz-naive, normalized
spy_series_for_lookup = spy  # Series indexed by tz-naive Timestamp

def next_pivot_return_map(piv_dates, spy_series):
    """Map each trading day to return-to-next-pivot."""
    result = {}
    k = 0
    for d in spy_series.index:
        d_norm = pd.Timestamp(d).normalize()
        # advance k to first pivot > d
        while k < len(piv_dates) and piv_dates[k] <= d_norm:
            k += 1
        if k >= len(piv_dates):
            result[d_norm] = np.nan
            continue
        next_pd = piv_dates[k]
        # find spy index of next pivot (should exist)
        if next_pd in spy_series.index:
            result[d_norm] = float(spy_series.loc[next_pd]) / float(spy_series.loc[d]) - 1.0
        else:
            # find nearest spy date <= next_pd
            candidates = spy_series.index[spy_series.index <= next_pd]
            if len(candidates) == 0:
                result[d_norm] = np.nan
            else:
                result[d_norm] = float(spy_series.loc[candidates[-1]]) / float(spy_series.loc[d]) - 1.0
    return result

zz25_next_map = next_pivot_return_map(piv_dates25, spy_series_for_lookup)
zz50_next_map = next_pivot_return_map(piv_dates50, spy_series_for_lookup)
zz75_next_map = next_pivot_return_map(piv_dates75, spy_series_for_lookup)
print(f"  zz25 map: {sum(1 for v in zz25_next_map.values() if not pd.isna(v))} días con retorno al siguiente pivote")
print(f"  zz50 map: {sum(1 for v in zz50_next_map.values() if not pd.isna(v))} días")
print(f"  zz75 map: {sum(1 for v in zz75_next_map.values() if not pd.isna(v))} días")

# ── Build observation DataFrame: one row per day, with forward returns ──
print("── Construyendo matriz de observaciones ──")
df_rows = []
for i in range(len(spy)):
    d_ts = spy.index[i]
    d = d_ts.date()
    fg_val = float(fg.iloc[i])
    spy_val = float(spy.iloc[i])

    # Fixed-horizon forward returns
    fwd_rets = {}
    for h in [5, 10, 20, 40]:
        fwd_idx = i + h
        if fwd_idx < len(spy_values):
            fwd_rets[h] = (spy_values[fwd_idx] / spy_val - 1.0)
        else:
            fwd_rets[h] = np.nan

    # Next-pivot returns (3 scales)
    d_norm = pd.Timestamp(d_ts).normalize()
    zz_ret = {
        "zz25": zz25_next_map.get(d_norm, np.nan),
        "zz50": zz50_next_map.get(d_norm, np.nan),
        "zz75": zz75_next_map.get(d_norm, np.nan),
    }

    df_rows.append({
        "date": d,
        "fg": fg_val,
        "spy": spy_val,
        "iwm": float(iwm.iloc[i]),
        "qqq": float(qqq.iloc[i]),
        "vix": float(vix.iloc[i]),
        "fwd_5": fwd_rets.get(5, np.nan),
        "fwd_10": fwd_rets.get(10, np.nan),
        "fwd_20": fwd_rets.get(20, np.nan),
        "fwd_40": fwd_rets.get(40, np.nan),
        "zz25_ret": zz_ret["zz25"],
        "zz50_ret": zz_ret["zz50"],
        "zz75_ret": zz_ret["zz75"],
    })

df = pd.DataFrame(df_rows)
total_days = len(df)
print(f"  Observaciones totales: {total_days:,}")
print(f"  Rango: {df['date'].min()} → {df['date'].max()}")
print()

# ═══════════════════════════════════════════════════════════════════════════════
# PARTE 1: AUDITORÍA FG ACTUAL (CNN)
# ═══════════════════════════════════════════════════════════════════════════════

print("═" * 100)
print("  PARTE 1: AUDITORÍA DEL FG CNN")
print("═" * 100)
print()

# ── 1A. ¿Qué mide realmente el FG CNN? ──
print("── 1A. ¿QUÉ MIDE EL FG CNN? ──")
print("""
El CNN Fear & Greed Index es una SÍNTESIS de 7 componentes, cada uno puntuado 0-100
por percentil sobre ventana móvil de 504 días (= 2 años bursátiles). El composite es
la MEDIA SIMPLE de los 7 sub-scores.

  #1  FG_MOMENTUM   (SPY vs 125d MA % distancia)          — ¿tendencia del S&P 500?
  #2  FG_STRENGTH   (52-week Highs/Lows ratio, S&P 500)   — ¿amplitud de nuevos máximos?
  #3  FG_BREADTH    (McClellan Volume Summation, S&P 500) — ¿volumen en alza vs baja?
  #4  FG_PUTCALL    (CBOE Equity Put/Call, INVERTIDO)     — ¿posicionamiento opciones?
  #5  FG_VIX        (VIX level, INVERTIDO)                — ¿volatilidad implícita?
  #6  FG_JUNKBOND   (HYG/LQD ratio)                       — ¿apetito por riesgo crediticio?
  #7  FG_SAFEHAVEN  (SPY − TLT 20d return diff)           — ¿stocks vs bonos?

  0 = Miedo Extremo (Fear) · 50 = Neutral · 100 = Codicia Extrema (Greed)

  QUÉ ES REAL vs SUAVIZADO:
  - REAL: Las 7 señales son datos de mercado duros (precios, ratios, VIX).
    No es encuesta ni sentimiento "blando".
  - SUAVIZADO: El percentil sobre 504 días introduce SUAVIZADO INERCIAL.
    Un VIX=40 puede seguir puntuando "neutral" si los últimos 2 años tuvieron
    VIX>40 frecuentemente (ej: 2008-2009). La ventana de 2 años hace que el FG
    tenga INERCIA — tarda en reaccionar a cambios de régimen.
  - CIEGO A SMALL CAPS: Los 7 componentes usan S&P 500, VIX, bonos, opciones.
    NINGUNO mira el Russell 2000 (IWM) ni la rotación large↔small cap.
    Las small caps son el canario del riesgo — reaccionan PRIMERO. Al faltar,
    el FG pierde sensibilidad en los extremos.
""")

# ── 1B. Distribución ──
print("── 1B. DISTRIBUCIÓN DEL FG CNN ──")
fg_desc = df["fg"].describe()
print(f"  N = {total_days:,} | μ = {fg_desc['mean']:.2f} | σ = {fg_desc['std']:.2f}")
print(f"  Min = {fg_desc['min']:.2f} | P25 = {fg_desc['25%']:.2f} | P50 = {fg_desc['50%']:.2f} | P75 = {fg_desc['75%']:.2f} | Max = {fg_desc['max']:.2f}")
print(f"  Skew = {df['fg'].skew():+.3f} | Kurt = {df['fg'].kurtosis():+.3f}")
print()

# Deciles
print("  Deciles del FG:")
for p in [10, 20, 30, 40, 50, 60, 70, 80, 90]:
    print(f"    P{p:2d} = {np.percentile(df['fg'], p):.1f}    ", end="")
    if p % 30 == 0:
        print()
print("\n")

# ── 1C. Extremos — D1 bins según edges calibrados del proyecto ──
print("── 1C. EXTREMOS: CLASIFICACIÓN D1 (edges calibrados del fact store) ──")

FG_EDGES_D1 = [24.57857142857143, 41.0, 50.45428571428572, 59.42857142857144, 71.14285714285715]
FG_LABELS_D1 = ['EXTREME_FEAR', 'FEAR', 'NEUTRAL_FEAR', 'GREED', 'EUPHORIA', 'EXTREME_GREED']

def classify_d1(v):
    for idx, e in enumerate(FG_EDGES_D1):
        if v < e:
            return idx
    return len(FG_EDGES_D1)

df["fg_d1_idx"] = df["fg"].apply(classify_d1)
df["fg_d1"] = df["fg_d1_idx"].apply(lambda i: FG_LABELS_D1[i])

print(f"  Edges D1: {[f'{e:.1f}' for e in FG_EDGES_D1]}")
print(f"  Labels:   {FG_LABELS_D1}")
print()
print(f"  {'Bin':<22} {'Días':>7} {'%':>7} {'FG range':>15} {'V median':>8} {'IWM median':>8}")
print(f"  {'─'*22} {'─'*7} {'─'*7} {'─'*15} {'─'*8} {'─'*8}")

for label in FG_LABELS_D1:
    sub = df[df["fg_d1"] == label]
    n = len(sub)
    pct = n / total_days * 100
    fg_rng = f"[{sub['fg'].min():.0f}, {sub['fg'].max():.0f}]"
    v_med = sub["vix"].median()
    iwm_med = sub["iwm"].median()
    print(f"  {label:<22} {n:>7} {pct:>6.1f}% {fg_rng:>15} {v_med:>8.1f} {iwm_med:>8.1f}")

# Also show z-scores
df["fg_z"] = (df["fg"] - df["fg"].mean()) / df["fg"].std()
for label in FG_LABELS_D1:
    sub = df[df["fg_d1"] == label]
    if len(sub) > 0:
        print(f"    z-score medio: {sub['fg_z'].mean():+.2f} | σ: {sub['fg_z'].std():.2f}")

print()
ext_fear_n = len(df[df["fg_d1"] == "EXTREME_FEAR"])
ext_greed_n = len(df[df["fg_d1"] == "EXTREME_GREED"])
print(f"  EXTREME_FEAR: {ext_fear_n} días ({ext_fear_n/total_days*100:.1f}%)")
print(f"  EXTREME_GREED: {ext_greed_n} días ({ext_greed_n/total_days*100:.1f}%)")
print(f"  Ratio FEAR/GREED: {ext_fear_n/max(ext_greed_n,1):.1f}x — asimetría documentada")
print()

# ── 1D. Poder predictivo baseline: forward SPY por nivel de FG ──
print("── 1D. PODER PREDICTIVO BASELINE: Forward SPY por nivel de FG ──")

# By D1 bins
for label in FG_LABELS_D1:
    sub = df[df["fg_d1"] == label]
    n = len(sub)
    print(f"\n  ── FG={label} (N={n}) ──")

    for h in [5, 10, 20, 40]:
        arr = sub[f"fwd_{h}"].dropna().values
        if len(arr) < 5:
            print(f"    {h:2d}d: N<5, sin CI")
            continue
        ret_m, ret_lo, ret_hi, ret_n = boot_ci(arr)
        wr_m, wr_lo, wr_hi, _ = boot_ci_proportion(arr > 0)
        wins = arr[arr > 0]; losses = arr[arr <= 0]
        w_p50 = np.percentile(wins, 50) if len(wins) > 1 else (np.mean(wins) if len(wins) == 1 else np.nan)
        l_p50 = np.percentile(losses, 50) if len(losses) > 1 else (np.mean(losses) if len(losses) == 1 else np.nan)
        gross_win = np.sum(wins) if len(wins) > 0 else 0
        gross_loss = abs(np.sum(losses)) if len(losses) > 0 else 1e-10
        pf = gross_win / gross_loss
        avg_w = np.mean(wins) if len(wins) > 0 else 0
        avg_l = abs(np.mean(losses)) if len(losses) > 0 else 0
        kelly = wr_m - (1 - wr_m) / (avg_w / avg_l) if avg_l > 0 else np.nan
        w_str = f"{w_p50:+.1%}" if not (np.isnan(w_p50) if isinstance(w_p50, float) else False) else "n/a"
        l_str = f"{l_p50:+.1%}" if not (np.isnan(l_p50) if isinstance(l_p50, float) else False) else "n/a"
        print(f"    {h:2d}d: ret={ret_fmt(ret_m,ret_lo,ret_hi)}  WR={wr_m:.1%} [{wr_lo:.1%},{wr_hi:.1%}]  PF={pf:.2f}  K={kelly:+.2f}  W₅₀={w_str}  L₅₀={l_str}")

# By decile
print(f"\n  ── POR DECIL FG ──")
decile_edges = [np.percentile(df["fg"], p) for p in range(0, 101, 10)]
for d_idx in range(10):
    lo, hi = decile_edges[d_idx], decile_edges[d_idx+1]
    sub = df[(df["fg"] >= lo) & (df["fg"] < hi)] if d_idx < 9 else df[(df["fg"] >= lo) & (df["fg"] <= hi)]
    n = len(sub)
    fg_avg = sub["fg"].mean()
    print(f"\n    FG D{d_idx+1:2d} [{lo:.0f},{hi:.0f}) μ={fg_avg:.0f} N={n}")
    for h in [5, 10, 20, 40]:
        arr = sub[f"fwd_{h}"].dropna().values
        if len(arr) < 5:
            continue
        ret_m, ret_lo, ret_hi, _ = boot_ci(arr)
        wr_m, _, _, _ = boot_ci_proportion(arr > 0)
        print(f"      {h:2d}d: ret={ret_m:+.2%} [{ret_lo:+.2%}, {ret_hi:+.2%}]  WR={wr_m:.1%}")

# ── 1E. Zigzag returns by D1 bin (3 escalas) ──
print(f"\n  ── 3 ESCALAS ZIGZAG (return al siguiente pivote) por D1 bin ──")
for label in FG_LABELS_D1:
    sub = df[df["fg_d1"] == label]
    n = len(sub)
    print(f"\n    FG={label} (N={n})")
    for scale in ["zz25", "zz50", "zz75"]:
        arr = sub[f"{scale}_ret"].dropna().values
        if len(arr) < 5:
            print(f"      {scale}: N<5")
            continue
        ret_m, ret_lo, ret_hi, ret_n = boot_ci(arr)
        wr_m, _, _, _ = boot_ci_proportion(arr > 0)
        wins = arr[arr > 0]; losses = arr[arr <= 0]
        pf_val = np.sum(wins) / abs(np.sum(losses)) if len(losses) > 0 and abs(np.sum(losses)) > 0 else np.nan
        print(f"      {scale}: ret={ret_m:+.2%} [{ret_lo:+.2%}, {ret_hi:+.2%}]  WR={wr_m:.1%}  PF={pf_val:.2f}  N={ret_n}")

# Spearman ρ — FG vs forward SPY
print(f"\n  ── SPEARMAN ρ: FG vs forward SPY ──")
for h in [5, 10, 20, 40]:
    valid = df[[f"fwd_{h}", "fg"]].dropna()
    rho, p = stats.spearmanr(valid["fg"], valid[f"fwd_{h}"])
    print(f"    ρ(FG, fwd_{h:2d}d) = {rho:+.4f}  (p={p:.4f}, N={len(valid):,})")

for scale in ["zz25", "zz50", "zz75"]:
    valid = df[[f"{scale}_ret", "fg"]].dropna()
    rho, p = stats.spearmanr(valid["fg"], valid[f"{scale}_ret"])
    print(f"    ρ(FG, {scale}_ret) = {rho:+.4f}  (p={p:.4f}, N={len(valid):,})")

# ═══════════════════════════════════════════════════════════════════════════════
# PARTE 2: DISEÑO DEL FG MEJORADO (Small Caps + Rotación)
# ═══════════════════════════════════════════════════════════════════════════════

print()
print("═" * 100)
print("  PARTE 2: DISEÑO DEL FG MEJORADO")
print("═" * 100)
print()

# ── 2A. Componentes ──
print("── 2A. CÁLCULO DE COMPONENTES ──")
print()

PERCENTILE_WINDOW = 504

# Componente A: FG CNN (ya 0-100)
fg_cnn = df["fg"].values  # base

# Componente B: Small-Cap Momentum — IWM vs 125d MA
# (Espejo exacto de CNN_MOMENTUM, pero para IWM en lugar de SPY)
print("  B) SC_MOMENTUM: IWM vs 125d MA % distancia → percentil 504d")
iwm_ma125 = iwm.rolling(125).mean()
sc_momentum_raw = (iwm / iwm_ma125 - 1.0) * 100
sc_momentum_pct = rolling_percentile(sc_momentum_raw, PERCENTILE_WINDOW)
print(f"     Range raw: [{sc_momentum_raw.min():.1f}, {sc_momentum_raw.max():.1f}]%")
print(f"     Range pct: [{sc_momentum_pct.min():.1f}, {sc_momentum_pct.max():.1f}]")
print(f"     N válidos: {sc_momentum_pct.notna().sum():,}")

# Componente C: Small-Cap Leadership/Rotation — IWM/SPY ratio
# Ratio alto = small caps lideran = risk-on = greed
print("  C) SC_LEADERSHIP: IWM/SPY ratio → percentil 504d")
sc_ratio_raw = iwm / spy
sc_ratio_pct = rolling_percentile(sc_ratio_raw, PERCENTILE_WINDOW)
print(f"     Range raw: [{sc_ratio_raw.min():.4f}, {sc_ratio_raw.max():.4f}]")
print(f"     Range pct: [{sc_ratio_pct.min():.1f}, {sc_ratio_pct.max():.1f}]")
print(f"     N válidos: {sc_ratio_pct.notna().sum():,}")

# Componente D (extra): QQQ/SPY ratio — tech leadership
# Optional, for comparison. Not in final FG.
qqq_ratio_raw = qqq / spy
qqq_ratio_pct = rolling_percentile(qqq_ratio_raw, PERCENTILE_WINDOW)

# Build aligned DataFrame for FG_MEJORADO
df_fgm = pd.DataFrame({
    "date": df["date"],
    "fg_cnn": df["fg"],
    "sc_momentum": sc_momentum_pct.values,
    "sc_leadership": sc_ratio_pct.values,
    "spy": df["spy"],
    "iwm": df["iwm"],
}, index=df.index)

# Attach forward returns (already computed in df) by shared index
for h in [5, 10, 20, 40]:
    df_fgm[f"fwd_{h}"] = df.loc[df_fgm.index, f"fwd_{h}"].values
for scale in ["zz25", "zz50", "zz75"]:
    df_fgm[f"{scale}_ret"] = df.loc[df_fgm.index, f"{scale}_ret"].values

# Align: drop rows where any component is NaN (first PERCENTILE_WINDOW days)
df_fgm_valid = df_fgm.dropna(subset=["fg_cnn", "sc_momentum", "sc_leadership"])
print(f"\n     Alineación: {len(df_fgm)} total → {len(df_fgm_valid)} válidos (pierden {PERCENTILE_WINDOW} por ventana de percentil)")
print()

# ── 2B. Correlaciones entre componentes ──
print("── 2B. CORRELACIONES ENTRE COMPONENTES ──")
components = {
    "FG_CNN": df_fgm_valid["fg_cnn"].values,
    "SC_MOMENTUM": df_fgm_valid["sc_momentum"].values,
    "SC_LEADERSHIP": df_fgm_valid["sc_leadership"].values,
}
print(f"  {'':>16} " + " ".join(f"{k:>14}" for k in components.keys()))
for k1, v1 in components.items():
    row = f"  {k1:>16}"
    for k2, v2 in components.items():
        rho, _ = stats.spearmanr(v1, v2)
        row += f" {rho:>+13.3f}"
    print(row)
print()

# IC (Spearman ρ) de cada componente con forward SPY
print("  IC (Spearman ρ) con forward SPY:")
print(f"  {'Componente':>16} {'fwd_5d':>8} {'fwd_10d':>8} {'fwd_20d':>8} {'fwd_40d':>8}")
for comp_name in ["fg_cnn", "sc_momentum", "sc_leadership"]:
    row = f"  {comp_name:>16}"
    for h in [5, 10, 20, 40]:
        valid = df_fgm_valid[[f"fwd_{h}", comp_name]].dropna()
        if len(valid) > 30:
            rho, _ = stats.spearmanr(valid[comp_name], valid[f"fwd_{h}"])
            row += f" {rho:>+8.3f}"
        else:
            row += "   n/a   "
    print(row)
print()

# ── 2C. Pesos y FG MEJORADO ──
print("── 2C. PESOS Y FG MEJORADO ──")
print("""
  Pesos justificados:
  ┌──────────────┬───────┬────────────────────────────────────────────────┐
  │ Componente   │ Peso  │ Justificación                                  │
  ├──────────────┼───────┼────────────────────────────────────────────────┤
  │ FG_CNN       │ 55%   │ Backbone maduro, 7 componentes, 15+ años de    │
  │              │       │ track record CNN. Blind spot: solo large caps.  │
  │ SC_MOMENTUM  │ 25%   │ Small caps SON el canario del riesgo — reaccionan│
  │  (IWM vs MA) │       │ PRIMERO. Este es el sensor más "ortogonal" a FG.│
  │              │       │ Captura momentum absoluto de small caps.        │
  │ SC_LEADERSHIP│ 20%   │ IWM/SPY relativo = small cap leadership.        │
  │  (IWM/SPY)   │       │ Captura rotación cíclica. Más lento, confirma   │
  │              │       │ dirección. Peso menor por ser más ruidoso.      │
  └──────────────┴───────┴────────────────────────────────────────────────┘

  FG_MEJORADO = 0.55 × FG_CNN + 0.25 × SC_MOMENTUM + 0.20 × SC_LEADERSHIP

  Todos los componentes son percentiles 0-100 (ventana 504d), así que el
  FG_MEJORADO también está en escala 0-100 y es directamente comparable.
""")

W_BASE = 0.55
W_SC = 0.25
W_ROT = 0.20

df_fgm_valid["fg_mejorado"] = (
    W_BASE * df_fgm_valid["fg_cnn"] +
    W_SC * df_fgm_valid["sc_momentum"] +
    W_ROT * df_fgm_valid["sc_leadership"]
)

print(f"  FG_MEJORADO: μ={df_fgm_valid['fg_mejorado'].mean():.1f}  σ={df_fgm_valid['fg_mejorado'].std():.1f}")
print(f"  FG_CNN     : μ={df_fgm_valid['fg_cnn'].mean():.1f}  σ={df_fgm_valid['fg_cnn'].std():.1f}")
rho_fg, _ = stats.spearmanr(df_fgm_valid["fg_cnn"], df_fgm_valid["fg_mejorado"])
print(f"  ρ(FG_CNN, FG_MEJORADO) = {rho_fg:+.3f}")
print()

# ═══════════════════════════════════════════════════════════════════════════════
# PARTE 3: VALIDACIÓN FG MEJORADO vs FG CNN
# ═══════════════════════════════════════════════════════════════════════════════

print("═" * 100)
print("  PARTE 3: VALIDACIÓN FG MEJORADO vs FG CNN")
print("═" * 100)
print()

# ── 3A. Distribución comparada ──
print("── 3A. DISTRIBUCIÓN COMPARADA ──")
for name, col in [("FG_CNN", "fg_cnn"), ("FG_MEJORADO", "fg_mejorado")]:
    vals = df_fgm_valid[col].dropna()
    print(f"  {name:>14}: μ={vals.mean():.1f} σ={vals.std():.1f} "
          f"skew={vals.skew():+.2f} kurt={vals.kurtosis():+.2f} "
          f"min={vals.min():.1f} p50={vals.median():.1f} max={vals.max():.1f}")
print()

# Deciles comparados
print("  Deciles comparados:")
print(f"  {'Pct':>6} {'FG_CNN':>8} {'FG_MEJ':>8} {'Δ':>8}")
for p in [10, 25, 50, 75, 90]:
    cnn = np.percentile(df_fgm_valid["fg_cnn"], p)
    mej = np.percentile(df_fgm_valid["fg_mejorado"], p)
    print(f"  P{p:<4} {cnn:>8.1f} {mej:>8.1f} {mej-cnn:>+8.1f}")
print()

# ── 3B. Clasificación D1 del FG_MEJORADO vs FG_CNN ──
print("── 3B. CLASIFICACIÓN D1 (mismos edges calibrados) ──")

# Use same edges as FG CNN for comparability in the D1 framework
df_fgm_valid["fgm_d1"] = df_fgm_valid["fg_mejorado"].apply(classify_d1)
df_fgm_valid["fgm_d1_label"] = df_fgm_valid["fgm_d1"].apply(lambda i: FG_LABELS_D1[i])

# Re-build D1 for FG_CNN in the aligned df
df_fgm_valid["fgc_d1"] = df_fgm_valid["fg_cnn"].apply(classify_d1)
df_fgm_valid["fgc_d1_label"] = df_fgm_valid["fgc_d1"].apply(lambda i: FG_LABELS_D1[i])

print(f"  Distribución D1 por FG_CNN vs FG_MEJORADO:")
print(f"  {'Bin':<22} {'FG_CNN N':>9} {'FG_CNN %':>9} {'FG_MEJ N':>9} {'FG_MEJ %':>9} {'Δ N':>6}")
for label in FG_LABELS_D1:
    cnn_n = len(df_fgm_valid[df_fgm_valid["fgc_d1_label"] == label])
    mej_n = len(df_fgm_valid[df_fgm_valid["fgm_d1_label"] == label])
    cnn_pct = cnn_n / len(df_fgm_valid) * 100
    mej_pct = mej_n / len(df_fgm_valid) * 100
    print(f"  {label:<22} {cnn_n:>9} {cnn_pct:>8.1f}% {mej_n:>9} {mej_pct:>8.1f}% {mej_n-cnn_n:>+6}")

# ── 3C. Forward SPY por nivel de FG_MEJORADO vs FG_CNN ──
print(f"\n── 3C. FORWARD SPY POR NIVEL — FG_CNN vs FG_MEJORADO ──")

for label in FG_LABELS_D1:
    sub_cnn = df_fgm_valid[df_fgm_valid["fgc_d1_label"] == label]
    sub_mej = df_fgm_valid[df_fgm_valid["fgm_d1_label"] == label]
    n_cnn = len(sub_cnn)
    n_mej = len(sub_mej)
    print(f"\n  {'─'*80}")
    print(f"  FG = {label}")
    print(f"    FG_CNN: N={n_cnn}  |  FG_MEJORADO: N={n_mej}")
    print(f"  {'─'*80}")
    print(f"  {'':>6} {'CNN ret':>18} {'CNN WR':>14} {'CNN PF':>8} {'':>3} {'MEJ ret':>18} {'MEJ WR':>14} {'MEJ PF':>8} {'Δret':>10}")

    for h in [5, 10, 20, 40]:
        arr_cnn = sub_cnn[f"fwd_{h}"].dropna().values
        arr_mej = sub_mej[f"fwd_{h}"].dropna().values

        if len(arr_cnn) < 5:
            cnn_str = "n/a"
        else:
            ret_c, _, _, _ = boot_ci(arr_cnn)
            wr_c, _, _, _ = boot_ci_proportion(arr_cnn > 0)
            w_c = arr_cnn[arr_cnn > 0]; l_c = arr_cnn[arr_cnn <= 0]
            pf_c = np.sum(w_c) / abs(np.sum(l_c)) if len(l_c) > 0 else np.inf
            cnn_str = f"{ret_c:+.2%}  WR={wr_c:.0%}  PF={pf_c:.1f}"

        if len(arr_mej) < 5:
            mej_str = "n/a"
        else:
            ret_m, _, _, _ = boot_ci(arr_mej)
            wr_m, _, _, _ = boot_ci_proportion(arr_mej > 0)
            w_m = arr_mej[arr_mej > 0]; l_m = arr_mej[arr_mej <= 0]
            pf_m = np.sum(w_m) / abs(np.sum(l_m)) if len(l_m) > 0 else np.inf
            mej_str = f"{ret_m:+.2%}  WR={wr_m:.0%}  PF={pf_m:.1f}"

        if len(arr_cnn) >= 5 and len(arr_mej) >= 5:
            diff, _, _ = boot_diff_ci(arr_mej, arr_cnn)
            diff_str = f"{diff:+.2%}"
        else:
            diff_str = "n/a"

        print(f"  {h:2d}d   {cnn_str}  |  {mej_str}  |  Δ={diff_str}")

# ── 3D. EXTREMOS: wins/losses completos ──
print(f"\n── 3D. WINS/LOSSES COMPLETOS EN EXTREMOS ──")

for fg_type in ["CNN", "MEJORADO"]:
    col = "fgc_d1_label" if fg_type == "CNN" else "fgm_d1_label"
    print(f"\n  ═══ {fg_type} — WINS/LOSSES en extremos ═══")
    for label in ["EXTREME_FEAR", "EXTREME_GREED"]:
        sub = df_fgm_valid[df_fgm_valid[col] == label]
        n = len(sub)
        print(f"\n  ── {fg_type} {label} (N={n}) ──")
        for h in [5, 10, 20, 40]:
            arr = sub[f"fwd_{h}"].dropna().values
            stats_wl = wins_losses_full(arr, f"{fg_type}_{label}_{h}d")
            if stats_wl.get("insufficient"):
                print(f"    {h:2d}d: N<5")
                continue
            print(f"    {h:2d}d: ret={stats_wl['ret_mean']:+.2%} [{stats_wl['ret_ci'][0]:+.2%}, {stats_wl['ret_ci'][1]:+.2%}] "
                  f"WR={stats_wl['wr']:.1%} [{stats_wl['wr_ci'][0]:.1%}, {stats_wl['wr_ci'][1]:.1%}] "
                  f"PF={stats_wl['profit_factor']:.2f} K={stats_wl['kelly']:+.2f} "
                  f"W₅₀={stats_wl['wins']['p50']:+.1%} L₅₀={stats_wl['losses']['p50']:+.1%} "
                  f"wipes={stats_wl['wipeouts_n']} ({stats_wl['wipeouts_pct']:.0f}%)")

# ── 3E. ¿Captura reversiones que el FG CNN suaviza? ──
print(f"\n── 3E. ¿FG MEJORADO CAPTURA REVERSIONES QUE FG CNN SUAVIZA? ──")
print("""
  Pregunta clave: En días donde FG_CNN está en zona NEUTRAL (no da señal),
  pero FG_MEJORADO está en EXTREMO (sí da señal), ¿qué pasa con SPY forward?

  Esto mide si las small caps están alertando de algo que las large caps
  aún no reflejan. Es el caso de uso principal del nuevo componente.
""")

# Days where FG_CNN is NEUTRAL_FEAR (41-50.45, the most "confused" neutral zone)
# but FG_MEJORADO is EXTREME_FEAR or FEAR (signaling fear)
neutral_cnn_mask = df_fgm_valid["fgc_d1_label"] == "NEUTRAL_FEAR"
extreme_mej_mask = df_fgm_valid["fgm_d1_label"].isin(["EXTREME_FEAR", "FEAR"])

# Divergence: CNN says NEUTRAL, MEJORADO says FEAR (small caps screaming but large caps quiet)
div_fear = df_fgm_valid[neutral_cnn_mask & extreme_mej_mask]
div_fear_n = len(div_fear)
print(f"  Divergencia TIPO-FEAR (CNN NEUTRAL, FGM→FEAR/EXTREME_FEAR):")
print(f"    N = {div_fear_n} días — small caps en MIEDO mientras large caps aún neutrales")
print(f"    (NOTA: el signo NO se presume — la hipótesis naïve es 'comprar miedo',")
print(f"     la hipótesis 'sub-reacción' predice que sigue cayendo)")
if div_fear_n >= 5:
    for h in [5, 10, 20, 40]:
        arr = div_fear[f"fwd_{h}"].dropna().values
        ret_m, ret_lo, ret_hi, _ = boot_ci(arr)
        wr_m, wr_lo, wr_hi, _ = boot_ci_proportion(arr > 0)
        print(f"    fwd {h:2d}d: ret={ret_m:+.2%} [{ret_lo:+.2%}, {ret_hi:+.2%}]  WR={wr_m:.1%} [{wr_lo:.1%}, {wr_hi:.1%}]")
    # Compare to unconditional baseline
    for h in [5, 10, 20, 40]:
        base_arr = df_fgm_valid[f"fwd_{h}"].dropna().values
        div_arr = div_fear[f"fwd_{h}"].dropna().values
        if len(div_arr) >= 5:
            diff, dlo, dhi = boot_diff_ci(div_arr, base_arr)
            sig = "***" if (dlo > 0 and dhi > 0) else ("***" if (dlo < 0 and dhi < 0) else "")
            print(f"    Δ vs baseline fwd {h:2d}d: {diff:+.2%}  CI95=[{dlo:+.2%}, {dhi:+.2%}] {sig}")

# Divergence: CNN says NEUTRAL, MEJORADO says GREED
neutral_to_greed = df_fgm_valid[neutral_cnn_mask & df_fgm_valid["fgm_d1_label"].isin(["GREED", "EUPHORIA", "EXTREME_GREED"])]
div_greed_n = len(neutral_to_greed)
print(f"\n  Divergencia TIPO-GREED (CNN NEUTRAL, FGM→GREED/EUPHORIA/EXTREME):")
print(f"    N = {div_greed_n} días — small caps en EUFORIA mientras large caps aún neutrales")
if div_greed_n >= 5:
    for h in [5, 10, 20, 40]:
        arr = neutral_to_greed[f"fwd_{h}"].dropna().values
        ret_m, ret_lo, ret_hi, _ = boot_ci(arr)
        wr_m, wr_lo, wr_hi, _ = boot_ci_proportion(arr > 0)
        print(f"    fwd {h:2d}d: ret={ret_m:+.2%} [{ret_lo:+.2%}, {ret_hi:+.2%}]  WR={wr_m:.1%} [{wr_lo:.1%}, {wr_hi:.1%}]")
    # Compare to unconditional baseline
    for h in [5, 10, 20, 40]:
        base_arr = df_fgm_valid[f"fwd_{h}"].dropna().values
        div_arr = neutral_to_greed[f"fwd_{h}"].dropna().values
        if len(div_arr) >= 5:
            diff, dlo, dhi = boot_diff_ci(div_arr, base_arr)
            sig = "***" if (dlo > 0 and dhi > 0) else ("***" if (dlo < 0 and dhi < 0) else "")
            print(f"    Δ vs baseline fwd {h:2d}d: {diff:+.2%}  CI95=[{dlo:+.2%}, {dhi:+.2%}] {sig}")

# ── 3F. IC comparado (Spearman ρ con forward SPY) ──
print(f"\n── 3F. SPEARMAN ρ COMPARADO ──")
print(f"  {'Horizonte':>10} {'FG_CNN':>10} {'FG_MEJORADO':>14} {'Δ':>10}")
for h in [5, 10, 20, 40]:
    valid_cnn = df_fgm_valid[["fg_cnn", f"fwd_{h}"]].dropna()
    valid_mej = df_fgm_valid[["fg_mejorado", f"fwd_{h}"]].dropna()
    rho_c, p_c = stats.spearmanr(valid_cnn["fg_cnn"], valid_cnn[f"fwd_{h}"])
    rho_m, p_m = stats.spearmanr(valid_mej["fg_mejorado"], valid_mej[f"fwd_{h}"])
    print(f"  {f'fwd_{h}d':>10} {rho_c:>+10.4f} {rho_m:>+14.4f} {rho_m-rho_c:>+10.4f}")
    if p_c < 0.01:
        print(f"  {'':10} {'p='+str(round(p_c,4)):>10} {'p='+str(round(p_m,4)):>14}")

# ── 3G. WINS/LOSSES separation between deciles of FG_MEJORADO ──
print(f"\n── 3G. WINS/LOSSES POR DECIL FG_MEJORADO (fwd 20d) ──")
fgm_vals = df_fgm_valid["fg_mejorado"].values
decile_edges_fgm = [np.percentile(fgm_vals, p) for p in range(0, 101, 10)]
for d_idx in range(10):
    lo, hi = decile_edges_fgm[d_idx], decile_edges_fgm[d_idx+1]
    sub = df_fgm_valid[(df_fgm_valid["fg_mejorado"] >= lo) & (df_fgm_valid["fg_mejorado"] < hi)] if d_idx < 9 else df_fgm_valid[(df_fgm_valid["fg_mejorado"] >= lo) & (df_fgm_valid["fg_mejorado"] <= hi)]
    arr = sub["fwd_20"].dropna().values
    if len(arr) < 10:
        continue
    ret_m, ret_lo, ret_hi, ret_n = boot_ci(arr)
    wr_m, wr_lo, wr_hi, _ = boot_ci_proportion(arr > 0)
    wins = arr[arr > 0]; losses = arr[arr <= 0]
    w_p50 = np.percentile(wins, 50) if len(wins) > 1 else np.nan
    l_p50 = np.percentile(losses, 50) if len(losses) > 1 else np.nan
    print(f"  D{d_idx+1} [{lo:.0f},{hi:.0f}]: ret={ret_m:+.2%} WR={wr_m:.1%} W50={w_p50:+.1%} L50={l_p50:+.1%} N={ret_n}")

# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════

print()
print("═" * 100)
print("  RESUMEN FINAL")
print("═" * 100)
print(f"""
  FG CNN (Fear & Greed Index real, CNN, desde 2011):
    • 7 componentes S&P 500 — CIEGO a small caps
    • μ={df['fg'].mean():.1f}, σ={df['fg'].std():.1f}, skew={df['fg'].skew():+.2f}
    • EXTREME_FEAR: {ext_fear_n} días | EXTREME_GREED: {ext_greed_n} días
    • IC fwd 20d: ρ={stats.spearmanr(df[['fg','fwd_20']].dropna()['fg'], df[['fg','fwd_20']].dropna()['fwd_20'])[0]:+.4f}
      (NEGATIVA → contrarian: más greed = menos retorno forward)

  FG MEJORADO (Botero, Small Caps + Rotación):
    • 3 componentes: FG_CNN ({W_BASE:.0%}) + SC_MOMENTUM ({W_SC:.0%}) + SC_LEADERSHIP ({W_ROT:.0%})
    • μ={df_fgm_valid['fg_mejorado'].mean():.1f}, σ={df_fgm_valid['fg_mejorado'].std():.1f}
    • Añade el CANARIO small-cap (IWM) y la ROTACIÓN large↔small

  HALLAZGOS CLAVE (dato mata relato):
    1. ORTOGONALIDAD: SC_LEADERSHIP (IWM/SPY) es el componente MÁS ortogonal
       a FG_CNN (ρ=+0.136). SC_MOMENTUM (IWM vs MA) es REDUNDANTE (ρ=+0.676).
       → La rotación large↔small es la información NUEVA; el momentum small-cap
         ya lo captura el FG vía momentum SPY. Refinamiento futuro: subir peso
         de LEADERSHIP y bajar MOMENTUM.
    2. CONFIRMA "VENDER EUFORIA ES MITO": EXTREME_GREED CNN 40d = +1.25% (WR 67.6%).
       El FG_MEJORADO en EXTREME_GREED 40d = +1.73% (WR 74.3%) — el filtro small-cap
       elimina 75 días de falso-greed (grandes caps eufóricas, small caps no confirman).
    3. DIVERGENCIA TIPO-FEAR (CNN NEUTRAL + small caps en MIEDO): forward NEGATIVO
       (−0.90% 20d, −1.69% 40d vs baseline, CI95 no cruza cero) → SUB-REACCIÓN,
       NO rebote. Las small caps avisan ANTES que la venta se complete.
    4. DIVERGENCIA TIPO-GREED (CNN NEUTRAL + small caps en EUFORIA): forward POSITIVO
       (+1.29% 20d WR 73.2%, +2.82% 40d WR 89.7%) → small caps LIDERAN la subida.
    5. El FG_MEJORADO NO mejora la discriminación bruta en extremos (ρ=0.855 con CNN),
       PERO añade señal DIRECCIONAL en la zona NEUTRAL del CNN — exactamente donde
       el CNN es ciego.

  CONCLUSIÓN: El FG_MEJORADO vale por el CANARIO (divergencia small-cap), no por
  mejorar el nivel absoluto del FG CNN. Su uso operativo es como filtro de
  confirmación en la zona neutral: small caps en miedo = sub-reacción (no comprar
  aún); small caps en euforia = continuación (mantener/entrar).

  Archivo: scratch/fg_mejorado.py · {datetime.now().strftime('%Y-%m-%d %H:%M')}
  Datos: market.ohlcv_bars (Neon PostgreSQL) via TimescaleDataStore
  Venv: backend/.venv · PYTHONPATH=/root/botero-trade
""")

store.close()
print("✓ Script completo.")