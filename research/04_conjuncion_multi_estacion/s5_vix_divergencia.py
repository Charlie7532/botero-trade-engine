#!/usr/bin/env python3
"""
EJERCICIO DIVERGENCIA VIX×S5 — sentir vs hacer
=================================================
Vix = lo que el mercado SIENTE (miedo, volatilidad implícita)
S5 (S5TW) = lo que el mercado HACE (breadth de precio: % stocks > 20-MA)
SV5 (SV5TW) = CON QUÉ VOLUMEN lo hace (breadth de volumen)

4 REGÍMENES DE DIVERGENCIA:
  1. MIEDO SIN VENTA:   VIX↑ + S5 mantiene (no colapsa) → ¿sobre-reacción, rebote?
  2. MIEDO CON VENTA:   VIX↑ + S5 colapsa              → ¿venta real, sigue cayendo?
  3. CALMA CON AMPLITUD: VIX↓ + S5 se recupera          → tendencia sana
  4. CALMA SIN CONVICCIÓN: VIX↓ + S5 no reacciona        → deriva

MÉTRICA: 3 escalas zigzag (zz25/zz50/zz75) + horizontes fijos (5/10/20/40d).
Con baseline de alternación explícito, wins/losses separados, CI95, N.

¿SV5 distingue los casos ambiguos?
Reconciliación zigzag vs fijos: timing de la reversión.
"""

import sys
import json
from pathlib import Path
from datetime import timedelta, datetime
from collections import Counter

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def boot_ci(arr, ci=95, n_boot=3000, rng_seed=42):
    """Bootstrap CI95 for mean."""
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    n = len(arr)
    if n < 5:
        return float(np.nan), float(np.nan), float(np.nan), n
    rng = np.random.default_rng(rng_seed)
    means = np.zeros(n_boot)
    for i in range(n_boot):
        sample = rng.choice(arr, size=n, replace=True)
        means[i] = sample.mean()
    means.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(arr.mean()), float(np.percentile(means, lo)), float(np.percentile(means, hi)), n


def boot_ci_proportion(wins_bool, ci=95, n_boot=3000, rng_seed=42):
    """Bootstrap CI95 for a proportion (e.g. win rate)."""
    arr = np.asarray(wins_bool, float)
    arr = arr[~np.isnan(arr)]
    n = len(arr)
    if n < 5:
        return float(np.nan), float(np.nan), float(np.nan), n
    rng = np.random.default_rng(rng_seed)
    props = np.zeros(n_boot)
    for i in range(n_boot):
        props[i] = rng.choice(arr, size=n, replace=True).mean()
    props.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(arr.mean()), float(np.percentile(props, lo)), float(np.percentile(props, hi)), n


def boot_diff_ci(arr_a, arr_b, ci=95, n_boot=3000, rng_seed=42):
    """Bootstrap CI95 for difference of means A - B."""
    arr_a = np.asarray(arr_a, float)
    arr_b = np.asarray(arr_b, float)
    arr_a = arr_a[~np.isnan(arr_a)]
    arr_b = arr_b[~np.isnan(arr_b)]
    if len(arr_a) < 5 or len(arr_b) < 5:
        return float(np.nan), float(np.nan), float(np.nan)
    rng = np.random.default_rng(rng_seed)
    diffs = np.zeros(n_boot)
    for i in range(n_boot):
        sa = rng.choice(arr_a, size=len(arr_a), replace=True)
        sb = rng.choice(arr_b, size=len(arr_b), replace=True)
        diffs[i] = sa.mean() - sb.mean()
    diffs.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(arr_a.mean() - arr_b.mean()), float(np.percentile(diffs, lo)), float(np.percentile(diffs, hi))


def norm_idx(s):
    """Normalize OHLCV bar index to date objects, remove duplicates."""
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


# ═══════════════════════════════════════════════════════════════════════════════
# LOAD DATA
# ═══════════════════════════════════════════════════════════════════════════════

print("═" * 90)
print("  DIVERGENCIA VIX×S5 — sentir (VIX) vs hacer (S5)")
print("  Regimes: MIEDO SIN/CON VENTA × CALMA CON/SIN CONVICCIÓN")
print("═" * 90)
print()

store = TimescaleDataStore()
repo = ZigzagLegRepository(store)

# ── OHLCV bars ──
vix_raw = norm_idx(store.load_bars("VIX", "1d")["close"])
s5tw_raw = norm_idx(store.load_bars("S5TW", "1d")["close"])
sv5tw_raw = norm_idx(store.load_bars("SV5TW", "1d")["close"])
spy_raw = norm_idx(store.load_bars("SPY", "1d")["close"])

# Align on common dates (SV5TW starts ~1999-01)
common_idx = sorted(set(vix_raw.index) & set(s5tw_raw.index) & set(sv5tw_raw.index) & set(spy_raw.index))

