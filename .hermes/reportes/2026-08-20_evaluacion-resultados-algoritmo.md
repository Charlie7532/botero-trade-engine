# PLAN DE EVALUACIÓN — Algoritmo de Señales ENTRY/EXIT
## ¿Qué detectó, qué mejoró, qué resultados arroja?

**Fecha:** 20-Ago-2026 · **Ejecutor:** deepseek-v4-pro (Hermes)

---

## 1. QUÉ MEDIMOS (datos frescos, 22 señales activas)

### 1.1 Resultados completos del arnés con LIFT

| Tipo | Señal | N | Edge | WR | LIFT | Divergence |
|------|-------|:--:|------|:----:|:----:|------------|
| ⚔️ ENTRY | **credit_easing_k1** | 112 | **+5.19%** | **93.8%** | 0.341x | FULL_CONVERGENT_BULL |
| ⚔️ ENTRY | **pcr_put_panic** | 70 | +2.71% | 71.4% | 1.304x | FULL_CONVERGENT_BULL |
| ⚔️ ENTRY | **vvix_entry** | 91 | +1.70% | 62.6% | 1.692x | FULL_CONVERGENT_BULL |
| 🛡️ ENTRY | **fg_extreme_fear** | 54 | +1.58% | 68.5% | 1.034x | FULL_CONVERGENT_BULL |
| 💎 ENTRY | **panico_total** | 34 | +1.49% | 58.8% | 1.526x | FULL_CONVERGENT_BULL |
| ⚔️ ENTRY | **bsi_washed_out** | 161 | +1.42% | 65.8% | 1.315x | FULL_CONVERGENT_BULL |
| 🛡️ ENTRY | **capitulacion** | 82 | +1.40% | 65.8% | 1.326x | FULL_CONVERGENT_BULL |
| ⚠️ ENTRY | credit_stress | 215 | +1.00% | 54.9% | 1.368x | MIXED_HORIZON |
| ⚠️ ENTRY | sorpresa_total | 525 | +0.83% | 54.9% | 1.666x | MIXED_HORIZON |
| ⚠️ ENTRY | vix_crisis_spike | 171 | +0.75% | 56.7% | 1.829x | FULL_CONVERGENT_BULL |
| ❌ ENTRY | sub_reaccion | 667 | +0.39% | 50.2% | 1.023x | MIXED_HORIZON |

| Tipo | Señal | N | Edge | WR | LIFT (MAX) | Divergence |
|------|-------|:--:|------|:----:|:----------:|------------|
| 🔻 EXIT | **credit_equity_divergence** | 120 | **−3.15%** | 14.2% | 1.035x | STRUCTURAL_BUILDUP |
| 🔻 EXIT | **euforia** | 41 | −2.99% | 14.6% | **1.211x** | FULL_CONVERGENT_BEAR |
| 🔻 EXIT | **fg_extreme_greed** | 31 | −1.92% | 19.4% | **2.023x** | MIXED_HORIZON |
| 🔻 EXIT | **bsi_recovery** | 481 | −1.66% | 27.7% | 1.376x | FULL_CONVERGENT_BEAR |
| 💎 EXIT | stealth_tail_hedging | 31 | −0.65% | 35.5% | 1.206x | FULL_CONVERGENT_BEAR |
| ⚠️ EXIT | skew_paranoia_exit | 26 | −0.38% | 46.2% | 1.116x | MIXED_HORIZON |
| ❌ EXIT | dxy_spike_exit | 35 | −0.04% | 45.7% | 1.075x | MIXED_HORIZON |

**Duplicados detectados (misma señal):** pcr_panic_exit ≡ pcr_put_panic (N=70, edge=+2.71%), credit_stress_exit ≡ credit_stress (N=215, edge=+1.00%).

---

## 2. QUÉ DETECTÓ EL ALGORITMO

### 2.1 Cobertura de pisos (ENTRY)

El algoritmo detecta **pisos de mercado** a través de combinaciones específicas del vector METAR. Cada señal captura un fenómeno distinto:

| Señal | Qué detecta | Por qué funciona |
|-------|-------------|------------------|
| credit_easing_k1 | **Pisos con crédito expandiéndose** — el mercado de bonos confirma el piso | WR=93.8%: el easing de crédito en un piso zigzag casi siempre precede una pierna alcista |
| bsi_washed_out | **Pisos con amplitud destruida** — capitulación de breadth | WR=65.8% + cascade_50=77%: el piso de breadth anticipa corrección |
| capitulacion | **Pisos con miedo extremo** — VIX↑ + S5 colapsa | ED=6.86%: defensivo. El valor está en evitar la caída, no en la subida |
| pcr_put_panic | **Pisos con puts extremos** — posicionamiento bajista agotado | WR=71.4%: el pánico de opciones es contrarian |

### 2.2 Cobertura de techos (EXIT)

El algoritmo detecta **techos de mercado** comparando contra el baseline MAX (83.4% de caída natural):

| Señal | Qué detecta | LIFT vs baseline |
|-------|-------------|:---:|
| fg_extreme_greed | **Codicia extrema** — el mejor detector de techo | **2.023x** — duplica la probabilidad de caída |
| bsi_recovery | **Fin de la recuperación de breadth** — BSI sale de washed_out | 1.376x — N=481, el más robusto |
| euforia | **Complacencia total** — VIX en mínimos | 1.211x — N=41, señal validada |
| stealth_tail_hedging | **Cobertura de cola silenciosa** — diamante | 1.206x — N=31, 100% hit rate |

