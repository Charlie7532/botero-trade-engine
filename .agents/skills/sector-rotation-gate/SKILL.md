---
name: sector-rotation-gate
description: |
  Empirical sector rotation gate — operational rules for the QualityEntryGate (V26).
  10 market regimes classified from S5/SV5 breadth indicators with per-regime
  allocation strategies validated across 27.5 years (1999-2026).
  Covers regime classification thresholds, sector selection logic, SPY blend in
  recovery, institutional volume filters, and quantified backtest results.
  Use when modifying the QualityEntryGate, adding new regimes, tuning thresholds,
  or auditing sector rotation behavior.
department: QUALITY
layer: tool
requires: [clean-architecture, operational-purpose, hypothesis-governance]
modules: [entry_decision]
crewai_role: injected
---

# Sector Rotation Gate — Empirical Operating Manual

> This skill captures 27.5 years of empirical validation (1999-2026).
> Every rule below is backed by quantitative evidence. No rule exists
> without a measured contribution in SPY-equivalent shares.

## Performance Summary (V26)

```
Buy & Hold SPY      → 100.00 acciones (benchmark)
V20 Baseline        → 206.74 acciones (+106.74)
V22 Core Filter     → 230.26 acciones (+130.26)
V23 Pro SV5 Diverg  → 346.87 acciones (+246.87)
V25 Pullback SV5_TW → 373.14 acciones (+273.14)
V26 Recovery SPY    → 381.98 acciones (+281.98)
```

## Source File

- [quality_entry_gate.py](/root/botero-trade/backend/modules/entry_decision/application/use_cases/quality_entry_gate.py)

---

## The 10 Market Regimes

### Classification Inputs

| Input | Source | Description |
|:---|:---|:---|
| `S5_TH` (th) | Market aggregate | % of S&P 500 stocks above 200-DMA (structural) |
| `S5_FI` (fi) | Market aggregate | % above 50-DMA (intermediate) |
| `S5_TW` (tw) | Market aggregate | % above 20-DMA (tactical) |
| `SV5_TH` (v_th) | Market aggregate | % with SMA(50,vol) > SMA(200,vol) |
| `SV5_FI` (v_fi) | Market aggregate | % with SMA(20,vol) > SMA(50,vol) |
| `SV5_TW` (v_tw) | Market aggregate | % with EMA(5,vol) > SMA(20,vol) |
| `sec_*` | Per-sector | Same indicators per SPDR sector ETF |
| `n_dead` | Derived | Count of sectors with S5_TH < 25% |
| `inv_fi_streak` | Derived | Consecutive days where S5_FI - SV5_FI < -5pp |

### Regime Classification Rules (Homologated [SEC_] Identifiers)

| # | HSA Standard Prefix | Legacy Regime | Entry Condition | Priority |
|:-:|:---|:---|:---|:-:|
| 1 | `SEC_SYSTEMIC_CRASH` | `CRASH_SISTEMICO` | TH<30 AND FI<25 AND TW<20 AND n_dead>=5 | 1 (highest) |
| 2 | `SEC_SECTOR_CAPITULATION` | `CAPITULACION_SECTORIAL` | TH<30 AND FI<25 AND TW<20 AND n_dead<5 | 1 |
| 3 | `SEC_PRE_CRASH_DISTRIBUTION` | `DISTRIBUCION_PRE_CRASH` | inv_fi_streak >= 10 | 2 |
| 4 | `SEC_GENERATIONAL_FLOOR` | `PISO_GENERACIONAL` | TH<=25 AND SV5_TW>=60 (volume capitulation) | 3 |
| 5 | `SEC_BULLISH_REACCUMULATION` | `RE_ACUMULACION_ALCISTA` | TH>=60 AND FI<=45 AND SV5_TW>=60 | 4 |
| 6 | `SEC_BEAR_RALLY` | `BEAR_RALLY` | TH<35 AND FI<30 AND TW>40 | 6 |
| 7 | `SEC_BULLISH_PULLBACK` | `PULLBACK_ALCISTA` | TH>40 AND FI>40 AND TW<30 (+ can_switch) | 7 |
| 8 | `SEC_HEALTHY_BULL` | `MERCADO_SANO` | TH>60 AND FI>50 AND TW>40 | 8 |
| 9 | `SEC_ROTATIONAL_RECOVERY` | `RECUPERACION` | TH<40 AND FI<35 AND TW>35 | 9 |
| 10 | `SEC_NORMAL` | `NORMAL` | Default state | 10 (lowest) |

### Regime Transition Rules

- `min_regime_days = 20` — prevents whipsaw between regimes
- `can_switch` = days in current regime >= 20
- `is_falling_knife` blocks rebalancing (not regime transition)
- Transitions from CRASH -> PISO require volume capitulation OR defensive floor (XLP_FI>=25)
- Transitions from RECUPERACION -> MERCADO_SANO require TH>50 AND FI>50

---

## Per-Regime Allocation Strategies

### Regime Efficiency (measured contribution per day)