vix = pd.Series([float(vix_raw.loc[d]) for d in common_idx], index=common_idx)
s5tw = pd.Series([float(s5tw_raw.loc[d]) for d in common_idx], index=common_idx)
sv5tw = pd.Series([float(sv5tw_raw.loc[d]) for d in common_idx], index=common_idx)
spy = pd.Series([float(spy_raw.loc[d]) for d in common_idx], index=common_idx)

spy_dates = list(spy.index)
spy_values = spy.values
spy_date_to_idx = {d.date() if hasattr(d, "date") else d: i for i, d in enumerate(spy_dates)}

print(f"  Datos alineados: {spy_dates[0].date()} → {spy_dates[-1].date()}  ({len(spy)} barras)")
print()

# ── Diff windows for regime classification ──
REGIME_WINDOW = 5  # 5-day diff
vix_diff5 = vix.diff(REGIME_WINDOW)
s5_diff5 = s5tw.diff(REGIME_WINDOW)
sv5_diff5 = sv5tw.diff(REGIME_WINDOW)

# Build lookup dicts (date → diff) — keys normalized to datetime.date
vix_d5 = {d.date() if hasattr(d, "date") else d: float(v) for d, v in vix_diff5.items() if not pd.isna(v)}
s5_d5 = {d.date() if hasattr(d, "date") else d: float(v) for d, v in s5_diff5.items() if not pd.isna(v)}
sv5_d5 = {d.date() if hasattr(d, "date") else d: float(v) for d, v in sv5_diff5.items() if not pd.isna(v)}

# Also velocity diff(3) for SV5 quadrant analysis
s5_vel = s5tw.diff(3)
sv5_vel = sv5tw.diff(3)
s5v_dict = {d.date() if hasattr(d, "date") else d: float(v) for d, v in s5_vel.items() if not pd.isna(v)}
sv5v_dict = {d.date() if hasattr(d, "date") else d: float(v) for d, v in sv5_vel.items() if not pd.isna(v)}

# ── Zigzag legs (3 scales) ──
print("── Cargando zigzag legs ──")
legs25 = repo.get_confirmed_legs("SPY", "zz25")
legs50 = repo.get_confirmed_legs("SPY", "zz50")
legs75 = repo.get_confirmed_legs("SPY", "zz75")

print(f"  zz25: {len(legs25)} legs")
print(f"  zz50: {len(legs50)} legs")
print(f"  zz75: {len(legs75)} legs")

# ── Cascade targets (authoritative: same-type ±3d) ──
starts50_min = set(pd.to_datetime(l.start_timestamp).date() for l in legs50 if l.start_type == "MIN")
starts50_max = set(pd.to_datetime(l.start_timestamp).date() for l in legs50 if l.start_type == "MAX")
starts75_min = set(pd.to_datetime(l.start_timestamp).date() for l in legs75 if l.start_type == "MIN")
starts75_max = set(pd.to_datetime(l.start_timestamp).date() for l in legs75 if l.start_type == "MAX")

# ═══════════════════════════════════════════════════════════════════════════════
# BUILD OBSERVATIONS — classify regime at each zz25 pivot
# ═══════════════════════════════════════════════════════════════════════════════

df_rows = []
for l in legs25:
    pd_ = pd.to_datetime(l.start_timestamp).date()

    # Get indicator diffs at pivot date
    vd = vix_d5.get(pd_)
    sd = s5_d5.get(pd_)

    if vd is None or sd is None:
        continue  # missing indicator data

    # ── Classify regime ──
    vix_up = vd > 0
    s5_up = sd > 0  # S5 mantiene/se recupera (no colapsa)

    if vix_up and s5_up:
        regime = "MIEDO_SIN_VENTA"    # VIX↑, S5 mantiene (breadth expanding despite fear)
    elif vix_up and not s5_up:
        regime = "MIEDO_CON_VENTA"    # VIX↑, S5 colapsa (breadth collapsing with fear)
    elif not vix_up and s5_up:
        regime = "CALMA_CON_AMPLITUD"  # VIX↓, S5 se recupera
    else:
        regime = "CALMA_SIN_CONVICCION"  # VIX↓, S5 no reacciona

    # ── SV5 quadrant (diff(3) at pivot) ──
    s5v = s5v_dict.get(pd_, 0.0)
    sv5v = sv5v_dict.get(pd_, 0.0)
    s5v_up = 1 if s5v > 0 else 0
    sv5v_up = 1 if sv5v > 0 else 0
    sv5_quad = f"S5{'↑' if s5v_up else '↓'}SV5{'↑' if sv5v_up else '↓'}"

    # ── Zigzag targets ──
    start_type = l.start_type
    leg_bear = 1 if start_type == "MAX" else 0  # MAX→bear (down leg), MIN→bull

    # Cascade zz25→zz50: same-type zz50 leg starts ±3d
    cascade_50 = int(any(
        pd_ + timedelta(days=i) in (starts50_max if start_type == "MAX" else starts50_min)
        for i in range(-3, 4)
    ))

    # Cascade zz25→zz75: same-type zz75 leg starts ±3d
    cascade_75 = int(any(
        pd_ + timedelta(days=i) in (starts75_max if start_type == "MAX" else starts75_min)
        for i in range(-3, 4)
    ))

    # ── Fixed-horizon forward returns ──
    spy_idx = spy_date_to_idx.get(pd_)
    fwd_ret = {}
    if spy_idx is not None:
        entry_price = spy_values[spy_idx]
        for h in [5, 10, 20, 40]:
            fwd_idx = spy_idx + h
            if fwd_idx < len(spy_values):
                fwd_ret[h] = (spy_values[fwd_idx] / entry_price - 1.0)
            else:
                fwd_ret[h] = np.nan

    df_rows.append({
        "pivot_date": pd_,
        "start_type": start_type,
        "leg_bear": leg_bear,
        "cascade_50": cascade_50,
        "cascade_75": cascade_75,
        "vix_diff5": vd,
        "s5_diff5": sd,
        "sv5_diff5": sv5_d5.get(pd_, 0.0),
        "regime": regime,
        "vix_up": int(vix_up),
        "s5_up": int(s5_up),
        "s5_vel": s5v,
        "sv5_vel": sv5v,
        "sv5_quad": sv5_quad,
        "fwd_5": fwd_ret.get(5, np.nan),
        "fwd_10": fwd_ret.get(10, np.nan),
        "fwd_20": fwd_ret.get(20, np.nan),
        "fwd_40": fwd_ret.get(40, np.nan),
    })

