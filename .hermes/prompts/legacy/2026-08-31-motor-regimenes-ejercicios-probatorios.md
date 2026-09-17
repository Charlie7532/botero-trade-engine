# PROMPT v2 — Motor de Regímenes de Mercado: Ejercicios Probatorios

**Origen:** Conversación Claude Opus, 31-Ago-2026 — CORREGIDO post-auditoría Hermes
**Propósito:** Ejecutar los 6 ejercicios probatorios para descubrir regímenes de mercado naturales desde los datos, antes de diseñar el `MarketRegimeEngine`.
**Versión:** v2 (correcciones: lake index, manejo -1, cascade en pivotes, Bonferroni, ventanas reales)
**Contexto completo:** `docs/research/11_market_regime_engine/auditoria_arquitectonica_motor_regimenes.md`

---

## ⚠️ ERRATA TÉCNICA v1 (corregida en v2)

> La versión anterior del prompt y su `implementation_plan.md` contenían errores
> detectados por auditoría contra datos reales. CORREGIR antes de ejecutar:

| # | Error v1 | Corrección v2 | Impacto |
|---|---|---|---|
| 1 | `df['date']` para el lake | **El index es DatetimeIndex con nombre `time`.** Usar `df.index`, no `df['date']`. Cualquier `df['date']` lanza KeyError. | 🔴 Todos los scripts crashean sin fix |
| 2 | D1 bins tratados como régimen homogéneo | **-1 significa "estación no disponible", no es un estado.** El lake tiene bins {-1,0,1,2,3,4,5}. 11 estaciones sin -1 = solo 3,648/8,453 filas (43%, 2011-2026). | 🔴 Clustering sobre -1 produce clusters artefacto |
| 3 | "8 estaciones core 2000-2026 (6,700+ días)" | **La ventana 8-core (incluyendo credit, yield, rotation) es 4,613 filas (2008-2026, 18.4 años).** Sin credit serían 5,036 (1999-2026). Ninguna llega a 6,700 incluyendo CAT1 completo. | 🟡 Cifras infladas en v1 |
| 4 | cascade_conviction en lake para E6 | **El lake NO tiene cascade_conviction.** `quants_obs.pkl` la tiene pero solo en 1,590 pivotes, no en 8,453 días. Forward-fill introduce look-ahead. | 🔴 E6 no ejecutable con diseño diario |
| 5 | Bonferroni con un solo k | **GMM, HDBSCAN y K-Means dan k distintos.** No se puede aplicar α=0.05/k con un solo k. | 🟡 Corrección múltiple ambigua |
| 6 | 70/30 fijo sobre 14.6 años | GFC queda FUERA de la ventana 11-estación (empieza 2011). 70/30 fijo da ~4.4 años de test. | 🟡 Estabilidad de clusters dudosa |
| 7 | CAT2→CAT3→CAT1 "todo RUIDO" | En zz50|40d es **OP-SHORT** (-2.64%, 0% folds+). No es "todo" ruido. | 🟡 Imprecisión narrativa |
| 8 | Forward returns como pct_change(5/10/20/40d) | **NO usar horizontes fijos de calendario.** El proyecto mide retornos contra la pierna zigzag siguiente (triple barrier). Usar `next_leg` del arnés o acumular `spy_ret_1d` hasta el próximo zigzag. | 🔴 Error metodológico grave: mide retornos condicionales a régimen con métrica equivocada |

---

## CONTEXTO PREVIO (resumen para el nuevo hilo)

### Trabajo completado en la sesión anterior:

1. **Validador OOS Multi-Celda v2:** Cada señal del catálogo v7 se prueba en TODAS sus celdas (escala×régimen) independientemente. Correcciones: fix `_score()` (desempate por folds), Bonferroni señal-dependiente, veredicto 🔵 PENDIENTE para <5 folds.

