# Arquitectura de Inteligencia de Mercado — Botero Trade Engine

Este documento contiene la representación arquitectónica completa del **Sistema de Inteligencia de Mercado** (Market Intelligence System) en Botero Trade, estructurado bajo **Clean & Hexagonal Architecture** y las normas de acceso **Vault-First** (Reglas 13, 14, 18).

---

## 1. Diagrama de Fuentes de Información que Alimentan a los Gates (Data Sources Pipeline)

```mermaid
graph TD
    subgraph "PROVEEDORES Y SERVIDORES MCP (9 Fuentes de Información Activas)"
        MCP_FINVIZ["1. Finviz Elite (35 Tools)<br/>- Amplitud Sectorial & Screening<br/>- Presentaciones SEC & Filings"]
        MCP_GURU["2. GuruFocus Premium (55 Tools)<br/>- Beneish M-Score, Altman Z, Piotroski<br/>- Intrinsic GF Value & Insider Clusters<br/>- Politician & Guru Transactions"]
        MCP_FRED["3. FRED Macro Data & Currency (12 Tools)<br/>- Balance Fed (WALCL), Reverse Repo (RRP), TGA<br/>- Rendimientos Tesoro (DGS10, DGS2, DGS3MO)<br/>- Spreads de Curva (T10Y2Y, T10Y3M) & DXY / UUP"]
        MCP_FINNHUB["4. Finnhub (45 Tools)<br/>- Calendario de Earnings & Sorpresas EPS<br/>- Transacciones Insiders Redundante"]
        MCP_UW["5. Unusual Whales (20+ Tools)<br/>- Barridas de Opciones (Option Sweeps)<br/>- Flujo Darkpool, Spot GEX, Market Tide<br/>- Short Interest & Float Shorted"]
        MCP_YAHOO["6. Yahoo Finance (9 Tools)<br/>- VIX, VVIX, SKEW Index<br/>- CBOE Put/Call Ratio (CBOE_PCR_5M)"]
        MCP_NEWS["7. FinBERT Sentiment (4 Tools)<br/>- Puntuación FinBERT NLP<br/>- Velocidad de Sentimiento (Delta/Delta t)"]
        MCP_ALPACA["8. Alpaca Broker (61 Tools)<br/>- Precios Históricos & Ejecución Papel"]
        MCP_FED_CAL["9. Fed & FOMC Macro Calendar (macro_calendar.py)<br/>- 8 Reuniones Oficiales FOMC 2026 (SEP + Dot Plot)<br/>- Lanzamientos CPI, PCE, NFP & Discursos Fed<br/>- Regla de Bloqueo Pre-FOMC (Blackout Window)"]
    end

    subgraph "MECANISMO DE ENTREGA Y BÓVEDA DE DATOS (Delivery Mechanism & Vault Persistence)"
        DAEMON["Data Vault Daemon & Providers<br/>(backend/daemons/data_vault_daemon.py)<br/>- Escanea APIs externas e inyecta a la Bóveda"]
        OHLCV["market.ohlcv_bars<br/>(Precios, Amplitud S5/SV5, Indicadores)"]
        SNAPS["market.mcp_snapshots<br/>(Snapshots MCP: macro/fred, macro/calendar, flow/sweeps)"]
        STATES["market.regime_states<br/>(Estados Persistidos via RegimeStatePort)"]
    end

    subgraph "MOTOR DE SÍNTESIS Y DTOs (Domain Synthesis & NOTAM Protocol)"
        CIE["Causal Investigation Engine<br/>(Druckenmiller 5-Vector Causal Matrix)"]
        TTC["Temporal Trajectory Cascade<br/>(1M -> 1W -> 1D -> 1H -> 5M)"]
        DTO["NOTAMTickerPayload DTO<br/>- decision, quality_sizing, spec_sizing<br/>- certainty_score (Quality/Swing/Spec)<br/>- net_liquidity_trend, kalman_vel, slope"]
    end

    subgraph "GATES CONSUMIDORES & ASIGNACIÓN DE CAPITAL (Application Layer)"
        QCG["Quality Core Gate (Hohn / Munger)<br/>- Exige Beneish < -1.78, Stage 1/2, GF Value"]
        QSG["Quality Swing Gate (Druckenmiller)<br/>- Exige Skew, Div SV5-S5, Dip Regresión<br/>- Respeta FOMC Blackout Window"]
        SEH["Speculative Hub (PTJ / Seykota)<br/>- Exige 5M PCR Capitulación, Sweeps >= 10<br/>- Respeta FOMC Blackout Window"]
        SRG["Sector Rotation Gate (Weinstein / Pring)<br/>- 10 Regímenes Homologados, Regla Cap-Weight"]
    end

    MCP_FINVIZ & MCP_GURU & MCP_FRED & MCP_FINNHUB & MCP_UW & MCP_YAHOO & MCP_NEWS & MCP_ALPACA & MCP_FED_CAL --> DAEMON
    DAEMON -->|Escribe exclusivamente| OHLCV & SNAPS & STATES
    OHLCV & SNAPS & STATES -->|Lee exclusivamente| CIE & TTC
    CIE & TTC --> DTO
    DTO -->|Transmisión Numérica Zero-Parsing| QCG & QSG & SEH & SRG
```

