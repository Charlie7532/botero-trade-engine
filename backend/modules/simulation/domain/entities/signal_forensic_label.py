from dataclasses import dataclass, field
from typing import Optional, Any
from backend.modules.simulation.domain.entities.indicator_snapshot import IndicatorSnapshot

@dataclass
class HorizonSnapshot:
    bars: int                    # 3, 5, 10, 20, 40
    return_pct: float            # Return al cierre
    max_up_pct: float            # Máximo alcanzado (MFE)
    max_down_pct: float          # Mínimo alcanzado (MAE)
    bars_to_max_up: int          # Vela del máximo
    bars_to_max_down: int        # Vela del mínimo

@dataclass
class SignalForensicLabel:
    ticker: str
    signal_name: str
    signal_direction: int        # +1 (entry) o -1 (exit)
    signal_confidence: float
    signal_time: Any             # pd.Timestamp or string representation
    signal_price: float

    # Snapshot nativo del indicador al momento de la señal (Tier 1)
    snapshot: IndicatorSnapshot

    # Curva temporal multi-horizonte
    horizons: dict[int, HorizonSnapshot] = field(default_factory=dict)

    # Clasificación forense
    classification: str = "UNCLASSIFIED"
    primary_horizon: int = 10
    
    # Diagnóstico de fallos (Dalio: Pain + Reflection)
    failure_diagnosis: Optional[str] = None
    foreseeability: Optional[str] = None    # FORESEEABLE / PARTIALLY / UNFORESEEABLE
