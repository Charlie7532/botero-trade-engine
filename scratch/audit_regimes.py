#!/usr/bin/env python3
"""
AUDITOR DE REGÍMENES — Botero Trade (11 estaciones)
====================================================
1. Clasificar cada barra/pivot con el adapter (lookup_*_guidance) → state_key.
2. Medir SPY forward 20d por D1_bin principal → ¿estaciones accionables?
3. Para estaciones accionables, medir matriz D2×D3 dentro del D1 extremo.
4. ¿D3 es filtro universal o solo en sentimiento?
5. Clasificar: ENTRY SIGNAL / EXIT SIGNAL / FILTER / NEUTRAL.
6. Jerarquía de señales.

PYTHONPATH=/root/botero-trade
USAR venv: backend/.venv/bin/python
"""

import sys, json, os
from datetime import timedelta
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, ttest_ind
import time

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.modules.entry_decision.domain.services.convergence_compositor import d1_directional_vote

from backend.modules.entry_decision.domain.rules.vix_lookup import VIXLookupAdapter
from backend.modules.entry_decision.domain.rules.vvix_lookup import VVIXLookupAdapter
from backend.modules.entry_decision.domain.rules.pcr_lookup import PCRLookupAdapter
from backend.modules.entry_decision.domain.rules.fg_lookup import FGLookupAdapter
from backend.modules.entry_decision.domain.rules.sv5_turbulence_lookup import SV5TurbulenceLookupAdapter
from backend.modules.entry_decision.domain.rules.skew_lookup import SkewLookupAdapter
from backend.modules.entry_decision.domain.rules.credit_lookup import CreditLookupAdapter
from backend.modules.entry_decision.domain.rules.yield_curve_lookup import YieldCurveLookupAdapter
from backend.modules.entry_decision.domain.rules.rotation_lookup import RotationLookupAdapter
from backend.modules.entry_decision.domain.rules.bsi_lookup import BSILookupAdapter
from backend.modules.entry_decision.domain.rules.dxy_lookup import DXYLookupAdapter

STATION_CONFIG = {
    "vix":            {"ticker": "VIX",            "cls": VIXLookupAdapter,            "method": "lookup_vix_guidance"},
    "vvix":           {"ticker": "VVIX",           "cls": VVIXLookupAdapter,           "method": "lookup_vvix_guidance"},
    "pcr":            {"ticker": "CBOE_PCR",       "cls": PCRLookupAdapter,            "method": "lookup_pcr_guidance"},
    "fg":             {"ticker": "FG",             "cls": FGLookupAdapter,             "method": "lookup_fg_guidance"},
    "sv5_turbulence": {"ticker": "SV5_TURBULENCE", "cls": SV5TurbulenceLookupAdapter, "method": "lookup_sv5_turbulence_guidance"},
    "skew":           {"ticker": "SKEW",           "cls": SkewLookupAdapter,           "method": "lookup_skew_guidance"},
    "credit":         {"ticker": "CREDIT_RATIO",   "cls": CreditLookupAdapter,         "method": "lookup_credit_guidance"},
    "yield_curve":    {"ticker": "YIELD_SPREAD",   "cls": YieldCurveLookupAdapter,     "method": "lookup_yield_curve_guidance"},
    "rotation":       {"ticker": "ROTATION_INDEX", "cls": RotationLookupAdapter,       "method": "lookup_rotation_guidance"},
    "bsi":            {"ticker": "S5TW",           "cls": BSILookupAdapter,            "method": "lookup_bsi_guidance"},
    "dxy":            {"ticker": "DXY",            "cls": DXYLookupAdapter,            "method": "lookup_dxy_guidance"},
}

ALL = list(STATION_CONFIG.keys())
SENTIMENT = {"vix", "fg", "vvix", "pcr", "bsi"}
MACRO     = {"credit", "yield_curve", "dxy", "rotation", "sv5_turbulence", "skew"}


