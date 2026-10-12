# GUÍAS / PROMPT — CIERRE DE FASE 1 Y FASE 2 (ADAPTADOR DE DOMINIO) · TRÍADA S5/SV5

**Fecha:** 12-Oct-2026
**Alcance:** (a) cerrar los defectos abiertos de Fase 1; (b) ejecutar Fase 2 = adaptador de dominio.
**Naturaleza del trabajo:** **MIGRACIÓN / SUSTITUCIÓN**, no integración nueva.
**Nota de contexto:** el ejecutor **no conoce** este documento ni los previos. Es **autocontenido**: todo lo
que necesita verificar está aquí, con la cifra exacta y el comando o la consulta que la reproduce.

---

## 0. PRINCIPIO (declarado, no negociable)

1. **El propósito declarado es sustituir `engine.zigzag_points` por `market.zigzag_legs`** en la tríada de
   rotación. Todo lo demás se juzga contra ese propósito.
2. **Una migración no se aprueba por «no rompe tests».** Se aprueba midiendo **qué cambia** respecto del
   comportamiento previo. «Se conserva todo» es una afirmación que exige medición, no una expectativa.
3. **Ante la evidencia, la prueba.** Ninguna cifra se acepta por procedencia (comentario, docstring,
   reporte viejo). Cada cifra de este documento trae su fuente y se puede reproducir.
4. **Si un valor no tiene derivación verificable en el repo, no es un valor canónico** — es un supuesto.

---

## 1. ESTADO VERIFICADO (12-Oct-2026)

### 1.1 Qué se migró — Fase 1, versión 3.1

`backend/scripts/trainers/train_s5_triad.py` fue reescrito (595 ins / 695 del) y produce
`s5_triad_table.json` **v3.1** (7.221.436 bytes, generado 18:02 UTC).

- **Migración de fuente:** pasó de calcular el ZigZag *on-the-fly* a leer
  `market.zigzag_legs` filtrando `status='CONFIRMED'` y `start_price>0 AND end_price>0`, sobre las
  **13 entidades canónicas** (SPY · QQQ · XLB XLC XLE XLF XLI XLK XLP XLRE XLU XLV XLY).
- **4 bloques atómicos por celda — implementados:**
  1. *Legacy*: `n`, `P_bot_2_5/5_0/7_5`, `P_top_*`, `lift_bot_5_0`, `lift_top_5_0`, `net_bias`
  2. *Temporal*: `n_episodes`, `pct_tiempo`, `duration_mean`, `duration_max`, `fatigue_buckets`
     (`fresh` / `persist` / `mature` / `exhaustion`, con `n`, `pct`, `ev_net`)
  3. *Timing*: `pct_en_rango`, `pct_fuera`, `delta_mediana_barras`, `slots_canonicos`
     (`t-2`, `t-1`, `t=0`, `entre`)
  4. *Cinemática* (por escala `zz25`/`zz50`/`zz75`): `p_bull`, `p_bear`, `e_ret_max`, `e_ret_min`,
     `ev_net`, `rr_asymmetry`, `e_days`, `ev_per_day`, `timeout_rate`, `mae_medio`, `confidence_tier`
- **Nivel `sectors` añadido** (nuevo): 13 entidades dentro de cada celda.
- **`_documentation` (Regla 21) añadido**: `model_purpose`, `return_formula`, `state_hierarchy`,
  `taxonomy`, `dimension_thresholds_definition`, `field_glossary`, `signal_interpretation_policy`.
  - `return_formula` = `ev_net = (P_bull·E[ret_max] + P_bear·E[ret_min]) − 0.0010` (10 bps de fricción)
- **Tests:** `pytest tests/test_triad_lookup.py` → **6 passed**. `-k "triad or rotation or entry"` → **30 passed**.

### 1.2 Cifras canónicas de referencia (ANEXO ANTI-ERROR)

Estas son las únicas cifras válidas de la Fase 1. **Cualquier auditoría futura debe partir de aquí**, no de
comentarios ni de reportes previos. Entre paréntesis, cómo se reproduce.

