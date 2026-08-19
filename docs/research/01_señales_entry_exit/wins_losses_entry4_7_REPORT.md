# ESTUDIO WINS vs LOSSES — SV5T, VIX, BSI, CREDIT (ENTRY #4-7)

**Fecha:** 2026-08-16  
**Método:** state_key del METAR (D1__D2__D3), CI95 bootstrap 2000 iteraciones, NO promedia  
**Fuente:** `quants_obs.pkl` — 1,590 pivotes SPY zigzag zz25 (1993–2026)  
**Escalas:** D1 = nivel, D2 = velocidad Δ3d, D3 = volatilidad std(2d)/std(10d)

---

## RESUMEN EJECUTIVO

| Station | MIN N | MIN WR | MIN CI95 | MIN EV | MIN PF | MIN Kelly | MAX N | MAX WR | MAX EV | MAX Knife% |
|---------|-------|--------|----------|--------|--------|-----------|-------|--------|--------|------------|
| **SV5T** | 16 | 81.2% | [62.5%, 100.0%] | **5.34%** | 9.27 | +0.725 | 10 | 70.0% | 3.17% | 20.0% |
| **VIX** | 94 | 72.3% | [62.8%, 80.9%] | 2.94% | 2.47 | +0.431 | 77 | 62.3% | 1.93% | **39.0%** |
| **BSI** | 100 | **79.0%** | [71.0%, 86.0%] | 3.22% | 3.01 | +0.527 | 61 | 55.7% | 1.53% | 37.7% |
| **CREDIT** | **116** | 78.4% | [70.7%, 85.3%] | **3.44%** | 3.26 | +0.544 | **99** | **72.7%** | **1.86%** | 22.2% |

**Hallazgo principal:** Las 4 estaciones tienen EV positivo en MIN (entry LONG en miedo extremo). **CREDIT es la más robusta** (N=116, EV=3.44%, Kelly +0.544, CI95 estrecho). **VIX en MAX es la más peligrosa** (39% cuchillo cayendo, WR −23.3pp vs baseline).

---

## 1. SV5T — CRISIS_TURBULENCE (SV5_TURBULENCE)

### A. Win Rate
| Tipo | N | WR | CI95 | Baseline WR | Δ |
|------|---|------|------|-------------|-----|
| MIN | 16 | 81.2% | [62.5%, 100.0%] | 81.2% | +0.1% |
| MAX | 10 | 70.0% | [40.0%, 100.0%] | 81.4% | −11.4% |

⚠️ **N=16 (MIN) y N=10 (MAX) — muestra pequeña.** CI95 extremadamente ancho. No se puede tener alta confianza. El Δ vs baseline es esencialmente cero para MIN, negativo para MAX.

### B. Distribución WINS (MIN, n=13)
- mean=**7.37%**, median=5.44%, p25=4.45%, p75=6.76%, max=**20.84%**
- Los wins son sustanciales — la cola derecha es fuerte

### C. Distribución LOSSES (MIN, n=3)
- mean=−3.44%, maxloss=−4.97%
- **CERO wipeouts >20%**
- Las pérdidas son controladas (<5%)

### D. Profit Factor, Kelly, EV
- PF=**9.27**, Kelly=+0.725, EV=**5.34%** CI95=[2.5%, 8.4%], Sharpe=0.867
- **El EV más alto de las 4 estaciones** — pero con N=16, el CI95 es amplio

### E. Rachas
- Max win streak=**9**, max loss=2, avg win=4.3, avg loss=1.5
- Rachas ganadoras largas, rachas perdedoras cortas

### F. Timing vs Zigzag
- Pivot day return: mean=+2.06% (MIN), −3.02% (MAX)
- Costo al pivote: |return|=2.06% — se cede ~2% esperando confirmación
- **0% mismo día** — nunca se captura el pivote exacto

### G. Cuchillo Cayendo
- MIN: **0%** — nunca cuchillo
- MAX: 2 eventos (20%) → 2008-10-07 (−8.0%, VIX=53.7), 2025-04-09 (−10.1%, VIX=33.6)

### Top State Keys (MIN)
| State Key | N | WR | EV |
|-----------|----|------|------|
| CRISIS_TURBULENCE__ACCELERATING_UP_3D__VOL_NEUTRAL_BASELINE | 6 | 83.3% | 5.99% |
| CRISIS_TURBULENCE__STABLE_CONTINUATION_3D__VOL_NEUTRAL_BASELINE | 4 | 75.0% | 2.88% |

