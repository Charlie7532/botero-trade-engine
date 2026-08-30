# METAR D1×D2×D3 Labels — Canonical Reference

> **Módulo de**: [fact_store_v3_architecture.md](file:///root/botero-trade/.agents/references/metar/fact_store_v3_architecture.md) §4.2–4.4
> **Status**: `CANONICAL SOURCE OF TRUTH` | **Last Update**: 30-Ago-2026
> **Integrity Guard**: [`test_taxonomy_integrity.py`](file:///root/botero-trade/tests/test_taxonomy_integrity.py) (46 tests)
> **Relacionados**: [gaussian_scale_policy.md](file:///root/botero-trade/.agents/references/metar/gaussian_scale_policy.md)

---

## State Key — Formato Vectorial Numérico

```
state_key = "{D1_bin}__{D2_bin}__{D3_bin}"
```

**Los state keys son vectores numéricos**, no strings de labels. Ejemplo: `"5__4__4"` = `taxonomy.d1.labels[5]` + `taxonomy.d2.labels[4]` + `taxonomy.d3.labels[4]`.

Los labels semánticos viven **exclusivamente** en la sección `_documentation.taxonomy` del JSON. Esto desacopla la nomenclatura de la estructura de datos — renombrar labels NO requiere regenerar fact stores.

Espacio teórico: 6 × 5 × 5 = **150 estados** por estación. En la práctica, ~95-131 estados se observan empíricamente.

---

## D1 — Magnitud Puntual (6 bines por estación)

**Clasificación:** Expanding Window Percentile Rank con zero look-ahead bias. Los edges Gaussianos `[0.0228, 0.1587, 0.5000, 0.8413, 0.9772]` (= `[-2σ, -1σ, μ, +1σ, +2σ]`) se aplican al rank, NO al valor crudo.

**Simetría canónica:** Todas las etiquetas siguen el patrón `EXTREME_{concepto}` / `{concepto}` / `NEUTRAL_{sesgo}` / `NEUTRAL_{antónimo_sesgo}` / `{antónimo}` / `EXTREME_{antónimo}`.

| Estación | Bin 0 (< −2σ) | Bin 1 | Bin 2 (NEUTRAL_) | Bin 3 (NEUTRAL_) | Bin 4 | Bin 5 (> +2σ) |
|---|---|---|---|---|---|---|
| **VIX** | EXTREME_COMPLACENCY | COMPLACENCY | NEUTRAL_CALM | NEUTRAL_ALERT | PANIC | EXTREME_PANIC |
| **VVIX** | EXTREME_STABILITY | STABILITY | NEUTRAL_STABLE | NEUTRAL_UNSTABLE | INSTABILITY | EXTREME_INSTABILITY |
| **PCR** | EXTREME_CALL_EUPHORIA | CALL_EUPHORIA | NEUTRAL_CALL_BIAS | NEUTRAL_PUT_BIAS | PUT_PANIC | EXTREME_PUT_PANIC |
| **F&G** | EXTREME_FEAR | FEAR | NEUTRAL_FEAR | NEUTRAL_GREED | GREED | EXTREME_GREED |
| **SV5 Turb** | EXTREME_CALM | CALM | NEUTRAL_CALM | NEUTRAL_TURBULENT | TURBULENT | EXTREME_TURBULENT |
| **SKEW** | EXTREME_CONFIDENCE | CONFIDENCE | NEUTRAL_CONFIDENT | NEUTRAL_PARANOID | PARANOIA | EXTREME_PARANOIA |
| **Credit** | EXTREME_STRESS | STRESS | NEUTRAL_TIGHT | NEUTRAL_LOOSE | EASE | EXTREME_EASE |
| **Yield** | DEEP_INVERSION | MODERATE_INVERSION | FLAT_CURVE | NORMAL_CURVE | STEEPNING_CURVE | EXTREME_STEEPNING |
| **Rotation** | EXTREME_DEFENSIVE | DEFENSIVE | NEUTRAL_DEFENSIVE | NEUTRAL_OFFENSIVE | OFFENSIVE | EXTREME_OFFENSIVE |
| **BSI** | BREADTH_WASHED_OUT | OVERSOLD_BREADTH | NEUTRAL_LOW_BREADTH | NEUTRAL_HIGH_BREADTH | EXPANSIVE_BREADTH | HYPER_EXPANSIVE_BREADTH |
| **DXY** | EXTREME_WEAKNESS | WEAKNESS | NEUTRAL_WEAK | NEUTRAL_STRONG | STRENGTH | EXTREME_STRENGTH |

**Fuente autoritativa:** `backend/scripts/generators/generate_{station}_fact_table.py` → variable `D1_LABELS` o `D1_BINS`.

> [!CAUTION]
> **NUNCA inferir, "recordar", ni inventar labels D1.** Copiar LITERALMENTE de esta tabla o del generador correspondiente. El 29-Ago-2026 un agente inventó labels para 9/11 estaciones, incluyendo una inversión física del Credit. El test `test_taxonomy_integrity.py` previene este error.

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

## Dirección Física por Estación

Bin 0 corresponde siempre al **valor más bajo** del indicador en expanding rank. La semántica depende de si el valor bajo es "bueno" o "malo":

| Estación | Valor bajo = | Valor alto = | Dirección |
|---|---|---|---|
| VIX | Complacencia | Pánico | ↑ = peor |
| VVIX | Estabilidad | Inestabilidad | ↑ = peor |
| Credit (HYG/LQD) | Estrés crediticio | Facilidad crediticia | ↑ = mejor |
| F&G | Miedo extremo | Codicia extrema | ↑ = mejor (contrarian: peor) |
| BSI (S5TW) | Breadth destruido | Breadth expansivo | ↑ = mejor |
| PCR | Exceso de calls | Pánico en puts | ↑ = peor |
| SKEW | Confianza | Paranoia | ↑ = peor |
| SV5 Turb | Calma | Turbulencia | ↑ = peor |
| Rotation | Defensivo | Ofensivo | ↑ = risk-on |
| Yield Spread | Inversión profunda | Curva empinada | ↑ = expansión |
| DXY | Dólar débil | Dólar fuerte | ↑ = peor (para equities) |

---

## Clasificador Centralizado

Archivo: [`metar_classifier.py`](file:///root/botero-trade/backend/modules/entry_decision/domain/rules/metar_classifier.py)

Funciones:
- `classify_bin(val, edges) → int` — Clasifica un valor crudo en un índice de bin
- `make_state_key(d1, d2, d3) → str` — Construye la clave `"5__3__3"`
- `decode_state_key(key) → (int, int, int)` — Parsea la clave
- `resolve_label(bin_idx, labels) → str` — Traduce índice a label semántico
