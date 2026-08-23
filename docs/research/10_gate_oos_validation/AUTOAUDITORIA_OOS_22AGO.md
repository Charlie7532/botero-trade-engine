# AUTOAUDITORÍA HONESTA — Validador OOS + Cadena de Medición (22-Ago-2026)

**Auditor:** Hermes (qwen/qwen3.8-max) — autoauditoría antes de auditoría externa
**Propósito:** encontrar los fallos ANTES de celebrar el resultado OOS.

> Regla: si un número parece demasiado bueno, es que hay look-ahead en algún lugar.

---

## HALLAZGO 1 — LOOK-AHEAD EN EL BINNEO DE D2/D3 (CONFIRMADO EN CÓDIGO) ⚠️ CRÍTICO

**Dónde:** `backend/scripts/_lib/v3_fact_table_engine.py` líneas 469-483.

- **D1 es limpio:** usa `expanding(min_periods=252).rank(pct=True)` — solo datos pasados. ✅
- **D2 y D3 NO son limpios:** los bordes `d2_edges` y `d3_vol_edges` se calculan como
  `calib_df.quantile(...)` sobre **toda la historia**, y CADA barra histórica se
  clasifica contra esos bordes. Esto es información del futuro filtrando hacia atrás.

```python
d1_expanding_rank = ind_df["val"].expanding(min_periods=252).rank(pct=True)  # ← limpio
calib_df = ind_df[...]
d2_edges = calib_df["d2_velocity"].quantile(PERCENTILES_D2_GAUSS)   # ← TODA la historia
d3_vol_edges = calib_df["vol_norm"].quantile(PERCENTILES_D3_GAUSS)  # ← TODA la historia
ind_df["bin_d2"] = ind_df["d2_velocity"].apply(classify_value, d2_edges, ...)  # ← look-ahead
ind_df["bin_d3"] = ind_df["vol_norm"].apply(classify_value, d3_vol_edges, ...) # ← look-ahead
```

**Impacto:** TODOS los state_keys (`D1__D2__D3`) de quants_obs, y por tanto TODAS las
señales definidas sobre state_keys, heredan look-ahead en sus componentes D2 y D3.
El walk-forward OOS que acabo de correr **NO elimina este sesgo** porque la señal ya
llega contaminada al validador. El validador es honesto; el INPUT que consume no lo es.

**Lo que NO está contaminado:** las señales que solo usan D1 (ej. `pcr_put_panic`,
`bsi_washed_out`, `capitulacion` leen `*_sk.split("__")[0]` = solo D1). Las señales que
condicionan en D2/D3 o en `_val/_vel/_vol` numéricos SÍ están contaminadas.

**Corrección pendiente:** re-bin D2/D3 con expanding rank (como D1) y re-generar
quants_obs + re-correr evaluador y validador. Hasta entonces, los edges de señales
con componente D2/D3 son techo teórico con leakage.

---

## HALLAZGO 2 — VEREDICTO "SE REPITE OOS" SOBREVALORADO POR N DE FOLDS ⚠️

Mi criterio de veredicto era: OOS medio > 0 **y** folds_positivos/folds ≥ 0.6.
Con 2-4 folds eso es casi vacío:

| Señal | Folds | Folds+ | sign-test p | ¿Significativo? |
|-------|:---:|:---:|:---:|:---:|
| capitulacion | 2 | 2/2 | n/a | **NO** (mín p con 2 folds = 0.25) |
| skew_paranoia_exit | 1 | 1/1 | n/a | **NO** (1 fold, N=16) |
| pcr_put_panic | 4 | 3/4 | 0.3125 | **NO** (mín p con 4 folds = 0.0625) |
| bsi_washed_out | 6 | 5/6 | 0.1094 | **NO** (p>0.05) |

**Ningún sign-test puede ser significativo con ≤5 folds** (mínimo p posible con 5
folds todos positivos = 0.0313). Con 4 folds el mínimo es 0.0625 > 0.05. Por tanto
ninguna señal alcanza significancia estadística OOS todavía. El "🟢 SE REPITE" debe
leerse como **"dirección correcta, sin potencia estadística aún"**.

---

## HALLAZGO 3 — EL DECAY IS→OOS ES ASIMÉTRICO (SELECCIÓN OPTIMISTA EN IS) 🟡

El `decay = OOS_medio / IS_mejor_celda` compara:
- **IS:** la mejor celda elegida sobre TODA la historia (selección optimista con look-ahead).
- **OOS:** la celda elegida solo con train (selección honesta).

El denominador está inflado por selección optimista, así que decay<1 refleja en parte
esa asimetría, no solo la generalización real. El decay no es un ratio puro de
degradación; está contaminado por el optimismo del IS. Reportarlo como cota superior
de la degradación, no como número exacto.

---

## HALLAZGO 4 — LO QUE SÍ ES SÓLIDO (para no sobrecorregir) ✅

- El **validador OOS en sí es metodológicamente correcto**: celda elegida solo con
  train, baseline por período de test, sin mezclar mercados, first-passage bilateral.
- El **régimen observable** usa solo pivotes confirmados (sin leakage).
- Las señales que leen solo D1 (pcr_put_panic, bsi_washed_out, capitulacion) están
  **libres del look-ahead D2/D3** — son las más confiables del catálogo.
- La **dirección del edge es consistente OOS en todas las señales** (ninguna colapsó
  a negativa). Si fuera overfitting puro, veríamos signos mixtos.

---

## VEREDICTO DE LA AUTOAUDITORÍA

| Componente | Estado |
|-----------|:---:|
| Validador OOS (método) | ✅ Correcto |
| Input quants_obs D1 | ✅ Limpio |
| Input quants_obs D2/D3 | 🔴 **Look-ahead confirmado** |
| Veredicto "SE REPITE" | 🟡 Sobrevalorado por N de folds |
| Métrica decay | 🟡 Asimétrica (IS optimista) |

**Conclusión:** el resultado OOS es **prometedor en dirección pero NO está asegurado**.
El bloqueo real es el binneo D2/D3 con look-ahead (Hallazgo 1). Hasta re-bin y
re-generar quants_obs, ningún edge que toque D2/D3 es confiable, y la potencia
estadística OOS es insuficiente para declarar significancia.

---
**Firma:** qwen/qwen3.8-max (Hermes) · autoauditoría honesta · 22-Ago-2026
