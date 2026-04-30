# Botero Trade Engine — Arquitectura Institucional v10

> Última actualización: 2026-04-30 | Versión V10 (Clean Architecture + PostgreSQL Consolidation)

---

## 1. Mapa General del Sistema

```mermaid
graph TB
    subgraph EXT["🌐 Fuentes Externas — MCP Servers (8 activos, ~241 tools)"]
        UW["🐋 Unusual Whales<br/>20+ tools<br/>Flow alerts · Market Tide<br/>SPY delta · Dark Pool"]
        FV["📊 Finviz<br/>35 tools<br/>Screening · Sectores<br/>SEC filings"]
        GF["📈 GuruFocus Premium<br/>55 tools<br/>QGARP · Insiders<br/>Guru analysis"]
        FH["📅 Finnhub<br/>45 tools<br/>Earnings cal · Insiders<br/>News"]
        FR["🏛️ FRED<br/>12 tools<br/>GDP · CPI · FFR<br/>Yield curve"]
        ALP["🦙 Alpaca<br/>61 tools<br/>OHLCV · Quotes<br/>Execution (paper)"]
        YF["📉 Yahoo Finance<br/>9 tools<br/>VIX · Options<br/>Fallback data"]
        NS["📰 News Sentiment<br/>4 tools<br/>FinBERT scoring"]
    end

    subgraph SKILLS["🔧 Agent Skills (.agents/skills/)"]
        SK1["expert-mode — Skill Router"]
        SK2["operational-purpose — Zero-Bias"]
        SK3["clean-architecture — Hexagonal Rules"]
        SK4["fundamental-analyst — Hohn & Munger"]
        SK5["tactical-entries — Eifert & PTJ"]
        SK6["risk-manager — Druckenmiller & Seykota"]
        SK7["backtesting — Simulation Engine"]
        SK8["trading-analysis — Reports"]
    end

    subgraph MODULES["🧩 Backend Modules (11 modules · Clean Architecture)"]

        subgraph MOD_ED["entry_decision"]
            ED_D["domain/<br/>entities/ · ports/ · use_cases/<br/>EntryIntelligenceHub ⭐CORE<br/>EntryMarketDataPort · FlowDataPort"]
            ED_I["infrastructure/<br/>MarketDataFetcher (yfinance)"]
        end

        subgraph MOD_FI["flow_intelligence"]
            FI_D["domain/<br/>entities/ · ports/ · rules/ · use_cases/<br/>analyze_whale_flow · analyze_persistence<br/>CalendarDataPort"]
            FI_I["infrastructure/<br/>uw_adapter · uw_mcp_bridge<br/>fred_adapter · finnhub_adapter<br/>market_breadth_adapter"]
        end

        subgraph MOD_EX["execution"]
            EX_D["domain/<br/>entities/ · ports/ · rules/ · use_cases/<br/>orchestrate_paper_trading<br/>orchestrate_scans · monitor_positions<br/>execute_order · journal_trades<br/>BrokerPort · TradeJournalPort"]
            EX_I["infrastructure/<br/>brokers/ (alpaca · ib · base)<br/>alpaca_data_adapter<br/>postgres_journal_adapter"]
        end

        subgraph MOD_OG["options_gamma"]
            OG_D["domain/<br/>entities/ · ports/ · rules/ · use_cases/<br/>analyze_gamma · OptionsDataPort<br/>black_scholes · opex_calendar"]
            OG_I["infrastructure/<br/>yfinance_adapter"]
        end

        subgraph MOD_PM["portfolio_management"]
            PM_D["domain/<br/>entities/ · ports/ · rules/ · use_cases/<br/>filter_universe · scan_alpha<br/>qualify_ticker · optimize_portfolio<br/>detect_regime_change<br/>5 Ports · 7 Rules"]
            PM_I["infrastructure/<br/>gurufocus · finviz · sector_flow<br/>macro_data · payload_instruments"]
        end

        subgraph MOD_PA["price_analysis"]
            PA_D["domain/<br/>entities/ · rules/ · use_cases/<br/>detect_price_phase · analyze_rsi<br/>FIRE/STALK/ABORT verdicts"]
        end

        subgraph MOD_VI["volume_intelligence"]
            VI_D["domain/<br/>entities/ · rules/ · use_cases/<br/>track_volume_dynamics (Kalman)<br/>analyze_volume_profile (POC/VAH/VAL)"]
        end

        subgraph MOD_PR["pattern_recognition"]
            PR_D["domain/<br/>entities/ · use_cases/<br/>detect_patterns<br/>Hammer · Engulfing · VCP"]
        end

        subgraph MOD_SIM["simulation"]
            SIM_D["domain/<br/>entities/ · ports/ · use_cases/<br/>run_backtest · oracle_backtest<br/>calibrate_strategy · pre_trade_gate<br/>engineer_features · strategy_composer<br/>10 Ports"]
            SIM_I["infrastructure/<br/>data_harmonizer · timescale_data_store<br/>signal_adapters · smc_adapter<br/>postgres_trading_state<br/>triple_barrier · vault_interceptor"]
        end

        subgraph MOD_SH["shared"]
            SH_D["domain/<br/>entities/ · use_cases/<br/>shared_use_cases (delegation)<br/>cache_utils"]
        end
    end

    subgraph API["🔗 API Layer — FastAPI (port 8000)"]
        FAST["main.py<br/>FastAPI + CORS"]
        FAC["factories/<br/>execution_factory.py<br/>Composition Root ⭐"]
        R1["market_data.py"]
        R2["portfolio.py"]
        R3["strategy.py"]
        R4["orders.py"]
        R5["simulation.py"]
    end

    subgraph STORE["🗄️ Storage — PostgreSQL Único"]
        PG_PAY["Neon PostgreSQL<br/>PayloadCMS tables<br/>12 collections"]
        PG_TS["TimescaleDB<br/>OHLCV · Macro · Features<br/>engine.* schema"]
        PG_TJ["Trade Journal<br/>engine.trade_journal<br/>engine.trade_snapshots<br/>pgvector (9D)"]
    end

    subgraph FE["🖥️ Frontend — Next.js 16 + PayloadCMS 3 (port 3000)"]
        UI2["Trading Dashboard<br/>src/app/(frontend)"]
        CMS2["Admin Panel<br/>src/app/(payload)<br/>12 Collections"]
        FE_SHARED["src/shared/<br/>domain/ · application/<br/>infrastructure/ · handlers/"]
    end

    %% External → Infrastructure
    UW -->|"MCP tools"| FI_I
    FV -->|"MCP tools"| PM_I
    GF -->|"MCP tools"| PM_I
    FH -->|"MCP tools"| FI_I
    FR -->|"MCP tools"| FI_I
    ALP -->|"SDK"| EX_I
    YF -->|"yfinance"| OG_I
    YF -->|"yfinance"| ED_I

    %% Infrastructure → Domain (via Ports)
    ED_I -.->|"implements<br/>EntryMarketDataPort"| ED_D
    FI_I -.->|"implements<br/>FlowDataPort · CalendarDataPort"| FI_D
    EX_I -.->|"implements<br/>BrokerPort · TradeJournalPort"| EX_D
    OG_I -.->|"implements<br/>OptionsDataPort"| OG_D
    PM_I -.->|"implements<br/>5 Ports"| PM_D
    SIM_I -.->|"implements<br/>10 Ports"| SIM_D

    %% Domain → Domain (allowed cross-module)
    ED_D --> EX_D
    FI_D --> ED_D
    OG_D --> ED_D
    PA_D --> ED_D
    VI_D --> ED_D
    PR_D --> ED_D
    PM_D --> EX_D

    %% API → Factory → Modules
    FAST --> R1 & R2 & R3 & R4 & R5
    FAC -->|"builds"| EX_I
    R1 --> ED_D
    R3 --> EX_D
    R4 --> EX_D
    R5 --> SIM_D

    %% Storage
    EX_I --> PG_TJ
    SIM_I --> PG_TS
    PM_I --> PG_PAY

    %% Frontend
    FE -->|"HTTP /api"| API
    CMS2 --> PG_PAY
```

