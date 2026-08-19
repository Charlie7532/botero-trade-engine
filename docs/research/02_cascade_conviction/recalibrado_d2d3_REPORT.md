================================================================================
RECALIBRADO D2/D3 — REPORTE DE RESULTADOS
Análisis con bins calibrados de los lookup adapters (NO umbrales crudos)
================================================================================

DATOS:
- VIX: 8,437 barras (1990-2026), 6 bins D1, 5 bins D2, 4 bins D3 efectivos*
- FG:  3,876 barras (2011-2026), 6 bins D1
- BSI: 8,430 barras (1980-2026, ticker S5TW), 6 bins D1
- SPY forward: 5d, 10d, 20d

* NOTA: VOL_ACCELERATING_EXPANSION nunca se asigna en VIX/FG porque las edges
  D3 son solo 3 para 5 labels. El catch-all es VOL_PEAK_DECELERATION.
  Esto es reproducción fiel del comportamiento actual de los lookup adapters.

================================================================================
[1] MATRIZ DE OPORTUNIDAD — VIX (D1 = CRISIS_SPIKE, ELEVATED_PANIC)
================================================================================

CRISIS_SPIKE (N=1,299):
  → TODAS las celdas con N≥3 son POSITIVAS en 20d (rango +0.31% a +3.14%)
  → Best cell 10d: DECELERATING_DOWN_3D × VOL_MODERATE_COMPRESSION = +2.33% (N=23)
  → Best cell 20d: DECELERATING_DOWN_3D × VOL_MODERATE_COMPRESSION = +3.14% (N=23)
  → FAST_CRUSH_3D × VOL_EXTREME_SQUEEZE muy robusta: +1.38% 10d (N=142)
  → Worst cell 10d: DECELERATING_DOWN_3D × VOL_NEUTRAL_BASELINE = -1.71% (N=22)
  → Conclusión: en CRISIS_SPIKE, D3=MODERATE_COMPRESSION con D2≠STABLE es
    la combinación más alcista. D3=NEUTRAL_BASELINE con D2 negativo es la débil.

ELEVATED_PANIC (N=1,706):
  → Señales mucho más diluidas que CRISIS_SPIKE
  → Best 10d: ACCELERATING_UP_3D × VOL_NEUTRAL_BASELINE = +1.02% (N=72)
  → Best 20d: FAST_CRUSH_3D × VOL_NEUTRAL_BASELINE = +1.63% (N=71)
  → Varias celdas negativas en 10d: FAST_SPIKE×MODERATE (-0.42%), etc.
  → Conclusión: ELEVATED_PANIC no es suficiente por sí solo;
    se necesita D2/D3 específicos para filtrar.

================================================================================
[2] FLIP / TRANSICIÓN — Cambio de signo D2 en extremos D1
================================================================================

CRISIS_SPIKE:
  → D2 turns POSITIVE (empieza a subir): +0.79% 10d, +1.46% 20d (N=114)
    - Mejor con D3=VOL_PEAK_DECELERATION: +1.18% 10d, +2.11% 20d
  → D2 turns NEGATIVE (empieza a bajar): +0.69% 10d, +1.52% 20d (N=116)
    - Mejor con D3=VOL_EXTREME_SQUEEZE: +1.72% 10d, +2.46% 20d
  → Ambos flips son alcistas en CRISIS_SPIKE — el pánico cede en cualquier dirección

ELEVATED_PANIC:
  → D2 turns POSITIVE: +0.48% 10d, +0.41% 20d (N=99)
  → D2 turns NEGATIVE: +0.28% 10d, +0.98% 20d (N=124)
  → Señales mixtas, D3 discrimina:
    - D2↑ con D3=VOL_MODERATE_COMPRESSION → -0.08% 10d (cuidado)
    - D2↓ con D3=VOL_EXTREME_SQUEEZE → -0.61% 10d (cuidado)

================================================================================
[3] D3 COMO FILTRO — Discriminación en estados extremos
================================================================================

