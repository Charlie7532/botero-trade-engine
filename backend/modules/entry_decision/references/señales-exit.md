# Análisis Profundo y Replanteamiento de Señales de EXIT
## Módulo Entry Decision — Botero Trade Engine
**Fecha de Análisis:** 18 de Agosto de 2026  
**Estatus:** Referencia Técnica y Conceptual de Dominio  

---

## 0. Contexto y Problema Identificado

### 0.1 Asimetría del Sistema Actual
En la calibración de señales operativas sobre el vector de estado macro/mercado, se evidenció una asimetría crítica en el diseño inicial:

```
SISTEMA EVALUADO:
  ✅ 11 señales de ENTRY (credit_easing_k1, bsi_washed_out, capitulacion, pcr_put_panic, etc.)
  ❌ Solo 2 señales de EXIT originales (euforia, fg_extreme_greed)

ESPECIFICACIÓN INSTITUCIONAL:
  "No operar con stops estáticos de precio — aplicar stop de SEÑAL cuando el vector de estado METAR se degrada o anticipa peligro."

GAP IDENTIFICADO:
  El sistema poseía 11 condiciones determinísticas de entrada pero únicamente 2 mecanismos de salida por señal.
  Esto violaba el principio fundamental de salida dinámica por transición de estado METAR.
```

### 0.2 Señales de EXIT Históricas (Pre-auditoría)
1. **`euforia`**:
   - *Definición*: VIX en `DEEP_COMPLACENCY`/`LOW_VOL` conjuntamente con BSI en `BULLISH_BREADTH`.
   - *Comportamiento*: Edge de **-2.99%** (WR 15%) — señal efectiva de TECHO (Short / Venta).
   - *Limitación*: Solo detecta un tipo específico de techo (complacencia extrema).
2. **`fg_extreme_greed`**:
   - *Definición*: F&G en `EXTREME_GREED` (>90).
   - *Comportamiento*: Edge de **-1.92%** (WR 19%) — señal efectiva de TECHO.
   - *Limitación*: Solo detecta agotamiento por codicia minorista/sentimiento.

---

## 1. Hallazgos Empíricos Clave: El Error de la Hipótesis Inicial

### 1.1 La Falacia de "Peligro = Salida"
La hipótesis inicial planteaba que cualquier activación de estados de volatilidad extrema o pánico crediticio debía usarse como disparador de EXIT. Al medir empíricamente sobre la base histórica de datos (1993–2026), los resultados contradijeron la intuición:

```
RESULTADOS EMPÍRICOS DE SEÑALES DE PÁNICO:
  • vix_crisis_spike:    Edge = +0.75%  (WR = 56.7%)  → Comportamiento de ENTRY (Comprar pánico)
  • credit_stress_exit:  Edge = +1.00%  (WR = 54.9%)  → Comportamiento de ENTRY (Comprar pánico)
  • pcr_panic_exit:      Edge = +2.70%  (WR = 71.4%)  → Comportamiento de ENTRY (Comprar pánico)
```

> **Conclusión:** Las señales de "pánico o estrés agudo" son en realidad señales de **ENTRADA contrarian** (comprar pisos de liquidez y capitulación), NO de salida. Cuando el pánico es evidente, el movimiento a la baja ya ocurrió y la asimetría favorece el rebote.

### 1.2 La Señal de Salida Efectiva Descubierta: `bsi_recovery`
Al evaluar transiciones de amplitud, se aisló una señal de salida con edge negativo real y estadísticamente consistente:

```
MEDICIÓN:
  • bsi_recovery: Edge = -1.63%  (WR = 29.0%)  → EXIT Altamente Efectivo

MECÁNICA SUBYACENTE:
  Cuando el BSI (Breadth Sentiment Index) sale de BREADTH_WASHED_OUT y entra en BREADTH_RECOVERY 
  o NEUTRAL_HIGH_BREADTH, el mercado PIERDE en promedio 1.63% subsecuente.
  
  BREADTH_WASHED_OUT marca el fondo de la capitulación. Cuando la amplitud se normaliza hacia 
  la recuperación, la pierna alcista táctica ha concluido (agotamiento del impulso de rebote).
```

---

## 2. Redefinición Taxonómica de Señales de Salida

Las señales de **EXIT** deben modelar el **FIN de una tendencia alcista** o la **degradación estructural del régimen**, no el pánico reactivo.

```
TAXONOMÍA DE SALIDAS (Vector de Estado METAR):

1. EXIT por Fin de Euforia / Techo:
   - Estados de complacencia extrema y agotamiento de compradores.
   - Ejemplos: euforia, fg_extreme_greed, vix_complacency_exit.

2. EXIT por Fin de Recuperación / Agotamiento Táctico:
   - Normalización de amplitud que marca el final de la pierna de rebote.
   - Ejemplos: bsi_recovery, breadth_contraction_exit.

3. EXIT por Fin de Facilidad Crediticia:
   - Cese de condiciones monetarias/crediticias favorables.
   - Ejemplo: credit_ease_exit.

4. EXIT por Cambio de Régimen Macro (Verano → Invierno):
   - Transición estructural simultánea en crédito, volatilidad y amplitud.
   - Ejemplo: regime_change_exit.

5. EXIT por Degradación de Convicción:
   - Reversal en el modelo de convicción de cascada multiescala.
   - Ejemplo: cascade_reversal (caída de cascade_conviction_50 < 0.30).
```

---

## 3. Especificación de Señales de EXIT Propuestas

