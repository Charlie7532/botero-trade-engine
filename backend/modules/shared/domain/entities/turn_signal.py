"""
TurnSignal — Domain Entity for Turn Point Detection
========================================================
Central entity of the Sentinel Gate v6 system. Represents a
detected turn-proximity signal with archetype classification.

The 4 archetypes are the fundamental modes of price turns:
  HL (Higher Low)  — Pullback in uptrend (institutional accumulation)
  LL (Lower Low)   — Capitulation (panic selling, smart money buying)
  HH (Higher High) — Exhaustion (complacency, stealth distribution)
  LH (Lower High)  — Failed rally (bear market trap)

Each archetype maps to exactly ONE action per department.

Clean Architecture: Domain entity. Zero dependencies.
"""
from dataclasses import dataclass, field
from datetime import datetime


# ── Archetype constants ──
ARCHETYPE_HL = "HL"   # Higher Low — pullback entry
ARCHETYPE_LL = "LL"   # Lower Low — capitulation buy
ARCHETYPE_HH = "HH"  # Higher High — exhaustion trim
ARCHETYPE_LH = "LH"  # Lower High — failed rally / short
ARCHETYPE_NONE = "NONE"

# ── Density levels ──
DENSITY_SILENCE = "SILENCIO"
DENSITY_ALARM = "ALARMA"
DENSITY_PRESSURIZE = "PRESURIZACIÓN"
DENSITY_EXPLOSION = "EXPLOSIÓN"

# ── Actions ──
ACTION_ACCUMULATE = "ACCUMULATE"
ACTION_TRIM = "TRIM"
ACTION_SHORT = "SHORT"
ACTION_COVER = "COVER"
ACTION_HOLD = "HOLD"


@dataclass(frozen=True)
class TurnSignal:
    """A detected turn-proximity signal. The language of the system.

    Produced by turn_detector.compute_turn_signal().
    Persisted in engine.channel_snapshots (turn_* columns).
    Consumed by SwingGate, QualityEntryGate, SpeculativeEntryHub.
    """

    # ── Core detection ──
    archetype: str = ARCHETYPE_NONE        # HL, LL, HH, LH, NONE
    prob_piso: float = 0.0                  # P(near bottom) 0-1
    prob_techo: float = 0.0                 # P(near top) 0-1

    # ── Density (urgency) ──
    density_level: str = DENSITY_SILENCE    # SILENCIO → ALARMA → PRESURIZACIÓN → EXPLOSIÓN
    density_count: int = 0                  # Count of bars with prob > 0.5 in 3-bar window

    # ── Trend context ──
    trend_context: str = "NEUTRAL"          # WITH_TREND, AGAINST_TREND, NEUTRAL

    # ── Crescendo ──
    crescendo: bool = False                 # Is density increasing?

    # ── Actions per department (deterministic from archetype + density) ──
    quality_core_action: str = ACTION_HOLD
    quality_swing_action: str = ACTION_HOLD
    speculative_action: str = ACTION_HOLD

    # ── Conviction (from density level) ──
    conviction: float = 0.0                 # 0.0 → 1.0

    # ── Kalman context (for diagnostics / logging) ──
    kf_rsi_pred: float = 0.0               # kf_rsi_pred_val (SHAP #1)
    kf_price_vel: float = 0.0              # kf_price_filt_vel

    # ── Diagnosis string (Rule 17: decision context logging) ──
    diagnosis: str = ""

    @property
    def is_active(self) -> bool:
        """True if any turn signal is detected (not SILENCIO)."""
        return self.density_level != DENSITY_SILENCE

    @property
    def is_piso(self) -> bool:
        """True if this is a bottom-type signal (HL or LL)."""
        return self.archetype in (ARCHETYPE_HL, ARCHETYPE_LL)

    @property
    def is_techo(self) -> bool:
        """True if this is a top-type signal (HH or LH)."""
        return self.archetype in (ARCHETYPE_HH, ARCHETYPE_LH)
