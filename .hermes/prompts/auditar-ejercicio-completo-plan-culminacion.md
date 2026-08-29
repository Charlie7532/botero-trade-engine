# PROMPT — Auditoría Pipeline Secuencial: Ejercicio 5-Addenda + Plan de Culminación

**Para:** Pipeline Hermes (Worker → Auditor)
**De:** Juan Andrés (Arquitecto) vía Gemini → Hermes
**Fecha:** 20-Ago-2026
**Prioridad:** P1
**Estado:** NUEVO

---

## 0. CONTEXTO Y ESTADO ACTUAL

En los últimos 3 días (17-19 Ago 2026) se realizaron ejercicios en Botero Trade. Todo está verificado, ejecutado y medido. Esta auditoría confirma que lo construido es sólido, identifica gaps, y propone un plan de culminación.

### 0.1 Tabla de Estado Actual (lo que YA está hecho)

| # | Ejercicio | Estado | Archivos |
|---|-----------|--------|----------|
| 1 | **Arnés medir_senal.py** (original, 1,183 líneas) | ✅ PRODUCCIÓN — 28 señales, 13 métricas, regresión cero | `research/01_señales_entry_exit/medir_senal.py` |
| 2 | **5 Addenda implementados** (20-Ago-2026) | ✅ COMPLETADO — +250 líneas, 3 funciones auxiliares | `medir_senal.py` (1,183→1,433 líneas) |
| 3 | **GUIA_EMPLEO.md** | ✅ NUEVO — Mapa Dato→Pregunta→Decisión | `research/01_señales_entry_exit/GUIA_EMPLEO.md` |
| 4 | **ARBOLES_DECISION.md** | ✅ NUEVO — Árboles ENTRY/EXIT operacionales | `research/01_señales_entry_exit/ARBOLES_DECISION.md` |
| 5 | **forense_precursores.py** (221 líneas) | ✅ PRODUCCIÓN — 86 precursores, LIFT, universalidad cross-señal | `research/04_conjuncion_multi_estacion/forense_precursores.py` |
| 6 | **fact_store_v3_architecture.md** (1,148 líneas) | ✅ DOCUMENTADO — 8 addenda + Sección 17 SIGMET | `.hermes/paraauditar/fact_store_v3_architecture.md` |
| 7 | **Auditoría cruzada fact_store vs algoritmos** | ✅ COMPLETADA — 11 factores, 4 gaps, 5 fortalezas | `.hermes/paraauditar/auditoria-cruzada-factstore-vs-algoritmos.md` |
| 8 | **Validación 5 interpretaciones** (Claude Opus) | ✅ INCORPORADA — 3 correcciones fácticas aplicadas | `.hermes/paraauditar/validacion_5_interpretaciones_fact_store.md` |
| 9 | **Auditoría de código fact_store_v3** | ✅ INCORPORADA — 8/11 D1 labels corregidos, BSI S5TW | `.hermes/paraauditar/audit_fact_store_v3_architecture.md` |
| 10 | **Casos de éxito y fracaso documentados** | ✅ DOCUMENTADOS — 3 casos de éxito + 1 caso de fracaso | `.hermes/casodeexito/` + `.hermes/casofracaso/` |
| 11 | **Auditoría Claude Opus de los 5 addenda** (20-Ago 21:00) | ✅ RESCATADA — 7 hallazgos, 5 verificados contra datos reales | `.hermes/reportes/auditoria_5_addenda_algoritmos.md` |

### 0.2 Hallazgos de Claude Opus (verificados contra datos reales) — OBLIGATORIO INCORPORAR

| # | Hallazgo | Veredicto | Datos reales |
|---|----------|:---:|---|
| PC1 | **4 señales EXIT tienen lift < 1.0** (peor que baseline) | ✅ CONFIRMADO | defensive_rotation_divergence lift=0.828x, sv5t_silent_distribution lift=0.840x, regime_change_exit lift=0.789x, credit_ease_exit lift=0.954x |
| PC2 | **2 señales EXIT tienen fire rate > 50%** (ruido de régimen) | ✅ CONFIRMADO | breadth_contraction_exit 87.7%, credit_ease_exit 51.6% |
| PC3 | **vix_complacency_exit ≡ euforia** (100% overlap) | ✅ CONFIRMADO | N=41 idéntico, 100% overlap → SON LA MISMA SEÑAL |
| PC4 | **Falta LIFT vs base rate en el output del arnés** | ✅ CONFIRMADO — gap real | forense_precursores.py lo tiene; medir_senal.py no |
| PC5 | **RandomState vs default_rng inconsistencia** | ✅ CONFIRMADO — menor | Líneas 1060, 1087 usan RandomState; L466 usa default_rng |
| PC6 | **Label fantasma en docstring** | ❌ FALSO POSITIVO | Es documentación del fix, no un bug |
| PC7 | **`import datetime` dentro de función** | ✅ CONFIRMADO — menor | Anti-patrón de estilo, no funcional |