---

## 2. Módulos Backend — Hexagonal Architecture

```mermaid
graph LR
    subgraph OUTER["Capa Externa"]
        API2["API Layer<br/>FastAPI routers (5)<br/>factories/ (Composition Root)<br/>port 8000"]
        FE2["Frontend<br/>Next.js 16 + PayloadCMS 3<br/>port 3000"]
    end

    subgraph MOD["11 Backend Modules<br/>backend/modules/"]
        subgraph INFRA2["Infrastructure<br/>(conoce Domain · usa SDKs)"]
            A1["entry_decision/infrastructure/<br/>MarketDataFetcher → EntryMarketDataPort"]
            A2["flow_intelligence/infrastructure/<br/>uw_adapter → FlowDataPort<br/>finnhub_adapter · fred_adapter<br/>market_breadth_adapter"]
            A3["execution/infrastructure/<br/>brokers/ (Alpaca · IB) → BrokerPort<br/>postgres_journal_adapter → TradeJournalPort"]
            A4["options_gamma/infrastructure/<br/>yfinance_adapter → OptionsDataPort"]
            A5["portfolio_management/infrastructure/<br/>gurufocus · finviz · sector_flow<br/>macro_data · payload_instruments"]
            A6["simulation/infrastructure/<br/>data_harmonizer · timescale_data_store<br/>signal_adapters · smc_adapter<br/>postgres_trading_state"]
        end

        subgraph DOMAIN["Domain<br/>(no conoce nada externo)"]
            D_ENT["entities/<br/>Typed dataclasses"]
            D_PRT["ports/<br/>ABC interfaces<br/>(~20 ports total)"]
            D_RUL["rules/<br/>Business constants<br/>& thresholds"]
            D_UC["use_cases/<br/>Pure business logic<br/>(~25 use cases)"]
        end
    end

    subgraph STORE2["Storage — PostgreSQL Único"]
        PG["Neon PostgreSQL<br/>+ TimescaleDB<br/>+ pgvector"]
    end

    OUTER --> INFRA2
    OUTER --> DOMAIN
    INFRA2 -.->|"implements Ports"| DOMAIN
    INFRA2 --> STORE2
    DOMAIN --> D_ENT & D_PRT & D_RUL & D_UC
```

