#!/usr/bin/env python3
"""SEÑAL D3 + AUDITORÍA DE SEMIVIDA/OVERSHOOTING
=================================================
Parte A — Señal D3: ¿la inestabilidad (D3) en el inicio de un episodio de
crisis predice la velocidad de absorción del impulso?
  Hipótesis: D3 alto (volatilidad de la volatilidad rota) → absorción lenta
  (cambio de régimen). D3 bajo → absorción rápida (shock ordinario).

Parte B — Auditoría de overshooting de la semivida:
  1. ¿El decaimiento sobrepasa el nivel de reposo (oscilación real)?
  2. ¿La semivida es estable al mover el inicio del ajuste (sensibilidad)?
  3. ¿Un ajuste multi-fase describe mejor que exponencial simple (GFC)?
  (Si la semivida depende del punto de inicio o del nº de fases, es un
   artefacto del ajuste — overshooting del modelo, no propiedad del mercado.)

Validación de cordura: la semivida mediana debe reproducir ~8 días.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import fisher_exact, spearmanr

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT / "backend/modules/entry_decision/domain/rules"))
from sigma_overflow import STATION_MU_SIGMA
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

store = TimescaleDataStore(); conn = store._conn()
df = pd.read_sql("SELECT time::date as date, close FROM market.ohlcv_bars "
                 "WHERE ticker='VIX' AND timeframe='1d' ORDER BY time", conn)
store.close()
s = df.set_index("date")["close"].astype(float)

mu, sig = STATION_MU_SIGMA["vix"]["d1"]
z = (s - mu) / sig

# ── D3 diario del VIX: std(2)/std(10) (misma definición que la capa SIGMET) ──
d3 = s.rolling(2).std() / s.rolling(10).std()
d3z = (d3 - d3.mean()) / d3.std()          # z-score del propio D3
TERC = d3.quantile([1/3, 2/3]).values
print(f"D3 VIX diario: media={d3.mean():.3f} terciles={np.round(TERC,3)}")

# ── Episodios de crisis: z cruza +3 → decae bajo +2 ──
ep = []; in_ep = False; start = None
for dt, zv in z.items():
    if not in_ep and zv > 3.0:
        in_ep = True; start = dt
    elif in_ep and zv < 2.0:
        ep.append((start, dt)); in_ep = False
if in_ep:
    ep.append((start, z.index[-1]))

rows = []
for (t0, t1) in ep:
    dur = len(s.loc[t0:t1])                     # barras hasta absorber (<2σ)
    d3_onset = d3.get(t0, np.nan)
    d3z_onset = d3z.get(t0, np.nan)
    if d3z_onset > 1:
        estado = "INESTABLE"
    elif d3z_onset < -0.5:
        estado = "CALMADO"
    else:
        estado = "MEDIO"
    peak = s.loc[t0:t1].max()
    rows.append({"inicio": str(t0), "fin": str(t1), "dur_barras": dur,
                 "peak": round(peak, 1), "peak_z": round((peak-mu)/sig, 1),
                 "d3_onset": round(d3_onset, 3) if not np.isnan(d3_onset) else None,
                 "d3z_onset": round(d3z_onset, 2) if not np.isnan(d3z_onset) else None,
                 "estado_D3": estado})
E = pd.DataFrame(rows)
pd.set_option("display.width", 200)
print(f"\n{'='*90}\nPARTE A — SEÑAL D3: {len(E)} episodios de crisis")
print(f"{'='*90}")
print(E.to_string(index=False))

# ¿D3 en el inicio predice absorción lenta?
med = E["dur_barras"].median()
ina = E[E["estado_D3"] == "INESTABLE"]
cal = E[E["estado_D3"].isin(["CALMADO", "MEDIO"])]
tabla = [[(ina["dur_barras"] > med).sum(), (ina["dur_barras"] <= med).sum()],
         [(cal["dur_barras"] > med).sum(), (cal["dur_barras"] <= med).sum()]]
or_, p_fisher = fisher_exact(tabla, alternative="greater")
rho, p_spear = spearmanr(E["d3_onset"].dropna(), E.loc[E["d3_onset"].notna(), "dur_barras"])
print(f"\nMediana de absorción: {med:.0f} barras")
print(f"INESTABLE: n={len(ina)}, absorción media={ina['dur_barras'].mean():.0f}b")
print(f"CALMADO/MEDIO: n={len(cal)}, absorción media={cal['dur_barras'].mean():.0f}b")
print(f"Fisher (lenta|inestable): p={p_fisher:.4f} | Spearman(d3_onset, dur): rho={rho:.2f} p={p_spear:.3f}")

# ── PARTE B — Auditoría de overshooting de la semivida ──
print(f"\n{'='*90}\nPARTE B — AUDITORÍA DE OVERSHOOTING DE LA SEMIVIDA")
print(f"{'='*90}")
halves, overshoots, sens = [], [], []
for (t0, t1) in ep:
    seg = s.loc[t0:t1]
    if len(seg) < 5:
        continue
    decay = seg.loc[seg.idxmax():]
    if len(decay) < 4:
        continue
    x = decay.values
    y = x - mu
    valid = y > 0
    if valid.sum() < 3:
        continue
    tv = np.arange(len(x))[valid]
    slope, intercept = np.polyfit(tv, np.log(y[valid]), 1)
    kappa = -slope
    if kappa > 0:
        halves.append(np.log(2) / kappa)

    # B1: overshoot real — ¿el decaimiento cae BAJO el nivel de reposo?
    # overshoot = profundidad bajo mu tras el pico (fracción de la amplitud pico-mu)
    amp = seg.max() - mu
    bajo_mu = decay.min() - mu
    if amp > 0:
        overshoots.append(min(0.0, bajo_mu) / amp if bajo_mu < 0 else 0.0)

    # B2: sensibilidad — semivida al iniciar el ajuste +2 barras después del pico
    if valid.sum() > 5:
        tv2 = tv[2:]
        if len(tv2) >= 3:
            slope2, _ = np.polyfit(tv2, np.log(y[valid][2:]), 1)
            if -slope2 > 0:
                sens.append((np.log(2)/kappa, np.log(2)/(-slope2)))

h = np.array(halves)
print(f"B0 validación: semivida mediana = {np.median(h):.1f}d (esperado ~8d)")
ov = np.array(overshoots)
print(f"B1 overshoot real: mediana={np.median(ov):.3f} de la amplitud "
      f"({(ov < -0.05).sum()}/{len(ov)} episodios sobrepasan 5% bajo reposo)")
if sens:
    a, b = zip(*sens)
    cambia = np.abs(np.array(b) - np.array(a)) / np.array(a)
    print(f"B2 sensibilidad: semivida cambia {np.median(cambia)*100:.0f}% (mediana) "
          f"al mover el inicio del ajuste +2 barras")

# B3: ¿GFC necesita multi-fase? ajuste 1 fase vs 2 fases (BIC)
def bic_sse(sse, n, k):
    return n * np.log(sse / n) + k * np.log(n)
for (t0, t1) in ep:
    seg = s.loc[t0:t1]
    if len(seg) < 30:
        continue
    decay = seg.loc[seg.idxmax():]
    x = decay.values; y = x - mu; valid = y > 0
    tv = np.arange(len(x))[valid]
    if valid.sum() < 20:
        continue
    lv = np.log(y[valid])
    # 1 fase
    sl1, ic1 = np.polyfit(tv, lv, 1)
    sse1 = np.sum((lv - (ic1 + sl1*tv))**2)
    # 2 fases: punto de quiebre en el medio
    mid = len(tv)//2
    sl_a, ic_a = np.polyfit(tv[:mid], lv[:mid], 1)
    sl_b, ic_b = np.polyfit(tv[mid:], lv[mid:], 1)
    sse2 = (np.sum((lv[:mid] - (ic_a + sl_a*tv[:mid]))**2) +
            np.sum((lv[mid:] - (ic_b + sl_b*tv[mid:]))**2))
    n = valid.sum()
    print(f"B3 episodio {t0} (n={n}): 1-fase κ={-sl1:.3f} | 2-fases κa={-sl_a:.3f} κb={-sl_b:.3f} | "
          f"BIC1={bic_sse(sse1,n,2):.0f} BIC2={bic_sse(sse2,n,4):.0f} → "
          f"{'2 fases mejora' if bic_sse(sse2,n,4) < bic_sse(sse1,n,2) else '1 fase basta'}")
