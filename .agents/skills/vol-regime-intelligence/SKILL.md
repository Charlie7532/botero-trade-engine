---
name: vol-regime-intelligence
description: |
  Volatility Regime Intelligence — transversal SERVICE skill.
  Defines the volatility state machine for both QUALITY and SPECULATIVE departments.
  Classifies regime from observable vol metrics (persistence, stability, duration, VIX).
  Emits per-department behavioral directives: what each tool CAN and CANNOT do
  in each regime. Consumed by entry gates, risk managers, and the CIO.
  Inspired by Mandelbrot (vol clustering), Dalio (cycles/templates), and
  the predator-prey dynamics of market microstructure.
department: SERVICE
layer: persona
requires: [operational-purpose, clean-architecture]
modules: [volatility_regime, simulation, entry_decision, execution]
mcp_servers: [yahoo-finance, fred]
crewai_role: agent
---

# Volatility Regime Intelligence — State Machine

## Core Principle

> Volatility comes in clusters (Mandelbrot). Low volatility announces that something is about to end. High volatility announces that something is about to happen. Both states are PREDICTABLE because they auto-correlate. Every stock and ETF has its own volatility signature — its rhythm, intensity, and persistence.

This skill defines the **behavioral state machine** that translates raw volatility measurements into operational directives for each department. The measurements are sensors; this skill is the controller.

---

## Observable Inputs (Sensors)

All inputs are pure-domain calculations already available in the ML pipeline:

| Sensor | Feature | What it Measures | Source |
|---|---|---|---|
| **Vol Level** | `TS_RealVol_Fast`, `TS_RealVol_Slow` | Current absolute volatility | `engineer_features.py` C2 |
| **Vol Compression** | `TS_VolRatio` (Fast/Slow) | Squeeze (<1) vs Expansion (>1) | `engineer_features.py` C3 |
| **Vol Persistence** | `TS_VolPersistence` | Autocorrelation — how predictable is the cluster | `engineer_features.py` C5 |
| **Vol Stability** | `TS_VolOfVol_Ratio` | Vol-of-vol — can we trust ATR-based stops? | `engineer_features.py` C6 |
| **Calm Duration** | `TS_CalmDuration` | Consecutive bars below mean vol (complacency) | `engineer_features.py` C7 |
| **Market Fear** | `MC_VIX_ZScore` | VIX vs its 60-day mean — macro fear level | `engineer_features.py` F1 |
| **Fear Velocity** | `MC_VIX_Velocity_ZScore` | Speed of VIX change — panic vs relief | `engineer_features.py` F2 |
| **Term Structure** | `MC_VIX_TermStructure` | Backwardation (panic) vs Contango (complacent) | `engineer_features.py` F3 |

---

## QUALITY State Machine — The Prey's Defense System

Quality positions are long-term tollkeeper holdings. Volatility is a **threat** — the predator approaching the watering hole. The state machine governs defense posture.

### States

```
                ┌─────────────┐
       ┌───────►│   NORMAL    │◄──────────┐
       │        │  Thesis OK  │           │
       │        └──────┬──────┘           │
       │               │                 │
  VIX normalizes    VIX > +1          CalmDur > 60
  Vol stabilizes    OR VolRatio > 1.3  AND VIX < -1
       │               │                 │
       │        ┌──────▼──────┐    ┌──────▼──────┐
       │        │  ELEVATED   │    │ COMPLACENT  │
       │        │  Defensive  │    │  Pre-Strike │
       │        └──────┬──────┘    └──────┬──────┘
       │               │                 │
       │           VIX > +2           Sudden VIX
       │           AND Vol spike      spike from
       │               │              complacency
       │        ┌──────▼──────────────────▼──────┐
       └────────┤           CRISIS               │
                │   Survival mode — thesis only   │
                └─────────────────────────────────┘
```

### Behavioral Rules Per State

