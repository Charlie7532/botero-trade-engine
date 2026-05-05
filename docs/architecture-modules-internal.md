# Botero Trade — Module Internals (Graphyfi-verified)

> Extraído de Graphyfi graph.json (3387 nodos, 512 archivos) | 2026-05-01

---

## 1. entry_decision — Central Intelligence Hub

```mermaid
graph TB
    subgraph ED["entry_decision"]
        subgraph ED_DOM["domain/"]
            ED_E["entities/<br/>entry_models.py"]
            ED_P["ports/<br/>EntryMarketDataPort (ABC)"]
            ED_R["rules/<br/>entry_rules.py"]
        end
        subgraph ED_APP["application/"]
            ED_UC["use_cases/<br/>evaluate_entry.py<br/>═══════════<br/>EntryIntelligenceHub ⭐CORE<br/>9-step pipeline<br/>_vectorize_report() → pgvector 9D<br/>Memory Guard"]
            ED_DTO["dtos/"]
        end
        subgraph ED_INF["infrastructure/"]
            ED_MDF["MarketDataFetcher<br/>→ implements EntryMarketDataPort<br/>yfinance: OHLCV, VIX, ATR"]
        end
    end

    ED_INF -.->|"implements"| ED_P
    ED_UC --> ED_E & ED_R & ED_P

    %% Cross-module inputs
    FI_IN["flow_intelligence<br/>FlowDataPort"] --> ED_UC
    OG_IN["options_gamma<br/>OptionsDataPort"] --> ED_UC
    PA_IN["price_analysis<br/>PricePhaseIntelligence"] --> ED_UC
    VI_IN["volume_intelligence<br/>VolumeProfile + Kalman"] --> ED_UC
    PR_IN["pattern_recognition<br/>PatternDetector"] --> ED_UC

    ED_UC -->|"EntryIntelligenceReport<br/>verdict: FIRE/STALK/BLOCK"| EX_OUT["execution<br/>PaperTradingOrchestrator"]

    style ED fill:#0f172a,stroke:#3b82f6,color:#93c5fd
    style ED_DOM fill:#1e3a5f,stroke:#60a5fa,color:#bfdbfe
    style ED_APP fill:#1e3a5f,stroke:#60a5fa,color:#bfdbfe
    style ED_INF fill:#1e3a5f,stroke:#60a5fa,color:#bfdbfe
```

**Skills activados:** `fundamental-analyst`, `tactical-entries`, `risk-manager`
**Decisión:** `EntryVerdict` — FIRE (ejecutar) / STALK (esperar) / BLOCK (rechazar)

---

## 2. execution — Order Lifecycle & Dual Exit

```mermaid
graph TB
    subgraph EX["execution"]
        subgraph EX_DOM["domain/"]
            EX_E["entities/<br/>order_models.py · trade_record.py<br/>exit_context.py · trade_context.py<br/>quality_trade_record.py ⭐<br/>speculative_trade_record.py ⭐"]
            EX_P["ports/<br/>BrokerPort (ABC)<br/>TradeJournalPort (ABC)<br/>InstrumentBlacklistPort (ABC) ⭐"]
            EX_R["rules/<br/>exit_rules.py<br/>SpeculativeExitEngine (Seykota)<br/>QualityExitEngine (Druckenmiller)<br/>AdaptiveTrailingStop"]
        end
        subgraph EX_APP["application/"]
            EX_UC["use_cases/<br/>orchestrate_paper_trading.py ⭐CORE<br/>orchestrate_scans.py<br/>execute_order.py<br/>journal_trades.py<br/>monitor_positions.py<br/>surveillance_loop.py ⭐"]
        end
        subgraph EX_INF["infrastructure/"]
            EX_BR["brokers/<br/>alpaca_adapter.py → BrokerPort<br/>ib_adapter.py → BrokerPort<br/>base.py (ABC)<br/>BrokerRegistry {Q↔S} ⭐"]
            EX_PG["postgres_journal_adapter.py<br/>→ TradeJournalPort<br/>JournalRegistry {Q↔S} ⭐"]
            EX_BL["postgres_blacklist_adapter.py<br/>→ InstrumentBlacklistPort ⭐"]
            EX_AD["alpaca_data_adapter.py"]
        end
    end

    EX_INF -.->|"implements"| EX_P
    EX_UC --> EX_E & EX_R & EX_P

    style EX fill:#0f172a,stroke:#ef4444,color:#fca5a5
```

**Skills activados:** `risk-manager`, `cio-allocator`, `trade-forensics`
**Decisiones:** `ExitDecision` (HOLD/CUT/LIQUIDATE), order execution, journal persistence

---

## 3. flow_intelligence — Whale Flow & Macro Events

