# PROMPT DE CORRECCIÓN CONSOLIDADO — Forense Dimensional + Ejercicios + Arquitectura

**Origen:** deepseek/deepseek-v4-flash (Hermes) + Claude Opus
**Propósito:** 12 correcciones priorizadas tras auditoría combinada de E1-E6, cobertura D1/D2/D3, tríada zigzag y estocasticidad

**Advertencias de la auditoría anterior (Claude Opus) ya incorporadas:**
- ❌ RN1 (renombrar señales.py) → Rechazado por Rule 12
- ❌ G1 (EV episodio) → Rechazado por duplicar first-passage
- ❌ G2 (EV post-episodio) → Rechazado por lookahead
- ⏸️ G4 (rendimiento slot zz50/zz75) → Diferido sin caso de uso

**Taxonomía del Vector de Estado — Hallazgos Verificados (DeepSeek Flash, 1-Sep-2026):**

### Rango canónico de dimensiones
- **D1: 6 niveles (0..5)** — 0 = piso -2σ, 5 = extremo +2σ. Rango completo operativo.
- **D2: 5 niveles (0..4)** — 0 = CRUSH (cayendo rápido), 4 = SPIKE (subiendo rápido). **4 es el extremo ±2σ. No existe 5** por diseño de calibración correcto.
  - D2=0,1 = **velocidad negativa** (VIX cayendo desde pico de pánico). D2=3,4 = **velocidad positiva** (VIX acelerando al alza).
  - **D2=2 es AMBIGUO/INDETERMINADO** — abarca del percentil 15.87 al 84.13 (-1σ a +1σ, ~68% de datos). **Incluye TANTO velocidad negativa COMO positiva.** La etiqueta actual `STABLE_CONTINUATION_3D` es **engañosa** — sugiere "cero" o "estable" cuando debería ser `AMBIGUOUS_VELOCITY`. ~20+ archivos la usan incorrectamente como label.
  - Cuando D2 supera ±2σ (más allá de bin 4), **se desborda a la escala de overflows (T1-T5+)**, evaluada hasta BLOWOFF (>10σ). Taxonomía `sigma_overflow.py`: T1=3-4σ (MODERADO), T2=4-5σ (EXTREMO), T3=5-7σ (SEVERO), T4=7-10σ (CRÍTICO), T5=10σ+ (CATÁSTROFICO/BLOWOFF).
  - **Ningún evaluador cruza D2 con overflows.** Los overflows existen en el lake (columnas `*_overflow_tier_*`) pero `evaluador_general.py` y `evaluador_vela_a_vela.py` nunca los consultan al evaluar señales.
- **D3: 5 niveles (0..4)** — 0 = MUY_ESTABLE (convicción), 4 = MUY_INESTABLE (duda/confusión). **4 es el extremo ±2σ. No existe 5** por diseño de calibración correcto.
- **Combinaciones con doble extremo (5_4_x), (5_x_4), (x_4_4) existen pero son raras.** La triple (5_4_4) es prácticamente inexistente (0-2 ocurrencias en 11 estaciones).

### Señales faltantes verificadas
| Patrón | Ocurrencias | % | Potencial |
|:-------|:-----------:|:-:|:----------|
| SKEW D1=0 | **516 pivotes** | 32.5% | Señal de complacencia extinta — EXIT |
| BSI D1=0,1 | **589 pivotes** | 37.0% | Señal de compresión extendida — ENTRY temprana |
| CREDIT (0__0__x) | **24 pivotes** | — | Diamante §3.3 — capitulación crediticia |

### Cascada dimensional real
- **D3=4 precursora de crisis en 11.7% de casos** (20/171 eventos D1=5 tuvieron D3=4 en los 30 días previos). Ejemplo verificado: 2025-04-04.
- **88.3% de crisis saltan directo a D1=5 sin precursora** (COVID-2020). La precursora D3 no es universal pero cuando ocurre, es información crítica no capturada.
- **Sesgo del indicador:** Lo que es alcista para VIX puede ser bajista para BSI (ej: `(0_2_2)` da SPY +0.14% en VIX pero -1.66% en BSI).

