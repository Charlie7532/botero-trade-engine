# SKEW — CBOE Tail Risk Index
## Indicator Personality Profile

### What It Measures
Measures the perceived tail risk of the S&P 500 — specifically the pricing
of out-of-the-money (OTM) put options relative to ATM options. High SKEW means
institutions are paying a premium to hedge against a crash.

### Data Source
- **Historical**: TradingView `CBOE_DLY_SKEW` (8,591 bars from 1991-12-24)
  + existing CBOE CDN data = 17,730 total daily bars
- **Live**: CBOE CDN CSV via `vault_cboe_indices` — daily

### Mechanical Behavior (HYPOTHESIS — requires expert committee review)
- SKEW ≈ 100: No tail risk premium — normal distribution assumed
- SKEW > 130: Moderate tail risk hedging
- SKEW > 150: Heavy institutional tail hedging — crash insurance expensive
- SKEW > 150 + VIX < 15 = "the most dangerous complacency" — institutions
  hedging while spot vol is calm. The surface is calm but the deep structure
  is pricing disaster.

### Expert Committee Questions (PENDING)
- Does high SKEW + low VIX = the most dangerous complacency state?
- How does SKEW interact with VVIX? Are they redundant or complementary?
- What SKEW level triggers portfolio hedge overlay for Quality?
- Does SKEW predict VIX spikes with any lead time?

### Department Relevance
- **Speculative**: Eifert — structural volatility surface analysis
- **Quality**: Druckenmiller — tail risk regime for position sizing
- **CIO**: Portfolio-level hedge timing

### Known Limitations
- Daily only — no intraday data available
- Can remain elevated for extended periods without a crash materializing
- Institutional hedging doesn't always predict crashes (could be routine)

### Signals (HYPOTHESIS — all require walk-forward validation)
None defined yet. Requires expert committee + preliminary simulation.

### Live Feed
✅ Daily from CBOE CDN via daemon
