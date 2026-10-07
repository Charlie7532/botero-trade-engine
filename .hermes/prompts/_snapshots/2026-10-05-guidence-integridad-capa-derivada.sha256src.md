# GUÍAS — Integridad de la capa derivada y cierre a UNA FUENTE DE VERDAD

**Fecha:** 2026-10-05 · **Ámbito:** Botero Trade / Vault `market` + `engine`
**Tipo:** auditoría GUIADA (estudio + corrección) · read-only hasta adjudicación

---

## 0. Regla de trabajo

Todo lo de abajo es MEDICIÓN, no hipótesis. Los números están verificados sobre la base viva.
Tu trabajo es **estudiar y proponer**, no re-descubrir. **Sustenta antes de enviar.**

- **NO modifiques nada** del Vault ni del código hasta que cada punto tenga decisión adjudicada.
- **NINGÚN criterio/query es correcto hasta que se EJECUTA** — pega el query y su salida.
- **Mide la población COMPLETA.** Los errores de esta semana nacieron todos de comparar poblaciones distintas
  (indicadores vs canónico, `timeframe` omitido, rangos de distinta longitud). Antes de comparar dos
  conjuntos: **declara ambos y verifica que son el MISMO conjunto.**
- **NO ANCLES:** donde pido dos caminos, resuélvelos por separado y verifica que **convergen**. Si no convergen,
  ese es el hallazgo — repórtalo, no lo promedies.
- **Cotas BILATERALES** en todo umbral (techo Y piso). **Mide MAGNITUD, no sólo conteo.**
- **Todo umbral** debe ser **medido/derivado del dato** o **declarado como decisión**. Nada heredado sin medición.

## 1. Lo que está firme (no re-discutir)

- **El pozo `market.ohlcv_bars` está completo y fiel.** 6.481.574 barras · 1927-12-30 → 2026-10-02 ·
  630 tickers. Los precios coinciden con Yahoo (`auto_adjust=True`) al decimal.
  **El rebuild NO extendió el histórico antiguo** — las +490.561 barras son de 2009-2021 y 2026.
- **Nada salió de circulación:** `S5*` 72 → 72 · `SV5*` 40 → 40.
- **Las dimensiones están intactas:** niveles del zigzag 0,025/0,050/0,075 · bordes de bin
  TH[28,6·55,0·82,5·93,1] FI[20,7·46,8·76,5·90,0] TW[16,9·42,4·74,7·89,5] · 566 tickers.
- **La amplitud de PRECIO quedó sana:** sólo **1,7 %** de los días cambia de estado combinatorio
  (S5TH 0,8 % · S5FI 0,4 % · S5TW 0,5 %), 81 estados en ambos lados. **La amplitud de precio NO es la causa.**
- **La corrección de volumen de 2026 fue CORRECTA:** Yahoo confirma el valor nuevo en **6/6** casos.

---

## 2. PROBLEMA 1 — El ZIGZAG: dos algoritmos, tres escritores, y un ×5 que no debe existir

### Medición (cerrada)
```
engine.zigzag_points:   362.459  →  1.782.308   (×4,9)   · 539 acciones crecieron, 20 iguales, 7 bajaron
   AMD   941 → 9.006 (×9,6)   WDC 798 → 8.962   MU 879 → 8.700   MSI 292 → 6.795
   SPY 1.321 → 1.304   ← INTACTO

Sus barras NO cambiaron: AMD 11.731 → 11.732 (+1) · WDC 12.078 → 12.079 (+1)
Sus precios coinciden con Yahoo al decimal. Los 3 niveles son los mismos.
```
**Firma:** las acciones **volátiles** (semis/hardware) explotaron ×10; **SPY no se movió**.
`high−low` diario de AMD/WDC/semis ≈ 3-5 % > umbral 2,5 % ⇒ **si la detección usa `high`/`low`, casi
toda barra califica como pivote.** El `high−low` de SPY es ~1 %, por debajo del umbral ⇒ sólo disparan
giros genuinos. **Coincide con la corrección registrada a `backfill_zigzag_points.py`: "usa high/low".**

**Prueba de orden de magnitud:** 5.162 pivotes / 11.732 barras = **44 % de las barras son pivotes** al
nivel 2,5 % — eso no es un detector de piernas. Los 523 viejos = **1 pivote cada 22 barras (~1/mes)**,
que es el orden correcto para un umbral del 2,5 %.

### Fuentes de verdad (todas, verificadas)
```
FUNCIONES:
  A. backfills/backfill_zigzag_points.py:51   zigzag_canonical(high, low, close, level)
  B. scripts/build_zigzag_benchmark.py:49     zigzag(close, min_pct=0.03)     ← otra, sólo close

ESCRITORES de engine.zigzag_points:
  1. backfills/wipe_reload_cascade.py        L183 DELETE por ticker + L440 INSERT   ← producción
  2. backfills/backfill_zigzag_points.py     L191 INSERT                            ← producción
  3. scripts/build_zigzag_benchmark.py       L110 DELETE ★SIN WHERE★ + L165 to_sql ← ¡BORRA TODO!
```
El #3 **crea la tabla, la borra completa sin `WHERE` y la reescribe con otro algoritmo**.
Hoy no lo llama nadie, pero existe y cualquiera lo puede correr.

