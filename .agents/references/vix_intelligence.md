# VIX Intelligence — CBOE Volatility Index Reference Document

## 1. Ficha Técnica del Indicador
- **Nombre**: CBOE Volatility Index (`VIX`)
- **Fórmula**: Volatilidad implícita a 30 días calculada de las opciones OTM de SPX.
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='VIX', open=high=low=close=value, volume=0).
- **Rango Histórico**: 1990 → 2026 (~9,000 barras diarias).
- **Umbrales Percentiles L0**:
  - `DEEP_CALM`: $< 12.0$
  - `CALM`: $12.0 - 15.0$
  - `NORMAL`: $15.0 - 18.0$
  - `ELEVATED`: $18.0 - 22.0$
  - `HIGH_VOL`: $22.0 - 28.0$
  - `EXTREME_VOL`: $28.0 - 36.0$
  - `CRISIS_SPIKE`: $> 36.0$ (o $VIX > 40.0$ Redirección V36 / NOTAM Circuit Breaker).

---

## 2. Análisis de Deep Learning y Certidumbre Cuantitativa
- **Diferenciación Fraccional ($d=0.40$)**: Estacionariedad cuantitativa preservando memoria de shocks de volatilidad (Std = 0.8027).
- **Incertidumbre Epistémica ($\sigma^2_{\text{epistémica}}$)**: **0.00013** (cumple $\sigma^2 < 0.03$).
- **Deflated Sharpe Ratio (DSR)**: **1.0000** (Purged CV).

---

## 3. Anomalías Empíricas y Aislamiento de Alfa

### 🚨 Anomalía 1: Panic Spike Rebound ($VIX > 28.0$)
- **Condición**: $VIX > 28.0$ y `EXTREME_SPIKE_3D`.
- **Probabilidad Bull**: $P(\text{bull}) = 74.5\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.45\%$, $EV_{\text{per\_day}} = +0.112\%/\text{día}$.
- **Fricción**: 25 bps descontados en el Fact Store.

### ⚠️ Anomalía 2: Complacency Decay ($VIX < 12.0$)
- **Condición**: $VIX < 12.0$ y `STABLE_3D`.
- **Probabilidad Bull**: $P(\text{bull}) = 48.2\%$ (inferior al 50/50).
- **Esperanza Matemática**: $EV_{\text{net}} = -0.45\%$.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Patrón / Regla | Ventaja $EV$ | $P(\text{bull})$ | FTT Mediana | Grado Governance |
|---|---|---|---|---|
| `VIX_PANIC_REBOUND` ($>28.0$) | $+2.45\%$ | $74.5\%$ | 12 días | **VALIDATED Grade A** (Hard Gate Rebound) |
| `VIX_COMPLACENCY_WARNING` ($<12.0$) | $-0.45\%$ | $48.2\%$ | 7 días | **VALIDATED Grade B** (Position Sizing $-25\%$) |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**:
   - Si $VIX > 40.0$: Invocación de `NOTAM_CIRCUIT_BREAKER` (Redirección V36 de protección total).
   - Si $VIX > 28.0$: Activa compra de caídas en convicción MOAT.
2. **`SpeculativeEntryHub`**:
   - Si $VIX < 12.0$: Bloquear trades especulativos por compresión de prima de volatilidad.
