# GUÍAS — Auditoría de la capa derivada y propuesta de solución · UNA FUENTE DE VERDAD

**Fecha:** 2026-10-05 · **Ámbito:** Botero Trade · Vault `market` + `engine` + `entry_decision`
**Encargo:** auditar CADA punto y **proponer una alternativa de solución**. Read-only hasta adjudicación.

---

## 0 · Cómo trabajar

Todo lo que sigue son **MEDICIONES CERRADAS**, no hipótesis. **No re-descubras: audita y propón.**

- **Read-only.** No modifiques Vault, código ni `.json` hasta que cada punto tenga decisión adjudicada.
- **Ningún query es válido hasta que se EJECUTA.** Pega el query y su salida.
- **Mide la población COMPLETA y declara AMBOS conjuntos antes de comparar.** Los errores de esta semana
  nacieron todos de comparar poblaciones distintas (indicadores vs canónico; `timeframe` omitido; rangos de
  distinta longitud). **Si dos conjuntos no son el mismo, la comparación es inválida.**
- **NO ANCLES.** Donde pido dos caminos, resuélvelos por separado y verifica que **convergen**. Si no
  convergen, **ese es el hallazgo** — repórtalo, no lo promedies.
- **Cotas BILATERALES** en todo umbral (techo Y piso). **Mide MAGNITUD, no sólo conteo.**
- **Umbral sustentado** = imposibilidad física **|** separación de poblaciones **|** decisión declarada.
  **Nada heredado sin medición.**
- **Para cada punto entrega:** `hallazgo → auditoría (hipótesis+método+query+salida) → conclusión →
  PROPUESTA DE SOLUCIÓN (marcada "a adjudicar")`. **Si no se puede cerrar con el dato disponible, dilo.**

**Reglas duras:** DIMENSIONES INVIOLABLES (sólo cambian ESCALAS/edges, nunca bins, etiquetas ni llave) ·
ADDITIVE-ONLY en esquemas · NO BORRADO TOTAL (conservar y migrar lo útil, con evidencia escrita) ·
Regla 22 (nada escrito en el Vault sin verificación) · snapshot de las 3 tablas antes de cualquier commit.

---

## 1 · Estado firme (no re-discutir)

- **El pozo está completo y fiel:** `market.ohlcv_bars` = **6.481.574 barras** · 1927-12-30 → 2026-10-02 ·
  630 tickers. Precios = Yahoo (`auto_adjust=True`) al decimal. **El rebuild NO extendió el histórico antiguo**
  (+490.561 barras son de 2009-2021 y 2026). **Sin duplicados** (`idx_ohlcv_dedup UNIQUE` existe; 0 grupos).
- **Nada salió de circulación:** `S5*` 72→72 · `SV5*` 40→40.
- **Dimensiones intactas:** niveles zigzag 0,025/0,050/0,075 · bordes TH[28,6·55,0·82,5·93,1]
  FI[20,7·46,8·76,5·90,0] TW[16,9·42,4·74,7·89,5] · 566 tickers.
- **La amplitud de PRECIO quedó sana:** sólo **1,7 %** de los días cambia de estado combinatorio
  (S5TH 0,8 % · S5FI 0,4 % · S5TW 0,5 %; 81 estados en ambos lados). **NO es la causa del desajuste.**
- **La corrección de volumen de 2026 fue CORRECTA:** Yahoo confirma el valor NUEVO en **6/6** casos.

---

## 2 · PUNTO 1 — ZIGZAG: dos algoritmos, tres escritores, un ×5 que no debe existir ⚠️ EL MAYOR

