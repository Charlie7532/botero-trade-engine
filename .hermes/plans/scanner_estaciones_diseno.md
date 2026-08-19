# SCANNER SISTEMÁTICO DE ESTACIONES — DISEÑO

> Estado: DISEÑO (no implementar aún). Juan Andrés + Hermes, 17-Ago-2026.
> Objetivo: reemplazar 11 estudios manuales por UN barrido automatizado que
> audite las 11 estaciones con D1×D2×D3 completo, marcos de tiempo, probabilidades,
> cross-station y la clasificación de 3 categorías.

---

## 1. PROPÓSITO — QUÉ DEBE ENCONTRAR

El scanner NO interpreta. MIDE y reporta hallazgos significativos. Debe responder,
para las 11 estaciones, las siguientes preguntas ordenadas por la clasificación:

### 1.1 Por estación (independiente)
- **D1 (nivel):** ¿qué nivel extremo predice qué? (contrarian/bearish/neutral)
- **D2 (velocidad):** ¿el movimiento está ENTRANDO o SALIENDO? (timing, dirección)
- **D3 (volatilidad):** ¿estable o errático? (confianza, cascade)
- **Matriz D2×D3 dentro de cada D1:** las 4-9 celdas que discriminan

### 1.2 Cross-station (conjunto)
- **Correlaciones:** raw, D2, D3 entre pares
- **Divergencias:** cuando dos estaciones se contradicen (ej. VIX↑ + S5 mantiene)
- **Conjunciones:** cuando dos o más coinciden en extremo (¿suma o no suma?)
- **Lead-lag:** ¿qué estación reacciona primero? (valida la cadena económica)

### 1.3 Por categoría (la clasificación de 3)
- **SALUD ECONÓMICA** (CREDIT, YIELD, DXY, ROTATION-A): ¿generan tendencia de largo plazo?
- **PRIMEROS SENTIMIENTOS** (VIX, VVIX, PCR, SKEW): ¿anticipan la protección?
- **ACCIÓN REAL** (BSI, SV5T, FG, ROTATION-B): ¿confirman la venta/compra?

### 1.4 Validación de la cadena causal
- ECONOMÍA → PROTECCIÓN → ACCIÓN: ¿el lead-time se confirma empíricamente?
- ¿La economía se deteriora ANTES de que se compre protección?
- ¿La protección se compra ANTES de que la acción (breadth) colapse?

---

## 2. FUENTES (qué lee el scanner)

### 2.1 Fact stores (la fuente primaria de estados)
```
backend/modules/entry_decision/domain/rules/*_fact_store.json  (11 archivos)
  - D1×D2×D3 state_key con zigzag_kinematic (p_bull, ev_net, e_days, rr_asymmetry)
  - prev_leg_domino, structural_momentum
  - dimension_thresholds_definition (edges D1/D2/D3)
```

### 2.2 Calibración del cascade
```
cascade_calibration.json — z-score params, tercile edges, type_mask, baseline IC
```

### 2.3 Datos crudos (para marcos de tiempo fijos)
```
market.ohlcv_bars — 11 tickers + SPY + IWM (small caps)
market.zigzag_legs — pivotes zz25/zz50/zz75
```

### 2.4 Referencias (contexto metodológico)
```
.agents/references/*_intelligence.md — la naturaleza de cada estación
.hermes/plans/clasificacion_naturaleza.md — la clasificación de 3 categorías
.hermes/plans/especificacion_operativa.md — la regla operativa
```

### 2.5 El mapa ticker→station (CRÍTICO — pitfall #13/#56)
```
VIX→VIX, VVIX→VVIX, PCR→CBOE_PCR, FG→FG, BSI→S5TW, SV5T→SV5_TURBULENCE,
SKEW→SKEW, CREDIT→HYG/LQD ratio, YIELD→YIELD_SPREAD, ROTATION→ROTATION_INDEX, DXY→DXY
```

---

## 3. HERRAMIENTAS (métodos)

### 3.1 Adapters por estación (NO un solo lookup)
```
Cada estación usa SU adapter: VIXLookupAdapter, FGLookupAdapter, BsiLookupAdapter,
SkewLookupAdapter, PcrLookupAdapter, ... (pitfall #13: el dispatch genérico falla silencioso)
```

### 3.2 Bootstrap CI (2000-3000 iters)
```
Toda señal: probabilidad + CI95 + N. Nunca una media sola (pitfall #51/#66)
```

### 3.3 Wins/losses SEPARADOS (nunca promediar)
```
wins P25/P50/P75/P90/max + losses P25/P50/P75/P90/min + wipeouts>20% + PF + Kelly
```

