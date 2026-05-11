# Volume Profile (POC, VAL, VAH)
## Indicator Personality Profile

### What It Measures
Distributes total volume across price levels to reveal where institutions
transacted the most. Identifies structural support (VAL), resistance (VAH),
and the gravitational center of price (POC — Point of Control).

### Data Source
- **Input**: OHLCV DataFrame — minimum 30 bars
- **Implementation**: `backend/modules/volume_intelligence/application/use_cases/analyze_volume_profile.py`
- **Class**: `VolumeProfileAnalyzer`
- **Output**: `DualProfileResult` containing short-term and long-term profiles

### Signals Produced

| Signal | What It Means | Mechanical Behavior |
|---|---|---|
| **POC (Point of Control)** | Price level with the highest volume transacted | Acts as a magnet — price gravitates toward POC |
| **VAL (Value Area Low)** | Bottom of the 70% value area | Institutional support — buying zone |
| **VAH (Value Area High)** | Top of the 70% value area | Institutional resistance — selling zone |
| **VP Shape (P/D/b)** | Profile shape: P=accumulation, D=balanced, b=distribution | Reveals institutional intent hidden in volume |
| **POC Migration** | Direction the POC is moving over time | Rising POC = institutional buying; Falling POC = selling |
| **Institutional Bias** | ACCUMULATION / DISTRIBUTION / NEUTRAL | Derived from shape + migration + close position |

### Departmental Reading

> **Evidence Status: `HYPOTHESIS`** — All directival statements below are based on
> observed volume mechanics, NOT on validated walk-forward OOS testing.
> These readings must pass the 5-Step Validation Pipeline before being promoted
> to hard gates. Until then, they feed the 13D Memory Guard as features only.

#### SPECULATIVE (Karsan / PTJ)
- **Timeframe**: Short-term VP (last 5-20 sessions)
- **Entry Use** (HYPOTHESIS): Buy at VAL (institutional support bounce). If price breaks above VAH with volume, it's a breakout. Use POC as a take-profit target for mean-reversion plays.
- **Confirmation** (HYPOTHESIS): If Put Wall (from Gamma) coincides with VAL within 1%, the support is "double-confirmed" — maximum conviction.
- **Exit Use** (HYPOTHESIS): VAH is the mechanical take-profit level. If price reaches VAH and stalls, close.
- **Scientific Methodology Constraint**: We do not hardcode vetoes (e.g., "never buy above VAH"). Instead, POC distance and Value Area relationships feed the 13D **Memory Guard**. The system empirically learns if buying above VAH without a BOS actually fails, avoiding unvalidated human assumptions.

#### QUALITY (Druckenmiller / Munger)
- **Timeframe**: Long-term VP (quarterly or annual)
- **Entry Use** (HYPOTHESIS): Verify that entry price is BELOW the Annual POC. This means we're buying the business cheaper than the average institutional transaction price of the year.
- **Structure Check** (HYPOTHESIS): If VP shape is "b" (distribution) on quarterly view, Druckenmiller would delay entry even if fundamentals are perfect — institutions are leaving.
- **Exit Use**: Quality does NOT use VP for exits. But if Annual POC migrates downward for 2+ quarters, it's a fundamental warning to re-evaluate thesis.

### Known Limitations
- Volume Profile is LAGGING — it tells you where volume WAS, not where it will be
- Accuracy requires at least 30 bars; best with 60+
- In thinly-traded stocks, the profile is "lumpy" and less reliable
- Cannot distinguish between accumulation and distribution within a single bar

### Live Feed
✅ Computed on demand from OHLCV data in the Vault (no external API needed)
