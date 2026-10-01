# PROMPT DE CONTEXTO — REANUDAR TIDE (Quality Swing)

**Destino:** agente ejecutor (Antigravity: Gemini / Claude guiada)
**Fecha:** 2026-09-28
**Preparado por:** Hermes (guiar / auditar / construir prompts — NO programar)
**Uso:** pegar como **PRIMER mensaje de un hilo NUEVO**. Sustituye al hilo origen, que se truncó (había arrancado con una directiva `/`).
**Hilos origen (referencia histórica):** `dda7ae62-58b2-44b8-adf4-6d8b6e16bd19` («Modelo EV Real & Puerta Confluencia Dual (P(bull) × EV)») y `68bcd487-aebf-4bc0-8e5a-c2301a19c8ba` («Swing EV Decision Engine»).

---

## 0. PROPÓSITO

Inyectar la memoria completa del subsistema **Tide** para continuarlo sin perder contexto. **Antes de escribir una sola línea, lee los archivos de referencia (§2).** La meta de la etapa es **cuadrar los regímenes de Tide** y ejecutar el trabajo abierto (§4). **Entregable 0 = rescate de los hilos → `.md` de memoria; Entregable 1 = diagnóstico (no código)** (§5).

---

## 1. QUÉ ES TIDE (arquitectura, verificado)

- **Tide = el gate de calidad/"swing"** (`backend/modules/quality_swing/`) = **Capa 3 (Entry Gate → directivas `STK_*`)** de la arquitectura de **3 niveles**. Decide el *cuándo* táctico (acumular / trim) sobre lo que Quality Core ya aprobó. **No decide QUÉ comprar.**
- **Modelo físico — Regression Channel de 3 escalas:**
  `Tide` (regresión 240 barras — tendencia estructural, meses) × `Current` (60 barras — momentum, semanas) × `σVw` (posición del precio en el canal VWAP, en σ — intra-ciclo, días).
  **Estado = `{Tide}|{Current}|{σVw}`** (ej. `T+++|C---|>`).
- **Dos granularidades coexistentes** (ver TAXONOMY MISMATCH, §4 TASK 1):
  - **Producción 3-bin:** `T+/T0/T−` × `C+/C0/C−` × 5 bins σVw = **45 estados** (DB `engine.ticker_fact_states`).
  - **Research 6-level:** `T+++…T−−−` × `C+++…C−−−` × 5 bins = **180 estados** (`rc_tide_derived.json`).
- **Modelo de Valor Esperado (EV):** `E[R|S_t]` (retorno real punto-en-tiempo, **sin "retorno fantasma"**: `R = Price(P_next)/Close(t) − 1`), `L0` baseline incondicional (nulo), `Ω = 1/σ²` (certidumbre), `Kelly f*` (half-Kelly per-ticker), `e_days` (duración dinámica al próximo pivote ZigZag), `EV_per_day` (velocidad de capital), `RR_asym` (asimetría up/down).
- **Cadena de datos (Vault-First):** Neon `market.ohlcv_bars` → `engine.channel_snapshots` (213.100 snapshots clasificados, 72 columnas) → `generate_per_ticker_fact_tables.py` → `engine.ticker_fact_states` + `engine.ticker_fact_baselines` → `rc_swing_ev_decision_engine.py`.
- **Regla de arquitectura (17-Sep):** las estaciones/gates emiten **HECHOS** (`p_bull`, `ev`, `n`), **nunca directivas** dentro del store de hechos; la estrategia final la determina el **régimen (nivel 3)**.
- **Gates duros validados:** `VIX Circuit Breaker` (VIX ≥ 28.0 AND T < −0.05 → `EXIT_CRISIS`; VIX se quitó como dimensión de estado, quedó como gate) y `Trend Protection Gate` (bloquea HARVEST en bull secular `t_slope ≥ 0.05` salvo `σVw ≥ 1.50`, por "Buyback Slippage").

---

## 2. ARCHIVOS DE REFERENCIA (leer antes de escribir)

