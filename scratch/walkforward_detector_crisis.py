#!/usr/bin/env python3
"""
WALK-FORWARD DEL DETECTOR DE RÉGIMEN DE CRISIS (Auditoría P1.5, 22-Ago-2026)
==============================================================================
Pregunta: ¿el detector de overflow ±3σ sigue funcionando cuando μ/σ se calibran
SOLO con datos pasados (ventana expansiva), en lugar de con toda la historia
(como hace hoy STATION_MU_SIGMA, que tiene look-ahead implícito)?

Método:
  1. Para cada estación con serie diaria (VIX, VVIX, SKEW, HYG/LQD→credit proxy,
     DXY), calcular d1=nivel, d2=diff(3), d3=std(2)/std(10) — idéntico al motor.
  2. Calibración FIJA (actual): μ/σ de STATION_MU_SIGMA sobre toda la historia.
  3. Calibración WALK-FORWARD: ventana expansiva, recalibrada cada año, usando
     SOLO datos hasta el año anterior. Mínimo 2 años de entrenamiento.
  4. Comparar: (a) tasa de detección anual fija vs walk-forward;
     (b) ¿las crisis conocidas siguen detectadas con walk-forward?;
     (c) deriva de μ/σ por estación (¿qué tan no-estacionaria es cada una?).
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT / "backend/modules/entry_decision/domain/rules"))
from sigma_overflow import STATION_MU_SIGMA
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

store = TimescaleDataStore(); conn = store._conn()

# Mapeo estación METAR → ticker diario disponible
# CORREGIDO 22-Ago: la serie real de credit SÍ existe en el Vault como CREDIT_RATIO
# (μ=0.6241 σ=0.0503 = idéntica a STATION_MU_SIGMA["credit"]["d1"]). El intento
# previo con HYG era un proxy de precio inválido (deriva 1358σ = artefacto).
TICKERS = {"vix": "VIX", "vvix": "VVIX", "skew": "SKEW", "dxy": "DXY",
           "credit": "CREDIT_RATIO"}

MIN_TRAIN_DIAS = 504  # 2 años

def dims_daily(vals):
    """Calcula d1, d2, d3 igual que el motor (v3_fact_table_engine L463-468)."""
    df = pd.DataFrame({"val": vals})
    df["d1"] = df["val"]
    df["d2"] = df["val"].diff(3)
    v2 = df["val"].rolling(2).std()
    v10 = df["val"].rolling(10).std().replace(0, np.nan)
    df["d3"] = (v2 / v10).fillna(1.0)
    return df

data = {}
for est, tkr in TICKERS.items():
    df = pd.read_sql(f"SELECT time::date as date, close FROM market.ohlcv_bars "
                     f"WHERE ticker='{tkr}' AND timeframe='1d' ORDER BY time", conn)
    s = df.set_index("date")["close"].astype(float)
    s.index = pd.to_datetime(s.index)
    data[est] = dims_daily(s)
store.close()

print(f"{'estación':>10s} | {'n días':>6s} | {'rango':>23s}")
for est, d in data.items():
    print(f"{est:>10s} | {len(d):>6d} | {str(d.index.min())} → {str(d.index.max())}")

# ── Calibración FIJA (actual) ──
def detect_fixed(d, est):
    """Overflow con μ/σ fijos de STATION_MU_SIGMA (método actual)."""
    out = {}
    for dim in ["d1", "d2", "d3"]:
        mu, sig = STATION_MU_SIGMA[est][dim]
        z = (d[dim] - mu) / sig
        out[dim] = z.abs() > 3.0
    return pd.DataFrame(out).any(axis=1)

# ── Calibración WALK-FORWARD (ventana expansiva, recalibrada anual) ──
def detect_wf(d, est):
    """Overflow con μ/σ de ventana expansiva: al inicio de cada año, recalibrar
    con SOLO los datos de los años anteriores (mínimo MIN_TRAIN_DIAS)."""
    out = pd.Series(False, index=d.index)
    years = sorted(d.index.year.unique())
    for yr in years:
        train = d[d.index.year < yr]
        if len(train) < MIN_TRAIN_DIAS:
            continue
        mask_yr = d.index.year == yr
        for dim in ["d1", "d2", "d3"]:
            mu = train[dim].mean()
            sig = train[dim].std()
            if sig == 0 or np.isnan(sig):
                continue
            z = (d.loc[mask_yr, dim] - mu) / sig
            out[mask_yr] = out[mask_yr] | (z.abs() > 3.0)
    return out

print(f"\n{'='*100}")
print(f"COMPARACIÓN: detección FIJA vs WALK-FORWARD")
print(f"{'='*100}")
print(f"{'estación':>10s} | {'fija total':>10s} {'fija %':>7s} | {'wf total':>9s} {'wf %':>6s} | "
      f"{'Δ %':>6s} | {'correl':>6s}")

resultados = {}
for est, d in data.items():
    fija = detect_fixed(d, est)
    wf = detect_wf(d, est)
    # alinear
    idx = fija.index.intersection(wf.index)
    fija, wf = fija.loc[idx], wf.loc[idx]
    n_fija, n_wf = fija.sum(), wf.sum()
    pct_fija = fija.mean() * 100
    pct_wf = wf.mean() * 100
    corr = np.corrcoef(fija.astype(int), wf.astype(int))[0, 1] if fija.std() > 0 and wf.std() > 0 else np.nan
    resultados[est] = {"fija": fija, "wf": wf}
    print(f"{est:>10s} | {n_fija:>10d} {pct_fija:>6.2f}% | {n_wf:>9d} {pct_wf:>5.2f}% | "
          f"{pct_wf-pct_fija:>+5.2f} | {corr:>6.3f}")

# ── Crisis conocidas: ¿detectadas por ambos métodos? ──
CRISIS = {
    "LTCM 1998": ("1998-08-01", "1998-10-31"),
    "Dot-com 2000-02": ("2000-03-01", "2002-10-31"),
    "GFC 2007-09": ("2007-10-01", "2009-03-31"),
    "Flash 2010": ("2010-05-01", "2010-05-31"),
    "Volmageddon 2018": ("2018-02-01", "2018-02-28"),
    "Pandemia 2020": ("2020-02-15", "2020-04-30"),
    "Yen carry 2024": ("2024-08-01", "2024-08-15"),
    "Aranceles 2025": ("2025-04-01", "2025-04-30"),
}
print(f"\n{'='*100}")
print(f"CRISIS CONOCIDAS — detección FIJA vs WALK-FORWARD")
print(f"{'='*100}")
print(f"{'crisis':>20s} | ", end="")
for est in data:
    print(f"{est:>8s} F/WF", end=" | ")
print()

for nombre, (t0, t1) in CRISIS.items():
    print(f"{nombre:>20s} | ", end="")
    for est in data:
        r = resultados[est]
        win = r["fija"].index[(r["fija"].index >= t0) & (r["fija"].index <= t1)]
        det_f = int(r["fija"].loc[win].sum()) if len(win) else 0
        det_w = int(r["wf"].loc[win].sum()) if len(win) else 0
        print(f"{det_f:>4d}/{det_w:<4d}", end=" | ")
    print()

# ── Deriva de μ/σ: no-estacionariedad ──
print(f"\n{'='*100}")
print(f"DERIVA DE μ/σ (no-estacionariedad) — fija vs últimos 5 años")
print(f"{'='*100}")
for est, d in data.items():
    recientes = d[d.index.year >= d.index.max().year - 5]
    print(f"\n{est}:")
    for dim in ["d1", "d2", "d3"]:
        mu_f, sig_f = STATION_MU_SIGMA[est][dim]
        mu_r, sig_r = recientes[dim].mean(), recientes[dim].std()
        drift_mu = (mu_r - mu_f) / sig_f if sig_f > 0 else np.nan
        drift_sig = sig_r / sig_f if sig_f > 0 else np.nan
        mark = " ⚠️" if abs(drift_mu) > 0.5 or abs(drift_sig - 1) > 0.5 else ""
        print(f"  {dim}: μ fija={mu_f:.3f} → reciente={mu_r:.3f} (deriva {drift_mu:+.2f}σ) | "
              f"σ fija={sig_f:.3f} → reciente={sig_r:.3f} (ratio {drift_sig:.2f}){mark}")