---

## 2. Diagrama de Arquitectura de Capas de Inteligencia de Mercado

```mermaid
graph TD
    subgraph "CAPA 0: BÓVEDA DE DATOS (Vault-First Infrastructure Layer)"
        TSDS["Neon PostgreSQL TimescaleDataStore<br/>(market.ohlcv_bars: 5.96M Barras, 1927-2026)"]
        MCPS["Snapshot Vault Storage<br/>(market.mcp_snapshots: macro/fred, macro/calendar, flow/sweeps)"]
        RST["Regime State Persistence<br/>(market.regime_states via RegimeStatePort)"]
    end

    subgraph "CAPA 1: SERVICIOS TRANSVERSALES DE INTELIGENCIA DE MERCADO"
        MHI["Market Health Intelligence Service<br/>(Convergencia 6D: Breadth, Volatility, Flow, Credit, Rotation, Macro)"]
        VRI["Vol Regime Intelligence Service<br/>(Máquina de Estados de Volatilidad & Mandelbrot Clustering)"]
        FRED["FRED Macro Intelligence Adapter<br/>(Net Liquidity = WALCL - RRP - TGA, Yield Spread T10Y2Y / T10Y3M)"]
        CAL_SRV["Macro Event Calendar Service (macro_calendar.py)<br/>(FOMC 2026 8 Reuniones, Blackout Window, Discursos Fed)"]
    end

    subgraph "CAPA 2: MOTOR CAUSAL NOTAM & INVESTIGACIÓN (Domain Layer)"
        CIE_ENGINE["Causal Investigation Engine<br/>(Matriz Causal de 5 Vectores de Druckenmiller)"]
        TTC_CASCADE["Temporal Trajectory Cascade (5 Horizontes)<br/>1M (Secular) -> 1W (Estructural) -> 1D (Táctico) -> 1H (Inercia) -> 5M (Micro)"]
        CER_ENGINE["Certainty & Credibility Scoring Engine<br/>(Overall, Quality 100%, Swing 100%, Speculative -30% Penalty if 5M Missing)"]
        PAY_GEN["NOTAMTickerPayload Generator<br/>(Incorpora Vectores de Tendencia & Velocidad: net_liquidity_trend, kalman_vel)"]
    end

    subgraph "CAPA 3: MOTOR DE ROTACIÓN SECTORIAL (10 Regímenes Validados 27.5 Años)"
        SRG_GATE["Sector Rotation Gate (V35 Production Baseline)<br/>10 Regímenes Homologados (SEC_HEALTHY_BULL ... SEC_SYSTEMIC_CRASH)<br/>Divergencia SV5-S5 + Protección Core Cap-Weight (>= 8%)"]
    end

    subgraph "CAPA 4: GATES CONSUMIDORES & ASIGNACIÓN DE CAPITAL (Application Layer)"
        QCG_GATE["Quality Core Gate (Hohn / Munger Mode)"]
        QSG_GATE["Quality Swing Gate (Druckenmiller Mode)"]
        SEH_HUB["Speculative Entry Hub (PTJ / Seykota Mode)"]
        CIO_ALLOC["CIO Allocator (Dalio Economic Machine Mode)"]
    end

    TSDS & MCPS & RST --> MHI & VRI & FRED & CAL_SRV
    TSDS & MCPS & RST --> CIE_ENGINE
    FRED & CAL_SRV --> CIE_ENGINE
    CIE_ENGINE --> TTC_CASCADE & CER_ENGINE --> PAY_GEN
    MHI & VRI & PAY_GEN --> SRG_GATE
    SRG_GATE & PAY_GEN & MHI & CAL_SRV --> QCG_GATE & QSG_GATE & SEH_HUB & CIO_ALLOC
    QCG_GATE & QSG_GATE & SEH_HUB & CIO_ALLOC -->|Persiste Transición| RST
```

