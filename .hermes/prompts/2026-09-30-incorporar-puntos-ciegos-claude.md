# PROMPT PARA CLAUDE — INCORPORAR LOS PUNTOS CIEGOS AL PROMPT DE REDISEÑO
## (con ventana de contexto completa)

**Fecha:** 2026-09-30 · **Preparado por:** Hermes (guiar/auditar/construir prompts — NO programar)
**Destino:** Claude (agente de diseño, Antigravity)
**Objetivo:** incorporar los **12 puntos ciegos identificados** al prompt de rediseño `2026-09-29-rediseno-ev-derived-escalas-adaptativas.md`, **de forma ADITIVA** (sin degradar), y dejar la **ventana de contexto** para que el diseño se haga con todo lo aprendido.

---

## 0. VENTANA DE CONTEXTO (leer ANTES de editar — esto es lo que hay que saber)

### 0.1. Objetivo del rediseño
Rediseñar la serie `rc_tide_ev_derived.json` (y Wave/Multiscale) con **escalas Gaussianas ADAPTATIVAS por ticker**, manteniendo las variables dimensionales establecidas.

### 0.1-bis. ¿EN QUÉ CONTEXTO TRABAJAMOS? (los EV y los archivos — EXPLÍCITO)
El objeto del rediseño es **el EV de las 3 dimensiones cinemáticas — Tide (T), Current (C) y Wave (W)** — materializado en estos archivos:

| # | Archivo | Dimensiones que cubre | Rol |
|---|---|---|---|
| 1 | `rc_tide_ev_derived.json` | **Tide (T) × Current (C) × VWAP** | **EV primario** (el "Tide EV") |
| 2 | `rc_wave_ev_derived.json` (+ `_3scales`) | **Wave (W) × σVc × σc × vel** | **EV primario** (el "Wave EV") |
| 3 | `rc_ev_multiscale_tree.json` | **T \| C \| W \| σVc \| σVw \| ΔσVw#FATIGUE** | **DERIVADO** de (1)+(2) |

- **Tablas base (insumo):** `rc_tide_ev_probability_table.json`, `rc_ev_multiscale_probability_table.json`.
- **Derivados consumidores:** `rc_tide_ev_lookup.py`, `rc_wave_ev_lookup.py`, `rc_multiscale_ev_lookup.py` (+ `swing_gate.py`).
- **Normativa de escalas:** `rc_vol_normalized_thresholds.json` (percentiles GLOBALES → a reemplazar por per-ticker).
- **⚠️ Confirmar:** "los dos archivos que estamos mejorando" = **(1) `rc_tide_ev_derived.json` + (2) `rc_wave_ev_derived.json`**; (3) `rc_ev_multiscale_tree.json` es **su derivado**. *(Si los 2 son otros, corregir aquí.)*

### 0.2. Decisiones YA adjudicadas (no re-abrir)
| ID | Decisión | Fundamento |
|---|---|---|
| **P0** | `p_bull = P(MAX) = n_pos/n_tot` — **RESUELTO** (commit `e2a2ada`) | Fórmula cruzada corregida en 2 generadores; JSONs regenerados |
| **D-SPACE** | **6×6×6 = 216 estados** (D1 gaussiano para T, C y VWAP) | El test de gradiente interno mostró que la mediana debe ser **corte** (VWAP Δ+0.0109, T Δ+0.0064, C Δ+0.0017) |
| **D-TESIS** | **MOMENTUM** | EV relativo monótono en VWAP: `>>` +0.0228, `<<` −0.0268 |
| **D-DEPLOY** | **Serie versionada + puntero atómico** (v1 materializada/reconstruible, v2 viva; flip atómico del puntero) | No dual de dos vivas; no reemplazo destructivo |
| **D-KEY** | La llave **evoluciona** a `T{6-bin}|C{6-bin}|{6-vwap_bin}`; los 5 lookups se adaptan en v2 | Consecuencia de 6×6×6 |

### 0.3. Hallazgos verificados (dato mata relato — no reinterpretar)
- **Distribuciones v1:** `T~` = **50%**; VWAP `>>` = **34.6%** (patología por edges fijos). VWAP real: `<<` 21.5% · `<` **14.3%** · `~` **12.5%** · `>` **17.2%** · `>>` 34.6% (N: 978.058 / 650.908 / 567.952 / 782.408 / 1.574.995; total **4.554.321**).
- **Medianas:** T +2.492 · C +2.857 · W +2.965 · VWAP +0.380.
- **Gradiente pico `T~→T+` = +0.0139** (robusto al fix P0).
- **L0 baseline** = +0.0247 (promedio de 3 escalas).
- **Bug semántico real:** `SlopeState.tide_sign = 1 if "+" in level else -1` → `T~` devuelve **−1** (bajista) siendo neutral.
- **Muestras:** 4.554.321 en raw table; 4.578.350 en `engine.channel_snapshots`.