### 3.1 `bsi_recovery` (Fin de Rebote de Amplitud — Validada)
- **Lógica:** BSI transiciona fuera de `BREADTH_WASHED_OUT` hacia zonas de recuperación normalizada.
- **Hipótesis:** Marca el fin de la pierna alcista táctica tras un piso de mercado.
- **Edge Empírico:** $-1.63\%$ ($WR = 29\%$).

### 3.2 `vix_complacency_exit` (Fin de Euforia por Volatilidad)
- **Lógica:** VIX en `DEEP_COMPLACENCY` o `LOW_VOL`.
- **Hipótesis:** La ausencia total de demanda de cobertura precede techos de mercado y correcciones de volatilidad.
- **Edge Esperado:** Negativo ($WR < 35\%$).

### 3.3 `credit_ease_exit` (Fin de Impulso Crediticio)
- **Lógica:** La estación Credit Stress abandona `CREDIT_EASE` / `DEEP_CREDIT_EASE`.
- **Hipótesis:** El deterioro del spread HYG/LQD frena el flujo institucional hacia renta variable.
- **Edge Esperado:** Negativo en forward returns.

### 3.4 `breadth_contraction_exit` (Contracción de Amplitud de Mercado)
- **Lógica:** BSI abandona `EXPANSIVE_BREADTH` / `HYPER_EXPANSIVE_BREADTH`.
- **Hipótesis:** Pérdida de participación de constituyentes anuncia agotamiento del rally.
- **Edge Esperado:** Negativo en forward returns.

### 3.5 `regime_change_exit` (Transición Verano → Invierno)
- **Lógica:** Conjunción de estrés crediticio (`CREDIT_STRESS` / `CREDIT_CRISIS`), volatilidad elevada (`HIGH_VOL` / `CRISIS_SPIKE`), y contracción de amplitud (`BREADTH_WASHED_OUT` / `OVERSOLD_BREADTH`).
- **Hipótesis:** Ruptura estructural del régimen macro que obliga a la liquidación de posiciones tácticas y swing.
- **Edge Esperado:** Negativo severo con alto Edge Defensivo ($ED > 5\%$).

### 3.6 `cascade_reversal` (Reversal de Convicción Multiescala)
- **Lógica:** La métrica `cascade_conviction_50` desciende por debajo de `0.30`.
- **Hipótesis:** Agotamiento de la probabilidad de continuación de la pierna en el horizonte de 50 barras.
- **Edge Esperado:** Negativo sostenido.

---

## 4. Metodología de Medición y Edge Defensivo

Toda señal de EXIT se evalúa bajo un marco cuantitativo de dos dimensiones ortogonales:

### 4.1 Edge Ofensivo (Forward Return Bajo la Señal)
$$\text{Edge Ofensivo} = \mathbb{E}[\text{forward\_return} \mid \text{señal\_exit = True}]$$
- Para una señal de EXIT, un **Edge Ofensivo negativo** indica que el mercado efectivamente cae tras el disparo.

### 4.2 Edge Defensivo (Pérdida Neta Evitada)
$$\text{Edge Defensivo } (ED) = |\overline{\text{Loss}}| - (\overline{\text{Win}} \times \text{FA\_rate})$$
Donde:
- $|\overline{\text{Loss}}|$: Magnitud promedio de la pérdida que se evita al cerrar la posición.
- $\overline{\text{Win}}$: Ganancia promedio que se deja de percibir si el mercado continuaba subiendo.
- $\text{FA\_rate}$: Tasa de falsa alarma ($\% \text{ de señales donde el mercado continuó al alza}$).

### 4.3 Métricas Complementarias
- **Anticipación Temporal ($\Delta t$):** Días hábiles de anticipación entre el disparo y el pivote máximo del ciclo.
- **Estabilidad Interdecenal:** Comportamiento consistente a través de las décadas de 1990s, 2000s, 2010s y 2020s.

---

## 5. Criterios Cuantitativos de Aprobación

Una señal de EXIT se considerará apta para integración en el motor de decisión si cumple:

| Métrica | Umbral Institucional | Justificación |
|---|---|---|
| **Edge Ofensivo** | $< -1.0\%$ | El subyacente debe caer con significancia estadística. |
| **Edge Defensivo ($ED$)** | $> +3.0\%$ | La pérdida evitada debe compensar holgadamente las falsas alarmas. |
| **Win Rate de Caída** | $< 40\%$ ($> 60\%$ acierto de caída) | La mayoría de las alertas deben preceder retornos negativos. |
| **Tasa de Falsa Alarma ($FA$)** | $< 40\%$ | Evita sobreoperación y whipsaws innecesarios. |
| **Estabilidad Decenal** | $WR < 50\%$ en todas las décadas | Ausencia de sobreajuste o degradación en períodos modernos. |

---

## 6. Hoja de Ruta de Calibración e Integración

1. **Fase de Investigación (Research Lab):** Medición de las 4 nuevas señales en entorno analítico aislado sin modificar los módulos de producción.
2. **Auditoría Estadística y Bootstrap:** Validación de significancia mediante intervalos de confianza CI95 (3,000 iteraciones con reemplazo).
3. **Selección de la Cesta Defensiva:** Homologación de las 3 a 4 señales con mayor Edge Defensivo y menor correlación mutua.
4. **Integración en Clean Architecture:** Mapeo de salidas dentro de `backend/modules/entry_decision/domain/` y `backend/modules/execution/` conforme a la taxonomía universal `STK_TRIM_TACTICAL` y `STK_DISTRIBUTE_DECAY`.
