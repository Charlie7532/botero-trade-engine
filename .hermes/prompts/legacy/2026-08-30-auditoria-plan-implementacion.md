# AUDITORÍA EXTERNA — Plan Maestro de Continuación (Implementation Plan)

**Solicitante:** Juan Andrés (Arquitecto) vía Hermes (deepseek/deepseek-v4-flash)
**Fecha:** 30-Ago-2026
**Documento a auditar:** `/root/.gemini/antigravity-ide/brain/012139fd-5535-41c8-9edc-96bd0916ecb5/implementation_plan.md`
**Contexto completo disponible en:** `/root/.gemini/antigravity-ide/brain/012139fd-5535-41c8-9edc-96bd0916ecb5/` (14 documentos: walkthrough, task list, meta-auditorías, lake audit, informe triádico V2, prompt maestro V3.4, auditoría plan V5, preguntas arquitectura)
**Estado del repo:** Rama `main`, 303 tests pasando, `continuous_metar_lake.parquet` generado (8,453×191), fact stores regenerados con claves numéricas y taxonomía simétrica, lookup adapters refactorizados.

---

## 1. CONTEXTO: QUÉ SE AUDITA

El **Plan Maestro de Continuación** (7 fases) fue diseñado por Claude Opus tras la finalización de la **Homologación Simétrica Canónica** — refactor masivo que cambió las 11 estaciones METAR de labels de texto (e.g. `"CRISIS_SPIKE"`) a vectores numéricos (e.g. `"5__3__3"`) con una taxonomía simétrica de 6 bins D1 (Bin 0 = EXTREME_{concepto}, Bin 5 = EXTREME_{antónimo}).

El plan propone 7 fases secuenciales:
1. **F1:** Sincronizar Fact Lake (`continuous_metar_lake.parquet`) con claves numéricas
2. **F2:** Sincronizar arnés de medición (`arnes/` y `medir_senal.py`)
3. **F3:** Recomputación triádica ponderada de 31 señales
4. **F4:** Validación rigurosa por TIERS (A/B/C)
5. **F5:** Anatomía de velas segregada MIN/MAX
6. **F6:** Integración a catálogo de producción
7. **F7:** Formalización del Prompt Maestro V3.4

