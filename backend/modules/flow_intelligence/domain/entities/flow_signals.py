from dataclasses import dataclass

@dataclass
class FlowPersistenceSignal:
    ticker: str
    
    # Temporal dimensions
    hours_since_latest: float = 999.0          # How fresh is the newest signal?
    days_with_flow: int = 0                    # How many of last 5 days had flow?
    consecutive_days: int = 0                  # Current streak of same-direction flow
    freshness_weight: float = 0.0              # e^(-0.3 * days_old), 0.0-1.0
    
    # Conviction modifiers
    direction_consistency: float = 0.0         # % of signals that agree (bullish vs bearish)
    premium_trend: str = "STABLE"              # INCREASING, STABLE, DECREASING
    voi_trend: str = "STABLE"                  # Are VOI ratios growing?
    
    # Dark pool confirmation
    darkpool_aligned: bool = False             # Is darkpool buying in same direction?
    darkpool_premium: float = 0.0              # Total dark pool premium in last 5 days
    darkpool_count: int = 0                    # Number of dark pool prints
    
    # Price validation (post-signal behavior)
    price_at_first_signal: float = 0.0         # Price when first signal of streak appeared
    price_now: float = 0.0                     # Current price
    price_confirmed: bool = False              # Did price move in signal direction?
    price_change_since_signal_pct: float = 0.0
    
    # Composite
    persistence_score: float = 0.0             # 0-100 composite
    persistence_grade: str = "UNKNOWN"         # FRESH_ACCUMULATION, DEAD_SIGNAL, etc.
