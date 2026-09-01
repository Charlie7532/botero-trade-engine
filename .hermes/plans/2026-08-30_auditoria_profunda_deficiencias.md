# Auditoría Completa del Proyecto — Deficiencias para Prompt de Claude

> **Propósito:** Este documento es el estudio profundo que me pediste. Cada punto está verificado contra código, tests y datos reales. Úsalo para construir el prompt de Claude con información precisa.

---

## 1. RESUMEN EJECUTIVO

| Métrica | Valor |
|---|---|
| Servicios METAR existentes | ✅ 11/11 (VIX a DXY) |
| Endpoints REST existentes | ⚠️ 10/11 (falta DXY) |
| Tests de router METAR | ⚠️ 1 test (cubre 7/11 estaciones) |
| Tests de convergence | ❌ 0 |
| Tests de signals | ❌ 0 |
| Servicios de inteligencia (cascade, confluence, rarity, leadlag) | ❌ 0 (todo greenfield) |
| Frontend consume METAR | ❌ No existe (ni tab ni componente) |
| Frontend data layer | ✅ Vault-First (Neon directo, no FastAPI) |
| NOTAM completo vs docstring | ⚠️ 66% (2/3 checks implementados) |
| Clopper-Pearson en producción | ❌ Solo en research |
| D2 timing en producción | ❌ Solo en research |
| Total tests | ~48 archivos, 4,626 líneas |
| Tests convergence compositor | ❌ 0 |

---

## 2. DEFICIENCIAS POR CAPA

### 🔴 BACKEND — Servicios

| # | Deficiencia | Evidencia | Impacto |
|---|---|---|---|
| B1 | **DXY no tiene endpoint REST** | Router tiene 10 estaciones, servicio DXY existe pero `/api/metar/dxy` da 404 | Estación más ortogonal invisible para REST |
| B2 | **Ningún DTO expone overflow_tier** | Ninguno de los 27-28 fields de ningún servicio tiene `overflow_tier`. Solo exponen `sigma_depth` y `overflow_flag` raw | Frontend no puede mostrar T1-T5 |
| B3 | **Ningún DTO expone d2_direction** | `grep -r "d2_direction" backend/` → 0 resultados. Concepto solo en research | Frontend no sabe si el miedo está building o resolving |
| B4 | **Ningún DTO expone rarity (CI95, §3.3)** | Clopper-Pearson solo en `research/01_señales_entry_exit/arnes/estadisticas.py` | Frontend no sabe si un evento es diamante o ruido |
| B5 | **Convergence Compositor no tiene service propio** | Vive como función `compute()` en `convergence_compositor.py`, no como servicio inyectable | No hay tests, no hay mockeabilidad, no hay endpoint dedicado a cascade conviction |
| B6 | **NOTAM incompleto vs su propio contrato** | Docstring promete 3 checks, solo implementa 2. Falta: stale data >24h y FOMC blackout. El calendario FOMC existe en `macro_calendar.py` pero no está conectado | Operación ciega durante FOMC |
| B7 | **Cascade Conviction usa labels string obsoletos** | `D1_BEARISH_BINS` y `D1_BULLISH_BINS` comparan labels semánticos (ej. `"EXTREME_PANIC"`). Si algún adapter retorna state_key numérico, el voto direccional es siempre 0 | Bug silencioso en producción (ya identificado por Opus el 30-Ago) |

### 🟡 BACKEND — Tests

| # | Deficiencia | Evidencia |
|---|---|---|
| T1 | **Convergence compositor: 0 tests** | No existe `test_convergence_compositor.py` |
| T2 | **Router METAR: test incompleto** | `test_metar_router.py` aserta `registered_count == 10` (debe ser 11). Solo testea endpoints vix, vvix, pcr, fg, sv5, bsi + all. NO testea skew, credit, yield_curve, rotation, dxy individualmente |
| T3 | **NOTAM router: 1 test existente** | `test_notam_router.py` existe pero no cubre stale data ni FOMC |
| T4 | **Frontend: 0 tests** | No existen tests para los componentes de UI |
| T5 | **Router SIGMET: 1 test** | `test_sigmet_router.py` existe pero solo verifica happy path |

### 🟡 BACKEND — Research → Producción

