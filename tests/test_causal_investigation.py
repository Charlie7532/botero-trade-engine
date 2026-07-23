"""
Unit Tests — Causal Investigation Engine Module
===============================================
Tests Stan Weinstein Stage analysis, Stanley Druckenmiller 5-vector Causal Counter-Veto,
and Causal Decision synthesis. Zero network, zero DB.
"""
import pytest
from backend.modules.shared.domain.rules.weinstein_stage_rules import (
    classify_weinstein_stage,
    compute_weinstein_ma_metrics,
)
from backend.modules.causal_investigation import (
    CausalInputDTO,
    CausalDecision,
    WeinsteinStage,
    evaluate_causal_conviction,
)
from backend.modules.causal_investigation.domain.rules.druckenmiller_causal_rules import (
    evaluate_druckenmiller_counter_veto,
)


def test_shared_weinstein_stage_classification():
    """Test 1: Shared Weinstein Stage classification rule."""
    # 150 prices in steady uptrend (Stage 2)
    uptrend_prices = [100.0 + i * 0.5 for i in range(160)]
    stage = classify_weinstein_stage(uptrend_prices, rs=0.2)
    assert stage == 2  # Advancing

    # 160 prices in severe downtrend (Stage 4)
    downtrend_prices = [200.0 - i * 0.8 for i in range(160)]
    stage = classify_weinstein_stage(downtrend_prices, rs=-0.3)
    assert stage == 4  # Declining

    # Less than 150 prices returns 0
    assert classify_weinstein_stage([100.0] * 50) == 0


def test_druckenmiller_counter_veto_low_evidence():
    """Test 2: Druckenmiller Counter-Veto with weak evidence score < 0.70."""
    res = evaluate_druckenmiller_counter_veto(
        symbol="XLK",
        uw_sweep_count=1,
        uw_net_premium=0.0,
        fred_macro_snapshot={"macro_regime": "neutral"},
        insider_activity={"signal": "neutral"},
        vol_div=2.0,
        news_sentiment_score=0.0,
    )
    assert res.is_overridden is False
    assert res.causal_score < 0.70
    assert res.conviction_level in ("NONE", "LOW")


def test_druckenmiller_counter_veto_high_evidence():
    """Test 3: Druckenmiller Counter-Veto with strong multi-vector evidence score >= 0.70."""
    res = evaluate_druckenmiller_counter_veto(
        symbol="XLK",
        uw_sweep_count=12,
        uw_net_premium=2_500_000.0,
        fred_macro_snapshot={"macro_regime": "risk_on", "net_liquidity_trend": "easing", "fed_stance": "dovish"},
        insider_activity={"signal": "strong_buy"},
        s5_th=70.0,
        s5_fi=40.0,
        sv5_tw=75.0,
        vol_div=20.0,
        news_sentiment_score=0.8,
    )
    assert res.is_overridden is True
    assert res.causal_score >= 0.70
    assert res.conviction_level == "HIGH"
    assert res.sizing_factor >= 1.0


def test_causal_engine_dead_cat_bounce_prevented():
    """Test 4: Stage 4 sector with low causal evidence -> VETO_ESTRUCTURAL."""
    downtrend_prices = [200.0 - i * 0.8 for i in range(160)]
    input_dto = CausalInputDTO(
        symbol="XLV",
        price_history=downtrend_prices,
        rs_score=-0.25,
        uw_sweep_count=1,
        vol_div=0.0,
        news_sentiment_score=-0.2,
    )

    snapshot = evaluate_causal_conviction(input_dto)
    assert snapshot.decision == CausalDecision.VETO_ESTRUCTURAL
    assert snapshot.structural_veto.stage == WeinsteinStage.STAGE_4_DECLINING
    assert snapshot.structural_veto.is_vetoed is True
    assert snapshot.counter_veto.is_overridden is False
    assert snapshot.sizing_multiplier == 0.0