2. **Catálogo v7 Definitivo (validación OOS multi-celda):**

   | TIER | Señales | Status |
   |:---|:---|:---|
   | **1 — ALPHA** | `cascade_reversal` (zz25\|ALZA, 9/9, p_bonf=0.004), `credit_stress` (zz75\|ALZA, 3/3, +4.96%) | CONFIRMADO |
   | **2 — CONTRIBUYENTE** | `breadth_contraction_exit` (zz75\|ALZA, 6/9, +1.62%), `pcr_put_panic` (zz50\|BAJA, 3/4) | CONFIRMADO |
   | **3 — PENDIENTE** | `vvix_entry` (3 folds, insuf. para sign-test), `capitulacion`/`bsi_washed_out` (p=0.50, contextual) | PENDIENTE |
   | **4 — DIAMANTE** | `panico_total`, `skew_paranoia_exit` | Protocolo §3.3 |

3. **Auditoría Arquitectónica del Motor de Regímenes:** Se identificaron 6 debilidades en la propuesta original de 5 regímenes narrativos. Conclusión: **necesitamos descubrir los regímenes desde los datos, no imponerlos desde la narrativa.**

### Infraestructura disponible (verificada contra datos):

- **METAR Lake:** `data/research/continuous_metar_lake.parquet` — **8,453 filas × 257 features (1993-2026). Index: DatetimeIndex con nombre `time`.**
  - 11 estaciones con `*_d1_bin`, `*_d2_bin`, `*_d3_bin` (bins {-1,0,1,2,3,4,5} donde -1 = estación no disponible)
  - 35 columnas `overflow_tier` (T0-T5+, distribuciones por estación — FG_D1 tiene 0 overflows)
  - SPY OHLCV: `spy_open`, `spy_high`, `spy_low`, `spy_close`, `spy_volume`, `spy_ret_1d`
  - **NO tiene cascade_conviction**
  - **Ventanas de datos completos sin -1:**
    - 11 estaciones: **3,648 filas** (2011-12-30 → 2026-08-17, 14.6 años)
    - 8 estaciones core (VIX+SKEW+YIELD+ROTATION+SV5+DXY+BSI+CREDIT): **4,613 filas** (2008-04-09 → 2026-08-17, 18.4 años)
    - 6 estaciones históricas (VIX+SKEW+YIELD+DXY+BSI+ROTATION): **~5,000+ filas** (1999-2026)

- **Fact Stores V3:** 11 almacenes JSON con matrices de probabilidad por estado.
- **Overflow Taxonomy:** Escala graduada T1-T5 implementada en `sigma_overflow.py`. Verificado: VIX tiene T0-T4, FG tiene solo T0.
- **Secuencias CAT1→CAT2→CAT3:** Validadas en `docs/research/08_versioned_benchmarks/validate_regimes_oos_REPORT.md`.
  - Solo Macro-Driven (CAT1→CAT2→CAT3) y Cuchillo (CAT1→CAT3→CAT2) tienen señal OOS: OP-SHORT.
  - CAT2→CAT3→CAT1 (Comprar Miedo): RUIDO en casi todo, pero marginal OP-SHORT en zz50|40d (-2.64%, 0% folds+).
  - CAT3-lidera, CAT2→CAT1→CAT3: INSUF o RUIDO.
- **quants_obs.pkl:** `data/research/pivots/quants_obs.pkl` — 1,590 pivotes × 165 columnas. Contiene `cascade_conviction` y `cascade_conviction_50`. **NOTA: cascade solo existe en días de pivote, no en la serie diaria del lake.**
- **Cascade reversal:** Umbral -0.957 = p15 de cascade_conviction_50 (15.2% de pivotes = 241/1590). Validado OOS: zz25|ALZA, 9/9 folds, +1.40%, p_bonf=0.004.

---

## REGLAS DE EJECUCIÓN (corregidas)