### Hallazgo (cerrado)
```
engine.zigzag_points:  362.459  →  1.782.308   (×4,9)   · 539 acciones crecieron · 20 iguales · 7 bajaron
   AMD 941→9.006 (×9,6) · WDC 798→8.962 · MU 879→8.700 · TER 793→8.494 · SWKS 621→8.016
   MSI 292→6.795 · KLAC 730→7.189 · HPQ 567→7.025 · AMAT 750→7.096 · REGN 438→6.377
   SPY 1.321→1.304   ← INTACTO

Sus barras NO cambiaron: AMD 11.731→11.732 (+1) · WDC 12.078→12.079 (+1) · MSI 16.296→16.297
Sus precios coinciden con Yahoo al decimal. Los 3 niveles son los mismos (0,025/0,05/0,075).
```
**Firma inequívoca:** las acciones **volátiles** explotaron ×10; **SPY no se movió**. El `high−low` diario
de AMD/WDC/semis ≈ 3-5 % **> umbral 2,5 %** ⇒ si la detección evalúa el umbral contra `high`/`low`,
**casi toda barra califica como pivote**. El `high−low` de SPY ≈ 1 %, por debajo del umbral ⇒ sólo
disparan giros genuinos. **Coincide con la corrección registrada: "usa high/low".**

**Prueba de orden de magnitud:** 5.162 pivotes / 11.732 barras = **44 % de las barras son pivotes** al
nivel 2,5 % — eso no describe PIERNAS, describe RUIDO. Los 523 viejos = **1 pivote cada 22 barras (~1/mes)**,
el orden correcto para un umbral del 2,5 %.

### Fuentes de verdad (verificado)
```
FUNCIONES:
  A. backfills/backfill_zigzag_points.py:51    zigzag_canonical(high, low, close, level)
  B. scripts/build_zigzag_benchmark.py:49      zigzag(close, min_pct=0.03)        ← otra, sólo close

ESCRITORES de engine.zigzag_points:
  1. backfills/wipe_reload_cascade.py      L183 DELETE por ticker + L440 INSERT    ← producción
  2. backfills/backfill_zigzag_points.py   L191 INSERT                             ← producción
  3. scripts/build_zigzag_benchmark.py     L110 DELETE ★SIN WHERE★ + L165 to_sql   ← ¡BORRA TODO!
```
**Ejecutado:** la canónica sobre los datos actuales de AMD da **9.006** (la base tiene 8.962 ✓). **Ninguna
de las dos funciones reproduce los 941 viejos** ⇒ los escribió un tercer productor (variante anterior).

### Auditar
1. **`git log -p` sobre `zigzag_canonical` y sobre la reorganización `e3d688d`** → localiza el commit exacto
   que introdujo `high`/`low` y **trae el diff**.
2. **Separa las poblaciones**: distribuciones de `swing_days` y `swing_speed` de ambos algoritmos.
   **Sustenta cuál describe piernas y cuál ruido** — con números, no con adjetivos.
3. **¿Qué consumidores leen `zigzag_points`?** Traza cada uno (usa `graphify`) y di cuál se rompe con cada opción.

### PROPUESTA DE SOLUCIÓN (a adjudicar)
- **Un algoritmo, una función, un escritor.** El benchmark escribe en `benchmark.`, nunca en `engine.`.
- **PRUEBA DE FIJACIÓN obligatoria:** el algoritmo elegido debe dejar **SPY ≈ 1.300** y **AMD ≈ 900-1.000**.
  Si no los reproduce, está mal. **Adjunta la salida.**
- **Borra el `DELETE` sin `WHERE`** de `build_zigzag_benchmark.py:110`.
- Propón el **contrato + test** que falle si aparece un segundo escritor de `zigzag_points`.

---

## 3 · PUNTO 2 — `SV5_TURBULENCE` y el umbral V41

### Hallazgo (cerrado) — y una advertencia metodológica
```
La serie SV5TW se EXTENDIÓ: 6.951 barras (1999→2026)  →  11.713 (1980→2026)

Comparación VÁLIDA (mismo período, 2010+):
   media 7,98 → 8,73 (+0,75) · P50 6,69 → 7,60 · P75 10,18 → 10,89 · P90 14,18 → 15,22

Comparación INVÁLIDA (serie completa, poblaciones de distinta longitud):
   media 7,08 → 7,40 · P75 8,81 → 8,82   ← 1980-1998 arrastra hacia abajo
```
**Un informe previo del hilo afirmó `P75 8,90 → 10,10`: NO es reproducible** (comparó poblaciones de
distinta longitud). **Sobre el período comparable el P75 se movió +0,71, no +1,20.**