### Patrones de rango medio que definen el 68% del mercado
| Patrón | VIX | BSI | SKEW | Interpretación |
|:-------|:---:|:---:|:----:|:---------------|
| `(2_2_2)` | +0.14% WR 57.7% | +0.11% WR 53.2% | -0.10% WR 50.5% | **Mild bullish** para VIX/BSI, neutral para SKEW |
| `(3_2_2)` | +0.13% WR 51.6% | +0.09% WR 52.1% | +0.02% WR 50.0% | **Neutral** — estado más común, sin edge |
| `(1_2_2)` | +0.32% WR 75.0% | -0.40% WR 38.4% | +0.06% WR 47.2% | **Bullish para VIX, bearish para BSI** — divergencia crítica |
| `(0_2_2)` | — | -1.66% WR 30.8% | -0.18% WR 45.4% | **Piso NO es compra** — el mercado sigue bajando |

### Extremos que SÍ definen edge operativo
| Patrón | D2 (velocidad VIX) | SPY ret | WR | N | Taxonomía |
|:-------|:-------------------|:-------:|:--:|:-:|:----------|
| `(5_4_x)` | D2=4 — VIX acelerando AL ALZA (vel + fuerte) | **-3.50%** | 15.8% | 57 | **PÁNICO CLÍMAX** — el miedo se acelera |
| `(5_3_x)` | D2=3 — VIX subiendo lento (vel + débil) | **-0.89%** | 32.3% | 31 | **ABDICACIÓN** — VIX sube pero desacelera |
| `(5_2_x)` | D2=2 — VIX plano (vel ≈ 0, ambiguo) | **+1.20%** | 62.1% | 29 | **AMBIGUO** — puede ser giro o pausa |
| `(5_<2_x)` | D2<2 — VIX cayendo (vel **negativa**) | **+0.80%** | 61.1% | 54 | **CONTRARIAN BUY** — el VIX se retira del pico, oportunidad |
| BSI `(5_2_x)` — Breadth extremo + neutral | **+1.49%** | 88.5% | 26 | **COMPRA FUERTE** — mayor WR del sistema |
| BSI `(0_2_2)` — Washed out + estable | **-1.66%** | 30.8% | 65 | **NO COMPRAR** — piso no es oportunidad |

---

## 🔴 P0 — NUEVO EJERCICIO E7: Taxonomía de Estados del Vector (D1×D2×D3)

**Propósito:** Analizar sistemáticamente el significado y frecuencia de cada combinación del vector de estado `(D1__D2__D3)` para las 11 estaciones METAR. No solo los extremos — también los patrones de rango medio que representan el 68% del mercado.

### Datos de entrada disponibles (verificados)

| Dataset | Barras | Columnas |
|:--------|:------:|:---------|
| Lake continuo | 8,453 | `*_d1_bin`, `*_d2_bin`, `*_d3_bin` para 11 estaciones |
| quants_obs (pivotes) | 1,354 | `*_sk` (state keys), `daily_return_pct`, `next_leg` |

### Preguntas a responder para cada estación

1. **Top 10 state keys más frecuentes** — ¿cuáles son y qué SPY retorno dan?
2. **Patrón (2_2_2) = "neutral completo"** — ¿es continuación, complacencia, o ruido? ¿Es lo mismo para VIX que para BSI que para SKEW?
3. **Patrón (3_2_2) = "D1=3 + velocidad neutra"** — ¿es continuación alcista o agotamiento?
4. **D2=2 (velocidad neutral) cuando D1 está en extremo** — ¿es complacencia o señal contrarian?
5. **D3=4 (inestabilidad) cuando D1 está en neutral (2,3)** — ¿es precursora de crisis o ruido?
6. **D2=0 (crush) cuando D1=0 (piso)** — ¿es capitulación o continuación?
7. **D2=4 (spike) cuando D1=5 (extremo)** — ¿es explosión o agotamiento?

### Output esperado