```mermaid
graph TB
    subgraph FI["flow_intelligence"]
        subgraph FI_DOM["domain/"]
            FI_E["entities/<br/>flow_signals.py<br/>whale_events.py"]
            FI_P["ports/<br/>CalendarDataPort (ABC)"]
            FI_R["rules/<br/>macro_calendar.py<br/>FOMC/CPI/NFP freeze rules"]
        end
        subgraph FI_APP["application/"]
            FI_UC["use_cases/<br/>analyze_whale_flow.py<br/>EventFlowIntelligence<br/>WhaleVerdict: RIDE/LEAN/UNCERTAIN/CONTRA<br/>───<br/>analyze_persistence.py<br/>FlowPersistenceAnalyzer<br/>FRESH→CONFIRMED→DECAYING→DEAD"]
        end
        subgraph FI_INF["infrastructure/"]
            FI_UW["uw_adapter.py + uw_mcp_bridge.py<br/>→ UW MCP (20+ tools)<br/>spy_cum_delta · market_tide<br/>sweep_call_pct · dark_pool"]
            FI_FH["finnhub_adapter.py + finnhub_api.py<br/>→ Finnhub MCP (45 tools)<br/>earnings_calendar · insiders"]
            FI_FR["fred_adapter.py<br/>→ FRED MCP (12 tools)<br/>GDP · CPI · FFR · yield curve"]
            FI_MB["market_breadth_adapter.py<br/>→ Yahoo Finance + UW<br/>S5TH · Fear & Greed"]
        end
    end

    FI_INF -.->|"implements"| FI_P

    style FI fill:#0f172a,stroke:#a855f7,color:#d8b4fe
```

**Skills activados:** `tactical-entries`
**Decisión:** `WhaleVerdict` + `FlowPersistence` → gates en EntryHub

---

## 4. options_gamma — Dealer Positioning

```mermaid
graph TB
    subgraph OG["options_gamma"]
        subgraph OG_DOM["domain/"]
            OG_E["entities/<br/>gamma_models.py<br/>GammaRegime: PIN/DRIFT/SQUEEZE"]
            OG_P["ports/<br/>OptionsDataPort (ABC)"]
            OG_R["rules/<br/>black_scholes.py<br/>opex_calendar.py"]
        end
        subgraph OG_APP["application/"]
            OG_UC["use_cases/<br/>analyze_gamma.py<br/>put_wall · call_wall<br/>gamma_flip · max_pain<br/>GEX regime detection"]
        end
        subgraph OG_INF["infrastructure/"]
            OG_YF["yfinance_adapter.py<br/>→ implements OptionsDataPort<br/>options chain · expiry dates"]
        end
    end

    OG_INF -.->|"implements"| OG_P

    style OG fill:#0f172a,stroke:#f59e0b,color:#fde68a
```

**Skills activados:** `tactical-entries`, `risk-manager`
**Decisión:** `GammaRegime` + structural levels → entry timing gates

---

## 5. portfolio_management — Universe Filter & CIO Orchestration

```mermaid
graph TB
    subgraph PM["portfolio_management"]
        subgraph PM_DOM["domain/"]
            PM_E["entities/<br/>portfolio_models.py<br/>universe_candidate.py (MarketRegime)<br/>candidate_dossier.py<br/>daily_mandate.py<br/>position_allocation.py"]
            PM_P["ports/ (5 ports)<br/>FundamentalDataPort<br/>ScreenerPort<br/>SectorDataPort<br/>MacroDataPort<br/>InstrumentRepoPort"]
            PM_R["rules/ (7 rules)<br/>macro_regime.py (MacroRegimeDetector)<br/>sector_ranker.py<br/>rotation_engine.py<br/>fundamental_filter.py<br/>relative_strength.py<br/>catalyst_detector.py<br/>risk_guardian.py"]
        end
        subgraph PM_APP["application/"]
            PM_UC["use_cases/<br/>cio_orchestrator.py ⭐<br/>filter_universe.py (4-tier pipeline)<br/>scan_alpha.py (AlphaScanner)<br/>qualify_ticker.py<br/>optimize_portfolio.py (HRP)<br/>detect_regime_change.py"]
        end
        subgraph PM_INF["infrastructure/"]
            PM_GF["gurufocus_adapter.py<br/>→ GuruFocus MCP (55 tools)"]
            PM_FV["finviz_adapter.py<br/>→ Finviz MCP (35 tools)"]
            PM_SF["sector_flow_adapter.py"]
            PM_MD["macro_data_adapter.py<br/>→ FRED MCP"]
            PM_PI["payload_instruments_adapter.py<br/>→ PayloadCMS (PG)"]
            PM_SEC["sec_filings_adapter.py<br/>sec_nlp_analyzer.py"]
        end
    end

    PM_INF -.->|"implements"| PM_P

    style PM fill:#0f172a,stroke:#10b981,color:#6ee7b7
```

