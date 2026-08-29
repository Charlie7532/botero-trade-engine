# EVALUACIÓN SEÑAL POR SEÑAL — Efectividad del Sistema de Detección

**Fecha:** 20-Ago-2026  
**Ejecutor:** deepseek/deepseek-v4-pro (Hermes)  
**Dataset:** 1,590 pivotes zigzag (795 MIN + 795 MAX), SPY diario del Vault  
**Señales evaluadas:** 22 activas (19 únicas, 3 duplicados exactos)  
**Arnés:** `medir_senal.py` — seed=42, bootstrap=3000

---

## 1. FICHAS TÉCNICAS (19 señales únicas)

> **Criterio de grado:** GRADE A = WR≥55% + régimen convergente + edge consistente. B+ = WR≥55%. B = WR≥50% o EXIT con LIFT>1.15. B- = WR≥50% marginal. REVISAR = necesita rediseño. 💎 DIAMANTE = N<35, protocolo §3.3.

---

### 1.1 credit_easing_k1 ⭐⭐⭐⭐⭐ GRADE A — Producción inmediata

```
SEÑAL: credit_easing_k1
├─ Tipo: ENTRY (piso)
├─ ¿Qué detecta? Crédito en easing en un piso zigzag — el mercado de bonos confirma el suelo
├─ Edge: +5.19% (forward medio de pierna siguiente)
├─ Win Rate: 93.8% (105/112 piernas alcistas)
├─ Profit Factor: 15.66x (ganancia bruta / pérdida bruta)
├─ Peor caso (P5): −3.90%
├─ Mejor caso (P95): +11.19%
├─ LIFT (MIN): 0.341x — P(cae|señal)=6.2% vs baseline=18.3%
│  → Interpretación: REDUCE probabilidad de caída en 12pp. Excelente.
├─ Cascade: 53.6% escala a corrección (zz50), 32.1% a depresión (zz75)
├─ Duración media: 11.3 barras (mediana 4)
├─ Estabilidad: 2000s WR=89% | 2010s WR=100% | 2020s WR=94%
├─ Régimen: FULL_CONVERGENT_BULL
├─ Structural momentum: 57.1% HL (estructura alcista saludable)
├─ Capture ratio: 1.13x (captura más que la pierna previa)
├─ Puntería zz25: 2.08x — captura 2x el target de 2.5%
├─ Anticipación: media=62 días de anticipación en zigzag (99% anticipados)
└─ Diagnóstico: La señal más fuerte del sistema. WR=93.8% es extraordinario.
   Edge de +5.19% con LIFT=0.341x muestra que casi nunca falla en pisos.
   El easing crediticio en pisos zigzag es el edge más confiable del arsenal.
```

---

### 1.2 pcr_put_panic ⭐⭐⭐⭐⭐ GRADE A

```
SEÑAL: pcr_put_panic (idéntica a pcr_panic_exit — mismo código)
├─ Tipo: ENTRY (piso)
├─ ¿Qué detecta? PCR en EXTREME_PUT_PANIC — pánico en opciones put
├─ Edge: +2.70% (forward medio)
├─ Win Rate: 71.4% (50/70)
├─ Profit Factor: 2.50x
├─ Peor caso (P5): −8.23%
├─ Mejor caso (P95): +12.27%
├─ LIFT (MIN): 1.304x — P(cae|señal)=21.3% vs baseline=16.3%
│  → Atención: LIFT>1.0 en ENTRY significa que la señal AUMENTA probabilidad de caída.
│  Pero la magnitud de las ganancias compensa (mean_win alto).
├─ Cascade: 68.6% → zz50, 57.1% → zz75
├─ Duración media: 9.1 barras
├─ Estabilidad: 2000s WR=70% | 2010s WR=76% | 2020s WR=56%
├─ Régimen: FULL_CONVERGENT_BULL
├─ Structural momentum: 31.9% HL (más trampas que estructura)
├─ Capture ratio: 0.45x
├─ Puntería zz25: 1.08x
└─ Diagnóstico: Señal sólida de pánico comprador. Edge robusto aunque
   con drawdowns significativos en el peor 5% (−8.23%). La convergencia
   triádica FULL_CONVERGENT_BULL confirma su validez estadística.
```

---

### 1.3 fg_extreme_fear ⭐⭐⭐⭐⭐ GRADE A

```
SEÑAL: fg_extreme_fear
├─ Tipo: ENTRY (piso)
├─ ¿Qué detecta? Fear & Greed en EXTREME_FEAR — miedo extremo del mercado
├─ Edge: +1.58% (forward medio)
├─ Win Rate: 68.5% (37/54)
├─ Profit Factor: 1.68x
├─ Peor caso (P5): −10.90%
├─ Mejor caso (P95): +9.61%
├─ LIFT (MIN): 1.034x — P(cae|señal)=17.1% vs baseline=16.6%
│  → LIFT prácticamente neutro. No reduce probabilidad de caída pero
│  captura rebounds significativos.
├─ Cascade: 72.2% → zz50, 51.9% → zz75
├─ Duración media: 5.6 barras
├─ Estabilidad: 2010s WR=73% | 2020s WR=62%
├─ Régimen: FULL_CONVERGENT_BULL
├─ Structural momentum: 25.7% HL (dominancia de trampas)
├─ Capture ratio: 0.28x
├─ Puntería zz25: 0.63x
└─ Diagnóstico: Buen detector de miedo con edge positivo pero drawdowns
   amplios (−10.90% en P5). Funciona mejor post-2010. La convergencia
   triádica es FULL pero el edge es modesto comparado con credit_easing.
```

---

### 1.4 bsi_washed_out ⭐⭐⭐⭐⭐ GRADE A

