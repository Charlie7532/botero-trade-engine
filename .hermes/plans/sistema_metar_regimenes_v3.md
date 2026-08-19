# SISTEMA METAR — Arquitectura de Regímenes por Categorías (Diseño v3)

> Estado: DISEÑO. La analogía meteorológica como principio organizador.
> Juan Andrés (piloto) + Hermes, 17-Ago-2026.

---

## 1. LA ANALOGÍA METEOROLÓGICA (el principio organizador)

```
CLIMA (estación del año)  →  CATEGORÍA 1: ECONOMÍA
  verano/invierno = la tendencia de fondo que nadie siente día a día
  pero que determina TODO lo que puede pasar
  CREDIT, YIELD, DXY, ROTATION-A

CONDICIONES (frente formándose) → CATEGORÍA 2: PROTECCIÓN/SENTIMIENTO
  el bochorno, la humedad ANTES de la lluvia
  VIX, VVIX, PCR, SKEW
  → se siente ANTES de que llueva (lead medio)

SENSACIÓN (la lluvia real)  →  CATEGORÍA 3: ACCIÓN/REALIDAD
  el agua cayendo, el viento soplando
  BSI (S5TW), SV5T, FG, ROTATION-B
  → es lo que YA está pasando (lead corto, confirmación)
```

**El orden (lead-time) = la cadena causal del clima:**
```
1. El clima establece la estación (economía)
2. Se siente el bochorno antes de llover (protección/sentimiento)
3. Recién después llueve (acción real)
```

---

## 2. LOS REGÍMENES = ESTADOS DEL TIEMPO

```
DESPEJADO (calma):       economía estable + sin protección + amplitud normal
BOCHORNO (pre-tormenta): economía deteriorándose + protección subiendo + amplitud AÚN no cae
  → "miedo sin venta" = sub-reacción = la lluvia AÚN no llegó
TORMENTA (crisis):       protección extrema + amplitud colapsando
  → "miedo con venta" = capitulación = está lloviendo YA
DESPEJANDO (piso):       amplitud colapsó + protección empieza a ceder
  → la lluvia YA pasó, sale el sol = comprar
VERANO ETERNO (euforia): economía fuerte + sin protección + amplitud en máximos
  → "calma con amplitud" = techo
```

**Los "momentos de verdad" = transiciones de estado:**
```
bochorno → tormenta   (la lluvia finalmente llega)
tormenta → despejando (la lluvia pasa)
despejado → bochorno  (se forma el próximo frente)
```

---

## 3. LA PREGUNTA DEL MILLÓN: ¿PUEDEN DETERMINAR REGÍMENES?

**SÍ — pero la pregunta correcta no es "¿puede una estación determinar el régimen?"**
**sino "¿pueden las 3 CATEGORÍAS juntas determinar el régimen?"**

```
Cada estación es un SENSOR. Una sola no determina el clima.
Pero el CONJUNTO de sensores de una categoría determina el ESTADO de esa categoría.
Y las 3 categorías juntas determinan el RÉGIMEN.

Economía:  ¿verano o invierno?
Sentimiento: ¿hay bochorno (humedad subiendo) o no?
Acción:    ¿está lloviendo YA o aún no?
```

---

## 4. ARQUITECTURA — 3 capas + expertos anidados + coordinator

```
┌──────────────────────────────────────────────────────────────┐
│              COORDINATOR (el meteorólogo)                    │
│  Lee las 3 categorías → determina el RÉGIMEN → detecta       │
│  MOMENTOS DE VERDAD (transiciones)                           │
└───────┬──────────────────┬──────────────────┬───────────────┘
        │                  │                  │
  ┌─────▼─────┐      ┌─────▼─────┐      ┌─────▼─────┐
  │ CAT 1     │      │ CAT 2     │      │ CAT 3     │
  │ ECONOMÍA  │      │ SENTIMIENT│      │ ACCIÓN    │
  │ "¿estación?"│    │ "¿bochorno?"│    │ "¿llueve?" │
  └─────┬─────┘      └─────┬─────┘      └─────┬─────┘
        │                  │                  │
   expertos:          expertos:          expertos:
   CREDIT             VIX                BSI (S5TW)
   YIELD              VVIX               SV5T
   DXY                PCR                FG
   ROTATION-A         SKEW               ROTATION-B
```

### 4.1 Expertos anidados (11 en total)
```
Cada experto es un AGENTE que entiende SU indicador a fondo:
- D1 (nivel), D2 (velocidad), D3 (volatilidad)
- La tríada de zigzag (zz25/zz50/zz75) y lo que expresa
- Su mecánica específica (ej. FG no tiene D2 flip, VIX sí)
- Cuándo SU indicador no está presente (FG pre-2011, SKEW gaps)

El experto reporta a SU category agent:
  "hoy, mi indicador dice: nivel X, velocidad Y, volatilidad Z,
   approaching extreme? → sí/no, confidence alta/media/baja"
```

