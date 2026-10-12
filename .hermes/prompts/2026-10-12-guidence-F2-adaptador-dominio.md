# GUÍAS / PROMPT #3 — FASE 2: ADAPTADOR DE DOMINIO, CON PUERTA DE MEDICIÓN PREVIA
**Fecha:** 12-Oct-2026 · **Alcance:** Fase 2 del plan v3.0 (`triad_lookup.py`).
**Estado de partida:** Fase 0 cerrada y sana (verificado). Fase 1 produjo `s5_triad_table.json` **v3.1**.

---

## 0. PRINCIPIO (declarado, no negociable)

**Un adaptador sin consumidor no es una fase: es un cambio de librería.**

Fase 2 extiende `triad_lookup.py` para que el dominio lea los 4 bloques y el nivel `sectors`. Antes de
escribir una línea, hay que responder: **¿qué decisión de producción cambia cuando esto funcione?**
Si la respuesta es «ninguna», Fase 2 no agrega valor — agrega superficie.

Y la segunda regla: **un nivel nuevo de granularidad se justifica por separación de poblaciones
medida, no por conveniencia arquitectónica.** Si el nivel no separa del ruido, no se expone.

---

## 1. ESTADO VERIFICADO (12-Oct-2026, medición directa)

### 1.1 `triad_lookup` NO TIENE CONSUMIDOR DE PRODUCCIÓN

```
grep -rn "triad_lookup|lookup_triad_signal|lookup_s5v_triad_signal" backend/modules/ --include="*.py"
→ solo las 2 definiciones dentro de triad_lookup.py
```

Consumidores reales, todos **fuera** de la ruta de decisión:

| Tipo | Archivo |
|---|---|
| Auditoría | `backend/scripts/audits/audit_multiscale_spans_and_zigzag_turns.py` |
| Auditoría | `backend/scripts/audits/audit_crossovers_and_market_intel.py` |
| Research | `backend/scripts/optimize_crash_sistemico_intelligence.py` |
| Reporte | `backend/scripts/scorecard_with_triad_probabilities.py` (:107 llama) |
| Tests | `tests/test_triad_lookup.py` (6 tests) |

**`QualityEntryGate` NO importa la tríada.** Clasifica con sus **propios** `S5_EDGES`/`SV5_EDGES`
hardcodeados (`quality_entry_gate.py:47-57`) y construye `spy_joint` con clave de **7 componentes**
(`TH|FI|TW|vTH|vFI|vTW|dir`), espacio distinto del `TH|FI|TW|DIR` de la tabla.

`entry_report.py` **declara** los campos (`sector_triad_p_bot`, `sector_triad_level`, …) pero **nadie
los puebla** desde el lookup.

⇒ La tabla v3.1 (7,2 MB) y su adaptador están **fuera de la ruta de decisión**.

### 1.2 El nivel `sectors` es DATO MUERTO

238 celdas R4 contienen hasta 13 sectores calculados. **Nadie los lee.** `triad_lookup` resuelve con
`_ETF_TO_TIER_LABEL` (L21-26) → **tier**, nunca `sectors`.

### 1.3 Las etiquetas de nivel no cuadran — y hay tres esquemas

```
_documentation.state_hierarchy (v3.1):  L0 = Global macro · L1 = Volatility Tiers · L2 = Individual Sectors (N >= 20)
código (triad_lookup L192/L200):        level = f"{res_level}_L1_{l1_key}"     ← L1 = TIER
                                        level = f"{res_level}_L2_global"      ← L2 = GLOBAL
TriadSignal docstring (L46):            "L1_Defensive", "L1_SPY", "L2_global"
```

### 1.4 Umbral: el plan dice 20, el código usa 30

`_metadata.hierarchical_fallback` **ya no existe en v3.1** ⇒ el código cae al default **30**
(`triad_lookup` L160-162). El `_documentation` promete sectores «si N >= 20».

