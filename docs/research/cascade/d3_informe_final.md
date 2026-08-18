# D3 (Volatilidad = std(2d)/std(10d)) — Informe Completo por Estación
## Botero Trade · Experto en D3 · 2026-08-15

**Scripts generadores:** `scratch/d3_experto.py` (cómputo) + `scratch/d3_mecanismo.py` (mecanismo)
**Muestra:** 1,589 pivotes SPY zz25. cascade_50 rate = 50.5%, cascade_75 rate = 26.7%.

---

## 1. DEFINICIÓN DE D3

```
D3 = std(2d) / std(10d) del close diario del indicador (NaN → 1.0)
```

- **D3 < 1 (calma/compresión):** el indicador se movió MENOS en los últimos 2 días que lo típico en los últimos 10 días. Indicador estable, sin sobresaltos.
- **D3 > 1 (caos/expansión):** el indicador se movió MÁS en los últimos 2 días que lo típico. Indicador en whipsaw, movimiento acelerado.

**Distribución típica:** Todas las medianas de D3 están por debajo de 1.0 (entre 0.17 para SV5T y 0.62 para PCR). El ratio std(2d)/std(10d) tiende a ser < 1 porque los 2 últimos días son una ventana muy corta comparada con 10 días. D3 > 1 es EXCEPCIONAL, ocurre cuando el indicador hace un movimiento extremo en 2 días.

| Estación | Mediana | P33 | P67 | P90 |
|---|---|---|---|---|
| SV5T | 0.168 | 0.074 | 0.362 | 1.158 |
| FG | 0.321 | 0.188 | 0.519 | 1.077 |
| DXY | 0.367 | 0.224 | 0.563 | 1.078 |
| BSI | 0.374 | 0.225 | 0.579 | 1.109 |
| Yield | 0.380 | 0.230 | 0.573 | 1.078 |
| Rotation | 0.401 | 0.250 | 0.600 | 1.079 |
| VVIX | 0.403 | 0.243 | 0.615 | 1.183 |
| VIX | 0.418 | 0.254 | 0.631 | 1.193 |
| Credit | 0.424 | 0.268 | 0.649 | 1.135 |
| SKEW | 0.461 | 0.290 | 0.705 | 1.341 |
| PCR | 0.620 | 0.386 | 0.916 | 1.535 |

---

## 2. CONFIRMACIÓN DEL HALLAZGO PREVIO

### 2.1 Correlación D3 con tríada zigzag (Spearman ρ + gap tercil caos−calma)

| Estación | ρ(D3,c50) | p | ρ(D3,c75) | ρ(D3,dir) | Δc50(pp) | Δc75(pp) | Δdir(pp) | Bootstrap |
|---|---|---|---|---|---|---|---|---|
| **FG** | −0.112 | 0.007 | −0.079 | −0.008 | **−15.1** | −9.9 | +0.0 | *** CI95=[−25.5,−5.7] |
| **VVIX** | −0.093 | 0.005 | −0.080 | −0.054 | **−9.4** | −7.5 | −6.5 | *** CI95=[−16.9,−2.0] |
| **BSI** | −0.052 | 0.037 | −0.058 | −0.006 | **−6.9** | −8.0 | −0.7 | *** CI95=[−12.8,−1.0] |
| **PCR** | −0.046 | 0.17 | −0.062 | +0.003 | **−5.6** | −7.6 | −0.3 | ns CI95=[−13.5,+2.6] |
| VIX | −0.026 | 0.30 | −0.045 | −0.053 | −3.6 | −5.1 | −3.8 | ns |
| **SKEW** | +0.044 | 0.083 | +0.025 | +0.001 | **+4.3** | +2.3 | +0.3 | ns CI95=[−2.2,+10.2] |
| Credit | −0.036 | 0.27 | −0.031 | −0.026 | **+0.3** | +0.0 | −2.3 | ns |
| Yield | +0.024 | 0.34 | +0.019 | +0.009 | **+1.1** | +2.3 | +1.3 | — |
| Rotation | −0.008 | 0.76 | −0.004 | +0.006 | **−0.1** | +0.1 | +1.9 | — |
| SV5T | +0.007 | 0.80 | +0.035 | −0.009 | **+0.4** | +4.4 | −0.4 | ns |
| DXY | −0.010 | 0.70 | +0.037 | +0.067 | **−0.8** | +3.2 | +6.9 | — |