---

## 2. VIX — CRISIS_SPIKE (VIX)

### A. Win Rate
| Tipo | N | WR | CI95 | Baseline WR | Δ |
|------|---|------|------|-------------|-----|
| MIN | 94 | 72.3% | [62.8%, 80.9%] | 84.9% | **−12.5%** |
| MAX | 77 | 62.3% | [51.9%, 72.7%] | 85.6% | **−23.3%** |

⚠️ **VIX CRISIS_SPIKE DEGRADA la win rate en AMBOS tipos de pivote.** En MIN, −12.5pp: el miedo extremo hace que el mercado sea más impredecible que en condiciones normales. En MAX, −23.3pp: entrar SHORT durante un pico de VIX en un techo es muy mal negocio.

### B. Distribución WINS (MIN, n=68)
- mean=6.81%, median=6.06%, p25=4.92%, p75=8.07%, max=**26.26%**
- Distribución simétrica, wins sólidos

### C. Distribución LOSSES (MIN, n=26)
- mean=−7.21%, maxloss=−14.99%
- **CERO wipeouts >20%** — el downside está controlado incluso en crisis
- Las pérdidas son el doble de grandes que SV5T (−7.2% vs −3.4%)

### D. Profit Factor, Kelly, EV
- PF=2.47, Kelly=+0.431, EV=2.94% CI95=[1.5%, 4.3%], Sharpe=0.411
- EV positivo pero modesto. El CI95 no incluye cero → **estadísticamente significativo**

### E. Rachas
- Max win=8, max loss=2, avg win=3.0, avg loss=1.2
- Rachas controladas — nunca más de 2 pérdidas consecutivas

### F. Timing vs Zigzag
- Costo al pivote: **5.07%** — el más alto de las 4 estaciones
- VIX CRISIS_SPIKE llega TARDE al pivote — el mercado ya rebotó ~5% cuando se confirma la señal
- **0% mismo día**

### G. Cuchillo Cayendo
- MIN: **0%** — nunca cuchillo en entrada LONG
- MAX: **30 eventos (39.0%)** — masivo. Fechas clave: 1998-08-31, 2008-09-29 (Lehman), 2008-10-09 (−16.9%), 2008-10-14, 2020-03-09 (COVID)

### Top State Keys (MIN)
| State Key | N | WR | EV |
|-----------|----|------|------|
| **CRISIS_SPIKE__FAST_SPIKE_3D__VOL_NEUTRAL_BASELINE** | 19 | **89.5%** | **6.02%** |
| CRISIS_SPIKE__ACCELERATING_UP_3D__VOL_NEUTRAL_BASELINE | 14 | 78.6% | 2.65% |
| CRISIS_SPIKE__FAST_SPIKE_3D__VOL_ACCELERATING_EXPANSION | 10 | 80.0% | 1.80% |
| ⚠️ CRISIS_SPIKE__FAST_CRUSH_3D__VOL_NEUTRAL_BASELINE | 10 | **50.0%** | 1.28% |
| ⛔ CRISIS_SPIKE__STABLE_CONTINUATION_3D__VOL_NEUTRAL_BASELINE | 9 | **44.4%** | −0.27% |

**Hallazgo clave D2:** FAST_SPIKE (pánico acelerando) = **89.5% WR**, pero STABLE (pánico estabilizado) = **44.4% WR**. La velocidad D2 discrimina outcome. FAST_CRUSH (pánico colapsando) = coin flip.

---

## 3. BSI — BREADTH_WASHED_OUT (S5TW)

### A. Win Rate
| Tipo | N | WR | CI95 | Baseline WR | Δ |
|------|---|------|------|-------------|-----|
| MIN | 100 | **79.0%** | [71.0%, 86.0%] | 84.0% | −5.0% |
| MAX | 61 | 55.7% | [42.6%, 67.3%] | 85.7% | **−29.9%** |

✅ **BSI MIN es excelente**: WR=79%, N=100 robusto, CI95 estrecho. La degradación vs baseline es solo −5pp — la mejor relación riesgo/señal.

⛔ **BSI MAX es la peor de las 4**: WR=55.7%, Δ=−29.9pp. BREADTH_WASHED_OUT en un techo es señal de que TODO el mercado está vendiendo — NO es momento de ponerse short (ya es tarde).

