# Mandatory Fact Store Reference — Read Before Any Fact Store Work

**This rule is UNCONDITIONAL and applies to ALL agents.**

## When This Rule Triggers

Any time a task involves:
- Reading, querying, or interpreting `*_fact_store.json` files
- Working with `quants_obs.pkl` or ZigZag pivot data
- Writing code that uses `zigzag_kinematic`, `structural_momentum`, `prev_leg_domino`
- Computing or discussing `p_bull`, `ev_net`, `e_days`, `cascade_50`, `cascade_75`
- Building signal measurement, ceiling/floor engines, or METAR telemetry
- Any mention of "fact store", "D1__D2__D3", "state_key", "Tríada", or "ZigZag scale"

## Required Action

**STOP.** Before writing ANY code or analysis, read the complete reference document:

```
.agents/references/fact_store_v3_architecture.md
```

This 795-line document contains:
1. What fact stores are and how they differ from quants_obs (Section 1)
2. The generation pipeline from Vault to JSON (Section 2)
3. The ZigZag Tríada: what each scale measures, overflow mechanics, statistical diamonds (Section 3)
4. The three dimensions D1/D2/D3: raw data vectors, formulas, units, classification (Section 4)
5. All data layers: standard, kinematic, structural momentum, domino (Sections 6-7)
6. The Employment Guide: what question each datum answers and what decision it informs (Section 15)
7. Anti-patterns: 10 errors that must NEVER be repeated (Section 16)

## Why This Rule Exists

The user has lost significant time across multiple sessions because agents:
- Did not know what data the fact stores contain
- Re-derived formulas that were already documented
- Misinterpreted `p_bull` (standard vs kinematic), cascade (co-occurrence vs threshold), and structural_momentum (ZigZig/ZagZag vs ZigZag)
- Discarded low-N states that are statistical diamonds
- Generated data without knowing its employment

**This will not happen again.**