| Archivo | Rol | Prioridad |
|---|---|:---:|
| `docs/modules/quality_swing/tide/README.md` | **Memoria maestra de diseño** (glosario, física, arquitectura, ground-truth, decision log, open work) | 🔴 OBLIGATORIO |
| `docs/modules/quality_swing/tide/IO_SPEC.md` | I/O de cada componente + auditoría de utilización de datos | 🔴 OBLIGATORIO |
| `docs/modules/quality_swing/tide/LOOKUP_SPEC.md` | Spec de `rc_tide_lookup.py` + `rc_tide_ev_lookup.py` | 🔴 OBLIGATORIO |
| `docs/modules/quality_swing/tide/REAL_EV_LOOKUP_SPEC.md` | Spec del motor Real EV | 🟠 |
| `docs/modules/quality_swing/tide/SLOPE_CLASSIFIER_SPEC.md` | Spec de `rc_slope_classifier.py` | 🟠 |
| `docs/modules/quality_swing/tide/CHANGELOG.md` · `PROPOSALS.md` | Diálogo de diseño + propuestas abiertas | 🟠 |
| `backend/modules/quality_swing/domain/rules/rc_tide_lookup.py` | Lookup T×C×σVw (→ `TideSignal`) | 🔴 |
| `backend/modules/quality_swing/domain/rules/rc_tide_ev_lookup.py` | Motor Real EV L3→L2→L1→L0 (→ `RealEVSignal`) | 🔴 |
| `backend/modules/quality_swing/domain/rules/rc_slope_classifier.py` | Clasificador de slopes (6-level, normalizado por ATR) | 🔴 |
| `backend/modules/quality_swing/application/use_cases/swing_gate.py` | **Orquestador de producción** (arma las alertas) | 🔴 |
| `backend/modules/quality_swing/domain/entities/tide_route_guidance.py` | DTO `TideRouteGuidance` (hazard/urgency/`STK_T_*`) | 🟠 |
| `backend/modules/quality_swing/domain/rules/rc_tide_derived.json` · `rc_tide_ev_derived.json` | Tablas de datos | 🔴 |
| `backend/scripts/generators/generate_tide_ev_real_derived.py` | Generador de `rc_tide_ev_derived.json` | 🟠 |

> ⚠️ Estas `.md` fueron **recuperadas de la historia de git** (habían quedado en 0 bytes por los commits `65917ba` y `9ee684f`). Si un doc y el código discrepan, **manda el código/dato** (dato mata relato).

---

## 3. ESTADO ACTUAL VERIFICADO (25-Sep-2026 — ejecutado, no inferido)

**Ruta de producción real:** `swing_gate.py` orquesta por-ticker y arma alertas: `TIDE[state_key]` (vía `rc_tide_lookup`→`TideSignal`), `REAL_EV[...]` (vía `rc_tide_ev_lookup`→`RealEVSignal`), `WAVE`, `MULTISCALE_EV`, `WAVE_EV`, más `HSA_GATEKEEPER`, FG (`MH_FG_*`), `UW_IV_RANK`.

1. 🔴 **BUG LATENTE VIVO — desajuste de DTO `fatigue_type`:**
   `swing_gate.py` lee `_real_ev.fatigue_type` en **L280** (alerta REAL_EV) y **L653** (gate de decisión de la rama TRIM: `if _real_ev and (_real_ev.ev <= -0.0020 or _real_ev.fatigue_type == "FATIGUE_RISK")`).
   Pero **`RealEVSignal` NO tiene `fatigue_type`** (verificado importando el dataclass).
   Efecto: (a) la alerta `REAL_EV` **nunca se emite** (el `try/except` la traga); (b) en la rama TRIM, cuando `_real_ev.ev > -0.0020`, **L653 lanza `AttributeError`**.
   Nota: `RealWaveEVSignal` (usado en L330) **sí** tiene `fatigue_type` → esa línea está sana. El problema es solo `_real_ev`.
   *(Es la misma familia de bug que rompía 4 tests en ago-2026: `hazard_alarm` en `RealEVSignal`.)*
2. ⚠️ **DTO nuevo sin cablear:** `tide_route_guidance.py` (`TideRouteGuidance` con `hazard_alarm`, códigos `STK_T_*`, `URGENCY_*`, `HAZARD_*`) es **aspiracional** — solo lo importan scripts de train/eval, **ningún módulo de producción**.
3. ⚠️ **Test desaparecido:** `test_tide_guidance.py` **ya no existe** en el repo (solo el `.pyc`); `git log --all` no registra commit. La suite **no protege** esta clase de error de contrato de DTO.
4. 📊 **Tablas vs doc (drift):** `rc_tide_ev_derived.json` tiene **245 L3 / 49 L2 / 7 L1 / 8 L0**; el `README` v1.0 declara **180 L3**. `rc_tide_derived.json` = 180 estados.
5. 📉 **I/O subutilizado:** el pipeline Tide usa **3 de 72 columnas (4.2%)** de `engine.channel_snapshots`; señales ya persistidas (RSI Intelligence, Kalman Velocity, Wave Duration) **no se consumen**.

