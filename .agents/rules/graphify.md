## graphify

This project has a graphify knowledge graph at graphify-out/.
Graph: 3,387 nodes · 6,258 edges · 218 communities.

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

### Session Startup (architecture sessions only)

Read `graphify-out/GRAPH_REPORT.md` lines 1-255 only (~800 tokens).
This covers: Summary, God Nodes, Surprising Connections.
Do NOT read the full report (67% is single-node noise with cohesion 1.0).

God Nodes (core abstractions by connectivity):
1. KalmanVolumeTracker (65 edges)
2. SignalPort (58 edges)
3. SmartEntryEngine (55 edges)
4. EntryIntelligenceHub (53 edges)
5. TradeJournal (49 edges)
6. InvestmentCategory (49 edges)
7. WalkForwardBacktester (48 edges)
8. StrategyProfile (48 edges)
9. Broker (41 edges)
10. TimescaleDataStore (40 edges)

### Graph Maintenance

- After structural changes (new module, rename, move files) → `pnpm graphify:update` (AST-only, 0 API cost)
- After minor code edits within existing files → do NOT update (unnecessary)
- Full rescan (`pnpm graphify`) → only after major refactors (has LLM API cost)
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