```json
{
  "E7_taxonomia_estados": {
    "vix": {
      "top_10": [{"key": "3__2__2", "n": 215, "pct": 13.5, "spy_ret": +0.0013, "wr": 51.6, "significado": "NEUTRAL_ALTO+VELOCIDAD_NEUTRAL+ESTABLE"}],
      "patrones_clave": {
        "2_2_2": {"n": 97, "spy_ret": +0.0014, "wr": 57.7, "interpretacion": "MILDLY_BULLISH — mercado neutral pero estable sesga al alza"},
        "5_2_x": {"n": 29, "spy_ret": +0.0120, "wr": 62.1, "interpretacion": "CONTRARIAN_BUY — panico sin velocidad = oportunidad de compra"},
        "5_4_x": {"n": 57, "spy_ret": -0.0350, "wr": 15.8, "interpretacion": "PANIC_CONFIRMATION — panico acelerandose = seguir bajando"}
      }
    },
    "bsi": { ... },
    "skew": { ... },
    "resumen_cruzado": {
      "2_2_2_es_alcista": {"si_para": ["vix", "bsi"], "no_para": ["skew", "credit"]},
      "d3_4_precursora_de_crisis": {"confirmado": ["vix_2025-04-04"], "saltado": ["covid_2020"]}
    }
  }
}
```

### Interpretaciones ya verificadas (datos concretos)

| Patrón | Estación | SPY ret | WR | N | Interpretación |
|:-------|:---------|:-------:|:--:|:-:|:---------------|
| `(2_2_2)` | VIX | +0.14% | 57.7% | 97 | **Mild bullish** — neutral completo sesga al alza |
| `(3_2_2)` | VIX | +0.13% | 51.6% | 215 | **Neutral** — el estado más común, sin señal clara |
| `(1_2_2)` | VIX | +0.32% | 75.0% | 20 | **Bullish** — VIX bajo + estable = complacencia real |
| `(5_2_x)` | VIX | +1.20% | 62.1% | 29 | **Contrarian buy** — pánico sin velocidad = oportunidad |
| `(5_4_x)` | VIX | -3.50% | 15.8% | 57 | **PÁNICO CLÍMAX** — D2=4, VIX acelerando al alza |
| `(5_3_x)` | VIX | -0.89% | 32.3% | 31 | **ABDICACIÓN** — D2=3, VIX subiendo, desacelera |
| `(5_2_x)` | VIX | +1.20% | 62.1% | 29 | **AMBIGUO** — D2=2, VIX plano, puede ser giro o pausa |
| `(5_<2_x)` | VIX | +0.80% | 61.1% | 54 | **CONTRARIAN BUY** — D2<2, VIX cayendo, velocidad negativa, pánico se agota |
| `(0_2_2)` | BSI | -1.66% | 30.8% | 65 | **Bearish** — washed out estable no es compra |
| `(4_2_2)` | BSI | +0.54% | 66.7% | 63 | **Bullish** — breadth fuerte + estable |
| `(0_2_2)` | SKEW | -0.18% | 45.4% | 337 | **Slightly bearish** — no miedo de cola pero el mercado no sube |
| `(1_2_2)` | CREDIT | +0.68% | 68.8% | 48 | **Bullish** — estrés crediticio bajo + estable = riesgo on |

### Reglas de ejecución

1. **No limitarse a extremos (0 y 5).** Los patrones de rango medio (2_2_2, 3_2_2) representan el 68% del mercado.
2. **Reportar por estación separadamente.** Lo que es alcista para VIX puede ser bajista para BSI (ej: `(0_2_2)` da +0.14% en VIX pero -1.66% en BSI).
3. **D3=4 como precursora.** Cuando D1=2,3 y D3=4, documentar si el mercado cayó en los siguientes 30 días (ej: 2025-04-04) vs casos donde no hubo crisis (ej: COVID saltó directo a D1=5).
4. **Output en `data/research/signals/e7_taxonomia_estados.json`**.
5. **Incluir CI95 Clopper-Pearson para WR y Bonferroni α' = 0.05/N_patrones.**

---

## 🔴 P0 — Errores Factuales en Ejercicios E1-E6 (4 correcciones)

### C1 — E1: Conclusión hardcoded dice 76% cuando el dato real es 32.6%
**Archivo:** `ejercicios_regimen.py`
**Problema:** La línea 99 del JSON E1 dice textualmente: "hit rate 76% en ALZA y 76% en BAJA" cuando los datos reales son 87.0% ALZA y 32.6% BAJA.
**Fix:** Generar conclusiones dinámicamente desde los datos calculados. NO usar templates estáticos.
```python
# En vez de:
conclusion = "La señal tiene hit rate 76% en ambos regímenes"
# Usar:
conclusion = f"ALZA: HR={hit_alza:.1%} (N={n_alza}) vs BAJA: HR={hit_baja:.1%} (N={n_baja})"
```

