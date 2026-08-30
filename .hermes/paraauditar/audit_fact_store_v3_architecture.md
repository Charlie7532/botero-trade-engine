# Auditoría Cruzada: `fact_store_v3_architecture.md` vs Código Real

> **Scope:** Verificar que cada afirmación del documento corresponde a la realidad del código fuente
> (generadores, engine, fact store JSONs, compositor, y políticas).
> **Fecha:** 2026-08-20 | **Auditor:** Automated cross-reference

---

## Resumen Ejecutivo

| Categoría | Correctas | Incorrectas | Parciales | N/A (aspiracional) |
|---|:---:|:---:|:---:|:---:|
| Arquitectura general | 12 | 0 | 1 | 0 |
| Fórmulas matemáticas | 9 | 0 | 1 | 0 |
| D1 Labels (11 estaciones) | 3 | **8** | 0 | 0 |
| D2/D3 Labels | 2 | 0 | 0 | 0 |
| Estructura del JSON | 6 | 0 | 0 | 0 |
| Campos de Addendums 1-7 | 0 | 0 | 0 | **7** |
| Conteos (estaciones, estados) | 5 | 0 | 0 | 0 |
| **TOTAL** | **37** | **8** | **2** | **7** |

> [!CAUTION]
> **8 de 11 tablas de D1 Labels están desincronizadas con los generadores.** Esto es el hallazgo más crítico — el documento muestra labels que NO coinciden con lo que producen los generadores actualmente.

---

## 1. Hallazgos Críticos: D1 Labels Incorrectos

La tabla de la Sección 4.2 (líneas 262-274) muestra D1 Labels por estación. Comparación contra los `D1_LABELS` definidos en cada `generate_{station}_fact_table.py`:

| Estación | Doc dice | Generador produce | Veredicto |
|---|---|---|:---:|
| **VIX** | `EXTREME_COMPLACENCY, LOW_VOL, MODERATE_VOL, HIGH_VOL, ELEVATED_PANIC, EXTREME_PANIC` | Idéntico | ✅ |
| **BSI** | `BREADTH_WASHED_OUT, DEPRESSED_BREADTH, NEUTRAL_LOW, NEUTRAL_HIGH, BREADTH_RECOVERY, HYPER_EXPANSIVE` | `BREADTH_WASHED_OUT, OVERSOLD_BREADTH, NEUTRAL_LOW_BREADTH, NEUTRAL_HIGH_BREADTH, EXPANSIVE_BREADTH, HYPER_EXPANSIVE_BREADTH` | ❌ **5/6 distintos** |
| **F&G** | `EXTREME_FEAR, FEAR, NEUTRAL_FEAR, NEUTRAL_GREED, GREED, EXTREME_GREED` | `EXTREME_FEAR, FEAR, NEUTRAL_FEAR, GREED, EXTREME_GREED, EUPHORIA` | ❌ **3/6 distintos** |
| **Credit** | `EXTREME_STRESS, CREDIT_STRESS, STABLE_CREDIT, ELEVATED_CREDIT, CREDIT_EASING, CREDIT_EUPHORIA` | `EXTREME_STRESS, CREDIT_STRESS, ELEVATED_CREDIT_STRESS, STABLE_CREDIT, CREDIT_EASE, DEEP_CREDIT_EASE` | ❌ **4/6 distintos** |
| **Rotation** | `EXTREME_DEFENSIVE, DEFENSIVE, NEUTRAL_ROTATION, MODERATE_RISK_ON, AGGRESSIVE_RISK_ON, EXTREME_RISK_ON` | `EXTREME_DEFENSIVE, DEFENSIVE, NEUTRAL_ROTATION, BALANCED, CYCLICAL_LEADERSHIP, EXTREME_OFFENSIVE` | ❌ **3/6 distintos** |
| **PCR** | `EXTREME_CALL_DOMINANCE, LOW_PCR, NEUTRAL_PCR, ELEVATED_PCR, HIGH_PCR, EXTREME_PUT_PANIC` | `EXTREME_CALL_EUPHORIA, CALL_EUPHORIA, NEUTRAL_PCR, ELEVATED_PCR, HIGH_PUT_PANIC, EXTREME_PUT_PANIC` | ❌ **3/6 distintos** |
| **VVIX** | `EXTREME_COMPLACENCY, LOW_VVIX, MODERATE_VVIX, HIGH_VVIX, ELEVATED_VVIX, EXTREME_VVIX` | Idéntico | ✅ |
| **SV5 Turb** | `LOW_TURBULENCE, MODERATE_LOW, MODERATE_TURBULENCE, HIGH_TURBULENCE, ELEVATED_TURBULENCE, EXTREME_TURBULENCE` | `EXTREME_CALM, LOW_TURBULENCE, MODERATE_TURBULENCE, HIGH_TURBULENCE, ELEVATED_TURBULENCE, EXTREME_TURBULENT` | ❌ **3/6 distintos** |
| **SKEW** | `LOW_TAIL_RISK, MODERATE_TAIL, NEUTRAL_TAIL, ELEVATED_TAIL_RISK, PARANOIA, EXTREME_PARANOIA` | `LOW_TAIL_RISK, NORMAL_TAIL_RISK, ELEVATED_TAIL_RISK, HIGH_TAIL_RISK, PARANOIA, EXTREME_PARANOIA` | ❌ **3/6 distintos** |
| **Yield** | `DEEP_INVERSION, MILD_INVERSION, FLAT_CURVE, NORMAL_CURVE, STEEPNING_CURVE, STEEP_CURVE` | `DEEP_INVERSION, MODERATE_INVERSION, FLAT_CURVE, NORMAL_CURVE, STEEPNING_CURVE, EXTREME_STEEPNING` | ❌ **2/6 distintos** |
| **DXY** | `DEEP_DOLLAR_CRUSH, LOW_DOLLAR, MODERATE_LOW_DOLLAR, MODERATE_HIGH_DOLLAR, ELEVATED_DOLLAR_STRESS, EXTREME_STRENGTH` | `DEEP_DOLLAR_CRUSH, WEAK_DOLLAR, MODERATE_LOW_DOLLAR, MODERATE_HIGH_DOLLAR, ELEVATED_DOLLAR_STRESS, EXTREME_STRENGTH` | ❌ **1/6 distinto** |