---

## 3. Composition Root — Factory Pattern

```mermaid
flowchart TD
    FAC["execution_factory.py<br/>🏭 Composition Root"]

    FAC --> B["build_broker()<br/>→ AlpacaAdapter(BrokerPort)<br/>Lee ALPACA_API_KEY"]
    FAC --> J["build_journal()<br/>→ PostgresTradeJournalAdapter<br/>Lee POSTGRES_URL"]
    FAC --> M["build_market_data()<br/>→ MarketDataFetcher<br/>(EntryMarketDataPort)"]
    FAC --> F["build_flow_data()<br/>→ UnusualWhalesIntelligence<br/>(FlowDataPort)"]
    FAC --> O["build_options()<br/>→ OptionsAwareness<br/>(via OptionsDataPort)"]
    FAC --> H["build_entry_hub()<br/>→ EntryIntelligenceHub<br/>(all ports injected)"]
    FAC --> P["build_orchestrator()<br/>→ PaperTradingOrchestrator<br/>(receives all ports)"]
    FAC --> MON["build_monitor()<br/>→ PositionMonitor<br/>(BrokerPort + TradeJournalPort)"]

    style FAC fill:#f59e0b,stroke:#d97706,color:#000
```

---

## 4. Pipeline de Decisión — EntryIntelligenceHub (V9)

