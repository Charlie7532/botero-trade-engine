#!/usr/bin/env python3
"""¿Se repiten las señales DESPUÉS de un extremo fuera de escala (±3σ)?
Detecta eventos ±3σ con validate_overflow (capa SIGMET oficial) sobre cada
fecha de pivote de quants_obs, y mide qué señales disparan en los N días siguientes.
Compara contra la tasa base de cada señal (permutation)."""
import sys
from pathlib import Path
ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))
sys.path.insert(0, str(ROOT / "backend/modules/entry_decision/domain/rules"))
import numpy as np, pandas as pd
from medir_senal import SEÑALES, _CERTEZA, cargar_datos
from sigma_overflow import validate_overflow

df, spy = cargar_datos()
dates = pd.DatetimeIndex(df["pivot_date"])
N_DIAS = 5  # ventana tras el extremo

# Estaciones y columnas de valor disponibles en df
ESTACIONES = {
    "vix": "vix_val", "vvix": "vvix_val", "pcr": "pcr_val", "fg": "fg_val",
    "sv5_turbulence": "sv5_turbulence_val", "skew": "skew_val",
    "credit": "credit_val", "bsi": "bsi_val", "dxy": "dxy_val",
    "rotation": "rotation_val",
}
ESTACIONES = {k: v for k, v in ESTACIONES.items() if v in df.columns}

# ── 1. Detectar eventos ±3σ por día (sobre fechas de pivote = universo del análisis) ──
eventos = []  # (fecha, estacion, sigma_depth, direccion)
for est, col in ESTACIONES.items():
    vals = df[col].astype(float)
    for i, v in vals.items():
        if pd.isna(v):
            continue
        depth, flag = validate_overflow(est, "d1", float(v))
        if flag is not None:
            eventos.append((dates[i], est, depth, flag))
ev = pd.DataFrame(eventos, columns=["fecha", "estacion", "depth", "dir"])
ev = ev.sort_values("fecha").reset_index(drop=True)
print(f"Eventos ±3σ detectados (capa SIGMET): {len(ev)}")
print(f"  por estación: {ev['estacion'].value_counts().to_dict()}")
print(f"  UPPER: {(ev['dir']=='UPPER').sum()}, LOWER: {(ev['dir']=='LOWER').sum()}")
print()

# ── 2. Señales activas evaluables ──
activas = {}
for n in SEÑALES:
    cert = str(_CERTEZA.get(n, {}).get("validacion", ""))
    if "RETIRADA" in cert and "duplicado" in cert:
        continue
    if "pivot_type" in str(SEÑALES[n](df.head(0)).index.__class__.__name__):
        pass
    activas[n] = SEÑALES[n](df).astype(bool)

# ── 3. ¿Qué señales disparan en los N días tras cada evento ±3σ? ──
# Precomputar ventanas de índices (una vez, fuera de la permutación)
fechas_np = dates.values
rangos_eventos = []  # lista de ranges de índice por evento
for _, e in ev.iterrows():
    idx0 = int(np.searchsorted(fechas_np, np.datetime64(e["fecha"])))
    rangos_eventos.append(range(idx0, min(idx0 + N_DIAS + 1, len(fechas_np))))

print(f"SEÑALES QUE DISPARAN EN LOS {N_DIAS} DÍAS TRAS UN EXTREMO ±3σ:")
print(f"{'señal':>26s} | {'eventos':>7s} | {'con_señal':>9s} | {'tasa':>5s} | {'tasa_base':>9s} | {'lift':>5s} | {'p_perm':>7s}")
resultados = []
for s, sig in sorted(activas.items()):
    sig_dates = set(dates[sig.values])
    hits = sum(1 for k, e in ev.iterrows()
               if any((e["fecha"] + pd.Timedelta(days=j)) in sig_dates
                      for j in range(0, N_DIAS + 1)))
    total = len(ev)
    tasa = hits / total if total else 0
    base_hits = sum(1 for d in dates
                    if any((d + pd.Timedelta(days=k)) in sig_dates
                           for k in range(-N_DIAS, N_DIAS + 1)))
    tasa_base = base_hits / len(dates)
    lift = tasa / tasa_base if tasa_base > 0 else np.inf
    # permutation: 200 remuestreos usando rangos precomputados
    rng = np.random.default_rng(42)
    sig_arr = sig.values
    perm_hits = []
    for _ in range(200):
        sh = rng.permutation(sig_arr)
        h = sum(1 for rng_ in rangos_eventos if any(sh[k] for k in rng_))
        perm_hits.append(h / total if total else 0)
    p_perm = float(np.mean(np.array(perm_hits) >= tasa))
    mark = "✓✓" if p_perm < 0.01 else ("✓" if p_perm < 0.05 else "")
    print(f"{s:>26s} | {total:>7d} | {hits:>9d} | {tasa:>4.0%} | {tasa_base:>8.0%} | {lift:>5.2f} | {p_perm:>7.3f} {mark}")
    resultados.append({"señal": s, "eventos": total, "con_señal": hits, "tasa": tasa,
                       "tasa_base": tasa_base, "lift": lift, "p": p_perm})

# ── 4. ¿Los extremos UPPER vs LOWER disparan señales distintas? ──
print()
print("DIFERENCIA UPPER vs LOWER (eventos con al menos una señal en +5d):")
for direccion in ("UPPER", "LOWER"):
    sub = ev[ev["dir"] == direccion]
    con = 0
    for _, e in sub.iterrows():
        d = e["fecha"]
        ventana = set(d + pd.Timedelta(days=k) for k in range(0, N_DIAS + 1))
        if any(len(ventana & set(dates[s.values])) for s in activas.values()):
            con += 1
    print(f"  {direccion:>6s}: {con}/{len(sub)} = {con/len(sub):.0%} eventos seguidos de señal")