df = pd.DataFrame(df_rows)

# Filter to common indicator range (post-1999)
print(f"\n  Total zz25 pivots: {len(legs25)}")
print(f"  Pivots con VIX+S5+SV5 data: {len(df)}")
print(f"  Date range: {df['pivot_date'].min()} → {df['pivot_date'].max()}")
print()

# ═══════════════════════════════════════════════════════════════════════════════
# UNCONDITIONAL BASELINES — alternation by construction
# ═══════════════════════════════════════════════════════════════════════════════

bear_mean, bear_lo, bear_hi, bear_n = boot_ci(df["leg_bear"])
c50_mean, c50_lo, c50_hi, c50_n = boot_ci(df["cascade_50"])
c75_mean, c75_lo, c75_hi, c75_n = boot_ci(df["cascade_75"])

print("═══ BASELINES INCONDICIONALES (todos los pivotes zz25) ═══")
print(f"  ALTERNACIÓN: zigzag alterna MIN→MAX→MIN por construcción → p(bear) ≈ 50%")
print(f"  %bear (próximo leg bajista):  {pct_fmt(bear_mean, bear_lo, bear_hi)}  N={bear_n}")
print(f"  %cascade_50 (→ zz50 ±3d):     {pct_fmt(c50_mean, c50_lo, c50_hi)}  N={c50_n}")
print(f"  %cascade_75 (→ zz75 ±3d):     {pct_fmt(c75_mean, c75_lo, c75_hi)}  N={c75_n}")
print()

# Forward return baselines
for h in [5, 10, 20, 40]:
    arr = df[f"fwd_{h}"].dropna().values
    ret_m, ret_lo, ret_hi, ret_n = boot_ci(arr)
    wr_m, wr_lo, wr_hi, wr_n = boot_ci_proportion(arr > 0)
    print(f"  SPY fwd {h:2d}d incondicional: ret={ret_fmt(ret_m, ret_lo, ret_hi)}  WR={wr_m:.1%} [{wr_lo:.1%}, {wr_hi:.1%}]  N={ret_n}")

print()
print("  ⚠  La dirección del próximo leg zigzag NO es predicción — es alternación estructural.")
print("  El baseline de %bear ≈ 50% refleja que MIN y MAX alternan.")
print("  El baseline de cascade_50 ≈ 40% es la tasa de continuación estructural.")
print()

# ═══════════════════════════════════════════════════════════════════════════════
# 4 DIVERGENCE REGIMES
# ═══════════════════════════════════════════════════════════════════════════════

REGIMES = ["MIEDO_SIN_VENTA", "MIEDO_CON_VENTA", "CALMA_CON_AMPLITUD", "CALMA_SIN_CONVICCION"]
REGIME_LABELS = {
    "MIEDO_SIN_VENTA":    "VIX↑ + S5 mantiene (miedo sin venta real → ¿sobre-reacción?)",
    "MIEDO_CON_VENTA":    "VIX↑ + S5 colapsa (miedo con venta real → ¿confirmado?)",
    "CALMA_CON_AMPLITUD": "VIX↓ + S5 se recupera (calma real con amplitud → tendencia sana)",
    "CALMA_SIN_CONVICCION": "VIX↓ + S5 no reacciona (calma sin convicción → deriva)",
}

# Summary container
regime_results = {}

