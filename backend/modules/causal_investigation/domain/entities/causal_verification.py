"""
Causal Verification Snapshot Entity — NOTAM Aviation & Completeness Protocol
================================================================================
Combines Weinstein Veto and Druckenmiller Counter-Veto into a final CausalDecision.

Implements NOTAM (Notice to Airmen) Aviation Timestamp & Completeness Protocol:
  - as_of_timestamp: Date & time of underlying data in UTC.
  - valid_until: Expiration date & time of this verification.
  - data_age_hours: Exact age of data in hours.
  - notam_status: FRESH (<24h), AGING (24-48h), STALE (48-72h), EXPIRED (>72h).
  - missing_vectors: Explicit list of vectors that failed to fetch data.
  - data_completeness_pct: Percentage of 5 causal vectors successfully loaded (0-100%).
  - notam_header: Structured aviation-style NOTAM alert header.
"""
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import List
from enum import Enum

from backend.modules.causal_investigation.domain.entities.weinstein_stage import StructuralVeto
from backend.modules.causal_investigation.domain.entities.druckenmiller_causal import CounterVetoResult


class CausalDecision(Enum):
    ALLOW_ENTRY = "ALLOW_ENTRY"
    VETO_ESTRUCTURAL = "VETO_ESTRUCTURAL"
    CONTRA_VETO_CAUSAL = "CONTRA_VETO_CAUSAL"


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
    decision_log: str = ""

    def to_dict(self) -> dict:
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
            "decision_log": self.decision_log,
        }