---

## 3. Matriz de Fuentes de Información por Departamento / Gate

| Gate Consumidor | Fuentes Principales que lo Alimentan | Indicadores Específicos Extraídos | Criterios de Aceptación / Veto |
|---|---|---|---|
| **Quality Core Gate** *(Hohn / Munger)* | Finviz, GuruFocus, FRED | Beneish M-Score, Altman Z, Piotroski, $10Y-2Y$ Spread, GF Value Intrínsico. | Beneish $< -1.78$, Z-Score $> 1.81$, Stage 1/2, Descuento $>15\%$. |
| **Quality Swing Gate** *(Druckenmiller)* | Unusual Whales, Yahoo Finance, Finviz, **Macro Calendar** | Risk Reversal Skew, Divergencia $SV5_{TW} - S5_{FI}$, Fear & Greed, **FOMC Blackout Window**. | Regresión a Soporte ($\sigma \le -1.5$), Skew $< -5.0\%$, FG $\le 20$, **Sin ventana FOMC activa**. |
| **Speculative Hub** *(PTJ / Seykota)* | Unusual Whales, Yahoo Finance, Finnhub, **Macro Calendar** | $CBOE\_PCR_{5M}$, Barridas $1H$ (Option Sweeps $\ge 10$), Short Interest $\ge 15\%$, **FOMC Blackout Window**. | Capitulación 5M ($PCR \ge 1.40$), Sweeps $\ge 10$, Stop ATR $1.5\times$, **Sin ventana FOMC activa**. |
| **Sector Rotation Gate** *(Weinstein / Pring)* | Finviz, Yahoo Finance, Bóveda OHLCV | Amplitud $S5_{TH}, S5_{FI}, S5_{TW}$, Amplitud de Volumen $SV5_{TH}, SV5_{FI}, SV5_{TW}$. | Clasificación en uno de los 10 Regímenes (`SEC_HEALTHY_BULL` ... `SEC_CRASH`). |

---

## 4. Garantía de Arquitectura Clean: Norma Vault-First

De acuerdo con las **Reglas 13 y 14 de AGENTS.md**:
1. Los módulos de producción (`backend/modules/`) **NUNCA realizan llamadas directas a APIs externas** ni a servidores MCP.
2. Los **Data Vault Daemons** alimentan la Bóveda en segundo plano.
3. Los **Gates leen exclusivamente de la Bóveda** (`market.ohlcv_bars` y `market.mcp_snapshots`), garantizando rendimiento institucional, latencia mínima y cero fallos por límites de API en tiempo de ejecución.

---

## 5. Contratos de Entradas y Salidas Detalladas por Módulo (Module Input/Output Data Contracts)

```mermaid
graph LR
    subgraph "FLOW DE ENTRADAS Y SALIDAS ENTRE MÓDULOS DE PRODUCCIÓN"
        VAULT["BÓVEDA NEON POSTGRESQL<br/>(market.ohlcv_bars, market.mcp_snapshots)"] --> PM["1. portfolio_management"]
        VAULT --> CI["2. causal_investigation"]
        VAULT --> OG["3. options_gamma"]
        VAULT --> FI["4. flow_intelligence"]
        
        PM -->|QualityWatchlist DTO| ED["5. entry_decision"]
        CI -->|NOTAMTickerPayload DTO| ED
        OG -->|SpotGEXSnapshot / OptionsAnalysis| ED
        FI -->|WhaleFlowSignal / FlowPersistenceReport| ED
        
        ED -->|EntryIntelligenceReport DTO| EXEC["6. execution & simulation"]
        ED -->|MarketHealth / Regímenes| CIO["7. cio_allocator"]
        EXEC -->|StateSnapshot| RST_DB["market.regime_states"]
    end
```

