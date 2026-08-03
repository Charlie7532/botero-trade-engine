# CBOE SKEW Index Intelligence — Reference Document

> **Auto-generated**: 2026-08-03T19:05:26Z | **Source**: `skew_fact_store.json` | **Status**: `VALIDATED (Grade A)`

## 1. Ficha Técnica del Indicador
- **Nombre**: CBOE SKEW Index (`SKEW`)
- **Fórmula**: Medida de riesgo de cola: demanda de puts OTM en SPX. 100=neutral, >130=cola activa.
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='SKEW', timeframe='1d').
- **Rango Histórico**: N/A → present (8,417 barras diarias / 33.4 años).
- **Umbrales Percentiles L0** (empíricos del Fact Store):
  - `BLACK_SWAN_PARANOIA`: $< 110.47$
  - `COMPLACENCY`: $110.47 - 113.27$
  - `DEEP_COMPLACENCY`: $113.27 - 117.41$
  - `ELEVATED`: $117.41 - 124.58$
  - `HIGH_TAIL_RISK`: $124.58 - 137.02$
  - `NORMAL_HIGH`: $137.02 - 148.03$
  - `NORMAL_LOW`: $> 148.03$

---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Std = 3.7194.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store. PurgedKFold con 10 días de purga.
- **DSR p-value**: **1.0000** ✅ (significativo)
- **Mean Sharpe Ratio**: 0.6154 ± 0.3062 (5 folds)
- **Fold SRs**: [0.7945, 0.2447, 0.3628, 0.921, 1.0093]

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\sigma^2_{\text{epistémica}}$): **0.000001** (N=46 estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas por N

| Escala ZigZag | Horizonte Máximo | $EV_{\text{net}}$ (ponderado) | $P(\text{bull})$ (ponderado) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+0.16%` | `55.1%` | `6.8d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `+0.95%` | `58.8%` | `21.2d` |
| **`zz75` (7.5% Estructural)** | 90 días | `+1.73%` | `61.3%` | `38.8d` |

**Población total**: 8,417 observaciones | $P(\text{bull})$ ponderado = 58.8% | $EV_{50}$ ponderado = +0.95%

---

## 3. Anomalías Empíricas (extraídas del Fact Store, N ≥ 20)

### 🚨 Anomalía Empírica 1: `COMPLACENCY__FAST_RELAXATION_3D` (Alcista)
- **Condición**: Estado empírico con N=53 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 60.5\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +3.03\%$, $EV_{\text{per\_day}} = +0.1893\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### 🚨 Anomalía Empírica 2: `DEEP_COMPLACENCY__RISING_HEDGING_3D` (Alcista)
- **Condición**: Estado empírico con N=40 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 76.9\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.96\%$, $EV_{\text{per\_day}} = +0.1646\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### 🚨 Anomalía Empírica 3: `NORMAL_LOW__STABLE_3D` (Alcista)
- **Condición**: Estado empírico con N=700 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 62.0\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.44\%$, $EV_{\text{per\_day}} = +0.1222\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### ⚠️ Anomalía Bajista 1: `BLACK_SWAN_PARANOIA__EXTREME_RELAXATION_3D`
- **Condición**: Estado empírico con N=36 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 33.3\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -2.15\%$.
- **Régimen**: `FULL_STRUCTURAL_BEAR` → `STK_BLOCK_CRISIS`.

### ⚠️ Anomalía Bajista 2: `BLACK_SWAN_PARANOIA__STABLE_3D`
- **Condición**: Estado empírico con N=43 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 41.7\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -1.33\%$.
- **Régimen**: `TACTICAL_BOUNCE_ONLY` → `STK_BUY_DIP_TACTICAL_ONLY_STRICT_STOP`.

### ⚠️ Anomalía Bajista 3: `COMPLACENCY__STABLE_3D`
- **Condición**: Estado empírico con N=394 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 47.0\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.74\%$.
- **Régimen**: `FULL_STRUCTURAL_BEAR` → `STK_BLOCK_CRISIS`.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\text{bull})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `SKEW` | `VALIDATED (Grade A)` | **1.0000** | 0.6154 | 58.8% | 46 | 2 | **Grade C — Informational Only** |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**: SKEW extremo (P95) indica protección de cola activa.
2. **`SpeculativeEntryHub`**: Consultar régimen de divergencia por velocidad.
