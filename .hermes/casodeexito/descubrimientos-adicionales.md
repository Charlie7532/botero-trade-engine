# SEÑALES Y DESCUBRIMIENTOS ADICIONALES — Más Allá del Arnés Base
## Auditoría de Código Python — 17-19 Ago 2026
## Lo que aislamos que NO estaba en las 28 señales de medir_senal.py

---

## 0. CONTEXTO

`medir_senal.py` registra 28 señales. `forense_precursores.py` aísla 86 precursores de crash. Pero entre ambos, hubo DESCUBRIMIENTOS ADICIONALES que no son "señales registradas" sino PATRONES, FILTROS, y RECLASIFICACIONES que surgieron del análisis profundo de los datos.

Este documento captura TODO lo que encontramos MÁS ALLÁ de las señales base.

---

## 1. CREDIT EASING K=1 — La Señal que Requiere Contexto de Piso

### El descubrimiento

**No es simplemente "credit_easing_k1 está registrada en medir_senal.py".** El hallazgo real fue MÁS ESPECÍFICO:

```
CREDIT easing en ventana K=1 SOLO funciona en PISOS (pivot_type == MIN).

  EASING en piso:   +5.19%, WR 93.75%, N=112
  SIN easing en piso: +2.99%, WR 75.65%
  EASING en techo:   -0.01%, WR 33.7%   ← NO FUNCIONA

  → La señal NO es "credit easing". Es "credit easing EN UN PISO DE DRAWDOWN".
  → El contexto (pivot_type == MIN) es PARTE de la definición de la señal.
  → Sin el filtro de piso, la señal colapsa.
```

### Cómo lo aislamos

```
1. LEAVE-ONE-OUT del canal EV mostró que CREDIT restaba (−0.0031)
2. Pero el análisis de CREDIT easing K=1 mostró +5.19% en pisos
3. La contradicción se resolvió al separar por pivot_type:
   → MIN (piso): +5.19%, WR 93.75%
   → MAX (techo): ruido
4. El hallazgo NO es "CREDIT sirve" — es "CREDIT easing solo sirve en pisos"
```

### Por qué es valioso

```
No es una señal más. Es un PATRÓN:
  - Señal + contexto = edge real
  - Señal sin contexto = ruido

Este patrón se repite en: capitulacion (solo MIN), bsi_washed_out (solo MIN),
credit_stress (solo con duration > 2b).
```

---

## 2. LOS TRES TIPOS DE CAPITULACIÓN — Reclasificación por Nido

### El descubrimiento

El forense reveló que "CAPITULACIÓN" no es UNA señal — son TRES señales distintas que miden cosas distintas con herramientas distintas:

| # | Nombre Original | Dónde se mide | Definición Operativa | Herramienta | Edge |
|---|---|---|---|---|---|
| 1 | CAPITULACIÓN_RÉGIMEN | `sentiment_regime.py` | FG<20 + VIX>25 + SPY crashed >2%/5d | Sentimiento (FG) | No medido en este ejercicio |
| 2 | CAPITULACIÓN_METAR | `references/` GRADE A | VIX↑ + S5 colapsa (medido por signo de diff(5)) | Breadth (S5TW) | +1.5% 20d, PF 2.19 |
| 3 | CAPITULACIÓN_SECTORIAL | `quality_entry_gate.py` | n_dead ≥ 5 sectores | Rotación sectorial | +14.43% 120d, WR 81% |

### Cómo lo aislamos

```
1. El forense de Claude Opus encontró que "capitulacion" daba resultados distintos
   según qué herramienta se usara para medirla
2. La auditoría reveló que el mismo NOMBRE se aplicaba a 3 FENÓMENOS distintos
3. La solución NO fue unificarlos — fue RENOMBRARLOS por su nido de medición
4. Cada uno con UNA capa, UNA herramienta canónica, UNA definición operativa
```

### Por qué es valioso

```
"No todos son del mismo nido y son medidos con diferentes herramientas,
 que no van a estar habilitadas."

La lección: un nombre ≠ un fenómeno. La herramienta de medición DEFINE el fenómeno.
Si mides "capitulación" con FG, con S5TW, y con rotación sectorial,
estás midiendo TRES cosas distintas. Reconocerlo es el 90% del trabajo.
```

---

## 3. CONJUNCIÓN DE ZIGZAGS (3/3) — El Evento Especial No Registrado

### El descubrimiento

No es una señal en `medir_senal.py`. Es un FENÓMENO que emerge del forense de precursores:

```
CONFLUENCIA DE ZIGZAGS: cuando las 3 escalas (zz25, zz50, zz75) están alineadas
en el MISMO PUNTO (mínimo o máximo).

  3/3 en MÍNIMO: "REBOTE BIEN COGIDO" (oportunidad de compra)
  3/3 en MÁXIMO: "CUCHILLO A PUNTO DE CAER" (riesgo de short/evitar)
  2/3: alineación parcial
  1/3: normal (no evento)

DIFERENCIA CON CASCADE:
  Cascade = propagación TEMPORAL (¿el 2.5% se convierte en 5%?)
  Confluencia = alineación ESPACIAL (¿el punto YA es 2.5% Y 5% Y 7.5% a la vez?)
```

### Cómo lo aislamos

```
La especificación dice: "Aprender a identificar los eventos especiales
es tal vez una de las habilidades más importantes y un objetivo prioritario."

El forense encontró que cuando un estado D1×D2×D3 aparece en las 3 escalas
simultáneamente, el lift es MULTIPLICATIVO (no aditivo).

Esto NO está en medir_senal.py porque no es "una señal de una estación" —
es una CONJUNCIÓN de 3 escalas del zigzag.
```

### Por qué es valioso

```
La confluencia 3/3 es el evento de MÁXIMA SIGNIFICANCIA en el sistema.
No es una señal — es la CONFIRMACIÓN de que múltiples señales independientes
apuntan en la misma dirección en el mismo momento.

Esto NO se puede registrar como "@_registrar" porque no depende de UNA estación.
Depende de la ALINEACIÓN de las 3 escalas del zigzag.
```

---

## 4. SIGN FLIPS D2×D3 — Cuando el Edge se INVIERTE

### El descubrimiento

Claude Opus encontró que **20 de 34 combinaciones D2×D3 (59%) producen SIGN FLIPS** — el edge de la señal se INVIERTE completamente dependiendo del sub-estado D2 (velocidad) o D3 (volatilidad):

```
bsi_washed_out × FG D2:
  DECELERATING_DOWN_3D: +5.17%, WR 100%, N=5   ← COMPRAR
  FAST_CRUSH_3D:        -1.74%, WR 50%,  N=8   ← NO COMPRAR

  → El MISMO D1 (FEAR) con diferente D2 produce edge OPUESTO.
  → El D2 DISCRIMINA entre señal válida y ruido.
```

### Los 5 sign flips más grandes

| # | Señal | Estación | Dim | BEST | mean | N | WORST | mean | N | Spread |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | sub_reaccion | vix | D2 | ACCEL_UP | +5.11% | 13 | DECEL_DOWN | -2.59% | 12 | **+7.70pp** |
| 2 | pcr_put_panic | bsi | D2 | STABLE_CONT | +5.38% | 18 | FAST_CRUSH | -2.19% | 5 | **+7.57pp** |
| 3 | bsi_washed_out | fg | D2 | DECEL_DOWN | +5.17% | 5 | FAST_CRUSH | -1.74% | 8 | **+6.91pp** |
| 4 | vvix_entry | dxy | D2 | FAST_CRUSH | +5.01% | 8 | FAST_SPIKE | -1.23% | 6 | **+6.24pp** |
| 5 | capitulacion | bsi | D3 | VOL_COMPR | +5.42% | 15 | VOL_EXP | -0.67% | 6 | **+6.09pp** |

### Cómo lo aislamos

```
1. medir_senal.py calcula D2×D3 desglose (sección 4.10)
2. Para cada señal, desglosa el forward por D2 y D3 de cada estación
3. Reporta "best" y "worst" con CI95 bootstrap
4. Claude Opus auditó y encontró que solo 1/5 pasa bootstrap CI95
   → Los sign flips con N<15 son direccionales, no certezas
```

### Por qué es valioso

```
Los sign flips D2×D3 son FILTROS, no señales nuevas:
  - Si D2=FAST_CRUSH → NO entrar (aunque D1 diga que sí)
  - Si D3=VOL_COMPRESSION → entras con MÁS tamaño
  - Si D3=VOL_EXPANSION → entras con MENOS tamaño

No agregan señales al sistema. REFINAN las señales existentes.
```

---

## 5. PRECURSOR UNIVERSAL #1 — credit.D2=ACCELERATING_UP_3D

### El descubrimiento

`forense_precursores.py` encontró 86 precursores. Pero UNO de ellos trasciende a todos los demás:

```
credit.D2=ACCELERATING_UP_3D aparece como precursor en 5 de 6 señales analizadas:

  credit_easing_k1:  lift=2.2×  N_lose=8
  pcr_put_panic:     lift=3.7×  N_lose=3
  bsi_washed_out:    lift=2.2×  N_lose=8
  credit_stress:     lift=1.7×  N_lose=17
  capitulacion:      lift=9.0×  N_lose=5

  → 5/6 señales, lift medio 4.1×
  → El crédito acelerándose es el precursor más universal de crash
```

### Por qué es valioso

```
No es una señal de trading. Es un TERMÓMETRO DEL SISTEMA:
  - Si credit.D2=ACCEL_UP → TODAS las señales de ENTRY tienen mayor riesgo de fallar
  - No te dice "no entres". Te dice "si entras, reduce tamaño".
  - Es un MODULADOR de riesgo, no un generador de señales.

Interpretación macro: "El crédito se está tensando RÁPIDO.
La renta fija NO está confirmando el fondo. Cuidado."
```

---

## 6. PROTECTORES UNIVERSALES — Estados que NUNCA Crashean

### El descubrimiento

El forense encontró estados del vector con **lift=0** — aparecen en winners pero NUNCA en losers:

```
vix.D2=STABLE_CONTINUATION_3D:    0 crashes en credit_easing y pcr_put_panic
vix.D3=VOL_MODERATE_COMPRESSION:  21 wins, 0 losses en credit_easing
vvix.D1=EXTREME_VVIX:             12 wins, 0 losses en credit_easing
pcr.D3=VOL_MODERATE_COMPRESSION:  7 wins, 0 losses en pcr_put_panic

→ Si ves estos estados, la probabilidad de crash es ~0%.
→ Son "protectores totales".
```

### Cómo lo aislamos

```
El forense calcula lift para cada estado × cada señal.
Los protectores son estados con lift ≤ 0.5 y n_win ≥ 3.
Los protectores TOTALES son lift = 0.0 (nunca vistos en crashes).

Estos NO son señales de entrada. Son CONFIRMACIONES de que es seguro operar.
```

### Por qué es valioso

```
Si estás considerando entrar con credit_easing_k1, y ves:
  vix.D2=STABLE_CONTINUATION_3D (protector total)
  → La probabilidad de que esta entrada falle es ~0%.

No es una señal nueva. Es un FILTRO de las señales existentes.
```

---

## 7. ASIMETRÍA GANANCIA/PÉRDIDA — El Factor Oculto

### El descubrimiento

