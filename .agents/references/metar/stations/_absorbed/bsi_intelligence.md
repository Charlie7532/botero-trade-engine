# Breadth Shock Index (S5TW) Intelligence — 10th METAR Station — Reference Document

> **Auto-generated**: 2026-08-05T20:50:00Z | **Source**: `bsi_fact_store.json` | **Status**: `VALIDATED (Grade A)`

## 1. Ficha Técnica del Indicador
- **Nombre**: Breadth Shock Index (S5TW) (`S5TW`)
- **Fórmula**: Δ S5TW / 9.57 — 1-day acceleration of S&P 500 stocks above 20-DMA.
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='S5TW', timeframe='1d').
- **Rango Histórico**: 1980-01-02 → present (11,668 barras diarias / 46.3 años).
- **SHAP Rank Kinemático**: #1 Unified (SHAP: 0.7770).

---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Aplicada en pipeline para eliminar sesgos de tendencia.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store. PurgedKFold con 10 días de purga.
- **DSR p-value**: **0.9980** ✅ (Significativo)
- **Mean Sharpe Ratio**: 0.8920 ± 0.5100 (5 folds)

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\sigma^2_{\text{epistémica}}$): **0.000001** (N=104 estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas Reales (Vault Data)

| Escala ZigZag | Horizonte Máximo | $EV_{\text{net}}$ (ponderado real) | $P(\text{bull})$ (ponderado real) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+0.049%` | `53.6%` | `1.0d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `+0.148%` | `57.0%` | `3.0d` |
| **`zz75` (7.5% Estructural)** | 90 días | `+0.239%` | `57.7%` | `5.0d` |

**Población total**: 8,429 observaciones | $P(\text{bull})$ ponderado = 53.6% | $EV_{25}$ ponderado = +0.049%

---

## 3. Anomalías Empíricas Validadas (N ≥ 20)

### 🚨 Anomalía Empírica 1: `BREADTH_WASHED_OUT__DECELERATING_DOWN_3D__VOL_NEUTRAL_BASELINE`
- **Condición**: Estado empírico en Vault con N=41 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 53.6\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +0.449\%$.
- **Régimen**: `FULL_CONVERGENT_BULL` → `STK_BUY_DIP_TACTICAL`.

### 🚨 Anomalía Empírica 2: `BREADTH_WASHED_OUT__STABLE_CONTINUATION_3D__VOL_MODERATE_COMPRESSION`
- **Condición**: Estado empírico en Vault con N=58 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 56.4\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +0.383\%$.
- **Régimen**: `FULL_CONVERGENT_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### 🚨 Anomalía Empírica 3: `NEUTRAL_HIGH_BREADTH__STABLE_CONTINUATION_3D__VOL_MODERATE_COMPRESSION`
- **Condición**: Estado empírico en Vault con N=262 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 53.1\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +0.338\%$.
- **Régimen**: `FULL_CONVERGENT_BULL` → `STK_BUY_DIP_TACTICAL`.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\text{bull})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `S5TW` | `VALIDATED (Grade A)` | **0.9980** | 0.8920 | 53.6% | 104 | 20 | **Grade A — Hard Gate / Modifier** |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**: Consultar `P(turning_point)` cinemático combinando `S5TW` con BSI y VIX.
2. **`SpeculativeEntryHub`**: En estados de pánico (`S5TW` en extremos), respetar vetos y circuit breakers.

---

## 6. Hallazgos GBM+SHAP Kinemáticos (Modelo de 10 Estaciones)
- **SHAP Rank**: #1 Unified (SHAP: 0.7770).
- **Lag Primordial**: t_-1 (#1 PREDICTOR: BSI level + BSI_D2 velocity).
- **Look-Ahead Bias Removal**: Transformado mediante **Expanding Window (`expanding(min_periods=252)`)** en $D1$.

---

## 🛡️ Official Confidence Card Standard

> **Confidence Card**
> | Field | Value |
> |---|---|
> | **N** | 8,429 |
> | **Test Type** | Purged 5-Fold CV + Expanding Window D1 |
> | **Metric** | AUC 0.8387 OOS (10-Station Model) |
> | **CI 95%** | [0.82, 0.88] |
> | **DSR Grade** | A |
> | **Window** | t_-1 to t_-5 (PREDICTIVE, no t_0) |
> | **Last Validated** | 2026-08-05 |
> | **Status** | `VALIDATED (Grade A)` |
> | **Decay Check** | 2026-11-05 |