```mermaid
flowchart TD
    START(["🎯 evaluate(ticker, strategy_bucket)"])

    S1["STEP 1: Precio<br/>EntryMarketDataPort.fetch_prices()<br/>ATR · RVOL · RSI · RS vs SPY<br/>VIX"]

    S2["STEP 2: Opciones — Gamma<br/>OptionsDataPort.get_options_chain()<br/>put_wall · call_wall<br/>gamma_regime · max_pain"]

    S3["STEP 3: Volumen — Wyckoff<br/>KalmanVolumeTracker<br/>wyckoff_state · velocity<br/>Kalman Bayesian filter"]

    S4["STEP 4: Flujo de Ballenas<br/>FlowDataPort (UW MCP)<br/>spy_cum_delta · market_tide<br/>sweep_call_pct · am_pm_divergence"]

    S4B["STEP 4b: Flow Persistence V7<br/>FlowPersistenceAnalyzer<br/>FRESH_ISOLATED · CONFIRMED_STREAK<br/>DECAYING · DEAD_SIGNAL"]

    DEAD{"DEAD_SIGNAL?"}
    BLOCK1(["❌ BLOCK — Signal decayed"])

    S5["STEP 5: EventFlowIntelligence<br/>WhaleVerdict<br/>RIDE_THE_WHALES · LEAN_WITH_FLOW<br/>UNCERTAIN · CONTRA_FLOW"]

    CONTRA{"CONTRA_FLOW?"}
    BLOCK2(["❌ BLOCK (CORE)<br/>TACTICAL pasa al análisis de fase"])

    S55["STEP 5.5: Volume Profile V9 ⭐<br/>VolumeProfileAnalyzer (20d + 50d)<br/>POC · VAH · VAL<br/>Shape: P/D/b · POC Migration<br/>Institutional Bias ACCUMULATION/DISTRIBUTION"]

    DIST{"VP DISTRIBUTION<br/>≥75% confidence<br/>(CORE only)?"}
    BLOCK3(["⏳ STALK — VP Distribution Gate<br/>Institucionales distribuyendo"])

    S6["STEP 6: PricePhaseIntelligence<br/>Fases: CORRECTION · BREAKOUT<br/>CONTRARIAN_DIP · MOMENTUM_CONT<br/>EXHAUSTION_UP · STEALTH_DIST<br/>Verdict: FIRE / STALK / ABORT<br/>Entry/Stop/Target anclados a VP"]

    S6B["STEP 6b: PatternIntelligence V8 ⭐<br/>PatternRecognitionIntelligence<br/>Hammer · Engulfing · Morning Star<br/>Inside Bar · VCP · Shooting Star<br/>confirmation_score -1.0 → +1.0"]

    S7{"STEP 7: Dictamen Final"}

    ABORT_F(["❌ BLOCK — Phase ABORT"])

    FIRE_F["Phase = FIRE"]
    RSI_GATE{"CORE RSI<br/>35-65 sweet spot?"}
    STALK3(["⏳ STALK — RSI Quality Gate"])
    PAT_VETO{"Pattern BEARISH<br/>score ≤ -0.5?"}
    STALK4(["⏳ STALK — Pattern VETO"])
    VECTOR["TradeJournalPort.find_similar()<br/>pgvector 9D query"]
    MEM{"80%+ históricos<br/>similares perdieron?"}
    BLOCK4(["❌ BLOCK — Memory Guard"])
    AMPLIFY{"Pattern BULLISH<br/>en soporte +score ≥0.5?"}
    EXECUTE(["✅ EXECUTE<br/>+25% scale si AMPLIFY"])

    STALK_F["Phase = STALK"]
    PROMOTE{"Pattern BULLISH<br/>score≥0.7 · dims≥2 · RR≥3?"}
    EXECUTE2(["✅ EXECUTE (75% scale)<br/>Pattern PROMOTE: STALK→FIRE"])
    STALK_FINAL(["⏳ STALK — Waiting better setup"])

    START --> S1 --> S2 --> S3 --> S4 --> S4B
    S4B --> DEAD
    DEAD -->|Sí| BLOCK1
    DEAD -->|No| S5
    S5 --> CONTRA
    CONTRA -->|Sí CORE| BLOCK2
    CONTRA -->|No| S55
    S55 --> DIST
    DIST -->|Sí| BLOCK3
    DIST -->|No| S6
    S6 --> S6B --> S7

    S7 -->|"ABORT"| ABORT_F
    S7 -->|"FIRE"| FIRE_F
    S7 -->|"STALK"| STALK_F

    FIRE_F --> RSI_GATE
    RSI_GATE -->|"Fuera rango"| STALK3
    RSI_GATE -->|"OK"| PAT_VETO
    PAT_VETO -->|"Sí"| STALK4
    PAT_VETO -->|"No"| VECTOR --> MEM
    MEM -->|"Sí"| BLOCK4
    MEM -->|"No"| AMPLIFY
    AMPLIFY -->|"Sí"| EXECUTE
    AMPLIFY -->|"No"| EXECUTE

    STALK_F --> PROMOTE
    PROMOTE -->|"Sí"| EXECUTE2
    PROMOTE -->|"No"| STALK_FINAL
```

---

## 5. Universe Filter — 4-Tier Pipeline

