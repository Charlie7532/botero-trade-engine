"""
Volatility Regime Classifier — Domain Rules

Pure business rules. Zero external dependencies.
Classifies vol regime from observable metrics using vectorized pd.Series ops.

Evidence Status: HYPOTHESIS — all thresholds need empirical calibration.
Committee corrections applied:
  - Simons: STRIKE uses EMA(vol_ratio, 5) + ≥3 bar persistence (not single-bar)
  - LdP: All thresholds as class constants with HYPOTHESIS tags
  - Dalio: P0 = ML feature only. Gates and allocation shifts are P1/P2.
"""
import pandas as pd
import numpy as np


class VolRegimeClassifier:
    """Classifies vol regime from sensor values.

    All thresholds are HYPOTHESIS — need empirical calibration via
    sensitivity analysis before promotion to VALIDATED.

    Usage:
        classifier = VolRegimeClassifier()
        quality_series = classifier.classify_quality_series(calm, vol_persist, ...)
        spec_series = classifier.classify_speculative_series(calm, vol_persist, ...)
    """

    # ── Quality thresholds (HYPOTHESIS) ──────────────────────────
    CALM_THRESHOLD = 60              # HYPOTHESIS — bars below vol mean for COMPLACENT
    VIX_COMPLACENT = -1.0            # HYPOTHESIS — z-score below which market is complacent
    VIX_ELEVATED = 1.0               # HYPOTHESIS — z-score above which vol is elevated
    VIX_CRISIS = 2.0                 # HYPOTHESIS — z-score for crisis regime
    VIX_VELOCITY_CRISIS = 2.0        # HYPOTHESIS — rate of VIX change for crisis
    VOL_RATIO_ELEVATED = 1.3         # HYPOTHESIS — fast/slow vol ratio for elevated
    VOL_PERSISTENCE_STABLE = 0.8     # HYPOTHESIS — autocorr for stable cluster
    VOL_PERSISTENCE_ACTIVE = 0.6     # HYPOTHESIS — autocorr for active vol regime

    # ── Speculative thresholds (HYPOTHESIS) ──────────────────────
    CALM_STALK = 20                  # HYPOTHESIS — min calm bars for stalk
    VOL_RATIO_COMPRESSED = 0.8       # HYPOTHESIS — ratio below which vol is compressed
    VOL_RATIO_EXPANDING = 1.0        # HYPOTHESIS — ratio above which vol is expanding
    STRIKE_PERSISTENCE_BARS = 3      # HYPOTHESIS — min bars above expanding for STRIKE (Simons fix)
    STRIKE_EMA_SPAN = 5              # HYPOTHESIS — EMA span for vol_ratio smoothing (Simons fix)
    VOL_PERSISTENCE_HARVEST = 0.7    # HYPOTHESIS — autocorr for sustained move
    VOL_OF_VOL_RETREAT_PCT = 0.80    # HYPOTHESIS — rolling percentile for RETREAT
    VIX_RETREAT = 3.0                # HYPOTHESIS — z-score for speculative retreat
    VOL_PERSISTENCE_BREAK = 0.3      # HYPOTHESIS — sudden persistence drop = chaos

    def classify_quality_series(
        self,
        calm_duration: pd.Series,
        vol_persistence: pd.Series,
        vol_of_vol: pd.Series,
        vol_ratio: pd.Series,
        vix_zscore: pd.Series,
        vix_velocity: pd.Series,
    ) -> pd.Series:
        """Classify Quality vol regime for an entire time series.

        Returns integer-encoded Series: 0=NORMAL, 1=COMPLACENT, 2=ELEVATED, 3=CRISIS.
        Decision tree (evaluated top-down, first match wins):
          CRISIS:     VIX > +2σ AND (VIX_velocity > +2σ OR VoV > rolling p90)
          ELEVATED:   VIX > +1σ OR (VolRatio > 1.3 AND VolPersistence > 0.6)
          COMPLACENT: CalmDuration > 60 AND VIX < -1σ AND VolPersistence > 0.8
          NORMAL:     default
        """
        # VolOfVol percentile (rolling 252, Eifert: HYPOTHESIS)
        vov_pct = vol_of_vol.rolling(252, min_periods=60).rank(pct=True)

        # Default: NORMAL (0)
        regime = pd.Series(0, index=calm_duration.index, dtype=int)

        # COMPLACENT (1) — checked first so ELEVATED/CRISIS can override
        is_complacent = (
            (calm_duration > self.CALM_THRESHOLD)
            & (vix_zscore < self.VIX_COMPLACENT)
            & (vol_persistence > self.VOL_PERSISTENCE_STABLE)
        )
        regime[is_complacent] = 1

        # ELEVATED (2) — overrides COMPLACENT
        is_elevated = (
            (vix_zscore > self.VIX_ELEVATED)
            | ((vol_ratio > self.VOL_RATIO_ELEVATED) & (vol_persistence > self.VOL_PERSISTENCE_ACTIVE))
        )
        regime[is_elevated] = 2

        # CRISIS (3) — highest priority, overrides everything
        is_crisis = (
            (vix_zscore > self.VIX_CRISIS)
            & ((vix_velocity > self.VIX_VELOCITY_CRISIS) | (vov_pct > 0.90))
        )
        regime[is_crisis] = 3

        return regime

    def classify_speculative_series(
        self,
        calm_duration: pd.Series,
        vol_persistence: pd.Series,
        vol_of_vol: pd.Series,
        vol_ratio: pd.Series,
        vix_zscore: pd.Series,
        vix_velocity: pd.Series,
    ) -> pd.Series:
        """Classify Speculative vol regime for an entire time series.

        Returns integer-encoded Series: 0=STALK, 1=STRIKE, 2=HARVEST, 3=RETREAT.

        Simons fix: STRIKE uses EMA-smoothed vol_ratio with ≥3 bar persistence
        to avoid false triggers from single noisy bars at the boundary.
        """
        # VolOfVol percentile (rolling 252, Eifert: HYPOTHESIS)
        vov_pct = vol_of_vol.rolling(252, min_periods=60).rank(pct=True)

        # Smoothed vol_ratio (Simons fix: EMA instead of raw to reduce noise)
        vr_smooth = vol_ratio.ewm(span=self.STRIKE_EMA_SPAN, min_periods=3).mean()

        # STRIKE persistence: ≥N consecutive bars above expanding threshold
        above_expanding = (vr_smooth >= self.VOL_RATIO_EXPANDING).astype(float)
        # Count consecutive bars above threshold using groupby trick
        above_groups = (above_expanding != above_expanding.shift(1)).cumsum()
        consecutive_above = above_expanding.groupby(above_groups).cumsum()

        # Default: STALK (0)
        regime = pd.Series(0, index=calm_duration.index, dtype=int)

        # STALK (0) — already default, but mark explicitly for clarity
        # Conditions: compressed vol, calm market
        # (default handles this)

        # STRIKE (1) — compression breakout with persistence
        # Simons: ≥3 bars above expanding after being compressed
        was_compressed = (vr_smooth.rolling(20, min_periods=5).min() < self.VOL_RATIO_COMPRESSED)
        is_strike = (
            (consecutive_above >= self.STRIKE_PERSISTENCE_BARS)
            & was_compressed
        )
        regime[is_strike] = 1

        # HARVEST (2) — sustained high-vol move
        is_harvest = (
            (vol_persistence > self.VOL_PERSISTENCE_HARVEST)
            & (vr_smooth > self.VOL_RATIO_EXPANDING)
            & (~is_strike)  # STRIKE has priority during initial breakout
            & (consecutive_above > self.STRIKE_PERSISTENCE_BARS + 3)  # Move is maturing
        )
        regime[is_harvest] = 2

        # RETREAT (3) — highest priority, vol is chaotic
        is_retreat = (
            (vov_pct > self.VOL_OF_VOL_RETREAT_PCT)
            | (vix_zscore > self.VIX_RETREAT)
            | (vol_persistence < self.VOL_PERSISTENCE_BREAK)
        )
        regime[is_retreat] = 3

        return regime
