# Tide System — Open Proposals

> **Purpose:** Active proposals under discussion. Each proposal has a status,
> a clear problem statement, proposed solutions with tradeoffs, and open questions
> for the System Architect. Once resolved, proposals move to the
> [Changelog](./CHANGELOG.md) and the [Decision Log](./README.md#5-decision-log-change-control).

---

## Proposal Index

| ID | Title | Status | Priority |
|:---:|---|:---:|:---:|
| P-001 | [Taxonomy Unification](#p-001-taxonomy-unification) | 🔴 Superseded | — |
| P-002 | [Dynamic Duration & Capital Velocity](#p-002-dynamic-duration--capital-velocity) | 🟡 Under Review | HIGH |
| P-003 | [Scaled Forensic Benchmark](#p-003-scaled-forensic-benchmark) | 🟢 Approved Concept | MEDIUM |
| P-004 | [Deprecation of JSON Lookup Path](#p-004-deprecation-of-json-lookup-path) | 🔴 Rejected (JSON is Operational) | — |
| P-005 | [Nuevo Planteamiento Fact Generation (Coincidencia T/W/VWAP)](#p-005-nuevo-planteamiento-fact-generation) | 🟡 PENDIENTE CRÍTICO | HIGH |
| P-006 | [Respaldo en DB de JSONs y Política de Fallback sobre Respaldo](#p-006-respaldo-en-db-de-jsons-y-politica-de-fallback-sobre-respaldo) | 🟡 PENDIENTE CRÍTICO | HIGH |
| P-007 | [Persistencia de Columnas Clasificadas en ChannelSnapshots](#p-007-persistencia-de-columnas-clasificadas-en-channelsnapshots) | 🟢 APROBADO ARQUITECTURA | HIGH |
| P-008 | [Heterogeneidad de Historial por Ticker](#p-008-heterogeneidad-de-historial-por-ticker) | 🟡 PENDIENTE (anotado 30-Sep) | HIGH |
| P-009 | [Registro, Interpretación y Excepción de Overflow / Blowoff](#p-009-registro-interpretacion-y-excepcion-de-overflow--blowoff) | 🟡 PENDIENTE (anotado 30-Sep) | HIGH |
| P-010 | [Migración de Hallazgos Existentes a las Nuevas Escalas/Formatos](#p-010-migracion-de-hallazgos-existentes-a-las-nuevas-escalasformatos) | 🟡 PENDIENTE (anotado 30-Sep) | HIGH |
| **P0** | [Bug `p_bull` cruzado (bloquea todo Tide)](#p0-bug-p_bull-cruzado-bloqueante) | 🟢 RESUELTO (2026-09-30) | RESOLVED |

---

## P-001: Taxonomy Unification

**Status:** 🟡 Ready for Review
**Priority:** HIGH — blocks production deployment of `rc_tide_ev_lookup.py`
**Decision IDs:** D-010

### Problem

Two lookup modules exist in `quality_swing/domain/rules/`:

| Module | Data Source | Key Format | Example Key |
|---|---|---|---|
| `rc_swing_ev_decision_engine.py` | Neon PostgreSQL (`engine.ticker_fact_states`) | 3-bin | `T+\|C-\|<<` |
| `rc_tide_ev_lookup.py` | `rc_tide_ev_derived.json` | 6-level | `T+++\|C---\|>` |

The decision engine is Vault-First (Rule 13 compliant). The EV lookup is JSON-based (Rule 13 violation).

Callers that use `rc_tide_ev_lookup.lookup_real_ev()` cannot benefit from per-ticker fact tables, and any updates to the DB data are invisible to them.

### Proposed Solution

**Option A — Full Migration (Recommended):**
1. Modify `rc_tide_ev_lookup.py` to query `engine.ticker_fact_states` via `TimescaleDataStore`.
2. Add key normalization: `T+++/T++/T+` → `T+`, `C---/C--/C-` → `C-`, etc.
3. Return the same `RealEVSignal` dataclass — zero breaking changes for callers.
4. JSON file becomes offline research artifact, not production dependency.

**Option B — Adapter Bridge:**
1. Keep `rc_tide_ev_lookup.py` reading JSON.
2. Create a thin adapter that queries DB and converts to the same output format.
3. Caller decides which backend to use.

### Tradeoffs

| Aspect | Option A | Option B |
|---|---|---|
| Rule 13 compliance | ✅ Full | ⚠️ Partial (JSON path remains) |
| Code complexity | Lower (single path) | Higher (two paths) |
| Per-ticker data | ✅ Available | ❌ JSON is cross-ticker |
| Offline research | ⚠️ Need separate script | ✅ JSON still works |

### Open Questions for Architect

1. **Do any callers of `rc_tide_ev_lookup.lookup_real_ev()` require 6-level granularity** (e.g., distinguishing `T+++` from `T+`)? If not, Option A is strictly superior.
2. **The `lookup_tide_guidance()` function** in the same module references hazard alarms and Waze-style routing. Should this function also migrate to DB, or is it a separate concern?
3. **The `rc_tide_lookup.py` module** (non-EV, signal-only) — does it also need migration, or is it a research-only tool?

---

## P-002: Dynamic Duration & Capital Velocity

**Status:** 🟡 Ready for Review
**Priority:** HIGH — proven concept, pending implementation
**Decision IDs:** D-007, D-008, D-009

### Problem

The fact table generator uses `lookforward_days = 20` as a fixed horizon for computing E[R|S_t]. This implies every state has the same expected holding period, which is empirically false.

The `audit_dynamic_duration_practicability.py` script validated that ZigZag 5% pivot distances vary from 5 to 40+ days depending on state and ticker.

### Proposed Changes

#### Part A: Schema Extension

```sql
ALTER TABLE engine.ticker_fact_states
ADD COLUMN IF NOT EXISTS e_days DOUBLE PRECISION DEFAULT 20.0,
ADD COLUMN IF NOT EXISTS ev_per_day DOUBLE PRECISION DEFAULT 0.0;
```

#### Part B: Generator Update (`generate_per_ticker_fact_tables.py`)

1. Compute ZigZag 5% pivot points for the ticker (reuse `_compute_zigzag_pivots()` from audit script).
2. For each bar in a given state, record the distance (in days) to the next ZigZag pivot.
3. Aggregate: `e_days(state) = mean(days_to_next_pivot)` for bars in that state.
4. Compute: `ev_per_day = ev_net / max(e_days, 1.0)`.
5. INSERT into DB alongside existing columns.

#### Part C: Decision Engine Update (`rc_swing_ev_decision_engine.py`)

1. Add `e_days` and `ev_per_day` to `EVLookupResult` dataclass.
2. Update SQL query in `_load_ticker_table()` to select the new columns.
3. Kelly sizing modulation: weight by `ev_per_day` instead of raw `ev_net`.
4. Time Stop: position expires at `1.5 × e_days(S_t)` bars (dynamic).

### Open Questions for Architect

1. **ZigZag deviation threshold:** 5% (structural, fewer pivots, longer durations) or 2.5% (tactical, more pivots, shorter durations)? The audit used 5%.
2. **Time Stop behavior at expiry:** Hard exit (sell 100%) or soft degradation (reduce sizing by 50% per half-life)?
3. **Backward compatibility:** If `e_days` is NULL in DB (existing rows), should the engine fall back to 20 days? (Proposed: yes, using `COALESCE(e_days, 20.0)` in SQL.)
4. **Should `ev_per_day` replace `ev_net` in the HARVEST/ACCUMULATE thresholds**, or should both be considered? Proposed: `ev_per_day` for sizing, `ev_net` for direction.

---

## P-003: Scaled Forensic Benchmark

**Status:** 🟢 Approved Concept — execution pending Task 1 & 2 completion
**Priority:** MEDIUM

### Scope

1. **Phase 1 (10 tickers):** AAPL, MSFT, WMT, COST, JNJ, SPY, QQQ, HD, JPM, XOM
   - Full forensic report per ticker: Δ shares vs B&H, per-signal accuracy, Markov calibration.
2. **Phase 2 (366+ tickers):** Full Vault universe.
   - Aggregate statistics: median Δ shares, distribution, worst-case tickers.
   - Identify tickers where the engine underperforms B&H (analysis targets).

### Dependencies

- P-001 (Taxonomy Unification): not strictly required, but recommended for consistency.
- P-002 (Dynamic Duration): ideally integrated before the scaled run to avoid re-running.

### No Open Questions

The benchmark script (`eval_swing_forensic_benchmark.py`) already exists and is functional. The only decision is sequencing relative to P-001 and P-002.

---

---

## P-004: Deprecation of JSON Lookup Path

**Status:** 🔴 Rejected (JSON is Operational Standard)
**Priority:** —

### Decision Directive (2026-07-28)

- The JSON lookup path (`rc_tide_derived.json`, `rc_tide_probability_table.json`, `rc_tide_ev_derived.json`) remains the **operational standard**.
- Deprecation is rejected. All research/operational lookup functions MUST read from these verified JSON structures without hardcoded fallbacks.

---

## P-005: Nuevo Planteamiento Fact Generation (Coincidencia T/W/VWAP)

**Status:** 🟡 PENDIENTE CRÍTICO
**Priority:** HIGH — Reemplaza el generador previo de 3 bins

### Contexto y Decisión Directa

El script legacy `generate_per_ticker_fact_tables.py` utilizaba cortes de pendiente rígidos en 3 bins (`T+`/`T0`/`T-` en `±0.05`) sin normalizar por volatilidad. **Esta aproximación ha sido desconectada y rechazada.**

Los asuntos de las pendientes y regímenes de activos heterogéneos no pueden resolverse con un corte plano universal.

### Planteamiento del Nuevo Modelo (Pendiente a Elaborar)

1. **Mapa de Coincidencias Cuánticas T, W, VWAP:**
   - Correr la triada $T, W, \sigma_{VWAP}$ a lo largo de las series de tiempo.
   - Construir un mapa espectral de coincidencia estocástica y giros de fase.
2. **Entrenamiento de Clasificadores Especificados por Tipo de Activo:**
   - Evaluar si se requieren instancias o cuantiles adaptativos de `rc_slope_classifier.py` por clase de activo (Mega Cap Tech vs Consumer Staples vs High Beta).
3. **Desconexión del Generador Previo:**
   - `generate_per_ticker_fact_tables.py` genera `RuntimeError` si se ejecuta.
   - La operación del motor se sostiene sobre la fuente estandarizada `rc_tide_derived.json` y `rc_tide_probability_table.json`.

---

## P-006: Respaldo en DB de JSONs y Política de Fallback sobre Respaldo

**Status:** 🟡 PENDIENTE CRÍTICO
**Priority:** HIGH — Regla estructural de datos y persistencia

### Contexto y Requerimiento

1. **Respaldo de Tablas JSON en Neon PostgreSQL (Vault):**
   - Persistir las tablas estandarizadas de investigación (`rc_tide_derived.json`, `rc_tide_probability_table.json`, `rc_tide_ev_derived.json`, `rc_vol_normalized_thresholds.json`) dentro de la Base de Datos (`engine.fact_rules_tide`, `engine.quantile_thresholds` o equivalente JSONB/relacional).
   - Evaluar cuál esquema/mecanismo de persistencia en PostgreSQL es el más adecuado y eficiente (JSONB vs tablas normalizadas por `state_key`/`quantile_key`).

2. **Re-Alineación de la Política de Fallback (Vault-Backed Fallback Policy):**
   - **Prohibición Absoluta:** Queda estrictamente prohibido realizar fallbacks sobre datos dummy, asunciones hardcodeadas o números arbitrarios inventados en el código.
   - **Política Ajustada:** El fallback **únicamente es válido si se realiza sobre un dato de respaldo verificado** almacenado en la Base de Datos (Neon Vault).
   - **Comportamiento ante Ausencia Total:** Si tanto el dato primario en memoria/JSON como el dato de respaldo en la Base de Datos no están disponibles o faltan, el sistema debe notificar y lanzar una excepción de falta de dato sin asumir o inventar nada.

---

## P-007: Persistencia de Columnas Clasificadas en ChannelSnapshots

**Status:** 🟢 APROBADO ARQUITECTURA
**Priority:** HIGH — Single Source of Truth & ML Feature Store Optimization
**Decision IDs:** D-014

### Contexto y Decisión Directa

Actualmente `engine.channel_snapshots` almacena los valores flotantes continuos (`tide_slope`, `current_slope`, `wave_slope`, `vwap_sigma_wave`). La clasificación cuantílica normalizada por ATR% (`T++`, `C+`, `W-`, `<<`, `T++/C+/<<`) se ejecutaba posteriormente en memoria en Python.

**Decisión:** Persistir las etiquetas discretizadas exactas directamente en la tabla `engine.channel_snapshots` desde el paso de Backfill y Daemons, convirtiendo el Vault en un Feature Store autónomo y autotenido.

### Cambios de Esquema Propuestos (`engine.channel_snapshots`)

```sql
ALTER TABLE engine.channel_snapshots
ADD COLUMN IF NOT EXISTS atr_pct DOUBLE PRECISION DEFAULT 0.01,
ADD COLUMN IF NOT EXISTS tide_level VARCHAR(10),        -- 'T+++', 'T++', 'T+', 'T~', 'T-', 'T--', 'T---'
ADD COLUMN IF NOT EXISTS current_level VARCHAR(10),     -- 'C+++', 'C++', 'C+', 'C~', 'C-', 'C--', 'C---'
ADD COLUMN IF NOT EXISTS wave_level VARCHAR(10),        -- 'W+++', 'W++', 'W+', 'W~', 'W-', 'W--', 'W---'
ADD COLUMN IF NOT EXISTS vwap_bin VARCHAR(5),           -- '<<', '<', '~', '>', '>>'
ADD COLUMN IF NOT EXISTS state_key_3d VARCHAR(30),      -- 'T++/C+/<<'
ADD COLUMN IF NOT EXISTS quantile_version VARCHAR(20) DEFAULT 'v1_2026';
```

### Beneficios Técnicos Auditados

1. **Single Source of Truth:** Una única fuente de verdad directa desde el Vault. Cero divergencias entre scripts de producción e investigación.
2. **Rendimiento 100×:** Agrupaciones y entrenamientos directo en SQL mediante `GROUP BY state_key_3d` a velocidad de motor relacional indexado sin re-clasificar 4.57M de filas en Python.
3. **Hermeticidad:** El `ChannelSnapshot` leído de DB contiene todas sus clasificaciones sin requerir re-cálculos de volatilidad externos.

---

## P-008: Heterogeneidad de Historial por Ticker

**Status:** 🟡 PENDIENTE (anotado 2026-09-30) · **Priority:** HIGH

### Problem
Los tickers tienen historial de **distinta longitud e incepción** (IPOs, inclusiones en índices, cambios de perfil de volatilidad). Una escala Gaussiana **adaptativa per-ticker** exige una ventana de calibración; si el historial difiere:
- Tickers jóvenes (COIN, ARM, PLTR…) tienen pocas barras → percentiles extremos **inestables**.
- Tickers con **ruptura estructural** (TSLA pre/post S&P500, NVDA pre/post IA) tienen distribuciones **no estacionarias**.
- Revolver el censo completo mezcla regímenes.

### Open Questions
- ¿Ventana: **censo completo** vs **rolling (3-5 años)** vs **expanding**?
- ¿**N_min** de barras para calibrar un ticker? ¿Y si no lo alcanza → pooling a familia/clase de volatilidad?
- ¿Tratar rupturas estructurales (retrain/re-anchor) o asumir estacionariedad?

---

## P-009: Registro, Interpretación y Excepción de Overflow / Blowoff

**Status:** 🟡 PENDIENTE (anotado 2026-09-30) · **Priority:** HIGH

### Problem
Los **`overflow`** (valores que superan ±2σ) y los **`blowoff`** (tiers `T1..T5+`) deben: **registrarse, interpretarse y manejar su excepción**. Hoy:
- En METAR existe la escala canónica `T1..T5+` en metadatos (`sigma_overflow.py`).
- En **Tide/Wave/Multiscale NO está definido** cómo se registra el overflow en el state_key, cómo se interpreta (¿señal especial?), ni qué excepción/regla se activa.

### Open Questions
- ¿Overflow como **atributo del state_key** (como METAR) o **dimensión propia**?
- ¿Cómo se interpreta: **ruptura de régimen / señal especial / blowoff parabólico (techo) / capitulación (piso)**?
- ¿Qué **excepción**: se agrupa con el bin extremo, se **escinde a estado aparte**, o **dispara alerta**?
- Alineación con **§3.3 (diamantes)** y con la regla *"señales especiales NO son ruido"*.

---

## P-010: Migración de Hallazgos Existentes a las Nuevas Escalas/Formatos

**Status:** 🟡 PENDIENTE (anotado 2026-09-30) · **Priority:** HIGH

### Problem
Si cambian las escalas (7→6 bins) o el formato de llave (5→6 VWAP, per-ticker), **todos los hallazgos validados sobre las escalas viejas** quedan potencialmente inválidos o no comparables:
- KI `ev-horizon-divergence` (80% acuerdo, FLOOR 31%, CEILING 29%) — referidos a las escalas **actuales**.
- KI `zz-s5-breadth-coincidence` (62.4/77.1/85.0%) — referidos a `zz25/50/75`.
- **Heatmap EV T×VWAP**, gradientes, y las reglas de decisión **D-001..D-015**.
- Los **fact stores** y los **5 lookups** de `swing_gate.py`.

### Open Questions
- ¿Cómo se **traslada** un hallazgo de una escala a otra (remapeo de bins)? ¿Se **re-valida** o se asume?
- ¿Qué hallazgos **sobreviven** el cambio de escala y cuáles hay que **re-medir**?
- ¿Se mantiene un **puente de homologación viejo↔nuevo** (para no perder lo aprendido)?

---

## P0: Bug `p_bull` cruzado (BLOQUEANTE)

**Status:** 🟢 RESUELTO (2026-09-30) · **Priority:** RESOLVED

**Resolución:**
Se corrigió la fórmula cruzada en `generate_tide_ev_real_derived.py` (L63) y `generate_multiscale_ev_derived.py` (L60), restituyendo `raw_p_bull = n_pos / n_tot = P(MAX)`. Se actualizaron docstrings/glosarios en ambos generadores y en `rc_tide_ev_lookup.py` (L33-34), se fortaleció la resolución de muestras `n` en la jerarquía L3/L2/L1, y se regeneraron exitosamente `rc_tide_ev_derived.json` y `rc_ev_multiscale_tree.json`. Verificación empírica confirmó `p_bull = 0.5444` en `T~|C~|~` (coincidencia exacta con `n_pos/n_tot`). Fact stores y downstream desbloqueados.

---

## P-011: Evaluador General Tide (análogo al "evaluador continuo" de METAR)

**Status:** 🟡 PENDIENTE (anotado 2026-09-30) · **Priority:** HIGH

### Problem
METAR tiene un **evaluador continuo** (validación empírica obligatoria: *"ninguna regla heurística se acepta sin validación en el evaluador continuo"*, `metar_architecture_and_signals_map.md` §5.1). Tide **no tiene un evaluador general equivalente**.

### Open Questions
- ¿Qué mide el evaluador Tide? (IC, EV_rel por decil, hit-rate, lift OOS, p_BH/DSR).
- ¿Cada cuánto corre (semanal/mensual/por evento)?
- ¿Promueve/demota señales como el de METAR?

---

## P-012: Herramienta Integradora de Dimensiones (candidato: "10-Station Model")

**Status:** 🟡 PENDIENTE (anotado 2026-09-30 — **nombre por confirmar con el Arquitecto**) · **Priority:** HIGH

### Contexto
El Arquitecto recuerda *"otra herramienta que integra las dimensiones, determinante en las estaciones METAR — algo como «tristatate»"*.

### Candidato identificado (búsqueda en repo)
**`/root/botero-trade/.agents/references/metar/interactions.md`** — *"METAR Station Interactions — Cross-Station Intelligence (10-Station Model)"*:
- **Metodología:** *Kinematic proximity tensor* (t_-1..t_-5) + Expanding Window D1 + SHAP TreeExplainer.
- **Performance:** **AUC 0.8387 OOS** (Purged 5-Fold CV, Grade B validado).
- **Naturaleza:** integra las **10 estaciones METAR** (VIX, VVIX, PCR, FG, SV5T, SKEW, CREDIT, YIELD, ROTATION, BSI) en espacio tensorial — **reemplaza la confluencia lineal** (que fracasó, lift −7.2%).
- Otros candidatos: `metar_architecture_and_signals_map.md` §M1 *"Confluencia Vectorial Acoplada (D1×D2×D3)"*; composites `triple_fear.yaml`.

### Open Questions
- **Confirmar el nombre real** que recuerda el Arquitecto.
- **✅ Herramienta LOCALIZADA (graphify, 01-Oct-2026):** `backend/scripts/trainers/train_kinematic_metar_gbm_shap.py` — el **trainer del modelo cross-station ("10-Station Model")**: `build_predictive_dataset()`, `train_segregated_gbm()`, **`PurgedKFold`** (purga + embargo), `evaluate_circuit_breakers()`, `generate_report()` (SHAP). **Es el INTEGRADOR real** que reemplaza la confluencia lineal (AUC 0.8387 OOS). Doc: `.agents/references/metar/interactions.md`.
- **Contexto:** el Arquitecto había pedido **anotar este pendiente** ("construir una herramienta similar") — y **costó localizar la original** (el término "tristatate" no existe literal; se localizó vía `graphify explain/query`).
- ¿Se construye un **"Tide Interactions"** análogo (integrar T × C × W × VWAP en tensor) para los regímenes?

---

*Last updated: 2026-09-30T00:00Z*
*Version: 1.5.0*