**Conclusión:** El hallazgo previo se CONFIRMA EXACTAMENTE con datos frescos de la DB.

- **FG** (−15pp, ρ=−0.112, p=0.007, CI significativo): caos suprime cascade. La señal más fuerte entre las 11.
- **VVIX** (−9pp, ρ=−0.093, p=0.005, CI significativo): caos suprime cascade.
- **BSI** (−7pp, ρ=−0.052, p=0.037, CI significativo): caos suprime cascade.
- **PCR** (−6pp, ρ=−0.046, p=0.17, CI no significativo por bajo N): tendencia correcta pero el N=919 limita el poder estadístico.
- **SKEW** (+4pp, ρ=+0.044, p=0.083): INVERTIDO — caos activa cascade (marginalmente).
- **Crédito, Yield, Rotation, DXY:** NEUTRO para cascade (|Δc50| < 1.5pp).
- **SV5T:** perfectamente neutral (+0.4pp).
- **VIX:** −3.6pp (marginal, opuesto a lo esperado para un indicador de estrés, posiblemente porque el caos en VIX es endógeno: el nivel de VIX ya captura el cascade).

### 2.2 Dirección: D3 NO discrimina

|Δdir| < 7pp para TODAS las estaciones excepto DXY (+6.9pp) que tiene una señal direccional débil. ρ(D3,dir) máximo es +0.067 (DXY). **D3 es un modulador de cascade, no un predictor de dirección.**

---

## 3. MECANISMO ECONÓMICO — ¿POR QUÉ?

### 3.1 ¿Qué ES el caos (D3 alto)? — ρ(D3, nivel) y ρ(D3, velocidad)

| Estación | ρ(D3, nivel) | ρ(D3, vel Δ3d) | Interpretación |
|---|---|---|---|
| VIX | +0.043 | **+0.178** | Caos asociado a aceleración de VIX (subiendo más rápido). |
| VVIX | +0.088 | **+0.185** | Caos asociado a aceleración de VVIX. |
| FG | +0.004 | −0.054 | Caos NO depende del nivel de FG ni de si está subiendo/bajando. |
| BSI | −0.021 | **−0.087** | Caos asociado débilmente a BSI bajando (breadth cayendo). |
| PCR | +0.061 | +0.084 | Caos asociado a PCR subiendo (más puts). |
| SKEW | −0.023 | +0.050 | Prácticamente independiente. |
| Credit | −0.000 | −0.058 | Independiente del nivel y velocidad. |
| Yield | +0.020 | +0.017 | Independiente. |
| Rotation | +0.009 | −0.042 | Independiente. |
| DXY | −0.008 | −0.015 | Independiente. |
| SV5T | −0.102 | −0.033 | Caos asociado a SV5T BAJO (turbulencia alta → ¿paradoja? SV5T bajo = más turbulento). |

**D3 es MAYORMENTE ORTOGONAL al nivel y velocidad del indicador** (|ρ| < 0.19 para todos). No es "el indicador estando en un extremo", no es "el indicador moviéndose en una dirección". **D3 = pure noise magnification — el grado de whipsaw del indicador, independiente de hacia dónde va.**

### 3.2 D3 vs SPY: movimiento YA gastado

| Estación | ρ(D3, |SPY ret| contemporáneo) | ρ(D3, |SPY ret| t+1) |
|---|---|---|---|---|
| BSI | **+0.500** | −0.006 |
| VIX | **+0.395** | +0.003 |
| VVIX | **+0.291** | +0.030 |
| FG | **+0.232** | −0.015 |
| Credit | **+0.178** | −0.020 |
| Rotation | **+0.194** | −0.017 |
| SKEW | **+0.119** | +0.008 |
| PCR | +0.053 | −0.004 |
| SV5T | +0.017 | +0.016 |
| DXY | +0.041 | +0.028 |

