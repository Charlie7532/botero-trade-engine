# PROMPT: POZO DE CATALOGACIÓN DE SEÑALES POR VENTANA DE TIMING (A2/A3/A4) — sin agentes, con ejercicios previos reutilizados

**Fecha:** 05-Sep-2026
**Objetivo:** Construir un **pozo de catalogación de señales** que clasifique las señales del catálogo por su **relación temporal con el pivote** (ventanas A2/A3/A4), para **encontrar coincidencias y secuencias** como ya se logró en ejercicios previos. **Los agentes del comité están DEPRECATED (desconectados) — este pozo usa solo el Evaluador General + timing, no los agentes.**

**Decisión arquitectónica (ya tomada):** los agentes del comité (`comite_metar/`) NO intervienen. El pozo se construye sobre el Evaluador General (`evaluador_general.py`) que produce `timing_canonico` por señal — la fuente de verdad de medición.

---

## LA TAXONOMÍA DE VENTANAS (define qué catalogamos)

Cada señal del catálogo se clasifica según su disparo relativo al PIVOTE (el giro zz del `blanco`) usando el `timing_canonico` que el Evaluador General ya mide por señal:

| Ventana | Rango de timing | Rol | Significado |
|:--------|:----------------|:----|:------------|
| **A2 — ANTICIPACIÓN** | **-2t, -1, 0** → disparos en `t-2`/`t-1`/`t0` (antes/en el pivote) | **CANARIO / PRECURSOR** | Señal que se enciende ANTES del giro — anticipa el pivote |
| **A3 — CONFIRMACIÓN** | **0, +t, +2t** → disparos en `t0`/`t+1`/`t+2` (en/justo después del pivote) | **CONFIRMADORA / INSTITUCIONAL** | Señal que valida el giro ya formado (entradas institucionales tras el pivote) |
| **A4 — CONTINUACIÓN** | **Fuera de rango** → disparos en `ENTRE` (lejos de cualquier pivote) | **RÉGIMEN / PERSISTENCIA** | Señal sin relación con el giro inminente — describe el estado, no el giro |

**Base de datos disponible:** `evaluacion_generalizada_lake.json` — cada una de las 36 señales tiene `timing_canonico` con `counts: {t-2, t-1, t0, t+1, t+2, ENTRE}`, `pct_anticipada`, `pct_exacta`, `pct_retrasada`, `pct_en_rango`. (verificado: vvix_entry anticipada 42.9%, fg_extreme_fear en-rango 83%.)

---

## REUTILIZAR LOS EJERCICIOS PREVIOS (los que ya logramos — no reinventar)

El pozo debe CONECTARSE con el trabajo de coincidencias/secuencias ya realizado:

1. **`data/research/signals/confluencias_canarias.json`** (51 pares) → reutilizar para cruzar **coincidencias de señales** dentro de cada ventana.
2. **`data/research/conjunctions/timing_derisking_report.json`** → reutilizar la clasificación de **secuencias** CAT1→CAT2→CAT3 (macro-driven vs cuchillo) y el `lead_lag` (qué estación lidera primero: dxy 279, skew 206, yield 153...) — esto es EXACTAMENTE la idea de "qué precede a qué".
3. **`.hermes/plans/tecnica-forense-precursores.md`** → reutilizar el **método Bayesiano de lift** `P(estado|evento)/P(estado|no evento)` para N pequeño (funciona con N<20, no colapsa como t-test) — es el algoritmo correcto para señales raras.
4. **`data/research/precursors/*.json`** → los reportes de señales adelantadas ya generados; reconciliar/conectar.

**Prohibido reinventar:** si el timing o las secuencias ya están calculados, CONSUMIRLOS. El pozo agrega la catalogación por ventana A2/A3/A4, no re-mide lo ya medido.

---

## TAREA: CONSTRUIR EL POZO

### Fase 1 — Clasificar cada señal en A2/A3/A4
Para cada una de las 36 señales del catálogo (usando su `timing_canonico` + `blanco` techo/piso + edge de `rendimiento_lake`):
- Si `pct_anticipada >= 35` → **A2 (CANARIO)** — anticipa el giro
- Si `pct_exacta >= 45` o `pct_retrasada >= 30` con en_rango alto → **A3 (CONFIRMADORA)**
- Si `pct_fuera` (ENTRE) alto → **A4 (CONTINUACIÓN/RÉGIMEN)**
- Reportar señal, ventana, blanco (techo/piso), edge, N, CI95 preinception §3.3 si N<21.

### Fase 2 — Detectar coincidencias dentro de cada ventana
- En A2 (canario): ¿qué señales CANARIO tienden a dispararse JUNTAS antes del mismo pivote? → usar las 51 confluencias canarias para enriquecer.
- En A3 (confirmadora): ¿qué señales confirman juntas el giro?
- En A4 (continuación): ¿qué señales coexisten en régimen persistente?
- Cruzar con el `lead_lag` de timing_derisking (qué estación antecede a cuál).

### Fase 3 — Detectar secuencias (el propósito clave: coincidencias y secuencias)
- Para los pivotes con múltiples disparos: construir las **secuencias temporales** típicas — p.ej. `[A2 canaria: skew/vix] → [pivote] → [A3 confirmadora: bsi]`.
- Usar el método de lift Bayesiano de precursores para medir en qué ventana una señal es DESPROPORCIONADAMENTE más probable.
- Reportar las secuencias más frecuentes y su hit-rate del pivote siguiente.

### Fase 4 — Consolidar el pozo
Salida en `data/research/pozo_catalogacion/`:
- `pozo_señales_ventanas.json` — señal → {ventana A2/A3/A4, rol, blanco, edge, timing}
- `pozo_coincidencias_ventana.json` — señales que co-disparan por ventana
- `pozo_secuencias.json` — las secuencias temporales pivote a pivote y su rentabilidad
- `resumen_pozo.json` — conteos por ventana/rol/blanco

**Métricas por señal en cada ventana:** hit_rate del pivote real, edge vs baseline de su ventana, N, CI95 (§3.3 si N<21), p-value.

---

## PRINCIPIOS (no negociables)
- **SIN agentes** — el pozo usa solo Evaluador General + timing + factores. Los agentes/comité quedan fuera (deprecated).
- **§3.3 rareza = riqueza:** N<21 = diamante, se reporta con CI95 y análisis individual, NUNCA se descarta por N bajo.
- **Dato mata relato:** consumir los ejercicios previos verificados, no re-medir.
- **La verdad habla:** si una señal no encaja limpio en una ventana, reportarlo — no forzar.
- **Sin lookahead:** el timing_canonico ya lo garantiza el Evaluador General.

## VERIFICACIÓN DE ACEPTACIÓN
- Las 36 señales clasificadas por ventana A2/A3/A4 (ninguna sin asignar).
- Coincidencias por ventana usando las 51 confluencias canarias.
- Secuencias pivote-a-pivote con hit-rate del pivote siguiente.
- Sin referencias a `comite_metar`/agentes en el output.
- Coherente con `timing_derisking` (lead_lag) y `forense_precursores` (método lift).

**NO implementar el comité.** Este es el pozo de catalogación que vale para tu propósito (entender y aprovechar estadísticamente cada señal por su rol temporal).