### 1. Módulo: `portfolio_management` (Quality Core Watchlist & Universe Filter)
- **Entradas (Inputs)**:
  - **Bóveda OHLCV (`market.ohlcv_bars`)**: Tickers, precios diarios, volúmenes de 531 activos.
  - **Snapshots MCP (`market.mcp_snapshots`)**: 
    - `fundamental/screening`: Beneish M-Score, Altman Z-Score, Piotroski F-Score.
    - `fundamental/estimates`: Intrinsic GF Value, Descuento %, Ratios de Deuda.
    - `macro/fred`: DXY Index, Spreads de Curva ($T10Y2Y$, $T10Y3M$).
- **Salidas (Outputs)**:
  - `QualityWatchlist`: Lista de candidatas A-Grade aprobadas que pasan los filtros de Munger/Hohn.
  - DTO de Calidad: `QualityScore` (0.0 a 100.0), `BeneishVerdict` (manipulación contable), `DiscountPct` (margen de seguridad).

---

### 2. Módulo: `causal_investigation` (Engine de Causalidad Druckenmiller 5-Vectores & NOTAM)
- **Entradas (Inputs)**:
  - **Vector 1 (Flow)**: `flow/alerts` (Option Sweeps $\ge 10$), `flow/darkpool`, `flow/tide`.
  - **Vector 2 (Macro)**: `macro/fred` (Liquidez Neta $\text{WALCL}-\text{RRP}-\text{TGA}$, $HY\_OAS$ High Yield Spread, DXY Index).
  - **Vector 3 (Corporate)**: `sourcing/insider` (Insiders Comprando), `sourcing/guru_picks`.
  - **Vector 4 (Volume & Sentiment)**: Amplitud $S5_{FI}, SV5_{TW}$, `macro/vix_live`, `macro/fear_greed`, `cboe/indices` ($PCR_{5M}$, SKEW, VVIX).
  - **Vector 5 (Narrative)**: `finnhub/news` (Score FinBERT & Velocidad de Noticias).
- **Salidas (Outputs)**:
  - `NOTAMTickerPayload` DTO:
    - `decision`: `"ALLOW"`, `"BLOCK"`, `"REDUCE"`.
    - `causal_score`: Puntaje compuesto ponderado (0.00 a 1.00).
    - `quality_sizing`, `spec_sizing`: Sizing factor derivado de convicción.
    - `certainty_score`: Matriz de certeza (Overall, Quality, Swing, Speculative).
    - `net_liquidity_trend`, `kalman_vel`, `slope`: Indicadores de tendencia macro y aceleración de volumen.

---

### 3. Módulo: `options_gamma` (UW Gamma Adapter & Options Awareness)
- **Entradas (Inputs)**:
  - **Snapshots MCP (`market.mcp_snapshots`)**: 
    - `uw/spot_gex`: Dealer Net Gamma (`gamma_per_pct_oi`), Net Charm, Net Vanna por 1% move.
    - `uw/greeks`: Call/Put Delta, Gamma, Theta, Vega, Rho por Strike.
    - `uw/max_pain`: Precio Max Pain y distancia %.
    - `uw/oi_per_strike`: Interés Abierto por strike (Calls y Puts).
    - `uw/iv_term_structure`: Curva de volatilidad implícita (0DTE vs Front vs Back DTE).
    - `uw/vol_stats`: IV Rank, Variance Risk Premium (IV - RV).
- **Salidas (Outputs)**:
  - `SpotGEXSnapshot`: Net Gamma (`gamma_per_pct_oi`), Net Charm, Net Vanna.
  - `IVTermStructure`: `is_backwardation` (pánico 0DTE), `ultra_front_iv`, `term_spread`.
  - `VolStats`: `iv_rank`, `variance_risk_premium`.
  - `OptionsAnalysis`: `put_wall` & `put_wall_oi`, `call_wall` & `call_wall_oi`, `max_pain`, `gravity_score`, `pin_range`.

