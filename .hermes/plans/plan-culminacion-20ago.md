# PLAN DE CULMINACIÓN INSTITUCIONAL: PIPELINE DE SEÑALES Y ARNESES

**Documento:** Plan de Culminación Final · **Fecha:** 20-Ago-2026 · **Consolidado por:** Pipeline Hermes (Worker + Auditor)
**Estado:** ✅ APROBADO CON RESERVAS → LISTO PARA EJECUCIÓN

---

## 0. Resumen Ejecutivo

Este plan consolida la auditoría fáctica del arnés de medición `medir_senal.py`, los 5 addenda incorporados desde `fact_store_v3_architecture.md`, y las verificaciones estadísticas de 33 años de historia del S&P 500 (1,590 pivotes). 

El objetivo es cerrar la brecha entre la experimentación y el motor de decisión institucional en producción, eliminando anti-señales con lift < 1.0, ruido de régimen (fire rate > 50%), y asegurando que cada señal de trading posea edge cuantificado con significancia empírica demostrada.

---

## 1. Mapa de Señales: Diagnóstico Fáctico Final

### 🟢 Señales de Producción / Validadas (Top Edge & Lift > 1.05x)

| Señal | Tipo | N (Pivotes) | WR / Hit Rate | Lift vs Base | Forward Medio | Estado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **`credit_easing_k1`** | ENTRY (MIN) | 112 | 93.8% sube | 1.125x | +5.19% | ✅ PRODUCCIÓN (Grade A) |
| **`euforia`** | EXIT (MAX) | 35 | 100.0% cae | 1.199x | -4.35% | ✅ PRODUCCIÓN (Grade A) |
| **`stealth_tail_hedging`** | EXIT (MAX) | 20 | 100.0% cae | 1.199x | -4.45% | ✅ PRODUCCIÓN (Diamante) |
| **`bsi_recovery`** | EXIT (MAX) | 346 | 92.2% cae | 1.106x | -3.62% | ✅ PRODUCCIÓN (Robusta) |
| **`fg_extreme_greed`** | EXIT (MAX) | 25 | 92.0% cae | 1.103x | -3.32% | ✅ PRODUCCIÓN (Grade A) |
| **`capitulacion`** | ENTRY (MIN) | 82 | 65.9% sube | 1.082x | +1.40% | ✅ PRODUCCIÓN (Grade A) |
| **`pcr_put_panic`** | ENTRY (MIN) | 70 | 71.4% sube | 1.095x | +2.70% | ✅ PRODUCCIÓN (Grade A) |
| **`bsi_washed_out`** | ENTRY (MIN) | 161 | 65.8% sube | 1.080x | +1.42% | ✅ PRODUCCIÓN (Grade A) |

---

### 🔴 Señales a Retirar / Depurar del Registro

| Señal | Motivo de Retiro | Datos Fácticos | Acción |
|---|---|---|---|
| **`breadth_contraction_exit`** | Ruido de régimen (fire rate 87.7%) | 1,394/1,590 pivotes activos | Retirar de `SEÑALES` |
| **`credit_ease_exit`** | Ruido de régimen (fire rate 51.6%) | 820/1,590 pivotes activos | Retirar de `SEÑALES` |
| **`defensive_rotation_divergence`** | Anti-señal (Lift = 0.828x < 1.0) | En MAX cae solo 69.0% vs base 83.4% | Retirar o invertir lógica |
| **`sv5t_silent_distribution`** | Anti-señal (Lift = 0.840x < 1.0) | En MAX cae solo 70.0% vs base 83.4% | Retirar de `SEÑALES` |
| **`regime_change_exit`** | Anti-señal (Lift = 0.789x < 1.0) | En MAX cae solo 65.8% vs base 83.4% | Retirar de `SEÑALES` |
| **`vix_complacency_exit`** | Duplicado 100% idéntico | Idéntica a `euforia` (overlap 1.0) | Eliminar duplicado |

---

## 2. Plan de Acción Priorizado (Máximo 8 Ítems)

