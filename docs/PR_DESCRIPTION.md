# Payload Dashboard — Portfolio, Agents & Theme Overhaul

## Summary

Full-stack feature branch that delivers **four major capabilities** on top of the existing Hexagonal Architecture backend:

1. **Portfolio Management** — Clean Architecture collection with settings UI, membership hooks, and auth provider refactor.
2. **AI Agent Infrastructure** — Bots × AgentSkills × McpServers collections with Anthropic integration, agent lifecycle sync, and a real-time chat interface.
3. **Admin Dashboard Widgets** — Claude token consumption and Postgres performance monitoring panels.
4. **UI Polish** — HeroUI theme variables, hero type safety, auth button streamlining, and 404 page improvements.

---

## What Changed

### 1. Portfolio Collection & Auth Refactor
> Commits: `165268f`, `a01a66d`, `371da0c`

- **New settings routes**: `portafolio/[slug]/settings/` with rename form, profile form, and member management pages.
- **Clean Architecture lifecycle**: slug + owner auto-generation hook, owner membership creation hook, and `PayloadPortfolioCreator` adapter implementing `PortfolioCreator` port.
- **Auth provider rewrite**: Monolithic `Auth.ts` → `Auth/index.tsx` (client provider) + `Auth/server.ts` (server utility). Improved `getMeUser` with proper redirect handling.
- **Hero components**: Added explicit TypeScript generics for `Page` and `Post` media types; removed unsafe type assertions.
- **Auth pages**: Standardized all 7 auth pages to use `variant="shadow"` button styling and corrected redirect paths.

### 2. AI Agent & Bot Infrastructure
> Commits: `f0c68c9`, `f8629c6`, `5bf9c43`, `8a82c36`

- **3 new Payload collections**:
  - `AgentSkills` — skill definitions with domain validation rules
  - `McpServers` — MCP server registry with connection config and tool manifests
  - `Bots` (extended) — added `slug`, `systemPrompt`, `model`, `maxTokens`, `mcpServers` relationship, and `agentStatus` fields
- **Anthropic adapter** (`anthropicAgentAdapter.ts`): Handles agent creation, synchronization, and archival against the Anthropic API.
- **Lifecycle hooks**: `syncAgentOnSave` (provisions/updates agent on Anthropic), `archiveAgentOnDelete`, `generateBotSlug`.
- **Chat API route** (`/api/agent/[slug]/chat`): Streaming endpoint that looks up the bot, validates auth, and proxies to Anthropic.
- **AgentChat component** (`src/components/AgentChat/`):
  - Real-time streaming chat with `MarkdownRenderer` (react-markdown + syntax highlighting)
  - `MermaidBlock` for rendering Mermaid diagrams in agent responses
  - Moved from page-level to shared component for reuse

### 3. Admin Dashboard Widgets
> Commit: `7383504`

- **ClaudeTokenConsumptionWidget**: Refactored for cleaner data flow, added model breakdown, and improved chart styling.
- **PostgresPerformanceWidget**: Refactored with better connection pool visualization and query latency metrics.
- Both widgets updated env example with required API keys.

### 4. Theme & UI Polish
> Commits: `165268f`, `5bf9c43`, `8a82c36`

- **HeroUI theme CSS**: Comprehensive light/dark mode CSS custom properties covering surfaces, foregrounds, borders, focus rings, dividers, and content layers.
- **404 page**: Enhanced layout and styling for the frontend not-found page.
- **Payload admin**: Added `custom.scss` for admin panel visual tweaks.

---

## New Files

| Path | Purpose |
|------|---------|
| `src/collections/AgentSkills/` | Skill collection + domain rules |
| `src/collections/McpServers/` | MCP server registry collection |
| `src/collections/Bots/infrastructure/` | Anthropic adapter + lifecycle hooks |
| `src/components/AgentChat/` | Chat UI with Markdown & Mermaid rendering |
| `src/app/api/agent/[slug]/chat/route.ts` | Streaming chat API endpoint |
| `src/app/(frontend)/agent/` | Agent chat frontend pages |
| `src/app/(frontend)/(settings)/portafolio/[slug]/settings/` | Portfolio settings UI (7 files) |
| `src/collections/Portfolios/interface/` | Service + hooks (slug, ownership) |
| `src/collections/Portfolios/infrastructure/PayloadPortfolioCreator.ts` | Port adapter |
| `src/collections/Portfolios/domain/ports/PortfolioCreator.ts` | Domain port |
| `src/providers/Auth/index.tsx` | Client-side auth provider |
| `src/providers/Auth/server.ts` | Server-side auth utility |
| `src/scripts/seedAgentSkills.ts` | Seed script for default agent skills |

## Deleted Files

| Path | Reason |
|------|--------|
| `src/providers/Auth.ts` | Replaced by `Auth/index.tsx` + `Auth/server.ts` |
| `src/collections/Portfolios/domain/useCases/createOwnerMembership.ts` | Moved to `interface/hooks/` |

---

## Architecture Compliance

All new code follows Clean Architecture boundaries:

| Component | Layer | Compliance |
|-----------|-------|------------|
| `AgentSkills/domain/rules/` | Domain | ✅ No infrastructure imports |
| `McpServers/domain/rules/` | Domain | ✅ No infrastructure imports |
| `Bots/domain/rules/` | Domain | ✅ No infrastructure imports |
| `Bots/infrastructure/` | Infrastructure | ✅ Depends on domain only |
| `Portfolios/domain/ports/` | Domain | ✅ ABC only |
| `Portfolios/infrastructure/` | Infrastructure | ✅ Implements port |
| `AgentChat` component | UI | ✅ Delegates to API route |
| Auth provider | Infrastructure | ✅ No direct Payload imports in client |

---

## Dependencies Added

```json
{
  "react-markdown": "^9.x",
  "remark-gfm": "^4.x",
  "react-syntax-highlighter": "^15.x",
  "mermaid": "^11.x"
}
```

---

## Changelog

### Phase 1: Import Hygiene & Module Init
- **FIX**: 6 legacy `from modules.` imports → `from backend.modules.` across `shared/use_cases.py`, `alpaca_adapter.py`, `ib_adapter.py`, `evaluate_entry.py`, `qualify_ticker.py`
- **FIX**: Dead import path in `qualify_ticker.py` pointing to non-existent `modules.simulation.domain.feature_engineering`
- **ADD**: `__init__.py` public API exports for 6 modules: `execution`, `flow_intelligence`, `options_gamma`, `pattern_recognition`, `portfolio_management`, `shared`
- **RESTRUCTURE**: `shared/` module migrated to standard 5-folder domain layout (`domain/dtos`, `domain/entities`, `domain/ports`, `domain/rules`, `application/use_cases`)

### Phase 2: Rules Layer Purity
- **EXTRACT**: `import yfinance` and FRED infrastructure import removed from `portfolio_management/domain/rules/macro_regime.py` → data fetching moved to new `infrastructure/macro_data_adapter.py`
- **EXTRACT**: Finnhub adapter import removed from `flow_intelligence/domain/rules/macro_calendar.py` → now accepts injectable `external_events_fetcher` parameter
- **ADD**: `portfolio_management/infrastructure/macro_data_adapter.py` — `YFinanceMacroAdapter` and `FREDMacroAdapter`

### Phase 3: Port Definitions (Hexagonal Backbone)
- **ADD**: 9 new Port ABCs across 5 modules:
  - `options_gamma/domain/ports/options_data_port.py` — `OptionsDataPort`
  - `entry_decision/domain/ports/market_data_port.py` — `EntryMarketDataPort`
  - `entry_decision/domain/ports/flow_data_port.py` — `FlowDataPort`
  - `execution/domain/ports/broker_port.py` — `BrokerPort`
  - `portfolio_management/domain/ports/screener_port.py` — `ScreenerPort`
  - `portfolio_management/domain/ports/fundamental_data_port.py` — `FundamentalDataPort`
  - `portfolio_management/domain/ports/macro_data_port.py` — `MacroDataPort`
  - `flow_intelligence/domain/ports/calendar_data_port.py` — `CalendarDataPort`
  - `flow_intelligence/domain/ports/whale_flow_port.py` — `WhaleFlowPort`
- **MOVE**: `BrokerAdapter` ABC relocated from `infrastructure/brokers/base.py` → `domain/ports/broker_port.py` (old location kept as re-export alias)

### Global Entity Distribution (prior session)
- **DELETE**: `backend/domain/entities.py` (monolithic entity file)
- **DISTRIBUTE**: Entities into their owning modules:
  - `Order`, `Trade`, `Broker` → `execution/domain/entities/order_models.py`
  - `Position`, `Portfolio` → `portfolio_management/domain/entities/portfolio_models.py`
  - `Bar` → `shared/domain/entities/market_data.py`
  - `Signal` → `entry_decision/domain/entities/signal.py`
  - `BacktestResult` → `simulation/domain/entities/simulation_models.py`

### Documentation & Agent Skills
- **ADD**: `.agent/clean_architecture_skill.md` — Comprehensive Hexagonal Architecture skill with import matrix, Port/Adapter patterns, and known violations registry
- **ADD**: `docs/phase4_dependency_injection_plan.md` — Detailed handoff document for Phase 4 completion
- **UPDATE**: `CLAUDE.md` — Reflects new modular architecture, updated layer rules and project structure

---

## Files Changed

| Category | Count |
|---|---|
| Modified | 15 |
| New files | ~35 |
| Deleted | ~20 |
| **Total** | ~70 |

## How to Test

```bash
# 1. Start dev server
pnpm dev

# 2. Verify portfolio settings pages
# Navigate to /portafolio/<slug>/settings

# 3. Verify agent chat
# Create a Bot in admin → navigate to /agent/<slug>

# 4. Verify dashboard widgets
# Open Payload admin dashboard — Claude & Postgres widgets should render

# 5. Verify theme
# Toggle light/dark mode — all HeroUI components should respect theme variables
```

## Breaking Changes

> ⚠️ **Auth provider import path changed**: `src/providers/Auth.ts` → `src/providers/Auth/index.tsx`. All existing imports of `Auth` from providers should auto-resolve via directory index.

> ⚠️ **New env variables required**: `ANTHROPIC_API_KEY`, `CLAUDE_API_KEY`, `PG_CONNECTION_STRING` — see `.env.example`.

> ⚠️ **Payload config updated**: Three new collections (`AgentSkills`, `McpServers` updated `Bots`) registered. Run `pnpm generate` to regenerate types and importMap.