> [!IMPORTANT]
> **Solo VIX y VVIX coinciden al 100%.** Las 9 restantes estaciones tienen labels documentados que difieren del código. El convergence compositor ([`convergence_compositor.py`](file:///root/botero-trade/backend/modules/entry_decision/domain/services/convergence_compositor.py) L125-152) usa los labels del **generador** (correctos en producción), no los del documento.

---

## 2. BSI Ticker: Doc dice S5FI, generador usa S5TW

El documento (línea 248, 618) indica:
> BSI: `val = 7.8` (% de acciones del S&P 500 sobre su media de **50 días**)
> Ticker Vault: `S5FI` (breadth)

Pero el generador [`generate_bsi_fact_table.py`](file:///root/botero-trade/backend/scripts/generators/generate_bsi_fact_table.py#L18-L19) dice:
```python
ticker = "S5TW"  # S5TW = % above 20-day MA, NOT S5FI (50-day MA)
```

Y el fact store JSON confirma: `model_purpose: "METAR Station: BSI (S5TW)"`.

> [!WARNING]
> **S5FI** = porcentaje sobre media de **50 días** (Intermediate). **S5TW** = porcentaje sobre media de **20 días** (Tactical). Son indicadores DIFERENTES con interpretaciones distintas. El documento describe el indicador equivocado.

---

## 3. Fórmulas Matemáticas — Verificación contra Engine

### 3.1 Bayesian Laplace Shrinkage (m=10) ✅

**Doc (línea 413-415):**
```
P_smooth = (n_pos + 10 x 0.50) / (N + 10)
EV_smooth = (N / (N + 10)) x EV_sample
```

**Engine ([v3_fact_table_engine.py](file:///root/botero-trade/backend/scripts/_lib/v3_fact_table_engine.py#L74-L82)):**
```python
def bayesian_shrink_p(n_pos, n_tot, p0=0.50, m=10.0):
    return (n_pos + m * p0) / (n_tot + m)

def bayesian_shrink_ev(ev_sample, n_tot, ev0=0.0, m=10.0):
    credibility = n_tot / (n_tot + m)
    return credibility * ev_sample + (1.0 - credibility) * ev0
```

**Veredicto:** ✅ Las fórmulas coinciden exactamente.

---

### 3.2 D1 — Expanding Window Rank ✅

**Doc (línea 251-258):** Dice expanding window percentile rank con zero look-ahead bias, clasificado contra bordes sigma.

**Engine ([L471-481](file:///root/botero-trade/backend/scripts/_lib/v3_fact_table_engine.py#L470-L481)):**
```python
d1_expanding_rank = ind_df["val"].expanding(min_periods=252).rank(pct=True)
ind_df["bin_d1"] = d1_expanding_rank.apply(
    lambda r: classify_value(r, PERCENTILES_D1_GAUSS, d1_labels)
)
```

**Veredicto:** ✅ El expanding rank se aplica al valor crudo, y luego el rank (0-1) se clasifica contra los umbrales sigma `[0.0228, 0.1587, 0.5, 0.8413, 0.9772]`. Zero look-ahead garantizado.

---

### 3.3 D2 — Velocity diff(3) ✅

**Doc (línea 278):** `vel = val[t] - val[t-3]`

**Engine ([L464](file:///root/botero-trade/backend/scripts/_lib/v3_fact_table_engine.py#L464)):**
```python
ind_df["d2_velocity"] = ind_df["val"].diff(3)
```

**Veredicto:** ✅ Coincide exactamente.

---

### 3.4 D3 — Vol Ratio std(2d)/std(10d) ✅

**Doc (líneas 235, 298):** `vol = std(val, 2d) / std(val, 10d)`

**Engine ([L466-468](file:///root/botero-trade/backend/scripts/_lib/v3_fact_table_engine.py#L466-L468)):**
```python
vol_2d = ind_df["val"].rolling(2).std()
vol_10d = ind_df["val"].rolling(10).std().replace(0, np.nan)
ind_df["vol_norm"] = (vol_2d / vol_10d).fillna(1.0)
```

**Veredicto:** ✅ Correcto. Usa std(2d)/std(10d) como el doc V1.1 indica.

---

### 3.5 D2/D3 Edge Computation — Parcial ⚠️

**Doc (línea 284):** "Percentiles Gaussianos sobre la **poblacion historica completa**"

**Engine ([L473-477](file:///root/botero-trade/backend/scripts/_lib/v3_fact_table_engine.py#L473-L477)):**
```python
calib_df = ind_df[pd.to_datetime(ind_df.index) >= "2011-02-01"] if station_name.lower() == "skew" else ind_df
d2_edges = calib_df["d2_velocity"].dropna().quantile(PERCENTILES_D2_GAUSS)
d3_vol_edges = calib_df["vol_norm"].dropna().quantile(PERCENTILES_D3_GAUSS)
```

**Veredicto:** ⚠️ Parcialmente correcto. La afirmacion de "poblacion historica completa" es verdad para 10/11 estaciones, pero SKEW tiene un corte en 2011. El documento no menciona esta excepcion.

---

### 3.6 Operational Guidance — Composite EV ✅

**Doc (línea 601):**
> EV compuesto = `0.3 x EV_1d + 0.4 x EV_3d + 0.3 x EV_5d`

**Engine ([L358](file:///root/botero-trade/backend/scripts/_lib/v3_fact_table_engine.py#L358)):**
```python
composite_ev = 0.3 * ev_1d + 0.4 * ev_3d + 0.3 * ev_5d
```

**Veredicto:** ✅ Coincide exactamente.

---

### 3.7 Cascade Conviction — Ventana de +-3 dias ✅

**Doc (lineas 338-350):** Ventana de `range(-3, +4)` (+/-3 dias)

**Engine ([decay_check_cascade_conviction.py](file:///root/botero-trade/backend/scripts/_lib/decay_check_cascade_conviction.py#L115-L119)):**
```python
df25["cascade_50"] = df25["pivot_date"].apply(
    lambda d: int(any(d + timedelta(days=i) in starts50 for i in range(-3, 4)))
)
```

**Veredicto:** ✅ Correcto. `range(-3, 4)` = [-3, -2, -1, 0, 1, 2, 3] = +/-3 dias.

---

### 3.8 Kinematic Layer — Log Return ✅

**Doc (lineas 506-507):** `e_ret_max = mean(log(P_end/P_start) x 100 | up legs)`

**Engine ([L164](file:///root/botero-trade/backend/scripts/_lib/v3_fact_table_engine.py#L164)):**
```python
e_max = float(pos_legs["log_return"].mean()) if n_pos > 0 else 0.02
```

**Veredicto:** ✅ Usa `log_return` del repositorio ZigZag (columna pre-computada).

---

### 3.9 Structural Momentum — MIN a MIN / MAX a MAX ✅

**Doc (lineas 524-539):** Compara pivotes del mismo tipo, calcula `log(P2/P0) x 100`.

**Engine ([L205-223](file:///root/botero-trade/backend/scripts/_lib/v3_fact_table_engine.py#L205-L223)):**
```python
for leg_type, start_type in [("up_legs", "MIN"), ("down_legs", "MAX")]:
    ...
    accum_ret = np.log(P2 / P0) * 100.0
```

**Veredicto:** ✅ Coincide exactamente.

---

## 4. Estructura del JSON — Verificacion contra Fact Store Real

### 4.1 Top-level keys ✅

**Doc (Seccion 5):** `n, stats, divergence_regime, operational_guidance, zz25, zz50, zz75, zigzag_kinematic`

**Real (VIX fact store):** `['n', 'stats', 'divergence_regime', 'operational_guidance', 'zz25', 'zz50', 'zz75', 'zigzag_kinematic']`

**Veredicto:** ✅ Identico.

---

### 4.2 Standard Layer fields ✅

**Doc (Seccion 6):** `n_raw, p_bull, p_bear, e_ret_max, e_ret_min, ev_net, e_days, ev_per_day, rr_asymmetry, confidence_tier`

**Real:** `['confidence_tier', 'e_days', 'e_ret_max', 'e_ret_min', 'ev_net', 'ev_per_day', 'n_raw', 'p_bear', 'p_bull', 'rr_asymmetry']`

**Veredicto:** ✅ Identico (solo orden difiere).

---

### 4.3 Kinematic Layer fields ✅

**Doc (Seccion 7):** `n_pos, n_neg, p_bull, p_bear, e_ret_max, e_ret_min, ev_net, e_days, ftt_bull_days, ftt_bear_days, ev_per_day, rr_asymmetry, confidence_tier, structural_momentum, prev_leg_domino`

**Real:** Todos presentes + campo extra `zigzag_pure_vault` (no documentado, omision menor).

**Veredicto:** ✅ Correcto.

---

## 5. Conteos — Verificacion contra Datos Reales

### 5.1 Numero de fact stores: 11 ✅

### 5.2 Numero de estados por estacion

| Estacion | Doc dice | Real | Veredicto |
|---|:---:|:---:|:---:|
| VIX | 108 | 108 | ✅ |
| BSI | 104 | 104 | ✅ |
| F&G | 82 | 82 | ✅ |
| Credit | 112 | 112 | ✅ |
| Rotation | 120 | 120 | ✅ |
| SV5 Turb | 104 | 104 | ✅ |
| SKEW | 98 | 98 | ✅ |
| PCR | 103 | 103 | ✅ |
| VVIX | 104 | 104 | ✅ |
| Yield Curve | 133 | 133 | ✅ |
| DXY | 128 | 128 | ✅ |

**Veredicto:** ✅ Todos los conteos son correctos.

---

### 5.3 Total teorico de estados ✅

**Doc (linea 359):** "6 x 5 x 5 = 150 por estacion. En la practica, ~80-133 poblados."
**Real:** Rango 82-133. ✅ Correcto.

---

### 5.4 Confidence Tier boundaries ✅

**Doc (linea 792-799):** ROBUST>=21, HIGH>=11, MODERATE>=6, LOW>=3, ANECDOTAL>=1, NONE=0

**Engine ([L85-97](file:///root/botero-trade/backend/scripts/_lib/v3_fact_table_engine.py#L85-L97)):** Coincide exactamente.

---

## 6. Addendums 1-7 (Secciones 6.2-6.4, 11.1-11.2, 13.1-13.2) — ASPIRACIONAL

Los Addendums del 20-Ago-2026 documentan campos y metricas que **NO existen** actualmente en los fact stores generados:

| Addendum | Campo documentado | Existe en fact store? | Existe en engine? |
|---|---|:---:|:---:|
| 6.2 Wins/Losses | `n_wins, n_losses, mean_win, mean_loss, win_rate_raw, profit_factor, asymmetry` | ❌ No | ❌ No |
| 6.3 Distribucion P5/P95 | `p5_ret, p25_ret, p50_ret, p75_ret, p95_ret` | ❌ No | ❌ No |
| 6.4 Base Rate | `base_rate` | ❌ No | ❌ No |
| 11.1 Overlap Matrix | overlap matrix contra seniales existentes | ❌ No | ❌ No |
| 11.2 Cross-Station Aggregation | precursor counts cross-station | ❌ No | ❌ No |
| 13.1 Bootstrap CI95 | CI95 con block bootstrap | ❌ No | ❌ No |
| 13.2 N_eff | N_eff = N_bruto / (1 + 2*sum(rho_k)) | ❌ No | ❌ No |

> [!IMPORTANT]
> Estos 7 addendums son **propuestas de mejora / especificaciones futuras**, no descripciones de lo que los fact stores contienen hoy. El documento no distingue claramente entre lo que **existe** y lo que **deberia existir**. Esto puede confundir a un agente que lea el documento esperando encontrar estos campos en los JSONs.

---

## 7. Convergence Compositor — Verificacion (parcial) ⚠️

**Doc (lineas 91-107):** Describe `SCALE_FACTORS` y `reliability_factor(N)`.

**Compositor real ([L108-120](file:///root/botero-trade/backend/modules/entry_decision/domain/services/convergence_compositor.py#L108-L120)):** Tiene SCALE_FACTORS per-station y per-scale (zz25/zz50/zz75), no el esquema simplificado del doc. El doc muestra un ejemplo conceptual (`scale_factor["zz25"]`), que es correcto en espiritu pero simplificado vs la implementacion real con pesos IC-calibrados por estacion.

**Veredicto:** ⚠️ El concepto es correcto, pero la implementacion real es mas sofisticada que lo documentado.

---

## 8. Regimenes de Divergencia Temporal ✅

**Doc (Seccion 8):** 5 regimenes: FULL_CONVERGENT_BULL, FULL_CONVERGENT_BEAR, TACTICAL_REBOUND_IN_BEAR, STRUCTURAL_BULL_PULLBACK, MIXED_HORIZON_TRANSITION.

**Engine ([L360-369](file:///root/botero-trade/backend/scripts/_lib/v3_fact_table_engine.py#L360-L369)):** Coincide exactamente con las condiciones documentadas.

---

## 9. Operational Guidance Thresholds ✅

**Doc (Seccion 9):**
- BLOCK_CRISIS: `EV_comp <= -0.008` OR `p_bull_3d <= 0.42` OR D1 in {CRISIS, SPIKE, PARANOIA}
- ACCUMULATE_MAX: `EV_comp >= 0.008` AND `p_bull_3d >= 0.58` AND `N >= 10`
- BUY_DIP: `EV_comp >= 0.003` AND `p_bull_3d >= 0.52`
- TRIM: `EV_comp <= -0.003`

**Engine ([L371-380](file:///root/botero-trade/backend/scripts/_lib/v3_fact_table_engine.py#L371-L380)):** Coincide exactamente.

---

## 10. Cadena de Generacion y Datos de Origen ✅

Confirmado:
- Neon PostgreSQL -> `market.ohlcv_bars` + `market.zigzag_legs`
- `TimescaleDataStore` + `ZigzagLegRepository` como fuentes
- `v3_fact_table_engine.py` como motor compartido (excepto DXY que tiene su propia copia)

---

## 11. Errores Menores y Omisiones

### 11.1 Field Glossary en JSON inconsistente

La `_documentation.field_glossary` dentro de cada JSON de fact store (engine L606-614) dice:
```json
"confidence_tier": "Statistical confidence grade (HIGH >=30, MED >=10, LOW <10)"
```

Pero los umbrales reales son ROBUST>=21, HIGH>=11, MODERATE>=6. Los thresholds en el glossary del JSON son incorrectos (30/10 vs 21/11/6), aunque el codigo los aplica correctamente.

### 11.2 Seccion 7 numerada como 6.1, 6.2, 6.3

Las subsecciones dentro de la Seccion 7 (Capa Cinematica) estan numeradas como 6.1, 6.2, 6.3 (lineas 499, 519, 563), lo que genera confusion con la Seccion 6 real.

### 11.3 generate_all dice "10 METAR stations" en el docstring

[`generate_all_150_state_fact_stores.py`](file:///root/botero-trade/backend/scripts/generators/generate_all_150_state_fact_stores.py#L3) dice "10 METAR Stations" en el docstring, pero el codigo ejecuta 11 estaciones (incluye DXY).

### 11.4 DXY generator no usa el engine compartido

[`generate_dxy_fact_table.py`](file:///root/botero-trade/backend/scripts/generators/generate_dxy_fact_table.py) es 700 lineas (30KB) e implementa su propia logica en vez de llamar a `build_v3_dual_layer_fact_store()`. El doc implica que todos usan el engine compartido.

---

## 12. Resumen de Acciones Requeridas

### CRITICOS (afectan interpretacion por agentes)

| # | Accion | Impacto |
|---|---|---|
| 1 | **Actualizar D1 Labels** en Seccion 4.2 para las 8 estaciones incorrectas | Un agente que consulte el doc y compare con un state_key de un fact store no va a matchear |
| 2 | **Corregir BSI ticker** de S5FI a S5TW y la descripcion "50 dias" a "20 dias" | Un agente podria cargar el indicador equivocado |

### IMPORTANTES (afectan claridad)

| # | Accion | Impacto |
|---|---|---|
| 3 | **Marcar Addendums 1-7** como `[PROPUESTA - NO IMPLEMENTADO]` | Un agente buscaria campos inexistentes en los JSONs |
| 4 | Corregir numeracion de subsecciones en Seccion 7 (6.1 a 7.1, etc.) | Confusion entre Seccion 6 y 7 |
| 5 | Documentar excepcion SKEW (calibracion post-2011) en Seccion 4.3 | Completitud |

### MENORES

| # | Accion | Impacto |
|---|---|---|
| 6 | Corregir field_glossary confidence_tier thresholds en el engine (30/10 a 21/11) | Consistencia interna del JSON metadata |
| 7 | Unificar `generate_dxy_fact_table.py` para usar el engine compartido | Deuda tecnica, no afecta datos |
| 8 | Corregir "10 METAR" a "11 METAR" en generate_all docstring | Consistencia |

---

## 13. Que SI Esta Correctamente Documentado

A pesar de los errores, la mayoria del documento es **preciso y valioso**:

- ✅ **Arquitectura Dual-Layer** (Standard + Kinematic) — correcta
- ✅ **Bayesian Shrinkage m=10** — formulas exactas
- ✅ **D1 Expanding Rank** (zero look-ahead) — correcto
- ✅ **D2 diff(3), D3 std(2d)/std(10d)** — correctos
- ✅ **Gaussian sigma-percentiles** `[0.0228, 0.1587, 0.5, 0.8413, 0.9772]` — correctos
- ✅ **D2/D3 labels universales** (FAST_CRUSH_3D, etc.) — correctos
- ✅ **Structural Momentum** MIN-MIN / MAX-MAX con log return — correcto
- ✅ **Prev Leg Domino** con terciles, cascade_rate, p_extreme_prev — correcto
- ✅ **Divergence Regimes** — 5 regimenes con condiciones exactas — correcto
- ✅ **Operational Guidance** — umbrales y logica — correctos
- ✅ **Confidence Tiers** — boundaries exactas — correctas
- ✅ **Diamantes estadisticos** — concepto y protocolo — correcto
- ✅ **Anti-patrones** (Seccion 16) — todos validos y relevantes
- ✅ **Guia de Empleo** (Seccion 15) — mapa Dato-Pregunta-Decision — correcto
- ✅ **Arboles de Decision** EXIT/ENTRY — logica correcta
- ✅ **Fact Stores vs quants_obs** — distincion correcta
- ✅ **Flujo de produccion** (Seccion 15.5) — arquitectura correcta
