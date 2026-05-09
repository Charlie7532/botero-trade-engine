# Botero Trade — Expert Committee & Decision Architecture

> Actualizado 2026-05-08 | 20 Skills · 11 Modules · 8 MCP Servers

---

## 1. Investment Committee — Expert Personas & Decision Chain

```mermaid
graph TB
    subgraph CIO["🏛️ CIO — Ray Dalio<br/>cio-allocator skill"]
        DALIO["DailyMandate<br/>Capital: 80Q/20S default<br/>Sector vetoes & focus<br/>Regime: RISK_ON/OFF/NEUTRAL/CRISIS<br/>Idea Meritocracy: believability-weighted<br/>5-Step Self-Correcting Machine"]
    end

    subgraph RESEARCH["🔍 Research & Intelligence<br/>research-intelligence skill"]
        RQ["Track 1: QUALITY<br/>Guru Accumulation · Insider Clusters<br/>→ Quantitative Gate (Z/Piotroski/Beneish)<br/>→ Moat Stress Test (5 checks)<br/>→ Helmer Expectations Engine<br/>→ Valuation Zones (GF Value)<br/>→ CandidateDossier"]
        RS["Track 2: SPECULATIVE<br/>UW Sweeps · Dark Pool<br/>→ Flow Anomaly Detection<br/>→ Structure Analysis (Eifert/Karsan/PTJ)<br/>→ OpportunityBrief"]
    end

    subgraph QUALITY_DEPT["🏦 QUALITY Department<br/>department-quality skill"]
        HOHN["Fundamental Analyst<br/>🎩 Hohn & Munger<br/>fundamental-analyst skill<br/>─────────────<br/>Inversion Gate<br/>Tollkeeper Test<br/>Barrier Stack (≥2 moats)<br/>Moat Stress Test (5 checks)<br/>Pricing Power<br/>Helmer Reverse DCF<br/>Valuation Zones (GF Value)"]
        DRUCK["Risk Manager QUALITY<br/>📊 Druckenmiller<br/>risk-quality skill<br/>─────────────<br/>Thesis-based exits only<br/>Go for Jugular sizing<br/>18-24mo forward<br/>Swing around core<br/>No mechanical stops<br/>Liquidity > Earnings"]
    end

    subgraph SPEC_DEPT["⚡ SPECULATIVE Department<br/>department-speculative skill"]
        EIFERT["Tactical Entries<br/>🎯 Eifert, Karsan & PTJ<br/>tactical-entries skill<br/>─────────────<br/>Eifert: WHO & WHY (skeptic)<br/>Karsan: GEX/Vanna/Charm map<br/>PTJ: 5:1 R:R · 200-DMA · tape<br/>Three-voice veto chain"]
        SEYKOTA["Risk Manager SPECULATIVE<br/>🔥 Seykota<br/>risk-speculative skill<br/>─────────────<br/>Mechanical stops (2-3 ATR)<br/>Time stops (2-5 sessions)<br/>Risk of Ruin < 5%<br/>Anti-Martingale<br/>Psychology Gate (3 losses)<br/>PTJ Rhythm Sizing"]
    end

    subgraph ROTATION["🌍 Rotation Intelligence<br/>rotation-analyst skill"]
        WEIN["Weinstein Stage Analysis<br/>30-week MA · RS · Volume<br/>Stage 1-4 classification<br/>26 ETFs tracked"]
        PRING["Pring Intermarket Cycle<br/>Bonds→Stocks→Commodities<br/>Economic phase detection"]
    end

    subgraph FORENSICS["🔬 Trade Forensics<br/>trade-forensics skill"]
        FSPEC["Seykota Loop (SPECULATIVE)<br/>Detect→Learn→Retrain→Prevent<br/>Stop calibration · Pattern decay<br/>Memory Guard effectiveness<br/>engine.trade_journal_speculative"]
        FQUAL["Druckenmiller Loop (QUALITY)<br/>Thesis accuracy scoring<br/>Surveillance lag measurement<br/>4Q blacklist enforcement<br/>engine.trade_journal_quality"]
    end

    subgraph BACKTEST["🧪 Quantitative Lab<br/>backtesting skill"]
        LOPRADO["López de Prado<br/>Triple Barrier · Meta-Labeling<br/>Purged CV · Deflated Sharpe<br/>Feature importance (MDA/SFI)<br/>Information-Driven Bars"]
        SIMONS["Signal Miner (Simons)<br/>signal-miner skill<br/>Non-intuitive anomaly detection<br/>Cross-asset correlations<br/>Signal decay monitoring<br/>Feeds → López de Prado"]
    end

    %% Decision flow
    CIO -->|"DailyMandate<br/>budget + sectors"| QUALITY_DEPT
    CIO -->|"DailyMandate<br/>budget + sectors"| SPEC_DEPT
    CIO -->|"regime query"| ROTATION

    RESEARCH -->|"CandidateDossier"| QUALITY_DEPT
    RESEARCH -->|"OpportunityBrief"| SPEC_DEPT

    ROTATION -->|"sector_flows<br/>stage_transitions"| CIO
    ROTATION -->|"Stage 2 sectors"| RESEARCH

    HOHN -->|"HOHN QUALITY<br/>CONDITIONAL<br/>TOO HARD"| DRUCK
    EIFERT -->|"FIRE/WAIT<br/>entry params"| SEYKOTA

    DRUCK -->|"HOLD/SCALE/LIQUIDATE"| FORENSICS
    SEYKOTA -->|"CUT MECHANICAL"| FORENSICS

    FORENSICS -->|"calibrated params"| EIFERT
    FORENSICS -->|"adjusted thresholds"| DRUCK
    FORENSICS -->|"recalibration data"| BACKTEST

    SIMONS -->|"signal candidates"| LOPRADO
    BACKTEST -->|"VIABLE/OVERFIT"| CIO

    style CIO fill:#f59e0b,stroke:#d97706,color:#000
    style QUALITY_DEPT fill:#3b82f6,stroke:#2563eb,color:#fff
    style SPEC_DEPT fill:#ef4444,stroke:#dc2626,color:#fff
    style RESEARCH fill:#8b5cf6,stroke:#7c3aed,color:#fff
    style ROTATION fill:#10b981,stroke:#059669,color:#fff
    style FORENSICS fill:#f97316,stroke:#ea580c,color:#fff
    style BACKTEST fill:#6366f1,stroke:#4f46e5,color:#fff
```

