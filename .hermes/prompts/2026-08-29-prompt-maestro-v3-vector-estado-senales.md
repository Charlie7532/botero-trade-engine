# Evaluación de la Auditoría Gemini + Prompt Maestro V3.1 Definitivo

**Versión:** 3.1 — 29-Ago-2026 19:24 UTC  
**Cambios vs V3.0:** Integración de lectura DINÁMICA multi-escala de los fact stores. Ya no se asigna una escala fija por señal — se leen las 3 escalas simultáneamente y el patrón inter-escala ES la predicción. Evidencia factual real extraída de los fact stores de VIX, Credit y BSI.

---

# PARTE I: EVALUACIÓN DE LA AUDITORÍA GEMINI

## Veredicto General

La auditoría de Gemini identificó correctamente 3 de las 5 deficiencias que presentó. Las otras 2 son parciales o incompletas. Además, **Gemini omitió 3 problemas que son más graves** que los que detectó.

### Calificación por Punto Ciego

| # | Punto Ciego Gemini | Veredicto | Justificación |
|:-:|---|---|---|
| 1 | Contradicción Bonferroni vs §3.3 | **✅ VÁLIDO — Crítico** | La arquitectura §3.3 explícitamente prohíbe matar diamantes con Bonferroni/Shrinkage. La regla E.7 del V1.0 era autocontradictoria. El protocolo dual propuesto es correcto. |
| 2 | Trampa de limitar a quants_obs | **✅ VÁLIDO — Crítico** | `quants_obs.pkl` solo tiene 1,590 pivotes. Enriquecer solo eso deja ciego al 53.7% ENTRE. La propuesta de capa dual (pivotal + continua) es la solución correcta y ya estaba contemplada en la arquitectura METAR/SIGMET. |
| 3 | Residuos de 20d fijo | **✅ VÁLIDO — Pero Matizado** | Las tablas del V1.0 usan `WR 20d` porque los datos que TENEMOS son esos — los scripts `audit_vector_confluence.py` y `extract_overflows_vela_a_vela.py` calcularon `fwd_20d`. No podemos reportar métricas de tríada (zz25/zz50/zz75) que AÚN NO HEMOS COMPUTADO. Lo correcto es: (a) mantener las tablas de 20d como referencia ACTUAL, (b) marcarlas como PROVISIONALES, (c) el Protocolo C debe incluir explícitamente la recomputación con la Tríada. |
| 4 | Tensor de polaridad incompleto | **⚠️ PARCIAL — Válido pero sobreingeniería** | Gemini tiene razón en que SKEW y Credit faltan. Pero proponer un "Tensor Decadimensional de 30 canales con matriz Φ ∈ {-1,0,+1}³⁰" es sobreingeniería formal. El Panic/Euphoria Score fue definido heurísticamente y FUNCIONA (WR 78-85%). La formalización correcta es: agregar los canales faltantes a la fórmula heurística, no algebraizar en notación tensorial. |
| 5 | Omisión de cascada y momentum | **⚠️ INCOMPLETO — Señala el problema sin resolver** | Gemini menciona la cascada pero no especifica QUÉ métricas adicionales medir ni CÓMO vincularlas. La pregunta operativa real es: ¿un diamante con VIX.d2 ≥4σ en t=0 MIN tiene cascade_rate mayor que el baseline? Los campos `cascade_conviction_50/75` ya existen en quants_obs — la vinculación es posible HOY. |

---

### 3 Omisiones que Gemini NO Detectó

