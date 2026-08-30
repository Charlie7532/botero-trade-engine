# Generadores — Clasificación por Capa y Cadencia

**Fecha:** 30-Ago-2026  
**Total:** 33 scripts Python + 1 `__init__.py`  
**Política de cadencia:** Ver Rules S8/S9 en [`gaussian_scale_policy.md`](file:///root/botero-trade/.agents/references/metar/gaussian_scale_policy.md)

---

## 🟢 NÚCLEO — Pipeline METAR Esencial (Cadencia: **Mensual**)

Ejecutar en **orden estricto** según Rule S9. Cada paso depende del anterior.

| Orden | Script | Artefacto | Tiempo |
|:-----:|:-------|:----------|:------:|
| 1 | `generate_all_150_state_fact_stores.py` | 11 fact stores JSON | ~10 min |
| 1.1 | `generate_vix_fact_table.py` | `vix_fact_store.json` | (invocado por #1) |
| 1.2 | `generate_vvix_fact_table.py` | `vvix_fact_store.json` | (invocado por #1) |
| 1.3 | `generate_pcr_fact_table.py` | `pcr_fact_store.json` | (invocado por #1) |
| 1.4 | `generate_fg_fact_table.py` | `fg_fact_store.json` | (invocado por #1) |
| 1.5 | `generate_sv5_turbulence_fact_table.py` | `sv5_turbulence_fact_store.json` | (invocado por #1) |
| 1.6 | `generate_skew_fact_table.py` | `skew_fact_store.json` | (invocado por #1) |
| 1.7 | `generate_credit_fact_table.py` | `credit_fact_store.json` | (invocado por #1) |
| 1.8 | `generate_yield_curve_fact_table.py` | `yield_curve_fact_store.json` | (invocado por #1) |
| 1.9 | `generate_rotation_fact_table.py` | `rotation_fact_store.json` | (invocado por #1) |
| 1.10 | `generate_bsi_fact_table.py` | `bsi_fact_store.json` | (invocado por #1) |
| 1.11 | `generate_dxy_fact_table.py` | `dxy_fact_store.json` | (invocado por #1) |
| 2 | `build_continuous_metar_lake.py` | `continuous_metar_lake.parquet` (8,453×257) | ~3 min |
| 3 | `generate_quants_obs.py` | `quants_obs.pkl` (1,590×165) | ~1 min |

**Nota:** Solo se ejecuta `generate_all_150_state_fact_stores.py` (#1) que orquesta los 11 sub-generadores internamente. Los scripts 1.1-1.11 también pueden ejecutarse individualmente para regenerar una sola estación.

---

## 🟡 INVESTIGACIÓN — Evaluadores y Análisis (Cadencia: **A pedido**)

Se ejecutan cuando hay una nueva señal, cambio de población, o auditoría.

| Script | Propósito |
|:-------|:----------|
| `generate_cascade_calibration.py` | Calibración de z-score empírico y terciles asimétricos para cascadas |
| `generate_clean_intelligence_references.py` | Genera referencias cuantitativas limpias para las 10 estaciones METAR |
| `generate_s5_qqq_indicators.py` | Genera indicadores de breadth S5_QQQ y SV5_QQQ (1999-2026) |
| `generate_zigzag_spectrum_json.py` | Espectro multi-activo ZigZag breadth (SPY, QQQ, 11 sectores ETF) |

> **Nota:** Los evaluadores principales (`evaluador_vela_a_vela.py`, `validador_oos.py`, `recompute_triad_v2.py`, `audit_overflow_v2.py`) están en `research/01_señales_entry_exit/`, no aquí.

---

## ⚪ SECUNDARIOS — TIDE, Wave, Benchmarks (Cadencia: **Sin cadencia fija**)

Generadores de tablas derivadas, benchmarks históricos, y árboles de decisión experimentales. Se ejecutan solo durante investigación activa o al crear nuevas versiones del motor.

### TIDE / EV Derivados
| Script | Propósito |
|:-------|:----------|
| `generate_tide_derived_table.py` | `rc_tide_derived.json` v2 — tabla derivada del comité TIDE |
| `generate_tide_ev_real_derived.py` | Matriz EV real derivada y reglas multi-nivel (P(bull) × EV) |
| `generate_unified_ev_real_derived.py` | Árbol EV unificado con fallbacks jerárquicos (S1→S5) |
| `generate_multiscale_ev_derived.py` | Árbol EV multi-escala (Stage 2) |

### Wave
| Script | Propósito |
|:-------|:----------|
| `generate_wave_derived_table.py` | `rc_wave_derived.json` — tabla derivada wave |
| `generate_wave_ev_real_derived.py` | Matriz EV real derivada wave multi-nivel |
| `generate_wave_multiscale_tree.py` | `rc_wave_multiscale_tree.json` — árbol multi-escala wave |

### Benchmarks (V37-V41)
| Script | Propósito |
|:-------|:----------|
| `generate_v37_full_benchmark.py` | Benchmark comparativo V36 vs V37 (2000-2026) |
| `generate_v38_full_master_benchmark.py` | Benchmark maestro V38 (2000-2026) |
| `generate_v39_full_master_benchmark.py` | Benchmark maestro V39 (2000-2026) |
| `generate_v40_full_master_benchmark.py` | Benchmark maestro V40 con fórmulas auditadas |
| `generate_v41_comparative_benchmark.py` | Benchmark comparativo V40 vs V41 |

### Tablas de auditoría
| Script | Propósito |
|:-------|:----------|
| `generate_final_comprehensive_tables.py` | Reporte de benchmark final y estadísticas de eficiencia (V37.1) |
| `generate_grouped_distribucion_table.py` | Tabla de auditoría agrupada DISTRIBUCION_PRE_CRASH |
| `generate_perfect_grouped_table.py` | Tabla de auditoría agrupada perfecta (ordenada por S5TH) |

---

## Regeneración Mensual (Rule S9)

```bash
cd /root/botero-trade

# 1. Fact stores (desde Vault) — regenera 11 JSON (~10 min)
PYTHONPATH=. backend/.venv/bin/python \
  backend/scripts/generators/generate_all_150_state_fact_stores.py

# 2. Lake continuo — regenera continuous_metar_lake.parquet (~3 min)
PYTHONPATH=. backend/.venv/bin/python \
  backend/scripts/generators/build_continuous_metar_lake.py

# 3. Tabla pivotal — regenera quants_obs.pkl (~1 min)
PYTHONPATH=. backend/.venv/bin/python \
  backend/scripts/generators/generate_quants_obs.py

# 4. Tests de regresión — verifica integridad (~1 min)
PYTHONPATH=. backend/.venv/bin/python -m pytest tests/ -q
```