---

## 2. 6-Gate Investment Committee Protocol

```mermaid
flowchart LR
    G1["🌍 Gate 1<br/>Rotation Intel<br/>Weinstein & Pring<br/>─────────<br/>WHERE is capital<br/>flowing?"]
    G2["🏛️ Gate 2<br/>Fundamental Screen<br/>Hohn & Munger<br/>─────────<br/>Is this a<br/>tollkeeper?"]
    G3["🎯 Gate 3<br/>Tactical Validation<br/>Eifert, Karsan, PTJ<br/>─────────<br/>Is NOW the<br/>right time?"]
    G4["⚖️ Gate 4<br/>CIO Review<br/>Dalio Meritocracy<br/>─────────<br/>Who DISAGREES<br/>and why?"]
    G5["📊 Gate 5<br/>Risk Sizing<br/>Druckenmiller/Seykota<br/>─────────<br/>How much capital?<br/>Where is the stop?"]
    G6["✅ Gate 6<br/>Execution<br/>User Confirmation<br/>─────────<br/>Place order?<br/>Broker routing"]

    G1 -->|"FOCUS sectors"| G2
    G2 -->|"candidates"| G3
    G3 -->|"ENTER/WAIT"| G4
    G4 -->|"APPROVED"| G5
    G5 -->|"sized positions"| G6

    G1 -.->|"VETO"| KILL1([❌ Killed])
    G2 -.->|"TOO HARD"| KILL2([❌ Killed])
    G3 -.->|"NO ENTRY"| KILL3([❌ Killed])
    G4 -.->|"REJECTED"| KILL4([❌ Killed])

    style G1 fill:#10b981,stroke:#059669,color:#fff
    style G2 fill:#3b82f6,stroke:#2563eb,color:#fff
    style G3 fill:#ef4444,stroke:#dc2626,color:#fff
    style G4 fill:#f59e0b,stroke:#d97706,color:#000
    style G5 fill:#8b5cf6,stroke:#7c3aed,color:#fff
    style G6 fill:#22c55e,stroke:#16a34a,color:#fff
```

---

## 3. Skill Dependency Graph — Layers & Conflicts

