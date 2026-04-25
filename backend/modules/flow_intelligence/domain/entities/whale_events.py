from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Optional

@dataclass
class MacroEvent:
    """Un evento económico que puede mover el mercado."""
    name: str                          # "FOMC_DECISION", "CPI", "NFP", etc.
    event_date: datetime               # Fecha y hora del evento
    impact_level: int = 1              # 1=NUCLEAR, 2=HIGH, 3=MODERATE
    has_projections: bool = False      # FOMC con Dot Plot / SEP
    description: str = ""

    @property
    def hours_away(self) -> float:
        """Horas hasta el evento desde ahora."""
        delta = self.event_date - datetime.now(UTC)
        return max(0, delta.total_seconds() / 3600)

@dataclass
class WhaleVerdict:
    """Veredicto del flujo de ballenas sobre la dirección del mercado."""
    verdict: str = "UNCERTAIN"          # RIDE_THE_WHALES, LEAN_WITH_FLOW, UNCERTAIN, CONTRA_FLOW
    position_scale: float = 1.0         # Factor de escala para tamaño de posición
    confidence: float = 0.0             # 0-1, confianza en el veredicto

    # Componentes que contribuyeron
    spy_flow_direction: str = "NEUTRAL" # BULLISH, BEARISH, NEUTRAL
    sweep_intensity: str = "NONE"       # EXPLOSIVE, MODERATE, WEAK, NONE
    gex_regime: str = "UNKNOWN"         # PIN, DRIFT, SQUEEZE_UP, SQUEEZE_DOWN
    tide_direction: str = "NEUTRAL"     # BULLISH, BEARISH, NEUTRAL
    am_pm_divergence: bool = False      # Señal de reversión inminente

    # Contexto de evento
    nearest_event: Optional[MacroEvent] = None
    is_event_window: bool = False       # True si hay evento en < 48h
    hours_to_event: float = 999.0

    # Recomendación de stop
    freeze_stops: bool = False          # True si el evento es inminente (< 30 min)
    freeze_duration_min: int = 0        # Minutos de congelamiento

    # Diagnóstico textual
    diagnosis: str = ""