#### NORMAL — Business as Usual
**Conditions**: VIX_ZScore ∈ [-1, +1], CalmDuration < 60, VolOfVol_Ratio < median

| Module | Behavior | Rationale |
|---|---|---|
| `entry_decision` | New entries ALLOWED. Standard gate pipeline. | No regime threat. |
| `execution` | Sizing at Druckenmiller standard (conviction-based). | Normal conditions. |
| `portfolio_management` | Watchlist scanning active. Universe filtering standard. | Business as usual. |
| Risk (Druckenmiller) | Thesis review cadence: quarterly. | No urgency. |

#### COMPLACENT — The Lake Has Been Safe Too Long
**Conditions**: CalmDuration > 60 AND VIX_ZScore < -1 AND VolPersistence > 0.8 (stable low vol)

> [!WARNING]
> This is Dalio's "beautiful calm before the storm." The longer the calm, the bigger the eventual disruption. The prey are fattened and predictable.

| Module | Behavior | Rationale |
|---|---|---|
| `entry_decision` | New entries ALLOWED but with REDUCED sizing (0.75×). | Don't accumulate more when everyone is complacent. |
| `execution` | NO new position increases. Existing positions held. | Druckenmiller: don't pile in when the market is too calm. |
| `portfolio_management` | INCREASE thesis review frequency to monthly. Stress-test every moat. | Hohn: "What could kill this?" becomes urgent. |
| Risk (Druckenmiller) | Begin mentally preparing exits for weakest-thesis positions. | Not selling yet — but knowing WHERE the exit is. |
| CIO (Dalio) | Alert: "Complacency detected. Debt cycle template says watch credit spreads." | Template matching activation. |

#### ELEVATED — The Predator is Near
**Conditions**: VIX_ZScore ∈ [+1, +2] OR (VolRatio > 1.3 AND VolPersistence > 0.6)

| Module | Behavior | Rationale |
|---|---|---|
| `entry_decision` | New entries RESTRICTED to ultra-high-conviction only (Ceiling Sharpe > 1.5). | Only tollkeepers with proven robustness. |
| `execution` | Sizing REDUCED to 0.5× standard. No position increases. | Druckenmiller: size down in hostile vol. |
| `portfolio_management` | Switch from "scanning" to "defending." Focus on thesis integrity, not new candidates. | The time for shopping is over. |
| Risk (Druckenmiller) | Thesis review cadence: WEEKLY. Flag any moat showing stress. | Accelerated surveillance. |
| CIO (Dalio) | Evaluate QUALITY→SPECULATIVE capital rebalance. Vol = opportunity for the predator. | The CIO sees both sides of the coin. |

#### CRISIS — Survival Mode
**Conditions**: VIX_ZScore > +2 AND (VIX_Velocity_ZScore > +2 OR VolOfVol_Ratio > historical 90th percentile)

> [!CAUTION]
> In crisis, the only question is: "Is the thesis dead?" Price action is noise. Do NOT sell because the price dropped. Sell ONLY if the business is structurally impaired.

| Module | Behavior | Rationale |
|---|---|---|
| `entry_decision` | ZERO new entries. Pipeline frozen. | Capital preservation. |
| `execution` | Thesis-death exits ONLY. Hold everything else with conviction. | Druckenmiller: "Markets recover. Dead businesses don't." |
| `portfolio_management` | Halt all scanning. 100% focus on thesis integrity of existing positions. | Triage mode. |
| Risk (Druckenmiller) | Thesis review: DAILY. Any moat breach → immediate CIO escalation. | Maximum vigilance. |
| CIO (Dalio) | If template matches "beautiful deleveraging" pattern → HOLD. If "ugly deflation" → LIQUIDATE weakest 20%. | Template matching is the decision framework. |

### QUALITY Transition Alerts

