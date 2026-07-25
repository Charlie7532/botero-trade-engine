"""
Signal Cataloger & Processor — Pure Domain Component
======================================================
Encapsulates the rules, conditions, and ML-evolveable criteria
for classifying quantitative feature vectors from the Fact Store (JSON)
into Universal Signal Taxonomy actions (STK_*, WAVE_*).

This decouples the raw empirical data store (pure numbers) from the
decision logic (evolveable classification conditions).
"""
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class TideFeatureVector:
    """Quantitative features extracted from the Tide Fact Store."""
    zone: str
    p_bull: float
    asymmetry_pp: float
    zz25_min_pct: float
    zz25_max_pct: float
    zz50_min_pct: float = 0.0
    zz50_max_pct: float = 0.0
    zz75_min_pct: float = 0.0
    momentum_purity: float = 50.0
    n_samples: int = 0


@dataclass(frozen=True)
class WaveFeatureVector:
    """Quantitative features for micro-wave timing extracted from the Wave Fact Store."""
    wave_direction: str
    wave_zone: str
    channel_zone: str
    momentum_state: str
    n_samples: int
    bot_lift: float
    top_lift: float
    bot_clean: float
    top_clean: float
    asymmetry_bias: str


class SignalCataloger:
    """Cataloger & Processor for Trading Signals.
    
    Contains the explicit, versioned conditions to map feature vectors into
    Universal Signal Taxonomy codes. Designed to be easily tuned, re-trained,
    or replaced by ML/AI model classifiers.
    """

    @staticmethod
    def classify_tide(features: TideFeatureVector) -> Tuple[str, str, str, str]:
        """Classify Tide Macro Features into Universal Action Codes.

        Returns:
            (signal_name, action_code, urgency_level, scope_level)
        """
        # Condition 1: STK_ACCUMULATE_STRUCTURAL — Deep capitulation
        if features.zone == "FLOOR" and features.p_bull < 38.0 and (features.zz75_min_pct > 8.0 or features.zz50_min_pct > 12.0):
            return "ACCUMULATE", "STK_ACCUMULATE_STRUCTURAL", "LOW", "STK"

        # Condition 2: STK_BUY_DIP_TACTICAL — Statistical dip
        if features.zone in ("FLOOR", "BELOW") and features.p_bull < 46.0 and (features.asymmetry_pp > 15.0 or features.zz25_min_pct > 18.0):
            return "BUY_DIP", "STK_BUY_DIP_TACTICAL", "HIGH", "STK"

        # Condition 3: STK_TRIM_TACTICAL — Blow-off top risk
        if features.zone == "CEILING" and (features.zz25_max_pct > 15.0 or features.zz50_max_pct > 7.15):
            return "TAKE_PROFIT", "STK_TRIM_TACTICAL", "LOW", "STK"

        # Condition 4: STK_HOLD_EXTENDED — Strong trend at ceiling with low top risk
        if features.zone == "CEILING" and features.p_bull > 78.0 and features.zz25_max_pct < 12.0:
            return "STRONG_TREND", "STK_HOLD_EXTENDED", "PASSIVE", "STK"

        # Condition 5: STK_DISTRIBUTE_DECAY — Preventive distribution
        if features.zone == "CEILING":
            return "REDUCE", "STK_DISTRIBUTE_DECAY", "NORMAL", "STK"

        # Condition 6: STK_ACCUMULATE_PASSIVE — Clean uptrend with high purity
        if features.zone == "ABOVE" and features.p_bull > 70.0 and features.momentum_purity > 70.0 and features.zz25_max_pct < 10.0:
            return "MOMENTUM", "STK_ACCUMULATE_PASSIVE", "LOW", "STK"

        # Condition 7: STK_HOLD_STABLE — Stable uptrend above VWAP
        if features.zone == "ABOVE" and features.p_bull > 65.0 and features.zz25_max_pct < 10.0:
            return "BULL_TREND", "STK_HOLD_STABLE", "PASSIVE", "STK"

        # Condition 8: STK_WATCH_PASSIVE — Discount zone without trigger yet
        if features.zone in ("FLOOR", "BELOW"):
            return "WATCH", "STK_WATCH_PASSIVE", "PASSIVE", "STK"

        # Condition 9: STK_HOLD_NEUTRAL — Neutral range without statistical edge
        return "NO_EDGE", "STK_HOLD_NEUTRAL", "PASSIVE", "STK"


    @staticmethod
    def classify_wave(features: WaveFeatureVector) -> Tuple[str, str, str, str]:
        """Classify Wave Micro-Timing Features into Universal Wave Action Codes.

        Returns:
            (signal_name, action_code, urgency_level, scope_level)
        """
        if features.n_samples < 30:
            return "NO_EDGE", "WAVE_NO_EDGE", "PASSIVE", "STK"

        # 1. WAVE_EXHAUSTION_BOTTOM — Agotamiento vendedor: Caída con desaceleración/frenado de flujo
        if (
            features.bot_lift >= 1.5
            and features.bot_clean >= 50.0
            and features.wave_direction in ("STRONG_DOWN", "MODERATE_DOWN")
            and features.momentum_state in ("FALLING", "NEUTRAL")
        ):
            return "EXHAUSTION_BOTTOM", "WAVE_EXHAUSTION_BOTTOM", "IMMEDIATE", "STK"

        # 2. WAVE_DIVERGENCE_BOTTOM — Divergencia alcista micro: Recuperación de flujo en canal positivo
        if (
            features.bot_lift >= 1.5
            and features.bot_clean >= 50.0
            and features.wave_direction in ("MILD_UP", "MODERATE_UP")
            and features.momentum_state in ("RISING", "NEUTRAL")
        ):
            return "DIVERGENCE_BOTTOM", "WAVE_DIVERGENCE_BOTTOM", "HIGH", "STK"

        # 3. WAVE_APPROACHING_BOTTOM — Proximidad general a suelo
        if features.bot_lift >= 1.5 and features.bot_clean >= 50.0 and features.asymmetry_bias in ("STRONG_BOTTOM", "MILD_BOTTOM"):
            return "APPROACHING_BOTTOM", "WAVE_APPROACHING_BOTTOM", "HIGH", "STK"

        # 4. WAVE_WATCH_BOTTOM — Formación de suelo bajo observación
        if features.bot_lift >= 1.2 and features.asymmetry_bias == "STRONG_BOTTOM":
            return "WATCH_BOTTOM", "WAVE_WATCH_BOTTOM", "NORMAL", "STK"

        # 5. WAVE_EXHAUSTION_TOP — Clímax / Agotamiento comprador: Subida con frenado en techo
        if (
            features.top_lift >= 1.5
            and features.top_clean >= 50.0
            and features.wave_direction in ("STRONG_UP", "MODERATE_UP")
            and features.momentum_state in ("FALLING", "NEUTRAL")
        ):
            return "EXHAUSTION_TOP", "WAVE_EXHAUSTION_TOP", "HIGH", "STK"


        # 6. WAVE_APPROACHING_TOP — Proximidad general a techo
        if features.top_lift >= 1.5 and features.top_clean >= 50.0 and features.asymmetry_bias in ("STRONG_TOP", "MILD_TOP"):
            return "APPROACHING_TOP", "WAVE_APPROACHING_TOP", "HIGH", "STK"

        # 7. WAVE_WATCH_TOP — Formación de techo bajo observación
        if features.top_lift >= 1.2 and features.asymmetry_bias == "STRONG_TOP":
            return "WATCH_TOP", "WAVE_WATCH_TOP", "NORMAL", "STK"

        # 8. WAVE_CONTINUATION — Impulso de onda continuo
        if features.bot_lift < 0.5 and features.top_lift < 0.5:
            return "CONTINUATION", "WAVE_CONTINUATION", "PASSIVE", "STK"

        # 9. WAVE_NO_EDGE — Rango neutral sin ventaja de temporización
        return "NO_EDGE", "WAVE_NO_EDGE", "PASSIVE", "STK"

