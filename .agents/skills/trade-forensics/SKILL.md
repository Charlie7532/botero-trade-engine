---
name: trade-forensics
description: >
  Closed-loop trade forensics for both departments. 
  Speculative (Seykota): Detect pattern failures → calibrate stops → retrain Memory Guard.
  Quality (Druckenmiller): Detect thesis inaccuracy → measure surveillance lag → enforce blacklist.
  Runs the Detect → Learn → Retrain → Prevent cycle.
department: VALIDATION
layer: tool
requires: [operational-purpose, clean-architecture]
modules: [simulation, execution]
mcp_servers: []
crewai_role: agent
---

# Trade Forensics — Closed-Loop Learning System

## When to Activate

- After any trade is CLOSED (automatically via journal close_trade)
- Weekly learning report generation
- When user asks for post-mortem analysis
- When a pattern shows declining win rate

## Dual-Department Forensics

### SPECULATIVE (Seykota Loop)

The Seykota Loop runs on `engine.trade_journal_speculative` and focuses on
**execution quality**, not just outcome.

#### DETECT
```
SELECT exit_reason, COUNT(*), 
       AVG(pnl_r_multiple) as avg_r,
       AVG(max_adverse_excursion_pct) as avg_mae,
       AVG(max_favorable_excursion_pct) as avg_mfe
FROM engine.trade_journal_speculative
WHERE status = 'CLOSED' AND created_at > NOW() - INTERVAL '90 days'
GROUP BY exit_reason
ORDER BY avg_r ASC
```

Key diagnostic questions:
1. **Stop calibration**: Is avg MAE > initial stop distance? → Stops too tight
2. **MFE capture**: Is avg exit price < avg MFE? → Exiting too early
3. **Pattern decay**: Any pattern_tag with WR < 40% over last 20 trades? → Blacklist pattern
4. **Regime blindness**: Are losses concentrated in specific vol regimes?
   - Weinstein: `GROUP BY RG_WinsteinProxy` from ML Data Lake features
   - Vol regime: `GROUP BY RG_VolRegime_Quality` (or `_Speculative`)
   - Source: `VolRegimeClassifier` via `engineer_features.py`

#### LEARN
- Compute optimal trailing stop multiplier from MFE/MAE distribution
- Identify "blind spots" — combinations of (gamma_regime + wyckoff_state) that always lose
- Measure Memory Guard effectiveness — did blocked trades actually lose?

#### RETRAIN
- Export calibrated parameters to `AdaptiveTrailingStop` defaults
- Update `_vectorize_report()` weights if certain dimensions dominate false signals
- Feed findings to simulation module for walk-forward validation

#### PREVENT
- ≥3 consecutive losses on same pattern → auto-cooldown that pattern for 2 weeks
- Memory Guard vector similarity threshold tightening after streak
- Alert the tactical-entries skill to review entry criteria

---

### QUALITY (Druckenmiller Loop)

The Druckenmiller Loop runs on `engine.trade_journal_quality` and focuses on
**thesis accuracy** and **surveillance timeliness**.

#### DETECT
```
SELECT ticker, entry_thesis, thesis_death_reason,
       entry_roic, entry_operating_margin,
       EXTRACT(DAYS FROM (exit_time::timestamp - entry_time::timestamp)) as holding_days,
       pnl_pct, irr
FROM engine.trade_journal_quality
WHERE status = 'CLOSED'
ORDER BY exit_time DESC
```

Key diagnostic questions:
1. **Thesis accuracy**: Did the exit reason match the original thesis risk? → Measure conviction quality
2. **Surveillance lag**: How many quarters between moat deterioration start and THESIS_DEATH detection?
3. **Entry quality**: Were fundamentals (ROIC, margin) already declining at entry? → Tighten entry criteria
4. **Sector concentration**: Are losses concentrated in specific sectors? → Diversification issue

#### LEARN
- Compute "thesis accuracy score" — % of exits where exit_reason was predicted by entry_thesis
- Measure average quarters between actual moat decay and surveillance detection
- Build fundamental decay velocity curves per sector

#### RETRAIN
- Adjust `SurveillanceLoop._evaluate_moat_decay()` thresholds:
  - If detection lag > 2Q: tighten margin drop threshold from 15% to 12%
  - If capex bloat missed: lower capex multiplier from 1.25x to 1.20x
- Update `reduce_zone` calculation methodology

#### PREVENT
- 4Q blacklist after THESIS_DEATH (enforced by `InstrumentBlacklistPort`)
- If 2+ THESIS_DEATH exits in same sector within 1Y: flag sector for rotation review
- Cross-reference with `rotation-analyst` skill for macro confirmation

---

## Integration Points

