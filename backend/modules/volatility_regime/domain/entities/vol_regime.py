"""
Volatility Regime — Domain Entity

Pure dataclass representing a volatility regime snapshot.
No framework imports, no external dependencies.
"""
from dataclasses import dataclass


# Quality states: defense posture
Q_NORMAL = 0       # Business as usual
Q_COMPLACENT = 1   # Lake too calm — Dalio's pre-strike warning
Q_ELEVATED = 2     # Predator near — defensive sizing
Q_CRISIS = 3       # Survival mode — thesis exits only

# Speculative states: hunt cycle
S_STALK = 0        # Observe, probe, map energy
S_STRIKE = 1       # Compression broke — execute
S_HARVEST = 2      # Move underway — ride, don't chase
S_RETREAT = 3      # Vol chaotic — protect capital

QUALITY_LABELS = {Q_NORMAL: "NORMAL", Q_COMPLACENT: "COMPLACENT",
                  Q_ELEVATED: "ELEVATED", Q_CRISIS: "CRISIS"}
SPECULATIVE_LABELS = {S_STALK: "STALK", S_STRIKE: "STRIKE",
                      S_HARVEST: "HARVEST", S_RETREAT: "RETREAT"}


@dataclass
class VolRegimeState:
    """Volatility regime snapshot for a single asset at a point in time.

    P0: Feature only. Gates and allocation shifts are P1/P2.
    """
    quality_regime: int = Q_NORMAL
    speculative_regime: int = S_STALK

    @property
    def quality_label(self) -> str:
        return QUALITY_LABELS.get(self.quality_regime, "NORMAL")

    @property
    def speculative_label(self) -> str:
        return SPECULATIVE_LABELS.get(self.speculative_regime, "STALK")
