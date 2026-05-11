# TNX — 10-Year Treasury Yield
## Indicator Personality Profile

### What It Measures
Yield on the 10-Year US Treasury Note. The benchmark "risk-free" rate that
anchors ALL equity valuations (DCF discount rate), mortgage rates, and
corporate borrowing costs. The single most important macro number.

### Data Source
- **Historical**: TradingView `TVC_TNX` (11,040 bars from **1982-04-29** — longest series in vault)
- **Live**: yfinance (`^TNX`) via `vault_market_indices` — daily

### Mechanical Behavior (HYPOTHESIS — requires expert committee review)
- TNX rising = discount rates up = equity valuations compressed (especially growth)
- TNX falling = discount rates down = equity valuations expand
- Rate of CHANGE matters more than level — sudden spikes dislocate
- TNX > 5% historically triggers equity stress (last seen 2023)

### Intermarket Rotation (Pring Framework)
- **Bonds → Stocks → Commodities** is the Pring cycle sequence
- TNX falling (bonds rallying) = early cycle → rotate INTO equities
- TNX rising (bonds falling) = late cycle → commodities lead, equities lag
- Yield curve (TNX minus 3M/2Y): Inversion = recession warning (FRED has this)

### Helmer/DCF Integration
- TNX directly feeds the Helmer Protocol's Reverse DCF discount rate
- TNX shift of 100bp changes "expectations embedded in price" materially
- Quality department must recalculate Expectations Engine when TNX moves >50bp

### Expert Committee Questions (PENDING)
- At what TNX level does the Expectations Engine need mandatory recalculation?
- How does TNX interact with DXY for cycle positioning?
- Should TNX regime changes trigger Quality portfolio review?
- What TNX/SPX divergence (both rising) indicates "late cycle euphoria"?

### Department Relevance
- **Quality**: Druckenmiller/Munger — discount rate for all valuations
- **CIO**: Ray Dalio — debt cycle, yield curve regime
- **Speculative**: PTJ — macro inflection points, 200-DMA on TNX

### Known Limitations
- Massive Fed intervention post-2008 distorts "natural" levels
- QE/QT directly manipulates the yield curve
- Political headline risk (debt ceiling, etc.)

### Signals (HYPOTHESIS — all require walk-forward validation)
None defined yet. Requires expert committee + preliminary simulation.

### Live Feed
✅ Daily from yfinance via daemon