| Component | How Forensics Connects |
|---|---|
| `orchestrate_paper_trading.generate_learning_report()` | Provides raw data for DETECT phase |
| `AdaptiveTrailingStop` (exit_rules.py) | Receives calibrated params from RETRAIN |
| `InstrumentBlacklistPort` | Enforces PREVENT blacklists |
| `SurveillanceLoop._evaluate_moat_decay()` | Receives adjusted thresholds from RETRAIN |
| `EntryHub._vectorize_report()` | Receives weight adjustments from RETRAIN |
| `simulation` module | Validates recalibrations via walk-forward |
| `TripleBarrierAdapter` (MAE/MFE/sweep) | Persists forensic excursion data per label |
| `engine.ml_labels` (Neon) | Stores MAE, MFE, post_exit_hit_target, stop_was_sweep |
| `RegressionChannelAdapter` (slope conjugation) | Provides J11 feature for forensic analysis |

## Validated Forensic Findings (Empirical)

> [!IMPORTANT]
> These findings are persisted in the ML Data Lake and can be queried via
> `engine.ml_labels` forensic columns.

### MAE/MFE Analysis (Quality Department)

- **53.8%** of stop-outs eventually hit the original profit target (false negatives).
- Only **5.6%** were genuine liquidity sweeps.
- Average MAE at stop: **-2.7%**. Average MFE before stop: **+4.5%**.
- **Action taken**: Created `QUALITY_THESIS` geometry (no mechanical stop, 120 bars).

### Slope Conjugation (Regression Channel)

- Winners enter during the dip: avg short slope = **-0.05** (negative).
- Losers enter late: avg short slope = **+0.04** (positive, wave already turned).
- This is captured as `MTF_SlopeConjugation_5` feature — **#2 importance** in XGBoost.

### BEAR Regime Filter

- All 5 BEAR losers had `slope_long < -0.05` (structural collapse, not pullback).
- Filter: `slope_long > -0.03` blocks structural collapses. BEAR WR: **100%** (N=2).

### Pattern Forensics — Candlestick Conjugation (DSR Validated, 2026-05-19)

Walk-Forward PCV (2yr Train / 6mo Test / 10d Purge / 5d Embargo) across 32 tickers
(30 Quality + SPY 1993→2026 + QQQ 1999→2026). Deflated Sharpe Ratio adjusted for N=10 trials.

**Grade C — Sizing Modifier (downgraded from A after 20yr deep validation):**

| Setup | WR (5yr) | WR (20yr) | N (20yr) | Status |
|---|---|---|---|---|
| **HYPER_3BC_MB** (base) | 66.5% | **62.9%** | 717 | Degraded: sobreajustada a crash 2022 |
| **MICRO_BM_MB** | 67.6% | pending | 102 | Needs 20yr re-validation |

**Narrative Signatures — Internal Pattern Intelligence (20yr data):**

When HYPER_3BC_MB fires, the INTERNAL composition of the 3 hyper-candles modifies signal quality:

| Narrative Signature | WR | N | Δ vs Base | Confidence |
|---|---|---|---|---|
| BEARISH_ENGULFING central (2nd hyper) | **73.9%** | 23 | **+11pp** | ×1.25 |
| BEARISH_MARUBOZU central (2nd hyper) | **75.0%** | 16 | **+12pp** | ×1.25 |
| TWEEZER_TOP central (2nd hyper) | **100%** | 7 | **+37pp** | Monitor (N low) |
| SHOOTING_STAR conclusión (3rd hyper) | **87.5%** | 8 | **+25pp** | Monitor (N low) |
| DRAGONFLY_DOJI central (anti) | **28.6%** | 7 | **-34pp** | ×0.50 |
| MORNING_STAR conclusión (anti) | **54.5%** | 22 | **-8pp** | ×0.60 |

**Anti-Señales (Sharpe negativo demostrado):**

| Setup | Sharpe OOS | WR OOS | N_OOS | Acción |
|---|---|---|---|---|
| HYPER_SS_A | -0.502 | 46.8% | 109 | VETO: Shooting Star en ALCISTA NO predice reversión |
| MACRO_SS_A | -1.079 | 41.7% | 120 | VETO: Destruye capital sistemáticamente |

**Key Insight**: La señal base HYPER_3BC_MB se degrada con historia profunda (estaba
sobreajustada a 2022), pero las **narrative signatures específicas** (la "palabra central"
del párrafo) mantienen su poder. La descomposición fractal es la fuente real de alpha,
no el patrón exterior. El Shooting Star en tendencia alcista, contrariamente al dogma,
no predice reversiones — su interpretación correcta en sentido inverso es una señal de
advertencia: "no entres aquí".

## Output Format

When generating a forensics report, structure as:

```markdown
## Trade Forensics Report — [DEPARTMENT] — [Date Range]

### 🔍 DETECT: Key Findings
- [Finding 1 with data]
- [Finding 2 with data]

### 📚 LEARN: Insights
- [Insight 1: what the data teaches us]
- [Insight 2: pattern or regime identified]

### 🔧 RETRAIN: Parameter Adjustments
- [Param 1: old → new value, reason]
- [Param 2: old → new value, reason]

### 🛡️ PREVENT: Rules Activated
- [Rule 1: what's now blocked/modified]
- [Rule 2: blacklist or cooldown applied]
```
