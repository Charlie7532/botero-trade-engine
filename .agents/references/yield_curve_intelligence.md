# Yield Curve Spread (10Y - 13W) Intelligence — Reference Document

> **Auto-generated**: 2026-08-05T20:50:00Z | **Source**: `yield_curve_fact_store.json` | **Status**: `VALIDATED (Grade A)`

## 1. Ficha Técnica del Indicador
- **Nombre**: Yield Curve Spread (10Y - 13W) (`YIELD_SPREAD`)
- **Fórmula**: TNX - IRX (10-year Treasury yield minus 13-week T-bill yield).
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='YIELD_SPREAD', timeframe='1d').
- **Rango Histórico**: 1962-01-02 → present (16,123 barras diarias / 64.0 años).
- **SHAP Rank Kinemático**: #8 Unified (SHAP: 0.1236).

---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Aplicada en pipeline para eliminar sesgos de tendencia.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store. PurgedKFold con 10 días de purga.
- **DSR p-value**: **0.9680** ✅ (Significativo)
- **Mean Sharpe Ratio**: 0.5890 ± 0.4200 (5 folds)

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\sigma^2_{\text{epistémica}}$): **0.000001** (N=101 estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas Reales (Vault Data)

| Escala ZigZag | Horizonte Máximo | $EV_{\text{net}}$ (ponderado real) | $P(\text{bull})$ (ponderado real) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+0.051%` | `53.7%` | `1.0d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `+0.150%` | `57.0%` | `3.0d` |
| **`zz75` (7.5% Estructural)** | 90 días | `+0.244%` | `57.8%` | `5.0d` |

**Población total**: 8,403 observaciones | $P(\text{bull})$ ponderado = 53.7% | $EV_{25}$ ponderado = +0.051%

---

## 3. Anomalías Empíricas Validadas (N ≥ 20)

### 🚨 Anomalía Empírica 1: `NORMAL_CURVE__ACCELERATING_UP_3D__VOL_MODERATE_COMPRESSION`
- **Condición**: Estado empírico en Vault con N=51 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 69.4\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +0.413\%$.
- **Régimen**: `FULL_CONVERGENT_BULL` → `STK_BUY_DIP_TACTICAL`.

### 🚨 Anomalía Empírica 2: `FLAT_CURVE__FAST_CRUSH_3D__VOL_NEUTRAL_BASELINE`
- **Condición**: Estado empírico en Vault con N=21 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 49.5\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +0.338\%$.
- **Régimen**: `FULL_CONVERGENT_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### 🚨 Anomalía Empírica 3: `STEEPNING_CURVE__DECELERATING_DOWN_3D__VOL_MODERATE_COMPRESSION`
- **Condición**: Estado empírico en Vault con N=24 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 59.9\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +0.307\%$.
- **Régimen**: `TACTICAL_REBOUND_IN_BEAR` → `STK_BLOCK_CRISIS`.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\text{bull})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `YIELD_SPREAD` | `VALIDATED (Grade A)` | **0.9680** | 0.5890 | 53.7% | 101 | 20 | **Grade A — Hard Gate / Modifier** |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**: Consultar `P(turning_point)` cinemático combinando `YIELD_SPREAD` con BSI y VIX.
2. **`SpeculativeEntryHub`**: En estados de pánico (`YIELD_SPREAD` en extremos), respetar vetos y circuit breakers.

---

## 6. Hallazgos GBM+SHAP Kinemáticos (Modelo de 10 Estaciones)
- **SHAP Rank**: #8 Unified (SHAP: 0.1236).
- **Lag Primordial**: t_-1 (Velocity YIELD_D2 + Inversion macro context).
- **Look-Ahead Bias Removal**: Transformado mediante **Expanding Window (`expanding(min_periods=252)`)** en $D1$.

---

## 🛡️ Official Confidence Card Standard

> **Confidence Card**
> | Field | Value |
> |---|---|
> | **N** | 8,403 |
> | **Test Type** | Purged 5-Fold CV + Expanding Window D1 |
> | **Metric** | AUC 0.8387 OOS (10-Station Model) |
> | **CI 95%** | [0.82, 0.88] |
> | **DSR Grade** | A |
> | **Window** | t_-1 to t_-5 (PREDICTIVE, no t_0) |
> | **Last Validated** | 2026-08-05 |
> | **Status** | `VALIDATED (Grade A)` |
> | **Decay Check** | 2026-11-05 |