### 0.4. Puntos ciegos identificados (12) — el INVENTARIO a incorporar
| ID | Punto ciego | Prioridad |
|---|---|---|
| PC-01 | Desaparición del neutro `T~` (corrige bug de sign, pero elimina el estado neutral) | P1 |
| PC-02 | **Overflow / Blow-off inexistente en Tide** (METAR tiene `sigma_overflow.py` T1–T5) | **P0** |
| PC-03 | **Política de Inception no definida** (tickers cortos: ventana, N_min, warm-up) | **P0** |
| PC-04 | D2 (velocidad) y D3 (estabilidad) no existen en Tide (METAR: D1×D2×D3) | P2 |
| PC-05 | `_documentation.taxonomy` ausente en Tide (METAR la tiene, Rule 21) | P1 |
| PC-06 | Formato de key: numérico `"3__1__5"` (Rule 24) vs textual `"T+\|C-\|>>"` | P1 |
| PC-07 | Expanding window vs población fija (look-ahead bias) | P2 |
| PC-08 | Cascade entre escalas ZZ (`cascade_50/cascade_75`, `prev_leg_domino`) no medida | P2 |
| PC-09 | Naming VWAP (`<<</~/>>` cambian de significado con 6-bin) — **⚠️ tabla con 3 valores FALSOS, ver §2** | P1 |
| PC-10 | Naming T/C (`+++/++/+/-/--/---` en 6-bin) — recomendación: mantener | P2 |
| PC-11 | Cadencia de recalibración no definida | P2 |
| PC-12 | Transition tracking vía `RegimeStatePort` no conectado | P3 |

### 0.5. Artefacto fuente
`/root/.gemini/antigravity-ide/brain/e8aaefd3-.../analisis_puntos_ciegos_metar_vs_tide.md`

---

## 1. TAREA
Añadir al prompt de rediseño una **sección nueva: "Inventario de Puntos Ciegos Identificados"**, con los **12 PC-01..PC-12**. Cada punto debe llevar:
- **(a) Descripción** del gap.
- **(b) Evidencia** (archivo/línea o medición).
- **(c) Acción recomendada.**
- **(d) Prioridad** (P0/P1/P2/P3).

Destacar los **2 P0** (PC-02 overflow, PC-03 inception). Incluir también los **6 patrones transferibles de METAR** (PT-01..PT-06: clasificador centralizado, taxonomy, diamantes, overflow, inception, regeneración atómica).

## 2. CORRECCIÓN OBLIGATORIA — PC-09
La tabla de distribución VWAP v1 del artefacto tiene **3 valores falsos**. Reemplazar por los **reales verificados**:
| Bin | Afirmado (falso) | **Real** |
|---|---:|---:|
| `<<` | 21.5% | **21.5%** ✓ |
| `<` | 7.6% | **14.3%** |
| `~` | 8.3% | **12.5%** |
| `>` | 27.9% | **17.2%** |
| `>>` | 34.6% | **34.6%** ✓ |
*(N: 978.058 / 650.908 / 567.952 / 782.408 / 1.574.995)*. La **conclusión** de PC-09 (los labels cambian de significado) **se mantiene**; solo corrige la tabla.

## 2-bis. PC-06 — PROPUESTA DE ESCALA CON SIGNO (σ-index) — EVALUAR E INCORPORAR
> Origen: el Arquitecto. En METAR hubo **muchos problemas de interpretación** con la escala 1–5 (sin dirección/magnitud clara).

**Propuesta:** reemplazar los labels textuales (`+++/++/+/-/--/---` y `<</</../>/>>`) por **enteros con signo que representan σ**:
- **6 bins (T, C, W):** `+3, +2, +1, −1, −2, −3` (sin 0).
- **5 bins (VWAP, σVc, σc):** `+2, +1, 0, −1, −2` (**0 = neutro, preservado**).

**Ventajas (verificadas con la experiencia METAR):**
1. **Signo = dirección; |valor| = magnitud en σ** → cero ambigüedad de dirección/magnitud.
2. **Elimina la lógica de centralización** (`"+" in level`) → es un entero con signo; comparaciones `>0`, `abs()`, orden trivial.
3. **Corrige el bug de `T~`** (PC-01): el signo surge del número, no de parsear texto.
4. **Numérico (Rule 24) CON semántica σ** — superior a un índice 0..5 ciego.

**Refinamiento:** mantener **prefijo de canal** para que la llave siga autodescriptiva:
`T3|C1|V-2` (textual) o `t3__c1__v2` (numérico Rule 24, con signo). *(Se recomienda el numérico firmado como clave primaria + el label semántico como campo auxiliar, ver PC-06 original.)*

**Acción para el diseño:** adoptar el **σ-index firmado** como base del `taxonomy` y de la llave v2, y definir el mapeo explícito bin↔σ en la `_documentation`.

---

## 3. REGLAS (obligatorias)
1. 🚫 **ADDITIVE-ONLY:** no eliminar, acortar, resumir ni "simplificar" ningún esquema, campo, `_documentation`, jerarquía o taxonomía ya presente. Toda edición es **aditiva o de corrección factual**.
2. **No degradar:** el diff debe **crecer**, nunca encoger.
3. **No inventar:** si un dato no está verificado, **marcarlo como hipótesis** (no afirmarlo).
4. **Ventana de contexto:** preservar §0 y la coherencia con las decisiones §0.2.
5. **Conservar `zz25 / zz50 / zz75`** (intocables) y **los extremos raros** (§3.3).

## 4. NO HACER
- ❌ **No resolver las investigaciones** (P-008/009/010/011/012): son **pre-work NUESTRO**. Solo **registrarlas** como gaps identificados; **no las cierres**.
- ❌ No recalibrar umbrales D-001..D-015 (throwaway).
- ❌ No tocar código de producción.

## 5. CRITERIO DE ACEPTACIÓN
- [ ] Sección "Inventario de Puntos Ciegos" con los **12 PC** + los **6 PT**.
- [ ] **PC-09 corregido** con los valores reales.
- [ ] **Diff aditivo** verificado (el archivo crece; ningún esquema recortado).
- [ ] Los 2 **P0** destacados.
- [ ] Las investigaciones P-008/009/010/011/012 quedan **registradas como pendientes**, NO resueltas.

## 6. ENTREGABLE
El prompt de rediseño modificado (aditivo) + un resumen del diff (qué se añadió, byte-delta) confirmando que **nada se recortó**.