### Auditar
1. **Re-deriva los percentiles sobre un período DECLARADO y COMPARABLE.** No muevas el umbral a un número
   ajeno: **re-derívalo del dato corregido** y reporta el rango de sensibilidad.
2. **Efecto del gate, bilateral:** con el P75 nuevo ¿qué % de días dispara? ¿y en el piso (P25) y el techo (P90)?
3. **Separa las dos causas del desplazamiento** en dos caminos independientes que deben **converger**:
   (a) el cambio de ventana/universo del recomputo, (b) la corrección del volumen de 2026.

### PROPUESTA DE SOLUCIÓN (a adjudicar)
- **Insertar el umbral como percentil derivado + declararlo**, con su rango de sensibilidad.
- **Cota bilateral:** el gate debe tener techo Y piso medidos, no sólo un umbral de disparo.

---

## 4 · PUNTO 3 — LA BARRA PARCIAL: la puerta está en `ohlcv_provider.py`

### Hallazgo (cerrado) — la puerta, con líneas
```
backend/daemons/vault_providers/ohlcv_provider.py
  L19   _ET = ZoneInfo("America/New_York")
  L20   SESSION_FINAL_ET = dtime(18, 0)    # barra aceptada sólo después de 18:00 ET de ese día
  L21   OVERLAP_DAYS = 7                   # días de calendario re-descargados en cada corrida
  L51   if _already_vaulted_today(store, "ohlcv/update", "BATCH_DONE"): → SKIP del batch
  L133-134  df = yf.download(download_sym, start=last−OVERLAP_DAYS, interval="1d", auto_adjust=True)
  L148  df = _drop_unfinished_session(df)
  L152  revised = _revised_bars(store, ticker, df[df.index <= last_ts])
  L164  store.save_bars(ticker, "1d", revised, overwrite=True)     ← consolida (DO UPDATE)
  L165  _invalidate_snapshots_from(store, ticker, revised.index.min())
  L168  store.save_bars(ticker, "1d", new)                          ← inserta (DO NOTHING)

  L178-182  def _drop_unfinished_session(df):
      """Drop bars whose session date is today (ET) before SESSION_FINAL_ET, or in the future."""
      last_final = now_et.date() if now_et.time() >= SESSION_FINAL_ET else now_et.date() − 1d
      return df[df.index.date <= last_final]

  L185-200  def _revised_bars(store, ticker, fresh):
      """Fresh bars already stored whose VOLUME differs from the stored one (partial or revised).
      Volume is the comparison key on purpose: a dividend re-adjustment rescales prices but not
      volume, so it does not trigger an overwrite of recent bars onto a new price scale."""
      changed = [ts for ts in common if int(fresh.at[ts,"volume"]) != int(stored_vol.at[ts])]
      return fresh.loc[changed]

backend/modules/shared/infrastructure/timescale_data_store.py
  L79-87  def save_bars(..., overwrite: bool = False):
      conflict_sql = ("DO UPDATE SET open=EXCLUDED.open, …, volume=EXCLUDED.volume" if overwrite
                      else "DO NOTHING")
```
**⇒ El diseño que se necesita YA ESTÁ ESCRITO. Falla por dos razones medibles:**
**① La ventana es de TIEMPO y la cadencia es IRREGULAR.**
```
Huecos medidos entre corridas del batch (44 huecos): 1d×16 · 2d×11 · 3d×2 · 4d×2 · 5d×6 · 6d×4 · 7d×1 · 9d×1 · 11d×1
Verificado uno por uno: los huecos de 3-4 días SÍ son fines de semana; los de 5-7 y los de 9 y 11 NO lo son.
```
**⇒ `OVERLAP_DAYS = 7` está en el borde: cualquier hueco >7 (2 de 44) deja barras parciales SIN CURA POSIBLE.**
**② `_revised_bars` sólo dispara si el VOLUMEN difiere** ⇒ una parcial que difiera sólo en precio/high/low
**nunca se corrige.**
**⇒ Resultado medido:** 483 de 506 tickers × **23 días de 2026** con volumen a 6-30 % del real.
Yahoo confirma el valor NUEVO en 6/6 (AAPL 09-16: 3.148.156→35.981.000 · MSFT: 1.172.790→16.670.300 ·
JPM: 537.253→8.303.400 · CAT 10-01: 834.012→2.153.800). **99,66 % de las 4.383.228 barras históricas
comparadas son IDÉNTICAS: sólo 2026 cambió.**

