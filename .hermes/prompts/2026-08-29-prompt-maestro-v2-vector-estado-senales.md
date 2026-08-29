# Evaluación de la Auditoría Gemini + Prompt Maestro V2.0 Definitivo

**Fecha:** 29-Ago-2026 18:30 UTC

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

> [!WARNING]
> **Métricas WR 20d son PROVISIONALES.** Fueron computadas con retorno close-to-close a horizonte fijo. La validación definitiva debe usar la Tríada Estocástica (zz25/zz50/zz75). Ver Protocolo C.2.

**En t=0 (pivotes):**

| N_sim | N | WR 1d | WR 20d (prov) | Fwd 20d (prov) |
|:-:|:-:|:-:|:-:|:-:|
| 1 | 353 | 49.3% | 59.2% | +0.62% |
| 3 | 111 | 56.8% | 64.0% | +1.11% |
| **4** | **80** | **63.7%** | **72.5%** | **+3.85%** |
| **8** | **10** | **70.0%** | **80.0%** | **+2.85%** |
| 10 | 6 | 50.0% | 100% | +7.23% |

**En ENTRE (>2d del pivote más cercano):**

| N_sim | N | WR 1d | WR 20d (prov) | Fwd 20d (prov) |
|:-:|:-:|:-:|:-:|:-:|
| 1 | 1,341 | 57.0% | 67.6% | +0.95% |
| 3 | 250 | 57.6% | 73.2% | +1.42% |
| **5** | **40** | **65.0%** | **85.0%** | **+2.09%** |
| 6 | 21 | 61.9% | 81.0% | +2.33% |

**Regla provisional:** Pivote ≥4 canales = operable. ENTRE ≥5 canales = diamante.

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

### C.2 Recomputar confluencia con Tríada Estocástica
Sustituir `WR 20d` y `Fwd 20d` por las métricas multi-escala: p_bull(zz25), p_bull(zz50), p_bull(zz75), EV neto, e_days. Los datos actuales (Sección A.2) son PROVISIONALES medidos en 20d fijo.

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

## D. CLASIFICACIÓN DE SEÑALES POR SLOT TEMPORAL

| Slot | Tipo | Uso Operativo | Horizonte de Efecto |
|---|---|---|---|
| **t-2** | Alerta temprana | Reducir exposición / preparar liquidez | Efecto en bar[0] = 2 días después |
| **t-1** | Precursor | Sizing down / activar stops / cobertura | Efecto en bar[0] = mañana |
| **t=0** | Exacta | Entry/Exit con conviction modulada por confluencia y polaridad | Efecto en bar[+1] = hoy/mañana |
| **t+1** | Confirmación | Añadir posición si t=0 fue acertada; confirmar que la señal no fue falsa | Posmortem |
| **t+2** | Posmortem | Solo validación — no accionable directamente | Posmortem |
| **ENTRE** | Continuación | Mantener posiciones / trend following / señales SIGMET continuas | Variable (estocástico) |

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
9. **Las métricas WR 20d del inventario son PROVISIONALES.** La validación definitiva debe usar la Tríada Estocástica (zz25/zz50/zz75).

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
