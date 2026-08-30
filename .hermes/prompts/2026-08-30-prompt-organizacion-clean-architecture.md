# PROMPT DE ORGANIZACIÓN — Clean Architecture + Cadencia del Proyecto

**Origen:** deepseek/deepseek-v4-flash (Hermes)
**Propósito:** Organizar el proyecto según Clean Architecture: dominio puro desacoplado de infraestructura, taxonomía canónica de bins numéricos.
**Contexto:** La homologación canónica (Fase 0→7) está completa. Los walkthroughs y archivos de referencia están actualizados. Ahora hay que dejar la estructura del proyecto ordenada y con políticas de mantenimiento claras.

---

## DIAGNÓSTICO — Estado actual del proyecto

### ✅ Lo que ya está correcto

| Componente | Estado | Ubicación |
|:-----------|:------:|:----------|
| Pipeline activo (5 scripts) | ✅ Confirmado | `research/01_señales_entry_exit/` |
| Legado histórico (14 scripts) | ✅ Movido | `research/_legacy/` |
| Walkthrough completo | ✅ 12 secciones, 356 líneas | Antigravity |
| agent_quick_reference.md | ✅ Corregido (OOS real) | `.agents/references/metar/` |
| 4 archivos de referencia | ✅ Actualizados | `.agents/references/metar/` |
| Taxonomía "Extremo = ±2σ" | ✅ Homologada D1/D2/D3 | `gaussian_scale_policy.md` |

### ❌ Pendiente de organización

| Problema | Impacto |
|:---------|:--------|
| **`build_continuous_metar_lake.py`** en `research/` cuando debería estar en `backend/scripts/generators/` | 1 generador de producción fuera de su lugar Clean |
| **32 generadores en `backend/scripts/generators/` sin clasificar** por capa (núcleo/investigación/TIDE) | Un agente no sabe cuáles ejecutar mensualmente |
| **158 scripts de investigación** en `research/02_` a `research/11_` sin clasificación legacy/activo | Riesgo de confusión, pero no crítico — son artefactos de exploración histórica |
| **Sin políticas de cadencia** (Rule S8/S9) | Nadie sabe cuándo regenerar los artefactos |
| **Sin cron de regeneración mensual** | Los fact stores, lake y quants_obs pueden quedar desactualizados |

---

## PLAN DE ACCIÓN — 4 tareas

### TAREA 1: Migrar `build_continuous_metar_lake.py` a producción

**Qué:** Copiar de `research/01_señales_entry_exit/build_continuous_metar_lake.py` a `backend/scripts/generators/build_continuous_metar_lake.py`.

**Verificar:**
```bash
cd /root/botero-trade
PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
  backend/scripts/generators/build_continuous_metar_lake.py --dry-run
# → Sin errores, lake se regenera correctamente
```

---

### TAREA 2: Clasificar los 32 generadores de `backend/scripts/generators/` en 3 capas

| Capa | Criterio | Incluye | Cadencia |
|:-----|:---------|:--------|:---------|
| **🟢 NÚCLEO** | Pipeline METAR esencial | `generate_all_150_state_fact_stores.py`, 11× `generate_{station}_fact_table.py`, `build_continuous_metar_lake.py`, `generate_quants_obs.py` | **Mensual** |
| **🟡 INVESTIGACIÓN** | Evaluadores y análisis | `evaluador_vela_a_vela.py`, `validador_oos.py`, `recompute_triad_v2.py`, `audit_overflow_v2.py` | **A pedido** |
| **⚪ TIDE/BENCHMARKS** | Secundarios, sin cadencia fija | `generate_tide_derived_table.py`, `generate_wave_*.py`, `generate_v37_*` a `v41_*`, `generate_cascade_calibration.py`, etc. | **Sin cadencia** |

**Acción:** Crear archivo `backend/scripts/generators/README_GENERATORS.md` con esta clasificación.

---

### TAREA 3: Agregar políticas de cadencia Rule S8 + S9 a `gaussian_scale_policy.md`

