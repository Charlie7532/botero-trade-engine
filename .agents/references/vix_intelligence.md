# CBOE Volatility Index Intelligence — Reference Document

> **Auto-generated**: 2026-08-03T19:05:22Z | **Source**: `vix_fact_store.json` | **Status**: `VALIDATED (Grade A)`

## 1. Ficha Técnica del Indicador
- **Nombre**: CBOE Volatility Index (`VIX`)
- **Fórmula**: Volatilidad implícita a 30 días calculada de las opciones OTM de SPX.
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='VIX', timeframe='1d').
- **Rango Histórico**: 1993-01-29 → 2026-07-30 (8,404 barras diarias / 33.35 años).
- **Umbrales Percentiles L0** (empíricos del Fact Store):
  - `DEEP_CALM`: $< 11.34$
  - `CALM`: $11.34 - 12.64$
  - `NORMAL`: $12.64 - 15.29$
  - `ELEVATED`: $15.29 - 20.63$
  - `HIGH_VOL`: $20.63 - 26.08$
  - `EXTREME_VOL`: $26.08 - 33.47$
  - `CRISIS_SPIKE`: $> 33.47$

---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Std = 1.9206.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store. PurgedKFold con 10 días de purga.
- **DSR p-value**: **1.0000** ✅ (significativo)
- **Mean Sharpe Ratio**: 0.5360 ± 0.3125 (5 folds)
- **Fold SRs**: [0.844, 0.1135, 0.198, 0.8203, 0.6772]

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\sigma^2_{\text{epistémica}}$): **0.000001** (N=46 estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas por N

| Escala ZigZag | Horizonte Máximo | $EV_{\text{net}}$ (ponderado) | $P(\text{bull})$ (ponderado) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+0.16%` | `55.9%` | `8.1d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `+0.98%` | `62.1%` | `23.0d` |
| **`zz75` (7.5% Estructural)** | 90 días | `+1.73%` | `64.2%` | `40.9d` |

**Población total**: 8,403 observaciones | $P(\text{bull})$ ponderado = 62.1% | $EV_{50}$ ponderado = +0.98%

---

## 3. Anomalías Empíricas (extraídas del Fact Store, N ≥ 20)

### 🚨 Anomalía Empírica 1: `DEEP_CALM__RISING_3D` (Alcista)
- **Condición**: Estado empírico con N=42 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 81.0\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.67\%$, $EV_{\text{per\_day}} = +0.0721\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### 🚨 Anomalía Empírica 2: `NORMAL__FAST_CRUSH_3D` (Alcista)
- **Condición**: Estado empírico con N=122 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 71.3\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.37\%$, $EV_{\text{per\_day}} = +0.0657\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### 🚨 Anomalía Empírica 3: `CALM__RISING_3D` (Alcista)
- **Condición**: Estado empírico con N=152 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 79.6\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.19\%$, $EV_{\text{per\_day}} = +0.0634\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### ⚠️ Anomalía Bajista 1: `CRISIS_SPIKE__RISING_3D`
- **Condición**: Estado empírico con N=37 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 48.6\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.43\%$.
- **Régimen**: `FULL_STRUCTURAL_BEAR` → `STK_BLOCK_CRISIS`.

### ⚠️ Anomalía Bajista 2: `HIGH_VOL__DECELERATING_3D`
- **Condición**: Estado empírico con N=300 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 51.7\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.16\%$.
- **Régimen**: `TACTICAL_PULLBACK` → `STK_BUY_DIP_TACTICAL`.

### ⚠️ Anomalía Bajista 3: `HIGH_VOL__FAST_CRUSH_3D`
- **Condición**: Estado empírico con N=226 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 53.5\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.04\%$.
- **Régimen**: `TRANSITIONAL` → `STK_HOLD_STABLE`.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\text{bull})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `VIX` | `VALIDATED (Grade A)` | **1.0000** | 0.5360 | 62.1% | 46 | 4 | **Grade C — Informational Only** |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**: Consultar fact store para señal específica por nivel + velocidad.
2. **`SpeculativeEntryHub`**: En estados `FULL_STRUCTURAL_BEAR`, respetar el bloqueo.
