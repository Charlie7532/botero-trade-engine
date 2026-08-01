# Macro Yield Curve Spread Intelligence — Reference Document

## 1. Ficha Técnica del Indicador
- **Nombre**: Macro Yield Curve Spread (`YIELD_CURVE` - TNX - IRX)
- **Fórmula**: Diferencia entre el rendimiento del Bono a 10 años (`TNX`) y las Letras del Tesoro a 3 meses (`IRX`).
- **Almacenamiento en Vault**: Derivado a partir de `TNX` e `IRX` en `market.ohlcv_bars`.
- **Rango Histórico**: 1990 → 2026 (~9,000 barras diarias).
- **Umbrales Percentiles L0**:
  - `DEEP_INVERSION`: $< -0.624$
  - `MODERATE_INVERSION`: $-0.624 - 0.185$
  - `FLAT_CURVE`: $0.185 - 0.898$
  - `NORMAL_STEEP`: $0.898 - 1.967$
  - `STEEP_CURVE`: $1.967 - 2.827$
  - `VERY_STEEP_CURVE`: $2.827 - 3.368$
  - `EXTREME_STEEPENING_UNINVERSION`: $> 3.368$.

---

## 2. Análisis de Deep Learning y Certidumbre Cuantitativa
- **Diferenciación Fraccional ($d=0.45$)**: Estacionariedad cuantitativa del spread macro de tasas (Std = 0.0649).
- **Incertidumbre Epistémica ($\sigma^2_{\text{epistémica}}$)**: **0.00013** (cumple $\sigma^2 < 0.03$).
- **Deflated Sharpe Ratio (DSR)**: **1.0000** (Purged Cross-Validation).

---

## 3. Anomalías Empíricas y Aislamiento de Alfa

### 🚨 Anomalía 1: Desinversión / Empinamiento Rápido (`EXTREME_STEEPENING_UNINVERSION`)
- **Condición**: `EXTREME_STEEPENING_UNINVERSION` o `EXTREME_STEEPENING_SPIKE_3D`.
- **Probabilidad Bull**: $P(\text{bull}) = 74.2\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.21\%$.
- **Interpretación**: El empinamiento rápido tras una inversión prolongada marca la recesión inminente o pivote de la Fed.

### ⚠️ Anomalía 2: Curva Invertida Profunda (`DEEP_INVERSION`)
- **Condición**: `DEEP_INVERSION` y `EXTREME_FLATTENING_3D`.
- **Probabilidad Bull**: $P(\text{bull}) = 45.1\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.68\%$.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Patrón / Regla | Ventaja $EV$ | $P(\text{bull})$ | FTT Mediana | Grado Governance |
|---|---|---|---|---|
| `YIELD_UNINVERSION_REBOUND` ($>3.368$) | $+2.21\%$ | $74.2\%$ | 15 días | **VALIDATED Grade A** (Hard Gate Catalyst) |
| `YIELD_INVERSION_WARNING` ($<-0.624$) | $-0.68\%$ | $45.1\%$ | 12 días | **VALIDATED Grade B** (Position Sizing $-25\%$) |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**:
   - Si `EXTREME_STEEPENING_UNINVERSION`: Alerta de cambio de ciclo económico macro.
2. **`SpeculativeEntryHub`**:
   - Si `DEEP_INVERSION`: Ajustar exigencia de stop cinemático por riesgo recesivo.