```mermaid
graph TB
    subgraph ROUTER["Router Layer"]
        EM["expert-mode<br/>Skill Router"]
    end

    subgraph TOOLS["Tool Layer (VALIDATION)"]
        BT["backtesting-trading-strategies<br/>López de Prado"]
        TF["trade-forensics<br/>Closed-Loop Learning"]
    end

    subgraph PERSONAS["Persona Layer"]
        subgraph P_QUALITY["QUALITY Personas"]
            FA["fundamental-analyst<br/>Hohn & Munger"]
            RQ["risk-quality<br/>Druckenmiller"]
        end
        subgraph P_SPECULATIVE["SPECULATIVE Personas"]
            TE["tactical-entries<br/>Eifert/Karsan/PTJ"]
            RS_P["risk-speculative<br/>Seykota"]
            SM["signal-miner<br/>Simons"]
        end
        subgraph P_SERVICE["SERVICE Personas"]
            RA["rotation-analyst<br/>Weinstein & Pring"]
            RI["research-intelligence<br/>Research Director"]
        end
        subgraph P_CROSS["CROSS Persona"]
            CIA["cio-allocator<br/>Dalio"]
        end
    end

    subgraph DEPTS["Department Layer"]
        DQ["department-quality<br/>80% Tollkeeper Capital"]
        DS["department-speculative<br/>20% Tactical Alpha"]
    end

    subgraph BASELINE["Baseline Layer (ALWAYS ACTIVE)"]
        OP["operational-purpose<br/>Zero-Bias Alignment"]
        CA["clean-architecture<br/>Hexagonal Enforcement"]
    end

    %% Router → everything
    EM --> TOOLS & PERSONAS & DEPTS

    %% Personas → departments
    FA --> DQ
    RQ --> DQ
    TE --> DS
    RS_P --> DS
    SM --> DS

    %% Departments → baseline
    DQ --> OP & CA
    DS --> OP & CA

    %% Service/Cross → baseline directly
    RA --> OP & CA
    RI --> OP & CA
    CIA --> OP & CA
    BT --> OP & CA
    TF --> OP & CA

    %% Conflict lines (red dashed)
    FA -.-x SM
    RQ -.-x RS_P
    DQ -.-x DS

    linkStyle 19 stroke:#ef4444,stroke-dasharray:5
    linkStyle 20 stroke:#ef4444,stroke-dasharray:5
    linkStyle 21 stroke:#ef4444,stroke-dasharray:5

    style ROUTER fill:#1e1b4b,stroke:#4338ca,color:#c7d2fe
    style TOOLS fill:#431407,stroke:#ea580c,color:#fed7aa
    style P_QUALITY fill:#1e3a5f,stroke:#3b82f6,color:#93c5fd
    style P_SPECULATIVE fill:#5f1e1e,stroke:#ef4444,color:#fca5a5
    style P_SERVICE fill:#1e5f3a,stroke:#10b981,color:#6ee7b7
    style P_CROSS fill:#5f4b1e,stroke:#f59e0b,color:#fcd34d
    style DEPTS fill:#2d1b4e,stroke:#8b5cf6,color:#c4b5fd
    style BASELINE fill:#1e1e1e,stroke:#6b7280,color:#d1d5db
```

---

## 4. Skill → Module → Decision Map

```mermaid
graph LR
    subgraph SKILLS["Agent Skills (20)"]
        direction TB
        S_OP["operational-purpose<br/>ALWAYS ACTIVE"]
        S_CA["clean-architecture<br/>ALWAYS ACTIVE"]
        S_DQ["department-quality"]
        S_DS["department-speculative"]
        S_CIO["cio-allocator"]
        S_ROT["rotation-analyst"]
        S_RI["research-intelligence"]
        S_FA["fundamental-analyst"]
        S_TE["tactical-entries"]
        S_RQ["risk-quality"]
        S_RS["risk-speculative"]
        S_SM["signal-miner"]
        S_BT["backtesting"]
        S_TF["trade-forensics"]
        S_PL["4× Payload CMS"]
    end

    subgraph MODULES["Backend Modules (11)"]
        direction TB
        M_ED["entry_decision"]
        M_EX["execution"]
        M_FI["flow_intelligence"]
        M_OG["options_gamma"]
        M_PR["pattern_recognition"]
        M_PM["portfolio_management"]
        M_PA["price_analysis"]
        M_RI["rotation_intelligence"]
        M_SH["shared"]
        M_SIM["simulation"]
        M_VI["volume_intelligence"]
    end

    subgraph DECISIONS["Decisions Produced"]
        direction TB
        D_MANDATE["DailyMandate<br/>budget + sectors"]
        D_STAGE["StageMap<br/>sector rotation"]
        D_DOSSIER["CandidateDossier<br/>quality candidates"]
        D_BRIEF["OpportunityBrief<br/>speculative setups"]
        D_ENTRY["EntryVerdict<br/>FIRE/STALK/BLOCK"]
        D_EXIT["ExitDecision<br/>HOLD/CUT/LIQUIDATE"]
        D_SIZE["PositionAllocation<br/>sizing + stops"]
        D_CALIB["CalibrationProfile<br/>signal weights"]
        D_REGIME["MarketRegime<br/>RISK_ON/OFF"]
    end

    %% Skills → Modules (QUALITY path)
    S_FA --> M_ED & M_PM
    S_RQ --> M_EX & M_PM & M_ED

    %% Skills → Modules (SPECULATIVE path)
    S_TE --> M_ED & M_FI & M_OG & M_PA & M_PR & M_VI
    S_RS --> M_EX & M_OG & M_ED
    S_SM --> M_SIM

    %% Skills → Modules (SERVICE/CROSS/VALIDATION)
    S_CIO --> M_EX & M_PM & M_RI
    S_ROT --> M_RI
    S_RI --> M_PM
    S_BT --> M_SIM
    S_TF --> M_EX

    %% Modules → Decisions
    M_PM --> D_MANDATE & D_REGIME & D_DOSSIER
    M_RI --> D_STAGE
    M_ED --> D_ENTRY
    M_EX --> D_EXIT & D_SIZE
    M_SIM --> D_CALIB
    M_FI --> D_BRIEF

    style SKILLS fill:#1e1b4b,stroke:#4338ca,color:#c7d2fe
    style MODULES fill:#042f2e,stroke:#0d9488,color:#99f6e4
    style DECISIONS fill:#431407,stroke:#ea580c,color:#fed7aa
```