### A estudiar y proponer
1. **¿Cuál es el zigzag operativo?** Sobre `close` (o swing medido close-a-close) o sobre `high`/`low`.
   **Sustenta con separación de poblaciones**, no con opinión: presenta la distribución de
   `swing_days` y `swing_speed` de ambos y di cuál describe PIERNAS y cuál describe RUIDO.
2. **Prueba de fijación (obligatoria):** el algoritmo elegido debe dejar **SPY ≈ 1.300** y
   **AMD ≈ 900-1.000**. Si no los reproduce, el algoritmo está mal.
3. **Un escritor, una función.** El benchmark no debe tocar `engine.`: si es benchmark, escribe en `benchmark.`
4. **`git log -p`** sobre `zigzag_canonical` y sobre la reorganización `e3d688d`: **localiza el commit que
   introdujo `high`/`low`** y trae el diff. Ese es el punto exacto del quiebre.
5. **¿Hubo retraining contra el zigzag nuevo?** No (tablas del 01-Oct). **Confírmalo y cuantifica.**

---

## 3. PROBLEMA 2 — `SV5_TURBULENCE` y el umbral V41

### Medición (cerrada) — y una advertencia metodológica
```
La serie SV5TW se EXTENDIÓ: 6.951 barras (1999→2026)  →  11.713 (1980→2026)

Comparación VÁLIDA (mismo período, 2010+):
   SV5_TURBULENCE   media 7,98 → 8,73 (+0,75) · P50 6,69 → 7,60 · P75 10,18 → 10,89 · P90 14,18 → 15,22

Comparación INVÁLIDA (serie completa, poblaciones de distinta longitud):
   media 7,08 → 7,40 · P75 8,81 → 8,82   ← 1980-1998 arrastra hacia abajo
```
**El P75 (umbral V41 según el informe del hilo) se movió +0,71 sobre el período comparable — no +1,20.**
Un informe previo comparó rangos de distinta longitud y por eso **no es reproducible**.

### A estudiar y proponer
1. **Re-deriva los percentiles sobre un período DECLARADO y COMPARABLE.** No cambies el umbral a un número
   ajeno: **re-derívalo del dato corregido** y reporta el rango de sensibilidad.
2. **Mide el efecto del umbral:** con el P75 nuevo, ¿qué % de días dispara el gate? **Cota bilateral:**
   qué pasa en el piso (P25) y en el techo (P90). **Mide magnitud del cambio de señal, no sólo conteo.**
3. **Separa las dos causas del desplazamiento:** (a) la ventana/universo del recomputo, (b) la corrección
   del volumen de 2026. **Dos caminos independientes que deben converger.**

---

## 4. PROBLEMA 3 — El volumen parcial de 2026 (defecto de ingesta, no de cálculo)

### Medición (cerrada)
```
483 de 506 tickers afectados · 23 días de 2026
El volumen VIEJO tenía 6-30 % del real. Yahoo confirma el NUEVO en 6/6 casos:
   AAPL 09-16: 3.148.156 → 35.981.000   MSFT 09-16: 1.172.790 → 16.670.300
   JPM  09-16:   537.253 →  8.303.400   CAT  10-01:   834.012 →  2.153.800
   XOM  09-23: 12.569.300 = 12.569.300 (ese no cambió)
Histórico: 99,66 % de las 4.383.228 barras comparadas son IDÉNTICAS. Sólo 2026 cambió.
```
**⇒ No fue un error de la corrección: el error estaba en el dato viejo.** El daemon escribió la barra
**a media sesión** y nunca la actualizó.

### A estudiar y proponer
1. **Encuentra la puerta:** ¿qué ruta escribe una barra del día en curso antes del cierre?
   Traza `data_vault_daemon` / `ohlcv_provider` y **nombra la línea**.
2. **Propón el guard** (p. ej. no emitir la barra del día hasta que el volumen sea > X % de la mediana de
   20 días **y** se declare como decisión medida). **Cota bilateral.**
3. **Declara en el Vault** (Regla 22) que el volumen de esos 23 días de 2026 era falso: cualquiera que
   compare un backtest de 2026 contra uno anterior verá el mismo "desastre" sin saber por qué.

---

## 5. PROBLEMA 4 — La ventana de amplitud y el sesgo de membresía (pre-existente)

