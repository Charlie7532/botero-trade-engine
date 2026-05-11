# PCCE — CBOE Equity Put/Call Ratio
## Indicator Personality Profile

### ⚠️ STATUS: HISTORICAL ONLY — NO LIVE FEED
This indicator has historical data (4,854 daily + 1H + 15m bars from 2007) but
CANNOT be updated automatically. CBOE blocked CDN access (403), Yahoo delisted `^PCCE`.
**Do NOT activate in production gates until a live feed is found.**

### What It Measures
Ratio of equity put volume to equity call volume on CBOE.
Direct measure of options-market fear/greed, excluding index options (which
are dominated by institutional hedging and distort the signal).

### Data Source
- **Historical**: TradingView `USI_PCCE` (4,854 bars 1D + 1H + 15m from 2007)
- **Live**: ❌ None available. CBOE CDN returns 403. Yahoo `^PCCE` delisted.

### Mechanical Behavior (HYPOTHESIS — requires expert committee review)
- PCCE > 1.0: More puts than calls — extreme fear, potential contrarian buy
- PCCE < 0.5: More calls than puts — extreme greed, potential contrarian sell
- Normal range: 0.6 - 0.8
- 5-day MA of PCCE smooths noise and is more reliable than raw reading

### Expert Committee Questions (PENDING)
- How does PCCE interact with Karsan's GEX regime? Do they confirm or diverge?
- Does PCCE extreme + Negative Gamma = the most explosive setup?
- What PCCE threshold constitutes "institutional hedging" vs "retail panic"?
- Should this be an Eifert-validated signal ("who is on the other side")?

### Department Relevance
- **Speculative**: Eifert — "who and why" behind option flow
- **Speculative**: Karsan — options flow as mechanical force indicator

### Known Limitations
- Equity-only (excludes index options — intentional to avoid hedging noise)
- Can stay extreme for days during persistent trends
- Not available from Finviz per-stock PCR (different metric)
- No live feed — historical analysis only until resolved

### Signals (HYPOTHESIS — all require walk-forward validation)
None defined yet. Requires expert committee + preliminary simulation.

### Live Feed
❌ **NO LIVE FEED** — reserved for future extension