### 1.5 MEDICIÓN DE LA PUERTA D-2 — RESUELTA, Y CONTRADICE MI EXPECTATIVA

Corrí el test de separación (§3) sobre la tabla **v3.1 real**:

| Nivel | Umbral | Celdas evaluables | Ratio dispersión/ruido (mediana) | Superan 2× | No superan 1× |
|---|---|---:|---:|---:|---:|
| **Sector** | N ≥ 20 | **101 / 238** (42%) | **2,44×** | **68,3%** | 3 |
| **Sector** | N ≥ 30 | 78 / 238 (33%) | 2,39× | 66,7% | 5 |
| Tier | N ≥ 30 | 104 / 238 (44%) | 1,72× | 39,4% | — |

**⇒ El nivel Sector separa MÁS que el Tier, no menos.** Yo esperaba lo contrario (que el N menor lo
hundiera). El dato dice 2,44× contra 1,72×. La explicación es contraintuitiva pero consistente: **el
Tier POOLIZA sectores similares** (Defensive = XLP+XLV+XLU+XLRE+XLB), y poolizar **promedia** las
diferencias. Al bajar un nivel aparece la dispersión que el pooling escondía.

Por el criterio pre-declarado («se expone si el ratio mediano supera 2×»): **D-2 se resuelve en SÍ.**

**Dos advertencias que van con ese SÍ, y no son menores:**

1. **Cobertura parcial.** Sólo **101 de 238** celdas R4 (42%) son evaluables con N ≥ 20, y **78 (33%)**
   con N ≥ 30. En **más de la mitad de los estados no habrá nivel Sector** y seguirá corriendo el Tier.
   El nivel nuevo aplica en menos de la mitad de las situaciones.
2. **Separación ≠ ganancia predictiva.** El ratio mide dispersión *dentro* de la celda normalizada por
   ruido; **no** mide si resolver en Sector predice mejor que resolver en Tier. Eso exige un test
   **fuera de muestra** (¿mejora `P_bot`/`lift` al resolver por sector?). Es el test que decide de
   verdad, y queda como **D-5**.

*(Nota: el ratio del nivel Tier se movió de 1,54× en v2.0 a 1,72× en v3.1 — la regeneración cambió
las probabilidades. Coherente, pero conviene saber que el número de referencia se movió.)*

### 1.6 Referencia previa — dispersión intersectorial (pierna MIN→MAX)

| Medición | Resultado |
|---|---|
| Dispersión real (13 entidades) | zz25 **0,80 pp** · zz50 1,54 pp · zz75 2,57 pp |
| Lo que el §1 del plan declara | 9,1 pp (XLK +14,2% vs XLU +5,1%) — **no reproduce en 4 definiciones** |

La dispersión **incondicional** entre sectores es chica; pero la dispersión **condicional** (dentro de
una celda de estado) es la que separa del ruido. Ambas cosas son ciertas y no se contradicen.

### 1.7 El renombre de `level` NO rompe los tests (verificado)

```
test_lookup_triad_signal_hierarchical_fallback → assert any(x in sig.level for x in ["R3_","R2_","R1_"])
test_lookup_triad_signal_fallback_levels       → asserta triad_key / dir_bin / n_samples (no level)
```
Los tests afirman sobre el **prefijo R** (profundidad: R4→R3→R2→R1), **no** sobre `L1_`/`L2_`
(agregación). ⇒ Alinear las etiquetas L con `_documentation` es **seguro**.

*(Detalle de higiene: `entry_report.py:118` tiene el comentario stale «16705 obs» — el real es 83.154.)*

---

## 1.8 HALLAZGOS DE LA RE-AUDITORÍA (12-Oct, nueva pasada) — UNO ES BLOQUEANTE

### 🔴 N-1 BLOQUEANTE: la recalibración de los umbrales fue ELIMINADA en v3.1

