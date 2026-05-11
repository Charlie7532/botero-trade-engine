# ADL — Advance-Decline Line (SPX & NDQ)
## Indicator Personality Profile

### ⚠️ STATUS: HISTORICAL ONLY — NO LIVE FEED
ADL data was extracted from TradingView SPX/NDQ OHLCV exports. The cumulative
line is stored in `market.macro_data`. No live source updates this automatically.
**Do NOT activate in production gates until a live feed is found.**

### What It Measures
Cumulative sum of (advancing issues - declining issues) over time.
The classic market-top warning: when the index makes new highs but the ADL
diverges (declining), the rally is driven by fewer stocks → fragile.

### Data Source
- **Historical**: Extracted from TradingView SPX/NDQ CSV exports
  - `spx_adl`: 8,751 values from 1991-08-05
  - `ndq_adl`: 8,716 values from 1991-09-25
- **Stored in**: `market.macro_data` (name/value key-value table)
- **Live**: ❌ None available. Could theoretically be computed from
  advance/decline statistics, but no MCP provides this.

### Mechanical Behavior (HYPOTHESIS — requires expert committee review)
- ADL rising + Index rising = broad participation → healthy bull
- ADL flat/falling + Index rising = NARROW market → classic top warning
- ADL rising + Index flat = breadth improving → potential breakout ahead
- The DIVERGENCE between ADL and price is the signal, not the absolute level

### Expert Committee Questions (PENDING)
- How does ADL divergence timing compare to S5TH/S5TW divergence?
- Is the ADL divergence signal stronger for SPX or NDQ?
- What duration of divergence (days/weeks) is meaningful vs noise?
- Can we compute ADL ourselves from our SP500 OHLCV data?

### Department Relevance
- **Quality**: Druckenmiller — macro market structure assessment
- **CIO**: Market regime classification (broad vs narrow)

### Known Limitations
- Cumulative — starting point is arbitrary, absolute level meaningless
- Requires comparison (index vs ADL trend) — cannot use alone
- No live feed — historical analysis only until resolved
- Exchange-level data (NYSE/NASDAQ), not S&P 500 specific

### Signals (HYPOTHESIS — all require walk-forward validation)
None defined yet. Requires expert committee + preliminary simulation.

### Live Feed
❌ **NO LIVE FEED** — reserved for future extension
