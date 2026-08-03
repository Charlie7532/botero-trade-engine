# SV5 Institutional Volume Turbulence Intelligence — Reference Document

> **Auto-generated**: 2026-08-03T19:05:25Z | **Source**: `sv5_turbulence_fact_store.json` | **Status**: `VALIDATED (Grade A)`

## 1. Ficha Técnica del Indicador
- **Nombre**: SV5 Institutional Volume Turbulence (`SV5_TURBULENCE`)
- **Fórmula**: std(Δ_SV5TW, 10d) — desviación estándar del cambio en participación institucional.
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='SV5_TURBULENCE', timeframe='1d').
- **Rango Histórico**: 1999-01-19 → 2026-07-30 (6,922 barras diarias / 27.47 años).
- **Umbrales Percentiles L0** (empíricos del Fact Store):
  - `DEEP_SERENITY`: $< 2.71$
  - `SERENE_VOLUME`: $2.71 - 3.56$
  - `NORMAL_PARTICIPATION`: $3.56 - 4.85$
  - `ELEVATED_PARTICIPATION`: $4.85 - 7.46$
  - `HIGH_VOLUME_TURBULENCE`: $7.46 - 10.95$
  - `EXTREME_TURBULENCE_SHOCK`: $10.95 - 14.87$
  - `CRISIS_TURBULENCE_VETO`: $> 14.87$

---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Std = 3.3694.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store. PurgedKFold con 10 días de purga.
- **DSR p-value**: **0.9958** ✅ (significativo)
- **Mean Sharpe Ratio**: 0.5428 ± 0.3774 (5 folds)
- **Fold SRs**: [0.0253, 0.2647, 0.7484, 0.6801, 1.0978]

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\sigma^2_{\text{epistémica}}$): **0.000000** (N=49 estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas por N

| Escala ZigZag | Horizonte Máximo | $EV_{\text{net}}$ (ponderado) | $P(\text{bull})$ (ponderado) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+0.02%` | `54.8%` | `6.5d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `+0.47%` | `59.1%` | `20.5d` |
| **`zz75` (7.5% Estructural)** | 90 días | `+1.19%` | `62.2%` | `38.8d` |

**Población total**: 6,921 observaciones | $P(\text{bull})$ ponderado = 59.1% | $EV_{50}$ ponderado = +0.47%

---

## 3. Anomalías Empíricas (extraídas del Fact Store, N ≥ 20)

### 🚨 Anomalía Empírica 1: `CRISIS_TURBULENCE_VETO__STABLE_3D` (Alcista)
- **Condición**: Estado empírico con N=65 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 75.4\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.44\%$, $EV_{\text{per\_day}} = +0.1437\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### 🚨 Anomalía Empírica 2: `CRISIS_TURBULENCE_VETO__EXTREME_TURBULENCE_SPIKE_3D` (Alcista)
- **Condición**: Estado empírico con N=112 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 76.8\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.19\%$, $EV_{\text{per\_day}} = +0.1045\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### 🚨 Anomalía Empírica 3: `CRISIS_TURBULENCE_VETO__DECELERATING_3D` (Alcista)
- **Condición**: Estado empírico con N=40 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 67.5\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +1.71\%$, $EV_{\text{per\_day}} = +0.0951\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### ⚠️ Anomalía Bajista 1: `SERENE_VOLUME__STABLE_3D`
- **Condición**: Estado empírico con N=269 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 46.1\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.82\%$.
- **Régimen**: `FULL_STRUCTURAL_BEAR` → `STK_BLOCK_CRISIS`.

### ⚠️ Anomalía Bajista 2: `EXTREME_TURBULENCE_SHOCK__RISING_3D`
- **Condición**: Estado empírico con N=100 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 51.0\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.54\%$.
- **Régimen**: `TACTICAL_PULLBACK` → `STK_BUY_DIP_TACTICAL`.

### ⚠️ Anomalía Bajista 3: `HIGH_VOLUME_TURBULENCE__EXTREME_TURBULENCE_SPIKE_3D`
- **Condición**: Estado empírico con N=64 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 56.2\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.49\%$.
- **Régimen**: `TACTICAL_PULLBACK` → `STK_BUY_DIP_TACTICAL`.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\text{bull})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `SV5_TURBULENCE` | `VALIDATED (Grade A)` | **0.9958** | 0.5428 | 59.1% | 49 | 0 | **Grade C — Informational Only** |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**: Turbulencia > P95 indica régimen de vol institucional.
2. **`CIO Allocator`**: Turbulencia es proxy de VIX cuando VIX no está disponible.
