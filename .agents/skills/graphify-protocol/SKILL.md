---
name: graphify-protocol
description: Use this skill to query the project's knowledge graph before answering architecture questions or making refactors. Outlines when to use grep vs graphify.
---

## graphify

This project has a graphify knowledge graph at graphify-out/.
Graph: 5,252 nodes · 13,400 edges · 349 communities.
Last scan: 2026-05-20 · 789 files · ~619,938 words.

### Decision Protocol — grep vs graphify

Use **grep** when:
- Searching for an exact string, import, class name, or variable
- Finding where a function is defined or called
- Debugging (searching for errors, values)
- Working inside a single known file

Use **graphify** when:
- Tracing cross-module dependencies ("what depends on X?") → `graphify query "..." --budget 500`
- Finding the shortest dependency path between two nodes → `graphify path "A" "B"`
- Understanding a god node and its connections → `graphify explain "X"`
- Assessing blast radius before a refactor
- Any question requiring 3+ greps to answer

**Rule of thumb**: If the question is "where is X?" → grep. If the question is "what connects to X?" → graphify.

### MANDATORY: When to consult the graph

Before answering any of these question types, **query the graph first**:

1. **Architecture questions** — "how does module X connect to Y?" → `graphify path "X" "Y"`
2. **Refactor impact** — "what breaks if I change X?" → `graphify explain "X"` to see all connections
3. **New feature placement** — "where should I put this?" → `graphify query "where does [concept] belong?" --budget 500`
4. **Dependency audit** — "what does this module depend on?" → `graphify query "dependencies of [module]"`
5. **Cross-cutting concerns** — "what else uses this pattern?" → `graphify query "[pattern] usage"`

Do NOT answer architecture questions from memory alone. The graph has 5,252 nodes of verified relationships — use it.

### Session Startup (architecture sessions only)

Read `graphify-out/GRAPH_REPORT.md` lines 1-255 only (~800 tokens).
This covers: Summary, God Nodes, Surprising Connections.
Do NOT read the full report (67% is single-node noise with cohesion 1.0).

God Nodes (core abstractions by connectivity):
1. TimescaleDataStore (638 edges) — THE central data nexus, Vault read/write interface
2. SignalPort (188 edges) — Signal interface consumed by all modules
3. AlpacaAdapter (165 edges) — Broker execution adapter
4. UnusualWhalesIntelligence (164 edges) — Institutional flow intelligence
5. FinnhubIntelligence (157 edges) — Earnings/insider intelligence
6. GuruFocusMCPBridge (148 edges) — Fundamental data bridge
7. VaultInterceptor (144 edges) — Data access interceptor
8. UWDataBridge (141 edges) — Unusual Whales data pipeline
9. PatternRecognitionIntelligence (136 edges) — Candlestick pattern engine
10. QuantFeatureEngineer (126 edges) — ML feature engineering

### Available Commands

| Command | When to use | Example |
|---|---|---|
| `graphify query "Q" --budget N` | Open-ended architecture questions | `graphify query "what modules write to Neon?" --budget 500` |
| `graphify path "A" "B"` | Shortest dependency path between two nodes | `graphify path "SignalPort" "TimescaleDataStore"` |
| `graphify explain "X"` | Understand a node's role and all connections | `graphify explain "VaultInterceptor"` |
| `graphify query "Q" --dfs` | Deep trace following one path | `graphify query "execution flow from signal to order" --dfs` |

### Graph Maintenance

- After structural changes (new module, rename, move files) → `pnpm graphify:update` (AST-only, 0 API cost)
- After minor code edits within existing files → do NOT update (unnecessary)
- Full rescan (`pnpm graphify`) → only after major refactors (has LLM API cost)
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- Git hooks installed: post-commit and post-checkout auto-update the graph
