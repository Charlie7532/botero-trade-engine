# REEVALUACIÓN INTEGRADA — Marco Corregido: Edge Defensivo + Forense Claude Opus
## Botero Trade — Agosto 2026

> **INTEGRACIÓN DE 7 REPORTES CLAUDE OPUS + 1 REPORTE ANALISTA PREVIO**
>
> Fuentes integradas:
> 1. `falsas_alarmas_precursores.md` (Claude) — Precision/Recall de 32 combinaciones señal×precursor
> 2. `edge_defensivo_graduado.md` (Claude) — Marco ED, Lift, graduated response
> 3. `puntos_ciegos_adicionales.md` (Claude) — Bootstrap CI, estabilidad década, cross-overlap, duration_bars
> 4. `determinismo_d2d3.md` (Claude) — 20 sign flips D2/D3, vvix_entry más sensible
> 5. `audit_medir_senal.md` (Claude) — 2 bugs activos, 5 blind spots de medir_senal.py
> 6. `diagnostico_consolidado_señales.md` (Claude) — Ranking 10 señales, CI95, duración, década
> 7. `forense_precursores_crash.md` (Claude) — 86 precursores, lift, protectores, FA=0%
> 8. `analisis_estadistico_profundo.md` (Analista previo) — Reevaluación marco corregido, ED, asimetría

---

## ÍNDICE