```mermaid
flowchart LR
    T0(["🌍 Universo Inicial<br/>~5000 tickers"])

    subgraph T1["TIER 1 — Macro Gate<br/>FRED MCP (12 tools)"]
        M1["MacroRegimeDetector<br/>GDP · CPI · FFR<br/>Yield curve · VIX<br/>Regime: RISK_ON/RISK_OFF/NEUTRAL"]
    end

    subgraph T2["TIER 2 — Sector Filter<br/>Finviz (35 tools)"]
        M2["SectorRotationEngine<br/>Sector performance 1m/3m<br/>Money flow · Relative strength<br/>Top 3 sectors only"]
    end

    subgraph T3["TIER 3 — Fundamental Screen<br/>GuruFocus Premium (55 tools)<br/>Finnhub (45 tools)"]
        M3["QGARP Score<br/>Insider ownership %<br/>Guru holdings count<br/>Earnings calendar filter"]
    end

    subgraph T4["TIER 4 — Catalyst Filter<br/>Unusual Whales (20+ tools)<br/>News Sentiment (4 tools)"]
        M4["Flow alerts · Dark pool prints<br/>FinBERT news sentiment<br/>Event calendar (earnings/Fed)"]
    end

    OUT(["✅ Candidatos Finales<br/>5-15 tickers de alta convicción<br/>→ AlphaScanner"])

    T0 --> T1 --> T2 --> T3 --> T4 --> OUT
```

---

## 6. Port / Adapter Map — Módulo por Módulo

| Módulo | Port (domain) | Adapter (infrastructure) | External Source |
|---|---|---|---|
| **entry_decision** | `EntryMarketDataPort` | `MarketDataFetcher` | yfinance |
| **entry_decision** | `FlowDataPort` | `UnusualWhalesIntelligence` | UW MCP |
| **execution** | `BrokerPort` | `AlpacaAdapter` · `IBAdapter` | Alpaca SDK · IBKR |
| **execution** | `TradeJournalPort` | `PostgresTradeJournalAdapter` | PostgreSQL |
| **options_gamma** | `OptionsDataPort` | `YFinanceOptionsAdapter` | yfinance |
| **flow_intelligence** | `CalendarDataPort` | `FinnhubAdapter` | Finnhub MCP |
| **portfolio_management** | `FundamentalDataPort` | `GuruFocusAdapter` | GuruFocus MCP |
| **portfolio_management** | `ScreenerPort` | `FinvizAdapter` | Finviz MCP |
| **portfolio_management** | `SectorDataPort` | `SectorFlowAdapter` | Finviz + UW MCP |
| **portfolio_management** | `MacroDataPort` | `MacroDataAdapter` | FRED MCP |
| **portfolio_management** | `InstrumentRepoPort` | `PayloadInstrumentsAdapter` | PayloadCMS (PG) |
| **simulation** | `HistoricalDataPort` | (TimescaleDB) | PostgreSQL |
| **simulation** | `TimeSeriesPort` | `TimescaleDataStore` | PostgreSQL |
| **simulation** | `DataHarmonizerPort` | `DataHarmonizer` | Internal |
| **simulation** | `SignalPort` | `SignalAdapters` | Internal |
| **simulation** | `TradingStatePort` | `PostgresTradingState` | PostgreSQL |
| **simulation** | `MarketStructurePort` | `SMCAdapter` | Internal |
| **simulation** | `BarrierLabelerPort` | `TripleBarrierAdapter` | Internal |
| **simulation** | `MLConfidencePort` | (planned) | — |
| **simulation** | `DashboardSyncPort` | (planned) | — |
| **simulation** | `VolumeAnalysisPort` | (planned) | — |

---

## 7. Storage — PostgreSQL Consolidado

```mermaid
graph TB
    subgraph PG["PostgreSQL (Neon)"]
        subgraph PAY["PayloadCMS Schema (public)"]
            C1["Users · Portfolios · PortfolioMemberships"]
            C2["BrokerAccounts · Instruments"]
            C3["Bots · BotAssignments"]
            C4["CalibrationProfiles · RegimePhases"]
            C5["CandidateScreenings · TradeSnapshots"]
            C6["Media"]
        end

        subgraph ENG["Engine Schema (engine.*)"]
            T1["engine.trade_journal<br/>Trades con JSONB snapshots<br/>pgvector embeddings (9D)"]
            T2["engine.trade_snapshots<br/>Pre/Post trade intelligence"]
            T3["engine.ohlcv_daily<br/>TimescaleDB hypertable"]
            T4["engine.macro_indicators<br/>FRED data series"]
            T5["engine.features<br/>ML-ready feature store"]
            T6["engine.trading_state<br/>Live positions & regime"]
        end
    end

    style PAY fill:#3b82f6,stroke:#2563eb,color:#fff
    style ENG fill:#10b981,stroke:#059669,color:#fff
```

