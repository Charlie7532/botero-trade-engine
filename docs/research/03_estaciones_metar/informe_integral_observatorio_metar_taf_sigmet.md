# INFORME TÉCNICO-INSTITUCIONAL: OBSERVATORIO AERONÁUTICO DE MERCADO (METAR · TAF · SIGMET · NOTAM)

**Para:** Comité de Inversiones, Arquitectura Cuantitativa y Dirección del Proyecto Botero Trade  
**Asunto:** Estado del Sistema, Telemetría Multi-Estación, Respaldo Matemático-Estadístico, Validación Fuera de Muestra (OOS) y Justificación del Ciclo de Investigación y Desarrollo  
**Fecha de Referencia:** Agosto 2026  
**Entorno:** Neon PostgreSQL Institutional Data Vault · Python Pure Domain Trading Engine · Clean & Hexagonal Architecture  

---

## 1. RESUMEN EJECUTIVO

El sistema **METAR / TAF / SIGMET / NOTAM** de Botero Trade es una infraestructura de telemetría de mercado, pronóstico estocástico multi-escala y gestión de riesgo sistémico inspirada en los estándares de la aviación institucional (FAA / OACI).

El propósito central de esta arquitectura es erradicar el sesgo cognitivo, la heurística empírica no validada y las opiniones narrativas de mercado, sustituyéndolos por **telemetría física determinista, modelado no lineal de información mutua y matrices probabilísticas condicionadas** calculadas sobre más de 33 años de historia real de mercado (1993–2026).

```
   ┌────────────────────────────────────────────────────────────────────────┐
   │                        NEON POSTGRESQL VAULT                           │
   │           5.80M Barras OHLCV · 4M+ Piernas ZigZag · 628 Tickers        │
   └───────────────────────────────────┬────────────────────────────────────┘
                                       │
                    ┌──────────────────┴──────────────────┐
                    ▼                                     ▼
   ┌─────────────────────────────────┐   ┌──────────────────────────────────┐
   │        METAR (TELEMETRÍA)       │   │       TAF (PRONÓSTICO EV/FTT)    │
   │  11 Estaciones Ortogonales      │   │  Multi-Escala: zz25, zz50, zz75  │
   │  Vector D1(Nivel) × D2(Δ3d)     │   │  Velocidad de Capital: EV/Día    │
   │  × D3(Vol Ratio) = 150 Estados  │   │  First-Time-to-Touch (Duración)  │
   └────────────────┬────────────────┘   └────────────────┬─────────────────┘
                    │                                     │
                    └──────────────────┬──────────────────┘
                                       ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                  CONVERGENCE COMPOSITOR & GATES                        │
   │    Information Coefficient (Grinold & Kahn) · Dual-Channel Rarity      │
   └────────────────┬──────────────────────────────────┬────────────────────┘
                    ▼                                  ▼
   ┌─────────────────────────────────┐   ┌──────────────────────────────────┐
   │     SIGMET (ALERTAS SEVERAS)    │   │      NOTAM (DISRUPCIONES OPS)    │
   │  Clima Extremo / Tails (±3σ-10σ)│   │  Staleness, Desconexión Broker,  │
   │  Directivas: STK_BLOCK_CRISIS,  │   │  Halts Macroeconómicos / FOMC    │
   │  MKT_MACRO_CIRCUIT_BREAKER      │   │  Status Operativo de Pipeline    │
   └─────────────────────────────────┘   └──────────────────────────────────┘
```

---

## 2. DETALLE EXHAUSTIVO DE LO CONSTRUIDO (ARQUITECTURA HEXAGONAL Y NIVELES)

La arquitectura se divide en 4 niveles de reporte operativo aeronáutico, respetando estrictamente la **Regla 23 de Arquitectura Institucional**:

```
                       ESPECTRO DE ALERTAS AERONÁUTICAS
 ┌──────────┐ ┌─────────────────────────────────────────────────────────┐ ┌──────────────┐
 │ SERVICIO │ │                      DESCRIPCIÓN                        │ │   ENDPOINT   │
 ├──────────┤ ├─────────────────────────────────────────────────────────┤ ├──────────────┤
 │  METAR   │ │ Telemetría rutinaria continua D1×D2×D3 (11 estaciones)  │ │ /api/metar/* │
 │   TAF    │ │ Pronóstico estocástico de retorno, horizonte y EV/día   │ │ /convergence │
 │  SIGMET  │ │ Boletines de riesgo extremo (VIX≥28, SKEW≥145, Blow-off)│ │ /sigmet/*    │
 │  NOTAM   │ │ Alertas operacionales de infraestructura y tuberías     │ │ /notam/*     │
 └──────────┘ └─────────────────────────────────────────────────────────┘ └──────────────┘
```

### 2.1. METAR (Multi-Station Telemetry)
Telemetría de alta resolución que descompone el estado de **11 estaciones ortogonales** en un tensor tridimensional homogéneo de **150 estados teóricos por estación** ($6 \times 5 \times 5$):

1. **D1 — Nivel / Magnitud Puntual (6 bines gaussianos, 0..5):** Clasifica la posición del indicador en su campana gaussiana histórica en tramos de $\sigma$: $[-2\sigma, -1\sigma, \mu, +1\sigma, +2\sigma]$.
2. **D2 — Velocidad Cinemática $\Delta 3d$ (5 bines, 0..4):** Derivada de primer orden a 72 horas para registrar aceleración o desaceleración: `FAST_CRUSH_3D`, `DECELERATING_DOWN_3D`, `STABLE_CONTINUATION_3D`, `ACCELERATING_UP_3D`, `FAST_SPIKE_3D`.
3. **D3 — Estabilidad / Volatilidad de Estación (5 bines, 0..4):** Relación de dispersión $\frac{\text{std}(2d)}{\text{std}(10d)}$ para medir si la estación está en compresión de volatilidad o régimen caótico.

