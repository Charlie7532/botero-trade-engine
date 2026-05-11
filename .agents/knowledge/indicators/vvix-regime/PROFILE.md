# VVIX — VIX of VIX (Volatility of Volatility)
## Indicator Personality Profile

### What It Measures
Implied volatility of VIX options — measures how uncertain the market is
about FUTURE volatility. VVIX rising while VIX is calm = structural instability
building beneath the surface.

### Data Source
- **Historical**: TradingView `CBOE_DLY_VVIX` (5,003 bars 1D from 2006, + 1H + 15m)
- **Live**: CBOE CDN CSV (daily download via `vault_cboe_indices`)
- **Intraday**: 1H and 15m available as historical only (no intraday live feed)

### Mechanical Behavior (HYPOTHESIS — requires expert committee review)
- Range: ~60 (extreme complacency) to ~200+ (extreme uncertainty about vol)
- Normal range: 80-110
- VVIX spike PRECEDES VIX spike — it's the early warning system
- VVIX/VIX ratio captures the "surprise factor":
  - Ratio > 6.0: Market pricing massive vol surprise potential
  - Ratio < 4.0: Complacent about vol trajectory

### Expert Committee Questions (PENDING)
- What VVIX/VIX ratio thresholds trigger Speculative size reduction?
- Does VVIX > 120 with VIX < 15 = the most dangerous complacency state?
- How does VVIX interact with Karsan's GEX regime?
- Should VVIX regime be a hard gate or advisory?

### Department Relevance
- **Speculative**: Eifert — structural volatility dislocation detection
- **Quality**: Druckenmiller — macro regime awareness

### Known Limitations
- CBOE live feed is daily only — intraday VVIX not available live
- Can remain elevated for extended periods (not a timing tool)
- Requires VIX options market to be liquid (always true for VIX)

### Signals (HYPOTHESIS — all require walk-forward validation)
None defined yet. Requires expert committee + preliminary simulation.

### Live Feed
✅ Daily from CBOE CDN | ⚠️ Intraday historical only (no live 1H/15m feed)