### B. Distribución WINS (MIN, n=79)
- mean=6.11%, median=5.05%, p25=3.83%, p75=7.72%, max=26.26%
- Wins consistentes, distribución compacta

### C. Distribución LOSSES (MIN, n=21)
- mean=−7.65%, maxloss=−14.99%
- **CERO wipeouts >20%**
- 21 pérdidas con media −7.65% — peor que CREDIT (−7.05%) pero mejor que VIX (−7.21%)

### D. Profit Factor, Kelly, EV
- PF=**3.01**, Kelly=+0.527, EV=3.22% CI95=[2.0%, 4.5%], Sharpe=0.492
- **Segundo mejor PF después de SV5T**, pero con N=100 (6× más datos)

### E. Rachas
- Max win=**10**, max loss=2, avg win=4.2, avg loss=1.1
- Rachas ganadoras muy largas — consistencia alta

### F. Timing vs Zigzag
- Costo al pivote: 4.17% — alto, señal llega tarde
- 0% mismo día

### G. Cuchillo Cayendo
- MIN: **0%**
- MAX: 23 eventos (37.7%) — similar a VIX

### Top State Keys (MIN)
| State Key | N | WR | EV |
|-----------|----|------|------|
| **BREADTH_WASHED_OUT__STABLE_CONTINUATION_3D__VOL_MODERATE_COMPRESSION** | 22 | **90.9%** | **5.79%** |
| BREADTH_WASHED_OUT__DECELERATING_DOWN_3D__VOL_NEUTRAL_BASELINE | 17 | 88.2% | 3.55% |
| BREADTH_WASHED_OUT__STABLE_CONTINUATION_3D__VOL_NEUTRAL_BASELINE | 39 | 74.4% | 2.27% |
| BREADTH_WASHED_OUT__FAST_CRUSH_3D__VOL_NEUTRAL_BASELINE | 9 | 66.7% | 1.53% |

**Hallazgo clave D3:** D3=VOL_MODERATE_COMPRESSION (volatilidad comprimida, no caótica) mejora WR a 90.9%. D3 discrimina: compresión = oportunidad, neutral = decente, caos = peor.

---

## 4. CREDIT — CREDIT_STRESS (HYG+LQD)

### A. Win Rate
| Tipo | N | WR | CI95 | Baseline WR | Δ |
|------|---|------|------|-------------|-----|
| MIN | **116** | 78.4% | [70.7%, 85.3%] | 80.6% | **−2.2%** |
| MAX | **99** | **72.7%** | [64.6%, 80.8%] | 82.1% | −9.4% |

🏆 **CREDIT es la estación más robusta**: N más alto en ambos tipos, WR más cercana al baseline (−2.2pp MIN, −9.4pp MAX — la menor degradación). Es la única donde MAX también tiene EV claramente positivo (CI95 no incluye cero).

### B. Distribución WINS (MIN, n=91)
- mean=6.32%, median=5.26%, p25=3.74%, p75=7.72%, max=26.26%
- Consistente con las demás, ligeramente superior a BSI

### C. Distribución LOSSES (MIN, n=25)
- mean=−7.05%, maxloss=−14.99%
- **CERO wipeouts >20%**

### D. Profit Factor, Kelly, EV
- PF=**3.26**, Kelly=+0.544, EV=3.44% CI95=[2.2%, 4.7%], Sharpe=**0.515**
- **Mejor combinación de PF, Sharpe y N.** El CI95 es el más estrecho.

### E. Rachas
- Max win=**16**, max loss=2, avg win=4.0, avg loss=1.1
- **Racha ganadora más larga de todas** — 16 wins consecutivos. Consistencia extraordinaria.

### F. Timing vs Zigzag
- Costo al pivote: **2.79%** — el más bajo de las 4
- CREDIT da la señal más cercana al pivote real

### G. Cuchillo Cayendo
- MIN: **0%**
- MAX: 22 eventos (22.2%) — el porcentaje más bajo entre las 4

