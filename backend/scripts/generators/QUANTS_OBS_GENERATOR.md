# `quants_obs.pkl` — Generador Oficial y Tabla de Observación Canónica

**Versión:** 28-Ago-2026 (builder v9 — precursores t-1/t-2 añadidos)
**Generador:** `backend/scripts/generators/generate_quants_obs.py`
**Tests:** `backend/tests/test_quants_obs_builder.py` (7 tests de regresión)
**Artefacto:** `data/research/pivots/quants_obs.pkl` (1,590 pivotes × 165 columnas)

---

## 1. PROPÓSITO (leer primero)

`quants_obs.pkl` es la **tabla de observación canónica** del sistema de señales:
para cada pivote del zigzag SPY (escala zz25), captura el **estado dimensional
instantáneo de 11 estaciones METAR** en ese instante. Es la única tabla sobre la
que el evaluador (`research/01_señales_entry_exit/evaluador_vela_a_vela.py`)
mide el edge real de las 28 señales de entry/exit.

**Principio rector:** la tabla debe ser CORRECTA según la lógica de producción y
REPRODUCIBLE. La fidelidad a artefactos históricos es un *detector de
divergencias*, nunca la meta. Si la lógica de producción y un artefacto viejo
divergen, se usa producción y se documenta la divergencia (clasificación CAT).

**Historia:** el generador original fue un one-off de sesión IA del 17-Ago que
nunca se versionó. El 22-23 de Agosto se reconstruyó como builder versionado,
se auditó 3 veces externamente (Opus vía Antigravity), se le aplicaron 15 fixes
y se promovió a producción el 23-Ago-2026.

---

## 2. CÓMO USAR

### Generar / regenerar la tabla
```bash
cd /root/botero-trade && PYTHONPATH=/root/botero-trade \
  backend/.venv/bin/python backend/scripts/generators/generate_quants_obs.py
# --dry-run: construye y verifica sin escribir el pickle oficial
```
Tiempo: ~40 s. Determinista bit-a-bit.

### Cargarla (camino oficial)
```python
from arnes.datos import cargar_datos   # lee data/research/pivots/quants_obs.pkl
df, spy = cargar_datos()
```
Consumidores reales (24 scripts): arnés de señales, evaluador vela-a-vela,
validador OOS, detector de régimen de crisis, scripts cascade/LDP/conjunción.

### Verificar integridad tras cualquier cambio
```bash
cd /root/botero-trade && PYTHONPATH=/root/botero-trade \
  backend/.venv/bin/python -m pytest backend/tests/test_quants_obs_builder.py -v
```
Si un test falla, la cadena está rota: detener el trabajo sobre señales hasta
diagnosticar. Los tests congelan: esquema 165 columnas (143 base + 22 precursores
`_sk_t1`/`_sk_t2`), pivotes idénticos al repo oficial, state_keys sin huérfanos,
cascade_reversal no inerte (~240 disparos), z_bear consistente con el cal-file,
diamantes no degradados.

### Cuándo regenerar
Cuando el zigzag confirme pivotes nuevos (la tabla crece), cuando cambien los
fact stores o el `cascade_calibration.json`, o tras modificar un LookupAdapter.
Tras regenerar, correr SIEMPRE los tests y revisar la compuerta de deriva
(sección 9 del generador) y el manifiesto de fidelidad.

---

## 3. ESQUEMA DE LAS 143 COLUMNAS

### 3.1 Columnas de pivote (columna vertebral)
| Columna | Definición | Fuente |
|---------|-----------|--------|
| `pivot_date` | Fecha del pivote (UTC naive) | `ZigzagLegRepository.get_confirmed_legs("SPY","zz25")`, ordenado por `start_timestamp` |
| `pivot_type` | `"MAX"` (techo) / `"MIN"` (piso) | `leg.start_type` |
| `prev_leg_return` | Retorno % de la pierna que TERMINA en el pivote | `leg.prev_leg_return` |
| `prev_leg_duration`, `abs_prev_leg_return`, `pivot_year`, `pivot_decade` | Derivadas directas | — |
| `leg_bear` | `pivot_type == "MAX"` (0/1) | derivada |
| `next_bear`, `next_leg_direction` | **Idénticas a leg_bear** — el one-off las nombró mal; se conservan por compatibilidad de esquema | — |
| `duration_bars` | Duración **calendario** de la pierna que ARRANCA en el pivote, piso 1 día (piernas degeneradas) | `leg.end_timestamp - leg.start_timestamp` |
| `daily_return_pct` | Retorno % de la pierna saliente ÷ `duration_bars` | derivada |
| `cascade_50`, `cascade_75` | 1 si el pivote cae a ±3 días calendario de algún pivote zz50/zz75 (proximidad, NO pertenencia — definición de `research/05_precursores_crash/early_warning.py`) | `market.zigzag_legs` |

