# METAR Signal Rules & Confidence Tiers

> **Módulo de**: [fact_store_v3_architecture.md](file:///root/botero-trade/.agents/references/metar/fact_store_v3_architecture.md) §11–13
> **Status**: `PRODUCTION` | **Last Audit**: 29-Ago-2026
> **Relacionados**: [anti_patterns.md](file:///root/botero-trade/.agents/references/metar/anti_patterns.md), [d1_labels_canonical.md](file:///root/botero-trade/.agents/references/metar/d1_labels_canonical.md)

---

## 1. Reglas de Interpretación para Señales

### La Regla de Oro
> La fiabilidad de una señal NO es solo `p_bull`. Es la combinación de **probabilidad × magnitud del retorno en ambas direcciones** (Descomposición EV).

```
EV = p_bull × avg_bull_return + (1 - p_bull) × avg_bear_return
```

Un `p_bull = 0.55` con `avg_bull = +4.2%` y `avg_bear = -1.8%` tiene EV = +0.049% — una señal de calidad. Un `p_bull = 0.80` con `avg_bull = +0.5%` y `avg_bear = -2.0%` tiene EV = +0.00% — una trampa.

### Métricas del Estado

| Métrica | Qué Mide | Uso |
|---|---|---|
| `n` | Observaciones históricas en este estado | Confiabilidad del dato |
| `p_bull` | Probabilidad de retorno positivo | Dirección |
| `ev` | Expected Value ponderado | Señal de convicción |
| `sharpe` | Sharpe ratio del estado | Calidad riesgo/retorno |
| `rr_asymmetry` | `|avg_bull| / |avg_bear|` | Asimetría del payoff |

### Regla de Multi-Escala

Los 3 horizontes ZigZag son **independientes** y pueden divergir:
- **`zz25` (2.5%)**: Señal táctica (1-30 días)
- **`zz50` (5.0%)**: Señal intermedia (1-60 días)
- **`zz75` (7.5%)**: Señal estructural (1-90 días)

**Convergencia = alta convicción.** Si las 3 escalas coinciden en dirección, la señal es robusta. Si divergen, el horizonte temporal importa más que la señal individual.

---

## 2. Señales Incondicionales vs Condicionales

### Incondicionales (siempre activas)
Una señal que dispara sin importar el contexto del mercado:
- `VIX en CRISIS_SPIKE__FAST_SPIKE_3D__VOL_ACCELERATING_EXPANSION` → modo crisis
- `FG en EXTREME_FEAR + panic_score ≥ 5` → acumulación contrarian

### Condicionales (requieren contexto)
Una señal que solo tiene significado en combinación con otra:
- `BSI en OVERSOLD_BREADTH` → solo relevante si Credit NO está en CREDIT_CRISIS (breadth wash puede continuar en crisis crediticia)
- `SKEW en TAIL_PARANOIA` → relevante si VIX está < HIGH_VOL (protección excesiva en ambiente tranquilo = contrarian)

---

## 3. Confidence Tiers (Protocolo §3.3)

| Tier | Criterio | Tratamiento |
|---|---|---|
| **Tier A** | N ≥ 30 + CI95 acotado + EV > 0 | Producción directa |
| **Tier B** | 10 ≤ N < 30 + CI95 | Producción con flag de incertidumbre |
| **Tier C** | N < 10 | Observación solamente — sin peso en decisiones |

### Protocolo §3.3 (Marco de Validación)
1. **N ≥ 30** observaciones históricas
2. **Dossier cualitativo** explicando por qué la señal debería funcionar (no puro data mining)
3. **CI95** (Intervalo de confianza 95%) que no cruza cero para EV

> [!IMPORTANT]
> **No aplicar Bonferroni sobre §3.3.** El protocolo ya incluye su propio marco de validación. Bonferroni encima es sobre-corrección.

### DSR — Deflated Sharpe Ratio
Para señales con N ≥ 30, el DSR corrige por:
- Múltiples comparaciones (cuántos estados se probaron)
- Longitud de la serie temporal
- Asimetría y curtosis de los retornos

Un DSR p-value > 0.95 indica que la señal probablemente no es espuria.