| Transition | Signal | What it Means |
|---|---|---|
| NORMAL → COMPLACENT | CalmDuration crosses 60, VIX drops below -1σ | "The lake is too calm. Predator is somewhere." |
| COMPLACENT → ELEVATED | Sudden VIX spike from low base (Velocity > +2) | "The attack begins. Were we prepared?" |
| COMPLACENT → CRISIS | VIX jumps directly to +2σ from complacent state | "Black swan from calm." Maximum danger. |
| ELEVATED → CRISIS | Vol persists and accelerates (VolPersistence stays high) | "This isn't a correction. It's a regime change." |
| CRISIS → ELEVATED | VIX starts declining but still above +1σ | "Worst may be over. Don't relax yet." |
| ELEVATED → NORMAL | VIX normalizes, VolRatio returns < 1.0 | "All clear. Resume normal operations." |

---

## SPECULATIVE State Machine — The Predator's Hunt Cycle

Speculative positions are short-term tactical trades. Volatility is a **weapon** — the predator's hunting tool. The state machine governs the hunt cycle.

### States

```
                ┌─────────────┐
       ┌───────►│   STALK     │◄──────────┐
       │        │ Observe &   │           │
       │        │ Wait        │           │
       │        └──────┬──────┘           │
       │               │                 │
  Vol stabilizes    Compression break     Vol becomes
  VoV drops         VIX_Vel > +1.5        chaotic
       │               │                 │
       │        ┌──────▼──────┐    ┌──────▼──────┐
       │        │  STRIKE     │    │  RETREAT    │
       │        │  Execute!   │    │  Protect    │
       │        └──────┬──────┘    └─────────────┘
       │               │                 ▲
       │           Vol persists          │
       │           (cluster)         VoV spikes
       │               │                 │
       │        ┌──────▼──────┐           │
       └────────┤  HARVEST    ├───────────┘
                │  Ride trend  │
                └──────────────┘
```

### Behavioral Rules Per State

#### STALK — The Predator Observes
**Conditions**: CalmDuration > 20, VolPersistence > 0.7 (in low vol), VolRatio < 0.8 (compressed)

> The vol is low and predictable. The prey (retail) are comfortable. The predator scans for the setup.