```
FASE 1: LIMPIEZA & LIFT NATIVO (P1)
  ├─ Item 1: Incorporar métrica LIFT en medir_senal.py
  ├─ Item 2: Depuración del registro SEÑALES & forzado de pivot_type
  └─ Item 3: Corrección de lógica BEAR en _divergence_regime + limpieza RNG

FASE 2: VALIDACIÓN CIENTÍFICA & METAR (P2)
  ├─ Item 4: Validación Walk-Forward (OOS 2016-2026) TOP signals
  └─ Item 5: Exposición de sigma_depth en servicios METAR/SIGMET

FASE 3: MEDICIÓN SISTEMÁTICA & CIERRE (P3)
  ├─ Item 6: Medición sistemática de las 15 señales PROPOSED restantes
  ├─ Item 7: Actualización de GUIA_EMPLEO.md y ARBOLES_DECISION.md
  └─ Item 8: Commit unificado y sincronización en git
```

---

### Detalle de Tareas

| # | Prioridad | Tarea / Ítem | Esfuerzo | Dependencias | Entregable Concreto |
|---|:---:|---|:---:|---|---|
| **1** | **P1** | **Métrica LIFT Nativa en `medir_senal.py`**<br>Incorporar `lift_vs_base_rate` en `rep["activa"]` y en el resumen de salida para todas las ejecuciones. | 1.0 h | Ninguna | `medir_senal.py` actualizado emitiendo LIFT en stdout y JSON. |
| **2** | **P1** | **Depuración del Registro `SEÑALES` y Filtro de Tipo**<br>Retirar las 6 señales defectuosas/duplicadas y forzar `pivot_type == "MAX"` en funciones EXIT. | 1.0 h | Ítem 1 | Registro depurado con 100% de señales con Lift ≥ 1.05x o N diamante. |
| **3** | **P1** | **Corrección de Divergencia BEAR e Higiene de Código**<br>Ajustar `_divergence_regime` para reconocer colapso severo (high cascade) en caídas, unificar a `default_rng` y remover import inline. | 0.5 h | Ninguna | `medir_senal.py` con lógica simétrica y determinismo homogéneo. |
| **4** | **P2** | **Validación Walk-Forward (Out-of-Sample 2016–2026)**<br>Entrenar parámetros en 1993–2015 y validar OOS en 2016–2026 para las TOP 3 ENTRY y TOP 3 EXIT. | 2.5 h | Ítems 1, 2 | Reporte de robustez libre de sesgo look-ahead / data snooping. |
| **5** | **P2** | **Puente METAR/SIGMET: Exposición de `sigma_depth`**<br>Integrar `sigma_overflow.py` en los servicios METAR para reportar anomalías >±3σ en el broadcast diario. | 2.0 h | fact_store_v3 §17 | Endpoints `/api/metar/*` con campo `sigma_depth` y alertas SIGMET activas. |
| **6** | **P3** | **Medición Sistemática de Señales PROPOSED Restantes**<br>Ejecutar el arnés enriquecido sobre el catálogo completo depurado y almacenar JSONs en `data/research/`. | 1.5 h | Ítems 1, 2, 3 | Conjunto completo de JSONs de auditoría en el feature lake. |
| **7** | **P3** | **Sincronización de Documentación Operacional**<br>Actualizar `GUIA_EMPLEO.md` y `ARBOLES_DECISION.md` reflejando las métricas de LIFT y el catálogo final depurado. | 1.0 h | Ítems 2, 6 | Documentos operacionales alineados con el código de producción. |
| **8** | **P3** | **Cierre y Commit Unificado en Repositorio**<br>Consolidar diffs limpios, verificar py_compile general y preparar commit estructurado bajo Clean Architecture. | 0.5 h | Aprobación Juan Andrés | Commit en git con trazabilidad institucional completa. |

---

## 3. Checklist de Autotest y Control de Calidad

- [x] Todas las afirmaciones fácticas verificadas contra `quants_obs.pkl` y precios SPY del Vault.
- [x] Determinismo verificado (RNG con seed fija).
- [x] Límite de 8 ítems respetado estrictamente.
- [x] Sin mutaciones destructivas en código base durante la auditoría.
