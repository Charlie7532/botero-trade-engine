#!/usr/bin/env python3
"""
ESTUDIO DE DIVERGENCIA S5 × 10 ESTACIONES — Botero Trade
=========================================================
S5 = S5TW = price breadth (lo que el mercado HACE — realidad).
Las otras 10 estaciones miden otras dimensiones (miedo, posicionamiento, macro...).

OBJETIVO: encontrar las DIVERGENCIAS entre S5 (realidad) y cada estación que
ADVIERTAN un cambio: piso, techo, reversión, cuando el mercado "ya no sigue".

HIPÓTESIS (a validar con datos, NO a asumir):
  - S5 diverge de VIX          -> miedo no respaldado por acción -> reversión
  - S5 diverge de FG           -> sentimiento no respaldado por breadth -> techo/piso
  - S5 diverge de CREDIT/YIELD -> amplitud no confirma régimen macro
  - S5 diverge de DXY          -> flujos internacionales vs participación local

DEFINICIÓN MECÁNICA DE DIVERGENCIA (signo de D2 = diff(3d)):
  - S5↑ + estación↑  = convergencia (misma dirección)
  - S5↓ + estación↓  = convergencia (misma dirección)
  - S5↑ + estación↓  = DIVERGENCIA (direcciones opuestas)
  - S5↓ + estación↑  = DIVERGENCIA (direcciones opuestas)

MÉTODO (estadística COMPLETA — pitfall #74, #66, #51):
  1. Correlación raw / D2 (diff3) / D3 (std2/std10) — Pearson + Spearman.
  2. Divergencia vs convergencia a HORIZONTES FIJOS 5/10/20/40d (entrada en barra,
     de-cluster ≥10 días, forward SPY, wins/losses separados, CI95 bootstrap 2000).
  3. Divergencia en PIVOTES ZIGZAG 2.5/5/7.5 (siguiente-leg direccional + cascade),
     desglosado por MIN (piso) vs MAX (techo).
  4. ¿Qué divergencia advierte piso/techo/reversión?

Dato mata relato. Todo medido, nada asumido.
"""

import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

# ─── Config ───────────────────────────────────────────────────────────────────
FW_HORIZONS = [5, 10, 20, 40]
N_BOOT = 2000
SEED = 42
MIN_SPACING = 10           # trading days between signals
WIPEOUT_THRESHOLD = -0.20  # -20% forward return = wipeout
ZIG_SCALES = [("zz25", 2.5), ("zz50", 5.0), ("zz75", 7.5)]

STATIONS = [
    ("VIX", "VIX"),
    ("VVIX", "VVIX"),
    ("PCR", "CBOE_PCR"),
    ("FG", "FG"),
    ("SV5T", "SV5_TURBULENCE"),
    ("SKEW", "SKEW"),
    ("CREDIT", "CREDIT_RATIO"),
    ("YIELD", "YIELD_SPREAD"),
    ("ROTATION", "ROTATION_INDEX"),
    ("DXY", "DXY"),
]
S5_TICKER = "S5TW"


# ─── Bootstrap helpers ────────────────────────────────────────────────────────

def boot_ci(arr, ci=95, n_boot=N_BOOT, seed=SEED):
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


def boot_prop(wins_bool, ci=95, n_boot=N_BOOT, seed=SEED):
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


def boot_diff(a, b, ci=95, n_boot=N_BOOT, seed=SEED):
    """Bootstrap CI + P(diff>0) for difference of means (a - b)."""
    a = np.asarray(a, float); a = a[~np.isnan(a)]
    b = np.asarray(b, float); b = b[~np.isnan(b)]
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


def kelly(wr, avg_win, avg_loss):
    if avg_loss <= 0:
        return float("inf")
    wl = avg_win / avg_loss
    if wl <= 0:
        return 0.0
    return max(0.0, wr - (1 - wr) / wl)


def compute_d2_d3(s):
    d2 = s.diff(3)
    s2 = s.rolling(2).std()
    s10 = s.rolling(10).std()
    d3 = (s2 / s10).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    return d2, d3