1. **Dato mata opinión.** Ningún régimen se nombra ni se le asigna acción hasta que los datos muestren que sus retornos forward son significativamente diferentes del baseline.
2. **El index del lake es DatetimeIndex (`df.index`).** No existe columna 'date'. Usar `df.index` para fechas.
3. **FILTRAR -1 de D1 antes de clusterizar.** -1 significa "estación no disponible", no es un estado de régimen. Filtrar: `df[d1_cols].ne(-1).all(axis=1)`.
4. **Reportar las 3 ventanas:** 11 estaciones (3,648 rows), 8 core (4,613 rows), 6 históricas (~5,000 rows). No usar cifras infladas.
5. **Walk-forward: usar expanding window, NO sliding 70/30 fijo.** La ventana 11-estación solo da ~4.4 años de test con 70/30. Expanding window preserva más datos OOS. *(Motivo: validate_regimes_oos usó expanding window K=8 folds con éxito.)*
6. **Bonferroni por algoritmo, no un solo k.** GMM, HDBSCAN y K-Means darán k distintos. Reportar α por algoritmo: `α = 0.05 / k_algoritmo`.
7. **cascade_conviction NO es diario.** Solo existe en 1,590/8,453 días (pivotes). E6 debe restringirse a días de pivote dentro de regímenes, no a la serie completa.
8. **Cada escala es independiente.** Si el clustering revela que zz25 y zz75 dan regímenes diferentes, preservar ambos.
9. **Scripts en `research/11_market_regime_engine/`.** Cada ejercicio = 1 script autocontenido + 1 orquestador secuencial.

---

## EJERCICIOS A EJECUTAR (orden: E1 → E2 → E5 → E4 → E3 → E6)

### ⚙️ PRE-PASO: Preparación del Lake

1. Cargar lake: `df = pd.read_parquet('data/research/continuous_metar_lake.parquet')`
2. Index: `df.index` (DatetimeIndex, nombre `time`). NO usar `df['date']`.
3. D1 columns: `d1_cols = [c for c in df.columns if c.endswith('_d1_bin')]`
4. Filtrar válidas: `mask_valid = df[d1_cols].ne(-1).all(axis=1)`
5. Crear 3 datasets:
   - `df_11`: mask_valid (3,648 rows, 2011-2026)
   - `df_8`: 8 core sin -1 (VIX, SKEW, YIELD, ROTATION, SV5, DXY, BSI, CREDIT) — 4,613 rows, 2008-2026
   - `df_6`: 6 históricas (VIX, SKEW, YIELD, DXY, BSI, ROTATION) — ~5,000+ rows, 1999-2026
6. Del dataset elegido, extraer el vector D1: `X = df[d1_cols].values` (solo filas sin -1)
7. **⚠️ NO USAR `pct_change(N)` para medir retornos.** El sistema de evaluación del proyecto usa triple barrier de López de Prado basado en zigzag. Ver `research/01_señales_entry_exit/medir_senal.py` y `ARNES.md`. Los retornos se miden contra `next_leg` (pierna siguiente) o contra escalas zz25/zz50/zz75, NO contra horizontes de calendario fijo. Para E2 se usará la columna forward del arnés.
8. Overflow tiers: columnas `*_overflow_tier_*`

---

### E1: Descubrimiento No-Supervisado de Regímenes Naturales

**Input:** Vector D1 de 11 estaciones (`*_d1_bin`) — solo filas sin -1.
**Método:** HDBSCAN + GMM + K-Means. NO imponer k. Evaluar con silhouette y estabilidad temporal.

**REQUISITOS TÉCNICOS:**
- **Filtrar -1 antes del clustering.** `X = df[d1_cols][mask_valid].values`
- **Ejecutar sobre df_11 (3,648 rows) y df_8 (4,613 rows).** Comparar resultados.
- **Estabilidad temporal:** Usar expanding window para simular walk-forward: clusterizar sobre train creciente, medir asignación en test. NO sliding 70/30 fijo.
- **HDBSCAN** está disponible en sklearn 1.8.0 (`sklearn.cluster.HDBSCAN`). Usar `min_cluster_size=50` (≈1.4% de 3,648 filas).

**Output:**
- `data/research/regimes/e1_discovered_clusters.json`
  - Número de clusters por algoritmo y por dataset (df_11 y df_8)
  - Centroides D1 normalizados
  - Serie temporal de régimen asignado
  - Métricas: Silhouette, Davies-Bouldin, estabilidad temporal (Adjusted Rand Index entre train/test)
  - NOTA: si GMM da k=4, HDBSCAN k=6 y K-Means k=5 — reportar los 3. No elegir uno.

**Pregunta clave:** ¿Cuántos regímenes de mercado existen realmente?

