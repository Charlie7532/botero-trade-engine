# PRINCIPIO DE VALOR Y SIGNIFICADO DE SEÑALES — Documento de Diseño (v1)

**Fecha:** 03-Sep-2026
**Estado:** Documento fundacional para discusión — NO es prompt de implementación.
**Propósito:** Establecer el criterio de qué es una señal con valor vs ruido en el sistema METAR, bajo la visión del arquitecto. Este documento se somete a comité para crítica antes de cualquier implementación.

---

## 1. El principio rector (contrapunto a López de Prado)

**López de Prado** (y el estándar cuantitativo) tratan la rareza como ruido: de-clusterizan, aplican Bonferroni/BH, y **silencian** las muestras poco frecuentes por falta de significancia estadística. Su objetivo es minimizar falsos positivos en un contexto de múltiples pruebas masivas.

**Nuestra posición (§3.3 y visión del arquitecto):**
> La rareza no es ruido — es **significado**. Una muestra poco frecuente "no ocurre porque sí": existe porque refleja una condición de mercado específica. El de-clustering NO descarta esa señal: solo reporta cuántas muestras verdaderamente independientes la respaldan (credibilidad), y la señal se **clasifica por su significado**, no se elimina.

**La reconciliación operativa:**
| Herramienta | Para qué la usamos | Qué NO hace |
|:------------|:-------------------|:-------------|
| De-clustering (N honesto) | Credibilidad del dato | NO descarta lo escaso |
| Clopper-Pearson (CI95) | Incertidumbre real | NO silencia lo improbable |
| Bonferroni/BH | Evitar falsos + en ranking masivo | NO destruye significado |
| **§3.3 (rareza=riqueza)** | **Es la ley de compensación** | **Las señales escasas se estudIAN, no se filtran** |

**Regla concreta (§3.3):** Si una señal produjo 13/15 veces el mismo resultado y las 2/15 no mostraron riesgo significativo, esa señal **se mantiene y se etiqueta** — es un patrón. Podrá ser de tier LOW (N bajo) pero tiene significado. Solo la falta de *cualquier* patrón, con riesgo material, la degrada.

---

## 2. Métrica de impacto: posición en el rango (NO HR direccional)

La taxonomía NO se basa en "¿cuánto sube después?" (HR direccional — que fue el error del primer análisis). Se basa en:

**A. Posición de la señal respecto al giro (rango del pivote ZigZag):**
```
EN RANGO (anticipa/coincide):
  t-2, t-1, t=0, t+1, t+2   → señal dentro de la ventana del giro
FUERA DEL RANGO (ENTRE):
  lejos del pivote             → señal en continuación de la pierna
```

**B. Cada ocurrencia se mide en un CONTINUO posicional, no binario:**
- distancia exacta al pivote (barras/días)
- dirección hacia dónde apunta el giro (MAX/MIN)

**C. La lectura por GRADIENTE (lo que aporta significado):**
| Posición | Significado |
|:---------|:------------|
| t-n (lejos, anticipa mucho) | Canaria de **proceso** (acumulación/distribución) |
| t-1 | Canaria de **inminencia** |
| t=0 | **Confirmación** del giro |
| t+1, t+2 | **Reacción / rezagada** |
| FUERA (ENTRE) | No descarta — se estudia: ¿apunta al rango futuro? ¿es reversión? ¿contraria? |

**D. La pregunta de "cantidad":** *cuántas veces impacta al giro, de cuántas veces aparece* (impact ratio). NO el HR de subida/caída.

---

## 3. Lo FUERA del rango NO se excluye

Las velas en posición fuera del rango (ENTRE) tienen preguntas propias de significado:
- ¿Win rate desde FUERA hasta el rango? (señales que apuntan al giro desde lejos)
- ¿Cuáles son contrarias? (apuntan contra la dirección del giro)
- ¿Cuáles aparecen en **reversiones**?
- ¿Cuáles son **acumulación/distribución** (proceso lento hacia un giro)?

Esto responde al error conceptual de "excluir lo que no está en rango": **esos datos también significan**, y su estudio es parte de la taxonomía.

---

## 4. Huella multi-escala (el gradiente vertical)

Cada señal se evalúa en su impacto a **corto (zz25), mediano (zz50) y largo (zz75)**. El gradiente entre escalas ES información:

| Patrón cross-escala | Significado |
|:--------------------|:------------|
| zz25 abajo, zz75 arriba/plano | Más probable el **rebote** (divergencia favorable) |
| zz25 arriba, zz75 abajo | Más probable la **corrección** |
| Las 3 alineadas | **Continuación con fuerza** |
| Alguna desalineada | **Desacuerdo / desidia** en ese horizonte |

La huella multi-escala distingue: continuación con fuerza (sin draw down), desacuerdo, punto de interés, acumulación, distribución.

---

## 5. Taxonomía de significado (capa semántica)

Cada señal del vector D1×D2×D3 se clasifica en:
1. **CONTINUACIÓN CON FUERZA** — sube sin drawdown, mantiene sesgo
2. **DESACUERDO / DESIDIA** — empuja pero se estanca
3. **PUNTO DE INTERÉS** — niveles donde la acción se concentra
4. **ACUMULACIÓN** — proceso de largo plazo hacia giro alcista
5. **DISTRIBUCIÓN** — proceso de largo plazo hacia giro bajista
6. **CANARIO DE GIRO** — canta cerca del pivote (t-1/t-2)
7. **CANARIO DE PROCESO** — canta muy lejos (>15d), marca acumulación/distribución
8. **ALEATORIA/NO-PATRÓN** — sin patrón, pero aun así etiquetada (significa algo)

**Nota esencial:** aun la señal aleatoria "no ocurre porque sí" — se mantiene etiquetada. La ausencia de patrón también es un dato.

---

## 6. Confluencia y forecast probabilístico

*"Una sola golondrina no hace verano."* El sistema de forecast NO predice un determinante único:

- **Confluencia de señales** → apunta a una **condición de mercado** (no a 1 resultado)
- **Miedo y euforia tienden a exagerarse** → sobre todo el miedo (fat-tails)
- Cada señal es **un voto probabilístico**, no un veredicto
- Salida: **probabilidad de giro + alertas** (TAF/SIGMET/NOTAM), NO un punto determinista

**El instrumento entregado:** conocer el ESTADO ACTUAL + sistema de FORECAST y ALERTAS.

---

## 7. Rol de ML / agentes: INTÉRPRETES, no filtros

**ADVERTENCIA CRÍTICA:** si se monta ML/DL/agentes usando pérdida clásica (minimizar error de predicción), **destruirá el significado** — los outliers (señales raras) se descartarán como ruido para mejorar la métrica.

**Diseño requerido:** ML/agentes como **intérpretes del significado de cada firma**, aprendiendo a *reconocer* qué condición refleja cada combinación exótica, NO a silenciarla. La pérdida debe premiar la **reconstrucción de la firma y su significado**, no la minimización de error que penaliza lo raro.

**¿Cómo se les enseña que "una muestra fuera de las probabilidades es significativa"?** El mal de aprendizaje debe incluir un término que preserve/destaque los casos raros como clases válidas con significado propio — no tratarlos como outliers a eliminar.

---

## 8. La data ya está decantada/calificada (estado actual)

De la investigación previa, la data de señales está:
- **Decantada:** 31-37 señales catalogadas, con BLANCOS auditados
- **Clasificada:** tiers §3.3 (ANECDOTAL a ROBUST), rareza, grados
- **Dispuesta:** fact stores OHLC, bar_augment regenerado, medicion_*.json

Este documento define cómo se *analiza* esa data pre-clasificada para extraer SIGNIFICADO — no cómo se re-mide.

---

## 9. Preguntas para el comité

1. ¿La distinción "de-clustering = credibilidad, no exclusión" es defendible frente al estándar? ¿Dónde está el límite en que una señal escasa SÍ es ruido?
2. ¿La métrica de impacto posicional (posición en el rango + impact ratio) es más informativa que el HR direccional? ¿Qué límites tiene?
3. ¿El tratamiento de lo FUERA-del-rango como significado (no como exclusión) es un artefacto o un hallazgo?
4. ¿Cómo implementar un ML/agente que premie significado en vez de silenciar outliers — qué arquitectura de pérdida?
5. ¿La huella cross-escala (zz25 vs zz75 como divergencia de rebote) es una señal sólida o un artefacto de no-estacionariedad?
6. ¿Qué definición operativa de "canario" (distancia al pivote que clasifica proceso vs giro) es robusta?

---

*Este documento se somete a comité multidisciplinario (estadístico, cuantitativo LaPrade-esque, semántico, ML) para crítica fundada en los datos. NO es una especificación de implementación.*