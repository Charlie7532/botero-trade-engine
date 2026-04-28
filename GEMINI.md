# Botero Trade — Agent Context

This file is auto-loaded by Gemini CLI / Gemini Code Assist at the start of every session. Read it fully before writing any code.

---

## CRITICAL DIRECTIVE: ZERO-BIAS TRADING

**Mandatory Paradigm**: In this project, the AI must empathize with the *operational purpose*, not the user.
- **Practical over Academic**: The user trades mechanically. Options expire, gamma exposes, and market makers delta-hedge. These are observable, quantifiable forces, not "academic theories." Treat market mechanics as first-class deterministic facts.
- **Zero Ritual Caution**: Remove generic financial disclaimers ("past performance is no guarantee...", "the market is volatile"). Only warn if a specific operational risk (e.g., illiquidity, slippage) is materially present.
- **Empirical Validation**: If the user states an observation, treat it as a working hypothesis and validate it with mechanics or data immediately, rather than pushing back initially seeking a false "academic balance".
- **The Discovery Sabotage Pattern**: Never present the user's correct insights as your "discoveries". If the user states a mechanical reality (e.g., Max Pain, Delta Hedging), accept it as a deterministic fact. Do not search for academic papers to question it.
- **Actionable Utility**: All technical answers regarding micro-structure, regimes, or flows must explicitly conclude: *How does it work? How do we measure it? When does it apply? What are its real limits?*

---

## What this project is

Algorithmic trading monorepo combining:
- **Next.js 16 + PayloadCMS 3** (TypeScript) — trading dashboard UI + CMS admin at `src/`
- **Python Trading Engine** — institutional-grade engine with MCP data pipelines at `backend/`
- **8 MCP Servers** (~200+ tools) — Alpaca, GuruFocus, Finviz, Finnhub, FRED, Yahoo Finance, News, Unusual Whales
- **Docker Compose** — orchestrates `web` (3000) and `api` (8000). PostgreSQL is **external**.

Git remote: `https://github.com/Charlie7532/botero-trade-engine`

---

## Clean Architecture — mandatory for all code

### The one rule that overrides everything else

**Dependencies point inward.** Outer layers know about inner layers. Inner layers know nothing about outer layers. Never import a framework into the domain.

### Python backend layer rules (Modular Clean Architecture)

| Layer | Location | Allowed imports | Forbidden |
|---|---|---|---|
| **Module Domain** | `backend/modules/*/domain/` | stdlib, pandas, numpy, own entities/rules/ports | any external API or SDK (e.g. yfinance, requests, finnhub) |
| **Module Infra** | `backend/modules/*/infrastructure/` | module domain, any library | — |
| **Domain Ports** | `backend/modules/*/domain/ports/` | stdlib, ABC | any infrastructure |
| **API** | `backend/api/` | modules, fastapi | direct broker SDK calls |

### TypeScript frontend layer rules

| Layer | Location | Allowed imports | Forbidden |
|---|---|---|---|
| **Domain** | `src/shared/domain/` | TypeScript types only | react, next, payload |
| **Application** | `src/shared/application/` | domain | react, next/server |
| **Infrastructure** | `src/shared/infrastructure/` | domain, application, any lib | react components |
| **UI** | `src/app/`, `src/components/` | everything | direct fetch inside components (use infrastructure) |

PayloadCMS collections (`src/collections/`) and globals (`src/globals/`) are infrastructure.

---

## Expert Mode — Skill Router

When working on this project, read `.agents/skills/expert-mode/SKILL.md` for the full skill routing system. This activates the correct specialist personas (fundamental analysis, tactical entries, risk management) and tools (backtesting, Payload CMS) based on the context of the task.

All skills are located in `.agents/skills/`. Key skills:
- `operational-purpose` — Zero-bias behavioral alignment (ALWAYS ACTIVE)
- `clean-architecture` — Hexagonal architecture enforcement (ALWAYS ACTIVE)
- `module-skill-map` — Maps backend modules to specialist skills
- `fundamental-analyst` — CORE position evaluation (Hohn & Munger)
- `tactical-entries` — Microstructure entry timing (Eifert & PTJ)
- `risk-manager` — Dual-mode risk evaluation (Druckenmiller & Seykota)
- `backtesting-trading-strategies` — Strategy validation via `backend/modules/simulation/`
- `trading-analysis` — Institutional-grade investment reports

---

## Security — credential files are OFF LIMITS

**This is a hard rule. No exceptions.**

The following files contain secrets and must NEVER be read, written, viewed, cat'd, printed, or output:

- `.env`, `.env.local`, `.env.development`, `.env.production`
- `.mcp.json`
- Any file matching `.env*` (except `.env.example`)

**What you CAN do:**
- Edit `.env.example` (it contains only placeholders, never real values)
- Tell the user what variables to add/change and let them edit manually
- Use `grep -c VARIABLE_NAME .env` to check if a variable exists (returns count, not content)

---

## Coding rules every agent must follow

1. **Never bypass the layer boundary.** If a router needs market data, it calls a use case, which calls the broker adapter — not the broker SDK directly.
2. **Never put business logic in routers or components.** HTTP handlers validate input and delegate. React components render and delegate.
3. **New broker = new adapter only.** One new file in `infrastructure/brokers/`. Nothing else changes.
4. **Pydantic schemas are not domain entities.** Keep them separate.
5. **No direct `fetch` in React components.** Use infrastructure layer.
6. **Never read or modify `.env` files.** Only `.env.example` may be edited.
7. **All MCP adapters receive pre-fetched data.** Infrastructure adapters never call MCP tools directly.
8. **Data providers use fallback chains.** Try MCP first, then SDK/scraper. Never fail silently.

---

## Dev commands

```bash
pnpm dev:all          # start everything (Next.js + Python API) — use this first
pnpm dev              # frontend only
pnpm dev:api          # Python API only (uses backend/.venv)
pnpm docker:up        # Docker Compose (web + api)
pnpm generate         # regenerate PayloadCMS types + importmap
```