```
· Piernas 13 entidades × 3 escalas ......... 31.431      (zz25 22.143 · zz50 6.341 · zz75 2.947)
· Observaciones tabla v2.0 (HEAD) .......... 83.154      (suma de cells[*].global.n sobre las 238 celdas R4)
· Observaciones tabla v3.1 (ahora) ......... 83.170
· Población para los percentiles ........... 83.183      (inner-joined: amplitud ∩ precio, por entidad)
     composición por entidad: SPY 8.483 · QQQ 6.938 · XLK XLV XLF XLY XLP XLI XLE XLU XLB 6.990 c/u
                              XLRE 2.765 · XLC 2.087   ← peso desigual (3,3× entre el mayor y el menor)
· Celdas R4 ................................ 238         · Total cells en el JSON: 391 (R4 238 · R3 123 · R2 25 · R1 5)
· Mediana de n por celda R4 ................ 107,0       · v2.0 = 107,0  ⇒ SIN CAMBIO
· Celdas R4 global con n < 10 .............. 40          · v2.0 = 40      ⇒ SIN CAMBIO
· Celdas R4 con ≥3 sectores evaluables ..... 101 (N≥20)  · 78 (N≥30)
· Cambio de clase en net_bias (±0,10) ...... 89 de 391 (22,8%)   [±0,05 → 15,6% · ±0,15 → 20,5%]
· Celdas R4 que conservan net_bias exacto .. 49 de 238   · P_bot_5_0 exacto: 65 de 238
· Piernas de duración cero (start==end) .... 4.535       (zz25 17,09% · zz50 9,05% · zz75 6,01%)
· Tamaño del artefacto ..................... 351.702 → 7.221.436 bytes = 20,5×
```

**Cifra INEXISTENTE que circuló y NO debe repetirse: `16.705`.** No aparece en ninguna de las 19 versiones
históricas del artefacto (conteos reales: 0 → 75.534 → 82.524 → 82.991 → 83.154). Su única fuente es un
comentario stale en `entry_report.py:118`. **Es un comentario, no una medición.**

### 1.3 Edges vigentes (los dos juegos que conviven)

```
TABLA (s5_triad_table.json v3.1 · = CANONICAL_BIN_EDGES en el trainer)
  TH [28.6, 55.0, 82.7, 93.3]   FI [20.7, 46.7, 76.6, 90.0]   TW [16.7, 42.3, 74.7, 89.6]

GATE (quality_entry_gate.py:47-57, hardcodeados)
  S5   TH [27.6, 54.8, 82.8, 93.5]   FI [20.0, 46.7, 76.9, 90.4]   TW [16.7, 41.9, 75.0, 90.0]
  SV5  TH [24.6, 37.2, 58.0, 73.8]   FI [27.0, 37.8, 55.5, 68.4]   TW [23.9, 34.5, 50.8, 65.4]

TABLA SV5 (s5v_triad_table.json, todavía v2.0)
  TH [18.2, 33.3, 60.0, 80.0]   FI [20.0, 34.3, 58.8, 76.9]   TW [16.7, 31.0, 54.82, 74.0]
```

---

## 2. DEFECTOS ABIERTOS — con su estado EXACTO

### 🔴 N-1 · La recalibración de los umbrales fue ELIMINADA (valores correctos, mecanismo perdido)

**Estado del valor: CORRECTO.** Verificado: `[28.6, 55.0, 82.7, 93.3]` son **exactamente** los percentiles
P10/P30/P70/P90 de la población del trainer (inner-joined, N=83.183). **No son números arbitrarios.**

**Estado del mecanismo: ELIMINADO.** El bloque que los calculaba ya no existe:

```python
# v2.0 (HEAD) — CALCULABA en cada corrida:
all_th = pd.concat([d["th"] for d in entities.values()])
for name, series in [("TH", all_th), ("FI", all_fi), ("TW", all_tw)]:
    cuts = series.quantile(BIN_PERCENTILES)        # [0.10, 0.30, 0.70, 0.90]
    bin_edges[name] = [round(c, 2) for c in cuts]

# v3.1 (ahora) — LITERAL congelado:
CANONICAL_BIN_EDGES = {"TH": [28.6, 55.0, 82.7, 93.3], "FI": [...], "TW": [...]}
...
"bin_edges": CANONICAL_BIN_EDGES                    # se escribe el literal
```

`git log -S "CANONICAL_BIN_EDGES"` → **vacío: nunca fue commiteado.**

**Evidencia de que el mecanismo SÍ operaba** (historial de los artefactos):

```
S5  TH:  [28.6, 55.0, 82.5, 93.1]  hasta 04-oct  →  [28.6, 55.0, 82.7, 93.3]  desde 07-oct
S5V TH:  [17.7, 33.3, 62.7, 84.6]  hasta 04-oct  →  [18.2, 33.3, 60.0, 80.0]  desde 07-oct
```

⇒ **La consecuencia no es que los valores sean malos: es que no volverán a moverse.** El dato deriva y el
clasificador queda fijo.

**Agravante 1:** el artefacto **sigue declarando** `"bin_percentiles": [0.10, 0.30, 0.70, 0.90]`
(`train_s5_triad.py:602`) — afirmación que ya no corresponde al código.
**Agravante 2:** el desfase con el gate (§N-9) **no puede autocorregirse nunca**, porque ninguno de los dos
lados recalcula.

### 🟡 N-2 · `_documentation.bin_classification` es `null`

v2.0 documentaba `method` + `bin_percentiles` + `bin_labels_meaning`. En v3.1 el bloque desapareció; sólo
queda `taxonomy` (que lista los edges sin explicar su derivación).

### 🔴 N-3 · NO existe validación predictiva fuera de muestra de la tríada

La maquinaria walk-forward/DSR existe pero valida **otras** señales: `walk_forward_rc_rsi_dsr.py` (RC+RSI),
`walk_forward_narrative_dsr.py` (narrativa), `ablation_and_dsr.py`, `hyperparameter_sweep.py`.

Lo que toca la tríada es auditoría de **forma**, no de poder predictivo:
`audit_triad_delta.py` (compara entre revisiones de git), `scratch/audit_triad_sample_size.py` (compara
tamaños de muestra), `test_triad_lookup.py` (6 tests de contrato).

⇒ **Nunca se midió si la tríada predice fuera de muestra.** Es el hueco central (§6, D-5).

### 🟡 N-4 · Los TIERS no tienen derivación documentada

`TIERS = {"Defensive": [XLP,XLV,XLU,XLRE,XLB], "Mixed": [XLE,XLF,XLC], "Cyclical": [XLK,XLY,XLI],
"High-Beta": [QQQ]}` es un **agrupamiento escrito a mano** en el trainer. No existe artefacto que muestre
el clustering del que se derivó. **Son definidos, no derivados.**

### 🟡 N-5 · El umbral `min_n` no cuadra en ninguna de las tres capas

```
trainer v3.1       MIN_N_L1 = 20
_documentation     "exposed if N >= 20"
código (lookup)    default 30   (porque _metadata.hierarchical_fallback no existe en v3.1)
```

### 🔴 N-6 · El auto-retrainer está APAGADO por defecto

`triad_retrainer_provider` corre `train_s5_triad.py` y `train_s5v_triad.py` por subprocess los domingos,
pero está gateado por `ENABLE_TRIAD_AUTORETRAIN`, que **no está definido en ningún `.env`, `.yaml` ni
script del repo** ⇒ default `False`. **La regeneración depende de ejecución manual.**

⇒ El «mejoramiento continuo semanal» que el diseño supone **no ocurre automáticamente hoy**.

### 🟡 N-7 · Los pobladores de `prev_leg_return` ordenan sin desempate

