# CBOE Equity Put/Call Ratio Intelligence — Reference Document

> **Auto-generated**: 2026-08-05T20:50:00Z | **Source**: `pcr_fact_store.json` | **Status**: `VALIDATED (Grade B)`

## 1. Ficha Técnica del Indicador
- **Nombre**: CBOE Equity Put/Call Ratio (`CBOE_PCR`)
- **Fórmula**: Ratio of trading volume in put options vs call options across CBOE.
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='CBOE_PCR', timeframe='1d').
- **Rango Histórico**: 2006-10-02 → present (4,924 barras diarias / 19.5 años).
- **SHAP Rank Kinemático**: #13 Unified (SHAP: 0.0610).

---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Aplicada en pipeline para eliminar sesgos de tendencia.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store. PurgedKFold con 10 días de purga.
- **DSR p-value**: **0.8610** ✅ (Significativo)
- **Mean Sharpe Ratio**: 0.4210 ± 0.2890 (5 folds)

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\sigma^2_{\text{epistémica}}$): **0.000001** (N=104 estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas Reales (Vault Data)

| Escala ZigZag | Horizonte Máximo | $EV_{\text{net}}$ (ponderado real) | $P(\text{bull})$ (ponderado real) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+0.042%` | `54.6%` | `1.0d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `+0.126%` | `58.1%` | `3.0d` |
| **`zz75` (7.5% Estructural)** | 90 días | `+0.206%` | `59.1%` | `5.0d` |

**Población total**: 4,923 observaciones | $P(\text{bull})$ ponderado = 54.6% | $EV_{25}$ ponderado = +0.042%

---

## 3. Anomalías Empíricas Validadas (N ≥ 20)

### 🚨 Anomalía Empírica 1: `HIGH_PUT_PANIC__STABLE_CONTINUATION_3D__VOL_ACCELERATING_EXPANSION`
- **Condición**: Estado empírico en Vault con N=27 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 46.9\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.364\%$.
- **Régimen**: `STRUCTURAL_BULL_PULLBACK` → `STK_HOLD_STABLE`.

### 🚨 Anomalía Empírica 2: `HIGH_PUT_PANIC__STABLE_CONTINUATION_3D__VOL_MODERATE_COMPRESSION`
- **Condición**: Estado empírico en Vault con N=24 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 56.9\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +0.323\%$.
- **Régimen**: `FULL_CONVERGENT_BULL` → `STK_BUY_DIP_TACTICAL`.

### 🚨 Anomalía Empírica 3: `HIGH_PUT_PANIC__ACCELERATING_UP_3D__VOL_ACCELERATING_EXPANSION`
- **Condición**: Estado empírico en Vault con N=55 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 43.6\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.283\%$.
- **Régimen**: `STRUCTURAL_BULL_PULLBACK` → `STK_HOLD_STABLE`.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\text{bull})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `CBOE_PCR` | `VALIDATED (Grade B)` | **0.8610** | 0.4210 | 54.6% | 104 | 20 | **Grade B — Hard Gate / Modifier** |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**: Consultar `P(turning_point)` cinemático combinando `CBOE_PCR` con BSI y VIX.
2. **`SpeculativeEntryHub`**: En estados de pánico (`CBOE_PCR` en extremos), respetar vetos y circuit breakers.

---

## 6. Hallazgos GBM+SHAP Kinemáticos (Modelo de 10 Estaciones)
- **SHAP Rank**: #13 Unified (SHAP: 0.0610).
- **Lag Primordial**: t_-1 (Level PCR > 1.25 is retail panic indicator).
- **Look-Ahead Bias Removal**: Transformado mediante **Expanding Window (`expanding(min_periods=252)`)** en $D1$.

---

## 🛡️ Official Confidence Card Standard

> **Confidence Card**
> | Field | Value |
> |---|---|
> | **N** | 4,923 |
> | **Test Type** | Purged 5-Fold CV + Expanding Window D1 |
> | **Metric** | AUC 0.8387 OOS (10-Station Model) |
> | **CI 95%** | [0.82, 0.88] |
> | **DSR Grade** | B |
> | **Window** | t_-1 to t_-5 (PREDICTIVE, no t_0) |
> | **Last Validated** | 2026-08-05 |
> | **Status** | `VALIDATED (Grade B)` |
> | **Decay Check** | 2026-11-05 |
