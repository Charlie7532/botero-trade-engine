# S5FI — S&P 500 % Above 50-DMA
## Indicator Personality Profile

### What It Measures
Percentage of S&P 500 constituent stocks trading above their 50-day
moving average. Same family as S5TH (200-DMA) and S5TW (20-DMA) —
identical nature, identical data source, identical calculation method.
The three form a breadth triad at different time horizons:

| Indicator | MA Period | Horizon | Role |
|---|---|---|---|
| **S5TW** | 20-DMA | Tactical (days/weeks) | Fast — detects swings |
| **S5FI** | 50-DMA | Intermediate (weeks/months) | Bridge — detects rolling corrections |
| **S5TH** | 200-DMA | Structural (months/quarters) | Slow — detects regime changes |

### Data Source
- **Historical**: TradingView `INDEX_S5FI` (4,892 bars from 2006-12-29)
- **Live**: Calculated daily by daemon from SP500-member OHLCV bars (506 tickers)
- Same source and method as S5TH and S5TW — only the MA window differs


### Mechanical Behavior (HYPOTHESIS — requires expert committee review)
- Moves at intermediate speed — slower than S5TW, faster than S5TH
- Range: 0% (complete intermediate breakdown) to 100% (all stocks in uptrend)
- Typical oscillation: 30%-70% in normal markets
- "Rolling corrections" visible as S5FI declining while S5TH holds — stocks
  rotating below 50-DMA sector by sector without a broad structural break

### Expert Committee Questions (PENDING)
- How does S5FI divergence vs S5TH predict sector rotation speed?
- What S5FI threshold differentiates "rolling correction" vs "structural decline"?
- Does S5FI crossing below S5TW signal acceleration of selling?
- Should this be used in Quality gates, Speculative gates, or both?

### Observed Correlations (HYPOTHESIS — not validated OOS)
- S5TH: moderate positive (structural parent)
- S5TW: strong positive (tactical sibling)
- VIX: moderate negative

### Known Limitations
- Requires 50+ trading days per ticker to calculate
- Intermediate speed means it confirms rather than predicts
- New indicator — no validation history yet

### Signals (HYPOTHESIS — all require walk-forward validation)
None defined yet. Requires expert committee + preliminary simulation.

### Live Feed
✅ Calculated daily from SP500 stocks in vault (added 2026-05-11)