### 4.2 Category agents (3 en total)
```
Cada category agent agrega sus expertos y decide EL ESTADO de la categoría:

CAT 1 (Economía):  "¿verano (saludable) o invierno (deteriorándose)?"
  → CREDIT stress + YIELD invertida + DXY subiendo + ROTATION-A saliendo

CAT 2 (Sentimiento): "¿hay bochorno (humedad subiendo) o no?"
  → VIX subiendo + PCR extremo + SKEW subiendo = bochorno
  → VIX bajo + PCR bajo = aire seco (complacencia)

CAT 3 (Acción):    "¿está lloviendo YA o aún no?"
  → S5 colapsó = está lloviendo (capitulación)
  → S5 mantiene = bochorno, aún no llueve (sub-reacción)
```

### 4.3 Coordinator (1)
```
Lee los 3 estados → RÉGIMEN completo:
  CAT1=invierno + CAT2=bochorno + CAT3=no llueve → PRE-TORMENTA (esperar)
  CAT1=invierno + CAT2=bochorno + CAT3=lloviendo → TORMENTA (piso cerca)
  CAT1=invierno + CAT2=cede + CAT3=llovió    → DESPEJANDO (comprar)
  CAT1=verano + CAT2=seco + CAT3=máximos    → EUFORIA (techo)

Detecta MOMENTOS DE VERDAD (transición de una categoría):
  "CAT2 pasó de seco → bochorno en 3 días" = el frente se está formando
```

---

## 5. BENCHMARK — anticipación vs falsa señal

### 5.1 Lo que hay que medir
```
Para CADA señal de cada experto:
  - ¿Cuántos días ANTICIPA el pivote? (lead medio + distribución)
  - ¿Cuántas veces es FALSA? (señaló y no pasó nada)
  - ¿Cuántas veces es TARDÍA? (llegó después del pivote)
  - ¿Cuál es el costo de anticiparse de más vs de menos?

BENCHMARK = la curva de anticipación vs falsa alarma
  - anticipar 5 días: ¿cuántas falsas alarmas?
  - anticipar 1 día: ¿cuántas falsas alarmas?
  - no anticipar (confirmar): ¿cuánto del movimiento se pierde?
```

### 5.2 El "bochorno falso" (el caso más difícil)
```
A veces hay bochorno (humedad sube) pero NO llueve (el frente pasa).
= sentimiento extremo SIN capitulación de amplitud.

Esto es EXACTAMENTE la falsa señal que hay que benchmarkear:
  - ¿Cuántos "bochornos" (VIX↑ + protección) NO terminan en lluvia (S5 colapso)?
  - ¿Qué distingue el bochorno que llueve del que no?
  - (pista: D2, D3, o la categoría 1 — ¿es verano o invierno?)
```

---

## 6. LAS PIEZAS SUELTAS (pendientes por engranar)

```
1. TAF (forecast) — pendiente de integrar (ev_per_day, ftt_days)
2. SIGMET (alertas severas) — pendiente de validar
3. Data huérfana (N<10) — Orphan Interpreter pendiente
4. Small-cap canary (IWM) — descubierto, no integrado
5. ROTATION dual — descubierto, no separado (A vs B)
6. PCR lado alcista (call heavy = techo) — identificado, no medido
7. Pre/post zigzag timing — identificado, no medido
8. Regímenes — clasificación inicial, no validada
9. Lead-lag entre categorías — hipótesis, no medida
```

**Todas estas piezas se engranan en la arquitectura de 3 categorías:**
- TAF → salida del coordinator (forecast del régimen)
- SIGMET → alertas del coordinator (tormenta severa)
- Huérfanas → el Orphan Interpreter dentro de cada category agent
- Small-cap canary → sensor adicional de CAT 3
- ROTATION dual → un sensor, dos categorías (PLA)

---

## 7. DIVIDIR PARA CONQUISTAR (sin romper lo engranado)

```
El riesgo: dividir en pedazos que rompan las conexiones.
La solución: dividir por CATEGORÍA (3 capas), no por estación (11 silos).

CADA CATEGORÍA es un pedazo independiente PERO autocontenido:
  - CAT 1 puede operar sola: "¿verano o invierno?"
  - CAT 2 puede operar sola: "¿bochorno o no?"
  - CAT 3 puede operar sola: "¿llueve o no?"

El coordinator las une SIN romperlas.
Las conexiones entre categorías son el REGIMEN (la foto completa).
```

