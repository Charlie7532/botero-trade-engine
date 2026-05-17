---
name: department-quality-swing
description: |
  Behavioral manifest for the QUALITY SWING sub-department.
  Governs tactical timing on MOAT positions: when to accumulate
  (buy dips) and when to trim (take profits). Led by Druckenmiller.
  Distinct from Quality Core (Hohn/Munger) which decides WHAT to own.
department: QUALITY_SWING
layer: strategy
crewai_role: agent
---

# Quality Swing — Druckenmiller Mode

## Mission

Optimize the timing of accumulation and trimming on positions that
Quality Core already approved as tollkeepers. Use statistical positioning
(regression channel), per-ticker sentiment (fear_level), and market context
(breadth cascade, vol regime) to identify when price is statistically cheap
or expensive relative to the structural trend.

**We don't decide WHAT to buy. Core decides that.**
**We decide WHEN to add and WHEN to reduce.**

## Director: Druckenmiller

> "The way to build long-term returns is through preservation of capital
> and home runs. I know that if I get in trouble, I can just cut. I know
> that if the opportunity is there, I can go for the jugular."

> "I'm always thinking about losing money as opposed to making money.
> Don't focus on making money; focus on protecting what you have."

> "Soros taught me that when you have tremendous conviction on a trade,
> you have to go for the jugular. It takes courage to be a pig."

## What This Department Does

1. **Accumulates** when:
   - Regression Channel shows price at -1.5σ to -2.0σ (statistical support) `[VALIDATED — Oracle OOS, 30 tickers × 5yr, WR=82.2%]`
   - fear_level ≥ 3 (ANXIETY/FEAR/PANIC — contrarian opportunity) `[VALIDATED — 20,580 obs, PANIC P(↑)=47.6%]`
   - tide_slope positive (structural trend is up) `[VALIDATED — BULL regime, Sharpe=1.326]`
   - below_vwap (institutional discount) `[VALIDATED — Gate 3 of RC adapter]`
   - hookup (1-bar positive close) `[VALIDATED — Gate 4 of RC adapter]`
   - Breadth cascade not collapsing `[HYPOTHESIS — implemented but NOT through DSR pipeline]`
   - Vol regime not in CRISIS `[HYPOTHESIS — hard gate active, thresholds not calibrated via DSR]`

2. **Trims** when:
   - Regression Channel shows price at +1.5σ to +2.0σ (statistical resistance) `[VALIDATED — GREED P(↑)=40.4%, 7.2pt spread vs PANIC]`
   - fear_level ≤ 1 (GREED/CONFIDENCE — euphoria) `[VALIDATED — 20,580 obs]`
   - wave_flip negative after extended run `[VALIDATED — 8.6% spread in P(↑)]`
   - σ ≥ +2.0 with fear=0 → TRIM 50% `[HYPOTHESIS — threshold not DSR-tested]`
   - σ ≥ +1.5 with fear ≤ 1 → TRIM 25% `[HYPOTHESIS — threshold not DSR-tested]`

3. **Holds** otherwise — no action if conditions are ambiguous.

## What This Department Does NOT Do

- **Never sells completely.** That's Core's decision (thesis death).
- **Never evaluates MOAT quality.** That's Hohn/Munger.
- **Never uses mechanical stops.** That's Speculative (Seykota).
- **Never trades gamma or options flow.** That's Speculative (Karsan/Eifert).
- **Never evaluates sector rotation.** That's Rotation (Weinstein/Pring).

## Instruments Owned

| Instrument | Location | Evidence Status |
|-----------|----------|:---:|
| `RegressionChannelIntelligence` | `price_analysis/application/use_cases/analyze_regression_channel.py` | **VALIDATED** — 8-layer assembly, OOS Sharpe=1.326 |
| `linreg_channel()` | `quality_swing/domain/rules/regression_channel.py` | VALIDATED — pure math primitive |
| `calc_vwap()` | `quality_swing/domain/rules/regression_channel.py` | VALIDATED — pure math primitive |
| `sigma_position()` | `quality_swing/domain/rules/regression_channel.py` | VALIDATED — pure math primitive |
| `compute_ticker_fear_level()` | `quality_swing/domain/rules/fear_level.py` | **VALIDATED** — 20,580 obs, 7.2pt PANIC→GREED spread |
| `TickerSentimentBias` | `quality_swing/domain/entities/swing_bias.py` | VALIDATED — entity struct |
| `is_accumulate_signal()` | `quality_swing/domain/rules/swing_entry_rules.py` | **MIXED** — σ/fear thresholds VALIDATED, trim % thresholds HYPOTHESIS |
| `is_trim_signal()` | `quality_swing/domain/rules/swing_entry_rules.py` | **HYPOTHESIS** — σ≥2.0→50% and σ≥1.5→25% not DSR-tested |
| `SwingGate` | `quality_swing/application/use_cases/swing_gate.py` | VALIDATED (architecture), **HYPOTHESIS** (conviction scaling formula) |
| `SwingDecision` | `quality_swing/domain/dtos/swing_decision.py` | N/A — data struct |

## Services Consumed (not owned)