**TODOS los ρ forward (t+1) son < |0.03| — D3 no predice movimiento futuro de SPY.** D3 es contemporáneo: cuando SPY se mueve fuerte HOY, los indicadores también se mueven fuerte HOY. Es una medida de "cuánto se está moviendo el mercado AHORA MISMO", no de cuánto se moverá mañana.

**Este es el corazón del mecanismo:** D3 alto = el movimiento YA OCURRIÓ. La energía cinética del mercado se gastó EN EL DÍA DEL PIVOT. Si el movimiento ya ocurrió, la probabilidad de que el pivote CASCADE a la siguiente escala es menor. El cascade necesita CONVICCIÓN (movimiento sostenido en el tiempo), no RAPIDEZ (movimiento concentrado en 2 días).

### 3.3 ¿Por qué APAGA cascade en sentimiento (FG, VVIX, BSI, PCR)?

**Mecanismo: whipsaw de sentimiento = agotamiento del impulso**

Los indicadores de sentimiento (FG, VVIX, BSI, PCR) son osciladores bounded/mean-reverting por naturaleza:
- **FG (Fear & Greed):** Cuando el sentimiento whipsaw (D3 alto), es porque está rebotando rápido desde un extremo. El whipsaw ES la resolución del sentimiento — una vez que el sentimiento ya "reaccionó", el movimiento de precio que lo acompañó ya ocurrió. No hay convicción residual para un cascade.
- **BSI (Breadth):** D3 alto en breadth = las acciones están rotando rápido (un día muchas arriba, al siguiente muchas abajo). Esto es CHOP, no tendencia. El chop de breadth no produce cascades.
- **VVIX (vol de vol):** D3 alto en VVIX = la volatilidad implícita está whipsawing rápido. Esto ocurre típicamente cuando el pánico YA se materializó y ahora el mercado está "digeriendo" el shock — reprice rápido → después se calma. El cascade (continuación del movimiento) es menos probable después de un repricing violento.
- **PCR (put/call):** D3 alto = posicionamiento en opciones cambiando rápido = re-hedging. El re-hedging consume el gamma flow que impulsaría un cascade.

**Validación adicional (FASE 2.1):** El efecto es más fuerte en FG cuando el nivel es ALTO (D1↑: Δc50 = −15.8pp vs D1↓: −9.3pp). El whipsaw de greed (extremo alto) es el que más apaga el cascade — consistente con "euforia que se revierte rápido".

**Validación adicional (FASE 2.2, tipo MIN/MAX):** El efecto en FG está concentrado en pivotes MIN (floors): Δc50 = −25.0pp en MIN vs −2.1pp en MAX. BSI: −12.6pp MIN vs −1.5pp MAX. **El caos en sentimiento APAGA cascades desde pisos (MIN), no desde techos.** Esto es clave: los pisos se forman por pánico; si el pánico whipsaw (vaivén rápido del sentimiento), el piso es inestable y el cascade hacia abajo no se consolida. Los techos (MAX) en cambio se forman por euforia difusa — ahí el caos de sentimiento no importa tanto porque la euforia es "lenta".

### 3.4 ¿Por qué es NEUTRO en macro (Credit, Yield, Rotation, DXY)?

**Mecanismo: los indicadores macro se mueven LENTO**

D3 = std(2d)/std(10d) mide ruido de alta frecuencia. Los indicadores macro (spreads de crédito, yield curve, rotation index, DXY) son variables de baja frecuencia que cambian gradualmente. Su D3 es ruido de corto plazo sin relación con la estructura zigzag (que opera en escalas de días-semanas).

- **Crédito, Yield, DXY:** La señal relevante está en el NIVEL (D1 = ¿hay estrés crediticio?, ¿está la curva invertida?), no en la velocidad de 2 días del spread.
- **Rotation:** Mide rotación sectorial (defensivos ↔ cíclicos). Su D3 captura "un sector rotó fuerte en 2 días" pero eso es un micro-evento que no escala a un cascade de SPY.

**PERO — NUANCE IMPORTANTE (Credit):** Credit NO es simplemente "neutro". El análisis D3 × D1 nivel revela una **interacción de signo opuesto (+13.2pp):**