### Auditar
1. **¿Con qué cadencia DEBE correr el daemon?** Mide la actual y **declara qué hueco es aceptable.**
2. **¿Qué consumidores leen barras del día en curso?** Traza quién usaría una parcial para un cálculo live.
3. **Verifica `SESSION_FINAL_ET`:** ¿18:00 ET garantiza que Yahoo ya tiene el volumen consolidado?
   **Mídelo** (compara el volumen a las 18:00 vs T+1 para una muestra).

### PROPUESTA DE SOLUCIÓN (a adjudicar) — la cura por ESTADO, no por ventana
```
1. Columna ADITIVA bar_status ('PROVISIONAL' | 'FINAL') en market.ohlcv_bars.
2. Al escribirla tras 18:00 ET, entra como PROVISIONAL.   (_drop_unfinished_session se MANTIENE ✓)
3. En CADA corrida: re-descargar y sobrescribir TODAS las PROVISIONAL, SIN límite de antigüedad.
   ⇒ cura aunque el daemon se caiga 11 días.
4. Promover a FINAL cuando el valor sea estable en dos corridas consecutivas (regla declarada y medida).
5. FUERA del conjunto PROVISIONAL: seguir comparando por VOLUMEN
   ⇒ así un reajuste por dividendos NO sobrescribe barras viejas con la escala nueva (evita mezclar épocas).
6. _invalidate_snapshots_from se MANTIENE ✓
7. SEÑAL DE FRESCURA: alerta cuando el último bar FINAL tenga más de N días (N medido, no supuesto).
   Hoy el Vault se congela en silencio — y nadie lo notó hasta que apareció el volumen falso.
```
**Regla del usuario, ya validada:** *"siempre sobrescribir desde una vela anterior"* — correcta, pero
**acotada al conjunto PROVISIONAL**, no a las últimas N velas a ciegas (eso arrastraría el problema de
épocas de ajuste que `_revised_bars` evita a propósito).

---

## 5 · PUNTO 4 — La VENTANA de amplitud y el sesgo de membresía (PRE-EXISTENTE)

### Hallazgo (cerrado) — dos afirmaciones refutadas por medición
```
VIEJO (backfills/backfill_breadth_history.py, borrado en fc1e7cc):
   ma = close_df.rolling(window=ma_length, min_periods=ma_length).mean()     ← por Nº DE BARRAS
   AND m.asset_type='STOCK' AND 'SP500' = ANY(m.index_membership)            ← ¡EL MISMO FILTRO!
NUEVO (backfills/rebuild_breadth_history.py):
   WINDOW = "300D"  +  _window_count(obs, WINDOW)                            ← por CALENDARIO
   AND m.update_source = 'vault_ohlcv_bars'                                  ← excluye 0 tickers
```
- **REFUTADO:** el filtro `update_source` **no excluye ningún ticker** (los 506 ya lo tienen) ⇒ efecto nulo.
- **REFUTADO:** el `'SP500' = ANY(index_membership)` **ya estaba** en el script viejo ⇒ **el sesgo de
  supervivencia retrospectiva es PRE-EXISTENTE, no lo introdujo el rebuild.**
- **El único cambio estructural real es la VENTANA.** Con los bloques pre-cinta del pozo (huecos de años con
  `volume=0`), la ventana de **calendario EXCLUYE** las barras del hueco mientras la de **conteo las INCLUYE**
  ⇒ ahí están los **70-77 % de valores diarios** que cambiaron (aunque sólo 1,7 % de días cambia de estado).

### Auditar
1. **Declara la semántica de la ventana.** ¿Qué debe significar "300 días" con huecos: 300 de calendario,
   o las barras existentes en esa ventana? **Mide ambas y compara.**