En extremos D1 (CRISIS_SPIKE + ELEVATED_PANIC, N=3,005):
  Forward 5d:  todas D3 positivas (T-stat 1.6-3.1), poca discriminación
  Forward 10d: todas D3 positivas (T-stat 2.2-3.8), NEUTRAL_BASELINE y PEAK_DECEL mejor
  Forward 20d: todas D3 positivas (T-stat 3.2-6.2), EXTREME_SQUEEZE lidera con +1.13%

  → D3 discrimina más a 20d que a 5d
  → VOL_EXTREME_SQUEEZE consistentemente el mejor bin con mayor N (1,038)
  → Baseline (todos extremos): +0.51% 10d, +1.08% 20d
  → Ningún D3 es consistentemente bajista en extremos

================================================================================
[4] D2 VELOCITY GRADIENT — FAST_SPIKE → ACCELERATING → STABLE → DECELERATING → FAST_CRUSH
================================================================================

En extremos D1 (10d forward):
  FAST_SPIKE_3D:         +0.69%  (60.1% pos) ← mejor 5d y 10d
  ACCELERATING_UP_3D:    +0.63%  (61.3% pos)
  STABLE_CONTINUATION_3D: +0.29%  (58.0% pos) ← peor
  DECELERATING_DOWN_3D:  +0.04%  (54.9% pos) ← casi plano
  FAST_CRUSH_3D:         +0.67%  (59.3% pos) ← rebote!

En extremos D1 (20d forward):
  FAST_CRUSH_3D:         +1.66%  (66.1% pos) ← MEJOR, rebote mean-reversion
  FAST_SPIKE_3D:         +1.29%  (63.2% pos)
  DECELERATING_DOWN_3D:  +0.75%  (61.1% pos)
  ACCELERATING_UP_3D:    +0.73%  (59.0% pos)
  STABLE_CONTINUATION_3D: +0.62%  (62.3% pos)

  → A 5-10d: momentum (FAST_SPIKE, ACCELERATING) gana
  → A 20d: FAST_CRUSH revierte con fuerza (+1.66%), el rebote post-pánico
  → STABLE es consistentemente el peor — sin momentum no hay edge
  → En ALL D1 states: gradiente menos extremo pero mismo patrón

================================================================================
[5] PICO VS CRUCE — Primer bar CRISIS_SPIKE vs esperar
================================================================================

141 entradas en CRISIS_SPIKE:
  Forward 5d:
    Buy at 1st CRISIS_SPIKE:   +0.26% (56% pos)
    Wait → ELEVATED_PANIC:     +0.39% (57% pos) ← mejor
    Wait → HIGH_VOL:           -0.02% (53% pos)

  Forward 10d:
    Buy at 1st CRISIS_SPIKE:   +0.74% (60% pos) ← MEJOR
    Wait → ELEVATED_PANIC:     +0.54% (63% pos)
    Wait → HIGH_VOL:           +0.63% (60% pos)

  Forward 20d:
    Buy at 1st CRISIS_SPIKE:   +1.18% (64% pos)
    Wait → ELEVATED_PANIC:     +1.68% (67% pos) ← MEJOR
    Wait → HIGH_VOL:           +0.62% (67% pos)

  → Comprar en el primer bar de CRISIS_SPIKE es BUENO (+0.74% 10d)
  → Esperar a ELEVATED_PANIC mejora a 20d (+1.68% vs +1.18%)
  → Esperar a HIGH_VOL es PEOR — la oportunidad ya pasó
  → Estrategia: comprar en CRISIS_SPIKE ya funciona; esperar a ELEVATED_PANIC
    añade +0.5% a 20d pero NO esperar más allá

================================================================================
[6] FG (FEAR & GREED) — Extreme Greed y Extreme Fear
================================================================================

EXTREME_GREED (N=583):
  → 10d forward: mayormente positivo (+0.4% a +1.0%)
  → Best 10d: FAST_SPIKE_3D × VOL_PEAK_DECELERATION = +1.01% (N=59)
  → Best 20d: FAST_CRUSH_3D × VOL_NEUTRAL_BASELINE = +2.81% (N=19)
  → Conclusión: greed extremo NO es bajista en el corto plazo con D2 positivo

