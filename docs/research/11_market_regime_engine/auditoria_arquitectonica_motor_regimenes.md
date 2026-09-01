# Auditoría Arquitectónica — Motor de Regímenes de Mercado

**Fecha:** 31-Ago-2026  
**Objeto:** Auditar la propuesta de `MarketRegimeEngine` (Flash, 30-Ago-2026), debatirla contra la evidencia empírica acumulada, y proponer ejercicios probatorios antes de implementar.

---

## Parte 1 — Lo que Sabemos Empíricamente (Dato Mata Opinión)

Antes de diseñar nada, inventariemos qué está **PROBADO** y qué es **NARRATIVA**.

### ✅ PROBADO (Evidencia OOS, Walk-Forward, Significancia Estadística)

| Hallazgo | Evidencia | Fuente |
|:---|:---|:---|
| `cascade_reversal` detecta agotamiento en ALZA a escala táctica | 9/9 folds OOS, p_bonf=0.004, +1.40%, zz25\|ALZA | validador_oos v2 |
| `credit_stress` marca pisos macro en escala estructural | 3/3 folds OOS, +4.96%, zz75\|ALZA | validador_oos v2 |
| `breadth_contraction_exit` marca salidas estructurales | 6/9 folds OOS, +1.62%, zz75\|ALZA | validador_oos v2 |
| Secuencia CAT1→CAT2→CAT3 ("Macro-Driven") predice caídas | OOS mean=-1.77% a 20d, 0% folds+, Kelly=-0.42 | validate_regimes_oos |
| Secuencia CAT1→CAT3→CAT2 ("Cuchillo Cayendo") — peor escenario | OOS mean=-5.20% a 20d, 0% folds+, N=30 | validate_regimes_oos |
| S5_FI >70% coincide con techos ZZ en 77% de casos | 2,652 turns, 11 sectores, 5 años | KI zz-s5-breadth |
| S5_FI <22% coincide con pisos ZZ | Spread de 46pp entre MAX y MIN | KI zz-s5-breadth |
| σ-Overflows T3+ (≥5σ) se concentran en crisis sistémicas | ~120 eventos en 33 años, clusters de 5-15 días | overflow_taxonomy |
| 10 Regímenes S5/SV5 con allocation backtesteada 27.5 años | V26: 381.98 vs 100 acciones SPY B&H | sector-rotation-gate |
| Cada escala ZZ es independiente (fractalidad confirmada) | Señales operan en escalas distintas (zz25 vs zz75) | validador_oos multi-celda |

### ⚠️ HIPÓTESIS (Plausible pero sin validación OOS formal)

| Hipótesis | Estado | Gap |
|:---|:---|:---|
| Los 5 regímenes propuestos por Flash son los correctos | NARRATIVA | Boundaries no medidos, no hay clustering empírico |
| Las 4 dimensiones del vector son ortogonales | PARCIAL | VIX aparece en V (Hazard) y M (Macro vía crédito). Credit aparece en M y en la señal `credit_stress` |
| El compositor de convergencia (6D MHI) tiene poder predictivo | HIPÓTESIS | G1-G6 tienen `Evidence Status: HYPOTHESIS` excepto G5 (Pring) y G6 (Yield) |
| Post Blow-Off T4+ = ventana de acumulación | HIPÓTESIS | Mencionado en overflow_taxonomy §7.3, sin test walk-forward |
| cascade_conviction < -0.957 marca agotamiento universal | PARCIAL | cascade_reversal está validada OOS, pero el umbral -0.957 es IS |

---

## Parte 2 — Las 6 Debilidades Estructurales de la Propuesta de Flash

### Debilidad 1: Los 5 Regímenes Son Narrativa, No Datos

Flash propuso: EXPANSION_BULL, OVERHEATED_EXHAUSTION, MACRO_DE_RISKING, CRISIS_WASHOUT, ACCUMULATION_SPRING.

