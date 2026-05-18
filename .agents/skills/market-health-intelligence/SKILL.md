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

### F&G Actions (forensically corrected — 2026-05-18)

> [!WARNING]
> **All statistics below use overlapping-return-adjusted t-stats (López de Prado).**
> Previous values (FG-H01 t=6.39 etc.) were inflated ~4x by assuming independence
> of overlapping 20d returns. N=414 on full Vault dataset (2011-2026, 3,843 days).
> Prior analysis used N=106 on partial data.

```
F&G < 20 (alone)     → FEAR_WATCH          [t_adj=1.47, WR=66.9%, N=414 — NOT significant alone]
F&G < 20 + VIX > 25  → CAPITULATION_WATCH  [Ret=+3.38%, WR=70.3%, N=158 — needs momentum]
F&G < 20 + VIX > 25
  + SPY fell > 2%/5d  → CAPITULATION_BUY   [Regime: Ret=+4.29%, WR=75.9%, N=112, t=+1.42]
  urgency LOW:          Day 1-10           [WR 60-68% — sell-off immature, wait]
  urgency HIGH:         Day 11+            [WR 73-86% — seller exhaustion confirmed]
F&G 20-40 + VIX↓
  + SPY bouncing       → RECOVERY_BUY      [Ret=+1.52%, WR=69.4%, N=206]
F&G 25-75              → NONE              (not actionable alone)
F&G 55-75 + VIX < 15
  + PCR < 0.85         → COMPLACENCY_WARN  [Ret=-0.14%, WR=57.3%, N=211 — ONLY negative regime]
F&G > 75               → GREED_HOLD        [WR=71.7% — NOT a sell, momentum protects]
F&G > 75 + PCR > 1.0   → WALL_OF_WORRY    [WR=81.6%, Ret=+1.63%, N=38 — institutional alpha]
```

### F&G Direction × Level (forensically corrected — INVERTED from prior)

> Prior skill said FALLING = best. Forensics proved EXIT (rising past 20) = best.

| F&G Level | Direction | Action | Evidence |
|:-:|---|---|---|
| < 20 | **EXIT FEAR (→ 20+)** | ✅✅ **BUY** — strongest event signal | t_event=**+2.53**, WR=73.7% |
| < 20 | STABLE (11+ days) | ✅ BUY — seller exhaustion | Day 21+: WR=86.4%, Ret=+3.23% |
| < 20 | FALLING (entering) | ⚠️ WATCH — panic immature | t_event=+1.07, WR=70.2% |
| < 20 | + VIX > 25 required | Mandatory filter | Raw F&G not significant without VIX |
| > 80 | Any | ⚪ HOLD — not a sell | WR=82%, Ret=+1.25%. Greed = momentum |

### Sentiment Regime Classifier (NEW — replaces raw F&G actions)

> F&G alone is a PLAUSIBLE sensor (t=1.47). Combined with VIX + PCR + SPY momentum,
> it becomes a regime classifier that produces 232% more alpha (CAPITULATION regime
> +4.29% vs raw F&G +1.85%). Formal implementation:
> `backend/modules/entry_decision/domain/rules/sentiment_regime_classifier.py`

```
CAPITULATION   = F&G<20 + VIX>25 + SPY fell>2%/5d    → Ret +4.29%, WR 75.9%, N=112
STRESS         = F&G<35 + VIX↑ + SPY↓                → Ret +1.43%, WR 67.3%, N=266
RECOVERY       = F&G 20-40 + VIX↓ + SPY↑             → Ret +1.52%, WR 69.4%, N=206
WALL_OF_WORRY  = F&G 30-55 + SPY↑20d + VIX > 60d avg → Ret +0.36%, WR 66.3%, N=246
NORMAL_BULL    = default                               → Ret +0.95%, WR 67.1%, N=2454
COMPLACENCY    = F&G 55-75 + VIX<15 + PCR<0.85        → Ret -0.14%, WR 57.3%, N=211
EUPHORIA       = F&G>75 + VIX<18 + SPY near highs     → Ret +0.78%, WR 69.8%, N=318
DISTRIBUTION   = F&G>65 + VIX↑ + PCR↑                 → Ret +0.97%, WR 63.3%, N=30
```

### Divergence Interpretation (forensically corrected)

