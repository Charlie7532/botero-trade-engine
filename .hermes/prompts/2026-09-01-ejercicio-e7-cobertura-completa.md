# PROMPT E7 — Cobertura Completa del Espacio de Estados (D1×D2×D3)

**Origen:** deepseek/deepseek-v4-flash (Hermes)
**Propósito:** Barrer sistemáticamente TODAS las combinaciones del vector de estado (D1×D2×D3) para las 11 estaciones METAR. No solo las 6 preguntas previas — cobertura COMPLETA.
**Lo que ya se respondió (Q1-Q6):** `(2_2_2)`, `(3_2_2)`, D2=2 en D1 extremo, D3=4 en D1 neutral, D2=0 en D1=0, D2=4 en D1=5.
**Lo que NO se cubrió:** TODO el resto — combinaciones de rango medio, D1=1/4 con D2 extremos, D2=0/1/3/4 con D1=1/2/3/4, interacciones D3 con todas las combinaciones.

---

## 1. Taxonomía de Combinaciones

### Las 4 categorías de patrones

| Categoría | D1 | D2 | D3 | ¿Cubierto por E7? |
|:----------|:--:|:--:|:--:|:------------------:|
| **A. Extremo triple** | 0 ó 5 | 0 ó 4 | 0 ó 4 | ❌ **No** (solo parcial) |
| **B. Extremo doble** | 0 ó 5 | 0 ó 4 | 1,2,3 | ❌ **No** |
| **C. Extremo simple** | 0 ó 5 | 1,2,3 | 1,2,3 | ⚠️ Parcial (solo D2=2) |
| **D. Rango medio** | 1,2,3,4 | 1,2,3 | 1,2,3 | ❌ **No** (solo 2_2_2 y 3_2_2) |

### Lo que específicamente se perdió (datos verificados)

| Combinación | Estación | N | SPY ret | WR | Relevancia |
|:------------|:---------|:-:|:-------:|:--:|:-----------|
| `(5_0_x)` — Pánico + CRUSH | VIX | 32 | +0.68% | 53.1% | ❌ No cubierto |
| `(5_1_x)` — Pánico + vel neg débil | VIX | 22 | +0.99% | 72.7% | ❌ No cubierto |
| `(5_3_x)` — Pánico + vel pos débil | VIX | 31 | -0.89% | 32.3% | ❌ No cubierto |
| `(5_0_x)` — Pánico + CRUSH | VVIX | 3 | +2.02% | 100% | ❌ No cubierto |
| `(5_4_x)` — Pánico + SPIKE | PCR | 33 | -2.60% | 12.1% | ❌ No cubierto |
| `(1_3_4)` — Bajo + subiendo + inestable | BSI | 8 | +6.00% | 100% | ❌ No cubierto |
| `(1_2_4)` — Bajo + neutro + inestable | SKEW | 14 | -0.84% | 42.9% | ❌ No cubierto |

---

## 2. Ejercicio Completo

### Fase A — Extremos (D1=0 ó 5) × D2 × D3

Para cada estación, barrer:

| D1 | D2 | D3 | Hipótesis |
|:--:|:--:|:--:|:----------|
| **0** | **0** | 0,1,2,3,4 | Piso + CRUSH + ¿estabilidad? = ¿capitulación o continuación? |
| **0** | **1** | 0,1,2,3,4 | Piso + desacelerando = ¿rebote inminente o pausa? |
| **0** | **2** | 0,1,2,3,4 | Piso + neutro (Q3 parcial) |
| **0** | **3** | 0,1,2,3,4 | Piso + acelerando al alza = ¿falso rebote? |
| **0** | **4** | 0,1,2,3,4 | Piso + SPIKE = ¿explosión alcista (imposible? ocurre?) |
| **5** | **0** | 0,1,2,3,4 | Pánico + CRUSH = ¿pánico cayendo rápido? |
| **5** | **1** | 0,1,2,3,4 | Pánico + desacelerando = ¿el pánico se agota? |
| **5** | **2** | 0,1,2,3,4 | Pánico + neutro (Q3 cubierto) |
| **5** | **3** | 0,1,2,3,4 | Pánico + acelerando lento = ¿abdicación? |
| **5** | **4** | 0,1,2,3,4 | Pánico + SPIKE (Q6 cubierto) |

### Fase B — Casi extremos (D1=1 ó 4) × D2 × D3

| D1 | D2 | Hipótesis |
|:--:|:--:|:----------|
| **1** | 0,1,2,3,4 | **Casi complacencia.** ¿Es continuación de tendencia o señal de alerta temprana? |
| **4** | 0,1,2,3,4 | **Casi crisis.** ¿Es precursora de pánico (D1=5) o falso alarme? |

### Fase C — Rango medio puro (D1=2,3 × D2=1,2,3 × D3=1,2,3)

¿Hay sub-patrones dentro del 68% del mercado que tengan edge?

