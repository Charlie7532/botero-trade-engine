# PROMPT DE AUDITORÍA GUIADA — Datos "best-effort" de proveedor y la familia de features `VF_*`

> **Revisión fija:** ejecuta `git rev-parse HEAD` al empezar y **cita el hash en el informe**.
> Sin hash fijo, cualquier "no existe" o "está así" es incomparable. Parte de `04edfaa` (verifícalo).

---

## 0. EL PROBLEMA (planteado)

> ⚠️ **CÓMO LEER ESTA SECCIÓN — es la clave del ejercicio.**
> - Los **NÚMEROS** de aquí son **mediciones de OTRO auditor**, no hechos: son **afirmaciones a reproducir** (T9 las ejecuta una por una).
> - Las **frases interpretativas** («es una fecha disfrazada», «fuga temporal», «feature degradada») son **la lectura del auditor que escribe este prompt**: son **hipótesis a REFUTAR**, no conclusiones.
> - **No te doy los resultados esperados.** Si te los doy, la validación no sirve. Si algo de esta sección no se sostiene al medirlo, **ese es el hallazgo**.

En este repo conviven **dos cosas distintas que se llaman "vwap"** y se han estado confundiendo:

**(A) El VWAP de la vela** — `market.ohlcv_bars.vwap` (y su gemelo `trade_count`).
- Es un **dato PRIMITIVO**: el VWAP *del día* (Σ(precio×vol)/Σ(vol) **dentro** del día).
- **NO es derivable del OHLCV diario** (requiere intradía).
- Procede de un **enriquecimiento "best-effort" de Alpaca** (`daemons/vault_providers/ohlcv_provider.py`, comentario literal: *"Best-effort enrichment with Alpaca trade_count and vwap"*).
- **Cobertura medida hoy: 660.921 / 6.005.907 filas = 11,0%** — **caótica por ticker**:
  AAPL y MSFT desde 2021-04-30 · COST desde 2026-07-17 · SPY desde 2026-05-18 · **XOM: nunca**.
- **`vwap` y `trade_count` tienen cobertura IDÉNTICA** (660.921 cada uno; 0 filas con una y no la otra) → vienen del mismo enriquecimiento.
- El **Wipe & Reload** (`wipe_reload_cascade.py`) inserta `NULL` en ambas → **los tickers recargados quedan 100% NULL**.

**(B) Los tres VWAP del canal** — `channel_snapshots.vwap_tide/current/wave` (y `vwap_sigma_*`).
- Son **INDICADORES DERIVADOS**: VWAP rodante de la MISMA fórmula con **tres ventanas**: `tide=240`, `current=60`, `wave=auto (max(10, min(ciclo_dominante, 60)))`.
- Se calculan **exclusivamente de `(close, high, low, volume)`** (`compute_channel.py::_calc_vwap_with_std`).
- **NO usan la columna (A)** → el canal y el EV de Tide son **independientes** de Alpaca.
- Cobertura: **100%**.

**Y aquí está el problema que motiva esta auditoría:**

La columna (A) **sí entra a modelos entrenados**. La cadena es:
```
engineer_features.py::get_feature_columns()      # L1282
    prefixes = ('FD_','MS_','TS_','CS_','VF_','MC_','OV_','CAL_','IM_','RG_','MTF_','BA_','ST_','NP_')
    return [c for c in df.columns if c.startswith(prefixes)]
        ↓
    feature_cols → X_train/X_test
        ↓
speculative_qualifier.py:113 · qualify_ticker.py:233 · quality_qualifier.py:104 · oracle_backtest.py:402
        ↓
    GBM / redes secuenciales (modelos que califican tickers)
```
Dentro de esa lista está **`VF_VWAPPremium_ZScore`** (prefijo `VF_`), que **se afirma** construida así:
```python
premium = pd.Series(0.0, index=df.index)          # las filas SIN vwap quedan en 0.0 EXACTO
premium[has_vwap] = (close - vwap) / vwap          # solo el 11% tiene valor real
prem_mean = premium.rolling(50).mean()
prem_std  = premium.rolling(50).std().clip(lower=1e-8)
df['VF_VWAPPremium_ZScore'] = (premium - prem_mean) / prem_std
```
→ **Interpretación del auditor que escribe este prompt (A REFUTAR, no a asumir):** que `premium == 0.0` funcione como **fecha disfrazada** (pre-2021 vs post, enriquecido vs no, recargado vs no) y que un árbol pueda partir por ese cero y **aprender la época** (fuga temporal). **Es una hipótesis: T3 y T4 existen para tumbarla o sostenerla.**

Y hay **dos features hermanas** con el mismo enriquecimiento y patrones de relleno semejantes:
`VF_TradeCountRel_ZScore` (L298-306) y `VF_TradeCountAccel_ZScore` (L311+) — con `fillna(0)` / `fillna(1).clip(lower=1)`.

