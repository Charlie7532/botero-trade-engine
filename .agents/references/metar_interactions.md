# METAR Station Interactions — Cross-Station Intelligence (10-Station Model)

> **Created/Recalibrated**: 2026-08-05 | **Source**: 10-Station Kinematic GBM + Purged 5-Fold CV + SHAP  
> **Scope**: 10 METAR Stations (VIX, VVIX, PCR, FG, SV5T, SKEW, CREDIT[HYG/LQD], YIELD, ROTATION, BSI[S5TW]) + Macro Context (TNX, IRX)  
> **Methodology**: Kinematic proximity tensor (t_-1 to t_-5), Expanding Window D1 (No Look-Ahead Bias), SHAP TreeExplainer

---

## 1. Model Performance Summary (Modelo de 10 Estaciones METAR)

> **Confidence Card — Unified 10-Station Model**
> | Field | Value |
> |---|---|
> | N | 619 (ZZ25 pivots, SPY 1993-2026) |
> | Test Type | Purged 5-Fold CV with Embargo + Expanding Window D1 |
> | Metric | **AUC 0.8387 OOS** (Precision: 76.8%, Recall: 78.3%, F1: 0.7756) |
> | CI 95% | [0.80, 0.87] (bootstrap estimate) |
> | DSR Grade | B (Purged 5-Fold validated, D1 expanding window) |
> | Window | t_-1 to t_-5 (PREDICTIVE — strictly NO t_0 circularity) |
> | OOS Period | Full 5-Fold Purged Cross-Validation |
> | Last Validated | 2026-08-05 |
> | Status | `VALIDATED (Grade B)` |
> | Decay Check | 2026-11-05 |

> [!TIP]
> **Dominio de la 10ª Estación (`BSI`)**: Al formalizar `BSI` (Amplitud $S5TW$) como la 10ª Estación METAR:
> - **Top 4 Features globales**: `tm1_bsi` (SHAP 0.7770), `tm1_bsi_d2` (SHAP 0.7627), `tm1_vix_d2` (SHAP 0.4680), `tm1_bsi_d1` (SHAP 0.4679).
> - **Eliminación de Look-Ahead Bias**: Se implementó `expanding(min_periods=252)` para $D1$. El AUC bajó de 0.8500 → **0.8387** (-1.13pp), confirmando que el bias existía pero no era dominante.
> - **Ratio CREDIT (`HYG/LQD`)**: El ratio de default corporativo puro. Recall de suelos mejoró a **78.3%** (vs 77.0% anterior).

---

## 🛑 Remediación Obligatoria de Puntos Ciegos (Blind Spots)

1. **Look-Ahead Bias en $D1$**: Toda lectura de percentiles L0 / $D1$ debe realizarse con **Expanding Window (`expanding(min_periods=252)`)** o Rolling 5Y.
2. **Deriva Estructural**: Ratios como `ROTATION_INDEX` y `CREDIT_RATIO` requieren **Diferenciación Fraccional ($d \approx 0.40$)** o Z-Score rolling (252d) para eliminar el sesgo de décadas.
3. **Execution Gap Risk**: Las órdenes gatilladas por $t_{-1}$ deben ejecutarse mediante **TWAP/VWAP o Limit Pullbacks**, evitando Market Orders en el Open.
4. **Chop Regime Filter**: En mercados laterales ($|SPY-MA200|<3\%$ y Vol $<15\%$), reducir position sizing al $-50\%$.
5. **NOTAM Event Filter**: Congelar señales de volatilidad táctica 24h antes y 12h después de anuncios FOMC u OpEx.

---

## 2. SHAP Interaction Pairs (Non-Linear Cross-Station Effects)

These pairs produce effects that CANNOT be captured by individual station analysis.
The interaction strength measures the non-linear amplification when both features fire simultaneously.

| Rank | Feature A | Feature B | Interaction | Interpretation |
|:---:|---|---|:---:|---|
| 1 | `tm1_bsi_d2` | `tm1_bsi` | **0.0758** | BSI velocity × BSI level → self-amplification |
| 2 | `tm1_bsi_d1` | `tm1_bsi_d2` | 0.0513 | BSI rank × BSI velocity → quantile-modulated shock |
| 3 | `tm1_vix_d1` | `tm1_bsi` | 0.0394 | VIX level × breadth shock → fear amplification |
| 4 | `tm1_bsi` | `tm2_bsi_d1` | 0.0319 | BSI yesterday × BSI rank 2d ago → temporal cascade |
| 5 | `tm1_bsi` | `tm5_rotation_d3` | 0.0312 | BSI × Rotation vol 5d ago → sector instability |
| 6 | `tm1_skew_d1` | `tm1_bsi_d2` | 0.0296 | SKEW level × BSI velocity → hedging + breadth shock |
| 7 | `tm1_bsi_d1` | `tm2_bsi_d1` | 0.0288 | BSI rank persistence (t-1 vs t-2) |
| 8 | `tm1_vix_d2` | `tm1_bsi` | 0.0242 | VIX velocity × BSI level → panic + breadth |
| 9 | `tm1_yield_curve_d2` | `tm1_bsi_d2` | 0.0233 | Yield velocity × BSI velocity → macro + breadth |
| 10 | `tm1_bsi` | `tm2_bsi_d2` | 0.0201 | BSI self-reinforcement across temporal lags |

