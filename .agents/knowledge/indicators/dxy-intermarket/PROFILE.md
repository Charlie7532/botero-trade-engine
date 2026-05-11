# DXY — US Dollar Index (Intermarket)
## Indicator Personality Profile

### What It Measures
Trade-weighted value of the US Dollar against a basket of 6 major currencies
(EUR ~57.6%, JPY ~13.6%, GBP ~11.9%, CAD ~9.1%, SEK ~4.2%, CHF ~3.6%).
Core intermarket indicator for capital flow analysis.

### Data Source
- **Historical**: TradingView `TVC_DXY` (9,080 bars from 1990-07-11)
- **Live**: yfinance (`DX-Y.NYB`) via `vault_market_indices` — daily

### Mechanical Behavior (HYPOTHESIS — requires expert committee review)
- Strong USD typically negative for: EM equities, commodities, gold
- Strong USD typically positive for: US treasuries (flight to safety)
- DXY and SPX can move together (both attract capital) OR diverge
  (strong dollar chokes EM and multinational earnings)

### Intermarket Rotation (Pring Framework)
- Bond → Stock → Commodity cycle maps to DXY inversely:
  - DXY rising + Bonds rising = early cycle (flight to safety)
  - DXY falling + Commodities rising = late cycle (reflation)
  - DXY falling + EM ETFs rising = capital flowing OUT of USD assets

### Expert Committee Questions (PENDING)
- How to integrate DXY into Weinstein Stage Analysis for sector rotation?
- Does DXY > 105 + SPX rising = late-stage divergence warning?
- Should DXY regime be a Quality-only gate or cross-department?
- How does DXY interact with TNX (yields) for cycle positioning?

### Department Relevance
- **Quality**: Pring/Weinstein — intermarket rotation and cycle timing
- **Speculative**: PTJ — macro tape reading (200-DMA on DXY)
- **CIO**: Ray Dalio — Economic Machine, credit cycle phase

### Known Limitations
- Heavily EUR-weighted (57.6%) — may not reflect true broad dollar strength
- Political/central bank intervention can override mechanics
- Slow-moving — not useful for intraday tactical decisions

### Signals (HYPOTHESIS — all require walk-forward validation)
None defined yet. Requires expert committee + preliminary simulation.

### Live Feed
✅ Daily from yfinance via daemon
