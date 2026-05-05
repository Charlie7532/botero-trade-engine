# Botero Trade Engine — Arquitectura Institucional v14

> Última actualización: 2026-05-01 | Versión V14 (Dual-Mandate Architecture)
> Verificado con Graphify: 2821 nodos, 6074 edges, 187 comunidades, 524 archivos

> [!NOTE]
> Skills y perfiles de expertos documentados en `AGENTS.md` / `GEMINI.md`.
> Detalle interno de módulos en [`architecture-modules-internal.md`](./architecture-modules-internal.md).
> Expert Committee en [`architecture-expert-committee.md`](./architecture-expert-committee.md).

---

## 1. Dual-Mandate — Separación QUALITY / SPECULATIVE

```mermaid
graph TB
    subgraph CIO["🏛️ CIO (Dalio) — Budget Allocation Only"]
        MANDATE["DailyMandate<br/>80% QUALITY / 20% SPECULATIVE<br/>Regime-aware rebalancing"]
    end

    subgraph QUALITY["QUALITY Department (Hohn + Munger + Druckenmiller)"]
        QR["QualityResearchPipeline<br/>📊 Fundamental only<br/>QGARP · FCF · Piotroski · Insider"]
        QQ["QualityQualifier<br/>📐 Daily WF · Grade A required<br/>Payoff 2.0-3.0x"]
        QE["QualityEntryGate<br/>🚪 VP Distrib block · RSI hostile<br/>CONTRA_FLOW = BLOCK"]
        QO["QualityOrchestrator<br/>⏰ Daily cadence<br/>→ SurveillanceLoop (moat decay)"]
    end

    subgraph SPECULATIVE["SPECULATIVE Department (Karsan + Eifert + PTJ + Seykota)"]
        SS["SpeculativeScanner<br/>⚡ Microstructure only<br/>Gamma · Flow · DarkPool · RVOL"]
        SQ["SpeculativeQualifier<br/>📐 Hourly WF · Grade B sufficient<br/>Payoff 1.5-2.5x"]
        SE["SpeculativeEntryHub<br/>🎯 Memory Guard · Flow Persistence<br/>PTJ ≥3:1 Asymmetry Gate"]
        SO["SpeculativeOrchestrator<br/>⏰ 15min cadence<br/>→ SpeculativeSurveillance (stops)"]
    end

    MANDATE -->|"80% budget"| QR
    MANDATE -->|"20% budget"| SS
    QR --> QQ --> QE --> QO
    SS --> SQ --> SE --> SO
```

---

## 2. System Overview

```mermaid
graph TB
    subgraph EXT["🌐 MCP Servers (8 activos · ~241 tools)"]
        UW["🐋 Unusual Whales<br/>Flow · Tide · DarkPool"]
        GF["📈 GuruFocus<br/>QGARP · Insider · Gurus"]
        FV["📊 Finviz<br/>Screening · Sectores"]
        FH["📅 Finnhub<br/>Earnings · SEC"]
        FR["🏛️ FRED<br/>GDP · CPI · Yield"]
        ALP["🦙 Alpaca ×2<br/>QUALITY + SPEC accounts"]
        YF["📉 Yahoo Finance<br/>VIX · Options"]
        NS["📰 News Sentiment<br/>FinBERT"]
    end

    subgraph MODULES["🧩 Backend Modules (12 · Clean Architecture)"]
        PM["portfolio_management<br/>QualityResearchPipeline<br/>SpeculativeScanner<br/>CIOOrchestrator<br/>Qualifiers ×2"]
        ED["entry_decision<br/>QualityEntryGate<br/>SpeculativeEntryHub"]
        EX["execution<br/>QualityOrchestrator<br/>SpeculativeOrchestrator<br/>SmartEntryEngine<br/>Surveillance ×2"]
        FI["flow_intelligence<br/>WhaleFlow · Persistence<br/>EventCalendar"]
        OG["options_gamma<br/>GEX · MaxPain<br/>Gamma Regime"]
        PA["price_analysis<br/>PricePhase · RSI"]
        VI["volume_intelligence<br/>Kalman · VP"]
        PR["pattern_recognition<br/>Candlestick · VCP"]
        RI["rotation_intelligence<br/>Weinstein · Pring"]
        SIM["simulation<br/>WalkForward · Features<br/>TripleBarrier · LSTM"]
        SH["shared<br/>Entities · Cache"]
    end

    subgraph API["🔗 FastAPI (port 8000)"]
        FAST["main.py + routers (5)<br/>factories/ (Composition Root)"]
    end

    subgraph FE["🖥️ Next.js 16 + PayloadCMS 3 (port 3000)"]
        UI["Dashboard + Admin<br/>12 Collections"]
    end

    subgraph STORE["🗄️ PostgreSQL"]
        PG["Neon + TimescaleDB + pgvector"]
    end

    EXT --> MODULES
    FE -->|"HTTP"| API --> MODULES
    MODULES --> STORE
```

---

## 3. Hexagonal Architecture — Dependency Rule

