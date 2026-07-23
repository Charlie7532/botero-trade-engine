"""
Causal Investigation DTOs
==========================
Data Transfer Objects for Causal Investigation requests and responses.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class CausalInputDTO:
    """
    Concentrated input container prepared by the Vault Daemon and passed to
    the pure domain use case. Zero I/O in the domain layer.
    """
    symbol: str
    price_history: List[float] = field(default_factory=list)
    rs_score: float = 0.0
    as_of_dt: Optional[Any] = None

    # Vector 1: Unusual Whales Options / Darkpool
    uw_flow_alerts: Optional[List[dict]] = None
    uw_net_premium: float = 0.0
    uw_sweep_count: int = 0

    # Vector 2: FRED Macro Net Liquidity & Rates
    fred_macro_snapshot: Optional[dict] = None

    # Vector 3: Insiders
    insider_activity: Optional[dict] = None

    # Vector 4: Volume Capitulation / Re-absorption (S5/SV5)
    s5_th: float = 50.0
    s5_fi: float = 50.0
    s5_tw: float = 50.0
    sv5_tw: float = 50.0
    vol_div: float = 0.0

    # Vector 5: News Sentiment
    news_sentiment_score: float = 0.0


@dataclass
class CausalVerificationRequest:
    symbol: str
    date_ref: Optional[str] = None


@dataclass
class CausalVerificationResponse:
    symbol: str
    decision: str
    sizing_multiplier: float
    causal_score: float
    weinstein_stage: str
    summary: str