2. **Cuantifica el sesgo de membresía** en 2000-2008 (356→416 constituyentes con barra, lista ACTUAL aplicada
   al pasado). **¿Es material? Números, no adjetivos.**
3. **¿Qué consumidores dependen del histórico lejano de amplitud?** (el módulo de rotación ¿usa pre-1999?)

### PROPUESTA DE SOLUCIÓN (a adjudicar)
- **Elegir y DECLARAR** la semántica de la ventana, con la medición que la sustenta.
- Si el sesgo es material: **conservar y migrar lo útil** — declarar la limitación del histórico pre-N en el
  registro, y **no** presentarlo como comparable al post-N.

---

## 6 · PUNTO 5 — El RETRAINING que no corrió

### Hallazgo (cerrado)
```
s5_triad_table.json / s5v_triad_table.json:
   "generated_at": "2026-10-01T16:38:39"     ·  "generated_by": "backend/scripts/trainers/train_s5_triad.py"
   "training": { "zigzag_thresholds": [2.5,5.0,7.5], "near_window_bars": 3, "n_observations": 82.991 }
El pipeline master_retrain_pipeline.py fue REWIREADO en b4ff048 (step_1..4 → step_1_breadth_rebuild) ✓
PERO el contenido de las tablas NO cambió (sólo rutas) y generated_at sigue en 01-Oct ⇒ NO se ejecutó.
```
**⇒ La tabla de triado se entrena contra los giros ZigZag — y el zigzag cambió en TODAS las fechas.**

### Auditar
**Orden estricto, no negociable:** (1) arreglar el zigzag → (2) **verificar con la prueba de fijación**
(SPY≈1.300 / AMD≈940) → (3) **SÓLO ENTONCES** re-entrenar (`train_s5v_triad.py && train_s5_triad.py` →
`master_retrain_pipeline.py`) → (4) re-correr los benchmarks v40/v41.
**Recalibrar antes de arreglar el zigzag es calibrar sobre ruido.**

### PROPUESTA DE SOLUCIÓN (a adjudicar)
- **Congelar los benchmarks v40/v41** hasta que el zigzag esté fijado; **dejar escrito** que los resultados
  anteriores son pre-rebuild y no comparables.

---

## 7 · PUNTO 6 — `build_zigzag_benchmark.py` BORRA la tabla de producción
`L110 DELETE FROM engine.zigzag_points` **sin `WHERE`** + `L165 to_sql(..., schema='engine')`. Es huérfano
(nadie lo llama) pero **crea, vacía y reescribe la tabla de producción con OTRO algoritmo**.
**Auditar:** por qué un benchmark escribe en `engine.` · **Proponer:** moverlo a `benchmark.` o eliminarlo,
**migrando lo útil** (su lógica de resumen/validación) y dejando evidencia escrita.

## 8 · PUNTO 7 — `GLOBAL_MIN_N = 100` / `SECTOR_MIN_N = 10`
Heredados de un script **borrado**, **sin test y sin medición**. **Hecho:** ningún sector llega a 100
constituyentes (Technology 93 · Industrials 76 · Financial Services 71 · Healthcare 62 · Consumer Cyclical 56 ·
Consumer Defensive 36 · Real Estate 32 · Utilities 32 · ETF 30 · Communication 25 · Energy 23 · Basic Materials 20)
⇒ el umbral sectorial de 10 es **necesario** (un único 100 habría suprimido TODAS las series sectoriales).
**Auditar:** dispositivo de medición de estabilidad de la amplitud frente a N (100/300/500) sobre las mismas
fechas. **Proponer:** umbral medido o declarado, con su cota bilateral.

## 9 · PUNTO 8 — Los DELISTED y el Security Master
AVB · CTRA · EA · EQR se detectaron **porque falló una descarga**. No hay estado de listado, vigencia del
símbolo, ni identificador estable (FIGI). **Auditar:** cómo se detectó y qué retornos se perdieron.
**Proponer:** estado de listado + identificador estable, **y la decisión de sesgo sin tomar** (Shumway:
¿se carga el retorno terminal o se excluyen esas series del cálculo de anclas?).