**Problema:** Estos nombres son intuitivamente razonables pero **las fronteras entre ellos no están definidas empíricamente**. ¿En qué valor exacto de S5_FI transitas de EXPANSION a OVERHEATED? ¿Es 65%? ¿70%? ¿75%? Sin datos, son etiquetas arbitrarias.

**Contraste con lo que SÍ funciona:** El `sector-rotation-gate` tiene **10 regímenes con fronteras numéricas explícitas** (TH<30 AND FI<25 = CRASH, TH>60 AND FI>50 = SANO), validados en 27.5 años con contribución medida en acciones equivalentes.

> [!WARNING]
> **Imponer 5 regímenes sin dejar que los datos hablen primero es el error clásico de HARKing** (Hypothesizing After Results are Known). Debemos descubrir primero cuántos regímenes naturales existen.

### Debilidad 2: Circularidad Dimensional

El vector $\langle T, B, V, M \rangle$ tiene dependencias circulares:
- **T** (Cinemática) incluye cascade_conviction, que se calcula DESDE las estaciones METAR.
- **V** (Hazard) incluye VIX, que correlaciona $\rho=-0.61$ con Credit (dimensión **M**).
- **B** (Breadth) alimenta BSI, que es una estación METAR que a su vez alimenta el cascade.

Las 4 dimensiones no son independientes. Esto no las invalida, pero hace que el producto cartesiano $T \times B \times V \times M$ tenga muchos estados teóricos vacíos (combinaciones imposibles en la práctica).

### Debilidad 3: La Secuencia CAT1→CAT2→CAT3 Es Mayoritariamente RUIDO

De las 5 secuencias probadas en `validate_regimes_oos_REPORT.md`:
- **CAT1→CAT2→CAT3** (Macro-Driven): OP-SHORT confirmada — **pero predice CAÍDAS, no es un régimen de compra.**
- **CAT1→CAT3→CAT2** (Cuchillo): OP-SHORT extrema (N=30, -5.20% a 20d) — **señal de venta/cobertura.**
- **CAT2→CAT3→CAT1** (Comprar Miedo): **RUIDO** en todas las escalas excepto 40d en zz50.
- **CAT2→CAT1→CAT3** y **CAT3-lidera**: **INSUF** o **RUIDO** en casi todo.

Flash presentó las secuencias como "estructura de transición anticipable" pero los datos muestran que **solo las secuencias que empiezan con CAT1 (macro) tienen señal, y esa señal es OP-SHORT** (el mercado cae). Las secuencias "de compra" son ruido.

### Debilidad 4: Fractalidad Sin Resolver

Flash reconoce que zz25 puede ser ALZA mientras zz75 es BAJA, pero su tabla de 5 regímenes usa un solo $T$ (dirección). ¿Cuál dirección? ¿La de zz25? ¿La de zz75?

**Lo que sabemos:** cascade_reversal opera en zz25 (táctica), credit_stress en zz75 (estructural). Son señales de **escalas diferentes que coexisten**. Un régimen que use una sola T es una simplificación que pierde información fractal.

### Debilidad 5: No Hay Métrica de Persistencia

Flash no define cuánto dura cada régimen ni qué probabilidad tiene de transitar al siguiente. Sin una **matriz de transición de Markov** con duraciones empíricas, no podemos saber si un régimen detectado va a durar 3 días o 300.

El sector-rotation-gate SÍ tiene esto: `min_regime_days = 20`, duraciones medidas (SANO = 4,342 días, CRASH = 188 días).

### Debilidad 6: Mapeo Prescriptivo Prematuro

La tabla "Régimen → Acción Institucional" asigna acciones ($STK\_ACCUMULATE$, $STK\_TRIM$, etc.) a regímenes que aún no están definidos empíricamente. Esto invierte el proceso científico: primero se define el régimen, luego se mide su retorno forward, y DESPUÉS se decide qué hacer.

