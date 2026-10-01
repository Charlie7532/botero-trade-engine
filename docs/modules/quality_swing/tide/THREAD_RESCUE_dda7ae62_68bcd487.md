# Rescate de Memoria e Hilos Históricos — Subsistema Tide (`quality_swing`)

> **Propósito:** Consolidar la memoria histórica completa, decisiones de diseño, hipótesis probadas/refutadas, directivas del Arquitecto y tareas pendientes de los hilos de origen `dda7ae62-58b2-44b8-adf4-6d8b6e16bd19` («Modelo EV Real & Puerta Confluencia Dual») y `68bcd487-aebf-4bc0-8e5a-c2301a19c8ba` («Swing EV Decision Engine»).
> **Fecha de Rescate:** 2026-09-28
> **Estado:** MEMORIA MAESTRA RESCATADA Y VERIFICADA

---

## 1. Contexto e Identificación de Hilos Históricos

1. **Hilo 1: `dda7ae62-58b2-44b8-adf4-6d8b6e16bd19`**
   - **Título original:** *Auditing EV Data Schema / Modelo EV Real & Puerta Confluencia Dual (P(bull) × EV)*
   - **Objetivo:** Auditar el esquema de datos EV en Neon PostgreSQL (`engine.ticker_fact_states`), corregir la fórmula de retorno real punto-en-tiempo y construir la Puerta de Confluencia Dual para `quality_swing`.
2. **Hilo 2: `68bcd487-aebf-4bc0-8e5a-c2301a19c8ba`**
   - **Título original:** *Architectural Review Real EV Model / Swing EV Decision Engine*
   - **Objetivo:** Refactorizar el motor de decisiones de `combined` a **Tide**, implementar el pipeline de 3 dimensiones (Tide × Current × σVw), resolver el "Buyback Slippage", calibrar la matriz Markov de 16,470 transiciones y diseñar las reglas formales de salida y acumulación.

---

## 2. Directivas del Arquitecto de Sistema (Citas y Principios Institucionales)

> 💬 **«Dato mata Relato!»** — *Injunción cuantitativa fundamental: Ninguna corazonada o teoría académica prevalece sobre la prueba empírica en el Vault de Neon.*

> 💬 **«No usar retorno fantasma»** — *El cálculo de retorno esperado debe ser estrictamente punto-en-tiempo: \(R = \frac{\text{Price}(P_{\text{next}})}{\text{Close}(t)} - 1\), eliminando cualquier sesgo de lookahead o retornos teóricos desfasados.*

> 💬 **«Tide no decide QUÉ comprar, decide CUÁNDO acumular o trimmar»** — *Tide actúa estrictamente como Capa 3 (Entry Gate / Quality Swing) dentro de la arquitectura de 3 niveles. Las empresas aprobadas vienen de Quality Core (Sir Christopher Hohn / Charlie Munger); Tide y Druckenmiller gestionan la velocidad de capital y el timing.*

> 💬 **«Cero cambios unilaterales de plan»** — *Las mutaciones arquitectónicas o de código deben ser explícitamente presentadas con diagnóstico empírico previo antes de modificar archivos en producción.*

---

## 3. Hipótesis Probadas, Refutadas y Decisiones de Diseño

### 3.1. [VALIDADO] Modelo de Valor Esperado (EV) Punto en el Tiempo (Real EV)
- **Hallazgo:** El cálculo legacy inflaba el EV en ~3pp por un cruce de fórmulas entre retornos positivos y recuentos totales.
- **Solución Implementada:** Cálculo de EV real condicionado \(E[R | S_t]\), baseline incondicional \(L0\), certidumbre \(\Omega = 1/\sigma^2\), Half-Kelly per-ticker, y asimetría \(RR_{\text{asym}}\).

### 3.2. [VALIDADO] Experimento VIX 3D vs 4D (VIX fuera del espacio de estados)
- **Hipótesis:** Añadir el régimen VIX como 4ª dimensión (`T|C|VWAP|VIX`) mejoraría el ajuste del modelo.
- **Resultado [REFUTADO]:** 
  - **3D (`T|C|VWAP`, 45 estados):** \(\Delta\) shares medio +0.50% vs Buy & Hold (\(t=1.64\)).
  - **4D (`T|C|VWAP|VIX`, 180+ estados):** \(\Delta\) shares medio +0.08% (\(t=0.18\)). VIX cruzó fronteras 238 veces en 5.5 años, fragmentando la muestra en celdas con \(N < 15\) que forzaban caídas a L0.
- **Decisión:** VIX se eliminó como dimensión de estado y se conservó como **Circuit Breaker Gate** duro (`VIX \ge 28.0` AND `T < -0.05` \(\rightarrow\) `EXIT_CRISIS`).

