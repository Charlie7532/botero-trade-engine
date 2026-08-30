# CBOE Volatility Index Intelligence — Reference Document

> **Auto-generated**: 2026-08-05T20:50:00Z | **Source**: `vix_fact_store.json` | **Status**: `VALIDATED (Grade A)`

## 1. Ficha Técnica del Indicador
- **Nombre**: CBOE Volatility Index (`VIX`)
- **Fórmula**: Implicit 30-day volatility calculated from SPX S&P 500 options.
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='VIX', timeframe='1d').
- **Rango Histórico**: 1990-01-02 → present (9,237 barras diarias / 36.5 años).
- **SHAP Rank Kinemático**: #3 Unified (SHAP: 0.4680).

---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Aplicada en pipeline para eliminar sesgos de tendencia.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store. PurgedKFold con 10 días de purga.
- **DSR p-value**: **0.9947** ✅ (Significativo)
- **Mean Sharpe Ratio**: 0.7155 ± 0.8098 (5 folds)

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\sigma^2_{\text{epistémica}}$): **0.000001** (N=107 estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas Reales (Vault Data)

| Escala ZigZag | Horizonte Máximo | $EV_{\text{net}}$ (ponderado real) | $P(\text{bull})$ (ponderado real) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+0.049%` | `53.6%` | `1.0d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `+0.151%` | `57.1%` | `3.0d` |
| **`zz75` (7.5% Estructural)** | 90 días | `+0.242%` | `57.8%` | `5.0d` |

**Población total**: 8,435 observaciones | $P(\text{bull})$ ponderado = 53.6% | $EV_{25}$ ponderado = +0.049%

---

## 3. Anomalías Empíricas Validadas (N ≥ 20)

### 🚨 Anomalía Empírica 1: `EXTREME_PANIC__FAST_SPIKE_3D__VOL_ACCELERATING_EXPANSION`
- **Condición**: Estado empírico en Vault con N=22 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 66.7\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +1.279\%$.
- **Régimen**: `FULL_CONVERGENT_BULL` → `STK_BLOCK_CRISIS`.

### 🚨 Anomalía Empírica 2: `EXTREME_PANIC__STABLE_CONTINUATION_3D__VOL_NEUTRAL_BASELINE`
- **Condición**: Estado empírico en Vault con N=40 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 42.7\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.622\%$.
- **Régimen**: `FULL_CONVERGENT_BEAR` → `STK_BLOCK_CRISIS`.

### 🚨 Anomalía Empírica 3: `EXTREME_PANIC__FAST_CRUSH_3D__VOL_NEUTRAL_BASELINE`
- **Condición**: Estado empírico en Vault con N=33 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 56.6\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +0.317\%$.
- **Régimen**: `FULL_CONVERGENT_BULL` → `STK_BLOCK_CRISIS`.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\text{bull})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `VIX` | `VALIDATED (Grade A)` | **0.9947** | 0.7155 | 53.6% | 107 | 20 | **Grade A — Hard Gate / Modifier** |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**: Consultar `P(turning_point)` cinemático combinando `VIX` con BSI y VIX.
2. **`SpeculativeEntryHub`**: En estados de pánico (`VIX` en extremos), respetar vetos y circuit breakers.

---

## 6. Hallazgos GBM+SHAP Kinemáticos (Modelo de 10 Estaciones)
- **SHAP Rank**: #3 Unified (SHAP: 0.4680).
- **Lag Primordial**: t_-1 (Velocity VIX_D2 is #1 volatility driver).
- **Look-Ahead Bias Removal**: Transformado mediante **Expanding Window (`expanding(min_periods=252)`)** en $D1$.

---

## 🛡️ Official Confidence Card Standard

> **Confidence Card**
> | Field | Value |
> |---|---|
> | **N** | 8,435 |
> | **Test Type** | Purged 5-Fold CV + Expanding Window D1 |
> | **Metric** | AUC 0.8387 OOS (10-Station Model) |
> | **CI 95%** | [0.82, 0.88] |
> | **DSR Grade** | A |
> | **Window** | t_-1 to t_-5 (PREDICTIVE, no t_0) |
> | **Last Validated** | 2026-08-05 |
> | **Status** | `VALIDATED (Grade A)` |
> | **Decay Check** | 2026-11-05 |