| Module | Behavior | Rationale |
|---|---|---|
| `entry_decision` | Entries ALLOWED but with MINIMUM sizing (exploration only). | Seykota: small probes to test the water. |
| `options_gamma` | ACTIVE monitoring: GEX levels, Vanna dates, Max Pain. | Karsan: mapping dealer energy for the coming move. |
| `flow_intelligence` | ACTIVE monitoring: sweeps, dark pool prints, institutional flow. | Eifert: "Who is positioning and why?" |
| Risk (Seykota) | TIGHT time stops (2 sessions). Sizing at 0.5× base. | Don't bleed capital waiting for the move. |
| Signal Miner (Simons) | Run cross-asset vol scans. Look for divergences (one stock's vol breaking while market is calm). | The spider builds the web. |

**Eifert Opportunity**: In STALK, implied vol is typically depressed (contango). This is the time to buy cheap options as asymmetric bets for the coming vol expansion.

#### STRIKE — The Predator Attacks
**Conditions**: Transition from compressed to expanding vol (VolRatio crosses above 1.0 from below) AND (VIX_Velocity > +1.5 OR CalmDuration just broke after > 30)

> The compression breaks. The move begins. Execute decisively.

| Module | Behavior | Rationale |
|---|---|---|
| `entry_decision` | FULL pipeline activated. Standard sizing or above. | PTJ: "When you see it, hit it. Don't hesitate." |
| `options_gamma` | If GEX is negative → dealers will AMPLIFY the move. GO WITH the direction. | Karsan: "Negative GEX = forced selling = ride the wave." |
| `flow_intelligence` | Validate that institutional flow CONFIRMS the direction. | Eifert: don't fight smart money. |
| Risk (Seykota) | WIDE stops (2.5-3× ATR). The move will be volatile — give it room. | Seykota: "Don't set stops where the noise will take you out." |
| Risk (Seykota) | Anti-martingale ON: if profitable, ADD to position (pyramid up). | Seykota: "Ride winners aggressively." |
| Risk (Seykota) | Time stops: 3-5 sessions (extended from STALK's 2). | The move needs time to develop. |

**PTJ Asymmetry Gate Enhancement**: In STRIKE mode, the R:R threshold drops from 5:1 to 3:1 because the directional edge from the compression breakout provides inherent asymmetry.

#### HARVEST — The Predator Feeds
**Conditions**: VolPersistence > 0.7 in high vol (confirmed cluster, move underway), VolRatio > 1.2 sustained

> The move is in progress. Don't chase new setups — ride existing winners.

| Module | Behavior | Rationale |
|---|---|---|
| `entry_decision` | NO new entries. Only manage existing positions. | Seykota: "Don't chase. You already have the prey." |
| `options_gamma` | Monitor for GEX flip (neg→pos). That's the kill signal. | Karsan: when dealers stop amplifying, the move exhausts. |
| Risk (Seykota) | Trailing stops at 1.5× ATR (tighter than STRIKE). | Lock in profits progressively. |
| Risk (Seykota) | Anti-martingale OFF (no new additions). | The opportunity window is closing. |
| Risk (Seykota) | Time stops: 2-3 sessions remaining. | Don't overstay. |

**Seykota Exit Wisdom**: "The trend is your friend until the end when it bends." In HARVEST, you're watching for the bend — the moment vol persistence breaks.

#### RETREAT — The Predator Withdraws
**Conditions**: VolOfVol_Ratio > historical 80th percentile (vol itself is unstable) OR VIX_ZScore > +3 OR VolPersistence drops below 0.3 suddenly

> Vol is chaotic. ATR stops are unreliable. The rules themselves are changing. Only action: protect capital.

| Module | Behavior | Rationale |
|---|---|---|
| `entry_decision` | FROZEN. Zero entries. | The market is a casino — don't play when the rules change every minute. |
| `execution` | Close everything not in profit > 2R. | Seykota: "When in doubt, get out." |
| Risk (Seykota) | Stops TIGHTENED to 1× ATR (emergency). | Minimize damage from erratic price action. |
| Risk (Seykota) | Time stops HALVED (1-2 sessions max for anything open). | Don't let positions bleed. |
| Risk (Seykota) | Sizing at MINIMUM (0.25× base) if any exposure remains. | Survival is the only objective. |
| Signal Miner (Simons) | OBSERVE ONLY. Log the chaos for future pattern analysis. | The spider records but doesn't hunt in a hurricane. |

### SPECULATIVE Transition Alerts

| Transition | Signal | What it Means | PTJ Analogy |
|---|---|---|---|
| STALK → STRIKE | VolRatio crosses 1.0 from below, VIX velocity spikes | "The compression breaks. The move is ON." | "I see 5:1. Fire." |
| STRIKE → HARVEST | VolPersistence stays > 0.7, move has been running 3+ bars | "The move is maturing. Stop chasing." | "We're in. Now ride it." |
| HARVEST → RETREAT | VolOfVol spikes, VolPersistence drops sharply | "The move is exhausting into chaos." | "Take profits and go home." |
| HARVEST → STALK | Vol normalizes, VolRatio drops below 1.0, VIX calms | "The hunt is over. Reset." | "Wait for the next setup." |
| RETREAT → STALK | VolOfVol normalizes, VIX below +1σ | "The storm passed. Rebuild the web." | "Start scanning again." |
| Any → RETREAT | VolOfVol extreme spike | "Emergency. Everything is unreliable." | "Flat. Now." |

---

## Cross-Department Coordination (CIO Level)

The CIO (Dalio) observes BOTH state machines simultaneously:

| Quality State | Speculative State | CIO Directive |
|---|---|---|
| NORMAL | STALK | Standard allocation (80/20). Both departments in routine. |
| COMPLACENT | STALK | Alert: "Calm before storm." Consider shifting 5% from QUALITY to SPECULATIVE for cheap vol bets. |
| ELEVATED | STRIKE | Speculative is hunting while Quality is defending. **Ideal**: the 20% earns while the 80% protects. |
| CRISIS | RETREAT | Total defense. Both departments minimizing exposure. Cash is a position. |
| NORMAL | STRIKE | Rare but possible (sector-specific vol while market is calm). Let Speculative run. Quality unaffected. |
| ELEVATED | HARVEST | Speculative riding the move that is pressuring Quality. CIO monitors for rebalancing opportunity. |

---

## Integration Points

### ML Pipeline
The vol regime should be injected as a categorical feature:
- `RG_VolRegime_Quality`: 0=NORMAL, 1=COMPLACENT, 2=ELEVATED, 3=CRISIS
- `RG_VolRegime_Speculative`: 0=STALK, 1=STRIKE, 2=HARVEST, 3=RETREAT

### Entry Gates
Both `QualityEntryGate` and `SpeculativeEntryHub` should consult the regime before evaluating any signal:
```
Gate -1: Vol Regime Check → Apply sizing/permission overrides from this skill
```

### Risk Managers
Both `risk-quality` (Druckenmiller) and `risk-speculative` (Seykota) should reference this skill for regime-dependent stop/sizing rules.

### Oracle Backtest
`oracle_backtest.py` should tag each labeled entry with `vol_regime_at_entry` to enable per-regime autopsy via `trade-forensics`.

---

## Evidence Status Tags

| Rule | Evidence Status | Validation Path |
|---|---|---|
| Vol clustering is real | ✅ EMPIRICAL — Mandelbrot (1963), confirmed in our data (TS_VolPersistence in ML pipeline) | Direct measurement |
| VIX term structure predicts regime | ✅ EMPIRICAL — MC_VIX_TermStructure is #3 in model importance (4.87%) | ML feature importance |
| CalmDuration predicts vol spikes | ⚠️ HYPOTHESIS — Implemented as feature, not yet validated per-regime | Needs stratified backtest |
| VolOfVol invalidates ATR stops | ⚠️ HYPOTHESIS — Mechanical logic is sound, not yet backtested | Needs trade-forensics with vol regime tag |
| Sizing multipliers (0.5×, 0.75×, etc.) | ⚠️ HYPOTHESIS — Heuristic values, need calibration | Walk-forward optimization |
| CalmDuration threshold (60 bars) | ⚠️ HYPOTHESIS — Arbitrary, needs empirical calibration | Sensitivity analysis |
| VIX_ZScore thresholds (+1, +2) | ⚠️ HYPOTHESIS — Standard deviation boundaries, may need asset-specific tuning | Regime-stratified backtest |

---

## Code Mapping

| Concept | Location | Status |
|---|---|---|
| Vol Regime Classifier | `backend/modules/volatility_regime/domain/rules/vol_classifier.py` | ✅ Live (160 lines) |
| Vol Regime Entity | `backend/modules/volatility_regime/domain/entities/vol_regime.py` | ✅ Live (44 lines) |
| Vol Sensors (Features) | `backend/modules/simulation/application/use_cases/engineer_features.py` | ✅ C5-C7 + F1-F3 |
| ML Integration | `engineer_features.py:extract_vol_regime_features()` → `RG_VolRegime_*` | ✅ Live |
| Entry Gate Override (Quality) | `entry_decision/application/use_cases/quality_entry_gate.py` | 🔲 Phase 2 — Gate -1 |
| Entry Hub Override (Speculative) | `entry_decision/application/use_cases/speculative_entry_hub.py` | 🔲 Phase 2 — Gate -1 |
| Trade Forensics Tag | `oracle_backtest.py` → `vol_regime_at_entry` | 🔲 Phase 2 |
