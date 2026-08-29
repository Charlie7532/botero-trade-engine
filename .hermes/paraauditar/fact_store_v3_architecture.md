# Fact Store V3 — Documentación Completa de Arquitectura, Estadística e Interpretación

> **Propósito:** Referencia definitiva para cualquier agente o sesión que trabaje con los fact stores.
> Leer ANTES de escribir cualquier código que consulte, genere, o interprete fact stores.

---

## 1. Qué Son los Fact Stores

Un Fact Store es un **JSON de probabilidades prospectivas** condicionado al estado observable del mercado. Para cada combinación de 3 dimensiones (D1×D2×D3), el fact store contiene:

- **Capa Estándar:** Retornos esperados del SPY a 1d, 3d, 5d (`zz25/zz50/zz75`)
- **Capa Cinemática:** Retornos de pierna ZigZag física (`zigzag_kinematic.zz25/zz50/zz75`)
- **Momentum Estructural:** Tendencia HH/HL/LH/LL (`structural_momentum`)
- **Efecto Dominó:** Qué tipo de pierna precedió este estado (`prev_leg_domino`)

### Fact Stores vs quants_obs — Son Instrumentos Diferentes

| | **Fact Store** (Prospección) | **quants_obs** (Historia) |
|---|---|---|
| **Dirección temporal** | → ADELANTE | ← ATRÁS |
| **Pregunta que responde** | "Dado que HOY el estado es X, ¿qué espero?" | "En pivotes pasados con estado X, ¿qué pasó?" |
| **Población** | Todos los días de mercado en el estado | Solo los pivotes ZigZag (MAX/MIN) |
| **Filtro pivot_type** | NO — incluye todos los días | SÍ — filtra por MAX o MIN |
| **Uso** | Engine de decisión en producción | Validación empírica (backtest) |
| **Sesgo** | Ninguno (población completa) | Selección por pivote (infla WR) |

**Regla:** La validación correcta requiere consistencia entre ambas fuentes. Si divergen >20%, investigar el sesgo de selección por `pivot_type`.

---

## 2. Cadena de Generación

```
Neon PostgreSQL (market.ohlcv_bars + market.zigzag_legs)
    ↓
    ├─ TimescaleDataStore.load_bars()      → Series del indicador (VIX, BSI, etc.)
    ├─ ZigzagLegRepository                 → Piernas ZigZag confirmadas del SPY
    │   └─ market.zigzag_legs              → 4M+ legs, 613 tickers, 3 escalas, desde 1927
    ↓
v3_fact_table_engine.py (Motor compartido)
    ├─ Expanding Window Rank (D1)          → Zero look-ahead bias
    ├─ diff(3) (D2 Velocity)               → Cinemática 72h
    ├─ std(2d)/std(10d) (D3 Vol)           → Estabilidad intra-indicador
    ├─ compute_standard_scale_metrics()    → Capa Estándar (retorno diario)
    ├─ compute_zigzag_scale_metrics()      → Capa Cinemática (retorno de pierna)
    ├─ compute_structural_momentum()       → HH/HL/LH/LL (MIN→MIN, MAX→MAX)
    └─ compute_domino_stats()              → Lookback (pierna anterior)
    ↓
backend/modules/entry_decision/domain/rules/{station}_fact_store.json
```

**Generadores:** 11 scripts en `backend/scripts/generators/generate_{station}_fact_table.py`, cada uno define:
- `D1_LABELS`: Nombres de los 6 bines gaussianos del indicador
- `pivot_fn`: Detección de pivotes físicos del indicador (opcional)
- `pivot_overrides`: Sobrecargas de `operational_guidance` por pivote

---

## 3. La Tríada ZigZag — Vector de Estado Multi-Escala

> **CONCEPTO FUNDAMENTAL:** Cada día de mercado tiene un **vector de estado (D1, D2, D3)** por cada estación METAR. Al día siguiente, el vector CAMBIA — nuevas probabilidades, nueva velocidad, nueva estabilidad. El fact store no es una foto fija: es una serie temporal de vectores de estado que evolucionan diariamente.

### 3.0 El Vector de Estado y su Naturaleza Temporal

Cada estación METAR produce **tres vectores** simultáneos, uno por cada escala ZigZag:

```
DÍA T (ejemplo: VIX en CRISIS_SPIKE__FAST_SPIKE_3D__VOL_ACCEL):
  zz25 → p_bull=0.30, ev=-0.015, e_days=4     ← pullback táctico
  zz50 → p_bull=0.35, ev=-0.032, e_days=12    ← corrección
  zz75 → p_bull=0.42, ev=-0.051, e_days=35    ← movimiento estructural

DÍA T+1 (VIX baja → pasa a ELEVATED_PANIC__DECEL_DOWN_3D__VOL_NEUTRAL):
  zz25 → p_bull=0.48, ev=-0.003, e_days=3     ← perdió fuerza táctica
  zz50 → p_bull=0.40, ev=-0.018, e_days=10    ← aún bearish intermedio
  zz75 → p_bull=0.38, ev=-0.045, e_days=30    ← sigue bearish estructural
```

**La relación entre los tres vectores es PREDICTIVA:**

| Patrón inter-escala | p_bull zz25 vs zz50 vs zz75 | Significado | Implicación operacional |
|---|---|---|---|
| **Convergencia alcista** | 0.70 → 0.68 → 0.65 | Las tres escalas dicen lo mismo: BULL | Alta convicción para ENTRY |
| **Convergencia bajista** | 0.30 → 0.28 → 0.25 | Las tres escalas dicen lo mismo: BEAR | Alta convicción para EXIT |
| **Divergencia de agotamiento** | 0.65 → 0.50 → 0.35 | Lo táctico dice BULL pero lo estructural dice BEAR | Movimiento se agota — no escala |
| **Divergencia de reversión** | 0.35 → 0.50 → 0.70 | Lo táctico dice BEAR pero lo estructural dice BULL | Movimiento es contrarían — buscar piso |
| **Asimetría EV** | ev +0.01, +0.03, +0.08 | EV crece con la escala | Señal asimétrica — upside crece más que downside |
| **Simetría EV** | ev -0.01, -0.01, -0.01 | EV igual en las tres escalas | Señal proporcional — movimiento uniforme |

