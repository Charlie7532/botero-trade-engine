# PROMPT: AUDITORÍA DIAGNÓSTICA — El OOS/Evaluador General contradice el catálogo de señales validadas (ERROR GRAVE)

**Fecha:** 04-Sep-2026
**Ejecutor:** Gemini (auditoría + diagnóstico, NO implementar fixes aún)
**Propósito:** Investigar y diagnosticar por qué, tras la corrección del OOS del comité (Alternativa B), **el evaluador/OOS ha quedado en un estado inútil y perjudicial**: con él o sin él, el resultado de las señales es el mismo o peor. El sistema ya no discrimina señales, y contradice el conocimiento establecido (señales validadas + diamantes ya encontrados).

---

## CONTEXTO — EL PROBLEMA (verificado)

### Lo que el catálogo YA sabe (señales reales validadas, no inventadas)
El ranking maestro y la evaluación generalizada identificaron, con el sistema anterior (Evaluador General continuo, política de inception, first-passage OHLC), señales con edge real:

| Señal | score | diamante | tier | sigBH |
|:------|:-----:|:--------:|:----:|:-----:|
| fg_extreme_fear | 22.4 | ✅ | HIGH | ✅ |
| dxy_bearish | 18.1 | | ROBUST | ✅ |
| vvix_entry | 15.1 | | ROBUST | ✅ |
| defensive_rotation_divergence | 14.2 | | ROBUST | ✅ |
| vix_crisis_spike | 14.0 | | ROBUST | ✅ |
| panico_total | 16.6 | | ROBUST | |

Estas señales fueron validadas con: first-passage OHLC intrabar, baseline por era, control FDR/BH en el ranking maestro, política de inception (SKEW/FG ≥2011), y la lección de no usar solo-pivote. Déjalo claro: **el catálogo NO es un invento — es trabajo validado previo.**

### Lo que el OOS del comité AHORA dice (contradicción)
Tras la corrección de la Alternativa B (baseline direccional-condicionado + FDR + N≥50 + OBSERVAR peso 0), el resultado OOS fue:
- **In-Sample (lake 1993-2026):** 1 VALIDADA (rotation), 10 INVALIDADAS.
- **OOS (test ≥2023):** **0 VALIDADAS, 11 INVALIDADAS** — todas con N<50 (el filtro OBSERVAR dejó 1-12 señales por estación).
- La confluencia del comité en test tiene **lift negativo vs baseline** (no añade edge).

### El ERROR GRAVE (lo que debes diagnosticar)
**El sistema ha llegado a un punto en que es INÚTIL Y PERJUDICIAL:**
1. **Contradice el conocimiento establecido:** señales que el catálogo ya validó (fg_extreme_fear diamante, dxy_bearish, etc.) AHORA quedan como "INVALIDADAS" en el OOS del comité. O el catálogo está mal, o el OOS del comité está mal — **no pueden ambas ser ciertas**.
2. **No discrimina:** con el OOS actual, prácticamente TODAS las señales quedan igual (0 validadas) → el instrumento no separa lo bueno de lo malo. "Con él o sin él, el resultado es igual o peor" = el evaluador no añade información.
3. **Puede DESCARTAR señales reales:** como el filtro OBSERVAR deja N<50 en casi todas, el OOS invalida por "evidencia insuficiente" señales que en el catálogo tienen N decente y edge — un falso negativo grosero.

---

## LO QUE DEBES AUDITAR / DIAGNOSTICAR (con datos y ejecución, no solo leer)

### 1. ¿Dónde está la desconexión entre el catálogo y el OOS del comité?
Comparar la misma señal (ej. fg_extreme_fear, dxy_bearish, vvix_entry):
- **En el ranking maestro/evaluación generalizada**: ¿qué edge/hit rate/significancia reporta?
- **En el OOS del comité**: ¿qué reporta y por qué la invalida (N<50? p_BH? edge<0.03? OBSERVAR?)
- ¿La diferencia es (a) el filtro OBSERVAR demasiado estricto, (b) el N mínimo ≥50 demasiado alto, (c) un bug en cómo se propaga la señal del agente, o (d) un criterio conceptualmente distinto que invalida señales legítimas?

### 2. ¿El filtro OBSERVAR está MATANDO señales válidas? (hipótesis principal)
- Comparar N de señal del catálogo vs N operacional tras OBSERVAR, por señal/estación.
- Si la convicción del agente emite OBSERVAR demasiado a menudo (ej. >80% del tiempo), el filtro convierte señales reales en "no operar" → el OOS las descarta sin haberlas medido.
- Cuantificar: ¿cuántas NOTs de catalogo caen por debajo de N≥50 por culpa del filtro OBSERVAR?

### 3. ¿El N mínimo ≥50 + FDR es apropiado para señales RARAS (§3.3)?
- La filosofía del proyecto es "rareza = riqueza" (§3.3): N<21 = DIAMANTE, y NO se degrada por N bajo — se reporta con CI95.
- El OOS exige N≥50 para validar → **contradice §3.3**, porque descarta diamantes (N 4-19, como vix/credit/fg) que el catálogo considera valiosos.
- ¿El criterio N≥50 del comité es correcto para señales de cola, o un umbral equivocado que elimina los diamantes?