| # | Concepto | Dónde está ahora | Lo que falta |
|---|---|---|---|
| R1 | **Confluencia vectorial** | Hallazgo empírico (sesión 29-Ago). Mapeo: N canales → WR | Servicio nuevo, no existe en backend |
| R2 | **Clopper-Pearson CI95** | `research/01_señales_entry_exit/arnes/estadisticas.py` | Migrar rule a `backend/modules/entry_decision/domain/rules/` |
| R3 | **D2 Timing (building/resolving)** | `research/04_conjuncion_multi_estacion/timing_derisking.py` | Crear `d2_timing_classifier(d2_bin, d2_velocity) → "building"|"resolving"|"stable"` |
| R4 | **Catálogo 31 señales medidas** | `research/01_señales_entry_exit/catalogo_31_senales_medidas.json` | Crear servicio lector en producción |
| R5 | **Validación OOS v7** | `data/research/signals/validacion_oos_catalogo_v7.json` | Crear servicio que evalúe bins actuales contra señales |
| R6 | **Lead-Lag matrix** | `backend/scripts/lead_lag_xlk_vs_qqq.py` (solo 2 ETFs) + `backend/scripts/build_zigzag_benchmark.py` | Servicio semanal multi-estación (11 station cross-correlation) |
| R7 | **Eras / Structural Breaks** | Concepto del usuario (GFC 2009-03-09) | JSON manual + service lector |

### 🔴 FRONTEND — Inexistencia de METAR

| # | Deficiencia | Evidencia |
|---|---|---|
| F1 | **No existe tab "Cockpit" o "METAR"** | Frontend tiene 4 tabs: Pulse, Mechanics, Rotation, Macro. Ninguno menciona METAR/SIGMET/NOTAM |
| F2 | **Frontend es Vault-First, no FastAPI-dependent** | `market.ts` L6-9: *"NO dependency on the FastAPI backend — the dashboard stays online even when the Python services are offline."* |
| F3 | **El data layer TS lee OHLCV directo de Neon** | `timescale.ts` usa `pg.Pool` contra POSTGRES_URL. No existe `fetch()` a FastAPI para datos de mercado |
| F4 | **Ningún componente TSX referencia METAR** | `grep -r "METAR\|metar\|SIGMET\|sigmet\|cascade\|convergence" src/` → 0 resultados en componentes |

### 🔴 DATOS — Pipeline y Consistencia

| # | Deficiencia | Evidencia |
|---|---|---|
| D1 | **5 de 11 estaciones no tienen tests de router individual** | skew, credit, yield_curve, rotation, dxy no tienen test de endpoint |
| D2 | **registered_count hardcodeado a 10 en test y router** | Router L238: `len(indicators)` que son 10. Test L74: `== 10`. DXY no está |
| D3 | **SIGMET usa 11 estaciones pero el test de router no lo verifica** | `test_sigmet_router.py` no testea que DXY genera SIGMETs |

---

## 3. MAPA DE LO QUE VS LO QUE DEBERÍA SER

### APIs Actuales

```
GET /api/metar/vix          ✅  (27 fields, sin tier/d2dir/rarity)
GET /api/metar/vvix         ✅  (idem)
GET /api/metar/pcr          ✅  (idem)
GET /api/metar/fg           ✅  (idem)
GET /api/metar/sv5-turbulence ✅ (idem)
GET /api/metar/skew         ✅  (idem, sin test de endpoint)
GET /api/metar/credit       ✅  (idem, sin test de endpoint)
GET /api/metar/yield-curve  ✅  (idem, sin test de endpoint)
GET /api/metar/rotation     ✅  (idem, sin test de endpoint)
GET /api/metar/bsi          ✅  (idem)
GET /api/metar/dxy          ❌  NO EXISTE (servicio sí, endpoint no)
GET /api/metar/all          ✅  10 estaciones (debe ser 11)
GET /api/metar/convergence  ✅  Sin DTO dedicado para cascade
GET /api/sigmet/active      ✅  Completo (incluye DXY)
GET /api/notam/incidents    ⚠️  Incompleto (falta stale + FOMC)
GET /api/notam/circuit-breaker ✅
```

### APIs que DEBERÍAN existir

```
GET /api/metar/{station}     ← + overflow_tier, d2_direction, rarity
GET /api/metar/all           ← 11 estaciones + confluence + panic_score
GET /api/metar/convergence   ← cascade dedicado + timing + taf_aggregate
GET /api/metar/overflow      ← NUEVO: confluence + tiers
GET /api/metar/leadlag       ← NUEVO: matriz multi-estación
GET /api/metar/era           ← NUEVO: structural breaks
GET /api/signals/active      ← NUEVO: 31 señales validadas OOS
```