print("═" * 90)
print("  4 REGÍMENES DE DIVERGENCIA — métricas zigzag + horizontes fijos")
print("═" * 90)

for regime in REGIMES:
    sub = df[df["regime"] == regime]
    n = len(sub)
    pct = n / len(df)
    rr = {"N": n, "pct": pct, "label": REGIME_LABELS[regime]}

    print(f"\n{'━' * 90}")
    print(f"  {regime} — {REGIME_LABELS[regime]}")
    print(f"  N = {n}  ({pct:.1%} de pivotes)")
    print(f"{'━' * 90}")

    # ── ZIGZAG METRICS ──
    b_m, b_lo, b_hi, b_n = boot_ci(sub["leg_bear"])
    c50_m, c50_lo, c50_hi, c50_n = boot_ci(sub["cascade_50"])
    c75_m, c75_lo, c75_hi, c75_n = boot_ci(sub["cascade_75"])

    b_diff, b_dlo, b_dhi = boot_diff_ci(sub["leg_bear"], df["leg_bear"])
    c50_diff, c50_dlo, c50_dhi = boot_diff_ci(sub["cascade_50"], df["cascade_50"])
    c75_diff, c75_dlo, c75_dhi = boot_diff_ci(sub["cascade_75"], df["cascade_75"])

    rr["zigzag"] = {
        "bear_mean": b_m, "bear_ci": [b_lo, b_hi],
        "c50_mean": c50_m, "c50_ci": [c50_lo, c50_hi],
        "c75_mean": c75_m, "c75_ci": [c75_lo, c75_hi],
        "Δbear": b_diff, "Δbear_ci": [b_dlo, b_dhi],
        "Δc50": c50_diff, "Δc50_ci": [c50_dlo, c50_dhi],
        "Δc75": c75_diff, "Δc75_ci": [c75_dlo, c75_dhi],
    }

    print(f"  ── DIRECCIÓN ZIGZAG (próximo leg) ──")
    print(f"  %bear (próx leg bajista):  {pct_fmt(b_m, b_lo, b_hi)}")
    print(f"    vs baseline ({bear_mean:.1%}):  Δ={b_diff:+.1%}  CI95=[{b_dlo:+.1%}, {b_dhi:+.1%}]")

    print(f"  ── CASCADA (misma escala) ──")
    print(f"  %cascade_50 (→ zz50):  {pct_fmt(c50_m, c50_lo, c50_hi)}")
    print(f"    vs baseline ({c50_mean:.1%}):  Δ={c50_diff:+.1%}  CI95=[{c50_dlo:+.1%}, {c50_dhi:+.1%}]")
    print(f"  %cascade_75 (→ zz75):  {pct_fmt(c75_m, c75_lo, c75_hi)}")
    print(f"    vs baseline ({c75_mean:.1%}):  Δ={c75_diff:+.1%}  CI95=[{c75_dlo:+.1%}, {c75_dhi:+.1%}]")

    # ── FIXED HORIZONS ──
    rr["fixed"] = {}
    print(f"\n  ── HORIZONTES FIJOS (SPY forward) ──")
    print(f"  {'Horizonte':<10} {'Retorno':>22} {'Win Rate':>22} {'Profit Factor':>14} {'Kelly':>8} {'Wins P50':>10} {'Losses P50':>10} {'Wipeouts>20%':>14}")
    print(f"  {'─'*10} {'─'*22} {'─'*22} {'─'*14} {'─'*8} {'─'*10} {'─'*10} {'─'*14}")

    for h in [5, 10, 20, 40]:
        arr = sub[f"fwd_{h}"].dropna().values
        if len(arr) < 5:
            print(f"  {f'{h}d':<10} {'N<5, sin CI':>22}")
            rr["fixed"][h] = {"N": len(arr), "insufficient": True}
            continue

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

        w_p50 = np.percentile(wins, 50) if len(wins) > 1 else (np.mean(wins) if len(wins) == 1 else np.nan)
        l_p50 = np.percentile(losses, 50) if len(losses) > 1 else (np.mean(losses) if len(losses) == 1 else np.nan)

        rr["fixed"][h] = {
            "N": ret_n,
            "ret_mean": ret_m, "ret_ci": [ret_lo, ret_hi],
            "wr": wr_m, "wr_ci": [wr_lo, wr_hi],
            "profit_factor": pf,
            "kelly": float(kelly) if not np.isnan(kelly) else None,
            "wins": {
                "n": len(wins),
                "p50": float(w_p50) if not np.isnan(w_p50) else None,
                "p25": float(np.percentile(wins, 25)) if len(wins) >= 4 else None,
                "p75": float(np.percentile(wins, 75)) if len(wins) >= 4 else None,
                "p90": float(np.percentile(wins, 90)) if len(wins) >= 10 else None,
                "max": float(np.max(wins)) if len(wins) > 0 else None,
            },
            "losses": {
                "n": len(losses),
                "p50": float(l_p50) if not np.isnan(l_p50) else None,
                "p25": float(np.percentile(losses, 25)) if len(losses) >= 4 else None,
                "p75": float(np.percentile(losses, 75)) if len(losses) >= 4 else None,
                "p90": float(np.percentile(losses, 90)) if len(losses) >= 10 else None,
                "min": float(np.min(losses)) if len(losses) > 0 else None,
            },
            "wipeouts_n": len(wipeouts),
            "wipeouts_pct": len(wipeouts) / len(arr) * 100,
        }

        w_str = f"P50={w_p50:+.1%}" if not (np.isnan(w_p50) if isinstance(w_p50, float) else False) else "n/a"
        l_str = f"P50={l_p50:+.1%}" if not (np.isnan(l_p50) if isinstance(l_p50, float) else False) else "n/a"
        print(f"  {f'{h}d':<10} {ret_fmt(ret_m, ret_lo, ret_hi):>22}  "
              f"WR={wr_m:.1%} [{wr_lo:.1%}, {wr_hi:.1%}]  "
              f"PF={pf:.2f}  K={kelly:+.2f}  "
              f"{w_str:>10}  {l_str:>10}  {len(wipeouts)} ({len(wipeouts)/len(arr)*100:.0f}%)")

    regime_results[regime] = rr