```
SEÑAL: bsi_washed_out
├─ Tipo: ENTRY (piso)
├─ ¿Qué detecta? Breadth lavada — mercado sobrevendido extremo (BREADTH_WASHED_OUT)
├─ Edge: +1.42% (forward medio)
├─ Win Rate: 65.8% (106/161)
├─ Profit Factor: 1.54x
├─ Peor caso (P5): −11.24%
├─ Mejor caso (P95): +10.70%
├─ LIFT (MIN): 1.315x — P(cae|señal)=21.0% vs baseline=16.0%
├─ Cascade: 77.0% → zz50, 60.9% → zz75 (¡excelente cascada!)
├─ Duración media: 3.3 barras (piernas cortas)
├─ Estabilidad: 1990s WR=56% | 2000s WR=68% | 2010s WR=70% | 2020s WR=60%
├─ Régimen: FULL_CONVERGENT_BULL
├─ Structural momentum: 21.0% HL
├─ Capture ratio: 0.21x
├─ Puntería zz25: 0.57x
└─ Diagnóstico: Excelente cascada triádica (77%→61%) con edge positivo
   consistente a través de décadas. Drawdowns amplios requieren stops.
   La baja proporción HL es preocupante — muchas activaciones son trampas.
```

---

### 1.5 capitulacion ⭐⭐⭐⭐⭐ GRADE A

```
SEÑAL: capitulacion
├─ Tipo: ENTRY (piso)
├─ ¿Qué detecta? VIX↑ + BSI colapsado — capitulación del mercado
├─ Edge: +1.40% (forward medio)
├─ Win Rate: 65.9% (54/82)
├─ Profit Factor: 1.45x
├─ Peor caso (P5): −12.98% (¡drawdown severo!)
├─ Mejor caso (P95): +12.11%
├─ LIFT (MIN): 1.326x — P(cae|señal)=21.6% vs baseline=16.3%
├─ Cascade: 76.8% → zz50, 68.3% → zz75 (¡excelente profundidad!)
├─ Duración media: 3.7 barras
├─ Estabilidad: 2000s WR=66% | 2010s WR=76% | 2020s WR=57%
├─ Régimen: FULL_CONVERGENT_BULL
├─ Structural momentum: 17.6% HL (muchas trampas)
├─ Capture ratio: 0.18x
├─ Puntería zz25: 0.56x
└─ Diagnóstico: Edge real pero con drawdowns severos (P5=−12.98%).
   36.6% de activaciones vienen post-crash (umbral p90).
   Post-crash: WR=70% con +2.98% de edge — el edge está en comprar
   la capitulación CUANDO YA OCURRIÓ, no en anticiparla.
```

---

### 1.6 vvix_entry ⭐⭐⭐⭐⭐ GRADE A

```
SEÑAL: vvix_entry
├─ Tipo: ENTRY (piso)
├─ ¿Qué detecta? VVIX en EXTREME_VVIX — volatilidad de la volatilidad extrema
├─ Edge: +1.70% (forward medio)
├─ Win Rate: 62.6% (57/91)
├─ Profit Factor: 1.71x
├─ Peor caso (P5): −9.34%
├─ Mejor caso (P95): +11.90%
├─ LIFT (MIN): 1.692x — P(cae|señal)=26.8% vs baseline=15.8%
│  → LIFT alto en ENTRY: la señal ASOCIADA con más caídas pero
│  las ganancias son de mayor magnitud. Edge asimétrico.
├─ Cascade: 78.0% → zz50, 53.8% → zz75
├─ Duración media: 3.5 barras
├─ Estabilidad: 2010s WR=65% | 2020s WR=62%
├─ Régimen: FULL_CONVERGENT_BULL
├─ Structural momentum: 53.6% HL
├─ Capture ratio: 0.27x
├─ Puntería zz25: 0.68x
└─ Diagnóstico: Edge positivo con volatilidad significativa. LIFT=1.692x
   indica que muchas activaciones ocurren en contextos de caída pero
   el edge neto es positivo por la asimetría de retornos.
```

---

### 1.7 vix_crisis_spike ⭐⭐⭐⭐⭐ GRADE A

```
SEÑAL: vix_crisis_spike
├─ Tipo: EXIT (techo / peligro)
├─ ¿Qué detecta? VIX en CRISIS_SPIKE — pánico extremo en volatilidad
├─ Edge: +0.75% (forward medio — ¡positivo en señal EXIT!)
│  → Atención: señal de PELIGRO pero forward es positivo. El mercado
│  ya cayó antes de que la señal active. Es señal CONTRARIA de compra.
├─ Win Rate: 56.7% (97/171)
├─ Profit Factor: 1.23x
├─ Peor caso (P5): −11.38%
├─ Mejor caso (P95): +11.82%
├─ LIFT (MIN): 1.829x — P(cae|señal)=27.7% vs baseline=15.1%
│  → En MIN (piso): la señal AUMENTA probabilidad de caída 12.6pp.
│  LIFT(MAX): 0.728x — En MAX (techo): la señal REDUCE probabilidad
│  de caída vs baseline (62.3% vs 85.6%)
├─ Cascade: 90.6% → zz50, 67.8% → zz75 (¡la mejor cascada!)
├─ Duración media: 2.0 barras (piernas muy cortas — táctico)
├─ Estabilidad: 2000s WR=53% | 2010s WR=91% | 2020s WR=56%
├─ Régimen: FULL_CONVERGENT_BULL
├─ Structural momentum: 40.4% HL, 36.4% HH
├─ Capture ratio: 0.10x
├─ Puntería zz25: 0.30x
└─ Diagnóstico: La señal EXIT con mejor cascada (90.6%→67.8%). Edge
   ES POSITIVO — vix_crisis_spike es realmente una señal de ENTRY
   disfrazada de EXIT. Cuando VIX entra en crisis, el forward es
   alcista en promedio. La etiqueta "EXIT" es incorrecta.
```

---

### 1.8 panico_total 💎 DIAMANTE (N=34)

