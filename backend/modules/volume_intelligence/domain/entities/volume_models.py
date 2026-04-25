from dataclasses import dataclass, field
from typing import List
from datetime import datetime, UTC


@dataclass
class VolumeNode:
    """Un nodo de volumen en el profile."""
    price_low: float
    price_high: float
    price_mid: float
    volume: float
    pct_of_total: float
    is_hvn: bool = False  # High Volume Node
    is_lvn: bool = False  # Low Volume Node


@dataclass
class VolumeProfileResult:
    """Resultado del análisis de Volume Profile."""
    poc: float = 0.0
    vah: float = 0.0
    val: float = 0.0
    current_price: float = 0.0
    current_vs_poc: str = "UNKNOWN"
    current_vs_va: str = "UNKNOWN"
    poc_distance_pct: float = 0.0
    nearest_hvn_above: float = 0.0
    nearest_hvn_below: float = 0.0
    shape: str = "D"
    shape_skew: float = 0.0
    period_days: int = 20
    nodes: List[VolumeNode] = field(default_factory=list)


@dataclass
class DualProfileResult:
    """Resultado combinado de perfiles corto y largo."""
    short: VolumeProfileResult = field(default_factory=VolumeProfileResult)
    long: VolumeProfileResult = field(default_factory=VolumeProfileResult)
    poc_migration: str = "NEUTRAL"
    poc_migration_pct: float = 0.0
    institutional_bias: str = "NEUTRAL"
    bias_confidence: float = 0.0
    primary_support: float = 0.0
    primary_resistance: float = 0.0
    entry_zone_low: float = 0.0
    entry_zone_high: float = 0.0
    diagnosis: str = ""


@dataclass
class KalmanState:
    """Estado estimado por el Filtro de Kalman para un ETF."""
    etf: str
    rel_vol: float = 1.0
    velocity: float = 0.0
    acceleration: float = 0.0
    wyckoff_state: str = 'UNKNOWN'
    confidence: float = 0.0
    last_update: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    history_len: int = 0


@dataclass
class VolumeDynamicsReport:
    """
    Reporte consolidado de dinámica de volumen para el Motor de Trading.

    Este es el output final que consume el SmartEntryEngine antes de
    decidir si aprobar o rechazar una entrada.
    """
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    # Señales tempranas de rotación (los "caballos que van a salir")
    early_rotation_signals: list = field(default_factory=list)

    # Estado Wyckoff del sector del ticker candidato
    ticker_sector_etf: str = ""
    ticker_sector_state: str = "UNKNOWN"
    ticker_sector_velocity: float = 0.0

    # Flujo global
    dominated_by_distribution: bool = False   # ¿La mayoría del mercado distribuye?
    risk_off_international: bool = False       # ¿EEM/EFA en distribución?
    n_accumulating: int = 0   # ETFs en acumulación
    n_distributing: int = 0   # ETFs en distribución

    # Recomendación final
    flow_supports_entry: bool = True
    abort_reason: str = ""

    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp,
            'early_rotation_signals': self.early_rotation_signals,
            'ticker_sector_etf': self.ticker_sector_etf,
            'ticker_sector_state': self.ticker_sector_state,
            'ticker_sector_velocity': self.ticker_sector_velocity,
            'dominated_by_distribution': self.dominated_by_distribution,
            'risk_off_international': self.risk_off_international,
            'n_accumulating': self.n_accumulating,
            'n_distributing': self.n_distributing,
            'flow_supports_entry': self.flow_supports_entry,
            'abort_reason': self.abort_reason,
        }