---

## 8. Frontend — Next.js 16 + PayloadCMS 3

```mermaid
graph TB
    subgraph NEXT["Next.js 16 (port 3000)"]
        subgraph ROUTES["App Router"]
            R_FE["(frontend)/<br/>Trading Dashboard"]
            R_PAY["(payload)/<br/>Admin Panel"]
        end

        subgraph COLLECTIONS["PayloadCMS Collections (12)"]
            COL1["Users · Portfolios"]
            COL2["BrokerAccounts · Instruments"]
            COL3["Bots · BotAssignments"]
            COL4["CalibrationProfiles · RegimePhases"]
            COL5["CandidateScreenings · TradeSnapshots"]
            COL6["PortfolioMemberships · Media"]
        end

        subgraph SHARED["src/shared/ (Clean Layers)"]
            S_DOM["domain/<br/>TypeScript types only"]
            S_APP["application/<br/>domain imports only"]
            S_INF["infrastructure/<br/>API clients, adapters"]
            S_HAN["handlers/<br/>Payload hook handlers"]
        end
    end

    R_FE -->|"uses"| S_INF
    S_INF --> S_APP --> S_DOM
    R_PAY --> COLLECTIONS
    COLLECTIONS --> S_HAN

    NEXT -->|"HTTP /api"| FAST["FastAPI :8000"]
```

---

## 9. Exit System — 5 Señales Forenses

```mermaid
flowchart TD
    POS(["📍 Posición Abierta"])

    E1["1. STOP_HIT<br/>AdaptiveTrailingStop<br/>Adapta según VIX + Wyckoff regime"]
    E2["2. PROFIT_TARGET<br/>TACTICAL: 2×ATR o +2%<br/>Target anclado a VP POC/VAH"]
    E3["3. TIME_STOP_3D<br/>TACTICAL: salida a 3 días<br/>si no alcanzó target (forensic)"]
    E4["4. SMA20_RECLAIM<br/>CONTRARIAN_DIP: salida<br/>cuando precio recupera SMA20"]
    E5["5. MFE_LOCK<br/>Si MFE > 3%<br/>→ Lock-in 40% de la ganancia"]

    POS --> E1
    POS --> E2
    POS --> E3
    POS --> E4
    POS --> E5

    E1 --> CLOSE(["💰 Cerrar posición<br/>→ TradeJournalPort<br/>→ PostgreSQL (pgvector)"])
    E2 --> CLOSE
    E3 --> CLOSE
    E4 --> CLOSE
    E5 --> CLOSE
```

---

## 10. MCP Skills Map — Herramientas por Módulo

| Módulo Backend | MCP / Skill | Tools usados |
|---|---|---|
| **flow_intelligence** (UW) | Unusual Whales | `get_flow_alerts`, `get_market_tide`, `get_spy_ticks`, `get_darkpool_prints` |
| **flow_intelligence** (FRED) | FRED | `get_series`, `search_series`, `get_releases` |
| **flow_intelligence** (Finnhub) | Finnhub | `get_earnings_calendar`, `get_insider_transactions` |
| **flow_intelligence** (Breadth) | Yahoo Finance + UW | S5TH, Fear & Greed |
| **portfolio_management** (GuruFocus) | GuruFocus Premium | `get_financials`, `get_insider_transactions`, `get_guru_holdings` |
| **portfolio_management** (Finviz) | Finviz | `get_sector_performance`, `get_market_overview`, `screen_stocks` |
| **portfolio_management** (Instruments) | PayloadCMS (PG) | Direct DB read via adapter |
| **options_gamma** | Yahoo Finance | `get_options_chain`, `get_options_expiry` |
| **entry_decision** (Market Data) | yfinance (internal) | OHLCV, VIX |
| **volume_intelligence** | — (NumPy puro) | OHLCV de yfinance, Kalman filter |
| **pattern_recognition** | — (NumPy puro) | OHLCV, candlestick detection |
| **execution** (Broker) | Alpaca SDK | `place_order`, `get_positions`, `get_portfolio` |
| **execution** (Journal) | PostgreSQL | pgvector similarity search |
| **simulation** | TimescaleDB | OHLCV, features, trading state |
| **shared** | News Sentiment MCP | `analyze_sentiment` (FinBERT) |

---

## 11. Inward Dependency Rule — Verificado ✅