### 3.2 Columnas por estación (11 × 10 = 110)
Estaciones: `vix`, `vvix`, `pcr` (CBOE_PCR), `fg`, `sv5_turbulence`, `skew`,
`credit` (CREDIT_RATIO), `yield_curve` (YIELD_SPREAD), `rotation`
(ROTATION_INDEX), `bsi` (S5TW), `dxy`.

| Sufijo | Definición |
|--------|-----------|
| `{st}_val` | Close de la serie en la fecha exacta del pivote. **NaN fuera del rango de la serie** (nunca ffill). |
| `{st}_vel` | `serie.diff(3)`; fuera de rango = 0.0 |
| `{st}_vol` | `rolling(2).std() / rolling(10).std()`; fuera de rango = 1.0 |
| `{st}_sk` | State key completo `D1__D2__D3` del LookupAdapter de producción (`lookup_{st}_guidance(val, d3_speed, vol_norm, vol_d3)`) |
| `{st}_n` | Muestra N del estado en el fact store |
| `{st}_d1_vote` | Voto direccional D1 (`d1_directional_vote(state_key)`): −1 / 0 / +1 |
| `{st}_zk_pbull`, `{st}_zk_pbear` | p_bull/p_bear del bloque `zigzag_kinematic.zz25` del fact store |
| `{st}_zz25_pbull`, `{st}_zz25_pbear`, `{st}_ev_net` | Bloque plano zz25 de la guidance del adapter |

**Lectura del state_key:** `sk.split("__")[0]` = D1 (dimensión principal),
`[1]` = D2, `[2]` = D3. Las señales del catálogo leen mayoritariamente solo D1;
`stealth_tail_hedging` lee SKEW D3 (documentado en CAT-A).

### 3.3 Derivadas del cascade (13 columnas)
| Columna | Fórmula | Nota |
|---------|---------|------|
| `d1_bear_5` | `count(voto<0) / n_disponibles` sobre el Grupo A (fórmula exacta de producción: `convergence_compositor.py` L484) | Denominador VARIABLE (2-5) según disponibilidad histórica → ver BS3 |
| `n_stations_a` | Estaciones del Grupo A con voto no-NaN en ese pivote | Permite segmentar por disponibilidad |
| `mean_zk_pbull_A`, `mean_zk_pbull_11` | Media de `_zk_pbull` del Grupo A / de las 11 | — |
| `z_bear` | `(d1_bear_5 − μ) / σ` con μ/σ de `cascade_calibration.json["d1_bear_5"]` | Dinámico: lee el cal-file en cada ejecución |
| `z_dom` | `(abs_prev_leg_return − μ25) / σ25` con stats de `cal["domino_zz25"]` | — |
| `cascade_conviction` | `w_bear·z_bear + w_dom·z_dom` con pesos del `type_mask` del cal-file, **por fila según pivot_type** | — |
| `cascade_conviction_50` | == `cascade_conviction` (c50 del compositor) | Nombre correcto que lee la señal `cascade_reversal` |

---

## 4. DEPENDENCIAS (qué alimenta al generador)

1. **TimescaleDB** (`market.zigzag_legs`, series diarias vía `load_bars`) —
   requiere la base de datos de producción con datos actualizados.
2. **LookupAdapters** de `backend/modules/entry_decision/domain/rules/*_lookup.py`
   — clasifican (val, vel, vol) → state_key con los edges estáticos del fact store.
3. **Fact stores** `backend/modules/entry_decision/domain/rules/{st}_fact_store.json`
   — estados, N, p_bull/p_bear por bloque.
4. **`cascade_calibration.json`** (mismo directorio) — μ/σ de d1_bear_5 y
   domino_zz25, pesos del type_mask, terciles. Se regenera con
   `backend/scripts/generators/generate_cascade_calibration.py`.
5. **`convergence_compositor.d1_directional_vote`** — mapeo D1 → voto.

