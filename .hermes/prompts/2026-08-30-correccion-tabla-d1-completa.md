# CORRECCIÓN — Tabla D1 completa (11 estaciones) en gaussian_scale_policy.md

**Archivo:** `.agents/references/metar/gaussian_scale_policy.md`
**Problema:** La tabla de D1 (líneas 42-48) solo muestra 3 estaciones (VIX, FG, Credit) como ejemplos. Debe mostrar las **11 estaciones** completas, igual que en `d1_labels_canonical.md`.

---

## QUÉ HACER

### Estado actual (INCORRECTO) — líneas 41-48:

```
| Bin Index | Range | Percentile Band | Population % | Semantic Role | Ejemplos Canónicos |
|:---:|---|:---:|:---:|---|---|
| 0 | val < −2σ | P0 → P2.28 | 2.28% | Extremo inferior | VIX→EXTREME_COMPLACENCY, FG→EXTREME_FEAR, Credit→EXTREME_STRESS |
| 1 | −2σ ≤ val < −1σ | P2.28 → P15.87 | 13.59% | Bajo | VIX→COMPLACENCY, FG→FEAR, Credit→STRESS |
| 2 | −1σ ≤ val < μ | P15.87 → P50 | 34.13% | Neutro (sesgo bajo) | VIX→NEUTRAL_CALM, FG→NEUTRAL_FEAR, Credit→NEUTRAL_TIGHT |
| 3 | μ ≤ val < +1σ | P50 → P84.13 | 34.13% | Neutro (sesgo alto) | VIX→NEUTRAL_ALERT, FG→NEUTRAL_GREED, Credit→NEUTRAL_LOOSE |
| 4 | +1σ ≤ val < +2σ | P84.13 → P97.72 | 13.59% | Elevado | VIX→PANIC, FG→GREED, Credit→EASE |
| 5 | val ≥ +2σ | P97.72 → P100 | 2.28% | Extremo superior | VIX→EXTREME_PANIC, FG→EXTREME_GREED, Credit→EXTREME_EASE |
```

### Estado deseado (CORRECTO) — 11 estaciones, con referencias cruzadas:

**Opción A — Tabla vertical (11 filas por estación):**

```
| Bin | Range | % Pop | Estación | Bin 0 (< −2σ) | Bin 1 | Bin 2 (NEUTRAL bajo) | Bin 3 (NEUTRAL alto) | Bin 4 | Bin 5 (> +2σ) |
|:---:|---|:---:|:---|---:|---|---|---|---|---|
| | | | **VIX** | EXTREME_COMPLACENCY | COMPLACENCY | NEUTRAL_CALM | NEUTRAL_ALERT | PANIC | EXTREME_PANIC |
| | | | **VVIX** | EXTREME_STABILITY | STABILITY | NEUTRAL_STABLE | NEUTRAL_UNSTABLE | INSTABILITY | EXTREME_INSTABILITY |
| | | | **PCR** | EXTREME_CALL_EUPHORIA | CALL_EUPHORIA | NEUTRAL_CALL_BIAS | NEUTRAL_PUT_BIAS | PUT_PANIC | EXTREME_PUT_PANIC |
| | | | **F&G** | EXTREME_FEAR | FEAR | NEUTRAL_FEAR | NEUTRAL_GREED | GREED | EXTREME_GREED |
| | | | **SV5 Turb** | EXTREME_CALM | CALM | NEUTRAL_CALM | NEUTRAL_TURBULENT | TURBULENT | EXTREME_TURBULENT |
| | | | **SKEW** | EXTREME_CONFIDENCE | CONFIDENCE | NEUTRAL_CONFIDENT | NEUTRAL_PARANOID | PARANOIA | EXTREME_PARANOIA |
| | | | **Credit** | EXTREME_STRESS | STRESS | NEUTRAL_TIGHT | NEUTRAL_LOOSE | EASE | EXTREME_EASE |
| | | | **Yield** | DEEP_INVERSION | MODERATE_INVERSION | FLAT_CURVE | NORMAL_CURVE | STEEPNING_CURVE | EXTREME_STEEPNING |
| | | | **Rotation** | EXTREME_DEFENSIVE | DEFENSIVE | NEUTRAL_DEFENSIVE | NEUTRAL_OFFENSIVE | OFFENSIVE | EXTREME_OFFENSIVE |
| | | | **BSI** | BREADTH_WASHED_OUT | OVERSOLD_BREADTH | NEUTRAL_LOW_BREADTH | NEUTRAL_HIGH_BREADTH | EXPANSIVE_BREADTH | HYPER_EXPANSIVE_BREADTH |
| | | | **DXY** | EXTREME_WEAKNESS | WEAKNESS | NEUTRAL_WEAK | NEUTRAL_STRONG | STRENGTH | EXTREME_STRENGTH |
```

**Nota:** La información de rangos (val < −2σ, etc.) y porcentajes de población ya está en las filas de cabecera. Cada estación hereda esos rangos — no es necesario repetirlos por fila.

**Opción B — Más compacta (mantener estructura actual pero con todas las estaciones):**

La columna "Ejemplos Canónicos" pasaría de tener 3 ejemplos a tener 11, separados por `|`:

```
| 0 | val < −2σ | P0 → P2.28 | 2.28% | Extremo inferior | VIX→EXTREME_COMPLACENCY | VVIX→EXTREME_STABILITY | PCR→EXTREME_CALL_EUPHORIA | FG→EXTREME_FEAR | SV5→EXTREME_CALM | SKEW→EXTREME_CONFIDENCE | Credit→EXTREME_STRESS | Yield→DEEP_INVERSION | Rotation→EXTREME_DEFENSIVE | BSI→BREADTH_WASHED_OUT | DXY→EXTREME_WEAKNESS |
```

**Recomendación:** Opción A (tabla vertical) es más legible para agentes y humanos.

---

## REFERENCIA

Fuente autoritativa: `d1_labels_canonical.md` (líneas 30-42) — archivo verificado por 46 tests de integridad taxonómica.

```python
# Verificación contra los fact stores reales
# backend/scripts/generators/generate_{station}_fact_table.py → variable D1_LABELS
```

---

## VERIFICACIÓN POST-CORRECCIÓN

```bash
cd /root/botero-trade
# Verificar que las 11 estaciones aparecen
grep -c "\*\*" .agents/references/metar/gaussian_scale_policy.md | head -1
# Debe mostrar 11 líneas de estaciones

# Verificar contra d1_labels_canonical.md
# Extraer nombres de estaciones de ambos archivos y comparar
grep -E "^\|\| \*\*[A-Z]" d1_labels_canonical.md | wc -l
grep -E "^\|\| \*\*[A-Z]" gaussian_scale_policy.md | wc -l
# Ambos deben mostrar 11
```