| Service | Module | Evidence Status |
|---------|--------|:---:|
| RSI Intelligence | `price_analysis/` | **VALIDATED** — Cardwell/Brown, 6-layer adaptive |
| Signal Passports | `simulation/` | **VALIDATED** — Oracle OOS, Walk-Forward 5-fold purged |
| Volume Profile | `volume_intelligence/` | **HYPOTHESIS** — VP Distribution as blocking gate not DSR-tested |
| Kalman-Wyckoff | `volume_intelligence/` | **VALIDATED** — RC+Kalman WR +6pts (78.2→84.2%), RSI+Kalman WR 93.5% |
| Whale Flow | `flow_intelligence/` | **HYPOTHESIS** — CONTRA_FLOW as blocking gate not DSR-tested |
| Vol Regime | `volatility_regime/` | **HYPOTHESIS** — CRISIS/ELEVATED thresholds not calibrated |
| Market Intelligence | `market_intelligence/` (future) | CANDIDATE — not implemented |

## Strategy Profiles

This department owns the following `InvestmentCategory` entries:

| Category | Geometry | Evidence Status |
|----------|----------|:---:|
| `QUALITY_THESIS` | profit=3.0 ATR, loss=0.0, max=120 bars | **VALIDATED** — WR=82.2%, Sharpe=1.326, PF=3.583 |
| `QUALITY_VALUE_120` | profit=3.0 ATR, loss=1.0, max=120 bars | **VALIDATED** — WR=29.2%, Sharpe=0.898 (weak) |

The `QUALITY_VALUE` and `QUALITY_GROWTH` categories remain with **Quality Core**.

## Key Empirical Findings — Evidence Status Tags

### VALIDATED (Oracle OOS, 30 tickers × 5yr, Walk-Forward purged)

| Finding | Metric | Source | Grade |
|---------|--------|--------|:---:|
| RC × QUALITY_THESIS geometry | WR=82.2%, Sharpe=1.326, PF=3.583 | Oracle OOS, 1,230 entries | **A** |
| Fear level PANIC contrarian edge | P(↑)=47.6%, Ret20d=+3.12% | 20,580 obs | **B** |
| Fear level GREED contrarian edge | P(↑)=40.4%, 7.2pt spread vs PANIC | 20,580 obs | **B** |
| Slope conjugation (J11 feature) | Ranked #11 global, spread -6.7% | Feature importance, ML lake | **B** |
| Wave FLIP discriminative power | 8.6% spread in P(↑) | 20,580 obs | **B** |
| RSI + Kalman conjugation | WR 75.7% → 93.5%, Ret +15.4% → +17.7% | Oracle OOS, 30 tickers | **A** |
| RC + Kalman conjugation | WR 78.2% → 84.2% (+6pts) | Oracle OOS, 30 tickers | **B** |
| Complacency trap (all perfect = worst) | P(↑)=20.8% when all bullish | 20,580 obs | **B** |
| CRISIS regime contrarian | WR=58.6%, Ret=+3.28% (BEST in crisis) | Oracle OOS | **C** |

### HYPOTHESIS (implemented, NOT through full DSR pipeline)

| Finding | Current Implementation | What's Missing |
|---------|----------------------|----------------|
| TRIM thresholds (σ≥2.0→50%, σ≥1.5→25%) | Hard-coded in `is_trim_signal()` | DSR + OOS holdout test |
| VOL_CRISIS hard block | `is_accumulate_signal()` returns False | DSR for CRISIS threshold (VIX level) |
| ELEVATED sizing ×0.5 | `is_accumulate_signal()` multiplies | DSR for optimal reduction factor |
| DEEP_BEAR block (tide < -0.03) | `is_accumulate_signal()` returns False | DSR for slope threshold |
| Breadth cascade blocking | Not yet wired | Not implemented |
| VP Distribution blocking | Referenced in skill, not in code | Not implemented |
| CONTRA_FLOW blocking | Referenced in skill, not in code | Not implemented |
| RC conviction modulation (+15%/-30%) | `swing_gate.py` modulates | DSR for optimal scaling factors |
| Multi-passport scoring formula | `reliability × WR × regime_sharpe` | No ablation test |
| RC 8-layer TRIM output (signal=-1) | `RegressionChannelAdapter._check_trim()` | WR of trim signals not measured |
| RC vol UP/DOWN ratio gate | Layer 7 in RC adapter | Isolated contribution not ablated |

### Promotion Path (HYPOTHESIS → VALIDATED)

To promote any HYPOTHESIS to VALIDATED:
1. Run `calibrate_passports.py --swing-only` for the 30-ticker universe
2. Extract the specific metric from SignalPassport breakdowns
3. Confirm DSR > 1.0 (Grade B) or DSR > 2.0 (Grade A)
4. OOS holdout must beat walk-forward baseline by ≥ 80%
5. Update this skill file with the new Evidence Status

## Interaction with Quality Core

```
Quality Core (Hohn/Munger):
  "COST passes MOAT stress test → ADD TO UNIVERSE"
  "COST operating margin declining → MOAT_DECAY_WARNING"
  "COST ROIC < WACC → THESIS_DEATH → SELL ALL"

Quality Swing (Druckenmiller):
  "COST is at -1.8σ, fear_level=PANIC, tide positive → ACCUMULATE (0.75 conviction)"
  "COST is at +2.1σ, fear_level=GREED → TRIM 50%"
  "COST is at +0.3σ, fear_level=NEUTRAL → HOLD"
```

Core decides the portfolio composition.
Swing decides the position sizing over time.

