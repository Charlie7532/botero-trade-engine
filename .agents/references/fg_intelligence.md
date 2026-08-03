# CNN Fear & Greed Index Intelligence — Reference Document

> **Auto-generated**: 2026-08-03T19:05:24Z | **Source**: `fg_fact_store.json` | **Status**: `VALIDATED (Grade A)`

## 1. Ficha Técnica del Indicador
- **Nombre**: CNN Fear & Greed Index (`FG`)
- **Fórmula**: Índice compuesto CNN de 7 indicadores de sentimiento (0=miedo extremo, 100=codicia extrema).
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='FG', timeframe='1d').
- **Rango Histórico**: market.ohlcv_bars → present (3,870 barras diarias / 15.4 años).
- **Umbrales Percentiles L0** (empíricos del Fact Store):
  - `DEEP_FEAR`: $< 12.00$
  - `EUPHORIA`: $12.00 - 24.56$
  - `EXTREME_FEAR`: $24.56 - 41.00$
  - `EXTREME_GREED`: $41.00 - 59.52$
  - `FEAR`: $59.52 - 71.14$
  - `GREED`: $71.14 - 81.00$
  - `NEUTRAL`: $> 81.00$

---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Std = 10.9852.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store. PurgedKFold con 10 días de purga.
- **DSR p-value**: **0.9977** ✅ (significativo)
- **Mean Sharpe Ratio**: 0.7745 ± 0.3001 (5 folds)
- **Fold SRs**: [0.6618, 0.5827, 0.4069, 0.8712, 1.2817]

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\sigma^2_{\text{epistémica}}$): **0.000001** (N=46 estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas por N

| Escala ZigZag | Horizonte Máximo | $EV_{\text{net}}$ (ponderado) | $P(\text{bull})$ (ponderado) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+0.27%` | `58.3%` | `9.1d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `+1.11%` | `64.7%` | `28.2d` |
| **`zz75` (7.5% Estructural)** | 90 días | `+2.14%` | `68.8%` | `57.7d` |

**Población total**: 3,870 observaciones | $P(\text{bull})$ ponderado = 64.7% | $EV_{50}$ ponderado = +1.11%

---

## 3. Anomalías Empíricas (extraídas del Fact Store, N ≥ 20)

### 🚨 Anomalía Empírica 1: `EUPHORIA__RISING_3D` (Alcista)
- **Condición**: Estado empírico con N=44 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 79.5\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.68\%$, $EV_{\text{per\_day}} = +0.0743\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### 🚨 Anomalía Empírica 2: `EUPHORIA__FALLING_3D` (Alcista)
- **Condición**: Estado empírico con N=26 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 73.1\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.49\%$, $EV_{\text{per\_day}} = +0.0682\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### 🚨 Anomalía Empírica 3: `GREED__SURGING_EXTREME_3D` (Alcista)
- **Condición**: Estado empírico con N=46 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 76.1\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.31\%$, $EV_{\text{per\_day}} = +0.0571\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### ⚠️ Anomalía Bajista 1: `EXTREME_GREED__SURGING_EXTREME_3D`
- **Condición**: Estado empírico con N=26 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 42.3\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.73\%$.
- **Régimen**: `TACTICAL_PULLBACK` → `STK_BUY_DIP_TACTICAL`.

### ⚠️ Anomalía Bajista 2: `EXTREME_GREED__FALLING_3D`
- **Condición**: Estado empírico con N=46 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 43.5\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.44\%$.
- **Régimen**: `TACTICAL_PULLBACK` → `STK_BUY_DIP_TACTICAL`.

### ⚠️ Anomalía Bajista 3: `FEAR__SURGING_EXTREME_3D`
- **Condición**: Estado empírico con N=42 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 47.6\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.35\%$.
- **Régimen**: `FULL_STRUCTURAL_BEAR` → `STK_BLOCK_CRISIS`.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\text{bull})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `FG` | `VALIDATED (Grade A)` | **0.9977** | 0.7745 | 64.7% | 46 | 1 | **Grade C — Informational Only** |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**: Fear extremo es contrarian — BUT requiere confirmación por velocidad.
2. **Greed extremo NO es señal bajista** — data empírica muestra EV positivo.