---

## Parte 3 — Lo que SÍ Tiene Valor y Debemos Preservar

La propuesta de Flash no es errónea — es prematura. Preservamos:

1. **La estructura de 4 dimensiones como FRAMEWORK conceptual** — no como producto final. Cinemática, Amplitud, Volatilidad y Macro son las familias correctas.

2. **El principio de que overflow/blow-off marca rupturas de régimen** — la evidencia empírica de clusters T3+ en GFC/COVID lo respalda.

3. **La fractalidad como ley física** — cada escala temporal tiene su propia tendencia independiente.

4. **La definición de tendencia como "Estado Energético de Convicción"** — elegante y correcta, pero necesita operacionalización medible.

5. **El concepto de Superposición de Transición** — el lead-lag entre CAT1→CAT2→CAT3 está confirmado por los datos (solo en la dirección bajista).

---

## Parte 4 — Los 6 Ejercicios Probatorios

Para construir el Motor de Regímenes sobre evidencia y no sobre narrativa, propongo 6 ejercicios que usan datos que **ya tenemos** (lake de 8,453 días × 257 features, 33 años).

### Ejercicio 1: Descubrimiento No-Supervisado de Regímenes Naturales

**Pregunta:** ¿Cuántos regímenes de mercado existen naturalmente en los datos?

**Método:**
1. Tomar el vector D1 de las 11 estaciones (11 features: `vix_d1_bin`, `vvix_d1_bin`, ..., `dxy_d1_bin`) del lake.
2. Aplicar clustering (HDBSCAN o Gaussian Mixture Model) para descubrir clusters naturales.
3. Evaluar con métricas de silhouette y estabilidad temporal.
4. **NO imponer k=5.** Dejar que el algoritmo determine cuántos clusters existen.

**Output esperado:** Número de regímenes naturales, sus centroides (qué combinación D1 define cada uno), y su distribución temporal.

**Herramienta:** `continuous_metar_lake.parquet` — las 11 columnas `*_d1_bin`.

---

### Ejercicio 2: Retornos Forward Condicionales por Régimen Descubierto

**Pregunta:** ¿Los regímenes descubiertos en Ejercicio 1 tienen distribuciones de retorno significativamente diferentes?

**Método:**
1. Para cada régimen del Ejercicio 1, calcular forward returns de SPY a 5d, 10d, 20d, 40d.
2. Test de Kruskal-Wallis (no paramétrico) para verificar que las distribuciones son diferentes.
3. Calcular EV, Sharpe y WR por régimen × horizonte.
4. Walk-forward: entrenar clustering en train (primeros 70%), medir retornos en test (último 30%).

**Output esperado:** Tabla régimen × horizonte con EV, WR, Sharpe, y p-value de diferencia vs baseline.

---

### Ejercicio 3: Matriz de Coincidencia Señal ↔ Régimen

**Pregunta:** ¿Las señales validadas OOS se concentran en transiciones de régimen específicas?

**Método:**
1. Etiquetar cada día del lake con su régimen (del Ejercicio 1).
2. Para cada señal validada (cascade_reversal, credit_stress, breadth_contraction):
   - ¿En qué régimen dispara con mayor frecuencia?
   - ¿Dispara ANTES de las transiciones de régimen (líder) o DURANTE (confirmador)?
   - Medir el lag en días entre el disparo de la señal y el cambio de régimen.

**Output esperado:** Heatmap señal × régimen mostrando concentración. Histograma de lag señal→transición.

---

### Ejercicio 4: σ-Overflow como Detector de Transición de Régimen

**Pregunta:** ¿Qué porcentaje de cambios de régimen son precedidos por overflows T2+?

**Método:**
1. Identificar todos los cambios de régimen (del Ejercicio 1).
2. Para cada cambio, verificar si hubo un overflow T2+ (≥4σ en cualquier estación×dimensión) en los 10 días previos.
3. Calcular:
   - % de cambios de régimen precedidos por overflow (recall)
   - % de overflows que preceden un cambio de régimen (precision)
   - F1-score del overflow como detector de transición

