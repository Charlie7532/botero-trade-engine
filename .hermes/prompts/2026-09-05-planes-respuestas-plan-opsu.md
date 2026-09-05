# PROMPT: DECISIONES y EJECUCIÓN del Plan de Implementación (respuestas a las Open Questions de Claude Opus)

**Fecha:** 05-Sep-2026
**Base:** Plan de Claude Opus (`implementation_plan.md` del brain Antigravity) — "Rescate del Validador OOS Antiguo + Saneamiento + Mejoras Selectivas".
**Objetivo:** RESPONDER las preguntas que el plan de Claude Opus deja abiertas (incluida la del comité) y, con esas decisiones, EJECUTAR el plan. CEÑIDO al plan — no abrir temas ajenos.

---

## RESPUESTA A LAS PREGUNTAS DEL PLAN (decisiones del arquitecto)

### Pregunta "User Review Required" (L64-67) — decisión arquitectónica central
> ¿Restauramos el validador OOS antiguo como sistema de validación OOS canónico, saneado?

**RESPUESTA: SÍ.** El validador OOS antiguo (`research/10_gate_oos_validation/validador_oos.py`) se restaura como el sistema de validación OOS canónico de señales, saneado **con las correcciones 1-3** (la corrección 4, serie continua, se pospone — ver Open Q1). Es la pieza correcta.

### Open Question 1 (L74-75) — ¿serie continua o pivotes?
> ¿Preferimos que el nuevo OOS evalúe las señales sobre la serie continua o mantenga el universo de pivotes?

**RESPUESTA: MANTENER el universo de pivotes — conservar el validador como está (NO evolucionar ahora).**
- **Decisión del arquitecto:** el validador OOS se conserva tal como se encuentra en su metrología actual (universo de pivotes de `quants_obs.pkl`), para no alterar la base de resultados existente. **La evolución a serie continua (recomendada por el plan) se pospone para una etapa posterior**, cuando se considere prudente.
- **Justificación prudencial:** cambiar la base del validador (de pivotes a serie continua) ahora alteraría los resultados de referencia y mezclaría el saneamiento (correcciones 1-3) con un rediseño de universo. Es más seguro sanear primero sobre la metrología actual, validar el saneamiento, y luego —en una etapa separada y decidida— evaluar la migración a serie continua.
- La pregunta del plan ("¿walk-forward encima del evaluador general en vez de remendar el validador?") queda **documentada como consideración futura**, NO como acción de este prompt.

### Open Question 2 (L77) — ¿qué hacer con el comité?
> ¿Se preserva comite_metar/ como servicio METAR puro de confluencia para sizing, o no?

**RESPUESTA: ELIMINAR el comité.** No se conserva como activo de producción — fue construido con un paradigma defectuoso (estaciones-trader), potencia estadística cero, y no aporta valor verificable que el Evaluador General + fact stores no tengan ya.

- **Se migra lo útil (no todo):** las funciones estadísticas puras `edge_direccional()` y `clopper_pearson_ci()` → `arnes/` como mejoras al validador.
- **`_direccion_spy`:** heurística manual redundante con fact stores → NO se migra como activo (decisión pendiente: archivar como doc o descartar).

**NOTA de alcance:** este prompt NO abre temas ajenos (pozo A2/A3/A4, catalogación) — quedan fuera, para cuando el arquitecto los solicite aparte.

---

## EJECUCIÓN (según el plan de Claude Opus, con las respuestas anteriores)

### Fase 1 — Sanear el Validador OOS (correcciones 1-3 del plan; la 4 se pospone)
`research/10_gate_oos_validation/validador_oos.py`:
1. **Inception policy:** cada señal usa su `fecha_inicio_valida` de `_CERTEZA`; folds empiezan en `max(T0, inception_señal)`; folds con test pre-inception se saltan.
2. **OHLC intrabar:** sustituir `first_passage(prices, t, thr, blanco)` (solo close) por `first_passage_bar(close, highs, lows, t, scale, blanco, max_barras)` (importar a `arnes/medicion.py` o copiar la utilidad).
3. **Time-stop C9:** `max_barras = ceil(2/scale)` → zz25=80, zz50=40, zz75=27. Timeout = fracaso.
4. **Corrección 4 (serie continua) — NO se aplica en esta etapa.** Se conserva el universo de pivotes actual. La evolución a serie continua queda como consideración futura (pospuesta), documentada pero no ejecutada.