### C2 — E4: Conclusión dice "≤5 barras" cuando la mediana real es 10.0
**Archivo:** `ejercicios_regimen.py`
**Problema:** "50% se completan en ≤5 barras" → Dato real: mediana=10.0, P90=25.4.
**Fix:** Generar conclusión desde los percentiles reales.

### C3 — E5: Lift NEGATIVO (-2.4%) invalida la hipótesis, no la confirma
**Archivo:** `ejercicios_regimen.py`
**Problema:** `lift_vs_unconditional = -2.4%`. El ejercicio demuestra que la confluencia de pánico produce PEORES resultados que el azar.
**Root cause:** El diseño usa umbral ≥2 estaciones en D1 extremo — demasiado laxo. Con 6 estaciones monitoreadas, tener 2 en D1 extremo no es raro.
**Fix:** (a) Cambiar conclusión a "RECHAZADA — lift negativo"; (b) Rediseñar con umbral ≥3 estaciones o confluencia D1+D2 simultáneo.

### C4 — E6: N=0 en bear trend invalida la comparación bull/bear
**Archivo:** `ejercicios_regimen.py`
**Problema:** N=18 bull / N=0 bear. `fg_extreme_greed` solo dispara en bull markets.
**Fix:** Cambiar conclusión a "INCONCLUSO — sin datos de bear (N=0). La señal es intrínsecamente procíclica."

---

## 🔴 P0 — Rankings y CI95 (3 correcciones)

### C5 — Sin CI95 Clopper-Pearson en E1-E6
**Archivo:** `ejercicios_regimen.py`
**Problema:** 0/6 ejercicios reportan CI95 para hit rates.
**Fix:** Agregar a cada métrica de hit rate:
```python
from scipy.stats import beta
alpha = hits + 1
beta_param = n - hits + 1
ci_lower = beta.ppf(0.025, alpha, beta_param)
ci_upper = beta.ppf(0.975, alpha, beta_param)
```
**Afecta:** E1 (hit_rate_alza/baja), E2 (hit_rate_pre/post), E3 (pct_*), E4 (hit_rate_zz25), E5 (hit_rate_zz50), E6 (hit_rate_bull)

### C6 — Bonferroni en ranking maestro
**Archivo:** `consolidar_ranking.py`
**Problema:** 33 señales comparadas sin ajuste por múltiples pruebas. α' = 0.05/33 = 0.0015.
**Fix:** Agregar columna `p_bonferroni = min(p_value * 33, 1.0)` al ranking.

### C7 — Sin p-values ni Bonferroni en E1-E6
**Archivo:** `ejercicios_regimen.py`
**Problema:** Solo E1 reporta Fisher p-value. E2-E6 no reportan significancia estadística.
**Fix:** Agregar Fisher/Mann-Whitney U a cada ejercicio con Bonferroni `α' = 0.05/6 = 0.0083`.

---

## 🟡 P1 — Cobertura Dimensional (3 correcciones)

### C8 — E5 rediseñado: Confluencia multi-dimensional (D1+D2+D3)
**Archivo:** `ejercicios_regimen.py`
**Problema actual:** Cuenta estaciones con D1 extremo (≥2). No usa D2 ni D3 del vector de estado.
**Propuesta:** Usar `arnes/confluencia.py` existente con `calcular_score_confluencia()` que sí lee todas las dimensiones.
```python
# Usar la función ya migrada:
from arnes.confluencia import calcular_score_confluencia
panic, euphoria = calcular_score_confluencia(z_mat, sigma_threshold=2.0)
# Filtrar días con panic >= 3 (confluencia fuerte)
```

