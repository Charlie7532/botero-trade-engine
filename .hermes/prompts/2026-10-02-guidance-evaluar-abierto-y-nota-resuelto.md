# GUIDANCE — Evaluar lo abierto y TOMAR NOTA de lo ya resuelto (Tide v2)

> **Sesión limpia. Autocontenido.**
> **Revisión de referencia:** `eef0a8e`. Verifícala al arrancar y cítala.
> **Instrucción:** evalúa SOLO la PARTE B. La PARTE A **ya fue discutida y decidida en el hilo** — se toma nota, **no se re-evalúa**.
> **Contexto:** este guidance nace de una auditoría externa que **se equivocó** al re-abrir el paso 7→6 (ya decidido el 30-Sep). El propósito es que ese error no se repita aguas abajo.

---

## PARTE A — LO YA RESUELTO (TOMAR NOTA — NO RE-EVALUAR)

Todo lo siguiente está **decidido en el hilo de diseño (30-Sep / 02-Oct)** y **ya incorporado al prompt principal**. Reproducirlo aquí es para que nadie lo vuelva a abrir.

| # | Asunto | Estado | Dónde quedó |
|:--|:--|:--|:--|
| **A1** | **Escalas T/C/VWAP = D1 (6 bins) → 216 estados** | ✅ **DECISIÓN DEL ARQUITECTO** (30-Sep). No es un cambio indebido: es el rediseño pedido | Prompt §1.9 (`D-SIGMA`) + plan FASE 4 |
| **A2** | **Desaparición del estado neutro `T~` (PC-01)** | ✅ **EVALUADO = MEJORA SEMÁNTICA**, no un gap. Se documenta como ventaja | Prompt §10.3 |
| **A3** | **σ-index firmado como sistema de naming** (`+3,+2,+1,−1,−2,−3` en 6-bin; `+2,+1,0,−1,−2` en 5-bin) | ✅ Propuesta del Arquitecto, adoptada. Elimina el parsing textual (`"+" in level`) y el bug semántico de `T~` | Prompt §1.9 / §2.5 |
| **A4** | **Serie versionada + puntero atómico** (`rc_tide_ev_derived_v2.json`, v1 reconstruible) | ✅ Decidido (30-Sep) | Prompt (actualizado 30-Sep) |
| **A5** | **Tesis MOMENTUM** | ✅ Decidido | Prompt §9.1 |
| **A6** | **D-FAM: F2 sectorial** (11 sectores, 646–3.768 obs/celda) | ✅ **Adjudicado** | Plan §0 |
| **A7** | **D-CAL: Opción A** (cuantiles empíricos per-ticker) **+ shrinkage para jóvenes** | ✅ **Adjudicado** | Plan §0 |
| **A8** | **D-K: K=252, target = Q_sector** (no global) | ✅ **Adjudicado** | Plan §0 |
| **A9** | **D-FAT: fatiga FUERA del Fact Store** (dato puro ≠ interpretación, patrón Rotation) | ✅ **Adjudicado.** La interpretación de la fatiga es un **workstream separado, post-calibración** — **no entra en este plan** | Plan §0 |
| **A10** | **D-ORDER: secuencial por dependencia** | ✅ Eliminado como decisión | Plan §0 |
| **A11** | **Análisis de nomenclatura de pendientes T/C y labels VWAP** | ✅ Ya realizado en el hilo | hilo 30-Sep |

**Regla para la PARTE A: no se re-mide, no se re-abre, no se cuestiona.** Si algo de aquí parece contradictorio con el repo, **se reporta como nota**, no como hallazgo a resolver.

---

## PARTE B — LO ABIERTO (ESTO SÍ SE EVALÚA)

> **EJE RECTOR — LEER ANTES DE EMPEZAR:**
> **La homologación sectorial YA EXISTE y NO se reinventa. El SSOT es `backend/modules/shared/domain/constants/sectors.py`**
> (*"Canonical Sector & ETF Mapping — Single Source of Truth. All modules MUST use canonical names from this file."*)
> ```
> FINVIZ_TO_CANONICAL = { "Consumer Cyclical":"Consumer Discretionary", "Consumer Defensive":"Consumer Staples",
>                         "Financial Services":"Financials", "Financial":"Financials", "Basic Materials":"Materials" }
> canonicalize(nombre) -> nombre canónico
> SECTOR_ETFS = { XLK, XLV, XLF, XLY, XLP, XLI, XLE, XLU, XLRE, XLB, XLC }   # los 11 canónicos
> ```
> **Y el Gate de Rotación ya opera así:** `sector_rotation_flow.py` usa los **11 ETFs** como llave
> (`cyclical=["XLK","XLF","XLY","XLI"]` · `defensive=["XLP","XLV","XLU","XLRE"]` · `all_sectors` = los 11),
> y `sector_breadth_adapter.py` tiene `_SECTOR_TO_ETF` que **acepta AMBAS nomenclaturas** (Finviz *y* GICS) → ETF.
>
> **⇒ REGLA: Tide v2 DEBE leer/escribir los sectores con `canonicalize()` + `SECTOR_ETFS`, igual que Rotación. Prohibido crear un mapeo nuevo.**

