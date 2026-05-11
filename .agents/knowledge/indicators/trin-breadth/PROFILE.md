# TRIN — Arms Index (Market Internals)
## Indicator Personality Profile

### ⚠️ STATUS: HISTORICAL ONLY — NO LIVE FEED
This indicator has historical data (5,728 daily bars from 2003) but CANNOT be
updated automatically. No MCP server, Yahoo Finance, or CBOE CDN exposes TRIN.
**Do NOT activate in production gates until a live feed is found.**

### What It Measures
(Advancing Issues / Declining Issues) / (Advancing Volume / Declining Volume).
Measures the INTENSITY of up/down volume relative to the breadth of advancing/declining stocks.

### Data Source
- **Historical**: TradingView `INDEX_TRIN` (5,728 bars from 2003-07-18)
- **Live**: ❌ None available. Future extension required.

### Mechanical Behavior (HYPOTHESIS — requires expert committee review)
- TRIN = 1.0: Neutral — volume is distributed proportionally to advances/declines
- TRIN > 2.0: Panic selling clímax — heavy volume on decliners (potential washout bottom)
- TRIN < 0.5: Euphoric buying — heavy volume on advancers (potential exhaustion top)
- Intraday TRIN spikes are the classic "capitulation" detection tool

### Expert Committee Questions (PENDING)
- Does TRIN clímax (> 2.0) coincide with S5TW washout for timing capitulation entries?
- What TRIN threshold + VIX spike = reliable bottom signal?
- Is TRIN useful for Speculative only, or also Quality entry timing?
- Can we calculate TRIN ourselves from advance/decline data? (What data source?)

### Department Relevance
- **Speculative**: PTJ — tape reading, capitulation detection
- **Speculative**: Karsan — if combined with GEX flip, may amplify signals

### Known Limitations
- NYSE-specific (not S&P 500)
- Can produce misleading readings in low-volume environments
- No live feed — historical analysis only until resolved

### Signals (HYPOTHESIS — all require walk-forward validation)
None defined yet. Requires expert committee + preliminary simulation.

### Live Feed
❌ **NO LIVE FEED** — reserved for future extension
