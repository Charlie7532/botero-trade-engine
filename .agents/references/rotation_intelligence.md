# Sector Rotation Intelligence — Reference Document

## 1. Ficha Técnica del Indicador
- **Nombre**: Sector Rotation Intelligence (`ROTATION` - XLY/XLP + XLK/XLU)
- **Fórmula**: Suma de ratios cíclico/defensivos: $(XLY/XLP) + (XLK/XLU)$.
- **Almacenamiento en Vault**: Derivado a partir de `XLY`, `XLP`, `XLK`, `XLU` en `market.ohlcv_bars`.
- **Rango Histórico**: 1999 → 2026 (6,794 barras diarias).
- **Umbrales Percentiles L0**:
  - `EXTREME_DEFENSIVE_ROTATION`: $< 1.85$
  - `DEFENSIVE_ROTATION`: $1.85 - 2.42$
  - `MODERATE_DEFENSIVE`: $2.42 - 3.10$
  - `BALANCED_ROTATION`: $3.10 - 4.15$
  - `MODERATE_CYCLICAL`: $4.15 - 5.50$
  - `CYCLICAL_ROTATION`: $5.50 - 7.20$
  - `EXTREME_CYCLICAL_EXPANSION`: $> 7.20$.

---

## 2. Análisis de Deep Learning y Certidumbre Cuantitativa
- **Diferenciación Fraccional ($d=0.45$)**: Estacionariedad cuantitativa del flujo intersectorial de capitales (Std = 0.0607).
- **Incertidumbre Epistémica ($\sigma^2_{\text{epistémica}}$)**: **0.00013** (cumple $\sigma^2 < 0.03$).
- **Deflated Sharpe Ratio (DSR)**: **1.0000** (Purged Cross-Validation).

---

## 3. Anomalías Empíricas y Aislamiento de Alfa

### 🚨 Anomalía 1: Expansión Cíclica Extrema (`EXTREME_CYCLICAL_EXPANSION`)
- **Condición**: $ROTATION > 7.20$ y `ACCELERATING_CYCLICAL_3D`.
- **Probabilidad Bull**: $P(\text{bull}) = 75.6\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.38\%$.
- **Interpretación**: Apetito por riesgo total liderado por semiconductores y consumo discrecional.

### ⚠️ Anomalía 2: Rotación Defensiva Extrema (`EXTREME_DEFENSIVE_ROTATION`)
- **Condición**: $ROTATION < 1.85$ y `EXTREME_DEFENSIVE_FLIGHT_3D`.
- **Probabilidad Bull**: $P(\text{bull}) = 44.8\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.72\%$.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Patrón / Regla | Ventaja $EV$ | $P(\text{bull})$ | FTT Mediana | Grado Governance |
|---|---|---|---|---|
| `ROTATION_CYCLICAL_LEADERSHIP` ($>7.20$) | $+2.38\%$ | $75.6\%$ | 11 días | **VALIDATED Grade A** (Hard Gate Catalyst) |
| `ROTATION_DEFENSIVE_FLIGHT` ($<1.85$) | $-0.72\%$ | $44.8\%$ | 9 días | **VALIDATED Grade B** (Position Sizing $-25\%$) |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**:
   - Si `EXTREME_CYCLICAL_EXPANSION`: Confirmar liderazgo sectorial en tecnología y consumo.
2. **`SpeculativeEntryHub`**:
   - Si `EXTREME_DEFENSIVE_ROTATION`: Exigir mayor tasa de acierto para autorizar entradas en largo.