---

## 8. ITERACIONES PROPUESTAS

```
ITERACIÓN 1 (prueba de concepto):
  1 category agent (CAT 2 — Sentimiento, el más estudiado: VIX+VVIX+PCR+SKEW)
  + 1 coordinator mínimo
  → ¿el category agent determina "bochorno vs seco"?
  → ¿el coordinator detecta la transición?

ITERACIÓN 2:
  + CAT 3 (Acción: BSI+SV5T+FG)
  → ¿coordinator detecta "bochorno→lluvia" (el momento de verdad)?

ITERACIÓN 3:
  + CAT 1 (Economía: CREDIT+YIELD+DXY+ROTATION)
  → régimen COMPLETO de 3 categorías

ITERACIÓN 4:
  + benchmark (anticipación vs falsa señal)
  + piezas sueltas (TAF, SIGMET, huérfanas, canary, ROTATION dual)
```

---

## 9. DECISIONES RESUELTAS (Juan Andrés, 17-Ago)

1. **Estados de categoría:** GRADUADOS (0-100%), usando las escalas Gaussianas
   existentes (PERCENTILES_D1_GAUSS). No binarios.
2. **Coordinator:** PROBABILÍSTICO (regla de oro: probabilidad + CI95 + N).
3. **Benchmark:** lead-days + % de movimiento perdido, en los 3 marcos de la
   tríada zigzag. La señal se estudia COMPLETA: se compara con cada cruce del
   zigzag (look-forward/back al cruce más cercano), se observa cuándo se dio la
   señal honesta (anticipada/en-pivote/retrasada) y se evalúa el ciclo completo.
4. **Expertos:** AGENTES separados, cada uno con su knowledge (D1/D2/D3/zigzag).
5. **Régimen = METAR (estado actual) + TAF (forecast) + SIGMET (advertencia).**
   SIGMET = el reporte que determina un CAMBIO SIGNIFICATIVO: tormenta o
   CORTANTE DE VIENTO (la transición abrupta de régimen).
6. **Data huérfana (N<10):** culminar la documentación de interpretación.
   Proporcionar nuestros hallazgos. Futuros agentes deben tener este contexto
   MUY claro — analizar con más detalle, nunca ignorar.

## 10. NOTAS ADICIONALES (Hermes)

### 10.1 SIGMET = "cortante de viento" (wind shear)
```
En aviación, la cortante de viento es el cambio ABRUPTO de dirección/velocidad
del viento — el peligro más súbito. En el mercado:
  = la transición abrupta de régimen (el "momento de verdad" violento)
  = D2 flip + D3 expansión simultáneos en la categoría 2 (protección)
  → SIGMET no es solo "alerta de tormenta" — es la detección de la CORTANTE:
    el instante en que el bochorno se vuelve lluvia de golpe.
```

### 10.2 Las escalas Gaussianas ya codifican probabilidad
```
PERCENTILES_D1_GAUSS = [0.0228, 0.1587, 0.50, 0.8413, 0.9772]
  = los cuantiles de la normal (P2.3, P15.9, P50, P84.1, P97.7)
  = 2σ, 1σ, media, +1σ, +2σ

Esto significa que los estados GRADUADOS (0-100%) se mapean naturalmente a
probabilidades gaussianas — el bin P97.7 es "evento del 2.3%", el P2.3 es
"evento del 2.3% opuesto". La graduación YA es probabilística.
```

### 10.3 Principio del equipo (para grabar en memoria)
```
"Nadie es portador de la verdad absoluta" — el dato manda, no la autoridad.
Los hallazgos se corrigen con datos, no se defienden por orgullo.
Sistema abierto a revisión, revertir cuando los datos contradicen.
```

## 11. ITERACIONES (actualizado)

```
ITERACIÓN 1 (prueba de concepto):
  1 category agent (CAT 2 — Sentimiento: VIX+VVIX+PCR+SKEW)
  + 1 coordinator mínimo (METAR + TAF + SIGMET)
  → ¿determina "bochorno vs seco" graduado?
  → ¿detecta la cortante de viento (transición)?

ITERACIÓN 2:
  + CAT 3 (Acción: BSI+SV5T+FG)
  → ¿detecta "bochorno→lluvia" (el momento de verdad)?

ITERACIÓN 3:
  + CAT 1 (Economía: CREDIT+YIELD+DXY+ROTATION)
  → régimen COMPLETO de 3 categorías

ITERACIÓN 4:
  + benchmark (anticipación vs falsa señal, ciclo completo de señal)
  + piezas sueltas (TAF fields, SIGMET validation, huérfanas, canary, ROTATION dual)
```
