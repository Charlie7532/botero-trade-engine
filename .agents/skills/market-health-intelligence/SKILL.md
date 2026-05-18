---
name: market-health-intelligence
description: |
  Market Health Intelligence — transversal SERVICE skill.
  Computes a 6-dimensional convergence score from orthogonal market inputs
  (Breadth, Volatility, Flow, Credit, Rotation, Macro Cycle) plus a
  Fear & Greed contrarian signal layer. Never decides — only informs.
  Consumed by SwingGate, QualityEntryGate, CIO Allocator, and optionally
  SpeculativeEntryHub. Persist-then-Read: daemon computes 1x/day,
  gates read from Vault.
department: SERVICE
layer: tool
requires: [clean-architecture, operational-purpose, hypothesis-governance]
modules: [market_health]
mcp_servers: [fred, yahoo-finance]
crewai_role: injected
---

# Market Health Intelligence — Convergence Engine

## Core Principle

> The value is in CONVERGENCE, not individual readings. When breadth, credit,
> volatility, flow, rotation, and macro cycle ALL point the same direction,
> the probability of that regime persisting is mechanically high. When they
> DIVERGE, the market is transitioning — that's when positioning matters most.
> — Dalio, "Economic Machine"

This module computes a unified `MarketHealthSnapshot` from 6 orthogonal
dimensions plus a Fear & Greed contrarian validation layer. It is a
**SERVICE** — it never decides to buy or sell. It INFORMS the decision-makers.

---

## The 6 Orthogonal Dimensions

Each dimension answers ONE question and produces ONE directional signal
(RISK_ON / NEUTRAL / RISK_OFF). The convergence score counts how many
dimensions agree.

### G1: Breadth Cascade (Structure)

> **Question:** Is market participation broad or narrow?

| Input | Source | History |
|---|---|---|
| S5TW (% > 20-DMA) | `ohlcv_bars` ticker='S5TW' | 2007–present |
| S5FI (% > 50-DMA) | `ohlcv_bars` ticker='S5FI' | 2007–present |
| S5TH (% > 200-DMA) | `ohlcv_bars` ticker='S5TH' | 1990–present |

**CascadeState classification:**

```
HEALTH (0):     S5TW ≥ 40 AND S5FI ≥ 40 AND S5TH ≥ 40
PULLBACK (1):   S5TW < 40 AND S5FI ≥ 50 AND S5TH ≥ 60
CORRECTION (2): S5TW < 30 AND S5FI < 40 AND S5TH ≥ 50
BEAR (3):       default (all failing)
```

Evidence Status: `HYPOTHESIS` — thresholds from engineer_features L1132-1141, not DSR-tested.

### G2: Volatility Regime (Protection)

> **Question:** Is volatility stable, compressed, or chaotic?

Consumed from `volatility_regime` module — NOT recomputed.
Uses `VolRegimeState.quality_label` and `speculative_label`.
VIX z-score computed dynamically from Vault VIX bars (replaces hardcoded 20.0/5.0).

Evidence Status: `HYPOTHESIS` — all vol_classifier thresholds pending calibration.

### G3: Institutional Flow

> **Question:** Are institutions buying or selling?

Source: `flow_intelligence` module via `flow_score` (0-100 composite).
When not available: `NEUTRAL`.

Evidence Status: `HYPOTHESIS` — flow_score formula is empirical.

### G4: Credit Health

> **Question:** Is credit stress emerging?

| Input | Source |
|---|---|
| HYG bars | `ohlcv_bars` ticker='HYG' (2021–present, 1,262 bars) |
| TLT bars | `ohlcv_bars` ticker='TLT' |

**CreditRegime classification:**
```
HYG/TLT ratio z-score (60d rolling):
  z < -1.5 → STRESS     (flight to safety, HY selling)
  z > +1.0 → RISK_ON    (risk appetite, HY buying)
  else     → NORMAL
```

Evidence Status: `HYPOTHESIS` — thresholds need DSR validation.

### G5: Sector Rotation

> **Question:** Are defensive or cyclical sectors leading?

Consumed from `rotation_intelligence` module via `RotationSnapshot`.
Uses `cycle_phase` (Pring) and `dominant_rotation`.

Evidence Status: `VALIDATED` — Pring intermarket cycle is well-established.

### G6: Macro Cycle (Dalio)

> **Question:** Is the economy expanding or contracting?

| Input | Source |
|---|---|
| Yield 10Y/3M spread | `macro_data` (2,512 pts) |
| FRED macro snapshot | `mcp_snapshots` category='macro/fred_real' |

**Yield Curve Signal:**
```
spread > 1.0  → NORMAL      (expansion)
spread 0-1.0  → FLAT        (late cycle)
spread < 0    → INVERTED    (recession warning)
spread rising from negative → STEEPENING (recovery)
```

Evidence Status: Yield inversion → recession = `VALIDATED` (7/8 since 1970).

---

## Fear & Greed: Contrarian Signal Layer

