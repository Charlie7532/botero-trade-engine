# PROMPT: VERIFICACIÓN DE ALINEACIÓN — station_profiles + signal_discriminator + family_sequence_detector
# Auditado con los hallazgos previos (dato mata relato)

**Fecha:** 2026-09-17
**Repo:** /root/botero-trade · **Intérprete:** backend/.venv/bin/python3 · **Respuesta:** español
**Rol:** EL AGENTE ejecuta verificación empírica con scripts y reporta. NO modifica código a menos que se solicite — primero diagnóstica y reporta.

---

## CONTEXTO ARQUITECTÓNICO (comprendido, no asumir)

La arquitectura de inteligencia METAR se compone de 3 módulos puras-domain en `backend/modules/entry_decision/domain/rules/` que DEBEN estar alineados:

1. **`station_profiles.py`** (Single Source of Truth):
   - 11 `StationProfile` (polarity, cat, profession, bins canónicos stress/complacent/floor/ceiling, singularidades D2/D3)
   - `classify_tier(n, d1)` → EVENT/TRANSITIONAL/CONFIRMED/BASELINE
   - `signal_router(n, d1, station,...)` → 3 dimensiones desacopladas (peso estadístico por N · alerta por severidad D1/σ · anomalía cinemática D2/D3)

2. **`signal_discriminator.py`** (clasificador de señal):
   - Concordancia de 7 condiciones (C1-C7) → STRUCTURAL_FLOOR/MODERATE/PULLBACK/TRAP/NOISE (floor) y espejo ceiling.
   - `_extract_metrics_from_timing(timing, side)` = métricas DESDE el TIMING CONTEXT (NO fact store) ✓
   - `_apply_d2d3_modulation` (singularidades de profiles) — NO degrada rareza (is_rare=True, n<5 NO degrada).

3. **`family_sequence_detector.py`** (confluencia cross-station):
   - STATION_CATEGORIES (CAT1_MACRO/CAT2_SENTIMENT/CAT3_ACTION), secuencia inter-categoría.

**CITA REGENTE (fuente de la verdad):** "Los indicadores NO dan instrucciones de cómo operar. Emiten HECHOS (p_bull, ev, n, timing), no directivas. La decisión (MKT_/STK_) sale del compositor + Entry Gate." → Verificar que ningún módulo introdujo campos DIRECTIVOS en stores de hechos.

---

## TAREA 1 — Verificar identidad/alineación estable

1. **Estabilidad de bins canónicos:** confirmar que `signal_discriminator` y `family_sequence_detector` importan los bins de `station_profiles` (NO duplicados hardcodeados). Reportar divergencias si existen.
2. **Consistencia STATION_CATEGORIES vs cat en profiles:** para cada estación, comparar `STATION_CATEGORIES` (family) con `cat` (profiles). Deben mapear coherente (CAT1=cat1, CAT2=cat2, CAT3=cat3). Reportar cualquier mismatch.
3. **Programa de probes:** levantar cada módulo en import y verificar que los 11 profiles cargan sin error y los get_all_*_bins() devuelven dict de 11.

## TAREA 2 — Punto ciego A: el fallback NO_TIMING_DATA

Verificar la rama sin-timing de `classify_floor`/`classify_ceiling`:
- Cuando `timing.first_passage_floor` es None/ausente, `concordance_score=-1` y se usa `d2_rule.get("hr_zz75", 0.0)` del rules JSON.
- **Verificar:** ¿existen esos `hr_zz75`/`sgs_median` en el rules JSON? ¿O retornan 0.0 (default) produciendo clasificación NOISE por datos ausentes?
- **Cuantificar:** ¿cuántos estados de cada timing store tendrían este fallback (estado con poblacion.n_episodios=0 o sin medicion_first_passage)? Reportar por estación.
- **Riesgo:** si el fallback se dispara silenciosamente, el discriminator "clasifica" con datos vacíos → señales falsas NOISE o fallback. Determinar si es accionable.

## TAREA 3 — Punto ciego B: umbrales de concordancia vs datos reales (CRÍTICO)

Los thresholds en `_concordance_to_class_and_confidence` están HARDCODEADOS:
- 0/7 → HR75≈70% STRUCTURAL; 1/7 → ~58%; 2/7 → ~52%; 3-4/7 → ~50% NOISE/PULLBACK; 5/7 → ~40% TRAP; 6-7/7 → ~0% TRAP.

**Verificar contra los datos REALES del timing store:**
1. Para cada estación y cada state_key: extraer del **timing store** `medicion_min.first_passage.zz75.hit_rate` (hr75), `zz25.hit_rate` (hr25), `profit_factor`, `rr_asymmetry`, `sgs`, `mae_medio`, `mfe_medio`, `p_value` — las mismas métricas que usa `_extract_metrics_from_timing`.
2. Computar las 7 condiciones (C1-C7) por las reglas del discriminator y el concordance_score (0-7).
3. **Validar la monotonicidad:** para todos los estados de las 11 estaciones, ¿se cumple que score alto ⇔ HR75 bajo? Construir tabla `score (0-7) → HR75 medio real` y comparar contra los umbrales del código.
4. **Reportar:** ¿los umbrales (70/58/52/50/40/0) coinciden con los datos? ¿Dónde divergen? ¿El mapeo score→clase produce clases consistentes con la realidad?
5. **Especial atención a C5 (dual_hr75) y C7 (pvalue):** cuantificar cuántos estados quedan con tile default (dual_hr75=0.5 vía `else: 0.5`, pvalue default 1.0) — ¿C5/C7 están activos o silenciados en la práctica?

## TAREA 4 — Punto ciego C: silencio de C5/C7

- Verificar cuántos estados reales tienen `first_passage_ceiling` (o floor para ceiling) poblado → si el "dual" está vacío, `dual_hr75=0.5` y C5 NO vota (silencioso).
- Verificar cuántos tienen `p_value` real vs default 1.0. Si la mayoría cae a default, C7 (pvalue>0.80) vota SIEMPRE → sesgo hacia NOISE.

## TAREA 5 — Cumplimiento de la cita (no directivas en hechos)

- Verificar que **ningún campo directivo** (`operational_guidance`, `instruccion`, `STK_*`/`MKT_*`) se emitida desde dentro de los 3 módulos como "hecho". Los módulos clasifican (NOISE/FLOOR/tier) — NO deben emitir órdenes. Confirmar que la ORDEN (`MKT_*`/`STK_*`) sale solo del compositor/Entry Gate, no de estos.
- Reportar si algún módulo filtra una directiva que deba estar solo en compositor.

---

## ENTREGABLES (reporte en español, con datos)
1. Tabla de alineación: {módulo, importa bins de profiles?, categorías consistentes?, carga OK?}
2. Punto ciego A: {estados sin timing por estación, ¿fallback dispara?, hr_zz75 existe en rules JSON?}
3. **Punto ciego B (lo más importante):** tabla `score(0-7) → HR75 real` por estación, comparada con umbrales hardcodeados; veredicto: ¿bien calibrados u obsoletos?
4. Punto ciego C: {% estados con dual_hr75=default 0.5, % con pvalue=default 1.0}
5. Cumplimiento cita: {¿algún campo directivo en los 3 módulos?}

**NO modifica código — reporta con datos primero.** Si un hallazgo requiere corrección, proponer el fix exacto (archivo, línea, cambio) y esperar aprobación (Rule 22).