### 3.4 Métricas avanzadas
```
- Mutual Information (estructura no-lineal que Spearman esconde) — pitfall #45
- CUSUM (structural breaks por década)
- Walk-forward OOS (cualquier claim de predictividad)
- PBO (probabilidad de overfitting)
```

### 3.5 Marcos de tiempo (NO solo zigzag)
```
3 escalas zigzag: zz25 (2.5%), zz50 (5%), zz75 (7.5%)
4 horizontes fijos: 5, 10, 20, 40 días
→ AMBAS métricas, y RECONCILIAR si contradicen (pitfall #74)
```

---

## 4. EL ORDENAMIENTO DE SEÑALES (la clasificación de 3 categorías)

El scanner clasifica cada hallazgo por la categoría a la que pertenece:

```
CATEGORÍA 1 — SALUD ECONÓMICA (lead largo, tendencia)
  CREDIT (HYG/LQD), YIELD (10Y-3M), DXY, ROTATION-A (dinero entra/sale USA)

CATEGORÍA 2 — PRIMEROS SENTIMIENTOS (lead medio, protección)
  VIX, VVIX, PCR (ambos lados), SKEW

CATEGORÍA 3 — ACCIÓN REAL (lead corto, confirmación)
  BSI (S5TW), SV5T, FG, ROTATION-B (defensivo↔cíclico)
```

Cada hallazgo reporta: estación, categoría, lead-time esperado, y si el lead-time
SE CONFIRMA (cross-station lead-lag analysis).

---

## 5. QUÉ DEBE ENCONTRAR (estructura de salida)

### 5.1 Por estación — tabla de estados poblados
```
| Estación | Estado D1×D2×D3 | N | p_bull | ev_net | dirección | cascade | CI95 | señal |
```
Solo estados N≥10. Los N<10 van a una tabla separada de "huérfanas".

### 5.2 Por categoría — ranking de señales
```
| Categoría | Estación | Mejor señal | Edge | CI95 | N | Lead confirmado |
```

### 5.3 Cross-station — matriz de divergencias y conjunciones
```
| Par | Correlación (raw/D2/D3) | Divergencia relevante | Conjunción |
```

### 5.4 Validación de la cadena causal
```
ECONOMÍA (t0) → PROTECCIÓN (t+Δ1) → ACCIÓN (t+Δ2)
con Δ1 y Δ2 medidos empíricamente (lead-lag)
```

### 5.5 FLAGS automáticos (violaciones de metodología)
```
- Etiqueta binaria sin probabilidad → FLAG (pitfall #51)
- N<10 mezclado con N≥30 → FLAG (pitfall #55)
- Wins/losses promediados → FLAG (pitfall #66)
- Adapter equivocado → FLAG (pitfall #13)
- Solo zigzag sin horizontes fijos → FLAG (pitfall #74)
```

---

## 6. QUÉ NO DEBE HACER (límites)

```
- NO proponer pesos/formulas sin medir (pitfall #1)
- NO usar Kronos/ML sintético para predicción (pitfall #42)
- NO tocar cascade_conviction (columna vertebral)
- NO mezclar estaciones de categorías distintas sin justificar
- NO reportar "funciona/no funciona" — reportar magnitud + dirección + CI (pitfall #39)
```

---

## 7. VALIDACIÓN DEL SCANNER (antes de confiar en él)

```
1. Reproducir un hallazgo CONOCIDO (ej. cascade_50 = 40.69%) → valida el pipeline
2. Reproducir PÁNICO TOTAL (PF 8.09, 0 wipeouts) → valida cross-station
3. Reproducir MIEDO SIN VENTA (sub-reacción) → valida divergencias
4. Si el scanner no reproduce los hallazgos ya validados, NO confiar en él
```

---

## 8. SALIDA FINAL

Un reporte unificado: `scratch/scanner_estaciones_report.md` + JSON, con:
- Tablas por estación (D1×D2×D3 poblado)
- Tablas por categoría (ranking de señales)
- Matriz cross-station (divergencias/conjunciones)
- Validación de la cadena causal (lead-time medido)
- FLAGS de violaciones metodológicas

**El scanner reemplaza 11 estudios manuales por UN barrido de ~15 minutos.**
**Vos revisás los hallazgos significativos y decidís cuáles profundizar.**

---

## PREGUNTAS ABIERTAS (para resolver antes de construir)

1. ¿El scanner corre como UN agente monolitico o como orquestador de 11 sub-agentes?
2. ¿Reporta TODO o solo hallazgos significativos (CI95 excluye 0)?
3. ¿El lead-lag analysis usa correlación cruzada con lags, o algo más preciso (Granger)?
4. ¿Incluye small caps (IWM) como estación de referencia cruzada adicional?