### Medición (cerrada)
```
VIEJO (backfill_breadth_history.py, borrado en fc1e7cc):
   ma = close_df.rolling(window=ma_length, min_periods=ma_length).mean()   ← por Nº DE BARRAS
   AND m.asset_type='STOCK' AND 'SP500' = ANY(m.index_membership)          ← ¡EL MISMO FILTRO!
NUEVO (rebuild_breadth_history.py):
   WINDOW = "300D"  +  _window_count(obs, WINDOW)                          ← por CALENDARIO
   AND m.update_source = 'vault_ohlcv_bars'                                ← excluye 0 tickers
```
**Dos afirmaciones del informe del hilo quedan REFUTADAS por medición:**
- El filtro `update_source` **no excluye ningún ticker** (los 506 ya lo tienen) ⇒ efecto nulo.
- El `'SP500' = ANY(index_membership)` **ya estaba en el script viejo** ⇒ el sesgo de supervivencia
  retrospectiva **es pre-existente**, NO lo introdujo el rebuild.

**El único cambio estructural real es la VENTANA** (bar-count → 300D calendario). Con los bloques
pre-cinta del pozo (huecos de años con `volume=0`), la ventana de calendario **excluye** las barras del
hueco mientras la de conteo **las incluye** ⇒ ahí están los 70-77 % de valores que cambiaron.

### A estudiar y proponer
1. **Decide la semántica de la ventana y DECLÁRALA.** ¿Qué debe significar "300 días" con huecos:
   300 días de calendario, o las barras existentes en esa ventana? **Mide ambas y compara.**
2. **Cuantifica el sesgo de membresía** (aplicar la lista ACTUAL a todo el histórico) sobre el período
   2000-2008 (356→416 constituyentes). **¿Es material? Sustenta con números, no con el adjetivo.**
3. **¿Se conserva o se corrige?** Si el sesgo es material, propón **conservar y migrar lo útil**:
   nunca borrado total.

---

## 6. PROBLEMA 5 — El retraining que no corrió

```
master_retrain_pipeline.py fue REWIREADO en b4ff048 (step_1..step_4 → step_1_breadth_rebuild) ✓
Pero las tablas siguen con "generated_at": "2026-10-01T16:38:39"  ⇒  NO se ejecutó
s5_triad_table.json / s5v_triad_table.json : su CONTENIDO no cambió (sólo rutas) ⇒ siguen
entrenadas contra el zigzag VIEJO.
```
**⇒ La tabla de triado tiene como OBJETIVO los giros ZigZag (`zigzag_thresholds: [2.5,5.0,7.5]`,
`near_window_bars: 3`, `n_observations: 82.991`) — y el zigzag cambió en TODAS las fechas.**

### A estudiar y proponer
**Orden estricto, no negociable:** (1) arreglar el zigzag → (2) verificar con la prueba de fijación
(SPY≈1.300 / AMD≈940) → (3) **y SÓLO ENTONCES** re-entrenar (`train_s5v_triad.py && train_s5_triad.py`
→ `master_retrain_pipeline.py`) → (4) re-correr los benchmarks v40/v41.
**Recalibrar antes de arreglar el zigzag es calibrar sobre ruido.**

---

## 7. OBJETIVO FINAL — UNA FUENTE DE VERDAD

Hoy **no hay un dueño único por indicador**. Entrega una **tabla de productores y dueños**:

| Serie / tabla | Quién la escribe hoy | Cuántos escritores | Dueño propuesto | Riesgo |
|---|---|---|---|---|
| `engine.zigzag_points` | wipe_reload_cascade · backfill_zigzag_points · build_zigzag_benchmark | **3** | ? | alto |
| `market.ohlcv_bars` (S5/SV5/BSI…) | rebuild_breadth_history · providers diarios | ? | ? | |
| `engine.channel_snapshots` | backfills (ningún daemon de producción) | ? | ? | |
| `s5_triad_table.json` / `s5v` | train_s5_triad / train_s5v_triad | ? | ? | |

Y propón el **mecanismo de cierre** (contrato + test que falle si aparece un segundo escritor).
**Referencia de la casa:** el kernel VWAP ya se unificó en `regression_channel.py::calc_vwap_with_std`
(devuelve `None`, nunca fabrica). **Ese es el patrón a replicar.**

---

## 8. Reglas duras (no negociables)

1. **DIMENSIONES INVIOLABLES.** Sólo cambian **escalas (edges)**, nunca bins, etiquetas ni llave.
2. **ADDITIVE-ONLY** en esquemas. Nada de renombrar/borrar columnas en uso.
3. **NO BORRADO TOTAL.** Conservar y migrar lo útil; evidencia escrita de que la lógica migró.
4. **Regla 22:** nada escrito en el Vault sin verificación.
5. **Todo umbral:** medido/derivado o declarado como decisión. Nunca heredado sin medición
   (el `GLOBAL_MIN_N = 100` es el caso pendiente: hoy no tiene test ni medición).
6. **Auditoría read-only** hasta adjudicación. **Snapshot de las 3 tablas antes de cualquier commit.**

## 9. Entregable

Para **cada** problema: **hipótesis · método · medición (query + salida) · conclusión · decisión propuesta
(marcada "a adjudicar")**. Y **extiende la tabla §7 completa**.
**Si un punto no se puede cerrar con el dato disponible, dilo — no lo rellenes.**