### C9 — Time-stop como tercera barrera en first-passage
**Archivo:** `evaluador_general.py` (función `first_passage_bar`)
**Problema:** No hay penalización temporal. Señales que tardan 200 barras se evalúan igual que las que tardan 5.
**Fix:** Agregar `max_barras` como tercer resultado de triple barrier:
```python
def first_passage_bar(close, highs, lows, t0, scale, blanco, max_barras=40):
    ...
    if event_i >= max_barras:
        return {"resuelto": False, "hit": False, "favorable": 0.0,
                "mae": 0.0, "mfe": 0.0, "bars": max_barras, "timeout": True}
```
**Nota:** `max_barras = ceil(1/scale)`. Para zz25=2.5% → 40b. Para zz50=5.0% → 20b. Para zz75=7.5% → 14b.

### C10 — Renombrar `perfil_3d_régimen` → `perfil_escala_régimen`
**Archivo:** `evaluador_vela_a_vela.py` y `consolidar_ranking.py`
**Problema:** El nombre sugiere que mide D1/D2/D3 del vector de estado. En realidad mide zz25/zz50/zz75 × ALZA/BAJA.
**Fix:** Renombrar la clave en `evaluador_vela_a_vela.py` L411 y actualizar referencias en `consolidar_ranking.py` L109-110, `ejercicios_regimen.py` L76.

---

## ⚪ P2 — Arquitectura (2 correcciones)

### C11 — Conclusiones dinámicas para todos los ejercicios (framework)
**Archivo:** `ejercicios_regimen.py`
**Problema:** Las conclusiones de E1, E2, E4, E6 son templates estáticos que no reflejan los datos.
**Fix:** Crear función `_generar_conclusion(ejercicio, resultados)` que genere texto dinámicamente:
- Si lift significativo → "CONFIRMADO"
- Si N < 21 → "DIAMANTE §3.3 — datos insuficientes"
- Si p > α' → "NO SIGNIFICATIVO tras Bonferroni"
- Si contradice hipótesis → "RECHAZADO"

### C12 — Documentar ventanas de datos por era en E3
**Archivo:** `ejercicios_regimen.py`
**Problema:** E3 usa todo el lake (1993→2026) para credit_stress que tiene inception 2007. Funcionalmente correcto por NaN, pero no documentado.
**Fix:** Agregar nota explícita: "Credit SK tiene NaN pre-2007 → _get_dim retorna NaN → la condición falla → funcionalmente correcto. Documentar para mantenibilidad."

---

## 🟡 P1 — Nuevas Señales Dimensionales (4 correcciones)

### C13 — SKEW D1=0: Señal de complacencia extrema faltante
**Archivo:** `arnes/señales.py`
**Datos:** SKEW D1=0 ocurre en **516 pivotes (32%)** — es el estado más común de SKEW. No tenemos ninguna señal que lo capture. Solo `skew_paranoia_exit` captura D1=5 (0.6%).
**Interpretación:** SKEW en D1=0 significa que el mercado NO está pagando por protección de cola = complacencia extrema. Es una señal de EXIT (techo de mercado).
**Fix:** Crear señal `skew_complacencia_entry` (tipo="exit", D1=0 de SKEW).

### C14 — BSI D1=0,1: Señal de washed-out extendido faltante
**Archivo:** `arnes/señales.py`
**Datos:** BSI D1=0 (161 pivotes) + D1=1 (428 pivotes) = 589 pivotes (37%). Existe `bsi_washed_out` (D1=0) pero no existe señal para D1=1 que es 2.6× más frecuente.
**Interpretación:** BSI D1=1 es "casi washed out" — el breadth está muy comprimido pero no en el piso absoluto. Puede ser una señal de entry más temprana que `bsi_washed_out`.
**Fix:** Crear señal `bsi_compression_entry` (tipo="entry", D1≤1 de BSI).

### C15 — CREDIT 0__0__x: Piso+caída como entry de crédito
**Archivo:** `arnes/señales.py`
**Datos:** 24 pivotes de CREDIT en estado (0__0__x) — piso absoluto + desacelerando. Es la combinación más rara pero potencialmente más valiosa.
**Interpretación:** Cuando CREDIT está en piso (D1=0) y cayendo (D2=0), es el momento de máxima tensión crediticia. Potencial entry contrarian.
**Fix:** Crear señal `credit_capitulation_entry` (tipo="entry", D1=0 y D2=0 de CREDIT).