**La pregunta de fondo (aquí está la perspectiva amplia):**
> ¿Es este un caso aislado del `vwap`, o es **una clase**? Es decir:
> **¿cuántos datos del vault tienen cobertura condicionada a un proveedor "best-effort", cuántas features se construyen sobre ellos con rellenos que borran la diferencia entre "no hay dato" y "vale 0", y cuántas de esas features son entradas reales de modelos?**

---

## 1. HIPÓTESIS A CONTRASTAR (no a confirmar — a refutar si se puede)

| # | Hipótesis | Se refuta si... |
|---|---|---|
| **H1** | Solo `VF_VWAPPremium_ZScore` + las 2 de `trade_count` están afectadas. | Existen más features de otros prefijos que consumen columnas con cobertura condicionada. |
| **H2** | Los ceros de relleno actúan como **proxy temporal** explotable por los modelos. | "El feature vale exactamente 0" no predice la época mejor que el azar. |
| **H3** | El patrón `fillna(0)` + `rolling().std().clip(lower=1e-8)` se repite en otras `N` features. | El patrón es único de esa familia. |
| **H4** | Otras familias de datos (no vwap/trade_count) tienen también cobertura **condicionada al proveedor**. | Todas las columnas de `ohlcv_bars`/`channel_snapshots` tienen cobertura ~100% o son intencionalmente escasas y declaradas. |
| **H5** | La cobertura de esos datos **no está declarada ni validada** en ningún sitio (ni constraint, ni check, ni doc). | Existe documentación/validación que ya la declara. |
| **H6** | Quitar esas features de `feature_cols` **cambia** el comportamiento de los modelos de forma medible. | La importancia/el aporte de esas features es indistinguible de ruido (o exactamente 0). |

---

## 2. TAREAS (cada una con su método y su evidencia)

**T1 · Inventario de la entrada real de los modelos**
Ejecuta `get_feature_columns()` sobre los mismos DataFrames que usan los 4 consumidores. Reporta: **número total de features**, el desglose **por prefijo**, y la lista completa. Evidencia: el output literal.

**T2 · Provenance y cobertura por feature**
Para **cada** feature, traza:
 (a) qué columnas de entrada consume (leyendo el código de construcción, línea a línea);
 (b) su **cobertura** (% no-NA) y, cuando aplique, **qué fracción de sus valores es exactamente 0 / exactamente el valor de relleno**;
 (c) el patrón de relleno usado (`fillna(0)`, `fillna(1)`, `clip(1e-8)`, `ffill`, `interpolate`, …).
Salida: tabla. **No enumeres "las que recuerdes": genera la lista programáticamente desde `df.columns`.**

**T3 · El test de "el valor de relleno es una fecha"** (el decisive para H2)
Para cada feature afectada: toma la máscara `feature == valor_de_relleno` y mide si esa máscara **separa poblaciones temporales** (p. ej. distribución de la máscara por año; AUC de predecir "año ≥ 2021" con esa máscara; concentración por ticker).
**Criterio de sustento:** separación de poblaciones medible y grande (no "se ve claro").

**T4 · El test de fuga en el modelo** (para H2/H6)
Con el pipeline real (walk-forward, `SEQ`, `TRAIN`, `TEST`, `PURGE` tal como están en el código):
 (a) mide la **importancia** de las features afectadas;
 (b) repite el entrenamiento **sin** ellas y compara métricas out-of-sample.
**Si el resultado cambia, no concluyas "mejora": concluye "cambia" y cuantifícalo.** Si no puedes correrlo completo, decláralo como **no resuelto** en vez de inferirlo.

**T5 · Censo de datos con cobertura condicionada al proveedor** (la perspectiva amplia)
Barre `market.ohlcv_bars` y `engine.channel_snapshots`: para **cada columna**, la cobertura global, **por ticker** y **por año**. Señala toda columna cuya cobertura **no sea ~100% ni escasa-por-diseño** y explique *por qué* es escasa si lo es (¿intradía? ¿proveedor? ¿histórico?).
Prohibido: elegir las columnas a mano. Barrido completo por familia.

**T6 · Mapa de consumidores**
Para cada dato/feature afectado, traza **hasta el final**: quién lo lee, quién lo transforma, y si llega a una **decisión** (calificación de ticker, entrada, sizing). Un hallazgo sin consumidor trazado es un hallazgo incompleto.

**T7 · Declaración y validación**
Verifica si existe **algún** sitio donde la cobertura/semántica de estos datos esté declarada: constraints, `CHECK`, comentarios de tabla, docstrings, validaciones de ingesta. Si no existe: dilo explícitamente ("nada lo declara").

**T8 · Clase vs caso aislado** (la pregunta de fondo)
Con todo lo anterior: responde con evidencia si esto es **un caso del vwap** o **una clase de datos**. Cuantifica: ¿cuántos datos? ¿cuántas features? ¿cuántos entran a modelos?