> F&G is a LAGGING indicator (corr +0.61 same-day, zero predictive power
> for daily moves). BUT extreme LEVELS identify exhausted markets, and
> exhausted markets bounce. F&G measures sentiment exhaustion, not future
> direction.
>
> F&G is NOT a 7th dimension of convergence. 5 of 7 sub-indicators
> overlap with G1, G2, G4, G5. Including it would double-count.

### F&G Composition (CNN, equal-weighted average of 7):

| # | Component | Our equivalent |
|---|-----------|:---:|
| 1 | S&P Momentum (vs MA125) | G1: S5FI |
| 2 | NYSE 52wk Hi/Lo ratio | _(no direct equivalent)_ |
| 3 | McClellan Volume Summation | G1: SPX ADL |
| 4 | CBOE Put/Call ratio | G3: Options flow |
| 5 | Junk Bond spread (HY vs IG) | G4: HYG/TLT |
| 6 | VIX vs 50d mean | G2: Vol regime |
| 7 | Stock vs Bond returns (20d) | G4/G5: TLT vs SPY |

### F&G Actions (forensically calibrated)

```
F&G < 15           → CAPITULATION_BUY   [FG-H01 t=6.39, WR 75.5%]
  urgency HIGH:      Day 1-3 in fear    [FG-H07: WR 80.8% — act NOW]
  urgency DECAYING:  Day 10+ in fear    [FG-H07: WR drops to 50%]
F&G 15-25          → FEAR_BUY           [FG-H01 t=5.37, WR 69.9%]
F&G 25-75          → NONE               (not actionable alone)
F&G > 75           → GREED_CAUTION      [FG-H02 REJECTED as sell, only -30% sizing]
F&G > 75 + SPY DD  → GREED_TRAP         [FG-H08: WR 0%, N=6 — hard block]
```

### F&G Direction × Level (forensically corrected)

| F&G Level | Direction | Action | Evidence |
|:-:|---|---|---|
| < 20 | **FALLING** | ✅ **BUY** — HIGHEST WR (80.6%) | FG-H03 corrected |
| < 20 | STABLE | ✅ BUY — WR 70% | FG-H01 |
| < 20 | RISING | ✅ BUY — WR 67% (much of move done) | FG-H03 |
| > 80 | Any | ⚠️ Sizing reduction only — NOT a sell | FG-H02 rejected |

### Divergence Interpretation (FG-H14 — forensically inverted)

```
convergence = RISK_ON  AND fg < 25  → STEALTH_ACCUMULATION   [WR 79%, t=6.21]
  (internal healthy + public fear = institutional buying with retail combustible)

convergence = RISK_OFF AND fg > 75  → DISTRIBUTION_WARNING
  (internal weak + public euphoric = smart money exiting)

convergence NEUTRAL   AND fg < 25   → CONTRARIAN_BUY
  (flat convergence + fear = washout → bounce)

convergence agrees with fg          → CONFIRMING
```

### Duration Effect (FG-H07)

```
Day 1-3 in extreme fear:  WR 80.8%  → urgency=HIGH (max boost)
Day 4-10:                 WR 75.0%  → urgency=NORMAL
Day 11-20:                WR 50.0%  → urgency=DECAYING (signal exhausted)
Mean-reversion to 50:     ~16 days median [FG-H10]
```

### Multi-Horizon Signal Strength (FG-H13)

```
Horizon  Fear Mean  Baseline  Diff     t-stat
    5d     +1.27%    +0.05%   +1.22%   +3.57 ✅
   10d     +2.51%    +0.09%   +2.41%   +5.98 ✅
   20d     +3.56%    +0.26%   +3.30%   +5.52 ✅
   40d     +4.51%    +0.56%   +3.95%   +5.10 ✅
   60d     +6.43%    +2.27%   +4.17%   +5.22 ✅
→ Signal STRENGTHENS over time. Not a quick bounce — regime shift.
```

---

## Hypothesis Registry

### Market Health Hypotheses (MH)

| ID | Hypothesis | Type | Status |
|---|---|---|:---:|
| MH-H01 | CascadeState==PULLBACK is accumulation zone | DIRECTIONAL | `HYPOTHESIS` |
| MH-H02 | CascadeState==BEAR blocks entries profitably | PROTECTIVE | `HYPOTHESIS` |
| MH-H03 | NarrowMarket precedes correction in 60d | PREDICTIVE | `HYPOTHESIS` |
| MH-H04 | HYG/TLT ratio decline precedes equity stress | INTERMARKET | `HYPOTHESIS` |
| MH-H05 | Convergence ≥ 5/6 RISK_OFF → CIO defensive | ALLOCATION | `CANDIDATE` |
| MH-H06 | Yield curve inversion > 90d → contraction | MACRO | `VALIDATED` |
| MH-H08 | PANIC + S5FI WEAK = Munger spot | COMPOSITE | `VALIDATED` |

### Fear & Greed Hypotheses (FG)