**LO QUE YA ESTÁ HECHO (no re-auditar):**
- ✅ `metar_classifier.py` — clasificador centralizado con `classify_bin()` y `make_state_key()`
- ✅ 11 fact stores regenerados con claves numéricas y sección `taxonomy`
- ✅ 11 lookup adapters refactorizados (usan `classify_bin` + `make_state_key`)
- ✅ `v3_fact_table_engine.py` corregido (vectores numéricos, fix TypeError d1_bin)
- ✅ OUTPUT_PATH bug corregido (`backend/backend/` → `backend/`)
- ✅ 46 tests de integridad taxonómica + 303 suite completa — **todos pasan**
- ✅ `continuous_metar_lake.parquet` generado y verificado
- ✅ Bug NaN→GREED en FG corregido (meta-auditoría Opus #5)
- ✅ DXY pre-SPY alignment corregido (Gemini #1)
- ✅ Credit orientation invertida corregida
- ✅ `signals_triad_fact_sheet_v2.json` generado
- ✅ `overflow_candle_anatomy_v2.json` generado

---

## 2. EL PROBLEMA CENTRAL QUE LA AUDITORÍA DEBE RESOLVER

Tras la homologación, **`quants_obs.pkl` NO se regeneró** y **`arnes/señales.py` NO se actualizó**.

Estado actual:
- Los fact stores tienen claves numéricas: `states["5__3__3"]`
- `quants_obs.pkl` tiene labels viejos: `"CRISIS_SPIKE__ACCELERATING_UP_3D__VOL_ACCELERATING_EXPANSION"`
- Las 28 señales buscan por nombre viejo: `vix_d1 == "CRISIS_SPIKE"`
- **Hoy las señales "funcionan" porque `quants_obs.pkl` no se regeneró** — pero en el momento de regenerarla, las 28 señales devolverán 0 disparos.

El plan propuesto NO tiene una fase explícita para manejar esta transición. El riesgo es que la Fase 1 o 2 del plan rompa la cadena sin que el plan lo reconozca.

---

## 3. PREGUNTAS PARA EL AUDITOR (ordenadas por criticidad)

### P1 — Secuencia de fases: ¿el plan ignora una dependencia crítica? (CRÍTICO)

El plan dice: F1 (Lake) → F2 (Arnés) → F3 (Tríada) → ...

**Problema:** F2 (Arnés) requiere que `quants_obs.pkl` esté regenerado con los labels simétricos. Pero regenerar `quants_obs.pkl` sin actualizar `señales.py` primero mata las señales. Y actualizar `señales.py` requiere saber qué labels simétricos corresponden a qué labels viejos.

**Pregunta concreta:** ¿La secuencia correcta debería ser?

```
Fase 0 (NUEVA): Regenerar quants_obs con adapters actualizados
                + Auditar/actualizar señales.py con labels simétricos
                + Verificar compuerta 28/28

... luego continuar con el plan existente
```

O, alternativamente, ¿se puede actualizar señales.py **antes** de regenerar quants_obs, usando un mapeo directo 1:1 viejo→nuevo (ej. `CRISIS_SPIKE` → `EXTREME_PANIC`)? Dictaminar si existe riesgo de que el mapeo no sea exacto.

### P2 — Riesgo de migración: ¿las señales se rompen o no? (CRÍTICO)

Verificar independientemente en el código:

1. En `arnes/señales.py`, las 28 señales referencian labels como `CRISIS_SPIKE`, `DEEP_COMPLACENCY`, `TAIL_PARANOIA`, `BREADTH_WASHED_OUT`.
2. En los fact stores nuevos, los D1 son numéricos: `0, 1, 2, 3, 4, 5`.
3. En el lake continuo nuevo, los labels son los simétricos: `EXTREME_COMPLACENCY`, `COMPLACENCY`, `NEUTRAL_CALM`, etc.

**Pregunta:** ¿Cuál de estos escenarios es verdad?

- (a) Si regeneramos `quants_obs.pkl` con los LookupAdapters refactorizados → los state_keys serán **numéricos** (ej. `"0__1__2"`) → las señales que hacen `str.split("__").str[0]` y comparan con `"CRISIS_SPIKE"` devuelven 0 disparos.
- (b) Si el LookupAdapter tiene un `resolve_label()` que mapea `"0"` → `"EXTREME_PANIC"` → entonces el state_key podría seguir siendo semántico.
- (c) Hay un plan intermedio que no estamos viendo.

**Verificar con datos:** ejecutar el generador `generate_quants_obs.py` y ver qué state_keys produce. Luego correr las 28 señales y reportar cuántas disparan vs 0.

### P3 — El bug `_capitulacion`: ¿corregir antes o después? (ALTO)

Hallazgo #4 de Gemini (confirmado por Opus en meta-auditoría): `_capitulacion` omite `ELEVATED_PANIC`/`PANIC` (Bin 4), solo evalúa `HIGH_VOL`/`NEUTRAL_ALERT` (Bin 3) y `CRISIS_SPIKE`/`EXTREME_PANIC` (Bin 5).

**Datos:** 79 observaciones de `ELEVATED_PANIC + BREADTH_WASHED_OUT` — perdidas.

**Pregunta:** ¿Se debe corregir este bug (añadir Bin 4 a `_capitulacion`) **antes** o **después** de la migración a labels simétricos? Argumentar:
- A favor de corregir antes: se resuelve de una vez, la migración es el momento natural.
- A favor de corregir después: el edge actual se midió sin Bin 4; cambiarlo requiere re-validación; mezclar migración con corrección de bugs añade riesgo.
- ¿Hay una tercera opción (corregir en señales.py pero marcar la corrección como pendiente de re-validación OOS)?

### P4 — TIER C vs Protocolo Diamante §3.3: ¿redundancia o conflicto? (MODERADO)

El plan Fase 4 define:
- TIER A (N ≥ 30): DSR + Walk-forward + CI95
- TIER B (10 ≤ N < 30): Binomial Exact + CI95
- TIER C (N < 10): Dossier cualitativo

**Pero** el Protocolo de Diamantes §3.3 (fact_store_v3_architecture.md, vigente desde 22-Ago) ya define:
- N < 21 = diamante → p_raw + CI95 Clopper-Pearson + análisis individual
- Nunca degradar por muestra baja. Rareza = riqueza.
- La meta-auditoría Opus (30-Ago) confirma: Bonferroni NO se aplica; las señales son hipótesis informadas, no data mining ciego.

**Pregunta:** ¿TIER C y §3.3 son compatibles? ¿O TIER C introduce un marco paralelo que contradice la arquitectura establecida? Dictaminar si el plan debe referenciar §3.3 explícitamente en lugar de inventar TIER C.

### P5 — ¿El lake continuo está realmente sincronizado? (MODERADO)

El walkthrough dice que el lake ya fue regenerado con los labels correctos tras las correcciones (Gemini #1 + Opus #5). Verificar:

1. Ejecutar el overlap test contra los fact stores de producción (11 estaciones). ¿Todas superan 72%? ¿Cuáles son las que más divergen y por qué?
2. Verificar que el bug NaN→GREED (Opus #5) está efectivamente corregido — la distribución de FG D1 debe ser Gaussiana (~34% por bin central), no 73% en GREED.
3. Verificar que la orientación de Credit no está invertida (2008 debe mapear a `CREDIT_CRISIS`/`0`, no a `DEEP_CREDIT_EASE`/`5`).

### P6 — ¿Qué pasa con `arnes/estructura.py`? (MODERADO)

El plan menciona que `_surprise_vector` en `estructura.py` usa labels viejos. ¿Cuál es el plan concreto para actualizarlo? ¿O ya fue actualizado? La señal `sorpresa_total` depende de esto.

### P7 — Riesgo de drift entre Expanding Rank y Static Edges (INFORMATIVO)

La meta-auditoría Opus (Punto #2) concluye: el drift del 35-48% entre lake (expanding rank) y lookup adapters (edges estáticos) es **inherente al diseño dual y no es un defecto**. Sin embargo, el plan no menciona este diagnóstico ni propone documentarlo como limitación conocida. ¿Es necesario incluirlo en la documentación de referencia para evitar que futuras auditorías redescubran este "bug"?

---

## 4. LÍMITES DEL SCOPE

- ✅ **Preservar** el trabajo ya hecho (Homologación Simétrica, lake, fact stores, 303 tests).
- ✅ **Respetar** la arquitectura dual: lake continuo para señales ENTRE, quants_obs para señales de pivote.
- ✅ **Aislar** la auditoría al plan de implementación — no proponer nuevo código.
- ❌ **No re-abrir** el debate Bonferroni vs §3.3 — Opus y el usuario ya lo resolvieron: Bonferroni no se aplica.
- ❌ **No re-abrir** el drift Expanding Rank vs Static Edges — ya diagnosticado como inherente.

---

## 5. FORMATO DE ENTREGA ESPERADO

1. **Veredicto por pregunta (P1-P7):** APROBADO / RECHAZADO / REQUIERE CAMBIO, con evidencia reproducible.
2. **Veredicto global del plan:** APTO para ejecutar / APTO con cambios / REQUIERE RE-ESCRITURA.
3. **Si requiere cambios:** sugerir la secuencia corregida explícitamente (qué fase va antes de qué).
4. **Hallazgos nuevos** si los hay (¿el auditor encuentra algo que ni Gemini ni Opus detectaron en las rondas previas?).
5. **Riesgo estimado de ejecución:** BAJO / MEDIO / ALTO, con justificación.
6. **Firma del modelo auditor y fecha.**

---

## 6. ANEXO: ESTADO ACTUAL DE COMPONENTES CLAVE (para que el auditor no tenga que descubrirlos)

```python
# quants_obs.pkl — NO REGENERADO
vix_sk = ['LOW_VOL__STABLE_CONTINUATION_3D__VOL_NEUTRAL_BASELINE', ...]
→ labels viejos tipo texto

# continuous_metar_lake.parquet — REGENERADO
vix_sk = ['COMPLACENCY__STABLE_CONTINUATION_3D__VOL_NEUTRAL_BASELINE', ...]
→ labels nuevos simétricos (pero texto, no numéricos)

# fact stores — REGENERADOS
vix_fact_store['states'].keys() = {'0__0__0', '0__0__1', ..., '5__4__4'}
→ claves numéricas
→ taxonomy.d1.labels = ['EXTREME_COMPLACENCY', 'COMPLACENCY', 'NEUTRAL_CALM',
                        'NEUTRAL_ALERT', 'PANIC', 'EXTREME_PANIC']

# Lookup adapters — REFACTORIZADOS
→ import metar_classifier; classify_bin(val, edges); make_state_key(d1, d2, d3)
→ state_keys de salida = numéricos ("5__3__3")

# Tests: 46 taxonomy + 303 suite = ✅ todos pasan
# Scripts nuevos: recompute_signals_fact_store_triad_v2.py (OK),
#                  audit_overflow_candle_anatomy_v2.py (OK),
#                  build_continuous_metar_lake.py (actualizado)
```