# MAPA DE GENERADORES — Cadencia de Actualización (Clean Architecture)

**Fecha:** 30-Ago-2026
**Propósito:** Clasificar todos los generadores según su frecuencia de ejecución, dependencias y ubicación clean.

---

## CADENCIA DE ACTUALIZACIÓN

### ⚡ DIARIA — Ingesta de datos (no ejecuta generadores)

| Acción | Responsable | ¿Automatizado? |
|:-------|:-----------|:--------------:|
| Ingesta de OHLCV al Vault (TimescaleDB) | Fuente externa / EOD batch | ❌ Manual |
| Verificar frescura del Vault | `NOTAM_incident_service` | ✅ Automático |

**Archivos tocados:** Solo Vault (TimescaleDB). Ningún archivo del repo.

---

### 📅 SEMANAL — Verificación de drift (no regenera artefactos)

| Acción | Comando | Tiempo |
|:-------|:--------|:------:|
| Verificar integridad taxonómica | `pytest tests/test_taxonomy_integrity.py -q` | ~5s |
| Verificar que 31/31 señales disparan | `generate_quants_obs.py --dry-run` | ~40s |

**Archivos verificados (solo lectura, no modifica):**
- `tests/test_taxonomy_integrity.py` (46 tests)
- `backend/scripts/generators/generate_quants_obs.py` (compuerta de propósito)

---

### 📆 MENSUAL — Regeneración completa de artefactos

**Orden estricto** (cada paso depende del anterior):

| Orden | Script | Artefacto generado | Tiempo |
|:-----:|:-------|:-------------------|:------:|
| 1 | `generate_all_150_state_fact_stores.py` | 11 fact stores JSON | ~10 min |
| 2 | `build_continuous_metar_lake.py` | `continuous_metar_lake.parquet` (8,453×257) | ~3 min |
| 3 | `generate_quants_obs.py` | `quants_obs.pkl` (1,590×165) | ~1 min |
| 4 | `pytest tests/ -q` | 303 tests de regresión | ~1 min |

**Ubicación clean de cada script tras la migración:**

| Script | Ubicación actual | Ubicación clean final |
|:-------|:----------------:|:---------------------:|
| `generate_all_150_state_fact_stores.py` | ✅ `backend/scripts/generators/` | ✅ ya está |
| 11 × `generate_{station}_fact_table.py` | ✅ `backend/scripts/generators/` | ✅ ya están |
| `build_continuous_metar_lake.py` | ❌ `research/01_señales_entry_exit/` | ➡️ **mover a `backend/scripts/generators/`** |
| `generate_quants_obs.py` | ✅ `backend/scripts/generators/` | ✅ ya está |

**Archivos generados (no versionados, regenerables):**
- `data/research/continuous_metar_lake.parquet` (~3.9 MB)
- `data/research/pivots/quants_obs.pkl` (~2.0 MB)
- `backend/modules/entry_decision/domain/rules/*_fact_store.json` (11 archivos, ~3-5 MB total)

---

### 🔴 POR EVENTO — Regeneración condicional

| Evento | Acción | Archivos que cambian |
|:-------|:-------|:---------------------|
| **Cambio de taxonomía** (nuevos labels, bins) | Regeneración completa mensual + walkthrough | `d1_labels_canonical.md`, `gaussian_scale_policy.md`, `agent_quick_reference.md` |
| **Bug en lookup adapter** | Solo ese adapter + tests | `backend/.../domain/rules/{station}_lookup.py` |
| **Nueva señal en señales.py** | Tests + compuerta 31/31 | `research/01_señales_entry_exit/arnes/señales.py` |
| **Vault >20% nuevo** (≈5-7 años) | Recalibrar edges (Rule S6) | 11 fact stores + lake + quants_obs |
| **Structural regime shift** | Recalibrar edges (Rule S6) + documentación | Fact stores + docs |
| **Ejecutar evaluador/validador** | A pedido (investigación) | `data/research/signals/evaluacion_*.json` |
| **Ejecutar tríada/anatomía** | A pedido (investigación) | `signals_triad_fact_sheet_v2.json`, `overflow_candle_anatomy_v2.json` |

---

## CLASIFICACIÓN CLEAN — Todos los generadores

### 🟢 NÚCLEO — Pipeline METAR (se ejecuta mensualmente, migrado a backend)

