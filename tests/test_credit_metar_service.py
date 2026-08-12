"""
Unit Tests for CreditMetarService (Credit Stress Intelligence)
================================================================
Verifica el comportamiento del Credit METAR Service:
  - Clasificación en los regímenes empíricos de crédito.
  - Tolerancia y política estricta ante falta de datos (StrictDataPolicyError).
  - Persistencia de StateSnapshot vía RegimeStatePort (clave: credit:entry_decision:MARKET).
  - Formateo de difusión CLI / Broadcast.
"""
import pytest
from unittest.mock import MagicMock
import pandas as pd

from backend.modules.entry_decision.domain.services.credit_metar_service import (
    CreditMetarService,
    StrictDataPolicyError,
    MarketMETAR,
    get_credit_market_metar,
)


@pytest.fixture
def mock_store():
    store = MagicMock()
    return store


@pytest.fixture
def mock_port():
    port = MagicMock()
    return port


def test_credit_metar_service_strict_error_on_empty(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: pd.DataFrame())
        svc = CreditMetarService(data_store=mock_store, regime_state_port=mock_port)
        
        with pytest.raises(StrictDataPolicyError) as exc_info:
            svc.evaluate("2026-07-31")
        assert "METAR NOT AVAILABLE" in str(exc_info.value)


def test_credit_metar_service_expansion(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    dates = pd.date_range(end="2026-07-31", periods=10, freq="D")
    df_hyg = pd.DataFrame({"date": dates, "ticker": "HYG", "close": 78.0})
    df_lqd = pd.DataFrame({"date": dates, "ticker": "LQD", "close": 105.0})
    df = pd.concat([df_hyg, df_lqd])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df)
        svc = CreditMetarService(data_store=mock_store, regime_state_port=mock_port)
        metar = svc.evaluate("2026-07-31")

        assert isinstance(metar, MarketMETAR)
        assert metar.action_code in [
            "MKT_CREDIT_EXPANSION_STABLE",
            "MKT_CREDIT_STRESS_ELEVATED",
            "MKT_CREDIT_FREEZE_EXTREME",
        ]
        assert metar.credit_ratio_value == pytest.approx(78.0 / 105.0, rel=1e-3)
        assert mock_port.commit_transition.called
        assert mock_port.commit_transition.call_args[1]["key"] == "credit:entry_decision:MARKET"


def test_credit_metar_service_freeze(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    dates = pd.date_range(end="2026-07-31", periods=10, freq="D")
    # Low ratio HYG/LQD = 50.0 / 100.0 = 0.50 (CREDIT_CRISIS)
    df_hyg = pd.DataFrame({"date": dates, "ticker": "HYG", "close": 50.0})
    df_lqd = pd.DataFrame({"date": dates, "ticker": "LQD", "close": 100.0})
    df = pd.concat([df_hyg, df_lqd])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df)
        svc = CreditMetarService(data_store=mock_store, regime_state_port=mock_port)
        metar = svc.evaluate("2026-07-31")

        assert metar.action_code == "MKT_CREDIT_FREEZE_EXTREME"
        assert metar.is_crisis_override is True
        assert metar.credit_bin == "CREDIT_CRISIS"


def test_credit_metar_cli_broadcast(mock_store, mock_port):
    conn = MagicMock()
    mock_store._conn.return_value = conn

    dates = pd.date_range(end="2026-07-31", periods=10, freq="D")
    df_hyg = pd.DataFrame({"date": dates, "ticker": "HYG", "close": 70.0})
    df_lqd = pd.DataFrame({"date": dates, "ticker": "LQD", "close": 100.0})
    df = pd.concat([df_hyg, df_lqd])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pd, "read_sql", lambda q, c: df)
        svc = CreditMetarService(data_store=mock_store, regime_state_port=mock_port)
        metar = svc.evaluate("2026-07-31")

        broadcast = metar.format_cli_broadcast()
        assert "MARKET METAR — CREDIT STRESS RATIO" in broadcast
        assert "LIVE TELEMETRY" in broadcast
        assert "OPERATIONAL DIRECTIVES" in broadcast