```
┌─────────────────────────────────────────────────┐
│  API Layer (routers, factories)                  │
│  ┌───────────────────────────────────────────┐  │
│  │  Infrastructure (adapters, SDKs, PG)       │  │
│  │  ┌─────────────────────────────────────┐  │  │
│  │  │  Application (use_cases, dtos)       │  │  │
│  │  │  ┌───────────────────────────────┐  │  │  │
│  │  │  │  Domain (entities, ports, rules)│  │  │  │
│  │  │  │  • ZERO SDK imports            │  │  │  │
│  │  │  │  • ZERO infrastructure imports │  │  │  │
│  │  │  │  • Dependencies via Ports (ABC)│  │  │  │
│  │  │  └───────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

---

## 4. Composition Root

```mermaid
flowchart TD
    FAC["execution_factory.py<br/>🏭 Composition Root"]

    FAC --> BR["build_broker_registry()<br/>{QUALITY: Alpaca①, SPECULATIVE: Alpaca②}"]
    FAC --> JR["build_journal_registry()<br/>{QUALITY: PG①, SPECULATIVE: PG②}"]
    FAC --> BL["build_blacklist()<br/>InstrumentBlacklistPort"]
    FAC --> MD["build_market_data()<br/>→ EntryMarketDataPort"]
    FAC --> FD["build_flow_data()<br/>→ FlowDataPort"]
    FAC --> OP["build_options_provider()<br/>→ OptionsDataPort"]
    FAC --> QG["build_quality_gate()<br/>→ QualityEntryGate"]
    FAC --> SH["build_spec_hub()<br/>→ SpeculativeEntryHub"]
    FAC --> QO["build_quality_orchestrator()<br/>→ QualityOrchestrator"]
    FAC --> SO["build_spec_orchestrator()<br/>→ SpeculativeOrchestrator"]

    BR --> QO & SO
    JR --> QO & SO
    QG --> QO
    SH --> SO

    style FAC fill:#f59e0b,stroke:#d97706,color:#000
```

---

## 5. Entry Pipelines — Side by Side

### 5a. QualityEntryGate (Deep, Daily)

```mermaid
flowchart TD
    START(["🎩 evaluate(ticker)"])
    BL{"Blacklist<br/>4Q cooldown?"}
    PRICE["1. Price Data<br/>ATR · RVOL · RS · VIX"]
    OPT["2. Options<br/>Gamma Regime"]
    VP["3. Volume Profile<br/>POC · VAH · VAL<br/>Institutional Bias"]
    VP_GATE{"VP DISTRIBUTION<br/>≥75%?"}
    WHALE["4. Whale Flow<br/>EventFlowIntelligence"]
    CONTRA{"CONTRA_FLOW?"}
    PHASE["5. Price Phase<br/>FIRE / STALK / ABORT"]
    RSI{"RSI hostile<br/>zone?"}
    PAT{"Pattern<br/>BEARISH?"}
    EXEC(["✅ EXECUTE<br/>Conviction sizing"])

    START --> BL
    BL -->|"Yes"| BLOCK1(["❌ BLOCK"])
    BL -->|"No"| PRICE --> OPT --> VP
    VP --> VP_GATE
    VP_GATE -->|"Yes"| STALK1(["⏳ STALK"])
    VP_GATE -->|"No"| WHALE --> CONTRA
    CONTRA -->|"Yes"| BLOCK2(["❌ BLOCK"])
    CONTRA -->|"No"| PHASE
    PHASE -->|"ABORT"| BLOCK3(["❌ BLOCK"])
    PHASE -->|"FIRE"| RSI
    RSI -->|"Hostile"| STALK2(["⏳ STALK"])
    RSI -->|"OK"| PAT
    PAT -->|"Yes"| STALK3(["⏳ STALK"])
    PAT -->|"No"| EXEC
    PHASE -->|"STALK"| STALK4(["⏳ STALK"])
```

### 5b. SpeculativeEntryHub (Fast, Intraday)

```mermaid
flowchart TD
    START(["⚡ evaluate(ticker)"])
    BL{"Blacklist?"}
    PRICE["1. Price Data"]
    GAMMA["2. Gamma Regime<br/>(Karsan)"]
    KALMAN["3. Kalman Wyckoff<br/>Volume Dynamics"]
    FLOW["4. Flow Intelligence<br/>+ Persistence"]
    DEAD{"DEAD_SIGNAL?"}
    WHALE["5. Event Flow<br/>CONTRA = warning only"]
    PHASE["6. Price Phase"]
    MEM{"Memory Guard<br/>80%+ failed?"}
    ASYM{"R:R ≥ 3:1?<br/>(PTJ gate)"}
    EXEC(["✅ EXECUTE"])

    START --> BL
    BL -->|"Yes"| BLOCK1(["❌ BLOCK"])
    BL -->|"No"| PRICE --> GAMMA --> KALMAN --> FLOW
    FLOW --> DEAD
    DEAD -->|"Yes"| BLOCK2(["❌ BLOCK"])
    DEAD -->|"No"| WHALE --> PHASE
    PHASE -->|"ABORT"| BLOCK3(["❌ BLOCK"])
    PHASE -->|"FIRE"| MEM
    MEM -->|"Yes"| BLOCK4(["❌ BLOCK<br/>Memory Guard"])
    MEM -->|"No"| ASYM
    ASYM -->|"No"| STALK1(["⏳ STALK"])
    ASYM -->|"Yes"| EXEC
    PHASE -->|"STALK"| STALK2(["⏳ STALK"])