---

### E2: Retornos Forward Condicionales por Régimen (usando SISTEMA DE EVALUACIÓN DEL PROYECTO)

**⚠️ IMPORTANTE: NO usar `pct_change(N)`.** Este proyecto mide retornos contra la pierna zigzag siguiente (triple barrier de López de Prado), no contra horizontes de calendario fijo. El sistema de evaluación completo está en:
- `research/01_señales_entry_exit/medir_senal.py` — función `medir(señal_nombre, df, forward_col="next_leg", ...)`
- `research/01_señales_entry_exit/GUIA_EMPLEO.md` — mapeo de cada campo a decisión operativa
- `research/01_señales_entry_exit/arnes/medicion.py` — motor de medición con bootstrap 3000, wins/losses, CI95

**Método correcto:**

1. Para cada régimen descubierto en E1, etiquetar los días del lake con `regimen_id`.
2. Para cada día, el forward return NO es `pct_change(5)` — es:
   - **Opción A (primaria):** Usar `spy_ret_1d` del lake y acumular hasta el próximo zigzag (o hasta horizonte fijo si no hay zigzag). La función `medir()` del arnés ya hace esto.
   - **Opción B (si el lake no tiene `next_leg` directa):** Calcular como `spy_close` forward hasta el cambio de régimen (distancia variable, no fija).
3. Métricas por régimen:
   - **EV** (mean forward return)
   - **Win Rate** (P(ret > 0))
   - **Profit Factor** (sum wins / |sum losses|)
   - **CI95** (bootstrap 3000, como el arnés)
   - **Wins y Losses separados** (mean_win, mean_loss, p90_win, p10_loss, wipeouts>20%)
   - **Sharpe** del forward return
   - **Kelly fraction**
4. Tests estadísticos:
   - **Kruskal-Wallis** para diferencia global entre regímenes.
   - **Mann-Whitney U** por régimen vs baseline incondicional.
   - **Bonferroni por algoritmo:** α = 0.05 / k_algoritmo.
5. Walk-forward expanding: clusters entrenados en train, retornos medidos en test.
6. **NO usar `pct_change(5).shift(-5)`.** Eso mide retornos fijos de calendario, no condicionales al régimen.

**Output:** `data/research/regimes/e2_forward_returns.json`
- Tabla régimen × métrica con EV, WR, PF, CI95, wins/losses, p-value (corregido), N.
- NOTA: al usar forward variable (no horizonte fijo), el N por régimen puede diferir del N de días en el régimen.

**Referencia metodológica:** El design doc del validador OOS multi-celda (`research/10_gate_oos_validation/validador_oos.py`) y `docs/research/08_versioned_benchmarks/validate_regimes_oos_REPORT.md` muestran exactamente cómo se miden retornos en este proyecto: baseline incondicional, exceso sobre baseline, CI95, folds+.

**Pregunta clave:** ¿Los regímenes descubiertos tienen distribuciones de retorno forward significativamente diferentes?

---

### E3: Matriz Señal ↔ Régimen

**Input:** Regímenes de E1 + fechas de disparo de señales validadas OOS.
**Señales:** cascade_reversal, credit_stress, breadth_contraction_exit, pcr_put_panic, panico_total, vvix_entry, capitulacion, skew_paranoia_exit.

**REQUISITOS TÉCNICOS:**
- Las señales se definen en `research/01_señales_entry_exit/arnes/señales.py`
- Las fechas de disparo se obtienen desde `quants_obs.pkl` aplicando cada función de señal.
- **Para medir lag señal→transición:** identificar el día exacto del disparo y el día del cambio de régimen (E1). Diferencia en días.

**Output:** `data/research/regimes/e3_signal_regime_matrix.json`
- Heatmap P(Régimen | Señal) y P(Señal | Régimen).
- Histograma de lag señal → transición.
- Clasificación: ¿la señal dispara en núcleo del régimen (confirmador) o en transición ±5d (líder)?

**Pregunta clave:** ¿Las señales se concentran en transiciones de régimen?

---

### E4: σ-Overflow como Detector de Transición

