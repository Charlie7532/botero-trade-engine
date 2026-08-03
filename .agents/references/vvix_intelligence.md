# CBOE VVIX (Volatility of VIX) Intelligence — Reference Document

> **Auto-generated**: 2026-08-03T19:05:23Z | **Source**: `vvix_fact_store.json` | **Status**: `VALIDATED (Grade A)`

## 1. Ficha Técnica del Indicador
- **Nombre**: CBOE VVIX (Volatility of VIX) (`VVIX`)
- **Fórmula**: Volatilidad implícita del VIX — mide la inestabilidad del mercado de volatilidad.
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='VVIX', timeframe='1d').
- **Rango Histórico**: 2006-03-06 → 2026-07-30 (5,072 barras diarias / 20.13 años).
- **Umbrales Percentiles L0** (empíricos del Fact Store):
  - `DEEP_STABILITY`: $< 71.02$
  - `STABLE_VOL`: $71.02 - 78.73$
  - `NORMAL_VVIX`: $78.73 - 85.78$
  - `ELEVATED_VVIX`: $85.78 - 96.87$
  - `HIGH_VVIX_RISK`: $96.87 - 109.95$
  - `EXTREME_VVIX_INSTABILITY`: $109.95 - 122.16$
  - `VOL_OF_VOL_CRISIS`: $> 122.16$

---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Std = 4.5217.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store. PurgedKFold con 10 días de purga.
- **DSR p-value**: **0.9912** ✅ (significativo)
- **Mean Sharpe Ratio**: 0.5687 ± 0.5017 (5 folds)
- **Fold SRs**: [-0.1605, 1.107, 0.863, 0.4079, 1.1922]

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\sigma^2_{\text{epistémica}}$): **0.000001** (N=49 estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas por N

| Escala ZigZag | Horizonte Máximo | $EV_{\text{net}}$ (ponderado) | $P(\text{bull})$ (ponderado) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+0.17%` | `57.5%` | `7.4d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `+0.76%` | `62.0%` | `22.0d` |
| **`zz75` (7.5% Estructural)** | 90 días | `+1.68%` | `66.4%` | `40.4d` |

**Población total**: 5,071 observaciones | $P(\text{bull})$ ponderado = 62.0% | $EV_{50}$ ponderado = +0.76%

---

## 3. Anomalías Empíricas (extraídas del Fact Store, N ≥ 20)

### 🚨 Anomalía Empírica 1: `VOL_OF_VOL_CRISIS__DECELERATING_3D` (Alcista)
- **Condición**: Estado empírico con N=28 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 85.7\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +3.48\%$, $EV_{\text{per\_day}} = +0.2176\%/\text{día}$.
- **Régimen**: `TACTICAL_PULLBACK` → `STK_BUY_DIP_TACTICAL`.

### 🚨 Anomalía Empírica 2: `NORMAL_VVIX__VVIX_ACCUMULATION_3D` (Alcista)
- **Condición**: Estado empírico con N=37 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 75.7\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.72\%$, $EV_{\text{per\_day}} = +0.1007\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### 🚨 Anomalía Empírica 3: `ELEVATED_VVIX__EXTREME_VVIX_SPIKE_3D` (Alcista)
- **Condición**: Estado empírico con N=20 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 75.0\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.39\%$, $EV_{\text{per\_day}} = +0.1405\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### ⚠️ Anomalía Bajista 1: `DEEP_STABILITY__RISING_3D`
- **Condición**: Estado empírico con N=32 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 40.6\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -1.13\%$.
- **Régimen**: `TACTICAL_PULLBACK` → `STK_BUY_DIP_TACTICAL`.

### ⚠️ Anomalía Bajista 2: `HIGH_VVIX_RISK__EXTREME_VVIX_SPIKE_3D`
- **Condición**: Estado empírico con N=70 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 54.3\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.68\%$.
- **Régimen**: `TACTICAL_PULLBACK` → `STK_BUY_DIP_TACTICAL`.

### ⚠️ Anomalía Bajista 3: `VOL_OF_VOL_CRISIS__EXTREME_VVIX_CRUSH_3D`
- **Condición**: Estado empírico con N=28 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 50.0\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.48\%$.
- **Régimen**: `TRANSITIONAL` → `STK_HOLD_STABLE`.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\text{bull})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `VVIX` | `VALIDATED (Grade A)` | **0.9912** | 0.5687 | 62.0% | 49 | 0 | **Grade C — Informational Only** |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**: VVIX es confirmador de régimen de VIX, no señal primaria.
2. **`SpeculativeEntryHub`**: VVIX > P95 indica transición de régimen vol.
