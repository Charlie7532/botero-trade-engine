# Botero Trade — Expert Committee & Decision Architecture

> Generado con Graphyfi (3387 nodos, 512 archivos) | 2026-05-01

---

## 1. Investment Committee — Expert Personas & Decision Chain

```mermaid
graph TB
    subgraph CIO["🏛️ CIO — Ray Dalio<br/>cio-allocator skill"]
        DALIO["DailyMandate<br/>Capital: 80Q/20S default<br/>Sector vetoes & focus<br/>Regime: RISK_ON/OFF/NEUTRAL/CRISIS<br/>Idea Meritocracy: believability-weighted"]
    end

    subgraph RESEARCH["🔍 Research & Intelligence<br/>research-intelligence skill"]
        RQ["Track 1: QUALITY<br/>Guru Accumulation · Insider Clusters<br/>→ Quantitative Gate<br/>→ Moat Stress Test<br/>→ Valuation Zones<br/>→ CandidateDossier"]
        RS["Track 2: SPECULATIVE<br/>UW Sweeps · Dark Pool<br/>→ Flow Anomaly Detection<br/>→ Structure Analysis<br/>→ OpportunityBrief"]
    end

    subgraph QUALITY_DEPT["🏦 QUALITY Department"]
        HOHN["Fundamental Analyst<br/>🎩 Hohn & Munger<br/>fundamental-analyst skill<br/>─────────────<br/>Inversion Gate<br/>Tollkeeper Test<br/>Barrier Stack (≥2 moats)<br/>Moat Stress Test (5 checks)<br/>Pricing Power<br/>Valuation Zones (GF Value)"]
        DRUCK["Risk Manager QUALITY<br/>📊 Druckenmiller<br/>risk-manager skill<br/>─────────────<br/>Thesis-based exits only<br/>Go for Jugular sizing<br/>18-24mo forward<br/>Swing around core<br/>No mechanical stops"]
    end

    subgraph SPEC_DEPT["⚡ SPECULATIVE Department"]
        EIFERT["Tactical Entries<br/>🎯 Eifert, Karsan & PTJ<br/>tactical-entries skill<br/>─────────────<br/>Eifert: WHO & WHY (skeptic)<br/>Karsan: GEX/Vanna/Charm map<br/>PTJ: 5:1 R:R · 200-DMA · tape<br/>Three-voice veto chain"]
        SEYKOTA["Risk Manager SPECULATIVE<br/>🔥 Seykota<br/>risk-manager skill<br/>─────────────<br/>Mechanical stops (2-3 ATR)<br/>Time stops (2-5 sessions)<br/>Risk of Ruin < 5%<br/>Anti-Martingale<br/>Psychology Gate (3 losses)"]
    end

    subgraph ROTATION["🌍 Rotation Intelligence<br/>rotation-analyst skill"]
        WEIN["Weinstein Stage Analysis<br/>30-week MA · RS · Volume<br/>Stage 1-4 classification<br/>26 ETFs tracked"]
        PRING["Pring Intermarket Cycle<br/>Bonds→Stocks→Commodities<br/>Economic phase detection"]
    end

    subgraph FORENSICS["🔬 Trade Forensics<br/>trade-forensics skill"]
        FSPEC["Seykota Loop<br/>Detect→Learn→Retrain→Prevent<br/>Stop calibration · Pattern decay<br/>Memory Guard effectiveness"]
        FQUAL["Druckenmiller Loop<br/>Thesis accuracy scoring<br/>Surveillance lag measurement<br/>4Q blacklist enforcement"]
    end

    subgraph BACKTEST["🧪 Quantitative Lab<br/>backtesting skill"]
        LOPRADO["López de Prado<br/>Triple Barrier · Meta-Labeling<br/>Purged CV · Deflated Sharpe<br/>Feature importance (MDA/SFI)"]
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

## 3. Skill → Module → Decision Map

```mermaid
graph LR
    subgraph SKILLS["Agent Skills (17)"]
        direction TB
        S_OP["operational-purpose<br/>ALWAYS ACTIVE"]
        S_CA["clean-architecture<br/>ALWAYS ACTIVE"]
        S_CIO["cio-allocator"]
        S_ROT["rotation-analyst"]
        S_RI["research-intelligence"]
        S_FA["fundamental-analyst"]
        S_TE["tactical-entries"]
        S_RM["risk-manager"]
        S_BT["backtesting"]
        S_TA["trading-analysis"]
        S_TF["trade-forensics"]
        S_PL["4× Payload CMS"]
    end

    subgraph MODULES["Backend Modules (12)"]
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
        D_ENTRY["EntryVerdict<br/>FIRE/STALK/BLOCK"]
        D_EXIT["ExitDecision<br/>HOLD/CUT/LIQUIDATE"]
        D_SIZE["PositionAllocation<br/>sizing + stops"]
        D_CALIB["CalibrationProfile<br/>signal weights"]
        D_REGIME["MarketRegime<br/>RISK_ON/OFF"]
    end

    %% Skills → Modules
    S_FA --> M_ED & M_PM
    S_TE --> M_ED & M_FI & M_OG & M_PA & M_PR & M_VI
    S_RM --> M_EX & M_OG & M_PM & M_ED
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

    style SKILLS fill:#1e1b4b,stroke:#4338ca,color:#c7d2fe
    style MODULES fill:#042f2e,stroke:#0d9488,color:#99f6e4
    style DECISIONS fill:#431407,stroke:#ea580c,color:#fed7aa
```