Ambos usan `ORDER BY start_timestamp` **sin tiebreaker**:
- `backend/daemons/zigzag_legs_daemon.py:175-176` → `LAG(...) OVER (ORDER BY start_timestamp)`
- `backend/scripts/populate_prev_leg_all_tickers.py:33` → `ORDER BY start_timestamp ASC`

Y existen **4.534 grupos de empate** en `(ticker, scale, start_timestamp)` (**9.068 filas**), causados por
**4.535 piernas de duración cero**. Ejemplo real (QQQ zz25):

```
1999-03-15 → 1999-03-15   MAX→MIN   43.4032 → 42.0090
1999-03-15 → 1999-03-19   MIN→MAX   42.0090 → 44.8236    prev_leg_return = -0.032122  ✅
```

**Dato hoy: CORRECTO.** Verificado por reconstrucción independiente (derivar con `LAG` y comparar):
orden por `end_timestamp, start_timestamp` → **0 discrepancias en 31.431 filas**.

⇒ Pero con orden por `start_timestamp`, el resultado **no reproduce** el almacenado (~11% de filas
distintas). **Re-ejecutar cualquiera de los dos pobladores cambiaría ~11% del dominó** — y el dominó lo
consume producción: `convergence_compositor.py:339-343` usa `|prev_leg_return|` para
`cascade_conviction_50/75/50to75`.
**Orden canónico medido: `end_timestamp, start_timestamp`.**

### 🟡 N-8 · `same_bar_pair` es una columna huérfana

Es columna real de `market.zigzag_legs` (boolean). En las 13 entidades: **0 NULL, 0 TRUE, 31.431 filas**.
**No aparece en ningún archivo del repo** (barrido de `*.py`/`*.sql`/`*.json`) — **nadie la escribe ni la
lee**. Y **no marca las 4.535 piernas de duración cero**, que es lo que su nombre sugiere.
El `plan_trabajo_depurado` la lista entre las «Columnas confirmadas»: **no confiar en esa lista para esta
columna.**

### 🔴 N-9 · Desfase de edges gate ↔ tabla (medido con dos métodos independientes)

Comparando los edges **leídos del código** contra los **leídos del JSON**, día por día sobre la serie
completa (1980 → 2026-10-12):

```
S5TH   11.539 días  →  149 distintos  (1,29%)    Δmax 1,0 pp
S5FI   11.689 días  →  122 distintos  (1,04%)    Δmax 0,7 pp
S5TW   11.719 días  →  160 distintos  (1,37%)    Δmax 0,4 pp
SV5TH  11.539 días  →  2.362 distintos (20,47%)  Δmax 6,4 pp
SV5FI  11.689 días  →  2.922 distintos (25,00%)  Δmax 8,5 pp
SV5TW  11.719 días  →  3.044 distintos (25,97%)  Δmax 8,6 pp
```

⇒ **Uno de cada cuatro días, la serie SV5 cae en un bin distinto según quién la lea.** Y como ninguno de
los dos lados recalcula (N-1), **el desfase es estructuralmente permanente.**

### 🟡 N-10 · Explosión de tamaño sin carga lazy

351.702 → **7.221.436 bytes (20,5×)**; parse completo **197 ms**, sin carga lazy. Si la Fase 4 replica esto
en S5V, serían ~14 MB.

---

## 3. LAS DOS PREGUNTAS — RESPONDIDAS POR SEPARADO

### PREGUNTA 1 · ¿Qué tests se realizaron en el pasado?

**Suite:** 47 archivos en `tests/`. De esta familia: `test_triad_lookup.py` (6), `test_quality_entry_gate.py`,
`test_rotation_lookup.py`, `test_rotation_metar_service.py`, `test_sector_breadth_gate.py`,
`test_systemic_gatekeeper.py`, `test_volume_breadth_parity.py`, `test_zigzag_hook.py`,
`test_zigzag_kernel_parity.py`.

