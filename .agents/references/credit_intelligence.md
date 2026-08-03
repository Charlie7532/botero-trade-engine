# High Yield Corporate Credit Stress Ratio (HYG/TLT) Intelligence — Reference Document

> **Auto-generated**: 2026-08-03T19:05:27Z | **Source**: `credit_fact_store.json` | **Status**: `VALIDATED (Grade A)`

## 1. Ficha Técnica del Indicador
- **Nombre**: High Yield Corporate Credit Stress Ratio (HYG/TLT) (`CREDIT`)
- **Fórmula**: Ratio HYG/TLT — mide apetito por riesgo crediticio vs refugio soberano.
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='CREDIT', timeframe='1d').
- **Rango Histórico**: 2007-04-11 → 2026-07-30 (4,857 barras diarias / 19.27 años).
- **Umbrales Percentiles L0** (empíricos del Fact Store):
  - `EXTREME_CREDIT_FREEZE`: $< 0.45$
  - `CREDIT_STRESS_HIGH`: $0.45 - 0.50$
  - `CREDIT_STRESS_MODERATE`: $0.50 - 0.55$
  - `NEUTRAL_CREDIT`: $0.55 - 0.61$
  - `HEALTHY_CREDIT`: $0.61 - 0.75$
  - `EXPANSIVE_CREDIT`: $0.75 - 0.90$
  - `MAX_CREDIT_EXPANSION`: $> 0.90$

---

## 2. Validación Cuantitativa y Certidumbre

### Estacionariedad
- **Diferenciación Fraccional ($d=0.40$)**: Std = 0.0064.

### DSR — Deflated Sharpe Ratio (Conditional Returns, PurgedKFold)
- **Metodología**: Retornos reales de SPY a 5 días, condicionados por la señal del fact store. PurgedKFold con 10 días de purga.
- **DSR p-value**: **0.9966** ✅ (significativo)
- **Mean Sharpe Ratio**: 0.7137 ± 0.4050 (5 folds)
- **Fold SRs**: [0.2187, 1.3452, 0.5834, 0.6409, 1.1374]

### Incertidumbre Epistémica (Bootstrap)
- **Varianza Bootstrap** ($\sigma^2_{\text{epistémica}}$): **0.000001** (N=49 estados, 1000 resamples)

---

## 🧭 Multi-Escala ZigZag — Estadísticas Ponderadas por N

| Escala ZigZag | Horizonte Máximo | $EV_{\text{net}}$ (ponderado) | $P(\text{bull})$ (ponderado) | FTT Mediana |
|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+0.11%` | `56.5%` | `7.1d` |
| **`zz50` (5.0% Intermedio)** | 60 días | `+0.66%` | `61.1%` | `22.1d` |
| **`zz75` (7.5% Estructural)** | 90 días | `+1.47%` | `64.9%` | `40.4d` |

**Población total**: 4,856 observaciones | $P(\text{bull})$ ponderado = 61.1% | $EV_{50}$ ponderado = +0.66%

---

## 3. Anomalías Empíricas (extraídas del Fact Store, N ≥ 20)

### 🚨 Anomalía Empírica 1: `EXTREME_CREDIT_FREEZE__EXTREME_CREDIT_CRASH_3D` (Alcista)
- **Condición**: Estado empírico con N=38 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 76.3\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +3.31\%$, $EV_{\text{per\_day}} = +1.6532\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### 🚨 Anomalía Empírica 2: `EXTREME_CREDIT_FREEZE__STABLE_CREDIT_3D` (Alcista)
- **Condición**: Estado empírico con N=44 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 79.5\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.85\%$, $EV_{\text{per\_day}} = +0.2379\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### 🚨 Anomalía Empírica 3: `EXTREME_CREDIT_FREEZE__FAST_CREDIT_RECOVERY_3D` (Alcista)
- **Condición**: Estado empírico con N=24 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 75.0\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.66\%$, $EV_{\text{per\_day}} = +0.4437\%/\text{día}$.
- **Régimen**: `FULL_STRUCTURAL_BULL` → `STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION`.

### ⚠️ Anomalía Bajista 1: `NEUTRAL_CREDIT__EXTREME_CREDIT_CRASH_3D`
- **Condición**: Estado empírico con N=39 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 43.6\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -1.32\%$.
- **Régimen**: `FULL_STRUCTURAL_BEAR` → `STK_BLOCK_CRISIS`.

### ⚠️ Anomalía Bajista 2: `HEALTHY_CREDIT__FAST_CREDIT_RECOVERY_3D`
- **Condición**: Estado empírico con N=115 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 47.0\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.97\%$.
- **Régimen**: `FULL_STRUCTURAL_BEAR` → `STK_BLOCK_CRISIS`.

### ⚠️ Anomalía Bajista 3: `HEALTHY_CREDIT__EXTREME_CREDIT_SURGE_3D`
- **Condición**: Estado empírico con N=45 observaciones.
- **Probabilidad Bull**: $P(\text{bull}) = 46.7\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.77\%$.
- **Régimen**: `TACTICAL_BOUNCE_ONLY` → `STK_BUY_DIP_TACTICAL_ONLY_STRICT_STOP`.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Indicador | Status | DSR p-value | Mean SR | $P(\text{bull})$ ponderado | N estados | N mínimo | Grado |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `CREDIT` | `VALIDATED (Grade A)` | **0.9966** | 0.7137 | 61.1% | 49 | 2 | **Grade C — Informational Only** |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**: Credit stress alto (P05-P15) es zona de alerta SIGMET.
2. **`CIO Allocator`**: Credit es dimensión independiente de volatilidad (bond market).