### C16 — D3 precursora: Señal de inestabilidad temprana (VIX D3=4)
**Archivo:** `arnes/señales.py`
**Datos:** 183 eventos de VIX D3=4 en el lake (2.2% de barras). D3=4 mide la inestabilidad del VIX mismo (vol-of-vol extremo). En 2025-04-04, D3=4 antecedió a D1=5 en ~30 días.
**Interpretación:** D3=4 es una señal de alerta temprana de que el VIX se está volviendo impredecible. Antes de que el pánico explote (D1=5), la volatilidad del VIX ya está en extremos.
**Fix:** Crear señal `vix_instability_warning` (tipo="entry", VIX D3=4 y D1≤3 — inestabilidad sin pánico confirmado aún).

---

## 🟠 P1 — Puente Dimensional y Fact Store (de auditoría Claude Opus)

### C17 — Generar variantes D2 para top-10 señales D1-only activas
**Archivo:** `arnes/señales.py`
**Datos:** 26/33 señales (79%) ignoran D2. Las V2 demostraron que agregar D2 mejora especificidad (`capitulacion_v2`, `euforia_v2`, `vix_crisis_spike_v2`).
**Propuesta (Claude Opus PC-1):** Para las 10 señales activas de mayor score, generar variantes V2 que incorporen D2 de la estación primaria. Evaluar si la especificidad mejora sin destruir N.
**Orden sugerido:** `credit_stress` + D2, `pcr_put_panic` + D2, `fg_extreme_fear/greed` + D2, `vvix_entry` + D2, `dxy_bearish` + D2.

### C18 — Cruzar evaluadores con Fact Store (alignment score)
**Archivo:** `evaluador_general.py` o nuevo módulo
**Datos (Claude Opus PC-2):** El Fact Store predice `p_bull=0.72` para VIX `5__3__2`, pero el evaluador mide hit rate real directamente. Nadie verifica si coinciden.
**Propuesta:** Agregar al reporte de cada señal un campo `fact_store_alignment`:
- Para cada state_key activo al disparar, registrar su `p_bull` del Fact Store
- Comparar distribución de `p_bull` cuando la señal dispara vs cuando no dispara
- Si divergen significativamente → el Fact Store detecta algo que la señal no captura (o viceversa)

---

## ⚪ P2 — Refinamientos de Clasificación y Persistencia

### C19 — Separar `FILTRO_FONDO` del ranking de señales tácticas
**Archivo:** `consolidar_ranking.py`
**Datos (Claude Opus PC-5):** `sorpresa_total` tiene cadencia 7v, fire rate 32% — dispara 1/3 de los días. Está rankeada junto con señales tácticas de rareza 100-400v. El `score_compuesto` mezcla tipos incomparables.
**Fix:** El ranking ya clasifica `FILTRO_FONDO` como rol, pero el score debe calcularse por catería (no comprar un filtro de fond con una señal táctica).

### C20 — Evaluación de persistencia temporal de las señales
**Archivo:** `evaluador_general.py`
**Datos (Claude Opus PC-6):** El evaluador mide "qué pasó después del disparo" pero no "cuánto dura el régimen favorable una vez detectado". Una señal que permanece activa 3 meses (skew_paranoia) es distinta a una de 1 barra (vix_crisis_spike).
**Fix:** Agregar al reporte métrica de vida media del régimen favorable: cuántas barras pasa el mercado en el estado favorable después de la señal antes de revertir.

---

> **Nota sobre alcance:** Claude Opus incluyó en su auditoría un diseño de "entry gate" arquitectónico que excede el scope actual. Nos aislamos de esa propuesta. Las correcciones C17-C20 se limitan a puentes detectables con la infraestructura existente.

---

## ORDEN DE EJECUCIÓN