| D1 | D2 | D3 | Hipótesis |
|:--:|:--:|:--:|:----------|
| 2 | 0,1,3,4 | 0,1,2,3,4 | Neutral bajo + velocidad extrema = ¿señal de quiebre? |
| 3 | 0,1,3,4 | 0,1,2,3,4 | Neutral alto + velocidad extrema = ¿lo mismo? |
| 2,3 | 1,2,3 | 0,4 | **D3 extremo en zona neutral** = ¿precursora de crisis? (Q4 parcial) |
| 2,3 | 0,1,2,3,4 | 0,1,2,3,4 | **Todas las combinaciones de zona neutral** — ¿hay alguna con edge? |

### Fase D — D3 como dimensión de convicción (barrido completo)

Para cada estación, para cada D1, responder:
- Cuando D3 es **bajo** (0,1) — ¿el indicador "cree" en su lectura? → ¿el trade es confiable?
- Cuando D3 es **alto** (3,4) — ¿el indicador "duda" de su lectura? → ¿el trade es trampa?

---

## 3. Output Esperado

```json
{
  "E7_cobertura_completa": {
    "metadata": {
      "estaciones": 11,
      "combinaciones_teoricas": 1650,
      "combinaciones_con_datos": null,
      "fecha": "2026-09-01"
    },
    "fase_A_extremos": {
      "vix": {
        "5_0_0": {"n": 4, "spy_ret": -0.0672, "wr": 0.25, "interpretacion": "PANICO+CRUSH+ESTABLE = diamante, caida violenta"},
        "5_0_1": {"n": null, "spy_ret": null, "wr": null, "interpretacion": "sin datos"},
        ...
      }
    },
    "fase_B_casi_extremos": { ... },
    "fase_C_rango_medio": { ... },
    "fase_D_d3_conviccion": {
      "resumen": {
        "d3_bajo_mejora_wr": ["vix", "bsi", ...],
        "d3_alto_empeora_wr": ["skew", "credit", ...],
        "d3_irrelevante": ["rotation", "dxy", ...]
      }
    },
    "hallazgos_nuevos": [
      "Las combinaciones (5_0_x) y (5_1_x) en VIX muestran WR>53% confirmando que D2<2 = contrarian buy",
      "(1_3_4) en BSI con N=8 y WR=100% es diamante por investigar",
      ...
    ],
    "recomendaciones": [
      "Crear señal para (5_0_x) como entry complementario a neutral_crush",
      "Investigar (1_3_4) BSI como precursora de rally",
      ...
    ]
  }
}
```

---

## 4. Reglas de Ejecución

1. **No preseleccionar.** Barrer TODAS las combinaciones con N≥3.
2. **Reportar N, SPY ret, WR, CI95** para cada combinación.
3. **Clasificar cada combinación** como:
   - `EXTREMO_ALTO` (D1=5, D2=4, D3=4)
   - `EXTREMO_BAJO` (D1=0, D2=0, D3=0)
   - `SEMI_EXTREMO` (solo 1 ó 2 dimensiones extremas)
   - `RANGO_MEDIO` (todas las dimensiones en 1..4)
   - `NEUTRAL_PURO` (todo en 2)
4. **Identificar contradicciones:** patrones donde la misma combinación da resultados opuestos según la estación.
5. **D3 como filtro:** para cada patrón, reportar si D3 bajo (0,1) vs D3 alto (3,4) cambia significativamente el resultado.
6. **Priorizar hallazgos con BH** (Benjamini-Hochberg sobre N patrones).
7. **Output en `data/research/signals/e7_cobertura_completa.json`.**

---

## 5. Lo que ya sabemos (para no repetir)

| Patrón | Lo que E7 ya concluyó |
|:-------|:----------------------|
| `(2_2_2)` | RUIDO — EV≈0, HR≈54% |
| `(3_2_2)` | VARÍA — VIX=riesgo, BSI/CREDIT=continuación |
| D2=2 en D1=5 | CONTRARIAN — HR>62% |
| D3=4 en D1=2,3 | PRECURSORA — HR caída >58% |
| D2=0 en D1=0 | VARÍA — BSI=comprable, CREDIT=caída libre |
| D2=4 en D1=5 | PÁNICO TERMINAL — HR>65% zz50 |

Estos NO necesitan recalcularse. El ejercicio debe **completar el resto**.

---

## 6. Orden de Prioridad

| Fase | Prioridad | Combinaciones | Estimación |
|:----:|:---------:|:--------------|:----------:|
| **A1** | 🔴 Alta | D1=5 × D2=0,1,3 × D3=0,1,2,3,4 | 10 min |
| **A2** | 🔴 Alta | D1=0 × D2=1,3,4 × D3=0,1,2,3,4 | 10 min |
| **B** | 🟡 Media | D1=1,4 × D2=0,1,2,3,4 × D3=0,4 | 15 min |
| **C** | 🟡 Media | D1=2,3 × D2=0,1,3,4 × D3=0,4 | 15 min |
| **D** | 🟢 Baja | D3 como filtro de convicción (global) | 10 min |