---

## 4. TRABAJO ABIERTO (del `README` §6 — Decision Log D-007/008/009/013)

- **TASK 1 — Unificación de Taxonomía.** `rc_tide_ev_lookup.py` lee JSON 6-level (`T+++|C---|>`); `rc_swing_ev_decision_engine.py` lee DB 3-bin (`T+|C-|>`). Conectar el lookup EV al Vault (`TimescaleDataStore`) + normalizar 6-level→3-bin, manteniendo compatibilidad. *(Preguntas abiertas: ¿deprecar el JSON o conservarlo como fallback offline? ¿se necesita el 6-level en la DB?)*
- **TASK 2 — Duración dinámica.** Añadir `e_days` y `ev_per_day` a `engine.ticker_fact_states` (hoy fijo `lookforward_days=20`); el motor usa `ev_per_day` para Kelly; Time Stop = `1.5 × e_days(S_t)`. *(Preguntas: ¿ZigZag 5% o 2.5%? ¿Time Stop duro o blando?)*
- **TASK 3 — Benchmark forense escalado.** `eval_swing_forensic_benchmark.py` en 10 → 366+ tickers; Δ shares vs Buy & Hold, accuracy por señal, calibración Markov.

---

## 5. PUNTO DE INICIO — DOS ENTREGABLES (primero rescate, luego diagnóstico; NO construir aún)

### 5.0. ENTREGABLE 0 — RESCATE DE LOS HILOS → `.md` de memoria  🔴 PRIMERO

Antes de diagnosticar nada, **levanta TODO el texto de los hilos de trabajo** y consolídalo en un `.md` de memoria (esto ya se hizo antes en este proyecto; es el patrón de rescate de hilo).

**Fuentes a levantar (léelas directo, no pidas que te las peguen):**
- Conversaciones (SQLite): `/root/.gemini/antigravity-ide/conversations/<id>.db`, tabla `steps`.
  - Semántica de `step_type`: `14`=mensaje usuario · `5`=write_to_file (el edit real, con el contenido completo) · `15`=mensaje del modelo (narración) · `21/7/8`=tool_call (`run_command`/`grep`/`view_file`) · `101`=fin del task.
  - Hilos de trabajo: `dda7ae62-58b2-44b8-adf4-6d8b6e16bd19` («Modelo EV Real & Puerta Confluencia Dual») y `68bcd487-aebf-4bc0-8e5a-c2301a19c8ba` («Swing EV Decision Engine»).
  - Extraer: mensajes de usuario (`14`), narración del modelo (`15`) y los `write_to_file` (`5`) de archivos `*tide*`/`rc_ev*`/`rc_tide*`.
- Artefactos del brain: `/root/.gemini/antigravity-ide/brain/<id>/*.md` (ya existentes: `implementation_plan.md`, `walkthrough.md`, `audit_*.md`, `tide_macro_regime_standard.md`, `wave_triad_audited_schema.md`, `bayesian_tide_vwap_architectural_debate.md`, `mathematical_expectation_manifesto.md`, `scientific_fact_tables_and_heaven_hell_bifurcation.md`).
- Los `.md` de diseño ya recuperados: `docs/modules/quality_swing/tide/*.md`.

**Salida del Entregable 0:**
1. Un `.md` consolidado de memoria, p.ej. `docs/modules/quality_swing/tide/THREAD_RESCUE_dda7ae62_68bcd487.md`, con: **decisiones de diseño**, **hipótesis validadas/refutadas**, **conceptos clave**, **tareas pendientes**, y las **citas textuales** del Arquitecto que las originaron (marca cada hallazgo con su status: VALIDADO / HIPÓTESIS / PENDIENTE).
2. **Integrar** el resumen cronológico en `docs/modules/quality_swing/tide/CHANGELOG.md` (es su rol: "chronological record of every design discussion, experiment, and decision").