**En producción** (ver [`convergence_compositor.py`](file:///root/botero-trade/backend/modules/entry_decision/domain/services/convergence_compositor.py)):

Cada METAR service empaqueta el vector triádico completo:
```python
# Cada estación emite un VECTOR, no un escalar:
ev_net_vector  = [guidance.zz25.ev_net,  guidance.zz50.ev_net,  guidance.zz75.ev_net]
p_bull_vector  = [guidance.zz25.p_bull,  guidance.zz50.p_bull,  guidance.zz75.p_bull]
e_days_vector  = [guidance.zz25.e_days,  guidance.zz50.e_days,  guidance.zz75.e_days]
```

El compositor diferencia por escala usando `SCALE_FACTORS` (IC empírico por horizonte temporal):
```python
# EV compuesto corto plazo: pesa ZZ25
ew_1d = station_weight * scale_factor["zz25"] * reliability_factor(N)
# EV compuesto largo plazo: pesa ZZ75
ew_5d = station_weight * scale_factor["zz75"] * reliability_factor(N)
```

### 3.1 Las Tres Escalas

| Escala | Umbral | Fenómeno que Captura | Horizonte Típico | Análogo |
|---|:---:|---|:---:|---|
| **zz25** (2.5%) | ≥ 2.5% | **Pullbacks tácticos.** Retrocesos menores dentro de una tendencia. Ruido de alta frecuencia del mercado. | 1-15 días | Olas intradía/semanal |
| **zz50** (5.0%) | ≥ 5.0% | **Correcciones intermedias.** Cambios de sentimiento que duran semanas. La escala donde la mayoría de los swing trades operan. | 5-60 días | Corrección de mercado |
| **zz75** (7.5%) | ≥ 7.5% | **Movimientos estructurales.** Cambios de régimen, crashes, bear markets, rally post-capitulación. Señales de alta convicción. | 20-200+ días | Bear/Bull market legs |

### 3.2 El Programa de Overflow (Cascada entre Escalas)

Una pierna ZigZag en zz25 puede "desbordar" (overflow) a zz50 si el movimiento supera el 5%, y a zz75 si supera el 7.5%. Este desborde NO es automático — depende de si el movimiento continúa sin una reversión suficiente.

```
Día 1:  SPY cae -2.8%  → ZZ25 detecta pierna bajista (>2.5%)  ✓
                        → ZZ50: aún no (necesita >5.0%)         ✗
                        → ZZ75: aún no (necesita >7.5%)         ✗

Día 5:  Acumulado -5.3% → ZZ25: misma pierna continúa          ✓
                        → ZZ50: OVERFLOW — nueva pierna (>5.0%) ✓
                        → ZZ75: aún no                          ✗

Día 12: Acumulado -8.1% → ZZ25: misma pierna continúa          ✓
                        → ZZ50: misma pierna continúa           ✓
                        → ZZ75: OVERFLOW — nueva pierna (>7.5%) ✓  ← CASCADA COMPLETA
```

**Reglas del Overflow:**

1. **Overflow es acumulativo y direccional.** Solo ocurre si el movimiento continúa en la misma dirección sin reversión mayor que el umbral de la escala superior.

2. **No toda pierna zz25 desborda.** La tasa de overflow de zz25→zz50 es la `cascade_50` en quants_obs. La tasa zz25→zz75 es `cascade_75`. Típicamente: ~40% desbordan a zz50, ~25-30% a zz75.

3. **Las señales que predicen overflow son las más valiosas.** Una señal EXIT que dice "este pullback de -3% va a convertirse en una corrección de -8%" tiene más valor operacional que una que solo dice "va a caer".

4. **La Tríada se mide COMPLETA.** Para cada señal, se reportan las tres escalas:
   - **zz25:** ¿Hay un movimiento táctico? (base mínima)
   - **zz50:** ¿El movimiento escala a corrección? (potencia)
   - **zz75:** ¿El movimiento es estructural/crash? (severidad)

5. **La escalada de p_bull entre escalas es diagnóstica:**
   - Si $p_{bull}$ se mantiene estable (ej. 0.55 → 0.56 → 0.57): señal de **continuación** — el movimiento es sostenido.
   - Si $p_{bull}$ cae (ej. 0.55 → 0.45 → 0.35): señal de **agotamiento** — el movimiento pierde fuerza en escalas mayores.
   - Si $p_{bull}$ sube (ej. 0.40 → 0.55 → 0.70): señal de **reversión** — los movimientos grandes tienden a revertir.

6. **Overflow > 3σ = verificación obligatoria.** Cuando existe un overflow entre escalas y la magnitud de la pierna previa (`prev_leg_return`) supera 3 desviaciones estándar de la población histórica, **el dato existe y DEBE verificarse**. No se asume — se mide.

   Los campos que ya contienen esta información en el fact store:

   ```
   prev_leg_domino:
     p_extreme_prev      → Fracción con |prev_leg_return| > P90 de la población
     extreme_threshold_p90 → El umbral numérico del P90 (ej. 0.087 = 8.7%)
     terciles_domino:
       t3_large:
         mean_abs_return  → Retorno medio de las piernas grandes (tercil 3)
         cascade_rate     → Tasa de cascada cuando la pierna previa fue grande
   ```

   **Regla operacional:** Si `|prev_leg_return|` > 3σ de `domino_zz25.std` (calibración: σ ≈ 0.035 para zz25, σ ≈ 0.064 para zz50):
   - zz25: 3σ ≈ 0.105 (10.5%) → pierna previa fue extrema
   - zz50: 3σ ≈ 0.192 (19.2%) → pierna previa fue una crisis

   En estos casos:
   - **Consultar `cascade_rate` del tercil `t3_large`**: ¿cuántas piernas extremas cascadean?
   - **Consultar `p_extreme_prev`**: ¿qué fracción de las piernas en este estado fueron extremas?
   - **Cruzar con `cascade_conviction_50/75`**: el z-score del domino ya pondera esta extremidad
   - **Estos eventos son diamantes** (ver Sección 3.3) — cada uno se analiza individualmente

### 3.3 Diamantes Estadísticos (N Bajo ≠ Descartable)

> **REGLA INAMOVIBLE:** Los estados con muestra baja (N < 10) en la Tríada NO se descartan. Son **diamantes estadísticos** que se analizan por separado.

**¿Por qué son diamantes?**

Los eventos más importantes del mercado son inherentemente raros:
- VIX CRISIS_SPIKE solo ocurre ~5% del tiempo
- La combinación CRISIS_SPIKE + FAST_SPIKE_3D + VOL_PEAK_DECELERATION puede tener N=3 en 26 años
- Pero esos 3 eventos incluyen 2008, 2020, y otro crash — son los momentos donde más capital se gana o se pierde

**Protocolo para Diamantes:**

| N | Tier | Qué se puede inferir | Qué NO se puede inferir |
|:---:|---|---|---|
| 1-2 | ANECDOTAL | El evento existe y tuvo un resultado específico | Nada probabilístico |
| 3-5 | LOW | Dirección predominante (bull/bear) | Magnitudes, conos de dispersión |
| 6-10 | MODERATE | Probabilidad con alta incertidumbre, dirección confiable | EV preciso, cuartiles |
| 11-20 | HIGH | Probabilidad y EV con incertidumbre moderada | Terciles finos |
| 21+ | ROBUST | Todo | — |

**Análisis separado de diamantes:**

1. **Listar cada evento individualmente** con fecha, contexto de mercado, y resultado
2. **Identificar si hay un patrón narrativo** (ej. "los 3 eventos fueron crashes sistémicos")
3. **NO aplicar Bayesian Shrinkage agresivo** — con N=3, el shrinkage con m=10 tira el dato hacia el prior neutro y destruye la señal
4. **Reportar la tasa cruda** junto con la tasa shrunk: `p_raw = n_pos/n_tot` vs `p_bayesian`
5. **Cruzar con quants_obs** para verificar si la historia confirma el diamante

**Ejemplo de diamante:**
```
VIX: CRISIS_SPIKE__FAST_SPIKE_3D__VOL_PEAK_DECELERATION
  N = 3 (tier = LOW)
  zigzag_kinematic.zz75: n_pos=0, n_neg=3 → p_bull_raw=0.000, p_bull_bayesian=0.385
  
  El shrinkage dice 38.5% bull — INCORRECTO para decisiones.
  La realidad es 0/3 = 100% bear. Los 3 eventos fueron:
    - Lehman Brothers (2008): SPY -50%
    - COVID crash (2020): SPY -34%
    - [otro evento extremo]
  
  Este diamante vale más que 1000 observaciones de MODERATE_VOL__STABLE__NEUTRAL.
  Se analiza cualitativamente, no se descarta por N bajo.
```

---

## 4. Las Tres Dimensiones (D1×D2×D3)

Cada estado es un `state_key` con formato `D1__D2__D3`. Ejemplo: `CRISIS_SPIKE__FAST_SPIKE_3D__VOL_ACCELERATING_EXPANSION`.

### 4.1 El Vector de Datos Crudo

Para cada estación, el motor calcula **tres valores numéricos crudos** que luego clasifica:

```python
val = series[t]                           # D1: Valor del indicador HOY
vel = series[t] - series[t-3]             # D2: Cambio en 3 días (diff(3))
vol = std(series[t-1:t+1]) / std(series[t-9:t+1])  # D3: std(2d) / std(10d)
```

| Dimensión | Variable cruda | Fórmula exacta | Unidades | Qué mide |
|---|---|---|---|---|
| **D1** | `val` | Valor directo del indicador | Unidades del indicador (puntos VIX, %, ratio) | **Nivel absoluto** — ¿dónde está el indicador hoy? |
| **D2** | `vel` | `val[t] - val[t-3]` | Mismas unidades que D1 (Δ puntos VIX, Δ%, Δratio) | **Velocidad de cambio** — ¿se está moviendo rápido? ¿en qué dirección? |
| **D3** | `vol` | `std(val, 2d) / std(val, 10d)` | Ratio adimensional (sin unidades) | **Estabilidad** — ¿el indicador está quieto o volátil? |

### 4.2 D1 — Nivel Direccional (6 bines)

**Dato crudo:** `val = series[t]` → el valor del indicador en el día $t$.
- VIX: `val = 34.1` (puntos VIX)
- BSI (S5TW): `val = 7.8` (% de acciones del S&P 500 sobre su media de 20 días)
- Credit: `val = 0.644` (ratio HYG/LQD)

**Clasificación:** NO se usan bordes fijos. Se usa **Expanding Window Percentile Rank** con zero look-ahead bias:
```python
rank = series[:t].rank(pct=True).iloc[-1]  # Percentil expandible hasta HOY
# Luego se clasifica usando bordes Gaussianos σ sobre el rank:
bins = [0.0228, 0.1587, 0.5000, 0.8413, 0.9772]  # -2σ, -1σ, μ, +1σ, +2σ
# Si rank < 0.0228 → Bin 0 (extremo inferior, ej. DEEP_COMPLACENCY)
# Si rank > 0.9772 → Bin 5 (extremo superior, ej. CRISIS_SPIKE)
```

**Labels D1:** Específicos por estación. 6 bines = 6 nombres descriptivos:

| Estación | Bin 0 (< −2σ) | Bin 1 | Bin 2 | Bin 3 | Bin 4 | Bin 5 (> +2σ) |
|---|---|---|---|---|---|---|
| **VIX** | DEEP_COMPLACENCY | LOW_VOL | MODERATE_VOL | HIGH_VOL | ELEVATED_PANIC | CRISIS_SPIKE |
| **BSI** | BREADTH_WASHED_OUT | OVERSOLD_BREADTH | NEUTRAL_LOW_BREADTH | NEUTRAL_HIGH_BREADTH | EXPANSIVE_BREADTH | HYPER_EXPANSIVE_BREADTH |
| **F&G** | EXTREME_FEAR | FEAR | NEUTRAL_FEAR | GREED | EXTREME_GREED | EUPHORIA |
| **Credit** | CREDIT_CRISIS | CREDIT_STRESS | ELEVATED_CREDIT_STRESS | STABLE_CREDIT | CREDIT_EASE | DEEP_CREDIT_EASE |
| **Rotation** | DEFENSIVE_CAPITULATION | DEFENSIVE | NEUTRAL_ROTATION | BALANCED | CYCLICAL_LEADERSHIP | AGGRESSIVE_ROTATION |
| **PCR** | EXTREME_CALL_HEAVY | BULLISH_PCR | NEUTRAL_PCR | ELEVATED_PCR | HIGH_PUT_PANIC | EXTREME_PUT_PANIC |
| **VVIX** | EXTREME_COMPLACENCY | LOW_VVIX | MODERATE_VVIX | HIGH_VVIX | ELEVATED_VVIX | EXTREME_VVIX |
| **SV5 Turb** | QUIET_FLOW | LOW_TURBULENCE | MODERATE_TURBULENCE | HIGH_TURBULENCE | ELEVATED_TURBULENCE | CRISIS_TURBULENCE |
| **SKEW** | LOW_TAIL_RISK | NORMAL_TAIL_RISK | ELEVATED_TAIL_RISK | HIGH_TAIL_RISK | TAIL_PARANOIA | BLACK_SWAN_PARANOIA |
| **Yield** | DEEP_INVERSION | MODERATE_INVERSION | FLAT_CURVE | NORMAL_CURVE | STEEPNING_CURVE | EXTREME_STEEPNING |
| **DXY** | DEEP_DOLLAR_CRUSH | WEAK_DOLLAR | MODERATE_LOW_DOLLAR | MODERATE_HIGH_DOLLAR | ELEVATED_DOLLAR_STRESS | DOLLAR_SPIKE_CRISIS |

### 4.3 D2 — Velocidad Cinemática (5 bines)

**Dato crudo:** `vel = val[t] - val[t-3]` → cambio del indicador en 3 días.
- VIX: `vel = +6.99` → VIX subió 6.99 puntos en 3 días (spike de pánico)
- BSI: `vel = -26.2` → Breadth cayó 26.2 puntos porcentuales en 3 días (destrucción)

**Unidades:** Las MISMAS que el indicador. No es un retorno porcentual — es diferencia aritmética.

**Clasificación:** Percentiles Gaussianos `[0.0228, 0.1587, 0.8413, 0.9772]` sobre la **población histórica completa** de `vel` para esa estación. Los bordes son EMPÍRICOS (quantile), no paramétricos.

**Labels D2 (universales para todas las estaciones):**

| Bin | Label | Significado | Vel típica |
|:---:|---|---|---|
| 0 | `FAST_CRUSH_3D` | Caída extrema en 72h (< −2σ) | Ej. VIX: < −4.5 puntos |
| 1 | `DECELERATING_DOWN_3D` | Bajando moderadamente (−2σ a −1σ) | Ej. VIX: −4.5 a −1.2 |
| 2 | `STABLE_CONTINUATION_3D` | Sin cambio significativo (−1σ a +1σ) | Ej. VIX: −1.2 a +1.3 |
| 3 | `ACCELERATING_UP_3D` | Subiendo moderadamente (+1σ a +2σ) | Ej. VIX: +1.3 a +5.0 |
| 4 | `FAST_SPIKE_3D` | Subida extrema en 72h (> +2σ) | Ej. VIX: > +5.0 puntos |

### 4.4 D3 — Estabilidad/Volatilidad Intra-Indicador (5 bines)

**Dato crudo:** `vol = std(val, 2d) / std(val, 10d)` → ratio de volatilidad reciente vs normal.
- Si `vol = 0.12` → El indicador está 8x más quieto que lo normal → **squeeze**
- Si `vol = 1.0` → Volatilidad normal del indicador → **baseline**
- Si `vol = 2.5` → El indicador es 2.5x más volátil que lo normal → **expansión**

**Unidades:** Ratio adimensional (sin unidades). Es una medida de **estabilidad del propio indicador**, no del mercado.

**Clasificación:** Mismos percentiles Gaussianos que D2.

**Labels D3 (universales):**

| Bin | Label | vol ratio | Significado |
|:---:|---|:---:|---|
| 0 | `VOL_EXTREME_SQUEEZE` | < P2.28 | Indicador congelado, calma antes de la tormenta |
| 1 | `VOL_MODERATE_COMPRESSION` | P2.28 — P15.87 | Indicador estable, baja dispersión |
| 2 | `VOL_NEUTRAL_BASELINE` | P15.87 — P84.13 | Comportamiento normal |
| 3 | `VOL_ACCELERATING_EXPANSION` | P84.13 — P97.72 | Indicador moviéndose erráticamente |
| 4 | `VOL_PEAK_DECELERATION` | > P97.72 | Indicador en volatilidad extrema (crisis) |

### 4.5 Ejemplo Concreto: Pivote MIN del 10-Jul-2002

```
Fecha: 2002-07-10 | Tipo: MIN | Cascade_50=1, Cascade_75=0

VIX:      val=34.10  vel=+6.99   vol=1.12 → ELEVATED_PANIC__FAST_SPIKE_3D__VOL_ACCEL_EXPANSION
BSI:      val= 7.80  vel=-26.20  vol=0.55 → BREADTH_WASHED_OUT__DECEL_DOWN_3D__VOL_NEUTRAL
SKEW:     val=108.79  vel=-7.55  vol=0.68 → LOW_TAIL_RISK__DECEL_DOWN_3D__VOL_NEUTRAL
Rotation: val=-0.12   vel=-0.24  vol=0.13 → NEUTRAL_ROTATION__STABLE_3D__VOL_NEUTRAL
SV5Turb:  val=11.17   vel=+3.05  vol=0.01 → ELEVATED_TURBULENCE__ACCEL_UP_3D__VOL_COMPRESSION
YieldCrv: val= 2.96   vel=-0.22  vol=1.03 → STEEPNING_CURVE__FAST_CRUSH_3D__VOL_ACCEL_EXPANSION
DXY:      val=105.77  vel=-0.57  vol=0.30 → ELEVATED_DOLLAR_STRESS__STABLE_3D__VOL_NEUTRAL
```

**Lectura:** VIX en pánico con spike rápido + Breadth destruido + Turbulencia alta → PISO CLÁSICO con 4 estaciones convergiendo en señal de capitulación. El cascade_50=1 confirma que el movimiento táctico desbordó a corrección intermedia.

### 4.6 Medición del Overflow (Cascade) — Fórmula Exacta

El overflow NO se mide por magnitud de retorno. Se mide por **co-ocurrencia temporal** entre pivotes de escalas diferentes:

```python
# Fuente: decay_check_cascade_conviction.py L115-120
starts_50 = {fecha de inicio de cada pierna ZZ50 confirmada}
starts_75 = {fecha de inicio de cada pierna ZZ75 confirmada}

cascade_50 = int(any(
    pivot_date_zz25 + timedelta(days=i) in starts_50 
    for i in range(-3, +4)  # ventana de ±3 días
))

cascade_75 = int(any(
    pivot_date_zz25 + timedelta(days=i) in starts_75 
    for i in range(-3, +4)
))
```

**Significado:** `cascade_50 = 1` significa que dentro de ±3 días del pivote ZZ25, **también arrancó una pierna ZZ50**. El movimiento táctico se convirtió en corrección intermedia.

**Tasas base empíricas (1993-2026, N=1590):**
- `cascade_50`: ~50% (la mitad de las piernas ZZ25 desbordan a ZZ50)
- `cascade_75`: ~27% (una de cada cuatro piernas ZZ25 desbordan a ZZ75)

**Total teórico de estados:** 6 × 5 × 5 = **150 por estación**. En la práctica, ~80-133 poblados.

---

## 5. Estructura de un Estado

```json
{
  "CRISIS_SPIKE__ACCELERATING_UP_3D__VOL_NEUTRAL_BASELINE": {
    "n": 78,                          // Días de mercado en este estado
    "stats": {                        // Estadísticas del valor del indicador
      "min": 16.61, "max": 46.67,
      "mean": 30.43, "std": 11.20
    },
    "divergence_regime": "...",       // Régimen de divergencia temporal
    "operational_guidance": "...",     // Acción recomendada (Taxonomía 4D)

    // ═══ CAPA ESTÁNDAR (retorno DIARIO del SPY) ═══
    "zz25": { ... },                  // Forward 1-day
    "zz50": { ... },                  // Forward 3-day
    "zz75": { ... },                  // Forward 5-day

    // ═══ CAPA CINEMÁTICA (retorno de PIERNA ZigZag del SPY) ═══
    "zigzag_kinematic": {
      "zz25": { ... },               // Piernas ZigZag 2.5%
      "zz50": { ... },               // Piernas ZigZag 5.0%
      "zz75": { ... }                // Piernas ZigZag 7.5%
    }
  }
}
```

---

## 6. Capa Estándar (`zz25`/`zz50`/`zz75` a nivel de estado)

**Mide:** Retorno DIARIO del SPY. "Si hoy estoy en este estado, ¿qué retorno espero mañana / en 3d / en 5d?"

| Campo | Fórmula | Interpretación |
|---|---|---|
| `n_raw` | Conteo de días | Tamaño de muestra empírico |
| `p_bull` | $(n_{pos} + m \cdot 0.5) / (N + m)$, $m=10$ | Probabilidad Bayesiana de retorno positivo |
| `p_bear` | $1 - p_{bull}$ | Probabilidad de retorno negativo |
| `e_ret_max` | $\text{mean}(r \mid r > 0)$ | Retorno medio cuando sube |
| `e_ret_min` | $\text{mean}(r \mid r < 0)$ | Retorno medio cuando baja |
| `ev_net` | $\text{credibility} \cdot EV_{sample} + (1-\text{cred}) \cdot 0$ | Esperanza matemática Bayesiana |
| `e_days` | $k$ (1, 3, o 5) | Horizonte temporal |
| `ev_per_day` | $EV_{net} / e_{days}$ | Velocidad del EV (eficiencia temporal) |
| `rr_asymmetry` | $|e_{ret\_max}| / |e_{ret\_min}|$ | Asimetría riesgo/recompensa. >1 = más upside |
| `confidence_tier` | ROBUST(≥21), HIGH(≥11), MODERATE(≥6), LOW(≥3), ANECDOTAL(≥1), NONE | Confianza estadística |

### Bayesian Laplace Shrinkage ($m = 10$)

```
P_smooth = (n_pos + 10 × 0.50) / (N + 10)    → Tira hacia 50% con muestras pequeñas
EV_smooth = (N / (N + 10)) × EV_sample        → Tira hacia 0 con muestras pequeñas
```

**Con N=10:** credibilidad = 50% (la mitad del dato, la mitad del prior neutro)
**Con N=100:** credibilidad = 91% (casi todo el dato empírico)

### 6.2 Wins/Losses Desglosados con Asimetría

> **ADDENDUM 3 — 20-Ago-2026 [PROPUESTA — NO IMPLEMENTADO AÚN]:** La media agregada (`ev_net`) esconde la asimetría ganancia/pérdida. Wins y losses deben reportarse por separado. Estos campos NO existen actualmente en los fact stores generados.

| Campo | Fórmula | Interpretación |
|-------|---------|----------------|
| `n_wins` | `count(r > 0)` | Número de días/piernas positivas |
| `n_losses` | `count(r ≤ 0)` | Número de días/piernas negativas |
| `mean_win` | `mean(r \| r > 0)` | Retorno medio cuando gana |
| `mean_loss` | `mean(r \| r < 0)` | Retorno medio cuando pierde |
| `win_rate_raw` | `n_wins / (n_wins + n_losses)` | Tasa de acierto CRUDA (sin shrinkage) |
| `profit_factor` | `gross_win / gross_loss` | Factor de profit |
| `asymmetry` | `mean_win / \|mean_loss\|` | >1: gana más de lo que pierde. <1: pierde más de lo que gana. |

**Clasificación por asimetría:**
```
asymmetry > 1.2 → 🛡️ DEFENSIVO (evitar pérdidas es más valioso que buscar ganancias)
asymmetry 0.8–1.2 → ⚖️ BALANCEADO
asymmetry < 0.8 → ⚔️ OFENSIVO (buscar ganancias es más valioso que evitar pérdidas)
```

**Ejemplo real:** `capitulacion`: mean_win=+6.91%, mean_loss=−9.22% → asimetría=0.75 → OFENSIVO (pierde 33% más de lo que gana). Sin wins/losses separados, esta asimetría es invisible.

### 6.3 Distribución Completa de Retornos (P5/P95)

> **ADDENDUM 4 — 20-Ago-2026 [PROPUESTA — NO IMPLEMENTADO AÚN]:** `ev_net` y `p_bull` NO revelan el riesgo de cola. La distribución completa es obligatoria. Estos campos NO existen actualmente en los fact stores generados.

Para cada estado, reportar percentiles:

| Percentil | Campo | Interpretación |
|-----------|-------|----------------|
| P5 | `p5_ret` | Peor escenario (cola izquierda) — el 5% peor de los casos |
| P25 | `p25_ret` | Escenario pesimista |
| P50 | `p50_ret` (median) | Escenario central (más robusto que la media) |
| P75 | `p75_ret` | Escenario optimista |
| P95 | `p95_ret` | Mejor escenario (cola derecha) — el 5% mejor de los casos |

**Por qué es crítico:**
```
Un estado con p_bull=0.55 y ev_net=+0.02 puede tener:
  P5  = -15% (cola izquierda catastrófica)
  P95 = +8%  (upside limitado)
  → El riesgo de cola es INACEPTABLE aunque la media sea positiva.
```

**Regla:** Si P5 < −10% → el estado requiere sizing reducido, independientemente de su ev_net.

### 6.4 Tasa de Activación Base (Background Rate)

> **ADDENDUM 5 — 20-Ago-2026 [PROPUESTA — NO IMPLEMENTADO AÚN]:** Una variable que se activa en >50% de los casos NO es una señal — es background. Medir la tasa de activación base ANTES de reportar cualquier estado como "señal". Este campo NO existe actualmente en los fact stores generados.

```python
base_rate = n_days_in_state / n_total_days
```

**Clasificación:**
```
base_rate > 50% → BACKGROUND (no es señal, es constante)
base_rate 20–50% → COMÚN (poder discriminante limitado)
base_rate 5–20% → NORMAL (señal potencial)
base_rate 1–5% → RARO (potencial diamante)
base_rate < 1% → EXTREMO (diamante — validar con protocolo Sección 3.3)
```

**Ejemplo real del incidente 19-Ago:**
```
BSI Oversold: base_rate = 68.9% de TODOS los pisos MIN
→ NO es una señal de piso. Es ruido de fondo.
→ Reportar "92.9% cobertura" sin mencionar base_rate del 68.9% es ENGÁÑOSO.
```

**Regla:** Todo estado reportado como "señal" DEBE incluir su `base_rate`. Si `base_rate > 50%`, no es una señal — es una constante del mercado.

---

## 7. Capa Cinemática (`zigzag_kinematic.zz25/zz50/zz75`)

**Mide:** Retorno de la PIERNA ZIGZAG COMPLETA del SPY. "Si hoy estoy en este estado y se inicia una pierna ZigZag, ¿cuánto dura, cuánto retorna, y en qué dirección?"

### 7.1 Métricas Base

| Campo | Fórmula | Interpretación |
|---|---|---|
| `n_pos` | Piernas que empiezan en MIN (alcistas) | Número de piernas bullish |
| `n_neg` | Piernas que empiezan en MAX (bajistas) | Número de piernas bearish |
| `p_bull` | Bayesian Shrinkage sobre $n_{pos} / (n_{pos} + n_{neg})$ | P(la pierna es alcista) |
| `e_ret_max` | $\text{mean}(\log(P_{end}/P_{start}) \times 100 \mid \text{up legs})$ | Retorno medio de pierna alcista (%) |
| `e_ret_min` | $\text{mean}(\log(P_{end}/P_{start}) \times 100 \mid \text{down legs})$ | Retorno medio de pierna bajista (%) |
| `ev_net` | Bayesian Shrinkage sobre $EV_{raw}$ | Esperanza matemática de la pierna |
| `e_days` | Mediana de `duration_bars` | Duración esperada de la pierna |
| `ftt_bull_days` | Mediana de duración de piernas alcistas | First-Time-To bull |
| `ftt_bear_days` | Mediana de duración de piernas bajistas | First-Time-To bear |
| `ev_per_day` | $EV_{net} / e_{days}$ | Velocidad del edge por día |
| `rr_asymmetry` | $e_{ret\_max} / |e_{ret\_min}|$ | Asimetría. >1 = conviene comprar |

> **CRÍTICO:** `p_bull` en zigzag_kinematic NO es lo mismo que en la capa estándar.
> - Capa estándar: P(retorno DIARIO > 0)
> - Capa cinemática: P(la pierna ZigZag que coincide con este estado es ALCISTA)

### 7.2 Structural Momentum (HH/HL/LH/LL)

**Mide:** Momentum de la ESTRUCTURA de precios comparando pivotes del mismo tipo (ZigZig y ZagZag, NO ZigZag).

```
up_legs (start_type = MIN):
  MIN₁ ──→ MIN₂ ──→ MIN₃
  P₀       P₂       P₄
  
  accum_ret = log(P₂ / P₀) × 100
  Si > 0 → Higher Low  (HL) → estructura alcista
  Si < 0 → Lower Low   (LL) → estructura bajista

down_legs (start_type = MAX):
  MAX₁ ──→ MAX₂ ──→ MAX₃
  P₀       P₂       P₄
  
  accum_ret = log(P₂ / P₀) × 100
  Si > 0 → Higher High (HH) → estructura alcista
  Si < 0 → Lower High  (LH) → estructura bajista
```

| Campo | Interpretación |
|---|---|
| `n_measured` | Número de transiciones mismo-tipo medidas |
| `p_continuation` | P(siguiente pivote del mismo tipo es más alto). Bayesian shrunk. |
| `ev_structural_pct` | EV acumulado del momentum estructural |
| `mean_accum_ret` | Retorno medio acumulado entre pivotes del mismo tipo |
| `median_accum_ret` | Mediana (más robusta a outliers) |
| `terciles_pct.t1_weak` | Tercil inferior: momentum débil |
| `terciles_pct.t2_neutral` | Tercil medio: momentum neutro |
| `terciles_pct.t3_strong` | Tercil superior: momentum fuerte |
| `accum_edges` | Bordes de los terciles (P33, P67) |

**Clasificación de Tendencia:**

| P(HL) | P(HH) | Tendencia |
|:---:|:---:|---|
| > 0.55 | > 0.55 | **UPTREND** — HH + HL |
| < 0.45 | < 0.45 | **DOWNTREND** — LH + LL |
| > 0.55 | < 0.45 | **DIVERGENCIA** — LH + HL (estructura deteriorándose por arriba) |
| < 0.45 | > 0.55 | **DIVERGENCIA** — HH + LL (rango expandiéndose) |
| 0.45-0.55 | 0.45-0.55 | **RANGO** — sin tendencia definida |

### 7.3 Prev Leg Domino (Lookback)

**Mide:** Qué tipo de pierna PRECEDIÓ la llegada a este estado. "¿Vine de una pierna pequeña o de un crash?"

| Campo | Interpretación |
|---|---|
| `n_measured` | Piernas con dato de pierna anterior |
| `mean_prev_return` | Retorno absoluto medio de la pierna anterior (Bayesian shrunk) |
| `median_prev_return` | Mediana del retorno absoluto previo |
| `mean_prev_duration` | Duración media de la pierna anterior (días) |
| `p_negative_prev` | P(pierna anterior fue bajista). Bayesian shrunk. |
| `p_extreme_prev` | P(pierna anterior fue extrema, > P90 de toda la población) |
| `extreme_threshold_p90` | Umbral P90 de retorno absoluto |
| `terciles_domino.t1_small` | Piernas previas pequeñas: N, retorno medio, tasa de cascada |
| `terciles_domino.t2_medium` | Piernas previas medianas |
| `terciles_domino.t3_large` | Piernas previas grandes: mayor tasa de cascada |
| `tercile_edges` | Bordes de los terciles |

**Regla del Dominó:** `cascade_rate` aumenta monotónicamente con el tamaño de la pierna previa. Piernas grandes preceden cascadas con mayor frecuencia.

---

## 8. Regímenes de Divergencia Temporal

El engine clasifica cada estado en un régimen basado en la consistencia del EV entre horizontes:

| Régimen | Condición | Significado |
|---|---|---|
| `FULL_CONVERGENT_BULL` | $EV_{1d} > 0$ Y $EV_{3d} > 0$ Y $EV_{5d} > 0$ | Todos los horizontes alcistas |
| `FULL_CONVERGENT_BEAR` | $EV_{1d} < 0$ Y $EV_{3d} < 0$ Y $EV_{5d} < 0$ | Todos los horizontes bajistas |
| `TACTICAL_REBOUND_IN_BEAR` | $EV_{1d} > 0$ Y $EV_{5d} < 0$ | Rebote táctico en tendencia bajista |
| `STRUCTURAL_BULL_PULLBACK` | $EV_{1d} < 0$ Y $EV_{5d} > 0$ | Pullback en tendencia alcista |
| `MIXED_HORIZON_TRANSITION` | Cualquier otro caso | Transición entre regímenes |

---

## 9. Operational Guidance (Taxonomía 4D)

El engine emite una acción basada en EV compuesto ($0.3 \cdot EV_{1d} + 0.4 \cdot EV_{3d} + 0.3 \cdot EV_{5d}$):

| Guidance | Condición | Acción |
|---|---|---|
| `STK_BLOCK_CRISIS` | $EV_{comp} \le -0.008$ O $p_{bull,3d} \le 0.42$ O D1 ∈ {CRISIS, SPIKE, PARANOIA} | Bloquear operación |
| `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION` | $EV_{comp} \ge 0.008$ Y $p_{bull,3d} \ge 0.58$ Y $N \ge 10$ | Acumulación máxima convicción |
| `STK_BUY_DIP_TACTICAL` | $EV_{comp} \ge 0.003$ Y $p_{bull,3d} \ge 0.52$ | Compra táctica en dip |
| `STK_TRIM_TACTICAL` | $EV_{comp} \le -0.003$ | Recorte táctico |
| `STK_HOLD_STABLE` | Cualquier otro caso | Mantener sin cambios |

---

## 10. Estaciones METAR (11 Fact Stores)

| Estación | Ticker Vault | D1 Labels | N estados | Observaciones |
|---|---|---|:---:|---|
| **VIX** | `VIX` | DEEP_COMPLACENCY → CRISIS_SPIKE | 108 | Pivotes físicos: PANIC_SPIKE, VOL_CRUSH_REBOUND |
| **BSI** | `S5TW` (breadth 20d MA) | BREADTH_WASHED_OUT → HYPER_EXPANSIVE_BREADTH | 104 | % S&P500 sobre media 20 días |
| **F&G** | `FG` | EXTREME_FEAR → EUPHORIA | 82 | CNN Fear & Greed, datos desde 2011 |
| **Credit** | `CREDIT_RATIO` (HYG/LQD) | CREDIT_CRISIS → DEEP_CREDIT_EASE | 112 | Ratio sintético, proxy de estrés crediticio |
| **Rotation** | `ROTATION_INDEX` | DEFENSIVE_CAPITULATION → AGGRESSIVE_ROTATION | 120 | z(XLY/XLP) + z(XLK/XLU) |
| **SV5 Turb** | `SV5_TURBULENCE` | QUIET_FLOW → CRISIS_TURBULENCE | 104 | std(Δ_SV5TW, 10d) |
| **SKEW** | `SKEW` | LOW_TAIL_RISK → BLACK_SWAN_PARANOIA | 98 | CBOE SKEW index (calibración post-2011) |
| **PCR** | `CBOE_PCR` | EXTREME_CALL_HEAVY → EXTREME_PUT_PANIC | 103 | Put/Call Ratio |
| **VVIX** | `VVIX` | EXTREME_COMPLACENCY → EXTREME_VVIX | 104 | Vol-de-vol |
| **Yield Curve** | `YIELD_SPREAD` | DEEP_INVERSION → EXTREME_STEEPNING | 133 | TNX − IRX (10Y − 13W) |
| **DXY** | `DXY` | DEEP_DOLLAR_CRUSH → DOLLAR_SPIKE_CRISIS | 128 | Índice del dólar |

---

## 11. Reglas de Interpretación para Señales

### 10.1 Techos (Señales EXIT) — Se Miden Diferente

Para evaluar una señal EXIT, se consulta el fact store cuando el indicador está en un D1 extremo alto:

```python
# LECTURA CORRECTA para EXIT/Techo
kinematic = estado["zigzag_kinematic"]["zz25"]

p_bear_leg = 1 - kinematic["p_bull"]         # P(la pierna es bajista)
e_caida     = kinematic["e_ret_min"]          # Retorno medio de caída
ftt_bear    = kinematic["ftt_bear_days"]      # Días hasta el piso
ev_riesgo   = kinematic["ev_net"]             # EV < 0 → estado bearish

# LOOKBACK: ¿De dónde venimos?
domino = kinematic.get("prev_leg_domino", {})
prev_ret = domino.get("mean_prev_return")      # Pierna previa grande = más cascada
cascade_rate_t3 = domino.get("terciles_domino", {}).get("t3_large", {}).get("cascade_rate", 0)

# TENDENCIA: ¿Está haciendo LH?
momentum = kinematic.get("structural_momentum", {}).get("down_legs", {})
p_hh = momentum.get("p_continuation", 0.5)    # < 0.45 = Lower Highs = deterioro
```

### 10.2 Pisos (Señales ENTRY) — Se Miden Diferente

```python
# LECTURA CORRECTA para ENTRY/Piso
kinematic = estado["zigzag_kinematic"]["zz75"]  # Escala estructural para pisos

p_bull_leg  = kinematic["p_bull"]               # P(la pierna es alcista)
e_subida    = kinematic["e_ret_max"]            # Retorno medio de subida
ftt_bull    = kinematic["ftt_bull_days"]         # Días hasta el techo
ev_oportunidad = kinematic["ev_net"]            # EV > 0 → estado bullish

# TENDENCIA: ¿Está haciendo HL?
momentum = kinematic.get("structural_momentum", {}).get("up_legs", {})
p_hl = momentum.get("p_continuation", 0.5)     # > 0.55 = Higher Lows = recuperación
```

### 10.3 Conos de Dispersión y Duración

Para techos y pisos, el **cono de tiempos** es distinto:

| Métrica | Techo (EXIT) | Piso (ENTRY) |
|---|---|---|
| Duración relevante | `ftt_bear_days` (cuánto tarda en caer) | `ftt_bull_days` (cuánto tarda en subir) |
| Retorno relevante | `e_ret_min` (cuánto cae) | `e_ret_max` (cuánto sube) |
| RR Asymmetry | < 1 → riesgo > recompensa → salir | > 1 → recompensa > riesgo → entrar |
| EV_per_day | < 0 → cada día cuesta dinero | > 0 → cada día gana dinero |

### 10.4 Costo de No Salir vs Costo de Salir

```
COSTO_NO_SALIR = |e_ret_min| × p_bear × (1 + cascade_rate_t3)
                 → Cuánto pierdo si ignoro la señal y la caída se materializa

COSTO_SALIR    = e_ret_max × p_bull
                 → Cuánto dejo de ganar si salgo y el mercado sube

RATIO_RIESGO   = COSTO_NO_SALIR / COSTO_SALIR
                 → Si > 1, es más caro NO salir que salir → SALIR
                 → Si < 1, es más caro salir que quedarse → QUEDARSE
```

---

## 12. Señales Incondicionales vs Condicionales

### Señal Incondicional
Funciona sin importar si el ZigZag detector confirmó un pivote. El hecho de estar en ese D1 ya es suficiente.

**Test:** Historia (quants_obs) y Prospección (fact store) deben coincidir con Δ < 15%.

**Validadas como incondicionales:** `vix_complacency`, `fg_extreme_greed`, `bsi_recovery` (EXIT); `bsi_washed_out`, `vvix_extreme`, `pcr_put_panic` (ENTRY)

### Señal Condicional
Solo funciona CUANDO el ZigZag detector ya confirmó un pivote MAX (para EXIT) o MIN (para ENTRY). El estado D1 amplifica la severidad del pivote, pero sin pivote confirmado, no tiene poder predictivo.

**Test:** quants_obs muestra poder (WR > 65%) pero fact store muestra p_bull ≈ 0.50 (neutral).

**Validadas como condicionales:** `def_rotation_div`, `skew_d3_vol_exp`, `rot_d2_crush`, `credit_d2_accel`

### 11.1 Matriz de Overlap entre Señales (Redundancia)

> **ADDENDUM 6 — 20-Ago-2026 [PROPUESTA — NO IMPLEMENTADO AÚN]:** Antes de proponer una "nueva capa" o "nueva señal", medir el overlap con las señales/capas existentes. Si overlap > 60%, no agrega información nueva al vector de decisión. Esta funcionalidad NO está implementada en los fact stores actuales.

```python
# Para cada par de señales (S_a, S_b):
overlap = P(S_a ∩ S_b) / P(S_a ∪ S_b)
# → % de activaciones que son COMPARTIDAS vs. DISJUNTAS
```

**Clasificación de redundancia:**
```
overlap > 80% → REDUNDANTE TOTAL (es la misma señal medida de otro ángulo)
overlap 60–80% → ALTA REDUNDANCIA (no justifica ser capa independiente)
overlap 30–60% → COMPLEMENTARIA (aporta información parcialmente nueva)
overlap < 30% → ORTOGONAL (información genuinamente nueva)
```

**Ejemplo real del incidente 19-Ago:**
```
SKEW Tail Risk overlap con señales existentes:
  vix_complacency:   86%
  credit_divergence: 82%
  bsi_recovery:      69%
  def_rotation:      65%
  sv5t_silence:      60%
→ SKEW NO es una "capa V4". Ya está implícito en el 60-86% de las capas existentes.
→ Reportar "98.7% cobertura" agregando SKEW es inflación por redundancia.
```

**Regla:** Toda nueva señal DEBE incluir su overlap matrix contra las señales existentes. Si overlap > 60% con al menos 3 señales → NO se agrega como capa independiente.

### 11.2 Agregación Cross-Estación (Precursores Universales)

> **ADDENDUM 7 — 20-Ago-2026 [PROPUESTA — NO IMPLEMENTADO AÚN]:** La arquitectura de 11 fact stores independientes es CIEGA a patrones que cruzan estaciones. Un estado bearish en UNA estación no es señal — el MISMO patrón bearish en 3+ estaciones independientes SÍ lo es. Esta funcionalidad NO está implementada en los fact stores actuales.

**Algoritmo de agregación:**
```python
# Para cada state_key D1:
precursor_counts = defaultdict(list)

for station in STATIONS:
    for state in fact_store[station]:
        if state.p_bull < 0.40:  # bearish
            key = f"{station}.D1={state.name}"
            precursor_counts[key].append({
                "station": station,
                "p_bull": state.p_bull,
                "n": state.n
            })

# Precursores universales: ≥3 estaciones independientes
universal = {k: v for k, v in precursor_counts.items() if len(v) >= 3}
```

**Interpretación:**
```
1 estación bearish  → ruido (esa estación puede estar en un extremo normal)
2 estaciones bearish → atención (dos fuentes independientes coinciden)
3+ estaciones bearish → PRECURSOR UNIVERSAL (mercado en estado de alerta)
```

**Ejemplo real:**
```
credit: ACCELERATING_UP_3D   → p_bull=0.35 (bearish)
vix:    CRISIS_SPIKE          → p_bull=0.32 (bearish)
bsi:    BREADTH_WASHED_OUT    → p_bull=0.28 (bearish)
→ 3/11 estaciones bearish independientes → ALERTA DE CRASH
→ Este patrón NO se detecta mirando los fact stores por separado.
```

**Regla:** Reportar diariamente el "índice de estrés cross-estación": número de estaciones con D1 bearish (p_bull < 0.40). Si ≥ 3 → activar protocolo de precursores universales.

---

## 13. Confidence Tiers y Muestras Mínimas

| Tier | N mínimo | Uso |
|---|:---:|---|
| **ROBUST** | ≥ 21 | Todas las capas confiables |
| **HIGH** | ≥ 11 | Capas estándar y cinemática confiables |
| **MODERATE** | ≥ 6 | Solo capa estándar confiable |
| **LOW** | 3-5 | Solo dirección (bull/bear), no magnitudes |
| **ANECDOTAL** | 1-2 | Solo contexto, no operar |
| **NONE** | 0 | Sin datos |

### 13.1 Confidence Tiers with Bootstrap CI95

> **ADDENDUM 1 — 20-Ago-2026 [PROPUESTA — NO IMPLEMENTADO AÚN]:** Los tiers por N absoluto son una heurística. La validación definitiva requiere bootstrap CI95 con seed fija. Esta funcionalidad NO está implementada en los fact stores actuales.

| Tier | N | Condición CI95 | Interpretación |
|------|---|----------------|----------------|
| **CONFIRMED** | ≥21 | CI95 no cruza cero Y ancho < 5pp | Señal completamente validada |
| **ROBUST** | ≥21 | CI95 no cruza cero | Señal robusta |
| **DIRECTIONAL** | ≥21 | CI95 cruza cero | Dirección correcta, magnitud incierta |
| **DIAMANTE** | 3-20 | CI95 no cruza cero | Alta asimetría, evento raro valioso — analizar con protocolo de diamantes (Sección 3.3) |
| **EXPLORATORIO** | 3-20 | CI95 cruza cero | Observar, no operar |
| **INSUFICIENTE** | <3 | — | Sin datos suficientes |

**Parámetros del bootstrap:**
```python
n_iter = 3000
seed = 42
block_size = 5  # corrige autocorrelación temporal
alpha = 0.05    # CI95
```

**Regla:** El tier final es `min(tier_N, tier_CI95)`. Un estado con N=100 pero CI95 que cruza cero NO es ROBUST — es DIRECTIONAL. Un estado con N=8 y CI95 tight que no cruza cero es DIAMANTE, no LOW.

### 13.2 Effective Sample Size (N_eff)

> **ADDENDUM 2 — 20-Ago-2026 [PROPUESTA — NO IMPLEMENTADO AÚN]:** Señales que disparan en clusters temporales inflan el N bruto. Cada cluster cuenta como UN evento independiente. Esta funcionalidad NO está implementada en los fact stores actuales.

**Fórmula:**
```python
N_eff = N_bruto / (1 + 2 * sum(rho_k for k in autocorrelation_lags))
```

**Block bootstrap:** Ventana de 30 días. Si `N_eff / N_bruto < 0.5` → inflación significativa.

**Reportar AMBOS:** `N_bruto` y `N_eff`. Los confidence tiers usan `N_eff`, no `N_bruto`.

**Ejemplo real del incidente 19-Ago:**
```
credit_equity_divergence: N_bruto=120, N_eff≈42
yield_inv:               N_bruto=383, N_eff≈55
skew_tail:               N_bruto=523, N_eff≈98
→ Inflación 2.86x–6.96x. CI95 reportado con N_bruto es demasiado optimista.
```

---

## 14. Datos de Origen (Neon Vault)

### market.zigzag_legs

| Columna | Tipo | Descripción |
|---|---|---|
| `ticker` | varchar | SPY (para fact stores), o cualquier ticker |
| `scale` | varchar | `zz25`, `zz50`, `zz75` |
| `leg_id` | integer | ID secuencial de la pierna |
| `start_timestamp` | timestamptz | Inicio de la pierna |
| `start_type` | varchar | `MIN` (pierna alcista) o `MAX` (pierna bajista) |
| `start_price` | numeric | Precio al inicio |
| `end_timestamp` | timestamptz | Fin de la pierna |
| `end_type` | varchar | Tipo del pivote final |
| `end_price` | numeric | Precio al final |
| `confirmed_at_timestamp` | timestamptz | Cuándo se confirmó (causalidad) |
| `status` | varchar | `CONFIRMED` o `TENTATIVE` |
| `prev_leg_return` | numeric | Retorno de la pierna anterior |
| `prev_leg_duration` | integer | Duración de la pierna anterior en barras |

**Estadísticas:**
- zz25: 2,528,814 legs
- zz50: 989,893 legs
- zz75: 526,835 legs
- 613 tickers, desde 1927

## 15. Guía de Empleo — Qué Dato Responde Qué Pregunta

> **Si no sabemos qué información generamos, no podemos emplearla.**
> Esta sección mapea cada dato a la DECISIÓN CONCRETA que informa.

### 15.1 Mapa Completo: Dato → Pregunta → Decisión

| Dato | Pregunta que responde | Decisión que informa | Consumidor |
|---|---|---|---|
| **`p_bull` (estándar)** | ¿Es más probable que el SPY suba o baje MAÑANA? | Sesgo direccional del día | METAR telemetry |
| **`p_bull` (kinematic)** | ¿La pierna ZigZag que empieza HOY será alcista o bajista? | Timing de entrada/salida | Ceiling/Floor Engine |
| **`e_ret_max`** | Si sube, ¿cuánto espero que suba? | Sizing: target de profit | Risk Manager |
| **`e_ret_min`** | Si baja, ¿cuánto espero que baje? | Sizing: stop loss implícito | Risk Manager |
| **`ev_net`** | ¿Cuál es la esperanza matemática neta? | Decisión GO/NO-GO | Entry Gate |
| **`ev_per_day`** | ¿Cuánto EV gano por día de exposición? | Eficiencia temporal, comparación entre señales | CIO Allocator |
| **`rr_asymmetry`** | ¿El upside supera al downside? | Convexidad de la posición | Quality/Speculative sizing |
| **`e_days`** | ¿Cuánto tiempo durará este movimiento? | Horizonte del trade, selección de instrumento | Trade planner |
| **`ftt_bull_days`** | ¿Cuánto tarda en llegar al techo si sube? | Stop temporal para entries | Time stop |
| **`ftt_bear_days`** | ¿Cuánto tarda en llegar al piso si baja? | Ventana de dolor para exits | Risk Manager |
| **`confidence_tier`** | ¿Puedo confiar en estos números? | Tamaño de posición, peso de la señal | Todos |
| **`structural_momentum.up_legs.p_continuation`** | ¿Los pisos están subiendo (HL) o bajando (LL)? | Estructura de pisos (ORTOGONAL a `p_bull`, $r=0.015$) | Trend classifier |
| **`structural_momentum.down_legs.p_continuation`** | ¿Los techos están subiendo (HH) o bajando (LH)? | Clímax de distribución (HH cae 90.2% de las veces) | Ceiling Engine |
| **`prev_leg_domino.mean_prev_return`** | ¿De qué tamaño fue la pierna que nos trajo aquí? | Contexto: ¿venimos de un crash o de un drift? | Forensic context |
| **`prev_leg_domino.p_extreme_prev`** | ¿La pierna previa fue extrema (> P90)? | Umbral operativo calibrado: > 0.20-0.30 (el 50% es inalcanzable en VIX) | Circuit breaker |
| **`prev_leg_domino.cascade_rate` (t3_large)** | Si la pierna previa fue grande, ¿cascadea? | ¿Esto escala o se contiene? | Overflow predictor |
| **`cascade_50` (quants_obs)** | ¿Este pullback de 2.5% desbordó a corrección de 5%? | ¿Debí haber salido antes? | Post-mortem |
| **`cascade_75` (quants_obs)** | ¿Esta corrección de 5% desbordó a crash de 7.5%? | ¿La señal predijo algo catastrófico? | Signal severity |
| **`divergence_regime`** | ¿Los tres horizontes (1d/3d/5d) están de acuerdo? | ¿Es una señal convergente o divergente? | Conviction filter |
| **`D2 velocity`** | ¿El indicador se está MOVIENDO rápido? | ¿Es urgente actuar? | Urgency tag |
| **`D3 vol ratio`** | ¿El indicador está ESTABLE o ERRÁTICO? | ¿Puedo confiar en el nivel D1? | Signal quality |

### 15.2 Árbol de Decisión: Señal EXIT (Techo)

```
¿Hay una señal EXIT activa?
│
├─ SÍ → Consultar fact store para el estado D1__D2__D3 actual
│   │
│   ├─ ¿p_bull (kinematic) < 0.30?  ────────────────────────── ALTA CONVICCIÓN
│   │   ├─ ¿ev_net < -1.0%?  → SALIR (EV fuertemente negativo)
│   │   ├─ ¿cascade_rate_t3 > 0.50? → SALIR URGENTE (cascada probable)
│   │   └─ ¿P(LH) del structural_momentum < 0.45? → SALIR (estructura deteriorada)
│   │
│   ├─ ¿p_bull (kinematic) 0.30 — 0.45?  ──────────────────── CONVICCIÓN MEDIA
│   │   ├─ ¿D2 = FAST_SPIKE_3D? → ESPERAR (velocidad puede revertir)
│   │   ├─ ¿rr_asymmetry < 0.8? → SALIR (riesgo > recompensa)
│   │   └─ ¿ftt_bear_days < 10? → SALIR (caída rápida esperada)
│   │
│   ├─ ¿p_bull (kinematic) 0.45 — 0.55?  ──────────────────── NEUTRAL
│   │   ├─ ¿Es señal INCONDICIONAL (vix_complacency, fg_greed)?
│   │   │   └─ SÍ → REDUCIR POSICIÓN (incondicional tiene poder propio)
│   │   └─ ¿Es señal CONDICIONAL (def_rotation, skew_d3)?
│   │       └─ SÍ → ¿ZigZag detector confirmó pivote MAX?
│   │           ├─ SÍ → SALIR (condicional + pivote = alta convicción)
│   │           └─ NO → MANTENER (sin pivote, señal condicional no opera)
│   │
│   └─ ¿p_bull (kinematic) > 0.55?  ───────────────────────── MOMENTUM / CLÍMAX
│       ├─ ¿structural_momentum.exit.p_hh > 0.55? (Techo en Higher Highs)
│       │   └─ SÍ → AMPLIFICAR SEÑAL EXIT (STK_TRIM_TACTICAL / STK_DISTRIBUTE_DECAY)
│       │           (Dato empírico: los techos HH caen el 90.2% de las veces; clímax de distribución)
│       └─ NO → MANTENER con trailing stop ajustado.
│
└─ NO → Consultar METAR de rutina. Sin señal EXIT, mantener posiciones.
```

### 15.3 Árbol de Decisión: Señal ENTRY (Piso)

```
¿Hay una señal ENTRY activa?
│
├─ SÍ → Consultar fact store para el estado D1__D2__D3 actual
│   │
│   ├─ ¿p_bull (kinematic zz75) > 0.70?  ──────────────────── ALTA CONVICCIÓN
│   │   ├─ ¿ev_net > +2.0%?  → ACUMULAR (EV fuertemente positivo)
│   │   ├─ ¿P(HL) > 0.55? → ACUMULAR (estructura haciendo Higher Lows)
│   │   └─ ¿prev_leg_domino.p_extreme > 0.60? → ACUMULAR (post-capitulación)
│   │
│   ├─ ¿p_bull (kinematic zz75) 0.55 — 0.70?  ────────────── CONVICCIÓN MEDIA
│   │   ├─ ¿D2 = FAST_CRUSH_3D? → ESPERAR (puede seguir cayendo)
│   │   ├─ ¿rr_asymmetry > 1.3? → ENTRAR (recompensa supera riesgo)
│   │   └─ ¿cascade_75 rate baja? → ENTRAR (movimiento se contiene)
│   │
│   ├─ ¿p_bull (kinematic zz75) 0.45 — 0.55?  ────────────── NEUTRAL
│   │   └─ ¿P(LL) > 0.55? (structural_momentum)
│   │       ├─ SÍ → NO ENTRAR (estructura haciendo Lower Lows = trampa bajista)
│   │       └─ NO → POSICIÓN EXPLORATORIA (pequeña, con stop)
│   │
│   └─ ¿p_bull (kinematic zz75) < 0.45?  ─────────────────── CONTRADICTORIA
│       └─ El fact store dice BEAR pero la señal dice ENTRY
│           → NO ENTRAR. El piso aún no llegó.
│
└─ NO → Sin señal. No forzar entries.
```

### 15.4 Cálculo de Costo/Beneficio por Señal

```python
# CEILING: ¿Cuánto cuesta quedarse vs cuánto cuesta salir?
costo_no_salir = abs(e_ret_min) * p_bear * (1 + cascade_rate_t3)
costo_salir    = e_ret_max * p_bull
ratio_riesgo   = costo_no_salir / costo_salir

# Si ratio > 1.0 → Es más caro NO salir → SALIR
# Si ratio < 1.0 → Es más caro salir   → QUEDARSE
# Si ratio > 3.0 → Urgente salir
# Si ratio > 5.0 → Salir ya, sin esperar confirmación

# FLOOR: ¿Cuánto cuesta no entrar vs cuánto cuesta entrar?
costo_no_entrar = e_ret_max * p_bull
costo_entrar    = abs(e_ret_min) * p_bear
ratio_oportunidad = costo_no_entrar / costo_entrar

# Si ratio > 1.0 → Es más caro NO entrar → ENTRAR
# Si ratio > 3.0 → Acumular agresivamente
```

### 15.5 Integración: Cómo Fluyen los Datos en Producción

```
                    ┌─────────────────────────────────┐
                    │  Neon Vault (market.ohlcv_bars)  │
                    │  + market.zigzag_legs            │
                    └─────────┬───────────────────────┘
                              │
           ┌──────────────────┼──────────────────┐
           ▼                  ▼                  ▼
    ┌─────────────┐   ┌─────────────┐    ┌─────────────┐
    │ METAR Daemon│   │ ZZ Daemon   │    │ Fact Store  │
    │ (diario)    │   │ (diario)    │    │ Generators  │
    │             │   │             │    │ (semanal)   │
    │ val,vel,vol │   │ piernas SPY │    │ ← recalibra │
    └──────┬──────┘   └──────┬──────┘    └──────┬──────┘
           │                 │                  │
           ▼                 ▼                  ▼
    ┌──────────────────────────────────────────────────┐
    │  Estado actual: D1__D2__D3 por estación          │
    │  → Lookup en fact_store.json                     │
    │  → p_bull, ev_net, e_days, rr_asymmetry          │
    │  → structural_momentum (HH/HL/LH/LL)            │
    │  → prev_leg_domino (contexto de la pierna previa)│
    └──────────────────────┬───────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
      ┌────────────┐ ┌──────────┐ ┌──────────┐
      │CEILING     │ │FLOOR     │ │METAR     │
      │ENGINE      │ │ENGINE    │ │TELEMETRY │
      │            │ │          │ │          │
      │¿Es techo?  │ │¿Es piso? │ │¿Cómo está│
      │¿Costo de   │ │¿Costo de │ │el mercado│
      │ quedarse?  │ │ no entrar│ │hoy?      │
      └─────┬──────┘ └────┬─────┘ └────┬─────┘
            │              │            │
            ▼              ▼            ▼
      ┌─────────────────────────────────────┐
      │  DECISIÓN FINAL                     │
      │  SALIR / ENTRAR / MANTENER / SIZING │
      └─────────────────────────────────────┘
```

---

## 16. Anti-Patrones (Errores a NUNCA Repetir)

1. **Comparar `ev_net` de capa estándar con retornos de quants_obs.** La capa estándar mide retorno DIARIO (~0.001), quants_obs mide retorno de PIERNA (~5%). Son escalas diferentes.

2. **Agregar `p_bull` de capa estándar ignorando que incluye todos los días.** Un `p_bull = 0.55` en el fact store incluye días normales, pisos y techos. No es comparable con el WR de quants_obs que filtra por pivot_type.

3. **Usar t-test para validar señales.** Los retornos ZigZag NO son normales (Shapiro-Wilk p=0.000). Usar Mann-Whitney U.

4. **Ignorar structural_momentum.** Contiene la clasificación HH/HL/LH/LL que distingue tendencia de rango. Sin esto, no se sabe si un piso es HL (comprable) o LL (trampa).

5. **Mezclar la Tríada.** zz25 (2.5%), zz50 (5.0%), zz75 (7.5%) miden escalas diferentes. Una señal validada en zz25 puede ser irrelevante en zz75. Medir siempre las tres y reportar por separado.

6. **Tratar Win Rate como métrica.** El WR del ZigZag tiene sesgo estructural: pisos siempre "ganan" (la pierna siguiente sube) y techos siempre "pierden" (la pierna siguiente baja). No es una métrica válida de poder de señal.

7. **Descartar estados con N bajo.** Los estados con N=3-5 en la Tríada son diamantes estadísticos — eventos raros que capturan crashes y capitulaciones. Descartarlos por "muestra insuficiente" es destruir la señal más valiosa del sistema. Se analizan por separado con protocolo de diamantes (ver Sección 3.3).

8. **Aplicar Bayesian Shrinkage ciego a diamantes.** Con N=3, el shrinkage con m=10 produce `p_bayesian = (n_pos + 5) / (3 + 10) = 0.38-0.62` — aplana todo hacia 50%. Para diamantes, reportar SIEMPRE la tasa cruda `p_raw = n_pos / n_tot` junto con la shrunk. La decisión se toma con la cruda + contexto narrativo, no con la shrunk.

9. **Ignorar el programa de overflow.** Una señal EXIT que dice "va a caer" sin medir si la caída escala a zz50 y zz75 tiene valor operacional limitado. La cascada de overflow es lo que distingue un pullback de -3% (operable) de un crash de -15% (existencial). Siempre reportar la tasa de overflow entre escalas.

10. **Generar datos sin documentar su empleo.** Cada campo computado DEBE tener un consumidor documentado (Sección 15.1). Si un campo no aparece en el mapa Dato→Pregunta→Decisión, o se documenta o se elimina. Datos huérfanos son deuda técnica invisible.

---

---

## 17. Capa SIGMET — Eventos fuera de escala (>±3σ): implementación y protocolo

> **ADDENDUM 8 (corregido) — 20-Ago-2026:** El tratamiento de eventos >±3σ **ya está implementado** en el software, en una capa separada que NO toca los fact stores. Esta sección documenta la implementación real (verificada ejecutándola), la taxonomía de nombres para comunicar la anomalía, y la brecha de comunicación pendiente a nivel METAR.

### 17.1 Principio de diseño: los fact stores permanecen intactos

Regla codificada en `sigma_overflow.py`:

> *"Pure software layer. Fact stores are UNTOUCHED."*

Los fact stores mantienen el clipping gaussiano ±2σ (6 bins D1, 5 bins D2/D3). **No existe ni debe existir un bin ±3σ en los fact stores**, porque rompería la taxonomía gaussiana y crearía celdas ultra-raras sin estadística. La anomalía fuera de escala se gestiona en una **capa paralela de software** que lee el valor crudo.

### 17.2 Implementación real (archivos verificados)

| Componente | Archivo | Función |
|-----------|---------|---------|
| Tabla μ/σ por estación×dimensión | `backend/modules/entry_decision/domain/rules/sigma_overflow.py` (L15) | `STATION_MU_SIGMA`: μ y σ empíricos para las 11 estaciones en d1, d2, d3 |
| Detector de overflow | `sigma_overflow.py` (L74) | `validate_overflow(station, dim, value)` → `(sigma_depth, "UPPER"/"LOWER"/None)` |
| Inyección en la telemetría | 12 archivos `{station}_lookup.py` | Llama `validate_overflow()` para d1/d2/d3; puebla `sigma_depth_d1/d2/d3` + `overflow_flag` |
| Propagación al METAR | 12 archivos `{station}_metar_service.py` | Copia `sigma_depth_*` y `overflow_flag` al dataclass METAR |
| Emisión de SIGMETs | `market_sigmet_hazard_service.py` (L72, `_check_overflow_sigmet`) | Convierte overflow en SIGMET nombrado |

**Fórmula:** `z_score = (value − μ) / σ`. Si `z > +3` → overflow UPPER con `sigma_depth=z`. Si `z < −3` → overflow LOWER. Dentro de ±3σ → `(None, None)`.

**Cobertura:** D1 (nivel), D2 (velocidad 3d) y D3 (ratio de volatilidad) — las tres dimensiones están cubiertas, no solo D1.

### 17.3 Nombres para comunicar la anomalía (taxonomía SIGMET)

`_check_overflow_sigmet()` (market_sigmet_hazard_service.py L72-134) emite tres tipos:

| Condición | `hazard_type` (nombre oficial) | Severidad | Acción operacional |
|-----------|-------------------------------|-----------|-------------------|
| ≥2 dimensiones >±3σ simultáneamente | `OVERFLOW_MULTI` — "Multi-Dimensional σ-Overflow (Black Swan Anomaly)" | CRITICAL 🚨 | `MKT_MACRO_CIRCUIT_BREAKER` |
| max(sigma_depth) > 4σ | `OVERFLOW_EXTREMO` — "Extreme σ-Overflow ({depth}σ > 4σ)" | CRITICAL 🚨 | `STK_BLOCK_CRISIS` |
| 3σ < max(sigma_depth) ≤ 4σ | `OVERFLOW_MODERADO` — "Moderate σ-Overflow ({depth}σ > 3σ)" | WARNING ⚠️ | `STK_HOLD_STABLE` |

Ejemplos reales verificados (20-Ago-2026):

```
VVIX=207.59 (2020-03-16) → sigma_depth=6.96  → OVERFLOW_EXTREMO (CRITICAL)
PCR=2.872   (2010-02-05) → sigma_depth=11.03 → OVERFLOW_EXTREMO (CRITICAL)
SKEW=175.76 (2025-02-19) → sigma_depth=3.66  → OVERFLOW_MODERADO (WARNING)
```

El identificador único sigue el patrón: `SIGMET-OVERFLOW-{station}-{fecha}-{MULTI|EXTREMO|MODERADO}`.

### 17.4 Brecha de comunicación pendiente (lo que falta)

**El nombre existe a nivel SIGMET, pero NO a nivel METAR.** El reporte diario de una estación muestra el label D1 (`CRISIS_SPIKE`) sin distinguir si el valor está a +2.1σ o a +11σ. La anomalía solo se comunica cuando el servicio SIGMET evalúa y emite el evento — la telemetría METAR de rutina no porta el `sigma_depth` de forma visible para el operador.

**Tratamiento correcto (protocolo):**
1. La telemetría METAR de cada estación DEBE incluir `sigma_depth` y `overflow_flag` como campos visibles (ya están en el dataclass; falta exponerlos en el formato de reporte/broadcast).
2. Cuando `overflow_flag` está activo, el reporte METAR debe anteponer el aviso SIGMET: "⚠️ OVERFLOW_MODERADO: VIX a 3.3σ — fuera de escala gaussiana".
3. Los eventos >±3σ se registran en el inventario de eventos especiales como transiciones/disrupciones, no como estados de régimen.
4. Un SIGMET **amplifica** las señales de la estación, nunca las reemplaza: el estado D1 sigue siendo válido como clasificación; el overflow agrega urgencia y severidad.

### 17.5 Relación con las capas del sistema

```
METAR (clima diario)      → D1×D2×D3, bins gaussianos ±2σ, label D1 (clipping)
SIGMET (esta sección)     → detección >±3σ sobre D1/D2/D3, nombres OVERFLOW_*
TAF (proyección)          → cascade y forward
Diamantes (Sección 3.3)   → análisis cualitativo de lo raro
```

Un SIGMET overflow es siempre un diamante estadístico (rareza 0.13% por observación), pero un diamante no siempre es un overflow (puede ser raro por la combinación D1×D2×D3 sin exceder ±3σ en ninguna dimensión individual).

### 17.6 Inventario fáctico: eventos >±3σ en los 1,590 pivotes (medido 20-Ago-2026)

**34 eventos** en 11 estaciones. Ejemplos con valores crudos:

| Fecha | Estación | Valor crudo | Label D1 asignado (clipped) |
|-------|----------|-------------|------------------------------|
| 2020-03-16 | VVIX | 207.59 | EXTREME_VVIX |
| 2010-02-05 | PCR | 2.872 | EXTREME_PUT_PANIC |
| 2024-12 / 2025-02 | SKEW | 173.7–175.8 | BLACK_SWAN_PARANOIA |
| 2026-06-26 | SV5 Turb | 26.307 | CRISIS_TURBULENCE |
| 2002-01-31 | DXY | 120.28 | DOLLAR_SPIKE_CRISIS |
| 2008-10-15 | Yield | 3.811 | EXTREME_STEEPNING |
| 2023-05-04 | Yield | −1.705 | DEEP_INVERSION |

Total por estación: VIX=4, BSI=3, Credit=2, SKEW=4, SV5=3, VVIX=3, PCR=3, DXY=3, Yield=5, Rotation=3, FG=1.

### 17.7 Reglas

1. Los fact stores NO almacenan estados ±3σ — la anomalía vive en la capa SIGMET (`sigma_overflow.py`), que permanece como única fuente de verdad del overflow.
2. `STATION_MU_SIGMA` es la referencia de calibración: si el motor recalibra los indicadores, esta tabla debe actualizarse en paralelo (riesgo de desincronización documentado).
3. Todo estado en bin extremo (bin 0 o bin 5) debe verificarse con `validate_overflow()` antes de tratarse como estado normal. Un `CRISIS_SPIKE` a +2.1σ no es lo mismo que uno a +11σ.
4. La telemetría METAR debe exponer `sigma_depth`/`overflow_flag` (brecha pendiente, §17.4).
5. Los SIGMETs overflow entran al inventario de eventos especiales como transiciones, con nombre oficial (`OVERFLOW_MULTI/EXTREMO/MODERADO`) y profundidad σ registrada.
