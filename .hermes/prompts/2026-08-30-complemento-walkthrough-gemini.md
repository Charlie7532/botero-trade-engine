# COMPLEMENTO AL WALKTHROUGH — lo que falta para que esté completo

**Origen:** deepseek/deepseek-v4-flash (Hermes) tras auditoría independiente
**Propósito:** Completar el walkthrough de Fase 0→7 con lo que se omitió o simplificó
**Problema conocido:** El walkthrough actual solo muestra 7 señales de muestra y omite:

---

## 1. AGREGAR: Lista COMPLETA de las 31 señales con su clasificación

No basta con 7 ejemplos. El walkthrough debe incluir la tabla completa para que cualquier lector entienda el ecosistema completo:

### 🟢 NÚCLEO ROBUSTO (5 — OOS validado)
capitulacion, pcr_put_panic, vvix_entry, credit_stress, bsi_washed_out
→ Cada una con: condición en bins numéricos, N, edge zz75, OOS edge, decay

### 💎 DIAMANTES §3.3 (2 — N<21, nunca degradar)
panico_total, skew_paranoia_exit
→ p_raw + CI95 Clopper-Pearson + contexto de crisis

### 🟡 PROPOSED (1)
cascade_reversal
→ Umbral −0.957 congelado, p=0.25, edge sobrevive walk-forward pero no significativo

### 🆕 SEÑALES V2 (3 — vectoriales D1+D2)
capitulacion_v2, euforia_v2, vix_crisis_spike_v2
→ Añaden cinemática D2 sobre V1 base

### ⚪ ACTIVAS SIN OOS (8)
vix_crisis_spike, euforia, fg_extreme_fear, fg_extreme_greed, sorpresa_total, stealth_tail_hedging, sub_reaccion, dxy_bearish
→ Nota: sub_reaccion y dxy_bearish NO funcionan (p≥0.99) — documentar, no ocultar

### 🔴 DEGRADADAS (3)
breadth_contraction_exit — structural break OOS (pre-2016 −1.48%, post +1.81%)
credit_ease_exit — reliquia pre-QE (+6.99% pre → −2.84% post)
bsi_recovery — edge colapsó post-2009

### ⚫ RETIRADAS (9)
credito_easing_k1, credit_stress_exit, dxy_spike_exit, pcr_panic_exit, vix_complacency_exit, credit_equity_divergence, defensive_rotation_divergence, regime_change_exit, sv5t_silent_distribution
→ Motivo de cada retirada: duplicado exacto / lift<1.0 / pivot_type exclusivo

## 2. AGREGAR: Pipeline legacy — marcar lo que NO es activo

El walkthrough actual presenta scripts exploratorios como si fueran parte del pipeline vivo:

| Estos scripts SON LEGACY | Razón |
|:-------------------------|:-------|
| `extract_overflows_vela_a_vela.py` | Fue el barrido inicial. Su hallazgo (53.7% de overflows ENTRE) ya está en el lake |
| `audit_overflow_candle_anatomy.py` (V1) | Reemplazado por V2. Mezclaba MIN/MAX (bug conocido) |
| `detector_regimen_crisis.py` | One-off que produjo 79 episodios. No lo consume ninguna señal |
| `audit_vector_confluence.py` | Sus scores ya están incorporados en `build_continuous_metar_lake.py` |

**Aclaración obligatoria:** El pipeline activo es:
```
medir_senal (arnes de 8 módulos) → quants_obs.pkl → evaluador/tríada/anatomía → clasificación
```

Los scripts legacy fueron trabajo de descubrimiento que informó el diseño. Se preservan por trazabilidad pero **no se ejecutan hoy** y **no son parte del pipeline de medición**. Incluirlos sin esta nota confunde al lector y a futuros agentes.

## 3. CORREGIR: Path del artefacto de anatomía V2

En la línea 16 del resumen ejecutivo dice:
```
data/research/overflow_candle_anatomy_v2.json
```
**Debe decir:**
```
data/research/anatomy/overflow_candle_anatomy_v2.json
```
(La línea 47 de la Sección 2 ya lo tiene correcto, pero el resumen ejecutivo se contradice.)

## 4. AGREGAR: Validador OOS y resultados walk-forward

El walkthrough cubre el evaluador (Fase 2) pero omite completamente el **validador OOS** (`validador_oos.py`) que ejecuta walk-forward anclado de 10 folds. Esta es la única validación que responde "¿se repetirá mañana?" — sin ella, el walkthrough está incompleto.

Resultados a incluir (catálogo v7):

| Señal | IS | OOS | Decay | Folds+ |
|:------|:--:|:---:|:-----:|:------:|
| capitulacion | +3.40% | +2.64% | 0.77 | 2/2 |
| pcr_put_panic | +4.04% | +2.56% | 0.63 | 3/4 |
| vvix_entry | +3.11% | +2.08% | 0.67 | 2/3 |
| credit_stress | +3.42% | +1.43% | 0.42 | 3/4 |
| bsi_washed_out | +1.73% | +0.99% | 0.57 | 5/6 |

Ninguna señal del núcleo fue negativa en OOS. El método: 10 folds cronológicos, train anclado (mínimo 5 años), test (~3 años por fold), mejor celda elegida solo con datos train.

## 5. AGREGAR: Políticas de medición — verificación de no-arbitrariedad

El walkthrough debe incluir una sección que responda explícitamente: **¿qué hace que estas mediciones NO sean arbitrarias?**

| Método | ¿Por qué no es arbitrario? |
|:-------|:---------------------------|
| Bins D1/D2/D3 | Percentiles empíricos con expanding rank (zero look-ahead) — no asume normalidad |
| CI95 | Bootstrap 3,000 iteraciones (seed fija) o Clopper-Pearson exacto para diamantes |
| Walk-forward | 10 folds temporales con train anclado y test no visto. Mejor celda elegida sin mirar test |
| Overflow tiers | T1(3σ-4σ) a T5(≥10σ) — escala estándar de 5 niveles, no inventada |
| First-passage | Mide primer cruce de umbral favorable vs adverso — sin horizonte fijo arbitrario |
| Baseline | Excluye los pivotes donde la propia señal disparó — evita contaminación |

Además, incluir **lo que está PROHIBIDO** (y se cumple):
- ❌ No degradar por N bajo (§3.3 — rareza=riqueza)
- ❌ No aplicar Bonferroni a señales o diamantes (no son data mining ciego)
- ❌ No mezclar MIN y MAX en la misma medición
- ❌ No usar horizonte fijo 20d como métrica causal

## 6. AGREGAR: Nota sobre `_regime_change_exit` — el bin que Gemini perdió en la primera iteración y que ya fue corregido

En la primera migración de señales, `_regime_change_exit` tenía `credit_d1 <= 1` (faltaba el Bin 2). Fue corregido en la segunda iteración a `credit_d1 <= 2`. Incluir esta nota como ejemplo de la revisión que se hizo y cómo se resolvió.

## 7. FORMATO DE ENTREGA ESPERADO

1. Walkthrough actualizado con los 6 puntos anteriores incorporados
2. Mantener la estructura de fases (Fase 0→7) pero agregando la distinción entre pipeline activo y legacy
3. La lista completa de 31 señales debe incluir su clasificación (NÚCLEO/DIAMANTE/PROPOSED/etc.)
4. Evitar el atajo de solo mostrar ejemplos — el lector necesita el mapa completo

---

**Problema conocido de este prompt:** No detecté si `credit_easing_k1` realmente quedó correctamente migrada a bins numéricos o si sigue teniendo sesgo de pivot_type. El auditor debe verificar esto durante la actualización del walkthrough.