| # | Prioridad | Corrección | Archivo | Esfuerzo | Depende de |
|:-:|:---------:|:-----------|:--------|:--------:|:-----------|
| **1** | 🔴 P0 | C1: E1 conclusión dinámica (76%→32.6%) | `ejercicios_regimen.py` | 5 min | — |
| **2** | 🔴 P0 | C2: E4 conclusión dinámica (≤5→10.0) | `ejercicios_regimen.py` | 5 min | — |
| **3** | 🔴 P0 | C3: E5 lift negativo → hipótesis RECHAZADA | `ejercicios_regimen.py` | 5 min | — |
| **4** | 🔴 P0 | C4: E6 N=0 bear → INCONCLUSO | `ejercicios_regimen.py` | 2 min | — |
| **5** | 🔴 P0 | C5: CI95 Clopper-Pearson en 6 ejercicios | `ejercicios_regimen.py` | 15 min | — |
| **6** | 🔴 P0 | C6: Bonferroni en ranking maestro | `consolidar_ranking.py` | 10 min | — |
| **7** | 🔴 P0 | C7: p-values + Bonferroni en E1-E6 | `ejercicios_regimen.py` | 15 min | C5 |
| **8** | 🟡 P1 | C8: E5 rediseño con `arnes/confluencia.py` (D1+D2+D3) | `ejercicios_regimen.py` | 30 min | C3 |
| **9** | 🟡 P1 | C9: Time-stop en first-passage (max_barras) | `evaluador_general.py` | 20 min | — |
| **10** | 🟡 P1 | C10: Renombrar perfil_3d → perfil_escala | 3 archivos | 10 min | — |
| **11** | 🟡 P1 | **C13: SKEW D1=0 → señal `skew_complacencia_entry`** | `arnes/señales.py` | 15 min | — |
| **12** | 🟡 P1 | **C14: BSI D1=0,1 → señal `bsi_compression_entry`** | `arnes/señales.py` | 15 min | — |
| **13** | 🟡 P1 | **C15: CREDIT 0__0__x → señal `credit_capitulation_entry`** | `arnes/señales.py` | 15 min | — |
| **14** | 🟡 P1 | **C16: VIX D3=4 precursora → señal `vix_instability_warning`** | `arnes/señales.py` | 15 min | — |
| **15** | ⚪ P2 | C11: Framework conclusiones dinámicas | `ejercicios_regimen.py` | 20 min | C1-C4 |
| **16** | ⚪ P2 | C12: Documentar eras en E3 | `ejercicios_regimen.py` | 5 min | — |
| **17** | 🟠 P1 | C17: Variantes D2 para top-10 señales D1-only | `arnes/señales.py` | 30 min | — |
| **18** | 🟠 P1 | C18: Fact Store alignment score en reportes | `evaluador_general.py` | 30 min | — |
| **19** | ⚪ P2 | C19: Score separado por categoría (fondo vs tácticas) | `consolidar_ranking.py` | 15 min | — |
| **20** | ⚪ P2 | C20: Persistencia temporal del régimen favorable | `evaluador_general.py` | 15 min | — |

---

## VERIFICACIÓN POST-CORRECCIÓN

```bash
# 1. Conclusiones dinámicas verificadas
cd /root/botero-trade
PYTHONPATH=research/01_señales_entry_exit:. backend/.venv/bin/python3 -c "
import json
ej = json.load(open('data/research/signals/ejercicios_regimen_e1_e6.json'))
for e in ['E1','E2','E3','E4','E5','E6']:
    r = ej[e]
    print(f'{e}: conclusion={r.get(\"conclusion\", \"?\")[:80]}')
    # Verificar que NO contenga texto hardcoded del template viejo
    assert '76%' not in r.get('conclusion',''), f'{e} aun tiene conclusion hardcoded'
    assert '5 barras' not in r.get('conclusion',''), f'{e} aun tiene conclusion hardcoded'
"

# 2. CI95 presentes en todos los ejercicios
PYTHONPATH=research/01_señales_entry_exit:. backend/.venv/bin/python3 -c "
ej = json.load(open('data/research/signals/ejercicios_regimen_e1_e6.json'))
for e_name, e_data in ej.items():
    has_ci = any('ci95' in str(k).lower() or 'ci_lower' in str(v) for k, v in e_data.items() if isinstance(v, dict))
    print(f'{e_name}: CI95 {\"✅\" if has_ci else \"❌\"}')
"

# 3. Bonferroni en ranking
PYTHONPATH=research/01_señales_entry_exit:. backend/.venv/bin/python3 -c "
import json
rank = json.load(open('data/research/signals/ranking_maestro.json'))
r = rank['ranking']
has_bonf = 'p_bonferroni' in r[0] if r else False
print(f'Ranking: Bonferroni {\"✅\" if has_bonf else \"❌\"}')
print(f'Total senales: {len(r)}')
"

# 4. Time-stop implementado
grep -n "max_barras\|timeout" research/01_señales_entry_exit/evaluador_general.py | head -5

# 5. Tests pasan
backend/.venv/bin/python3 -m pytest tests/test_arnes_timing.py backend/modules/entry_decision/tests/test_compositor.py -v

# 6. Re-ejecutar ejercicios con conclusiones dinámicas
PYTHONPATH=research/01_señales_entry_exit:. backend/.venv/bin/python3 research/01_señales_entry_exit/ejercicios_regimen.py
```