### Frontend Actual

```
/portafolio/{slug}/market    ← 4 tabs, 0 METAR
  PulseTab                   ← SPY, VIX, Fear&Greed (datos Vault)
  MechanicsTab               ← GEX, MaxPain, Tide (datos Vault)
  RotationTab                ← Sectores, Breadth, RRG (datos Vault)
  MacroTab                   ← Yield curve, Earnings (datos Vault)
```

### Frontend que DEBERÍA tener

```
/portafolio/{slug}/market    ← 5 tabs (añadir Cockpit)
  PulseTab                   ← (existe)
  CockpitTab                 ← NUEVO: cascade gauge, confluence radar, matriz 11 estaciones
  MechanicsTab               ← (existe)
  RotationTab                ← (existe)
  MacroTab                   ← (existe)
TopBar (global)              ← SIGMET banner + NOTAM alerts (fetch a FastAPI)
```

---

## 4. COMPLEJIDAD DE IMPLEMENTACIÓN

| Tarea | Esfuerzo | Dependencias | Prioridad |
|---|---|---|---|
| Añadir `/api/metar/dxy` | 30 min | Ninguna | 🔴 P0 |
| Exponer overflow_tier en DTOs | 2h | Ninguna | 🔴 P0 |
| Crear d2_timing_classifier() | 4h | Migrar research | 🟡 P1 |
| Migrar Clopper-Pearson a producción | 4h | Mover rule | 🟡 P1 |
| Completar NOTAM (stale + FOMC) | 3h | macro_calendar.py existe | 🟡 P1 |
| Crear confluence_overflow_service | 6h | Greenfield | 🟡 P2 |
| Crear signals endpoint | 6h | JSON existe | 🟡 P2 |
| Crear lead_lag_service | 8h | Greenfield (solo script aislado) | 🟢 P3 |
| Crear era_service | 2h | JSON manual | 🟢 P3 |
| Tests: convergence compositor | 4h | Ninguna | 🟡 P1 |
| Tests: router endpoints faltantes | 2h | Ninguna | 🟡 P1 |
| Frontend: CockpitTab | 8h | APIs nuevas | 🟡 P2 |
| Decisión arquitectónica frontend | — | Vault-First vs Híbrido vs Proxy | 🔴 BLOQUEANTE |

---

## 5. DECISIONES PENDIENTES (OPEN QUESTIONS)

| # | Pregunta | Opciones | Recomendación |
|---|---|---|---|
| **Q1** | **¿Frontend consume METAR cómo?** | (A) Vault-First: clasificar en TS (B) FastAPI fetch (C) Híbrido: datos Vault, inteligencia FastAPI | **C** — datos crudos (OHLCV, valores actuales) desde Vault; cascade/confluence/signals desde FastAPI con degradación graceful |
| **Q2** | **¿Lead-lag en V1 o V2?** | V1: endpoint básico con matrix estática. V2: correlación dinámica intra-semanal | **V1 estática** — no cambia intraday, precomputar semanal |
| **Q3** | **¿Eras manual o algoritmo?** | Manual: JSON con fechas de structural breaks. Algoritmo: detection de breakpoints | **Manual V1** — algoritmo detection como V2 |
| **Q4** | **¿Señales activas auth?** | Internas (solo compositor) vs endpoint público | **Endpoint público V1** — pero sin datos de sizing, solo status (FIRED/STALK/SLEEPING) |

---

## 6. CÓMO USAR ESTE DOCUMENTO CON CLAUDE

1. Claude debe leer el archivo completo como contexto
2. Claude debe auditar CADA punto contra código (no asumir, como hizo Opus)
3. Claude debe identificar nuevos puntos ciegos (lo que yo también omití)
4. Claude debe proponer orden de implementación con justificación técnica
5. Claude DEBE verificar que `d1_directional_vote()` sigue funcionando con bins numéricos (bug identificado por Opus el 30-Ago)

---

## 7. FIRMA

**Auditor:** deepseek/deepseek-v4-flash + Opus meta-auditoría  
**Fecha:** 30-Ago-2026  
**Base:** Código real, tests, DTOs, AS-T, grep, investigación  
**Nota:** Cada afirmación está verificada contra archivos reales. Si Claude encuentra una contradicción, el error es mío y debe corregirlo.