# VIX Regime Classification
## Indicator Personality Profile

### What It Measures
CBOE Volatility Index — the market's implied 30-day volatility expectation.
Used as a fear/complacency gauge and regime classifier.

### Data Source
- **Historical**: TradingView — 4 timeframes available:
  - `1d`: 8,343 bars from 1993 (+ 9,155 existing from yfinance = 17,498 total)
  - `1h`: 7,174 bars from Apr 2024
  - `15m`: 8,673 bars from Sep 2025
  - `5m`: 10,200 bars from Feb 2026 (0DTE gamma detection)
- **Live**: yfinance (`^VIX`) via `vault_vix_live` — every daemon cycle

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
- 5m data enables 0DTE gamma flip detection (Karsan mechanics)

### Known Limitations
- Spot VIX is a LEVEL, not a SIGNAL — knowing VIX=20 doesn't predict direction
- VIX regime transitions happen fast — by the time you detect "panic",
  the move is often 50% done
- VIX < 15 (extreme calm) can persist for months — not actionable alone

### Live Feed
✅ Every daemon cycle from yfinance