**LIFT verificado para las TOP 5 EXIT desde pivotes MAX (base rate=83.4%):**

| Señal | N (MAX) | %Cae | Lift | Fwd | Veredicto |
|-------|:---:|:---:|:---:|:---:|---|
| euforia | 35 | 100.0% | 1.199x | -4.35% | ⭐ TOP |
| vix_complacency_exit | 35 | 100.0% | 1.199x | -4.35% | ⚠️ DUPLICADO de euforia |
| stealth_tail_hedging | 20 | 100.0% | 1.199x | -4.45% | ⭐ TOP — N diamante |
| bsi_recovery | 346 | 92.2% | 1.106x | -3.62% | ✅ N robusto |
| fg_extreme_greed | 25 | 92.0% | 1.103x | -3.32% | ✅ N marginal |

### 0.3 Lo construido hoy (para referencia del worker)

**3 funciones nuevas en medir_senal.py:**
- `_structural_momentum_filter(señal, df, spy)` → HL/LL (entry) y HH/LH (exit) por precio SPY real
- `_prev_leg_context(señal, fwd, df)` → post-crash vs drift, umbral P90, desglose forward
- `_divergence_regime(rep)` → convergencia/divergencia con umbrales calibrados contra datos reales

**Bugs corregidos:** label fantasma `BREADTH_RECOVERY` → `EXPANSIVE_BREADTH` (N 324→481), guard `DIAMANTE_ANECDOTAL` (protocolo §3.3), N=0 guard en main().

---

## 1. ARQUITECTURA DEL PIPELINE (secuencial)

```
ESPECIFICACIÓN (este prompt)
        │
        ▼
┌─────────────────────────────────┐
│  WORKER (qwen-2.5-coder-32b)     │
│  • Lee el código (medir_senal.py)│
│  • Ejecuta verificaciones        │
│  • Propone plan de culminación   │
│  • Entrega: plan_worker.json     │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│  AUDITOR (qwen3.8-max)           │
│  • Verifica hallazgos del worker │
│  • Busca errores no detectados   │
│  • Emite Confidence Card         │
│  • Entrega: reporte_auditor.md   │
└──────────────┬──────────────────┘
               │
               ▼
          PLAN FINAL
   .hermes/plans/plan-culminacion-20ago.md
```

---

## 2. FASE 1 — WORKER (qwen-2.5-coder-32b)

**Perfil:** `worker` — modelo codec entrenado en repositorios/diffs/refactors. Ejecuta especificaciones sin razonar sobre el dominio financiero (previene scope creep como el de Gemini B1).

**Tareas:**

| # | Tarea | Verificación |
|---|-------|-------------|
| W1 | Leer `medir_senal.py` completo y verificar que las 3 funciones auxiliares compilan, están correctamente aisladas, y no comparten estado mutable con `medir()` | py_compile + diff vs original |
| W2 | Ejecutar `medir_senal.py --señal credit_easing_k1` y `--señal bsi_recovery` y verificar que los 3 campos nuevos (`structural_momentum`, `prev_leg_context`, `divergence_regime`) están presentes en el JSON con valores correctos | Comparar contra reporte de Hermes (p_hl≈0.571, p_hh≈0.702) |
| W3 | Identificar TODAS las señales PROPOSED que requieren medición prioritaria y las que deben ser **retiradas** según los hallazgos de Claude Opus (lift<1.0 o fire rate>50%) | Lista con justificación por señal |
| W4 | Proponer un **plan de culminación** con máximo 8 ítems, ordenados P1→P3, con: prioridad, descripción, esfuerzo estimado, dependencias, y entregable | Tabla en markdown |
| W5 | Identificar brechas entre lo construido y la arquitectura documentada en `fact_store_v3_architecture.md` (especialmente §17 SIGMET y §3.3 Diamantes) | Lista de gaps con severidad |

**Formato de entrega del worker:** archivo `.hermes/reportes/2026-08-20_plan_worker.json` con estructura:

```json
{
  "verificacion_codigo": {"compila": true/false, "campos_presentes": [...], "bugs_detectados": [...]},
  "señales_retirar": [{"nombre": "...", "razon": "lift<1.0|fire_rate>50%|duplicado", "datos": {...}}],
  "señales_medir_prioritario": [{"nombre": "...", "prioridad": "P1|P2|P3", "razon": "..."}],
  "plan_culminacion": [
    {"prioridad": "P1", "item": "...", "esfuerzo": "...", "depende_de": "...", "entregable": "..."}
  ],
  "brechas": [{"gap": "...", "severidad": "ALTA|MEDIA|BAJA", "accion": "..."}]
}
```

---

## 3. FASE 2 — AUDITOR (qwen3.8-max)

**Perfil:** `auditor` — generalista analítico. Busca errores que el implementador no vio. Emite Confidence Card.

**Input:** `plan_worker.json` (output del worker) + archivos del proyecto.

**Tareas:**

| # | Tarea | Verificación |
|---|-------|-------------|
| A1 | Verificar CADA afirmación del worker contra el código fuente real. Si el worker dice "compila", re-compilar. Si dice "campos presentes", abrir el JSON y verificarlos. | Confirmación o refutación con evidencia |
| A2 | Buscar errores que el worker NO detectó: ¿los umbrales de `_divergence_regime` son correctos para todas las señales? ¿la clasificación HL/LL usa correctamente precios SPY? ¿el label `EXPANSIVE_BREADTH` existe en el generador? | ≥3 hallazgos propios (no copiados del worker) |
| A3 | Verificar los datos de lift reportados por Claude Opus: ¿defensive_rotation_divergence realmente tiene lift=0.828x? ¿breadth_contraction_exit realmente tiene fire rate 87.7%? | Ejecutar medición independiente |
| A4 | Evaluar el plan de culminación del worker: ¿las prioridades son correctas? ¿falta algún ítem crítico? ¿las dependencias son realistas? | Score 1-10 y justificación |
| A5 | Emitir **Confidence Card** para el plan final: `[APROBADO / APROBADO CON RESERVAS / RECHAZADO]` con justificación de 3-5 líneas | Confidence Card al inicio del reporte |

**Formato de entrega del auditor:** archivo `.hermes/reportes/2026-08-20_reporte_auditor.md` con estructura:

```markdown
# CONFIDENCE CARD: [APROBADO / APROBADO CON RESERVAS / RECHAZADO]
Justificación: ...

## 1. Verificación de hallazgos del worker
| Afirmación | Veredicto | Evidencia |

## 2. Hallazgos propios (no detectados por el worker)
| # | Hallazgo | Severidad | Evidencia |

## 3. Verificación de datos de Claude Opus
| Dato | Veredicto | Medición independiente |

## 4. Evaluación del plan de culminación
Score: X/10
Fortalezas: ...
Debilidades: ...
Ítems faltantes: ...
```

---

## 4. ARCHIVOS DE REFERENCIA (leer ANTES de ejecutar)

| # | Archivo | Buscar específicamente |
|---|---------|------------------------|
| 1 | `research/01_señales_entry_exit/medir_senal.py` | Funciones L570-790, llamadas en `medir()` L1200+ |
| 2 | `research/01_señales_entry_exit/GUIA_EMPLEO.md` | 38 campos — verificar existencia en JSON real |
| 3 | `research/01_señales_entry_exit/ARBOLES_DECISION.md` | Regla HH corregida (AMPLIFICAR, no ignorar) |
| 4 | `.hermes/reportes/2026-08-20_ejecucion_5-addenda-algoritmos.md` | Reporte completo de Hermes — fuente de verdad |
| 5 | `.hermes/reportes/auditoria_5_addenda_algoritmos.md` | **🔴 OBLIGATORIO.** 7 hallazgos de Claude Opus verificados |
| 6 | `.hermes/paraauditar/validacion_5_interpretaciones_fact_store.md` | 5 correcciones fácticas |
| 7 | `.hermes/paraauditar/auditoria-cruzada-factstore-vs-algoritmos.md` | 11 factores, 4 gaps, 5 fortalezas |
| 8 | `.hermes/paraauditar/fact_store_v3_architecture.md` | §3.3 (Diamantes), §16 (Anti-patrones), §17 (SIGMET) |
| 9 | `.hermes/casodeexito/medir_senal.md` | Fact store: decisiones de diseño, bugs, lecciones |
| 10 | `.hermes/casodeexito/forense_precursores.md` | Fact store: LIFT, gates, D1×D2, universalidad |
| 11 | `.hermes/casofracaso/fracaso-gemini-aislamiento-muestra.md` | 5 fallos, 9 checks anti-fracaso |
| 12 | `.hermes/plans/perfiles-hermes-final.md` | Perfiles aprobados |