---

## MAPA DE ARQUITECTURA POST-CORRECCIÓN

```
┌──────────────────────────────────────────────────────────────────┐
│                   ECOSISTEMA POST-CORRECCIÓN                       │
│                                                                      │
│  ┌──────────────┐    ┌───────────────────────────┐                 │
│  │ Lake/Pivotes  │───▶│ evaluador_general.py      │                 │
│  │ D1/D2/D3 bins │    │ First-passage + TIME-STOP  │                 │
│  │ state_keys    │    │ Timing + CI95 + D2/D3     │                 │
│  │ fact_stores   │    └───────────────────────────┘                 │
│  └──────────────┘             │                                    │
│         │                     ▼                                    │
│         │           ┌───────────────────────────┐                 │
│         └──────────▶│ evaluador_vela_a_vela.py    │                 │
│                     │ perfil_escala_regimen ✓     │                 │
│                     │ Inception filter + Baseline │                 │
│                     └───────────────────────────┘                 │
│         │                     │                                    │
│         └──────────▶│ ejercicios_regimen.py       │                 │
│                      │ Conclusiones DINAMICAS ✓   │                 │
│                      │ CI95 + Bonferroni ✓        │                 │
│                      │ E5 rediseñado (D1+D2+D3)   │                 │
│                      └───────────────────────────┘                 │
│                                  │                                    │
│                                  ▼                                    │
│                      ┌───────────────────────────┐                 │
│                      │ consolidar_ranking.py      │                 │
│                      │ Bonferroni + DSR ✓         │                 │
│                      └───────────────────────────┘                 │
│                                                                      │
│  ═══════════════════════════════════════════════════════════════     │
│  PUENTE EVALUADOR ↔ FACT STORE (P2 futuro):                         │
│  evaluador consulta p_bull del state_key activo en fact_store       │
│  y compara con first-passage observado.                             │
│  ═══════════════════════════════════════════════════════════════     │
└──────────────────────────────────────────────────────────────────┘
```

---

## VEREDICTO FINAL

| Categoría | Calificación | Por qué |
|:----------|:-----------:|:--------|
| Ejercicios E1-E6 | 🔴 4/6 con errores factuales | Conclusiones hardcoded que contradicen datos |
| Cobertura D1 | ✅ 94% de señales | 31/33 usan D1 correctamente |
| Cobertura D2 | ⚠️ 21% señales, 0% evaluadores | 7 señales usan D2, nadie evalúa su impacto |
| Cobertura D3 | 🔴 6% señales, 0% evaluadores | 2 señales usan D3 |
| D1+D2+D3 simultáneo | ⚠️ 0/33 señales | Ninguna usa las 3 dimensiones |
| Variantes D2 (V2) | 🔴 0/10 top activas | Sin expandir el éxito de las V2 (C17) |
| Fact Store ↔ Evaluador | ⚠️ Desconectados | Dos mundos paralelos (C18) |
| Estocasticidad | ❌ 0% | Todo determinístico. Sin Monte Carlo, sin CI95 (P0) |
| Time-stop | ❌ No implementado | Triple barrier incompleta (P1) |
| Ranking separado por tipo | ❌ No implementado | FILTRO_FONDO mezclado con tácticas (C19) |
| Persistencia temporal | ❌ No existe | No hay métrica de vida media del régimen (C20) |
| Ranking maestro | ⚠️ Sin Bonferroni | Sin ajuste por 33 pruebas |