def normalize(s):
    s = s.copy()
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s


# ─── Load data ────────────────────────────────────────────────────────────────
print("═" * 90)
print("  ESTUDIO DE DIVERGENCIA S5 × 10 ESTACIONES")
print("═" * 90)
store = TimescaleDataStore()

spy_raw = store.load_bars("SPY", "1d")["close"].copy()
spy = normalize(spy_raw)
spy_dates = list(spy.index)
spy_values = spy.values
spy_date_to_idx = {d: i for i, d in enumerate(spy_dates)}
print(f"  SPY: {spy_dates[0].date()} → {spy_dates[-1].date()} ({len(spy)} bars)")


def load_ticker(t):
    raw = store.load_bars(t, "1d")["close"].copy()
    return normalize(raw)


s5 = load_ticker(S5_TICKER)
series = {"S5": s5}
for name, t in STATIONS:
    series[name] = load_ticker(t)

repo = ZigzagLegRepository(store)
legs_by_scale = {sc: repo.get_confirmed_legs("SPY", sc) for sc, _ in ZIG_SCALES}
store.close()

# ─── D2 / D3 for every series ─────────────────────────────────────────────────
d2 = {}
d3 = {}
for name, s in series.items():
    d2[name], d3[name] = compute_d2_d3(s)

# ─── Zigzag pivot tables (per scale) ──────────────────────────────────────────
zig_data = {}
for sc, _ in ZIG_SCALES:
    legs = legs_by_scale[sc]
    nxt_sc = {"zz25": "zz50", "zz50": "zz75", "zz75": None}[sc]
    df = pd.DataFrame([
        {
            "start_timestamp": l.start_timestamp,
            "start_type": l.start_type,
            "prev_leg_return": l.prev_leg_return,
        }
        for l in legs
    ])
    df["pivot_date"] = pd.to_datetime(df["start_timestamp"]).dt.date
    df["is_min"] = (df["start_type"] == "MIN").astype(int)
    df["next_bear"] = (df["start_type"] == "MAX").astype(int)
    if nxt_sc is not None:
        nxt_legs = legs_by_scale[nxt_sc]
        starts_min = set(pd.to_datetime(l.start_timestamp).date() for l in nxt_legs if l.start_type == "MIN")
        starts_max = set(pd.to_datetime(l.start_timestamp).date() for l in nxt_legs if l.start_type == "MAX")
        df["cascade"] = df.apply(
            lambda r: int(any(
                r["pivot_date"] + pd.Timedelta(days=i) in (starts_max if r["start_type"] == "MAX" else starts_min)
                for i in range(-3, 4)
            )),
            axis=1,
        )
    else:
        df["cascade"] = np.nan
    zig_data[sc] = df


# ─── Day-by-day aligned frame (per station) ───────────────────────────────────
def align_pair(name):
    st = series[name]
    common = sorted(set(s5.index) & set(st.index) & set(spy.index))
    rows = []
    for d in common:
        s5_d2v = d2["S5"].get(d, np.nan)
        st_d2v = d2[name].get(d, np.nan)
        if pd.isna(s5_d2v) or pd.isna(st_d2v):
            continue
        rows.append({
            "date": d,
            "spy_idx": spy_date_to_idx.get(d),
            "s5_raw": s5.get(d, np.nan),
            "st_raw": st.get(d, np.nan),
            "s5_d2": s5_d2v,
            "st_d2": st_d2v,
            "s5_d3": d3["S5"].get(d, np.nan),
            "st_d3": d3[name].get(d, np.nan),
        })
    df = pd.DataFrame(rows)
    if len(df) == 0:
        return df
    df = df.dropna(subset=["spy_idx"]).sort_values("spy_idx").reset_index(drop=True)
    df["s5_up"] = (df["s5_d2"] > 0).astype(int)
    df["st_up"] = (df["st_d2"] > 0).astype(int)

    def q(r):
        if r["s5_up"] and r["st_up"]:
            return "CONV_UP"
        if not r["s5_up"] and not r["st_up"]:
            return "CONV_DN"
        if r["s5_up"] and not r["st_up"]:
            return "DIV_S5up_stdn"
        return "DIV_S5dn_stup"

    df["quad"] = df.apply(q, axis=1)
    df["is_div"] = df["quad"].str.startswith("DIV").astype(int)
    return df


