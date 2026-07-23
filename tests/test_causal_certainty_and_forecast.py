"""
Unit Tests — Certainty & Credibility Index + 120-Day Probabilistic Forecast
=============================================================================
Tests certainty score calculation, missing vector penalties, data age decay,
consensus bonus, and 120-day empirical forecast projections.
"""
import pytest
from backend.modules.causal_investigation.domain.rules.certainty_rules import compute_certainty_score
from backend.modules.causal_investigation.domain.rules.temporal_trajectory_rules import evaluate_temporal_trajectory
from backend.modules.causal_investigation import CausalInputDTO, evaluate_causal_conviction


def test_certainty_score_full_fresh_data():
    """Test 1: 100% data completeness + 0h age -> Certainty Score 100.0%, HIGH_CERTAINTY."""
    score, grade, note, depts = compute_certainty_score(
        missing_vectors=[],
        data_age_hours=2.0,
        vector_scores=[0.8, 0.75, 0.7, 0.85, 0.8],  # 5 agreeing bullish vectors -> Consensus bonus
        notam_status="FRESH",
    )
    assert score == 100.0
    assert grade == "HIGH_CERTAINTY"
    assert depts["quality_certainty_score"] == 100.0
    assert depts["speculative_certainty_score"] == 100.0
    assert "Consensus" in note or "Full Vector" in note


def test_certainty_score_missing_options_and_aging():
    """Test 2: Missing Options Flow -> Quality Gate certainty stays 100.0%, Speculative Gate drops to 70.0%."""
    score, grade, note, depts = compute_certainty_score(
        missing_vectors=["OPTIONS_DARKPOOL_FLOW"],
        data_age_hours=0.0,
        vector_scores=[0.5, 0.5, 0.5, 0.5],
        notam_status="FRESH",
    )
    assert score == 85.0  # 100 - 15 = 85.0
    assert depts["quality_certainty_score"] == 100.0      # Quality Gate ignores missing 5M option flow!
    assert depts["speculative_certainty_score"] == 70.0    # Speculative Gate suffers heavy -30% penalty!
    assert "Missing OPTIONS_DARKPOOL_FLOW" in note


def test_forecast_projections_pullback_accumulation():
    """Test 3: PULLBACK_ACCUMULATION trajectory forecast (81.2% WR, +14.43% 120d fwd return)."""
    snap = evaluate_temporal_trajectory(
        symbol="NVDA",
        weinstein_stage_1m=2,
        s5_th_1w=65.0,
        vol_div_1d=18.0,
        rsi_1d=35.0,
        sweeps_1h_count=5,
        pcr_5m_bars=[1.35, 1.45, 1.55],
        data_age_5m_mins=8.0,
    )
    assert snap.forecast_fwd_return_120d == 0.1443
    assert snap.win_rate_probability == 0.812
    assert snap.forecast_horizon_days == 120


def test_notam_ticker_payload_with_certainty_and_forecast():
    """Test 4: Full Causal Engine evaluation produces NOTAMTickerPayload with Certainty & Forecast fields."""
    uptrend_prices = [100.0 + i * 0.5 for i in range(160)]
    input_dto = CausalInputDTO(
        symbol="XLK",
        price_history=uptrend_prices,
        rs_score=0.25,
        uw_sweep_count=12,
        uw_net_premium=1_500_000.0,
        fred_macro_snapshot={"macro_regime": "risk_on"},
        s5_th=68.0,
        insider_activity={"signal": "buy"},
        news_sentiment_score=0.7,
        skew_val=130.0,
        vvix_val=84.0,
    )

    snapshot = evaluate_causal_conviction(input_dto)
    payload = snapshot.notam_ticker_payload
    assert payload is not None
    assert payload.certainty_score >= 85.0
    assert payload.certainty_grade == "HIGH_CERTAINTY"
    assert payload.forecast_trajectory == "ALIGNMENT_BULLISH"
    assert payload.forecast_win_rate_120d == 0.845
    assert payload.forecast_fwd_return_120d == 0.1820
    assert payload.forecast_horizon_days == 120

    dict_repr = snapshot.to_dict()["notam_ticker_payload"]
    assert dict_repr["certainty_score"] >= 85.0
    assert dict_repr["forecast_fwd_return_120d"] == 0.1820