```
Greed + PCR > 1.0 (Wall of Worry)       → INSTITUTIONAL_ALPHA [WR 81.6%, N=38]
  (public euphoric + institutions hedging = "climbing wall of worry")

DECLINING phase + F&G < 25              → STRONGEST BUY       [t_adj=+2.76, WR=74.9%, N=338]
  (price in structural downtrend + fear = max mean-reversion)

ADVANCING phase + F&G < 25              → TRAP                [WR=41.7%, N=36 — DO NOT BUY]
  (price making higher highs but F&G scared = false capitulation)

"Bearish" div (SPY↑, F&G↓)             → NO EDGE             [alpha=-0.40% vs base rate]
  (high WR=72.8% but zero excess return — base rate explains it all)
```

### Duration Effect (FG-H07 — CORRECTED, curve is U-shaped)

```
Day 1-3 in extreme fear:   WR 67.7%  Mean=+1.66%  → urgency=LOW (sell-off immature)
Day 4-10:                  WR 59.5%  Mean=+0.46%  → urgency=AVOID (the valley)
Day 11-20:                 WR 72.6%  Mean=+3.82%  → urgency=HIGH (exhaustion begins)
Day 21+:                   WR 86.4%  Mean=+3.23%  → urgency=MAXIMUM (confirmed exhaustion)
Mean-reversion to 50:      ~24 days median (extreme fear <15), ~19d for fear 15-25
```

### Multi-Horizon Signal Strength (FG-H13 — CORRECTED with adjusted t-stats)

```
Horizon  Fear Mean  Base Mean  Diff     t_adj
    5d     +0.36%    +0.16%   +0.20%   +0.46 ❌ NOT significant
   10d     +0.80%    +0.30%   +0.50%   +0.62 ❌ NOT significant
   20d     +1.85%    +0.61%   +1.25%   +0.90 ❌ NOT significant
   40d     +2.70%    +1.56%   +1.13%   +0.47 ❌ NOT significant
   60d     +4.56%    +3.02%   +1.53%   +0.46 ❌ NOT significant
→ Raw F&G fails significance at ALL horizons after overlapping correction.
  Use Sentiment Regime Classifier instead for actionable signals.
```

### What ADDS Alpha vs What DOESN'T (forensically proven)

```
✅ ADDS:  VIX level (>25)        → +83% alpha amplification
✅ ADDS:  SPY crash speed (<-5%) → +398% alpha amplification
✅ ADDS:  Duration (>11 days)    → +130% alpha vs early days
✅ ADDS:  Exit-fear transition   → t=2.53, ONLY signal above 1.96
❌ NOISE: F&G velocity (ROC5)   → corr +0.024 with Ret20d
❌ NOISE: PCR direction          → lagging (lag +1d corr=-0.088)
❌ NOISE: Volume climax/dry-up  → normal vol > climax vol in fear
❌ NOISE: VIX direction alone   → both rising & falling are positive
```

### Key Correlations (delta predictors of SPY Ret20d)

```
spy_mom20d   : -0.1510  ← ONLY strong predictor (mean reversion from drawdown)
spy_mom5d    : -0.0570  ← Crash speed (secondary)
vix_roc5     : -0.0088  ← Noise
pcr_roc5     : +0.0007  ← Null
fg_roc5      : +0.0244  ← Null
F&G vs VIX   : corr -0.456
F&G vs PCR   : corr -0.411
```

### Fear & Greed Hypotheses (FG) — Corrected Registry