# ─── Full wins/losses metrics ─────────────────────────────────────────────────
def full_metrics(arr):
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return {"N": len(arr), "insufficient": True}
    wins = arr[arr > 0]
    losses = arr[arr <= 0]
    wr, wr_lo, wr_hi = boot_prop(arr > 0)
    ev, ev_lo, ev_hi = boot_ci(arr)
    gross_win = wins.sum()
    gross_loss = abs(losses.sum())
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    avg_w = wins.mean() if len(wins) else 0.0
    avg_l = abs(losses.mean()) if len(losses) else 0.0
    wipe = arr[arr <= WIPEOUT_THRESHOLD]
    return {
        "N": len(arr),
        "wr": wr, "wr_ci95": [wr_lo, wr_hi],
        "ev": ev, "ev_ci95": [ev_lo, ev_hi],
        "median": float(np.median(arr)),
        "win_mean": float(avg_w),
        "loss_mean": float(avg_l),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "wins_p25": float(np.percentile(wins, 25)) if len(wins) else None,
        "wins_p50": float(np.percentile(wins, 50)) if len(wins) else None,
        "wins_p75": float(np.percentile(wins, 75)) if len(wins) else None,
        "wins_p90": float(np.percentile(wins, 90)) if len(wins) else None,
        "losses_p25": float(np.percentile(losses, 25)) if len(losses) else None,
        "losses_p50": float(np.percentile(losses, 50)) if len(losses) else None,
        "losses_p75": float(np.percentile(losses, 75)) if len(losses) else None,
        "losses_p90": float(np.percentile(losses, 90)) if len(losses) else None,
        "pf": float(pf),
        "kelly": float(kelly(wr, avg_w, avg_l)) if avg_l > 0 else None,
        "wipeouts_n": int(len(wipe)),
        "wipeouts_pct": float(len(wipe) / len(arr) * 100),
        "wipeouts_vals": [float(v) for v in wipe],
    }


def raw_forward(df, mask, h, spacing=MIN_SPACING):
    """Return (raw forward returns, deduped dates) for a mask at horizon h."""
    idxs = df.index[mask].tolist()
    deduped = []
    last = -spacing - 1
    for i in idxs:
        si = int(df.loc[i, "spy_idx"])
        if si - last >= spacing:
            deduped.append(i)
            last = si
    arr = []
    for i in deduped:
        entry = int(df.loc[i, "spy_idx"])
        fi = entry + h
        if fi < len(spy_values):
            arr.append(spy_values[fi] / spy_values[entry] - 1.0)
    return np.array(arr), [str(df.loc[i, "date"].date()) for i in deduped]


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN LOOP PER STATION
# ═══════════════════════════════════════════════════════════════════════════════

all_results = {}