0. [CAMBIO DE MARCO: La Pregunta Correcta](#0-cambio-de-marco-la-pregunta-correcta)
1. [INTEGRACIÓN: Convergencias y Contradicciones](#1-integración-convergencias-y-contradicciones)
2. [BUGS ACTIVOS DE medir_senal.py](#2-bugs-activos-de-medirsenalpy)
3. [DETERMINISMO D2×D3 — Sign Flips Confirmados](#3-determinismo-d2d3--sign-flips-confirmados)
4. [PRECURSORES DE CRASH — Forense Unificado](#4-precursores-de-crash--forense-unificado)
5. [FALSAS ALARMAS — Costo de Actuar vs Costo de Ignorar](#5-falsas-alarmas--costo-de-actuar-vs-costo-de-ignorar)
6. [EDGE DEFENSIVO GRADUADO — Ranking Final](#6-edge-defensivo-graduado--ranking-final)
7. [TABLA FINAL INTEGRADA](#7-tabla-final-integrada)
8. [ESTABILIDAD POR DÉCADA — Degradación 2020s](#8-estabilidad-por-década--degradación-2020s)
9. [CONFLUENCIA CROSS-SEÑAL — Aditividad vs Redundancia](#9-confluencia-cross-señal--aditividad-vs-redundancia)
10. [PUNTOS CIEGOS — Lo que NINGÚN REPORTS CUBRIÓ](#10-puntos-ciegos--lo-que-ningún-reporte-cubrió)
11. [RECOMENDACIONES OPERACIONALES](#11-recomendaciones-operacionales)
12. [ANEXO: Precursores FA=0%](#12-anexo-precursores-fa0)

---

## 0. CAMBIO DE MARCO: La Pregunta Correcta

| Marco Antiguo (DESCARTADO) | Marco Nuevo (CORREGIDO) |
|---|---|
| "¿Cuánto gana esta señal?" | "¿Cuánto DEJA DE PERDER si se retira a tiempo?" |
| Edge = forward_return mean | Edge = pérdida evitada - costo de falsas alarmas |
| Señales con WR bajo = ruido | Señales con WR bajo pueden tener edge defensivo ALTO |
| FA (falsa alarma) = fracaso | FA = costo aceptable si la pérdida evitada es mayor |
| Precursores raros (N=3) = artefacto | **Rareza = Riqueza** — regímenes extremos valiosos |

**La fórmula cambia de:**
```
Edge Ofensivo (antiguo) = mean(forward_return | señal activa)
```
**A:**
```
Edge Defensivo (nuevo) = |mean_loss| - (mean_win × FA_rate)
```

---

## 1. INTEGRACIÓN: Convergencias y Contradicciones

### ✅ CONVERGENCIAS PRINCIPALES (Hallazgos que AMBAS fuentes confirman)

| # | Hallazgo | Claude Opus | Analista Previo | Confianza |
|---|---|---|---|---|
| 1 | **credit_easing_k1 es la señal más robusta** | WR=93.8%, CI95 significativo, 0/2 D2D3 splits | ED=5.29%, 15.3× ratio actuar/no-actuar | 🔒 **SÓLIDA** |
| 2 | **credit_stress con pierna corta = CERO edge** | ≤2b: -0.01%, WR=49%, sign flip | Filtro operativo: ignorar si duration_bars ≤ 2 | 🔒 **SÓLIDA** |
| 3 | **pcr_put_panic se degrada en 2020s** | WR 76%→56% (2020s), pérdida de edge | WR 70-76%→56%, ED probable caído a ~2-3% | 🔒 **SÓLIDA** |
| 4 | **capitulacion colapsa en 2020s** | +1.32%→+0.12% por década | WR 76%→57%, tendencia bajista | 🟡 **MEDIA** |
| 5 | **credit.D2=ACCEL_UP es precursor universal** | Aparece en 5/6 señales, lift medio 4.1× | Confirmado como #1 precursor en forense | 🔒 **SÓLIDA** |
| 6 | **D2/D3 ignorados en señales actuales** | 20/34 sign flips, D2 más determinante que D3 | Punto ciego #1 de medir_senal.py | 🔒 **SÓLIDA** |
| 7 | **vvix_entry estable/mejorando** | +1.55% en 2020s, CI marginal pero estable | WR 65-62%, muy estable por década | 🟡 **MEDIA** |
| 8 | **bsi_washed_out estable con ruido** | WR 56-70% por década, estable | ED=5.58%, 3.1× baseline, dual | 🟡 **MEDIA** |

### ❌ CONTRADICCIONES O TENSIONES

| # | Tópico | Claude Opus | Analista Previo | Resolución |
|---|---|---|---|---|
| **1** | **capitulacion: CI95 vs ED** | CI95 cruza cero → "No pasa significancia estadística" | ED=6.86% → "Mejor señal defensiva del sistema" | **No hay contradicción real**. CI95 mide forward_return medio (marco antiguo). ED mide pérdida evitada (marco nuevo). Son métricas ortogonales. capitulacion puede tener forward_return no significativo PERO alto edge defensivo porque sus crashes son extremadamente caros (-9.22% media). |
| **2** | **D2/D3 significancia bootstrap** | Solo 1/5 sign flips pasa CI95 bootstrap. El resto cruza cero por N bajo. | Presenta 20 sign flips como determinantes y accionables. | **Tensión real**. Claude tiene razón en que N<15 en peor rama = no significativo. Pero el marco corregido (rareza=riqueza) rescata estos casos: un flip de +7.7pp con N=13 vs N=12 es información direccional aunque no pase CI95. La resolución: usar sign flips como **alertas contextuales**, no como filtros duros, salvo que el bootstrap lo confirme. |
| **3** | **dxy_bearish: útil o no?** | Edge ≈ 0%, no pasa CI95, columna 9/10 | No incluido en ranking ED principal | **Coinciden** — ambas lo descartan como señal operable. |
| **4** | **panico_total validez** | N=34, CI95 cruza cero ([-0.49%,+3.51%]) | ED=2.08%, 1.0× baseline = no mejora al azar | **Coinciden** — ambas dicen "en revisión / no operable" |
| **5** | **sub_reaccion validez** | CI95 cruza cero, sign flip por duración | No incluido en ranking ED, mencionado como "operable con filtro" | **Tensión leve**. Ambas reconocen que solo funciona con piernas >4b. La resolución: es operable SOLO condicionado a duration. |
| **6** | **euforia: señal de techo o defensiva?** | CI95 bajista significativo (-2.99%, WR=14.6%) | ED=0.11%, 0.1× baseline = "sin edge defensivo" | **Coinciden** — euforia es señal de TOPE (SHORT), no de protección. Mantener como señal de techo. |

### 📊 Mapa de Conflictos — Prioridad

| Conflicto | Severidad | Veredicto |
|---|---|---|
| capitulacion CI95 vs ED | 🟡 **Aparece** | Resuelto: métricas ortogonales |
| D2/D3 bootstrap vs accionabilidad | 🔴 **Real** | Usar bootstrap CI como filtro duro, direccional como alerta |
| sub_reaccion duración | 🟢 **Leve** | Usar con filtro duration >4b |
| dxy_bearish | 🟢 **Coinciden** | Descartar |
| panico_total | 🟢 **Coinciden** | En revisión |

---

## 2. BUGS ACTIVOS DE medir_senal.py

_Confirmados por Claude Opus en audit_medir_senal.md. Pendientes de corrección._

### 🔴 Bug 1 — Anticipación mide autocorrelación, NO anticipación temporal

```python
# Líneas 499-510 de medir_senal.py
adelantada = señal.shift(-k, fill_value=False)
coincidencia = (señal & adelantada).sum()
```

`shift(-k)` desplaza la serie **hacia adelante** — mide persistencia/clustering, no anticipación.
**Evidencia:** `shift(-k)` y `shift(+k)` dan los mismos valores (107, 83, 63, 51) para `bsi_washed_out`.

**Corrección:** Renombrar a `persistencia_cluster`. Para verdadera anticipación, consultar barras diarias del Vault antes del pivot_date.

### 🔴 Bug 2 — Capture Ratio tiene semántica invertida

```python
zz25_leg = df.loc[señal, "prev_leg_return"].dropna()
cr = np.nanmean(zz25_act) / np.nanmean(zz25_leg)
```

`prev_leg_return` es la pierna que **termina** en el pivote, no la que **empieza**. Para señales de piso (MIN), `prev_leg_return` es negativo. El ratio produce valores sin sentido: credit_stress **+163×** porque MIN y MAX se cancelan.

**Corrección:** Usar `forward / abs(prev_leg_return)` separando por `pivot_type`.

---

## 3. DETERMINISMO D2×D3 — Sign Flips Confirmados

> **Hallazgo central: 20 de 34 combinaciones (59%) producen SIGN FLIPS — el edge se INVIERTE dependiendo de D2 o D3.**

_D2 (velocidad) es más determinante que D3 (volatilidad de estación): 13 flips D2 vs 7 flips D3._

### Top 10 Sign Flips por Spread

| # | Señal | Estación | Dim | BEST | mean | WR | N | WORST | mean | WR | N | Spread |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | sub_reaccion | vix | D2 | ACCEL_UP | +5.11% | 69% | 13 | DECEL_DOWN | -2.59% | 25% | 12 | **+7.70pp** |
| 2 | pcr_put_panic | bsi | D2 | STABLE_CONT | +5.38% | 89% | 18 | FAST_CRUSH | -2.19% | 40% | 5 | **+7.57pp** |
| 3 | bsi_washed_out | fg | D2 | DECEL_DOWN | +5.17% | 100% | 5 | FAST_CRUSH | -1.74% | 50% | 8 | **+6.91pp** |
| 4 | vvix_entry | dxy | D2 | FAST_CRUSH | +5.01% | 88% | 8 | FAST_SPIKE | -1.23% | 50% | 6 | **+6.24pp** |
| 5 | capitulacion | bsi | D3 | VOL_COMPRESSION | +5.42% | 87% | 15 | VOL_EXPANSION | -0.67% | 50% | 6 | **+6.09pp** |
| 6 | vvix_entry | skew | D3 | VOL_BASELINE | +2.99% | 70% | 30 | VOL_COMPRESSION | -2.10% | 40% | 10 | **+5.09pp** |
| 7 | pcr_put_panic | skew | D3 | VOL_BASELINE | +3.90% | 79% | 19 | VOL_COMPRESSION | -1.06% | 57% | 7 | **+4.96pp** |
| 8 | capitulacion | fg | D2 | DECEL_DOWN | +3.44% | 80% | 5 | STABLE_CONT | -1.18% | 56% | 16 | **+4.62pp** |
| 9 | vvix_entry | yield | D2 | DECEL_DOWN | +3.52% | 67% | 9 | ACCEL_UP | -0.77% | 33% | 6 | **+4.29pp** |
| 10 | credit_stress | vix | D2 | ACCEL_UP | +3.31% | 70% | 33 | DECEL_DOWN | -0.97% | 38% | 24 | **+4.28pp** |

### ⚠️ Advertencia de Bootstrap (Claude Opus)

> De los 5 sign flips más grandes testeados con bootstrap (3000 iter, seed=42), **SOLO 1 pasa CI95**: `credit_stress × vix D2` ([+0.0107, +0.0730]).
>
> Los demás tienen N<15 en la peor rama — son indicaciones **direccionales**, no certezas estadísticas.
>
> **Resolución integrada:** Usar D2/D3 como filtros contextuales (graduated response), no como bloqueos duros, salvo que el bootstrap CI95 lo confirme. Para los sign flips sin CI95, reducir tamaño en lugar de bloquear.

### Señales Más Afectadas por D2/D3

| Señal | Sign Flips | Amplifiers | Total | Veredicto |
|---|---|---|---|---|
| **vvix_entry** | 5 | 4 | 9 | **MÁS SENSIBLE** — D2/D3 cambia todo |
| **pcr_put_panic** | 3 | 3 | 6 | Muy sensible a D3 de skew y pcr |
| **capitulacion** | 3 | 2 | 5 | D3 de bsi y D2 de fg son críticos |
| **credit_stress** | 3 | 1 | 4 | D2 de credit y vix son críticos |
| **dxy_bearish** | 2 | 2 | 4 | D2 de dxy y vix invierten |
| **bsi_washed_out** | 2 | 1 | 3 | D2 de fg y D3 de bsi amplifican |

---

## 4. PRECURSORES DE CRASH — Forense Unificado

> **Fusión del forense de Claude Opus (lift sobre estado) con el análisis del analista (FA rate, asimetría).**

### 🔴 Precursor Universal #1: credit.D2=ACCELERATING_UP_3D

| Métrica | Valor |
|---|---|
| Señales afectadas | **5/6** (credit_easing, pcr_put_panic, credit_stress, bsi_washed_out, capitulacion) |
| Lift medio | **4.1×** (rango 2.1×–11.2×) |
| Interpretación | Credit spread SUBIENDO rápido = estrés crediticio acelerando. Renta fija NO confirma el bottom. |
| Mecánica | Dalio: "the credit impulse leads equities by 3-6 months." |

### 🔴 Top 5 Precursores Universales (aparecen en ≥4 señales)

| # | Estado | Señales | Lift medio | Interpretación |
|---|---|---|---|---|
| 1 | `credit.D2=ACCEL_UP` | **5/6** | **4.1×** | Estrés crediticio acelerando — precursor más universal |
| 2 | `vix.D2=DECEL_DOWN` | **4/6** | **2.0×** | VIX bajando pero frenándose — floor de volatilidad |
| 3 | `skew.D3=VOL_EXPANSION` | **4/6** | **2.5×** | Volatilidad del SKEW expandiéndose — puts OTM con urgencia |
| 4 | `skew.D3=VOL_PEAK` | **4/6** | **3.0×** | SKEW en pico de inestabilidad — post-peak tail hedging |
| 5 | `sv5_turb.LOW×DECEL_DOWN` | **4/6** | **5.2×** | Calma institucional rompiéndose — smart money se mueve |

### 🟢 Protectores Universales (estados que NUNCA crashean)

| Estado | Señales protegidas | W/L |
|---|---|---|
| `vix.D2=STABLE_CONT` | credit_easing, pcr_put_panic | Innumerables wins, 0 losses |
| `vix.D3=VOL_COMPRESSION` | credit_easing | 21W, 0L |
| `vvix.D1=EXTREME_VVIX` | credit_easing | 12W, 0L |
| `pcr.D3=VOL_COMPRESSION` | pcr_put_panic | 7W, 0L |
| `credit.D1×D2=ELEV×DECEL_DOWN` | bsi_washed_out | 11W, 1L |

---

## 5. FALSAS ALARMAS — Costo de Actuar vs Costo de Ignorar

> **TODAS las señales con WR > 50% tienen ratio NO-actuar/Actuar > 1.** Ignorar la señal es siempre más caro que actuar.

| Señal | N | WR | Mean Win | Mean Loss | FA Rate | Costo Actuar | Costo NO Actuar | **Ratio** | Veredicto |
|---|---|---|---|---|---|---|---|---|---|
| **credit_easing_k1** | 112 | 93.8% | +5.91% | -5.66% | 6.2% | 0.37% | 5.66% | **15.3×** | ✅ GANA ACTUAR |
| **pcr_put_panic** | 70 | 71.4% | +6.30% | -6.29% | 28.6% | 1.80% | 6.29% | **3.5×** | ✅ GANA ACTUAR |
| **bsi_washed_out** | 161 | 65.8% | +6.14% | -7.67% | 34.2% | 2.10% | 7.67% | **3.7×** | ✅ GANA ACTUAR |
| **credit_stress** | 215 | 54.9% | +6.48% | -5.67% | 45.1% | 2.92% | 5.67% | **1.9×** | ✅ GANA ACTUAR |
| **vvix_entry** | 91 | 62.6% | +6.52% | -6.38% | 37.4% | 2.44% | 6.38% | **2.6×** | ✅ GANA ACTUAR |
| **capitulacion** | 82 | 65.9% | +6.91% | **-9.22%** | 34.1% | 2.36% | **9.22%** | **3.9×** | ✅ GANA ACTUAR |
| **fg_extreme_fear** | 54 | 68.5% | +5.70% | -7.40% | 31.5% | 1.80% | 7.40% | **4.1×** | ✅ GANA ACTUAR |
| **euforia** | 41 | 14.6% | +4.97% | -4.35% | 85.4% | 4.24% | 4.35% | **1.0×** | ⚠️ BORDE |
| **panico_total** | 34 | 58.8% | +5.61% | -4.39% | 41.2% | 2.31% | 4.39% | **1.9×** | ✅ GANA ACTUAR |
| **sorpresa_total** | 525 | 54.9% | +6.18% | -5.67% | 45.1% | 2.79% | 5.67% | **2.0×** | ✅ GANA ACTUAR |

### Hallazgos Clave

1. **capitulacion** tiene el mayor costo de NO actuar (-9.22%) — ignorar esta señal es 3.9× más caro que actuar.
2. **credit_easing_k1** tiene el ratio más extremo (15.3×) — casi nunca falla, pero cuando falla, duele.
3. **credit_stress** tiene el ratio más bajo (1.9×) — sigue siendo favorable pero marginal.
4. **euforia** está en el borde (1.0×) — consistente con su naturaleza de señal de techo.

### Asimetría Ganancia/Pérdida — El Factor Oculto

| Señal | Mean Win | Mean Loss | **Asimetría** | Interpretación |
|---|---|---|---|---|
| **capitulacion** | +6.91% | -9.22% | **1.33×** | Pierdes 33% más que ganas → **ALTO VALOR DEFENSIVO** |
| **fg_extreme_fear** | +5.70% | -7.40% | **1.30×** | Pierdes 30% más → **ALTO VALOR DEFENSIVO** |
| **bsi_washed_out** | +6.14% | -7.67% | **1.25×** | Pierdes 25% más → **VALOR DEFENSIVO** |
| **vvix_entry** | +6.52% | -6.38% | 0.98× | Simétrico → edge ofensivo ≈ edge defensivo |
| **pcr_put_panic** | +6.30% | -6.29% | 1.00× | Perfectamente simétrico |
| **credit_stress** | +6.48% | -5.67% | 0.87× | Ganas más que pierdes → **edge OFENSIVO** |
| **credit_easing_k1** | +5.91% | -5.66% | 0.96× | Casi simétrico → **edge OFENSIVO** |

> **Regla de Asimetría:** Señales con asimetría > 1.2× tienen edge defensivo SUBESTIMADO por el marco antiguo. `capitulacion` (1.33×), `fg_extreme_fear` (1.30×), `bsi_washed_out` (1.25×) son las más infravaloradas.

---

## 6. EDGE DEFENSIVO GRADUADO — Ranking Final

### Tabla Completa de Edge Defensivo

| Señal | N | WR | \|Loss\| | FA₂₅ | **ED₂₅** | **ED₅₀** | **ED₇₅** | BaseED | ×Base |
|---|---|---|---|---|---|---|---|---|---|
| **credit_easing_k1** | 112 | 93.8% | 5.66% | 6.2% | **5.29%** | 5.17% | 5.01% | 4.38% | 1.2× |
| **pcr_put_panic** | 70 | 71.4% | 6.29% | 28.6% | **4.49%** | 4.32% | 4.24% | 1.99% | **2.3×** |
| **bsi_washed_out** | 161 | 65.8% | 7.67% | 34.2% | **5.58%** | 5.49% | 5.61% | 1.78% | **3.1×** |
| **credit_stress** | 215 | 54.9% | 5.67% | 45.1% | **2.74%** | 2.76% | 2.97% | 1.98% | 1.4× |
| **vvix_entry** | 91 | 62.6% | 6.38% | 37.4% | **3.94%** | 3.90% | 3.72% | 1.98% | **2.0×** |
| **capitulacion** | 82 | 65.9% | **9.22%** | 34.1% | **6.86%** | 6.92% | 7.13% | 1.89% | **3.6×** |
| **fg_extreme_fear** | 54 | 68.5% | 7.40% | 31.5% | **5.61%** | 5.50% | 5.36% | 1.97% | **2.9×** |
| **euforia** | 41 | 14.6% | 4.35% | 85.4% | **0.11%** | -0.32% | 0.10% | 2.13% | 0.1× |
| **panico_total** | 34 | 58.8% | 4.39% | 41.2% | **2.08%** | 2.25% | 2.35% | 2.05% | 1.0× |
| **sorpresa_total** | 525 | 54.9% | 5.67% | 45.1% | **2.88%** | 2.88% | 2.88% | 1.74% | 1.7× |

### Graduated Response por Señal

#### capitulacion — Score de Riesgo

| Score | N | WR | Fwd mean | Acción |
|---|---|---|---|---|
| **0** | 62 | **75.8%** | +3.17% | Full size |
| **1** | 16 | 43.8% | -2.32% | **Exit** — ya no hay edge |
| **≥2** | 4 | **0.0%** | **-11.17%** | 🚨 **CIRCUIT BREAKER** |

#### credit_easing_k1 — Score de Riesgo

| Score | N | WR | Fwd mean | Acción |
|---|---|---|---|---|
| **0** | 82 | **100.0%** | +6.05% | Full size |
| **1** | 29 | 79.3% | +3.10% | Reduce 33% |
| **≥2** | 1 | — | — | Hedge o exit |

#### credit_stress — Score de Riesgo

| Score | N | WR | Fwd mean | Acción |
|---|---|---|---|---|
| **0** | 195 | 57.9% | +1.25% | Operable (pero ver duration) |
| **1** | 20 | **25.0%** | **-1.39%** | **Exit** |

#### pcr_put_panic — Score de Riesgo

| Score | N | WR | Fwd mean | Acción |
|---|---|---|---|---|
| 0 | 46 | **80.4%** | +3.97% | Full size |
| 1 | 15 | 60.0% | +1.04% | Reduce 50% |
| **2** | 8 | **50.0%** | **-0.74%** | Hedge |

#### bsi_washed_out — Score de Riesgo

| Score | N | WR | Fwd mean | Acción |
|---|---|---|---|---|
| 0 | 137 | **70.1%** | +1.99% | Full size |
| **1** | 23 | **39.1%** | **-2.08%** | **Exit** |

---

## 7. TABLA FINAL INTEGRADA

> **Formato solicitado: señal | perfil | edge_ofensivo | edge_defensivo | precursor_Nlose | veredicto**

| # | Señal | Perfil | Edge Ofensivo | Edge Defensivo | Precursor N_lose | Veredicto |
|---|---|---|---|---|---|---|
| 1 | **credit_easing_k1** | ⚔️ OFENSIVA | +5.19% (CI95✅) | 5.29% (1.2×) | sv5.D2=SPIKE (N=3), vix.D2=ACCEL (N=4) | ✅ **MANTENER** — estrella ofensiva, 93.8% WR, edge defensivo modesto pero real. Precursor FA=0% en sv5_turb para alerta máxima. |
| 2 | **capitulacion** | 🛡️ **DEFENSIVA PURA** | +1.40% (CI95❌) | **6.86% (3.6×)** 📊 | credit.D2=ACCEL (N=5), skew.D3=VOL_EXP (N=10) | ✅ **MANTENER** — mejor protección del sistema. CI95 no pasa en marco antiguo pero ED es el más alto. **OJO: colapsando en 2020s.** |
| 3 | **bsi_washed_out** | 🛡️⚔️ **DUAL** | +1.42% (CI95✅) | **5.58% (3.1×)** 📊 | credit.D2=ACCEL (N=8), vix.D3=SQUEEZE (N=3, FA=0%) | ✅ **MANTENER** — combinación ofensivo+defensivo más equilibrada. Edge decay leve en 2020s. |
| 4 | **fg_extreme_fear** | 🛡️ **DEFENSIVA** | — (CI95❌) | **5.61% (2.9×)** 📊 | vix.D2=ACCEL (N=3) | ✅ **MANTENER** — infravalorada por marco antiguo. N=54, ED alto. Monitorear estabilidad. |
| 5 | **pcr_put_panic** | 🛡️⚔️ **MIXTA** | +2.70% (CI95✅) | 4.49% (2.3×) | credit.D2=CRUSH (N=4, FA=0%), sv5.D2=SPIKE (N=4) | ⚠️ **MONITOREAR** — WR 56% en 2020s vs 70-76% histórico. ED probable caído a ~2-3%. |
| 6 | **vvix_entry** | ⚔️ OFENSIVA | +1.70% (CI95✅) | 3.94% (2.0×) | vvix.D3=VOL_EXP (N=15) | ✅ **MANTENER** — más sensible a D2/D3 (9 splits). Estable en 2020s. Usar con filtro D3. |
| 7 | **sorpresa_total** | ⚔️ OFENSIVA DÉBIL | — | 2.88% (1.7×) | credit.D2=ACCEL (N=13) | ✅ **MANTENER CON RESERVAS** — N=525, el más grande. Edge modesto pero consistente. |
| 8 | **credit_stress** | ⚔️ OFENSIVA DÉBIL | +1.00% (CI95✅) | 2.74% (1.4×) | bsi.D2=ACCEL (N=13), pcr.D1=NEUTRAL (N=20) | ⚠️ **FILTRO OBLIGATORIO** — duration ≤2b = CERO edge. Solo operable con piernas >2b. ED marginal. |
| 9 | **panico_total** | NEUTRA | +1.49% (CI95❌) | 2.08% (1.0×) | skew.D3=VOL_EXP (N=5) | ❌ **EN REVISIÓN** — N=34, no mejora al baseline. Sin CI95, sin ED superior. |
| 10 | **euforia** | 🔻 TOPE | **-2.99%** (CI95✅ SHORT) | 0.11% (0.1×) | — (señal inversa) | ✅ **MANTENER** — solo como señal de techo (SHORT), no como protección. WR=14.6%, edge negativo significativo. |
| 11 | **dxy_bearish** | ❌ DESCARTADA | -0.04% (CI95❌) | — | vix.D2=ACCEL (N=2) | ❌ **DESCARTAR** — edge ≈ 0, sin CI95, N pequeño. |
| 12 | **sub_reaccion** | ⚠️ CONDICIONAL | +0.39% (CI95❌) | — | — | ⚠️ **CONDICIONAL** — operable SOLO con duration >4b. Sin eso, edge ≈ 0. |

### Categorías de Perfil

| Categoría | Condición | Señales |
|---|---|---|
| 🛡️ **DEFENSIVA PURA** | ED > 5% y ×Base > 2.5× | capitulacion, bsi_washed_out, fg_extreme_fear |
| ⚔️ **OFENSIVA** | ED > 3% pero ×Base < 2× | credit_easing_k1, vvix_entry |
| 🛡️⚔️ **MIXTA** | ED > 4% y ×Base > 2× | pcr_put_panic |
| ⚔️ **OFENSIVA DÉBIL** | ED < 3% pero > BaseED | credit_stress, sorpresa_total |
| ⚠️ **EN REVISIÓN** | ED ≈ BaseED | panico_total |
| 🔻 **ESPECIAL** | ED = 0 (señal de techo) | euforia |
| ❌ **DESCARTADA** | Edge ≈ 0 | dxy_bearish |
| ⚠️ **CONDICIONAL** | Solo operable con filtro | sub_reaccion |

---

## 8. ESTABILIDAD POR DÉCADA — Degradación 2020s

> **Claude Opus aporta el breakdown por década que el analista previo ya incorporaba. Confirmación cruzada.**

### WR por Década

| Señal | 1990s | 2000s | 2010s | 2020s | Tendencia |
|---|---|---|---|---|---|
| **credit_easing_k1** | — | 89% | 100% | 94% | ✅ MUY ESTABLE |
| **bsi_washed_out** | 56% | 68% | 70% | 60% | ✅ ESTABLE (con ruido) |
| **capitulacion** | 60% | 66% | 76% | **57%** | ⚠️ **BAJÓ en 2020s** |
| **credit_stress** | — | 51% | 62% | 49% | ✅ ESTABLE (rango 49-62%) |
| **vvix_entry** | — | — | 65% | 62% | ✅ MUY ESTABLE |
| **pcr_put_panic** | — | 70% | 76% | **56%** | 🔴 **SE DEBILITÓ en 2020s** |
| **fg_extreme_fear** | — | — | 73% | 62% | ⚠️ BAJÓ en 2020s |
| **euforia** | 10% | 29% | 6% | — | ✅ ESTABLE (bajista) |

### Edge Ofensivo por Década

| Señal | 1990s | 2000s | 2010s | 2020s |
|---|---|---|---|---|
| `bsi_washed_out` | -0.43% (N=9) | +1.73% (N=51) | +1.58% (N=52) | +0.59% (N=41) |
| `credit_stress` | — | +0.52% (N=65) | +1.63% (N=87) | +0.77% (N=61) |
| `capitulacion` | -0.41% (N=3) | +1.32% (N=31) | +0.77% (N=13) | **+0.12%** (N=18) |
| `vvix_entry` | — | — | +0.79% (N=12) | +1.55% (N=71) |
| `pcr_put_panic` | — | +2.33% (N=17) | +3.53% (N=23) | **+0.20%** (N=27) |

### 🔴 Riesgo: Degradación de señales clave en 2020s

1. **pcr_put_panic**: WR 76% → 56%, edge ofensivo +3.53% → +0.20%. Pérdida dramática de eficacia. Posible causa: el mercado arbitró la señal post-COVID o la dinámica de PCR cambió con el aumento de opciones 0DTE.

2. **capitulacion**: WR 76% → 57%, edge ofensivo +0.77% → +0.12%. Colapsando. Su ED en 2020s probablemente es mucho menor que el histórico de 6.86%. La pregunta es si el ED defensivo todavía protege aunque el ofensivo decayó.

3. **fg_extreme_fear**: WR 73% → 62%. Bajó pero sigue siendo operable. Monitorear.

---

## 9. CONFLUENCIA CROSS-SEÑAL — Aditividad vs Redundancia

> **Ambos reportes confirman: NO toda confluencia es aditiva.**

### Confluencias Aditivas (el todo > suma de partes)

| Combo | N | WR | mean_ambas | solo_a | solo_b | Aditividad |
|---|---|---|---|---|---|---|
| credit_easing_k1 × vvix_entry | 12 | **100%** | **+7.11%** | +4.96% | +0.88% | **ADITIVA** 🏆 |
| credit_easing_k1 × credit_stress | 20 | **95%** | **+6.62%** | +4.88% | +0.42% | **ADITIVA** 🏆 |
| credit_easing_k1 × pcr_put_panic | 10 | **90%** | **+6.08%** | +5.10% | +2.14% | **ADITIVA** 🏆 |
| bsi_washed_out × credit_easing_k1 | 17 | **94%** | **+5.72%** | +0.92% | +5.09% | **ADITIVA** 🏆 |
| pcr_put_panic × vvix_entry | 13 | 77% | +3.76% | +2.46% | +1.36% | **ADITIVA** ✅ |
| credit_stress × pcr_put_panic | 21 | 81% | +3.71% | +0.71% | +2.27% | **ADITIVA** ✅ |
| capitulacion × vvix_entry | 21 | 67% | +2.19% | +1.13% | +1.55% | **ADITIVA** ✅ |

### Confluencias Redundantes (el todo ≈ la parte)

| Combo | Overlap | Solo Sig1 | Solo Sig2 | AMBAS | Aditividad |
|---|---|---|---|---|---|
| bsi × vvix | 31 (34%) | +1.39% WR=67% | +1.78% WR=63% | +1.55% WR=61% | ❌ **REDUNDANTE** |
| bsi × credit | 54 (34%) | +1.39% WR=66% | +0.84% WR=52% | +1.49% WR=65% | ❌ **REDUNDANTE** |
| capitulacion × credit | 32 (39%) | +1.48% WR=66% | +0.95% WR=53% | +1.28% WR=66% | ❌ **REDUNDANTE** |

> **Hallazgo clave:** `credit_easing_k1` es el amplificador universal. Cualquier señal combinada con ella multiplica el edge. Pero `bsi + credit` y `bsi + vvix` son redundantes — el overlap no mejora el edge. `capitulacion + vvix_entry` es la única confluencia aditiva sin credit_easing.

---

## 10. PUNTOS CIEGOS — Lo que NINGÚN REPORTS CUBRIÓ

> Los 7 reportes de Claude Opus y el analista previo cubren extensamente D2/D3, falsas alarmas, edge defensivo, y precursores. Sin embargo, hay **8 puntos ciegos que AMBAS fuentes omiten**.

### 🔴 Punto Ciego 1 — Overfitting risk de precursores con N_lose=3-5

**Problema:** Ambos reportes aceptan precursores con N_lose=3-5 como "diamantes" válidos. Pero ninguno evalúa:
- ¿Cuántos de estos predictores perfectos (FA=0%) son genuinos vs casualidad?
- Con 141 columnas × 150 combinaciones D2/D3 ≈ 21,150 estados posibles, es esperable que ~21 tengan FA=0% por pura combinatoria.
- **Ningún test de Bonferroni o FDR** se aplicó para ajustar por multiplicidad.

**Impacto:** Potencial sobreajuste severo. Un precursor "perfecto" con N=3 tiene 1/8 probabilidad de acertar 3/3 por azar si la tasa base es 50%.

**Mitigación:** Validación walk-forward OOS. Dividir en training (1993-2015) y test (2016-2026). Reportar cuántos precursores sobreviven.

### 🔴 Punto Ciego 2 — Costos de transacción y slippage

**Problema:** Ningún reporte modela:
- Spread bid-ask (especialmente en opciones y futuros)
- Slippage en ejecución (señales en VIX extremo = alta volatilidad = peor fill)
- Comisiones por trade
- **Impacto en señales de alta frecuencia** (duration_bars=1 significa entrar y salir rápido = costos multiplicados)

**Impacto:** Un edge de +1.0% con 50% WR puede desaparecer con 0.10% de slippage por trade. El edge defensivo de -9.22% evitado es nominal — el costo real de actuar incluye spread+slippage.

**Mitigación:** Simular equity curves con slippage de 5-15bps, spread de 2-10bps, comisión flat.

### 🟡 Punto Ciego 3 — Dependencia entre precursores (multicolinealidad)

**Problema:** Los precursores no son ortogonales. Ejemplos:
- `credit.D2=ACCEL_UP` y `skew.D3=VOL_EXP` ocurren juntos en crisis crediticias ~70% del tiempo
- `vix.D2=DECEL_DOWN` y `sv5_turb.LOW×DECEL_DOWN` miden el mismo fenómeno (desaceleración de volatilidad)
- El graduated response suma precursores como si fueran independientes — pero no lo son

**Impacto:** El score de riesgo sobreestima la señal cuando múltiples precursores reflejan el mismo fenómeno subyacente.

**Mitigación:** Calcular matriz de correlación entre precursores. Usar PCA o factor analysis para reducir dimensiones.

### 🟡 Punto Ciego 4 — Efectividad por régimen de volatilidad agregado

**Problema:** Los precursores se evalúan sobre todo el período (1993-2026), pero no se condicionan por:
- VIX en nivel bajo (<15) vs alto (>25)
- Mercado alcista vs bajista (bear market definido por -20% desde máximo)
- Ciclo de la Fed (easing, tightening, neutral)
- Regímenes macro (inflación alta, deflación, stagflation)

**Impacto:** Un precursor puede funcionar solo en bear markets (donde hay crashes) y ser noise en bull markets. Pero se reporta un lift promedio que mezcla ambos regímenes.

**Mitigación:** Desglosar lift y ED por régimen de VIX (bajo/medio/alto/crisis). Esto diría: "credit.D2=ACCEL_UP tiene lift 8× en VIX>25, pero solo 1.2× en VIX<15".

### 🟡 Punto Ciego 5 — Sesgo de supervivencia en datos históricos

**Problema:** El dataset 1993-2026 incluye:
- Instrumentos que ya no existen (índices con pesos diferentes)
- Estructura de mercado que cambió drásticamente (HFT, 0DTE, ETFs masivos)
- Regímenes que no volverán (GFC 2008, COVID 2020)

**Impacto:** Las señales y precursores identificados en 1990s-2000s pueden no ser replicables en el mercado actual. El colapso de `pcr_put_panic` en 2020s podría ser la punta del iceberg.

**Mitigación:** Peso decreciente a datos pre-2010. Validar señales solo en 2015-2026 como período moderno.

### 🟡 Punto Ciego 6 — Costo psicológico de falsas alarmas repetidas

**Problema:** El marco ED asume que un trader actuará consistentemente cada vez que un precursor se active. Pero con FA rate de 34-45%, un trader recibirá 3-5 falsas alarmas por cada acierto real. La fatiga de alarmas es un fenómeno documentado: la sensibilidad a la señal decrece con cada falso positivo.

**Impacto:** En la práctica, el edge defensivo real es menor que el teórico porque el trader no ejecutará consistentemente después de múltiples FA.

**Mitigación:** Modelar la probabilidad de acción como función decreciente de FA_rate. Ajustar ED con factor de cumplimiento realista.

### 🟡 Punto Ciego 7 — No hay backtest fuera de muestra (OOS) del sistema completo

**Problema:** Todos los análisis son **in-sample** sobre el mismo dataset:
- Las señales se definieron sobre estos datos
- Los precursores se identificaron sobre estos datos
- El ED se calculó sobre estos datos
- Los thresholds de graduated response se calibraron sobre estos datos

**No hay una sola partición train/test ni walk-forward analysis en ninguno de los 8 reportes.**

**Impacto:** Riesgo extremo de overfitting. El sistema completo (señales + precursores + graduated response) podría tener performance significativamente menor OOS.

**Mitigación:** Implementar walk-forward validation con ventana de 5 años de training, 1 año de test. Reportar Sharpe OOS.

### 🟡 Punto Ciego 8 — Efecto compuesto en equity curve

**Problema:** Todos los análisis usan **mean forward return por trade**. Nadie simula:
- Equity curve compuesta de operar cada señal consistentemente
- Maximum drawdown del sistema completo
- Sharpe ratio real (no por trade, por tiempo calendario)
- Kelly criterion para sizing óptimo

**Impacto:** Un edge de +0.39% con WR=50.2% en 667 trades (sub_reaccion) NO es lo mismo que +1.42% con WR=65.8% en 161 trades (bsi_washed_out). El segundo tiene drawdowns menores y compounding más estable.

**Mitigación:** Simular equity curve con todas las señales combinadas, con sizing por Kelly fraccional. Reportar Sharpe, Calmar, Max DD.

### Mapa de Puntos Ciegos No Cubiertos

| # | Punto Ciego | Severidad | Impacto | Prioridad |
|---|---|---|---|---|
| 1 | **Overfitting precursores N=3-5** | 🔴 Alta | Sobreestimación masiva de lift | **Inmediato** |
| 2 | **Costos de transacción/slippage** | 🔴 Alta | Edge nominal ≠ edge real | **Inmediato** |
| 3 | **Multicolinealidad de precursores** | 🟡 Media | Score de riesgo inflado | Corto plazo |
| 4 | **Efectividad por régimen** | 🟡 Media | Precursor puede ser ruido en bull | Corto plazo |
| 5 | **Sesgo de supervivencia** | 🟡 Media | Datos pre-2010 no replicables | Corto plazo |
| 6 | **Costo psicológico de FA** | 🟡 Media | ED teórico > ED real | Mediano |
| 7 | **Sin backtest OOS** | 🔴 **Crítica** | Sistema entero puede no funcionar | **Inmediato** |
| 8 | **Sin equity curve compuesta** | 🔴 Alta | No se conoce drawdown real | Corto plazo |

---

## 11. RECOMENDACIONES OPERACIONALES

### Prioridad Inmediata (esta semana)

1. **Corregir bugs de medir_senal.py**: Renombrar anticipación → persistencia_cluster. Corregir capture ratio.
2. **Filtro credit_stress**: Bloquear si `duration_bars ≤ 2` — elimina el pool con CERO edge.
3. **Validación OOS del sistema completo**: Implementar walk-forward. Sin esto, no sabemos si los precursores funcionan fuera de la muestra donde se descubrieron.
4. **Simular equity curve con costos**: Agregar slippage 10bps, spread 5bps. Comparar Sharpe con y sin sistema de precursores.

### Prioridad Corto Plazo (este mes)

5. **D2/D3 como filtro contextual**: No como bloqueo duro, sino como modificador de sizing. Si D2/D3 apunta a favorable → full size. Si apunta a desfavorable → reduce 50%.
6. **Graduated response por señal**: Implementar RISK_SCORE con pesos diferenciados (no todos los precursores pesan igual).
7. **Monitorear pcr_put_panic y capitulacion**: Si WR 2020s sigue cayendo, considerar retirar o reducir peso significativamente.
8. **Matriz de correlación de precursores**: Evitar double-counting en el score de riesgo.

### Prioridad Mediano Plazo

9. **Desglose por régimen de VIX**: Evaluar lift de precursores condicionado a VIX bajo/medio/alto.
10. **Kelly sizing por señal**: Asignar capital óptimo según edge y volatilidad.
11. **Modelo de fatiga de FA**: Ajustar ED teórico por probabilidad realista de acción tras N falsas alarmas consecutivas.
12. **Fact store consistency**: Validar señales contra ev_net y pbull de los fact stores.

---

## 12. ANEXO: Precursores FA=0%

> **Precursores con 0 falsas alarmas en la muestra histórica. Son los más valiosos del sistema.**

| Señal | Precursor | Lift | N_lose | FA | ¿Operable? |
|---|---|---|---|---|---|
| credit_stress | pcr.d1=EXTREME_CALL_HEAVY | 10.00× | 3 | 0% | ✅ Alerta — N=3 requiere confirmación |
| credit_stress | sv5_turb.d1=CRISIS_TURBULENCE | 8.58× | 5 | 0% | ✅ **OPERACIONAL** — N=5, FA=0%, robusto |
| credit_stress | dxy.d3=VOL_PEAK_DECELERATION | 10.00× | 3 | 0% | ✅ Alerta |
| bsi_washed_out | vix.d3=VOL_EXTREME_SQUEEZE | 10.00× | 3 | 0% | ✅ Alerta |
| bsi_washed_out | sv5_turb.LOW_TURB×DECEL_DOWN | 7.00× | 5 | 0% | ✅ **OPERACIONAL** — N=5, FA=0% |
| credit_easing_k1 | credit.d3=VOL_ACCEL_EXPANSION | 5.00× | 3 | 25% | ⚠️ Contextual — tiene 1 FA |
| credit_easing_k1 | sv5_turb.d2=FAST_SPIKE_3D | 11.25× | 3 | 25% | ⚠️ Contextual — tiene 1 FA |

### Regla para FA=0%

| N_lose | Clasificación | Acción |
|---|---|---|
| ≥5 | **OPERACIONAL** | Actuar directamente. Probabilidad de coincidencia < 3% |
| 3-4 | **ALERTA** | Actuar si hay confirmación macro o cross-señal |
| <3 | **ANÉCDOTA** | No actuar |

---

## Notas Metodológicas

- **Edge Defensivo = |mean_loss| - (mean_win × FA_rate)**
  - ED > 0 → la señal vale la pena
  - ED > BaseED → la señal tiene edge real vs no tener señal
- **BaseED** = |baseline_mean_loss| - (baseline_mean_win × (1 - baseline_WR))
  - Representa el edge defensivo del mercado aleatorio
- **Lift** (Claude Opus) = P(estado | LOSER) / P(estado | WINNER)
  - > 1.5 → estado sobrerepresentado en crashes = PRECURSOR
- **Lift** (Analista) = Precision / Base_Crash_Rate
  - Mide cuántas veces mejor que el azar es el precursor
- **Asymmetry Ratio = |mean_loss| / mean_win**
  - > 1.2× → señal defensiva subestimada por marco antiguo
- **Bootstrapping**: 3000 iteraciones, seed=42 para CI95 de spread
- **Precursores**: lift ≥ 1.5 con N_lose ≥ 3
- **Sign Flips**: spread > 2pp entre la mejor y peor rama D2/D3
- **FA=0%**: señal válida cuando N_lose ≥ 5 (protector perfecto en muestra)

---

*Documento generado por integración de 7 reportes Claude Opus + 1 reporte analista previo.*
*Agosto 2026 — Botero Trade Research*