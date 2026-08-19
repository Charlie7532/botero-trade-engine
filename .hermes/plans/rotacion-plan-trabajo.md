# Plan de Trabajo — Rotación (post-auditoría 2026-08-16)

## Errores a corregir (higiene inmediata)

- [ ] **Fix #1 — `market_status` siempre "NORMAL_BALANCED"**: Mapear los STK_* codes reales del fact store a market_status en `rotation_metar_service.py` líneas 225-232, o derivar market_status del `rotation_bin` (D1) en vez del action_code.
- [ ] **Fix #2 — Test stale `test_rotation_lookup.py`**: Actualizar la lista de labels D1 en línea 15 para que matchee los labels reales del lookup (`DEFENSIVE`, `BALANCED` en vez de `DEFENSIVE_FLIGHT`, `NEUTRAL_DEFENSIVE`).
- [ ] **Fix #3 — Limpiar labels obsoletos**: Eliminar o actualizar `update_unit_tests_for_150_states.py` (labels D1 de rotation totalmente obsoletos) y `audit_rotation_deep_learning.py`/`standardize_governance_in_references.py` (umbral crudo ROTATION < 1.85 que viola principio de bins calibrados).

## Cambios propuestos (exploración + infraestructura)

- [ ] **Cambio A — Trazabilidad de benchmarks**: Definir baseline canónico único para todos los benchmarks (unificar linaje de versiones Rotation Gate V1-V9 y Quality Entry Gate V22-V41, resolver la ambigüedad de "V40" con 3 valores distintos en 3 reportes). Auditar scripts `generate_v*_full_master_benchmark.py` y `compare_benchmarks_master.py`.
- [ ] **Cambio B — Descomposición de MERCADO_SANO en sub-fases**: Explorar los mismos S5/SV5 del Gate con lógica de sub-régimen (acumulación temprana, expansión media, euforia tardía). Señal interna, sin dependencias externas. Marcado ALTA PRIORIDAD desde V28, nunca ejecutado.