### 3b. 🔴 SIGNIFICANCIA DE LAS ESCALAS GAUSSIANAS (error crítico que ignora el OOS actual)
**Las señales están calibradas por rareza extrema en las escalas gaussianas (overflow). Un evento EXTREMO es RARO POR DEFINICIÓN — exigirle la misma N que a una señal común es un absurdo estadístico que las mata.**

Cuantificado (de la evaluación): 
- `fg_extreme_fear`: fire_rate **1.17%** (dispara 1 vez cada 218 barras), N=18 → **es diamante PORQUE es extremo/raro**. Exigirle N≥50 equivale a exigirle que deje de ser extremo.
- `panico_total`: fire_rate 1.35%, N=29.
- `sorpresa_total`: fire_rate **32%** (dispara cada 6.6 barras), N=1272 → común.

**Lo que el OOS debe tener en cuenta (la significancia gaussiana), NO ignorar:**

1. **La rareza ES señal de significado (§3.3):** un fire_rate bajo (colas extremas de la escala gaussiana ±σ) NO es "poca evidencia" — es "evidencia de un evento raro". La valoección de un diamante NO se mide por N absoluto, sino por **que su edge supere su baseline con CI95 aceptable incluso con N pequeño** (Clopper-Pearson, tasa + CI).

2. **El overflow/colas gaussianas indican intensidad:** una señal activada por overflow ±2σ/±3σ en las escalas (el `_overflow_tier_*`) es extremadamente rara. El OOS DEBE reconocer que estas señales de cola tienen pocas observaciones PORQUE son eventos de cola — y usar el **CI95 de Clopper-Pearson** + el **z-score de la escala gaussiana** como evidencia, no el N absoluto.

3. **Probar el N mínimo POR rareza, no un N+50 uniforme:** para una señal con fire_rate 1% (evento de cola), N≥50 puede tardar décadas en alcanzarse. El umbral debe ser **escalado por rareza** (p.ej. N_min_relativo = percentil de la frecuencia de disparo, o exigir CI95 cuyo límite inf. > baseline en vez de N absoluto).

4. **La significancia de una señal rara es su z-score/p-value gaussiano, no su conteo:** una señal que dispara 18 veces y acierta 14 con baseline 30% tiene p muy significativo (binomial), aunque N<50. El OOS debe considerar la significancia gaussiana (z-score del estado) + el CI95, NO descartar por "N<50".

**Pregunta central a responder:** ¿el umbral N≥50 uniforme está IGNORANDO la significancia de las escalas gaussianas y descartando diamantes (señales extremas necesariamente escasas) por un criterio de conteo mal aplicado? — Es la hipótesis más probable del "error grave" del evaluador.

### 4. ¿El Evaluador General y el OOS del comité usan el MISMO criterio?
- El Evaluador General (fuente de verdad) mide first-passage OHLC + baseline por era + significance Bohem.
- El OOS del comité (Alternativa B) mezcla: señal del agente (heurística causal) + curador + baseline direccional + N≥50.
- ¿Son los DOS medidores coherentes entre sí? Si difieren, ¿cuál es la fuente de verdad? **El objetivo es que el OOS del comité VALIDE lo que el Evaluador General mide, no que lo contradiga.**

### 5. ¿El sistema discrimina? (prueba de utilidad)
- Tomar una señal de cola validada (fg_extreme_fear, panico_total) y una señal débil/ruido (yield_curve, o una invalida genuinamente).
- ¿El OOS separa limpiamente ambas? Si NO separa (ambas invalidadas o ambas "con N insuficiente"), el instrumento es inútil: no discrimina.

---

## ENTREGABLES (dictamen diagnóstico)
1. **Dónde está la rotura exacta** (filtro OBSERVAR, N≥50, propagación de señal, concepto): localizar el eslabón que hace que el OOS contradiga el catálogo.
2. **Cuantificación:** cuántas señales validadas del catálogo caen por cada motivo (N<50, p_BH, OBSERVAR, edge<0.03) — tabla por señal.
3. **Verificar si es un BUG** (la señal del agente llega mal al OOS) o un **criterio mal calibrado** (OBSERVAR/N≥50 demasiado estrictos).
4. **Propuesta de corrección** para que el OOS del comité sea UTIL:
   - Reconciliar con el catálogo (que valide lo que el Evaluador General ya validó).
   - Respetar §3.3 (N<21 diamante = reportar con CI95, no descartar por N≥50).
   - Ajustar OBSERVAR y/o N mínimo para que las señales reales se midan y se discriminen.
   - Definir claramente la fuente de verdad (Evaluador General vs comité).

**NO implementar el fix — solo diagnosticar y proponer.** El ejecutor de corrección es otro.

**Principios:** Dato mata relato. §3.3 rareza=riqueza. La verdad habla. Si el evaluador no discrimina, está roto o mal calibrado — hay que averiguar cuál.