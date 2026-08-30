# Volatility of Volatility Index Intelligence — Reference Document

> **Auto-generated**: 2026-08-05T20:50:00Z | **Source**: `vvix_fact_store.json` | **Status**: `VALIDATED (Grade B)`

## 1. Ficha Técnica del Indicador
- **Nombre**: Volatility of Volatility Index (`VVIX`)
- **Fórmula**: Volatility of 30-day implied volatility calculated from VIX options.
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='VVIX', timeframe='1d').
- **Rango Histórico**: 2006-01-03 → present (5,075 barras diarias / 20.1 años).
- **SHAP Rank Kinemático**: #14 Unified (SHAP: 0.0520).

---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Aplicada en pipeline para eliminar sesgos de tendencia.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store. PurgedKFold con 10 días de purga.
- **DSR p-value**: **0.8790** ✅ (Significativo)
- **Mean Sharpe Ratio**: 0.4850 ± 0.3512 (5 folds)

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\sigma^2_{\text{epistémica}}$): **0.000001** (N=104 estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas Reales (Vault Data)

| Escala ZigZag | Horizonte Máximo | $EV_{\text{net}}$ (ponderado real) | $P(\text{bull})$ (ponderado real) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+0.039%` | `54.5%` | `1.0d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `+0.118%` | `57.9%` | `3.0d` |
| **`zz75` (7.5% Estructural)** | 90 días | `+0.191%` | `59.0%` | `5.0d` |

**Población total**: 5,075 observaciones | $P(\text{bull})$ ponderado = 54.5% | $EV_{25}$ ponderado = +0.039%

---

## 3. Anomalías Empíricas Validadas (N ≥ 20)

### 🚨 Anomalía Empírica 1: `EXTREME_INSTABILITY__DECELERATING_DOWN_3D__VOL_NEUTRAL_BASELINE`
- **Condición**: Estado empírico en Vault con N=20 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 61.2\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +0.771\%$.
- **Régimen**: `FULL_CONVERGENT_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### 🚨 Anomalía Empírica 2: `EXTREME_INSTABILITY__ACCELERATING_UP_3D__VOL_NEUTRAL_BASELINE`
- **Condición**: Estado empírico en Vault con N=42 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 52.6\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +0.573\%$.
- **Régimen**: `FULL_CONVERGENT_BULL` → `STK_BUY_DIP_TACTICAL`.

### 🚨 Anomalía Empírica 3: `EXTREME_INSTABILITY__FAST_SPIKE_3D__VOL_NEUTRAL_BASELINE`
- **Condición**: Estado empírico en Vault con N=36 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 59.5\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +0.356\%$.
- **Régimen**: `FULL_CONVERGENT_BULL` → `STK_BUY_DIP_TACTICAL`.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\text{bull})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `VVIX` | `VALIDATED (Grade B)` | **0.8790** | 0.4850 | 54.5% | 104 | 20 | **Grade B — Hard Gate / Modifier** |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**: Consultar `P(turning_point)` cinemático combinando `VVIX` con BSI y VIX.
2. **`SpeculativeEntryHub`**: En estados de pánico (`VVIX` en extremos), respetar vetos y circuit breakers.

---

## 6. Hallazgos GBM+SHAP Kinemáticos (Modelo de 10 Estaciones)
- **SHAP Rank**: #14 Unified (SHAP: 0.0520).
- **Lag Primordial**: t_-1 (Level VVIX > 140 triggers CB_VVIX_EXTREME).
- **Look-Ahead Bias Removal**: Transformado mediante **Expanding Window (`expanding(min_periods=252)`)** en $D1$.

---

## 🛡️ Official Confidence Card Standard

> **Confidence Card**
> | Field | Value |
> |---|---|
> | **N** | 5,075 |
> | **Test Type** | Purged 5-Fold CV + Expanding Window D1 |
> | **Metric** | AUC 0.8387 OOS (10-Station Model) |
> | **CI 95%** | [0.82, 0.88] |
> | **DSR Grade** | B |
> | **Window** | t_-1 to t_-5 (PREDICTIVE, no t_0) |
> | **Last Validated** | 2026-08-05 |
> | **Status** | `VALIDATED (Grade B)` |
> | **Decay Check** | 2026-11-05 |