**Antes (v2.0, commiteado en HEAD)** el trainer **calculaba** los edges en cada corrida:

```python
# STEP 2: DEFINE BIN EDGES (global percentiles)
all_th = pd.concat([d["th"] for d in entities.values()])
for name, series in [("TH", all_th), ("FI", all_fi), ("TW", all_tw)]:
    cuts = series.quantile(BIN_PERCENTILES)          # [0.10, 0.30, 0.70, 0.90]
    bin_edges[name] = [round(c, 2) for c in cuts]
```

**Ahora (v3.1, working tree)** los edges son un **literal congelado**:

```python
CANONICAL_BIN_EDGES = {                       # "Canonical bin edges (SSOT)"
    "TH": [28.6, 55.0, 82.7, 93.3],
    "FI": [20.7, 46.7, 76.6, 90.0],
    "TW": [16.7, 42.3, 74.7, 89.6],
}
...
"bin_edges": CANONICAL_BIN_EDGES,             # L604 — se escribe el literal
```

`git log -S "CANONICAL_BIN_EDGES"` → **vacío**: el literal **nunca fue commiteado**. Existe sólo en el
working tree.

**Y el artefacto sigue declarando el método viejo**: `train_s5_triad.py:602` escribe
`"bin_percentiles": [0.10, 0.30, 0.70, 0.90]` — **una afirmación que ya es falsa.**

**Verificado por medición independiente** (percentiles 10/30/70/90 de la población real, TH, n=147.300):

```
percentiles calculados : [27.8, 55.0, 83.8, 94.6]
edges embarcados       : [28.6, 55.0, 82.7, 93.3]     ← difieren hasta 1,3 pp
```

**Cadena de consecuencias (cada eslabón verificable):**

1. El **retrainer semanal** (`triad_retrainer_provider`, domingos) recomputa las probabilidades pero
   **los edges nunca se mueven** ⇒ el clasificador queda congelado mientras el dato deriva.
2. **Dos literales congelados que no coinciden**: gate `[27.6, 54.8, 82.8, 93.5]` vs tabla
   `[28.6, 55.0, 82.7, 93.3]`. Como **ninguno recalcula**, el desfase SV5 (20,5–26,0 % de los días)
   **no puede autocorregirse jamás**.
3. Existen **tres conjuntos** de edges en el repo: `[26.5, 48.8, 74.2, 87.5]` (ejemplo del docstring
   viejo, ya eliminado) · `[27.6, 54.8, 82.8, 93.5]` (gate) · `[28.6, 55.0, 82.7, 93.3]` (tabla v3.1).
4. **Esto explica mi hallazgo anterior** «`bin_edges` sin cambios en v3.1»: no es que no cambiaran —
   **no pueden cambiar.**

### 🟡 N-2 `_documentation.bin_classification` es `null` en v3.1

El `_metadata` de v2.0 documentaba `method` + `bin_percentiles` + `bin_labels_meaning`. En v3.1 ese
bloque **desapareció**. La única traza del método queda en `taxonomy` (que sólo lista los edges).

### 🔴 N-3 NO EXISTE validación fuera de muestra de la tríada

La maquinaria walk-forward/DSR **existe pero valida otras señales**:
`walk_forward_rc_rsi_dsr.py` (RC + RSI) · `walk_forward_narrative_dsr.py` (narrativa) ·
`ablation_and_dsr.py` · `hyperparameter_sweep.py`.

Lo que **sí** toca la tríada es auditoría de **forma**, no de poder predictivo:
- `audit_triad_delta.py` — compara tablas entre **revisiones de git** (reproducibilidad)
- `scratch/audit_triad_sample_size.py` — compara **tamaños de muestra** (13 ETFs vs SPX+QQQ vs SPX puro vs 2006-2026)
- `test_triad_lookup.py` (6 tests) — **contratos de humo**: que el lookup no falle y que el fallback opere