# ═══════════════════════════════════════════════════════════════════════════════
# KEY QUESTIONS
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 90}")
print("  PREGUNTAS CLAVE")
print(f"{'═' * 90}")

# Q1: ¿Cuando VIX sube y S5 NO colapsa, el mercado rebota (sobre-reacción)?
print(f"\n  ── Q1: ¿VIX↑ + S5 NO colapsa → rebote (sobre-reacción)? ──")
msv = regime_results["MIEDO_SIN_VENTA"]
mcv = regime_results["MIEDO_CON_VENTA"]

print(f"  MIEDO SIN VENTA (N={msv['N']}):")
for h in [5, 10, 20, 40]:
    if "insufficient" not in msv["fixed"][h]:
        fh = msv["fixed"][h]
        print(f"    {h:2d}d: ret={fh['ret_mean']:+.2%} [{fh['ret_ci'][0]:+.2%}, {fh['ret_ci'][1]:+.2%}]  "
              f"WR={fh['wr']:.1%}  PF={fh['profit_factor']:.2f}  Kelly={fh['kelly']:+.2f}")

print(f"\n  MIEDO CON VENTA (N={mcv['N']}):")
for h in [5, 10, 20, 40]:
    if "insufficient" not in mcv["fixed"][h]:
        fh = mcv["fixed"][h]
        print(f"    {h:2d}d: ret={fh['ret_mean']:+.2%} [{fh['ret_ci'][0]:+.2%}, {fh['ret_ci'][1]:+.2%}]  "
              f"WR={fh['wr']:.1%}  PF={fh['profit_factor']:.2f}  Kelly={fh['kelly']:+.2f}")

# Q2: ¿Cuando VIX sube y S5 colapsa, sigue cayendo?
print(f"\n  ── Q2: ¿VIX↑ + S5 colapsa → sigue cayendo (venta real)? ──")
print(f"  Dirección zigzag: %bear={mcv['zigzag']['bear_mean']:.1%} vs baseline {bear_mean:.1%}")
print(f"  Si %bear >> 50% → el próximo leg zigzag confirma la venta.")
print(f"  Si %bear ≈ 50% → no hay señal direccional clara en zigzag.")

# Q3: SV5 distinguishes?
print(f"\n  ── Q3: ¿SV5 (volumen) distingue los casos ambiguos? ──")
AMBIGUOUS_REGIMES = ["MIEDO_SIN_VENTA", "CALMA_SIN_CONVICCION"]

