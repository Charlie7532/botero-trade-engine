# SV5 Institutional Volume Turbulence Intelligence — Reference Document

> **Auto-generated**: 2026-08-05T20:50:00Z | **Source**: `sv5_turbulence_fact_store.json` | **Status**: `VALIDATED (Grade B)`

## 1. Ficha Técnica del Indicador
- **Nombre**: SV5 Institutional Volume Turbulence (`SV5_TURBULENCE`)
- **Fórmula**: std(Δ_SV5TW, 10d) — standard deviation of institutional participation change.
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='SV5_TURBULENCE', timeframe='1d').
- **Rango Histórico**: 1999-01-04 → present (6,927 barras diarias / 27.5 años).
- **SHAP Rank Kinemático**: #11 Unified (SHAP: 0.0749).

---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Aplicada en pipeline para eliminar sesgos de tendencia.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store. PurgedKFold con 10 días de purga.
- **DSR p-value**: **0.9170** ✅ (Significativo)
- **Mean Sharpe Ratio**: 0.4345 ± 0.3961 (5 folds)

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\sigma^2_{\text{epistémica}}$): **0.000001** (N=104 estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas Reales (Vault Data)

| Escala ZigZag | Horizonte Máximo | $EV_{\text{net}}$ (ponderado real) | $P(\text{bull})$ (ponderado real) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+0.035%` | `54.0%` | `1.0d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `+0.106%` | `56.9%` | `3.0d` |
| **`zz75` (7.5% Estructural)** | 90 días | `+0.166%` | `57.3%` | `5.0d` |

**Población total**: 6,924 observaciones | $P(\text{bull})$ ponderado = 54.0% | $EV_{25}$ ponderado = +0.035%

---

## 3. Anomalías Empíricas Validadas (N ≥ 20)

### 🚨 Anomalía Empírica 1: `EXTREME_TURBULENT__STABLE_CONTINUATION_3D__VOL_MODERATE_COMPRESSION`
- **Condición**: Estado empírico en Vault con N=50 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 62.3\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +0.403\%$.
- **Régimen**: `FULL_CONVERGENT_BULL` → `STK_BLOCK_CRISIS`.

### 🚨 Anomalía Empírica 2: `CALM__STABLE_CONTINUATION_3D__VOL_ACCELERATING_EXPANSION`
- **Condición**: Estado empírico en Vault con N=36 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 39.9\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.334\%$.
- **Régimen**: `FULL_CONVERGENT_BEAR` → `STK_TRIM_TACTICAL`.

### 🚨 Anomalía Empírica 3: `NEUTRAL_TURBULENT__ACCELERATING_UP_3D__VOL_ACCELERATING_EXPANSION`
- **Condición**: Estado empírico en Vault con N=78 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 58.4\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +0.273\%$.
- **Régimen**: `FULL_CONVERGENT_BULL` → `STK_HOLD_STABLE`.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\text{bull})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `SV5_TURBULENCE` | `VALIDATED (Grade B)` | **0.9170** | 0.4345 | 54.0% | 104 | 20 | **Grade B — Hard Gate / Modifier** |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**: Consultar `P(turning_point)` cinemático combinando `SV5_TURBULENCE` con BSI y VIX.
2. **`SpeculativeEntryHub`**: En estados de pánico (`SV5_TURBULENCE` en extremos), respetar vetos y circuit breakers.

---

## 6. Hallazgos GBM+SHAP Kinemáticos (Modelo de 10 Estaciones)
- **SHAP Rank**: #11 Unified (SHAP: 0.0749).
- **Lag Primordial**: t_-5 (Bimodal: SV5T < 3.6 = Silent Top, SV5T > 17.3 = Guaranteed Bottom).
- **Look-Ahead Bias Removal**: Transformado mediante **Expanding Window (`expanding(min_periods=252)`)** en $D1$.

---

## 🛡️ Official Confidence Card Standard

> **Confidence Card**
> | Field | Value |
> |---|---|
> | **N** | 6,924 |
> | **Test Type** | Purged 5-Fold CV + Expanding Window D1 |
> | **Metric** | AUC 0.8387 OOS (10-Station Model) |
> | **CI 95%** | [0.82, 0.88] |
> | **DSR Grade** | B |
> | **Window** | t_-1 to t_-5 (PREDICTIVE, no t_0) |
> | **Last Validated** | 2026-08-05 |
> | **Status** | `VALIDATED (Grade B)` |
> | **Decay Check** | 2026-11-05 |