**Insertar DESPUÉS de Rule S7** (actualmente en línea ~196):

```
### Rule S8: Update Cadence — Full Pipeline Regeneration

| Cadencia | Acción | Comando | Tiempo |
|:---------|:-------|:--------|:------:|
| Diaria | Ingesta al Vault (TimescaleDB) | EOD batch externo | — |
| Semanal | Verificar drift taxonómico | `pytest tests/test_taxonomy_integrity.py -q` | ~5s |
| Mensual | Regeneración completa de artefactos | Ver Rule S9 | ~15 min |
| Por evento | Bug / nueva señal / cambio taxonómico | Variable según evento | 5-60 min |

### Rule S9: Monthly Regeneration Procedure

Ejecutar en orden estricto:

```bash
# 1. Fact stores (desde Vault)
cd /root/botero-trade
PYTHONPATH=. backend/.venv/bin/python \\
  backend/scripts/generators/generate_all_150_state_fact_stores.py

# 2. Lake continuo
PYTHONPATH=. backend/.venv/bin/python \\
  backend/scripts/generators/build_continuous_metar_lake.py

# 3. Tabla pivotal
PYTHONPATH=. backend/.venv/bin/python \\
  backend/scripts/generators/generate_quants_obs.py

# 4. Tests de regresión
PYTHONPATH=. backend/.venv/bin/python -m pytest tests/ -q
```

**Artefactos generados:**
- 11 fact stores JSON: `backend/modules/entry_decision/domain/rules/*_fact_store.json`
- Lake continuo: `data/research/continuous_metar_lake.parquet`
- Tabla pivotal: `data/research/pivots/quants_obs.pkl`
```

---

### TAREA 4: Verificar que ningún script vigente está en legacy

**Ya verificado — 14 scripts en `research/_legacy/` con 0 importaciones activas:**

| Script | Estado | Evidencia |
|:-------|:------:|:----------|
| `extract_overflows_vela_a_vela.py` | ✅ Legacy | 0 referencias activas |
| `audit_overflow_candle_anatomy.py` (V1) | ✅ Legacy | 0 referencias (V2 es el activo) |
| `detector_regimen_crisis.py` | ✅ Legacy | Solo 1 comentario en docstring, no import |
| `audit_vector_confluence.py` | ✅ Legacy | 0 referencias |
| `recompute_signals_fact_store_triad.py` (V1) | ✅ Legacy | 0 referencias (V2 es el activo) |
| `wins_losses_*.py` (7 scripts) | ✅ Legacy | 0 referencias cada uno |
| `audit_entry_exit.py` | ✅ Legacy | 0 referencias |
| `generate_full_population_census.py` | ✅ Legacy | 0 referencias |

**Nota:** Los 158 scripts en `research/02_` a `research/11_` NO son legacy — son artefactos de exploración histórica en sus propios directorios. No necesitan moverse. Solo se movió lo que estaba en `research/01_señales_entry_exit/` mezclado con el pipeline activo.

---

## FORMATO DE ENTREGA ESPERADO

1. **Archivos modificados:**
   - `backend/scripts/generators/build_continuous_metar_lake.py` — copiado de research
   - `backend/scripts/generators/README_GENERATORS.md` — creado con clasificación de 32 generadores
   - `.agents/references/metar/gaussian_scale_policy.md` — Rule S8 + S9 agregadas

2. **Archivos de referencia (no modificar):**
   - `research/_legacy/` — 14 scripts confirmados
   - `research/01_señales_entry_exit/` — 5 scripts activos
   - `.agents/references/metar/` — resto de archivos intactos

3. **Verificación ejecutada:**
   - Lake regenerable desde producción: `build_continuous_metar_lake.py --dry-run`
   - Tests: `pytest tests/ -q` (303 passed)
   - Compuerta: 31/31 señales activas
   - 0 referencias activas a legacy

4. **Firma del modelo auditor** y fecha