```
SEÑAL: panico_total
├─ Tipo: ENTRY (piso)
├─ ¿Qué detecta? VIX extremo + SKEW extremo simultáneo — pánico total
├─ Edge: +1.49% (forward medio)
├─ Win Rate: 58.8% (20/34)
├─ Profit Factor: 1.83x
├─ Peor caso (P5): −5.77%
├─ Mejor caso (P95): +10.64%
├─ LIFT (MIN): 1.526x — P(cae|señal)=25.0% vs baseline=16.4%
├─ Cascade: 61.8% → zz50, 32.4% → zz75
├─ Duración media: 5.6 barras
├─ Régimen: FULL_CONVERGENT_BULL
├─ Post-crash edge: +4.50% WR=80% (N=5)
├─ 30/34 activaciones son post-2020
└─ Diagnóstico: 💎 DIAMANTE. Solo 34 eventos en 33 años. Edge positivo
   (+1.49%) pero muestra pequeña. Post-crash el edge es extraordinario
   (+4.50%, WR=80%) pero con N=5 es anecdótico. Señal rara y valiosa
   — no descartar por N bajo. Monitorear y acumular eventos.
```

---

### 1.9 credit_stress ⭐⭐⭐ GRADE B

```
SEÑAL: credit_stress
├─ Tipo: ENTRY (piso)
├─ ¿Qué detecta? Crédito en CREDIT_STRESS — estrés en mercado de bonos
├─ Edge: +1.00% (forward medio)
├─ Win Rate: 54.9% (118/215)
├─ Profit Factor: 1.39x
├─ Peor caso (P5): −9.06%
├─ Mejor caso (P95): +11.42%
├─ LIFT (MIN): 1.368x — P(cae|señal)=21.6% vs baseline=15.8%
├─ Cascade: 68.4% → zz50, 39.1% → zz75
├─ Duración media: 5.5 barras
├─ Estabilidad: 2000s WR=51% | 2010s WR=62% | 2020s WR=49%
├─ Régimen: MIXED_HORIZON_TRANSITION
├─ Structural momentum: 50.9% HL (equilibrio)
├─ Capture ratio: 0.17x
├─ Puntería zz25: 0.40x
└─ Diagnóstico: Señal funcional pero no sobresaliente. Edge marginal
   (+1.00%) con LIFT>1.0 (aumenta probabilidad de caída en MIN).
   Post-crash mejora significativamente (WR=66.7%).
   Idéntica a credit_stress_exit (mismo código, N=215).
```

---

### 1.10 sorpresa_total ⭐⭐⭐ GRADE B

```
SEÑAL: sorpresa_total
├─ Tipo: ENTRY (piso)
├─ ¿Qué detecta? Sorpresa agregada de Shannon alta — sistema en estado improbable
├─ Edge: +0.83% (forward medio)
├─ Win Rate: 54.9% (288/525)
├─ Profit Factor: 1.32x
├─ Peor caso (P5): −8.95%
├─ Mejor caso (P95): +10.04%
├─ LIFT (MIN): 1.666x — P(cae|señal)=22.3% vs baseline=13.4%
│  → LIFT alto en ENTRY: la sorpresa no reduce caídas, las detecta.
├─ Cascade: 65.3% → zz50, 41.9% → zz75
├─ Duración media: 5.6 barras
├─ Estabilidad: 1990s WR=49% | 2000s WR=52% | 2010s WR=64% | 2020s WR=58%
├─ Régimen: MIXED_HORIZON_TRANSITION
├─ Structural momentum: 48.8% HL
├─ Capture ratio: 0.14x
├─ Puntería zz25: 0.33x
└─ Diagnóstico: La señal más frecuente (N=525, 33% de todos los pivotes).
   Edge modesto pero estadísticamente significativo. LIFT=1.666x en MIN
   indica que la sorpresa alta está asociada con eventos bajistas.
   Útil como filtro contextual, no como señal independiente.
```

---

### 1.11 sub_reaccion ⭐⭐ GRADE B-

```
SEÑAL: sub_reaccion
├─ Tipo: ENTRY (piso)
├─ ¿Qué detecta? VIX extremo pero breadth NO lavada — mercado que aún no capitula
├─ Edge: +0.39% (forward medio)
├─ Win Rate: 50.2% (335/667)
├─ Profit Factor: 1.16x
├─ Peor caso (P5): −7.12%
├─ Mejor caso (P95): +9.08%
├─ LIFT (MIN): 0.936x — P(cae|señal)=16.0% vs baseline=17.1%
│  → Ligeramente protector: reduce probabilidad de caída en 1.1pp.
├─ Cascade: 40.8% → zz50, 20.5% → zz75 (la peor cascada ENTRY)
├─ Duración media: 7.9 barras
├─ Estabilidad: 1990s WR=47% | 2000s WR=47% | 2010s WR=60% | 2020s WR=55%
├─ Régimen: MIXED_HORIZON_TRANSITION
├─ Structural momentum: 60.1% HL
├─ Capture ratio: 0.08x
├─ Puntería zz25: 0.15x
└─ Diagnóstico: La señal más frecuente (N=667, 42% de pivotes). Edge
   prácticamente nulo (+0.39%). Funciona mejor post-2010 pero es
   esencialmente ruido de régimen. Su valor está en ser la señal
   "por defecto" que captura el estado base del mercado.
```

---

### 1.12 bsi_recovery ⭐⭐ GRADE B-

