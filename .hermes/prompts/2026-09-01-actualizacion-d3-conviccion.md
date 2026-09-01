# ACTUALIZACIÓN CRÍTICA — D3 = Dimensión de Convicción

**Corrección del auditor:** D2 y D3 usan 5 niveles (0..4) donde 4 = ±2σ. D2=4 y D3=4 son los extremos reales. No existe "5" por diseño correcto. Esto no es un bug — es la calibración canónica.

---

## Los datos que cambian todo

### VIX D1=5 (pánico) — el mismo D1, pero D3 cambia radicalmente el resultado

| D3 | Interpretación | N | SPY ret | WR | ¿Qué significa? |
|:--:|:---------------|:-:|:-------:|:--:|:----------------|
| **0** | **Pánico estable** — el VIX cree en su pánico | 4 | **-6.72%** | 25% | 💎 **DIAMANTE.** Mercado convencido de la caída. Señal de continuación bajista. |
| **1** | Pánico con leve estabilidad | 21 | **+2.96%** | 67% | El pánico es estable pero el mercado ya descuenta reversión. |
| 2 | Pánico neutral | 112 | +0.19% | 52% | La mayoría. Sin señal clara. |
| **3** | **Pánico inestable** — el VIX duda de su pánico | 32 | **+1.28%** | 63% | ⚠️ **ALERTA DE REVERSIÓN.** El VIX está en pánico pero es errático → el pánico se agota. |

**Interpretación:** D3=0 en D1=5 = "VIX cree en su pánico" → seguir bajando. D3=3 en D1=5 = "VIX no cree en su pánico" → reversión inminente. **Misma D1, resultados opuestos, separados por D3.**

### VIX D1=4 (crisis) — la inestabilidad anticipa el rebote

| D3 | N | SPY ret | WR | Significado |
|:--:|:-:|:-------:|:--:|:------------|
| 0 | 13 | -0.45% | 56% | Crisis estable → sigue bajando |
| 1 | 71 | +0.02% | 51% | Neutro |
| 2 | 403 | -0.01% | 54% | La mayoría |
| **3** | **104** | **+0.83%** | **61%** | **Crisis inestable → el mercado anticipa el suelo** |
| 4 | 7 | +0.07% | 56% | Baja N pero misma dirección |

### SKEW D1=0 (complacencia) — ¿calma real o falsa?

| D3 | N | SPY ret | WR | Significado |
|:--:|:-:|:-------:|:--:|:------------|
| **0** | **9** | **+0.90%** | **67%** | **Complacencia real** → el mercado cree en la calma, sigue subiendo |
| 1 | 58 | -0.01% | 55% | Complacencia con leve ruido |
| 2 | 349 | +0.06% | 53% | La mayoría |
| **3** | **100** | **+0.24%** | **51%** | **Calma falsa** — SKEW no cree en su propia calma, mercado débil |
| 4 | 14 | +0.27% | 43% | Muy baja convicción alcista |

---

## La métrica: D3 es ortogonal a D1

r(D1, D3) en las 11 estaciones:

| Estación | r(D1,D3) | ¿Ortogonal? |
|:---------|:--------:|:-----------:|
| VIX | -0.005 | ✅ **Casi perfecto** |
| VVIX | +0.065 | ✅ |
| PCR | +0.077 | ✅ |
| BSI | -0.015 | ✅ |
| SKEW | +0.008 | ✅ |
| CREDIT | +0.106 | ✅ |
| ROTATION | -0.017 | ✅ |
| DXY | +0.024 | ✅ |
| FG | +0.127 | ✅ |
| SV5 | -0.027 | ✅ |
| YIELD | -0.023 | ✅ |

**Ninguna supera 0.13.** D3 NO es derivable de D1. Es una dimensión independiente.

---

## Implicación para el prompt

**Claude dijo:** "La mejora de mayor impacto es escalar las señales al espacio D1×D2."

**Los datos dicen:** D3 es igual o más importante que D2 para la convicción. La jerarquía correcta es:

| Prioridad | Dimensión | Información que aporta | 
|:---------:|:---------:|:-----------------------|
| **1** | D1 | Magnitud — ¿qué tan extremo es el estado? |
| **2** | **D3** | **Convicción — ¿el indicador cree en su propia lectura?** |
| 3 | D2 | Velocidad — ¿hacia dónde se mueve? |

**D3 debe estar al mismo nivel que D2 en el plan de expansión.** No después.

---

## Corrección al prompt

Agregar a la sección C17 (variantes D2):

### C17b — Variantes D3 para señales D1-only (prioridad inmediata)
**Datos:** r(D1,D3) ≈ 0 en 11 estaciones. D3=0 en D1=5 da SPY -6.72% vs D3=3 da +1.28%. D3 cambia el signo del trade dentro del mismo D1.
**Propuesta:** Para cada señal D1-only de alto score, crear variante con constraint D3:
- `vix_crisis_spike_D3_low` (D1=5, D3≤1) → pánico con convicción = continuación bajista
- `vix_crisis_spike_D3_high` (D1=5, D3≥3) → pánico sin convicción = reversión alcista
- `skew_complacencia_D3_low` (D1=0, D3≤1) → complacencia real = seguir largo
- `skew_complacencia_D3_high` (D1=0, D3≥3) → calma falsa = alerta de salida

### C18b — Fact Store alignment: incluir D3 en el cruce
El Fact Store tiene `p_bull` por state_key completo (D1__D2__D3). El cruce debe ser sobre el state_key completo, no solo D1.
**Propuesta:** El `fact_store_alignment` debe comparar el `p_bull` del state_key real (D1×D2×D3) con el hit rate observado, no solo D1.