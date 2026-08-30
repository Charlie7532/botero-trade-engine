# METAR Fact Store Guide — Estructura e Interpretación

> **Módulo de**: [fact_store_v3_architecture.md](file:///root/botero-trade/.agents/references/metar/fact_store_v3_architecture.md) §1 + §5–8
> **Status**: `PRODUCTION` | **Last Update**: 29-Ago-2026
> **Relacionados**: [d1_labels_canonical.md](file:///root/botero-trade/.agents/references/metar/d1_labels_canonical.md), [signal_rules.md](file:///root/botero-trade/.agents/references/metar/signal_rules.md)

---

## 1. Qué Es un Fact Store

Un Fact Store es un **JSON de probabilidades prospectivas** condicionado al estado observable del mercado. Para cada combinación D1×D2×D3, contiene estadísticas de lo que históricamente ocurrió DESPUÉS.

| | **Fact Store** (Prospección) | **quants_obs** (Historia) |
|---|---|---|
| **Dirección** | → ADELANTE | ← ATRÁS |
| **Pregunta** | "Dado HOY el estado X, ¿qué espero?" | "En pivotes pasados con estado X, ¿qué pasó?" |
| **Población** | Todos los días de mercado en el estado | Solo los pivotes ZigZag (MAX/MIN) |
| **Uso** | Engine de decisión en producción | Validación empírica (backtest) |

**Regla:** Si divergen >20%, investigar el sesgo de selección por `pivot_type`.

---

## 2. Estructura de un State Key

```
state_key = "{D1_label}__{D2_label}__{D3_label}"
```

Ejemplo: `NEUTRAL_ALERT__ACCELERATING_UP_3D__VOL_ACCELERATING_EXPANSION`

Cada estado contiene 3 capas de información:

### Capa Estándar (`zz25`/`zz50`/`zz75`)

Estadísticas condicionales del retorno de SPY medido con ZigZag a 3 escalas:

```json
{
  "n": 45,
  "p_bull": 0.622,
  "ev": 0.00185,
  "sharpe": 0.34,
  "rr_asymmetry": 1.42,
  "avg_bull": 0.0312,
  "avg_bear": -0.0220,
  "ftt_median_days": 3.0
}
```

| Campo | Significado |
|---|---|
| `n` | Observaciones históricas en este estado |
| `p_bull` | P(retorno positivo) condicional a este estado |
| `ev` | Expected Value = p_bull × avg_bull + (1-p_bull) × avg_bear |
| `sharpe` | Sharpe ratio condicional |
| `rr_asymmetry` | Asimetría risk/reward: `|avg_bull| / |avg_bear|` |
| `ftt_median_days` | First-Touch-Time mediano (cuántos días hasta completar la pierna ZZ) |

### Capa Cinemática (`zigzag_kinematic`)

Descomposición de la pierna ZigZag actual por tipo de movimiento:

```json
"zigzag_kinematic": {
  "zz25": {"n": 45, "p_bull": 0.622, "momentum": "CONTINUATION", ...},
  "zz50": {"n": 23, "p_bull": 0.565, "momentum": "REVERSAL", ...}
}
```

### Structural Momentum

Tendencia HH/HL/LH/LL — la secuencia de altos y bajos:
- `CONTINUATION`: Same direction as prior leg
- `REVERSAL`: Opposite direction
- `ACCELERATION`: Increasing magnitude
- `DECELERATION`: Decreasing magnitude

---

## 3. Regímenes de Divergencia Temporal (Horizon Divergence)

Cuando `zz25` y `zz75` divergen en dirección, se activa un régimen de divergencia:

| zz25 | zz75 | Régimen | Interpretación |
|---|---|---|---|
| BULL | BULL | **Convergencia alcista** | Alta convicción larga |
| BEAR | BEAR | **Convergencia bajista** | Alta convicción corta/protección |
| BULL | BEAR | **Rebote táctico en bear estructural** | Scalp/swing corto horizonte |
| BEAR | BULL | **Pullback táctico en bull estructural** | Dip-buying con stops anchos |

---

## 4. Lectura Correcta de un Estado

Dado el state_key `EXTREME_PANIC__FAST_SPIKE_3D__VOL_ACCELERATING_EXPANSION`:

1. **D1 = EXTREME_PANIC**: VIX en el percentil >97.72% histórico (bin 5, extremo superior)
2. **D2 = FAST_SPIKE_3D**: La velocidad de cambio en 3 días está en >97.72% (subida extrema)
3. **D3 = VOL_ACCELERATING_EXPANSION**: La volatilidad intra-indicador está expandiéndose

→ Esto describe un **spike de VIX extremo, acelerándose, con inestabilidad creciente**. Verificar overflow con `validate_overflow()` para determinar si es T1 (3σ) o T4+ (blow-off).
