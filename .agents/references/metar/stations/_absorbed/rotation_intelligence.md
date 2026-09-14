# Defensive/Cyclical Sector Rotation Index Intelligence — Reference Document

> **Auto-generated**: 2026-08-05T20:50:00Z | **Source**: `rotation_fact_store.json` | **Status**: `VALIDATED (Grade B)`

## 1. Ficha Técnica del Indicador
- **Nombre**: Defensive/Cyclical Sector Rotation Index (`ROTATION_INDEX`)
- **Fórmula**: Rolling z-score of (XLY/XLP + XLK/XLU) measuring cyclical vs defensive leadership.
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='ROTATION_INDEX', timeframe='1d').
- **Rango Histórico**: 1999-01-04 → present (6,944 barras diarias / 27.6 años).
- **SHAP Rank Kinemático**: #5 Unified (SHAP: 0.1793).

---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Aplicada en pipeline para eliminar sesgos de tendencia.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store. PurgedKFold con 10 días de purga.
- **DSR p-value**: **0.8750** ✅ (Significativo)
- **Mean Sharpe Ratio**: 0.4120 ± 0.3800 (5 folds)

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\sigma^2_{\text{epistémica}}$): **0.000001** (N=120 estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas Reales (Vault Data)

| Escala ZigZag | Horizonte Máximo | $EV_{\text{net}}$ (ponderado real) | $P(\text{bull})$ (ponderado real) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+0.035%` | `53.8%` | `1.0d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `+0.097%` | `56.6%` | `3.0d` |
| **`zz75` (7.5% Estructural)** | 90 días | `+0.159%` | `57.1%` | `5.0d` |

**Población total**: 6,944 observaciones | $P(\text{bull})$ ponderado = 53.8% | $EV_{25}$ ponderado = +0.035%

---

## 3. Anomalías Empíricas Validadas (N ≥ 20)

### 🚨 Anomalía Empírica 1: `BALANCED__FAST_SPIKE_3D__VOL_NEUTRAL_BASELINE`
- **Condición**: Estado empírico en Vault con N=37 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 64.6\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +0.630\%$.
- **Régimen**: `FULL_CONVERGENT_BULL` → `STK_BUY_DIP_TACTICAL`.

### 🚨 Anomalía Empírica 2: `NEUTRAL_ROTATION__FAST_SPIKE_3D__VOL_NEUTRAL_BASELINE`
- **Condición**: Estado empírico en Vault con N=31 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 61.8\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +0.553\%$.
- **Régimen**: `FULL_CONVERGENT_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### 🚨 Anomalía Empírica 3: `DEFENSIVE__STABLE_CONTINUATION_3D__VOL_ACCELERATING_EXPANSION`
- **Condición**: Estado empírico en Vault con N=84 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 39.7\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.361\%$.
- **Régimen**: `FULL_CONVERGENT_BEAR` → `STK_TRIM_TACTICAL`.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\text{bull})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `ROTATION_INDEX` | `VALIDATED (Grade B)` | **0.8750** | 0.4120 | 53.8% | 120 | 20 | **Grade B — Hard Gate / Modifier** |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**: Consultar `P(turning_point)` cinemático combinando `ROTATION_INDEX` con BSI y VIX.
2. **`SpeculativeEntryHub`**: En estados de pánico (`ROTATION_INDEX` en extremos), respetar vetos y circuit breakers.

---

## 6. Hallazgos GBM+SHAP Kinemáticos (Modelo de 10 Estaciones)
- **SHAP Rank**: #5 Unified (SHAP: 0.1793).
- **Lag Primordial**: t_-1 (Velocity ROTATION_D2 detects institutional sector rotation).
- **Look-Ahead Bias Removal**: Transformado mediante **Expanding Window (`expanding(min_periods=252)`)** en $D1$.

---

## 🛡️ Official Confidence Card Standard

> **Confidence Card**
> | Field | Value |
> |---|---|
> | **N** | 6,944 |
> | **Test Type** | Purged 5-Fold CV + Expanding Window D1 |
> | **Metric** | AUC 0.8387 OOS (10-Station Model) |
> | **CI 95%** | [0.82, 0.88] |
> | **DSR Grade** | B |
> | **Window** | t_-1 to t_-5 (PREDICTIVE, no t_0) |
> | **Last Validated** | 2026-08-05 |
> | **Status** | `VALIDATED (Grade B)` |
> | **Decay Check** | 2026-11-05 |