**Input:** Cambios de régimen de E1 + overflow tiers del lake.
**Método:** Precision/Recall/F1 del overflow T2+ como predictor de cambio de régimen (ventana 10 días previos).

**REQUISITOS TÉCNICOS:**
- **Reportar POR ESTACIÓN.** FG_D1 tiene 0 overflows (todas las filas en T0). No tiene sentido agrupar todas las estaciones en una métrica si algunas nunca producen overflows.
- Ventana de búsqueda: 10 días calendario previos al cambio de régimen.
- Calcular P/R/F1 para:
  - **Por estación:** VIX_D1, VVIX_D1, SKEW_D1, CREDIT_D1, etc.
  - **Por tier:** T2 (≥4σ), T3 (≥5σ), T4+ (≥7σ).
  - **Agregado:** cualquier overflow T2+ en cualquier estación × 10 días.
- Distribución del lead time (días de anticipación).

**Output:** `data/research/regimes/e4_overflow_transitions.json`
- P/R/F1 por estación, por tier, y agregado.

**Pregunta clave:** ¿Los overflows marcan las rupturas de régimen?

---

### E5: Persistencia y Duración (Markov)

**Input:** Serie temporal de regímenes de E1 + fechas.
**Método:** Matriz de transición de primer orden. Duración media/mediana. Test de estacionariedad.

**REQUISITOS TÉCNICOS:**
- Matriz de transición k×k: P(S_{t+1} | S_t)
- Duración: media, mediana, P90. Persistencia teórica: E[D_i] = 1/(1-P_{ii})
- **Transiciones prohibidas:** identificar pares con P < 1%.
- **Estacionariedad:** Comparar matriz de primera mitad vs segunda mitad. Distancia de Frobenius. Test de homogeneidad de Markov (chi-cuadrado).

**Output:** `data/research/regimes/e5_markov_persistence.json`

**Pregunta clave:** ¿Los regímenes son estables o cambian cada 3 días?

---

### E6: Cascade Conviction como Precursor de Agotamiento

**Input:** Cascade conviction del `quants_obs.pkl` (1,590 pivotes) + regímenes alcistas de E1.

**⚠️ IMPORTANTE:** cascade_conviction **NO existe en el lake diario.** Solo existe en `quants_obs.pkl` que tiene 1,590 pivotes zigzag. E6 NO puede medir lead time diario. Diseño corregido:

**Método corregido (pivote-based, no diario):**
1. Identificar los regímenes alcistas de E1 y sus fechas de inicio y fin.
2. Para cada pivote en `quants_obs.pkl`, determinar si está dentro de un régimen alcista.
3. Dentro de regímenes alcistas que terminaron:
   - ¿Hubo un cascade_reversal (cascade_conviction < -0.957) en los últimos N pivotes antes del fin?
   - ¿El cascade_reversal ocurrió antes del fin del régimen (líder) o después (confirmador)?
   - Lead time en **pivotes** (no en días), entre cascade_reversal y fin del régimen.
4. Falsos positivos: cascade_reversal dentro de régimen alcista pero el régimen NO terminó.

**Alternativa (si es inviable):** Medir correlación entre cascade_conviction y la asignación de régimen en los ~1,590 días de pivote.

**Output:** `data/research/regimes/e6_cascade_exhaustion.json`
- Lead time medio en pivotes.
- Precision/Recall de cascade como predictor de fin de régimen alcista.
- Distribución de falsos positivos.

**Pregunta clave:** ¿cascade_conviction predice el fin de los regímenes alcistas?

---

## ORQUESTADOR SECUENCIAL

Además de los 6 scripts individuales, crear `run_regime_pipeline.py` que ejecute E1 → E2 → E5 → E4 → E3 → E6 secuencialmente, verificando que cada paso produjo su output antes de pasar al siguiente.

