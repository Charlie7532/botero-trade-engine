---
name: hypothesis-governance
description: |
  Mandatory system directive for all agents. Enforces the Scientific Methodology
  Constraint: every operational recommendation must carry an Evidence Status Tag,
  and only empirically validated rules may influence trading decisions.
  Loaded automatically alongside clean-architecture.
layer: governance
requires: [clean-architecture]
conflicts_with: []
modules: [simulation]
---

# Hypothesis Lifecycle Governance

## Directive

This is a **system-level governance policy**. Every agent, every session, every code change
that touches trading logic MUST comply with these rules. No exceptions.

## The One Rule

**No unvalidated hypothesis may act as a Hard Gate.**

A hypothesis is any assertion that a specific market condition predicts a specific outcome.
Examples: "CHoCH bearish = block longs", "RSI < 30 = buy", "Volume at VAL = accumulation".

---

## Evidence Status Tags

Every directive in a PROFILE.md or indicator configuration that implies an action
(block, reduce sizing, exit, enter) MUST carry one of these tags:

| Status | Grade | Authority | Transition |
|---|---|---|---|
| `CANDIDATE` | — | None (not in code) | → HYPOTHESIS if p < 0.10 |
| `HYPOTHESIS` | D | Advisory Only | → VALIDATED via 5-Step Pipeline |
| `VALIDATED` | A-C | Hard Gate / Sizing Modifier | → DEGRADED if decay > 25% |
| `DEGRADED` | D | Demoted to Advisory | → RETIRED or → REPOSTULATED |
| `REPOSTULATED` | D | Advisory (re-enters pipeline) | → HYPOTHESIS (conjugated) |
| `RETIRED` | — | None (removed from code) | End of lifecycle |

## Authority by Grade

| Grade | Authority Level | What It Can Do | What It Cannot Do |
|---|---|---|---|
| **A** (DSR > 0.95) | Hard Gate | Block/allow trades, full veto power | — |
| **B** (DSR > 0.85) | Hard Gate | Block/allow trades | Override Grade A signals |
| **C** (DSR > 0.70) | Sizing Modifier | Adjust position ±25% | Block or allow trades |
| **D** (unvalidated) | Advisory Only | Log alerts, feed Memory Guard 13D | Modify sizing or block trades |
| **F** (failed OOS) | None | Nothing | Must be removed from active code |

## Mandatory Validation Pipeline (5 Steps)

No agent may promote a HYPOTHESIS to VALIDATED without completing ALL steps:

1. **Oracle Alpha Ceiling** (`OracleBacktester.run_signal`)
   - Minimum: Sharpe ≥ 0.3, N entries ≥ 10, Win Rate ≥ 30%
   - If fails: → RETIRED immediately

2. **Feature Engineering** (`QuantFeatureEngineer`)
   - Fractional Differencing for stationarity
   - Z-Score normalization for comparability

3. **Walk-Forward Validation** (`StrategyCalibrator`)
   - SPECULATIVE: 1yr train / 3mo test, 5-20 bar horizon
   - QUALITY: 2yr train / 6mo test, 10 bar horizon (forward return)
     - NOTE: If data history is < 8 years, use 2yr/6mo to ensure ≥4 folds.
       If data history is ≥ 8 years, use 3yr/1yr for deeper training.
   - Purged + Embargoed cross-validation (10d purge, 5d embargo)
   - **Minimum N_OOS ≥ 30** for statistical significance (López de Prado)

4. **Deflated Sharpe Ratio** (DSR)
   - Adjusts for number of trials tested
   - DSR probability thresholds (implemented in `walk_forward_dsr_v2.py`):
     - Grade A: DSR > 0.95 → Hard Gate with veto power
     - Grade B: DSR > 0.85 → Hard Gate (subordinate)
     - Grade C: DSR > 0.70 → Sizing Modifier (±25%)
     - Grade D: DSR ≤ 0.70 → Advisory Only

5. **Out-of-Sample Confirmation**
   - Final holdout test on unseen data
   - Must beat walk-forward baseline by ≥ 80%
   - Overfitting check: IS_Sharpe / OOS_Sharpe ratio > 2.0 = SUSPECT

