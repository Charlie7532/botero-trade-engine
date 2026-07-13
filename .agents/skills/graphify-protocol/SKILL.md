---
name: graphify-protocol
description: |
  Knowledge graph generation for the Botero Trade codebase.
  Wraps the global graphify skill with project-specific configuration.
  Use /graphify to regenerate or query the knowledge graph.
department: ALL
layer: tool
---

# Graphify Protocol — Botero Trade

## Overview

This skill wraps the globally installed `graphify` tool (`~/.agents/skills/graphify/SKILL.md`)
with project-specific configuration for the Botero Trade monorepo.

## Quick Reference

```bash
# Full pipeline (regenerate everything)
/graphify

# Incremental update (only changed files)
/graphify --update

# Query the graph
/graphify query "How does SwingGate consume MarketHealth?"
/graphify path "SwingGate" "MarketHealthSnapshot"
/graphify explain "RegimeStatePort"
```

## Project Configuration

- **Root:** `/root/botero-trade`
- **Output:** `graphify-out/`
- **Ignore patterns:** `.graphifyignore` (excludes node_modules, .next, data/, .venv, .env*)
- **Python interpreter:** `/root/.local/share/uv/tools/graphifyy/bin/python`

## Current Graph Stats

| Metric | Value |
|---|---|
| Nodes | 7,471 |
| Edges | 19,045 |
| Communities | 823 |
| Files indexed | 991 |
| Words | ~932K |
| Last updated | 2026-07-10 |

## Outputs

| File | Purpose |
|---|---|
| `graphify-out/graph.json` | Full graph (NetworkX JSON, 12MB) |
| `graphify-out/GRAPH_TREE.html` | Interactive HTML visualization (aggregated community view) |
| `graphify-out/GRAPH_REPORT.md` | Plain-language report with community analysis |
| `graphify-out/cache/ast/` | AST extraction cache (1,557 files) |

## When to Regenerate

Run `/graphify --update` after:
- Adding new modules to `backend/modules/`
- Significant refactoring of domain entities or ports
- Adding new skills or updating architecture docs

The graph uses AST extraction (deterministic, free) + semantic extraction (LLM, costs tokens).
AST alone captures imports, calls, and class hierarchies. Semantic extraction finds
cross-document conceptual relationships.

## Delegation

For full pipeline instructions, read the global skill:
```
~/.agents/skills/graphify/SKILL.md
```
