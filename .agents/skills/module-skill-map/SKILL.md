---
name: module-skill-map
description: |
  Maps each backend module to the skills that should be activated when that
  module is referenced. Use this to ensure consistent context, architecture
  compliance, and domain-specific expertise whenever working on any module.
---

# Module → Skill Activation Map

When any agent works on a backend module, activate the skills listed for that module.
**`clean-architecture` and `operational-purpose` are ALWAYS active for all modules.**

---

## Activation Matrix

| Module | Always | Domain-Specific Skills | Why |
|---|---|---|---|
| `entry_decision` | `clean-architecture`, `operational-purpose` | `fundamental-analyst`, `tactical-entries`, `risk-manager` | Hub that gates all entries — needs fundamental quality, tactical precision, AND risk assessment |
| `execution` | `clean-architecture`, `operational-purpose` | `risk-manager` | Order lifecycle, broker adapters, position monitoring — risk is the governing constraint |
| `flow_intelligence` | `clean-architecture`, `operational-purpose` | `tactical-entries` | Whale flows, sweeps, institutional positioning — pure microstructure |
| `options_gamma` | `clean-architecture`, `operational-purpose` | `tactical-entries`, `risk-manager` | GEX, Max Pain, gamma regime — drives entry timing AND risk regime detection |
| `pattern_recognition` | `clean-architecture`, `operational-purpose` | `tactical-entries` | Candlestick/technical patterns — visual structure for entry timing |
| `portfolio_management` | `clean-architecture`, `operational-purpose` | `fundamental-analyst`, `risk-manager` | Universe filtering, alpha scanning, position sizing — quality + risk governance |
| `price_analysis` | `clean-architecture`, `operational-purpose` | `tactical-entries` | RSI, price phase detection — technical structure analysis |
| `shared` | `clean-architecture`, `operational-purpose` | *(none)* | Foundational types and shared ports — architecture-only |
| `simulation` | `clean-architecture`, `operational-purpose` | `backtesting-trading-strategies` | Backtesting engine — directly maps to the backtesting skill |
| `volume_intelligence` | `clean-architecture`, `operational-purpose` | `tactical-entries` | Volume profile, POC/VAH/VAL — institutional volume microstructure |

---

## Visual Map

```
                        ┌─────────────────────┐
                        │   ALWAYS ACTIVE      │
                        │  clean-architecture  │
                        │  operational-purpose │
                        └────────┬────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
  ┌─────▼──────┐          ┌─────▼──────┐          ┌─────▼──────┐
  │ FUNDAMENTAL │          │  TACTICAL   │          │    RISK     │
  │  ANALYST    │          │  ENTRIES    │          │  MANAGER    │
  └─────┬──────┘          └─────┬──────┘          └─────┬──────┘
        │                       │                       │
  ┌─────┘                 ┌─────┼─────┐           ┌────┘
  │                       │     │     │           │
  ▼                       ▼     ▼     ▼           ▼
portfolio_mgmt    flow_intel  price  volume    execution
entry_decision    options_γ  pattern  entry    options_γ
                  entry_dec          decision  portfolio_mgmt
                                               entry_decision
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
| `entry_decision` | Central gate for all trade entries — aggregates signals from all intelligence modules | `evaluate_entry` |
| `execution` | Order management, broker adapters (Alpaca, IB), trade journaling, position monitoring | `execute_order`, `orchestrate_paper_trading`, `journal_trades` |
| `flow_intelligence` | Whale flow analysis (Unusual Whales), macro event calendar, flow persistence signals | `analyze_whale_flow`, `analyze_persistence` |
| `options_gamma` | Gamma regime detection (PIN/DRIFT/SQUEEZE), Max Pain, GEX, Black-Scholes, OpEx calendar | `analyze_gamma` |
| `pattern_recognition` | Candlestick and technical pattern detection (reversals, continuations) | `detect_patterns` |
| `portfolio_management` | Universe filtering, alpha scanning, position sizing, ticker qualification | `filter_universe`, `scan_alpha`, `qualify_ticker`, `optimize_portfolio` |
| `price_analysis` | RSI regime-aware interpretation (Cardwell/Brown), price phase detection | `analyze_rsi`, `detect_price_phase` |
| `shared` | Cross-cutting types: `Bar`, `MarketDataPort`, `ExecutionPort` | Foundation for all modules |
| `simulation` | Walk-forward backtesting, trade autopsy, feature engineering | `run_backtest`, `analyze_trades`, `engineer_features` |
| `volume_intelligence` | Volume Profile analysis (POC, VAH, VAL, shapes), volume dynamics tracking | `analyze_volume_profile`, `track_volume_dynamics` |
