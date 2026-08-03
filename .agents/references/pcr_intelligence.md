# CBOE Put/Call Ratio Intelligence — Reference Document

> **Auto-generated**: 2026-08-03T19:05:24Z | **Source**: `pcr_fact_store.json` | **Status**: `VALIDATED (Grade A)`

## 1. Ficha Técnica del Indicador
- **Nombre**: CBOE Put/Call Ratio (`CBOE_PCR`)
- **Fórmula**: Ratio total de volumen de puts vs calls en opciones CBOE.
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='CBOE_PCR', timeframe='1d').
- **Rango Histórico**: market.ohlcv_bars → present (4,922 barras diarias / 19.5 años).
- **Umbrales Percentiles L0** (empíricos del Fact Store):
  - `DEEP_BULLISH`: $< 0.73$
  - `BULLISH`: $0.73 - 0.80$
  - `MODERATE_BULLISH`: $0.80 - 0.87$
  - `NEUTRAL`: $0.87 - 0.98$
  - `MODERATE_BEARISH`: $0.98 - 1.09$
  - `BEARISH`: $1.09 - 1.23$
  - `EXTREME_HEDGING`: $> 1.23$

---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Std = 0.0734.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store. PurgedKFold con 10 días de purga.
- **DSR p-value**: **0.9927** ✅ (significativo)
- **Mean Sharpe Ratio**: 0.5866 ± 0.4220 (5 folds)
- **Fold SRs**: [-0.0768, 1.0919, 0.8922, 0.5282, 0.9627]

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\sigma^2_{\text{epistémica}}$): **0.000001** (N=45 estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas por N

| Escala ZigZag | Horizonte Máximo | $EV_{\text{net}}$ (ponderado) | $P(\text{bull})$ (ponderado) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+0.12%` | `57.2%` | `7.1d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `+0.68%` | `61.7%` | `21.7d` |
| **`zz75` (7.5% Estructural)** | 90 días | `+1.56%` | `66.0%` | `39.9d` |

**Población total**: 4,922 observaciones | $P(\text{bull})$ ponderado = 61.7% | $EV_{50}$ ponderado = +0.68%

---

## 3. Anomalías Empíricas (extraídas del Fact Store, N ≥ 20)

### 🚨 Anomalía Empírica 1: `MODERATE_BEARISH__EXTREME_HEDGING_SPIKE_3D` (Alcista)
- **Condición**: Estado empírico con N=31 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 80.7\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.06\%$, $EV_{\text{per\_day}} = +0.0794\%/\text{día}$.
- **Régimen**: `TACTICAL_PULLBACK` → `STK_BUY_DIP_TACTICAL`.

### 🚨 Anomalía Empírica 2: `NEUTRAL__EXTREME_PUT_COLLAPSE_3D` (Alcista)
- **Condición**: Estado empírico con N=48 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 72.9\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.01\%$, $EV_{\text{per\_day}} = +0.1119\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### 🚨 Anomalía Empírica 3: `BULLISH__PUT_UNWIND_3D` (Alcista)
- **Condición**: Estado empírico con N=93 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 73.1\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +1.65\%$, $EV_{\text{per\_day}} = +0.0635\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### ⚠️ Anomalía Bajista 1: `BEARISH__STABLE_3D`
- **Condición**: Estado empírico con N=75 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 52.0\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.20\%$.
- **Régimen**: `TACTICAL_BUY_DIP_ONLY` → `STK_BUY_DIP_TACTICAL_ONLY_STRICT_STOP`.

### ⚠️ Anomalía Bajista 2: `DEEP_BULLISH__PUT_UNWIND_3D`
- **Condición**: Estado empírico con N=48 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 62.5\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.15\%$.
- **Régimen**: `TACTICAL_PULLBACK` → `STK_BUY_DIP_TACTICAL`.

### ⚠️ Anomalía Bajista 3: `EXTREME_HEDGING__EXTREME_HEDGING_SPIKE_3D`
- **Condición**: Estado empírico con N=115 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 54.8\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.09\%$.
- **Régimen**: `TACTICAL_PULLBACK` → `STK_BUY_DIP_TACTICAL`.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\text{bull})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `CBOE_PCR` | `VALIDATED (Grade A)` | **0.9927** | 0.5866 | 61.7% | 45 | 4 | **Grade C — Informational Only** |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**: PCR extremo (P95) es señal contrarian, no de pánico.
2. **`SpeculativeEntryHub`**: Consultar régimen de divergencia antes de actuar.
