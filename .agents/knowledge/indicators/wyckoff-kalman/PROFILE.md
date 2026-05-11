# Wyckoff Phase Detection (Kalman Filter)
## Indicator Personality Profile

### What It Measures
Uses a Kalman Filter to clean raw volume into smoothed velocity and acceleration,
then classifies the current Wyckoff phase: ACCUMULATION, MARKUP, DISTRIBUTION,
or MARKDOWN. The filter strips HFT noise to reveal institutional intent.

### Data Source
- **Input**: RVOL (Relative Volume) and price change % per bar
- **Implementation**: `backend/modules/volume_intelligence/application/use_cases/track_volume_dynamics.py`
- **Class**: `KalmanVolumeTracker` (stateful — maintains per-ticker Kalman state)
- **Classifier**: `SectorRegimeDetector.classify(rvol, velocity, acceleration)`

### Signals Produced

| Signal | What It Means | Mechanical Behavior |
|---|---|---|
| **Wyckoff State** | ACCUMULATION / MARKUP / DISTRIBUTION / MARKDOWN | Phase of the institutional cycle |
| **Velocity** | Rate of volume change (Kalman-smoothed) | Positive = volume expanding, Negative = volume contracting |
| **Acceleration** | Rate of velocity change | Positive acceleration in MARKUP = trend strengthening |
| **RVOL** | Current bar volume / 20-day average volume | >1.5 = significant institutional activity |

### Wyckoff Phases (Mechanical Interpretation)

```
ACCUMULATION → MARKUP → DISTRIBUTION → MARKDOWN → (repeat)
     🟢            🚀          🔴              💀
```

- **ACCUMULATION**: Smart money is buying quietly. Volume is DRY on down days, slightly elevated on up days. Price is in a range. This is where the institutional position is built.
- **MARKUP**: The trend begins. Volume surges on breakout. Velocity is positive and accelerating. This is where retail "discovers" the move.
- **DISTRIBUTION**: Smart money is selling quietly. Volume is elevated but price stalls. Classic "churning" at the top.
- **MARKDOWN**: The downtrend. Volume spikes on down days. Velocity is negative. Retail panics.

### Departmental Reading

> **Evidence Status: `HYPOTHESIS`** — All directival statements below are based on
> observed Wyckoff/Kalman volume mechanics, NOT on validated walk-forward OOS testing.
> These readings must pass the 5-Step Validation Pipeline before being promoted
> to hard gates. Until then, they feed the 13D Memory Guard as features only.

#### SPECULATIVE (Karsan / Seykota)
- **Timeframe**: Daily bars, 20-bar Kalman window
- **Entry Use** (HYPOTHESIS): Enter during MARKUP phase with positive acceleration (riding the institutional wave). Enter ACCUMULATION only if a Liquidity Sweep (SMC) confirms the Spring.
- **Exit Use** (HYPOTHESIS): If Wyckoff transitions from MARKUP → DISTRIBUTION while position is open, activate tighter trailing stop. The `SpeculativeExitEngine` currently uses `wyckoff_state == DISTRIBUTION` as a mandatory exit trigger (Exit D).
- **Speed** (HYPOTHESIS): Kalman Velocity is the key signal. If velocity decelerates for 3+ consecutive bars during MARKUP, the trend is exhausting.

#### QUALITY (Druckenmiller)
- **Timeframe**: Weekly bars (derive from daily aggregation)
- **Entry Use** (HYPOTHESIS): Confirm that the ticker is NOT in DISTRIBUTION phase before initiating a large position. Druckenmiller will not fight institutional selling, even if the moat is intact.
- **Patience**: ACCUMULATION phase can last months — Quality is patient. Use ACCUMULATION detection to START building a position slowly.
- **Exit Use**: Quality does NOT exit based on Wyckoff. But DISTRIBUTION detected on weekly timeframe is a warning flag to audit the investment thesis.

### Scientific Methodology Constraint
**Empirical Validation Required**: The current architecture uses Wyckoff `DISTRIBUTION` as a mandatory exit trigger in the `SpeculativeExitEngine` (Exit D) and as a 50% sizing penalty in the `QualityEntryGate`. While these are mechanically sound heuristics derived from market microstructure, Marcos López de Prado's methodology dictates that **these hardcoded rules must be periodically subjected to walk-forward cross-validation**. If empirical data shows that exiting purely on Kalman DISTRIBUTION degrades the Sharpe ratio compared to a dynamic ATR trailing stop, the rule must be demoted from a hard gate to a Memory Guard feature. Current status: **`HYPOTHESIS`** — awaiting first walk-forward validation cycle.

### Known Limitations
- Kalman filter is stateful — needs "warm-up" period of ~20 bars to stabilize
- Phase classification uses static thresholds (`SectorRegimeDetector`) which may need per-sector calibration
- Cannot distinguish between genuine accumulation and a dead stock with no volume
- In fast-moving markets (VIX > 30), Kalman lag increases — velocity readings may be stale

### Live Feed
✅ Computed on demand from OHLCV data. Kalman state is maintained in-memory per ticker per session.