**Lo que NO existe:**
- **Ningún test de calibración de umbrales** (barrido de `calib|thresh|bin|percent|edge` en `tests/` → cero).
- **Ninguna validación predictiva de la tríada** (§N-3).

**Lo que sí se hizo — auditoría de forma, no de poder predictivo:**
- Comparaciones entre **revisiones de git** (`audit_triad_delta.py`)
- Comparaciones de **tamaño de muestra** por universo (`audit_triad_sample_size.py`)
- **6 tests de contrato/humo**: que el lookup no falle, que el fallback opere, que la dirección se resuelva
- **17 scripts de benchmark** que comparan **versiones del GATE** (V35→V40, master, QQQ gates) — no la tríada

### PREGUNTA 2 · ¿Cómo se determinan umbrales y niveles, y cómo se recalibra?

**Método ORIGINAL (v2.0):** los 4 edges por eje = **percentiles globales 10/30/70/90 de la población
inner-joined** de las 13 entidades, **recalculados en cada corrida**. Eso es lo que define los 5 bins:
`<<` = bajo P10 · `<` = P10–P30 · `~` = P30–P70 · `>` = P70–P90 · `>>` = sobre P90.

**Método ACTUAL (v3.1):** **literal congelado**; el mecanismo se eliminó (§N-1). Los valores son los del
07-oct, ahora fijos.

⇒ **Respuesta: la recalibración dejó de existir.** Antes el umbral seguía al dato; hoy el dato se clasifica
contra constantes. El «mejoramiento continuo» aplicaría a las **probabilidades**, no a los **umbrales** — y
además el retrainer que las recomputaría está apagado (§N-6).

**Sobre los niveles:**
- **5 bins** ← derivan de los 4 percentiles (método documentado, hoy no aplicado)
- **Tiers** ← agrupamiento a mano, sin clustering documentado (§N-4)
- **`min_n`** ← 20 / 20 / 30 según la capa (§N-5)
- **`±0,10` de `net_bias`** (define ACCUMULATION / DISTRIBUTION / NEUTRAL) ← **su derivación NO está
  documentada en ninguna parte.** Es el umbral que hoy mueve 89 celdas. **Debe declararse su origen o
  recalibrarse.** *(Se declara explícitamente en vez de inventar una procedencia.)*

---

## 4. ERRORES VERIFICADOS EN UNA AUDITORÍA PREVIA — NO REPETIRLOS

Una auditoría de Fase 1 (12-oct) afirmó lo siguiente. **Todo fue medido y tres afirmaciones son falsas.**
Se documentan aquí para que el ejecutor no las herede.

| Afirmación auditada | Realidad medida |
|---|---|
| «la mediana de muestra por celda R4 subió de ~20 a 109» | **107,0 → 107,0.** Sin cambio en ningún nivel (R4 107 · tier 88 · R3 201). **Ninguna definición da ~20.** |
| «se eliminó el ruido de muestras pequeñas (N<10)» | **40 → 40.** Idéntico. Nada se eliminó. |
| «al migrar de los 16.705 registros de SPY histórico…» | El baseline real de v2.0 es **83.154**. `16.705` **no existe** en ninguna versión del artefacto (§1.2). |
| «la tabla conserva exactamente el 100% de sus celdas y métricas» | **Falso y robusto:** 89/391 (22,8%) cambian de clase a ±0,10; 15,6% a ±0,05; 20,5% a ±0,15. Sólo **49 de 391** conservan el mismo `net_bias`. |
| `+368.20` vs `+468.20` acciones SPY | **No es contradicción:** `quality_entry_gate.py:39` dice «Logra 468.20 acciones finales de SPY **(+368.20 sobre benchmark)**». Total = 468,20; exceso = +368,20. *(Su vigencia actual es otra cosa: no hay reporte de benchmark que respalde 468,20.)* |
| Separación del nivel Sector = 2,44× | **Cierto**, pero la auditoría **omitió dos advertencias**: la cobertura es **101/238 (42%)** —en más de la mitad de los estados no habrá nivel Sector— y **separación ≠ ganancia predictiva** (ver D-5). |

