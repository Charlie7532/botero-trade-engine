# CONJUNCIÓN DE-RISKING — Veredicto Final
## secuencia (fase) + cascade (dirección) + σ-overflow (colas)

**Script:** `research/04_conjuncion_multi_estacion/conjuncion_derisking.py`  
**JSON:** `data/research/conjunctions/conjuncion_derisking_report.json`  
**Intérprete:** `PYTHONPATH=/root/botero-trade backend/.venv/bin/python`

---

### Método
- **Clasificador de secuencias:** réplica EXACTA de `validate_regimes_oos.py` (9 tickers, percentiles crudos, SIGMET trajectory-based, ventana 30d).
- **Entrada HONESTA:** barra de señal = max(1ª activación CAT1/CAT2/CAT3), sin look-ahead.  
- **Cascade_conviction:** réplica del compositor real: d1_bear_masked (5 Grupo A con type_mask) + domino zz25 (|prev_leg_return|). c50 → tercil t1_low/t2/t3 (umbrales -0.387/+0.302 del `cascade_calibration.json`).
- **σ-overflow:** `validate_overflow()` (±3σ en D1/D2/D3 de las 11 estaciones). MULTI = 2+ dimensiones de la MISMA estación.
- **Forward:** 5/10/20/40d SPY desde barra de señal. Bootstrap CI95 3000 iter.
- **3 escalas zigzag:** zz25, zz50, zz75.
- **Baseline SPY:** todos los días en la ventana elegible (1993-2026).

---

### Resultados

#### Secuencia SHORT sola (combinación a) = macro-driven (CAT1→CAT2→CAT3) + cuchillo (CAT1→CAT3→CAT2)

| Escala | N | fwd 20d | CI95 20d | fwd 40d | CI95 40d | downWR 20d | PF 20d | Kelly 20d | wipe>20% 40d |
|--------|---|---------|----------|---------|----------|------------|--------|-----------|-------------|
| zz25 | 1294 | −1.84% | [−2.21,−1.46] | −1.13% | [−1.63,−0.60] | 61% | 2.15 | +0.33 | 11 |
| zz50 | 402 | −3.26% | [−4.11,−2.36] | −2.17% | [−3.43,−0.84] | 65% | 2.93 | +0.43 | 7 |
| zz75 | 160 | −4.32% | [−5.69,−3.00] | −4.26% | [−5.99,−2.26] | 64% | 3.97 | +0.48 | 1 |

✅ OP-SHORT en las 3 escalas. CI95 no cruza 0 en ningún horizonte.

---

#### ⚠️ HALLAZGO CRÍTICO — Signo invertido en cascade_conviction

El cascade_conviction (c50) es MONOTÓNICO en la dirección SHORT — a MÁS convicción (t3_high = voto bear alto), MÁS negativo el forward:

**Descomposición por tercil (zz50, 20d):**
| Tercil | N | fwd 20d | CI95 | Significado |
|--------|---|---------|------|-------------|
| t1_low (c50<−0.387) | 182 | −2.21% | [−3.4,−0.8] | Convicción BAJA = voto bear BAJO = **MENOS bajista** |
| t2_medium | 132 | −3.36% | [−4.9,−1.9] | Neutral |
| t3_high (c50>+0.302) | 88 | **−5.27%** | [−7.4,−3.1] | Convicción ALTA = voto bear ALTO = **MÁS bajista** |

**La misma monotonicidad se replica en zz25 y zz75.**

👉 **El "cascade bear" correcto es t3_high (c50 > +0.302, convicción alta, voto bear alto), NO t1_low.**  
La definición del task "conviction t1_low o negativa" está **INVERTIDA**: selecciona el tercil MENOS bajista.

---

#### Combinaciones (task literal vs signo correcto)

##### Task literal — "cascade bear = c50 < 0 (t1_low o negativa)"

| Comb | Escala | N | fwd 20d | fwd 40d | CI95 20d todo-neg | Δ vs (a) 20d | CI95 Δ |
|------|--------|---|---------|---------|-------------------|-------------|--------|
| b | zz50 | 266 | −2.70% | −1.80% | ✅ | +0.56pp | [−0.78,+1.98] |
| b | zz75 | 107 | −3.66% | −2.66% | ✅ | +0.66pp | [−1.42,+2.64] |
| d | zz50 | 50 | −2.68% | −2.88% | ✅ | +0.58pp | [−1.31,+2.45] |
| d | zz75 | 20 | −2.51% | −2.94% | ❌ (20d CI cruza 0) | +1.81pp | [−1.53,+5.30] |