### Top State Keys (MIN)
| State Key | N | WR | EV |
|-----------|----|------|------|
| **CREDIT_STRESS__DECELERATING_DOWN_3D__VOL_NEUTRAL_BASELINE** | 34 | 82.4% | 4.33% |
| CREDIT_STRESS__STABLE_CONTINUATION_3D__VOL_NEUTRAL_BASELINE | 21 | 76.2% | 3.38% |
| CREDIT_STRESS__FAST_CRUSH_3D__VOL_NEUTRAL_BASELINE | 15 | 66.7% | 3.01% |
| ⛔ CREDIT_STRESS__FAST_CRUSH_3D__VOL_NEUTRAL_BASELINE (MAX) | 9 | **22.2%** | −3.67% |

**Advertencia MAX:** CREDIT_STRESS__FAST_CRUSH_3D en MAX tiene solo 22.2% WR — el crédito colapsando en un techo es pésima entrada SHORT.

---

## COMPARATIVO FINAL

### Ranking MIN (entry LONG — el caso natural)

| # | Station | Score | N | WR | EV | PF | Kelly | Fortalezas |
|---|---------|-------|---|------|-----|-----|-------|------------|
| 🥇 | **CREDIT** | 9.2/10 | 116 | 78.4% | 3.44% | 3.26 | +0.544 | Mayor N, mejor Sharpe, menor costo timing, racha 16 wins |
| 🥈 | **BSI** | 8.5/10 | 100 | 79.0% | 3.22% | 3.01 | +0.527 | Mejor WR, excelente PF, D3 discrimina bien |
| 🥉 | **VIX** | 7.0/10 | 94 | 72.3% | 2.94% | 2.47 | +0.431 | Mayor degradación vs baseline, costo timing alto (5%) |
| 4 | **SV5T** | 6.5/10* | 16 | 81.2% | 5.34% | 9.27 | +0.725 | *N=16 insuficiente, CI95 enorme, no confiable |

### Hallazgos transversales

1. **CERO wipeouts >20% en las 4 estaciones.** El downside está controlado en entradas de miedo extremo. Esto es CLAVE: aunque la WR sea menor que el baseline, las pérdidas nunca son catastróficas.

2. **El costo de timing es real.** VIX paga 5.07%, BSI 4.17%, CREDIT 2.79%, SV5T 2.06%. La señal de CREDIT es la más cercana al pivote.

3. **VIX CRISIS_SPIKE en MAX es PELIGROSO:** 39% cuchillo cayendo, WR −23.3pp. NUNCA entrar SHORT durante un pico de VIX aunque sea un techo técnico.

4. **D2 (velocidad) discrimina outcomes dramáticamente:**
   - VIX: FAST_SPIKE → 89.5% WR vs STABLE → 44.4% (45pp de diferencia)
   - BSI: D3 comprimido → 90.9% vs neutral → 74.4%
   - CREDIT MAX: FAST_CRUSH → 22.2% (NO ENTRAR)

5. **CREDIT es la estación más confiable** para entradas en estrés: mayor N, mejor Sharpe, menor costo, rachas más largas, y funciona razonablemente bien incluso en MAX (72.7% WR, EV +1.86%).

6. **SV5T tiene los mejores números pero N=16 es insuficiente.** El CI95 [62.5%, 100%] es demasiado ancho. No se debe tomar como confirmación sin más datos.

### Recomendaciones tácticas

- **CREDIT_STRESS en MIN → ENTRY LONG con confianza.** Kelly +0.544, EV 3.44%, 116 observaciones.
- **VIX CRISIS_SPIKE en MIN → ENTRY LONG solo si D2=FAST_SPIKE** (89.5% WR). Si D2=STABLE, EVALUAR (44.4% WR).
- **BREADTH_WASHED_OUT en MIN → ENTRY LONG, especialmente con D3 comprimido** (90.9% WR).
- **NUNCA ENTRAR SHORT en MAX con VIX CRISIS_SPIKE o BSI BREADTH_WASHED_OUT** (39% cuchillo, WR <60%).
- **SV5T CRISIS_TURBULENCE → MONITOREAR** hasta acumular N≥50 antes de tomar decisiones.

---

**Archivos generados:**
- `/root/botero-trade/research/01_señales_entry_exit/wins_losses_sv5t_vix_bsi_credit.py` — script de análisis
- `/root/botero-trade/research/01_señales_entry_exit/wins_losses_entry47_v2_report.json` — datos completos JSON
- `/root/botero-trade/research/01_señales_entry_exit/wins_losses_entry47_v2_results.json` — resultados iniciales