### 3.3. [VALIDADO] Trend Protection Gate (Solución al Buyback Slippage)
- **Problema:** En tendencias secualres alcistas (`t_slope \ge 0.05` en JNJ, WMT, COST), el sistema emitía señales `HARVEST` prematuras por EV marginalmente negativo, forzando recompras más caras.
- **Solución Implementada:** Exigir expectativa relativa \((E[R] - L0) < \text{threshold}\) y bloquear `HARVEST` cuando `t_slope \ge 0.05`, salvo que exista sobrecompra extrema (\(\sigma Vw \ge 1.50\)).
- **Resultado:** JNJ pasó de -0.78 a +0.28 \(\Delta\) shares netas (+1.06 de mejora); WMT pasó de -0.41 a +0.15 \(\Delta\) shares.

### 3.4. [VALIDADO] Calibración Markoviana (16,470 Transiciones OOS)
- **Resultado:** Matriz de transición predijo el estado siguiente con calibración lineal casi perfecta:
  - \(P \ge 90\%\): 90.8% hit rate real (2,104 transiciones).
  - \(P \ge 80\%\): 82.1% hit rate real (4,892 transiciones).
- **Decisión:** Anticipación Markoviana integrada en el motor para ejecuciones preventivas.

### 3.5. [VALIDADO] Escalamiento Kelly Per-Ticker y Modificador Tanh
- **Kelly Per-Ticker:** Sustituido la constante global `_KELLY_SCALE = 0.0736` por una escala propia calculada desde el baseline L0 del ticker (\(l0\_half\_kelly = |E[R]_{L0} / \sigma^2_{L0}| / 2\)).
- **VWAP Drift Modifier:** Sustituida la función discontinua `copysign` por `tanh(ev_net * 200)` para evitar saltos bruscos cerca de \(EV = 0\).

### 3.6. [HIPÓTESIS] Duración Dinámica (\(e\_days\)) y Velocidad de Capital
- **Concepto:** Las 20 barras fijas de lookforward distorsionan tickers con distintas velocidades de pivote ZigZag. Tickers de alta beta (AAPL, NVDA) pivotan en 5–8 días, mientras defensivas (JNJ, PG) tardan 15–20 días.
- **Estado:** `[HIPÓTESIS / PENDIENTE DE DEPLOY]` — Integración formal de \(e\_days\) y \(ev\_per\_day\) en la DB de producción.

---

## 4. Clasificación de Estado de los Hallazgos

| Concepto / Componente | Estatus | Ubicación en Código / DB |
|---|:---:|---|
| **Modelo EV Real Punto-en-Tiempo** | `[VALIDADO]` | `rc_tide_ev_lookup.py`, `rc_tide_ev_derived.json` |
| **Circuit Breaker Gate (VIX >= 28)** | `[VALIDADO]` | `swing_gate.py` |
| **Trend Protection Gate (Secular Bull)** | `[VALIDADO]` | `swing_gate.py` |
| **VWAP Drift Tanh Modifier** | `[VALIDADO]` | `rc_tide_ev_lookup.py` |
| **Kelly Scale Per-Ticker** | `[VALIDADO]` | `rc_tide_ev_derived.json` |
| **Desajuste de Taxonomía (3-bin vs 6-level)** | `[PENDIENTE]` | TASK 1 — Vault DB (45) vs JSON (180/245) |
| **Duración Dinámica (\(e\_days\))** | `[PENDIENTE]` | TASK 2 — `engine.ticker_fact_states` |
| **Benchmark Forense a Escala (366 Tickers)** | `[PENDIENTE]` | TASK 3 — `eval_swing_forensic_benchmark.py` |
| **Bug DTO `fatigue_type` en `_real_ev`** | `[BUG ACTIVO]` | `swing_gate.py` L280 & L653 |

---

## 5. Tareas Pendientes Heredadas (Roadmap Abierto)

1. **TASK 1 — Unificación de Taxonomía:** Conectar `rc_tide_ev_lookup.py` a la DB Vault (`TimescaleDataStore`) normalizando de 6 niveles (`T+++|C---|>`) a 3 bins (`T+|C-|>`) o consolidando el Feature Store de 180 estados en la DB de Neon.
2. **TASK 2 — Duración Dinámica y Velocidad de Capital:** Persistir \(e\_days\) y \(ev\_per_day\) por estado en `engine.ticker_fact_states`. Ajustar sizing Kelly por velocidad de capital e implementar Time Stop dinámico en \(1.5 \times e\_days(S_t)\).
3. **TASK 3 — Benchmark Forense Escalado:** Ejecutar `eval_swing_forensic_benchmark.py` sobre los 366+ tickers de la masa crítica de Quality Core.