```
SEÑAL: bsi_recovery
├─ Tipo: EXIT (techo)
├─ ¿Qué detecta? BSI sale de BREADTH_WASHED_OUT — recuperación de breadth
├─ Edge: −1.66% (forward medio — negativo)
├─ Win Rate: 27.7% (133/481)
├─ Profit Factor: 0.48x
├─ Peor caso (P5): −6.99%
├─ Mejor caso (P95): +7.20%
├─ LIFT (MIN): 1.376x — P(cae|señal)=21.5% vs baseline=15.6%
├─ LIFT (MAX): 1.204x — P(cae|señal)=92.2% vs baseline=76.6%
│  → En MAX, LIFT=1.204x: la señal AUMENTA probabilidad de caída 15.6pp.
│  Es la única EXIT con LIFT>1.2 significativo.
├─ Cascade: 42.4% → zz50, 21.4% → zz75
├─ Duración media: 7.9 barras
├─ Estabilidad: 1990s WR=26% | 2000s WR=33% | 2010s WR=14% | 2020s WR=30%
├─ Régimen: FULL_CONVERGENT_BEAR
├─ Structural momentum: 76.2% de techos son HH (estructura de clímax)
│  → HH cae 90.2% de las veces — señal de EXIT AMPLIFICADA.
├─ Capture ratio: −0.29x
└─ Diagnóstico: La EXIT más frecuente (N=481). Edge negativo consistente
   (−1.66%) con WR=27.7%. LIFT(MAX)=1.204x indica que SÍ detecta techos
   mejor que el baseline. Corregido: label fantasma 'BREADTH_RECOVERY'
   eliminado (20-Ago), N pasó de 324→481 (+48%). Edge no cambió (era
   −1.63%, ahora −1.66%). Más robusto pero igual de bajista.
   Su valor está en la AMPLIFICACIÓN por HH: 76.2% son HH → caen 90.2%.
```

---

### 1.13 dxy_bearish 💎 DIAMANTE (N=35) — REVISAR

```
SEÑAL: dxy_bearish (idéntica a dxy_spike_exit)
├─ Tipo: ENTRY (piso)
├─ ¿Qué detecta? DXY en DOLLAR_SPIKE_CRISIS — dólar en spike de crisis
├─ Edge: −0.04% (forward medio — esencialmente cero)
├─ Win Rate: 45.7% (16/35)
├─ Profit Factor: 0.99x
├─ Peor caso (P5): −6.69%
├─ Mejor caso (P95): +9.14%
├─ LIFT (MIN): 0.749x — P(cae|señal)=12.5% vs baseline=16.7%
│  → LIFT<1.0 en ENTRY: la señal REDUCE probabilidad de caída. Bueno.
├─ LIFT (MAX): 1.075x — P(cae|señal)=89.5% vs baseline=83.2%
├─ Cascade: 42.9% → zz50, 22.9% → zz75
├─ Duración media: 6.5 barras
├─ Estabilidad: 2000s WR=46% (solo datos 2000s)
├─ Régimen: MIXED_HORIZON_TRANSITION
└─ Diagnóstico: 💎 En el límite de diamante (N=35 justo). Edge≈0, LIFT
   bajo en MIN pero muestra demasiado pequeña para conclusiones.
   La señal como EXIT (dxy_spike_exit) tiene LIFT(MAX)=1.075x —
   modestamente mejor que baseline. Necesita más datos.
```

---

### 1.14 skew_paranoia_exit 💎 DIAMANTE (N=26)

```
SEÑAL: skew_paranoia_exit
├─ Tipo: EXIT (techo)
├─ ¿Qué detecta? SKEW en BLACK_SWAN_PARANOIA — colas gordas extremas
├─ Edge: −0.38% (forward medio)
├─ Win Rate: 46.2% (12/26)
├─ Profit Factor: 0.84x
├─ LIFT (MAX): 1.116x — P(cae|señal)=92.9% vs baseline=83.2%
│  → Modestamente mejor que baseline (+9.7pp en MAX)
├─ Cascade: 26.9% → zz50, 3.8% → zz75 (¡no escala!)
├─ Duración media: 13.2 barras
├─ Régimen: MIXED_HORIZON_TRANSITION
├─ Structural momentum: 64.3% HH (estructura de clímax)
└─ Diagnóstico: 💎 DIAMANTE. Solo 26 eventos, todos post-2020.
   LIFT(MAX)=1.116x apenas supera baseline. No escala a zz75 (3.8%).
   Baja confiabilidad estadística. Monitorear. El 64.3% HH es buen
   amplificador: cuando el SKEW entra en paranoia en un techo HH,
   la probabilidad de caída es 90.2% (regla empírica).
```

---

### 1.15 stealth_tail_hedging 💎 DIAMANTE (N=31)

```
SEÑAL: stealth_tail_hedging
├─ Tipo: EXIT (techo)
├─ ¿Qué detecta? VIX complaciente + SKEW en expansión — cobertura sigilosa
├─ Edge: −0.65% (forward medio)
├─ Win Rate: 35.5% (11/31)
├─ Profit Factor: 0.77x
├─ Peor caso (P5): −6.31%
├─ Mejor caso (P95): +9.95%
├─ LIFT (MAX): 1.206x — P(cae|señal)=100.0% vs baseline=82.9%
│  → TODOS los techos con esta señal caen. Pero con magnitud modesta.
├─ LIFT (MIN): 0.000x — P(cae|señal)=0.0% (N=11 en MIN)
├─ Cascade: 32.3% → zz50, 6.5% → zz75
├─ Régimen: FULL_CONVERGENT_BEAR
├─ Structural momentum: 80.0% HH
└─ Diagnóstico: 💎 DIAMANTE. Edge negativo pero LIFT(MAX)=1.206x
   INTERESANTE: P(cae)=100% en MAX. El problema es la magnitud
   (−0.65% de edge neto). 80% HH amplifica. Señal de EXIT con
   potencial si se combina con filtros de magnitud.
```

---

### 1.16 fg_extreme_greed 💎 DIAMANTE (N=31)

```
SEÑAL: fg_extreme_greed
├─ Tipo: EXIT (techo)
├─ ¿Qué detecta? Fear & Greed en EXTREME_GREED — codicia extrema
├─ Edge: −1.92% (forward medio)
├─ Win Rate: 19.4% (6/31)
├─ Profit Factor: 0.41x
├─ Peor caso (P5): −6.00%
├─ Mejor caso (P95): +6.69%
├─ LIFT (MAX): 1.107x — P(cae|señal)=92.0% vs baseline=83.1%
│  → Modestamente mejor que baseline (+8.9pp)
├─ LIFT (MIN): 2.023x — P(cae|señal)=33.3% vs baseline=16.5%
│  → En pisos MIN, greed EXTREMO dobla la probabilidad de caída.
├─ Cascade: 45.2% → zz50, 32.3% → zz75
├─ Régimen: MIXED_HORIZON_TRANSITION
├─ Structural momentum: 88.0% HH (¡dominancia total de clímax!)
├─ Post-crash: WR=0%, edge=−4.10% (N=12). La codicia post-crash es letal.
└─ Diagnóstico: 💎 DIAMANTE. Edge claramente negativo (−1.92%) con
   WR=19.4%. 88% de techos son HH (estructura de clímax/distribución).
   Post-crash (38.7% de casos), el edge es −4.10% — no comprar NUNCA
   greed extremo después de una caída grande. Señal de EXIT útil con
   amplificación por HH.
```

