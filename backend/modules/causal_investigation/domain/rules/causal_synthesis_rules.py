"""
Causal Synthesis Rules — NOTAM Aviation & Structured Ticker Payload Protocol
================================================================================
Synthesizes Weinstein's Structural Veto and Druckenmiller's Causal Counter-Veto
into a final CausalVerificationSnapshot with NOTAM aviation timestamp, missing vector metadata,
and a pre-digested numerical NOTAMTickerPayload.
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
    NOTAMTickerPayload,
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

    Calculates Aviation NOTAM Timestamp & Structured Ticker Payload:
      - as_of_timestamp: Issuance time of data (UTC).
      - valid_until: Expiration time (as_of + valid_hours).
      - data_age_hours: Age of data in hours relative to execution time.
      - notam_status: FRESH (<24h), AGING (24-48h), STALE (48-72h), EXPIRED (>72h).
      - missing_vectors: Explicit list of missing data vectors.
      - data_completeness_pct: Percentage of causal vectors loaded (0-100%).
      - notam_header: NOTAM format string.
      - notam_ticker_payload: Pre-digested numerical bar for immediate gate consumption.
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

    # Department-Calibrated Sizing Multipliers
    quality_sizing = sizing_mult if decision != CausalDecision.VETO_ESTRUCTURAL else 0.0
    # Speculative Hub gets aggressive multiplier up to 1.50x if options flow sweeps >= 10
    spec_mult = sizing_mult
    if counter_veto.evidence_matrix.options_darkpool_score >= 0.8:
        spec_mult = min(1.50, spec_mult * 1.20)
    speculative_sizing = spec_mult if decision != CausalDecision.VETO_ESTRUCTURAL else 0.0

    details = counter_veto.evidence_matrix.details
    vix_z = float(details.get("vix_zscore", 0.0))
    vix_val = float(details.get("vix_val", 18.0))
    vvix_val = float(details.get("vvix_val", 85.0))
    vvix_vix_ratio = round(vvix_val / max(1.0, vix_val), 4)

    # Calculate Certainty & Credibility Index
    from backend.modules.causal_investigation.domain.rules.certainty_rules import compute_certainty_score
    vec_scores = [
        counter_veto.evidence_matrix.options_darkpool_score,
        counter_veto.evidence_matrix.macro_liquidity_score,
        counter_veto.evidence_matrix.insider_accumulation_score,
        counter_veto.evidence_matrix.volume_reabsorption_score,
        counter_veto.evidence_matrix.narrative_momentum_score,
    ]
    cert_score, cert_grade, cert_note, dept_cert = compute_certainty_score(
        missing_vectors=missing,
        data_age_hours=data_age_hours,
        vector_scores=vec_scores,
        notam_status=notam_status,
    )

    # Forecast Trajectory Snapshot
    from backend.modules.causal_investigation.domain.rules.temporal_trajectory_rules import evaluate_temporal_trajectory
    traj_snap = evaluate_temporal_trajectory(
        symbol=symbol,
        weinstein_stage_1m=structural_veto.stage.value,
        s5_th_1w=float(details.get("s5_th", 50.0)),
        vol_div_1d=float(details.get("vol_div", 0.0)),
        sweeps_1h_count=int(details.get("uw_sweeps", 0)),
        data_age_5m_mins=data_age_hours * 60.0,
        macro_liquidity_score=counter_veto.evidence_matrix.macro_liquidity_score,
    )

    ticker_payload = NOTAMTickerPayload(
        symbol=symbol,
        as_of_timestamp=as_of_str,
        valid_until=valid_until_str,
        data_age_hours=data_age_hours,
        notam_status=notam_status,
        data_completeness_pct=completeness,
        missing_vectors=missing,
        decision=decision.value,
        weinstein_stage_code=structural_veto.stage.value,
        causal_score=counter_veto.causal_score,
        quality_sizing_mult=round(quality_sizing, 4),
        speculative_sizing_mult=round(speculative_sizing, 4),
        skew_index=float(details.get("skew_val", 120.0)),
        vvix_vix_ratio=vvix_vix_ratio,
        vix_zscore=vix_z,
        cboe_pcr=float(details.get("cboe_pcr", 1.0)),
        fg_score=float(details.get("fg_score", 50.0)),
        certainty_score=cert_score,
        certainty_grade=cert_grade,
        quality_certainty_score=dept_cert["quality_certainty_score"],
        swing_certainty_score=dept_cert["swing_certainty_score"],
        speculative_certainty_score=dept_cert["speculative_certainty_score"],
        data_uncertainty_note=cert_note,
        forecast_trajectory=traj_snap.trajectory_state.value,
        forecast_win_rate_120d=traj_snap.win_rate_probability,
        forecast_fwd_return_120d=traj_snap.forecast_fwd_return_120d,
        forecast_horizon_days=120,
        options_flow_score=counter_veto.evidence_matrix.options_darkpool_score,
        macro_liquidity_score=counter_veto.evidence_matrix.macro_liquidity_score,
        insider_score=counter_veto.evidence_matrix.insider_accumulation_score,
        volume_reabsorption_score=counter_veto.evidence_matrix.volume_reabsorption_score,
        news_sentiment_score=counter_veto.evidence_matrix.narrative_momentum_score,
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
        notam_ticker_payload=ticker_payload,
        decision_log=f"{notam_header} || {log_msg}",
    )