def test_causal_engine_paradigm_shift_unlocked():
    """Test 5: Stage 4 sector with massive institutional/macro/news evidence -> CONTRA_VETO_CAUSAL."""
    downtrend_prices = [200.0 - i * 0.8 for i in range(160)]
    input_dto = CausalInputDTO(
        symbol="XLV",
        price_history=downtrend_prices,
        rs_score=-0.25,
        uw_sweep_count=15,
        uw_net_premium=3_000_000.0,
        fred_macro_snapshot={"macro_regime": "risk_on", "net_liquidity_trend": "easing", "fed_stance": "dovish"},
        insider_activity={"signal": "cluster_buy"},
        s5_th=65.0,
        s5_fi=35.0,
        sv5_tw=70.0,
        vol_div=25.0,
        news_sentiment_score=0.9,
    )

    snapshot = evaluate_causal_conviction(input_dto)
    assert snapshot.decision == CausalDecision.CONTRA_VETO_CAUSAL
    assert snapshot.structural_veto.is_vetoed is True
    assert snapshot.counter_veto.is_overridden is True
    assert snapshot.sizing_multiplier >= 1.0


def test_causal_engine_advancing_stage_allowed():
    """Test 6: Stage 2 advancing sector -> ALLOW_ENTRY."""
    uptrend_prices = [100.0 + i * 0.5 for i in range(160)]
    input_dto = CausalInputDTO(
        symbol="XLK",
        price_history=uptrend_prices,
        rs_score=0.3,
    )

    snapshot = evaluate_causal_conviction(input_dto)
    assert snapshot.decision == CausalDecision.ALLOW_ENTRY
    assert snapshot.structural_veto.stage == WeinsteinStage.STAGE_2_ADVANCING
    assert snapshot.structural_veto.is_vetoed is False
    assert snapshot.sizing_multiplier > 0.0


def test_notam_aviation_timestamp_protocol():
    """Test 7: NOTAM Aviation Timestamp Protocol (as_of, valid_until, notam_status, notam_header)."""
    from datetime import datetime, timedelta, UTC
    as_of = datetime.now(UTC) - timedelta(hours=2)

    uptrend_prices = [100.0 + i * 0.5 for i in range(160)]
    input_dto = CausalInputDTO(
        symbol="XLK",
        price_history=uptrend_prices,
        rs_score=0.3,
        as_of_dt=as_of,
    )

    snapshot = evaluate_causal_conviction(input_dto)
    assert snapshot.notam_status == "FRESH"
    assert snapshot.data_age_hours == 2.0
    assert "[NOTAM-CAUSAL] XLK" in snapshot.notam_header
    assert "STATUS: FRESH" in snapshot.notam_header
    assert "VALID_UNTIL:" in snapshot.notam_header
    assert snapshot.to_dict()["notam_status"] == "FRESH"


def test_missing_vectors_reporting():
    """Test 8: Explicit reporting of missing vectors and data completeness percentage."""
    uptrend_prices = [100.0 + i * 0.5 for i in range(160)]
    # Provide Options flow (uw_sweep_count=5), but NO FRED, NO Insiders, NO News Sentiment
    input_dto = CausalInputDTO(
        symbol="XLE",
        price_history=uptrend_prices,
        rs_score=0.1,
        uw_sweep_count=5,
        fred_macro_snapshot=None,
        insider_activity=None,
        news_sentiment_score=0.0,
    )

    snapshot = evaluate_causal_conviction(input_dto)
    assert "FRED_MACRO_LIQUIDITY" in snapshot.missing_vectors
    assert "CORPORATE_INSIDER_ACTIVITY" in snapshot.missing_vectors
    assert "NEWS_SENTIMENT_FINBERT" in snapshot.missing_vectors
    assert snapshot.data_completeness_pct == 40.0  # 2 of 5 available
    assert "COMPLETENESS: 40%" in snapshot.notam_header
    assert "UNHEALTHY_VECTORS:" in snapshot.notam_header
    dict_repr = snapshot.to_dict()
    assert dict_repr["data_completeness_pct"] == 40.0
    assert "FRED_MACRO_LIQUIDITY" in dict_repr["missing_vectors"]


