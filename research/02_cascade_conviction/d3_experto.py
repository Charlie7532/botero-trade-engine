#!/usr/bin/env python3
"""
D3 (VOLATILIDAD = std(2d)/std(10d)) — Análisis completo por estación
=====================================================================
Misión: comprender QUÉ SIGNIFICA la volatilidad de cada indicador y por qué
su poder predictivo (cascade) varía entre estaciones.

1. D3 = rolling(2).std() / rolling(10).std() de la serie diaria del indicador.
   D3 < 1  → el indicador se movió MENOS en los últimos 2 días que lo típico (CALMA/compresión).
   D3 > 1  → el indicador se movió MÁS en los últimos 2 días que lo típico (CAOS/expansión).
2. Correlación con tríada zigzag: cascade_50, cascade_75, leg_bear (dirección).
3. Confirma hallazgo previo (FG/VVIX/BSI/PCR discriminan cascade; macro neutro; SKEW invertido).
4. Mecanismo económico: ρ(D3, nivel), ρ(D3, velocidad), matriz de correlación D3 entre estaciones.
5. Correlación D3 con movimiento diario de SPY (contemporáneo + forward).
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
GRUPO = {
    "A_direccional": ["vix", "bsi", "fg", "credit", "rotation"],
    "B_modulador": ["skew", "pcr", "sv5_turbulence"],
    "C_contexto": ["dxy", "yield_curve", "vvix"],
}

def spearman(x, y):
    m = ~np.isnan(x) & ~np.isnan(y)
    if m.sum() < 8 or np.std(x[m]) == 0 or np.std(y[m]) == 0:
        return np.nan, np.nan, m.sum()
    r, p = spearmanr(x[m], y[m])
    return (float(r) if not np.isnan(r) else np.nan), (float(p) if not np.isnan(p) else np.nan), int(m.sum())

def main():
    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)

    # ── 1. Zigzag legs ─────────────────────────────────────────────
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

    # ── 2. D3 por estación + SPY ───────────────────────────────────
    d3_series = {}; lvl_series = {}; vel_series = {}
    for code, cfg in STATION_CONFIG.items():
        dfi = store.load_bars(cfg["ticker"], "1d")
        if dfi is None or dfi.empty:
            print(f"  ⚠️ {code}: sin datos para {cfg['ticker']}")
            continue
        s = dfi["close"].copy()
        s.index = [d.date() if hasattr(d, "date") else d for d in pd.to_datetime(s.index)]
        std2 = s.rolling(2).std(); std10 = s.rolling(10).std()
        d3 = (std2 / std10).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        d3_series[code] = d3
        lvl_series[code] = s
        vel_series[code] = s.diff(3)  # D2

    # SPY barras
    spy = store.load_bars("SPY", "1d")["close"].copy()
    spy.index = [d.date() if hasattr(d, "date") else d for d in pd.to_datetime(spy.index)]
    spy_ret = spy.pct_change()
    spy_abs = spy_ret.abs()
    store.close()

    # ── 3. Observaciones: D3 en cada pivot ─────────────────────────
    rows = []
    for _, r in df25.iterrows():
        pd_ = r["pivot_date"]
        rec = {"pivot_date": pd_, "c50": r["c50"], "c75": r["c75"],
               "leg_bear": r["leg_bear"], "type": r["start_type"]}
        for code in ALL:
            s = d3_series.get(code)
            if s is None:
                rec[f"{code}_d3"] = np.nan; continue
            idx = s.index[s.index <= pd_]
            rec[f"{code}_d3"] = float(s.iloc[len(idx)-1]) if len(idx) > 0 else np.nan
        rows.append(rec)
    df = pd.DataFrame(rows)
    N = len(df)
    print(f"\n  N pivots zz25: {N} | cascade_50 rate: {df['c50'].mean():.3f} | "
          f"cascade_75 rate: {df['c75'].mean():.3f} | leg_bear rate: {df['leg_bear'].mean():.3f}")

    # ── 4. Correlación + terciles ──────────────────────────────────
    print("\n" + "═"*104)
    print("  TABLA 1 — D3 vs tríada zigzag (Spearman ρ + gap tercil caos−calma)")
    print("═"*104)
    print(f"  {'estación':<16} {'ρ(D3,c50)':>10} {'p':>8} {'ρ(D3,c75)':>10} {'ρ(D3,dir)':>10} "
          f"{'Δc50(pp)':>10} {'Δc75(pp)':>10} {'Δdir(pp)':>10} {'N':>5}")

    results = {}
    for code in ALL:
        col = f"{code}_d3"
        d3 = df[col]
        mask = ~np.isnan(d3)
        n = int(mask.sum())
        if n < 30:
            continue
        r_c50, p_c50, _ = spearman(d3, df["c50"])
        r_c75, p_c75, _ = spearman(d3, df["c75"])
        r_dir, p_dir, _ = spearman(d3, df["leg_bear"])

        # tercil split sobre los valores válidos
        valid = d3[mask]
        lo_thr, hi_thr = valid.quantile(0.33), valid.quantile(0.67)
        lo = d3 <= lo_thr
        hi = d3 >= hi_thr
        c50_lo = df.loc[lo, "c50"].mean(); c50_hi = df.loc[hi, "c50"].mean()
        c75_lo = df.loc[lo, "c75"].mean(); c75_hi = df.loc[hi, "c75"].mean()
        dir_lo = df.loc[lo, "leg_bear"].mean(); dir_hi = df.loc[hi, "leg_bear"].mean()
        dc50 = (c50_hi - c50_lo) * 100
        dc75 = (c75_hi - c75_lo) * 100
        ddir = (dir_hi - dir_lo) * 100

        results[code] = dict(r_c50=r_c50, p_c50=p_c50, r_c75=r_c75, r_dir=r_dir,
                             dc50=dc50, dc75=dc75, ddir=ddir, n=n,
                             c50_lo=c50_lo, c50_hi=c50_hi, lo_thr=lo_thr, hi_thr=hi_thr)
        print(f"  {code:<16} {r_c50:>+10.4f} {p_c50:>8.2g} {r_c75:>+10.4f} {r_dir:>+10.4f} "
              f"{dc50:>+10.1f} {dc75:>+10.1f} {ddir:>+10.1f} {n:>5}")

    # ── 5. Mecanismo: ρ(D3, nivel) y ρ(D3, velocidad D2) ───────────
    print("\n" + "═"*104)
    print("  TABLA 2 — ¿Con qué coincide el CAOS (D3 alto)?  ρ(D3, nivel) y ρ(D3, velocidad)")
    print("═"*104)
    print(f"  {'estación':<16} {'ρ(D3,nivel)':>12} {'ρ(D3,vel Δ3d)':>14} {'tipo':>14}")
    for code in ALL:
        s = d3_series.get(code); lv = lvl_series.get(code); ve = vel_series.get(code)
        if s is None:
            continue
        # alinear sobre el índice del D3 (fechas comunes)
        common = s.index.intersection(lv.index).intersection(ve.index)
        a = s.loc[common].values; b = lv.loc[common].values; c = ve.loc[common].values
        r_lvl, p_lvl, _ = spearman(pd.Series(a), pd.Series(b))
        r_vel, p_vel, _ = spearman(pd.Series(a), pd.Series(c))
        tipo = ""
        for g, codes in GRUPO.items():
            if code in codes:
                tipo = g
        print(f"  {code:<16} {r_lvl:>+12.4f} {r_vel:>+14.4f} {tipo:>14}")

    # ── 6. Matriz de correlación D3 entre estaciones ───────────────
    print("\n" + "═"*104)
    print("  TABLA 3 — Matriz de correlación D3 entre estaciones (¿qué caos se mueve junto?)")
    print("═"*104)
    # construir dataframe alineado por fecha
    d3_df = pd.DataFrame(d3_series).dropna(how="all")
    corr = d3_df.corr(method="spearman")
    codes_present = [c for c in ALL if c in corr.columns]
    hdr = "  " + "".join(f"{c[:6]:>9}" for c in codes_present)
    print(hdr)
    for c1 in codes_present:
        row = f"  {c1:<8}"
        for c2 in codes_present:
            v = corr.loc[c1, c2]
            row += f"{v:>+9.2f}" if not np.isnan(v) else f"{'·':>9}"
        print(row)

    # ── 7. D3 vs movimiento diario de SPY ──────────────────────────
    print("\n" + "═"*104)
    print("  TABLA 4 — D3 del indicador vs movimiento diario de SPY (contemporáneo y forward)")
    print("═"*104)
    print(f"  {'estación':<16} {'ρ(D3,|ret| t)':>14} {'ρ(D3,ret t)':>13} {'ρ(D3,|ret| t+1)':>16} {'N':>6}")
    spy_cont = {}; spy_fwd = {}
    for code in ALL:
        s = d3_series.get(code)
        if s is None:
            continue
        common_t = s.index.intersection(spy_abs.index)
        d3v = s.loc[common_t].values
        absv = spy_abs.loc[common_t].values
        retv = spy_ret.loc[common_t].values
        r_cont, p_cont, n_cont = spearman(pd.Series(d3v), pd.Series(absv))
        r_ret, _, _ = spearman(pd.Series(d3v), pd.Series(retv))
        # forward: D3(t) vs |ret|(t+1)  → shift spy_abs
        spy_abs_shift = spy_abs.shift(-1)
        common_f = s.index.intersection(spy_abs_shift.index)
        d3vf = s.loc[common_f].values
        absvf = spy_abs_shift.loc[common_f].values
        r_fwd, p_fwd, n_fwd = spearman(pd.Series(d3vf), pd.Series(absvf))
        print(f"  {code:<16} {r_cont:>+14.4f} {r_ret:>+13.4f} {r_fwd:>+16.4f} {n_cont:>6}")

    # ── 8. Estadísticas descriptivas de D3 ─────────────────────────
    print("\n" + "═"*104)
    print("  TABLA 5 — Distribución de D3 (mediana, percentiles) — ¿qué tan 'caótico' es típico?")
    print("═"*104)
    print(f"  {'estación':<16} {'mediana':>9} {'p33':>8} {'p67':>8} {'p90':>8} {'max':>8}")
    for code in ALL:
        s = d3_series.get(code)
        if s is None:
            continue
        v = s.dropna()
        print(f"  {code:<16} {v.median():>9.3f} {v.quantile(0.33):>8.3f} {v.quantile(0.67):>8.3f} "
              f"{v.quantile(0.90):>8.3f} {v.max():>8.3f}")

    # ── 9. Guardar resultados ──────────────────────────────────────
    out = {"N_pivots": N, "cascade_50_rate": float(df["c50"].mean()),
           "cascade_75_rate": float(df["c75"].mean()),
           "per_station": {k: {kk: (None if (isinstance(vv, float) and np.isnan(vv)) else vv)
                               for kk, vv in v.items()} for k, v in results.items()}}
    outpath = Path("/root/botero-trade/data/research/d3_results.json")
    with open(outpath, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n  💾 Resultados guardados en {outpath}")

    # ── 10. Clasificación final ────────────────────────────────────
    print("\n" + "═"*104)
    print("  CLASIFICACIÓN (Δc50 pp = caos−calma en cascade_50)")
    print("═"*104)
    for code, v in sorted(results.items(), key=lambda x: x[1]["dc50"]):
        if abs(v["dc50"]) < 3:
            cls = "NEUTRO"
        elif v["dc50"] < 0:
            cls = "APAGA cascade (caos→menos cascade)"
        else:
            cls = "ENCIENDE cascade (caos→más cascade)"
        print(f"  {code:<16} Δc50={v['dc50']:+.1f}pp  → {cls}   (N={v['n']})")

if __name__ == "__main__":
    main()
