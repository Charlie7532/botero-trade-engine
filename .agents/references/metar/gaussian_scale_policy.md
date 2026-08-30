# Gaussian Sigma Scale Calibration Policy — Indicator Dimensional Classification

> **Status**: `MANDATORY POLICY` | **Version**: `1.1` | **Effective**: 2026-08-04
> **Scope**: All 10 METAR stations, all fact store generators, all lookup adapters
> **Last Calibration Audit**: 2026-08-04 — **7/9 PASS, 2 DRIFT (FG, YIELD_CURVE — integer resolution artifact)**

---

## 1. Fundamental Principle

All indicator bin edges in the Botero Trade Engine are derived from **Gaussian Normal Distribution σ-percentiles** applied to the **full historical population** of each indicator in the Neon Vault.

This is NOT arbitrary bucketing. The edges correspond to exact positions on the Gaussian bell curve, ensuring that:
- **Extreme bins** (±2σ) contain exactly **~2.28%** of historical observations
- **Moderate bins** (±1σ to ±2σ) contain exactly **~13.59%** each
- **Core bins** (within ±1σ) contain exactly **~68.27%** combined

---

## 2. Dimensional Schema (D1 × D2 × D3)

Every indicator observation is classified along 3 independent dimensions:

| Dimension | Variable | Formula | Interpretation |
|:---:|---|---|---|
| **D1** | Magnitud Puntual | Raw value of the indicator | "¿Dónde está?" |
| **D2** | Velocidad Cinemática | `diff(3)` — change over 3 trading days | "¿Hacia dónde se mueve?" |
| **D3** | Volatilidad de la Estación | `std(2d) / std(10d)` — vol ratio | "¿Está estable o agitada?" |

---

## 3. Edge Computation — Canonical Percentiles

### D1: Magnitud Puntual (6 bines, 5 edges)

```
Percentiles:  [0.0228,  0.1587,  0.5000,  0.8413,  0.9772]
Sigma:        [ -2σ,     -1σ,      μ,      +1σ,     +2σ   ]
```

| Bin Index | Range | Percentile Band | Population % | Semantic Role |
|:---:|---|:---:|:---:|---|
| 0 | val < −2σ | P0 → P2.28 | **2.28%** | Extremo inferior |
| 1 | −2σ ≤ val < −1σ | P2.28 → P15.87 | **13.59%** | Bajo |
| 2 | −1σ ≤ val < μ | P15.87 → P50 | **34.13%** | Neutro (sesgo bajo) |
| 3 | μ ≤ val < +1σ | P50 → P84.13 | **34.13%** | Neutro (sesgo alto) |
| 4 | +1σ ≤ val < +2σ | P84.13 → P97.72 | **13.59%** | Elevado |
| 5 | val ≥ +2σ | P97.72 → P100 | **2.28%** | Extremo superior |