### B1. Alineación con el Gate de Rotación (sustituye "declarar el mapeo")
**Ya no es una pregunta abierta.** La clave canónica del sector es **el ETF sectorial**, y la conversión es `canonicalize()`.
**Tarea:** verificar y declarar que la FASE 2/3 del plan usan:
1. **`canonicalize()`** para normalizar lo que venga de `market.ticker_metadata.sector` (hoy en nomenclatura Finviz/Yahoo),
2. **el ETF como llave de pool** (no la etiqueta descriptiva),
3. **el mismo universo que Rotación**: `load_sp500_closes_by_sector()` filtra `asset_type='STOCK' AND ('SP500'=ANY(index_membership) OR 'QQQ'=ANY(index_membership)) AND update_source='vault_ohlcv_bars'`.
**Reportar cualquier divergencia** entre lo que hace Rotación y lo que haría el plan.

### B2. `Technology`: tres números — explicar la diferencia de UNIVERSO, no de taxonomía
```
Plan: 122   ·   market.ticker_metadata: 93   ·   SP500_SECTOR_MAP: 58 (XLK)
```
**No es un problema de nombres** (los tres dicen "Technology"). **Es de universo de filtrado.**
**Tarea:** declarar de qué query/universo sale el 122, y compararlo con los tres universos conocidos: metadata completo (737), SP500+QQQ de Rotación (~500+100), y `SP500_SECTOR_MAP` (418). Los otros 10 sectores coinciden exacta o ±1.

### B3. "Excluidos (non-GICS): 7" vs 30 tickers con sector `ETF`
**Tarea:** reconciliar con la misma lógica que Rotación: `canonicalize()` deja pasar sin tocar lo que no mapea, y `load_sp500_closes_by_sector` excluye por `asset_type`. **Declarar el criterio exacto con su comando.**

### B4. FASE 4/5 — impacto del cambio de umbral sin cuantificar
Unificar `vel/traj` a `(-0.127, +0.122)` reemplaza el `±0.30` del Multiscale (**2,3×–2,5× más estricto**). El prompt ya advirtió que eso infla el STABLE.
**Tarea: medir cuántas observaciones cambian de estado** con el umbral nuevo vs el viejo, por ticker. **Ese número decide la viabilidad del cambio.** Sin él, la fase no se autoriza.

### B5. El plan omite lo que el prompt SÍ decidió: versionado y puntero atómico
**A4 dice:** serie versionada + puntero atómico. **El plan emite `_v2.json` pero no menciona el puntero ni la coexistencia v1/v2.**
**Tarea:** añadir el mecanismo de conmutación y la reconstruibilidad de v1. **No es una decisión nueva — es ejecutar A4.**

### B6. Referencias sin definir
- **"A1 + D-1"** (plan §1): el **`D-1` no está definido** → definirlo o corregir la referencia.
- **"Tickers < 252: 2"** (plan §4): medido **1 (`SNDK`)**.

### B7. Cobertura del mapeo ticker→ETF (trabajo nuevo, medido)
```
SP500_SECTOR_MAP: 418 tickers mapeados   ·   La F2 necesita el universo de Tide (566 en el lake)
→ estirado: ~141-148 tickers sin mapping ticker→ETF
```
**Tarea:** medir exactamente cuántos tickers del universo Tide **no** tienen sector asignado por el SSOT, y proponer cómo cubrirlos **sin inventar** (fuente: el mismo `ticker_metadata.sector` + `canonicalize()`).

---

## REGLAS
1. **Ejecutar ≠ leer.** Cada afirmación de la PARTE B con comando + salida.
2. **La PARTE A no se re-abre.** Si algo choca con el repo, **nota**, no hallazgo.
3. **El spec es la autoridad.**
4. **SECTORES: una sola fuente de verdad — `constants/sectors.py`.** Se usa `canonicalize()` + `SECTOR_ETFS`. **Prohibido crear mapeos nuevos.** Si algo no está cubierto, se reporta el gap, no se inventa la equivalencia.
5. **Alineación con Rotation:** lo que el Gate de Rotación ya resuelve (llave = ETF, universo = SP500+QQQ, tier map) **se hereda, no se redefine**.
6. **Las dimensiones del v2 ya están decididas** (A1/A2/A3) — **no se discuten de nuevo**.
7. **ADDITIVE-ONLY** en prompts y artefactos.
8. **No amplíes el alcance:** carril `vwap`/`trade_count` cerrado; la fatiga es workstream separado (A9).
9. **Reporta lo que NO pudiste verificar.**

---

## ENTREGABLE
1. **Sección "NOTA" con la PARTE A** — una línea por punto confirmando que se leyó y no se re-evaluó. **Sin mediciones nuevas.**
2. **Tabla de la PARTE B:** `PUNTO | COMANDO | OUTPUT REAL | RESULTADO | ACCIÓN` para los 7 puntos.
3. **La cifra del B4** (observaciones que cambian de estado) — decide si FASE 4/5 se autoriza.
4. **Declaración de alineación con Rotation (B1):** confirmación de que el plan usa `canonicalize()` + `SECTOR_ETFS` + llave-ETF + el universo SP500+QQQ — o la lista exacta de divergencias.
5. **La cifra del B7:** cuántos tickers del universo Tide **no** cubre el SSOT.
6. **Dos listas:** *"afirmaciones que no debí hacer sin medir"* y *"no verificable aquí"*.
7. **Respuesta corta:** ¿el plan es ejecutable **sin decisiones nuevas** del arquitecto y **alineado con Rotation**? Sí/No + los bloqueos.