> **Confidence Card — Interaction Values**
> | Field | Value |
> |---|---|
> | N | 80 (subset for O(n×f²) computation) |
> | Test Type | SHAP TreeExplainer interaction_values on trained GBM |
> | Metric | Absolute mean interaction strength |
> | CI 95% | Not computed (requires bootstrap on interaction values) |
> | DSR Grade | D (N=80 < 100 minimum for interaction robustness) |
> | Status | `HYPOTHESIS` — requires larger N for promotion |
> | Decay Check | 2026-11-05 |

### Key Structural Finding: D3 as MULTIPLIER

D3 (station volatility ratio `std(2d)/std(10d)`) rarely appears as a standalone
predictor but consistently appears in **interaction pairs**. This means D3 is a
MULTIPLIER — it amplifies the effect of D1/D2 signals from other stations.

From the prior segregated study (AUC 0.938, N=660):
- `credit_d3 × rotation_d2`: 0.133 interaction strength
- `vix_d3 × bsi`: 0.023 interaction strength (confirmed in V2)

---

## 3. Circuit Breaker Registry

Circuit Breakers are extreme market events with validated forward returns.
These operate as **priority overrides** — when active, they supersede normal gate logic.

| Event | Condition | N | WR 1d | WR 3d | WR 5d | Ret 1d | Ret 3d | Ret 5d |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `CB_CREDIT_PANIC` | CREDIT D2 < P2.28 | 111 | **64.9%** | **71.2%** | 65.8% | +0.72% | +1.33% | +1.44% |
| `CB_VVIX_EXTREME` | VVIX > 140 | 63 | 61.9% | 69.8% | **74.6%** | +0.51% | +1.68% | +2.52% |
| `CB_BSI_REVERSAL` | BSI > +3σ | 31 | 61.3% | 64.5% | 67.7% | +0.04% | +0.51% | +0.48% |
| `CB_FEAR_CAPITULATION` | FG < 10 | 135 | 53.3% | 61.5% | 60.7% | -0.06% | +0.24% | +0.38% |
| `CB_SKEW_UNHEDGED` | SKEW < 110 | 331 | 56.2% | 58.9% | 60.4% | +0.29% | +0.42% | +0.62% |
| `CB_YIELD_INVERTED` | YIELD < 0 | 923 | 55.9% | 59.0% | 61.6% | +0.04% | +0.15% | +0.27% |

> **Confidence Card — Circuit Breakers**
> | Field | Value |
> |---|---|
> | N | Variable per event (31 to 923) |
> | Test Type | Historical forward returns (not CV — unconditional) |
> | Metric | Win Rate at 1d, 3d, 5d horizons |
> | CI 95% | Pending (requires binomial CI per event) |
> | DSR Grade | D (unconditional returns, not purged-validated) |
> | Window | Full history (1993-2026 for VIX, 2006+ for VVIX) |
> | Last Validated | 2026-08-05 |
> | Status | `HYPOTHESIS` — requires DSR validation for promotion |
> | Decay Check | 2026-11-05 |

### Operational Hierarchy

```
FASTEST (use at 1-3d horizon):
  1. CB_CREDIT_PANIC   → WR 71.2% at 3d (peak at 3d, fades at 5d)
  2. CB_VVIX_EXTREME   → WR 69.8% at 3d (scales to 74.6% at 5d)

NEEDS TIME (use at 3-5d horizon):
  3. CB_BSI_REVERSAL   → WR 67.7% at 5d (builds steadily)
  4. CB_FEAR_CAPITULATION → WR 61.5% at 3d (USELESS at 1d: 53.3%)

BACKGROUND BIAS (not tactical):
  5. CB_YIELD_INVERTED → WR 61.6% at 5d (regime, not event)
  6. CB_SKEW_UNHEDGED  → WR 60.4% at 5d (weak across all horizons)
```

---

## 4. CREDIT × YIELD Cross-Stratification (Regime Context)

Stratifies ZZ25 bottoms by the macro regime at the time of the turn.

| CREDIT Regime | YIELD Regime | N | WR 5d | Ret 5d | Signal |
|---|---|:---:|:---:|:---:|---|
| EXPANDING (trend > 0) | NORMAL (spread > 0) | 77 | **93.5%** | +3.09% | Standard buy |
| EXPANDING | INVERTED | 10 | 90.0% | +2.01% | Buy with caution |
| CONTRACTING (trend < 0) | NORMAL | 74 | 89.2% | **+3.81%** | Aggressive buy (biggest returns) |
| CONTRACTING | INVERTED | 7 | 100% | +2.75% | N too small |

