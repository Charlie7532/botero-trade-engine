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

**Macro Regime:** Read directly from `macro/fred_real` snapshot
(`macro_regime`, `fed_stance`, `liquidity_regime`).

Evidence Status: Yield inversion → recession = `VALIDATED` (7/8 since 1970).

---

## Fear & Greed: Contrarian Signal Layer

> F&G is NOT a 7th dimension of convergence. It is a COMPOSITE of 7
> sub-indicators that overlap with our G1, G2, G4, G5 dimensions.
> Including it in convergence would double-count.
>
> F&G has its own operational value: extreme levels are contrarian
> signals with independent predictive power.

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

### F&G Operational Roles

**Role 1 — Contrarian extremes (independent signal):**

```
F&G < 15  → CAPITULATION_BUY   — Aggressive accumulation
F&G < 25  → FEAR_BUY           — Gradual accumulation
F&G 25-75 → NONE               — Not actionable alone
F&G > 75  → GREED_CAUTION      — Reduce sizing
F&G > 85  → EUPHORIA_SELL      — Active trimming
```

**Role 2 — Direction + Level (the combination is the signal):**

| F&G Level | Direction | Action |
|:-:|---|---|
| < 20 | Rising | ✅ BUY — bounce confirmed, capitulation complete |
| < 20 | Falling | ⏳ WAIT — active panic, don't catch falling knife |
| < 20 | Stable | 🔍 WATCH — sustained fear, await catalyst |
| > 80 | Falling | ✅ TRIM — distribution starting |
| > 80 | Rising | ⏳ HOLD — euphoria not confirmed yet |
| > 80 | Stable | ⚠️ CAUTION — complacency, don't add |

**Role 3 — Divergence vs convergence_score:**

```
convergence = RISK_ON  AND fg < 25  → CONTRARIAN_BUY
convergence = RISK_OFF AND fg > 75  → CONTRARIAN_SELL
convergence agrees with fg          → CONFIRMING (high confidence)
convergence disagrees               → DIVERGING (investigate)
```

---

## Hypothesis Registry

### Market Health Hypotheses (MH)

| ID | Hypothesis | Type | Validation Method | Status |
|---|---|---|---|:---:|
| MH-H01 | CascadeState==PULLBACK is accumulation zone | DIRECTIONAL | Oracle: Ret20d when CascadeState==1 | `HYPOTHESIS` |
| MH-H02 | CascadeState==BEAR blocks entries profitably | PROTECTIVE | Oracle: WR+DD in CascadeState==3 | `HYPOTHESIS` |
| MH-H03 | NarrowMarket precedes correction in 60d | PREDICTIVE | Oracle: Ret60d when NarrowMarket==1 | `HYPOTHESIS` |
| MH-H04 | HYG/TLT ratio decline precedes equity stress | INTERMARKET | Oracle: equity DD lag after HYG/TLT drop | `HYPOTHESIS` |
| MH-H05 | Convergence ≥ 5/6 RISK_OFF → CIO defensive | ALLOCATION | Portfolio backtest by regime | `CANDIDATE` |
| MH-H06 | Yield curve inversion > 90d → contraction | MACRO | FRED: inversion → recession lag | `VALIDATED` |
| MH-H07 | wave_flip + fear≥4 → Munger entry zone | TACTICAL | Oracle: WR+Ret20d conditional | `HYPOTHESIS` |
| MH-H08 | PANIC + S5FI WEAK = Munger spot | COMPOSITE | P(↑)=55.3%, Ret20d=+5.44% | `VALIDATED` |
| MH-H09 | VVIX/VIX > 5.0 = vol of vol extreme | VOL | Oracle: MAE following ratio spikes | `CANDIDATE` |

### Fear & Greed Hypotheses (FG)

| ID | Hypothesis | Type | Validation Method | Status |
|---|---|---|---|:---:|
| FG-H01 | F&G < 20 → SPY Ret20d > 2% | CONTRARIAN | Backtest: FG bars × SPY bars (2011–2026) | `CANDIDATE` |
| FG-H02 | F&G > 80 → SPY Ret20d < 0% | CONTRARIAN | Backtest: FG bars × SPY bars | `CANDIDATE` |
| FG-H03 | F&G < 15 + velocity rising → SPY Ret20d > 5% | COMPOSITE | Backtest: FG level + direction × SPY | `CANDIDATE` |
| FG-H04 | F&G velocity < -3σ → more downside before bounce | TIMING | Backtest: MAE10d after panic velocity | `CANDIDATE` |
| FG-H05 | QQQ reacts stronger than SPY to F&G extremes | RELATIVE | Backtest: |QQQ Ret20d| vs |SPY Ret20d| | `CANDIDATE` |

---

## Behavioral Directives per Department

### Quality Core (QualityEntryGate)

| Condition | Directive |
|---|---|
| `cascade_state == BEAR` | **BLOCK** entry (hard gate) |
| `cascade_state == CORRECTION` | Reduce sizing to 50% |
| `convergence_score <= 2` | Reduce sizing by convergence |
| `fg_action == CAPITULATION_BUY` | Override: allow entry even in CORRECTION |
| `credit_regime == STRESS` | Reduce sizing to 50%, alert |

### Quality Swing (SwingGate)

| Condition | Directive |
|---|---|
| `cascade_state == PULLBACK` | Increase accumulation conviction |
| `cascade_state == BEAR` | **BLOCK** new accumulation |
| `narrow_market == True` | Tighten stops |
| `fg_action == FEAR_BUY` | Boost contrarian conviction |
| `fg_action == GREED_CAUTION` | Reduce accumulation sizing |

### CIO Allocator (synthesize_live_mandate)

| Condition | Directive |
|---|---|
| `convergence_direction == RISK_OFF` | Tilt to 90/10 Q/S |
| `convergence_direction == RISK_ON` | Allow up to 60/40 Q/S |
| `macro_regime == CONTRACTION` | Defensive allocation |
| `fg_action == EUPHORIA_SELL` | Cap speculative budget |

### Speculative (SpeculativeEntryHub) — Optional

| Condition | Directive |
|---|---|
| `cascade_state == BEAR` | Reduce sizing to 50% |
| All other fields | Not consumed (has own flow + gamma) |

---

## Architecture: Persist-then-Read

```
Daemon Pipeline (1x/day):
  OHLCVProvider → BreadthProvider → FGProvider → MarketHealthProvider
                                                        ↓
                                               compute_market_health()
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
```
