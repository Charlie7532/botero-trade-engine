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
4. **Regime blindness**: Are losses concentrated in specific VIX/gamma regimes?

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