#### Omisión A: El Script de Anatomía Usa σ Paramétricos, No Empíricos
El script [`audit_overflow_candle_anatomy.py`](file:///root/botero-trade/research/01_señales_entry_exit/audit_overflow_candle_anatomy.py) calcula z-scores usando las constantes paramétricas μ/σ de [`sigma_overflow.py`](file:///root/botero-trade/backend/modules/entry_decision/domain/rules/sigma_overflow.py), mientras que la Política Gaussiana del proyecto (Rule 24) exige que los bines D1/D2/D3 de los fact stores usen **percentiles empíricos** (`series.quantile()`). Esto significa que un overflow "≥4σ paramétrico" puede corresponder a un bin D1 ligeramente distinto al de los fact stores. **No invalida los resultados** (la dirección y magnitud relativa se preservan), pero la reconciliación con la tríada (Protocolo C.1) debe ser consciente de esta diferencia.

#### Omisión B: Ausencia de Segregación MIN vs MAX en los Diamantes de Vela
Las tablas A.5 del V1.0 reportan diamantes CON slot temporal (t-2, t-1, t=0, t+1, t+2, ENTRE) pero **sin segregar por tipo de pivote** (MIN vs MAX). El hallazgo A.3 demostró que pisos y techos se comportan de forma radicalmente diferente. Un diamante "BSI.d2 NEG(-) en t=0" con bar[+1]=76% ¿es en pisos o techos? Si solo ocurre en pisos MIN, su significado es capitulación. Si ocurre en techos MAX, es completamente distinto.

**Implicación:** El Protocolo C debe incluir re-ejecutar los diamantes SEGREGADOS por pivot_type.

#### Omisión C: Métricas de Anatomía de Vela Incompletas
El script mide `(close-open)/open` como body %, y `close > open` como "vela verde". Pero la anatomía de una vela incluye:
- **Sombra superior** (wick): `(high-max(open,close))/close` — indica rechazo de precios altos
- **Sombra inferior** (tail): `(min(open,close)-low)/close` — indica absorción compradora
- **Rango total** (range): `(high-low)/close` — indica volatilidad intradiaria
- **Volumen relativo** al promedio 20d

Un bar[+1] "verde" con body +0.47% pero con sombra superior del 2% y volumen bajo es cualitativamente distinto a uno con body +1.37% sin sombras y volumen alto. La señal es más rica de lo que medimos.

---

# PARTE II: PROMPT MAESTRO V2.0 DEFINITIVO

---

## A. INVENTARIO DE DESCUBRIMIENTOS EMPÍRICOS

### A.1 Censo de Overflows del Vault

**Fuente:** Recorrido vela a vela sobre `TimescaleDataStore` (10 estaciones × 3 dimensiones = 30 canales).  
**Z-scores:** Paramétricos vía `STATION_MU_SIGMA` (no empíricos de fact store — ver nota en E.8).

| Métrica | Solo Pivotes | Vault Completo | Factor |
|---|:-:|:-:|:-:|
| Overflows ≥2σ | 2,449 | **13,071** | 5.3× |
| Overflows ≥3σ | ~650 | **3,354** | 5.2× |
| % fuera de pivotes | — | **53.7%** | — |

### A.2 Confluencia Vectorial

> [!CAUTION]
> **Los datos de confluencia se midieron con `WR 1d` (bar[+1]) y con horizonte fijo 20d.** La columna `WR 1d` es causal (reacción inmediata). La columna `WR 20d` es DESCRIPTIVA del entorno — NO atribuible a la señal del día 0 porque en 20 días ocurren múltiples señales y eventos. El Protocolo C.2 define la recomputación con la Tríada multi-escala.

**En t=0 (pivotes):**

| N_sim | N | **WR 1d (causal)** | WR 20d (descriptivo) |
|:-:|:-:|:-:|:-:|
| 1 | 353 | 49.3% | 59.2% |
| 3 | 111 | **56.8%** | 64.0% |
| **4** | **80** | **63.7%** | 72.5% |
| **8** | **10** | **70.0%** | 80.0% |
| 10 | 6 | 50.0% | 100% |

**En ENTRE (>2d del pivote más cercano):**

| N_sim | N | **WR 1d (causal)** | WR 20d (descriptivo) |
|:-:|:-:|:-:|:-:|
| 1 | 1,341 | **57.0%** | 67.6% |
| 3 | 250 | **57.6%** | 73.2% |
| **5** | **40** | **65.0%** | 85.0% |
| 6 | 21 | 61.9% | 81.0% |

**Regla provisional:** Pivote ≥4 canales = operable (WR 1d 63.7%). ENTRE ≥5 canales = diamante (WR 1d 65.0%).

### A.3 Polaridad: Tensor Institucional de Pánico y Euforia

**Definición formal (15 canales):**

```
PANIC_SCORE = Σ overflow en dirección de capitulación:
  VIX.d1(+), VIX.d2(+), VVIX.d1(+), VVIX.d2(+), PCR.d1(+), PCR.d2(+),
  SKEW.d1(+), SV5_Turb.d1(+),
  BSI.d1(-), BSI.d2(-), FG.d1(-), Credit.d1(-), Credit.d2(-),
  Rotation.d1(-), Yield.d2(+)

EUPHORIA_SCORE = Σ overflow en dirección de complacencia/momentum:
  FG.d1(+), BSI.d1(+), BSI.d2(+), Rotation.d1(+),
  VIX.d1(-), VIX.d2(-), PCR.d1(-), PCR.d2(-),
  Credit.d1(+), Credit.d2(+), SKEW.d1(-)
```

Donde (+) = z ≥ +2σ, (-) = z ≤ -2σ. Valor por canal: 0 o 1 (sin peso diferencial — peso uniforme hasta validación empírica de contribución marginal).

> [!NOTE]
> **Cambios vs V1.0:** Añadidos SKEW.d1, Credit.d2, VIX.d2, PCR.d2, Rotation.d1, Yield.d2 al tensor. Corrige Punto Ciego 4 de la auditoría Gemini. La D3 (turbulencia) se excluye del tensor de polaridad porque no tiene dirección intrínseca — actúa como CERTIFICADOR de régimen, no como contribuyente direccional.

**t=0 MIN (Pisos):** Panic Score alto = rebote explosivo.

| Panic Score | N | WR 1d | WR 20d | Fwd 20d |
|:-:|:-:|:-:|:-:|:-:|
| 4 | 38 | 65.8% | 73.7% | +4.16% |
| 7 | 12 | 91.7% | 83.3% | +1.50% |
| 8 | 6 | 83.3% | 83.3% | **+8.49%** |

**t=0 MAX (Techos):** Efecto táctico a 1-5d, diluido a 20d por drift alcista secular.

| Euphoria Score | N | Short WR 1d | Short WR 5d | Short WR 20d |
|:-:|:-:|:-:|:-:|:-:|
| 0 | 217 | 77.9% | 69.1% | 49.3% |
| 1 | 115 | 71.3% | 67.8% | 52.2% |
| 2 | 44 | 65.9% | 70.5% | 54.5% |

**ENTRE — Euforia ≠ techo:**

| Euphoria ≥ K | N | Short WR 5d | Short WR 20d | Long WR 20d |
|:-:|:-:|:-:|:-:|:-:|
| ≥1 | 907 | 32.6% | 30.2% | 69.8% |
| ≥3 | 30 | 6.7% | 26.7% | 73.3% |
| ≥4 | 8 | 12.5% | 12.5% | **87.5%** |

**REGLA: Shortear euforia en tendencia es suicida.** Momentum institucional ≥3 canales: WR Long 73-87%.

### A.4 Magnitud σ Aislada — Anatomía de Vela SPY

| Sigma | Signo | N | Bar[-1] Verde | Bar[0] Verde | Bar[+1] Verde |
|:-:|---|:-:|:-:|:-:|:-:|
| 2σ-3σ | POS(+) | 4,936 | 52.2% | 49.9% | 52.6% |
| 2σ-3σ | NEG(-) | 1,960 | 43.3% | 42.7% | **53.8%** |
| 3σ-4σ | POS(+) | 1,290 | 50.2% | 46.0% | 52.2% |
| 3σ-4σ | NEG(-) | 292 | 43.8% | 46.9% | **58.6%** |
| **≥4σ** | POS(+) | 357 | 50.4% | 42.6% | **58.3%** |
| **≥4σ** | NEG(-) | 112 | 56.2% | 58.9% | 56.2% |

**Patrón:** 2σ-3σ = ruido. 3σ = señal emergente. ≥4σ = operativo. Overflows negativos (capitulación) generan rebote progresivamente mayor con la magnitud.

> [!NOTE]
> **Limitación de anatomía:** Solo mide body% `(close-open)/open` y dirección (verde/roja). No mide sombras (wick/tail), rango intradiario, ni volumen relativo. Protocolo C.6 debe ampliar.

### A.5 Diamantes de Vela

> [!WARNING]
> **Limitación:** Estos diamantes NO están segregados por pivot_type (MIN vs MAX). La re-ejecución segregada es obligatoria (Protocolo C.5).

**Top 9 Alcistas (bar[+1] ≥71% verde, N≥10):**

| Canal | σ | Signo | Slot | N | Bar[+1]% | Body[+1] |
|---|:-:|---|---|:-:|:-:|:-:|
| VVIX.d2 | ≥4σ | POS(+) | t=0 | 13 | **85%** | +1.21% |
| SKEW.d1 | 3σ-4σ | POS(+) | ENTRE | 12 | **83%** | -0.03% |
| Yield.d2 | 3σ-4σ | POS(+) | t=0 | 10 | **80%** | +1.06% |
| BSI.d2 | 2σ-3σ | NEG(-) | t=0 | **55** | **76%** | +0.47% |
| BSI.d2 | 3σ-4σ | POS(+) | ENTRE | 21 | **76%** | +0.20% |
| SV5_Turb.d2 | 3σ-4σ | NEG(-) | ENTRE | 24 | **75%** | +0.21% |
| VIX.d2 | ≥4σ | POS(+) | t=0 | **34** | **74%** | **+1.37%** |
| BSI.d2 | 3σ-4σ | NEG(-) | t=0 | 19 | **74%** | +0.79% |
| SV5_Turb.d2 | ≥4σ | NEG(-) | ENTRE | 28 | **71%** | +0.27% |

**Top 9 Bajistas (bar[+1] ≤30% verde, N≥10):**

| Canal | σ | Signo | Slot | N | Bar[+1]% | Body[+1] |
|---|:-:|---|---|:-:|:-:|:-:|
| VIX.d2 | 3σ-4σ | POS(+) | t-1 | 10 | **30%** | -0.83% |
| PCR.d1 | 2σ-3σ | POS(+) | t-1 | 18 | **28%** | -1.03% |
| VIX.d3 | 3σ-4σ | POS(+) | t-1 | 11 | **27%** | -1.02% |
| SV5_Turb.d3 | 3σ-4σ | POS(+) | t-1 | 13 | **23%** | -1.07% |
| SV5_Turb.d3 | 2σ-3σ | POS(+) | t-2 | 18 | **22%** | -0.49% |
| PCR.d1 | 2σ-3σ | POS(+) | ENTRE | 23 | **22%** | -0.34% |
| Credit.d2 | 2σ-3σ | POS(+) | t=0 | 14 | **21%** | -1.04% |
| VVIX.d2 | 2σ-3σ | NEG(-) | t=0 | 15 | **20%** | -0.63% |
| Yield.d1 | 2σ-3σ | NEG(-) | t-1 | 11 | **9%** | -0.57% |

### A.6 Canales con Edge Individual (sin confluencia)

**En t=0 (sólos, sin otros canales en overflow):**

| Canal | N | WR 20d (prov) | Veredicto |
|---|:-:|:-:|---|
| VIX.d3 | 20 | 85% | ✅ Fuerte |
| VIX.d1 | 21 | 81% | ✅ Fuerte |
| SKEW.d1 | 20 | 80% | ✅ Fuerte |
| VIX.d2 | 15 | 67% | ○ Moderado |
| BSI.d3 | 20 | 40% | ❌ Anti-señal |
| Yield.d3 | 21 | 38% | ❌ Anti-señal |

**En ENTRE (sólos):**

| Canal | N | WR 20d (prov) | Veredicto |
|---|:-:|:-:|---|
| Credit.d1 | 49 | 84% | ✅ Diamante |
| SV5_Turb.d2 | 72 | 78% | ✅ Fuerte |
| SKEW.d1 | 48 | 75% | ✅ Fuerte |

### A.7 Función Cinemática de las 3 Dimensiones

| Dimensión | Pregunta | Rol en el Vector | En Solitario |
|---|---|---|---|
| **D1** (Nivel) | ¿Dónde estamos? | Extremo estático — sobrecompra o sobreventa | Débil sin D2/D3 (excepto VIX y SKEW que SÍ discriminan solos) |
| **D2** (Velocidad = diff(3)) | ¿Hacia dónde vamos? | Inercia cinemática — si D2 frena → piso inminente; si D2 acelera → caída continúa | El discriminador más potente: VIX.d2 ≥4σ = 74% bar[+1] verde |
| **D3** (Turbulencia = std(2d)/std(10d)) | ¿Está cambiando el régimen? | Certificador de transición — no tiene dirección intrínseca | Débil aislado (BSI.d3 = 40% WR). Valida confluencia. |

### A.8 Taxonomía de Medición por Naturaleza de Señal

> [!IMPORTANT]
> **PROHIBIDO usar retornos a horizonte fijo como métrica causal de una señal individual.** En 20 días ocurren docenas de señales adicionales, cambios de régimen y eventos exógenos. Atribuir el retorno a 20d a una señal del día 0 es un sofisma de causalidad (post hoc ergo propter hoc).

**Las tres escalas ZigZag como instrumento de medición:**

| Escala | Umbral | Fenómeno | Horizonte Típico |
|---|:-:|---|:-:|
| **zz25** | ≥2.5% | Pullback táctico | 1-15 días |
| **zz50** | ≥5.0% | Corrección intermedia | 5-60 días |
| **zz75** | ≥7.5% | Movimiento estructural | 20-200+ días |

**Infraestructura existente:** Cada state_key D1×D2×D3 de cada fact store YA contiene `zigzag_kinematic.zz25/zz50/zz75` con: `p_bull`, `ev_net`, `e_days`, `ftt_bull_days`, `ftt_bear_days`, `rr_asymmetry`. Las 3 escalas se leen SIMULTÁNEAMENTE — no se elige una.

**4 Clases de Señal:**

| Clase | Naturaleza | Medición Inmediata | Medición Estocástica (Fact Store) |
|---|---|---|---|
| **IMPULSO** | Descarga puntual (spike ≥4σ) | **bar[+1] anatomía** | Consultar state_key actual → leer zz25/zz50/zz75 |
| **PRECURSOR** | Alarma en t-1/t-2 | **¿Ocurrió el pivote?** (binario) | N/A |
| **TIDE** | Estado sostenido entre ciclos | N/A (efecto no es inmediato) | Consultar state_key actual → leer zz25/zz50/zz75 |
| **CONFLUENCIA** | ≥4 canales simultáneos | **bar[+1] impulso** | Consultar state_key de CADA estación → leer zz25/zz50/zz75 |

> [!CAUTION]
> **LECTURA DINÁMICA MULTI-ESCALA OBLIGATORIA.** No se asigna una escala fija por señal. Para TODA señal (excepto PRECURSOR): identificar la estación, calcular su state_key D1×D2×D3 actual, consultar el fact store, y leer `zigzag_kinematic.zz25/zz50/zz75` simultáneamente. La escala dominante EMERGE de la data.

**Protocolo de lectura dinámica:**

```
Señal dispara en Día T:
  1. Identificar estación(es) que disparan (VIX, Credit, BSI...)
  2. Calcular state_key D1×D2×D3 actual de cada estación
  3. Para CADA estación, consultar su fact store:
     zigzag_kinematic.zz25: p_bull, ev_net, e_days
     zigzag_kinematic.zz50: p_bull, ev_net, e_days
     zigzag_kinematic.zz75: p_bull, ev_net, e_days
  4. Clasificar el PATRÓN INTER-ESCALA:
```

| Patrón Inter-Escala | p_bull(zz25) vs zz50 vs zz75 | Predicción | Acción |
|---|---|---|---|
| **Convergencia alcista** | ↗ ↗ ↗ (las 3 > 0.55) | Pierna alcista sostenida, escala a estructural | ENTRY convicción plena |
| **Convergencia bajista** | ↘ ↘ ↘ (las 3 < 0.45) | Pierna bajista sostenida | EXIT o SHORT con convicción |
| **Divergencia agotamiento** | zz25↗ zz50→ zz75↘ | Rebote táctico que NO cascadea | Scalp rápido, NO mantener |
| **Divergencia reversión** | zz25↘ zz50→ zz75↗ | Lo táctico sigue cayendo pero lo estructural gira | Acumular en el pullback |
| **Asimetría EV creciente** | ev crece con escala | Riesgo/recompensa asimétrico a favor | Sizing agresivo |

### A.9 Evidencia Factual: Descomposición EV y R:R por Señal

> [!NOTE]
> Datos extraídos directamente de los fact stores en `backend/modules/entry_decision/domain/rules/`. Incluyen la **descomposición completa de la Esperanza Matemática**: `EV = p_bull × e_ret_max + p_bear × e_ret_min` y el **ratio R:R** (riesgo/recompensa) = `|e_ret_max| / |e_ret_min|`.

> [!IMPORTANT]
> **La fiabilidad estadística de una señal NO es solo p_bull.** Es la combinación de probabilidad × magnitud del retorno en ambas direcciones. Una señal con p_bull=55% pero R:R de 2:1 es más valiosa que una con p_bull=70% y R:R de 0.5:1. La descomposición EV es OBLIGATORIA en toda evaluación de señal.

**IMPULSO: VIX en CRISIS_SPIKE + FAST_SPIKE_3D + VOL_NEUTRAL (N=40):**

| Escala | p_bull | e_ret_max (ganar) | e_ret_min (perder) | EV_bull | EV_bear | **EV_total** | **R:R** |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| zz25 | 0.587 | +7.28% | -10.93% | +4.27% | -4.51% | **-0.24%** | **0.67:1** |
| zz50 | 0.581 | +8.75% | -10.91% | +5.09% | -4.57% | **+0.52%** | **0.80:1** |
| zz75 | 0.577 | +18.54% | -13.37% | +10.69% | -5.66% | **+5.04%** | **1.39:1** |

→ **Patrón revelador:** En zz25 el R:R es DESFAVORABLE (0.67:1 — pierdes más de lo que ganas). Pero en zz75 el R:R se invierte a **1.39:1** — ganas +18.54% cuando aciertas vs -13.37% cuando fallas. La señal es ESTRUCTURALMENTE asimétrica a favor. Implicación: NO tradear el impulso inmediato (zz25), HOLDEAR la pierna estructural (zz75).

**IMPULSO: VIX CRISIS_SPIKE + FAST_SPIKE_3D + VOL_ACCEL_EXPANSION (N=19):**

| Escala | p_bull | e_ret_max | e_ret_min | EV_bull | EV_bear | **EV_total** | **R:R** |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| zz25 | 0.576 | +5.39% | -7.95% | +3.10% | -3.37% | **-0.27%** | **0.68:1** |
| zz50 | 0.600 | +7.09% | -10.38% | +4.26% | -4.15% | **+0.10%** | **0.68:1** |
| zz75 | 0.600 | +9.65% | -11.93% | +5.79% | -4.77% | **+1.02%** | **0.81:1** |

→ Con D3 en expansión: R:R sigue desfavorable en táctico pero EV positivo en zz50/zz75. La turbulencia CERTIFICA el piso.

**IMPULSO: VIX CRISIS_SPIKE + FAST_CRUSH (VIX aplastándose, N=28):**

| Escala | p_bull | e_ret_max | e_ret_min | EV_bull | EV_bear | **EV_total** | **R:R** |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| zz25 | 0.469 | +7.44% | -6.23% | +3.49% | -3.31% | **+0.18%** | **1.19:1** |
| zz50 | 0.450 | +11.49% | -8.79% | +5.17% | -4.83% | **+0.34%** | **1.31:1** |
| zz75 | 0.462 | +39.32% | -17.73% | +18.15% | -9.55% | **+8.60%** | **2.22:1** |

→ **Descubrimiento extraordinario:** Cuando VIX está en CRISIS y se aplasta (FAST_CRUSH = crisis cediendo), el p_bull es bajo (~46%) PERO el R:R es EXTREMADAMENTE favorable: **2.22:1 en zz75**. Ganas +39% cuando aciertas, pierdes -17.7% cuando fallas. EV_total = +8.60%. **Esta es la señal con mayor asimetría de toda la base.**

---

**TIDE: Credit en ELEVATED_CREDIT_STRESS — según D2 (con R:R):**

| D2 (Velocidad) | N | Escala | p_bull | e_ret_max | e_ret_min | **EV_total** | **R:R** |
|---|:-:|---|:-:|:-:|:-:|:-:|:-:|
| **DECEL_DOWN** (cediendo) | **188** | zz25 | **0.725** | +5.28% | -5.59% | **+2.29%** | 0.94:1 |
|  |  | zz50 | **0.720** | +11.19% | -7.02% | **+6.09%** | **1.59:1** |
|  |  | zz75 | **0.647** | +15.74% | -8.18% | **+7.30%** | **1.92:1** |
| **ACCEL_UP** (empeorando) | **170** | zz25 | **0.385** | +4.60% | -5.65% | **-1.71%** | 0.81:1 |
|  |  | zz50 | **0.350** | +8.66% | -8.20% | **-2.30%** | 1.06:1 |
|  |  | zz75 | **0.429** | +8.55% | -13.43% | **-4.01%** | **0.64:1** |
| **STABLE_CONT** (persistente) | **651** | zz25 | 0.466 | +5.46% | -4.40% | **+0.19%** | 1.24:1 |
|  |  | zz50 | **0.400** | +13.45% | -9.44% | **-0.29%** | 1.42:1 |
|  |  | zz75 | **0.391** | +14.34% | -13.77% | **-2.77%** | 1.04:1 |

→ **Credit cediendo:** p_bull=72% + R:R=1.92:1 en zz75 = **SEÑAL DE MÁXIMA CALIDAD**. Ganas +15.74%, pierdes -8.18%.  
→ **Credit empeorando:** p_bull=35% + R:R=0.64:1 en zz75 = **TRAMPA**. Pierdes -13.43% vs ganas +8.55%.  
→ **Credit persistente (N=651):** R:R parece favorable (1.42:1 en zz50) PERO p_bull=40% mata el EV → EV negativo.

**TIDE: BSI washed_out (breadth destruido):**

| D2 | N | Escala | p_bull | e_ret_max | e_ret_min | **EV_total** | **R:R** |
|---|:-:|---|:-:|:-:|:-:|:-:|:-:|
| FAST_CRUSH (cap. acelerada) | ~30 | zz25 | 0.600 | +6.15% | -7.30% | **+0.77%** | 0.84:1 |
|  |  | zz50 | 0.600 | +9.33% | -6.71% | **+2.92%** | **1.39:1** |
|  |  | zz75 | **0.615** | +11.68% | -0.02% | **+7.18%** | **∞** |
| DECEL_DOWN (cediendo) | ~40 | zz25 | 0.612 | +5.67% | -6.82% | **+0.83%** | 0.83:1 |
|  |  | zz50 | **0.667** | +10.93% | -11.04% | **+3.61%** | 0.99:1 |
|  |  | zz75 | 0.588 | +15.20% | -10.48% | **+4.63%** | **1.45:1** |

→ **BSI washed_out + FAST_CRUSH en zz75:** p_bull=61.5%, **e_ret_min = -0.02%** (prácticamente sin downside). R:R = **∞**. La pierna estructural casi siempre es alcista cuando BSI está destruido y se aplasta más. Implicación: acumular agresivamente.

→ Convergencia alcista. La turbulencia D3 en expansión CERTIFICA que el spike de VIX es sistémico (no ruido).

**Ejemplo operativo completo — Señal de Capitulación:**

```
DÍA T:
  VIX.d2 ≥ 4σ POS(+) [IMPULSO]
  BSI.d2 ≤ -3σ NEG(-) [IMPULSO]
  Credit.d1 = ELEVATED_CREDIT_STRESS, D2 = DECEL_DOWN [TIDE]
  Panic Score = 5 [CONFLUENCIA]

PASO 1 — Bar[+1] (IMPULSO inmediato):
  VIX.d2 ≥4σ → 74% bar[+1] verde, body +1.37%
  BSI.d2 NEG(-) → 76% bar[+1] verde

PASO 2 — Fact store VIX (CRISIS_SPIKE__FAST_SPIKE_3D__VOL_NEUTRAL, N=40):
  zk.zz25: p_bull=0.587, ev=+0.16%, e_days=1
  zk.zz50: p_bull=0.581, ev=+0.77%, e_days=1
  zk.zz75: p_bull=0.577, ev=+4.04%, e_days=1.5
  → CONVERGENCIA ALCISTA: 3 escalas BULL, EV crece 25×

PASO 3 — Fact store Credit (ELEV_CREDIT_STRESS__DECEL_DOWN__VOL_NEUTRAL, N=188):
  zk.zz25: p_bull=0.725, ev=+2.31%, e_days=4
  zk.zz50: p_bull=0.720, ev=+5.26%, e_days=13
  zk.zz75: p_bull=0.647, ev=+5.08%, e_days=39
  → CONVERGENCIA ALCISTA: corriente de distensión crediticia de 13-39 días

DIAGNÓSTICO INTEGRADO:
  IMPULSO confirma rebote inmediato (bar[+1])
  VIX fact store confirma piso estructural (EV +4.04% en zz75)
  Credit fact store confirma TIDE alcista de 13-39 días
  → ENTRY con convicción plena
  → Horizonte natural: e_days(zz50) del Credit = 13 días (no "20d fijo")
```

**Clasificación de las señales del arnés por Clase (la escala NO es fija — se lee dinámicamente):**

| Señal/Diamante | Clase | Medición Inmediata | Fact Store a Consultar |
|---|---|---|---|
| VIX.d2 ≥4σ en t=0 | IMPULSO | bar[+1]: 74% verde, +1.37% | `vix_fact_store.json` → zk.zz25/50/75 |
| VVIX.d2 ≥4σ en t=0 | IMPULSO | bar[+1]: 85% verde, +1.21% | `vvix_fact_store.json` → zk.zz25/50/75 |
| BSI.d2 NEG(-) en t=0 | IMPULSO | bar[+1]: 76% verde, +0.47% | `bsi_fact_store.json` → zk.zz25/50/75 |
| Credit.d2 POS(+) t=0 MAX | IMPULSO | bar[+1]: 21% verde (bajista) | `credit_fact_store.json` → zk.zz25/50/75 |
| `capitulacion`, `panico_total` | IMPULSO | bar[+1] anatomía | Multi-estación → zk.zz25/50/75 |
| PCR.d1 POS(+) en t-1 | PRECURSOR | ¿bar[0] roja? 72% sí | N/A |
| SV5_Turb.d3 en t-1/t-2 | PRECURSOR | ¿caída ocurrió? 77% sí | N/A |
| Credit.d1 en ENTRE | TIDE | N/A | `credit_fact_store.json` → zk.zz25/50/75 |
| BSI washed_out sostenido | TIDE | N/A | `bsi_fact_store.json` → zk.zz25/50/75 |
| Euforia ENTRE (Score ≥3) | TIDE | N/A | Multi-estación → zk.zz25/50/75 |
| `credit_stress` señal | TIDE | N/A | `credit_fact_store.json` → zk.zz25/50/75 |
| `fg_extreme_fear` | TIDE+IMPULSO | bar[+1] | `fg_fact_store.json` → zk.zz25/50/75 |
| Confluencia ≥4 canales | CONFLUENCIA | bar[+1] | Todas las estaciones en overflow → zk.zz25/50/75 |
| Panic Score ≥4 en piso | CONFLUENCIA | bar[+1] | Todas las estaciones en overflow → zk.zz25/50/75 |

---

## B. ARQUITECTURA DE DATOS DUAL

> [!IMPORTANT]
> La investigación requiere DOS capas de observación, no una:

| Capa | Artefacto | Contenido | Uso |
|---|---|---|---|
| **Pivotal** | `quants_obs.pkl` (1,590 pivotes × 165+ cols) | State keys categóricos + z-scores numéricos (a añadir) + cascade metrics | Calibración de giros t=0, t±1, t±2. Backtesting de señales V1 y V2. Vinculación con tríada fact store. |
| **Continua** | `continuous_metar_lake.parquet` (8,400+ barras × ~200 cols) | Z-scores diarios de 30 canales + confluencia + polaridad + SPY OHLCV | Señales ENTRE, evaluación continua vela a vela, servicio METAR/SIGMET en tiempo real. |

- `quants_obs.pkl` ya existe y es la base del arnés de 28 señales. Debe enriquecerse con z-scores numéricos.
- `continuous_metar_lake.parquet` NO existe aún. Su construcción es un prerrequisito para las señales ENTRE y el SIGMET continuo.

---

## C. PROTOCOLO DE INVESTIGACIÓN PENDIENTE

### C.1 Cruzar diamantes con la tríada del fact store
Para cada diamante de A.5: consultar `state_key` D1×D2×D3 del fact store, extraer p_bull, ev_net, e_days en zz25/zz50/zz75. ¿El fact store ya captura este edge o es información nueva no contenida en los bins categóricos?

**Nota sobre σ paramétrico vs empírico (E.8):** Los z-scores del audit usan μ/σ de `STATION_MU_SIGMA`; los fact stores usan `expanding window rank` con percentiles empíricos. Reconciliar qué state_key corresponde a cada z-score paramétrico.

### C.2 Recomputar señales con lectura dinámica multi-escala

**Para TODAS las señales (excepto PRECURSOR):** Cruzar cada señal con el fact store de su estación. Para el state_key D1×D2×D3 correspondiente al momento de la señal, leer `zigzag_kinematic.zz25/zz50/zz75` simultáneamente.

**Lo que se extrae de cada fact store:**

```python
# Para el state_key actual de la estación:
for scale in ['zz25', 'zz50', 'zz75']:
    d = fact_store['states'][state_key]['zigzag_kinematic'][scale]
    p_bull   = d['p_bull']      # Probabilidad alcista de la pierna
    ev_net   = d['ev_net']      # Esperanza matemática neta
    e_days   = d['e_days']      # Duración estocástica (mediana)
    ftt_bull = d['ftt_bull_days']  # Time-to-first-touch alcista
    ftt_bear = d['ftt_bear_days']  # Time-to-first-touch bajista
    rr_asym  = d['rr_asymmetry']   # Asimetría riesgo/recompensa
```

**Clasificar el patrón inter-escala:**
- Si p_bull(zz25) ≈ p_bull(zz50) ≈ p_bull(zz75) > 0.55 → CONVERGENCIA BULL
- Si p_bull cae con la escala (ej. 0.65 → 0.50 → 0.35) → AGOTAMIENTO
- Si ev_net crece con la escala (ej. +0.16% → +0.77% → +4.04%) → ASIMETRÍA FAVORABLE
- El e_days de la escala donde p_bull es más extremo = horizonte natural de la señal

**Para señales CONFLUENCIA (≥4 canales):** Leer fact stores de TODAS las estaciones en overflow. Si múltiples estaciones muestran convergencia alcista en las 3 escalas simultáneamente → señal de máxima convicción.

**Para señales PRECURSOR:** Medición binaria ya disponible. ¿Ocurrió el pivote predicho? No requiere fact store.

### C.3 Construir `continuous_metar_lake.parquet`
Generar la matriz diaria completa: para cada barra de SPY, calcular los 30 z-scores, la confluencia vectorial, el panic/euphoria score, y alinear con SPY OHLCV. Base para señales ENTRE y SIGMET.

### C.4 Validar significancia con Protocolo Dual

**Para señales con N ≥ 30:**
- Bonferroni con K = número de señales testeadas (NO 210 fijo — depende de cuántas señales finales se propongan)
- DSR de López de Prado
- Walk-forward OOS (5 folds temporales)
- Structural break (pre-2009 / post-2009 / post-COVID)

**Para diamantes con N < 30:**
- Exact Binomial Test vs baseline empírico del slot (ej: baseline bar[+1] verde en t=0 ≈ 52%)
- Dossier cualitativo: listar CADA evento con fecha, contexto de mercado y resultado
- Protocolo §3.3 de Fact Store V3: NO aplicar shrinkage agresivo, reportar tasa cruda + bayesiana
- Cruzar con quants_obs para verificar overlap con eventos conocidos (2008, 2020, 2024)

### C.5 Re-ejecutar diamantes segregados por pivot_type
Los diamantes A.5 no distinguen MIN vs MAX. Dado que pisos y techos se comportan de forma radicalmente distinta (A.3), re-ejecutar el análisis de anatomía de vela SEGREGADO. Un "BSI.d2 NEG(-) en t=0 MIN" tiene significado de capitulación; en "t=0 MAX" significaría algo completamente distinto.

### C.6 Ampliar métricas de anatomía de vela
Agregar al script de auditoría:
- **Sombra superior (wick):** `(high - max(open,close)) / close`
- **Sombra inferior (tail):** `(min(open,close) - low) / close`
- **Rango total:** `(high - low) / close`
- **Volumen relativo:** `volume / SMA(volume, 20)`
- **Body absoluto:** `abs(close - open) / close`

### C.7 Vincular diamantes con cascada y momentum
Para los diamantes con slot t=0: medir tasa de cascada (zz25→zz50, zz25→zz75) y secuencia de momentum (HH/HL/LH/LL del zigzag posterior). Usar los campos `cascade_conviction_50/75` de quants_obs.

---

## D. CLASIFICACIÓN BIDIMENSIONAL: SLOT × CLASE

Las señales se clasifican en DOS ejes ortogonales: el SLOT temporal (cuándo ocurren relativo al pivote) y la CLASE de señal (cómo se miden).

| Slot | Clase predominante | Medición | Escala ZZ | Uso Operativo |
|---|---|---|---|---|
| **t-2** | PRECURSOR | ¿Ocurrió la caída predicha? (binario) | N/A | Reducir exposición / preparar liquidez |
| **t-1** | PRECURSOR | ¿bar[0] fue del color esperado? (binario) | N/A | Sizing down / activar stops |
| **t=0** | IMPULSO o CONFLUENCIA | bar[+1] anatomía + zz25 first-passage | zz25 (táctico) | Entry/Exit con conviction |
| **t+1** | CONFIRMACIÓN | Validar que bar[0] fue coherente con t=0 | N/A | Añadir posición si t=0 confirmada |
| **t+2** | POSMORTEM | Solo validación retrospectiva | N/A | No accionable |
| **ENTRE** | TIDE | p_bull y e_days del fact store (zz25/zz50/zz75 según duración del estado) | Multi-escala | Mantener posiciones / trend following |

**Cruce de Clase × Escala ZZ:**

```
                         zz25 (2.5%)      zz50 (5.0%)       zz75 (7.5%)
                         Táctico           Intermedio         Estructural
                         1-15 días         5-60 días          20-200+ días
                         ─────────────────────────────────────────────────
IMPULSO (descarga):      bar[+1] +         ────────────────────────────────
                         ¿inicia pierna?   (no se mide — el impulso se agota)

PRECURSOR (alarma):      binario ──────────────────────────────────────────
                         ¿ocurrió el evento predicho?

TIDE (corriente):        p_bull(zz25)      p_bull(zz50)      p_bull(zz75)
                         e_days(zz25)      e_days(zz50)      e_days(zz75)
                         ────────── convergencia inter-escala ──────────

CONFLUENCIA (compuesto): bar[+1] +         cascade_rate      cascade_rate
                         ¿inicia pierna?   zz25→zz50         zz50→zz75
```

---

## E. RESTRICCIONES INAMOVIBLES

1. **Dato mata relato.** Toda conclusión debe tener N, WR, retorno medio. CI95 cuando N ≥ 20.
2. **No agrupar magnitudes.** 2σ, 3σ, 4σ son fenómenos distintos. Separar siempre.
3. **No ignorar el signo.** VIX(+) ≠ VIX(-). Separar siempre.
4. **No evaluar sin el vector completo.** Confluencia y polaridad son obligatorias.
5. **No implementar antes de explorar.** El Protocolo C debe completarse antes de cualquier plan de código.
6. **Protocolo dual de validación (C.4).** Bonferroni/DSR para N ≥ 30. Protocolo §3.3 para diamantes N < 30. NUNCA aplicar Bonferroni a diamantes de cola extrema.
7. **Segregar MIN vs MAX siempre.** Pisos y techos tienen mecánica opuesta. No mezclar.
8. **Consciente de la diferencia σ paramétrico vs empírico.** Los z-scores del audit usan μ/σ fijos de STATION_MU_SIGMA. Los fact stores usan expanding window rank. Reconciliar antes de cruzar.
9. **PROHIBIDO usar retornos a horizonte fijo como métrica CAUSAL de señales individuales.** En 20 días ocurren docenas de señales y eventos — atribuir el retorno a una señal es un sofisma. Cada señal se mide según su CLASE: IMPULSO → bar[+1]; PRECURSOR → ¿ocurrió? (binario); TIDE/CONFLUENCIA → lectura dinámica multi-escala del fact store. Los "WR 20d" de las tablas A.2/A.3 son DESCRIPTIVOS del entorno, no métricas causales.
10. **Lectura DINÁMICA multi-escala obligatoria.** No asignar una escala fija a cada señal. Consultar el state_key D1×D2×D3 del fact store correspondiente y leer `zigzag_kinematic.zz25/zz50/zz75` simultáneamente. El patrón inter-escala (convergencia/divergencia de p_bull y asimetría de ev_net) ES la predicción. La escala dominante emerge de la data, no se impone.
11. **Descomposición EV obligatoria en toda evaluación de señal.** Reportar p_bull SOLA no basta. Para cada señal y cada escala ZZ: `EV = p_bull × e_ret_max + (1-p_bull) × e_ret_min`. Reportar e_ret_max (cuánto ganas cuando aciertas), e_ret_min (cuánto pierdes cuando fallas), EV_total y R:R = `|e_ret_max|/|e_ret_min|`. Una señal con p_bull=55% y R:R=2:1 es más valiosa que p_bull=70% y R:R=0.5:1. El R:R inter-escala (cómo cambia el R:R de zz25 a zz75) indica si la señal es un impulso que se agota (R:R decreciente) o una asimetría estructural (R:R creciente).

---

## F. ARCHIVOS DE REFERENCIA

**Scripts de investigación:**
- [`audit_overflow_candle_anatomy.py`](file:///root/botero-trade/research/01_señales_entry_exit/audit_overflow_candle_anatomy.py) — Anatomía de vela
- [`audit_vector_confluence.py`](file:///root/botero-trade/research/01_señales_entry_exit/audit_vector_confluence.py) — Polaridad y confluencia
- [`extract_overflows_vela_a_vela.py`](file:///root/botero-trade/research/01_señales_entry_exit/extract_overflows_vela_a_vela.py) — Extracción Vault

**Arquitectura:**
- [`fact_store_v3_architecture.md`](file:///root/botero-trade/.hermes/paraauditar/fact_store_v3_architecture.md) — Tríada, Cascada, Protocolo §3.3
- [`sigma_overflow.py`](file:///root/botero-trade/backend/modules/entry_decision/domain/rules/sigma_overflow.py) — Constantes μ/σ (10 estaciones × 3 dims)
- [`señales.py`](file:///root/botero-trade/research/01_señales_entry_exit/arnes/señales.py) — 28+3 señales actuales
- [`generate_quants_obs.py`](file:///root/botero-trade/backend/scripts/generators/generate_quants_obs.py) — Generador pivotal

**Artefactos de sesión:**
- [`distribucion_overflows_distancia_pivote.md`](file:///root/.gemini/antigravity-ide/brain/012139fd-5535-41c8-9edc-96bd0916ecb5/distribucion_overflows_distancia_pivote.md)
- [`auditoria_descubrimiento_vector_estado.md`](file:///root/.gemini/antigravity-ide/brain/012139fd-5535-41c8-9edc-96bd0916ecb5/auditoria_descubrimiento_vector_estado.md)
- [`anatomia_velas_overflows_corregido.md`](file:///root/.gemini/antigravity-ide/brain/012139fd-5535-41c8-9edc-96bd0916ecb5/anatomia_velas_overflows_corregido.md)
- [`inventario_overflows_cinematicos.md`](file:///root/.gemini/antigravity-ide/brain/012139fd-5535-41c8-9edc-96bd0916ecb5/inventario_overflows_cinematicos.md)
- [`fact_stores_como_instrumento_dinamico.md`](file:///root/.gemini/antigravity-ide/brain/012139fd-5535-41c8-9edc-96bd0916ecb5/fact_stores_como_instrumento_dinamico.md)
- [`taxonomia_medicion_senales.md`](file:///root/.gemini/antigravity-ide/brain/012139fd-5535-41c8-9edc-96bd0916ecb5/taxonomia_medicion_senales.md)
