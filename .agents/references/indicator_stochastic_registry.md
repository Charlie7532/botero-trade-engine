# Indicator Stochastic Registry & SIGMET / Market NOTAM Service

> **Location:** `backend/modules/entry_decision/domain/services/`
> **REST Endpoint:** `/api/notam/incidents` & `/api/notam/circuit-breaker`
> **Zero Fallback Policy:** Enforces StrictDataPolicyError on missing or unupdated Vault dates.

---

## Registered SIGMET / NOTAM Indicators (9 Domain Services)

| Indicator / Domain | Ticker | Service File | Primary Metric / Interpretation |
|---|---|---|---|
| **SV5_TURBULENCE** | `SV5_TURBULENCE` | `sv5_turbulence_sigmet_service.py` | Institutional Volume Turbulence ($\text{std}(\Delta_{\text{SV5TW}}, 10d)$). Capitulación ($>14.87$) vs Trampa de Serenidad ($<4.85$). |
| **VIX** | `VIX` | `vix_sigmet_service.py` | CBOE Volatility Index. <20=Calma, 20-28=Elevado, >28=Pánico. |
| **VVIX** | `VVIX` | `vvix_sigmet_service.py` | Volatility of Volatility Index. >120=Transición de régimen de volatilidad. |
| **FG** | `FG` | `fg_sigmet_service.py` | CNN Fear & Greed Index (0-100). Sentimiento contrario (<10=Miedo Extremo 76% WR, >90=Euforia). |
| **CBOE_PCR** | `CBOE_PCR` | `pcr_sigmet_service.py` | CBOE Equity Put/Call Ratio. Medida de cobertura en mercado de opciones. |
| **SKEW** | `SKEW` | `skew_sigmet_service.py` | CBOE SKEW Index. Riesgo de cola y demanda de Puts OTM. |
| **CREDIT** | `HYG/LQD` / FRED | `credit_sigmet_service.py` | Corporate Credit Spreads. Estrés en liquidez corporativa. |
| **ROTATION** | `S5_*` / `SV5_*` | `rotation_sigmet_service.py` | Sector Breadth & Institutional Rotation across 11 GICS sectors + QQQ. |
| **YIELD_CURVE** | `T10Y2Y` / `TNX` | `yield_curve_sigmet_service.py` | Macro Yield Curve Spread (10Y-2Y). Ciclo de crédito y recesión. |

---

## Architecture & Integration Boundaries

- **Data Source**: Exclusive read from Neon Vault (`market.ohlcv_bars`).
- **Domain Adaptation**: Each service queries a pure domain Fact Store Lookup (`*_lookup.py`).
- **Orchestration**: `notam_incident_service.py` aggregates active NOTAM bulletins for the CIO Allocator, Quality Entry Gate, and Speculative Entry Hub.
