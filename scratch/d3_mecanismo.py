#!/usr/bin/env python3
"""
D3 — FASE 2: mecanismo económico (¿dónde y cuándo importa el caos?)
====================================================================
Preguntas:
1. ¿D3 discrimina cascade sólo cuando el indicador está en un EXTREMO (D1 alto/bajo)
   o en todo el rango?  → split D3 × D1 (mediana).
2. ¿D3 discrimina distinto en pivots MIN vs MAX?  → split por tipo.
3. ¿Cuál es la cascada a lo largo de deciles de D3 (monotonicidad)?
4. ¿D3 apaga cascade porque coincide con SPY moviéndose YA (el movimiento se gastó)?
   → comparar cascade rate con |SPY ret| del día del pivot (movimiento "gastado").
"""
import sys, json
from datetime import timedelta
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.scripts._lib.decay_check_cascade_conviction import STATION_CONFIG

ALL = list(STATION_CONFIG.keys())

def main():
    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)

    legs25 = repo.get_confirmed_legs("SPY", "zz25")
    legs50 = repo.get_confirmed_legs("SPY", "zz50")
    legs75 = repo.get_confirmed_legs("SPY", "zz75")
    s50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)
    s75 = set(pd.to_datetime(l.start_timestamp).date() for l in legs75)

    df25 = pd.DataFrame([
        {"start_timestamp": l.start_timestamp, "start_type": l.start_type,
         "prev_leg_return": l.prev_leg_return} for l in legs25
    ]).dropna(subset=["prev_leg_return"]).reset_index(drop=True)
    df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
    df25["c50"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in s50 for i in range(-3,4))))
    df25["c75"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in s75 for i in range(-3,4))))
    df25["leg_bear"] = (df25["start_type"] == "MAX").astype(float)

    d3_series = {}; lvl_series = {}
    for code, cfg in STATION_CONFIG.items():
        dfi = store.load_bars(cfg["ticker"], "1d")
        if dfi is None or dfi.empty:
            continue
        s = dfi["close"].copy()
        s.index = [d.date() if hasattr(d, "date") else d for d in pd.to_datetime(s.index)]
        std2 = s.rolling(2).std(); std10 = s.rolling(10).std()
        d3 = (std2 / std10).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        d3_series[code] = d3
        lvl_series[code] = s

    spy = store.load_bars("SPY", "1d")["close"].copy()
    spy.index = [d.date() if hasattr(d, "date") else d for d in pd.to_datetime(spy.index)]
    spy_abs = spy.pct_change().abs()
    store.close()

    # build obs
    rows = []
    for _, r in df25.iterrows():
        pd_ = r["pivot_date"]
        rec = {"pivot_date": pd_, "c50": r["c50"], "c75": r["c75"],
               "leg_bear": r["leg_bear"], "type": r["start_type"]}
        for code in ALL:
            s = d3_series.get(code); lv = lvl_series.get(code)
            if s is None:
                rec[f"{code}_d3"] = np.nan; rec[f"{code}_lvl"] = np.nan; continue
            idx = s.index[s.index <= pd_]
            if len(idx) > 0:
                rec[f"{code}_d3"] = float(s.iloc[len(idx)-1])
            else:
                rec[f"{code}_d3"] = np.nan
            # nivel D1 (mediana relativa)
            li = lv.index[lv.index <= pd_]
            rec[f"{code}_lvl"] = float(lv.iloc[len(li)-1]) if len(li) > 0 else np.nan
        # SPY |ret| del día del pivot
        si = spy_abs.index[spy_abs.index <= pd_]
        rec["spy_abs_now"] = float(spy_abs.iloc[len(si)-1]) if len(si) > 0 else np.nan
        # SPY |ret| del día siguiente (forward)
        sif = spy_abs.index[spy_abs.index > pd_]
        rec["spy_abs_next"] = float(spy_abs.iloc[spy_abs.index.get_loc(sif[0])]) if len(sif) > 0 else np.nan
        rows.append(rec)
    df = pd.DataFrame(rows)

    # ── 1. D3 × D1 nivel (split por mediana de nivel) ───────────────
    print("═"*100)
    print("  FASE 2.1 — ¿El efecto de D3 depende del NIVEL (D1)?  (caos vs calma dentro de D1 alto/bajo)")
    print("═"*100)
    print(f"  {'estación':<16} {'D1↓: Δc50':>11} {'D1↓: Δc75':>11} {'D1↑: Δc50':>11} {'D1↑: Δc75':>11} "
          f"{'interacción':>12}")
    for code in ALL:
        col = f"{code}_d3"; lvlcol = f"{code}_lvl"
        m = ~np.isnan(df[col]) & ~np.isnan(df[lvlcol])
        sub = df[m]
        if len(sub) < 60:
            continue
        lvl_med = sub[lvlcol].median()
        lo_lvl = sub[lvlcol] <= lvl_med
        hi_lvl = sub[lvlcol] > lvl_med
        out = []
        for lmask, lbl in [(lo_lvl, "D1↓"), (hi_lvl, "D1↑")]:
            d3sub = sub[lmask][col]
            lo_t = d3sub.quantile(0.33); hi_t = d3sub.quantile(0.67)
            calma = lmask & (sub[col] <= lo_t)
            caos = lmask & (sub[col] >= hi_t)
            dc50 = (sub.loc[caos, "c50"].mean() - sub.loc[calma, "c50"].mean()) * 100
            dc75 = (sub.loc[caos, "c75"].mean() - sub.loc[calma, "c75"].mean()) * 100
            out.append((dc50, dc75))
        (lo_dc50, lo_dc75), (hi_dc50, hi_dc75) = out
        inter = hi_dc50 - lo_dc50
        print(f"  {code:<16} {lo_dc50:>+11.1f} {lo_dc75:>+11.1f} {hi_dc50:>+11.1f} {hi_dc75:>+11.1f} {inter:>+12.1f}")

    # ── 2. D3 × tipo MIN/MAX ────────────────────────────────────────
    print("\n" + "═"*100)
    print("  FASE 2.2 — ¿D3 discrimina distinto en pivots MIN vs MAX?")
    print("═"*100)
    print(f"  {'estación':<16} {'MIN: Δc50':>11} {'MIN: Δc75':>11} {'MAX: Δc50':>11} {'MAX: Δc75':>11}")
    for code in ALL:
        col = f"{code}_d3"
        m = ~np.isnan(df[col])
        sub = df[m]
        if len(sub) < 60:
            continue
        out = []
        for typ, tmask in [("MIN", sub["type"] == "MIN"), ("MAX", sub["type"] == "MAX")]:
            d3sub = sub[tmask][col]
            if d3sub.sum() < 20:
                out.append((np.nan, np.nan)); continue
            lo_t = d3sub.quantile(0.33); hi_t = d3sub.quantile(0.67)
            calma = tmask & (sub[col] <= lo_t)
            caos = tmask & (sub[col] >= hi_t)
            dc50 = (sub.loc[caos, "c50"].mean() - sub.loc[calma, "c50"].mean()) * 100
            dc75 = (sub.loc[caos, "c75"].mean() - sub.loc[calma, "c75"].mean()) * 100
            out.append((dc50, dc75))
        (min_dc50, min_dc75), (max_dc50, max_dc75) = out
        print(f"  {code:<16} {min_dc50:>+11.1f} {min_dc75:>+11.1f} {max_dc50:>+11.1f} {max_dc75:>+11.1f}")

    # ── 3. Monotonicidad: cascade rate por decil de D3 ──────────────
    print("\n" + "═"*100)
    print("  FASE 2.3 — Cascade_50 rate por decil de D3 (¿monotónico?)")
    print("═"*100)
    for code in ["fg", "vvix", "bsi", "pcr", "skew", "vix", "credit", "yield_curve", "sv5_turbulence"]:
        col = f"{code}_d3"
        m = ~np.isnan(df[col])
        sub = df[m]
        if len(sub) < 100:
            continue
        q = pd.qcut(sub[col], 5, labels=False, duplicates="drop")
        rates = sub.groupby(q)["c50"].agg(["mean", "count"])
        s = "  " + code.ljust(16) + " ".join(f"{r['mean']*100:4.0f}%({int(r['count']):>3})" for _, r in rates.iterrows())
        print(s)

    # ── 4. ¿El caos coincide con SPY moviéndose ya? ─────────────────
    print("\n" + "═"*100)
    print("  FASE 2.4 — ¿El caos (D3 alto) coincide con SPY moviéndose YA?  ρ(D3, |SPY ret| contemporáneo)")
    print("═"*100)
    print(f"  {'estación':<16} {'ρ(D3,|ret| t)':>14} {'ρ(D3,|ret| t+1)':>16} {'D3 predice?':>12}")
    for code in ALL:
        col = f"{code}_d3"
        m = ~np.isnan(df[col]) & ~np.isnan(df["spy_abs_now"])
        if m.sum() < 30:
            continue
        r_now = spearmanr(df.loc[m, col], df.loc[m, "spy_abs_now"])[0]
        m2 = ~np.isnan(df[col]) & ~np.isnan(df["spy_abs_next"])
        r_next = spearmanr(df.loc[m2, col], df.loc[m2, "spy_abs_next"])[0]
        pred = "SÍ (forward)" if abs(r_next) > 0.05 else "NO (contemp.)"
        print(f"  {code:<16} {r_now:>+14.4f} {r_next:>+16.4f} {pred:>12}")

    # ── 5. bootstrap significancia de los Δc50 clave ────────────────
    print("\n" + "═"*100)
    print("  FASE 2.5 — Bootstrap (1000x) del gap caos−calma en cascade_50")
    print("═"*100)
    rng = np.random.RandomState(42)
    for code in ["fg", "vvix", "bsi", "pcr", "skew", "vix", "credit", "sv5_turbulence"]:
        col = f"{code}_d3"
        m = ~np.isnan(df[col])
        sub = df[m]
        if len(sub) < 60:
            continue
        d3 = sub[col].values; c50 = sub["c50"].values
        lo_t, hi_t = np.quantile(d3, 0.33), np.quantile(d3, 0.67)
        lo_m = d3 <= lo_t; hi_m = d3 >= hi_t
        obs_gap = c50[hi_m].mean() - c50[lo_m].mean()
        # bootstrap del gap
        n_lo, n_hi = lo_m.sum(), hi_m.sum()
        gaps = []
        for _ in range(1000):
            i_lo = rng.choice(np.where(lo_m)[0], n_lo, replace=True)
            i_hi = rng.choice(np.where(hi_m)[0], n_hi, replace=True)
            gaps.append(c50[i_hi].mean() - c50[i_lo].mean())
        ci = np.percentile(gaps, [2.5, 97.5])
        sig = "***" if not (ci[0] <= 0 <= ci[1]) else "ns"
        print(f"  {code:<16} gap={obs_gap*100:+6.1f}pp  CI95=[{ci[0]*100:+.1f}, {ci[1]*100:+.1f}]pp  {sig}  "
              f"(N_calma={n_lo}, N_caos={n_hi})")

if __name__ == "__main__":
    main()
