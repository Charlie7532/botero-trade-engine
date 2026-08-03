# Defensive/Cyclical Sector Rotation Index Intelligence — Reference Document

> **Auto-generated**: 2026-08-03T19:05:30Z | **Source**: `rotation_fact_store.json` | **Status**: `HYPOTHESIS (Grade D)`

## 1. Ficha Técnica del Indicador
- **Nombre**: Defensive/Cyclical Sector Rotation Index (`ROTATION`)
- **Fórmula**: Z-score de ratio XLY/XLP + XLK/XLU (rolling 252d) — mide rotación defensiva/cíclica.
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='ROTATION', timeframe='1d').
- **Rango Histórico**: 1998-12-28 → 2026-07-30 (6,939 barras diarias / 27.54 años).
- **Umbrales Percentiles L0** (empíricos del Fact Store):
  - `EXTREME_DEFENSIVE_ROTATION`: $< -3.57$
  - `DEFENSIVE_ROTATION`: $-3.57 - -2.09$
  - `MODERATE_DEFENSIVE`: $-2.09 - -0.47$
  - `BALANCED_ROTATION`: $-0.47 - 1.81$
  - `MODERATE_CYCLICAL`: $1.81 - 3.03$
  - `CYCLICAL_ROTATION`: $3.03 - 4.04$
  - `EXTREME_CYCLICAL_EXPANSION`: $> 4.04$

---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Std = 0.7390.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store. PurgedKFold con 10 días de purga.
- **DSR p-value**: **0.0000** ⚠️ (no significativo)
- **Mean Sharpe Ratio**: 0.0000 ± 0.0000 (0 folds)
- **Fold SRs**: []

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\sigma^2_{\text{epistémica}}$): **0.000000** (N=49 estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas por N

| Escala ZigZag | Horizonte Máximo | $EV_{\text{net}}$ (ponderado) | $P(\text{bull})$ (ponderado) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+0.03%` | `54.9%` | `6.5d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `+0.49%` | `59.2%` | `20.6d` |
| **`zz75` (7.5% Estructural)** | 90 días | `+1.21%` | `62.3%` | `38.0d` |

**Población total**: 6,939 observaciones | $P(\text{bull})$ ponderado = 59.2% | $EV_{50}$ ponderado = +0.49%

---

## 3. Anomalías Empíricas (extraídas del Fact Store, N ≥ 20)

### 🚨 Anomalía Empírica 1: `DEFENSIVE_ROTATION__EXTREME_CYCLICAL_SPIKE_3D` (Alcista)
- **Condición**: Estado empírico con N=43 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 76.7\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.55\%$, $EV_{\text{per\_day}} = +0.2038\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `MKT_ROTATION_DEFENSIVE_FLIGHT`.

### 🚨 Anomalía Empírica 2: `EXTREME_DEFENSIVE_ROTATION__EXTREME_CYCLICAL_SPIKE_3D` (Alcista)
- **Condición**: Estado empírico con N=22 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 72.7\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +1.91\%$, $EV_{\text{per\_day}} = +0.2125\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `MKT_ROTATION_DEFENSIVE_FREEZE`.

### 🚨 Anomalía Empírica 3: `MODERATE_CYCLICAL__FAST_CYCLICAL_SURGE_3D` (Alcista)
- **Condición**: Estado empírico con N=135 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 71.1\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +1.85\%$, $EV_{\text{per\_day}} = +0.0710\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `MKT_ROTATION_CYCLICAL_EXPANSION`.

### ⚠️ Anomalía Bajista 1: `EXTREME_CYCLICAL_EXPANSION__DECELERATING_ROTATION_3D`
- **Condición**: Estado empírico con N=50 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 32.0\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -2.92\%$.
- **Régimen**: `FULL_STRUCTURAL_BEAR` → `MKT_ROTATION_CYCLICAL_EXPANSION`.

### ⚠️ Anomalía Bajista 2: `EXTREME_CYCLICAL_EXPANSION__ACCELERATING_CYCLICAL_3D`
- **Condición**: Estado empírico con N=80 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 43.8\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -1.61\%$.
- **Régimen**: `FULL_STRUCTURAL_BEAR` → `MKT_ROTATION_CYCLICAL_EXPANSION`.

### ⚠️ Anomalía Bajista 3: `EXTREME_CYCLICAL_EXPANSION__FAST_DEFENSIVE_ROTATION_3D`
- **Condición**: Estado empírico con N=20 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 45.0\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -1.53\%$.
- **Régimen**: `TACTICAL_BOUNCE_ONLY` → `MKT_ROTATION_CYCLICAL_EXPANSION`.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\text{bull})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `ROTATION` | `HYPOTHESIS (Grade D)` | **0.0000** | 0.0000 | 59.2% | 49 | 8 | **Grade C — Informational Only** |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**: Rotación defensiva extrema (P05-P15) es SIGMET.
2. **`CIO Allocator`**: Rotation es dimensión de flujo de equity independiente.
