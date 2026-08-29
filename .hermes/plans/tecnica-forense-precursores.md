# FORENSE DE PRECURSORES — Lógica, Técnicas y Factores de Éxito
## Cómo aislamos las señales que anteceden a los crashes
## Botero Trade — 19-Ago-2026

---

## 0. EL PROBLEMA QUE RESOLVIÓ

```
PREGUNTA: ¿Qué combinación de estados del vector METAR (D1×D2×D3)
          PRECEDE a un crash del SPY?

DIFICULTAD: 11 estaciones × ~6 estados D1 × ~5 estados D2 × ~5 estados D3
            = ~1,650 estados posibles × 4 dimensiones (D1, D2, D3, D1×D2)
            = ~6,600 combinaciones a evaluar

RESTRICCIÓN: Cada combinación aparece pocas veces. N pequeño.
             La estadística frecuentista (t-test, IC) colapsa con N<20.

SOLUCIÓN: Marco Bayesiano — lift = P(estado | CRASH) / P(estado | NO CRASH)
          No necesito que el estado sea frecuente.
          Necesito que sea DESPROPORCIONADO.
```

---

## 1. LA LÓGICA MATEMÁTICA (línea por línea)

### 1.1 El corazón del algoritmo (líneas 40-47)

```python
# Paso 1: Para una señal concreta (ej: bsi_washed_out),
#         separar sus activaciones en WINNERS y LOSERS
mask_activa = señal & fwd.notna()
winners = mask_activa & (fwd > 0)    # La señal acertó
losers  = mask_activa & (fwd <= 0)   # La señal falló

# Paso 2: Gate mínimo — si no hay suficientes datos, no analizar
if n_win < 5 or n_lose < 3:
    return None  # No hay suficientes LOSERS para ser informativo
```

**Por qué funciona:** El gate `n_lose ≥ 3` es el FILTRO MÁS IMPORTANTE del algoritmo. No es estadístico — es de SIGNIFICADO. Si un estado solo apareció en 1 o 2 crashes, no sabemos si es casualidad o patrón. Con 3, ya es un patrón que merece atención.

### 1.2 La fórmula LIFT (línea 95)

```python
# LIFT = Probabilidad del estado DADO crash / Probabilidad del estado DADO no-crash
# 
# Interpretación:
#   lift = 1.0  → El estado aparece IGUAL en crashes que en no-crashes
#   lift = 3.0  → El estado aparece 3× MÁS en crashes → PRECURSOR
#   lift = 0.3  → El estado aparece 3× MENOS en crashes → PROTECTOR
#   lift = 0.0  → El estado NUNCA aparece en crashes → PROTECTOR TOTAL
#
# Edge case: si p_win es casi 0 (estado nunca visto en winners),
#            cap lift a 10.0 para evitar división por ~0

p_win  = win_dist.get(state, 0)   # P(estado | WINNER)
p_lose = lose_dist.get(state, 0)  # P(estado | LOSER)
lift = p_lose / p_win if p_win > 0.01 else (10.0 if p_lose > 0 else 1.0)
```

**Por qué LIFT es superior a la correlación (Spearman, Pearson):**

| Métrica | Qué mide | Problema con N bajo |
|---------|----------|---------------------|
| Correlación (ρ) | Asociación lineal entre dos variables continuas | Requiere N grande para ser estable |
| t-test / CI95 | Diferencia de medias entre dos grupos | Intervalo colapsa con N < 20 |
| **LIFT (nuestro)** | Desproporción de un estado discreto entre dos grupos | Funciona con N = 3 — la desproporción ES la señal |

**La intuición Bayesiana detrás del LIFT:**

```
Antes de ver el estado:   P(crash) = n_lose / (n_win + n_lose)
Después de ver el estado: P(crash | estado) = P(estado | crash) × P(crash) / P(estado)

El LIFT es el FACTOR DE BAYES:
  P(crash | estado) / P(crash) = P(estado | crash) / P(estado) ≈ LIFT

  → Un lift de 4.1× significa que ver ese estado MULTIPLICA por 4.1
    la probabilidad de que la señal falle.
```

### 1.3 Las 4 dimensiones evaluadas (líneas 76-153)

El algoritmo no analiza solo D1. Evalúa **4 dimensiones del vector de estado**:

