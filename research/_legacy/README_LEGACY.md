# Research Legacy Archive — Trazabilidad Histórica

> **Aviso de Trazabilidad:**
> *Los scripts en este directorio fueron parte del trabajo de descubrimiento y exploración histórica (Fases pre-homologación, Agosto 2026). Su funcionalidad fue completamente incorporada y superada por el pipeline activo en `research/01_señales_entry_exit/` y los generadores en `backend/scripts/generators/`. Se preservan exclusivamente para trazabilidad, auditoría forense y re-evaluación futura. **NO ejecutar como parte del pipeline de medición de producción.***

---

## Inventario de Scripts Históricos

| Script | Propósito Original | Razón de Deprecación / Reemplazo |
|:-------|:-------------------|:----------------------------------|
| `extract_overflows_vela_a_vela.py` | Barrido inicial de overflows sigma | Hallazgos e indicadores incorporados formalmente a `build_continuous_metar_lake.py`. |
| `audit_overflow_candle_anatomy.py` (V1) | Análisis preliminar de anatomía de velas | Reemplazado por `audit_overflow_candle_anatomy_v2.py` (la V1 mezclaba incorrectamente techos y pisos). |
| `detector_regimen_crisis.py` | Estudio one-off de 79 episodios de crisis | Estudio puntual histórico; la telemetría continua ahora vive en el data lake y SIGMET. |
| `audit_vector_confluence.py` | Métricas de confluencia vectorial D1/D2/D3 | Scores de confluencia integrados en `build_continuous_metar_lake.py`. |
| `recompute_signals_fact_store_triad.py` (V1) | Agregación triádica preliminar | Reemplazado por `recompute_signals_fact_store_triad_v2.py`. |
| `wins_losses_*.py` (7 scripts) | Mediciones preliminares de win rates | Unificados y superados por el paquete determinista `arnes/` + `medir_senal.py`. |
| `audit_entry_exit.py` | Auditoría de señales entry/exit inicial | Reemplazado por el arnés modular de señales. |
| `generate_full_population_census.py` | Censo poblacional temprano | Incorporado en los scripts generadores estándar de `backend/scripts/generators/`. |

---

## Pipeline Activo Vigente

Para tareas de medición, evaluación y regeneración, referirse exclusivamente a:
- **Arnés de Medición:** `research/01_señales_entry_exit/medir_senal.py`
- **Generador Data Lake:** `research/01_señales_entry_exit/build_continuous_metar_lake.py`
- **Evaluador First-Passage:** `research/01_señales_entry_exit/evaluador_vela_a_vela.py`
- **Triada Multiescala V2:** `research/01_señales_entry_exit/recompute_signals_fact_store_triad_v2.py`
- **Anatomía Segregada V2:** `research/01_señales_entry_exit/audit_overflow_candle_anatomy_v2.py`