⇒ **Nunca se midió si la tríada predice fuera de muestra.** Ese es exactamente el hueco que hace de
**D-5** el test decisivo, no un extra.

### 🟡 N-4 Los TIERS no tienen derivación documentada

`TIERS = {"Defensive": [XLP,XLV,XLU,XLRE,XLB], "Mixed": [...], ...}` es un **agrupamiento escrito a
mano** en el trainer. El metadata afirmaba «se agrupan por comportamiento similar», pero **no existe
artefacto que muestre el clustering**. Los tiers son **definidos**, no derivados.

### 🟡 N-5 `MIN_N_L1` no cuadra en ninguna de las tres capas

```
trainer v3.1      MIN_N_L1 = 20
_documentation    "exposed if N >= 20"
código (lookup)   default 30  (porque _metadata.hierarchical_fallback no existe en v3.1)
```
Tres fuentes, dos números. Debe quedar **una sola clave**, la que el código lee.

---

```
D-1  ¿La tríada ENTRA en la ruta de decisión de producción?
     (a) Sí → se declara QUÉ consumidor y con qué contrato (y Fase 2 tiene valor).
     (b) No, por ahora → Fase 2 se limita a los campos opcionales + etiquetas,
         y el nivel `sectors` NO se expone hasta que haya consumidor.
     (c) No, nunca → la tabla v3.1 queda como artefacto de research y se declara así.

D-2  ¿Se expone el nivel Sector?  **RESUELTA EN SÍ por medición** (§1.5): ratio mediano 2,44× (N≥20),
     por encima del criterio pre-declarado de 2×. Pero ver D-5 — la cobertura es del 42% y separación
     no es lo mismo que ganancia predictiva.

D-5  **El test que decide de verdad (fuera de muestra).** El ratio de §1.5 mide separación DENTRO de la
     celda; no mide si resolver en Sector predice mejor que resolver en Tier. Antes de que el nivel
     Sector toque producción: medir walk-forward si `P_bot`/`lift` resueltos por sector superan a los
     resueltos por tier, fuera de muestra. Si no superan, el nivel se expone en la tabla pero NO se
     conecta a la decisión — y eso se declara.

D-3  Umbral: ¿20 (lo que documenta `_documentation`) o 30 (lo que el código usa hoy)?
     Debe quedar en UNA sola clave, la que el código lee (`_metadata.hierarchical_fallback.min_n_prefix`),
     y el `_documentation` debe citar esa misma. Dato para decidir: con 20 son 101 celdas evaluables
     (42%); con 30 son 78 (33%). El ratio es casi idéntico (2,44× vs 2,39×).

D-4  ¿Se renombran las etiquetas a L0/L1/L2 como en `_documentation`?
     (Recomendado: sí — los tests no dependen de ellas y hoy hay tres esquemas conviviendo.)
```

---

## 3. MEDICIÓN OBLIGATORIA ANTES DE ESCRIBIR CÓDIGO (puerta de D-2)

Para cada celda R4 con muestra suficiente, y para cada sector con N ≥ umbral, calcular:

```
dispersión_sector = max(P_bot_5_0) - min(P_bot_5_0)   entre sectores dentro de la celda
ruido             = 2 × EE_binomial medio = 2 × sqrt(p(1-p)/n)   por sector
ratio             = dispersión_sector / ruido
```

**Reportar:** mediana y media del ratio · cuántas celdas superan 2× · cuántas no superan 1× ·
y **cuántas celdas R4 tienen ≥3 sectores con N ≥ 20 y N ≥ 30** (sin eso, el nivel no es evaluable).

**Regla de decisión:** si el ratio mediano **no supera 2×**, el nivel Sector **NO se expone** — se
documenta el resultado y se cierra la decisión con ese número. No se implementa «por si acaso».

---

## 4. EL CAMBIO (si D-1 y D-2 lo habilitan)

