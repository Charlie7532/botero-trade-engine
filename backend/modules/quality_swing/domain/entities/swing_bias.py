"""
Ticker Sentiment Bias — Per-ticker fear/greed entity.

Produced by compute_ticker_fear_level() from dual regression channel slopes.
Consumed by SwingGate and engineer_features as a conviction modulator.

Contrarian interpretation (empirically validated, 20 tickers × 5 years):
  fear_level 0 (GREED) → P(↑)=40.4%, Ret20d=+1.26% (worst)
  fear_level 5 (PANIC) → P(↑)=47.6%, Ret20d=+3.12% (best)
  Wave FLIP → 8.6% spread in P(↑) — most discriminative feature

Buffett/Munger validated: buy in fear, sell in greed.
"""
from dataclasses import dataclass


@dataclass
class TickerSentimentBias:
    """Per-ticker fear/greed state from dual regression channels.

    Contrarian interpretation (empirically validated):
      fear_level 0 (GREED) → P(↑) lowest → caution, don't chase
      fear_level 5 (PANIC) → P(↑) highest → Munger opportunity
    """
    fear_level: int          # 0=GREED, 1=CONFIDENCE, 2=NEUTRAL, 3=ANXIETY, 4=FEAR, 5=PANIC
    fear_label: str          # Human-readable label
    tide_slope: float        # Long regression slope (200 bars, normalized)
    wave_slope: float        # Short regression slope (cycle-adaptive, normalized)
    tide_accel: float        # Change in tide slope vs previous bar
    wave_flip: bool          # Did the wave change sign? (knife stopped/started falling)
    wave_flip_direction: int # +1 = flipped positive, -1 = flipped negative, 0 = no flip
    sigma_position: float    # Price position in σ units within the long channel
    slope_conjugation: float = 0.0  # wave_slope - tide_slope (ángulo entre líneas)
                             # Negative = pullback (entry) → Feature #11, spread -6.7%
                             # Positive = momentum (hold)
                             # Very positive = exhaustion (trim zone)