```
┌─────────────────────────────────────────────────────┐
│  API Layer (routers, factories)                      │
│  ┌───────────────────────────────────────────────┐  │
│  │  Infrastructure (adapters, SDKs, PostgreSQL)   │  │
│  │  ┌─────────────────────────────────────────┐  │  │
│  │  │  Domain (entities, ports, rules, use_cases)│  │  │
│  │  │  • ZERO SDK imports                       │  │  │
│  │  │  • ZERO os.getenv / os.environ            │  │  │
│  │  │  • ZERO infrastructure imports            │  │  │
│  │  │  • Dependencies injected via Ports (ABC)  │  │  │
│  │  └─────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

| Check | Count | Status |
|---|---|---|
| Infrastructure imports in domain | **0** | ✅ |
| SDK imports in domain | **0** | ✅ |
| `os.getenv` in domain | **0** | ✅ |
| MongoDB references | **0** | ✅ Purged |
| Ports defined | **~20** | ✅ |
| Adapters implementing ports | **~15** | ✅ |
| Composition Root | `execution_factory.py` | ✅ |
| Clean modules (11/11) | **11** | ✅ |

---

## 12. Diagramas de Estado

### 12a. Trade Lifecycle — `TradeJournalEntry.status`

```mermaid
stateDiagram-v2
    [*] --> CANDIDATE: Universe Filter<br/>selecciona ticker

    CANDIDATE --> BLOCKED: EntryHub verdict=BLOCK<br/>o RiskGuardian rechaza
    CANDIDATE --> STALKING: EntryHub verdict=STALK<br/>esperando mejor setup
    CANDIDATE --> PROBING: EntryHub verdict=EXECUTE<br/>orden LIMIT enviada

    STALKING --> PROBING: Pattern PROMOTE<br/>o condiciones mejoran
    STALKING --> BLOCKED: Timeout sin mejora

    PROBING --> OPEN: Orden llenada<br/>journal.open_trade()
    PROBING --> CANCELLED: Orden no ejecutada<br/>o rechazada por SmartEntry

    OPEN --> OPEN: Monitor: trailing stop sube<br/>RS tracking · MFE/MAE update

    OPEN --> CLOSED_WIN: ExitEngine: PROFIT_TARGET<br/>o MA20_REVERSION
    OPEN --> CLOSED_LOSS: ExitEngine: STOP_HIT<br/>o RS_DECAY · DISTRIBUTION · TIMEOUT

    CLOSED_WIN --> LEARNING: journal.close_trade()<br/>post-mortem + grade
    CLOSED_LOSS --> LEARNING: journal.close_trade()<br/>lesson_learned

    LEARNING --> [*]: pgvector embedding<br/>actualizado para Memory Guard

    BLOCKED --> [*]
    CANCELLED --> [*]

    state OPEN {
        [*] --> Monitoring
        Monitoring --> FreezeActive: Evento macro<br/>(FOMC/CPI/NFP < 4h)
        FreezeActive --> Monitoring: Evento pasa<br/>(freeze_duration expira)
        Monitoring --> ExitEvaluation: check_positions()
        ExitEvaluation --> Monitoring: No exit signal
    }
