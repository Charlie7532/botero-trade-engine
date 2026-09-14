# Families & Confluence — Cross-Station Intelligence Architecture

> **Purpose:** How 11 individual METAR stations combine into 3 families (CAT1/CAT2/CAT3) 
> to detect 6 causal phases and classify floor/ceiling/trap patterns.
> **Source code:** `family_sequence_detector.py` (451 lines, 18 tests)

---

## 1. The Three Categories (Validated Empirically)

| Category | Stations | Lead Time | Role |
|---|---|---|---|
| **CAT1_MACRO** | CREDIT, YIELD_CURVE, DXY | Long (months) | Economic background — establishes base regime |
| **CAT2_SENTIMENT** | VIX, VVIX, PCR, SKEW | Medium (weeks) | Derivative fear — institutions buy protection BEFORE price falls |
| **CAT3_ACTION** | BSI, SV5_TURBULENCE, FG | Short (days) | Market action — capitulation, breadth collapse, sentiment extremes |

**Causal chain (validated: 95% of signals follow this order):**
```
CAT1 deteriorates (credit/yield stress)
  → CAT2 escalates (VIX/VVIX/PCR/SKEW spike — institutions hedge)
    → CAT3 confirms (BSI collapses, FG extreme fear, SV5 turbulence)
      → FLOOR or CRASH
```

## 2. The 6 Causal Phases

| Phase | Condition | Meaning |
|---|---|---|
| `MACRO_PRECURSOR` | CAT1 ≥ 50% stressed, CAT2/3 not | Early warning — macro deteriorating, markets haven't reacted |
| `VOLATILITY_ACCELERATING` | CAT1+CAT2 ≥ 50% stressed, CAT3 not | Institutions hedging heavily — the storm is building |
| `CAPITULATION_BUILDING` | All three ≥ 50% + VIX D2 rising | Full panic — fear building across all layers |
| `CAPITULATION_RESOLVING` | All three ≥ 50% + VIX D2 falling | Post-peak fear — stress still high but momentum reversing |
| `COMPLACENT_DISTRIBUTION` | CAT1+CAT2 ≥ 50% complacent | Silent distribution — institutions exiting while retail complacent |
| `NEUTRAL` | No clear pattern | Normal market conditions (~68% of the time) |

## 3. Floor/Ceiling/Trap Classification

Each station is classified using structural momentum from zigzag_kinematic:

| Type | Condition | Meaning |
|---|---|---|
| **FLOOR_STRUCTURAL** | P(HL) > 0.55 at stress bins | Real floor — higher lows expected |
| **FLOOR_TACTICAL** | P(HL) 0.45-0.55 | Uncertain — could hold or break |
| **FLOOR_TRAP** | P(HL) < 0.45 at stress bins | False floor — lower lows likely |
| **CEILING_STRUCTURAL** | P(HH) < 0.45 at complacent bins | Real ceiling — lower highs expected |
| **CEILING_TACTICAL** | P(HH) 0.45-0.55 | Uncertain |
| **CEILING_TRAP** | P(HH) > 0.55 at complacent bins | False ceiling — Regla de Oro (90.2%) |

## 4. Divergence Regime Consensus (E2.2)

Cross-station count of divergence regimes from fact stores:

| Field | Meaning |
|---|---|
| `n_convergent_bull` | Stations with FULL_CONVERGENT_BULL (p_bull rises with scale) |
| `n_convergent_bear` | Stations with FULL_CONVERGENT_BEAR (p_bull drops with scale) |
| `n_tactical_rebound` | Stations with TACTICAL_REBOUND_IN_BEAR (scalp opportunity) |
| `n_structural_pullback` | Stations with STRUCTURAL_BULL_PULLBACK (dip in uptrend) |

## 5. SIGMET Family-Level Hazards

The SIGMET service now emits 3 family-level hazards:

| Hazard | Condition | Urgency |
|---|---|---|
| `SIGMET_CAPITULATION_TRAP_FLOOR` | CAPITULATION_BUILDING + ≥2 TRAP floors | EMERGENCY |
| `SIGMET_CAPITULATION_RESOLVING_OPPORTUNITY` | CAPITULATION_RESOLVING + ≥2 STRUCTURAL floors | HIGH |
| `SIGMET_CEILING_TRAP_DISTRIBUTION` | COMPLACENT_DISTRIBUTION + HH exit amplify | HIGH |

## 6. Integration Points

```
Lookup (per-station) → to_vector() → station_summaries
                                          ↓
                                   detect_family_sequence()
                                          ↓
                                   FamilySequenceReport
                                          ↓
                              ConvergenceReport.family_sequence
                                          ↓
                              SIGMET service (family-level hazards)
                              TAF service (cone + family context)
```