---

## 5. AUTOTEST (obligatorio para cada agente antes de entregar)

| # | Pregunta | Respuesta esperada |
|---|----------|-------------------|
| 1 | ¿Dónde está `_structural_momentum_filter` y cuántas líneas ocupa? | `medir_senal.py`, ~130 líneas |
| 2 | ¿Cuál es `p_hl` para credit_easing_k1 (N=112) medido por precio SPY? | 0.571 |
| 3 | ¿Qué label reemplazó a `BREADTH_RECOVERY` en `bsi_recovery`? | `EXPANSIVE_BREADTH` — label correcto del generador BSI bin 4 |
| 4 | ¿Cuál es la regla CORRECTA para `p_hh > 0.55`? | AMPLIFICAR EXIT (HH cae 90.2%, más que LH 75.3%) |
| 5 | ¿Qué archivo contiene `validate_overflow` y qué dimensiones cubre? | `sigma_overflow.py` — D1, D2 y D3 |
| 6 | ¿Cuántos eventos >±3σ en 1,590 pivotes? ¿Valor más extremo? | 34 eventos. PCR=2.872 (11.03σ) |
| 7 | ¿Qué devuelve `_divergence_regime` con N<3? ¿Por qué? | `DIAMANTE_ANECDOTAL` — protocolo §3.3 |
| 8 | ¿Forensics_precursores.py fue modificado? | No — git diff vacío |
| 9 | ¿Lift de euforia vs defensive_rotation_divergence? | euforia: 1.199x (TOP) · defensive: 0.828x (ANTI-SEÑAL) |
| 10 | ¿Overlap vix_complacency_exit ↔ euforia? | 100% — SON LA MISMA SEÑAL |
| 11 | ¿Qué métrica falta en medir_senal.py? | LIFT vs base rate condicionado por pivot_type |

---

## 6. LÍMITES DEL SCOPE

- ✅ **Ejecutar** verificaciones sobre el código existente sin modificarlo — solo lectura y medición
- ✅ **Proponer** el plan de culminación basado en datos verificados, no en opiniones
- ✅ **Verificar** cada afirmación contra el código fuente real — ninguna afirmación sin evidencia
- ✅ **Consultar** los casos de éxito (`.hermes/casodeexito/`) para replicar patrones; los casos de fracaso (`.hermes/casofracaso/`) para evitar errores
- ✅ **Emitir** la Confidence Card al inicio del reporte para decisión rápida
- ✅ **Conservar** el código en `research/` sin modificaciones — esto es auditoría, no implementación
- ✅ **Preservar** la estructura de directorios — entregables en `.hermes/reportes/` y `.hermes/plans/`
- ✅ **Respetar** el pipeline secuencial: el worker entrega primero, el auditor verifica después

---

## 7. CRITERIOS DE ACEPTACIÓN

- [ ] Worker entrega `plan_worker.json` con las 5 secciones completas (W1-W5)
- [ ] Auditor entrega `reporte_auditor.md` con Confidence Card + 4 secciones (A1-A5)
- [ ] Ambos agentes pasaron el AUTOTEST (11/11) antes de entregar
- [ ] El auditor encontró ≥3 hallazgos propios (no copiados del worker)
- [ ] El plan de culminación tiene máximo 8 ítems priorizados P1→P3
- [ ] El plan incluye explícitamente: lift en el arnés, señales a retirar, brecha SIGMET
- [ ] Ningún agente modificó archivos en `research/` (solo lectura y ejecución)

---

## 8. ENTREGABLES

| # | Agente | Entregable | Ubicación |
|---|--------|-----------|-----------|
| 1 | Worker | Plan en JSON | `.hermes/reportes/2026-08-20_plan_worker.json` |
| 2 | Auditor | Reporte + Confidence Card | `.hermes/reportes/2026-08-20_reporte_auditor.md` |
| 3 | Consolidado | Plan de culminación final | `.hermes/plans/plan-culminacion-20ago.md` |

---
**Firma:** deepseek/deepseek-v4-pro (Hermes) — construido para Juan Andrés
**Fecha:** 20-Ago-2026