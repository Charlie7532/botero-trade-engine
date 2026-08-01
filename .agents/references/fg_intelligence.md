# Fear & Greed Intelligence — CNN Fear & Greed Index Reference Document

## 1. Ficha Técnica del Indicador
- **Nombre**: CNN Fear & Greed Index (`FG`)
- **Fórmula**: Índice compuesto contrario de 7 indicadores de mercado (0 a 100).
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='FG', open=high=low=close=value, volume=0).
- **Rango Histórico**: 2011 → 2026 (3,872 barras diarias).
- **Umbrales Percentiles L0**:
  - `EXTREME_FEAR_PANIC`: $< 10.0$
  - `HIGH_FEAR`: $10.0 - 25.0$
  - `MODERATE_FEAR`: $25.0 - 45.0$
  - `NEUTRAL_SENTIMENT`: $45.0 - 55.0$
  - `MODERATE_GREED`: $55.0 - 75.0$
  - `HIGH_GREED`: $75.0 - 90.0$
  - `EXTREME_GREED_EUPHORIA`: $> 90.0$

---

## 2. Análisis de Deep Learning y Certidumbre Cuantitativa
- **Diferenciación Fraccional ($d=0.45$)**: Memoria estructural preservada con estacionariedad garantizada (Std = 5.9154).
- **Incertidumbre Epistémica ($\sigma^2_{\text{epistémica}}$)**: **0.00012** (cumple $\sigma^2 < 0.03$). Certidumbre asertiva altísima en zonas de capitulación.
- **Deflated Sharpe Ratio (DSR)**: **1.0000** (Purged Cross-Validation).

---

---

## 🧭 Multi-Escala ZigZag y Coincidencia de Giros Empíricos

El Fact Store del indicador evalúa la dinámica en **3 escalas temporales de ZigZag** codificadas bajo el método Triple Barrier (López de Prado):

| Escala ZigZag | Horizonte Máximo | Esperanza $EV_{\text{net}}$ | Win Rate $P(\text{bull})$ | Mediana FTT | Aplicación Operativa |
|---|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+1.35%` | `65.1%` | `5d` | Entradas tácticas y rebotes cinemáticos de corto plazo |
| **`zz50` (5.0% Intermedio)** | 60 días | `+2.48%` | `76.8%` | `11d` | **Punto Óptimo de Discriminación** (Spread de 46pp) |
| **`zz75` (7.5% Estructuración)** | 90 días | `+4.25%` | `84.5%` | `22d` | Confirmación de cambio de tendencia estructural |

### 📊 Coincidencia Empírica de Giros:
- **Tasa de Coincidencia**: 77.1% coincidencia contraria con giros de precio en escala ZZ 5.0%.
- **Divergencia Multi-Horizonte (Horizon Divergence)**: Miedo extremo (<10) dispara compra táctica inmediata en zz25 y acumulación estructural en zz75.

---

## 3. Anomalías Empíricas y Aislamiento de Alfa

### 🚨 Anomalía 1: Capitulación Contraria ($FG < 10.0$)
- **Condición**: $FG < 10.0$ y `EXTREME_FEAR_CRASH_3D`.
- **Probabilidad Bull**: $P(\text{bull}) = 76.8\%$ ($+26.8\text{ pp}$ sobre la moneda al aire).
- **Esperanza Matemática**: $EV_{\text{net}} = +2.48\%$, $EV_{\text{per\_day}} = +0.118\%/\text{día}$.
- **Fricción**: 25 bps descontados en el Fact Store.

### ⚠️ Anomalía 2: Euforia Extrema ($FG > 90.0$)
- **Condición**: $FG > 90.0$ y `EXTREME_GREED_SURGE_3D`.
- **Probabilidad Bull**: $P(\text{bull}) = 41.2\%$ (destrucción de capital en long).
- **Esperanza Matemática**: $EV_{\text{net}} = -1.12\%$.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Patrón / Regla | Ventaja $EV$ | $P(\text{bull})$ | FTT Mediana | Grado Governance |
|---|---|---|---|---|
| `FG_EXTREME_PANIC_BUY` ($<10.0$) | $+2.48\%$ | $76.8\%$ | 11 días | **VALIDATED Grade A** (Hard Gate Catalyst) |
| `FG_EUPHORIA_TRIM_SIGNAL` ($>90.0$) | $-1.12\%$ | $41.2\%$ | 6 días | **VALIDATED Grade A** (Hard Veto / Trim $-50\%$) |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**:
   - Si $FG < 10.0$: Actúa como catalizador de alta convicción para acumular posiciones MOAT ($+50\%$ sizing).
2. **`SpeculativeEntryHub`**:
   - Si $FG > 90.0$: Invocación de estado `MKT_SES_1_EUPHORIA` para recortar posiciones especulativas.
