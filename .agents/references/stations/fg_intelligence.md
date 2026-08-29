# CNN Fear & Greed Index Intelligence — Reference Document

> **Auto-generated**: 2026-08-05T20:50:00Z | **Source**: `fg_fact_store.json` | **Status**: `VALIDATED (Grade A)`

## 1. Ficha Técnica del Indicador
- **Nombre**: CNN Fear & Greed Index (`FG`)
- **Fórmula**: 7-factor sentiment index (0=extreme fear, 100=extreme greed).
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='FG', timeframe='1d').
- **Rango Histórico**: 2011-01-03 → present (3,877 barras diarias / 15.4 años).
- **SHAP Rank Kinemático**: #12 Unified (SHAP: 0.0680).

---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Aplicada en pipeline para eliminar sesgos de tendencia.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store. PurgedKFold con 10 días de purga.
- **DSR p-value**: **0.9620** ✅ (Significativo)
- **Mean Sharpe Ratio**: 0.6120 ± 0.4100 (5 folds)

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\sigma^2_{\text{epistémica}}$): **0.000001** (N=83 estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas Reales (Vault Data)

| Escala ZigZag | Horizonte Máximo | $EV_{\text{net}}$ (ponderado real) | $P(\text{bull})$ (ponderado real) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+0.048%` | `54.7%` | `1.0d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `+0.145%` | `58.7%` | `3.0d` |
| **`zz75` (7.5% Estructural)** | 90 días | `+0.233%` | `59.6%` | `5.0d` |

**Población total**: 3,874 observaciones | $P(\text{bull})$ ponderado = 54.7% | $EV_{25}$ ponderado = +0.048%

---

## 3. Anomalías Empíricas Validadas (N ≥ 20)

### 🚨 Anomalía Empírica 1: `EXTREME_FEAR__STABLE_CONTINUATION_3D__VOL_NEUTRAL_BASELINE`
- **Condición**: Estado empírico en Vault con N=24 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 48.1\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.544\%$.
- **Régimen**: `FULL_CONVERGENT_BEAR` → `STK_BLOCK_CRISIS`.

### 🚨 Anomalía Empírica 2: `NEUTRAL_FEAR__FAST_CRUSH_3D__VOL_NEUTRAL_BASELINE`
- **Condición**: Estado empírico en Vault con N=29 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 65.0\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +0.313\%$.
- **Régimen**: `FULL_CONVERGENT_BULL` → `STK_BUY_DIP_TACTICAL`.

### 🚨 Anomalía Empírica 3: `NEUTRAL_FEAR__FAST_SPIKE_3D__VOL_NEUTRAL_BASELINE`
- **Condición**: Estado empírico en Vault con N=25 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 63.9\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +0.234\%$.
- **Régimen**: `FULL_CONVERGENT_BULL` → `STK_BUY_DIP_TACTICAL`.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\text{bull})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `FG` | `VALIDATED (Grade A)` | **0.9620** | 0.6120 | 54.7% | 83 | 20 | **Grade A — Hard Gate / Modifier** |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**: Consultar `P(turning_point)` cinemático combinando `FG` con BSI y VIX.
2. **`SpeculativeEntryHub`**: En estados de pánico (`FG` en extremos), respetar vetos y circuit breakers.

---

## 6. Hallazgos GBM+SHAP Kinemáticos (Modelo de 10 Estaciones)
- **SHAP Rank**: #12 Unified (SHAP: 0.0680).
- **Lag Primordial**: t_-1 (Level FG < 10 triggers CB_FEAR_CAPITULATION).
- **Look-Ahead Bias Removal**: Transformado mediante **Expanding Window (`expanding(min_periods=252)`)** en $D1$.

---

## 🛡️ Official Confidence Card Standard

> **Confidence Card**
> | Field | Value |
> |---|---|
> | **N** | 3,874 |
> | **Test Type** | Purged 5-Fold CV + Expanding Window D1 |
> | **Metric** | AUC 0.8387 OOS (10-Station Model) |
> | **CI 95%** | [0.82, 0.88] |
> | **DSR Grade** | A |
> | **Window** | t_-1 to t_-5 (PREDICTIVE, no t_0) |
> | **Last Validated** | 2026-08-05 |
> | **Status** | `VALIDATED (Grade A)` |
> | **Decay Check** | 2026-11-05 |
