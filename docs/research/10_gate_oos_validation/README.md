# Gate OOS — Documentación de la cadena `quants_obs`

**Última actualización:** 23-Ago-2026
**Estado:** cadena auditada ×3 externamente, tabla oficial sustituida, generador en producción.

Esta carpeta consolida la documentación de las 3 rondas de auditoría externa y
las autoauditorías de la cadena de observación canónica (`quants_obs`).

## Punto de entrada para cualquier IA/auditor

**Lea primero:** `backend/scripts/generators/QUANTS_OBS_GENERATOR.md` — la
documentación de referencia completa del generador (propósito, esquema de 143
columnas, fórmulas, dependencias, divergencias conocidas, limitaciones, checklist
de auditoría, historial de 15 fixes).

## Cronología de la documentación

| Documento | Contenido |
|-----------|-----------|
| `AUTOAUDITORIA_OOS_22AGO.md` | Autoauditoría del validador OOS walk-forward y la cadena de medición |
| `RESPUESTA_AUDITORIA_DOBLE_22AGO.md` | Respuesta a las auditorías externas Gemini + Opus del validador OOS; degradación de `breadth_contraction_exit`; fix look-ahead D2/D3 |
| `AUTOAUDITORIA_PROPOSITO_QUANTS_OBS.md` | Autoauditoría guiada por propósito del builder; descubrimiento del bug `cascade_conviction_50` |
| `COMPUERTA_FIDELIDAD_BUILDER_v2_22AGO.md` | Reporte de fidelidad builder v2 y causas raíz de divergencias |
| `AUTOAUDITORIA_GENERADOR_v5_22AGO.md` | Autoauditoría del generador v5 (bugs propios encontrados y corregidos) |
| `RESPUESTA_AUDITORIA_OPUS_GENERADOR_23AGO.md` | Respuesta a auditoría Opus del generador (F1-F4 aplicados; decisión diamante documentada) |
| `INFORME_AUDITORIA_PROFUNDA_CALIBRACION_23AGO.md` | Auditoría profunda de la cadena completa + calibración de `cascade_reversal` |
| `RESPUESTA_AUDITORIA_PROFUNDA_OPUS_23AGO.md` | Respuesta a la auditoría profunda Opus (BS1-BS3 aplicados; tratamiento diamante §3.3 con CI95 Clopper-Pearson; refutación de acusación Anti-patrón #7 con evidencia) |

## Artefactos clave (fuera de esta carpeta)

| Artefacto | Ubicación |
|-----------|-----------|
| Generador oficial | `backend/scripts/generators/generate_quants_obs.py` |
| Documentación del generador | `backend/scripts/generators/QUANTS_OBS_GENERATOR.md` |
| Tests de regresión (7) | `backend/tests/test_quants_obs_builder.py` |
| Tabla oficial | `data/research/pivots/quants_obs.pkl` |
| One-off original (referencia) | `data/research/pivots/quants_obs_pre_sustitucion_20260823.pkl` |
| Manifiesto CAT-A/B/C | `data/research/signals/manifiesto_divergencias_quants_obs.json` |
| Calibración cascade_reversal | `data/research/signals/calibracion_cascade_reversal.json` |
| Walk-forward cascade_reversal | `data/research/signals/walkforward_cascade_reversal.json` |
| Análisis individual diamantes | `data/research/signals/diamantes_analisis_individual.json` |
| Validación OOS catálogo v7 | `data/research/signals/validacion_oos_catalogo_v7.json` |
| Validador OOS | `research/10_gate_oos_validation/validador_oos.py` |
| Builder histórico (v8) | `research/10_gate_oos_validation/builder_quants_obs.py` |

## Decisiones de arquitectura vigentes

1. **Propósito > réplica:** la tabla debe ser correcta según producción; la
   fidelidad al one-off es detector de divergencias, no meta.
2. **Divergencias CAT-A/B/C:** CAT-A (artefacto del one-off) → producción;
   CAT-B (deriva de versión) → documentado; CAT-C (desconocida) → investigar.
   Hoy: 12 CAT-A, 37 CAT-B, 0 CAT-C.
3. **Protocolo diamante §3.3:** N<21 = diamante; p_raw + CI95 Clopper-Pearson;
   nunca degradar por muestra baja. Confirmados: `panico_total` (N=11),
   `skew_paranoia_exit` (N=10).
4. **`cascade_reversal`:** PROPOSED. Umbral −0.957 congelado; edge +0.28% fijo
   / +0.44% walk-forward rolling p15; p>0.05 → sin promoción todavía.
5. **Degradadas:** `breadth_contraction_exit` (break interno OOS),
   `credit_ease_exit` (reliquia pre-QE), `bsi_recovery` (post-QE).
