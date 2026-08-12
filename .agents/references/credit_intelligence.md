# High Yield Corporate Credit Spread (HYG/LQD) Intelligence — Reference Document

> **Auto-generated**: 2026-08-05T20:50:00Z | **Source**: `credit_fact_store.json` | **Status**: `VALIDATED (Grade A)`

## 1. Ficha Técnica del Indicador
- **Nombre**: High Yield Corporate Credit Spread (HYG/LQD) (`CREDIT_RATIO`)
- **Fórmula**: HYG/LQD ratio — pure corporate default risk without Treasury duration mismatch.
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='CREDIT_RATIO (HYG/LQD)', timeframe='1d').
- **Rango Histórico**: 2007-01-03 → present (4,861 barras diarias / 19.3 años).
- **SHAP Rank Kinemático**: #9 Unified (SHAP: 0.1150).

---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Aplicada en pipeline para eliminar sesgos de tendencia.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store. PurgedKFold con 10 días de purga.
- **DSR p-value**: **0.9509** ✅ (Significativo)
- **Mean Sharpe Ratio**: 0.5579 ± 0.4768 (5 folds)

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\sigma^2_{\text{epistémica}}$): **0.000001** (N=112 estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas Reales (Vault Data)

| Escala ZigZag | Horizonte Máximo | $EV_{\text{net}}$ (ponderado real) | $P(\text{bull})$ (ponderado real) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+0.041%` | `54.6%` | `1.0d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `+0.124%` | `58.1%` | `3.0d` |
| **`zz75` (7.5% Estructural)** | 90 días | `+0.201%` | `59.1%` | `5.0d` |

**Población total**: 4,861 observaciones | $P(\text{bull})$ ponderado = 54.6% | $EV_{25}$ ponderado = +0.041%

---

## 3. Anomalías Empíricas Validadas (N ≥ 20)

### 🚨 Anomalía Empírica 1: `ELEVATED_CREDIT_STRESS__FAST_SPIKE_3D__VOL_NEUTRAL_BASELINE`
- **Condición**: Estado empírico en Vault con N=43 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 45.9\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.442\%$.
- **Régimen**: `STRUCTURAL_BULL_PULLBACK` → `STK_HOLD_STABLE`.

### 🚨 Anomalía Empírica 2: `CREDIT_STRESS__STABLE_CONTINUATION_3D__VOL_MODERATE_COMPRESSION`
- **Condición**: Estado empírico en Vault con N=26 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 64.9\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +0.375\%$.
- **Régimen**: `FULL_CONVERGENT_BULL` → `STK_BUY_DIP_TACTICAL`.

### 🚨 Anomalía Empírica 3: `ELEVATED_CREDIT_STRESS__ACCELERATING_UP_3D__VOL_ACCELERATING_EXPANSION`
- **Condición**: Estado empírico en Vault con N=31 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 49.6\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.265\%$.
- **Régimen**: `STRUCTURAL_BULL_PULLBACK` → `STK_HOLD_STABLE`.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\text{bull})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `CREDIT_RATIO` | `VALIDATED (Grade A)` | **0.9509** | 0.5579 | 54.6% | 112 | 20 | **Grade A — Hard Gate / Modifier** |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**: Consultar `P(turning_point)` cinemático combinando `CREDIT_RATIO` con BSI y VIX.
2. **`SpeculativeEntryHub`**: En estados de pánico (`CREDIT_RATIO` en extremos), respetar vetos y circuit breakers.

---

## 6. Hallazgos GBM+SHAP Kinemáticos (Modelo de 10 Estaciones)
- **SHAP Rank**: #9 Unified (SHAP: 0.1150).
- **Lag Primordial**: t_-1 (CREDIT D2 < P2 triggers CB_CREDIT_PANIC).
- **Look-Ahead Bias Removal**: Transformado mediante **Expanding Window (`expanding(min_periods=252)`)** en $D1$.

---

## 🛡️ Official Confidence Card Standard

> **Confidence Card**
> | Field | Value |
> |---|---|
> | **N** | 4,861 |
> | **Test Type** | Purged 5-Fold CV + Expanding Window D1 |
> | **Metric** | AUC 0.8387 OOS (10-Station Model) |
> | **CI 95%** | [0.82, 0.88] |
> | **DSR Grade** | A |
> | **Window** | t_-1 to t_-5 (PREDICTIVE, no t_0) |
> | **Last Validated** | 2026-08-05 |
> | **Status** | `VALIDATED (Grade A)` |
> | **Decay Check** | 2026-11-05 |
