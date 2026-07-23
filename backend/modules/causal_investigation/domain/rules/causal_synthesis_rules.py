"""
Causal Synthesis Rules — NOTAM Aviation & Completeness Protocol
==================================================================
Synthesizes Weinstein's Structural Veto and Druckenmiller's Causal Counter-Veto
into a final CausalVerificationSnapshot with NOTAM aviation timestamp and missing vector metadata.
"""
from datetime import datetime, timedelta, UTC
from typing import Optional

from backend.modules.causal_investigation.domain.entities.weinstein_stage import (
    WeinsteinStage,
    StructuralVeto,
)
from backend.modules.causal_investigation.domain.entities.druckenmiller_causal import (
    CounterVetoResult,
)
from backend.modules.causal_investigation.domain.entities.causal_verification import (
    CausalDecision,
    CausalVerificationSnapshot,
)


def synthesize_causal_decision(
    symbol: str,
    structural_veto: StructuralVeto,
    counter_veto: CounterVetoResult,
    as_of_dt: Optional[datetime] = None,
    valid_hours: int = 24,
) -> CausalVerificationSnapshot:
    """
    Combines Weinstein Veto and Druckenmiller Counter-Veto into a final CausalDecision.

    Calculates Aviation NOTAM Timestamp & Completeness Metadata:
      - as_of_timestamp: Issuance time of data (UTC).
      - valid_until: Expiration time (as_of + valid_hours).
      - data_age_hours: Age of data in hours relative to execution time.
      - notam_status: FRESH (<24h), AGING (24-48h), STALE (48-72h), EXPIRED (>72h).
      - missing_vectors: Explicit list of missing data vectors.
      - data_completeness_pct: Percentage of causal vectors loaded (0-100%).
      - notam_header: NOTAM format string.
    """
    now = datetime.now(UTC)
    as_of = as_of_dt if as_of_dt is not None else now

    # Calculate age and expiration
    age_seconds = max(0.0, (now - as_of).total_seconds())
    data_age_hours = round(age_seconds / 3600.0, 2)
    valid_until_dt = as_of + timedelta(hours=valid_hours)

    if data_age_hours <= 24.0:
        notam_status = "FRESH"
    elif data_age_hours <= 48.0:
        notam_status = "AGING"
    elif data_age_hours <= 72.0:
        notam_status = "STALE"
    else:
        notam_status = "EXPIRED"

    as_of_str = as_of.strftime("%Y-%m-%dT%H:%M:%SZ")
    valid_until_str = valid_until_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    missing = counter_veto.missing_vectors
    completeness = counter_veto.data_completeness_pct

    # Determine Decision
    if not structural_veto.is_vetoed:
        decision = CausalDecision.ALLOW_ENTRY
        sizing_mult = counter_veto.sizing_factor
        log_msg = (
            f"ALLOW_ENTRY for {symbol}: Stage {structural_veto.stage.label} is healthy. "
            f"Causal Score={counter_veto.causal_score:.2f}."
        )
    else:
        if counter_veto.is_overridden:
            decision = CausalDecision.CONTRA_VETO_CAUSAL
            sizing_mult = counter_veto.sizing_factor
            log_msg = (
                f"CONTRA_VETO_CAUSAL for {symbol}: Weinstein Stage 4 Veto OVERRIDDEN by Druckenmiller. "
                f"Causal Score={counter_veto.causal_score:.2f} (Conviction: {counter_veto.conviction_level}, Mult: x{sizing_mult})."
            )
        else:
            decision = CausalDecision.VETO_ESTRUCTURAL
            sizing_mult = 0.0
            log_msg = (
                f"VETO_ESTRUCTURAL for {symbol}: Stage 4 Veto FIRM. Insufficient Causal Evidence "
                f"({counter_veto.causal_score:.2f} < threshold). Dead-cat bounce trap avoided."
            )

    missing_str = f" | UNHEALTHY_VECTORS: {', '.join(missing)}" if missing else ""
    notam_header = (
        f"[NOTAM-CAUSAL] {symbol} | AS_OF: {as_of_str} | AGE: {data_age_hours}h | "
        f"STATUS: {notam_status} | COMPLETENESS: {completeness:.0f}% | "
        f"VALID_UNTIL: {valid_until_str} | DECISION: {decision.value}{missing_str}"
    )

    return CausalVerificationSnapshot(
        symbol=symbol,
        decision=decision,
        sizing_multiplier=sizing_mult,
        structural_veto=structural_veto,
        counter_veto=counter_veto,
        timestamp=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        as_of_timestamp=as_of_str,
        valid_until=valid_until_str,
        data_age_hours=data_age_hours,
        notam_status=notam_status,
        missing_vectors=missing,
        data_completeness_pct=completeness,
        notam_header=notam_header,
        decision_log=f"{notam_header} || {log_msg}",
    )