## 10 · PUNTO 9 — `forensic_v13_triple_regression.py:71` fabrica VWAP
`calc_vwap` propio con docstring **"Production VWAP"** que fabrica (`close[-1] if len>0 else 0.0`;
`typical[-1]`), y `sigma()` con la **4.ª guarda** `if residual_std <= 0: return 0.0`.
**Auditar:** qué produce hoy y si sus salidas se usaron en alguna decisión.
**Proponer:** que importe el **kernel canónico** (`regression_channel.py::calc_vwap_with_std`, que devuelve
`None` y nunca fabrica) — **la corrección de su docstring es obligatoria.**

## 11 · PUNTO 10 — `signal_adapters.py`: `below_vwap = (…) else False`
Convierte **"no computable"** en **"no está bajo el VWAP"** ⇒ sesga el backtest y no está declarado.
**Auditar:** cuántos casos y en qué fechas. **Proponer:** `Optional[bool]` con `None` propagado, o excluir
esas barras **con la decisión declarada y medida.**

## 12 · PUNTO 11 — Fallbacks `0.0` residuales
`comp = wave_std/tide_std if tide_std > 0.01 else 0.0` · `t_accel/c_accel/w_accel = … else 0.0` ·
`slope_pct = (slope/y_mean*100) if y_mean > 0 else 0.0` (`backfill_channel_snapshots_v2.py` L86).
**Principio:** `0.0` = **sólo neutro medido**; **`NULL` = no computable**.
**Auditar:** cuántas barras afectadas por familia. **Proponer:** `None`/`NULL` y el consumidor que decida.

## 13 · PUNTO 12 — Documentación desactualizada
`AGENTS.md` fila TOTAL declara **~5,80M barras**; el pozo tiene **6.481.574**. Y las series ampliadas
(SV5 a 1980/1972 · S5CAP 7→11 sectores · VBI nueva) deben quedar declaradas con su fecha de corte.
**Proponer:** regenerar las tablas del registro **desde la base**, no a mano.

## 14 · PUNTO 13 — Sin verificar
`engineer_features.py:107,729` y `quaternion_core.py:59`. **Auditar y reportar** (fabricación, guarda, o nada).

## 15 · PUNTO 14 — `channel_snapshots` sin daemon de producción
Ningún daemon llama `compute_channel_snapshot`; **lo que puebla la tabla son los backfills.**
**Auditar:** quién mantiene la tabla viva. **Proponer:** un dueño único declarado.

---

## 16 · ENTREGABLE FINAL — UNA FUENTE DE VERDAD

**Extiende y completa esta tabla, con dueño propuesto, riesgo y mecanismo de cierre:**

| Serie / tabla | Escritores HOY (verificado) | Dueño propuesto | Riesgo |
|---|---|---|---|
| `engine.zigzag_points` | `wipe_reload_cascade` · `backfill_zigzag_points` · `build_zigzag_benchmark` | ? | **alto (×5 hoy)** |
| `market.ohlcv_bars` (S5/SV5/BSI…) | `rebuild_breadth_history` · providers diarios | ? | medio |
| `engine.channel_snapshots` | backfills (ningún daemon) | ? | medio |
| `s5_triad_table.json` / `s5v` | `train_s5_triad` / `train_s5v_triad` | ? | **alto (desfasadas)** |

**Y el MECANISMO DE CIERRE** (obligatorio): contrato + **test que falle si aparece un segundo escritor**.
**Referencia de la casa ya lograda:** el kernel VWAP unificado en
`modules/shared/domain/rules/regression_channel.py::calc_vwap_with_std` — **una sola fuente, devuelve `None`,
nunca fabrica.** **Replica ese patrón.**

---

## 17 · Orden de ataque propuesto (a adjudicar)

**1 → 3 → 5 → 2 → resto.** El **zigzag primero** (todo se calibra contra él); la **barra parcial** en paralelo
(es un defecto de ingesta, independiente); **retraining después del zigzag**; **recalibración al final**.
**Congelar los benchmarks** hasta que el zigzag esté fijado.
