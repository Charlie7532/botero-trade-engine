# CBOE Put/Call Ratio Intelligence — Reference Document

## 1. Ficha Técnica del Indicador
- **Nombre**: CBOE Total Put/Call Ratio (`CBOE_PCR`)
- **Fórmula**: Ratio diario entre volumen negociado de opciones Put y Call.
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='CBOE_PCR', open=high=low=close=value, volume=0).
- **Rango Histórico**: 2006 → 2026 (4,924 barras diarias).
- **Umbrales Percentiles L0**:
  - `EXTREME_CALL_COMPLACENCY`: $< 0.65$
  - `CALL_DOMINATED`: $0.65 - 0.78$
  - `NORMAL_EQUILIBRIUM`: $0.78 - 0.92$
  - `ELEVATED_PUT_HEDGING`: $0.92 - 1.08$
  - `HIGH_PUT_PROTECTION`: $1.08 - 1.25$
  - `EXTREME_PANIC_PUTS`: $1.25 - 1.45$
  - `CRISIS_PUT_PANIC_SPIKE`: $> 145.0$ (ó $> 1.45$).

---

## 2. Análisis de Deep Learning y Certidumbre Cuantitativa
- **Diferenciación Fraccional ($d=0.45$)**: Estacionariedad cuantitativa de demanda de cobertura (Std = 0.1253).
- **Incertidumbre Epistémica ($\sigma^2_{\text{epistémica}}$)**: **0.00013** (cumple $\sigma^2 < 0.03$).
- **Deflated Sharpe Ratio (DSR)**: **1.0000** (Purged Cross-Validation).

---

## 🧭 Multi-Escala ZigZag y Coincidencia de Giros Empíricos

El Fact Store del indicador evalúa la dinámica en **3 escalas temporales de ZigZag** codificadas bajo el método Triple Barrier (López de Prado):

| Escala ZigZag | Horizonte Máximo | Esperanza $EV_{\text{net}}$ | Win Rate $P(\text{bull})$ | Mediana FTT | Aplicación Operativa |
|---|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+1.18%` | `63.8%` | `4d` | Entradas tácticas y rebotes cinemáticos de corto plazo |
| **`zz50` (5.0% Intermedio)** | 60 días | `+2.32%` | `75.2%` | `10d` | **Punto Óptimo de Discriminación** (Spread de 46pp) |
| **`zz75` (7.5% Estructuración)** | 90 días | `+3.92%` | `82.9%` | `20d` | Confirmación de cambio de tendencia estructural |

### 📊 Coincidencia Empírica de Giros:
- **Tasa de Coincidencia**: 75.5% coincidencia en capitulación de opciones Put.
- **Divergencia Multi-Horizonte (Horizon Divergence)**: PCR >1.25 muestra piso cinemático táctico a 4d (zz25) y expansión a 20d (zz75).

---

## 3. Anomalías Empíricas y Aislamiento de Alfa

### 🚨 Anomalía 1: Capitulación de Coberturas ($PCR > 1.25$)
- **Condición**: $PCR > 1.25$ y `EXTREME_PCR_SPIKE_3D`.
- **Probabilidad Bull**: $P(\text{bull}) = 75.2\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = +2.32\%$.
- **Fricción**: 10 bps estándar.

### ⚠️ Anomalía 2: Complacencia Masiva de Calls ($PCR < 0.65$)
- **Condición**: $PCR < 0.65$ y `EXTREME_PCR_CRUSH_3D`.
- **Probabilidad Bull**: $P(\text{bull}) = 43.1\%$.
- **Esperanza Matemática**: $EV_{\text{net}} = -0.78\%$.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Patrón / Regla | Status Tag | DSR Score | Ventaja $EV$ | $P(\text{{bull}})$ | FTT Mediana | Grado & Nivel de Autoridad (`hypothesis-governance`) |
|---|:---:|:---:|:---:|:---:|:---:|---|
| `PCR_CAPITULATION_BUY` ($>1.25$) | `VALIDATED` | **1.0000** | $+2.32\%$ | $75.2\%$ | 10 días | **Grade A — Hard Gate Principal** (Put Capitulation Catalyst) |
| `PCR_CALL_COMPLACENCY` ($<0.65$) | `VALIDATED` | **0.8610** | $-0.78\%$ | $43.1\%$ | 6 días | **Grade B — Hard Gate Subordinado** (Position Sizing $-25\%$) |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**:
   - Si $PCR > 1.25$: Valida extremo de cobertura institucional y autoriza buy-the-dip.
2. **`SpeculativeEntryHub`**:
   - Si $PCR < 0.65$: Bloquear acumulación de Calls OTM por saturación de prima.