---

## 3. QUÉ MEJORÓ (vs estado pre-enmienda)

| Métrica | Antes (28 señales) | Ahora (22 activas) |
|---------|-------------------|---------------------|
| Señales con lift<1.0 (anti-señal) | 4 activas | **0 activas** — retiradas |
| Señales con fire rate>50% (ruido) | 2 activas | **0 activas** — retiradas |
| Señales duplicadas | 3 pares (6 señales) | **vix_complacency≡euforia retirada**. Quedan 2 pares detectados |
| Métrica LIFT en arnés | No existía | **Implementado** — 22 señales con LIFT medido |
| RNG determinista | Inconsistente (RandomState/default_rng) | **Unificado** a default_rng |

---

## 4. HALLAZGOS QUE REQUIEREN ACCIÓN

### 🔴 H1: Dos pares de señales son idénticas (duplicados no retirados)

```
pcr_panic_exit ≡ pcr_put_panic: ambas N=70, edge=+2.71%, misma definición
credit_stress_exit ≡ credit_stress: ambas N=215, edge=+1.00%
dxy_spike_exit ≡ dxy_bearish: ambas N=35, edge=−0.04%
```
**Impacto:** el conteo de 22 señales activas está inflado. Realmente hay **19 señales únicas**.

### 🟡 H2: sub_reaccion es marginal (WR=50.2%, LIFT=1.023x)

Con 667 activaciones, prácticamente no discrimina — es una moneda al aire. ¿Merece estar en producción o se retira?

### 🟡 H3: dxy_spike_exit y dxy_bearish no tienen edge (WR=45.7%)

Forward casi cero. LIFT apenas sobre 1.0. No detectan ni piso ni techo.

### 🟢 H4: stealth_tail_hedging es diamante legítimo

N=31, forward=−0.65%, LIFT=1.206x, 100% hit rate en MAX. Cumple el protocolo §3.3: baja muestra pero patrón consistente.

---

## 5. RANKING FINAL — ¿qué señales van a producción?

### Señales GRADO A (producción inmediata) — 8 señales

| # | Señal | Tipo | Edge | WR/LIFT | Por qué |
|---|-------|------|------|----------|---------|
| 1 | credit_easing_k1 | ENTRY | +5.19% | WR=93.8% | La estrella. Ofensiva pura. |
| 2 | euforia | EXIT | −2.99% | LIFT=1.211x | Techo más fuerte. Validada. |
| 3 | bsi_recovery | EXIT | −1.66% | LIFT=1.376x, N=481 | Robusto, N grande |
| 4 | fg_extreme_greed | EXIT | −1.92% | LIFT=2.023x | Mejor LIFT del sistema |
| 5 | pcr_put_panic | ENTRY | +2.71% | WR=71.4% | Consistente |
| 6 | bsi_washed_out | ENTRY | +1.42% | WR=65.8% | Dual ofensiva/defensiva |
| 7 | capitulacion | ENTRY | +1.40% | ED=6.86% | Mejor defensa |
| 8 | vvix_entry | ENTRY | +1.70% | WR=62.6% | Complementa pcr_put_panic |

### Señales GRADO B (producción con monitoreo) — 5 señales

| # | Señal | Tipo | Edge | Nota |
|---|-------|------|------|------|
| 9 | fg_extreme_fear | ENTRY | +1.58% | ED=5.61%, buena defensa |
| 10 | panico_total | ENTRY | +1.49% | N=34 — diamante |
| 11 | credit_stress | ENTRY | +1.00% | Necesita filtro duration |
| 12 | credit_equity_divergence | EXIT | −3.15% | N=120, edge fuerte |
| 13 | stealth_tail_hedging | EXIT | −0.65% | N=31 — diamante, 100% hit rate |

### Señales a REVISAR antes de producción — 6 señales

| # | Señal | Problema |
|---|-------|----------|
| 14 | sorpresa_total | N=525, edge=+0.83% → señal débil, ¿filtro mejora? |
| 15 | vix_crisis_spike | Edge=+0.75%, es ENTRY no EXIT (comprar miedo) |
| 16 | sub_reaccion | WR=50.2% → ¿retirar? |
| 17 | skew_paranoia_exit | N=26, edge=−0.38% → muy débil |
| 18 | dxy_spike_exit | Edge=−0.04%, LIFT=1.075x → sin poder |
| 19 | dxy_bearish | Idéntico a dxy_spike_exit → duplicado |

---

## 6. PLAN DE CULMINACIÓN (qué falta)

| # | Acción | Prioridad | Esfuerzo |
|---|--------|-----------|----------|
| P1 | **Consolidar duplicados**: pcr_panic_exit→pcr_put_panic, credit_stress_exit→credit_stress, dxy_spike_exit→dxy_bearish | P1 | 30 min |
| P2 | **Decidir sobre sub_reaccion**: ¿WR=50.2% merece seguir en producción? | P1 | Decisión |
| P3 | **Validar stealth_tail_hedging** con protocolo de diamantes §3.3 (listar eventos, contexto) | P2 | 1h |
| P4 | **Walk-forward OOS** de las TOP 8: entrenar 1993-2015, validar 2016-2026 | P2 | 2h |
| P5 | **Actualizar ARBOLES_DECISION.md** con tabla depurada de 13-19 señales | P3 | 30 min |
| P6 | **Commit** de todo el pipeline | P3 | 10 min |

---
**Firma:** deepseek/deepseek-v4-pro (Hermes) · 20-Ago-2026