```

---

## 6. Exit System — Dual Engine

```mermaid
flowchart TD
    POS(["📍 Posición Abierta"])
    DEPT{"strategy_bucket?"}

    POS --> DEPT

    DEPT -->|"QUALITY"| QUAL["QualityExitEngine<br/>🏛️ Druckenmiller"]
    DEPT -->|"SPECULATIVE"| SPEC["SpeculativeExitEngine<br/>🎯 Seykota"]

    QUAL --> QE1["THESIS_DEATH<br/>SurveillanceLoop → moat decay"]
    QUAL --> QE2["REDUCE_ZONE<br/>GF Value extremo"]

    SPEC --> SE1["STOP_HIT<br/>Adaptive trailing (VIX+RS+Flow)"]
    SPEC --> SE2["TIME_STOP<br/>PTJ: N bars sin profit"]
    SPEC --> SE3["RS_DECAY<br/>Alpha erosionado"]
    SPEC --> SE4["DISTRIBUTION<br/>Wyckoff state"]
    SPEC --> SE5["TIMEOUT<br/>Capital muerto"]

    QE1 & QE2 --> CLOSE(["💰 Cerrar → Journal"])
    SE1 & SE2 & SE3 & SE4 & SE5 --> CLOSE
```

---

## 7. Port / Adapter Map

| Módulo | Port (domain) | Adapter (infrastructure) | Source |
|---|---|---|---|
| **entry_decision** | `EntryMarketDataPort` | `MarketDataFetcher` | yfinance |
| **entry_decision** | `FlowDataPort` | `UnusualWhalesIntelligence` | UW MCP |
| **execution** | `BrokerPort` | `AlpacaAdapter` × 2 | Alpaca SDK |
| **execution** | `TradeJournalPort` | `PostgresTradeJournalAdapter` | PostgreSQL |
| **execution** | `InstrumentBlacklistPort` | `PostgresBlacklistAdapter` | PostgreSQL |
| **options_gamma** | `OptionsDataPort` | `YFinanceOptionsAdapter` | yfinance |
| **flow_intelligence** | `CalendarDataPort` | `FinnhubAdapter` | Finnhub MCP |
| **portfolio_management** | `FundamentalDataPort` | `GuruFocusAdapter` | GuruFocus MCP |
| **portfolio_management** | `ScreenerPort` | `FinvizAdapter` | Finviz MCP |
| **portfolio_management** | `SectorDataPort` | `SectorFlowAdapter` | Finviz + UW |
| **portfolio_management** | `MacroDataPort` | `MacroDataAdapter` | FRED MCP |
| **portfolio_management** | `InstrumentRepoPort` | `PayloadInstrumentsAdapter` | PayloadCMS |
| **rotation_intelligence** | `RotationDataPort` | `YahooRotationAdapter` | yfinance |
| **simulation** | `HistoricalDataPort` + 9 more | TimescaleDB adapters | PostgreSQL |

---

## 8. Storage — PostgreSQL Consolidado

```mermaid
graph LR
    subgraph PG["PostgreSQL (Neon)"]
        PAY["public.*<br/>PayloadCMS (12 collections)"]
        ENG["engine.*<br/>trade_journal · snapshots<br/>ohlcv · macro · features<br/>trading_state<br/>pgvector (9D)"]
    end

    style PAY fill:#3b82f6,stroke:#2563eb,color:#fff
    style ENG fill:#10b981,stroke:#059669,color:#fff
```

---

## 9. Graphify Integrity Check

| Check | Value | Status |
|---|---|---|
| Graphify nodes | **2821** | ✅ V14 |
| Graphify edges | **6074** | ✅ V14 |
| Communities | **187** | ✅ V14 |
| Files indexed | **524** | ✅ V14 |
| Infrastructure imports in domain | **0** | ✅ |
| SDK imports in domain | **0** | ✅ |
| `_legacy/` imports in modules/ | **0** | ✅ V14 |
| Clean modules | **12/12** | ✅ |
| Ports defined | **~21** | ✅ |
| Dual Entry Pipelines | Quality + Speculative | ✅ V14 |
| Dual Exit Engines | Quality + Speculative | ✅ |
| Dual Orchestrators | Quality + Speculative | ✅ V14 |
| Dual Surveillance | Quality + Speculative | ✅ V14 |
| Dual Qualifiers | Quality + Speculative | ✅ V14 |
| Dual Broker Accounts | QUALITY + SPECULATIVE | ✅ |
