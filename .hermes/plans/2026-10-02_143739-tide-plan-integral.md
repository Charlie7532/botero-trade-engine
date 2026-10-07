# Plan Integral — Tide: del rescate al rediseño

> **Plan (no ejecución).** Hoja de ruta de los dos carriles abiertos en Tide, con su orden, sus dependencias y su verificación.
> **Revisión de referencia:** `7a64cb2` (HEAD al 02-Oct-2026, 14:37).
> **Toda afirmación de estado aquí tiene su medición.** Lo que no se midió, se marca como pendiente.

---

## 0. GOAL

Continuar el subsistema **Tide** (Capa 3 del gate de calidad) desde donde quedó:
1. **Cerrar un bug vivo de producción** que el propio prompt de Recuperación detectó hace 4 días y sigue ahí.
2. **Poner al día el brief de diseño** (`2026-09-29-rediseno-ev-derived-escalas-adaptativas.md`) para que el rediseño del `ev_derived` arranque sobre un artefacto vigente.
3. **Ejecutar el Entregable 1 (diagnóstico)** que el prompt de Recuperación definió y que —hasta donde se verificó— no se ha producido.

**Tech stack:** Python · Neon PostgreSQL (TimescaleDataStore) · JSON de tablas (`rc_*` en `quality_swing/domain/rules/`) · Antigravity como ejecutor.

---

## 1. ESTADO VERIFICADO (lo analizado hoy)

| Hecho | Medición | Fuente |
|---|---|---|
| **E0 (rescate de hilos) Entregado** | `docs/modules/quality_swing/tide/THREAD_RESCUE_dda7ae62_68bcd487.md` (7.180 B, 28-Sep) + `CHANGELOG.md` (290 líneas) | verificado en disco |
| **El prompt de Recuperación sigue exacto en su núcleo** | Su autotest: 4/4 coinciden (245 estados · test ausente · L280/653 · dataclass sin campo) | ejecutado |
| **🔴 El bug `fatigue_type` SIGUE VIVO** | `swing_gate.py`: L280 y L653 usan `_real_ev.fatigue_type`; `RealEVSignal` no tiene ese campo | ejecutado |
| **El brief de diseño está desactualizado en 2 cifras** | dice `channel_snapshots`: 213.100 / 72 col → hoy **4.594.499 / 79** | medido |
| **El brief NO depende de lo retirado** | 0 menciones de `trade_count`, `VF_`, `Alpaca`; sus rutas citadas existen 3/3 | medido |
| **La evaluación del guidance de revisión** | 12.881 B · sólida · 5 hallazgos reales (H1-H5) + 3 ajustes (A1-A3) | verificado |
| **Carril `vwap`/`trade_count`: CERRADO** | 6 commits (`31e4f03`→`7a64cb2`), árbol limpio, rastro barrido | verificado |

**No reabrir el carril cerrado.** No tiene dependencia con nada de este plan.

---

## 2. LOS DOS CARRILES

### CARRIL A — 🔴 El bug `fatigue_type` (producción · alta severidad · bajo costo)
**Por qué primero:** está vivo en producción, rompe una alerta y puede lanzar `AttributeError` en la rama de decisión. Es aislado y no depende de nada del diseño.

### CARRIL B — 🎯 El rediseño de Tide (el trabajo de fondo)
**Por qué después:** es el objetivo de fondo, pero arranca sobre un artefacto que hay que poner al día, y su fase de diagnóstico (E1) aún no se ha producido.

---

## 3. FASES

### FASE 0 — Cerrar el bug `fatigue_type` (Carril A)
**Guidance:** `.hermes/prompts/2026-10-02-guidance-bug-fatigue-type.md`
**Dependencias:** ninguna.
**Criterio de cierre:** el hallazgo queda confirmado o refutado **con ejecución**, las opciones de arreglo están presentadas **con su trade-off y sin decidir**, y existe una prueba que impide la regresión.

| Paso | Acción | Verificación |
|---|---|---|
| 0.1 | Reproducir el fallo **ejecutando** (importar `RealEVSignal`, disparar L653) | `archivo:línea` + comando + output real |
| 0.2 | Determinar si la rama REAL_EV se emite alguna vez hoy | conteo de alertas REAL_EV en una corrida de `swing_gate` |
| 0.3 | Presentar las opciones de arreglo (añadir el campo vs retirar las referencias vs derivarlo) con su semántica y su costo | tabla de opciones — **a adjudicar por el arquitecto** |
| 0.4 | Ejecutar la opción aprobada + prueba de contrato del DTO | test que falla si un `*Signal` se usa con un campo inexistente |
| 0.5 | Verificación end-to-end: alerta REAL_EV emitida · rama TRIM sin excepción | corrida + evidencia |

### FASE 1 — Poner al día el brief de diseño (Carril B)
**Guidance:** `.hermes/prompts/2026-10-02-guidance-revision-prompt-tide.md` (ya escrito y evaluado)
**Dependencias:** ninguna (independiente de la Fase 0).
**Criterio de cierre:** el entregable 7.4 del guidance responde **"¿el prompt sigue siendo ejecutable?"** con los puntos exactos que lo bloquean (si los hay), y las correcciones quedan **redactadas y listas, en aditivo**.