```python
# Dimensión 1: D1 (nivel)     → "¿en qué estado está?"
# Dimensión 2: D2 (velocidad)  → "¿hacia dónde va y a qué velocidad?"
# Dimensión 3: D3 (volatilidad) → "¿qué tan inestable es?"
# Dimensión 4: D1×D2 (cruce)   → "¿nivel + velocidad juntos?"
```

**Por qué D1×D2 es la más informativa (líneas 115-151):**

```
D1 solo:  VIX = HIGH_VOL → lift genérico
D2 solo:  VIX = ACCELERATING → lift genérico
D1×D2:    VIX = HIGH_VOL × ACCELERATING → lift MUCHO más específico

El cruce D1×D2 captura la INTERACCIÓN que D1 y D2 por separado no ven.
Es la diferencia entre "hace calor" y "hace calor Y está subiendo rápido".
```

### 1.4 La agregación de precursores universales (líneas 201-217)

```python
# Para CADA estado, contar en CUÁNTAS señales distintas aparece como precursor
# Si aparece en ≥2 señales → PRECURSOR UNIVERSAL

precursor_counts = defaultdict(list)
for sig, res in all_results.items():
    for p in res.get("precursores", []):
        key = f"{p['station']}.{p['dim']}={p['state']}"
        precursor_counts[key].append(...)

universal = [(k, v) for k, v in precursor_counts.items() if len(v) >= 2]
```

**Por qué esto es poderoso:** Un precursor que aparece en UNA sola señal puede ser un artefacto de esa señal. Un precursor que aparece en 5 de 6 señales (como `credit.D2=ACCEL_UP`) es una señal del MERCADO, no de la estrategia. La universalidad a través de señales independientes es la validación más fuerte posible.

---

## 2. LAS DECISIONES DE DISEÑO QUE LO HICIERON EXITOSO

### Decisión 1: Marco Bayesiano, no frecuentista

```
ERROR COMÚN:   "Calculemos la media de retorno forward cuando el estado X está activo"
               → Con N=3, la media es ruido. El CI95 colapsa.

NUESTRA ELECCIÓN: "Calculemos cuánto MÁS probable es un crash cuando el estado X está activo"
               → Con N=3, si las 3 veces fue crash, lift=10.0. Eso ES señal.
```

### Decisión 2: Separar WINNERS de LOSERS por señal

```
ERROR COMÚN:   "Analicemos todos los pivotes juntos"
               → Se pierde el contexto de cada estrategia.

NUESTRA ELECCIÓN: Para CADA señal registrada en medir_senal.py,
               separamos sus propias activaciones en winners y losers.
               → Un estado puede ser precursor para UNA señal pero no para otra.
               → Esto respeta la especificidad de cada estrategia.
```

### Decisión 3: Gate n_lose ≥ 3 (no n_total ≥ N)

```
ERROR COMÚN:   "Filtremos estados con N total < 20"
               → Descarta el 93% de los precursores (los más valiosos).

NUESTRA ELECCIÓN: El gate opera sobre n_lose, no sobre n_total.
               → n_lose ≥ 3: "este estado apareció en al menos 3 crashes"
               → n_win ≥ 5: "hay suficientes no-crashes para comparar"
               → Esto preserva los eventos RAROS (n_lose=3-9) que son los más informativos.
```

### Decisión 4: Evaluar D1×D2 (la interacción)

```
ERROR COMÚN:   "Evaluemos D1, D2, D3 por separado"
               → Se pierde la interacción entre nivel y velocidad.

NUESTRA ELECCIÓN: D1×D2 como cuarta dimensión.
               → Captura la combinación que D1 y D2 no ven por separado.
               → Es la dimensión MÁS informativa (lift más altos).
```

### Decisión 5: Precursores universales (cross-señal)

```
ERROR COMÚN:   "Reportemos los precursores por señal y ya"
               → No sabemos cuáles son del mercado vs de la estrategia.

NUESTRA ELECCIÓN: Agregar por "station.dim=state" y contar en cuántas
               señales aparece.
               → Universalidad = validación cruzada implícita.
               → credit.D2=ACCEL_UP en 5/6 señales = señal del mercado.
```

### Decisión 6: Código determinista, sin agentes

```
ERROR COMÚN:   "Usemos un LLM para interpretar los resultados"
               → Inconsistente, no replicable.

NUESTRA ELECCIÓN: 221 líneas de Python puro. Mismo input → mismo output.
               → Importa SEÑALES desde medir_senal.py (mismo registro).
               → Sin dependencias externas salvo pandas + numpy.
```

---