```python
# run_regime_pipeline.py — orquestador
steps = [
    ("E1", "e1_descubrimiento_regimenes.py", "data/research/regimes/e1_discovered_clusters.json"),
    ("E2", "e2_retornos_forward.py", "data/research/regimes/e2_forward_returns.json"),
    ("E5", "e5_persistencia_markov.py", "data/research/regimes/e5_markov_persistence.json"),
    ("E4", "e4_overflow_transiciones.py", "data/research/regimes/e4_overflow_transitions.json"),
    ("E3", "e3_senales_regimenes.py", "data/research/regimes/e3_signal_regime_matrix.json"),
    ("E6", "e6_cascade_agotamiento.py", "data/research/regimes/e6_cascade_exhaustion.json"),
]
for name, script, output in steps:
    subprocess.run(["backend/.venv/bin/python", script], check=True)
    assert Path(output).exists(), f"{name} did not produce {output}"
```

---

## INFORME DE SÍNTESIS

Crear `docs/research/11_market_regime_engine/INFORME_EJERCICIOS_PROBATORIOS.md` respondiendo 6 preguntas clave:

1. ¿Cuántos regímenes existen realmente y cuáles son sus perfiles D1?
2. ¿Tienen perfiles de retorno forward estadísticamente diferenciados?
3. ¿Son estables en el tiempo o efímeros?
4. ¿Los σ-overflows anuncian las rupturas de régimen? (reportado por estación)
5. ¿Cómo se posicionan las señales del catálogo v7 respecto a los regímenes?
6. ¿cascade_conviction predice el agotamiento alcista? (en escala de pivotes)

Todo resultado con **Evidence Status Tag**: `[EVIDENCE: CONFIRMED OOS]`, `[EVIDENCE: REJECTED]`, `[EVIDENCE: INCONCLUSO]`, `[EVIDENCE: HYPOTHESIS]`.

---

## SKILLS A CARGAR

- `clean-architecture` (obligatorio)
- `hypothesis-governance` (cada hallazgo con Evidence Status Tag)
- `botero-trade` (proyecto, leer planes)

---

## ARCHIVOS DE REFERENCIA

| Archivo | Qué contiene |
|---|---|
|| `research/01_señales_entry_exit/arnes/señales.py` | Definiciones de las 9 señales del catálogo v7 |
|| `research/01_señales_entry_exit/medir_senal.py` | **🔴 OBLIGATORIO para E2.** Sistema de evaluación por triple barrier con bootstrap 3000, CI95, wins/losses separados. La función `medir()` es el estándar del proyecto para medir retornos condicionales |
|| `research/01_señales_entry_exit/GUIA_EMPLEO.md` | Mapeo campo→pregunta→decisión. Referencia para métricas de E2 |
|| `research/01_señales_entry_exit/ARNES.md` | Documentación del arnés de evaluación |
|| `research/10_gate_oos_validation/validador_oos.py` | Validador OOS multi-celda (referencia metodológica de walk-forward con baseline limpio) |
|| `research/10_gate_oos_validation/validacion_oos_catalogo_v7.json` | **🔴 OBLIGATORIO para E3.** Resultados OOS ya validados. Las señales NO se re-ejecutan — se cruzan sus fechas de disparo con los regímenes |
| `docs/research/11_market_regime_engine/auditoria_arquitectonica_motor_regimenes.md` | Auditoría completa (234 líneas) |
| `docs/research/08_versioned_benchmarks/validate_regimes_oos_REPORT.md` | Validación OOS de 5 secuencias CAT (205 líneas) |
| `docs/research/00_cross_cutting/regimen_crisis_semivida_d3_REPORT.md` | Máquina de estados de crisis (178 líneas) |
| `backend/modules/entry_decision/domain/rules/sigma_overflow.py` | Taxonomy de overflows |

---

## LÍMITES DEL SCOPE

- ✅ Descubrir regímenes desde datos (E1-E6)
- ✅ Medir poder predictivo forward
- ✅ Conectar con señales validadas OOS
- ❌ NO implementar `MarketRegimeEngine` — eso es DESPUÉS del informe
- ❌ NO modificar el lake, los fact stores, ni nada en `backend/`
- ❌ NO forzar coherencia entre escalas (zz25 y zz75 pueden dar regímenes distintos)
- ❌ NO usar ventanas fijas sin filtro de -1

---

**Firma:** Hermes (deepseek/deepseek-v4-flash) — corregido post-auditoría contra datos reales
**Fecha:** 31-Ago-2026