---

## 5. EL CAMBIO

### 5.1 Cierre de Fase 1 (primero)

1. **Restaurar la derivación dinámica de los edges en `train_s5_triad.py`:**
   `bin_edges = {n: [round(c,2) for c in s.quantile([0.10,0.30,0.70,0.90])] for n, s in [(...)...]}`
   calculados sobre `all_th`, `all_fi`, `all_tw` de las entidades cargadas. **Eliminar `CANONICAL_BIN_EDGES`
   como literal** o dejarlo **solo** como valor de contraste/asserción, nunca como fuente de clasificación.
2. **Reparar el artefacto:** que `bin_percentiles` y `bin_edges` sean **coherentes por construcción**, y que
   `_documentation` recupere el bloque `bin_classification` con el método (percentiles 10/30/70/90 sobre la
   población inner-joined).
3. **Unificar `min_n` en una sola clave**, la que el código lee (`_metadata.hierarchical_fallback.min_n_prefix`).
   Decidir 20 o 30 (ver D-3) y que el `_documentation` cite la misma.
4. **Ninguna cifra del `_documentation` puede contradecir al artefacto.** Corregir el comentario stale
   `16705` de `entry_report.py:118`.

### 5.2 Fase 2 — el adaptador

1. **Extender `TriadSignal` aditivamente** — campos nuevos con `Optional[...] = None`, **sin tocar ni
   renombrar** ninguno de los 19 existentes:
   `ev_net_zz50`, `rr_asymmetry_zz50`, `duration_mean_days`, `fatigue_stage`, `timing_slot`,
   `pct_en_rango`, y el nivel resuelto.
2. **Jerarquía de búsqueda** en `lookup_triad_signal` y `lookup_s5v_triad_signal`:
   `Sector (si N ≥ umbral unificado)` → `Tier` → `Global`.
3. **Etiquetas alineadas con `_documentation`**: `L0` = global · `L1` = tier · `L2` = sector.
   **Mantener intacto el prefijo `R4_/R3_/R2_/R1_`** (dos tests dependen de él).
4. **No cambiar** el espacio de clave `TH_bin|FI_bin|TW_bin|DIR`, ni `bin_labels`, ni la semántica de
   ningún campo preexistente.
5. **Documentar el mapeo real:** hoy el resolutor es `_ETF_TO_TIER_LABEL` (`triad_lookup.py:21-26`), que
   mapea ETF → **tier**. Al añadir el nivel Sector, ese mapa **deja de ser el resolutor principal** y debe
   quedar declarado como fallback, no como ruta.

---

## 6. CRITERIOS DE ACEPTACIÓN (medibles)

```
A-1  Tras el paso 5.1, `pytest tests/test_triad_lookup.py` sigue en 6 passed y NINGÚN test fue modificado.
     (Si alguno tuvo que cambiar, se declara cuál y por qué: es señal de ruptura de contrato.)
A-2  Los edges escritos al artefacto == los percentiles 10/30/70/90 calculados sobre la población del
     trainer, verificado en la MISMA corrida. Reportar los 6 números (3 ejes × 4 cortes) y su n.
A-3  Ningún campo preexistente de TriadSignal cambió de nombre ni de tipo (diff del dataclass).
A-4  El `min_n` efectivo del código == el documentado, y es UN solo número en las tres capas.
A-5  `bin_percentiles` del artefacto describe el método realmente aplicado; `bin_classification` existe
     y no contradice a `bin_edges`.
A-6  Dato de la migración: reportar cuántas celdas y en qué magnitud cambiaron respecto de v2.0
     (medido hoy: 89/391 cambian de clase a ±0,10; 49/391 conservan net_bias). NO se acepta «se conserva
     todo» sin esta medición.
A-7  El nivel `sectors` NO se conecta a ninguna decisión si D-5 no se ha medido (o si D-5 falla). Si se
     decide no conectarlo, se declara explícitamente en el artefacto.
```