Si cambia cualquiera de estas fuentes, regenerar y revisar la compuerta de
deriva (sección 9 del generador) + tests.

---

## 5. DIVERGENCIAS CONOCIDAS VS EL ONE-OFF ORIGINAL (no investigar de nuevo)

El pickle original del 17-Ago se conserva en
`data/research/pivots/quants_obs_pre_sustitucion_20260823.pkl`. El generador
emite un manifiesto columna-por-columna
(`data/research/signals/manifiesto_divergencias_quants_obs.json`) con la
clasificación auditada:

- **CAT-A (12 columnas) — artefactos del one-off; se usa lógica de producción:**
  - Skew D1 (8 cols): el one-off usó un clasificador irreproducible (bins D1
    solapados, imposibles con umbral estático; hipótesis trailing rechazada con
    máx 41.9% de match). Producción usa edges estáticos. Afecta el N de
    `panico_total` (34→11) y `skew_paranoia_exit` (26→10).
  - `bsi_d1_vote`: el one-off votaba OVERSOLD_BREADTH=−0.5; producción vota 0.
  - `d1_bear_5/z_bear/cascade_conviction(_50)`: propagación del punto anterior
    (exactamente las 428 filas OVERSOLD = 26.9% → match 73.1%) + F1: z_bear usa
    el cal-file ACTUAL (el one-off tenía calibración obsoleta que invertía el
    signo en 17.9% de las filas).
- **CAT-B (37 columnas) — deriva de versión:** `_zz25_pbull/pbear/_ev_net` de
  todas las estaciones (los fact stores fueron regenerados desde el 17-Ago),
  `rotation_zk_*`, 3 casos de borde en sv5/yield_curve/rotation.
- **CAT-C: ninguna.** Toda divergencia está clasificada. Cualquier CAT-C nueva
  en el manifiesto = detenerse e investigar.

---

## 6. LIMITACIONES CONOCIDAS (auditadas)

1. **F4 — 236 fechas de pivote duplicadas:** el zigzag almacena PIERNAS; dos
   piernas (forward/backward) pueden compartir `start_timestamp`. Propiedad del
   esquema, no bug. Inocuo para las señales actuales; cualquier consumidor que
   haga `groupby(pivot_date)` debe deduplicar.
2. **BS3 — denominador variable de d1_bear_5:** 64.2% de los pivotes tienen <5
   estaciones del Grupo A disponibles (primera fila con 5: 2011-02-18). Esto
   crea un structural break en la escala de z_bear (incrementos de 0.50 con 2
   estaciones vs 0.20 con 5). Usar `n_stations_a` para segmentar; para señales
   de cascade, considerar restringir análisis a post-2011.
3. **BS5 — cobertura de datos:** FG ausente en 64.2% de pivotes (~2011 en
   adelante), Credit/PCR/VVIX ~42% (~2006-07), DXY ~20%. Las señales
   multi-estación operan sobre poblaciones reducidas en la historia temprana.
4. **Look-ahead de los fact stores:** los state keys se calculan con los
   adapters de producción actuales (edges estáticos calibrados con datos
   posteriores). Aceptado para medición post-mortem; para backtesting estricto
   se requerirían edges históricos.

---

## 7. ESTADO DE LAS SEÑALES MEDIDAS SOBRE ESTA TABLA (23-Ago)

- **Núcleo robusto (OOS validado, idéntico en ambas tablas):** `capitulacion`
  (+3.40%), `pcr_put_panic` (+4.04%), `vvix_entry` (+3.11%), `credit_stress`
  (+3.42%), `bsi_washed_out` (+1.73%) — mejores celdas, ver
  `data/research/signals/validacion_oos_catalogo_v7.json`.
- **Diamantes §3.3 (rareza = riqueza, nunca degradar):** `panico_total` (N=11,
  11/11 en régimen de crisis ±3σ, p_raw=7/7 en zz25|ALZA, CI95 CP [0.59,1.0])
  y `skew_paranoia_exit` (N=10, 8/10 en crisis). Análisis individual:
  `data/research/signals/diamantes_analisis_individual.json`.
- **Degradadas:** `breadth_contraction_exit` (structural break interno OOS),
  `credit_ease_exit` (reliquia pre-QE), `bsi_recovery` (post-QE).
