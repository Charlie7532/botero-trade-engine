"""
Evaluate Causal Conviction Use Case
===================================
Application orchestrator for the Causal Investigation Engine.

Receives a concentrated CausalInputDTO prepared by the Vault Daemon,
evaluates Stan Weinstein's Structural Veto and Stanley Druckenmiller's
Counter-Veto, and returns a final CausalVerificationSnapshot.

Pure domain orchestrator — zero I/O, zero external dependencies.
"""
from backend.modules.shared.domain.rules.weinstein_stage_rules import (
    classify_weinstein_stage,
    compute_weinstein_ma_metrics,
)
from backend.modules.causal_investigation.domain.dtos.causal_dtos import CausalInputDTO
from backend.modules.causal_investigation.domain.entities.weinstein_stage import (
    WeinsteinStage,
    StructuralVeto,
)
from backend.modules.causal_investigation.domain.rules.druckenmiller_causal_rules import (
    evaluate_druckenmiller_counter_veto as eval_druckenmiller,
)
from backend.modules.causal_investigation.domain.rules.causal_synthesis_rules import (
    synthesize_causal_decision,
)
from backend.modules.causal_investigation.domain.entities.causal_verification import (
    CausalVerificationSnapshot,
)


def evaluate_causal_conviction(
    input_dto: CausalInputDTO,
    override_threshold: float = 0.70,
) -> CausalVerificationSnapshot:
    """
    Evaluates causal conviction for a symbol.

    Args:
        input_dto: CausalInputDTO with all pre-loaded market, flow, macro, insider, and news data.
        override_threshold: Threshold required for Druckenmiller Counter-Veto (default 0.70).

    Returns:
        CausalVerificationSnapshot with full decision context.
    """
    symbol = input_dto.symbol

    # 1. Weinstein Stage Analysis
    stage_val = classify_weinstein_stage(input_dto.price_history, input_dto.rs_score)
    stage_enum = WeinsteinStage(stage_val)

    curr_price, ma150, ma_slope = compute_weinstein_ma_metrics(input_dto.price_history)

    # Veto holds if Stage 4 (Declining) or Stage 3 with negative slope
    is_vetoed = (stage_val == 4) or (stage_val == 3 and ma_slope < 0)
    veto_rationale = f"Stage {stage_enum.label} (MA150={ma150:.2f}, Slope={ma_slope:.2f}, RS={input_dto.rs_score:.2f})"

    structural_veto = StructuralVeto(
        symbol=symbol,
        stage=stage_enum,
        is_vetoed=is_vetoed,
        current_price=curr_price,
        ma_150=ma150,
        ma_slope=ma_slope,
        rs_score=input_dto.rs_score,
        rationale=veto_rationale,
    )

    # 2. Druckenmiller Causal Counter-Veto
    counter_veto = eval_druckenmiller(
        symbol=symbol,
        uw_flow_alerts=input_dto.uw_flow_alerts,
        uw_net_premium=input_dto.uw_net_premium,
        uw_sweep_count=input_dto.uw_sweep_count,
        fred_macro_snapshot=input_dto.fred_macro_snapshot,
        insider_activity=input_dto.insider_activity,
        s5_th=input_dto.s5_th,
        s5_fi=input_dto.s5_fi,
        s5_tw=input_dto.s5_tw,
        sv5_tw=input_dto.sv5_tw,
        vol_div=input_dto.vol_div,
        fg_score=input_dto.fg_score,
        vix_zscore=input_dto.vix_zscore,
        vix_val=input_dto.vix_val,
        cboe_pcr=input_dto.cboe_pcr,
        skew_val=input_dto.skew_val,
        vvix_val=input_dto.vvix_val,
        news_sentiment_score=input_dto.news_sentiment_score,
        override_threshold=override_threshold,
    )

    # 3. Synthesis
    snapshot = synthesize_causal_decision(
        symbol=symbol,
        structural_veto=structural_veto,
        counter_veto=counter_veto,
        as_of_dt=input_dto.as_of_dt,
    )

    return snapshot