for regime in AMBIGUOUS_REGIMES:
    sub = df[df["regime"] == regime]
    n = len(sub)
    print(f"\n  {regime} (N={n}):")
    print(f"  {'SV5 sub-grupo':<20} {'N':>5} {'fwd 10d':>22} {'fwd 20d':>22} {'%bear zigzag':>20} {'%cascade_50':>18}")

    for sv5_up_flag, sv5_label in [(True, "SV5↑ (vol expandiendo)"), (False, "SV5↓ (vol contrayendo)")]:
        sv5_sub = sub[sub["sv5_vel"] > 0] if sv5_up_flag else sub[sub["sv5_vel"] <= 0]
        sv_n = len(sv5_sub)
        if sv_n < 5:
            print(f"  {sv5_label:<20} {sv_n:>5}  N<5, sin CI")
            continue

        ret10_m, ret10_lo, ret10_hi, _ = boot_ci(sv5_sub["fwd_10"].dropna().values)
        ret20_m, ret20_lo, ret20_hi, _ = boot_ci(sv5_sub["fwd_20"].dropna().values)
        bear_m, bear_lo, bear_hi, _ = boot_ci(sv5_sub["leg_bear"])
        c50_m, c50_lo, c50_hi, _ = boot_ci(sv5_sub["cascade_50"])

        print(f"  {sv5_label:<20} {sv_n:>5}  {ret_fmt(ret10_m, ret10_lo, ret10_hi):>22}  "
              f"{ret_fmt(ret20_m, ret20_lo, ret20_hi):>22}  "
              f"{pct_fmt(bear_m, bear_lo, bear_hi):>20}  {pct_fmt(c50_m, c50_lo, c50_hi):>18}")

    # Bootstrap difference SV5↑ vs SV5↓
    sv5_up_sub = sub[sub["sv5_vel"] > 0]
    sv5_dn_sub = sub[sub["sv5_vel"] <= 0]
    if len(sv5_up_sub) >= 5 and len(sv5_dn_sub) >= 5:
        for metric, col in [("fwd_10d", "fwd_10"), ("fwd_20d", "fwd_20"), ("%bear", "leg_bear"), ("%c50", "cascade_50")]:
            diff, dlo, dhi = boot_diff_ci(sv5_up_sub[col].dropna().values, sv5_dn_sub[col].dropna().values)
            sig = "***" if (dlo > 0 or dhi < 0) else "   "
            if col in ["fwd_10", "fwd_20"]:
                print(f"    ΔSV5↑−SV5↓ {metric}: {diff:+.2%}  CI95=[{dlo:+.2%}, {dhi:+.2%}] {sig}")
            else:
                print(f"    ΔSV5↑−SV5↓ {metric}: {diff:+.1%}  CI95=[{dlo:+.1%}, {dhi:+.1%}] {sig}")

# Also check S5×SV5 quadrant within each regime
print(f"\n  ── Q3b: S5×SV5 cuadrantes (diff(3)) dentro de cada régimen ──")
for regime in REGIMES:
    sub = df[df["regime"] == regime]
    n = len(sub)
    print(f"\n  {regime} (N={n}):")
    for quad in ["S5↑SV5↑", "S5↑SV5↓", "S5↓SV5↑", "S5↓SV5↓"]:
        qsub = sub[sub["sv5_quad"] == quad]
        qn = len(qsub)
        if qn < 5:
            continue
        ret20_m, ret20_lo, ret20_hi, _ = boot_ci(qsub["fwd_20"].dropna().values)
        wr20_m, wr20_lo, wr20_hi, _ = boot_ci_proportion((qsub["fwd_20"].dropna().values > 0))
        print(f"    {quad:<12} N={qn:>4}  fwd20d={ret_fmt(ret20_m, ret20_lo, ret20_hi)}  WR={wr20_m:.1%} [{wr20_lo:.1%}, {wr20_hi:.1%}]")

# ═══════════════════════════════════════════════════════════════════════════════
# RECONCILIATION: zigzag vs fixed horizons
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 90}")
print("  RECONCILIACIÓN: zigzag vs horizontes fijos")
print(f"{'═' * 90}")

print(f"""
  El zigzag mide DIRECCIÓN ESTRUCTURAL (la reversión confirmada cuando
  el precio cruza el umbral de 2.5/5/7.5%). Esto PUEDE tomar >40 días.

  Los horizontes fijos miden RETORNO ACUMULADO en plazos concretos.

  SI CONTRADICEN:
  - Zigzag dice \"próximo leg alcista\" pero fwd 20d es negativo →
    la reversión existe pero toma >20d en materializarse.
  - Zigzag dice \"próximo leg bajista\" pero fwd 20d es positivo →
    la caída estructural viene, pero el mercado sube primero (bear trap).

  AMBAS MÉTRICAS JUNTAS cuentan la verdad. Una sola MIENTE.
""")

# Compare zigzag direction vs fixed horizon direction per regime
print("  ── COMPARACIÓN DIRECCIÓN: zigzag %bear vs fwd 20d sign ──")
print(f"  {'Regime':<25} {'%bear zigzag':>20} {'fwd 20d ret':>20} {'fwd 20d WR':>20} {'¿Concuerdan?':>20}")
print(f"  {'─'*25} {'─'*20} {'─'*20} {'─'*20} {'─'*20}")

for regime in REGIMES:
    rr = regime_results[regime]
    b = rr["zigzag"]["bear_mean"]
    f20 = rr["fixed"].get(20, {})
    if "insufficient" not in f20:
        ret20 = f20["ret_mean"]
        wr20 = f20["wr"]
        # Zigzag: %bear close to 50% = no signal. >55% = bearish. <45% = bullish.
        # Fixed: ret > 0 = bullish, ret < 0 = bearish.
        # "Concuerdan" if both bearish (bear>55%, ret<0) or both bullish (bear<45%, ret>0)
        zig_bearish = b > 0.53
        zig_bullish = b < 0.47
        fwd_bearish = ret20 < 0
        agree = (zig_bearish and fwd_bearish) or (zig_bullish and not fwd_bearish) or (not zig_bearish and not zig_bullish)
        agree_str = "✓ sí" if agree else "✗ NO — timing"
        print(f"  {regime:<25} {pct_fmt(b, rr['zigzag']['bear_ci'][0], rr['zigzag']['bear_ci'][1]):>20}  "
              f"{ret_fmt(ret20, f20['ret_ci'][0], f20['ret_ci'][1]):>20}  "
              f"WR={wr20:.1%} [{f20['wr_ci'][0]:.1%}, {f20['wr_ci'][1]:.1%}]  "
              f"{agree_str:>20}")
    else:
        print(f"  {regime:<25} {'N<5, sin CI':>20}")