| ID | Hypothesis | Evidence (adjusted) | Status |
|---|---|---|:---:|
| FG-H01 | F&G < 20 → SPY Ret20d positive | t_adj=+1.47, WR=66.9%, N=414 | `PLAUSIBLE` |
| FG-H02 | F&G > 80 → negative returns | WR=82% positive. Greed is bullish | `REJECTED` |
| FG-H03 | FALLING at fear = highest WR | EXIT fear WR=73.7% t=2.53 > ENTER WR=70.2% t=1.07 | `REJECTED` |
| FG-H05 | QQQ > SPY at extremes | QQQ beta=1.51x at F&G<15 | `CONFIRMED` |
| FG-H06 | F&G 0-10 = monster zone | Ret=+2.65%, WR=73.1%, t=+1.18 | `PLAUSIBLE` |
| FG-H07 | Day 1-3 peak WR, decays after 10 | U-curve: Day 1-3 WR=68%, 11-20d WR=73%, 21+ WR=86% | `REJECTED` |
| FG-H08 | Greed + SPY correction = TRAP | Greed+mild DD: WR=85%, N=20 — NOT a trap | `REJECTED` |
| FG-H09 | Entering fear is the signal | EXITING fear is the signal (t=2.53 vs 1.07) | `REJECTED` |
| FG-H10 | Mean-reversion ~16d | Median=24d (extreme fear <15). Slower than claimed | `PLAUSIBLE` |
| FG-H11 | Pullback + F&G < 15 = best combo | t_adj=+1.30, WR=67.1%, N=240. Not significant | `PLAUSIBLE` |
| FG-H12 | Velocity crash (<-20pts/5d) = buy | WR=63.2%, t=+0.30. Noise | `REJECTED` |
| FG-H13 | Signal strengthens 5→60d | All t_adj < 1.0. None significant after correction | `REJECTED` |
| FG-H14 | "Bearish" div = BULLISH | WR=72.8% but alpha=-0.40% vs base rate | `PLAUSIBLE` |
| **FG-H15** | **Sentiment Regime > raw F&G** | **CAPITULATION +4.29% vs raw +1.85% (232% alpha)** | **`CONFIRMED`** |
| **FG-H16** | **DECLINING + F&G<25 = strongest buy** | **t_adj=+2.76, WR=74.9%, N=338** | **`CONFIRMED`** |
| **FG-H17** | **COMPLACENCY is the only negative regime** | **Ret=-0.14%, WR=57.3%, N=211** | **`CONFIRMED`** |

---

## Behavioral Directives per Department

> Directives now reference `sentiment_regime` from the Sentiment Regime Classifier
> instead of raw `fg_action`. Old F&G raw actions (`CAPITULATION_BUY`, `GREED_TRAP`,
> etc.) are deprecated — the regime classifier subsumes them with superior alpha.

### Quality Core (QualityEntryGate)

| Condition | Directive |
|---|---|
| `cascade_state == BEAR` | Sizing 25% (hard reduction) |
| `cascade_state == CORRECTION` | Sizing 50% |
| `sentiment_regime == CAPITULATION` + day 11+ | Boost sizing ×1.75 (highest conviction) |
| `sentiment_regime == CAPITULATION` + day 1-10 | Boost sizing ×1.25 (immature — wait preferred) |
| `sentiment_regime == RECOVERY` | Boost sizing ×1.3 (reversal confirming) |
| `sentiment_regime == COMPLACENCY` | Sizing -30% (only negative regime) |
| `sentiment_regime == DISTRIBUTION` | Alert + sizing -20% (smart money hedging) |
| `phase == DECLINING + F&G < 25` | Boost ×1.5 (t=2.76, strongest signal) |
| `phase == ADVANCING + F&G < 25` | **BLOCK** (WR=42%, it's a trap) |
| `credit_regime == STRESS` | Reduce sizing 50%, alert |

### Quality Swing (SwingGate)

| Condition | Directive |
|---|---|
| `cascade_state == PULLBACK` | Increase accumulation conviction |
| `cascade_state == BEAR` | **BLOCK** new accumulation |
| `sentiment_regime == CAPITULATION` + day 11+ | Boost ×1.75 |
| `sentiment_regime == RECOVERY` | Boost ×1.3 (accumulate reversals) |
| `sentiment_regime == COMPLACENCY` | **BLOCK** new accumulation |
| `sentiment_regime == WALL_OF_WORRY` | Normal sizing (no edge) |
| `fg > 75 + pcr > 1.0` | Boost ×1.2 (Wall of Worry — WR=82%) |

### CIO Allocator (synthesize_live_mandate)

| Condition | Directive |
|---|---|
| `convergence_direction == RISK_OFF` | Tilt to 90/10 Q/S |
| `convergence_direction == RISK_ON` | Allow up to 60/40 Q/S |
| `macro_regime == CONTRACTION` | Defensive allocation |
| `sentiment_regime == COMPLACENCY` | Cap speculative budget, reduce exposure |
| `sentiment_regime == CAPITULATION` | Allow aggressive rebalancing into equity |

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