## Conjugation Rules

Individually weak signals may be powerful when combined. The ConjugationExplorer
tests pairwise/triplet combinations under these constraints:

1. Partner signals must come from **different families** (no RSI + RSI Cardwell)
2. Correlation between partners must be **< 0.80** (avoid redundancy)
3. Combined Sharpe must exceed best individual partner by **≥ 20%**
4. DSR penalty applies for total number of combinations tested
5. DEGRADED signals may be REPOSTULATED if conjugation produces viable edge

## Prohibited Behavior

1. **Never hardcode a HYPOTHESIS as a veto/gate.** Tag it, let it learn via Memory Guard.
2. **Never skip DSR when multiple thresholds were tested.** This is data snooping.
3. **Never promote based on in-sample performance alone.** OOS is mandatory.
4. **Never present an untested heuristic as "validated by mechanics."** Market mechanics
   are real, but their predictive power for specific trades requires empirical proof.
5. **Never override the RetrainTrigger's degradation.** If decay > 25%, the signal
   is DEGRADED automatically. A human or agent may investigate, but the demotion stands
   until revalidation passes.
6. **Never publish a rule without a Confidence Card.** See below.

---

## Confidence Card Standard

Every operational rule in intelligence files (`xx_intelligence.md`), interaction
registries (`metar_interactions.md`), domain rules, and gate configurations MUST
carry a **Confidence Card** with the following mandatory fields:

| Field | Description | Example |
|---|---|---|
| **N** | Sample size | `626` |
| **Test Type** | Validation method | `Purged 5-Fold CV + Walk-Forward OOS` |
| **Metric** | Primary performance metric | `AUC 0.8146` or `WR 71.2%` |
| **CI 95%** | 95% confidence interval | `[0.78, 0.85]` |
| **DSR Grade** | Hypothesis Governance grade | `B (DSR > 0.85)` |
| **Window** | Temporal scope / lag | `t_-1 to t_-5 (PREDICTIVE)` |
| **OOS Period** | Out-of-sample date range | `2020-01-17 → 2026-07-29` |
| **Last Validated** | Date of last validation | `2026-08-05` |
| **Status** | Lifecycle status | `VALIDATED (Grade B)` |
| **Decay Check** | Next scheduled revalidation | `2026-11-05` |

### Automatic Status Rules

- Rules **without** a Confidence Card → automatic `CANDIDATE` status → **CANNOT**
  influence sizing or gating decisions.
- Rules with **N < 30** → automatic **Grade D maximum** regardless of WR/AUC
  (insufficient statistical power per López de Prado).
- Rules with **Last Validated > 6 months ago** → automatic `DEGRADED` status →
  must be re-validated before use.

### Confidence Card Format (Markdown)

```markdown
> **Confidence Card**
> | Field | Value |
> |---|---|
> | N | 626 |
> | Test Type | Purged 5-Fold CV + Walk-Forward OOS |
> | Metric | AUC 0.8146 OOS |
> | CI 95% | [0.78, 0.85] |
> | DSR Grade | B |
> | Window | t_-1 to t_-5 (predictive, no t_0) |
> | OOS Period | 2020-01-17 → 2026-07-29 |
> | Last Validated | 2026-08-05 |
> | Status | VALIDATED (Grade B) |
> | Decay Check | 2026-11-05 |
```

---

## Decay & Revalidation Policy

1. **Quarterly decay checks** — every VALIDATED rule must be re-tested every 3 months.
2. **Regime shift trigger** — if Vault population grows >20% or a structural market
   event occurs (e.g., new rate regime, liquidity crisis), all rules must be re-validated.
3. **Decay detection** — if Walk-Forward OOS metric drops >25% from its Confidence Card
   value, the rule is automatically DEGRADED.
4. **Revalidation** — a DEGRADED rule re-enters the 5-Step Pipeline from Step 3
   (Walk-Forward Validation). If it passes, its Confidence Card is updated with new dates.
