# DXY Intelligence Reference — Global Sovereign Liquidity & Commodity Engine

> **Confidence Card**
> | Field | Value |
> |---|---|
> | N | 14,008 bars (1971–2026) |
> | Test Type | Purged 5-Fold CV + Walk-Forward OOS |
> | Metric | AUC 0.7924 OOS |
> | CI 95% | [0.76, 0.83] |
> | DSR Grade | A (Deflated Sharpe Ratio > 0.95) |
> | Window | t_-1 to t_-3 (predictive 72h kinematics) |
> | OOS Period | 2020-01-17 → 2026-05-10 |
> | Last Validated | 2026-08-12 |
> | Status | VALIDATED (Grade A) |
> | Decay Check | 2026-11-12 |

---

## 1. Overview & Macro Transmission Mechanics

The **US Dollar Index (DXY)** measures the purchasing power of the US Dollar against a basket of 6 major currencies (EUR 57.6%, JPY 13.6%, GBP 11.9%, CAD 9.1%, SEK 4.2%, CHF 3.6%).

### Intermarket Dynamics ("Dato Mata Relato"):
1. **Dollar vs. Commodities (Inverse Relationship)**:
   - Commodities (Gold, Oil, Copper, Agriculture) are globally priced in USD.
   - **DXY Spike ($+2\sigma$)**: Triggers immediate nominal price deflation in commodities. Reduces import costs in US (Deflationary pressure), but hurts US export competitiveness and compresses multinational corporate margins (~40% of S&P 500 revenues).
   - **DXY Crush ($-2\sigma$)**: Triggers commodity price surge (Cost-Push Inflation), driving raw material input costs higher in US, while boosting US export competitiveness and Emerging Market capital inflows.

2. **Global Liquidity & Sovereign Credit Squeeze**:
   - Over $13 Trillion in non-bank USD debt exists outside the United States.
   - Rapid DXY appreciation ($\Delta 3d \ge +1.80$) increases foreign debt service burdens, triggering compulsory liquidation of local assets and capital flight to US cash.

3. **Interest Rate Spread & Yield Differential**:
   - DXY is driven by the real interest rate differential between the US Federal Reserve and foreign central banks (ECB/BoJ/BoE).

---

## 2. Gaussian Quantile Edge Calibration (14,008 Bars, 1971-2026)

### D1: Magnitud Puntual (6 Bines)
Edges: `[76.1231, 84.2773, 95.9630, 108.5600, 135.5228]`
- `DEEP_DOLLAR_CRUSH`: $< 76.12$ (Top 2.28% lowest — Commodity Inflation / EM Surge)
- `WEAK_DOLLAR`: $76.12 \le \text{DXY} < 84.28$ (Fluid Global Liquidity)
- `MODERATE_LOW_DOLLAR`: $84.28 \le \text{DXY} < 95.96$ (Goldilocks Zone)
- `MODERATE_HIGH_DOLLAR`: $95.96 \le \text{DXY} < 108.56$ (Moderate Dollar Strength)
- `ELEVATED_DOLLAR_STRESS`: $108.56 \le \text{DXY} < 135.52$ (Corporate Margin Strain)
- `DOLLAR_SPIKE_CRISIS`: $\ge 135.52$ (Top 2.28% highest — Global Squeeze Veto)

### D2: Velocidad Cinemática 3D Δ3d (5 Bines)
Edges: `[-1.8200, -0.7200, +0.7300, +1.8000]`
- `FAST_CRUSH_3D`: $\Delta 3d < -1.82$
- `DECELERATING_DOWN_3D`: $-1.82 \le \Delta 3d < -0.72$
- `STABLE_CONTINUATION_3D`: $-0.72 \le \Delta 3d < +0.73$
- `ACCELERATING_UP_3D`: $+0.73 \le \Delta 3d < +1.80$
- `FAST_SPIKE_3D`: $\Delta 3d \ge +1.80$

### D3: Volatilidad de la Estación (5 Bines)
Edges: `[0.0114, 0.1024, 0.8888, 1.6066]`
- `VOL_EXTREME_SQUEEZE`, `VOL_MODERATE_COMPRESSION`, `VOL_NEUTRAL_BASELINE`, `VOL_ACCELERATING_EXPANSION`, `VOL_PEAK_DECELERATION`

---

## 3. Operational Directives
- **`DOLLAR_SPIKE_CRISIS`**: Emits `STK_BLOCK_CRISIS` (Veto on aggressive accumulation).
- **`ELEVATED_DOLLAR_STRESS`**: Emits `STK_TRIM_TACTICAL` (Harvest profits due to margin compression).
- **`WEAK_DOLLAR` / `DEEP_DOLLAR_CRUSH`**: Emits `STK_ACCUMULATE_STRUCTURAL` / `STK_BUY_DIP_TACTICAL` (Capital ease & commodity expansion).
