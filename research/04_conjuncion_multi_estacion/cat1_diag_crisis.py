#!/usr/bin/env python3
"""Diagnóstico: salud económica en crisis conocidas (GFC 2008, COVID 2020, bear 2022)."""
import sys
sys.path.insert(0, '/root/botero-trade')
import pandas as pd
import numpy as np
import importlib.util

spec = importlib.util.spec_from_file_location("cat1", "/root/botero-trade/research/04_conjuncion_multi_estacion/cat1_economia.py")
cat1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cat1)

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

store = TimescaleDataStore()
raw = {}
for t in cat1.SENSORS:
    raw[t] = store.load_bars(t, "1d")["close"].dropna()
spy = store.load_bars("SPY", "1d")["close"].dropna()
store.close()

ci = raw["CREDIT_RATIO"].index
for t in cat1.SENSORS:
    ci = ci.intersection(raw[t].index)

# Reconstruir D y health (reutilizando funciones del módulo)
D = {}
for ticker, station in cat1.SENSORS.items():
    s = raw[ticker].reindex(ci)
    df = pd.DataFrame({"val": s})
    df["d2"] = df["val"].diff(3)
    df["d3"] = df["val"].rolling(2).std() / df["val"].rolling(10).std()
    mu, sd = float(df["val"].mean()), float(df["val"].std())
    fs = cat1.FS[station]
    rows = []
    for ts, row in df.iterrows():
        v = row["val"]
        if pd.isna(v):
            rows.append((None, None, None, None, np.nan)); continue
        li = cat1.classify_idx(v, fs["edges_d1"])
        d1 = cat1.classify(v, fs["edges_d1"], fs["labels_d1"])
        hs, depth = cat1.health_score(station, v, li, mu, sd)
        rows.append((li, d1, hs, depth, v))
    df["idx_d1"] = [r[0] for r in rows]
    df["label_d1"] = [r[1] for r in rows]
    df["health"] = [r[2] for r in rows]
    df["depth"] = [r[3] for r in rows]
    D[ticker] = df

health = pd.DataFrame(index=ci)
for t in cat1.SENSORS:
    health[t] = D[t]["health"]
health["salud"] = health[list(cat1.SENSORS)].mean(axis=1)

for label, s, e in [("GFC Sep-Nov 2008", "2008-09-15", "2008-11-15"),
                    ("COVID Feb-Apr 2020", "2020-02-20", "2020-04-20"),
                    ("Bear 2022", "2022-06-01", "2022-10-31")]:
    m = (ci >= pd.Timestamp(s, tz="UTC")) & (ci <= pd.Timestamp(e, tz="UTC"))
    h = health["salud"][m]
    print(f"--- {label} ---")
    print(f"  salud: mean={h.mean():.1f}% min={h.min():.1f}% max={h.max():.1f}%")
    print(f"  días <40%: {(h<40).sum()} / {(h<50).sum()} <50%")
    for t in cat1.SENSORS:
        hs = D[t]["health"][m]
        print(f"  {t:<15} health mean={hs.mean():.1f}")
    # día de mínima salud
    imin = h.idxmin()
    print(f"  día de mínima salud: {imin.date()} = {h.min():.1f}%")
    for t in cat1.SENSORS:
        print(f"    {t:<15} {D[t].loc[imin,'label_d1']} (health {D[t].loc[imin,'health']:.0f})")