for name, ticker in STATIONS:
    print("\n" + "═" * 90)
    print(f"  PAR:  S5 (S5TW)  ×  {name} ({ticker})")
    print("═" * 90)

    df = align_pair(name)
    if len(df) == 0:
        print("  SIN DATOS ALINEADOS — skip")
        continue
    n_days = len(df)

    # ── 1. Correlations ───────────────────────────────────────────────────────
    raw_pearson = float(np.corrcoef(df["s5_raw"].values, df["st_raw"].values)[0, 1])
    raw_spearman = float(df["s5_raw"].corr(df["st_raw"], method="spearman"))
    d2_pearson = float(np.corrcoef(df["s5_d2"].values, df["st_d2"].values)[0, 1])
    d2_spearman = float(df["s5_d2"].corr(df["st_d2"], method="spearman"))
    m = df["s5_d3"].notna() & df["st_d3"].notna()
    d3_pearson = float(np.corrcoef(df.loc[m, "s5_d3"].values, df.loc[m, "st_d3"].values)[0, 1]) if m.sum() > 2 else np.nan
    d3_spearman = float(df.loc[m, "s5_d3"].corr(df.loc[m, "st_d3"], method="spearman")) if m.sum() > 2 else np.nan

    print(f"\n  1. CORRELACIÓN  (n={n_days} días alineados)")
    print(f"     raw niveles:  Pearson {raw_pearson:+.3f}   Spearman {raw_spearman:+.3f}")
    print(f"     D2 (diff3):   Pearson {d2_pearson:+.3f}   Spearman {d2_spearman:+.3f}")
    print(f"     D3 (std2/10): Pearson {d3_pearson:+.3f}   Spearman {d3_spearman:+.3f}")

    # ── 2. Quadrant distribution ──────────────────────────────────────────────
    qc = df["quad"].value_counts()
    n_div = int(df["is_div"].sum())
    n_conv = int((1 - df["is_div"]).sum())
    print(f"\n  2. DISTRIBUCIÓN DE CUADRANTES (D2 signo)  n={n_days}")
    for q in ["CONV_UP", "DIV_S5up_stdn", "DIV_S5dn_stup", "CONV_DN"]:
        c = int(qc.get(q, 0))
        print(f"     {q:<16} N={c:6d}  ({c/n_days*100:5.1f}%)")
    print(f"     → DIVERGENCIA N={n_div} ({n_div/n_days*100:.1f}%)   CONVERGENCIA N={n_conv} ({n_conv/n_days*100:.1f}%)")

    # ── 3. Forward returns: divergencia vs convergencia ───────────────────────
    div_mask = df["is_div"] == 1
    conv_mask = df["is_div"] == 0

    div_metrics = {h: full_metrics(raw_forward(df, div_mask, h)[0]) for h in FW_HORIZONS}
    conv_metrics = {h: full_metrics(raw_forward(df, conv_mask, h)[0]) for h in FW_HORIZONS}
    _, div_dates = raw_forward(df, div_mask, 20)
    _, conv_dates = raw_forward(df, conv_mask, 20)

    print(f"\n  3. FORWARD SPY — DIVERGENCIA vs CONVERGENCIA (de-cluster ≥{MIN_SPACING}d)")
    print(f"     Señales: DIV={len(div_dates)}  CONV={len(conv_dates)}")
    print(f"     {'H':>4} │ {'DIV EV':>9} {'DIV CI95':>22} {'DIV WR':>7} │ {'CONV EV':>9} {'CONV CI95':>22} {'CONV WR':>7} │ {'ΔEV':>8} {'ΔEV CI95':>22} {'P(Δ>0)':>7}")
    print(f"     {'─'*4}─┼─{'─'*9}─{'─'*22}─┼─{'─'*7}─┼─{'─'*9}─{'─'*22}─┼─{'─'*7}─┼─{'─'*8}─{'─'*22}─┼─{'─'*7}")
    for h in FW_HORIZONS:
        d = div_metrics[h]
        c = conv_metrics[h]
        if d.get("insufficient") or c.get("insufficient"):
            print(f"     {h:>4}d │ insuficiente")
            continue
        arr_div, _ = raw_forward(df, div_mask, h)
        arr_conv, _ = raw_forward(df, conv_mask, h)
        diff, lo, hi, p_pos = boot_diff(arr_div, arr_conv)
        print(f"     {h:>4}d │ {d['ev']*100:+8.2f}% [{d['ev_ci95'][0]*100:+6.1f}%,{d['ev_ci95'][1]*100:+6.1f}%] {d['wr']*100:6.0f}% │ "
              f"{c['ev']*100:+8.2f}% [{c['ev_ci95'][0]*100:+6.1f}%,{c['ev_ci95'][1]*100:+6.1f}%] {c['wr']*100:6.0f}% │ "
              f"{diff*100:+7.2f}% [{lo*100:+6.1f}%,{hi*100:+6.1f}%] {p_pos*100:6.0f}%")

    # wins/losses detail at 20d
    for label, met in [("DIVERGENCIA", div_metrics[20]), ("CONVERGENCIA", conv_metrics[20])]:
        if met.get("insufficient"):
            continue
        print(f"\n     {label} @20d — wins/losses separados (N={met['N']}):")
        print(f"       EV {met['ev']*100:+.2f}% [{met['ev_ci95'][0]*100:+.2f}%,{met['ev_ci95'][1]*100:+.2f}%]  WR {met['wr']*100:.1f}%  med {met['median']*100:+.2f}%")
        print(f"       WINS:  mean {met['win_mean']*100:+.2f}%  P25/P50/P75/P90 = {met['wins_p25']*100:+.1f}/{met['wins_p50']*100:+.1f}/{met['wins_p75']*100:+.1f}/{met['wins_p90']*100:+.1f}%")
        print(f"       LOSSES:mean {met['loss_mean']*100:+.2f}%  P25/P50/P75/P90 = {met['losses_p25']*100:+.1f}/{met['losses_p50']*100:+.1f}/{met['losses_p75']*100:+.1f}/{met['losses_p90']*100:+.1f}%  min {met['min']*100:+.2f}%")
        print(f"       PF {met['pf']:.2f}  Kelly {met['kelly']*100:.0f}%  wipeouts>{abs(WIPEOUT_THRESHOLD)*100:.0f}%: {met['wipeouts_n']} ({met['wipeouts_pct']:.1f}%)")

    # ── 4. Zigzag pivots (3 scales) ───────────────────────────────────────────
    s5_d2_sign = {d.date(): (1 if v > 0 else 0) for d, v in d2["S5"].items() if not pd.isna(v)}
    st_d2_sign = {d.date(): (1 if v > 0 else 0) for d, v in d2[name].items() if not pd.isna(v)}

    print(f"\n  4. PIVOTES ZIGZAG — divergencia en pisos (MIN) vs techos (MAX)")

    zig_results = {}
    for sc, pct in ZIG_SCALES:
        zdf = zig_data[sc].copy()
        zdf["s5_up"] = zdf["pivot_date"].map(s5_d2_sign)
        zdf["st_up"] = zdf["pivot_date"].map(st_d2_sign)
        zdf = zdf.dropna(subset=["s5_up", "st_up"])
        if len(zdf) == 0:
            continue
        zdf["is_div"] = (zdf["s5_up"] != zdf["st_up"]).astype(int)
        div = zdf[zdf["is_div"] == 1]
        conv = zdf[zdf["is_div"] == 0]
        out_sc = {"N_div": int(len(div)), "N_conv": int(len(conv)),
                  "pct_div": float(len(div) / len(zdf))}
        for grp_label, g in [("DIV", div), ("CONV", conv)]:
            nb, nblo, nbhi = boot_prop(g["next_bear"]) if len(g) >= 3 else (np.nan, np.nan, np.nan)
            out_sc[grp_label] = {
                "N": int(len(g)), "p_next_bear": nb, "p_next_bear_ci95": [nblo, nbhi],
            }
            if sc != "zz75":
                cc, cclo, cchi = boot_prop(g["cascade"]) if len(g) >= 3 else (np.nan, np.nan, np.nan)
                out_sc[grp_label]["p_cascade"] = cc
                out_sc[grp_label]["p_cascade_ci95"] = [cclo, cchi]
        for typ_label, typ_mask in [("MIN", zdf["is_min"] == 1), ("MAX", zdf["is_min"] == 0)]:
            sub = zdf[typ_mask]
            sub_div = sub[sub["is_div"] == 1]
            sub_conv = sub[sub["is_div"] == 0]
            out_sc[f"{typ_label}_div_n"] = int(len(sub_div))
            out_sc[f"{typ_label}_conv_n"] = int(len(sub_conv))
            out_sc[f"{typ_label}_div_next_bear"] = float(boot_prop(sub_div["next_bear"])[0]) if len(sub_div) >= 3 else np.nan
            out_sc[f"{typ_label}_conv_next_bear"] = float(boot_prop(sub_conv["next_bear"])[0]) if len(sub_conv) >= 3 else np.nan
        zig_results[sc] = out_sc

        print(f"\n     ── escala {sc} ({pct}%) ──  N pivotes={len(zdf)}  DIV={len(div)} ({len(div)/len(zdf)*100:.1f}%)  CONV={len(conv)}")
        for grp_label, g in [("DIV", div), ("CONV", conv)]:
            r = out_sc[grp_label]
            if r["N"] < 3:
                print(f"        {grp_label:<6} N={r['N']}  insuficiente")
                continue
            s = f"        {grp_label:<6} N={r['N']:>4}  %next_bear {r['p_next_bear']*100:5.1f}% [{r['p_next_bear_ci95'][0]*100:4.1f}%,{r['p_next_bear_ci95'][1]*100:4.1f}%]"
            if sc != "zz75":
                s += f"   %cascade {r['p_cascade']*100:5.1f}% [{r['p_cascade_ci95'][0]*100:4.1f}%,{r['p_cascade_ci95'][1]*100:4.1f}%]"
            print(s)
        for typ_label in ["MIN", "MAX"]:
            dn = out_sc[f"{typ_label}_div_n"]; cn = out_sc[f"{typ_label}_conv_n"]
            dv = out_sc[f"{typ_label}_div_next_bear"]; cv = out_sc[f"{typ_label}_conv_next_bear"]
            if dn >= 3 and cn >= 3 and not np.isnan(dv) and not np.isnan(cv):
                print(f"        {typ_label}: DIV next_bear {dv*100:.1f}% (n={dn})  vs  CONV next_bear {cv*100:.1f}% (n={cn})  Δ={dv-cv:+.1%}")
            else:
                print(f"        {typ_label}: DIV n={dn}  CONV n={cn}  (insuficiente para CI)")

    # ── Store results ─────────────────────────────────────────────────────────
    all_results[name] = {
        "ticker": ticker,
        "n_days": n_days,
        "correlation": {
            "raw_pearson": raw_pearson, "raw_spearman": raw_spearman,
            "d2_pearson": d2_pearson, "d2_spearman": d2_spearman,
            "d3_pearson": d3_pearson, "d3_spearman": d3_spearman,
        },
        "quadrant_counts": {q: int(qc.get(q, 0)) for q in ["CONV_UP", "DIV_S5up_stdn", "DIV_S5dn_stup", "CONV_DN"]},
        "n_div": n_div, "n_conv": n_conv,
        "div_fwd": {str(h): div_metrics[h] for h in FW_HORIZONS},
        "conv_fwd": {str(h): conv_metrics[h] for h in FW_HORIZONS},
        "n_signals_div": len(div_dates),
        "n_signals_conv": len(conv_dates),
        "div_dates_20d": div_dates,
        "conv_dates_20d": conv_dates,
        "zigzag": zig_results,
    }


# ─── Serialize + save JSON ────────────────────────────────────────────────────
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
    "meta": {
        "script": "research/04_conjuncion_multi_estacion/s5_divergencia_estaciones.py",
        "description": "Estudio de divergencia S5 (S5TW) × 10 estaciones",
        "S5_definition": "S5TW = price breadth (% stocks > 20-DMA); direction = sign(diff(3))",
        "divergence_definition": "sign(D2 S5) != sign(D2 station)",
        "method": "correlación raw/D2/D3 + forward fijo 5/10/20/40d (de-cluster 10d) + zigzag 2.5/5/7.5",
        "bootstrap": "2000 iter CI95",
        "wipeout_threshold": WIPEOUT_THRESHOLD,
    },
    "stations": all_results,
}

out = ROOT / "data/research/conjunctions/s5_divergencia_estaciones.json"
with open(out, "w") as f:
    json.dump(ser(report), f, indent=2, default=str)

print("\n\n" + "═" * 90)
print(f"  Reporte JSON guardado: {out}")
print("═" * 90)
print("DONE.")