1. **Extender `TriadSignal` aditivamente** — campos nuevos con `Optional[...] = None`, **sin tocar ni
   renombrar** ninguno de los 19 existentes:
   `ev_net_zz50`, `rr_asymmetry_zz50`, `duration_mean_days`, `fatigue_stage`, `timing_slot`,
   `pct_en_rango`, y el nivel resuelto.
2. **Jerarquía de búsqueda** en `lookup_triad_signal` y `lookup_s5v_triad_signal`:
   `Sector (si N ≥ umbral unificado)` → `Tier` → `Global`.
3. **Etiquetas alineadas con `_documentation`**: `L0` = global · `L1` = tier · `L2` = sector.
   Mantener el prefijo `R4_/R3_/R2_/R1_` intacto (los tests dependen de él).
4. **No cambiar** el espacio de clave `TH_bin|FI_bin|TW_bin|DIR`, ni `bin_edges`, ni `bin_labels`.
5. **Higiene:** corregir el comentario stale `16705 obs` de `entry_report.py:118` → `83.154`.

---

## 5. CRITERIOS DE ACEPTACIÓN (medibles)

```
A-1  Los 6 tests de tests/test_triad_lookup.py siguen pasando, y NINGUNO fue modificado para lograrlo.
     (Si algún test tuvo que cambiar, se declara cuál y por qué — es señal de ruptura de contrato.)
A-2  Un test NUEVO que afirme la resolución Sector → Tier → Global con un caso construido por nivel.
A-3  Ningún campo preexistente de TriadSignal cambió de nombre ni de tipo (diff del dataclass).
A-4  El umbral efectivo del código == el documentado en `_documentation` (mismo número, una clave).
A-5  Si D-2 se resuelve en NO: la tabla NO expone `sectors`, o se declara explícitamente que es
     dato de research sin consumidor. No puede quedar como hoy: calculado y sin leer, sin declararlo.
```

---

## 6. NO ANCLAR (dos caminos deben converger)

Reporta la resolución por **dos vías independientes**:

1. **Vía código:** qué nivel resolvió cada consulta (`sig.level`), para una misma lectura de mercado.
2. **Vía tabla:** lectura directa del JSON — qué celda, qué nivel, qué `n`, para esa misma lectura.

Deben coincidir. Si no coinciden, se reporta la discrepancia — **no se ajusta el código para que cuadre.**

---

## 7. LO QUE **NO** ENTRA EN FASE 2 (declarado)

```
· Fase 4 (S5V): s5v_triad_table.json sigue v2.0 del 07-oct, celdas con una sola clave ['global'],
  y train_s5v_triad.py SIN modificar. Es fase propia.
· Desfase de edges gate↔tabla (SV5 20,5–26,0% de los días). Fase 2 no lo toca ni lo empeora.
· Tamaño del artefacto: 351 KB → 7,2 MB (20,5×), sin carga lazy. Fuera de alcance aquí.
· Tiebreaker en los dos pobladores de `prev_leg_return` (ordenan por `start_timestamp` sin desempate;
  4.535 piernas de duración cero crean 4.534 empates). El orden canónico medido es `end_timestamp`.
· `same_bar_pair`: columna huérfana — existe en la tabla, 0 TRUE, y no aparece en ningún archivo
  del repo (ni la escribe ni la lee nadie).
· Benchmark delta v2.0 → v3.1 (89 de 391 celdas cambian de clase con umbral ±0,10).
```

---

## 8. CIERRE ESPERADO

```
· D-1 y D-2 adjudicadas CON NÚMERO, no con criterio.
· Si el nivel Sector no separa ≥2× del ruido: decisión cerrada en NO, con la medición como evidencia.
· Si se habilita: TriadSignal extendido aditivamente, jerarquía Sector→Tier→Global, etiquetas L0/L1/L2,
  umbral único, 6 tests originales intactos + 1 test nuevo de jerarquía.
```