| ID | Hypothesis | Evidence | Status |
|---|---|---|:---:|
| FG-H01 | F&G < 20 → SPY Ret20d +3.56% | t=6.39, WR=75.5%, N=106 | `VALIDATED` |
| FG-H02 | F&G > 80 → negative returns | t=0.46, WR_neg=45%, N=20 | `REJECTED` |
| FG-H03 | FALLING at extreme fear = highest WR | WR=80.6% FALLING vs 66.7% RISING | `VALIDATED` |
| FG-H05 | QQQ > SPY at extremes | QQQ/SPY = 1.18x | `CONFIRMED` |
| FG-H06 | F&G 0-10 = monster zone (WR 90.5%) | t=5.47, N=21 | `CANDIDATE` |
| FG-H07 | Day 1-3 peak WR, decays after day 10 | WR 80.8% → 50% | `VALIDATED` |
| FG-H08 | Greed + SPY correction = TRAP | WR=0%, N=6 | `CANDIDATE` |
| FG-H09 | Entering fear is the signal, not exiting | t=3.12, WR=73.9% | `VALIDATED` |
| FG-H10 | Mean-reversion from extreme fear: ~16d | Median=16d, N=52 | `VALIDATED` |
| FG-H11 | Pullback + F&G < 15 = best combo | t=5.24, WR=75.5%, N=49 | `VALIDATED` |
| FG-H12 | Velocity crash (<-20pts/5d) = buy | t=4.64, WR=74.2%, N=31 | `VALIDATED` |
| FG-H13 | Signal strengthens over time (5→60d) | All t > 3.5 | `VALIDATED` |
| FG-H14 | "Bearish" div (SPY↑, F&G↓) = BULLISH | t=6.21, WR=79%, N=81 | `VALIDATED` |

---

## Behavioral Directives per Department

### Quality Core (QualityEntryGate)

| Condition | Directive |
|---|---|
| `cascade_state == BEAR` | Sizing 25% (hard reduction) |
| `cascade_state == CORRECTION` | Sizing 50% |
| `fg_action == CAPITULATION_BUY` | Boost sizing (×1.5, ×1.75 if HIGH urgency) |
| `fg_action == GREED_TRAP` | Sizing 25% (distribution trap) |
| `fg_divergence == STEALTH_ACCUMULATION` | Boost sizing ×1.25 |
| `credit_regime == STRESS` | Reduce sizing 50%, alert |

### Quality Swing (SwingGate)

| Condition | Directive |
|---|---|
| `cascade_state == PULLBACK` | Increase accumulation conviction |
| `cascade_state == BEAR` | **BLOCK** new accumulation |
| `fg_action == CAPITULATION_BUY` | Boost ×1.5 (×1.75 if HIGH urgency) |
| `fg_action == FEAR_BUY` | Boost ×1.2 |
| `fg_action == GREED_TRAP` | **BLOCK** accumulation |
| `fg_action == GREED_CAUTION` | Sizing -30% |
| `fg_divergence == STEALTH_ACCUMULATION` | Boost ×1.25 |

### CIO Allocator (synthesize_live_mandate)

| Condition | Directive |
|---|---|
| `convergence_direction == RISK_OFF` | Tilt to 90/10 Q/S |
| `convergence_direction == RISK_ON` | Allow up to 60/40 Q/S |
| `macro_regime == CONTRACTION` | Defensive allocation |
| `fg_action == GREED_CAUTION` | Cap speculative budget |

---

## Architecture: Persist-then-Read

```
Daemon Pipeline (1x/day):
  OHLCVProvider → BreadthProvider → FGProvider → MarketHealthProvider
                                                        ↓
                                               compute_market_health()
                                                        ↓
                                               inject vol_regime (SPY prices)
                                                        ↓
                                               save_mcp_snapshot(
                                                 "market/health", "MARKET"
                                               )

Consumers (read from Vault, <1ms):
  SwingGate:       store.load_mcp_latest("market/health", "MARKET")
  QualityEntryGate: store.load_mcp_latest("market/health", "MARKET")
  CIO:             store.load_mcp_latest("market/health", "MARKET")
```

---

## Module File Structure

```
backend/modules/market_health/
├── __init__.py
├── domain/
│   ├── __init__.py
│   ├── entities/
│   │   ├── __init__.py
│   │   └── health_snapshot.py       # MarketHealthSnapshot @dataclass
│   ├── rules/
│   │   ├── __init__.py
│   │   ├── cascade_classifier.py    # CascadeState from S5TW/FI/TH
│   │   ├── credit_classifier.py     # CreditRegime from HYG/TLT ratio
│   │   ├── macro_cycle_classifier.py # CyclePhase from FRED + yields
│   │   ├── fg_signal.py             # F&G contrarian logic + divergence
│   │   └── convergence_scorer.py    # Count 6 converging dimensions
│   └── use_cases/
│       ├── __init__.py
│       └── compute_market_health.py # The Compositor
└── # NO infrastructure/ — pure domain

backend/scripts/
├── backtest_fg_correlation.py        # FG-H01 through FG-H05 validation
└── backtest_fg_deep_forensics.py     # FG-H06 through FG-H14 discovery
```