# ═══════════════════════════════════════════════════════════════════════════════
# SENSITIVITY: diff(3) vs diff(5) regime window
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 90}")
print("  SENSIBILIDAD: ventana de régimen diff(3) vs diff(5)")
print(f"{'═' * 90}")

# Reclassify with diff(3)
vix_diff3 = vix.diff(3)
s5_diff3 = s5tw.diff(3)
vix_d3 = {d.date() if hasattr(d, "date") else d: float(v) for d, v in vix_diff3.items() if not pd.isna(v)}
s5_d3 = {d.date() if hasattr(d, "date") else d: float(v) for d, v in s5_diff3.items() if not pd.isna(v)}

df3_rows = []
for l in legs25:
    pd_ = pd.to_datetime(l.start_timestamp).date()
    vd = vix_d3.get(pd_)
    sd = s5_d3.get(pd_)
    if vd is None or sd is None:
        continue
    vix_up = vd > 0
    s5_up = sd > 0
    if vix_up and s5_up:
        regime = "MIEDO_SIN_VENTA"
    elif vix_up and not s5_up:
        regime = "MIEDO_CON_VENTA"
    elif not vix_up and s5_up:
        regime = "CALMA_CON_AMPLITUD"
    else:
        regime = "CALMA_SIN_CONVICCION"
    df3_rows.append({"pivot_date": pd_, "regime": regime})

df3 = pd.DataFrame(df3_rows)
print(f"  Pivotes con diff(3): {len(df3)}")
for regime in REGIMES:
    d5_n = len(df[df["regime"] == regime])
    d3_n = len(df3[df3["regime"] == regime])
    d5_pct = d5_n / len(df) * 100
    d3_pct = d3_n / len(df3) * 100
    print(f"  {regime:<25} diff(5): N={d5_n:>4} ({d5_pct:>4.1f}%)  diff(3): N={d3_n:>4} ({d3_pct:>4.1f}%)  "
          f"Δ={d3_pct-d5_pct:+.1f}pp")

# ═══════════════════════════════════════════════════════════════════════════════
# CHI-SQUARE tests
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 90}")
print("  CHI-SQUARE: independencia régimen × cascade / dirección")
print(f"{'═' * 90}")

for target, col in [("cascade_50", "cascade_50"), ("cascade_75", "cascade_75"), ("leg_bear", "leg_bear")]:
    ct = pd.crosstab(df["regime"], df[col])
    chi2, p, dof, _ = chi2_contingency(ct)
    sig = "SIGNIFICATIVO" if p < 0.05 else "no significativo"
    print(f"  régimen × {target}: χ²={chi2:.2f}, p={p:.4f}, dof={dof} → {sig}")

# ═══════════════════════════════════════════════════════════════════════════════
# JSON OUTPUT
# ═══════════════════════════════════════════════════════════════════════════════

def safe(v):
    if isinstance(v, (np.floating,)):
        return float(v) if not np.isnan(v) else None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, float) and np.isnan(v):
        return None
    return v

output = {
    "meta": {
        "script": "research/04_conjuncion_multi_estacion/s5_vix_divergencia.py",
        "description": "Divergencia VIX×S5 — sentir vs hacer. 4 regímenes medidos a 3 escalas zigzag + 4 horizontes fijos.",
        "regime_window": f"diff({REGIME_WINDOW})",
        "VIX_definition": "diff(5) of VIX close",
        "S5_definition": "diff(5) of S5TW (% stocks above 20-DMA)",
        "SV5_definition": "diff(3) of SV5TW (% stocks with expanding volume)",
        "targets": ["leg_bear (zigzag direction)", "cascade_50 (±3d zz50)", "cascade_75 (±3d zz75)", "SPY fwd 5/10/20/40d"],
        "bootstrap": "3000 iterations, CI95",
        "total_pivots": int(len(legs25)),
        "pivots_with_data": int(len(df)),
        "date_range": f"{df['pivot_date'].min()} → {df['pivot_date'].max()}",
    },
    "baseline": {
        "p_bear": safe(bear_mean), "p_bear_ci95": [safe(bear_lo), safe(bear_hi)], "N": bear_n,
        "p_cascade_50": safe(c50_mean), "p_c50_ci95": [safe(c50_lo), safe(c50_hi)], "N": c50_n,
        "p_cascade_75": safe(c75_mean), "p_c75_ci95": [safe(c75_lo), safe(c75_hi)], "N": c75_n,
    },
    "regimes": {},
    "sv5_discrimination": {},
    "sensitivity_diff3_vs_diff5": {},
}