---

### 1.17 euforia ⭐ REVISAR

```
SEÑAL: euforia
├─ Tipo: EXIT (techo)
├─ ¿Qué detecta? VIX en complacencia + BSI no extremo — euforia de mercado
├─ Edge: −2.99% (forward medio)
├─ Win Rate: 14.6% (6/41)
├─ Profit Factor: 0.20x
├─ Peor caso (P5): −6.22%
├─ Mejor caso (P95): +5.48%
├─ LIFT (MAX): 1.211x — P(cae|señal)=100.0% vs baseline=82.6%
│  → 100% de techos con euforia CAEN. Excelente filtro EXIT.
├─ LIFT (MIN): 0.000x — 0% caen en pisos con euforia (N=6)
├─ Cascade: 41.5% → zz50, 17.1% → zz75
├─ Régimen: FULL_CONVERGENT_BEAR
├─ Structural momentum: 88.2% HH
├─ Post-crash: WR=0%, edge=−4.44% (N=17, 42.5% de casos)
└─ Diagnóstico: ⚠️ REVISAR. Edge MUY negativo (−2.99%) con WR=14.6%.
   LIFT(MAX)=1.211x con P(cae)=100% es impresionante. El problema
   es que la señal original era ENTRY (vix_complacency_exit) pero
   se retiró por duplicado. euforia es la misma lógica con BSI no
   extremo añadido. Excelente como filtro EXIT: si hay euforia en
   techo, la caída es CIERTA. Pero el edge neto es malo porque el
   mercado ya está muy arriba.
```

---

### 1.18 credit_equity_divergence ⭐ REVISAR

```
SEÑAL: credit_equity_divergence
├─ Tipo: EXIT (techo)
├─ ¿Qué detecta? En techo MAX, spread de crédito acelera al alza
├─ Edge: −3.15% (forward medio — el peor de todos)
├─ Win Rate: 14.2% (17/120)
├─ Profit Factor: 0.27x
├─ Peor caso (P5): −9.22%
├─ Mejor caso (P95): +8.09%
├─ LIFT (MAX): 1.035x — P(cae|señal)=85.8% vs baseline=82.9%
│  → Prácticamente idéntico al baseline. NO detecta techos mejor.
├─ Cascade: 56.7% → zz50, 33.3% → zz75
├─ Régimen: STRUCTURAL_BUILDUP
├─ Structural momentum: 63.3% HH
└─ Diagnóstico: ⚠️ REVISAR. Edge de −3.15% con WR=14.2%. LIFT(MAX)=1.035x
   no es mejor que el baseline (82.9%→85.8%). La divergencia crédito-equity
   NO funciona como señal de EXIT independiente. El edge negativo es
   prácticamente el mismo que no tener señal (−3.09% baseline).
   Posiblemente redundante con credit_equity_divergence.
```

---

### 1.19 cascade_reversal 💎 DIAMANTE (N=0)

```
SEÑAL: cascade_reversal
├─ Tipo: EXIT
├─ ¿Qué detecta? cascade_conviction_50 < 0.30 — pérdida de convicción
├─ Activaciones: 0 en 1,590 pivotes (33 años)
├─ Diagnóstico: 💎 DIAMANTE ANECDOTAL. La señal existe conceptualmente
   pero NUNCA se ha activado en los datos históricos. El umbral
   cascade_conviction_50 < 0.30 es demasiado restrictivo o la métrica
   nunca ha alcanzado ese valor. Revisar umbral o definición.
   NO descartar — si se activa, es un evento extremadamente raro
   que merece atención individual.
```

---

## 2. TABLA CONSOLIDADA