---

## 5. CrewAI Agent Blueprint (Future Multi-Agent)

When CrewAI is implemented, each skill stack becomes an autonomous agent:

| Agent | System Prompt Skills | MCP Servers | Department |
|---|---|---|---|
| **Quality Agent** | operational-purpose, clean-architecture, department-quality, fundamental-analyst, risk-quality | GuruFocus, Finnhub, FRED | QUALITY |
| **Speculative Agent** | operational-purpose, clean-architecture, department-speculative, tactical-entries, risk-speculative | Unusual Whales, Yahoo Finance | SPECULATIVE |
| **Research Agent** | operational-purpose, clean-architecture, research-intelligence | GuruFocus, Finnhub, Finviz, Unusual Whales | SERVICE |
| **CIO Agent** | operational-purpose, clean-architecture, cio-allocator, rotation-analyst | FRED, Yahoo Finance | CROSS |
| **Validation Agent** | operational-purpose, clean-architecture, backtesting, trade-forensics, signal-miner | *(none)* | VALIDATION |

### Conflict Pairs (Never Co-Load)

| Pair | Reason | Exception |
|---|---|---|
| `fundamental-analyst` ↔ `signal-miner` | Quality vs Speculative cognitive conflict | CIO-level with explicit department scoping |
| `risk-quality` ↔ `risk-speculative` | Thesis exits vs mechanical stops | CIO-level audit only |
| `fundamental-analyst` ↔ `tactical-entries` | Long-term vs tactical framing | CIO-level with both departments |
| `department-quality` ↔ `department-speculative` | Contradictory mandates | CIO-level overview |

---

## 6. Data Flow — Vault-First Architecture

```mermaid
flowchart TB
    subgraph EXTERNAL["External Data Sources"]
        MCP_GF["GuruFocus MCP<br/>55 tools"]
        MCP_FV["Finviz MCP<br/>35 tools"]
        MCP_UW["Unusual Whales MCP<br/>20+ tools"]
        MCP_FH["Finnhub MCP<br/>45 tools"]
        MCP_FR["FRED MCP<br/>12 tools"]
        MCP_YF["Yahoo Finance MCP<br/>9 tools"]
    end

    subgraph DAEMONS["Daemons (Delivery Mechanism)"]
        VD["Vault Daemon<br/>Single Writer<br/>MCP → Neon"]
    end

    subgraph VAULT["Neon PostgreSQL (Vault)"]
        OHLCV["market.ohlcv_bars<br/>662K+ bars · 531 tickers"]
        SNAP["market.mcp_snapshots<br/>Fundamental + Flow data"]
        JOURNAL_Q["engine.trade_journal_quality"]
        JOURNAL_S["engine.trade_journal_speculative"]
    end

    subgraph MODULES["Backend Modules (Readers Only)"]
        MOD["All 11 modules<br/>Read via TimescaleDataStore<br/>NEVER call external APIs"]
    end

    EXTERNAL --> VD
    VD --> VAULT
    VAULT --> MOD

    style EXTERNAL fill:#1e1b4b,stroke:#4338ca,color:#c7d2fe
    style DAEMONS fill:#5f4b1e,stroke:#f59e0b,color:#fcd34d
    style VAULT fill:#1e5f3a,stroke:#10b981,color:#6ee7b7
    style MODULES fill:#042f2e,stroke:#0d9488,color:#99f6e4
```

**Rule 13**: Production modules read ONLY from the Vault. Direct calls to yfinance, requests, httpx, or any external API are **FORBIDDEN** in `backend/modules/`. Only `backend/daemons/` and `backend/scripts/` may call external APIs.