for regime in REGIMES:
    rr = regime_results[regime]
    regime_out = {
        "label": REGIME_LABELS[regime],
        "N": rr["N"],
        "pct": rr["pct"],
        "zigzag": {
            "p_bear": safe(rr["zigzag"]["bear_mean"]),
            "p_bear_ci95": [safe(rr["zigzag"]["bear_ci"][0]), safe(rr["zigzag"]["bear_ci"][1])],
            "Δbear_vs_baseline": safe(rr["zigzag"]["Δbear"]),
            "Δbear_ci95": [safe(rr["zigzag"]["Δbear_ci"][0]), safe(rr["zigzag"]["Δbear_ci"][1])],
            "p_cascade_50": safe(rr["zigzag"]["c50_mean"]),
            "p_c50_ci95": [safe(rr["zigzag"]["c50_ci"][0]), safe(rr["zigzag"]["c50_ci"][1])],
            "Δc50_vs_baseline": safe(rr["zigzag"]["Δc50"]),
            "Δc50_ci95": [safe(rr["zigzag"]["Δc50_ci"][0]), safe(rr["zigzag"]["Δc50_ci"][1])],
            "p_cascade_75": safe(rr["zigzag"]["c75_mean"]),
            "p_c75_ci95": [safe(rr["zigzag"]["c75_ci"][0]), safe(rr["zigzag"]["c75_ci"][1])],
            "Δc75_vs_baseline": safe(rr["zigzag"]["Δc75"]),
            "Δc75_ci95": [safe(rr["zigzag"]["Δc75_ci"][0]), safe(rr["zigzag"]["Δc75_ci"][1])],
        },
        "fixed_horizons": {},
    }
    for h in [5, 10, 20, 40]:
        fh = rr["fixed"].get(h, {})
        if "insufficient" in fh:
            regime_out["fixed_horizons"][h] = {"N": fh["N"], "insufficient": True}
        else:
            regime_out["fixed_horizons"][h] = {
                "N": fh["N"],
                "ret_mean": safe(fh["ret_mean"]),
                "ret_ci95": [safe(fh["ret_ci"][0]), safe(fh["ret_ci"][1])],
                "win_rate": safe(fh["wr"]),
                "wr_ci95": [safe(fh["wr_ci"][0]), safe(fh["wr_ci"][1])],
                "profit_factor": safe(fh["profit_factor"]),
                "kelly": safe(fh["kelly"]),
                "wins": {k: safe(v) for k, v in fh["wins"].items()},
                "losses": {k: safe(v) for k, v in fh["losses"].items()},
                "wipeouts_gt_20pct": {"n": fh["wipeouts_n"], "pct": safe(fh["wipeouts_pct"])},
            }
    output["regimes"][regime] = regime_out

# SV5 discrimination
for regime in AMBIGUOUS_REGIMES:
    sub = df[df["regime"] == regime]
    sv5_up = sub[sub["sv5_vel"] > 0]
    sv5_dn = sub[sub["sv5_vel"] <= 0]
    output["sv5_discrimination"][regime] = {
        "SV5_up": {"N": len(sv5_up)},
        "SV5_down": {"N": len(sv5_dn)},
    }
    if len(sv5_up) >= 5 and len(sv5_dn) >= 5:
        for metric, col in [("fwd_10d", "fwd_10"), ("fwd_20d", "fwd_20"), ("p_bear", "leg_bear"), ("p_cascade_50", "cascade_50")]:
            diff, dlo, dhi = boot_diff_ci(sv5_up[col].dropna().values, sv5_dn[col].dropna().values)
            output["sv5_discrimination"][regime][f"Δ_{metric}"] = safe(diff)
            output["sv5_discrimination"][regime][f"Δ_{metric}_ci95"] = [safe(dlo), safe(dhi)]

# Sensitivity
for regime in REGIMES:
    d5_n = len(df[df["regime"] == regime])
    d3_n = len(df3[df3["regime"] == regime])
    output["sensitivity_diff3_vs_diff5"][regime] = {
        "diff5_N": d5_n, "diff5_pct": d5_n / len(df),
        "diff3_N": d3_n, "diff3_pct": d3_n / len(df3),
        "delta_pct_pp": (d3_n / len(df3) - d5_n / len(df)) * 100,
    }

json_path = Path("/root/botero-trade/data/research/s5_vix_divergencia_results.json")
with open(json_path, "w") as f:
    json.dump(output, f, indent=2)

print(f"\n{'═' * 90}")
print(f"  RESULTADOS guardados: {json_path}")
print(f"{'═' * 90}")
print("  FIN — DIVERGENCIA VIX×S5")
print(f"{'═' * 90}")