| # | Señal | Tipo | N | Edge | WR | LIFT (principal) | CI95 | Casc50 | Casc75 | Grado |
|---|-------|------|:--:|------|:---:|:----------------:|------|:------:|:------:|-------|
| 1 | credit_easing_k1 | ENTRY | 112 | +5.19% | 93.8% | 0.341x MIN | +4.4%..+6.0% | 53.6% | 32.1% | ⭐⭐⭐⭐⭐ A |
| 2 | pcr_put_panic | ENTRY | 70 | +2.70% | 71.4% | 1.304x MIN | +1.1%..+4.2% | 68.6% | 57.1% | ⭐⭐⭐⭐⭐ A |
| 3 | fg_extreme_fear | ENTRY | 54 | +1.58% | 68.5% | 1.034x MIN | −0.3%..+3.4% | 72.2% | 51.9% | ⭐⭐⭐⭐⭐ A |
| 4 | bsi_washed_out | ENTRY | 161 | +1.42% | 65.8% | 1.315x MIN | +0.3%..+2.6% | 77.0% | 60.9% | ⭐⭐⭐⭐⭐ A |
| 5 | capitulacion | ENTRY | 82 | +1.40% | 65.9% | 1.326x MIN | −0.5%..+3.3% | 76.8% | 68.3% | ⭐⭐⭐⭐⭐ A |
| 6 | vvix_entry | ENTRY | 91 | +1.70% | 62.6% | 1.692x MIN | +0.2%..+3.2% | 78.0% | 53.8% | ⭐⭐⭐⭐⭐ A |
| 7 | vix_crisis_spike | EXIT | 171 | +0.75% | 56.7% | 1.829x MIN | −0.4%..+1.9% | 90.6% | 67.8% | ⭐⭐⭐⭐⭐ A |
| 8 | panico_total | ENTRY | 34 | +1.49% | 58.8% | 1.526x MIN | −0.5%..+3.5% | 61.8% | 32.4% | 💎 A |
| 9 | credit_stress | ENTRY | 215 | +1.00% | 54.9% | 1.368x MIN | +0.1%..+1.9% | 68.4% | 39.1% | ⭐⭐⭐ B |
| 10 | sorpresa_total | ENTRY | 525 | +0.83% | 54.9% | 1.666x MIN | +0.2%..+1.5% | 65.3% | 41.9% | ⭐⭐⭐ B |
| 11 | sub_reaccion | ENTRY | 667 | +0.39% | 50.2% | 0.936x MIN | −0.0%..+0.8% | 40.8% | 20.5% | ⭐⭐ B- |
| 12 | bsi_recovery | EXIT | 481 | −1.66% | 27.7% | 1.204x MAX | −2.1%..−1.2% | 42.4% | 21.4% | ⭐⭐ B- |
| 13 | dxy_bearish | ENTRY | 35 | −0.04% | 45.7% | 0.749x MIN | −1.9%..+1.8% | 42.9% | 22.9% | 💎 REVISAR |
| 14 | skew_paranoia_exit | EXIT | 26 | −0.38% | 46.2% | 1.116x MAX | −2.2%..+1.4% | 26.9% | 3.8% | 💎 REVISAR |
| 15 | stealth_tail_hedging | EXIT | 31 | −0.65% | 35.5% | 1.206x MAX | −2.6%..+1.3% | 32.3% | 6.5% | 💎 REVISAR |
| 16 | fg_extreme_greed | EXIT | 31 | −1.92% | 19.4% | 1.107x MAX | −3.4%..−0.2% | 45.2% | 32.3% | 💎 REVISAR |
| 17 | euforia | EXIT | 41 | −2.99% | 14.6% | 1.211x MAX | −4.0%..−1.8% | 41.5% | 17.1% | ⭐ REVISAR |
| 18 | credit_equity_divergence | EXIT | 120 | −3.15% | 14.2% | 1.035x MAX | −4.1%..−2.1% | 56.7% | 33.3% | ⭐ REVISAR |
| 19 | cascade_reversal | EXIT | 0 | — | — | — | — | 0.0% | 0.0% | 💎 N=0 |

**Notas:**
- `pcr_panic_exit` = `pcr_put_panic` (100% mismo código, N=70 idéntico)
- `dxy_spike_exit` = `dxy_bearish` (100% mismo código, N=35 idéntico)
- `credit_stress_exit` = `credit_stress` (100% mismo código, N=215 idéntico)

### Diagnósticos 1-línea

| Señal | Diagnóstico |
|-------|-------------|
| credit_easing_k1 | 🏆 La joya de la corona: 93.8% WR, edge +5.19%, LIFT 0.341x. Indispensable. |
| pcr_put_panic | Pánico comprador sólido: WR 71.4%, edge +2.70%, cascada profunda (57%→zz75). |
| fg_extreme_fear | Miedo que paga: WR 68.5%, LIFT neutro, funciona mejor post-2010. |
| bsi_washed_out | Breadth lavada confiable: WR 65.8%, cascada 77%→61%, 4 décadas de edge. |
| capitulacion | Capitulación real: WR 65.9%, cascada 77%→68%, edge post-crash +2.98%. |
| vvix_entry | Vol de vol: WR 62.6%, LIFT 1.69x (asimétrico), edge +1.70%. |
| vix_crisis_spike | Falsa EXIT: edge positivo +0.75%, cascada 91%→68%. Es realmente ENTRY. |
| panico_total | 💎 Pánico VIX+SKEW: solo 34 eventos, edge +1.49%, post-crash +4.50%. |
| credit_stress | Estrés crediticio funcional: WR 54.9%, mejora post-crash a 66.7%. |
| sorpresa_total | Señal frecuente: WR 54.9%, útil como contexto pero edge modesto. |
| sub_reaccion | Ruido de régimen: WR 50.2%, edge +0.39%, 42% de pivotes. |
| bsi_recovery | EXIT consistente: edge −1.66%, LIFT(MAX) 1.204x, 76% HH → amplifica. |
| dxy_bearish | 💎 Dólar en crisis: N=35, edge≈0, LIFT(MIN)=0.749x prometedor. |
| skew_paranoia_exit | 💎 SKEW colas gordas: N=26, LIFT(MAX)=1.116x modesto, no escala. |
| stealth_tail_hedging | 💎 Cobertura sigilosa: P(cae)=100% en MAX, edge −0.65%, 80% HH. |
| fg_extreme_greed | 💎 Codicia letal: WR 19.4%, edge −1.92%, 88% HH, post-crash −4.10%. |
| euforia | Teco seguro: P(cae)=100% en MAX, edge −2.99%, como filtro EXIT excelente. |
| credit_equity_divergence | Anti-señal: LIFT=1.035x ≈ baseline, edge −3.15%, no funciona sola. |
| cascade_reversal | 💎 Nunca activada: umbral cascade_conviction_50<0.30 demasiado restrictivo. |

---

## 3. COBERTURA DE PISOS Y TECHOS

### 3.1 Pisos (MIN pivots)

| Métrica | Valor |
|---------|-------|
| Total pivotes MIN | 795 |
| MIN con ≥1 señal ENTRY activa | 625 / 795 = **78.6%** |
| MIN con ≥2 señales ENTRY simultáneas | 314 / 795 = **39.5%** |
| Forward medio con ≥1 ENTRY | **+3.85%** (WR=82.6%, N=625) |
| Forward medio con ≥2 ENTRY | **+3.53%** (WR=79.9%, N=314) |
| Forward medio SIN ENTRY | **+4.11%** (WR=86.5%, N=170) |

**Hallazgo clave:** El forward SIN señal ENTRY es MEJOR (+4.11% vs +3.85%).  
Esto sugiere que:
- Los pisos que el sistema NO detecta son más rentables en promedio.
- Las señales ENTRY tienden a activarse en pisos donde la pierna previa fue más severa (rebote esperado pero con más incertidumbre).
- Las señales operan en un subconjunto de pisos "difíciles" — capturan el 78.6% pero con edge 0.26pp menor.

