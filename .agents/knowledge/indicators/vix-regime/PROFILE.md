# VIX Regime Classification
## Indicator Personality Profile

### What It Measures
CBOE Volatility Index — the market's implied 30-day volatility expectation.
Used as a fear/complacency gauge and regime classifier.

### Regime Thresholds (Operational — Used by Daemon)
These thresholds are OPERATIONALLY active in `vault_vix_live()`:
- **Calm**: VIX < 18 — full allocation permitted
- **Elevated**: 18-25 — reduce new entries
- **Panic**: 25-35 — halt new entries
- **Crisis**: VIX > 35 — consider hedging

NOTE: These thresholds are operational heuristics, NOT backtested signals.
They need walk-forward validation to confirm sizing impact.

### Mechanical Behavior
- VIX is mean-reverting (long-term mean ≈ 19-20)
- VIX spikes are fast (days), VIX declines are slow (weeks/months)
- VIX has negative correlation with SPY (r ≈ -0.71 with RSI)
- VIX futures term structure (contango/backwardation) adds context
  but we currently only track spot VIX

### Known Limitations
- Spot VIX is a LEVEL, not a SIGNAL — knowing VIX=20 doesn't predict direction
- VIX regime transitions happen fast — by the time you detect "panic",
  the move is often 50% done
- VIX < 15 (extreme calm) can persist for months — not actionable alone
- We have 9,155 bars of VIX OHLCV (1990-2026) but our other indicators
  only go back to 2021, limiting cross-analysis window

### Current Reading (as of 2026-05-10)
- VIX: 17.2
- Regime: Calm
- VIX-RSI correlation: -0.714
