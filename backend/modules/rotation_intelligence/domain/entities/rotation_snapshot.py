from dataclasses import dataclass, field


@dataclass
class RotationSignal:
    """A single ETF's rotation measurement."""
    etf: str              # "XLK"
    name: str             # "Technology"
    dimension: str        # "sector" | "international" | "asset_class"
    rs_score: float       # Relative Strength vs benchmark, normalized (-1.0 to 1.0)
    momentum_20d: float   # 20-day price return %
    momentum_60d: float   # 60-day price return %
    volume_ratio: float   # Current volume / 20-day avg volume
    stage: int = 0        # Weinstein Stage (1-4), 0 = unclassified


@dataclass
class RotationSnapshot:
    """
    Complete rotation picture at a point in time.

    Produced by the RotationScanner, consumed by the CIO (Dalio).
    """
    date: str
    sector_flows: dict[str, float] = field(default_factory=dict)
    international_flows: dict[str, float] = field(default_factory=dict)
    asset_class_flows: dict[str, float] = field(default_factory=dict)
    signals: list[RotationSignal] = field(default_factory=list)
    dominant_rotation: str = "NEUTRAL"
    cycle_phase: str = "UNKNOWN"  # Pring's intermarket phase