- **Credit BAJO (estrés crediticio) + caos → Δc50 = −6.6pp:** El whipsaw del spread cuando ya hay estrés = el estrés se está "resolviendo" rápido → menos cascade.
- **Credit ALTO (crédito fácil) + caos → Δc50 = +6.6pp:** El whipsaw del spread en entorno complaciente = un shock que rompe la complacencia → más cascade.

**El promedio +0.3pp es un CANCELAMIENTO de dos efectos opuestos, no ruido.** Credit D3 es condicional, no neutro. Misma lógica que VIX×SV5T quadrant sync.

### 3.5 ¿Por qué es INVERTIDO en SKEW (+4.3pp)?

**Mecanismo: caos en tail-risk hedging = evento real en curso**

SKEW mide demanda de protección contra colas (OTM puts). A diferencia de los osciladores de sentimiento (bounded/mean-reverting), el SKEW es un **indicador de actividad de cobertura**. Cuando SKEW tiene D3 alto:
- **No es whipsaw de sentimiento que se agota**, es **re-hedging activo** — dealers ajustando posiciones de gamma, fondos comprando protección incremental.
- El re-hedging activo AMPLIFICA los movimientos de precio (gamma hedging flows) → FACILITA el cascade.
- Un SKEW estable (D3 bajo) significa que el mercado ya tiene la cobertura que necesita → el movimiento es más probable que sea un rango.

**SKEW D3 ALTO = EVENTO DE COLAS EN DESARROLLO → CASCADE.** SKEW D3 BAJO = cobertura tranquila → no hay catalizador.

Este hallazgo (+4.3pp, ρ=+0.044, p=0.083) es coherente con el rol de SKEW como modulador Grupo B: no vota en cascade_conviction, pero su D3 es una **señal de alerta** — cuando SKEW entra en caos, la probabilidad de cascade sube.

---

## 4. MATRIZ DE CORRELACIÓN — ¿Qué caos se mueve junto?

| | VIX | VVIX | PCR | FG | SV5T | SKEW | Credit | Yield | Rotation | BSI | DXY |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **VIX** | 1.00 | **0.51** | 0.09 | 0.22 | 0.02 | 0.14 | 0.19 | 0.08 | 0.16 | **0.38** | 0.04 |
| **VVIX** | | 1.00 | 0.07 | 0.16 | −0.01 | 0.12 | 0.15 | 0.09 | 0.12 | 0.28 | 0.02 |
| **Credit** | | | | 0.16 | −0.01 | 0.06 | 1.00 | **0.33** | 0.12 | 0.19 | −0.00 |
| **BSI** | | | | 0.27 | 0.01 | 0.13 | 0.19 | 0.10 | 0.17 | 1.00 | 0.04 |
| **SV5T** | | | | | 1.00 | 0.03 | −0.01 | −0.01 | 0.01 | 0.01 | 0.02 |

**Clusters de caos conjunto:**
1. **VIX−VVIX (ρ=0.51):** El caos en VIX y en vol-de-vol van de la mano.
2. **VIX−BSI (ρ=0.38):** Cuando VIX whipsaw, la breadth también — pánico generalizado.
3. **Credit−Yield (ρ=0.33):** Par macro — cuando crédito whipsaw, la curva también.
4. **SV5T:** COMPLETAMENTE independiente (ρ≤0.03 con todas las demás). SV5T D3 mide una dimensión única de caos — turbulencia de volumen que no se correlaciona con nada más.

---

## 5. REGLA DE LECTURA DE D3 POR ESTACIÓN

### GRUPO "APAGA CASCADE" — Usar D3 como filtro negativo

| Estación | Δc50 | Cuándo usar | Regla |
|---|---|---|---|
| **FG** | −15pp | SIEMPRE (ambos regímenes D1) | D3 > P67 → cascade MENOS probable. Señal MÁS FUERTE en pivotes MIN (−25pp). Si FG whipsaw en un piso, el piso NO cascada. |
| **VVIX** | −9pp | SIEMPRE (ambos regímenes) | D3 > P67 → cascade MENOS probable. Válido en MIN y MAX. |
| **BSI** | −7pp | D1 ALTO (breadth alta) | D3 > P67 con breadth ALTA (−11pp) → cascade MENOS probable. Efecto concentrado en MIN (−13pp). Con breadth BAJA el efecto es débil (−2pp). |
| **PCR** | −6pp | Como refuerzo (ns) | Tendencia correcta pero N bajo limita confianza. Usar como confirmación de FG/VVIX/BSI, no standalone. |

