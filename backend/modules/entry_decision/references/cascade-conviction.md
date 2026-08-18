# Reevaluación Integrada — Marco Corregido: Edge Defensivo + Forense Cuantitativo
## Módulo Entry Decision — Botero Trade Engine
**Fecha de Análisis:** Agosto de 2026  
**Estatus:** Referencia Estadística de Dominio  

> **INTEGRACIÓN DE 7 REPORTES CLAUDE OPUS + 1 REPORTE ANALISTA PREVIO**
>
> Fuentes integradas:
> 1. `falsas_alarmas_precursores.md` — Precision/Recall de 32 combinaciones señal×precursor
> 2. `edge_defensivo_graduado.md` — Marco ED, Lift, graduated response
> 3. `puntos_ciegos_adicionales.md` — Bootstrap CI, estabilidad década, cross-overlap, duration_bars
> 4. `determinismo_d2d3.md` — 20 sign flips D2/D3, vvix_entry más sensible
> 5. `audit_medir_senal.md` — 2 bugs activos, 5 blind spots de medir_senal.py
> 6. `diagnostico_consolidado_señales.md` — Ranking 10 señales, CI95, duración, década
> 7. `forense_precursores_crash.md` — 86 precursores, lift, protectores, FA=0%
> 8. `analisis_estadistico_profundo.md` — Reevaluación marco corregido, ED, asimetría

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
10. [PUNTOS CIEGOS — Lo que Ningún Reporte Cubrió](#10-puntos-ciegos--lo-que-ningún-reporte-cubrió)
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

---

## 2. BUGS ACTIVOS DE medir_senal.py

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
> _D2 (velocidad) es más determinante que D3 (volatilidad de estación): 13 flips D2 vs 7 flips D3._

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

---

## 4. PRECURSORES DE CRASH — Forense Unificado

### 🔴 Precursor Universal #1: credit.D2=ACCELERATING_UP_3D

| Métrica | Valor |
|---|---|
| Señales afectadas | **5/6** (credit_easing, pcr_put_panic, credit_stress, bsi_washed_out, capitulacion) |
| Lift medio | **4.1×** (rango 2.1×–11.2×) |
| Interpretación | Credit spread SUBIENDO rápido = estrés crediticio acelerando. Renta fija NO confirma el bottom. |
| Mecánica | Dalio: *"the credit impulse leads equities by 3-6 months."* |

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

> **TODAS las señales con WR > 50% tienen ratio NO-actuar/Actuar > 1.** Ignorar la señal es siempre más costoso que actuar.

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

### Asimetría Ganancia/Pérdida

| Señal | Mean Win | Mean Loss | **Asimetría** | Interpretación |
|---|---|---|---|---|
| **capitulacion** | +6.91% | -9.22% | **1.33×** | Pierdes 33% más que ganas → **ALTO VALOR DEFENSIVO** |
| **fg_extreme_fear** | +5.70% | -7.40% | **1.30×** | Pierdes 30% más → **ALTO VALOR DEFENSIVO** |
| **bsi_washed_out** | +6.14% | -7.67% | **1.25×** | Pierdes 25% más → **VALOR DEFENSIVO** |
| **vvix_entry** | +6.52% | -6.38% | 0.98× | Simétrico → edge ofensivo ≈ edge defensivo |
| **pcr_put_panic** | +6.30% | -6.29% | 1.00× | Perfectamente simétrico |
| **credit_stress** | +6.48% | -5.67% | 0.87× | Ganas más que pierdes → **edge OFENSIVO** |
| **credit_easing_k1** | +5.91% | -5.66% | 0.96× | Casi simétrico → **edge OFENSIVO** |

---

## 6. EDGE DEFENSIVO GRADUADO — Ranking Final

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

---

## 7. TABLA FINAL INTEGRADA

| # | Señal | Perfil | Edge Ofensivo | Edge Defensivo | Precursor N_lose | Veredicto |
|---|---|---|---|---|---|---|
| 1 | **credit_easing_k1** | ⚔️ OFENSIVA | +5.19% (CI95✅) | 5.29% (1.2×) | sv5.D2=SPIKE (N=3), vix.D2=ACCEL (N=4) | ✅ **MANTENER** — estrella ofensiva, 93.8% WR. |
| 2 | **capitulacion** | 🛡️ **DEFENSIVA PURA** | +1.40% (CI95❌) | **6.86% (3.6×)** | credit.D2=ACCEL (N=5), skew.D3=VOL_EXP (N=10) | ✅ **MANTENER** — mejor protección del sistema. Ojo: colapsando en 2020s. |
| 3 | **bsi_washed_out** | 🛡️⚔️ **DUAL** | +1.42% (CI95✅) | **5.58% (3.1×)** | credit.D2=ACCEL (N=8), vix.D3=SQUEEZE (N=3, FA=0%) | ✅ **MANTENER** — combinación ofensivo+defensivo más equilibrada. |
| 4 | **fg_extreme_fear** | 🛡️ **DEFENSIVA** | — (CI95❌) | **5.61% (2.9×)** | vix.D2=ACCEL (N=3) | ✅ **MANTENER** — N=54, ED alto. Monitorear estabilidad. |
| 5 | **pcr_put_panic** | 🛡️⚔️ **MIXTA** | +2.70% (CI95✅) | 4.49% (2.3×) | credit.D2=CRUSH (N=4, FA=0%), sv5.D2=SPIKE (N=4) | ⚠️ **MONITOREAR** — WR 56% en 2020s vs 70-76% histórico. |
| 6 | **vvix_entry** | ⚔️ OFENSIVA | +1.70% (CI95✅) | 3.94% (2.0×) | vvix.D3=VOL_EXP (N=15) | ✅ **MANTENER** — sensible a D2/D3. Estable en 2020s. |
| 7 | **sorpresa_total** | ⚔️ OFENSIVA DÉBIL | — | 2.88% (1.7×) | credit.D2=ACCEL (N=13) | ✅ **MANTENER CON RESERVAS** — N=525. |
| 8 | **credit_stress** | ⚔️ OFENSIVA DÉBIL | +1.00% (CI95✅) | 2.74% (1.4×) | bsi.D2=ACCEL (N=13), pcr.D1=NEUTRAL (N=20) | ⚠️ **FILTRO OBLIGATORIO** — duration ≤2b = CERO edge. |
| 9 | **panico_total** | NEUTRA | +1.49% (CI95❌) | 2.08% (1.0×) | skew.D3=VOL_EXP (N=5) | ❌ **EN REVISIÓN** — N=34, no mejora al baseline. |
| 10 | **euforia** | 🔻 TOPE | **-2.99%** (CI95✅ SHORT) | 0.11% (0.1×) | — (señal inversa) | ✅ **MANTENER** — solo como señal de techo (SHORT). |
| 11 | **dxy_bearish** | ❌ DESCARTADA | -0.04% (CI95❌) | — | vix.D2=ACCEL (N=2) | ❌ **DESCARTAR** — edge ≈ 0. |
| 12 | **sub_reaccion** | ⚠️ CONDICIONAL | +0.39% (CI95❌) | — | — | ⚠️ **CONDICIONAL** — operable SOLO con duration >4b. |

---

## 8. ESTABILIDAD POR DÉCADA — Degradación 2020s

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

---

## 9. CONFLUENCIA CROSS-SEÑAL — Aditividad vs Redundancia

### Confluencias Aditivas (El todo > Suma de partes)
- `credit_easing_k1 × vvix_entry`: N=12, **100% WR**, $+7.11\%$ forward mean (**ADITIVA** 🏆).
- `credit_easing_k1 × credit_stress`: N=20, **95% WR**, $+6.62\%$ forward mean (**ADITIVA** 🏆).
- `credit_easing_k1 × pcr_put_panic`: N=10, **90% WR**, $+6.08\%$ forward mean (**ADITIVA** 🏆).
- `bsi_washed_out × credit_easing_k1`: N=17, **94% WR**, $+5.72\%$ forward mean (**ADITIVA** 🏆).

### Confluencias Redundantes
- `bsi × vvix`: Overlap 34%, no incrementa el edge respecto a las señales individuales.
- `bsi × credit`: Overlap 34%, redundante en régimen de compresión.
- `capitulacion × credit`: Overlap 39%, redundante.

---

## 10. Puntos Ciegos y Recomendaciones Operacionales

1. **Corrección de Métricas de Medición:** Corregir en scripts de auditoría el cálculo de anticipación (renombrar a persistencia de cluster) y la semántica del capture ratio.
2. **Filtro de Duración Obligatorio:** En `credit_stress`, ignorar si `duration_bars ≤ 2` (elimina el pool con cero edge).
3. **Validación Walk-Forward OOS:** Evaluar señales completas en ventanas móviles de 5 años de calibración y 1 año fuera de muestra para prevenir sobreajuste.
4. **Dimensiones D2/D3 como Modificador de Sizing:** Utilizar sign flips no como bloqueos binarios sino como escalonamiento del tamaño de posición ($50\% - 100\%$).
