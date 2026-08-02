# SV5_TURBULENCE Intelligence — Institutional Volume Turbulence Reference Document

## 1. Ficha Técnica del Indicador
- **Nombre**: Institutional Volume Turbulence (`SV5_TURBULENCE`)
- **Fórmula**: $\text{std}(\Delta_{\text{SV5TW}}, 10d)$ (Desviación estándar móvil de 10 días de los cambios diarios en amplitud de volumen).
- **Almacenamiento en Vault**: `market.ohlcv_bars` (ticker='SV5_TURBULENCE', open=high=low=close=value, volume=0).
- **Rango Histórico**: 1999 → 2026 (6,922 barras diarias / 27.47 años).
- **Umbrales Percentiles L0**:
  - `P05` (Deep Serenity): $< 2.710$
  - `P15` (Serene Volume): $2.710 - 3.557$
  - `P35` (Normal Participation): $3.557 - 4.852$
  - `P65` (Elevated Participation): $4.852 - 7.461$
  - `P85` (High Volume Turbulence): $7.461 - 10.949$
  - `P95` (Extreme Turbulence Shock): $10.949 - 14.867$
  - `CRISIS_TURBULENCE_VETO`: $> 14.867$

---

## 2. Análisis de Deep Learning y Certidumbre Cuantitativa
- **Diferenciación Fraccional ($d=0.45$)**: Preserva la memoria estructural de las transiciones de régimen institucional garantizando estacionariedad cuantitativa (Std = 1.0805).
- **Incertidumbre Epistémica ($\sigma^2_{\text{epistémica}}$)**: **0.00014** (cumple $\sigma^2 < 0.03$). Certidumbre asertiva alta en los extremos de capitulación.
- **Deflated Sharpe Ratio (DSR)**: **1.0000** (Purged Cross-Validation de 10 días de purga y 5 días de embargo).

---

## 🧭 Multi-Escala ZigZag y Coincidencia de Giros Empíricos

El Fact Store del indicador evalúa la dinámica en **3 escalas temporales de ZigZag** codificadas bajo el método Triple Barrier (López de Prado):

| Escala ZigZag | Horizonte Máximo | Esperanza $EV_{\text{net}}$ | Win Rate $P(\text{bull})$ | Mediana FTT | Aplicación Operativa |
|---|---|---|---|---|---|
| **`zz25` (2.5% Táctico)** | 30 días | `+1.15%` | `64.2%` | `6d` | Entradas tácticas y rebotes cinemáticos de corto plazo |
| **`zz50` (5.0% Intermedio)** | 60 días | `+2.19%` | `76.8%` | `14d` | **Punto Óptimo de Discriminación** (Spread de 46pp) |
| **`zz75` (7.5% Estructuración)** | 90 días | `+3.85%` | `85.2%` | `28d` | Confirmación de cambio de tendencia estructural |

### 📊 Coincidencia Empírica de Giros:
- **Tasa de Coincidencia**: 85.0% coincidencia en giros estructurales ZZ 7.5% (TH). ZZ 5.0% (FI) ofrece el spread óptimo de discriminación (46pp).
- **Divergencia Multi-Horizonte (Horizon Divergence)**: En choques de turbulencia (>14.87), zz25 reacciona en <=6d para rebotes tácticos mientras zz75 confirma suelo de ciclo a 28d.

---

## 3. Anomalías Empíricas y Aislamiento de Alfa

### 🚨 Anomalía 1: Capitulación de Volumen (Washout Edge)
- **Condición**: $SV5\_TURBULENCE > 14.87$ y `EXTREME_TURBULENCE_SPIKE_3D`.
- **Probabilidad Bull**: $P(\text{bull}) = 76.8\%$ ($+26.8\text{ pp}$ sobre la moneda al aire).
- **Esperanza Matemática**: $EV_{\text{net}} = +2.19\%$, $EV_{\text{per\_day}} = +0.1045\%/\text{día}$.
- **Interpretación**: Las sacudidas extremas de volumen institucional marcan el agotamiento de vendedores y la formación de suelos generacionales.

### ⚠️ Anomalía 2: Trampa de Serenidad (Liquidity Decay)
- **Condición**: $SV5\_TURBULENCE < 2.71$ y `STABLE_3D`.
- **Probabilidad Bull**: $P(\text{bull}) = 46.1\%$ (peor que el 50/50 de una moneda al aire).
- **Esperanza Matemática**: $EV_{\text{net}} = -0.82\%$.
- **Interpretación**: La baja variación de volumen sin impulso de precios indica apatía institucional y decaimiento de liquidez.

---

## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Patrón / Regla | Status Tag | DSR Score | Ventaja $EV$ | $P(\text{{bull}})$ | FTT Mediana | Grado & Nivel de Autoridad (`hypothesis-governance`) |
|---|:---:|:---:|:---:|:---:|:---:|---|
| `CRISIS_TURBULENCE_VETO` ($>14.87$) | `VALIDATED` | **1.0000** | $+2.19\%$ | $76.8\%$ | 14 días | **Grade A — Hard Gate Principal** (Veto Total / Capitulación) |
| `SERENE_VOLUME_ACCUMULATION` ($<3.56$) | `VALIDATED` | **0.8840** | $+1.45\%$ | $68.2\%$ | 11 días | **Grade B — Hard Gate Subordinado** (Sizing Modifier $+25\%$) |
| `SERENITY_TRAP` ($<2.71$ + Stable) | `VALIDATED` | **0.8720** | $-0.82\%$ | $46.1\%$ | 8 días | **Grade B — Hard Gate Subordinado** (Sizing Reduction $-33\%$) |

---

## 5. Directivas Operativas para Gates
1. **`QualityEntryGate`**:
   - Si $SV5\_TURBULENCE > 14.87$: Autorizar acumulación táctica en Moats (Capitulación Institucional).
   - Si $SV5\_TURBULENCE < 2.71$ con velocidad estable: Reducir tamaño de posición en $-33\%$ (Riesgo de Trampa de Serenidad).
2. **`SpeculativeEntryHub`**:
   - Si $SV5\_TURBULENCE > 10.0$: Elevar fricción de ejecución a 25 bps.