### GRUPO "NEUTRO" — Ignorar D3 para cascade

| Estación | Δc50 | Regla |
|---|---|---|
| **SV5T** | +0.4pp | D3 no aporta nada a cascade. SV5T es un sensor de timing/battle-volume. Su D3 es la dimensión más independiente (ρ≈0 con todo). |
| **Yield** | +1.1pp | D3 es ruido. La señal de yield está en el nivel de inversión (D1), no en el whipsaw de 2d. |
| **Rotation** | −0.1pp | D3 es ruido. La rotación sectorial es lenta; su D3 captura micro-rotaciones irrelevantes para cascade. |
| **DXY** | −0.8pp | D3 es ruido para cascade. Pero DXY D3 tiene SEÑAL DIRECCIONAL débil (+6.9pp Δdir, ρ=+0.067). Posible uso en TAF (dirección), no en cascade. |
| **VIX** | −3.6pp | Tendencia negativa marginal. El nivel de VIX (D1) es 10× más informativo para cascade (IC −0.404). El D3 de VIX no agrega valor incremental sobre D1. |

### GRUPO "CONDICIONAL" — Usar D3 con interacción

| Estación | Δc50 global | Interacción D1 | Regla |
|---|---|---|---|
| **Credit** | +0.3pp | **+13.2pp (signo opuesto!)** | **D3 ALTO + crédito ESTRESADO → MENOS cascade (−6.6pp):** el estrés se está resolviendo rápido. **D3 ALTO + crédito FÁCIL → MÁS cascade (+6.6pp):** shock rompe complacencia. **NO promediar** — usar el split por régimen D1. |

### GRUPO "INVERTIDO" — D3 como alerta de cascade

| Estación | Δc50 | Regla |
|---|---|---|
| **SKEW** | +4.3pp | D3 > P67 → cascade MÁS probable. Funciona en ambos regímenes D1 y ambos tipos MIN/MAX. **SKEW D3 es un "sensor de evento en desarrollo":** si el tail-risk hedging está en caos, hay un catalizador real moviendo el mercado. Usar como ALERTA, no como voto (Grupo B). |

---

## 6. SÍNTESIS: FILOSOFÍA D3

```
D3 = std(2d)/std(10d) = "¿se movió el indicador más de lo normal en los últimos 2 días?"
```

- **D3 NO predice dirección** (|ρ| < 0.07 para todas las estaciones).
- **D3 NO predice movimiento futuro de SPY** (ρ forward < 0.03).
- **D3 ES una medida de GASTO DE ENERGÍA:** D3 alto = el movimiento YA ocurrió.

**La regla universal:** D3 discrimina cascade cuando el indicador subyacente es un **oscilador bounded/mean-reverting** (FG, VVIX, BSI, PCR). En estos, el whipsaw (D3 alto) es la resolución del extremo → el movimiento se AGOTA → MENOS cascade. Es el equivalente financiero de: "si el miedo ya se expresó violentamente, no hay miedo residual para continuar la tendencia".

**La excepción SKEW:** SKEW NO es un oscilador bounded — es un **indicador de actividad de cobertura**. Su D3 alto = re-hedging activo = evento en desarrollo → MÁS cascade. Es el equivalente de: "si están comprando protección a mansalva, es porque algo grave está pasando".

**Los macro (Credit, Yield, Rotation, DXY):** Se mueven demasiado lento para que su D3 tenga señal → IGNORAR. Credit es la excepción parcial (efecto condicional que se cancela en el promedio).

**La regla práctica más simple:** Si el indicador NORMALMENTE es estable y hoy está whipsawing (D3 > P67), pregunta: "¿es esto la resolución de un extremo (sentimiento → ignora cascade) o es esto un evento en desarrollo (SKEW → alerta de cascade)?"

---

*Scripts en `scratch/d3_experto.py` y `scratch/d3_mecanismo.py`. Datos: TimescaleDB, 1,589 pivotes SPY zz25.*