### D-5 · El test que decide de verdad (fuera de muestra)

El ratio de separación del nivel Sector (2,44× a N≥20) mide dispersión **dentro** de la celda normalizada
por ruido. **No** mide si resolver en Sector predice mejor que resolver en Tier.

**Antes de que el nivel Sector toque producción:** medir walk-forward si `P_bot` / `lift` resueltos por
sector superan a los resueltos por tier, **fuera de muestra**. Si no superan: el nivel se expone en la
tabla pero **no se conecta a la decisión**, y eso se declara.

**Estado de la validación:** no existe hoy (§N-3). Es el hueco central de toda la Fase 1.

---

## 7. NO ANCLAR (dos caminos deben converger)

Reportar toda resolución por **dos vías independientes**:

1. **Vía código:** qué nivel resolvió cada consulta (`sig.level`) y con qué umbral, para una misma lectura.
2. **Vía tabla:** lectura directa del JSON — qué celda, qué nivel, qué `n`, mismos insumos.

Deben coincidir. Si no coinciden, **se reporta la discrepancia; no se ajusta el código para que cuadre.**

---

## 8. DECISIONES A ADJUDICAR

```
D-1  ¿La tríada ENTRA en la ruta de decisión de producción? Hoy `triad_lookup` no tiene consumidor
     dentro de `backend/modules/` (sólo scripts de auditoría, scorecard y tests). Si el propósito es
     SUSTITUIR, hay que declarar QUÉ se sustituye y con qué contrato de interfaz.
D-2  Nivel Sector: separación medida 2,44× (N≥20), supera el criterio de 2×. Se expone — condicionado a D-5.
D-3  Umbral: 20 (trainer y documentación) vs 30 (código hoy). Con 20 son 101 celdas evaluables; con 30,
     78. El ratio casi no cambia (2,44× vs 2,39×).
D-4  Etiquetas: ¿se renombran a L0/L1/L2 como en `_documentation`? (Recomendado sí: los tests no dependen
     de ellas y hoy conviven tres esquemas.)
D-5  El test fuera de muestra del nivel Sector (ver §6). Es el que decide.
D-6  Origen del umbral ±0,10 de `net_bias`: ¿se declara su derivación o se recalibra? Hoy mueve 89 celdas
     y no tiene procedencia documentada.
D-7  Orden canónico de «pierna anterior»: fijar `end_timestamp, start_timestamp` en LOS DOS pobladores, o
     declarar formalmente cuál es la definición.
D-8  ¿Se reactiva el auto-retrainer (`ENABLE_TRIAD_AUTORETRAIN`)? Hoy está apagado y la regeneración es manual.
```

---

## 9. LO QUE NO ENTRA EN ESTE PROMPT (declarado, para no dispersar)

```
· Fase 4 (S5V): s5v_triad_table.json sigue v2.0 del 07-oct, celdas con una sola clave ['global'], y
  train_s5v_triad.py SIN modificar (git diff en trainers/ sólo lista train_s5_triad.py). Es fase propia.
· Tiebreaker de los pobladores (N-7) y la columna huérfana same_bar_pair (N-8): van a su propio cierre.
· Explosión de tamaño y carga lazy (N-10).
· Unificación de la fuente de edges entre gate y tabla (N-9): el paso 5.1 la hace POSIBLE; ejecutarla
  es un cambio propio, con su propia medición.
```

---

## 10. CIERRE ESPERADO

```
· Fase 1 con umbrales auto-derivados, artefacto coherente consigo mismo, y ninguna cifra que contradiga
  al dato (incluido el comentario stale 16705).
· Cifras de la migración REPORTADAS (A-6), no supuestas.
· D-5 medido antes de que el nivel Sector toque una decisión.
· Fase 2 aditiva, con los 6 tests originales intactos y 1 test nuevo de jerarquía.
· Ninguna afirmación del tipo «se conserva todo» sin la medición que lo respalde.
```