---

### 4. Módulo: `flow_intelligence` (Whale Flow & Persistence Analyzer)
- **Entradas (Inputs)**:
  - **Snapshots MCP (`market.mcp_snapshots`)**: 
    - `flow/spy`: SPY Cumulative Delta.
    - `flow/tide`: Market Tide directional net premium.
    - `flow/alerts`: Sweeps individuales por ticker.
    - `flow/darkpool`: Impresiones institucionales fuera de mercado.
    - `uw/short_interest`: Days to Cover (DTC) y Short Interest Float %.
- **Salidas (Outputs)**:
  - `WhaleFlowSignal`: `spy_cum_delta`, `spy_signal`, `tide_direction`, `tide_accelerating`, `sweep_call_pct`.
  - `FlowPersistenceReport`: `persistence_grade` (`"HIGH"`, `"MEDIUM"`, `"DEAD_SIGNAL"`), `freshness_weight`, `consecutive_days`, `darkpool_aligned`.

---

### 5. Módulo: `entry_decision` (Quality Entry Gate, Speculative Hub, Sector Rotation Gate)
- **Entradas (Inputs)**:
  - **Precios & ATR**: `market.ohlcv_bars` (Precios históricos, ATR 14d, RVOL, RS vs SPY).
  - **NOTAM Payload**: `causal_investigation` (`NOTAMTickerPayload`).
  - **Options Gamma**: `options_gamma` (`put_wall`, `put_wall_oi`, `call_wall`, `call_wall_oi`, `spot_gex`, `max_pain`, `vanna_event`, `charm_direction`).
  - **Flow Intelligence**: `flow_intelligence` (`FlowPersistenceReport`, `WhaleFlowSignal`).
  - **Market Health**: `MarketHealthSnapshot` (`market/health`).
  - **Calendario Macro**: `macro_calendar.py` (FOMC Blackout Window, CPI, NFP).
  - **Patrón & Estructura**: Pattern Recognition & SMC Market Structure.
- **Salidas (Outputs)**:
  - `EntryIntelligenceReport` DTO:
    - `final_verdict`: `"EXECUTE"`, `"STALK"`, `"PASS"`, `"BLOCK"`.
    - `final_scale`: Factor de tamaño final (0.00 a 1.50).
    - `entry_price`, `stop_price`, `target_price`, `risk_reward`.
    - `spot_gex`, `put_wall_oi`, `call_wall_oi`.
    - `alerts`: Lista explicativa determinista de la decisión.

---

### 6. Módulo: `cio_allocator` (CIO Capital Allocation Engine - Dalio Mode)
- **Entradas (Inputs)**:
  - **Convergencia Market Health 6D**: Amplitud, Volatilidad, Flujo, Crédito, Rotación, Ciclo Macro.
  - **Matriz 3-Regímenes DXY**: Level $DXY$ + Trend 1Y ROC ($DXY < 90$, $92 \le DXY \le 100$, $DXY > 100$).
  - **Spread Crédito High-Yield**: $HY\_OAS$ (`BAMLH0A0HYM2`).
  - **Retornos Relativos Bóveda**: SPY, QQQ, EEM, EWZ, GLD, TLT.
- **Salidas (Outputs)**:
  - `CapitalAllocationPlan`:
    - Distribución Quality Core vs Quality Swing vs Speculative.
    - Distribución EE.UU. Equity vs Emergentes / LatAm vs Metales Preciosos (Oro).
    - Regla Anti-Cash Drag (Piso de Inversión en Bull Markets).

---

### 7. Módulo: `execution` & `simulation` (Paper Trading, Backtrader & Journaling)
- **Entradas (Inputs)**:
  - `EntryIntelligenceReport` DTO emitido por `entry_decision`.
  - Parámetros de Sizing & Stop Loss del departamento (Druckenmiller para Quality / Seykota para Speculative).
- **Salidas (Outputs)**:
  - `Order` & `Position`: Órdenes enviadas a broker (Alpaca) o motor de backtesting (Backtrader).
  - `TradeRecord`: Registro persistido de la transacción.
  - `StateSnapshot`: Estado de régimen persistido en `market.regime_states` via `RegimeStatePort`.
