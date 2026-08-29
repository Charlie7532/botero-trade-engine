# METAR D1×D2×D3 Labels — Canonical Reference

> **Módulo de**: [fact_store_v3_architecture.md](file:///root/botero-trade/.agents/references/metar/fact_store_v3_architecture.md) §4.2–4.4
> **Status**: `CANONICAL SOURCE OF TRUTH` | **Last Audit**: 29-Ago-2026
> **Integrity Guard**: [`test_taxonomy_integrity.py`](file:///root/botero-trade/tests/test_taxonomy_integrity.py) (46 tests)
> **Relacionados**: [gaussian_scale_policy.md](file:///root/botero-trade/.agents/references/metar/gaussian_scale_policy.md)

---

## D1 — Magnitud Puntual (6 bines por estación)

**Clasificación:** Expanding Window Percentile Rank con zero look-ahead bias. Los edges Gaussianos `[0.0228, 0.1587, 0.5000, 0.8413, 0.9772]` (= `[-2σ, -1σ, μ, +1σ, +2σ]`) se aplican al rank, NO al valor crudo.

| Estación | Bin 0 (< −2σ) | Bin 1 | Bin 2 | Bin 3 | Bin 4 | Bin 5 (> +2σ) |
|---|---|---|---|---|---|---|
| **VIX** | DEEP_COMPLACENCY | LOW_VOL | MODERATE_VOL | HIGH_VOL | ELEVATED_PANIC | CRISIS_SPIKE |
| **BSI** | BREADTH_WASHED_OUT | OVERSOLD_BREADTH | NEUTRAL_LOW_BREADTH | NEUTRAL_HIGH_BREADTH | EXPANSIVE_BREADTH | HYPER_EXPANSIVE_BREADTH |
| **F&G** | EXTREME_FEAR | FEAR | NEUTRAL_FEAR | GREED | EXTREME_GREED | EUPHORIA |
| **Credit** | CREDIT_CRISIS | CREDIT_STRESS | ELEVATED_CREDIT_STRESS | STABLE_CREDIT | CREDIT_EASE | DEEP_CREDIT_EASE |
| **Rotation** | DEFENSIVE_CAPITULATION | DEFENSIVE | NEUTRAL_ROTATION | BALANCED | CYCLICAL_LEADERSHIP | AGGRESSIVE_ROTATION |
| **PCR** | EXTREME_CALL_HEAVY | BULLISH_PCR | NEUTRAL_PCR | ELEVATED_PCR | HIGH_PUT_PANIC | EXTREME_PUT_PANIC |
| **VVIX** | EXTREME_COMPLACENCY | LOW_VVIX | MODERATE_VVIX | HIGH_VVIX | ELEVATED_VVIX | EXTREME_VVIX |
| **SV5 Turb** | QUIET_FLOW | LOW_TURBULENCE | MODERATE_TURBULENCE | HIGH_TURBULENCE | ELEVATED_TURBULENCE | CRISIS_TURBULENCE |
| **SKEW** | LOW_TAIL_RISK | NORMAL_TAIL_RISK | ELEVATED_TAIL_RISK | HIGH_TAIL_RISK | TAIL_PARANOIA | BLACK_SWAN_PARANOIA |
| **Yield** | DEEP_INVERSION | MODERATE_INVERSION | FLAT_CURVE | NORMAL_CURVE | STEEPNING_CURVE | EXTREME_STEEPNING |
| **DXY** | DEEP_DOLLAR_CRUSH | WEAK_DOLLAR | MODERATE_LOW_DOLLAR | MODERATE_HIGH_DOLLAR | ELEVATED_DOLLAR_STRESS | DOLLAR_SPIKE_CRISIS |

**Fuente autoritativa:** `backend/scripts/generators/generate_{station}_fact_table.py` → variable `D1_LABELS` o `D1_BINS`.

> [!CAUTION]
> **NUNCA inferir, "recordar", ni inventar labels D1.** Copiar LITERALMENTE de esta tabla o del generador correspondiente. El 29-Ago-2026 un agente inventó labels para 9/11 estaciones, incluyendo una inversión física del Credit que etiquetaba la GFC 2008 como "crédito fácil". El test `test_taxonomy_integrity.py` previene este error.

---

## D2 — Velocidad Cinemática (5 bines, universales)

**Dato crudo:** `vel = val[t] - val[t-3]` → cambio aritmético del indicador en 3 días hábiles.

**Edges Gaussianos:** `[0.0228, 0.1587, 0.8413, 0.9772]` sobre expanding rank de `vel`.

| Bin | Label | Significado |
|:---:|---|---|
| 0 | `FAST_CRUSH_3D` | Caída extrema en 72h (< −2σ) |
| 1 | `DECELERATING_DOWN_3D` | Bajando moderadamente (−2σ a −1σ) |
| 2 | `STABLE_CONTINUATION_3D` | Sin cambio significativo (−1σ a +1σ) |
| 3 | `ACCELERATING_UP_3D` | Subiendo moderadamente (+1σ a +2σ) |
| 4 | `FAST_SPIKE_3D` | Subida extrema en 72h (> +2σ) |

---

## D3 — Estabilidad/Volatilidad Intra-Indicador (5 bines, universales)

**Dato crudo:** `instability = std(val, 2d) / std(val, 10d)` → ratio de volatilidad reciente vs normal (V1.1).

**Edges Gaussianos:** `[0.0228, 0.1587, 0.8413, 0.9772]` sobre expanding rank de `instability`.

| Bin | Label | Significado |
|:---:|---|---|
| 0 | `VOL_EXTREME_SQUEEZE` | Indicador excepcionalmente quieto |
| 1 | `VOL_MODERATE_COMPRESSION` | Compresión moderada de la volatilidad |
| 2 | `VOL_NEUTRAL_BASELINE` | Volatilidad normal del indicador |
| 3 | `VOL_ACCELERATING_EXPANSION` | Volatilidad creciente |
| 4 | `VOL_PEAK_DECELERATION` | Pico de volatilidad desacelerando |

---

## State Key — Composición

```
state_key = "{D1_label}__{D2_label}__{D3_label}"
```

Ejemplo: `CRISIS_SPIKE__FAST_SPIKE_3D__VOL_ACCELERATING_EXPANSION`

Espacio teórico: 6 × 5 × 5 = **150 estados** por estación. En la práctica, ~100-130 estados se observan empíricamente.

---

## Dirección Física por Estación

Bin 0 corresponde siempre al **valor más bajo** del indicador en expanding rank. La semántica depende de si el valor bajo es "bueno" o "malo":

| Estación | Valor bajo = | Valor alto = | Dirección |
|---|---|---|---|
| VIX | Complacencia | Crisis | ↑ = peor |
| Credit (HYG/LQD) | Estrés crediticio | Facilidad crediticia | ↑ = mejor |
| F&G | Miedo extremo | Euforia | ↑ = mejor (contrarian: peor) |
| BSI (S5TW) | Breadth destruido | Breadth expansivo | ↑ = mejor |
| PCR | Exceso de calls | Pánico en puts | ↑ = peor |
| Rotation | Capitulación defensiva | Rotación agresiva | ↑ = risk-on |
| Yield Spread | Inversión profunda | Curva empinada | ↑ = expansión |
