# Botero Trade: Cognitive Architecture & Skill System

## Overview

The Botero Trade system uses a multi-layered, department-scoped cognitive architecture. This ensures that AI agents (whether functioning via CrewAI, OpenAI CLI, or Gemini) strictly adhere to institutional logic and avoid conflating distinct financial paradigms. 

The system strictly enforces a "Zero-Bias" quantitative philosophy, structurally separating **QUALITY** (long-term tollkeeper investing) from **SPECULATIVE** (tactical asymmetric trading).

---

## Architectural Layers

The skill system operates on a hierarchy of instructions. Agents assemble their `system_prompt` by stacking these layers from the bottom up:

1. **Baseline**: Unbreakable foundational rules (Clean Architecture, Zero-Bias).
2. **Router**: Orchestration logic that determines which department or persona to load.
3. **Department**: Institutional manifests that dictate entry gates, exit rules, and data interpretation for the allocated capital pool.
4. **Persona**: Specialized financial experts (e.g., Munger, Druckenmiller, Seykota, Simons) that provide domain-specific cognitive logic.
5. **Tool**: Surgical skills for specific technical or forensic operations.

---

## Skill Inventory by Department

### 🌐 GLOBAL / BASELINE (Active everywhere)
*These skills form the foundational mindset and routing logic for the entire system.*

| Skill | Layer | Description |
|---|---|---|
| `operational-purpose` | Baseline | Enforces pragmatic, Zero-Bias institutional mechanics. Disables generic AI financial disclaimers. |
| `clean-architecture` | Baseline | Strict Hexagonal Architecture rulebook. Prevents external API imports in the domain layer. |
| `expert-mode` | Router | Universal orchestrator. Executes Step 0 (Department Resolution) to load the correct context. |
| `module-skill-map` | Router | Matrix mapping backend Python modules to their appropriate cognitive skills. |

### 🏛️ QUALITY DEPARTMENT (80% Allocation)
*Long-term holding of essential "tollkeeper" businesses. Driven by thesis, exited only on thesis death.*

| Skill | Layer | Persona | Description |
|---|---|---|---|
| `department-quality` | Dept | — | The authoritative manifest. Blocks entries on `CONTRA_FLOW`. Forbids mechanical stops. |
| `fundamental-analyst` | Persona | Hohn / Munger | Deep forensic fundamental analysis, 7-Powers moat stress-testing, and Inversion Thinking. |
| `risk-quality` | Persona | Druckenmiller | "Go for the jugular" sizing. Manages thesis-based exits. Ignores intraday volatility. |

### ⚡ SPECULATIVE DEPARTMENT (20% Allocation)
*Tactical, asymmetric setups. Driven by market structure, gamma, and rigid risk management.*

| Skill | Layer | Persona | Description |
|---|---|---|---|
| `department-speculative` | Dept | — | The authoritative manifest. Permits tactical entries against flow. Enforces mechanical stops. |
| `tactical-entries` | Persona | PTJ / Eifert / Karsan | Options microstructure, 5:1 asymmetric entries, dealer gamma positioning (GEX, Vanna, Charm). |
| `signal-miner` | Persona | Jim Simons | Discovers non-intuitive mathematical anomalies in the data vault. |
| `risk-speculative` | Persona | Ed Seykota | Ruthless mechanical risk. ATR stops, time stops, anti-martingale sizing, Memory Guard. |

### 🦅 CIO & SERVICE (Cross-Department)
*Macro orchestration and independent intelligence gathering.*

| Skill | Layer | Persona | Description |
|---|---|---|---|
| `cio-allocator` | Persona | Ray Dalio | Orchestrates capital flow between Quality and Speculative based on macro liquidity (FRED). |
| `rotation-analyst` | Persona | Weinstein / Pring | Stage analysis, sector strength, and intermarket (bonds → stocks → commodities) rotation. |
| `research-intelligence`| Persona | — | Service department. Delivers pre-qualified dossiers to the CIO without making allocation decisions. |

### 🔬 VALIDATION (Quantitative Pipeline)
*Post-discovery scientific validation and post-trade autopsy.*

| Skill | Layer | Persona | Description |
|---|---|---|---|
| `backtesting-trading-strategies` | Tool | López de Prado | Rigorous scientific walk-forward analysis. Triple-barrier labeling, Purged CV, Deflated Sharpe. |
| `trade-forensics` | Tool | — | Closed-loop autopsy. Detects pattern failures, calibrates stops, and enforces blacklists. |

### ⚙️ FRONTEND & INFRASTRUCTURE
*Payload CMS and Next.js Next-Gen Architecture.*

| Skill | Layer | Description |
|---|---|---|
| `payload-access-policy-audit` | Tool | Secures multi-tenant access, standardizes `overrideAccess` usage. |
| `payload-hook-first-use-case` | Tool | Extracts business logic out of Payload hooks into Clean Architecture use cases. |
| `payload-lifecycle-manifest` | Tool | Normalizes collection lifecycle and generic handlers. |
| `payload-route-boundary-standardizer`| Tool | Keeps Next.js API routes thin, delegating to feature services. |

---

## Conflict Guardrails

To prevent cognitive dissonance, the `skill-graph.yaml` enforces hard conflicts. These skills must **never** be loaded in the same context unless orchestrated strictly by the CIO:

1. ❌ `fundamental-analyst` (Quality) + `signal-miner` (Speculative)
2. ❌ `risk-quality` (No stops) + `risk-speculative` (Mechanical stops)
3. ❌ `department-quality` + `department-speculative` (Mutually exclusive pipelines)

## Integration with the Codebase

All backend modules are explicitly mapped to these skills. For example, the `entry_decision` module uses `QualityEntryGate` (Quality context) and `SpeculativeEntryHub` (Speculative context). Shared modules like `volume_intelligence` load different skill configurations depending on which department is requesting the analysis.