> ⚠️ **NOTA DE COHERENCIA (importante):** "conservar el validador como está" significa **conservar el UNIVERSO DE PIVOTES**, no "sin cambios". Las correcciones 2-3 (OHLC + time-stop) **sí modificarán la metrología** y por tanto la tabla de resultados. Esto es esperado y correcto (es el saneamiento), y la tabla antes/después lo reportará. La "conservación" del arquitecto aplica solo al universo de evaluación (pivotes), no a la metrología (que se vuelve más rigurosa). Quede explícito para evitar expectativa de "resultados idénticos".

### Fase 2 — Migrar las mejoras del comité (solo las estadísticas puras)
- **`edge_direccional()`** → a `arnes/estadisticas.py` (es nueva; verificar que no haya colisión de nombre).
- **`clopper_pearson_ci()` — NO duplicar:** `arnes/estadisticas.py` **YA tiene `_clopper_pearson_ci()` en L91** (implementada con `scipy.stats.beta`). La del comité usa `binomtest`. **Decisión de unificación:** usar la función existente de `arnes/` (fuente canónica); si se requiere la del comité, comparar ambas en un test de paridad y elegir UNA — nunca dejar dos duplicadas. Anotar que son equivalentes (mismo intervalo Clopper-Pearson exacto) aboton nivel beta vs binomtest.
- En el validador: añadir edge direccional condicionado por dirección (`edge_alza`/`edge_baja`, `ci95`, `p_greater`), y smoke-test causal `assert_sin_lookahead()`.

### Fase 3 — Retirar el comité (archivar a `_legacy/`, no borrar)
- **Decisión:** usar el patrón del repo: `research/_legacy/` (directorio existente para código experimental/deprecated). → `mv comite_metar/ research/_legacy/` en lugar de `git rm -r` de borrado completo. Se conserva el registro sin dejar código activo.
- **Precaución git:** como `comite_metar/` tiene JSONs pesados (~7 MB en salidas/), revisar si conviene excluir `salidas/` del tracking o mantenerlos en `_legacy/`. 
- Tras mover: corregir la referencia en `docs/research/00_cross_cutting/pendiente_ingestion_vault_pcr_dxy_yield.md` (única ref externa) si menciona `comite_metar`.
- Verificar `grep -rn "comite_metar" backend/ src/` → vacío; solo `_legacy/` + docs de referencia.

### Verificación (2 pasos, para no exigir invarianza del instrumento)
**Paso A — Solo Corrección 1 (inception), sobre pivotes:**
- Re-ejecutar `validador_oos.py` con SOLO la corrección de inception (sin OHLC/time-stop todavía).
- Verificar que `cascade_reversal` mantiene 9/9 folds y p sign-test=0.002 (inception=1993 no le afecta — debe ser estable aquí).
- Señales post-2011 (skew, vvix) pierden folds tempranos (correcto por inception).

**Paso B — Aplicar Correcciones 2-3 (OHLC + time-stop):**
- Re-ejecutar, reportar **tabla antes/después** de cada señal cambiada de veredicto y por qué.
- ⚠️ Si `cascade_reversal` baja de 9/9 tras OHLC+time-stop, **NO es fallo del saneamiento** — es una medición más honesta. Reportarlo explícitamente, NO forzar invarianza.

## CRITERIOS DE ACEPTACIÓN
1. Validador OOS restaurado como canónico y saneado (correcciones 1-3 aplicadas; corrección 4/serie continua pospuesta).
2. Validador conservado sobre el universo de pivotes actual (corrección 4/serie continua NO aplicada — pospuesta).
3. `edge_direccional` en `arnes/estadisticas.py`; `_clopper_pearson_ci` unificada (sin duplicados).
4. `comite_metar/` archivado en `research/_legacy/`; `grep comite_metar` vacío en backend/src (solo `_legacy` + doc).
5. `cascade_reversal`: estable 9/9 en Paso A (solo inception); en Paso B (OHLC+time-stop) reporte tabla antes/después y NO forzar invarianza.
6. Sin refs rotas; tests pasan.

**Alcance estricto del plan:** sanear el validador OOS + migrar mejoras + archivar el comité a `_legacy`. NO se incluyen exploraciones futuras (pozo A2/A3/A4, catalogación) — quedan fuera, para cuando el arquitecto lo solicite.