**T9 · Reproduce las mediciones de la sección 0** (una por una, con su query)
```
Afirmación | Query ejecutada | Resultado HOY | ¿Coincide? | Corrección
```
Si alguna **no coincide** → **ese es el hallazgo prioritario**. Si alguna no se puede ejecutar, dilo y por qué.

---

## 2-bis. SECCIÓN DE AUSENCIAS (la parte de mayor rendimiento)

*"Lo que el artefacto NO dice."* Obligatoria. Probes sugeridos — mide cada uno:

- **Dividendos, no solo splits**: ¿qué pasa con el ajuste por dividendo en las series y en sus derivados?
- **Invalidación en CASCADA frente a capas derivadas**: al recargar `barras → snapshots → zigzag → observer → fact stores`, ¿qué se invalida y **quién** lo hace? ¿Y las cachés (L1/Redis) delante de cada capa?
- **Sincronía lago-a-lago**: ¿existen estados donde dos lagos discrepan sin que nadie lo detecte?
- **Semántica de estados y quién los cambia**: los flags (`update_source`, `active`, …) ¿quién los escribe y quién los lee?
- **Salidas derivadas ya consumidas**: si un dato cambia, ¿qué outputs **ya usados** (modelos entrenados, tablas materializadas) quedan inválidos y nadie regenera?

---

## 3. CRITERIOS DE SUSTENTO (aplican a CADA afirmación)

Un umbral o una conclusión solo se sostiene por **una de estas tres vías**:
1. **Imposibilidad física/matemática** (p. ej. un subnormal por debajo del mínimo del tipo).
2. **Separación de poblaciones medida** (las dos poblaciones no se solapan, con la métrica declarada).
3. **Decisión declarada como tal** ("elegimos X porque Y" — explícitamente marcada como decisión, no como dato).

Cualquier afirmación que no cumpla una de las tres: **márcala como "no sustentada"**.

**Cuidado con los sesgos ya registrados en este proyecto:**
- Mide **la población COMPLETA**, no una muestra sesgada (ya cometimos 3 errores por medir el conjunto equivocado).
- Ojo con los filtros `>=` vs `>` y con las **cotas bilaterales** (techo **y** piso).
- Mide **magnitud**, no solo conteo.
- Verifica **por familia de columnas**, nunca por enumeración manual de una lista corta.
- Distingue **OMISIÓN** (no está) de **SCOPE** (está pero fuera del alcance declarado).

---

## 4. REGLAS DE ESTA AUDITORÍA

1. **NO modifiques nada.** Ni código, ni datos, ni esquema. Solo lectura y medición.
2. **Evidencia literal por afirmación**: la query/comando **y** su output. Sin output, no hay afirmación.
3. **No ancles**: valida cada hipótesis por **dos caminos independientes** (lectura de código **y** medición de datos) que deben **converger**. Si divergen, el hallazgo es la divergencia.
4. **Analítico, no rápido**: es preferible "no resuelto, falta X" que una conclusión sin sustento.
5. **Nada de complacencia**: si algo contradice lo que ya creías (o lo que dicen los informes previos), **el dato manda**.
6. **LEY 1 — sin medición no hay conclusión.** Y con el MISMO peso: **«esto NO es un problema» exige EXACTAMENTE la misma evidencia que «esto SÍ lo es».** Sin esa evidencia, es una hipótesis pendiente disfrazada de veredicto.
7. **LEY 2 — ningún criterio es correcto hasta que se EJECUTA.** Un SQL escrito es una hipótesis; solo su ejecución es verificación.
8. **No te doy las respuestas esperadas.** Te doy el MÉTODO y las PREGUNTAS.
9. **Sé el escéptico del propio prompt**: si algo de la sección 0 no se sostiene al medirlo, ese es el hallazgo.

---

## 5. ENTREGABLE

Informe con esta estructura, por cada hallazgo:
```
HALLAZGO: <una frase>
EVIDENCIA: <comando/query + output literal>
POBLACIÓN MEDIDA: <cuántas filas/tickers, y por qué esa es LA población>
SUSTENTO: <una de las 3 vías>
CONSUMIDOR FINAL: <a qué decisión/modelo llega>
ESTADO: confirmado | refutado | no resuelto (y qué falta)
```
Además, **dos listas separadas**:
- **«Afirmaciones que NO debí hacer sin medir»** (del propio informe).
- **«No verificable aquí»** — declarado, con lo que haría falta para verificarlo.

Y al final, tres respuestas cortas:
1. **¿Caso aislado o clase?** (con el número que lo sostiene)
2. **¿Cuántas features entran a modelos con relleno que disfraza "sin dato"?**
3. **¿Cuál de las hipótesis H1-H6 queda sin resolver y qué medición falta para resolverla?**

---

*P.D. — Recuerda fijar el hash de revisión antes de empezar. Hoy los informes se han comparado contra estados distintos y eso ya costó conclusiones inválidas.*