## 3. LOS 5 FACTORES DE ÉXITO

| # | Factor | Por qué fue crítico |
|---|---|---|
| **1** | **LIFT como métrica** | Funciona con N=3 donde correlación y t-test colapsan. Mide desproporción, no magnitud. |
| **2** | **Gate n_lose ≥ 3** | Preserva rareza (93% de precursores). Filtra solo anécdotas (N<3). No descarta diamantes. |
| **3** | **D1×D2 como cuarta dimensión** | Captura la interacción nivel×velocidad que D1 y D2 no ven solos. Es la dimensión más informativa. |
| **4** | **Precursores universales (cross-señal)** | Validación cruzada implícita. Lo que aparece en 5/6 señales es del mercado, no de la estrategia. |
| **5** | **Separación winners/losers por señal** | Respeta la especificidad. No asume que un precursor es universal para todas las estrategias. |

---

## 4. LA LÓGICA DE AISLAMIENTO (paso a paso)

```
ENTRADA: Una señal registrada en medir_senal.py (ej: bsi_washed_out)
         + quants_obs.pkl (1,590 pivotes con state_keys D1×D2×D3)

PASO 1 — SEPARAR:
  De todas las veces que la señal se activó (N=161):
    → WINNERS (fwd > 0):  106 eventos (65.8%)
    → LOSERS  (fwd ≤ 0):   55 eventos (34.2%)

PASO 2 — MEDIR DESPROPORCIÓN:
  Para las 11 estaciones × 4 dimensiones × cada estado:
    → P(estado | WINNER): ¿en qué % de WINNERS apareció este estado?
    → P(estado | LOSER):  ¿en qué % de LOSERS apareció este estado?
    → LIFT = P(LOSER) / P(WINNER)

PASO 3 — FILTRAR:
  Si lift ≥ 1.5 Y n_lose ≥ 3 → PRECURSOR (estado sobrerepresentado en crashes)
  Si lift ≤ 0.5 Y n_win ≥ 3  → PROTECTOR (estado sobrerepresentado en aciertos)
  Si lift ≈ 1.0              → NEUTRO (el estado no discrimina)

PASO 4 — AGREGAR (cross-señal):
  Para CADA estado (station.dim=state), contar en cuántas señales aparece.
  Si aparece en ≥2 señales → PRECURSOR UNIVERSAL.

SALIDA:
  - 86 precursores (61.6% con N_lose 3-4 — los más valiosos)
  - Protectores (estados que NUNCA crashean)
  - Precursores universales (los que trascienden a una sola estrategia)
```

---

## 5. SI TUVIERA QUE REPETIR EL EJERCICIO DESDE CERO

### Especificación precisa para garantizar el mismo resultado

```python
# ============================================================
# ESPECIFICACIÓN FORMAL — Forense de Precursores
# ============================================================

ENTRADAS:
  - df: DataFrame con 1,590 pivotes zz25 del SPY (quants_obs.pkl)
    Columnas requeridas:
      - prev_leg_return: retorno de la pierna completa
      - {station}_sk: state_key D1__D2__D3 para 11 estaciones
  - SEÑALES: diccionario {nombre: función(df)->pd.Series(bool)}
    (importado desde medir_senal.py)

PARÁMETROS:
  - LIFT_THRESHOLD_PRECURSOR = 1.5
  - LIFT_THRESHOLD_PROTECTOR = 0.5
  - MIN_WINNERS = 5
  - MIN_LOSERS = 3
  - MIN_STATE_OBS = 3        # n_w + n_l ≥ 3 para considerar un estado
  - LIFT_CAP = 10.0          # cap para evitar división por ~0

FÓRMULA CENTRAL:
  lift = P(estado | LOSER) / P(estado | WINNER)
  donde:
    P(estado | LOSER)  = count(estado EN losers) / count(losers)
    P(estado | WINNER) = count(estado EN winners) / count(winners)

  Edge case: si P(WINNER) < 0.01 → lift = 10.0 si P(LOSER) > 0, else 1.0

DIMENSIONES A EVALUAR:
  1. D1 (nivel de la estación)
  2. D2 (velocidad Δ3d)
  3. D3 (volatilidad de la estación)
  4. D1×D2 (cruce nivel × velocidad)

ESTACIONES (11):
  vix, vvix, pcr, fg, sv5_turbulence, skew,
  credit, yield_curve, rotation, bsi, dxy

ALGORITMO:
  Para cada señal en SEÑALES:
    1. Activar señal → mask_activa = señal(df) & fwd.notna()
    2. winners = mask_activa & (fwd > 0)
    3. losers  = mask_activa & (fwd ≤ 0)
    4. Si n_win < 5 o n_lose < 3 → skip (no hay suficientes datos)
    5. Para cada estación:
       a. Extraer D1, D2, D3 del state_key (str.split("__"))
       b. Para cada dimensión (D1, D2, D3, D1×D2):
          - Calcular distribución de estados en winners y losers
          - Para cada estado con n_w + n_l ≥ 3:
            * lift = p_lose / p_win
            * Si lift ≥ 1.5 y n_l ≥ 3 → PRECURSOR
            * Si lift ≤ 0.5 y n_w ≥ 3 → PROTECTOR
    6. Ordenar precursores por lift descendente
    7. Ordenar protectores por lift ascendente

  AGREGACIÓN UNIVERSAL:
    - Agrupar todos los precursores por clave "station.dim=state"
    - Contar en cuántas señales distintas aparece cada clave
    - Si ≥ 2 señales → PRECURSOR UNIVERSAL

SALIDA ESPERADA:
  - ~86 precursores totales
  - ~61.6% con N_lose = 3-4 (eventos raros → más valiosos)
  - ~7% con N_lose ≥ 10 (estadística confiable)
  - credit.D2=ACCELERATING_UP_3D como precursor universal #1 (5/6 señales)
  - Protectores con lift=0 (estados que NUNCA crashean)
```

