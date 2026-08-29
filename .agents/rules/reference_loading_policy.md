# Reference Loading Policy — Context Budget Management

> **Status**: `MANDATORY RULE` | **Effective**: 29-Ago-2026
> **Scope**: All AI agents working on the Botero Trade Engine

---

## 1. Problem

The `.agents/references/` directory contains ~21 reference files totaling ~170KB. Loading all references into agent context wastes tokens and degrades attention on the actual task. Agents must load ONLY the references relevant to their current work.

## 2. Reference Directory Map

```
.agents/references/
├── metar/                              ← METAR system (~105KB total)
│   ├── fact_store_v3_architecture.md   ← Full monolith (70KB) — HUMAN ONLY, never auto-load
│   ├── d1_labels_canonical.md          ← D1×D2×D3 label tables (5KB)
│   ├── overflow_taxonomy.md            ← Overflow T1-T2 + Blow-Off T3-T5 (5KB)
│   ├── fact_store_guide.md             ← How to read fact store JSON (4KB)
│   ├── signal_rules.md                 ← Signal interpretation + Confidence Tiers (3KB)
│   ├── anti_patterns.md                ← 10 errors to never repeat (3KB)
│   ├── gaussian_scale_policy.md        ← Gaussian calibration policy (9KB)
│   ├── interactions.md                 ← Cross-station interactions (11KB)
│   └── indicator_stochastic_registry.md
├── stations/                           ← Per-station intelligence (~43KB total)
│   └── {station}_intelligence.md (×10) ← Individual station profiles (~4KB each)
├── vault/                              ← Data infrastructure
│   └── data_registry.md               ← Vault ticker/table registry (11KB)
└── skill-system-reference.md           ← System reference
```

## 3. Loading Rules

### Rule 1: Never Auto-Load the Monolith
`metar/fact_store_v3_architecture.md` (70KB) is for HUMAN reading only. Agents must use the modular extracts. If a modular file is insufficient, load specific line ranges from the monolith using `view_file` with `StartLine`/`EndLine`.

### Rule 2: Load by Task, Not by Default
Match the task to the minimum reference set:

| Task Type | Load These References | Total Context |
|---|---|---|
| **Classifying states / generating labels** | `metar/d1_labels_canonical.md` | ~5KB |
| **Reading/interpreting fact stores** | `metar/fact_store_guide.md` | ~4KB |
| **Working with SIGMET / crisis alerts** | `metar/overflow_taxonomy.md` | ~5KB |
| **Evaluating signal quality** | `metar/signal_rules.md` | ~3KB |
| **Any METAR code modification** | `metar/anti_patterns.md` (always) | ~3KB |
| **Working on a specific station** | `stations/{station}_intelligence.md` | ~4KB |
| **Modifying Gaussian edges/bins** | `metar/gaussian_scale_policy.md` | ~9KB |
| **Adding data to the Vault** | `vault/data_registry.md` | ~11KB |

### Rule 3: anti_patterns.md is Mandatory for METAR Work
If the task involves ANY code in `backend/modules/entry_decision/`, `backend/scripts/generators/`, or `research/01_señales_entry_exit/`, load `metar/anti_patterns.md` first. It's 3KB — negligible cost, high protection.

### Rule 4: Station Intelligence is Singular
When working on VIX-related code, load `stations/vix_intelligence.md`. Do NOT load all 10 station files. Cross-station work should load `metar/interactions.md` instead.

### Rule 5: Skill YAML Declares References
Skills that reference METAR infrastructure should declare their reference dependencies in the YAML frontmatter:

```yaml
---
name: my-skill
references:
  - metar/d1_labels_canonical.md
  - metar/anti_patterns.md
---
```

When a skill is activated, the agent SHOULD load its declared references before proceeding.

## 4. Context Budget Guidelines

| Agent Context Window | Max References per Task | Strategy |
|---|---|---|
| < 32K tokens | 2-3 modular files | Strict minimum |
| 32K - 128K tokens | 4-6 modular files | Task-matched set |
| > 128K tokens | 8-10 modular files | Broader context OK |

**Rule of thumb**: If total reference content exceeds 20KB, you're probably loading too much. The modular files are designed so that 2-3 files (6-12KB) cover any single task.

## 5. The module-skill-map Connection

The [`module-skill-map`](file:///root/botero-trade/.agents/skills/module-skill-map/SKILL.md) routes modules → skills. This policy adds the second hop: skills → references. The complete chain is:

```
User mentions a module
  → module-skill-map activates relevant skills
    → each skill declares reference dependencies
      → agent loads ONLY those reference files
```

This ensures an agent working on `options_gamma` never loads `metar/signal_rules.md`, and an agent working on `entry_decision` always loads `metar/anti_patterns.md`.
