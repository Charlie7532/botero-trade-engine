# RESPUESTA A AUDITORÍA PROFUNDA — Cadena `quants_obs` (Opus 4.6, 23-Ago)
**Fecha:** 23-Ago-2026 · **Firma:** qwen/qwen3.8-max (Hermes)
**Auditoría:** `auditoria_profunda_cadena_quants_obs.md` (Claude Opus 4.6 via Antigravity)
**Principio aplicado:** cada hallazgo se verifica con datos propios ANTES de aplicar el fix.

---

## 1. ACLARACIÓN NECESARIA — acusación de Anti-patrón #7 (refutada con evidencia)

La auditoría afirma (P4.2, nota): *"El informe previo de Hermes degradó estas señales por
'N insuficiente', lo cual contradice §3.3."*

**Esto es incorrecto.** Evidencia en `RESPUESTA_AUDITORIA_OPUS_GENERADOR_23AGO.md` (F2):
> "La auditoría recomienda reclasificar panico_total (N=11) y skew_paranoia_exit (N=10)
> como 'Grade D' por inviabilidad OOS. **Se aplica en cambio el protocolo de diamantes
> establecido** [...] N<21 = diamante anecdótico, **nunca degradar por muestra baja**."

Fue precisamente Hermes quien **rechazó** la recomendación de degradar (del auditor Opus
anterior) y aplicó el protocolo diamante. Esta sesión lo profundiza con el tratamiento
completo §3.3 (sección 3 de este documento).

## 2. VERIFICACIÓN INDEPENDIENTE DE HALLAZGOS

| Hallazgo | Mi verificación | ¿Confirmado? |
|----------|----------------|:---:|
| P1 pivotes | 1,590/1,590 idénticos al repo (ya verificado antes) | ✅ |
| P2 duplicados benignos | ningún consumidor operativo hace groupby(pivot_date) | ✅ |
| P3+ stealth_tail_hedging lee SKEW **D3** | confirmado en código: `skew_sk.split("__").str[2]` | ✅ nuevo |
| P4 cascade_reversal no es diamante (N=240) | correcto: N≥21 → protocolo normal | ✅ |
| P4 estabilidad del threshold: fire rate 29.9% (1993-2000) vs 6.3% (2004-2009) | aceptado | ✅ |
| P5 trade-off | ningún consumidor depende de valores históricos | ✅ |
| P6 determinismo | triple hash idéntico | ✅ |
| P7 los 11 fixes | verificados línea por línea | ✅ |
| **BS1** pesos MIN para todos los pivotes | confirmado en código (L287-288 pre-fix) | ✅ |
| **BS2** GRUPO_A hardcoded | confirmado (L72 pre-fix) | ✅ |
| **BS3** denominador variable d1_bear_5 | **confirmado con datos propios**: 2 est=211 piv, 3 est=464, 4 est=346, 5 est=569; 64.2% con <5; primer pivote con 5: **2011-02-18** | ✅ P1 real |
| BS4 threshold full-sample | aceptado (documentado, mild look-ahead, PROPOSED) | ✅ |
| BS5 cobertura NaN (FG 64.2% ausente) | consistente con mi mapa de inicios de serie | ✅ |

## 3. FIXES APLICADOS (builder v8)

| # | Fix | Cambio |
|:-:|-----|--------|
| BS1 | Pesos de cascade_conviction **por fila** según `pivot_type` (antes: MIN para todos) | `calc_cascade(row)` con `tm.get(row["pivot_type"])` |
| BS2 | GRUPO_A dinámico: unión de `type_mask.MIN/MAX.stations` del cal-file, fallback a default | ya no hardcoded |
| BS3 | Nueva columna **`n_stations_a`** (estaciones Grupo A disponibles por pivote) para que cualquier análisis pueda segmentar/normalizar por disponibilidad + structural break documentado | columna 143 |
| P3+ | `stealth_tail_hedging` añadida al manifiesto CAT-A (lee SKEW D3, 8 filas migran, marginal) | nota en manifiesto |

**Estado post-fixes (builder v8):** 1,590 × **143 columnas** · 101/141 ≥99.9% ·
12 CAT-A / 37 CAT-B / 0 sin clasificar · **28/28 señales disparan**.

## 4. TRATAMIENTO DIAMANTE §3.3 — panico_total y skew_paranoia_exit

**Regla inamovible aplicada:** N<21 = diamante; se reporta `p_raw` + CI95 Clopper-Pearson,
sin shrinkage, sin degradar. Resultados calculados esta sesión:

### panico_total (N=11 en tabla nueva) — DIAMANTE FUERTE
| Celda | N | p_raw | CI95 CP | baseline | Lectura |
|-------|:-:|:---:|---------|:---:|---------|
| **zz25\|ALZA** | 7 | **1.000** | **[0.590, 1.000]** | 0.532 | CI entero sobre baseline |
| zz25\|BAJA | 4 | 1.000 | [0.398, 1.000] | 0.743 | sobre baseline, N mínimo |
| zz50\|ALZA | 7 | 0.714 | [0.290, 0.963] | 0.553 | compatible con edge |
| zz50\|BAJA | 4 | 1.000 | [0.398, 1.000] | 0.696 | sobre baseline |

**p_raw = 7/7 en zz25|ALZA con CI95 inferior (0.59) por encima del baseline (0.532)** —
la definición más limpia de diamante confirmado disponible con N bajo.

### skew_paranoia_exit (N=10 en tabla nueva) — DIAMANTE
| Celda | N | p_raw | CI95 CP | baseline | Lectura |
|-------|:-:|:---:|---------|:---:|---------|
| **zz75\|ALZA** | 6 | **0.833** | [0.359, 0.996] | 0.490 | sobre baseline |
| zz50\|ALZA | 6 | 0.667 | [0.223, 0.957] | 0.557 | compatible |
| zz25\|ALZA | 6 | 0.667 | [0.223, 0.957] | 0.699 | dentro del ruido |

**Pendiente del protocolo (paso 4):** análisis individual de cada ocurrencia histórica
(¿en qué eventos dispararon? — hipótesis: pánicos de cola conocidos) y cruce con el
régimen de crisis ±3σ (donde ya se midió agrupación de la familia).

## 5. DICTÁMENES ACEPTADOS

- **cascade_reversal → PROPOSED** (aceptado): N=240 no es diamante; p=0.25 no significativo;
  inestabilidad temporal del threshold (fire rate 29.9%→6.3% entre folds) imposibilita
  promoción sin walk-forward. El umbral −0.957 queda congelado y documentado como
  calibración full-sample (BS4).
- **Trade-off fidelidad→producción** aprobado: ningún consumidor depende del one-off.
- **236 duplicados** = limitación conocida del esquema de piernas, benigna para todos
  los consumidores actuales.

## 6. ARTEFACTOS ACTUALIZADOS
- `builder_quants_obs.py` v8 (BS1+BS2+BS3 aplicados)
- `quants_obs_new.pkl` (1,590 × 143, incluye `n_stations_a`)
- Este documento + informes previos de la cadena