```

### 12b. Entry Verdict — `EntryIntelligenceReport.final_verdict`

```mermaid
stateDiagram-v2
    [*] --> PriceData: STEP 1<br/>fetch_prices()

    PriceData --> GammaAnalysis: STEP 2<br/>OptionsDataPort

    GammaAnalysis --> WyckoffVolume: STEP 3<br/>KalmanVolumeTracker

    WyckoffVolume --> WhaleFlow: STEP 4<br/>FlowDataPort (UW)

    WhaleFlow --> FlowPersistence: STEP 4b<br/>FlowPersistenceAnalyzer

    FlowPersistence --> BLOCK_DEAD: DEAD_SIGNAL<br/>señal decayó
    FlowPersistence --> EventFlow: No dead

    EventFlow --> BLOCK_CONTRA: CONTRA_FLOW (CORE)<br/>ballenas en contra
    EventFlow --> VolumeProfile: No contra

    VolumeProfile --> STALK_VP: VP DISTRIBUTION ≥75%<br/>(CORE only)
    VolumeProfile --> PricePhase: VP OK

    PricePhase --> PatternIntel: detect_price_phase()

    PatternIntel --> ABORT: Phase = ABORT

    PatternIntel --> FIRE_PATH: Phase = FIRE
    PatternIntel --> STALK_PATH: Phase = STALK

    state FIRE_PATH {
        [*] --> RSI_Gate
        RSI_Gate --> STALK_RSI: RSI fuera 35-65
        RSI_Gate --> PatternVeto: RSI OK
        PatternVeto --> STALK_PATTERN: score ≤ -0.5
        PatternVeto --> MemoryGuard: No veto
        MemoryGuard --> BLOCK_MEMORY: 80%+ similares perdieron
        MemoryGuard --> EXECUTE: Memory OK
    }

    state STALK_PATH {
        [*] --> PromoteCheck
        PromoteCheck --> EXECUTE_75: score≥0.7 · dims≥2 · RR≥3
        PromoteCheck --> STALK_WAIT: No promotion
    }

    EXECUTE --> [*]: ✅ EXECUTE (scale por whale_scale)
    EXECUTE_75 --> [*]: ✅ EXECUTE (75% scale)
    BLOCK_DEAD --> [*]: ❌ BLOCK
    BLOCK_CONTRA --> [*]: ❌ BLOCK
    BLOCK_MEMORY --> [*]: ❌ BLOCK
    ABORT --> [*]: ❌ BLOCK
    STALK_VP --> [*]: ⏳ STALK
    STALK_RSI --> [*]: ⏳ STALK
    STALK_PATTERN --> [*]: ⏳ STALK
    STALK_WAIT --> [*]: ⏳ STALK
```

### 12c. Market Regime — `MarketRegime` enum

```mermaid
stateDiagram-v2
    [*] --> NEUTRAL: Default

    RISK_ON --> NEUTRAL: VIX sube > 18<br/>o yield spread ≤ 0
    NEUTRAL --> RISK_ON: VIX < 18<br/>AND yield spread > 0

    NEUTRAL --> RISK_OFF: VIX > 25
    RISK_OFF --> NEUTRAL: VIX baja < 25

    RISK_OFF --> CRISIS: VIX > 35
    CRISIS --> RISK_OFF: VIX baja < 35

    state RISK_ON {
        [*] --> Cyclicals
        Cyclicals: Cíclicos + Growth<br/>CORE + TACTICAL activos<br/>Max position sizing
    }
    state NEUTRAL {
        [*] --> Selective
        Selective: Selectivo<br/>CORE con filtros estrictos<br/>TACTICAL normal
    }
    state RISK_OFF {
        [*] --> Defensive
        Defensive: Defensivos o Cash<br/>CORE pausado (VP gate)<br/>TACTICAL solo contrarian
    }
    state CRISIS {
        [*] --> CashOnly
        CashOnly: Solo reversión extrema<br/>Todos los gates activos<br/>Position size mínimo
    }
```

### 12d. Exit Engine — `ExitDecision.reason`

```mermaid
stateDiagram-v2
    [*] --> StopUpdate: AdaptiveTrailingStop<br/>recalcula con VIX + RS + Flow

    StopUpdate --> Frozen: freeze_stops = true<br/>(evento macro cercano)
    Frozen --> StopUpdate: freeze expira

    StopUpdate --> STOP_HIT: price ≤ stop<br/>urgency: HIGH
    StopUpdate --> CheckMA20: price > stop

    CheckMA20 --> MA20_REVERSION: price ≥ MA20<br/>AND bars ≥ 2<br/>urgency: MEDIUM
    CheckMA20 --> CheckRS: price < MA20

    CheckRS --> RS_DECAY: Alpha erosionado<br/>RS dropped > threshold<br/>urgency: varies
    CheckRS --> CheckWyckoff: RS OK

    CheckWyckoff --> DISTRIBUTION: wyckoff = DISTRIBUTION<br/>AND bars ≥ 3<br/>urgency: HIGH
    CheckWyckoff --> CheckTimeout: No distribution

    CheckTimeout --> TIMEOUT: bars ≥ max_bars<br/>urgency: MEDIUM
    CheckTimeout --> HOLD: Ningún trigger

    HOLD --> [*]: Continuar holding
    STOP_HIT --> [*]: 🔴 Cerrar
    MA20_REVERSION --> [*]: 🟡 Cerrar
    RS_DECAY --> [*]: 🟡 Cerrar
    DISTRIBUTION --> [*]: 🔴 Cerrar
    TIMEOUT --> [*]: 🟡 Cerrar
```
