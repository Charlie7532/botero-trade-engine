# US Treasury Yield Curve Spread (TNX - IRX) Intelligence — Reference Document

> **Auto-generated**: 2026-08-03T19:05:29Z | **Source**: `yield_curve_fact_store.json` | **Status**: `VALIDATED (Grade A)`

## 1. Ficha Técnica del Indicador
- **Nombre**: US Treasury Yield Curve Spread (TNX - IRX) (`YIELD_CURVE`)
- **Fórmula**: Diferencial de rendimiento entre bonos del Tesoro a 10 años (TNX) y 3 meses (IRX).
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='YIELD_CURVE', timeframe='1d').
- **Rango Histórico**: 1993-01-29 → 2026-07-30 (8,402 barras diarias / 33.34 años).
- **Umbrales Percentiles L0** (empíricos del Fact Store):
  - `DEEP_INVERSION`: $< -0.62$
  - `MODERATE_INVERSION`: $-0.62 - 0.18$
  - `FLAT_CURVE`: $0.18 - 0.90$
  - `NORMAL_STEEP`: $0.90 - 1.97$
  - `STEEP_CURVE`: $1.97 - 2.83$
  - `VERY_STEEP_CURVE`: $2.83 - 3.37$
  - `EXTREME_STEEPENING_UNINVERSION`: $> 3.37$

---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Std = 0.0561.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store. PurgedKFold con 10 días de purga.
- **DSR p-value**: **1.0000** ✅ (significativo)
- **Mean Sharpe Ratio**: 0.5536 ± 0.5031 (5 folds)
- **Fold SRs**: [0.7869, -0.0839, 0.0711, 1.1452, 1.0315]

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\sigma^2_{\text{epistémica}}$): **0.000001** (N=49 estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas por N

| Escala ZigZag | Horizonte Máximo | $EV_{\text{net}}$ (ponderado) | $P(\text{bull})$ (ponderado) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+0.15%` | `55.7%` | `6.6d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `+0.97%` | `61.9%` | `20.8d` |
| **`zz75` (7.5% Estructural)** | 90 días | `+1.72%` | `64.0%` | `38.8d` |

**Población total**: 8,401 observaciones | $P(\text{bull})$ ponderado = 61.9% | $EV_{50}$ ponderado = +0.97%

---

## 3. Anomalías Empíricas (extraídas del Fact Store, N ≥ 20)

### 🚨 Anomalía Empírica 1: `VERY_STEEP_CURVE__EXTREME_FLATTENING_3D` (Alcista)
- **Condición**: Estado empírico con N=53 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 52.8\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +6.12\%$, $EV_{\text{per\_day}} = +0.7205\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### 🚨 Anomalía Empírica 2: `EXTREME_STEEPENING_UNINVERSION__DECELERATING_SPREAD_3D` (Alcista)
- **Condición**: Estado empírico con N=75 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 37.3\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.85\%$, $EV_{\text{per\_day}} = +0.1679\%/\text{día}$.
- **Régimen**: `TACTICAL_PULLBACK` → `STK_BUY_DIP_TACTICAL`.

### 🚨 Anomalía Empírica 3: `VERY_STEEP_CURVE__FAST_FLATTENING_3D` (Alcista)
- **Condición**: Estado empírico con N=106 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 61.3\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.77\%$, $EV_{\text{per\_day}} = +0.1789\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### ⚠️ Anomalía Bajista 1: `MODERATE_INVERSION__EXTREME_FLATTENING_3D`
- **Condición**: Estado empírico con N=35 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 40.0\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -1.68\%$.
- **Régimen**: `FULL_STRUCTURAL_BEAR` → `STK_BLOCK_CRISIS`.

### ⚠️ Anomalía Bajista 2: `EXTREME_STEEPENING_UNINVERSION__FAST_STEEPENING_3D`
- **Condición**: Estado empírico con N=62 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 41.9\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.92\%$.
- **Régimen**: `TACTICAL_PULLBACK` → `STK_BUY_DIP_TACTICAL`.

### ⚠️ Anomalía Bajista 3: `EXTREME_STEEPENING_UNINVERSION__FAST_FLATTENING_3D`
- **Condición**: Estado empírico con N=33 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 51.5\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.58\%$.
- **Régimen**: `FULL_STRUCTURAL_BEAR` → `STK_BLOCK_CRISIS`.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\text{bull})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `YIELD_CURVE` | `VALIDATED (Grade A)` | **1.0000** | 0.5536 | 61.9% | 49 | 12 | **Grade C — Informational Only** |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**: Inversión profunda (P05) es SIGMET — pero es crónica, filtrar por velocidad.
2. **`CIO Allocator`**: Yield curve es dimensión macro independiente.