def main():
    t0 = time.time()
    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)

    # ── ZZ legs ──────────────────────────────────────────────────
    legs25 = repo.get_confirmed_legs("SPY", "zz25")
    legs50 = repo.get_confirmed_legs("SPY", "zz50")
    legs75 = repo.get_confirmed_legs("SPY", "zz75")
    s50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)
    s75 = set(pd.to_datetime(l.start_timestamp).date() for l in legs75)

    legs_sorted = sorted(legs25, key=lambda l: l.start_timestamp)
    df = pd.DataFrame([
        {"start_timestamp": l.start_timestamp, "start_type": l.start_type,
         "prev_leg_return": l.prev_leg_return} for l in legs_sorted
    ]).dropna(subset=["prev_leg_return"]).reset_index(drop=True)
    df["pivot_date"] = pd.to_datetime(df["start_timestamp"]).dt.date
    df["c50"] = df["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in s50 for i in range(-3,4))))
    df["c75"] = df["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in s75 for i in range(-3,4))))
    df["leg_bear"] = (df["start_type"] == "MAX").astype(int)

    N_PIVOTS = len(df)
    print(f"ZZ25 pivots: {N_PIVOTS}")

    # ── Load all indicator series + SPY ──────────────────────────
    series = {}
    for code, cfg in STATION_CONFIG.items():
        dfi = store.load_bars(cfg["ticker"], "1d")
        if dfi is not None and not dfi.empty:
            s = dfi["close"].copy()
            s.index = [d.date() if hasattr(d, "date") else d for d in pd.to_datetime(s.index)]
            series[code] = s
            print(f"  ✓ {code:18s} {s.index[0]} → {s.index[-1]} ({len(s)} bars)")
        else:
            print(f"  ✗ {code:18s} NO DATA")

    spy_bars = store.load_bars("SPY", "1d")
    spy_close = spy_bars["close"].copy()
    spy_close.index = pd.to_datetime(spy_close.index)

    store.close()
    print(f"DB load: {time.time()-t0:.1f}s")

    # ── Compute forward returns ──────────────────────────────────
    spy_s = pd.Series(spy_close.values, index=spy_close.index)
    fwd20 = spy_s.shift(-20) / spy_s - 1
    fwd10 = spy_s.shift(-10) / spy_s - 1
    fwd5  = spy_s.shift(-5)  / spy_s - 1

    # ── For each pivot, compute D1, D2, D3 for each indicator ────
    t1 = time.time()
    adapters = {code: cfg["cls"]() for code, cfg in STATION_CONFIG.items() if code in series}

    # Precompute D2 (velocity = diff3) and D3 (vol = std2/std10)
    d2 = {}; d3 = {}
    for code, s in series.items():
        d2[code] = s.diff(3)
        s2, s10 = s.rolling(2).std(), s.rolling(10).std()
        d3[code] = (s2 / s10).replace([np.inf, -np.inf], np.nan).fillna(1.0)

    # ── FASE 1: Classify each pivot ──────────────────────────────
    print(f"\nFASE 1: Classifying {N_PIVOTS} pivots × {len(ALL)} stations...")
    for code in ALL:
        if code not in series:
            df[f"{code}_state"] = None
            df[f"{code}_d1bin"] = None
            df[f"{code}_d2"] = np.nan
            df[f"{code}_d3"] = np.nan
            df[f"{code}_vote"] = np.nan
            continue
        s = series[code]
        vel = d2[code]
        vol = d3[code]
        adapter = adapters[code]
        method = STATION_CONFIG[code]["method"]

        states = []; d1bins = []; d2s = []; d3s = []; votes = []
        for pdate in df["pivot_date"]:
            idx = s.index[s.index <= pdate]
            if len(idx) == 0:
                states.append(None); d1bins.append(None)
                d2s.append(np.nan); d3s.append(np.nan); votes.append(np.nan)
                continue
            di = idx[-1]
            val = float(s.loc[di])
            v2  = float(vel.get(di, 0.0))
            v3  = float(vol.get(di, 1.0))
            if pd.isna(v2): v2 = 0.0
            if pd.isna(v3): v3 = 1.0
            d2s.append(v2); d3s.append(v3)
            try:
                res = getattr(adapter, method)(val=val, d3_speed=v2, vol_norm=v3, vol_d3=v3)
                if res and res.state_key:
                    states.append(res.state_key)
                    d1bins.append(res.state_key.split("__")[0])
                    votes.append(d1_directional_vote(res.state_key))
                else:
                    states.append(None); d1bins.append(None); votes.append(np.nan)
            except Exception:
                states.append(None); d1bins.append(None); votes.append(np.nan)

        df[f"{code}_state"] = states
        df[f"{code}_d1bin"] = d1bins
        df[f"{code}_d2"] = d2s
        df[f"{code}_d3"] = d3s
        df[f"{code}_vote"] = votes

    print(f"Classification: {time.time()-t1:.1f}s")

    # ── Add SPY fwd20 for each pivot ─────────────────────────────
    f20s = []
    for pdate in df["pivot_date"]:
        si = spy_close.index[spy_close.index.date <= pdate]
        if len(si) == 0:
            f20s.append(np.nan)
        else:
            f20s.append(float(fwd20.get(si[-1], np.nan)))
    df["fwd20"] = f20s
    df["fwd20_pct"] = df["fwd20"] * 100

    print(f"SPY joins: {time.time()-t1:.1f}s")

    # ═══════════════════════════════════════════════════════════════
    # FASE 2: SPY fwd20 por D1_bin → actionable?
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "═"*90)
    print("  FASE 2: SPY FORWARD 20d POR D1_BIN (¿estaciones accionables?)")
    print("═"*90)

    actionable = []; station_table = []
    for code in ALL:
        col = f"{code}_d1bin"
        mask = df[col].notna() & df["fwd20"].notna()
        sub = df[mask]
        if len(sub) < 30:
            station_table.append({"station": code, "spread_pp": 0, "actionable": False,
                                   "best_bin": None, "best_val": 0, "best_n": 0,
                                   "worst_bin": None, "worst_val": 0, "worst_n": 0,
                                   "n_total": 0, "n_bins": 0})
            continue

        grp = sub.groupby(col)["fwd20_pct"].agg(["mean", "std", "count"])
        grp["hit"] = sub.groupby(col)["fwd20"].apply(lambda x: (x > 0).mean())

        if len(grp) < 2:
            continue

        best_bin = grp["mean"].idxmax()
        worst_bin = grp["mean"].idxmin()
        best_val = grp.loc[best_bin, "mean"]
        worst_val = grp.loc[worst_bin, "mean"]
        spread = best_val - worst_val
        best_n = int(grp.loc[best_bin, "count"])
        worst_n = int(grp.loc[worst_bin, "count"])

        best_data = sub[sub[col] == best_bin]["fwd20_pct"]
        worst_data = sub[sub[col] == worst_bin]["fwd20_pct"]
        t_s, p_v = ttest_ind(best_data, worst_data) if len(best_data) > 3 and len(worst_data) > 3 else (0, 1)

        act = spread > 2.0 and p_v < 0.10

        print(f"  {code:<18s} spread={spread:+6.1f}pp  best='{str(best_bin)[:30]}' ({best_val:+5.1f}%,n={best_n})  "
              f"worst='{str(worst_bin)[:30]}' ({worst_val:+5.1f}%,n={worst_n})  "
              f"t={t_s:+.2f} p={p_v:.3f}  → {'✅ ACCIONABLE' if act else '⚪ NEUTRO'}")

        if len(grp) <= 5:
            for bin_name, row in grp.sort_values("mean", ascending=False).iterrows():
                print(f"      {str(bin_name)[:45]:45s} {row['mean']:+6.1f}%  n={int(row['count'])}  hit={row['hit']:.0%}")

        station_table.append({
            "station": code, "spread_pp": spread, "actionable": act,
            "best_bin": best_bin, "best_val": best_val, "best_n": best_n,
            "worst_bin": worst_bin, "worst_val": worst_val, "worst_n": worst_n,
            "t_stat": t_s, "p_val": p_v, "n_total": int(sub[col].count()),
            "n_bins": len(grp), "all_bins": grp,
        })
        if act:
            actionable.append(code)

    print(f"\n  ══ ACCIONABLES (spread>2pp, p<0.10): {actionable or 'NINGUNA'} ══")

    # ═══════════════════════════════════════════════════════════════
    # FASE 3: D2×D3 matrix inside D1 extreme
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "═"*90)
    print("  FASE 3: MATRIZ D2 × D3 DENTRO DEL D1 EXTREMO (best bin)")
    print("═"*90)

    # Use ALL stations (not just actionable) for the matrix analysis
    # since even non-actionable may have interesting quadrants
    for rec in sorted(station_table, key=lambda x: -abs(x["spread_pp"])):
        code = rec["station"]
        best_bin = rec["best_bin"]
        if best_bin is None:
            continue

        col = f"{code}_d1bin"
        mask = (df[col] == best_bin) & df["fwd20"].notna()
        sub = df[mask]
        if len(sub) < 20:
            continue

        d2col = f"{code}_d2"; d3col = f"{code}_d3"
        d2_up = sub[d2col] > 0; d3_hi = sub[d3col] > 1.0

        print(f"\n  {code} — D1={str(best_bin)[:40]} (fwd20={rec['best_val']:+.1f}%, n={rec['best_n']})")
        n_total = len(sub)
        print(f"  N={n_total}  D2↑={d2_up.sum()}  D2↓={(~d2_up).sum()}  D3_HI={d3_hi.sum()}  D3_LO={(~d3_hi).sum()}")

        quads = []
        for d2_lbl, d2m in [("D2↑", d2_up), ("D2↓", ~d2_up)]:
            for d3_lbl, d3m in [("D3_LO(≤1)", ~d3_hi), ("D3_HI(>1)", d3_hi)]:
                qsub = sub[d2m & d3m]
                n = len(qsub)
                if n < 5:
                    print(f"    {d2_lbl:>5s}×{d3_lbl:<12s}: n={n} (insuf)")
                    continue
                mf = qsub["fwd20_pct"].mean()
                hit = (qsub["fwd20"] > 0).mean()
                print(f"    {d2_lbl:>5s}×{d3_lbl:<12s}: {mf:+6.1f}%  hit={hit:.0%}  n={n}")
                quads.append((d2_lbl, d3_lbl, mf, n))
        if quads:
            quads.sort(key=lambda x: -x[2])
            print(f"    🏆 Mejor: {quads[0][0]}×{quads[0][1]} = {quads[0][2]:+.1f}%")

    # ═══════════════════════════════════════════════════════════════
    # FASE 4: D3 — ¿filtro universal o solo sentimiento?
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "═"*90)
    print("  FASE 4: ¿D3 ES FILTRO UNIVERSAL O SOLO EN SENTIMIENTO?")
    print("═"*90)

    d3_effects = []
    for code in ALL:
        d3col = f"{code}_d3"
        mask = df[d3col].notna() & df["c50"].notna()
        sub = df[mask]
        if len(sub) < 50:
            continue
        d3_med = sub[d3col].median()
        calma = sub[sub[d3col] <= d3_med]
        caos  = sub[sub[d3col] > d3_med]
        if len(calma) < 10 or len(caos) < 10:
            continue

        delta_c50 = (caos["c50"].mean() - calma["c50"].mean()) * 100
        t_s, p_v = ttest_ind(caos["c50"], calma["c50"])

        # Also check fwd20
        mask2 = df[d3col].notna() & df["fwd20"].notna()
        sub2 = df[mask2]
        d3m2 = sub2[d3col].median()
        calma2 = sub2[sub2[d3col] <= d3m2]
        caos2  = sub2[sub2[d3col] > d3m2]
        dfwd = (caos2["fwd20_pct"].mean() - calma2["fwd20_pct"].mean()) if len(calma2) >= 5 and len(caos2) >= 5 else 0

        grp = "sentiment" if code in SENTIMENT else "macro"
        sig = abs(delta_c50) > 3 and p_v < 0.10
        d3_effects.append({
            "station": code, "group": grp,
            "delta_c50_pp": delta_c50, "delta_fwd_pp": dfwd,
            "t_stat": t_s, "p_val": p_v, "significant": sig,
            "n_calma": len(calma), "n_caos": len(caos),
        })

    df_d3 = pd.DataFrame(d3_effects)
    print(f"\n  {'Station':<18s} {'Grupo':<12s} {'Δc50':>8s} {'t':>7s} {'p':>8s} {'Δfwd20':>8s} {'Sig?':>6s}")
    print(f"  {'─'*18} {'─'*12} {'─'*8} {'─'*7} {'─'*8} {'─'*8} {'─'*6}")
    for _, r in df_d3.sort_values("delta_c50_pp").iterrows():
        sig = "***" if r["significant"] else "ns"
        print(f"  {r['station']:<18s} {r['group']:<12s} {r['delta_c50_pp']:>+7.1f}pp "
              f"{r['t_stat']:>+7.2f} {r['p_val']:>8.3f} {r['delta_fwd_pp']:>+7.1f}pp {sig:>6s}")

    sent_d3 = df_d3[df_d3["group"] == "sentiment"] if len(df_d3) > 0 else pd.DataFrame()
    macro_d3 = df_d3[df_d3["group"] == "macro"] if len(df_d3) > 0 else pd.DataFrame()

    print(f"\n  ══ D3 EFFECT SUMMARY ══")
    if len(sent_d3) > 0:
        s_sig = sent_d3["significant"].sum()
        s_abs = sent_d3["delta_c50_pp"].abs().mean()
        print(f"  SENTIMENT: |Δc50|={s_abs:.1f}pp, {int(s_sig)}/{len(sent_d3)} sig")
    if len(macro_d3) > 0:
        m_sig = macro_d3["significant"].sum()
        m_abs = macro_d3["delta_c50_pp"].abs().mean()
        print(f"  MACRO:     |Δc50|={m_abs:.1f}pp, {int(m_sig)}/{len(macro_d3)} sig")

    if len(sent_d3) > 0 and len(macro_d3) > 0:
        s_abs = sent_d3["delta_c50_pp"].abs().mean()
        m_abs = macro_d3["delta_c50_pp"].abs().mean()
        s_sig = sent_d3["significant"].sum()
        m_sig = macro_d3["significant"].sum()

        if s_abs > 2.0 * m_abs and s_sig >= 3:
            print(f"  ➤ D3 es FILTRO DE SENTIMIENTO (no universal)")
        elif m_abs > 2.0 * s_abs and m_sig >= 3:
            print(f"  ➤ D3 es FILTRO MACRO (no universal)")
        else:
            print(f"  ➤ D3 tiene efecto MIXTO/NEUTRO")
    else:
        print(f"  ➤ Datos insuficientes")

    # ═══════════════════════════════════════════════════════════════
    # FASE 5: Classify ENTRY/EXIT/FILTER/NEUTRAL
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "═"*90)
    print("  FASE 5: CLASIFICACIÓN — ENTRY / EXIT / FILTER / NEUTRAL")
    print("═"*90)

    classes = []
    for rec in station_table:
        code = rec["station"]
        if rec["best_bin"] is None:
            classes.append({"station": code, "class": "NEUTRAL", "detail": "no data"})
            continue

        col = f"{code}_d1bin"
        mask = df[col].notna() & df["fwd20"].notna()
        sub = df[mask]

        # Check entry/exit via spread
        best_bin = rec["best_bin"]
        worst_bin = rec["worst_bin"]

        best_data = sub[sub[col] == best_bin]["fwd20_pct"]
        others_best = sub[sub[col] != best_bin]["fwd20_pct"]
        t_best, p_best = ttest_ind(best_data, others_best) if len(others_best) > 5 else (0, 1)

        worst_data = sub[sub[col] == worst_bin]["fwd20_pct"]
        others_worst = sub[sub[col] != worst_bin]["fwd20_pct"]
        t_worst, p_worst = ttest_ind(worst_data, others_worst) if len(others_worst) > 5 else (0, 1)

        has_entry = rec["best_val"] > 2 and p_best < 0.10
        has_exit = rec["worst_val"] < -2 and p_worst < 0.10

        # D3 filter check
        d3r = df_d3[df_d3["station"] == code] if len(df_d3) > 0 else pd.DataFrame()
        d3_filter = False
        d3_info = ""
        if len(d3r) > 0:
            r = d3r.iloc[0]
            if r["significant"] and abs(r["delta_c50_pp"]) > 3:
                d3_filter = True
                d3_info = f" D3(Δc50={r['delta_c50_pp']:+.1f}pp)"

        cls = "NEUTRAL"
        detail = ""
        if has_entry and has_exit:
            cls = "DUAL SIGNAL"
            detail = f"ENTRY({best_bin}={rec['best_val']:+.1f}%) + EXIT({worst_bin}={rec['worst_val']:+.1f}%)"
        elif has_entry:
            cls = "ENTRY SIGNAL"
            detail = f"{best_bin}={rec['best_val']:+.1f}%"
        elif has_exit:
            cls = "EXIT SIGNAL"
            detail = f"{worst_bin}={rec['worst_val']:+.1f}%"
        elif d3_filter:
            cls = "FILTER"
            detail = d3_info.strip()
        else:
            detail = f"spread={rec['spread_pp']:+.1f}pp (best={rec['best_val']:+.1f}%, worst={rec['worst_val']:+.1f}%)"

        if d3_filter and not has_entry and not has_exit:
            detail += d3_info

        classes.append({"station": code, "class": cls, "detail": detail,
                        "spread": rec["spread_pp"], "best_val": rec["best_val"],
                        "worst_val": rec["worst_val"], "n": rec["n_total"]})

    print(f"\n  {'Station':<18s} {'Clase':<15s} {'Spread':>7s} {'Best':>8s} {'Worst':>8s} {'N':>6s}  Detail")
    print(f"  {'─'*18} {'─'*15} {'─'*7} {'─'*8} {'─'*8} {'─'*6}  {'─'*50}")
    for c in sorted(classes, key=lambda x: -abs(x["spread"])):
        print(f"  {c['station']:<18s} {c['class']:<15s} {c['spread']:>+6.1f}pp "
              f"{c['best_val']:>+7.1f}% {c['worst_val']:>+7.1f}% {c['n']:>6d}  {c['detail'][:50]}")

    # ═══════════════════════════════════════════════════════════════
    # FASE 6: Jerarquía
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "═"*90)
    print("  FASE 6: JERARQUÍA DE SEÑALES")
    print("═"*90)

    priority = {"ENTRY SIGNAL": 0, "EXIT SIGNAL": 0, "DUAL SIGNAL": 1, "FILTER": 2, "NEUTRAL": 3}
    ranked = sorted(classes, key=lambda c: (priority.get(c["class"], 4), -abs(c["spread"])))

    for i, c in enumerate(ranked, 1):
        if c["class"] == "NEUTRAL":
            break
        print(f"  {i}. [{c['class']}] {c['station']:<18s} spread={c['spread']:+.1f}pp  {c['detail'][:60]}")

    # ═══════════════════════════════════════════════════════════════
    # FASE adicional: Tabla completa de D1 bins × SPY fwd20
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "═"*90)
    print("  TABLA COMPLETA: D1_BIN → SPY FWD20% (todas las estaciones)")
    print("═"*90)

    top_stations = sorted(station_table, key=lambda x: -abs(x["spread_pp"]))[:6]
    for rec in top_stations:
        code = rec["station"]
        if "all_bins" not in rec or rec["all_bins"] is None:
            continue
        grp = rec["all_bins"]
        print(f"\n  ── {code.upper()} (spread={rec['spread_pp']:+.1f}pp, {rec['n_bins']} bins, n={rec['n_total']}) ──")
        print(f"  {'D1_BIN':<40s} {'Fwd20%':>8s} {'N':>6s} {'Hit%':>7s}")
        print(f"  {'─'*40} {'─'*8} {'─'*6} {'─'*7}")
        for bin_name, row in grp.sort_values("mean", ascending=False).iterrows():
            print(f"  {str(bin_name)[:40]:40s} {row['mean']:>+7.2f}% {int(row['count']):>6d} {row['hit']:>6.1%}")

    # ── Final summary ─────────────────────────────────────────────
    print(f"\n{'═'*90}")
    print(f"  RESUMEN FINAL — AUDITOR DE REGÍMENES")
    print(f"{'═'*90}")
    n_entry = sum(1 for c in classes if "ENTRY" in c["class"])
    n_exit  = sum(1 for c in classes if "EXIT" in c["class"])
    n_dual  = sum(1 for c in classes if c["class"] == "DUAL SIGNAL")
    n_filt  = sum(1 for c in classes if c["class"] == "FILTER")
    n_neut  = sum(1 for c in classes if c["class"] == "NEUTRAL")

    print(f"  ENTRY: {n_entry} | EXIT: {n_exit} | DUAL: {n_dual} | FILTER: {n_filt} | NEUTRAL: {n_neut}")
    print(f"  N pivots: {N_PIVOTS}  |  N estaciones: {len(ALL)}")
    print(f"  Total runtime: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()