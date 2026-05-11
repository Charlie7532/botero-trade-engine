# Smart Money Concepts (SMC) — Market Structure
## Indicator Personality Profile

### What It Measures
Detects institutional footprints in price action using algorithmic structural analysis:
Break of Structure (BOS), Change of Character (CHoCH), Order Blocks (OB),
Fair Value Gaps (FVG), and Liquidity Sweeps.

### Data Source
- **Library**: `smartmoneyconcepts>=0.0.26` (pip install)
- **Input**: OHLCV DataFrame — minimum 50 bars for reliable detection
- **Implementation**: `backend/modules/simulation/infrastructure/smc_adapter.py`
- **Port**: `backend/modules/shared/domain/ports/market_structure_port.py`

### Signals Produced

| Signal | What It Means | Mechanical Behavior |
|---|---|---|
| **BOS (Break of Structure)** | Price broke a previous swing high/low in the direction of trend | Confirms trend continuation — dealers must re-hedge |
| **CHoCH (Change of Character)** | FIRST structural break against the prevailing trend | Early warning of trend reversal — the highest-conviction signal |
| **Order Block (OB)** | The candle that originated a strong impulsive move | Institutional "reload zone" — price gravitates back to OBs |
| **Fair Value Gap (FVG)** | 3-candle imbalance where price moved too fast, leaving a "void" | Price tends to retrace to fill the gap before continuing |
| **Liquidity Sweep** | Price briefly pierced a swing low/high, triggering stop-losses | Classic "stop hunt" — often precedes reversals (Spring) |

### Departmental Reading

> **Evidence Status: `HYPOTHESIS`** — All directival statements below are based on
> observed market microstructure mechanics, NOT on validated walk-forward OOS testing.
> These readings must pass the 5-Step Validation Pipeline before being promoted
> to hard gates. Until then, they feed the 13D Memory Guard as features only.

#### SPECULATIVE (PTJ / Seykota / Karsan)
- **Timeframe**: Daily (primary), 1H (confirmation)
- **Entry Use** (HYPOTHESIS): BOS BULLISH as momentum confirmation. Liquidity Sweep as CONTRARIAN_DIP trigger (Spring setup). FVG midpoint as precision limit-order anchor.
- **Exit Use** (HYPOTHESIS): Anchor Stop Loss BELOW nearest Bullish Order Block. If OB breaks, institutional thesis is dead.
- **Scientific Methodology Constraint**: We DO NOT hardcode vetoes based on unvalidated SMC heuristics (e.g., "abort all longs on CHoCH"). Instead, SMC data feeds the 13D **Memory Guard**. The empirical database will learn organically if a bearish CHoCH truly invalidates the edge over time.

#### QUALITY (Munger / Druckenmiller)
- **Timeframe**: Weekly/Monthly ONLY (noise filter)
- **Entry Use** (HYPOTHESIS): Verify swing_trend != DOWNTREND before initiating a position. Liquidity Sweep on monthly chart = rare institutional shake-out.
- **Exit Use**: Quality does NOT use SMC for exits. Exits are thesis-driven (moat decay, overvaluation).
- **Ignore**: All daily BOS/CHoCH/FVG signals — noise at Quality's time horizon.

### Known Limitations
- SMC is DESCRIPTIVE, not predictive — it labels what happened, not what will happen
- Effectiveness degrades in low-volume/illiquid tickers (OI < 1000 contracts)
- The `smartmoneyconcepts` library may not be installed — adapter degrades gracefully
- Order Blocks can cluster — only the NEAREST one to current price matters

### Live Feed
⚠️ Currently only used in simulation (`PreTradeGate`). Plan: inject into live Entry Hubs.