| Generador | Rol | Clean path |
|:----------|:----|:-----------|
| `generate_all_150_state_fact_stores.py` | Orquestador canónico | `backend/scripts/generators/` |
| `generate_vix_fact_table.py` | Fact store VIX | `backend/scripts/generators/` |
| `generate_vvix_fact_table.py` | Fact store VVIX | `backend/scripts/generators/` |
| `generate_pcr_fact_table.py` | Fact store PCR | `backend/scripts/generators/` |
| `generate_fg_fact_table.py` | Fact store FG | `backend/scripts/generators/` |
| `generate_sv5_turbulence_fact_table.py` | Fact store SV5 | `backend/scripts/generators/` |
| `generate_skew_fact_table.py` | Fact store SKEW | `backend/scripts/generators/` |
| `generate_credit_fact_table.py` | Fact store Credit | `backend/scripts/generators/` |
| `generate_yield_curve_fact_table.py` | Fact store Yield | `backend/scripts/generators/` |
| `generate_rotation_fact_table.py` | Fact store Rotation | `backend/scripts/generators/` |
| `generate_bsi_fact_table.py` | Fact store BSI | `backend/scripts/generators/` |
| `generate_dxy_fact_table.py` | Fact store DXY | `backend/scripts/generators/` |
| **`build_continuous_metar_lake.py`** | **Lake continuo** | **➡️ migrar a `backend/scripts/generators/`** |
| `generate_quants_obs.py` | Tabla pivotal | `backend/scripts/generators/` |

### 🟡 INVESTIGACIÓN — Evaluadores (permanecen en research, no se migran)

| Script | Rol | Clean path |
|:-------|:----|:-----------|
| `evaluador_vela_a_vela.py` | First-passage + INDEP + 3D-régimen | `research/01_señales_entry_exit/` |
| `validador_oos.py` | Walk-forward 10 folds | `research/10_gate_oos_validation/` |
| `recompute_signals_fact_store_triad_v2.py` | Agregación ponderada triádica | `research/01_señales_entry_exit/` |
| `audit_overflow_candle_anatomy_v2.py` | Anatomía MIN/MAX/ENTRE V2 | `research/01_señales_entry_exit/` |
| `arnes/` (8 módulos) | Arnés de medición | `research/01_señales_entry_exit/arnes/` |

### ⚪ TIDE/BENCHMARKS — Secundarios (permanecen en backend, sin cadencia fija)

| Generador | Rol | Clean path |
|:----------|:----|:-----------|
| `generate_cascade_calibration.py` | Calibración cascade | `backend/scripts/generators/` |
| `generate_tide_derived_table.py` | TIDE derived | `backend/scripts/generators/` |
| `generate_tide_ev_real_derived.py` | TIDE EV real | `backend/scripts/generators/` |
| `generate_wave_derived_table.py` | Wave derived | `backend/scripts/generators/` |
| `generate_wave_ev_real_derived.py` | Wave EV real | `backend/scripts/generators/` |
| `generate_wave_multiscale_tree.py` | Wave multiscale | `backend/scripts/generators/` |
| `generate_v37_full_benchmark.py` | Benchmark v37 | `backend/scripts/generators/` |
| `generate_v38_full_master_benchmark.py` | Benchmark v38 | `backend/scripts/generators/` |
| `generate_v39_full_master_benchmark.py` | Benchmark v39 | `backend/scripts/generators/` |
| `generate_v40_full_master_benchmark.py` | Benchmark v40 | `backend/scripts/generators/` |
| `generate_v41_comparative_benchmark.py` | Benchmark v41 | `backend/scripts/generators/` |
| `generate_final_comprehensive_tables.py` | Final tables | `backend/scripts/generators/` |
| `generate_grouped_distribucion_table.py` | Grouped distribution | `backend/scripts/generators/` |
| `generate_multiscale_ev_derived.py` | Multiscale EV | `backend/scripts/generators/` |
| `generate_perfect_grouped_table.py` | Perfect grouped | `backend/scripts/generators/` |
| `generate_s5_qqq_indicators.py` | S5 QQQ indicators | `backend/scripts/generators/` |
| `generate_unified_ev_real_derived.py` | Unified EV | `backend/scripts/generators/` |
| `generate_zigzag_spectrum_json.py` | Zigzag spectrum | `backend/scripts/generators/` |
| `generate_clean_intelligence_references.py` | Clean refs | `backend/scripts/generators/` |

### 🔴 LEGACY — A mover a `research/_legacy/`

| Script | Razón | Clean path final |
|:-------|:------|:-----------------|
| `builder_quants_obs.py` | Superado por `generate_quants_obs.py` | `research/_legacy/builder_quants_obs.py` |
| `extract_overflows_vela_a_vela.py` | Exploración histórica | `research/_legacy/` |
| `audit_overflow_candle_anatomy.py` (V1) | Reemplazado por V2 | `research/_legacy/` |
| `detector_regimen_crisis.py` | One-off exploratorio | `research/_legacy/` |
| `audit_vector_confluence.py` | Scores ya en lake | `research/_legacy/` |
| `wins_losses_*.py` (6 scripts) | Medición antigua | `research/_legacy/` |

---

## RESUMEN: Archivos tocados por cadencia

| Cadencia | Archivos modificados | Tiempo estimado |
|:---------|:---------------------|:---------------:|
| **Diaria** | 0 (solo Vault) | — |
| **Semanal** | 0 (solo verificación) | ~1 min |
| **Mensual** | 11 fact stores + lake + quants_obs + tests | ~15 min |
| **Por evento** | Variable según el evento | 5 min - 1 hora |
| **Una vez (migración)** | `build_continuous_metar_lake.py` → backend + legacy → `_legacy/` | ~10 min |