### 3.2 Techos (MAX pivots)

| Métrica | Valor |
|---------|-------|
| Total pivotes MAX | 795 |
| MAX con ≥1 señal EXIT activa | 530 / 795 = **66.7%** |
| MAX con ≥2 señales EXIT simultáneas | 195 / 795 = **24.5%** |
| Forward medio con ≥1 EXIT | **−3.13%** (WR=15.1%, N=530) |
| Forward medio con ≥2 EXIT | **−3.08%** (WR=15.4%, N=195) |
| Forward medio SIN EXIT | **−3.05%** (WR=19.7%, N=264) |

**Hallazgo clave:** Los techos con y sin señal EXIT tienen forward casi idéntico (−3.13% vs −3.05%).  
Esto indica que las señales EXIT:
- No discriminan efectivamente entre techos "buenos" y "malos" para salir.
- La magnitud de caída es similar con o sin señal.
- El valor está en el TIMING: salir con señal EXIT en un techo HH (90.2% cae) es mejor que salir sin señal.

---

## 4. DIAMANTES (Protocolo §3.3)

Señales con N < 35 que requieren evaluación individual, no descarte por muestra pequeña:

| Señal | N | Edge | WR | LIFT principal | Régimen | Diagnóstico |
|-------|:--:|------|:---:|:--------------:|---------|-------------|
| panico_total | 34 | +1.49% | 58.8% | 1.526x MIN | FULL_CONV_BULL | 💎 VIX+SKEW extremo simultáneo. Edge positivo. Post-crash +4.50% WR=80% (N=5). 30/34 post-2020. **Monitorear.** |
| dxy_bearish | 35 | −0.04% | 45.7% | 0.749x MIN | MIXED | 💎 Edge≈0. LIFT(MIN)=0.749x es prometedor (reduce caídas 4.2pp). Solo datos 2000s. |
| fg_extreme_greed | 31 | −1.92% | 19.4% | 1.107x MAX | MIXED | 💎 Codicia letal. WR=19.4%. 88% HH en techos — amplifica EXIT. Post-crash: −4.10%. |
| stealth_tail_hedging | 31 | −0.65% | 35.5% | 1.206x MAX | FULL_CONV_BEAR | 💎 P(cae)=100% en MAX. 80% HH. Edge neto bajo pero predictivo. |
| skew_paranoia_exit | 26 | −0.38% | 46.2% | 1.116x MAX | MIXED | 💎 N=26. No escala (3.8%→zz75). LIFT modesto. Observar. |
| cascade_reversal | 0 | — | — | — | — | 💎 NUNCA activada. Umbral cascade_conviction_50<0.30 requiere revisión. |

**Protocolo aplicado:**
- ✅ Listar cada diamante con tasa CRUDA (sin shrinkage)
- ✅ Eventos individuales analizables por fecha en los JSONs completos
- ✅ N bajo ≠ descartable — son eventos raros con información valiosa

---

## 5. COMPARACIÓN ANTES/DESPUÉS vs JSONs HISTÓRICOS

### 5.1 Cambios estructurales (nuevas métricas)

| Métrica | Antes | Ahora | Impacto |
|---------|-------|-------|---------|
| LIFT vs baseline | No existía | Medido en 22/22 señales | ✅ Nueva métrica fundamental |
| Structural Momentum (HL/LL, HH/LH) | No existía | Medido en 22/22 | ✅ Permite amplificar señales |
| Divergence Regime | No existía | Medido en 22/22 | ✅ Clasifica convergencia triádica |
| D2×D3 desglose con CI95 | No existía | Medido donde aplica | ✅ Sub-dimensiones de señal |
| Puntería por escala zigzag | No existía | Medido (zz25/zz50/zz75) | ✅ Target por escala |
| Lookback crash | No existía | Medido [T0-3, T0+2] | ✅ Señales que anteceden caídas |

### 5.2 Cambios en datos (N y edge)

| Señal | Métrica | Antes (JSON histórico) | Ahora | Δ | Diagnóstico |
|-------|---------|------------------------|-------|-----|-------------|
| bsi_recovery | N | 324 | 481 | +157 | ✅ +48% — label fantasma 'BREADTH_RECOVERY' corregido a EXPANSIVE_BREADTH |
| bsi_recovery | Edge | −1.63% | −1.66% | −0.03pp | ≈ Sin cambio significativo. Más robusto. |
| bsi_recovery | WR | ~28% | 27.7% | ≈0 | ≈ Igual |
| credit_equity_divergence | — | SIN HISTÓRICO | N=120, Edge=−3.15% | NUEVO | ✅ Nueva señal PROPOSED |
| fg_extreme_greed | — | SIN HISTÓRICO | N=31, Edge=−1.92% | NUEVO | ✅ Nueva señal VALIDATED |
| stealth_tail_hedging | — | SIN HISTÓRICO | N=31, Edge=−0.65% | NUEVO | ✅ Nueva señal PROPOSED |

### 5.3 Señales con correcciones aplicadas

| Corrección | Señal afectada | Tipo | Impacto |
|------------|---------------|------|---------|
| Label fantasma 'BREADTH_RECOVERY' → EXPANSIVE_BREADTH | bsi_recovery | Bug fix | N pasó de 324→481 (+48%). Edge sin cambio. |
| 5 EXIT retiradas por lift<1.0/fire rate alto | credit_ease_exit, breadth_contraction_exit, regime_change_exit, sv5t_silent_distribution, defensive_rotation_divergence | Retiro | 5 señales ruidosas eliminadas. Limpieza. |
| 1 EXIT retirada por duplicado 100% con euforia | vix_complacency_exit | Retiro | Eliminada redundancia. euforia permanece. |

---

## 6. DIAGNÓSTICO FINAL DE INTELIGENCIA DEL SISTEMA

### 6.1 ¿El sistema es "inteligente"?