| Paso | Acción | Verificación |
|---|---|---|
| 1.1 | Ejecutar el guidance de revisión (§0-§7) | tabla de revisión completa |
| 1.2 | Corregir las 2 cifras obsoletas (snapshots/columnas) | nota aditiva fechada |
| 1.3 | Re-anclar la baseline de revisión (`7a64cb2`) | nota aditiva |
| 1.4 | Re-verificar el **Registro Canónico de Dimensiones** contra los JSON de hoy | hallazgo principal esperado |
| 1.5 | Incorporar los hallazgos H1-H5 de la evaluación (line drift, docstring pre-fix, IC sin archivo, census, profiles) | cada uno con su nota |

### FASE 2 — Entregable 1: DIAGNÓSTICO DE ALINEACIÓN (Carril B)
**Guidance:** a redactar tras la Fase 1 (el brief actualizado es su entrada).
**Dependencias:** Fase 1.
**Alcance (definido por el prompt de Recuperación §5.1):**
- Cross-audit `docs ↔ código ↔ data` — empezando por **180 vs 245 estados L3**.
- Confirmar/refutar el bug de contrato (si la Fase 0 no lo cerró).
- Plan ordenado TASK 1 → 2 → 3 con dependencias y riesgos.
- Propuesta de **"cuadrar los regímenes"** con definición operativa.
**Criterio de cierre:** diagnóstico separado del plan de fixes; cada hallazgo con `archivo:línea` + reproducción + severidad + si es latente o activo hoy.

### FASE 3 — TASKs de construcción (Carril B)
**Dependencias:** Fase 2 aprobada. **No se arranca sin el diagnóstico.**
- **TASK 1** — Unificación de taxonomía (6-level JSON ↔ 3-bin DB).
- **TASK 2** — Duración dinámica (`e_days`, `ev_per_day`).
- **TASK 3** — Benchmark forense escalado (10 → 366+ tickers).
*(Cada una merece su propio plan detallado cuando llegue el momento — no se detalla aquí para no adelantar diseño.)*

---

## 4. ARCHIVOS QUE SE TOCAN (por fase)

| Fase | Archivos |
|---|---|
| **0** | `backend/modules/quality_swing/application/use_cases/swing_gate.py` (L280, L653) · `backend/modules/quality_swing/domain/rules/rc_tide_ev_lookup.py` (`RealEVSignal`) · **crear** el test de contrato |
| **1** | `.hermes/prompts/2026-09-29-rediseno-ev-derived-escalas-adaptativas.md` (**solo aditivo**) |
| **2** | ninguno — diagnóstico de solo lectura |
| **3** | según el diseño aprobado |

---

## 5. VALIDACIÓN POR FASE

| Fase | Prueba | Criterio |
|---|---|---|
| **0** | ejecución real del camino L653 + corrida de `swing_gate` | no hay `AttributeError` · la alerta REAL_EV se emite · test de contrato en verde |
| **1** | re-ejecutar el autotest del prompt de Recuperación (§8) | 5/5 siguen coincidiendo **o** el delta queda declarado |
| **2** | reproducibilidad: cada hallazgo con comando + output | ningún hallazgo "de lectura" |
| **3** | (se define con el diseño) | — |

---

## 6. RIESGOS Y PREGUNTAS ABIERTAS

| # | Riesgo / pregunta | Mitigación |
|---|---|---|
| **R1** | El bug `fatigue_type` puede tener **más de un consumidor** además de `swing_gate` | barrer por familia: `grep` de `fatigue_type` en todo el módulo antes de tocar |
| **R2** | Arreglar el campo **cambia el comportamiento** del gate TRIM (hoy la excepción aborta la rama) | presentar como decisión, no como fix mecánico |
| **R3** | La Fase 1 puede destapar que el brief **no es ejecutable** tal como está | el entregable 7.4 lo responde explícitamente |
| **R4** | Mezclar Carril A y B en una misma sesión | carriles separados y **sesiones separadas** si el contexto se alarga (la sesión previa se truncó 2 veces) |
| **Q1** | ¿El rediseño del `ev_derived` debe esperar a la unificación de taxonomía (TASK 1)? | a decidir en Fase 2 |
| **Q2** | ¿Se conserva el JSON 6-level como fallback offline al conectar el EV al Vault? | pregunta abierta del prompt, sin resolver |

---

## 7. PENDIENTES DECLARADOS (no entran en este plan)

- **Los 2 parquets de preservación** (`vwap` / `trade_count`): borrados el 02-Oct; la tabla `ohlcv_bars_backup_20260529` conserva 2.523 valores reales de ambas columnas (decisión del arquitecto: se queda).
- **El test guardián de rutas** (de los manifiestos JSON): propuesto, no implementado.
- **Las 3 menciones cosméticas** de `vwap`/`trade_count`: cerradas en `7a64cb2` ✓.

---

*Nota de método: este plan no ejecuta nada. Cada fase tiene su guidance. La Fase 0 tiene el suyo escrito; la Fase 1 también (y ya fue evaluada por el ejecutor); las Fases 2 y 3 lo tendrán cuando sus entradas estén listas.*
