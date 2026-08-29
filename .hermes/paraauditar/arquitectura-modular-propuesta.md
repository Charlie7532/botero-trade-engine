# ARQUITECTURA MODULAR — research/01_señales_entry_exit/
## Propuesta de Refactorización — 20-Ago-2026

---

## ÁRBOL PROPUESTO

```
research/01_señales_entry_exit/
├── harness/
│   ├── engine.py                  # ARNÉS INMUTABLE: Bootstrap en tiempo de evento,
│   │                              # Welch t-test, cálculo de p-values vs baseline incondicional.
│   └── baseline_fixtures.py       # Datasets inmutables de control (MAX ctrl, MIN ctrl).
│
├── techos/
│   ├── signals_exit.py            # Solo señales de SALIDA (Filtradas estrictamente por MAX).
│   └── test_techos.py             # Test automatizado de significancia (p < 0.05).
│
├── pisos/
│   ├── signals_entry.py           # Solo señales de ENTRADA (Filtradas estrictamente por MIN).
│   └── test_pisos.py              # Test automatizado de significancia (p < 0.05).
│
├── eventos_especiales/
│   ├── singularidades_climax.py   # Shocks exógenos: Tail Risk SKEW, Credit Easing K1, Flash Crash.
│   └── test_especiales.py         # Validación de diamantes (alta asimetría).
│
└── benchmarks/                    # JSONs versionados e inmutables con timestamp y hash git.
```

---

## QUÉ RESUELVE ESTA ARQUITECTURA

| Problema actual | Cómo lo resuelve |
|-----------------|------------------|
| `medir_senal.py` tiene 1,183 líneas con 28 señales mezcladas (ENTRY, EXIT, PROPOSED) | Separación por tipo: `techos/` solo EXIT, `pisos/` solo ENTRY, `eventos_especiales/` solo singularidades |
| Gemini no filtraba por `pivot_type == "MAX"` en señales de techo | `signals_exit.py` filtra ESTRICTAMENTE por MAX. `signals_entry.py` filtra ESTRICTAMENTE por MIN. |
| Las 28 señales no tienen tests automatizados | `test_techos.py`, `test_pisos.py`, `test_especiales.py` validan significancia (p < 0.05) |
| El harness de medición está acoplado a las señales | `harness/engine.py` es INMUTABLE. Las señales son plugins que se inyectan. |
| Los JSONs de medición no tienen versionado | `benchmarks/` guarda JSONs con timestamp + hash git para trazabilidad |

---

## PRINCIPIOS DE DISEÑO

```
1. HARNESS INMUTABLE: engine.py y baseline_fixtures.py NO se modifican.
   Solo se agregan señales como plugins en techos/, pisos/, eventos_especiales/.

2. FILTRO ESTRICTO POR PIVOT_TYPE:
   - techos/signals_exit.py → solo evalúa en df[pivot_type == "MAX"]
   - pisos/signals_entry.py → solo evalúa en df[pivot_type == "MIN"]
   - eventos_especiales/ → puede evaluar en ambos (singularidades)

3. TEST AUTOMATIZADO:
   - Cada señal nueva debe pasar test_*.py ANTES de ser aceptada
   - p < 0.05 como gate mínimo
   - Bootstrap CI95 con seed fija
   - N_eff corregido por clustering temporal

4. BENCHMARKS VERSIONADOS:
   - Cada medición guarda JSON con:
     {timestamp, git_hash, señal, métricas, CI95, p_value, N_eff}
   - Inmutables: nunca se sobreescriben
```

---

## MIGRACIÓN DESDE medir_senal.py ACTUAL

```
ACTUAL:
  medir_senal.py (1,183 líneas monolíticas)
  ├── 28 señales mezcladas
  ├── Harness de medición (medir(), _pctiles(), _bootstrap_ci(), etc.)
  └── main() que ejecuta todas las señales

FUTURO:
  harness/engine.py           ← medir(), _pctiles(), _bootstrap_ci(), etc.
  harness/baseline_fixtures.py ← cargar_datos(), baseline por pivot_type
  techos/signals_exit.py      ← bsi_recovery, euforia, fg_extreme_greed, + PROPOSED
  pisos/signals_entry.py      ← credit_easing_k1, pcr_put_panic, bsi_washed_out, etc.
  eventos_especiales/         ← panico_total, capitulacion, credit_easing_k1 (singularidad)
  benchmarks/                 ← JSONs de todas las mediciones
```

---

## ESTADO

| Campo | Valor |
|-------|-------|
| **Estado** | 📋 PROPUESTA (no implementada) |
| **Origen** | Gemini (post-incidente, como corrección) |
| **Validación pendiente** | ¿La separación harness/señales/benchmarks es correcta? ¿Los filtros estrictos por MAX/MIN son adecuados para todas las señales? |
| **Riesgo** | credit_easing_k1 es ENTRY pero también es evento especial (singularidad). ¿Dónde va? ¿En pisos/ o en eventos_especiales/? |
| **Próximo paso** | Auditoría de la propuesta contra los datos reales |

---
**Firma:** deepseek/deepseek-v4-pro (Hermes)
**Fecha:** 20-Ago-2026