---

## 6. LAS 3 TÉCNICAS QUE PERMITIERON EL AISLAMIENTO

### Técnica 1: LIFT como razón de verosimilitud bayesiana

```
No preguntamos "¿cuál es el retorno medio cuando X está activo?"
Preguntamos "¿cuánto MÁS probable es un crash cuando X está activo?"

Esto es sutil pero fundamental:
  - La media requiere N grande (teorema del límite central)
  - La proporción funciona con N pequeño (la desproporción ES la señal)

Es la diferencia entre "mido la magnitud del crash" y "mido la probabilidad del crash".
```

### Técnica 2: Separación por señal (contexto específico)

```
No analizamos "todos los pivotes del SPY" como una sola masa.
Analizamos "los pivotes donde la señal X se activó" por separado
para CADA una de las 6 señales analizadas.

Esto respeta que:
  - bsi_washed_out se activa en pisos (MIN)
  - credit_easing_k1 se activa en easing de crédito
  - capitulacion se activa en miedo con venta

Un estado puede ser precursor en UN contexto pero no en otro.
La especificidad ES la señal.
```

### Técnica 3: Universalidad cross-señal como validación

```
Un precursor que aparece en 1 señal → puede ser artefacto de esa estrategia.
Un precursor que aparece en 5/6 señales → es del MERCADO, no de la estrategia.

La universalidad a través de señales independientes es la validación
más fuerte posible — más fuerte que cualquier p-value.
```

---

## 7. QUÉ HARÍA DIFERENTE SI LO REPITIERA

| # | Mejora | Razón |
|---|---|---|
| 1 | Agregar bootstrap CI del lift | Para precursores con N≥10, calcular CI95 del lift via bootstrap y reportar si es significativo |
| 2 | Agregar D2×D3 como quinta dimensión | La interacción velocidad×volatilidad puede revelar patrones que D1×D2 no captura |
| 3 | Normalizar por cobertura de estación | Estaciones con menos datos (FG 35.8%) tienen lifts artificialmente inflados por muestra pequeña |
| 4 | Agregar "precursores inversos" | Estados que NUNCA aparecen en crashes (lift=0) merecen una categoría propia — son "protectores totales" |
| 5 | Validación OOS del lift | Dividir la muestra en train/test por décadas para ver si los precursores son estables |

---

## 8. LA LECCIÓN MÁS IMPORTANTE

> **"El LIFT no mide magnitud — mide desproporción. Y la desproporción es detectable con N=3, donde la magnitud requiere N=30. Esta es la razón por la que el algoritmo funciona donde otros fallan: eligió la métrica correcta para el problema correcto."**

No necesitamos más datos. Necesitamos la métrica correcta para los datos que tenemos.

---
**Firma:** deepseek/deepseek-v4-pro (Hermes)
**Fecha:** 19-Ago-2026
**Código analizado:** `research/04_conjuncion_multi_estacion/forense_precursores.py` (221 líneas)