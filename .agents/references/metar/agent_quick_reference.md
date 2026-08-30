# METAR Agent Quick Reference — Operación con la Data

> **Status**: `PRODUCTION` | **Created**: 30-Ago-2026 (homologación canónica)
> **Scope**: Todo agente que trabaje con fact stores, señales METAR, clasificación de estados, o decisiones de mercado.
> **Documentación completa**: [fact_store_v3_architecture.md](file:///root/botero-trade/.agents/references/metar/fact_store_v3_architecture.md) (1,264 líneas)

---

## Regla #1: Polaridad por `d1_vote` y Bins para Comparar

```python
# 1. POLARIDAD: Usa d1_vote (-1/0/+1). NO interpretes d1_bin direccionalmente sin contexto.
#    d1_vote = -1 (Bearish/Riesgo), 0 (Neutro), +1 (Bullish/Oportunidad)
#    Un bin 5 en VIX es BEARISH (d1_vote=-1), pero un bin 5 en Credit es BULLISH (d1_vote=+1).

# 2. COMPARACIONES: Compara contra bin numérico, NUNCA contra labels string.
if vix_d1_bin >= 3:  # NEUTRAL_ALERT + PANIC + EXTREME_PANIC
    trigger_crisis_protocol()

# ❌ INCORRECTO — comparar contra label string
if vix_label in {"PANIC", "EXTREME_PANIC"}:  # frágil, pierde NEUTRAL_ALERT
    trigger_crisis_protocol()
```

Los labels semánticos viven **exclusivamente** en `_documentation.taxonomy` del JSON y se usan solo para presentación al usuario humano.

---

## Definición Universal de "Extremo" (±2σ en D1 / D2 / D3)

> Cuando cualquier código, documento o señal se refiere a un estado como **"extremo"**, corresponde estrictamente a los bines de **±2σ** (2.28% de la población cada uno):
> - **D1 Extremos (6 bins, 0..5):** `d1_bin in {0, 5}` (Bin 0 < −2σ, Bin 5 ≥ +2σ)
> - **D2 Extremos (5 bins, 0..4):** `d2_bin in {0, 4}` (Bin 0 `FAST_CRUSH_3D`, Bin 4 `FAST_SPIKE_3D`)
> - **D3 Extremos (5 bins, 0..4):** `d3_bin in {0, 4}` (Bin 0 `VOL_EXTREME_SQUEEZE`, Bin 4 `VOL_PEAK_DECELERATION`)

```python
def es_extremo(d1_bin: int, d2_bin: int, d3_bin: int) -> bool:
    """Detecta si alguna dimensión está en su cola gaussiana extrema (+-2sigma)."""
    d1_extremo = d1_bin in {0, 5}  # 6 bines
    d2_extremo = d2_bin in {0, 4}  # 5 bines
    d3_extremo = d3_bin in {0, 4}  # 5 bines
    return d1_extremo or d2_extremo or d3_extremo
```

---

## Anatomía de un State Key

```
State Key: "4__1__3"
             │  │  │
             │  │  └─ D3 bin 3 = VOL_ACCELERATING_EXPANSION
             │  └──── D2 bin 1 = DECELERATING_DOWN_3D
             └─────── D1 bin 4 = PANIC (VIX) / PARANOIA (SKEW) / etc.
```

| Dimensión | Bines | Rango | Extremos (±2σ) | Neutro |
|:----------|:-----:|:------|:---------------|:-------|
| **D1** (Magnitud) | 6 (0-5) | `[-2σ, -1σ, μ, +1σ, +2σ]` | 0 y 5 | 2 y 3 |
| **D2** (Velocidad Δ3d) | 5 (0-4) | `[-2σ, -1σ, +1σ, +2σ]` | 0 y 4 | 2 |
| **D3** (Estabilidad) | 5 (0-4) | `[-2σ, -1σ, +1σ, +2σ]` | 0 y 4 | 2 |

Espacio teórico: 6×5×5 = **150 estados** por estación. Observados: ~95-131.

---

## Tabla de Comparaciones Rápidas

| Concepto | Comparación | Cobertura |
|:---------|:-----------|:----------|
| D1 Extremo alto | `d1_bin >= 4` (o `== 5` para >+2σ) | Bins 4 + 5 |
| D1 Extremo bajo | `d1_bin <= 1` (o `== 0` para <-2σ) | Bins 0 + 1 |
| D2 Extremo spike | `d2_bin == 4` (>+2σ) / `d2_bin >= 3` | FAST_SPIKE / ACCEL+SPIKE |
| D2 Extremo crush | `d2_bin == 0` (<-2σ) / `d2_bin <= 1` | FAST_CRUSH / DECEL+CRUSH |
| D3 Inestabilidad alta | `d3_bin == 4` (>+2σ) / `d3_bin >= 3` | VOL_PEAK / ACCEL+PEAK |
| D3 Compresión extrema | `d3_bin == 0` (<-2σ) / `d3_bin <= 1` | VOL_SQUEEZE / COMP+SQUEEZE |
| Zona neutra / baseline | `d1_bin in {2, 3}`, `d2_bin == 2`, `d3_bin == 2` | Centro de campana |
| Bin extremo D1 (→ verificar overflow) | `d1_bin in {0, 5}` | → `validate_overflow()` |

---

## Polaridad por Estación

> **No todas las estaciones tienen la misma polaridad.** Un bin 5 en VIX es MALO, pero un bin 5 en Credit es BUENO.

| Estación | Bin 0 = | Bin 5 = | `d1_bin >= 4` es... |
|:---------|:--------|:--------|:--------------------|
| **VIX** | Complacencia | Pánico | 🔴 BEARISH |
| **VVIX** | Estabilidad | Inestabilidad | 🔴 BEARISH |
| **PCR** | Euforia en calls | Pánico en puts | 🔴 BEARISH (contrarian: 🟢) |
| **SKEW** | Confianza | Paranoia | 🔴 BEARISH |
| **SV5 Turb** | Calma | Turbulencia | 🔴 BEARISH |
| **Credit** | Estrés | Facilidad | 🟢 BULLISH |
| **BSI** | Breadth destruido | Expansión hiper | 🟢 BULLISH |
| **F&G** | Miedo extremo | Codicia extrema | ⚠️ CONTRARIAN |
| **Rotation** | Defensivo | Ofensivo | 🟢 RISK-ON |
| **Yield** | Inversión profunda | Curva empinada | 🟢 EXPANSIÓN |
| **DXY** | Dólar débil | Dólar fuerte | 🔴 BEARISH (equities) |

---

## Las 5 Señales del Núcleo Robusto (OOS Validadas)

| Señal | Condición en Bins | Mejor Celda | N | Edge IS | OOS | Decay |
|:------|:-----------------|:----------:|:-:|:-------:|:---:|:-----:|
| **capitulacion** | `VIX >= 3 & BSI == 0` | zz25·BAJA | 28 | +3.40% | +2.64% | 0.77 |
| **pcr_put_panic** | `PCR == 5` | zz75·BAJA | 28 | +4.04% | +2.56% | 0.63 |
| **vvix_entry** | `VVIX == 5` | zz75·ALZA | 45 | +3.11% | +2.08% | 0.67 |
| **credit_stress** | `CREDIT <= 1` | zz75·ALZA | 101 | +3.42% | +1.43% | 0.42 |
| **bsi_washed_out** | `BSI == 0` | zz25·BAJA | 65 | +1.73% | +0.99% | 0.57 |

> **N sobre 1,354 pivotes** (población deduplicada — tras eliminar 236 fechas de pivote duplicado).
> **Fuente:** [`validacion_oos_catalogo_v7.json`](file:///root/botero-trade/data/research/signals/validacion_oos_catalogo_v7.json). Edge IS = `in_sample_fav_neto`; OOS = `oos_edge_medio_pct`; Decay = `decay_oos_vs_is`.

---

## Acceso a Fact Stores en Producción

```python
import json

# Ruta de los fact stores
FACT_STORE_PATH = "backend/modules/entry_decision/domain/rules/{station}_fact_store.json"

# Leer un estado
with open("backend/modules/entry_decision/domain/rules/vix_fact_store.json") as f:
    fs = json.load(f)

state = fs["5__4__3"]               # ← bin numérico, NUNCA label
p_bull = state["zz75"]["p_bull"]    # → probabilidad
ev = state["zz75"]["ev"]           # → expected value

# Labels (solo para presentación):
labels = fs["_documentation"]["taxonomy"]
label = labels["d1"]["labels"][5]   # → "EXTREME_PANIC"
```

---

## Clasificador Centralizado

```python
from backend.modules.entry_decision.domain.rules.metar_classifier import (
    classify_bin,      # valor crudo → bin index
    make_state_key,    # (d1, d2, d3) → "5__4__3"
    decode_state_key,  # "5__4__3" → (5, 4, 3)
    resolve_label,     # bin + labels → "EXTREME_PANIC"
)
```

---

## Señales en el Arnés de Investigación

```python
# Las 31 señales usan _get_dim() para extraer bins numéricos
from research.01_señales_entry_exit.arnes.señales import _get_dim

# _get_dim(df, "vix", 0)  → D1 bin numérico desde "vix_sk"
# _get_dim(df, "vix", 1)  → D2 bin numérico
# _get_dim(df, "vix", 2)  → D3 bin numérico
```

---

## Overflow / Blow-Off (Capa Paralela)

```python
# Overflows NO modifican el bin (el bin se clipea a [0, 5])
# Overflows operan sobre z-score crudo en paralelo

# Data Lake: columnas {st}_overflow_tier_d1, _d2, _d3
# Valores: 0 (normal), 1 (T1: 3-4σ), ..., 5 (T5: ≥10σ)

# Producción:
from backend.modules.entry_decision.domain.rules.sigma_overflow import validate_overflow
# validate_overflow(z_score) → (sigma_depth, tier, hazard_type)
```

| Tier | Rango σ | Acción |
|:---:|:---:|:---|
| T1 | 3-4σ | `STK_HOLD_STABLE` |
| T2 | 4-5σ | `STK_BLOCK_CRISIS` |
| T3 | 5-7σ | Circuit Breaker |
| T4 | 7-10σ | Solo coberturas |
| T5 | ≥10σ | Preservación capital |

---

## Anti-Patrones (NUNCA hacer)

1. ❌ Comparar contra labels string en código de producción
2. ❌ Promediar métricas entre escalas ZigZag (zz25 ≠ zz50 ≠ zz75)
3. ❌ Usar `fwd_20d` como métrica causal (usar ZigZag first-passage)
4. ❌ Inventar labels D1 — copiar de [d1_labels_canonical.md](file:///root/botero-trade/.agents/references/metar/d1_labels_canonical.md)
5. ❌ Degradar señales por N bajo en colas extremas (Protocolo §3.3)
6. ❌ Aplicar Bonferroni sobre §3.3
7. ❌ Tratar estados bin 0/5 como normales sin verificar overflow

> **Documentación completa de anti-patrones:** [anti_patterns.md](file:///root/botero-trade/.agents/references/metar/anti_patterns.md)