EUPHORIA (N=777):
  → 10d forward: mixto (-0.22% a +0.89%)
  → FAST_CRUSH_3D × VOL_PEAK_DECELERATION = -0.22% (N=50) ← cuidado
  → 20d: FAST_CRUSH_3D × VOL_MODERATE_COMPRESSION = +3.19% (N=15) ← outlier
  → Conclusión: euforia es más ambigua que greed extremo

EXTREME_FEAR (N=582):
  → 20d forward: FUERTEMENTE alcista
  → STABLE_CONTINUATION_3D × VOL_NEUTRAL_BASELINE = +4.03% (N=25)
  → ACCELERATING_UP_3D × VOL_PEAK_DECELERATION = +3.42% (N=30)
  → DECELERATING_DOWN_3D × VOL_MODERATE_COMPRESSION = +3.62% (N=16)
  → Conclusión: EXTREME_FEAR es la señal más alcista de todas a 20d

================================================================================
[7] BSI (S5TW BREADTH) — Extremos de breadth
================================================================================

BREADTH_WASHED_OUT (N=206):
  → Señales muy positivas pero baja N en varias celdas
  → FAST_CRUSH_3D × VOL_PEAK_DECELERATION: +5.78% 5d, +8.89% 20d (N=pequeña)
  → STABLE_CONTINUATION_3D × VOL_ACCELERATING_EXPANSION: +4.14% 10d (N=12)
  → Conclusión: BREADTH_WASHED_OUT es la señal más extrema; requiere
    validación con más datos dado el N bajo (206 barras totales)

OVERSOLD_BREADTH (N=1,091):
  → Señales mixtas, D3 discrimina bien
  → ACCELERATING_UP_3D × VOL_ACCELERATING_EXPANSION: +2.14% 10d, +3.25% 20d (N=34)
  → STABLE_CONTINUATION_3D × VOL_PEAK_DECELERATION: -2.22% 10d, -2.88% 20d (N=20)
  → FAST_CRUSH_3D × VOL_MODERATE_COMPRESSION: -2.00% 10d ← ÚNICA celda roja grande

HYPER_EXPANSIVE_BREADTH (N=197):
  → Pocas celdas con N suficiente
  → FAST_SPIKE_3D × VOL_NEUTRAL_BASELINE: -2.37% 20d (N=8) — potencialmente bajista
  → STABLE en HYPER_EXPANSIVE: +1.0-2.3% 20d — alcista, continuidad

================================================================================
CONCLUSIONES CLAVE
================================================================================

1. D3 SÍ DISCRIMINA: En CRISIS_SPIKE, D3=VOL_MODERATE_COMPRESSION
   es el mejor filtro (SPY +2.33% 10d). D3=VOL_NEUTRAL_BASELINE es
   el más débil en caídas.

2. D2 FAST_CRUSH NO ES PELIGROSO: En extremos D1, FAST_CRUSH_3D muestra
   el mejor rebote a 20d (+1.66%), efecto mean-reversion. Contrario a
   lo que sugeriría el nombre.

3. PICO VS CRUCE: Comprar en el 1er bar de CRISIS_SPIKE funciona (+1.18% 20d).
   Esperar a ELEVATED_PANIC es marginalmente mejor (+1.68% 20d).
   Esperar más a HIGH_VOL es contraproducente.

4. FG EXTREME_FEAR es la señal más alcista de todas las estaciones
   a 20d (+2-4%), superando a VIX CRISIS_SPIKE.

5. BREADTH_WASHED_OUT (BSI) produce las señales más extremas pero
   con N bajo — requiere validación out-of-sample.

6. VOL_ACCELERATING_EXPANSION está roto en VIX/FG: nunca se asigna
   porque hay 3 edges para 5 labels. Solo funciona en BSI (4 edges).
   → Posible bug en la calibración de los fact stores VIX/FG.

Archivos generados:
  research/02_cascade_conviction/recalibrado_d2d3.py           — script completo
  data/research/misc/recalibrado_d2d3_output.txt   — output completo (454 líneas)
================================================================================