"""
Causal Verification Snapshot Entity — NOTAM Aviation & Structured Ticker Payload
===================================================================================
Combines Weinstein Veto and Druckenmiller Counter-Veto into a final CausalDecision.

Implements NOTAM (Notice to Airmen) Aviation Timestamp & Structured Ticker Payload:
  - as_of_timestamp: Date & time of underlying data in UTC.
  - valid_until: Expiration date & time of this verification.
  - data_age_hours: Exact age of data in hours.
  - notam_status: FRESH (<24h), AGING (24-48h), STALE (48-72h), EXPIRED (>72h).
  - missing_vectors: Explicit list of vectors that failed to fetch data.
  - data_completeness_pct: Percentage of 5 causal vectors successfully loaded (0-100%).
  - notam_header: Structured aviation-style NOTAM alert header.
  - notam_ticker_payload: Pre-digested, pre-classified numerical data bar for consuming gates.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import List, Dict, Any, Optional
from enum import Enum

from backend.modules.causal_investigation.domain.entities.weinstein_stage import StructuralVeto
from backend.modules.causal_investigation.domain.entities.druckenmiller_causal import CounterVetoResult


class CausalDecision(Enum):
    ALLOW_ENTRY = "ALLOW_ENTRY"
    VETO_ESTRUCTURAL = "VETO_ESTRUCTURAL"
    CONTRA_VETO_CAUSAL = "CONTRA_VETO_CAUSAL"


@dataclass(frozen=True)
class NOTAMTickerPayload:
    """
    Pre-digested, structured numerical NOTAM ticker payload designed for immediate,
    zero-parsing consumption by Quality, Speculative, Quality Swing, and CIO gates.
    """
    symbol: str
    as_of_timestamp: str
    valid_until: str
    data_age_hours: float
    notam_status: str
    data_completeness_pct: float
    missing_vectors: List[str]

    # Decision & Sizing Multipliers per department mission
    decision: str
    weinstein_stage_code: int                # 1 (Basing), 2 (Advancing), 3 (Topping), 4 (Declining)
    causal_score: float                      # 0.0 to 1.0 composite causal conviction
    quality_sizing_mult: float               # Calibrated for Quality Gate (0.0 to 1.25x)
    speculative_sizing_mult: float           # Calibrated for Speculative Hub (0.0 to 1.50x)

    # Volatility Fragility & Skew Risk Metrics
    skew_index: float                        # CBOE Skew Index (Tail risk)
    vvix_vix_ratio: float                    # VVIX / VIX ratio (Vol of vol fragility)
    vix_zscore: float                        # Rolling VIX Z-Score
    cboe_pcr: float                          # CBOE Put/Call Ratio
    fg_score: float                          # CNN Fear & Greed Index (0-100)

    # 5-Vector Scores
    options_flow_score: float
    macro_liquidity_score: float
    insider_score: float
    volume_reabsorption_score: float
    news_sentiment_score: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CausalVerificationSnapshot:
    """
    Final decision snapshot emitted by the Causal Investigation Engine.

    Contains full temporal decision context per Rule 17 & Aviation NOTAM protocol.
    """
    symbol: str
    decision: CausalDecision
    sizing_multiplier: float
    structural_veto: StructuralVeto
    counter_veto: CounterVetoResult
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    as_of_timestamp: str = ""
    valid_until: str = ""
    data_age_hours: float = 0.0
    notam_status: str = "FRESH"      # FRESH, AGING, STALE, EXPIRED
    missing_vectors: List[str] = field(default_factory=list)
    data_completeness_pct: float = 100.0
    notam_header: str = ""
    notam_ticker_payload: Optional[NOTAMTickerPayload] = None
    decision_log: str = ""

    def to_dict(self) -> dict:
        payload_dict = self.notam_ticker_payload.to_dict() if self.notam_ticker_payload else {}
        return {
            "symbol": self.symbol,
            "decision": self.decision.value,
            "sizing_multiplier": self.sizing_multiplier,
            "weinstein_stage": self.structural_veto.stage.label,
            "is_vetoed": self.structural_veto.is_vetoed,
            "is_overridden": self.counter_veto.is_overridden,
            "causal_score": self.counter_veto.causal_score,
            "conviction_level": self.counter_veto.conviction_level,
            "timestamp": self.timestamp,
            "as_of_timestamp": self.as_of_timestamp,
            "valid_until": self.valid_until,
            "data_age_hours": self.data_age_hours,
            "notam_status": self.notam_status,
            "missing_vectors": self.missing_vectors,
            "data_completeness_pct": self.data_completeness_pct,
            "notam_header": self.notam_header,
            "notam_ticker_payload": payload_dict,
            "decision_log": self.decision_log,
        }
