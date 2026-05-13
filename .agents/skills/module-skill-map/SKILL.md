---
name: module-skill-map
description: |
  Maps each backend module to the skills that should be activated when that
  module is referenced. Use this to ensure consistent context, architecture
  compliance, and domain-specific expertise whenever working on any module.
department: ALL
layer: router
crewai_role: lookup
---

# Module → Skill Activation Map

When any agent works on a backend module, activate the skills listed for that module.
**`clean-architecture` and `operational-purpose` are ALWAYS active for all modules.**

---

## Activation Matrix

| Module | Department | Always | Domain-Specific Skills | Why |
|---|---|---|---|---|
| `entry_decision` | BOTH | `clean-architecture`, `operational-purpose` | QUALITY: `fundamental-analyst`, `risk-quality`. SPECULATIVE: `tactical-entries`, `risk-speculative` | Separate pipelines — `QualityEntryGate` vs `SpeculativeEntryHub` |
| `execution` | BOTH | `clean-architecture`, `operational-purpose` | QUALITY: `risk-quality`, `cio-allocator`. SPECULATIVE: `risk-speculative` | Order lifecycle, broker adapters — department-scoped risk |
| `flow_intelligence` | SPECULATIVE | `clean-architecture`, `operational-purpose` | `tactical-entries` | Whale flows, sweeps, institutional positioning — pure microstructure |
| `options_gamma` | SPECULATIVE | `clean-architecture`, `operational-purpose` | `tactical-entries`, `risk-speculative` | GEX, Max Pain, gamma regime — Speculative entry timing + risk |
| `pattern_recognition` | BOTH | `clean-architecture`, `operational-purpose` | QUALITY: `department-quality` (Gate 5). SPECULATIVE: `tactical-entries` | Candlestick/technical patterns — QUALITY uses as veto gate, SPECULATIVE uses for timing |
| `portfolio_management` | QUALITY | `clean-architecture`, `operational-purpose` | `research-intelligence`, `fundamental-analyst`, `risk-quality`, `cio-allocator` | Universe filtering, alpha scanning, CIO budget, watchlist |
| `price_analysis` | BOTH | `clean-architecture`, `operational-purpose` | QUALITY: `department-quality` (Gates 3-4). SPECULATIVE: `tactical-entries` | RSI + phase — QUALITY uses as binary gate, SPECULATIVE uses for tactical timing |
| `rotation_intelligence` | SERVICE | `clean-architecture`, `operational-purpose` | `rotation-analyst`, `cio-allocator` | Sector/international rotation — feeds CIO |
| `shared` | — | `clean-architecture`, `operational-purpose` | *(none)* | Foundational types and shared ports |
| `simulation` | VALIDATION | `clean-architecture`, `operational-purpose` | `backtesting-trading-strategies`, `trade-forensics` | Backtesting engine — López de Prado validation + MAE/MFE forensics |
| `signal_discovery` | SPECULATIVE | `clean-architecture`, `operational-purpose` | `signal-miner`, `backtesting-trading-strategies` | Statistical anomaly mining → validated via simulation |
| `volume_intelligence` | BOTH | `clean-architecture`, `operational-purpose` | QUALITY: `department-quality` (Gate 1). SPECULATIVE: `tactical-entries` | VP analysis — QUALITY uses for institutional bias check, SPECULATIVE uses for POC/VAH/VAL |
| `volatility_regime` | SERVICE | `clean-architecture`, `operational-purpose` | `vol-regime-intelligence` | Vol state machine — consumed by entry gates, risk managers, CIO |

---

## Visual Map

```
                        ┌─────────────────────┐
                        │   ALWAYS ACTIVE      │
                        │  clean-architecture  │
                        │  operational-purpose │
                        └────────┬────────────┘
                                 │
                    ┌────────────┼────────────┐
                    │                         │
              ┌─────▼──────┐           ┌─────▼──────┐
              │ DEPARTMENT │           │ DEPARTMENT │
              │  QUALITY   │           │ SPECULATIVE│
              └─────┬──────┘           └─────┬──────┘
                    │                        │
         ┌─────────┼─────────┐    ┌──────────┼──────────┐
         │         │         │    │          │          │
   ┌─────▼───┐ ┌───▼────┐ ┌─▼──┐ ┌▼─────┐ ┌──▼──┐ ┌────▼────┐
   │FUND.    │ │RISK    │ │CIO │ │TACT. │ │RISK │ │SIGNAL   │
   │ANALYST  │ │QUALITY │ │    │ │ENTRY │ │SPEC │ │MINER    │
   └────┬────┘ └───┬────┘ └─┬──┘ └──┬───┘ └──┬──┘ └────┬────┘
        │          │        │       │        │         │
  portfolio_mgmt  exec    rotation flow    exec     signal_disc
  entry_decision  port_m   intel   opt_γ   opt_γ    simulation
                                   price   entry
                                   volume
```

---

## How to Use This Map

### For Agents (Antigravity, Gemini, Claude)
When the user references or works on a module, read this map and activate the corresponding skills before responding. Read each activated skill's `SKILL.md` file for behavioral rules and output formats.

### For the `/me` Command
The `/me` command already auto-routes to specialist skills based on prompt content. This map adds module-level routing: if the prompt mentions a module path like `backend/modules/options_gamma/`, activate the skills listed here.

### For New Modules
When creating a new module, add it to this map and assign the appropriate skills. Every module gets `clean-architecture` + `operational-purpose` at minimum.

---

## Module Descriptions (Quick Reference)

| Module | Purpose | Key Use Cases |
|---|---|---|
| `entry_decision` | Department-scoped entry gate — `QualityEntryGate` (QUALITY) and `SpeculativeEntryHub` (SPECULATIVE) | `quality_entry_gate`, `speculative_entry_hub` |
| `execution` | Order management, broker adapters (Alpaca, IB), trade journaling, position monitoring | `execute_order`, `orchestrate_paper_trading`, `journal_trades` |
| `flow_intelligence` | Whale flow analysis (Unusual Whales), macro event calendar, flow persistence signals | `analyze_whale_flow`, `analyze_persistence` |
| `options_gamma` | Gamma regime detection (PIN/DRIFT/SQUEEZE), Max Pain, GEX, Black-Scholes, OpEx calendar | `analyze_gamma` |
| `pattern_recognition` | Candlestick and technical pattern detection (reversals, continuations) | `detect_patterns` |
| `portfolio_management` | Universe filtering, alpha scanning, position sizing, ticker qualification | `filter_universe`, `scan_alpha`, `qualify_ticker`, `optimize_portfolio` |
| `price_analysis` | RSI regime-aware interpretation (Cardwell/Brown), price phase detection | `analyze_rsi`, `detect_price_phase` |
| `shared` | Cross-cutting types: `Bar`, `MarketDataPort`, `ExecutionPort` | Foundation for all modules |
| `simulation` | Walk-forward backtesting, trade autopsy, feature engineering | `run_backtest`, `analyze_trades`, `engineer_features` |
| `signal_discovery` | Non-intuitive statistical signal mining (Simons methodology) | `discover_anomalies`, `monitor_signal_decay`, `scan_cross_asset` |
| `volume_intelligence` | Volume Profile analysis (POC, VAH, VAL, shapes), volume dynamics tracking | `analyze_volume_profile`, `track_volume_dynamics` |
| `volatility_regime` | Vol regime classification (COMPLACENT/NORMAL/ELEVATED/CRISIS for Quality; STALK/STRIKE/HARVEST/RETREAT for Speculative) | `classify_quality_regime`, `classify_speculative_regime` |
