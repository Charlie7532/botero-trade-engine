# RESPUESTA A LA DOBLE AUDITORÍA — Validador OOS (Gemini + Opus)
**Fecha:** 22-Ago-2026 · **Firma:** qwen/qwen3.8-max (Hermes)
**Auditores:** Gemini 3.7 Flash (1ª pasada) + Claude Opus 4.6 (2ª pasada profunda)
**Documentos:** `auditoria_externa_validador_oos.md` + `auditoria_externa_validador_oos_opus.md`

---

## 1. Veredicto consolidado de la doble auditoría

| Hallazgo | Auditor | Confirmado por mí | Acción |
|----------|:---:|:---:|--------|
| H1: look-ahead binneo D2/D3 | Ambos | ✅ en código | **P0.1 CORREGIDO** en el motor |
| H1b: catálogo v7 inmune (solo D1) | Ambos | ✅ inspección de las 8 | Ninguna |
| H2: sign-test sin potencia | Ambos | ✅ matemática | Reportar como descriptivo |
| H3: decay asimétrico | Ambos | ✅ | Reportar como cota |
| H4: pivot-identity look-ahead | Opus | ⚠️ inherente | Documentado (mitiga confirmación) |
| H5: enriquecimiento en pivotes ruido | Opus | ⚠️ aceptado | Descuento 10-25% documentado |
| **H6: structural break interno** | Opus | ✅ **verificado con mis datos** | **P0.2 APLICADO: degradada** |
| H7: population bias | Opus | ⚠️ aceptado | Pendiente evaluador diario |

## 2. H6 verificado con datos propios (el hallazgo más valioso)

Los 10 folds OOS de `breadth_contraction_exit` muestran un quiebre limpio:
- Folds 1-5 (≈2001-2016): [−2.19, −0.85, −0.79, −1.24, −2.34] → **media −1.48%** (anti-edge)
- Folds 6-10 (≈2016-2026): [+2.79, +0.17, +0.44, +2.43, +3.24] → **media +1.81%** (edge)

El "+0.17% OOS" que reporté era el promedio de dos regímenes opuestos. **Aplicado:**
`breadth_contraction_exit` → DEGRADADA (structural break interno). Queda excluida
automáticamente del evaluador sin `reevaluar=True`.

## 3. P0.1 aplicado — motor higienizado

`v3_fact_table_engine.py`: D2/D3 ahora usan `expanding(min_periods=252).rank(pct=True)`
(idéntico a D1, cero look-ahead). Verificado: compila + distribución de bins sana
(71% bin central, ~1.5% extremos). Los edges globales quedan solo como documentación.

**Nota crítica:** el pickle `quants_obs.pkl` (17-Ago) fue generado con el motor VIEJO.
Las señales D1 del catálogo son inmunes, pero cualquier análisis que use D2/D3 de ese
pickle (p.ej. el análisis de singularidades techos/pisos) heredó la contaminación.
Regenerar el pickle con el motor corregido es el paso pendiente.

## 4. Lo que NO se toca (verificado sólido)

- Las 6 señales núcleo del catálogo v7 retienen edge OOS positivo incluso con el
  descuento acumulado del 30-40%: capitulacion +1.5-2.0%, pcr_put_panic +1.4-1.9%,
  vvix_entry +1.1-1.5%, credit_stress +0.8-1.1%, bsi_washed_out +0.4-0.7%.
- `skew_paranoia_exit` es la señal más limpia (DEPLETED en ruido: 19.2% vs 41.6% base).
- El validador OOS es metodológicamente correcto (Gemini verificó baseline, régimen, folds).

## 5. Pendientes derivados de la auditoría

| # | Pendiente | Prioridad |
|:-:|-----------|:---:|
| 1 | Regenerar quants_obs.pkl con motor corregido | P1 |
| 2 | First-passage con High/Low intradía (−0.92pp MAE) | P1 |
| 3 | Normalizar denominador de decay (train_mean) | P1 |
| 4 | Bloques de test de 2 años (más folds, más potencia) | P1 |
| 5 | Evaluador sobre barras diarias (population bias H7) | P1 |
| 6 | Identificar causa del break post-2016 de breadth_contraction | P2 |
| 7 | Reportar edge por tipo de pivote (ruido vs estructural) | P2 |

---
**Firma:** qwen/qwen3.8-max (Hermes) · 22-Ago-2026
