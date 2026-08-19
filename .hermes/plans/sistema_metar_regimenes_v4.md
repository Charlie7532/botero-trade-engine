# SISTEMA METAR — Diseño v4 (multi-escala, día a día, sin look-ahead)

> Estado: DISEÑO. Incorpora: eventos especiales (cisnes/trampas), benchmark
> sin look-ahead, calificadores multi-escala, operación día a día.
> Juan Andrés + Hermes, 17-Ago-2026.

## 0. EL CONCEPTO CENTRAL (17-Ago, avance clave)

**El régimen NO se define por etiqueta (bull/bear) sino por CAUSA: la SECUENCIA
de activación de las categorías.**

```
DETERMINACIÓN DEL RÉGIMEN (orden fijo):
  1. CAT 1 (economía) = ¿expansión o contracción?  ← SIEMPRE primero (fundamento)
  2. La SECUENCIA de activación de CAT 2 y CAT 3 = la firma del régimen

LAS PERMUTACIONES = REGÍMENES DISTINTOS:
  CAT1→CAT2→CAT3 = macro-driven gradual
  CAT1→CAT3→CAT2 = acción se adelanta al sentimiento
  CAT2→CAT1→CAT3 = protección lidera (pánico anticipado)
  CAT2→CAT3→CAT1 = protección→acción→economía confirma
  CAT3→CAT1→CAT2 = acción lidera (violento)
  CAT3→CAT2→CAT1 = acción→sentimiento→economía

DOS TIPOS DE CAMBIO:
  TRANSICIÓN = cambio GRADUAL de secuencia (el árbol cambia de rama)
  EVENTO     = disrupción ABRUPTA (cisne negro salta ramas sin pasar intermedias)

La SECUENCIA es la huella digital del régimen. Dos regímenes pueden parecer
iguales (ambos bajan) pero son DISTINTOS si en uno lideró la economía y en
otro la acción.
```

---

## 1. OPERACIÓN DÍA A DÍA (sin look-ahead)

```
El BENCHMARK corre día a día, observando cómo se construye el clima
ENTRE los zigzags, SIN conocer el zigzag futuro.

REGLA DE SEPARACIÓN (crítica):
  - BENCHMARK:     solo conoce datos hasta el día T (sin futuro)
  - CALIFICADORES: SÍ usan el zigzag para clasificar la señal
                   como ANTICIPADA / EN_PIVOTE / RETRASADA

El benchmark dice "qué habría sabido yo en T".
Los calificadores dicen "qué pasó después" (para medir el timing).
```

## 2. MULTI-ESCALA — el problema de la TRAMPA

```
Los zigzags son ANIDADOS. Un zz25 (2.5%) vive DENTRO de un zz50 (5%),
que vive DENTRO de un zz75 (7.5%).

TRAMPA:  entramos en un zz25 (rebote táctico 2.5%)
         PERO estamos dentro de un "cuchillo cayendo" de zz75 (tendencia 7.5% abajo)
         → el rebote de 2.5% es una TRAMPA, la tendencia mayor sigue cayendo

Los retornos se miden DESDE/HASTA el zigzag del nivel MÁS PRÓXIMO:
  zz25 → 2.5%, zz50 → 5%, zz75 → 7.5%
  y se CONTEXTUALIZAN: ¿este zz25 está dentro de qué zz50/zz75?
```

## 3. EVENTOS ESPECIALES DEL MERCADO

```
CISNES NEGROS:  raros, extremos, IMPREDECIBLES (2008 Lehman, 2020 COVID)
  → el sistema NO puede predecirlos, pero DEBE detectarlos rápido
    cuando ocurren (SIGMET inmediato)

CISNES BLANCOS:  raros pero PREVISIBLES — la caída fue FLAGGEADA antes
  → el objetivo: ¿podemos detectar los cisnes blancos con anticipación?
    (el "bochorno" extremo que SÍ terminó en tormenta)

TRAMPAS:         señales FALSAS — un rebote táctico dentro de una tendencia mayor
  → bull trap (rebote 2.5% dentro de tendencia 7.5% bajista)
  → bear trap (caída 2.5% dentro de tendencia 7.5% alcista)
  → la clave: el CONTEXTO multi-escala (¿qué escala mayor rodea este zz25?)
```

## 4. ESTACIONES DETERMINANTES DEL CAMBIO DE RÉGIMEN

```
Pendiente: re-determinar QUÉ estaciones detectan con ANTICIPACIÓN
el cambio de un régimen a otro (lead-lag empírico, NO asumido).

Hipótesis a medir (no suponer):
  - CAT 1 (economía) lidera los cisnes blancos (deterioro gradual)
  - CAT 2 (sentimiento) lidera los pánicos (protección súbita)
  - CAT 3 (acción) puede ADELANTARSE (noticia anticipada)

El mapa de lead-lag se construye evento por evento:
  "en 2008, CREDIT emitió SIGMET 40 días antes que VIX"
  "en 2020, S5 colapsó el mismo día que VIX (sin lead)"
```

## 5. LOS 3 REPORTES (roles definitivos)

```
METAR = condición ACTUAL de cada estación, escala + PALABRA validada
  (extremos ALTOS y BAJOS + estado NORMAL de continuación)

TAF = predicción con esperanza matemática + probabilidades
  → CONO DE DISPERSIÓN (P10-P90, multi-escala zz25/zz50/zz75)

SIGMET = SOLO significancias (tormenta, cortante de viento)
  → el bus común donde cualquier categoría emite su advertencia
```

## 6. SIMETRÍA DE EXTREMOS

```
Extremo ALTO = tormenta (miedo): VIX↑, PCR↑, SKEW↑ → comprar miedo (validado)
Extremo BAJO = complacencia: VIX↓, PCR↓, SKEW↓ → peligro latente (por medir)
Normal       = tendencia continúa sin alteración (cascade)

Ambos extremos + el normal = los 3 estados de cada dimensión.
```

## 7. PENDIENTES CONSOLIDADOS

```
1. Extremo BAJO (complacencia) — subestudiado, medir simétrico al miedo
2. Estaciones determinantes del cambio de régimen — lead-lag empírico
3. Eventos especiales: cisnes negros, blancos, trampas
4. Multi-escala nesting — el contexto de la trampa (zz25 dentro de zz75)
5. Benchmark sin look-ahead + calificadores con zigzag (separación)
6. Cono de dispersión completo (P10-P90)
7. Data huérfana (N<10) — documentación de interpretación
8. TAF fields (ev_per_day, ftt_days) — integrar
9. Small-cap canary (IWM) — integrar a CAT 3
10. ROTATION dual (A/B) — separar
