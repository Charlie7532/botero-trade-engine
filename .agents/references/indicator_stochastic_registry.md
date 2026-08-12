# Indicator Stochastic Registry & METAR (Observación) / SIGMET (Alerta Severa) / Market NOTAM Service

> **Location:** `backend/modules/entry_decision/domain/services/`
> **REST Endpoint:** `/api/notam/incidents` & `/api/notam/circuit-breaker`
> **Zero Fallback Policy:** Enforces StrictDataPolicyError on missing or unupdated Vault dates.

---

## Registered METAR Telemetry Stations (10 Domain Services)

| Indicator / Domain | Ticker | Service File | Primary Metric / Interpretation |
|---|---|---|---|
| **SV5_TURBULENCE** | `SV5_TURBULENCE` | `sv5_turbulence_metar_service.py` | Institutional Volume Turbulence ($\text{std}(\Delta_{\text{SV5TW}}, 10d)$). Capitulación ($>14.87$) vs Trampa de Serenidad ($<4.85$). |
| **VIX** | `VIX` | `vix_metar_service.py` | CBOE Volatility Index. <20=Calma, 20-28=Elevado, >28=Pánico. |
| **VVIX** | `VVIX` | `vvix_metar_service.py` | Volatility of Volatility Index. >120=Transición de régimen de volatilidad. |
| **FG** | `FG` | `fg_metar_service.py` | CNN Fear & Greed Index (0-100). Sentimiento contrario (<10=Miedo Extremo 76% WR, >90=Euforia). |
| **CBOE_PCR** | `CBOE_PCR` | `pcr_metar_service.py` | CBOE Equity Put/Call Ratio. Medida de cobertura en mercado de opciones. |
| **SKEW** | `SKEW` | `skew_metar_service.py` | CBOE SKEW Index. Riesgo de cola y demanda de Puts OTM. |
| **CREDIT** | `HYG/LQD` | `credit_metar_service.py` | High Yield Corporate Credit Stress Ratio. Liquidez corporativa sin ruido de tipos. |
| **ROTATION** | `S5_*` / `SV5_*` | `rotation_metar_service.py` | Sector Breadth & Institutional Rotation across 11 GICS sectors + QQQ. |
| **YIELD_CURVE** | `YIELD_SPREAD` | `yield_curve_metar_service.py` | Macro Yield Curve Spread (TNX - IRX). Ciclo de crédito y recesión. |
| **BSI** | `S5TW` | `bsi_metar_service.py` | Breadth Shock Index (% de acciones S&P 500 sobre 20-DMA). Impulso y capitulación táctica. |

---

## Architecture & Integration Boundaries

- **Data Source**: Exclusive read from Neon Vault (`market.ohlcv_bars`).
- **Domain Adaptation**: Each service queries a pure domain Fact Store Lookup (`*_lookup.py`).
- **Orchestration**: `notam_incident_service.py` aggregates active NOTAM bulletins for the CIO Allocator, Quality Entry Gate, and Speculative Entry Hub.
