# GUIDANCE — Retirada de `market.ohlcv_bars.vwap`: instrucción de cierre

> **Revisión fija:** `31e4f03` (el commit de la exclusión). Verifícala al empezar y cítala.
> **Este guidance es ejecutable pero ORDENADO.** El orden no es sugerencia: es la salvaguarda.
> La columna debe seguir viva hasta el paso 3. **Si el DDL corre antes de 1 y 2, se rompen 204 archivos.**

---

## 0. ESTADO MEDIDO AL ESCRIBIR ESTO (verifícalo, no lo asumas)

```
✅ HECHO      La exclusión de las 4 features está commiteada en 31e4f03
              engineer_features.py:1284  y  train_meta_model.py:472 (las 2 definiciones)
              → las 4 salen de TODOS los consumidores de modelos

✅ CORRECTO   La columna market.ohlcv_bars.vwap SIGUE EXISTIENDO (660.921 filas con valor)
✅ CORRECTO   Los 4 puntos de código están intactos (el DDL no ha corrido)

⬜ PENDIENTE  ① El comentario en engineer_features.py cita un resultado que el T4 marcó como ruido
⬜ PENDIENTE  ② Los 4 puntos de código
⬜ PENDIENTE  ③ El parquet de preservación (660.921 filas)
⬜ PENDIENTE  ④ El DROP COLUMN
⬜ PENDIENTE  ⑤ La verificación
⬜ APARTE     La decisión sobre trade_count (3 features dependen de él) — NO se ejecuta aquí
```

---

## 1. LA INSTRUCCIÓN, EN ORDEN ESTRICTO

### PASO 1 — Corregir el sustento del comentario (2 líneas, primero, porque es gratis)

Hoy el comentario dice:
```python
# T4 ablation: 3/4 have zero importance, removing all 4 improves Sharpe +0.008, reduces σ.
```
**El propio T4 concluyó "INDISTINGUIBLE from noise (delta < combined std)".** Citar una mejora marginal no significativa como razón de un cambio de código es un fallo de sustento.

**Reescribirlo citando la razón que SÍ se sostiene** (medida y suficiente):
- **Fuga temporal**: `premium == 0.0` ocurre en el 89% de las filas (las sin vwap) y **separa pre-2021 de post-2021** → un árbol puede aprender la época.
- **Cobertura no declarada**: 660.921 / 6.202.372 = **10,7%**, condicionada a que el enriquecimiento de Alpaca haya corrido.
- **Y declarar los caveats**: el T4 corrió sobre un harness de **73 features** (no las 100 del ingeniero) y su delta **no fue significativo** — se excluye **por la fuga, no por la mejora**.
- Aplicar el mismo criterio al comentario espejo en `train_meta_model.py`.

### PASO 2 — Los 4 puntos de código (con la columna TODAVÍA viva)

```
②-a  timescale_data_store.py L147   load_bars SELECT
     quitar `vwap` de la lista de columnas   →  protege los 204 archivos que usan load_bars
②-b  timescale_data_store.py L102/110  save_bars INSERT
     quitar `vwap` del INSERT y del parseo de la fila
②-c  ohlcv_provider.py  el enriquecimiento Alpaca
     retirar la escritura de `vwap` (¿y la de trade_count? → PASO 6, no aquí)
②-d  backfill_trade_count.py  el UPDATE de vwap
     retirarlo o reducirlo a `trade_count` (según PASO 6)
```
**Criterio de cierre del paso 2:** `grep -rn vwap` en esos archivos deja **solo** las referencias a las columnas del lake (`vwap_tide/current/wave`, `vwap_sigma_*`, `vwap_spread_*`) — que son **otra tabla y NO se tocan**.

### PASO 3 — Preservar antes de destruir

Guardar las **660.921 filas** (`ticker`, `time`, `timeframe`, `vwap`) en parquet, con su fecha y el hash de revisión en el nombre o en un sidecar. **Sin esto, la serie no es recuperable desde el vault** (solo desde Alpaca, y con la cobertura que tenga la API hoy).

### PASO 4 — El DDL (solo ahora)

```
ALTER TABLE market.ohlcv_bars DROP COLUMN vwap;
```
Es operación de catálogo (**instantánea**, no reescribe las 6,2M filas). **Requisito de entrada:** pasos 1-3 completos y verificados.

### PASO 5 — La verificación (no se declara hecho sin esto)

```
① La columna ya no existe: information_schema.columns → 0 filas
② Los 204 archivos que usan load_bars siguen funcionando
     → smoke test: load_bars("SPY","1d") devuelve OHLCV correcto y sin la columna vwap
③ La ingesta sigue funcionando
     → smoke test de save_bars con una fila nueva
④ Los conteos de lo que NO se tocó siguen intactos
     → channel_snapshots: 4.594.499 filas · vwap_tide/current/wave al 100%
⑤ Los programas XGBoost cargan y entrenan
     → al menos uno de los 10 (p.ej. train_meta_model.py) corre una época / un fold sin error
⑥ La exclusión sigue vigente: get_feature_columns() ya no contiene las 4
```
**Si cualquiera de los 6 falla → ROLLBACK del paso 4 y reportar.** (El parquet del paso 3 permite reconstruir; por eso va antes.)

### PASO 6 — `trade_count`: **NO se ejecuta en esta instrucción**

3 features dependen de él (`TradeCountRel`, `TradeCountAccel`, `VolPerTrade`) — **ya están excluidas de los modelos** ✓, pero **la columna sigue ahí**. Es una **decisión aparte** (retirarla o reconstruirla desde `volume`). **Se reporta como pendiente declarado, no se improvisa.**

---

## 2. REGLAS DE ESTE EJERCICIO

1. **Orden no negociable**: comentario → código → parquet → DDL → verificación.
2. **La columna sigue viva hasta el paso 4.** Si algo exige tocar datos antes, **parar y reportar**.
3. **No ampliar el alcance**: `trade_count` es otro carril. Las columnas del lake (`vwap_*` de `channel_snapshots`) **no se tocan** — son otra tabla y alimentan a los pretrainers.
4. **Evidencia literal por paso** (comando + salida). Sin salida, no está hecho.
5. **Nada destructivo sin su reverso**: el parquet es el reverso del DDL.
6. **Si un consumidor inesperado lee `df['vwap']` y NO es tolerante, se declara antes de seguir** — no se asume.

---

## 3. ENTREGABLE

```
PASO | ACCIÓN | COMANDO/ARCHIVO | SALIDA LITERAL | ESTADO | OBSERVACIÓN
```
Más:
- **La lista de consumidores inesperados** encontrados (si hubo).
- **Lo que quedó sin verificar** (declarado, con qué haría falta).
- **La confirmación de que `trade_count` queda intacto y marcado como decisión pendiente.**