> Si algún `.md` de diseño está vacío/truncado, **repórtalo** y recupéralo de la historia de git (`git show 9ee684f^:docs/tide/<archivo>`) — no lo dejes en blanco.

### 5.1. ENTREGABLE 1 — DIAGNÓSTICO DE ALINEACIÓN (sin tocar código de producción)

1. **Cross-audit `docs` ↔ `código` ↔ `data`:** lista de todo drift (empezando por 180 vs 245 estados L3; verifica cada enum/label y lista de campos del README contra los JSON/generadores reales).
2. **Confirmar o refutar el bug `fatigue_type`** ejecutando (no leyendo): importar el dataclass y reproducir el fallo de L280/L653. Reporta `archivo:línea` + comando + output real.
3. **Plan ordenado TASK 1 → 2 → 3** con dependencias, criterios de aceptación y riesgo por tarea.
4. **Propuesta concreta de "cuadrar los regímenes" en Tide:** qué se entiende por régimen aquí (¿el vector `T×C×σVw`? ¿la transición Markov? ¿los Tiers del nivel 3?), dónde vive, y cómo se calibra/valida contra el ground-truth (ground-truth = resultado real del mercado vía ZigZag first-passage).

---

## 6. LÍMITES DEL SCOPE

- ✅ **Aislar** el diagnóstico en `backend/modules/quality_swing/` — no tocar frontend ni APIs.
- ✅ **Proteger** los `*_lookup.py`, `rc_slope_classifier.py` y los JSON de tablas: **solo lectura** durante esta etapa de diagnóstico.
- ✅ **Respetar** las tablas generadas tal como están — diagnosticar sobre el artefacto, no regenerar.
- ✅ **Conservar** la separación viejo (JSON 6-level, research) / nuevo (DB 3-bin, producción) en cada conclusión.
- ✅ **Ejecutar** comandos reales para cada hallazgo (verificar ≠ inferir).
- ✅ **Reportar** la tabla completa, no solo la mejor celda. Estados con N bajo = **diamantes** (§3.3), se listan y estudian, **no se descartan**.

---

## 7. CRITERIO DE ACEPTACIÓN (completo cuando:)

- [ ] **(E0)** Existe el `.md` de rescate de los hilos (decisiones, hipótesis validadas/refutadas, pendientes, citas del Arquitecto) y el resumen quedó integrado en `CHANGELOG.md`.
- [ ] Cada hallazgo trae `archivo:línea` + comando de reproducción + output real + severidad + si es **latente** o **activo hoy**.
- [ ] El entregable separa **DIAGNÓSTICO** (bloque 1) de **FIXES/PLAN PROPUESTOS** (bloque 2, sin aplicar).
- [ ] Tabla de drift doc↔código↔data completa.
- [ ] Bug `fatigue_type` confirmado/refutado con evidencia de ejecución.
- [ ] Plan TASK 1-3 priorizado con dependencias.
- [ ] Propuesta de "cuadrar regímenes" con definición operativa.

---

## 8. AUTOTEST (obligatorio — ejecutar antes de responder; respuestas ya validadas contra el repo)

1. `'fatigue_type' in RealEVSignal.__dataclass_fields__` → **False** (no lo tiene → bug activo).
2. `'fatigue_type' in RealWaveEVSignal.__dataclass_fields__` → **True** (L330 sana).
3. `len(rc_tide_ev_derived.json["l3_full_state"])` → **245** (no 180 como dice el README → drift).
4. `test_tide_guidance.py` presente en el repo → **NO** (solo `.pyc`).
5. `grep -n "_real_ev.fatigue_type" swing_gate.py` → líneas **280 y 653**.

Si alguna respuesta NO coincide, **detente y corrige la lectura antes de continuar** — un valor distinto puede ser dato nuevo; repórtalo, no lo ignores.

---

## 9. ENTREGABLE

1. **(E0)** El `.md` de memoria del rescate de los hilos + el resumen integrado en `CHANGELOG.md` (§5.0).
2. **(E1)** Reporte markdown, numerado, con `DIAGNÓSTICO` y `PLAN PROPUESTO` separados. **No apliques cambios de código.** Termina con una recomendación priorizada (qué atacar primero y por qué) y la definición operativa de "cuadrar los regímenes" de Tide.