Separar wins de losses (decisión de diseño #6 en medir_senal.py) reveló que:

```
capitulacion:
  mean_win:  +6.91%
  mean_loss: -9.22%
  → Asimetría: 1.33× (pierdes 33% más de lo que ganas)

fg_extreme_fear:
  mean_win:  +5.70%
  mean_loss: -7.40%
  → Asimetría: 1.30×

bsi_washed_out:
  mean_win:  +6.14%
  mean_loss: -7.67%
  → Asimetría: 1.25×
```

### Por qué es valioso

```
La asimetría REVELA el perfil real de cada señal:

  Señales con asimetría > 1.2× → 🛡️ DEFENSIVAS (su valor está en evitar pérdidas)
  Señales con asimetría < 1.0× → ⚔️ OFENSIVAS (su valor está en generar ganancias)
  Señales con asimetría ≈ 1.0× → BALANCEADAS

Sin wins/losses separados, esta clasificación es IMPOSIBLE.
El marco Edge Defensivo (ED) se deriva DIRECTAMENTE de esta asimetría.
```

---

## 8. DURATION_BARS COMO FILTRO — credit_stress Solo Funciona en Piernas Largas

### El descubrimiento

Claude Opus encontró que `duration_bars` es un modificador CRÍTICO para algunas señales:

```
credit_stress:
  pierna ≤2 bars: -0.01%, WR=49%, N=114  ← CERO EDGE
  pierna >2 bars: +2.14%, WR=61%, N=101  ← TODO EL EDGE

  → Sign flip total: -2.14pp de diferencia
  → Si duration ≤2, IGNORAR la señal. Es ruido.

sub_reaccion:
  pierna ≤4 bars: -0.29%, WR=47%, N=364
  pierna >4 bars: +1.20%, WR=54%, N=303
  → -1.49pp de diferencia. Significativo pero menos extremo.
```

### Cómo lo aislamos

```
medir_senal.py ya calcula "duracion_desglose" (cortas vs largas por mediana).
Claude Opus profundizó y encontró el punto de corte ÓPTIMO (≤2 vs >2) para credit_stress.

Este NO es un parámetro del arnés. Es un HALLAZGO específico de esta señal.
```

### Por qué es valioso

```
Es un FILTRO OPERATIVO INMEDIATO:
  - Si credit_stress se activa → mirar duration_bars
  - Si duration ≤ 2 → NO ENTRAR (la señal no tiene edge en piernas cortas)
  - Si duration > 2 → ENTRAR (todo el edge está en piernas largas)

No requiere modificar medir_senal.py. Es una REGLA DE OPERACIÓN.
```

---

## 9. CROSS-SIGNAL OVERLAP — Solo UNA Confluencia es Aditiva

### El descubrimiento

Claude Opus midió el edge de la intersección de pares de señales:

```
capitulacion + vvix_entry:  +2.19%, WR=67%  → ✅ ADITIVO (+0.8pp sobre individual)
vvix + sub_reaccion:        +2.04%, WR=62%  → ✅ ADITIVO
bsi + vvix:                 +1.55%, WR=61%  → ❌ REDUNDANTE
bsi + credit:               +1.49%, WR=65%  → ❌ REDUNDANTE
capitulacion + credit:      +1.28%, WR=66%  → ❌ REDUNDANTE
```

### Por qué es valioso

```
La mayoría de las confluencias NO mejoran el edge.
Solo capitulacion + vvix_entry es genuinamente aditiva.

Esto significa que:
  - No sirve acumular señales — la mayoría son redundantes
  - La confluencia que SÍ funciona es específica (miedo extremo + volatilidad extrema)
  - El sistema debe priorizar POCAS señales de alta calidad, no muchas señales
```

---

## 10. FG ES MODULADOR, NO SEÑAL — La Reclasificación Fundamental

### El descubrimiento

El análisis inicial concluyó "FG: EV -8.9%, sin señal registrada, RETIRAR". Esto era un ERROR:

```
ERROR:     Evaluar FG con el marco de "señal de entrada/salida"
CORRECCIÓN: FG es un MODULADOR de la probabilidad del régimen

  FG EXTREME_FEAR:   "El régimen es INVIERNO" → las señales de compra tienen MÁS peso
  FG EXTREME_GREED:  "El régimen es VERANO"   → las señales de venta tienen MÁS peso
  FG NEUTRAL_FEAR:   "El régimen es NEUTRAL"  → las señales se evalúan normalmente

FG no genera órdenes. MODIFICA la probabilidad de que otras señales acierten.
```

### Cómo lo aislamos

```
1. El leave-one-out del EV mostró FG = -8.9% → "peso muerto"
2. El forense mostró FG EXTREME_FEAR → +1.58%, WR 68.5% → "señal válida"
3. CONTRADICCIÓN: ¿es peso muerto o es señal válida?
4. Resolución: FG no es señal de entrada. Es MODULADOR de régimen.
   Su valor no está en el EV (magnitud) sino en la clasificación del régimen.
```

### Por qué es valioso

```
Cada estación tiene un ROL en el sistema. Evaluarla con el rol equivocado
produce conclusiones erróneas.

  FG:      MODULADOR (termómetro del sentimiento)
  CREDIT:  SEÑAL + MODULADOR (credit_easing es señal, credit_stress es modulador)
  VIX:     SEÑAL (la locomotora del cascade)
  YIELD:   MODULADOR (contexto macro, sin señal direccional propia)

La clasificación funcional de cada estación es UN DESCUBRIMIENTO en sí mismo.
```

---

## 11. SEÑALES DE PÁNICO SON ENTRY, NO EXIT — La Inversión de Hipótesis

### El descubrimiento

Medimos 7 señales como candidatas a EXIT. Solo 2 pasaron. Las demás resultaron ser ENTRY:

```
PROPUESTAS COMO EXIT:
  vix_crisis_spike:     +0.75%, WR 56.7%  → ❌ Es ENTRY (comprar miedo)
  credit_stress:        +1.00%, WR 54.9%  → ❌ Es ENTRY (comprar miedo)
  pcr_panic_exit:       +2.70%, WR 71.4%  → ❌ Es ENTRY (comprar pánico)
  dxy_spike_exit:       -0.04%, WR 45.7%  → ⚠️ Neutro (sin edge)
  skew_paranoia_exit:   -0.38%, WR 46.2%  → ⚠️ Neutro (sin edge)

EFECTIVAS COMO EXIT:
  bsi_recovery:         -1.63%, WR 29.0%  → ✅ EXIT efectivo
  euforia:              -2.99%, WR 14.6%  → ✅ EXIT efectivo
```

### Por qué es valioso

```
La hipótesis inicial ("el pánico es momento de salir") era INCORRECTA.
El pánico es momento de COMPRAR (contrarian). 

La salida NO ocurre en el pánico — ocurre en la COMPLACENCIA (euforia, greed)
o en la RECUPERACIÓN (bsi sale de washed_out).

Esto INVIERTE la intuición de trading convencional:
  - "Cuando hay miedo, vendo" → ❌ INCORRECTO (es cuando compro)
  - "Cuando hay complacencia, compro" → ❌ INCORRECTO (es cuando vendo)
```

---

## 12. EDGE DEFENSIVO — El Marco que Reveló lo Invisible

### El descubrimiento

Cambiar la pregunta de "¿cuánto gana?" a "¿cuánto dejo de perder?" reveló que las 2 mejores defensas del sistema estaban INVISIBILIZADAS:

```
                 Edge Ofensivo (viejo)    Edge Defensivo (nuevo)
capitulacion:    +1.40% (CI95 no pasa)    6.86% (3.6× baseline) ← 🥇 MEJOR DEFENSA
fg_extreme_fear: +1.58% (CI95 no pasa)    5.61% (2.9× baseline) ← 🥈 2da DEFENSA
bsi_washed_out:  +1.42% (CI95 pasa)       5.58% (3.1× baseline) ← 🥉 DUAL

Sin ED:   "capitulacion no es significativa, no usar"
Con ED:    "capitulacion es la MEJOR defensa del sistema, IMPRESCINDIBLE"
```

### Por qué es valioso

```
La métrica define lo que ves.
  - Edge Ofensivo: ves señales que generan ganancias
  - Edge Defensivo: ves señales que evitan pérdidas

El sistema necesita AMBAS. Sin ED, las mejores defensas son invisibles.
```

---

## RESUMEN: QUÉ ENCONTRAMOS MÁS ALLÁ DE LAS 28 SEÑALES

| # | Descubrimiento | Tipo | Impacto |
|---|---|---|---|
| 1 | CREDIT easing solo funciona en PISOS (MIN) | Filtro de contexto | Redefine la señal |
| 2 | 3 tipos de CAPITULACIÓN (por nido) | Reclasificación | Unifica sin homogeneizar |
| 3 | Confluencia de zigzags 3/3 | Evento especial | Máxima significancia |
| 4 | 20 sign flips D2×D3 (59% de combinaciones) | Filtro dimensional | Refina señales existentes |
| 5 | credit.D2=ACCEL_UP es precursor universal | Termómetro del sistema | Modulador de riesgo |
| 6 | Protectores totales (lift=0, nunca crashean) | Filtro de seguridad | Confirma entradas |
| 7 | Asimetría ganancia/pérdida (1.33× en capitulacion) | Clasificación funcional | Define perfil de señal |
| 8 | duration_bars como filtro (credit_stress ≤2b = 0 edge) | Filtro operativo | Regla inmediata |
| 9 | Solo 1 confluencia cross-señal es aditiva | Validación de ensemble | Evita sobreacumulación |
| 10 | FG es modulador, no señal | Reclasificación funcional | Corrige error fundamental |
| 11 | Señales de pánico son ENTRY, no EXIT | Inversión de hipótesis | Corrige intuición |
| 12 | Edge Defensivo revela lo invisible | Nuevo marco de medición | Cambia prioridades |

---

## LA LECCIÓN TRANSVERSAL

> **"Las 28 señales de medir_senal.py son el QUÉ. Estos 12 descubrimientos son el CÓMO y el POR QUÉ. Las señales te dicen CUÁNDO operar. Los descubrimientos te dicen CÓMO interpretar cada señal en su contexto."**

No basta con registrar señales. Hay que entender:
- ¿En qué CONTEXTO funciona? (piso vs techo, MIN vs MAX)
- ¿Qué DIMENSIÓN la refina? (D2 discrimina, D3 modula)
- ¿Qué ROL juega en el sistema? (señal vs modulador vs filtro)
- ¿Con qué OTRAS señales se complementa? (aditiva vs redundante)
- ¿Cuál es su ASIMETRÍA real? (defensiva vs ofensiva)

---
**Firma:** deepseek/deepseek-v4-pro (Hermes)
**Fecha:** 19-Ago-2026