Los labels semánticos específicos de cada estación están en [d1_labels_canonical.md](file:///root/botero-trade/.agents/references/metar/d1_labels_canonical.md). Para resolver un label dado un bin:

```python
import json
from backend.modules.entry_decision.domain.rules.metar_classifier import resolve_label

# Cargar labels del fact store de la estación
labels = json.load(open("backend/modules/entry_decision/domain/rules/vix_fact_store.json"))["_documentation"]["taxonomy"]["d1"]["labels"]
label = resolve_label(4, labels)  # → "PANIC" para VIX, "EASE" para Credit
```

Los overflows (> ±3σ) y blow-offs (> ±5σ) NO modifican el bin (se clipea a [0,5]). Operan en capa paralela sobre el z-score crudo. Ver [overflow_taxonomy.md](file:///root/botero-trade/.agents/references/metar/overflow_taxonomy.md) para la escala T1-T5. En código:

```python
from backend.modules.entry_decision.domain.rules.sigma_overflow import classify_overflow_tier

# z_score crudo del indicador
tier, hazard_name, hazard_type = classify_overflow_tier(z_score=4.2)
# → (2, "OVERFLOW_EXTREMO", "CRITICAL")
```

### D2: Velocidad Cinemática Δ3d (5 bines, 4 edges)

```
Percentiles:  [0.0228,  0.1587,  0.8413,  0.9772]
Sigma:        [ -2σ,     -1σ,     +1σ,     +2σ   ]
```

| Bin Index | Range | Population % | Label |
|:---:|---|:---:|---|
| 0 | vel < −2σ | **2.28%** | `FAST_CRUSH_3D` |
| 1 | −2σ ≤ vel < −1σ | **13.59%** | `DECELERATING_DOWN_3D` |
| 2 | −1σ ≤ vel < +1σ | **68.27%** | `STABLE_CONTINUATION_3D` |
| 3 | +1σ ≤ vel < +2σ | **13.59%** | `ACCELERATING_UP_3D` |
| 4 | vel ≥ +2σ | **2.28%** | `FAST_SPIKE_3D` |

### D3: Volatilidad de la Estación — Vol Ratio (5 bines, 4 edges)

```
Percentiles:  [0.0228,  0.1587,  0.8413,  0.9772]
Sigma:        [ -2σ,     -1σ,     +1σ,     +2σ   ]
```

| Bin Index | Range | Population % | Label |
|:---:|---|:---:|---|
| 0 | vr < −2σ | **2.28%** | `VOL_EXTREME_SQUEEZE` |
| 1 | −2σ ≤ vr < −1σ | **13.59%** | `VOL_MODERATE_COMPRESSION` |
| 2 | −1σ ≤ vr < +1σ | **68.27%** | `VOL_NEUTRAL_BASELINE` |
| 3 | +1σ ≤ vr < +2σ | **13.59%** | `VOL_ACCELERATING_EXPANSION` |
| 4 | vr ≥ +2σ | **2.28%** | `VOL_PEAK_DECELERATION` |

### 3.4 Definición Universal de "Extremo" (±2σ en D1 / D2 / D3)

> Cuando cualquier código, documento o señal se refiere a un estado como **"extremo"**, corresponde estrictamente a los bines de **±2σ** (2.28% de la población cada uno):
> - **D1 Extremos (6 bins, 0..5):** Bin 0 (< −2σ) y Bin 5 (≥ +2σ) → 2.28% cada uno.
> - **D2 Extremos (5 bins, 0..4):** Bin 0 (`FAST_CRUSH_3D`) y Bin 4 (`FAST_SPIKE_3D`) → 2.28% cada uno.
> - **D3 Extremos (5 bins, 0..4):** Bin 0 (`VOL_EXTREME_SQUEEZE`) y Bin 4 (`VOL_PEAK_DECELERATION`) → 2.28% cada uno.

Los percentiles Gaussianos son idénticos: `[0.0228, 0.1587, 0.5000, 0.8413, 0.9772]` para D1 (6 bins) y `[0.0228, 0.1587, 0.8413, 0.9772]` para D2/D3 (5 bins). D1 subdivide la zona media en dos bines (±1σ), mientras D2/D3 tienen un único bin central baseline.

---

## 4. Mandatory Implementation Rules

### Rule S1: Edges are Empirical Quantiles, Not Parametric

Edges are computed as:
```python
edges = series.quantile([0.0228, 0.1587, 0.8413, 0.9772])
```

This uses the **empirical quantile** of the full historical population — NOT the parametric Gaussian formula `μ ± kσ`. The Gaussian percentiles (0.0228, 0.1587, etc.) guarantee that each bin captures the correct proportion of observations **regardless of whether the data is normally distributed**.

This is critical because indicators like VIX and SKEW are **NOT normally distributed** — they are right-skewed with fat tails. Using `μ + 2σ` directly would place CRISIS_SPIKE at VIX=53 (wrong), while using P97.72 empirical places it at VIX≈40 (correct — captures the actual top 2.28% of observations).

### Rule S2: Full Historical Population is the Training Set

Edges MUST be computed from **all available data** in the Vault for each indicator:

| Indicator | Population Start | N Bars |
|---|---|---:|
| VIX | 1990-01-02 | ~9,236 |
| VVIX | 2006-03-06 | ~5,073 |
| SKEW | 1990-01-02 | ~9,198 |
| SV5_TURBULENCE | 1999-01-19 | ~6,927 |
| FG | 2011-01-03 | ~3,876 |
| PCR | 2006-10-17 | ~4,924 |
| CREDIT (HYG/LQD) | 2002+ | ~4,856 |
| YIELD_CURVE (TNX-IRX) | 1962+ | ~16,120 |
| ROTATION (composite) | 1999+ | ~6,941 |

### Rule S3: D2 Uses Raw `diff(3)`, Not Normalized

The velocity dimension D2 is computed as:
```python
d2 = series.diff(3)  # raw 3-day absolute change
```

Each indicator has its own D2 edges because the scale of `diff(3)` is indicator-specific:
- VIX diff(3) edges: `[-4.94, -1.72, +1.66, +5.43]`
- SKEW diff(3) edges: `[-9.37, -3.23, +3.30, +9.24]`

D2 is NOT cross-indicator comparable. Comparisons between indicators use the **bin label** (`FAST_SPIKE_3D`), never the raw value.

### Rule S4: D3 Uses Rolling Vol Ratio

```python
vol_2d = series.rolling(2).std()
vol_10d = series.rolling(10).std()
d3 = vol_2d / vol_10d  # vol_norm ratio
```

- `d3 > 1.0`: Short-term volatility exceeds long-term → station is agitated
- `d3 < 1.0`: Short-term volatility below long-term → station is compressing
- `d3 ≈ 1.0`: Equilibrium

> **V1.1 Change (2026-08-04)**: Changed from `std(5)/std(20)` to `std(2)/std(10)` based on empirical shootout across 135 SPY correction episodes. Results: `std(2)/std(10)` detects **80%** of corrections vs **46%** with `std(5)/std(20)` — same lead time (~14d). ATR variants tested (pseudo-ATR, real ATR) — all inferior to std. Root cause: 5-day numerator window smoothed away early excitation signals.
>
> **FG & YIELD_CURVE note**: `std(2)` can be exactly 0 when two consecutive integer values are identical, causing Bin 0 (VOL_EXTREME_SQUEEZE) to capture 0% instead of 2.28%. The missing population absorbs into Bin 1 (15.87% vs 13.59%). This is a data resolution artifact, not a calibration error.

### Rule S5: Labels Are Immutable

The D2 and D3 label sets are universal across all 9 indicators. They MUST NOT be renamed, reordered, or extended without updating ALL 9 fact stores, ALL 9 lookup adapters, and the `ConvergenceCompositor`.

D1 labels are indicator-specific but MUST maintain the same semantic ordering:
```
Index 0 = Extremo Inferior (lowest 2.28%)
Index 5 = Extremo Superior (highest 2.28%)
```

### Rule S6: Recalibration Protocol

Edges MUST be recalibrated when:
1. **Vault population grows by >20%** (e.g., a new year of data added)
2. **A structural regime shift** makes old data non-representative (e.g., post-2020 VIX regime)

Recalibration procedure:
1. Run `generate_all_150_state_fact_stores.py` (the canonical generator)
2. Verify edges via the calibration audit script
3. Confirm all 9 fact stores updated atomically
4. Log the recalibration event with before/after edges

### Rule S7: "Extreme" Means ±2σ (P2.28 / P97.72) — No Exceptions

When any code, documentation, or signal refers to a dimensional state as "extreme", it MUST correspond to the ±2σ bins:
- **D1 extremes (6 bins):** Bin 0 (< −2σ) or Bin 5 (≥ +2σ) → **2.28% of population each**
- **D2 extremes (5 bins):** Bin 0 (`FAST_CRUSH_3D`) or Bin 4 (`FAST_SPIKE_3D`) → **2.28% each**
- **D3 extremes (5 bins):** Bin 0 (`VOL_EXTREME_SQUEEZE`) or Bin 4 (`VOL_PEAK_DECELERATION`) → **2.28% each**

> **Regla:** Siempre comparar contra el bin numérico. El label semántico entre paréntesis es solo para referencia humana.

An indicator is NOT in an extreme state if it is in Bin 1 or Bin 4 (those are "elevated" = ±1σ to ±2σ).

For a generic function:
```python
def is_extreme(d1_bin: int, d2_bin: int, d3_bin: int) -> bool:
    d1_extreme = d1_bin in {0, 5}        # D1: 6 bins
    d2_extreme = d2_bin in {0, 4}        # D2: 5 bins (same ±2σ percentiles)
    d3_extreme = d3_bin in {0, 4}        # D3: 5 bins (same ±2σ percentiles)
    return d1_extreme or d2_extreme or d3_extreme
```

### Rule S8: Update Cadence — Full Pipeline Regeneration

| Cadencia | Acción | Comando | Responsable |
|:---------|:-------|:--------|:-----------:|
| **Diaria** | Ingesta al Vault (TimescaleDB) | EOD batch externo | Datos externos |
| **Semanal** | Verificar drift taxonómico | `pytest tests/test_taxonomy_integrity.py -q` | Automático (CI) |
| **Mensual** | Regeneración completa de artefactos | Ver Rule S9 | Humano o cron |
| **Por evento** | Bug / nueva señal / cambio taxonómico | Variable según evento | Humano |

### Rule S9: Monthly Regeneration Procedure

Ejecutar en **orden estricto** — cada paso depende del anterior:

```bash
cd /root/botero-trade

# 1. Fact stores (desde Vault) — regenera 11 JSON (~10 min)
PYTHONPATH=. backend/.venv/bin/python \
  backend/scripts/generators/generate_all_150_state_fact_stores.py

# 2. Lake continuo — regenera continuous_metar_lake.parquet (~3 min)
PYTHONPATH=. backend/.venv/bin/python \
  backend/scripts/generators/build_continuous_metar_lake.py

# 3. Tabla pivotal — regenera quants_obs.pkl (~1 min)
PYTHONPATH=. backend/.venv/bin/python \
  backend/scripts/generators/generate_quants_obs.py

# 4. Tests de regresión — verifica integridad (~1 min)
PYTHONPATH=. backend/.venv/bin/python -m pytest tests/ -q
```

**Artefactos generados (no versionados, regenerables):**
- `backend/modules/entry_decision/domain/rules/*_fact_store.json` (11 archivos)
- `data/research/continuous_metar_lake.parquet` (8,453×257)
- `data/research/pivots/quants_obs.pkl` (1,590×165)

> **NOTA:** Los scripts de investigación (evaluador vela-a-vela, tríada, anatomía) se ejecutan **a pedido**. No forman parte de la regeneración mensual.

---

## 5. Verified Calibration Audit (2026-08-04)

All 9 stations audited. Stored edges vs fresh-from-Vault edges:

| Station | Max Edge Drift | D1 Percentile Accuracy | Status |
|---|:---:|:---:|:---:|
| VIX | 0.016 (0.1%) | ±0.0% | ✅ PASS |
| VVIX | 0.073 (0.1%) | ±0.1% | ✅ PASS |
| PCR | 0.000 (0.0%) | ±0.1% | ✅ PASS |
| FG | 0.134 (0.3%) | ±0.7% | ✅ PASS |
| SV5_TURB | 0.002 (0.0%) | ±0.0% | ✅ PASS |
| SKEW | 0.005 (0.0%) | ±0.0% | ✅ PASS |
| CREDIT | 0.000 (0.0%) | ±0.0% | ✅ PASS |
| YIELD_CURVE | 0.001 (0.0%) | ±0.0% | ✅ PASS |
| ROTATION | 0.001 (0.2%) | ±0.0% | ✅ PASS |

> **FG note**: Fear & Greed uses integer values (0-100), so quantile edges snap to integers. P15.2% vs design P15.9% is a rounding artifact, not a calibration error.

---

## 6. Cross-Reference: Generator Files

| File | Role |
|---|---|
| [generate_all_150_state_fact_stores.py](file:///root/botero-trade/backend/scripts/generate_all_150_state_fact_stores.py) | **CANONICAL** generator — applies this policy |
| `backend/modules/entry_decision/domain/rules/*_lookup.py` | Runtime classifiers — read edges from JSON |
| `backend/modules/entry_decision/domain/rules/*_fact_store.json` | Persisted edges + state statistics |
