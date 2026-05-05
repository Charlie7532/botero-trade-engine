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
    internal_breadth_score: float = 0.0  # Breadth of components participating in move
    leading_subsector: str = ""          # e.g., "Semiconductors" within "Technology"
    # ── Institutional Flow (absorbed from SectorFlowEngine) ──
    flow_signal: str = "UNKNOWN"         # ACCUMULATION_ACTIVE, DISTRIBUTION, etc.
    kalman_velocity: float = 0.0         # Volume velocity (rate of change)
    kalman_acceleration: float = 0.0     # Volume acceleration (change of velocity)
    # ── Breadth Divergence (Cap-Weight vs Equal-Weight) ──
    cap_weighted_return: float = 0.0     # Return of the cap-weighted ETF (e.g. XLK)
    equal_weighted_return: float = 0.0   # Return of the equal-weight proxy (e.g. RSPT)
    breadth_divergence: float = 0.0      # equal - cap (>0 = broad, <0 = narrow/fragile)


@dataclass
class RotationSnapshot:
    """
    Complete rotation picture at a point in time.

    Produced by the RotationScanner, consumed by the CIO (Dalio),
    SectorRanker, Research Intelligence, EntryHub, and Risk Manager.
    """
    date: str
    sector_flows: dict[str, float] = field(default_factory=dict)
    international_flows: dict[str, float] = field(default_factory=dict)
    asset_class_flows: dict[str, float] = field(default_factory=dict)
    signals: list[RotationSignal] = field(default_factory=list)
    dominant_rotation: str = "NEUTRAL"
    cycle_phase: str = "UNKNOWN"  # Pring's intermarket phase
    # ── Market-level indicators (absorbed from MarketBreadthProvider) ──
    capitulation_level: int = 0          # 0-4 (0=Normal, 4=Blood in streets)
    capitulation_action: str = "operate_normal"
    fear_greed_score: float = 50.0       # CNN Fear & Greed (0-100)
    market_breadth_pct: float = 50.0     # RSP vs SPY breadth proxy