- **PROPOSED:** `cascade_reversal` — umbral calibrado −0.957 (congelado),
  edge +0.28% fijo / +0.44% walk-forward rolling p15, p>0.05 → requiere más
  evidencia antes de promoción. Walk-forward:
  `data/research/signals/walkforward_cascade_reversal.json`.

---

## 8. CÓMO AUDITAR ESTE GENERADOR (checklist)

1. **Pivotes:** ¿`pivot_date`/`pivot_type` == `ZigzagLegRepository` zz25?
   (test `test_pivotes_zigzag_oficial`)
2. **State keys:** ¿todo `_sk` existe en su fact store? (test `test_state_keys_sin_huerfanos`)
3. **z_bear:** ¿normalizado con μ/σ del cal-file actual? (test `test_z_bear_consistente_con_produccion`)
4. **Propósito:** ¿las 28 señales disparan? (sección 10 del generador; test
   `test_cascade_reversal_no_inerte`)
5. **Determinismo:** correr dos veces y comparar md5 del pickle.
6. **Deriva:** revisar la sección 9 del output del generador (columnas
   cambiadas vs oficial previo) — tras regenerar con datos nuevos, las únicas
   filas nuevas deben ser pivotes confirmados después de la última ejecución.
7. **Manifiesto:** ¿aparece algún CAT-C? Si sí → investigar antes de usar.

Historial completo de auditorías: `docs/research/10_gate_oos_validation/`
(README índice con los 8 documentos de las 3 rondas externas).

---

## 9. LOS 15 FIXES ACUMULADOS (trazabilidad)

| # | Fix | Fecha |
|:-:|-----|:---:|
| 1 | Columna `cascade_conviction_50` faltante (señal inerte en silencio) | 22-Ago |
| 2 | `d1_bear_5`: media → fracción de presión bearish | 22-Ago |
| 3 | Alineación `_val/_vel/_vol` ffill → fecha exacta, defaults vel=0/vol=1 | 22-Ago |
| 4 | `duration_bars`/`daily_return_pct` → pierna saliente, duración calendario, piso 1 | 22-Ago |
| 5 | `next_bear`/`next_leg_direction` → idénticos a `leg_bear` | 22-Ago |
| 6 | `{st}_zk_pbull/pbear` → bloque `zigzag_kinematic.zz25` del fact store | 22-Ago |
| F1 | μ/σ de z_bear hardcoded → cal-file dinámico (17.9% inversiones de signo → 0%) | 23-Ago |
| F3 | d1_bear_5 Σ(max(0,−v)) → conteo count(v<0) (robustez de dominio) | 23-Ago |
| F4 | 236 fechas duplicadas documentadas con warning activo | 23-Ago |
| F5 | Pesos cascade_conviction hardcoded → type_mask dinámico | 23-Ago |
| F6 | Umbral `cascade_reversal` 0.30 → −0.957 (calibrado, congelado) | 23-Ago |
| BS1 | Pesos de cascade por fila según pivot_type (antes MIN para todos) | 23-Ago |
| BS2 | GRUPO_A hardcoded → unión del type_mask del cal-file | 23-Ago |
| BS3 | Columna `n_stations_a` + structural break documentado | 23-Ago |
| P3+ | `stealth_tail_hedging` (lee SKEW D3) añadida al manifiesto CAT-A | 23-Ago |

---

## 10. ARCHIVOS RELACIONADOS

| Archivo | Rol |
|---------|-----|
| `backend/scripts/generators/generate_quants_obs.py` | Este generador |
| `backend/tests/test_quants_obs_builder.py` | Tests de regresión (7) |
| `data/research/pivots/quants_obs.pkl` | Artefacto oficial |
| `data/research/pivots/quants_obs_pre_sustitucion_20260823.pkl` | One-off original del 17-Ago (referencia de fidelidad) |
| `data/research/signals/manifiesto_divergencias_quants_obs.json` | Manifiesto CAT-A/B/C columna por columna |
| `research/01_señales_entry_exit/arnes/datos.py` | Carga oficial (`OBS_PKL`) |
| `research/01_señales_entry_exit/evaluador_vela_a_vela.py` | Consumidor principal (evalúa señales sobre esta tabla) |
| `docs/research/10_gate_oos_validation/` | Documentación de las 3 auditorías externas |
| `research/11_experimental_engines/regenerar_quants_obs.py` | DEPRECADO 23-Ago-2026 |