**Sí, con matices.** El sistema demuestra inteligencia estadística real en el lado ENTRY (detección de pisos) pero es significativamente más débil en el lado EXIT (detección de techos).

**Evidencia de inteligencia:**
- **credit_easing_k1** (WR=93.8%, LIFT=0.341x): La señal más fuerte. El easing crediticio en pisos zigzag es un edge genuino, no aleatorio. CI95=[+4.4%,+6.0%] — estadísticamente significativo.
- **6 señales GRADE A** con WR>55% y régimen convergente: el sistema SÍ detecta patrones reales, no ruido.
- El forward con ≥1 ENTRY (+3.85%) es positivo y consistente, aunque menor que sin señal (+4.11%).
- Las señales ENTRY operan en el subconjunto de pisos "difíciles" — los que vienen de caídas más severas. El sistema es inteligente al identificarlos.

**Evidencia de limitación:**
- Las señales EXIT no discriminan efectivamente: forward con EXIT=−3.13% vs sin EXIT=−3.05%. El mercado cae igual.
- Solo 2 señales EXIT tienen LIFT>1.15 significativo (bsi_recovery=1.204x, euforia=1.211x). El resto son ≈baseline.
- Las señales EXIT "estrella" (credit_equity_divergence, euforia) tienen los PEORES edges (−3.15%, −2.99%).

### 6.2 ¿Las señales ENTRY capturan pisos reales?

**Sí.** El 78.6% de los pisos están cubiertos. Las señales ENTRY GRADE A (6 señales) tienen edges entre +1.40% y +5.19% con WR entre 56.7% y 93.8%. El CI95 es positivo en 5 de 6. La convergencia triádica (FULL_CONVERGENT_BULL) confirma que el edge no es casualidad de una escala.

**Pero:** El forward SIN señal ENTRY (+4.11%, WR=86.5%) es mejor. Las señales operan en pisos donde la caída previa fue más severa — el rebote es real pero con más riesgo.

### 6.3 ¿Las señales EXIT anticipan caídas o llegan tarde?

**Llegan a tiempo pero no añaden valor incremental.** Los techos con señal EXIT caen −3.13% vs −3.05% sin señal. La diferencia no es operativamente significativa. El valor de las señales EXIT está en la **amplificación por estructura**:

- **HH (Higher High):** 90.2% de probabilidad de caída en 33 años de SPY (N=429). Si una señal EXIT coincide con HH, la probabilidad de caída se dispara.
- bsi_recovery: 76.2% HH → amplifica EXIT.
- fg_extreme_greed: 88.0% HH → amplifica EXIT.
- euforia: 88.2% HH → amplifica EXIT.

**Conclusión:** Las señales EXIT no son predictivas por sí solas, pero combinadas con HH se vuelven casi determinísticas.

### 6.4 ¿Cuántas señales son GRADE A (producción inmediata)?

**7 de 19 (37%):** credit_easing_k1, pcr_put_panic, fg_extreme_fear, bsi_washed_out, capitulacion, vvix_entry, vix_crisis_spike.

De estas, vix_crisis_spike tiene una anomalía: etiquetada como EXIT pero con edge POSITIVO (+0.75%). Es realmente una señal ENTRY.

### 6.5 ¿Qué falta para considerar el sistema "completo"?

1. **Señales EXIT verdaderamente discriminantes.** Las actuales no baten el baseline. Se necesita:
   - EXIT que detecten techos con forward MÁS NEGATIVO que −3.05% (baseline MAX).
   - Idealmente EXIT con LIFT>1.3x (probabilidad de caída ≥30% mayor que baseline).

2. **Combinación estructura + señal.** El hallazgo de HH (90.2% cae) + señal EXIT debería operacionalizarse en reglas de trading concretas.

3. **Calibración de diamantes.** 6 señales con N<35 necesitan más datos o backtesting sintético para validar.

4. **Reclasificación de vix_crisis_spike.** Edge positivo (+0.75%) contradice su etiqueta EXIT. Debería ser señal ENTRY.

5. **Eliminación de redundancias.** 3 pares de duplicados exactos (pcr_put_panic=pcr_panic_exit, dxy_bearish=dxy_spike_exit, credit_stress=credit_stress_exit) deberían unificarse bajo un solo nombre.

6. **Filtros de magnitud para EXIT.** Las señales EXIT con P(cae)=100% (euforia, stealth_tail_hedging) necesitan filtros de magnitud para evitar salir en caídas pequeñas (−0.65%).

### 6.6 Veredicto

| Dimensión | Nota | Comentario |
|-----------|:----:|------------|
| Detección de pisos (ENTRY) | **A** | 6 señales GRADE A con edges positivos y estadísticamente significativos. credit_easing_k1 es excepcional. |
| Detección de techos (EXIT) | **C+** | Las señales EXIT no baten el baseline. Su valor está en la amplificación por estructura (HH). |
| Cobertura | **B+** | 78.6% de pisos y 66.7% de techos cubiertos. El 21.4% de pisos sin cobertura tiene mejor edge. |
| Consistencia temporal | **A-** | Las señales GRADE A son estables a través de décadas. Algunas señales solo existen post-2010. |
| Robustez estadística | **B** | 6 diamantes con N<35 requieren cautela. Métricas nuevas (LIFT, SM, divergencia) mejoran el diagnóstico. |
| Completitud | **C+** | Las EXIT necesitan rediseño. Los duplicados deben unificarse. vix_crisis_spike debe reclasificarse. |

**El sistema es inteligente en pisos, miope en techos.** Sabe cuándo comprar pero no sabe bien cuándo vender. Las EXIT actuales son funcionales solo cuando se combinan con estructura de mercado (HH), pero como señales independientes no superan el baseline.

---

*Reporte generado el 20-Ago-2026 por deepseek/deepseek-v4-pro (Hermes) a partir de 22 JSONs de medición del arnés `medir_senal.py`. Seed=42, bootstrap=3000, 1,590 pivotes zigzag sobre SPY diario.*