| Regime | Days | Total Shares | per Day | Strategy |
|:---|---:|---:|---:|:---|
| PULLBACK_ALCISTA | 118 | +40.56 | +0.3438 | SV5 divergence + SV5_TW>=50 institutional dip filter |
| PISO_GENERACIONAL | 566 | +69.18 | +0.1222 | SV5-S5 divergence for floor selection |
| NORMAL | 240 | +27.35 | +0.1140 | Core sectors cap-weighted + satellite rotation |
| MERCADO_SANO | 4,342 | +184.33 | +0.0425 | Concentrated Core (6 sectors) beats SPY |
| RE_ACUMULACION | 237 | +1.45 | +0.0061 | Oversold core sectors (FI<=45) |
| DISTRIBUCION_PRE_CRASH | 931 | -9.87 | -0.0106 | 50% defensives (XLP/XLU/XLV), 50% cash |
| RECUPERACION | 82 | -9.60 | -0.1171 | 50% SPY + 50% sector leaders (V26) |
| CRASH_SISTEMICO | 188 | -25.75 | -0.1370 | 100% cash |

### MERCADO_SANO / NORMAL (68.3% of time)

```
Core Pool: [XLK, XLC, XLF, XLI, XLV, XLP] (80% cap-weighted)
Satellite: Best sector outside Core with TH>=40, FI<=35, RS_RoC>0, SV5-S5 div>10 (20%)
Core Filter: Exclude sectors with S5_FI < 55% (stagnation filter)
SPY: 0% — concentrated Core BEATS SPY by +195 shares over 27.5 years
```

CRITICAL: Never add SPY to MERCADO_SANO. The concentrated 6-sector Core outperforms
SPY because it excludes the ~20% dead weight (XLY, XLE, XLU, XLRE, XLB in non-leading periods).

### PULLBACK_ALCISTA (1.8% of time — HIGHEST efficiency)

```
Selection: Sectors where TH>45 AND TW<35 (oversold in bull market)
V25 Filter: SV5_TW >= 50% (institutional tactical volume = smart money buying dip)
Ranking: By SV5_FI - S5_FI divergence (institutional accumulation strength)
Fallback: Drop SV5_TW filter -> Drop TH/TW filter -> Top 5 by divergence
```

Why SV5_TW works: In pullbacks, price drops but structure holds (TH>45). SV5_TW>=50
means >50% of constituents have accelerating volume = institutions loading.
Backtest: +26.27 shares (V25).

### PISO_GENERACIONAL (8.4% of time)

```
Entry trigger: S5_TH <= 25% AND SV5_TW >= 60% (volume capitulation)
Selection: Top 5 sectors by SV5_FI - S5_FI divergence
Logic: Volume leads price at floors. Institutions accumulate BEFORE the bounce.
```

### DISTRIBUCION_PRE_CRASH (13.9% of time)

```
Trigger: inv_fi_streak >= 10 (SV5_FI > S5_FI for 10+ consecutive days)
Allocation: 50% in defensives [XLP, XLU, XLV] cap-weighted, 50% cash
Exit: When streak breaks AND TH > 50% (recovery confirmed)
```

### CRASH_SISTEMICO (2.8% of time)

```
Allocation: 100% cash
Exit: Volume capitulation OR defensive floor OR recovery breadth
```

### RECUPERACION (1.2% of time)

```
V26: 50% SPY + 50% sector leaders (by S5_FI, filtered by TW>35 and TH>25)
Logic: SPY captures broad rebound of sectors excluded from Core (XLY, XLE, XLB)
Backtest: +8.84 shares over sector-only strategy.
```

---

## Empirically Validated Principles

### What WORKS:
1. SV5-S5 divergence predicts floors — volume leads price BEFORE the move (+39 acc)
2. SV5_TW>=50 confirms institutional dip-buying — tactical volume spike in pullbacks (+26 acc)
3. Core concentration beats SPY — 6-sector Core outperforms full index (+195 acc)
4. 50% SPY in RECUPERACION captures broad rebound (+8.84 acc)
5. RS_RoC > 0 as satellite filter — eliminates value traps (+27 acc)
6. Core stagnation filter (FI>=55) — expels decaying sectors from Core

### What DOES NOT WORK:
1. Cash drag / confirmation waiting — loses V-rebound steepness (-51 acc)
2. VIX-based dynamic rotation — VIX too noisy at extremes (-78 acc)
3. SPY as refuge in bull markets — dilutes concentration (-195 acc)
4. Dynamic Core Pool expansion — concentration risk when pool empties (-36 acc)
5. SV5 divergence in RECUPERACION — picks laggards not leaders (-8 acc)
6. Hysteresis bands (50/55) in Core filter — retains decaying sectors (-1.78 acc)

---

## Anti-Patterns (DO NOT)

1. Never add SPY to MERCADO_SANO or NORMAL. Sector concentration wins.
2. Never use SV5 divergence after the move starts. Volume leads price only BEFORE inflection.
3. Never add complexity to rare regimes (BEAR_RALLY, CAPITULACION). ROI is zero.
4. Never make the Core Pool dynamic. Static list with purity filter is resilient.
5. Never wait for confirmation at floors. Speed beats precision for V-bounces.
6. Never use deterministic VIX thresholds for rotation. VIX is confirmatory, not predictive.

---

## File References

| File | Purpose |
|:---|:---|
| quality_entry_gate.py | Production gate (V26) |
| sectors.py | Sector ETF universe, cap weights, breadth tickers |
| sector_breadth_adapter.py | Infrastructure adapter for S5/SV5 breadth data |
| sector_rotation_flow.py | Domain rules for rotation logic |
