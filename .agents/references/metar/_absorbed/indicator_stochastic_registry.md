# Indicator Stochastic Registry & METAR (Observación) / SIGMET (Alerta Severa) / Market NOTAM Service

> **Location:** `backend/modules/entry_decision/domain/services/`
> **REST Endpoints:** `/api/metar/*`, `/api/sigmet/active`, `/api/notam/incidents`, `/api/notam/circuit-breaker`
> **Zero Fallback Policy:** Enforces StrictDataPolicyError on missing or unupdated Vault dates.
> **Architecture Reference:** [metar_architecture_and_signals_map.md](file:///root/botero-trade/.agents/references/metar/metar_architecture_and_signals_map.md)

---

## Registered METAR Telemetry Stations (11 Domain Services)

| Indicator / Domain | Ticker | Service File | Primary Metric / Interpretation | Polaridad (`d1_vote`) |
|---|---|---|---|:---:|
| **SV5_TURBULENCE** | `SV5_TURBULENCE` | `sv5_turbulence_metar_service.py` | Institutional Volume Turbulence ($\text{std}(\Delta_{\text{SV5TW}}, 10d)$). Capitulación ($>14.87$) vs Trampa de Serenidad ($<4.85$). | $-1$ (Bearish) |
| **VIX** | `VIX` | `vix_metar_service.py` | CBOE Volatility Index. <20=Calma, 20-28=Elevado, >28=Pánico. | $-1$ (Bearish) |
| **VVIX** | `VVIX` | `vvix_metar_service.py` | Volatility of Volatility Index. >120=Transición de régimen de volatilidad. | $-1$ (Bearish) |
| **FG** | `FG` | `fg_metar_service.py` | CNN Fear & Greed Index (0-100). Sentimiento contrario (<10=Miedo Extremo, >90=Euforia). | Contrarian |
| **CBOE_PCR** | `CBOE_PCR` | `pcr_metar_service.py` | CBOE Equity Put/Call Ratio. Cobertura institucional en derivados. | $-1$ (Bearish) |
| **SKEW** | `SKEW` | `skew_metar_service.py` | CBOE SKEW Index. Riesgo de cola y demanda de puts OTM. | $-1$ (Bearish) |
| **CREDIT** | `CREDIT_RATIO` | `credit_metar_service.py` | High Yield Corporate Credit Stress Ratio (HYG/LQD). Liquidez corporativa. | $+1$ (Bullish) |
| **ROTATION** | `ROTATION_INDEX` | `rotation_metar_service.py` | Sector Breadth & Institutional Rotation across 11 GICS sectors + QQQ. | $+1$ (Risk-On) |
| **YIELD_CURVE** | `YIELD_SPREAD` | `yield_curve_metar_service.py` | Macro Yield Curve Spread (TNX - IRX). Ciclo económico y recesión. | $+1$ (Expansión) |
| **BSI** | `S5TW` | `bsi_metar_service.py` | Breadth Shock Index (% SP500 sobre 20-DMA). Impulso y capitulación táctica. | $+1$ (Bullish) |
| **DXY** | `DXY` | `dxy_metar_service.py` | US Dollar Index. Condiciones globales de liquidez y estrés cambiario. | $-1$ (Bearish p/EQ) |

---

## Architecture & Integration Boundaries

- **Data Source**: Exclusive read from Neon Vault (`market.ohlcv_bars`).
- **Domain Adaptation**: Each service queries a pure domain Fact Store Lookup (`*_lookup.py`) with numeric state keys (`d1__d2__d3`).
- **Compositor**: `convergence_compositor.py` generates multi-station synthesis and dimensional telemetry.
- **Hazards & Disruptions**: `market_sigmet_hazard_service.py` issues severe weather bulletins (SIGMET) and `notam_incident_service.py` monitors operational anomalies (NOTAM).
