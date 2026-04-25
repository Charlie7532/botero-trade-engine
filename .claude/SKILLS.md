# Botero Trade — Available Commands & Skills

This file documents all slash commands and shared skills available in this project.

---

## Commands (`.claude/commands/`)

Claude-specific slash commands. Type `/command-name` in Claude Code to invoke.

### Operational

| Command | Purpose |
|---|---|
| `/me` | **Expert mode.** Activates zero-bias analysis + clean architecture + auto-routes to specialist skills based on prompt |
| `/start` | Launch all services in **production** mode (Docker or local) |
| `/dev` | Bootstrap full **development** environment with hot reload |
| `/stop` | Kill all running servers and free ports |
| `/pr` | **Full PR workflow.** Branch → commit → push → PR with summary, file changes, test checklist, mermaid diagrams → return to main |
| `/cln` | Load Clean & Hexagonal Architecture standards |
| `/context` | Load full project architecture reference (entities, endpoints, tech stack) |

### Guided Workflows

| Command | Purpose |
|---|---|
| `/add-strategy` | Step-by-step: create a new Backtrader trading strategy |
| `/add-broker` | Step-by-step: integrate a new broker adapter |

### Specialist Personas (auto-activated by `/me`)

| Command | Persona | Use when... |
|---|---|---|
| `/analista-filtrado` | Hohn & Munger | Evaluating fundamental quality, moats, pricing power, CORE positions |
| `/ejecutor-entradas` | Eifert & PTJ | Tactical entries, options flow, GEX, tape reading, microstructure |
| `/gestor-riesgos` | Druckenmiller & Seykota | Evaluating open positions, trailing stops, exit decisions |
| `/proposito-practico` | Zero-bias mode | AI losing focus on practical mechanics or showing excessive caution |

---

## Shared Skills (`.agents/skills/`)

Agent-agnostic skills usable by Claude, Antigravity, and Gemini.

### Core

| Skill | Purpose |
|---|---|
| `operational-purpose` | Zero-bias behavioral alignment — removes disclaimers, forces mechanical truth |
| `clean-architecture` | Clean & Hexagonal Architecture enforcement for the Botero Trade codebase |

### Trading Tools

| Skill | Purpose |
|---|---|
| `backtesting-trading-strategies` | Backtest strategies with Sharpe, Sortino, max drawdown, parameter optimization |
| `trading-analysis` | Generate institutional-grade investment reports with technical indicators and charts |

### Payload CMS

| Skill | Purpose |
|---|---|
| `payload-access-policy-audit` | Audit access policies, tenant scoping, and overrideAccess usage |
| `payload-hook-first-use-case` | Extract business logic from hooks into rules, use cases, and adapters |
| `payload-legacy-prisma-bridge` | Bridge Prisma-backed legacy flows to Payload-backed domain flows |
| `payload-lifecycle-manifest` | Normalize lifecycle manifests and shared hook handlers |
| `payload-route-boundary-standardizer` | Standardize API routes with typed errors and thin adapters |

---

## Claude-Only Skills (`.claude/skills/`)

| Skill | Purpose |
|---|---|
| `find-skills` | Discover and install skills from the Skillfish ecosystem (`npx skills`) |

---

## Architecture Rules

All commands and skills generate code that follows the dependency rule:

```
API / UI  →  Infrastructure  →  Application  →  Domain
```

- **Domain** — zero framework imports, pure business logic
- **Application** — orchestrates domain, no HTTP or broker SDK
- **Infrastructure** — implements ports, uses external libraries
- **API / UI** — outermost layer, delegates everything inward

If a command asks you to place code that violates this rule, correct the placement and note why.

---

## Adding New Items

### New command
1. Create `.claude/commands/{command-name}.md` with full content
2. Add an entry to this file (`SKILLS.md`)
3. Reference in `CLAUDE.md` if relevant

### New shared skill
1. Create `.agents/skills/{skill-name}/SKILL.md` with YAML frontmatter
2. Add an entry to this file (`SKILLS.md`)
3. If it needs a Claude slash command, create a pointer in `.claude/commands/`