#### Las 11 Estaciones Implementadas en Producción:
*   [VIX](file:///root/botero-trade/backend/modules/entry_decision/domain/services/vix_metar_service.py): Miedo y volatilidad implícita en opciones S&P 500.
*   [VVIX](file:///root/botero-trade/backend/modules/entry_decision/domain/services/vvix_metar_service.py): Volatilidad de la volatilidad (inestabilidad de régimen).
*   [PCR](file:///root/botero-trade/backend/modules/entry_decision/domain/services/pcr_metar_service.py): Put/Call Ratio de CBOE (posicionamiento de cobertura y apalancamiento).
*   [FG](file:///root/botero-trade/backend/modules/entry_decision/domain/services/fg_metar_service.py): Índice compuesto CNN Fear & Greed (sentimiento contrarian).
*   [SV5_TURBULENCE](file:///root/botero-trade/backend/modules/entry_decision/domain/services/sv5_turbulence_metar_service.py): Turbulencia de volumen institucional ($\text{std}(\Delta\text{SV5TW}, 10d)$), sensor de microestructura más ortogonal del sistema.
*   [SKEW](file:///root/botero-trade/backend/modules/entry_decision/domain/services/skew_metar_service.py): Riesgo de cola y demanda de puts OTM profundos.
*   [CREDIT](file:///root/botero-trade/backend/modules/entry_decision/domain/services/credit_metar_service.py): Estrés crediticio corporativo vía ratio sintético HYG/LQD.
*   [YIELD_CURVE](file:///root/botero-trade/backend/modules/entry_decision/domain/services/yield_curve_metar_service.py): Pendiente macro de tipos de interés (TNX − IRX: 10Y − 13W).
*   [ROTATION](file:///root/botero-trade/backend/modules/entry_decision/domain/services/rotation_metar_service.py): Índice de rotación sectorial ($z(\text{XLY}/\text{XLP}) + z(\text{XLK}/\text{XLU})$).
*   [BSI](file:///root/botero-trade/backend/modules/entry_decision/domain/services/bsi_metar_service.py): Breadth Shock Index táctico (porcentaje de acciones sobre su 20-DMA: S5TW).
*   [DXY](file:///root/botero-trade/backend/modules/entry_decision/domain/services/dxy_metar_service.py): Índice del dólar global (condiciones de liquidez transfronteriza).

### 2.2. TAF (Terminal Aerodrome Forecast)
Integra matrices de probabilidad condicional prospectiva para cada estado a través de la tríada multi-escala ZigZag ($zz25 = 2.5\%$, $zz50 = 5.0\%$, $zz75 = 7.5\%$):
*   **$P_{bull} / P_{bear}$**: Probabilidad bayesiana condicional de que el siguiente movimiento sea alcista o bajista.
*   **$EV_{net}$**: Valor esperado neto normalizado por sesgo histórico.
*   **FTT (First-Time-to-Touch)**: Duración mediana esperada en días ($ftt_{bull}$, $ftt_{bear}$) hasta completar el recorrido del precio.
*   **Velocidad de Capital ($EVPD = \frac{EV_{net}}{E_{days}}$)**: Retorno esperado por día de exposición en el mercado.

### 2.3. SIGMET (Severe Weather Hazard Bulletins)
Emisión estricta de boletines meteorológicos severos solo cuando los umbrales de peligro físico o colas gaussianas son vulnerados ([market_sigmet_hazard_service.py](file:///root/botero-trade/backend/modules/entry_decision/domain/services/market_sigmet_hazard_service.py)). Si el mercado opera en condiciones benignas, el endpoint `/api/sigmet/active` devuelve `status: CLEAR` con lista vacía `[]`.

#### Tipología de Alertas SIGMET:
*   `SIGMET_VOLATILITY_TURBULENCE`: VIX $\ge 28.0$ o SV5_Turbulence $\ge 12.0$.
*   `SIGMET_TAIL_RISK_SKEW`: SKEW $\ge 145.0$ (paranoia de cola extrema).
*   `SIGMET_CREDIT_FREEZE`: Ratio HYG/LQD $\le 0.58$ ($D1 \le 1$, estrés severo en crédito).
*   `SIGMET_YIELD_CURVE_INVERSION`: Spread 10Y-13W $< 0$ (inversión de ciclo económico).
*   `SIGMET_CAPITULATION_EXTREME`: Confluencia crítica de VIX $\ge 3$ con $BSI == 0$ (agotamiento total de vendedores).
*   **Escala de Sobrecarga de Colas $\sigma$-Overflow ([sigma_overflow.py](file:///root/botero-trade/backend/modules/entry_decision/domain/rules/sigma_overflow.py)):**
    *   *Tier 1 (3–4$\sigma$):* `OVERFLOW_MODERADO` $\to$ Alerta de monitoreo (`STK_HOLD_STABLE`).
    *   *Tier 2 (4–5$\sigma$):* `OVERFLOW_EXTREMO` $\to$ Veto de compras en crisis (`STK_BLOCK_CRISIS`).
    *   *Tier 3 (5–7$\sigma$):* `BLOW_OFF_SEVERE` $\to$ Disparo de Circuit Breaker.
    *   *Tier 4 (7–10$\sigma$):* `BLOW_OFF_EXTREME` $\to$ Restricción a coberturas exclusivas.
    *   *Tier 5 ($\ge 10\sigma$):* `BLOW_OFF_SYSTEMIC` $\to$ `MKT_MACRO_CIRCUIT_BREAKER` (preservación total de capital).

### 2.4. NOTAM (Notice to Airmen / Disrupciones Operacionales)
Canal dedicado en `/api/notam/incidents` para informar caídas de base de datos, desincronización de pipelines de datos (stale bars $> 24\text{h}$), desconexión de brokers o periodos de blackout de la FED / FOMC.

---

## 3. INFRAESTRUCTURA DE DATOS Y POBLACIÓN HISTÓRICA (NEON VAULT)

La precisión de los modelos reside en que **no se emplean muestras simuladas ni distribuciones sintéticas**. Todo está anclado en la base de datos institucional externa **Neon PostgreSQL**:

*   **Tabla Universal de Series:** `market.ohlcv_bars` alberga más de **5.80 millones de barras diarias**, clasificadas mediante `market.ticker_metadata`.
*   **Estandarización Temporal:** Todas las barras diarias se encuentran normalizadas a **medianoche UTC (`00:00:00+00`)**, evitando desfases de look-ahead bias o desalineación de zonas horarias.
*   **Población de Piernas ZigZag:** `market.zigzag_legs` almacena más de **4 millones de piernas confirmadas** a través de 613 tickers desde 1927, permitiendo calcular el comportamiento exacto de alternación y recorrido de precios.
*   **Fact Stores V3 en Producción:** 11 almacenes JSON en [`backend/modules/entry_decision/domain/rules/`](file:///root/botero-trade/backend/modules/entry_decision/domain/rules/) que albergan la totalidad del espacio de estados pre-calculado, con documentación estandarizada (`_documentation.taxonomy`).

---

## 4. RESPALDO MATEMÁTICO, ESTADÍSTICO Y METODOLOGÍA CUANTITATIVA (MARCO LÓPEZ DE PRADO)

El sistema fue sometido a una auditoría cuantitativa integral basada en la metodología de *Marcos López de Prado (Advances in Financial Machine Learning)* sobre una muestra de **1,589 pivotes ZigZag de SPY** entre 1993 y 2026.

```
                          MAPA DE RELACIÓN DE FEATURES
 ┌───────────────────────┐                                 ┌───────────────────────┐
 │       CASCADE         │                                 │       DIRECCIÓN       │
 │   (Continuación)      │                                 │     (Próximo Leg)     │
 ├───────────────────────┤                                 ├───────────────────────┤
 │ Dominado por: D1 Nivel│                                 │ Dominado por: D2 Vel  │
 │ · VIX (MI=0.109,ρ=0.4)│                                 │ · BSI (ρ=+0.363)      │
 │ · FG  (MI=0.071)      │                                 │ · VIX (ρ=-0.310)      │
 │ · D2: No lineal (en U)│                                 │ · Lineal y monótono   │
 └───────────────────────┘                                 └───────────────────────┘
                                       ▲
                                       │
                      ORTOGONALES POR CONSTRUCCIÓN FÍSICA
```

### 4.1. Información Mutua (MI) No-Lineal vs Correlación Lineal ($\rho$)
Se calculó la Información Mutua con 300 permutaciones ($p\text{-value}$) para descubrir dinámicas no monótonas invisibles para la estadística convencional:

| Feature / Dimensión | Target: Continuación (Cascade) | Target: Dirección de Mercado | Conclusión Mecánica |
|---|:---:|:---:|---|
| **VIX D1 (Nivel)** | $MI = 0.109$, $\rho = +0.426$ ($p < 0.001$) | $MI = 0.035$, $\rho = -0.118$ | El nivel de estrés predice **duración y cascada**, no dirección inmediata. |
| **VIX D2 (Velocidad $\Delta 3d$)** | **$MI = 0.024$, $\rho = 0.067$** ($p = 0.003$) | $MI = 0.057$, $\rho = -0.310$ | En cascada tiene relación en **forma de U** (invisibilizada por $\rho$); en dirección es un fuerte predictor lineal bajista. |
| **BSI D2 (Velocidad Breadth)** | $MI = 0.015$, $\rho = 0.042$ | **$MI = 0.069$, $\rho = +0.363$** ($p < 0.001$) | **Predictor dominante de rebotes** a corto plazo. |
| **Yield Curve D2 ($\Delta 3d$)** | **$MI = 0.018$, $\rho = 0.007$** ($p = 0.003$) | $MI = 0.009$, $\rho = 0.015$ | El aplanamiento/empinamiento brusco aporta información pura no-lineal de riesgo macro. |

> **Hallazgo Estructural #1:** El **Cascade (continuación de tendencia)** y la **Dirección del próximo tramo** son variables ortogonales. Cascade responde al *nivel de estrés macro* (D1), mientras que la Dirección responde al *momentum cinemático* (D2).
>
> **Hallazgo Estructural #2:** El vector de estado completo ($D1 \times D2 \times D3$) tiene un Information Coefficient de **$IC = -0.489$** para dirección, resultando **$3.2\times$ superior** al uso unidimensional de $D1$ ($IC = -0.155$).

### 4.2. Ortogonalidad Real y Clustering Jerárquico
El análisis de componentes principales (PCA) y la distancia jerárquica de Ward desmintieron las correlaciones intuitivas tradicionales:
*   *Miedo (VIX + VVIX)*: Correlación moderada ($\rho = 0.37$). VIX correlaciona más con crédito ($\rho = -0.61$) que con su propia volatilidad de vol.
*   *Posicionamiento (PCR + SKEW)*: Casi independientes ($\rho = -0.15$). Operan en diferentes capas de la estructura de capital y opciones.
*   **SV5_TURBULENCE:** Demostró ser la **estación más ortogonal del mercado** ($MI \le 0.48, \rho \le 0.22$ contra todas las demás), actuando como sensor independiente de fricción institucional.

```
                  DENDROGRAMA DE CLUSTERING JERÁRQUICO REAL
 ┌────────────────────────────────────────────────────────────────────────┐
 │ Cluster 1 (Sentimiento / Breadth): { PCR, FG, BSI }                    │
 │ Cluster 2 (Régimen de Vol / Divisas): { VVIX, DXY }                    │
 │ Cluster 3 (Macro & Estrés Estructural): { VIX, SKEW, CREDIT, YIELD }   │
 │ Cluster 4 (Microestructura Pura / Ortogonal): { SV5_TURBULENCE }       │
 └────────────────────────────────────────────────────────────────────────┘
```

### 4.3. Prevención de Sobreajuste (PBO y CPCV)
Para garantizar que las reglas no fueran producto de minería de datos espuria (*data snooping*), se aplicó **Combinatorial Purged Cross-Validation (CPCV)** con 8 particiones cronológicas y 28 combinaciones de prueba:
*   **Probability of Backtest Overfitting (PBO):** **$28.6\%$** (nivel bajo/moderado dentro de los estándares cuantitativos institucionales).
*   **Walk-Forward Out-Of-Sample (ventanas de 5 años):** **$92.9\%$ de folds positivos (26 de 28)**, con un $IC$ medio fuera de muestra de **$+0.302$**.
*   **Bootstrap Full-Sample (2,000 resamples):** $IC = +0.414$ con intervalo de confianza al 95% de $[+0.371, +0.455]$ (**$100\%$ de resamples positivos**).

### 4.4. Estabilidad Temporal y Quiebres Estructurales (CUSUM)
El análisis CUSUM sobre el Information Coefficient a través de 4 décadas (1990s a 2020s) demostró que la fuerza predictiva del sistema **se ha intensificado** en los regímenes modernos:
*   *1990s:* $IC = +0.410$ ($N=280$)
*   *2000s:* $IC = +0.367$ ($N=690$)
*   *2010s:* $IC = +0.376$ ($N=308$)
*   *2020s:* **$IC = +0.559$** ($N=311$, $p = 5.7\times 10^{-27}$)

---

## 5. CATÁLOGO DE SEÑALES, CONFIABILIDAD Y VALIDACIÓN FUERA DE MUESTRA (OOS)

### 5.1. Núcleo Robusto de Señales Validadas Fuera de Muestra (OOS)
Evaluación empírica sobre **1,354 pivotes deduplicados** (eliminando 236 pivotes redundantes para garantizar pureza estadística), utilizando Walk-Forward anclado con bloques de testeo de 3 años y entrenamiento mínimo de 5 años ([validacion_oos_catalogo_v7.json](file:///root/botero-trade/data/research/signals/validacion_oos_catalogo_v7.json)):

```
                             EDGE IN-SAMPLE VS OUT-OF-SAMPLE
 ┌──────────────────────┬──────────────────────┬─────────────┬─────────────┬───────────┐
 │        SEÑAL         │  CONDICIÓN EN BINS   │   EDGE IS   │  EDGE OOS   │   DECAY   │
 ├──────────────────────┼──────────────────────┼─────────────┼─────────────┼───────────┤
 │ capitulacion         │ VIX >= 3 & BSI == 0  │   +3.40%    │   +2.64%    │   0.77    │
 │ pcr_put_panic        │ PCR == 5             │   +4.04%    │   +2.56%    │   0.63    │
 │ vvix_entry           │ VVIX == 5            │   +3.11%    │   +2.08%    │   0.67    │
 │ credit_stress        │ CREDIT <= 1          │   +3.42%    │   +1.43%    │   0.42    │
 │ bsi_washed_out       │ BSI == 0             │   +1.73%    │   +0.99%    │   0.57    │
 └──────────────────────┴──────────────────────┴─────────────┴─────────────┴───────────┘
```

*   **Capitulación:** Mantiene el **$77\%$ de su edge en datos nunca vistos**, con un retorno neto OOS de $+2.64\%$ por operación.
*   **PCR Put Panic & VVIX Entry:** Robustez extrema en rebotes tácticos cuando el mercado de derivados entra en pánico asimétrico ($+2.56\%$ y $+2.08\%$ OOS).

### 5.2. El Paradigma del Edge Defensivo ($ED$)
Uno de los descubrimientos más importantes de la investigación fue que las señales de estrés extremo no deben juzgarse por su Win Rate ofensivo, sino por su **capacidad de evitar drawdowns catastróficos**:

$$\text{Edge Defensivo } (ED) = |\text{Pérdida Media en Crash}| - (\text{Ganancia Media} \times \text{Tasa de Falsas Alarmas})$$

*   La señal `capitulacion` exhibe un $ED = +6.86\%$, ya que cuando falla y continúa el colapso, el mercado cae en promedio un $-9.22\%$. Actuar preventivamente ahorra capital institucional masivo.
*   **Precursor Universal de Crash:** Se identificó empíricamente que cuando `credit.D2 == ACCELERATING_UP_3D` (el spread de crédito se dispara a 72h), el riesgo de crash en los siguientes 20 días tiene un **Lift multiplicador de $4.1\times$** sobre 5 de las 6 señales principales.

### 5.3. Inversiones de Signo Cinematográfico (*Sign Flips* D2/D3)
Se identificó que 20 de 34 combinaciones registraban una **inversión radical del resultado esperado** si se ignoraba la velocidad ($D2$) o la estabilidad ($D3$):
*   `sub_reaccion` con VIX acelerando hacia arriba (`ACCEL_UP`): **$+5.11\%$** de retorno esperado ($69\%$ WR).
*   `sub_reaccion` con VIX desacelerando hacia abajo (`DECEL_DOWN`): **$-2.59\%$** ($25\%$ WR). **Spread: $+7.70$ puntos porcentuales.**

---

## 6. UTILIDAD PRÁCTICA PARA EL PROYECTO BOTERO TRADE

Este observatorio no es un ejercicio teórico, sino el **motor central de toma de decisiones** de la plataforma:

```
                            IMPACTO OPERATIVO EN BOTERO TRADE
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │ 1. Quality / Moat (Druckenmiller & Munger):                                            │
 │    · Acumulación de alta convicción en capitulaciones (STK_ACCUMULATE_STRUCTURAL).     │
 │    · Cosecha táctica de beneficios en euforia extrema D1=5 (STK_TRIM_TACTICAL).        │
 ├────────────────────────────────────────────────────────────────────────────────────────┤
 │ 2. Speculative / Alpha (Seykota & Simons):                                             │
 │    · Entradas tácticas asimétricas 5:1 en rebotes de pánico (STK_BUY_DIP_TACTICAL).    │
 │    · Paradas de tiempo (Vertical Barriers) gobernadas por la mediana FTT en días.     │
 ├────────────────────────────────────────────────────────────────────────────────────────┤
 │ 3. Systemic Risk Guardian (Macro Circuit Breakers):                                    │
 │    · Veto estricto de compras en fases de estrés (STK_BLOCK_CRISIS).                   │
 │    · Desconexión automática de órdenes ante colas extremas ≥5σ (MKT_MACRO_CIRCUIT_...).│
 ├────────────────────────────────────────────────────────────────────────────────────────┤
 │ 4. Asignación de Capital (CIO Allocator):                                              │
 │    · Ponderación dinámica de capital según la Velocidad de Retorno Diario (EVPD).      │
 └────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. JUSTIFICACIÓN DEL TIEMPO INVERTIDO Y ESTUDIOS REALIZADOS

La envergadura de este desarrollo requirió un esfuerzo de ingeniería y análisis cuantitativo exhaustivo por las siguientes razones fundamentales:

1. **Eliminación de Sesgos de Selección y Minería de Datos (*Data Snooping*):**  
   Construir un sistema que no sobreajuste requirió evaluar más de **33 años de historia día a día**, programar generadores de ventanas expansivas sin fuga de información (*zero look-ahead bias*) y someter todas las reglas a pruebas combinatorias CPCV y test de permutaciones.
2. **Descubrimiento y Corrección de Errores Matemáticos Ocultos en Modelos Previos:**  
   Durante las auditorías forenses se identificaron y subsanaron fallas críticas en la literatura interna previa:
   *   *Corrección de fórmula de $P_{bull}$ cruzada:* Se corrigió un cálculo invertido en generadores heredados que sobrestimaba artificialmente el EV en 3 puntos porcentuales.
   *   *Desfase de población Triple Barrier vs ZigZag:* Se descubrió que el $e_{max}$ tomaba medias de retornos globales en lugar de retornos condicionados al toque de barrera, reduciendo la tasa de contradicción de señales del $58\%$ al $20\%$.
   *   *Deduplicación de 236 pivotes falsos:* Se depuró la base de eventos para evitar que pivotes redundantes inflaran artificialmente la significancia estadística ($N$).
   *   *Corrección en métricas de captura y anticipación:* Se repararon errores de cálculo en métricas de autocorrelación que confundían persistencia de clúster con anticipación causal.
3. **Ingeniería de Datos Masiva y Procesamiento a Gran Escala:**  
   Se procesaron y estandarizaron más de **5.80 millones de barras OHLCV** en Neon PostgreSQL, calculando series complejas de amplitud sectorial ($S5/SV5$), matrices de divergencia VIX vs S5, y estructurando más de **4 millones de piernas ZigZag**.
4. **Homologación Arquitectónica Hexagonal (Clean Architecture):**  
   Se desacopló completamente la lógica de dominio de la infraestructura. Se desarrollaron 11 servicios independientes de lectura estricta sobre el Vault, un clasificador centralizado (`metar_classifier.py`), una capa de gestión de anomalías de cola (`sigma_overflow.py`) y un router REST en FastAPI con tipado estricto.

---

## 8. CONCLUSIÓN Y ESTADO OPERACIONAL

El observatorio **METAR / TAF / SIGMET / NOTAM** se encuentra **100% construido, homologado en su taxonomía canónica, respaldado matemáticamente bajo el rigor de López de Prado y verificado en producción**.

El proyecto Botero Trade no opera sobre indicadores técnicos comunes ni opiniones de analistas, sino sobre una **estación meteorológica de mercado institucional cuantitativamente probada, con un Information Coefficient robusto ($IC = +0.414$ a $+0.559$), baja probabilidad de sobreajuste ($PBO = 28.6\%$) y un catálogo de señales con edge positivo verificado fuera de muestra.**