**Skills activados:** `research-intelligence`, `fundamental-analyst`, `risk-manager`, `cio-allocator`
**Decisiones:** `DailyMandate`, `MarketRegime`, `PositionAllocation`, universe candidates

---

## 6. simulation — Quantitative Validation Lab

```mermaid
graph TB
    subgraph SIM["simulation"]
        subgraph SIM_DOM["domain/"]
            SIM_E["entities/<br/>simulation_models.py<br/>strategy_profile.py<br/>trade_snapshot.py<br/>execution_intent.py"]
            SIM_P["ports/ (10 ports)<br/>HistoricalDataPort · TimeSeriesPort<br/>DataHarmonizerPort · SignalPort<br/>TradingStatePort · MarketStructurePort<br/>BarrierLabelerPort · MLConfidencePort<br/>DashboardSyncPort · VolumeAnalysisPort"]
        end
        subgraph SIM_APP["application/"]
            SIM_UC["use_cases/<br/>run_backtest.py (BacktestRunner)<br/>oracle_backtest.py (OracleBacktester)<br/>calibrate_strategy.py (StrategyCalibrator)<br/>pre_trade_gate.py (11-stage gate)<br/>engineer_features.py (QuantFeatureEngineer)<br/>strategy_composer.py<br/>retrain_trigger.py<br/>analyze_trades.py · analyze_indicators.py"]
        end
        subgraph SIM_INF["infrastructure/"]
            SIM_TS["timescale_data_store.py → TimeSeriesPort"]
            SIM_DH["data_harmonizer.py → DataHarmonizerPort"]
            SIM_SA["signal_adapters.py → SignalPort"]
            SIM_SM["smc_adapter.py → MarketStructurePort"]
            SIM_PS["postgres_trading_state.py → TradingStatePort"]
            SIM_TB["triple_barrier_adapter.py → BarrierLabelerPort"]
            SIM_VI["vault_interceptor.py"]
            SIM_BR["backtest_runner.py"]
        end
    end

    SIM_INF -.->|"implements"| SIM_P

    style SIM fill:#0f172a,stroke:#6366f1,color:#a5b4fc
```

**Skill activado:** `backtesting-trading-strategies` (López de Prado)
**Decisiones:** `CalibrationProfile`, signal weights, VIABLE/OVERFIT verdict

---

## 7. Módulos de Señal (Pure Domain)

```mermaid
graph LR
    subgraph SIGNAL["Módulos sin infraestructura propia"]
        subgraph PA["price_analysis"]
            PA_UC["detect_price_phase.py<br/>FIRE/STALK/ABORT<br/>───<br/>analyze_rsi.py<br/>Cardwell/Brown RSI"]
            PA_R["price_rules.py"]
            PA_E["price_models.py"]
        end

        subgraph VI["volume_intelligence"]
            VI_UC["track_volume_dynamics.py<br/>Kalman Bayesian filter<br/>───<br/>analyze_volume_profile.py<br/>POC/VAH/VAL · P/D/b shapes"]
            VI_R["volume_rules.py"]
            VI_E["volume_models.py"]
        end

        subgraph PR["pattern_recognition"]
            PR_UC["detect_patterns.py<br/>Hammer · Engulfing · VCP<br/>Morning Star · Inside Bar<br/>confirmation_score -1→+1"]
            PR_E["pattern_models.py<br/>PatternVerdict"]
        end
    end

    subgraph RI["rotation_intelligence"]
        RI_UC["rotation_scanner.py<br/>Weinstein + Pring<br/>26 ETFs: sector/intl/asset"]
        RI_P["RotationDataPort (ABC)"]
        RI_E["rotation_snapshot.py"]
        RI_INF["yahoo_rotation_adapter.py<br/>→ yfinance"]
    end

    PA & VI & PR -->|"signals"| HUB["entry_decision<br/>EntryIntelligenceHub"]
    RI -->|"sector_flows<br/>stage_transitions"| PM["portfolio_management<br/>CIO Orchestrator"]

    style SIGNAL fill:#0f172a,stroke:#94a3b8,color:#e2e8f0
    style RI fill:#0f172a,stroke:#10b981,color:#6ee7b7
```

**Skills:** `tactical-entries` (PA, VI, PR) · `rotation-analyst` + `cio-allocator` (RI)

---

## 8. shared — Cross-Module Foundation

| Component | Location | Purpose |
|---|---|---|
| `Bar`, market types | `domain/entities/market_data.py` | Typed dataclasses para OHLCV |
| `shared_use_cases.py` | `application/use_cases/` | Delegation hub |
| `cache_utils.py` | `infrastructure/` | TTL cache + retry with backoff |
| Skills | `operational-purpose` + `clean-architecture` only | Architecture baseline |