**Conclusión:** la conjunción con el signo del task NO mejora el edge SHORT. Las combinaciones b/d son MENOS bajistas (Δ positivo) que la secuencia sola. CI95 de la Δ cruza 0.

##### Signo correcto — "cascade bear = t3_high (voto bear alto, c50 > +0.302)"

| Comb | Escala | N | fwd 20d | fwd 40d | CI95 20d todo-neg | PF 40d | Kelly 40d | wipe>20% | Δ vs (a) 40d |
|------|--------|---|---------|---------|-------------------|--------|-----------|----------|-------------|
| e) t3_high | zz50 | 88 | **−5.27%** | −3.74% | ✅ | 2.54 | +0.42 | 3 | −1.57pp |
| e) t3_high | zz75 | 29 | **−7.35%** | **−7.93%** | ✅ | 20.27 | +0.79 | 0 | −3.66pp |
| **f) t3_high+overflow** | zz50 | 62 | **−5.67%** | **−4.26%** | ✅ | 2.54 | +0.43 | 3 | −2.09pp |
| **f) t3_high+overflow** | zz75 | 21 | **−7.87%** | **−8.11%** | ✅ | **31.40** | **+0.88** | **0** | −3.84pp |

**Conclusión:** la conjunción con el signo CORRECTO (t3_high = voto bear alto) SÍ mejora el edge SHORT direccionalmente. El edge se duplica aproximadamente en zz50/zz75. La Δ vs (a) no alcanza CI95 significativo (N más pequeño → mayor ruido), pero las combinaciones mismas tienen CI95 completamente negativo.

---

### Veredicto

1. **¿La conjunción mejora el edge SHORT sobre la secuencia sola?**  
   - Con el signo del task (c50<0 = t1_low): **NO.** Selecciona las entradas MENOS bajistas (Δ positivo).
   - Con el signo correcto (t3_high = voto bear alto): **SÍ, direccionalmente.** Punto estimado ~2× más bajista en zz50/zz75. La mejora (Δ) tiene CI95 que cruza 0 por menor N, pero las combinaciones mismas tienen CI95 completamente negativo y métricas de trade muy superiores (downWR, PF, Kelly, wipeouts).

2. **¿Cuál combinación es la más fuerte?**  
   **f) SHORT + cascade t3_high + overflow (triple confirmación, signo correcto)**.  
   zz75 40d: −8.11% CI95[−12.03,−4.56], downWR 90%, PF 31.40, Kelly +0.88, 0 wipeouts >20%.

3. **¿Triple confirmación (signo correcto) alcanza CI95 sin cruzar 0?**  
   **SÍ.** En zz50 (N=62) y zz75 (N=21) el CI95 es completamente negativo en 20d y 40d. La triple confirmación del task literal (d, c50<0+overflow) tiene N=20 en zz75 y su CI95 20d SÍ cruza 0 → INSUFICIENTE.

4. **Comparación vs baseline SPY (todos los días):**  
   Baseline SPY 40d = +1.79% (siempre positivo, drift natural).  
   La secuencia SHORT sola invierte el signo a −1.13% (zz25) / −2.17% (zz50) / −4.26% (zz75).  
   La triple correcta lleva el edge a −8.11% (zz75 40d). **La secuencia es un detector de de-risking real, y la conjunción correcta lo potencia.**

---

### Nota sobre el signo (dato mata relato)

El cascade_conviction c50 es MAYOR cuando el voto bear (d1_bear_masked) es MAYOR — más estaciones en estado de estrés = más convicción = t3_high. El task definió "cascade bear = t1_low o negativa", pero la evidencia empírica muestra que **t1_low es el tercil MENOS bajista** y **t3_high es el MÁS bajista** en las 3 escalas. La monotonicidad t1< t2< t3 se replica consistentemente. El signo correcto para "cascade bear" (confirmación bajista) es **t3_high**.