> **Confidence Card — Regime Cross**
> | Field | Value |
> |---|---|
> | N | 7 to 77 per cell |
> | Test Type | Conditional forward returns on confirmed ZZ25 bottoms |
> | Metric | Win Rate + Mean Return at 5d |
> | CI 95% | Pending |
> | DSR Grade | D (CONTRACTING×INVERTED N=7 is not statistically valid) |
> | Window | Post-hoc confirmed ZZ25 pivots only |
> | Last Validated | 2026-08-05 |
> | Status | `HYPOTHESIS` — all cells require DSR + larger N |
> | Decay Check | 2026-11-05 |

> [!CAUTION]
> These WR values are measured on **confirmed ZZ25 bottoms** (post-hoc).
> By definition, a ZZ25 bottom is followed by a 2.5% rally, so WR is mechanically high.
> The true signal is in the MAGNITUDE difference:
> CONTRACTING + NORMAL → +3.81% (biggest snap-back, stressed market)
> EXPANDING + NORMAL → +3.09% (healthy market, smaller bounce)

---

## 5. SV5_TURBULENCE Bimodal Profile

SV5T does NOT appear in the GBM Top 15 because it operates at the **extremes**,
not in the linear middle. Its signal is bimodal (U-shaped):

| SV5T State | Threshold | ZIG Bias | ZAG Bias | WR 5d (ZIG) | Interpretation |
|---|---|:---:|:---:|:---:|---|
| EXTREME CALM | < 2.30 (P2) | 1.9% | **2.9%** | 100% (N=6) | Silent distribution → TECHO bias |
| LOW | < 3.64 (P16) | 13.1% | 10.9% | **87.8%** | Fragile bottoms — lowest WR |
| NORMAL | P16–P84 | 55.3% | 58.8% | 93.1% | Standard |
| HIGH | > 10.73 (P84) | 12.8% | 10.9% | 89.7% | Institutional capitulation |
| EXTREME HIGH | > 17.30 (P98) | 2.6% | 2.2% | **100%** (N=8) | Guaranteed bottom |

### SV5T D2 Velocity at Structural Turns (ZZ75)

| Scale | ZIG avg D2 | ZAG avg D2 | Interpretation |
|---|:---:|:---:|---|
| ZZ25 | +0.116 | -0.063 | Subtle |
| ZZ50 | +0.412 | -0.066 | Amplified |
| **ZZ75** | +0.220 | **-0.577** | **Institutional stepping out before structural tops** |

> **Confidence Card — SV5T Bimodal**
> | Field | Value |
> |---|---|
> | N | 6-8 per extreme, 173-184 in normal |
> | Test Type | Conditional distribution analysis at ZZ25/50/75 pivots |
> | Metric | Frequency ratio ZIG/ZAG per state + WR 5d |
> | CI 95% | Not computable for extreme bins (N < 30) |
> | DSR Grade | D (extreme bins N < 30) |
> | Window | Full history with SV5T data (1999-2026) |
> | Last Validated | 2026-08-05 |
> | Status | `HYPOTHESIS` — extremes need more data for validation |
> | Decay Check | 2026-11-05 |

> [!WARNING]
> The extreme bins (CALM N=6, EXTREME HIGH N=8) have **insufficient statistical power**
> for Grade C or above. The HYPOTHESIS status means these can inform but NOT veto.
> The pattern is directionally correct but needs more history to confirm.

---

## 6. Production Usage Rules

### What This Model CAN Do (in production)

1. **Emit `P(turning_point)`** — a probability (0-1) that conditions resemble a historical
   turning point. Based on t_-1 to t_-5 signals from yesterday and prior days.
2. **Emit `direction_bias`** — whether the signal pattern matches a bottom (ZIG) or
   top (ZAG) signature, based on segregated SHAP profiles.
3. **Fire Circuit Breaker alerts** — when extreme conditions are met, emit alerts with
   validated WR and time horizon.
4. **Provide regime context** — CREDIT expanding/contracting + YIELD normal/inverted
   as a probabilistic bias layer.

### What This Model CANNOT Do (in production)

1. ❌ **Confirm a ZIG or ZAG** — ZigZag has 5-30 day lag before confirming the
   current leg type. The model emits probability, not confirmation.
2. ❌ **Act as a Hard Gate** — current DSR Grade is B for the unified model, but
   Circuit Breakers and interactions are still HYPOTHESIS (Grade D).
3. ❌ **Override the CIO or department heads** — this is a SERVICE module that informs;
   it never decides capital allocation.

### Decision Flow

```
METAR Observatory → P(turning_point), direction_bias, active CBs
       ↓
EntryGate reads P(tp) as ONE of N inputs
       ↓
EntryGate applies its own gating logic (regime state, sector breadth, etc.)
       ↓
Decision is logged with full StateSnapshot per Rule 17
```