**Output esperado:** Precision/Recall/F1 del overflow como predictor de cambio de régimen. Breakdown por tier (T2, T3, T4+).

---

### Ejercicio 5: Persistencia y Duración de Regímenes (Matriz de Transición de Markov)

**Pregunta:** ¿Cuánto dura cada régimen y cuál es la probabilidad de transitar a cada otro?

**Método:**
1. Con los regímenes del Ejercicio 1, construir la matriz de transición de primer orden.
2. Calcular la duración media y mediana de cada régimen.
3. Identificar transiciones "prohibidas" (probabilidad < 1%) y transiciones "dominantes" (> 50%).
4. Verificar estacionariedad: ¿la matriz de transición es estable entre la primera y segunda mitad de la muestra?

**Output esperado:** Matriz de transición $k \times k$, vector de duración, test de estacionariedad.

---

### Ejercicio 6: Cascade Conviction como Precursor de Agotamiento

**Pregunta:** ¿cascade_conviction_50 < -0.957 predice el fin de regímenes alcistas descubiertos en Ejercicio 1?

**Método:**
1. Calcular cascade_conviction en el lake (requiere enriquecer con datos de `quants_obs`).
2. Para cada régimen alcista descubierto, medir:
   - ¿Cuántos días ANTES del fin del régimen alcista cae cascade < -0.957?
   - ¿Hay falsos positivos (cascade cae pero el régimen no termina)?
3. Walk-forward: entrenar umbral en train, medir precisión/recall en test.

**Output esperado:** Lead time medio, precision/recall de cascade como predictor de fin de régimen alcista.

---

## Parte 5 — Secuencia de Ejecución Recomendada

```
                     FLUJO DE INVESTIGACIÓN
                     
    [E1: Descubrimiento]  ──→  [E5: Persistencia]  ──→  ¿Cuántos regímenes?
           │                          │                   ¿Cuánto duran?
           ▼                          ▼
    [E2: Retornos Forward]     [E4: Overflow-Transición]  ──→  ¿Son diferentes?
           │                          │                         ¿Overflow los marca?
           ▼                          ▼
    [E3: Señal↔Régimen]       [E6: Cascade-Agotamiento]  ──→  ¿Señales se alinean?
           │                          │                         ¿Cascade predice fin?
           ▼                          ▼
    ┌──────────────────────────────────────────────────┐
    │  SOLO AQUÍ: Diseñar el MarketRegimeCompositor    │
    │  con fronteras empíricas, no narrativas           │
    └──────────────────────────────────────────────────┘
```

**Orden recomendado:** E1 → E2 → E5 → E4 → E3 → E6.

Los ejercicios E1 y E2 son fundamentales — sin ellos no sabemos cuántos regímenes existen ni si importan. E5 y E4 validan la estructura temporal. E3 y E6 conectan las señales ya validadas con los regímenes descubiertos.

---

## Parte 6 — Conclusión

> [!IMPORTANT]
> **No estamos listos para implementar el `MarketRegimeEngine`.** Tenemos las piezas (señales validadas OOS, METAR lake, overflow taxonomy, sector-rotation-gate), pero nos falta el paso científico fundamental: **dejar que los datos nos digan cuántos regímenes existen y dónde están las fronteras.**
>
> La propuesta de Flash es un buen framework conceptual pero está construida de arriba hacia abajo (de la narrativa a los datos). Necesitamos construir de abajo hacia arriba (de los datos a la estructura). Los 6 ejercicios propuestos usan infraestructura que ya tenemos y pueden ejecutarse en 1-2 sesiones.

### Decisión Requerida

¿Procedemos con los ejercicios probatorios en este orden, o prefieres ajustar el alcance o la prioridad?
